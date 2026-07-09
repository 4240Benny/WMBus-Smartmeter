# Derived from python-cc1101, Copyright (C) 2020 Fabian Peter Hammerle
# <fabian@hammerle.me>, licensed under the GNU General Public License v3
# or any later version. https://github.com/fphammerle/python-cc1101
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.

"""CC1101 driver for receiving wireless M-Bus mode T frames.

The receive strategy follows TI application note AN067 (SWRA234a, "Wireless
MBUS implementation with CC1101"): the radio starts in infinite packet
length mode, the L-field of the frame is decoded from the first bytes in the
RX FIFO to compute the total on-air frame size, and the radio is switched to
fixed packet length mode so that reception stops exactly at the end of the
frame.

Wiring (defaults, matching the python-cc1101 README):

    CC1101 SPI   -> Raspberry Pi SPI0 (MOSI/MISO/SCLK/CE0)
    CC1101 GDO0  -> GPIO 24  (asserted while RX FIFO is at/above threshold)
    CC1101 GDO2  -> GPIO 25  (asserted from sync word until end of packet)
"""

from __future__ import annotations

import dataclasses
import logging
import time

import spidev

from meterreader import encoding, frame
from meterreader.errors import FrameDecodeError, RadioError
from meterreader.gpio import GdoPins
from meterreader.registers import (
    ConfigReg,
    FIFO_ADDRESS,
    MarcState,
    PacketLengthMode,
    StatusReg,
    Strobe,
)

_LOGGER = logging.getLogger(__name__)

# SPI header bits (table 45)
_WRITE_BURST = 0x40
_READ_SINGLE = 0x80
_READ_BURST = 0xC0

_CRYSTAL_FREQUENCY_HZ = 26e6
_FREQUENCY_STEP_HZ = _CRYSTAL_FREQUENCY_HZ / 2**16

_SUPPORTED_PARTNUM = 0x00
_SUPPORTED_VERSIONS = (0x04, 0x14)

_FIFO_SIZE = 64
# Never drain the RX FIFO completely while reception is ongoing
# (single-byte-over-SPI errata); the final bytes are read after the packet
# has ended.
_FIFO_CHUNK = 31

# Base configuration for wM-Bus mode T reception (values from TI SWRA234a /
# SmartRF Studio). FREQ2..FREQ0 are computed from the configured frequency.
_TMODE_CONFIG = (
    (ConfigReg.IOCFG2, 0x06),  # GDO2: sync word received ... end of packet
    (ConfigReg.IOCFG1, 0x2E),  # GDO1: high impedance (pin unused)
    (ConfigReg.IOCFG0, 0x00),  # GDO0: RX FIFO at or above threshold
    (ConfigReg.FIFOTHR, 0x07),  # RX FIFO threshold 32 bytes
    (ConfigReg.SYNC1, 0x54),  # mode T sync word (end of preamble sequence)
    (ConfigReg.SYNC0, 0x3D),
    (ConfigReg.PKTLEN, 0xFF),
    (ConfigReg.PKTCTRL1, 0x04),  # no addr check, append RSSI/LQI status bytes
    (ConfigReg.PKTCTRL0, 0x00),  # fixed length, CRC disabled, use FIFO
    (ConfigReg.ADDR, 0x00),
    (ConfigReg.CHANNR, 0x00),
    (ConfigReg.FSCTRL1, 0x08),  # IF frequency
    (ConfigReg.FSCTRL0, 0x00),
    (ConfigReg.MDMCFG4, 0x5C),  # RX filter BW 325 kHz, data rate exponent
    (ConfigReg.MDMCFG3, 0x04),  # data rate mantissa -> 103 kBaud
    (ConfigReg.MDMCFG2, 0x05),  # 2-FSK, 15/16 sync word bits detected
    (ConfigReg.MDMCFG1, 0x22),  # 4 preamble bytes, FEC disabled
    (ConfigReg.MDMCFG0, 0xF8),
    (ConfigReg.DEVIATN, 0x44),  # ~38 kHz deviation
    (ConfigReg.MCSM2, 0x07),
    (ConfigReg.MCSM1, 0x00),  # go to IDLE after a packet was received
    (ConfigReg.MCSM0, 0x18),  # auto-calibrate when going from IDLE to RX
    (ConfigReg.FOCCFG, 0x2E),  # frequency offset compensation
    (ConfigReg.BSCFG, 0xBF),  # bit synchronization
    (ConfigReg.AGCCTRL2, 0x43),
    (ConfigReg.AGCCTRL1, 0x09),
    (ConfigReg.AGCCTRL0, 0xB5),
    (ConfigReg.WOREVT1, 0x87),
    (ConfigReg.WOREVT0, 0x6B),
    (ConfigReg.WORCTRL, 0xFB),
    (ConfigReg.FREND1, 0xB6),
    (ConfigReg.FREND0, 0x10),
    (ConfigReg.FSCAL3, 0xEA),
    (ConfigReg.FSCAL2, 0x2A),
    (ConfigReg.FSCAL1, 0x00),
    (ConfigReg.FSCAL0, 0x1F),
    (ConfigReg.RCCTRL1, 0x41),
    (ConfigReg.RCCTRL0, 0x00),
    (ConfigReg.FSTEST, 0x59),
    (ConfigReg.PTEST, 0x7F),
    (ConfigReg.AGCTEST, 0x3F),
    (ConfigReg.TEST2, 0x81),
    (ConfigReg.TEST1, 0x35),
    (ConfigReg.TEST0, 0x09),
)


@dataclasses.dataclass(frozen=True)
class ReceivedFrame:
    encoded: bytes
    """The raw "3 out of 6" encoded frame as read from the RX FIFO."""
    rssi_dbm: float | None
    lqi: int | None


def _rssi_to_dbm(raw: int) -> float:
    """Convert the RSSI status byte to dBm (data sheet section 17.3)."""
    return (raw - 256 if raw >= 128 else raw) / 2 - 74


class CC1101TModeReceiver:
    """Receives wM-Bus mode T frames; use as a context manager."""

    def __init__(
        self,
        spi_bus: int = 0,
        spi_chip_select: int = 0,
        spi_speed_hz: int = 10_000_000,
        gpio_chip: int = 0,
        gdo0_gpio: int = 24,
        gdo2_gpio: int = 25,
        frequency_hz: float = 868_950_000.0,
    ) -> None:
        self._spi = spidev.SpiDev()
        self._spi_bus = spi_bus
        self._spi_chip_select = spi_chip_select
        self._spi_speed_hz = spi_speed_hz
        self._gpio_chip = gpio_chip
        self._gdo0_gpio = gdo0_gpio
        self._gdo2_gpio = gdo2_gpio
        self._frequency_hz = frequency_hz
        self._pins: GdoPins | None = None

    # --- SPI primitives ---------------------------------------------------

    def _strobe(self, strobe: Strobe) -> None:
        self._spi.xfer([strobe])

    def _write_register(self, register: ConfigReg, value: int) -> None:
        self._spi.xfer([register | _WRITE_BURST, value])

    def _read_register(self, register: ConfigReg) -> int:
        return self._spi.xfer([register | _READ_SINGLE, 0])[1]

    def _read_status_register(self, register: StatusReg) -> int:
        # status registers are read with the burst bit set (section 10.5)
        return self._spi.xfer([register | _READ_BURST, 0])[1]

    def _read_rx_fifo(self, length: int) -> bytes:
        return bytes(self._spi.xfer([FIFO_ADDRESS | _READ_BURST] + [0] * length)[1:])

    # --- setup ------------------------------------------------------------

    def __enter__(self) -> "CC1101TModeReceiver":
        try:
            self._spi.open(self._spi_bus, self._spi_chip_select)
        except (OSError, PermissionError) as exc:
            raise RadioError(
                f"cannot open /dev/spidev{self._spi_bus}.{self._spi_chip_select}:"
                f" {exc}"
            ) from exc
        try:
            self._spi.max_speed_hz = self._spi_speed_hz
            self._reset()
            self._verify_chip()
            self._configure()
            self._pins = GdoPins(self._gpio_chip, self._gdo0_gpio, self._gdo2_gpio)
        except Exception:
            self._spi.close()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if self._pins is not None:
            self._pins.close()
            self._pins = None
        try:
            self._strobe(Strobe.SIDLE)
        except Exception:  # noqa: BLE001 - best effort during teardown
            pass
        self._spi.close()
        return False

    def _reset(self) -> None:
        self._strobe(Strobe.SRES)
        time.sleep(0.01)
        self._strobe(Strobe.SIDLE)

    def _verify_chip(self) -> None:
        partnum = self._read_status_register(StatusReg.PARTNUM)
        version = self._read_status_register(StatusReg.VERSION)
        if version in (0x00, 0xFF):
            raise RadioError(
                f"unexpected chip version {version:#04x} - check the SPI wiring"
                " and bus/chip-select configuration"
            )
        if partnum != _SUPPORTED_PARTNUM or version not in _SUPPORTED_VERSIONS:
            _LOGGER.warning(
                "unexpected chip part number %#04x / version %#04x", partnum, version
            )

    def _configure(self) -> None:
        for register, value in _TMODE_CONFIG:
            self._write_register(register, value)
        frequency_word = round(self._frequency_hz / _FREQUENCY_STEP_HZ)
        for register, shift in (
            (ConfigReg.FREQ2, 16),
            (ConfigReg.FREQ1, 8),
            (ConfigReg.FREQ0, 0),
        ):
            self._write_register(register, (frequency_word >> shift) & 0xFF)
        marcstate = self._read_status_register(StatusReg.MARCSTATE)
        if marcstate != MarcState.IDLE:
            raise RadioError(f"radio is not idle after reset (MARCSTATE={marcstate})")
        _LOGGER.info(
            "CC1101 configured for wM-Bus mode T at %.3f MHz",
            frequency_word * _FREQUENCY_STEP_HZ / 1e6,
        )

    def _set_packet_length_mode(self, mode: PacketLengthMode) -> None:
        self._write_register(ConfigReg.PKTCTRL0, mode)

    # --- receiving --------------------------------------------------------

    def receive_frame(self, timeout_seconds: float) -> ReceivedFrame | None:
        """Wait for a frame; returns None if no sync word arrives in time."""
        if self._pins is None:
            raise RadioError("receiver is not open - use it as a context manager")
        self._strobe(Strobe.SIDLE)
        self._strobe(Strobe.SFRX)
        self._write_register(ConfigReg.FIFOTHR, 0x00)  # assert GDO0 at 4 bytes
        self._set_packet_length_mode(PacketLengthMode.INFINITE)
        self._strobe(Strobe.SRX)
        try:
            if not self._pins.wait_for_sync(timeout_seconds):
                return None
            return self._read_packet()
        finally:
            self._strobe(Strobe.SIDLE)
            self._strobe(Strobe.SFRX)

    def _read_packet(self) -> ReceivedFrame | None:
        pins = self._pins
        buffer = bytearray()
        expected: int | None = None
        deadline = time.monotonic() + 2.0

        while pins.read_gdo2():  # asserted until the end of the packet
            if time.monotonic() > deadline:
                raise FrameDecodeError("packet reception did not finish in time")
            if not pins.read_gdo0():  # RX FIFO below threshold
                continue
            if expected is None:
                # Enough of the frame has arrived to decode the L-field and
                # compute the total on-air size.
                buffer += self._read_rx_fifo(3)
                l_field = encoding.decode(bytes(buffer), 1)[0]
                expected = encoding.encoded_size(frame.packet_size(l_field))
                # PKTLEN holds the total size modulo 256; the switch to fixed
                # length mode happens once fewer than 256 bytes are missing.
                self._write_register(ConfigReg.PKTLEN, expected % 256)
                if expected < 256:
                    self._set_packet_length_mode(PacketLengthMode.FIXED)
                self._write_register(ConfigReg.FIFOTHR, 0x07)  # threshold 32
            else:
                if expected >= 256 and expected - len(buffer) < 256:
                    self._set_packet_length_mode(PacketLengthMode.FIXED)
                chunk = min(_FIFO_CHUNK, expected - len(buffer))
                if chunk <= 0:
                    break
                buffer += self._read_rx_fifo(chunk)

        if expected is None:
            _LOGGER.debug("sync word without following data (noise)")
            return None

        # wait for the radio to finish (GDO2 deasserts at the end of packet)
        while pins.read_gdo2():
            if time.monotonic() > deadline:
                raise FrameDecodeError("packet reception did not finish in time")

        rx_bytes = self._read_status_register(StatusReg.RXBYTES)
        if rx_bytes & 0x80:
            raise FrameDecodeError("RX FIFO overflowed during reception")

        remaining = expected - len(buffer)
        if remaining > 0:
            if remaining > _FIFO_SIZE:
                raise FrameDecodeError(
                    f"lost {remaining - (rx_bytes & 0x7F)} bytes of the frame"
                )
            buffer += self._read_rx_fifo(remaining)

        # PKTCTRL1.APPEND_STATUS adds two status bytes after the payload
        rssi_dbm = None
        lqi = None
        if (self._read_status_register(StatusReg.RXBYTES) & 0x7F) >= 2:
            status = self._read_rx_fifo(2)
            rssi_dbm = _rssi_to_dbm(status[0])
            lqi = status[1] & 0x7F
        return ReceivedFrame(encoded=bytes(buffer), rssi_dbm=rssi_dbm, lqi=lqi)

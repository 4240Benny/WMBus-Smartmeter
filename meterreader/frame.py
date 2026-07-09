"""Wireless M-Bus frame handling (EN 13757-4 frame format A).

A frame format A packet is transmitted as CRC-protected blocks:

    block 1:      L-field, C-field, M-field (2), A-field (6)   + CRC (2)
    block 2..n:   up to 16 bytes of payload                    + CRC (2)

The L-field counts all frame bytes except the L-field itself and the CRCs.

After CRC verification and removal, the "telegram" starts with the link
layer header followed by a transport layer (TPL) header identified by the
CI-field, e.g. 0x7A (short header) for the encrypted telegrams sent by many
smart electricity meters.
"""

from __future__ import annotations

import dataclasses

from meterreader import crypto, encoding
from meterreader.crc import crc16_en13757
from meterreader.errors import FrameDecodeError

# CI-field values (EN 13757-7 / OMS)
CI_SHORT_HEADER = 0x7A
CI_LONG_HEADER = 0x72
CI_NO_HEADER = 0x78

_BLOCK1_SIZE = 10
_BLOCK_SIZE = 16
_CRC_SIZE = 2


def num_blocks(l_field: int) -> int:
    """Number of CRC-protected blocks of a frame format A packet."""
    if l_field < 9:
        raise FrameDecodeError(f"L-field {l_field} is too small for a frame")
    payload_bytes = l_field - 9  # L counts C + M + A (9 bytes) + payload
    return 1 + (payload_bytes + _BLOCK_SIZE - 1) // _BLOCK_SIZE


def packet_size(l_field: int) -> int:
    """Total decoded packet size in bytes, including L-field and all CRCs."""
    return l_field + 1 + _CRC_SIZE * num_blocks(l_field)


def verify_and_strip_block_crcs(packet: bytes) -> bytes:
    """Verify the CRC of every block and return the telegram without CRCs.

    `packet` is the full decoded packet starting with the L-field. The
    returned telegram contains L-field, link layer header and payload.
    """
    l_field = packet[0]
    expected = packet_size(l_field)
    if len(packet) < expected:
        raise FrameDecodeError(
            f"packet too short: {len(packet)} bytes, expected {expected}"
        )
    telegram = bytearray()
    position = 0
    block_number = 1
    remaining = l_field + 1  # data bytes including the L-field
    while remaining > 0:
        block_size = _BLOCK1_SIZE if block_number == 1 else min(_BLOCK_SIZE, remaining)
        block = packet[position : position + block_size]
        crc_bytes = packet[position + block_size : position + block_size + _CRC_SIZE]
        received_crc = int.from_bytes(crc_bytes, "big")
        computed_crc = crc16_en13757(block)
        if received_crc != computed_crc:
            raise FrameDecodeError(
                f"CRC mismatch in block {block_number}:"
                f" received {received_crc:#06x}, computed {computed_crc:#06x}"
            )
        telegram += block
        position += block_size + _CRC_SIZE
        remaining -= block_size
        block_number += 1
    return bytes(telegram)


def build_frame_format_a(telegram: bytes) -> bytes:
    """Inverse of `verify_and_strip_block_crcs` (used for building test data)."""
    packet = bytearray()
    position = 0
    block_number = 1
    while position < len(telegram):
        block_size = _BLOCK1_SIZE if block_number == 1 else _BLOCK_SIZE
        block = telegram[position : position + block_size]
        packet += block
        packet += crc16_en13757(block).to_bytes(_CRC_SIZE, "big")
        position += len(block)
        block_number += 1
    return bytes(packet)


def manufacturer_code_to_string(code: int) -> str:
    """Decode a 16-bit M-field into the three-letter FLAG manufacturer ID."""
    return "".join(
        chr(((code >> shift) & 0x1F) + ord("@")) for shift in (10, 5, 0)
    )


@dataclasses.dataclass(frozen=True)
class Telegram:
    """A parsed (and, if applicable, decrypted) wireless M-Bus telegram."""

    l_field: int
    c_field: int
    manufacturer_code: int
    manufacturer: str
    device_id: str  # meter address as printed on the meter, e.g. "12345678"
    version: int
    device_type: int
    ci_field: int
    access_number: int | None
    status: int | None
    configuration: int | None
    encryption_mode: int
    payload: bytes
    """Application payload (M-Bus data records).

    For encrypted telegrams this is the decrypted plaintext, still including
    the leading 0x2F2F decryption-check bytes and any trailing 0x2F idle
    fillers; the record parser skips those.
    """


def decode_packet(encoded: bytes) -> bytes:
    """3-out-of-6 decode a received buffer into a CRC-stripped telegram."""
    l_field = encoding.decode(encoded, 1)[0]
    packet = encoding.decode(encoded, packet_size(l_field))
    return verify_and_strip_block_crcs(packet)


def parse_telegram(telegram: bytes, key: bytes | None = None) -> Telegram:
    """Parse a CRC-stripped telegram, decrypting the payload if necessary."""
    if len(telegram) < 11:
        raise FrameDecodeError(f"telegram too short: {len(telegram)} bytes")
    l_field = telegram[0]
    if len(telegram) != l_field + 1:
        raise FrameDecodeError(
            f"telegram length {len(telegram)} does not match L-field {l_field}"
        )
    c_field = telegram[1]
    manufacturer_code = int.from_bytes(telegram[2:4], "little")
    address = telegram[2:10]  # M-field + ID + version + device type
    device_id = telegram[4:8][::-1].hex()
    version = telegram[8]
    device_type = telegram[9]
    ci_field = telegram[10]

    access_number = None
    status = None
    configuration = None
    encryption_mode = 0

    if ci_field == CI_NO_HEADER:
        payload = telegram[11:]
    elif ci_field in (CI_SHORT_HEADER, CI_LONG_HEADER):
        if ci_field == CI_SHORT_HEADER:
            header_end = 11
        else:
            # The long header repeats the meter address (ID, M, version,
            # type); for encryption it takes precedence over the link layer.
            header_end = 19
            address = telegram[15:17] + telegram[11:15] + telegram[17:19]
            device_id = telegram[11:15][::-1].hex()
        try:
            access_number = telegram[header_end]
            status = telegram[header_end + 1]
            configuration = int.from_bytes(
                telegram[header_end + 2 : header_end + 4], "little"
            )
        except IndexError:
            raise FrameDecodeError("telegram too short for TPL header") from None
        payload = telegram[header_end + 4 :]
        encryption_mode = (configuration >> 8) & 0x1F
        if encryption_mode == 5:
            encrypted_length = 16 * ((configuration >> 4) & 0x0F)
            if encrypted_length > len(payload):
                raise FrameDecodeError(
                    f"configuration word announces {encrypted_length} encrypted"
                    f" bytes but payload has only {len(payload)}"
                )
            if key is None:
                raise FrameDecodeError(
                    "telegram is encrypted (mode 5) but no AES key is configured"
                )
            iv = crypto.mode5_iv(address, access_number)
            plaintext = crypto.decrypt_mode5(payload[:encrypted_length], key, iv)
            payload = plaintext + payload[encrypted_length:]
        elif encryption_mode != 0:
            raise FrameDecodeError(
                f"unsupported encryption mode {encryption_mode}"
            )
    else:
        raise FrameDecodeError(f"unsupported CI-field {ci_field:#04x}")

    return Telegram(
        l_field=l_field,
        c_field=c_field,
        manufacturer_code=manufacturer_code,
        manufacturer=manufacturer_code_to_string(manufacturer_code),
        device_id=device_id,
        version=version,
        device_type=device_type,
        ci_field=ci_field,
        access_number=access_number,
        status=status,
        configuration=configuration,
        encryption_mode=encryption_mode,
        payload=payload,
    )

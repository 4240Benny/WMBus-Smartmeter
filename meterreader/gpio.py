"""Access to the CC1101 GDO output pins via the Linux GPIO character device.

Uses the `lgpio` library, which works on all recent Raspberry Pi models
(including kernels where the deprecated sysfs GPIO interface is gone).
"""

from __future__ import annotations

import threading

import lgpio

from meterreader.errors import RadioError


class GdoPins:
    """Reads the CC1101 GDO0/GDO2 pins; GDO2 edges signal a received sync word."""

    def __init__(self, gpio_chip: int, gdo0: int, gdo2: int) -> None:
        self._gdo0 = gdo0
        self._gdo2 = gdo2
        self._sync_event = threading.Event()
        try:
            self._handle = lgpio.gpiochip_open(gpio_chip)
        except lgpio.error as exc:
            raise RadioError(f"cannot open gpiochip{gpio_chip}: {exc}") from exc
        try:
            lgpio.gpio_claim_input(self._handle, gdo0)
            lgpio.gpio_claim_alert(self._handle, gdo2, lgpio.RISING_EDGE)
            self._callback = lgpio.callback(
                self._handle, gdo2, lgpio.RISING_EDGE, self._on_rising_edge
            )
        except lgpio.error as exc:
            lgpio.gpiochip_close(self._handle)
            raise RadioError(
                f"cannot claim GPIO {gdo0}/{gdo2} on gpiochip{gpio_chip}: {exc}"
                " - used by another process?"
            ) from exc

    def _on_rising_edge(self, chip, gpio, level, timestamp) -> None:
        self._sync_event.set()

    def read_gdo0(self) -> bool:
        return bool(lgpio.gpio_read(self._handle, self._gdo0))

    def read_gdo2(self) -> bool:
        return bool(lgpio.gpio_read(self._handle, self._gdo2))

    def wait_for_sync(self, timeout_seconds: float) -> bool:
        """Wait for a rising edge on GDO2; True if one occurred, False on timeout."""
        self._sync_event.clear()
        if self.read_gdo2():
            return True
        return self._sync_event.wait(timeout_seconds)

    def close(self) -> None:
        self._callback.cancel()
        lgpio.gpiochip_close(self._handle)

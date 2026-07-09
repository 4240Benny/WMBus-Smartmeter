"""Mapping of M-Bus records to a meter reading, and a thread-safe store."""

from __future__ import annotations

import dataclasses
import datetime
import threading

from meterreader.records import (
    Record,
    VIF_DATE_TIME,
    VIF_FABRICATION_NUMBER,
)


@dataclasses.dataclass(frozen=True)
class MeterReading:
    received_at: datetime.datetime
    rssi_dbm: float | None = None
    serial: str | None = None
    meter_datetime: datetime.datetime | None = None
    total_import_wh: int | None = None
    total_export_wh: int | None = None
    current_import_w: int | None = None
    current_export_w: int | None = None


def _scaled(value: object, exponent: int) -> int | float | None:
    if not isinstance(value, (int, float)):
        return None
    scaled = value * 10**exponent
    return int(scaled) if float(scaled).is_integer() else scaled


def records_to_reading(
    meter_records: list[Record],
    received_at: datetime.datetime,
    rssi_dbm: float | None = None,
) -> MeterReading:
    """Extract the electricity-meter values from parsed data records.

    Recognised records (the first matching record wins):
      - fabrication/serial number (VIF 0x78)
      - date and time (VIF 0x6D)
      - energy in Wh (VIF 0x00-0x07), backward flow VIFE 0x3C -> export
      - power in W (VIF 0x28-0x2F), backward flow VIFE 0x3C -> export
    """
    fields: dict[str, object] = {}

    def put(name: str, value: object) -> None:
        if value is not None and name not in fields:
            fields[name] = value

    for record in meter_records:
        vif_base = record.vif & 0x7F
        if vif_base == VIF_FABRICATION_NUMBER:
            put("serial", record.data[::-1].hex())
        elif vif_base == VIF_DATE_TIME:
            put("meter_datetime", record.value)
        elif 0x00 <= vif_base <= 0x07:  # energy, 10^(n-3) Wh
            name = "total_export_wh" if record.is_backward_flow else "total_import_wh"
            put(name, _scaled(record.value, (vif_base & 0x07) - 3))
        elif 0x28 <= vif_base <= 0x2F:  # power, 10^(n-3) W
            name = "current_export_w" if record.is_backward_flow else "current_import_w"
            put(name, _scaled(record.value, (vif_base & 0x07) - 3))

    return MeterReading(received_at=received_at, rssi_dbm=rssi_dbm, **fields)


class ReadingStore:
    """Holds the most recent reading; written by the receiver thread,
    read by the HTTP API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: MeterReading | None = None

    def update(self, reading: MeterReading) -> None:
        with self._lock:
            self._latest = reading

    def latest(self) -> MeterReading | None:
        with self._lock:
            return self._latest

"""M-Bus application data record parsing (EN 13757-3).

Each record consists of a data information block (DIF + optional DIFEs), a
value information block (VIF + optional VIFEs) and the data itself. Only the
data types used by common electricity meters are decoded into Python values;
unknown records are still walked over correctly and returned with their raw
data so callers can log or extend them.
"""

from __future__ import annotations

import dataclasses
import datetime

from meterreader.errors import FrameDecodeError

DIF_IDLE_FILLER = 0x2F
_DIF_MANUFACTURER_SPECIFIC = (0x0F, 0x1F)
_DIF_EXTENSION = 0x80
_VIF_EXTENSION = 0x80

# DIF data field (low nibble) -> data length in bytes
_DATA_LENGTHS = {
    0x0: 0,  # no data
    0x1: 1,  # 8 bit integer
    0x2: 2,  # 16 bit integer
    0x3: 3,  # 24 bit integer
    0x4: 4,  # 32 bit integer
    0x5: 4,  # 32 bit real
    0x6: 6,  # 48 bit integer
    0x7: 8,  # 64 bit integer
    0x8: 0,  # selection for readout
    0x9: 1,  # 2 digit BCD
    0xA: 2,  # 4 digit BCD
    0xB: 3,  # 6 digit BCD
    0xC: 4,  # 8 digit BCD
    0xE: 6,  # 12 digit BCD
}
_BCD_DATA_FIELDS = frozenset((0x9, 0xA, 0xB, 0xC, 0xE))

VIF_DATE_TIME = 0x6D
VIF_FABRICATION_NUMBER = 0x78
VIFE_BACKWARD_FLOW = 0x3C


@dataclasses.dataclass(frozen=True)
class Record:
    dif: int
    difes: tuple[int, ...]
    vif: int
    vifes: tuple[int, ...]
    data: bytes
    value: object
    """Decoded value: int, float, str, datetime.datetime or None."""

    @property
    def is_backward_flow(self) -> bool:
        """True for values measured against the main flow direction,
        e.g. energy fed back into the grid."""
        return any(vife & 0x7F == VIFE_BACKWARD_FLOW for vife in self.vifes)


def _decode_bcd(data: bytes) -> int | str:
    """Decode little-endian packed BCD; returns str if non-decimal digits
    (e.g. 0xF fillers) are present."""
    digits = data[::-1].hex()
    try:
        return int(digits)
    except ValueError:
        return digits


def _decode_datetime_type_i(data: bytes) -> datetime.datetime | None:
    """CP48: second, minute, hour, day/year, month/year (+1 unused byte)."""
    second = data[0] & 0x3F
    minute = data[1] & 0x3F
    hour = data[2] & 0x1F
    day = data[3] & 0x1F
    month = data[4] & 0x0F
    year = 2000 + (((data[4] >> 4) & 0x0F) << 3 | (data[3] >> 5) & 0x07)
    try:
        return datetime.datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None


def _decode_datetime_type_f(data: bytes) -> datetime.datetime | None:
    """CP32: minute, hour, day/year, month/year."""
    minute = data[0] & 0x3F
    hour = data[1] & 0x1F
    day = data[2] & 0x1F
    month = data[3] & 0x0F
    year = 2000 + (((data[3] >> 4) & 0x0F) << 3 | (data[2] >> 5) & 0x07)
    try:
        return datetime.datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def _decode_value(data_field: int, vif: int, data: bytes) -> object:
    if not data:
        return None
    if vif & 0x7F == VIF_DATE_TIME:
        if len(data) == 6:
            return _decode_datetime_type_i(data)
        if len(data) == 4:
            return _decode_datetime_type_f(data)
        return None
    if data_field in _BCD_DATA_FIELDS:
        return _decode_bcd(data)
    if data_field in (0x1, 0x2, 0x3, 0x4, 0x6, 0x7):
        return int.from_bytes(data, "little")
    return None


def parse_records(payload: bytes) -> list[Record]:
    """Parse all data records from an application payload.

    Leading decryption-check bytes and idle fillers (0x2F) are skipped.
    Parsing stops at a manufacturer-specific data block or at a DIF that is
    not understood.
    """
    records = []
    position = 0
    try:
        while position < len(payload):
            dif = payload[position]
            position += 1
            if dif == DIF_IDLE_FILLER:
                continue
            if dif in _DIF_MANUFACTURER_SPECIFIC:
                records.append(
                    Record(dif, (), 0, (), payload[position:], None)
                )
                break

            difes = []
            extension = dif & _DIF_EXTENSION
            while extension:
                difes.append(payload[position])
                extension = payload[position] & _DIF_EXTENSION
                position += 1

            vif = payload[position]
            position += 1
            vifes = []
            extension = vif & _VIF_EXTENSION
            while extension:
                vifes.append(payload[position])
                extension = payload[position] & _VIF_EXTENSION
                position += 1

            data_field = dif & 0x0F
            if data_field == 0xD:  # variable length
                length = payload[position]
                position += 1
                if length >= 0xC0:
                    raise FrameDecodeError(
                        f"unsupported variable length field {length:#04x}"
                    )
            else:
                try:
                    length = _DATA_LENGTHS[data_field]
                except KeyError:
                    raise FrameDecodeError(
                        f"unsupported DIF data field {data_field:#03x}"
                    ) from None
            data = payload[position : position + length]
            if len(data) != length:
                raise FrameDecodeError("payload ends in the middle of a record")
            position += length

            records.append(
                Record(
                    dif=dif,
                    difes=tuple(difes),
                    vif=vif,
                    vifes=tuple(vifes),
                    data=data,
                    value=_decode_value(data_field, vif, data),
                )
            )
    except IndexError:
        raise FrameDecodeError("payload ends in the middle of a record") from None
    return records

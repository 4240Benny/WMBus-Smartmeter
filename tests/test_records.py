import datetime

import pytest

from meterreader import records
from meterreader.errors import FrameDecodeError
from meterreader.readings import records_to_reading


def test_datetime_type_i():
    # validated against a live meter transmission
    (record,) = records.parse_records(bytes.fromhex("066d545f004a3740"))
    assert record.value == datetime.datetime(2026, 7, 10, 0, 31, 20)


def test_datetime_type_f():
    # 2024-02-16 08:15, year split over bytes 2 and 3
    (record,) = records.parse_records(bytes.fromhex("046d0f081032"))
    assert record.value == datetime.datetime(2024, 2, 16, 8, 15)


def test_invalid_datetime_is_none():
    (record,) = records.parse_records(bytes.fromhex("066d0000000f0f00"))
    assert record.value is None


def test_idle_fillers_are_skipped():
    parsed = records.parse_records(bytes.fromhex("2f2f0b2b0015002f2f2f"))
    assert len(parsed) == 1
    assert parsed[0].value == 1500


def test_bcd_with_filler_digits_returns_string():
    (record,) = records.parse_records(bytes.fromhex("0c78123456f1"))
    assert record.value == "f1563412"


def test_integer_data_field():
    (record,) = records.parse_records(bytes.fromhex("02fd483902"))
    assert record.vifes == (0x48,)
    assert record.value == 0x0239


def test_manufacturer_specific_block_stops_parsing():
    parsed = records.parse_records(bytes.fromhex("0b2b0015000f0102030405"))
    assert len(parsed) == 2
    assert parsed[1].dif == 0x0F
    assert parsed[1].data == bytes.fromhex("0102030405")


def test_truncated_record_raises():
    with pytest.raises(FrameDecodeError, match="middle of a record"):
        records.parse_records(bytes.fromhex("0e0390"))


def test_records_to_reading_maps_all_fields():
    payload = bytes.fromhex(
        "2f2f"
        "0c78 89674523"
        "066d 545f004a3740"
        "0e03 896745030000"
        "0e833c 341200000000"
        "0b2b 420000"
        "0bab3c 000000"
        "2f2f2f2f"
    )
    reading = records_to_reading(
        records.parse_records(payload), received_at=datetime.datetime.now()
    )
    assert reading.serial == "23456789"
    assert reading.meter_datetime == datetime.datetime(2026, 7, 10, 0, 31, 20)
    assert reading.total_import_wh == 3456789
    assert reading.total_export_wh == 1234
    assert reading.current_import_w == 42
    assert reading.current_export_w == 0


def test_records_to_reading_scales_by_vif_exponent():
    # VIF 0x06 = energy * 10^3 Wh, VIF 0x2E = power * 10^3 W
    payload = bytes.fromhex("0e06 000000010000" "0b2e 002000")
    reading = records_to_reading(
        records.parse_records(payload), received_at=datetime.datetime.now()
    )
    assert reading.total_import_wh == 1_000_000_000
    assert reading.current_import_w == 2_000_000


def test_records_to_reading_missing_fields_are_none():
    reading = records_to_reading([], received_at=datetime.datetime.now())
    assert reading.serial is None
    assert reading.total_import_wh is None

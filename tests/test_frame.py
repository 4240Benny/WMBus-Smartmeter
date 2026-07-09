import datetime

import pytest

from meterreader import crypto, encoding, frame, records
from meterreader.crypto import DecryptionError
from meterreader.errors import FrameDecodeError
from meterreader.readings import records_to_reading

# EN 13757-4 example: unencrypted mode T frame of manufacturer "CEN",
# meter id 12345678, one volume record (876.543 m^3)
_EXAMPLE_PACKET = bytes.fromhex("0F44AE0C78563412010744 47780B134365871E6D")
_EXAMPLE_TELEGRAM = bytes.fromhex("0F44AE0C785634120107780B13436587")


def test_packet_size():
    assert frame.packet_size(0x0F) == 20
    assert frame.packet_size(0x3E) == 73


def test_verify_and_strip_block_crcs():
    assert frame.verify_and_strip_block_crcs(_EXAMPLE_PACKET) == _EXAMPLE_TELEGRAM


def test_corrupted_block_raises():
    corrupted = bytearray(_EXAMPLE_PACKET)
    corrupted[5] ^= 0x01
    with pytest.raises(FrameDecodeError, match="CRC mismatch in block 1"):
        frame.verify_and_strip_block_crcs(bytes(corrupted))


def test_build_frame_format_a_is_inverse():
    assert frame.build_frame_format_a(_EXAMPLE_TELEGRAM) == _EXAMPLE_PACKET


def test_decode_packet_from_encoded_capture():
    encoded = encoding.encode(_EXAMPLE_PACKET)
    assert frame.decode_packet(encoded) == _EXAMPLE_TELEGRAM


def test_parse_unencrypted_telegram():
    telegram = frame.parse_telegram(_EXAMPLE_TELEGRAM)
    assert telegram.manufacturer == "CEN"
    assert telegram.device_id == "12345678"
    assert telegram.version == 0x01
    assert telegram.device_type == 0x07
    assert telegram.ci_field == frame.CI_NO_HEADER
    assert telegram.encryption_mode == 0
    (volume,) = records.parse_records(telegram.payload)
    assert volume.vif == 0x13
    assert volume.value == 876543


def test_manufacturer_code_to_string():
    assert frame.manufacturer_code_to_string(0x0CAE) == "CEN"


# --- end-to-end test with a synthetic encrypted telegram -------------------

_KEY = bytes.fromhex("000102030405060708090A0B0C0D0E0F")


def _build_encrypted_frame() -> bytes:
    """Build a mode 5 encrypted telegram like a smart electricity meter
    sends it, and return the raw 3-out-of-6 encoded capture."""
    meter_records = bytes.fromhex(
        "0c78 78563412"  # serial 12345678
        "066d 1e2d0c2c3500"  # date/time 2025-05-12 12:45:30
        "0e03 907856341200"  # energy import 1234567890 Wh
        "0e833c 214305000000"  # energy export 54321 Wh
        "0b2b 001500"  # power import 1500 W
        "0bab3c 000000"  # power export 0 W
        .replace(" ", "")
    )
    address = bytes.fromhex("3A63" "78563412" "01" "02")  # M + ID + version + type
    access_number = 0x42
    iv = crypto.mode5_iv(address, access_number)
    ciphertext = crypto.encrypt_mode5(meter_records, _KEY, iv)
    assert len(ciphertext) == 48
    configuration = (5 << 8) | (len(ciphertext) // 16) << 4  # mode 5, 3 blocks
    tpl = bytes(
        [frame.CI_SHORT_HEADER, access_number, 0x00]
    ) + configuration.to_bytes(2, "little")
    body = bytes([0x44]) + address + tpl + ciphertext
    telegram = bytes([len(body)]) + body
    return encoding.encode(frame.build_frame_format_a(telegram))


def test_encrypted_telegram_end_to_end():
    encoded = _build_encrypted_frame()
    telegram_bytes = frame.decode_packet(encoded)
    telegram = frame.parse_telegram(telegram_bytes, _KEY)
    assert telegram.encryption_mode == 5
    assert telegram.access_number == 0x42
    assert telegram.payload.startswith(crypto.DECRYPTION_CHECK)

    reading = records_to_reading(
        records.parse_records(telegram.payload),
        received_at=datetime.datetime(2025, 5, 12, 12, 45, 31),
    )
    assert reading.serial == "12345678"
    assert reading.meter_datetime == datetime.datetime(2025, 5, 12, 12, 45, 30)
    assert reading.total_import_wh == 1234567890
    assert reading.total_export_wh == 54321
    assert reading.current_import_w == 1500
    assert reading.current_export_w == 0


def test_encrypted_telegram_wrong_key():
    encoded = _build_encrypted_frame()
    telegram_bytes = frame.decode_packet(encoded)
    with pytest.raises(DecryptionError, match="wrong AES key"):
        frame.parse_telegram(telegram_bytes, bytes(16))


def test_encrypted_telegram_without_key():
    encoded = _build_encrypted_frame()
    telegram_bytes = frame.decode_packet(encoded)
    with pytest.raises(FrameDecodeError, match="no AES key"):
        frame.parse_telegram(telegram_bytes, None)

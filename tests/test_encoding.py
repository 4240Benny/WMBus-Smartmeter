import pytest

from meterreader import encoding
from meterreader.encoding import ThreeOutOfSixError


def test_known_vector():
    # nibbles 0x0 and 0x1 -> symbols 010110 001101, zero-padded to 2 bytes
    assert encoding.encode(b"\x01") == bytes([0b01011000, 0b11010000])
    assert encoding.decode(bytes([0b01011000, 0b11010000]), 1) == b"\x01"


@pytest.mark.parametrize(
    "data",
    [b"\x00", b"\xff", b"\x12\x34\x56", bytes(range(256))],
)
def test_round_trip(data):
    assert encoding.decode(encoding.encode(data), len(data)) == data


def test_round_trip_odd_length_ignores_padding():
    # 3 data bytes occupy 36 bits; the trailing 4 bits are padding
    data = b"\xab\xcd\xef"
    encoded = encoding.encode(data)
    assert len(encoded) == encoding.encoded_size(len(data)) == 5
    assert encoding.decode(encoded, len(data)) == data


def test_invalid_symbol_raises():
    with pytest.raises(ThreeOutOfSixError, match="invalid symbol"):
        encoding.decode(b"\x00\x00\x00", 2)


def test_too_short_buffer_raises():
    with pytest.raises(ThreeOutOfSixError, match="need"):
        encoding.decode(b"\x58", 1)


def test_encoded_size():
    assert encoding.encoded_size(2) == 3
    assert encoding.encoded_size(20) == 30
    # odd sizes need half a byte extra for the trailing nibble
    assert encoding.encoded_size(73) == 110

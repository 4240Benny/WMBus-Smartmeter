"""CRC tests using the EN 13757-4 example frame

    0F 44 AE 0C 78 56 34 12 01 07 | 44 47 | 78 0B 13 43 65 87 | 1E 6D

(a mode T frame of manufacturer "CEN", meter id 12345678).
"""

from meterreader.crc import crc16_en13757


def test_block1_crc():
    assert crc16_en13757(bytes.fromhex("0F44AE0C785634120107")) == 0x4447


def test_block2_crc():
    assert crc16_en13757(bytes.fromhex("780B13436587")) == 0x1E6D


def test_empty():
    assert crc16_en13757(b"") == 0xFFFF

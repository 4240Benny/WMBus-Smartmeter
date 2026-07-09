"""CRC-16 used by wireless M-Bus (EN 13757-4).

Polynomial 0x3D65, initial value 0x0000, MSB first, final complement.
The CRC is transmitted most significant byte first.
"""

_POLYNOMIAL = 0x3D65


def crc16_en13757(data: bytes) -> int:
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ _POLYNOMIAL
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc ^ 0xFFFF

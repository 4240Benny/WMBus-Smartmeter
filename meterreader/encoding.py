""" "3 out of 6" channel coding used by wireless M-Bus mode T (EN 13757-4).

Every 4-bit nibble is transmitted as a 6-bit symbol that always contains
exactly three '1' bits, so one data byte occupies 12 bits on air.
"""

from __future__ import annotations

from meterreader.errors import FrameDecodeError


class ThreeOutOfSixError(FrameDecodeError):
    """The buffer contains a bit pattern that is not a valid 6-bit symbol."""


# nibble value -> 6-bit symbol (EN 13757-4 table)
_ENCODE = (
    0b010110,  # 0x0
    0b001101,  # 0x1
    0b001110,  # 0x2
    0b001011,  # 0x3
    0b011100,  # 0x4
    0b011001,  # 0x5
    0b011010,  # 0x6
    0b010011,  # 0x7
    0b101100,  # 0x8
    0b100101,  # 0x9
    0b100110,  # 0xA
    0b100011,  # 0xB
    0b110100,  # 0xC
    0b110001,  # 0xD
    0b110010,  # 0xE
    0b101001,  # 0xF
)

_DECODE = {symbol: nibble for nibble, symbol in enumerate(_ENCODE)}


def encoded_size(num_decoded_bytes: int) -> int:
    """Number of encoded bytes needed to carry `num_decoded_bytes` data bytes.

    Each data byte occupies 12 bits; for an odd number of data bytes the last
    encoded byte is only half used (the transmitter fills it with postamble
    bits).
    """
    return (3 * num_decoded_bytes + 1) // 2


def decode(encoded: bytes, num_decoded_bytes: int) -> bytes:
    """Decode the first `num_decoded_bytes` data bytes from an encoded buffer.

    Trailing bits beyond the requested amount of data (postamble, noise) are
    ignored.
    """
    if len(encoded) < encoded_size(num_decoded_bytes):
        raise ThreeOutOfSixError(
            f"need {encoded_size(num_decoded_bytes)} encoded bytes for"
            f" {num_decoded_bytes} data bytes, got {len(encoded)}"
        )
    bits = int.from_bytes(encoded, "big")
    total_bits = len(encoded) * 8
    nibbles = []
    for chunk_index in range(2 * num_decoded_bytes):
        shift = total_bits - 6 * (chunk_index + 1)
        symbol = (bits >> shift) & 0x3F
        try:
            nibbles.append(_DECODE[symbol])
        except KeyError:
            raise ThreeOutOfSixError(
                f"invalid symbol {symbol:#08b} at chunk {chunk_index}"
            ) from None
    return bytes(
        (nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2)
    )


def encode(data: bytes) -> bytes:
    """Encode data bytes; the last byte is zero-padded to a byte boundary."""
    bits = 0
    num_bits = 0
    for byte in data:
        for nibble in (byte >> 4, byte & 0x0F):
            bits = (bits << 6) | _ENCODE[nibble]
            num_bits += 6
    padding = -num_bits % 8
    bits <<= padding
    num_bits += padding
    return bits.to_bytes(num_bits // 8, "big")

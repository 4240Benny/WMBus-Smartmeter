"""AES decryption for wireless M-Bus security mode 5 (AES-128-CBC).

The initialisation vector is built from the address of the sending meter and
the access number of the telegram (EN 13757-3 / OMS):

    IV = M-field (2 bytes) || ID (4 bytes) || version || device type
         || access number repeated 8 times

Correctly decrypted plaintext starts with the two "decryption check" bytes
0x2F 0x2F.
"""

from __future__ import annotations

from Crypto.Cipher import AES

from meterreader.errors import FrameDecodeError

DECRYPTION_CHECK = b"\x2f\x2f"
IDLE_FILLER = 0x2F


class DecryptionError(FrameDecodeError):
    """Decryption failed - most likely a wrong AES key."""


def mode5_iv(address: bytes, access_number: int) -> bytes:
    """Build the mode 5 IV.

    `address` is the 8-byte meter address exactly as transmitted:
    M-field (2 bytes) + ID (4 bytes) + version + device type.
    """
    if len(address) != 8:
        raise ValueError(f"expected 8 address bytes, got {len(address)}")
    return address + bytes([access_number]) * 8


def decrypt_mode5(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt and verify the 0x2F2F decryption-check prefix."""
    if len(key) != 16:
        raise ValueError(f"expected a 16 byte AES-128 key, got {len(key)} bytes")
    if not ciphertext or len(ciphertext) % 16:
        raise DecryptionError(
            f"ciphertext length {len(ciphertext)} is not a multiple of 16"
        )
    plaintext = AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)
    if plaintext[:2] != DECRYPTION_CHECK:
        raise DecryptionError(
            "decrypted data does not start with 0x2F2F - wrong AES key?"
        )
    return plaintext


def encrypt_mode5(records: bytes, key: bytes, iv: bytes) -> bytes:
    """Inverse of `decrypt_mode5` (used for building test telegrams).

    Prepends the decryption-check bytes and pads with idle fillers to a
    multiple of the AES block size.
    """
    plaintext = DECRYPTION_CHECK + records
    plaintext += bytes([IDLE_FILLER]) * (-len(plaintext) % 16)
    return AES.new(key, AES.MODE_CBC, iv).encrypt(plaintext)

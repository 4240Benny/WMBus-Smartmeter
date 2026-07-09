"""Receive, decrypt and decode wireless M-Bus telegrams from a smart electricity meter.

The package is organised as a pipeline:

    CC1101 radio (cc1101.py, gpio.py, registers.py)
        -> "3 out of 6" decoding (encoding.py)
        -> frame format A CRC verification (crc.py, frame.py)
        -> transport layer parsing + AES decryption (frame.py, crypto.py)
        -> M-Bus data record parsing (records.py)
        -> latest reading store (readings.py)
        -> HTTP API (api.py)

`service.py` wires everything together and is the entry point used by the
systemd service.
"""

__version__ = "1.0.0"

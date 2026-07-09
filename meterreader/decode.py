"""Offline decoder for captured telegrams - useful for debugging.

Usage:
    python -m meterreader.decode [--key HEXKEY] HEXDATA
    python -m meterreader.decode [--key HEXKEY] --file capture.txt

Accepts, and automatically detects, any of:
  - a raw "3 out of 6" encoded capture (as read from the CC1101 RX FIFO),
  - a decoded frame format A packet (block CRCs included),
  - a CRC-stripped telegram (starting with the L-field).
"""

from __future__ import annotations

import argparse
import sys

from meterreader import encoding, frame, records
from meterreader.errors import FrameDecodeError


def _telegram_from_hex(data: bytes) -> tuple[bytes, str]:
    attempts = []
    try:
        return frame.decode_packet(data), "3-out-of-6 encoded capture"
    except FrameDecodeError as exc:
        attempts.append(f"as encoded capture: {exc}")
    try:
        return frame.verify_and_strip_block_crcs(data), "frame with block CRCs"
    except FrameDecodeError as exc:
        attempts.append(f"as frame with CRCs: {exc}")
    if len(data) == data[0] + 1:
        return data, "CRC-stripped telegram"
    attempts.append(
        f"as CRC-stripped telegram: length {len(data)} does not match"
        f" L-field {data[0]}"
    )
    raise FrameDecodeError("input not recognised:\n  " + "\n  ".join(attempts))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("hexdata", nargs="?", help="telegram as a hex string")
    parser.add_argument("--file", help="read hex data from a file instead")
    parser.add_argument("--key", help="AES-128 key as 32 hex digits")
    args = parser.parse_args(argv)

    if args.file:
        with open(args.file, encoding="utf-8") as capture_file:
            hexdata = capture_file.read()
    elif args.hexdata:
        hexdata = args.hexdata
    else:
        parser.error("provide HEXDATA or --file")
    data = bytes.fromhex("".join(hexdata.split()))
    key = bytes.fromhex(args.key) if args.key else None

    try:
        telegram_bytes, input_kind = _telegram_from_hex(data)
        telegram = frame.parse_telegram(telegram_bytes, key)
    except FrameDecodeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"input:            {input_kind}")
    print(f"telegram:         {telegram_bytes.hex()}")
    print(f"manufacturer:     {telegram.manufacturer} ({telegram.manufacturer_code:#06x})")
    print(f"device id:        {telegram.device_id}")
    print(f"version / type:   {telegram.version:#04x} / {telegram.device_type:#04x}")
    print(f"CI field:         {telegram.ci_field:#04x}")
    if telegram.access_number is not None:
        print(f"access number:    {telegram.access_number}")
        print(f"status:           {telegram.status:#04x}")
        print(f"configuration:    {telegram.configuration:#06x}"
              f" (encryption mode {telegram.encryption_mode})")
    print(f"payload:          {telegram.payload.hex()}")
    print("records:")
    for record in records.parse_records(telegram.payload):
        vif_chain = " ".join(
            f"{v:02x}" for v in (record.vif, *record.vifes)
        )
        print(
            f"  DIF {record.dif:02x} VIF {vif_chain:<8}"
            f" data {record.data.hex():<16} value {record.value!r}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

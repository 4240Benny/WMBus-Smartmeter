# wM-Bus Smart Meter Reader

Reads a smart electricity meter over **wireless M-Bus mode T** (868.95 MHz)
using a cheap **TI CC1101** transceiver module connected to a **Raspberry
Pi**, decrypts and decodes the telegrams, and serves the current readings
over a small **HTTP API** — ready to be consumed by Home Assistant, evcc,
scripts, or anything else that can poll JSON.

Many European electricity meters (e.g. those rolled out by Austrian grid
operators) broadcast an encrypted wM-Bus telegram every few seconds
containing total energy import/export and current power. With the AES key —
which you can request from your grid operator — this service turns a
Raspberry Pi and a ~3 € radio module into a local, cloud-free meter reader.

```
CC1101 radio ──▶ "3 out of 6" decoding ──▶ CRC check (EN 13757-4 frame A)
             ──▶ AES-128-CBC decryption (security mode 5)
             ──▶ M-Bus data record parsing ──▶ HTTP API
```

## Features

- Receives wM-Bus **mode T1** frames (frame format A) with a CC1101 on the
  Raspberry Pi SPI bus, following TI application note AN067: the frame
  length is decoded on the fly and the radio is switched to fixed packet
  length mode, so frames of any size are received reliably.
- Verifies the **CRC of every frame block** — corrupted frames are
  discarded instead of producing bogus readings.
- Decrypts **security mode 5** (AES-128-CBC) telegrams and validates the
  decryption, so a wrong key is reported clearly.
- Parses M-Bus data records generically (DIF/VIF), extracting meter serial,
  meter timestamp, total import/export energy and current import/export
  power, including unit scaling.
- Reports the **RSSI** of each received telegram.
- Small **HTTP API** with a `/health` endpoint for monitoring.
- Offline decoder CLI for captured telegrams, and a hardware-independent
  test suite.

## Hardware

| CC1101 module | Raspberry Pi (BCM numbering)   |
|---------------|--------------------------------|
| VDD           | 3.3 V (pin 1)                  |
| GND           | GND (pin 6)                    |
| SI (MOSI)     | GPIO 10 / SPI0 MOSI (pin 19)   |
| SO (MISO)     | GPIO 9 / SPI0 MISO (pin 21)    |
| SCLK          | GPIO 11 / SPI0 SCLK (pin 23)   |
| CSn           | GPIO 8 / SPI0 CE0 (pin 24)     |
| GDO0          | GPIO 24 (pin 18)               |
| GDO2          | GPIO 25 (pin 22)               |

Any CC1101 board for the 868 MHz band works. GDO0/GDO2 pins and the SPI
bus/chip-select are configurable.

## Installation

On Raspberry Pi OS:

```sh
# enable the SPI bus once
sudo raspi-config nonint do_spi 0

git clone https://github.com/<you>/wmbus-meterreader.git
cd wmbus-meterreader
python3 -m venv venv
venv/bin/pip install .

cp config.example.yaml config.yaml
nano config.yaml          # enter your meter's AES key
```

Run it manually first to see it working:

```sh
sudo venv/bin/python -m meterreader --config config.yaml
```

You should see one log line per received telegram:

```
2026-07-10 12:00:01 INFO meterreader.service: reading: serial=23456789 time=2026-07-10 12:00:00 import=3456789Wh export=1234Wh P+=42W P-=0W rssi=-73.5dBm
```

To run it as a service, adjust the paths in
[deploy/meterreader.service](deploy/meterreader.service) and:

```sh
sudo cp deploy/meterreader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meterreader
```

### The AES key

Telegrams are encrypted (wM-Bus security mode 5). Your grid operator can
give you the 128-bit AES key for your own meter, usually via their customer
portal. Put it in `config.yaml` (which is gitignored) or in the
`METERREADER_AES_KEY` environment variable.

## HTTP API

| Endpoint                  | Response                                    |
|---------------------------|---------------------------------------------|
| `/data`                   | all values in one JSON object               |
| `/meter_time`             | `{"value": "2026-07-10 12:00:00"}`          |
| `/meter_serial`           | `{"value": "23456789"}`                     |
| `/meter_total_import_wh`  | `{"value": 3456789}`                        |
| `/meter_total_export_wh`  | `{"value": 1234}`                           |
| `/meter_current_import_w` | `{"value": 42}`                             |
| `/meter_current_export_w` | `{"value": 0}`                              |
| `/health`                 | 200 while readings are fresh, 503 otherwise |

```sh
$ curl http://raspberrypi/data
{
  "age_seconds": 2.1,
  "meter_current_export_w": 0,
  "meter_current_import_w": 42,
  "meter_serial": "23456789",
  "meter_time": "2026-07-10 12:00:00",
  "meter_total_export_wh": 1234,
  "meter_total_import_wh": 3456789,
  "received_at": "2026-07-10 12:00:02",
  "rssi_dbm": -73.5
}
```

Endpoints return HTTP 503 until the first telegram has been received.

## Decoding captured telegrams offline

The decoder CLI accepts raw 3-out-of-6 encoded captures, frames with block
CRCs, or CRC-stripped telegrams (auto-detected):

```sh
venv/bin/python -m meterreader.decode --key <AESKEY> <HEXDATA>
```

## Development

The protocol code is pure Python and runs anywhere:

```sh
pip install -e .[dev]
pytest
```

The test suite covers the full pipeline — 3-out-of-6 coding, block CRCs,
mode 5 decryption and record parsing — using synthetic telegrams, so no
hardware is required.

## Scope and limitations

- Receive-only, wM-Bus **mode T1, frame format A** (the mode used by the
  common 868.95 MHz smart electricity meters).
- Encryption: **mode 5** (AES-128-CBC) and unencrypted telegrams.
  Mode 7 (AES-128-GCM/CMAC, used by some newer meters) is not implemented.
- Transport layers: CI `0x7A` (short header), `0x72` (long header) and
  `0x78` (no header).

## Credits

- The CC1101 SPI driver is derived from
  [python-cc1101](https://github.com/fphammerle/python-cc1101) by Fabian
  Peter Hammerle (GPL-3.0-or-later).
- The mode T receive strategy follows Texas Instruments application note
  [AN067 (SWRA234a)](https://www.ti.com/lit/an/swra234a/swra234a.pdf),
  "Wireless MBUS implementation with CC1101 and MSP430".

## License

[GPL-3.0-or-later](LICENSE)

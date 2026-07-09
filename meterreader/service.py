"""Service entry point: receiver loop + HTTP API."""

from __future__ import annotations

import argparse
import datetime
import logging
import threading
import time

from meterreader import __version__, frame, records
from meterreader.api import create_app
from meterreader.cc1101 import CC1101TModeReceiver, ReceivedFrame
from meterreader.config import Config, load_config
from meterreader.errors import FrameDecodeError, RadioError
from meterreader.readings import MeterReading, ReadingStore, records_to_reading

_LOGGER = logging.getLogger(__name__)

_RADIO_RETRY_SECONDS = 5.0


def process_frame(received: ReceivedFrame, aes_key: bytes | None) -> MeterReading:
    """Run a received frame through the full decoding pipeline."""
    telegram_bytes = frame.decode_packet(received.encoded)
    telegram = frame.parse_telegram(telegram_bytes, aes_key)
    meter_records = records.parse_records(telegram.payload)
    return records_to_reading(
        meter_records,
        received_at=datetime.datetime.now(),
        rssi_dbm=received.rssi_dbm,
    )


def run_receiver(config: Config, store: ReadingStore) -> None:
    """Receive frames forever; re-initialises the radio after failures."""
    radio_config = config.radio
    while True:
        try:
            with CC1101TModeReceiver(
                spi_bus=radio_config.spi_bus,
                spi_chip_select=radio_config.spi_chip_select,
                spi_speed_hz=radio_config.spi_speed_hz,
                gpio_chip=radio_config.gpio_chip,
                gdo0_gpio=radio_config.gdo0_gpio,
                gdo2_gpio=radio_config.gdo2_gpio,
                frequency_hz=radio_config.frequency_hz,
            ) as receiver:
                while True:
                    received = receiver.receive_frame(
                        radio_config.receive_timeout_seconds
                    )
                    if received is None:
                        _LOGGER.debug("no frame received, listening again")
                        continue
                    try:
                        reading = process_frame(received, config.aes_key)
                    except FrameDecodeError as exc:
                        _LOGGER.info("discarded frame: %s", exc)
                        continue
                    store.update(reading)
                    _LOGGER.info(
                        "reading: serial=%s time=%s import=%sWh export=%sWh"
                        " P+=%sW P-=%sW rssi=%sdBm",
                        reading.serial,
                        reading.meter_datetime,
                        reading.total_import_wh,
                        reading.total_export_wh,
                        reading.current_import_w,
                        reading.current_export_w,
                        reading.rssi_dbm,
                    )
        except RadioError as exc:
            _LOGGER.error(
                "radio error: %s - retrying in %.0f s", exc, _RADIO_RETRY_SECONDS
            )
            time.sleep(_RADIO_RETRY_SECONDS)
        except Exception:  # noqa: BLE001 - keep the service alive
            _LOGGER.exception(
                "unexpected error - reinitialising radio in %.0f s",
                _RADIO_RETRY_SECONDS,
            )
            time.sleep(_RADIO_RETRY_SECONDS)


def _serve_http(config: Config, store: ReadingStore) -> None:
    from waitress import serve

    app = create_app(store)
    _LOGGER.info(
        "HTTP API listening on http://%s:%d", config.http.host, config.http.port
    )
    serve(app, host=config.http.host, port=config.http.port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Receive wireless M-Bus telegrams from a smart meter"
        " and serve the readings over HTTP."
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="path to the YAML config file (default: %(default)s)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    logging.basicConfig(
        level=config.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if config.aes_key is None:
        _LOGGER.warning(
            "no AES key configured - encrypted telegrams will be discarded"
        )

    store = ReadingStore()
    http_thread = threading.Thread(
        target=_serve_http, args=(config, store), daemon=True, name="http"
    )
    http_thread.start()

    # The receiver runs in the main thread: if it dies despite the retry
    # logic, the process exits and systemd restarts the whole service.
    run_receiver(config, store)


if __name__ == "__main__":
    main()

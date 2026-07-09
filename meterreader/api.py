"""HTTP API serving the most recent meter reading.

The endpoint names and response shapes are compatible with the original
meter reader service, so existing consumers (e.g. Home Assistant REST
sensors) keep working unchanged.
"""

from __future__ import annotations

import datetime

from flask import Flask, jsonify

from meterreader.readings import MeterReading, ReadingStore

#: A reading older than this makes /health report failure.
_STALE_AFTER_SECONDS = 300

_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_FIELD_ENDPOINTS = {
    "meter_time": "meter_datetime",
    "meter_serial": "serial",
    "meter_total_import_wh": "total_import_wh",
    "meter_total_export_wh": "total_export_wh",
    "meter_current_import_w": "current_import_w",
    "meter_current_export_w": "current_export_w",
}


def _format(value: object) -> object:
    if isinstance(value, datetime.datetime):
        return value.strftime(_DATETIME_FORMAT)
    return value


def _age_seconds(reading: MeterReading) -> float:
    return round(
        (datetime.datetime.now() - reading.received_at).total_seconds(), 1
    )


def create_app(store: ReadingStore) -> Flask:
    app = Flask(__name__)

    def no_reading_response():
        return jsonify({"error": "no reading received yet"}), 503

    @app.route("/data", methods=["GET"])
    def data():
        reading = store.latest()
        if reading is None:
            return no_reading_response()
        return jsonify(
            {
                "meter_time": _format(reading.meter_datetime),
                "meter_serial": reading.serial,
                "meter_total_import_wh": reading.total_import_wh,
                "meter_total_export_wh": reading.total_export_wh,
                "meter_current_import_w": reading.current_import_w,
                "meter_current_export_w": reading.current_export_w,
                "received_at": _format(reading.received_at),
                "age_seconds": _age_seconds(reading),
                "rssi_dbm": reading.rssi_dbm,
            }
        )

    def make_field_endpoint(attribute: str):
        def field_endpoint():
            reading = store.latest()
            if reading is None:
                return no_reading_response()
            return jsonify({"value": _format(getattr(reading, attribute))})

        return field_endpoint

    for endpoint, attribute in _FIELD_ENDPOINTS.items():
        app.add_url_rule(
            f"/{endpoint}", endpoint, make_field_endpoint(attribute), methods=["GET"]
        )

    @app.route("/health", methods=["GET"])
    def health():
        reading = store.latest()
        if reading is None:
            return jsonify({"status": "error", "reason": "no reading yet"}), 503
        age = _age_seconds(reading)
        if age > _STALE_AFTER_SECONDS:
            return (
                jsonify(
                    {"status": "error", "reason": "stale", "age_seconds": age}
                ),
                503,
            )
        return jsonify({"status": "ok", "age_seconds": age})

    return app

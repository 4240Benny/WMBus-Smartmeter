import dataclasses
import datetime

import pytest

from meterreader.api import create_app
from meterreader.readings import MeterReading, ReadingStore


@pytest.fixture(name="store")
def store_fixture():
    return ReadingStore()


@pytest.fixture(name="client")
def client_fixture(store):
    app = create_app(store)
    app.testing = True
    return app.test_client()


def _sample_reading():
    return MeterReading(
        received_at=datetime.datetime.now(),
        rssi_dbm=-72.5,
        serial="23456789",
        meter_datetime=datetime.datetime(2026, 7, 10, 0, 31, 20),
        total_import_wh=3456789,
        total_export_wh=1234,
        current_import_w=42,
        current_export_w=0,
    )


def test_no_reading_yet_returns_503(client):
    for endpoint in ("/data", "/meter_total_import_wh", "/health"):
        response = client.get(endpoint)
        assert response.status_code == 503


def test_data_endpoint(client, store):
    store.update(_sample_reading())
    response = client.get("/data")
    assert response.status_code == 200
    data = response.get_json()
    assert data["meter_serial"] == "23456789"
    assert data["meter_time"] == "2026-07-10 00:31:20"
    assert data["meter_total_import_wh"] == 3456789
    assert data["meter_total_export_wh"] == 1234
    assert data["meter_current_import_w"] == 42
    assert data["meter_current_export_w"] == 0
    assert data["rssi_dbm"] == -72.5
    assert data["age_seconds"] >= 0


def test_single_value_endpoints(client, store):
    store.update(_sample_reading())
    assert client.get("/meter_total_import_wh").get_json() == {"value": 3456789}
    assert client.get("/meter_current_export_w").get_json() == {"value": 0}
    assert client.get("/meter_serial").get_json() == {"value": "23456789"}
    assert client.get("/meter_time").get_json() == {"value": "2026-07-10 00:31:20"}


def test_health(client, store):
    store.update(_sample_reading())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_health_stale(client, store):
    stale = datetime.datetime.now() - datetime.timedelta(hours=1)
    store.update(dataclasses.replace(_sample_reading(), received_at=stale))
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json()["reason"] == "stale"

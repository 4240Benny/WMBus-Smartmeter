"""Configuration loading (YAML file + environment variable overrides)."""

from __future__ import annotations

import dataclasses
import os

import yaml

from meterreader.errors import MeterReaderError

#: Environment variable that overrides the AES key from the config file, so
#: the key can be kept out of files entirely if preferred.
AES_KEY_ENV_VAR = "METERREADER_AES_KEY"


class ConfigError(MeterReaderError):
    pass


@dataclasses.dataclass(frozen=True)
class RadioConfig:
    spi_bus: int = 0
    spi_chip_select: int = 0
    spi_speed_hz: int = 10_000_000
    gpio_chip: int = 0
    gdo0_gpio: int = 24
    gdo2_gpio: int = 25
    frequency_hz: float = 868_950_000.0
    receive_timeout_seconds: float = 8.0


@dataclasses.dataclass(frozen=True)
class HttpConfig:
    host: str = "0.0.0.0"
    port: int = 80


@dataclasses.dataclass(frozen=True)
class Config:
    aes_key: bytes | None = None
    radio: RadioConfig = dataclasses.field(default_factory=RadioConfig)
    http: HttpConfig = dataclasses.field(default_factory=HttpConfig)
    log_level: str = "INFO"


def _build(dataclass_type, values: dict, context: str):
    field_names = {field.name for field in dataclasses.fields(dataclass_type)}
    unknown = set(values) - field_names
    if unknown:
        raise ConfigError(f"unknown {context} option(s): {', '.join(sorted(unknown))}")
    return dataclass_type(**values)


def _parse_aes_key(value: str) -> bytes:
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ConfigError(f"AES key is not valid hex: {exc}") from exc
    if len(key) != 16:
        raise ConfigError(
            f"AES key must be 16 bytes (32 hex digits), got {len(key)} bytes"
        )
    return key


def load_config(path: str) -> Config:
    try:
        with open(path, encoding="utf-8") as config_file:
            raw = yaml.safe_load(config_file) or {}
    except FileNotFoundError:
        raise ConfigError(
            f"config file {path!r} not found"
            " - copy config.example.yaml and adjust it"
        ) from None
    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path!r} must contain a mapping")

    known_sections = {"meter", "radio", "http", "log_level"}
    unknown = set(raw) - known_sections
    if unknown:
        raise ConfigError(f"unknown config section(s): {', '.join(sorted(unknown))}")

    aes_key = None
    key_hex = os.environ.get(AES_KEY_ENV_VAR) or (raw.get("meter") or {}).get(
        "aes_key"
    )
    if key_hex:
        aes_key = _parse_aes_key(str(key_hex))

    return Config(
        aes_key=aes_key,
        radio=_build(RadioConfig, raw.get("radio") or {}, "radio"),
        http=_build(HttpConfig, raw.get("http") or {}, "http"),
        log_level=str(raw.get("log_level", "INFO")),
    )

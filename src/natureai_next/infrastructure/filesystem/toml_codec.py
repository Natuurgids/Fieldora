"""Minimal deterministic TOML serializer for supported configuration values."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from pathlib import Path


def dumps_toml(document: Mapping[str, object]) -> str:
    lines: list[str] = []
    scalar_items = [
        (key, value) for key, value in document.items() if not isinstance(value, Mapping)
    ]
    table_items = [(key, value) for key, value in document.items() if isinstance(value, Mapping)]
    for key, value in scalar_items:
        lines.append(f"{_key(key)} = {_value(value)}")
    if scalar_items and table_items:
        lines.append("")
    for index, (section, values) in enumerate(table_items):
        lines.append(f"[{_key(section)}]")
        assert isinstance(values, Mapping)
        for key, value in values.items():
            if isinstance(value, Mapping):
                raise TypeError("Nested TOML tables deeper than one level are not supported")
            lines.append(f"{_key(str(key))} = {_value(value)}")
        if index != len(table_items) - 1:
            lines.append("")
    return "\n".join(lines) + "\n"


def _key(value: str) -> str:
    if value.replace("_", "").replace("-", "").isalnum():
        return value
    return _quote(value)


def _value(value: object) -> str:
    if isinstance(value, Enum):
        return _quote(str(value.value))
    if isinstance(value, Path):
        return _quote(str(value))
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, tuple | list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'

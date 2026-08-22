"""Offline-first internationalization services for Aperture.

The service intentionally has no Qt dependency.  Core and plugin code can use the
same catalog contract, while the UI may retranslate widgets at runtime.
"""
from __future__ import annotations

import json
import locale as system_locale
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Mapping

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "nl", "de", "fr", "es", "pt", "it")


@dataclass(frozen=True, slots=True)
class LocaleInfo:
    code: str
    name: str
    decimal_separator: str
    date_pattern: str


_LOCALE_INFO: dict[str, LocaleInfo] = {
    "en": LocaleInfo("en", "English", ".", "yyyy-MM-dd"),
    "nl": LocaleInfo("nl", "Nederlands", ",", "dd-MM-yyyy"),
    "de": LocaleInfo("de", "Deutsch", ",", "dd.MM.yyyy"),
    "fr": LocaleInfo("fr", "Français", ",", "dd/MM/yyyy"),
    "es": LocaleInfo("es", "Español", ",", "dd/MM/yyyy"),
    "pt": LocaleInfo("pt", "Português", ",", "dd/MM/yyyy"),
    "it": LocaleInfo("it", "Italiano", ",", "dd/MM/yyyy"),
}


class TranslationCatalog:
    """Merged built-in and plugin translation catalog with English fallback."""

    def __init__(self, resource_root: Path | None = None) -> None:
        self._root = resource_root or Path(__file__).resolve().parents[1] / "resources" / "i18n"
        self._catalogs: dict[str, dict[str, str]] = {}
        self._lock = RLock()

    def load(self, locale_code: str) -> Mapping[str, str]:
        code = normalize_locale(locale_code)
        with self._lock:
            if code not in self._catalogs:
                path = self._root / f"{code}.json"
                values: dict[str, str] = {}
                if path.exists():
                    document = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(document, dict):
                        values = {str(k): str(v) for k, v in document.items()}
                self._catalogs[code] = values
            return dict(self._catalogs[code])

    def add_plugin_catalog(self, locale_code: str, values: Mapping[str, str]) -> None:
        code = normalize_locale(locale_code)
        with self._lock:
            merged = dict(self.load(code))
            merged.update({str(k): str(v) for k, v in values.items()})
            self._catalogs[code] = merged


class LocaleService:
    """Runtime locale selection and deterministic translation lookup."""

    def __init__(self, catalog: TranslationCatalog | None = None, locale_code: str | None = None):
        self._catalog = catalog or TranslationCatalog()
        self._locale = normalize_locale(locale_code or detect_system_locale())

    @property
    def locale(self) -> str:
        return self._locale

    @property
    def info(self) -> LocaleInfo:
        return _LOCALE_INFO[self._locale]

    def set_locale(self, locale_code: str) -> None:
        self._locale = normalize_locale(locale_code)

    def translate(self, key: str, default: str | None = None, **values: object) -> str:
        text = self._catalog.load(self._locale).get(key)
        if text is None and self._locale != DEFAULT_LOCALE:
            text = self._catalog.load(DEFAULT_LOCALE).get(key)
        text = text if text is not None else (default if default is not None else key)
        return text.format_map(_SafeValues(values))

    def available_locales(self) -> tuple[LocaleInfo, ...]:
        return tuple(_LOCALE_INFO[code] for code in SUPPORTED_LOCALES)


class _SafeValues(dict[str, object]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def normalize_locale(locale_code: str) -> str:
    code = locale_code.strip().replace("_", "-").split("-", 1)[0].lower()
    return code if code in SUPPORTED_LOCALES else DEFAULT_LOCALE


def detect_system_locale() -> str:
    value = system_locale.getlocale()[0] or DEFAULT_LOCALE
    return normalize_locale(value)

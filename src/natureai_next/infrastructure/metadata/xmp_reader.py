"""Bounded, read-only extraction of standard descriptive XMP fields."""

from __future__ import annotations

from pathlib import Path

from defusedxml import ElementTree

from natureai_next.ports.media import MetadataResult

_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
}


class XmpMetadataReader:
    def __init__(
        self,
        *,
        max_bytes: int = 4 * 1024 * 1024,
        max_values: int = 512,
        max_text_length: int = 10_000,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_values = max_values
        self.max_text_length = max_text_length

    def read(self, path: Path) -> MetadataResult:
        size = path.stat().st_size
        if size > self.max_bytes:
            raise ValueError("XMP sidecar exceeds metadata size limit")
        payload = path.read_bytes()
        lowered = payload.lower()
        if b"<!doctype" in lowered or b"<!entity" in lowered:
            raise ValueError("XMP sidecar contains a prohibited document type or entity")
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            raise ValueError(f"cannot parse XMP sidecar: {path.name}") from exc
        title = self._first_alt(root, "dc:title")
        caption = self._first_alt(root, "dc:description")
        rights = self._first_alt(root, "dc:rights")
        creators = self._list(root, "dc:creator")
        keywords = self._list(root, "dc:subject")
        raw = {
            key: value
            for key, value in {
                "dc:title": title,
                "dc:description": caption,
                "dc:rights": rights,
                "dc:creator": creators,
                "dc:subject": keywords,
            }.items()
            if value not in (None, ())
        }
        normalized = {
            "title": title,
            "caption": caption,
            "rights": rights,
            "creators": creators,
            "keywords": keywords,
        }
        return MetadataResult(normalized, raw)

    def _first_alt(self, root: ElementTree.Element, field: str) -> str | None:
        values = self._list(root, field)
        return values[0] if values else None

    def _list(self, root: ElementTree.Element, field: str) -> tuple[str, ...]:
        parent = root.find(f".//{field}", _NS)
        if parent is None:
            return ()
        values: list[str] = []
        for item in parent.findall(".//rdf:li", _NS):
            text = " ".join((item.text or "").split())[: self.max_text_length]
            if text and text.casefold() not in {value.casefold() for value in values}:
                values.append(text)
            if len(values) >= self.max_values:
                break
        return tuple(values)

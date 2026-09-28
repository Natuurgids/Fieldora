"""Canonical media-type inference for Fieldora evidence.

Client/browser MIME declarations are hints, not authoritative metadata.  In
particular Qt/WebView and some OS integrations report an empty type for ordinary
files, which previously became application/octet-stream throughout the Library.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

_GENERIC = frozenset({"", "application/octet-stream", "binary/octet-stream"})
_OVERRIDES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".pdf": "application/pdf",
    ".svg": "image/svg+xml",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def canonical_media_type(filename: str, declared: str = "") -> str:
    """Return a useful bounded MIME type, preferring a specific declaration.

    Generic/empty client declarations are replaced using the filename extension.
    Unknown extensions remain application/octet-stream rather than being guessed
    from untrusted content bytes.
    """
    supplied = declared.strip().lower().split(";", 1)[0][:200]
    if supplied not in _GENERIC:
        return supplied
    suffix = Path(filename).suffix.casefold()
    inferred = _OVERRIDES.get(suffix) or mimetypes.guess_type(filename)[0]
    return (inferred or "application/octet-stream")[:200]

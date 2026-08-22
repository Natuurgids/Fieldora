"""Deterministic ZIP codec for portable Fieldora project packages."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from natureai_next.domain.science_packages import (
    SCIENCE_PACKAGE_FORMAT,
    SCIENCE_PACKAGE_VERSION,
)

_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class SciencePackageCodec:
    @staticmethod
    def _json_bytes(value: object) -> bytes:
        return (
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")

    @staticmethod
    def _write_member(archive: zipfile.ZipFile, name: str, payload: bytes) -> None:
        info = zipfile.ZipInfo(name, _ZIP_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o600 << 16
        archive.writestr(info, payload)

    def write(self, destination: Path, manifest: dict, records: dict) -> str:
        destination = destination.expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        records_bytes = self._json_bytes(records)
        manifest = {
            **manifest,
            "format": SCIENCE_PACKAGE_FORMAT,
            "format_version": SCIENCE_PACKAGE_VERSION,
            "records_file": "records.json",
            "records_sha256": hashlib.sha256(records_bytes).hexdigest(),
        }
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with zipfile.ZipFile(temporary, "w") as archive:
            self._write_member(archive, "manifest.json", self._json_bytes(manifest))
            self._write_member(archive, "records.json", records_bytes)
        temporary.replace(destination)
        return self.digest(destination)

    def read(self, source: Path) -> tuple[dict, dict, str]:
        source = source.expanduser().resolve()
        digest = self.digest(source)
        with zipfile.ZipFile(source, "r") as archive:
            names = set(archive.namelist())
            if names != {"manifest.json", "records.json"}:
                raise ValueError("portable project package has unexpected files")
            for member in archive.infolist():
                if member.file_size > 100 * 1024 * 1024:
                    raise ValueError("portable project package member exceeds 100 MB")
                if (
                    member.compress_size > 0
                    and member.file_size / member.compress_size > 200
                ):
                    raise ValueError("portable project package has an unsafe compression ratio")
            manifest_bytes = archive.read("manifest.json")
            records_bytes = archive.read("records.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        records = json.loads(records_bytes.decode("utf-8"))
        if (
            manifest.get("format") != SCIENCE_PACKAGE_FORMAT
            or manifest.get("format_version") != SCIENCE_PACKAGE_VERSION
        ):
            raise ValueError("unsupported portable project package")
        if manifest.get("records_file") != "records.json":
            raise ValueError("portable project package names an invalid records file")
        if hashlib.sha256(records_bytes).hexdigest() != manifest.get("records_sha256"):
            raise ValueError("portable project records checksum mismatch")
        if not isinstance(records, dict):
            raise ValueError("portable project records must be an object")
        return manifest, records, digest

    @staticmethod
    def digest(path: Path) -> str:
        result = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                result.update(chunk)
        return result.hexdigest()

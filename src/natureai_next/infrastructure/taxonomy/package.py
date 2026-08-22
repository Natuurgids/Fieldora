"""Signed taxonomy package verification and deterministic package building."""

from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from packaging.version import Version

from natureai_next import __version__
from natureai_next.domain.taxonomy import (
    LicenseMetadata,
    TaxonNameRecord,
    TaxonomyPackageData,
    TaxonRecord,
    TaxonRegionRecord,
    TaxonStatus,
)

_MAX_PACKAGE_BYTES = 512 * 1024 * 1024
_MAX_RECORDS = 5_000_000
_REQUIRED_FILES = ("taxa.jsonl", "names.jsonl", "regions.jsonl")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_jsonl(data: bytes, maximum: int) -> list[dict[str, Any]]:
    result = []
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        if len(result) >= maximum:
            raise ValueError("taxonomy package record limit exceeded")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL record {line_number} is not an object")
        result.append(value)
    return result


class Ed25519TaxonomyPackageVerifier:
    def __init__(
        self, trusted_keys: dict[str, bytes], *, application_version: str = __version__
    ) -> None:
        if not trusted_keys:
            raise ValueError("at least one trusted key is required")
        self._keys = dict(trusted_keys)
        self._application_version = Version(application_version)

    def verify(self, path: Path) -> TaxonomyPackageData:
        if not path.is_file() or path.stat().st_size > _MAX_PACKAGE_BYTES:
            raise ValueError("invalid taxonomy package size")
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            if "manifest.json" not in names or not set(_REQUIRED_FILES).issubset(names):
                raise ValueError("taxonomy package is incomplete")
            if any(
                info.file_size > _MAX_PACKAGE_BYTES
                or info.filename.startswith(("/", "\\"))
                or ".." in Path(info.filename).parts
                for info in archive.infolist()
            ):
                raise ValueError("unsafe taxonomy package entry")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("schema_version") != 1:
                raise ValueError("unsupported taxonomy package schema")
            key_id = str(manifest.get("key_id", ""))
            signature_text = str(manifest.get("signature", ""))
            key = self._keys.get(key_id)
            if key is None:
                raise ValueError("untrusted taxonomy signing key")
            unsigned = dict(manifest)
            unsigned.pop("signature", None)
            try:
                Ed25519PublicKey.from_public_bytes(key).verify(
                    base64.b64decode(signature_text, validate=True), _canonical(unsigned)
                )
            except (InvalidSignature, ValueError) as exc:
                raise ValueError("invalid taxonomy package signature") from exc
            files = manifest.get("files")
            if not isinstance(files, dict):
                raise ValueError("taxonomy manifest files are invalid")
            payloads: dict[str, bytes] = {}
            for name in _REQUIRED_FILES:
                data = archive.read(name)
                expected = files.get(name)
                if (
                    not isinstance(expected, dict)
                    or expected.get("sha256") != _sha(data)
                    or expected.get("bytes") != len(data)
                ):
                    raise ValueError(f"taxonomy payload checksum mismatch: {name}")
                payloads[name] = data
        minimum = Version(str(manifest["minimum_app_version"]))
        if minimum > self._application_version:
            raise ValueError("taxonomy package requires a newer application")
        license_value = manifest.get("license")
        if not isinstance(license_value, dict):
            raise ValueError("license metadata is required")
        license_meta = LicenseMetadata(
            str(license_value.get("name", "")),
            license_value.get("url"),
            str(license_value.get("attribution", "")),
            bool(license_value.get("redistribution_allowed", False)),
        )
        license_meta.validate()
        taxa = tuple(
            TaxonRecord(
                source_taxon_id=str(v["source_taxon_id"]),
                scientific_name=str(v["scientific_name"]),
                rank=str(v["rank"]),
                status=TaxonStatus(str(v["status"])),
                parent_source_taxon_id=v.get("parent_source_taxon_id"),
                accepted_source_taxon_id=v.get("accepted_source_taxon_id"),
                authorship=v.get("authorship"),
                kingdom=v.get("kingdom"),
                major_group=v.get("major_group"),
                extinct=bool(v.get("extinct", False)),
            )
            for v in _load_jsonl(payloads["taxa.jsonl"], _MAX_RECORDS)
        )
        names = tuple(
            TaxonNameRecord(
                source_taxon_id=str(v["source_taxon_id"]),
                name=str(v["name"]),
                name_type=str(v["name_type"]),
                source=str(v["source"]),
                language_tag=v.get("language_tag"),
                region_code=v.get("region_code"),
                preferred=bool(v.get("preferred", False)),
            )
            for v in _load_jsonl(payloads["names.jsonl"], _MAX_RECORDS)
        )
        regions = tuple(
            TaxonRegionRecord(
                source_taxon_id=str(v["source_taxon_id"]),
                region_code=str(v["region_code"]).upper(),
                occurrence_status=v.get("occurrence_status"),
                source=str(v["source"]),
            )
            for v in _load_jsonl(payloads["regions.jsonl"], _MAX_RECORDS)
        )
        for taxon in taxa:
            taxon.validate()
        package_checksum = _sha(path.read_bytes())
        return TaxonomyPackageData(
            str(manifest["package_id"]),
            str(manifest["source_name"]),
            str(manifest["source_version"]),
            str(manifest["minimum_app_version"]),
            license_meta,
            taxa,
            names,
            regions,
            package_checksum,
            str(manifest.get("attribution_text", license_meta.attribution)),
        )


def build_taxonomy_package(
    path: Path,
    *,
    private_key: Ed25519PrivateKey,
    key_id: str,
    package_id: str,
    source_name: str,
    source_version: str,
    minimum_app_version: str,
    license_metadata: LicenseMetadata,
    taxa: Iterable[dict[str, object]],
    names: Iterable[dict[str, object]] = (),
    regions: Iterable[dict[str, object]] = (),
    attribution_text: str | None = None,
) -> Path:
    payloads = {
        "taxa.jsonl": b"".join(_canonical(x) + b"\n" for x in taxa),
        "names.jsonl": b"".join(_canonical(x) + b"\n" for x in names),
        "regions.jsonl": b"".join(_canonical(x) + b"\n" for x in regions),
    }
    manifest = {
        "schema_version": 1,
        "package_id": package_id,
        "source_name": source_name,
        "source_version": source_version,
        "minimum_app_version": minimum_app_version,
        "key_id": key_id,
        "license": {
            "name": license_metadata.name,
            "url": license_metadata.url,
            "attribution": license_metadata.attribution,
            "redistribution_allowed": license_metadata.redistribution_allowed,
        },
        "attribution_text": attribution_text or license_metadata.attribution,
        "files": {
            name: {"sha256": _sha(data), "bytes": len(data)} for name, data in payloads.items()
        },
    }
    manifest["signature"] = base64.b64encode(private_key.sign(_canonical(manifest))).decode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", _canonical(manifest))
        [archive.writestr(name, data) for name, data in payloads.items()]
    return path

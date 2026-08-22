"""Signed offline model package verification, installation, and activation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from packaging.version import Version

from natureai_next import __version__
from natureai_next.domain.ai import (
    ModelArtifact,
    ModelPackageManifest,
    ModelVariantManifest,
    Precision,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory

_MAX_PACKAGE_BYTES = 8 * 1024 * 1024 * 1024
_MAX_ARTIFACTS = 128


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ModelPackageVerifier:
    def __init__(
        self, trusted_keys: dict[str, bytes], application_version: str = __version__
    ) -> None:
        if not trusted_keys:
            raise ValueError("at least one trusted model signing key is required")
        self._keys = dict(trusted_keys)
        self._application_version = Version(application_version)

    def verify(self, package_path: Path) -> tuple[ModelPackageManifest, dict[str, bytes], str]:
        if not package_path.is_file() or package_path.stat().st_size > _MAX_PACKAGE_BYTES:
            raise ValueError("invalid model package size")
        with zipfile.ZipFile(package_path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > _MAX_ARTIFACTS + 1:
                raise ValueError("model package contains too many files")
            if "manifest.json" not in archive.namelist():
                raise ValueError("model package manifest is missing")
            for info in infos:
                parts = Path(info.filename).parts
                if (
                    info.filename.startswith(("/", "\\"))
                    or ".." in parts
                    or info.file_size > _MAX_PACKAGE_BYTES
                ):
                    raise ValueError("unsafe model package entry")
            raw_manifest = json.loads(archive.read("manifest.json"))
            if raw_manifest.get("schema_version") != 1:
                raise ValueError("unsupported model package schema")
            signature_text = str(raw_manifest.get("signature", ""))
            unsigned = dict(raw_manifest)
            unsigned.pop("signature", None)
            key_id = str(unsigned.get("signing_key_id", ""))
            key = self._keys.get(key_id)
            if key is None:
                raise ValueError("untrusted model signing key")
            try:
                Ed25519PublicKey.from_public_bytes(key).verify(
                    base64.b64decode(signature_text, validate=True), _canonical(unsigned)
                )
            except (InvalidSignature, ValueError) as exc:
                raise ValueError("invalid model package signature") from exc
            if Version(str(unsigned["minimum_application_version"])) > self._application_version:
                raise ValueError("model package requires a newer application")
            artifacts: list[ModelArtifact] = []
            payloads: dict[str, bytes] = {}
            for item in unsigned.get("artifacts", []):
                relative_path = str(item["relative_path"])
                if relative_path not in archive.namelist():
                    raise ValueError(f"missing model artifact: {relative_path}")
                data = archive.read(relative_path)
                if len(data) != int(item["size_bytes"]) or _sha256(data) != str(item["sha256"]):
                    raise ValueError(f"model artifact checksum mismatch: {relative_path}")
                payloads[relative_path] = data
                artifacts.append(ModelArtifact(relative_path, str(item["sha256"]), len(data)))
            variant_rows = tuple(unsigned.get("variants", []))
            for item in variant_rows:
                runtime = str(item.get("runtime", ""))
                if runtime not in {"torch", "onnx"}:
                    raise ValueError(f"unsupported model runtime: {runtime}")
            variants = tuple(
                ModelVariantManifest(
                    identity=str(item["identity"]),
                    runtime=str(item["runtime"]),
                    precision=Precision(str(item["precision"])),
                    providers=tuple(str(x) for x in item["providers"]),
                    preprocessing_identity=str(item["preprocessing_identity"]),
                    embedding_dimension=int(item["embedding_dimension"]),
                    input_size=int(item["input_size"]),
                    normalized_output=bool(item["normalized_output"]),
                    artifact_path=str(item["artifact_path"]),
                )
                for item in variant_rows
            )
            if not artifacts or not variants:
                raise ValueError("model package requires artifacts and variants")
            artifact_paths = {item.relative_path for item in artifacts}
            if any(item.artifact_path not in artifact_paths for item in variants):
                raise ValueError("model variant references an unknown artifact")
            manifest = ModelPackageManifest(
                1,
                str(unsigned["package_id"]),
                str(unsigned["model_identity"]),
                str(unsigned["semantic_version"]),
                str(unsigned["model_family"]),
                str(unsigned["upstream_source"]),
                str(unsigned["license_name"]),
                str(unsigned["attribution_text"]),
                str(unsigned["minimum_application_version"]),
                key_id,
                tuple(artifacts),
                variants,
            )
        return manifest, payloads, _sha256(package_path.read_bytes())


class ModelPackageInstaller:
    def __init__(
        self, factory: SqliteConnectionFactory, models_root: Path, verifier: ModelPackageVerifier
    ) -> None:
        self._factory = factory
        self._root = models_root
        self._verifier = verifier

    def install(self, package_path: Path, *, activate: bool = True) -> str:
        manifest, payloads, package_checksum = self._verifier.verify(package_path)
        final_dir = self._root / manifest.model_identity / manifest.semantic_version
        self._root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".model-staging-", dir=self._root))
        try:
            for relative_path, data in payloads.items():
                target = staging / relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                if _sha256(target.read_bytes()) != _sha256(data):
                    raise OSError(f"staged model artifact verification failed: {relative_path}")
            manifest_json = json.dumps(
                asdict(manifest), sort_keys=True, separators=(",", ":"), default=str
            )
            (staging / "installed-manifest.json").write_text(manifest_json, encoding="utf-8")
            if final_dir.exists():
                shutil.rmtree(staging)
            else:
                final_dir.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging, final_dir)
            now = time.time_ns() // 1000
            connection = self._factory.connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT id,artifact_checksum FROM model_packages WHERE package_id=?",
                    (manifest.package_id,),
                ).fetchone()
                if existing is not None and existing[1] != package_checksum:
                    # Older packages were ZIP-hashed, so rebuilding the exact same
                    # signed manifest could produce a different checksum solely from
                    # ZIP member timestamps. Accept only when the installed semantic
                    # manifest and every artifact byte still match the verified input.
                    installed_manifest = final_dir / "installed-manifest.json"
                    same_content = False
                    try:
                        same_content = json.loads(
                            installed_manifest.read_text(encoding="utf-8")
                        ) == json.loads(manifest_json) and all(
                            (final_dir / relative_path).is_file()
                            and _sha256((final_dir / relative_path).read_bytes()) == _sha256(data)
                            for relative_path, data in payloads.items()
                        )
                    except (OSError, ValueError, json.JSONDecodeError):
                        same_content = False
                    if not same_content:
                        raise ValueError("model package identity was reused with different content")
                    connection.execute(
                        "UPDATE model_packages SET artifact_checksum=?,manifest_json=? WHERE id=?",
                        (package_checksum, manifest_json, int(existing[0])),
                    )
                if existing is None:
                    cursor = connection.execute(
                        "INSERT INTO model_packages(public_id,model_identity,semantic_version,model_family,artifact_checksum,manifest_json,license_json,install_path_token,installation_state,installed_at_us,package_id,signature_key_id,activated_at_us,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            manifest.package_id,
                            manifest.model_identity,
                            manifest.semantic_version,
                            manifest.model_family,
                            package_checksum,
                            manifest_json,
                            json.dumps(
                                {
                                    "name": manifest.license_name,
                                    "attribution": manifest.attribution_text,
                                },
                                sort_keys=True,
                            ),
                            str(final_dir),
                            "installed",
                            now,
                            manifest.package_id,
                            manifest.signing_key_id,
                            now if activate else None,
                            1 if activate else 0,
                        ),
                    )
                    package_db_id = int(cursor.lastrowid)
                    for variant in manifest.variants:
                        connection.execute(
                            "INSERT INTO model_variants(public_id,package_id,variant_identity,runtime,precision,device_requirements_json,preprocessing_identity,embedding_dimension,active,input_size,normalized_output,artifact_relative_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (
                                f"{manifest.package_id}:{variant.identity}",
                                package_db_id,
                                variant.identity,
                                variant.runtime,
                                variant.precision.value,
                                json.dumps({"providers": variant.providers}),
                                variant.preprocessing_identity,
                                variant.embedding_dimension,
                                1 if activate else 0,
                                variant.input_size,
                                1 if variant.normalized_output else 0,
                                variant.artifact_path,
                            ),
                        )
                else:
                    package_db_id = int(existing[0])
                if activate:
                    connection.execute(
                        "UPDATE model_packages SET active=0 WHERE model_identity=? AND id<>?",
                        (manifest.model_identity, package_db_id),
                    )
                    connection.execute(
                        "UPDATE model_variants SET active=0 WHERE package_id IN (SELECT id FROM model_packages WHERE model_identity=? AND id<>?)",
                        (manifest.model_identity, package_db_id),
                    )
                    connection.execute(
                        "UPDATE model_packages SET active=1,activated_at_us=? WHERE id=?",
                        (now, package_db_id),
                    )
                    connection.execute(
                        "UPDATE model_variants SET active=1 WHERE package_id=?", (package_db_id,)
                    )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
            return manifest.package_id
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)


def build_model_package(
    path: Path,
    *,
    private_key: Ed25519PrivateKey,
    manifest: dict[str, Any],
    artifacts: dict[str, bytes],
) -> Path:
    value = dict(manifest)
    value["schema_version"] = 1
    value["artifacts"] = [
        {"relative_path": name, "sha256": _sha256(data), "size_bytes": len(data)}
        for name, data in sorted(artifacts.items())
    ]
    value["signature"] = base64.b64encode(private_key.sign(_canonical(value))).decode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Fixed metadata makes rebuilt packages byte-for-byte reproducible. This
    # prevents false identity collisions when setup is rerun with unchanged data.
    fixed_time = (1980, 1, 1, 0, 0, 0)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        manifest_info = zipfile.ZipInfo("manifest.json", fixed_time)
        manifest_info.compress_type = zipfile.ZIP_DEFLATED
        manifest_info.external_attr = 0o600 << 16
        archive.writestr(manifest_info, _canonical(value))
        for name, data in sorted(artifacts.items()):
            artifact_info = zipfile.ZipInfo(name, fixed_time)
            artifact_info.compress_type = zipfile.ZIP_DEFLATED
            artifact_info.external_attr = 0o600 << 16
            archive.writestr(artifact_info, data)
    return path

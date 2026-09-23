"""Verify standalone Bastion dataset transfers before Fieldora authorization/import."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from natureai_next.application.security_install import require_security_install
from natureai_next.domain.security_install import (
    AuthenticatedReleaseContext,
    SecurityInstallAcceptanceError,
    canonical_sha256,
    file_sha256,
)

_ALLOWED_TYPES = {"map_dataset", "biodiversity_dataset"}
_MAX_EVIDENCE_BYTES = 4 * 1024 * 1024
_MAX_SIGNATURE_BYTES = 16 * 1024
_MAX_ZIP_MEMBERS = 100_000
_MAX_MEMBER_BYTES = 8 * 1024 * 1024 * 1024
_MAX_TOTAL_UNCOMPRESSED_BYTES = 64 * 1024 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 200


class DatasetTransferError(ValueError):
    """Raised when a Bastion dataset transfer cannot be independently authenticated."""


@dataclass(frozen=True, slots=True)
class VerifiedDatasetTransfer:
    artifact_type: str
    artifact_id: str
    version: str
    package_id: str
    payload_sha256: str
    file_count: int
    release: AuthenticatedReleaseContext
    evidence: dict[str, object]


def verify_dataset_transfer(
    artifact_path: Path,
    evidence_path: Path,
    signature_path: Path,
    trusted_signing_key: Path,
) -> VerifiedDatasetTransfer:
    for path, label, limit in (
        (evidence_path, "evidence", _MAX_EVIDENCE_BYTES),
        (signature_path, "signature", _MAX_SIGNATURE_BYTES),
        (trusted_signing_key, "trusted signing key", _MAX_SIGNATURE_BYTES),
    ):
        if path.is_symlink() or not path.is_file():
            raise DatasetTransferError(f"{label} must be a regular non-symlink file")
        if path.stat().st_size > limit:
            raise DatasetTransferError(f"{label} exceeds the configured size limit")
    if artifact_path.is_symlink() or not artifact_path.is_file():
        raise DatasetTransferError("artifact must be a regular non-symlink file")

    try:
        evidence_bytes = evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes)
        envelope = json.loads(signature_path.read_text(encoding="utf-8"))
        signature = base64.b64decode(str(envelope.get("signature") or ""), validate=True)
        public_key = serialization.load_pem_public_key(trusted_signing_key.read_bytes())
    except (OSError, ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DatasetTransferError("dataset transfer authentication material is invalid") from exc
    if not isinstance(evidence, dict) or not isinstance(envelope, dict):
        raise DatasetTransferError("dataset transfer evidence and signature must be objects")
    if envelope.get("algorithm") != "ed25519" or not isinstance(public_key, Ed25519PublicKey):
        raise DatasetTransferError("dataset transfer requires an Ed25519 trusted key")
    public_der = public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    key_id = hashlib.sha256(public_der).hexdigest()[:32]
    if str(envelope.get("key_id") or "") != key_id or str(evidence.get("signer_key_id") or "") != key_id:
        raise DatasetTransferError("dataset transfer signer does not match trusted key")
    try:
        public_key.verify(signature, evidence_bytes)
    except InvalidSignature as exc:
        raise DatasetTransferError("dataset transfer evidence signature verification failed") from exc

    artifact_type = str(evidence.get("artifact_type") or "")
    artifact_id = str(evidence.get("artifact_id") or "")
    version = str(evidence.get("version") or "")
    if artifact_type not in _ALLOWED_TYPES or not artifact_id or not version:
        raise DatasetTransferError("dataset transfer identity is invalid")
    artifact = evidence.get("artifact")
    if not isinstance(artifact, dict):
        raise DatasetTransferError("dataset transfer artifact evidence is invalid")
    package_id = str(artifact.get("package_id") or "")
    expected_sha = str(artifact.get("sha256") or "").lower()
    try:
        expected_size = int(artifact.get("size"))
        file_count = int(evidence.get("file_count"))
    except (TypeError, ValueError) as exc:
        raise DatasetTransferError("dataset transfer sizes are invalid") from exc
    if package_id != artifact_path.name or expected_size != artifact_path.stat().st_size:
        raise DatasetTransferError("dataset transfer artifact identity or size mismatch")
    actual_sha = file_sha256(artifact_path)
    if expected_sha != actual_sha:
        raise DatasetTransferError("dataset transfer artifact digest mismatch")
    payload_sha = str(evidence.get("payload_sha256") or "").lower()
    if len(payload_sha) != 64 or any(c not in "0123456789abcdef" for c in payload_sha) or file_count < 1:
        raise DatasetTransferError("dataset transfer payload binding is invalid")
    validation = evidence.get("type_validation")
    if not isinstance(validation, dict) or validation.get("approved") is not True:
        raise DatasetTransferError("dataset transfer type validation is not approved")

    release_payload = {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "version": version,
        "package_sha256": actual_sha,
        "signer_key_id": key_id,
    }
    release_digest = canonical_sha256(release_payload)
    if str(evidence.get("release_digest") or "").lower() != release_digest:
        raise DatasetTransferError("dataset transfer release binding mismatch")
    release_id = f"fieldora-artifact:{artifact_type}:{artifact_id}:{version}"
    if str(evidence.get("release_id") or "") != release_id:
        raise DatasetTransferError("dataset transfer release identity mismatch")

    return VerifiedDatasetTransfer(
        artifact_type, artifact_id, version, package_id, payload_sha, file_count,
        AuthenticatedReleaseContext(release_id, release_digest, key_id), evidence,
    )



def _security_install_evidence(verified: VerifiedDatasetTransfer, artifact_path: Path) -> dict[str, object]:
    """Translate authenticated Bastion facts into the provider-neutral Fieldora gate."""
    artifact_sha = file_sha256(artifact_path)
    component = f"fieldora-dataset:{verified.artifact_type}:{verified.artifact_id}"
    compatibility_payload = {
        "release_id": verified.release.release_id,
        "component": component,
        "version": verified.version,
    }
    return {
        "protocol_version": 1,
        "release_id": verified.release.release_id,
        "package_id": verified.package_id,
        "release_digest": verified.release.release_digest,
        "target": {
            "component": component,
            "version": verified.version,
            "compatible_from": ["not-installed"],
        },
        "artifact": {
            "package_id": verified.package_id,
            "sha256": artifact_sha,
            "size": artifact_path.stat().st_size,
        },
        "compatibility_approval": {
            "approved": True,
            "payload": compatibility_payload,
            "approval_digest": canonical_sha256(compatibility_payload),
        },
        "controlled_supply_chain": {
            "approved": True,
            "bastion_verified": True,
            "offline_transfer": True,
        },
        "provenance": {"release_digest": verified.release.release_digest},
        "secure_transfer": {
            "provider_id": "fieldora-bastion",
            "capability": "secure-transfer",
            "protocol_version": 1,
            "approved": True,
            "release_digest": verified.release.release_digest,
        },
        "transfer_receipt": {
            "package_id": verified.package_id,
            "collector_id": "fieldora-dataset-installer",
            "expected_sha256": artifact_sha,
            "observed_sha256": artifact_sha,
            "status": "accepted",
        },
        "independent_verification": {
            "verified": True,
            "package_id": verified.package_id,
            "release_digest": verified.release.release_digest,
            "sha256": artifact_sha,
        },
    }


def _zip_member_is_symlink(info: ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0o170000) == 0o120000


def _verify_archive_payload(artifact_path: Path, verified: VerifiedDatasetTransfer) -> None:
    """Independently bind ZIP members to Bastion's signed canonical payload digest."""
    digest = hashlib.sha256()
    file_count = 0
    try:
        with ZipFile(artifact_path, "r") as archive:
            files: list[tuple[str, int, str]] = []
            seen: set[str] = set()
            infos = archive.infolist()
            if len(infos) > _MAX_ZIP_MEMBERS:
                raise DatasetTransferError("dataset ZIP contains too many members")
            total_uncompressed = 0
            for info in infos:
                raw_name = info.filename
                raw = raw_name.replace("\\", "/")
                path = PurePosixPath(raw)
                first = path.parts[0] if path.parts else ""
                if (
                    not raw
                    or raw.startswith("//")
                    or path.is_absolute()
                    or (len(first) >= 2 and first[1] == ":" and first[0].isalpha())
                    or any(part in {"", ".", ".."} for part in path.parts)
                ):
                    raise DatasetTransferError("dataset ZIP contains an unsafe path")
                name = path.as_posix()
                if name in seen:
                    raise DatasetTransferError("dataset ZIP contains duplicate paths")
                seen.add(name)
                mode = (info.external_attr >> 16) & 0o170000
                if _zip_member_is_symlink(info):
                    raise DatasetTransferError("dataset ZIP contains a symlink")
                if mode not in {0, 0o100000, 0o040000}:
                    raise DatasetTransferError("dataset ZIP contains a special file")
                if info.is_dir():
                    continue
                if info.file_size > _MAX_MEMBER_BYTES:
                    raise DatasetTransferError("dataset ZIP member exceeds the size limit")
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_TOTAL_UNCOMPRESSED_BYTES:
                    raise DatasetTransferError("dataset ZIP exceeds the total size limit")
                compressed = max(info.compress_size, 1)
                if info.file_size > 1024 * 1024 and info.file_size / compressed > _MAX_COMPRESSION_RATIO:
                    raise DatasetTransferError("dataset ZIP member exceeds the compression ratio limit")
                member_digest = hashlib.sha256()
                size = 0
                with archive.open(info, "r") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        size += len(chunk)
                        member_digest.update(chunk)
                files.append((name, size, member_digest.hexdigest()))
            file_count = len(files)
            for name, size, sha256 in sorted(files):
                digest.update(f"{name}\0{size}\0{sha256}\n".encode())
    except DatasetTransferError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise DatasetTransferError("dataset artifact must be a readable safe ZIP") from exc
    if file_count != verified.file_count or digest.hexdigest() != verified.payload_sha256:
        raise DatasetTransferError("dataset ZIP payload does not match signed Bastion payload binding")


def _extract_verified_archive(artifact_path: Path, destination: Path) -> None:
    """Extract a previously verified ZIP without trusting archive paths or metadata."""
    try:
        with ZipFile(artifact_path, "r") as archive:
            for info in archive.infolist():
                raw = info.filename.replace("\\\\", "/")
                path = PurePosixPath(raw)
                target = destination.joinpath(*path.parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                size = 0
                with archive.open(info, "r") as source, target.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(chunk)
                        if size > info.file_size or size > _MAX_MEMBER_BYTES:
                            raise DatasetTransferError("dataset ZIP member changed during extraction")
                        output.write(chunk)
                if size != info.file_size:
                    raise DatasetTransferError("dataset ZIP member changed during extraction")
    except DatasetTransferError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise DatasetTransferError("dataset ZIP extraction failed") from exc


def install_dataset_transfer(
    artifact_path: Path,
    evidence_path: Path,
    signature_path: Path,
    trusted_signing_key: Path,
    dataset_store: Path,
    *,
    security_install_subject: str,
    access_control_database: Path | None = None,
    access_control_repository: object | None = None,
) -> tuple[VerifiedDatasetTransfer, Path]:
    """Verify, authorize and atomically activate a standalone dataset transfer."""
    verified = verify_dataset_transfer(
        artifact_path, evidence_path, signature_path, trusted_signing_key
    )
    _verify_archive_payload(artifact_path, verified)
    evidence = _security_install_evidence(verified, artifact_path)
    component = f"fieldora-dataset:{verified.artifact_type}:{verified.artifact_id}"

    def authorize() -> None:
        try:
            require_security_install(
                evidence,
                artifact_path=artifact_path,
                subject_id=security_install_subject,
                expected_package_id=verified.package_id,
                expected_target_component=component,
                actual_target_version="not-installed",
                authenticated_release=verified.release,
                access_control_database=access_control_database,
                access_control_repository=access_control_repository,
            )
        except SecurityInstallAcceptanceError as exc:
            raise DatasetTransferError(f"Security Install acceptance failed: {exc}") from exc

    authorize()
    destination = dataset_store / verified.artifact_type / verified.artifact_id / verified.version
    if destination.exists():
        raise DatasetTransferError("dataset version is already installed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".fieldora-dataset-", dir=destination.parent))
    try:
        staged_artifact = staging / verified.package_id
        shutil.copyfile(artifact_path, staged_artifact, follow_symlinks=False)
        if file_sha256(staged_artifact) != file_sha256(artifact_path):
            raise DatasetTransferError("dataset artifact changed during install staging")
        payload_dir = staging / "payload"
        payload_dir.mkdir()
        _extract_verified_archive(staged_artifact, payload_dir)
        (staging / "FIELDORA-INSTALL.json").write_text(
            json.dumps(
                {
                    "artifact_type": verified.artifact_type,
                    "artifact_id": verified.artifact_id,
                    "version": verified.version,
                    "release_id": verified.release.release_id,
                    "release_digest": verified.release.release_digest,
                    "signer_key_id": verified.release.signer_key_id,
                    "network": "offline",
                },
                sort_keys=True,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        _verify_archive_payload(staged_artifact, verified)
        authorize()
        if destination.exists():
            raise DatasetTransferError("dataset version is already installed")
        os.replace(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return verified, destination



def _postgres_repository(dsn_file: Path):
    if dsn_file.is_symlink() or not dsn_file.is_file() or dsn_file.stat().st_size > 16_384:
        raise DatasetTransferError("PostgreSQL access DSN file is invalid")
    dsn = dsn_file.read_text(encoding="utf-8").strip()
    if not dsn:
        raise DatasetTransferError("PostgreSQL access DSN file is empty")
    try:
        import psycopg
    except ImportError as exc:
        raise DatasetTransferError(
            "PostgreSQL Security Install requires the server-postgresql dependency"
        ) from exc
    from natureai_next.server.postgres_access import PostgresAccessControlRepository
    return PostgresAccessControlRepository(lambda: psycopg.connect(dsn, connect_timeout=10))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldora-dataset-transfer",
        description="Verify and install signed standalone Bastion dataset transfers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "install"):
        command = sub.add_parser(name)
        command.add_argument("artifact", type=Path)
        command.add_argument("--evidence", type=Path, required=True)
        command.add_argument("--signature", type=Path, required=True)
        command.add_argument("--trusted-signing-key", type=Path, required=True)
        if name == "install":
            command.add_argument("--store", type=Path, required=True)
            command.add_argument("--security-install-subject", required=True)
            access = command.add_mutually_exclusive_group(required=True)
            access.add_argument("--access-control-database", type=Path)
            access.add_argument("--postgres-access-dsn-file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            verified = verify_dataset_transfer(
                args.artifact, args.evidence, args.signature, args.trusted_signing_key
            )
            destination = None
        else:
            repository = (
                _postgres_repository(args.postgres_access_dsn_file)
                if args.postgres_access_dsn_file is not None else None
            )
            verified, destination = install_dataset_transfer(
                args.artifact, args.evidence, args.signature, args.trusted_signing_key,
                args.store, security_install_subject=args.security_install_subject,
                access_control_database=args.access_control_database,
                access_control_repository=repository,
            )
        output = {
            "ok": True,
            "artifact_type": verified.artifact_type,
            "artifact_id": verified.artifact_id,
            "version": verified.version,
            "release_id": verified.release.release_id,
            "signer_key_id": verified.release.signer_key_id,
        }
        if destination is not None:
            output["destination"] = str(destination)
    except (DatasetTransferError, OSError, UnicodeDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
        return 2
    print(json.dumps(output, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

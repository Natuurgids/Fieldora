"""Verified one-node server backup and non-destructive restore."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from natureai_next import __version__


@dataclass(frozen=True, slots=True)
class ServerBackupReport:
    archive: Path
    files: int
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RestoredRootReport:
    data_root: Path
    fieldora_version: str
    databases: tuple[str, ...]
    api_status: str

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fieldora.restored-root-readiness",
            "format_version": 1,
            "data_root": str(self.data_root),
            "fieldora_version": self.fieldora_version,
            "databases": list(self.databases),
            "api_status": self.api_status,
            "ready": True,
        }


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _safe_name(name: str) -> PurePosixPath:
    if "\\" in name:
        raise ValueError(f"unsafe backup member: {name}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(
        part in ("", ".", "..") for part in path.parts
    ):
        raise ValueError(f"unsafe backup member: {name}")
    return path


class OneNodeServerRecovery:
    DATABASE_SUFFIXES = (".sqlite3", ".db")
    LOCAL_OBJECT_ROOTS = ("server-media", "server-exports")

    def create(self, data_root: Path, destination: Path) -> ServerBackupReport:
        data_root = data_root.resolve(strict=True)
        destination = destination.expanduser().resolve()
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="fieldora-server-backup-", dir=destination.parent
        ) as temporary:
            stage = Path(temporary)
            entries: list[dict[str, object]] = []
            subsystem_root = data_root / "subsystems"
            for source in sorted(subsystem_root.iterdir() if subsystem_root.is_dir() else ()):
                if not source.is_file() or source.suffix.casefold() not in self.DATABASE_SUFFIXES:
                    continue
                relative = Path("databases") / source.name
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(
                    f"file:{source.as_posix()}?mode=ro", uri=True
                ) as source_connection, sqlite3.connect(target) as target_connection:
                    source_connection.backup(target_connection)
                    status = target_connection.execute("PRAGMA integrity_check").fetchone()
                    if status is None or str(status[0]).casefold() != "ok":
                        raise OSError(f"SQLite backup integrity failed: {source.name}")
                entries.append(self._entry(stage, target, "database"))
            for root_name in self.LOCAL_OBJECT_ROOTS:
                source_root = data_root / root_name
                if not source_root.is_dir():
                    continue
                for source in sorted(item for item in source_root.rglob("*") if item.is_file()):
                    relative = Path("objects") / root_name / source.relative_to(source_root)
                    target = stage / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    entries.append(self._entry(stage, target, "object"))
            manifest = {
                "format": "fieldora.one-node-server-backup",
                "format_version": 1,
                "fieldora_version": __version__,
                "created_at_utc": datetime.now(UTC).isoformat(),
                "files": entries,
                "external_dependencies": [
                    "S3-compatible objects when configured",
                    "TLS private key and certificate",
                    "export-signing private key and institutional trust material",
                ],
            }
            (stage / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary_archive = destination.with_suffix(destination.suffix + ".tmp")
            try:
                with zipfile.ZipFile(
                    temporary_archive, "x", compression=zipfile.ZIP_DEFLATED
                ) as archive:
                    for source in sorted(item for item in stage.rglob("*") if item.is_file()):
                        archive.write(source, source.relative_to(stage).as_posix())
                temporary_archive.replace(destination)
            except BaseException:
                temporary_archive.unlink(missing_ok=True)
                raise
        return self.verify(destination)

    def verify(self, archive_path: Path) -> ServerBackupReport:
        archive_path = archive_path.resolve(strict=True)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("backup contains duplicate members")
            safe_names = {_safe_name(name).as_posix() for name in names}
            if "manifest.json" not in safe_names:
                raise ValueError("backup manifest is missing")
            manifest = json.loads(archive.read("manifest.json"))
            if (
                manifest.get("format") != "fieldora.one-node-server-backup"
                or manifest.get("format_version") != 1
            ):
                raise ValueError("unsupported server backup")
            declared = {str(item["path"]): item for item in manifest.get("files", [])}
            if len(declared) != len(manifest.get("files", [])):
                raise ValueError("backup manifest contains duplicate paths")
            if safe_names != {"manifest.json", *declared}:
                raise ValueError("backup contents do not match manifest")
            with tempfile.TemporaryDirectory(prefix="fieldora-server-verify-") as temporary:
                root = Path(temporary)
                for name, entry in declared.items():
                    _safe_name(name)
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    if target.stat().st_size != int(entry["size_bytes"]):
                        raise ValueError(f"backup size mismatch: {name}")
                    if _digest(target) != str(entry["sha256"]):
                        raise ValueError(f"backup checksum mismatch: {name}")
                    if entry["kind"] == "database":
                        with sqlite3.connect(
                            f"file:{target.as_posix()}?mode=ro", uri=True
                        ) as connection:
                            status = connection.execute("PRAGMA integrity_check").fetchone()
                        if status is None or str(status[0]).casefold() != "ok":
                            raise ValueError(f"backup database is corrupt: {name}")
        return ServerBackupReport(
            archive_path, len(declared), archive_path.stat().st_size, _digest(archive_path)
        )

    def restore_to_new_root(self, archive_path: Path, destination: Path) -> Path:
        self.verify(archive_path)
        destination = destination.expanduser().resolve()
        if destination.exists():
            raise FileExistsError("restore destination must not exist")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=f".{destination.name}-restore-", dir=destination.parent
        ) as temporary:
            stage = Path(temporary) / destination.name
            stage.mkdir()
            with zipfile.ZipFile(archive_path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                for entry in manifest["files"]:
                    name = _safe_name(str(entry["path"]))
                    parts = name.parts
                    if parts[0] == "databases":
                        target = stage / "subsystems" / Path(*parts[1:])
                    elif parts[:2] in (
                        ("objects", "server-media"),
                        ("objects", "server-exports"),
                    ):
                        target = stage / Path(*parts[1:])
                    else:
                        raise ValueError(f"unsupported restore member: {name}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name.as_posix()) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
            stage.replace(destination)
        return destination

    def validate_restored_root(
        self, data_root: Path, report_path: Path | None = None
    ) -> RestoredRootReport:
        """Upgrade a recovery copy through current adapters and compose the API offline."""
        from natureai_next.application.access_control import PolicyDecisionService
        from natureai_next.application.authentication import AuthenticationService
        from natureai_next.application.device_authorization import (
            DeviceAuthorizationService,
        )
        from natureai_next.application.science import default_science_snapshot
        from natureai_next.infrastructure.database.access_control import (
            SqliteAccessControlRepository,
        )
        from natureai_next.infrastructure.database.science import SqliteScienceRepository
        from natureai_next.server.api import FieldoraApi, ScienceReadProjection
        from natureai_next.server.exports import GovernedExportStore
        from natureai_next.server.jobs import ServerJobStore
        from natureai_next.server.media import GovernedMediaStore
        from natureai_next.server.search import ServerSearchProjection

        data_root = data_root.resolve(strict=True)
        database_root = data_root / "subsystems"
        required = (
            "access-control.sqlite3",
            "science.sqlite3",
            "server-media.sqlite3",
            "server-jobs.sqlite3",
            "server-exports.sqlite3",
            "server-search.sqlite3",
        )
        missing = [name for name in required if not (database_root / name).is_file()]
        if missing:
            raise ValueError(
                "restored root is missing required databases: " + ", ".join(missing)
            )
        access = SqliteAccessControlRepository(database_root / required[0])
        SqliteScienceRepository(database_root / required[1], default_science_snapshot)
        media = GovernedMediaStore(
            database_root / required[2], data_root / "server-media"
        )
        jobs = ServerJobStore(database_root / required[3])
        exports = GovernedExportStore(
            database_root / required[4], data_root / "server-exports"
        )
        search = ServerSearchProjection(database_root / required[5])
        for name in required:
            with sqlite3.connect(
                f"file:{(database_root / name).as_posix()}?mode=ro", uri=True
            ) as connection:
                status = connection.execute("PRAGMA integrity_check").fetchone()
            if status is None or str(status[0]).casefold() != "ok":
                raise ValueError(f"restored database is corrupt: {name}")
        authentication = AuthenticationService(access)
        device_authorization = DeviceAuthorizationService(access, authentication)
        web_root = Path(__file__).parent.parent / "resources" / "server_web"
        application = FieldoraApi(
            authentication,
            PolicyDecisionService(access),
            ScienceReadProjection(database_root / required[1]),
            web_root,
            media,
            device_authorization,
            None,
            access,
            search,
            jobs,
            exports,
        )
        status_response = application.dispatch("GET", "/api/v1/status", {}, b"")
        status_payload = json.loads(status_response.body)
        if status_response.status != 200 or status_payload.get("version") != __version__:
            raise ValueError("restored server composition check failed")
        report = RestoredRootReport(
            data_root, __version__, required, str(status_payload["product"])
        )
        if report_path is not None:
            report_path = report_path.expanduser().resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = report_path.with_suffix(report_path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(report_path)
        return report

    @staticmethod
    def _entry(root: Path, path: Path, kind: str) -> dict[str, object]:
        return {
            "path": path.relative_to(root).as_posix(),
            "kind": kind,
            "size_bytes": path.stat().st_size,
            "sha256": _digest(path),
        }

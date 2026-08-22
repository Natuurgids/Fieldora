"""Missing-file, relinking, trash and analysis-aware permanent deletion services."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from natureai_next.ports.clock import Clock
from natureai_next.ports.identity import UuidGenerator
from natureai_next.ports.importing import FileFingerprinter, ManagedFileStore


def _now_us(clock: Clock) -> int:
    return int(clock.now_utc().timestamp() * 1_000_000)


def _path(path: Path) -> tuple[str, str]:
    value = str(path.expanduser().resolve())
    return value, os.path.normcase(value).casefold()


@dataclass(frozen=True)
class AssetRemovalPreview:
    asset_public_id: str
    lifecycle_state: str
    managed_files: tuple[str, ...]
    derivative_files: tuple[str, ...]
    analysis_count: int
    suggestion_count: int
    observation_count: int
    promotion_count: int
    running_job_count: int

    @property
    def has_authoritative_dependencies(self) -> bool:
        return self.observation_count > 0 or self.promotion_count > 0


@dataclass(frozen=True)
class AssetRemovalResult:
    asset_public_id: str
    deleted_files: int
    deleted_derivatives: int
    deleted_analyses: int
    deleted_suggestions: int
    deleted_observations: int
    cancelled_jobs: int


class CatalogMaintenanceService:
    def __init__(
        self,
        *,
        uow_factory,
        fingerprinter: FileFingerprinter,
        managed_store: ManagedFileStore,
        clock: Clock,
        ids: UuidGenerator,
        cache_roots: tuple[Path, ...] = (),
        read_connection_factory=None,
    ) -> None:
        self.uow_factory = uow_factory
        self.fingerprinter = fingerprinter
        self.managed_store = managed_store
        self.clock = clock
        self.ids = ids
        self.cache_roots = tuple(cache_roots)
        self.read_connection_factory = read_connection_factory

    def refresh_availability(self) -> int:
        changed = 0
        now = _now_us(self.clock)
        with self.uow_factory() as uow:
            assert uow.connection is not None
            c = uow.connection
            for row in c.execute(
                "SELECT id,normalized_path,availability_state FROM file_instances WHERE storage_mode IN ('managed','referenced')"
            ):
                target = "available" if Path(row["normalized_path"]).is_file() else "missing"
                if target != row["availability_state"]:
                    c.execute(
                        "UPDATE file_instances SET availability_state=?,modified_at_us=? WHERE id=?",
                        (target, now, row["id"]),
                    )
                    changed += 1
            uow.commit()
        return changed

    def relink(self, file_public_id: str, candidate: Path) -> None:
        fingerprint = self.fingerprinter.fingerprint(candidate)
        normalized, key = _path(candidate)
        now = _now_us(self.clock)
        with self.uow_factory() as uow:
            assert uow.connection is not None
            c = uow.connection
            row = c.execute(
                "SELECT sha256 FROM file_instances WHERE public_id=?", (file_public_id,)
            ).fetchone()
            if row is None:
                raise KeyError(file_public_id)
            if row["sha256"] and row["sha256"] != fingerprint.sha256:
                raise ValueError("relink candidate checksum does not match original")
            c.execute(
                "UPDATE file_instances SET normalized_path=?,path_key=?,file_size=?,modified_at_observed_us=?,sha256=?,fast_fingerprint=?,availability_state='available',verified_at_us=?,modified_at_us=? WHERE public_id=?",
                (
                    normalized,
                    key,
                    fingerprint.size,
                    candidate.stat().st_mtime_ns // 1000,
                    fingerprint.sha256,
                    fingerprint.fast_fingerprint,
                    now,
                    now,
                    file_public_id,
                ),
            )
            uow.commit()

    def trash(self, asset_public_id: str) -> bool:
        with self.uow_factory() as uow:
            assert uow.connection is not None
            cur = uow.connection.execute(
                "UPDATE assets SET lifecycle_state='trashed',modified_at_us=?,revision=revision+1 WHERE public_id=? AND lifecycle_state='active'",
                (_now_us(self.clock), asset_public_id),
            )
            uow.commit()
            return cur.rowcount == 1

    def restore(self, asset_public_id: str) -> bool:
        with self.uow_factory() as uow:
            assert uow.connection is not None
            cur = uow.connection.execute(
                "UPDATE assets SET lifecycle_state='active',modified_at_us=?,revision=revision+1 WHERE public_id=? AND lifecycle_state='trashed'",
                (_now_us(self.clock), asset_public_id),
            )
            uow.commit()
            return cur.rowcount == 1

    def removal_preview(self, asset_public_id: str) -> AssetRemovalPreview:
        # Dependency previews are read-only and must never take the process-wide
        # write lock.  This keeps Library actions responsive while AI/background
        # jobs are committing unrelated records.
        if self.read_connection_factory is not None:
            c = self.read_connection_factory()
            close = True
        else:
            uow = self.uow_factory().__enter__()
            c = uow.connection
            close = False
        try:
            assert c is not None
            asset = c.execute(
                "SELECT id,lifecycle_state FROM assets WHERE public_id=?", (asset_public_id,)
            ).fetchone()
            if asset is None:
                raise KeyError(asset_public_id)
            aid = int(asset["id"])
            managed = tuple(
                str(r[0])
                for r in c.execute(
                    "SELECT normalized_path FROM file_instances WHERE asset_id=? AND storage_mode='managed'",
                    (aid,),
                )
            )
            derivatives = tuple(
                str(r[0])
                for r in c.execute(
                    "SELECT relative_path FROM derivative_cache_entries WHERE asset_id=?", (aid,)
                )
            )

            def scalar(sql):
                return int(c.execute(sql, (aid,)).fetchone()[0])

            analyses = scalar("SELECT COUNT(*) FROM asset_analyses WHERE asset_id=?")
            suggestions = scalar("SELECT COUNT(*) FROM ai_suggestions WHERE asset_id=?")
            observations = scalar(
                "SELECT COUNT(DISTINCT observation_id) FROM observation_assets WHERE asset_id=?"
            )
            promotions = scalar(
                "SELECT COUNT(*) FROM analysis_observation_promotions p JOIN asset_analyses a ON a.id=p.analysis_id WHERE a.asset_id=?"
            )
            jobs = int(
                c.execute(
                    "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running','retry_wait','paused') AND json_extract(payload_json,'$.asset_public_id')=?",
                    (asset_public_id,),
                ).fetchone()[0]
            )
            return AssetRemovalPreview(
                asset_public_id,
                str(asset["lifecycle_state"]),
                managed,
                derivatives,
                analyses,
                suggestions,
                observations,
                promotions,
                jobs,
            )
        finally:
            if close:
                c.close()
            else:
                uow.__exit__(None, None, None)

    def _cache_path(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute() or not self.cache_roots:
            return path
        for root in self.cache_roots:
            candidate = root / path
            if candidate.exists():
                return candidate
        return self.cache_roots[0] / path

    def permanently_delete(
        self,
        asset_public_id: str,
        *,
        observation_policy: Literal["block", "unlink", "delete"] = "block",
    ) -> AssetRemovalResult:
        preview = self.removal_preview(asset_public_id)
        if preview.lifecycle_state == "active":
            # Permanent delete is one user operation.  Trash is an internal
            # lifecycle transition and is applied atomically before purge.
            self.trash(asset_public_id)
            preview = self.removal_preview(asset_public_id)
        if preview.lifecycle_state != "trashed":
            raise ValueError("asset is not eligible for permanent deletion")
        if observation_policy == "block" and preview.has_authoritative_dependencies:
            raise ValueError(
                "asset supports authoritative observations; choose unlink or delete explicitly"
            )
        now = _now_us(self.clock)
        with self.uow_factory() as uow:
            assert uow.connection is not None
            c = uow.connection
            asset = c.execute(
                "SELECT id FROM assets WHERE public_id=? AND lifecycle_state='trashed'",
                (asset_public_id,),
            ).fetchone()
            if asset is None:
                return AssetRemovalResult(asset_public_id, 0, 0, 0, 0, 0, 0)
            aid = int(asset["id"])
            observation_ids = [
                int(r[0])
                for r in c.execute(
                    "SELECT observation_id FROM observation_assets WHERE asset_id=?", (aid,)
                )
            ]
            if observation_policy == "unlink":
                c.execute(
                    "DELETE FROM analysis_observation_promotions WHERE analysis_id IN (SELECT id FROM asset_analyses WHERE asset_id=?)",
                    (aid,),
                )
                c.execute("DELETE FROM observation_assets WHERE asset_id=?", (aid,))
            elif observation_policy == "delete":
                c.execute(
                    "DELETE FROM analysis_observation_promotions WHERE analysis_id IN (SELECT id FROM asset_analyses WHERE asset_id=?) OR observation_id IN (SELECT observation_id FROM observation_assets WHERE asset_id=?)",
                    (aid, aid),
                )
                for oid in observation_ids:
                    c.execute("DELETE FROM observations WHERE id=?", (oid,))
            cancelled = c.execute(
                "UPDATE jobs SET cancellation_requested=1,modified_at_us=? WHERE state IN ('queued','running','retry_wait','paused') AND json_extract(payload_json,'$.asset_public_id')=?",
                (now, asset_public_id),
            ).rowcount
            intent = str(self.ids.new_uuid())
            c.execute(
                "INSERT INTO purge_intents(public_id,asset_id,managed_paths_json,state,created_at_us,modified_at_us) VALUES(?,?,?,'pending',?,?)",
                (
                    intent,
                    aid,
                    json.dumps(list(preview.managed_files) + list(preview.derivative_files)),
                    now,
                    now,
                ),
            )
            uow.commit()
        try:
            for value in preview.managed_files:
                self.managed_store.purge(Path(value))
            for value in preview.derivative_files:
                self.managed_store.purge(self._cache_path(value))
            with self.uow_factory() as uow:
                assert uow.connection is not None
                c = uow.connection
                c.execute(
                    "UPDATE purge_intents SET state='files_deleted',modified_at_us=? WHERE public_id=?",
                    (_now_us(self.clock), intent),
                )
                # The audit intent intentionally retains no FK after deletion.
                c.execute("UPDATE purge_intents SET asset_id=NULL WHERE public_id=?", (intent,))
                self._detach_restricting_asset_references(c, aid)
                c.execute("DELETE FROM assets WHERE id=?", (aid,))
                c.execute(
                    "UPDATE purge_intents SET state='completed',modified_at_us=? WHERE public_id=?",
                    (_now_us(self.clock), intent),
                )
                uow.commit()
            return AssetRemovalResult(
                asset_public_id,
                len(preview.managed_files),
                len(preview.derivative_files),
                preview.analysis_count,
                preview.suggestion_count,
                len(observation_ids) if observation_policy == "delete" else 0,
                int(cancelled),
            )
        except Exception as exc:
            with self.uow_factory() as uow:
                assert uow.connection is not None
                uow.connection.execute(
                    "UPDATE purge_intents SET state='failed',error_text=?,modified_at_us=? WHERE public_id=?",
                    (str(exc), _now_us(self.clock), intent),
                )
                uow.commit()
            raise


    @staticmethod
    def _detach_restricting_asset_references(connection, asset_id: int) -> None:
        """Resolve direct NO ACTION/RESTRICT references before deleting an asset.

        Most catalog-owned records cascade.  Historical import rows and newer
        enrichment/relationship tables intentionally use restrictive foreign keys.
        Nullable references are detached to preserve history; required dependent
        rows are removed as part of the same permanent-delete transaction.
        """
        tables = [str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        for table in tables:
            if table == "assets":
                continue
            columns = {str(row[1]): bool(row[3]) for row in connection.execute(f'PRAGMA table_info("{table}")')}
            for fk in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
                target = str(fk[2])
                column = str(fk[3])
                action = str(fk[6]).upper()
                if target != "assets" or action not in {"NO ACTION", "RESTRICT"}:
                    continue
                if table == "purge_intents":
                    continue
                quoted_table = table.replace('"', '""')
                quoted_column = column.replace('"', '""')
                if columns.get(column, False):
                    connection.execute(
                        f'DELETE FROM "{quoted_table}" WHERE "{quoted_column}"=?',
                        (asset_id,),
                    )
                else:
                    connection.execute(
                        f'UPDATE "{quoted_table}" SET "{quoted_column}"=NULL WHERE "{quoted_column}"=?',
                        (asset_id,),
                    )

    def purge(self, asset_public_id: str) -> bool:
        """Legacy recoverable purge: delete managed files and retain the purged catalog row."""
        now = _now_us(self.clock)
        with self.uow_factory() as uow:
            assert uow.connection is not None
            c = uow.connection
            asset = c.execute(
                "SELECT id FROM assets WHERE public_id=? AND lifecycle_state='trashed'",
                (asset_public_id,),
            ).fetchone()
            if asset is None:
                return False
            paths = [
                r[0]
                for r in c.execute(
                    "SELECT normalized_path FROM file_instances WHERE asset_id=? AND storage_mode='managed'",
                    (asset["id"],),
                )
            ]
            intent = str(self.ids.new_uuid())
            c.execute(
                "INSERT INTO purge_intents(public_id,asset_id,managed_paths_json,state,created_at_us,modified_at_us) VALUES(?,?,?,'pending',?,?)",
                (intent, asset["id"], json.dumps(paths), now, now),
            )
            uow.commit()
        try:
            for value in paths:
                self.managed_store.purge(Path(value))
            with self.uow_factory() as uow:
                assert uow.connection is not None
                c = uow.connection
                c.execute(
                    "UPDATE purge_intents SET state='files_deleted',modified_at_us=? WHERE public_id=?",
                    (_now_us(self.clock), intent),
                )
                c.execute(
                    "UPDATE assets SET lifecycle_state='purged',modified_at_us=?,revision=revision+1 WHERE id=?",
                    (_now_us(self.clock), asset["id"]),
                )
                c.execute(
                    "UPDATE purge_intents SET state='completed',modified_at_us=? WHERE public_id=?",
                    (_now_us(self.clock), intent),
                )
                uow.commit()
            return True
        except Exception as exc:
            with self.uow_factory() as uow:
                assert uow.connection is not None
                uow.connection.execute(
                    "UPDATE purge_intents SET state='failed',error_text=?,modified_at_us=? WHERE public_id=?",
                    (str(exc), _now_us(self.clock), intent),
                )
                uow.commit()
            raise

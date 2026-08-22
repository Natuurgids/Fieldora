"""Bounded cleanup for durable workflow history and temporary artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from natureai_next.domain.workflows import RetentionPolicy
from natureai_next.ports.retention import RetentionHistoryStore

_DAY_US = 86_400_000_000


@dataclass(frozen=True, slots=True)
class CleanupReport:
    jobs_removed: int = 0
    events_removed: int = 0
    temporary_files_removed: int = 0
    temporary_bytes_removed: int = 0
    empty_directories_removed: int = 0


@dataclass(frozen=True, slots=True)
class CleanupPreview:
    jobs_eligible: int = 0
    events_eligible: int = 0
    temporary_files_eligible: int = 0
    temporary_bytes_eligible: int = 0
    orphan_temporary_files: tuple[Path, ...] = ()


class WorkflowCleanupService:
    def __init__(
        self, history: RetentionHistoryStore, temporary_roots: tuple[Path, ...] = ()
    ) -> None:
        self.history = history
        self.temporary_roots = temporary_roots

    def preview(self, *, now_us: int, policy: RetentionPolicy) -> CleanupPreview:
        job_ids, event_ids = self.history.eligible_ids(now_us=now_us, policy=policy)
        file_paths, byte_count = self._eligible_files(now_us, policy)
        return CleanupPreview(len(job_ids), len(event_ids), len(file_paths), byte_count, file_paths)

    def cleanup(
        self, *, now_us: int, policy: RetentionPolicy, dry_run: bool = False
    ) -> CleanupReport:
        job_ids, event_ids = self.history.eligible_ids(now_us=now_us, policy=policy)
        if not dry_run:
            self.history.delete(job_ids=job_ids, event_ids=event_ids)

        file_count, byte_count, directories = self._cleanup_files(now_us, policy, dry_run)
        return CleanupReport(len(job_ids), len(event_ids), file_count, byte_count, directories)

    def _eligible_files(self, now_us: int, policy: RetentionPolicy) -> tuple[tuple[Path, ...], int]:
        threshold_seconds = (now_us - policy.temporary_file_days * _DAY_US) / 1_000_000
        paths: list[Path] = []
        total = 0
        for root in self.temporary_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                if stat.st_mtime >= threshold_seconds:
                    continue
                paths.append(path)
                total += stat.st_size
        return tuple(paths), total

    def _cleanup_files(
        self, now_us: int, policy: RetentionPolicy, dry_run: bool
    ) -> tuple[int, int, int]:
        paths, total = self._eligible_files(now_us, policy)
        if dry_run:
            return len(paths), total, 0
        removed = bytes_removed = 0
        touched_roots: set[Path] = set()
        for path in paths:
            try:
                size = path.stat().st_size
                path.unlink()
            except OSError:
                continue
            removed += 1
            bytes_removed += size
            touched_roots.add(path.parent)
        directories_removed = 0
        for root in self.temporary_roots:
            if not root.exists():
                continue
            directories = sorted(
                (p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True
            )
            for directory in directories:
                try:
                    directory.rmdir()
                except OSError:
                    continue
                directories_removed += 1
        return removed, bytes_removed, directories_removed


# ---------------------------------------------------------------------------
# Aperture V4 canonical-enrichment slimming
# ---------------------------------------------------------------------------

import json
from enum import StrEnum
from typing import Any

from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class RetentionProfileName(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    RESEARCH = "research"


@dataclass(frozen=True, slots=True)
class EnrichmentRetentionPolicy:
    """Deliberate policies for slimming observer-owned enrichment.

    Accepted records are never deleted implicitly.  A policy capable of deleting
    accepted categories must set ``delete_unselected_accepted`` explicitly.
    """

    profile: RetentionProfileName
    keep_accepted_shapes: frozenset[str] | None = None
    delete_unselected_accepted: bool = False
    delete_pending: bool = False
    delete_rejected: bool = True
    delete_expired: bool = True
    remove_diagnostics: bool = True
    remove_probability_vectors: bool = True
    remove_temporary_artifact_references: bool = True
    remove_media_cache_references: bool = True
    remove_ocr_intermediates: bool = True
    remove_source_package_references: bool = False

    @classmethod
    def named(cls, profile: RetentionProfileName | str) -> EnrichmentRetentionPolicy:
        name = RetentionProfileName(profile)
        if name is RetentionProfileName.MINIMAL:
            return cls(
                profile=name,
                keep_accepted_shapes=frozenset({"taxonomy_candidate", "label", "relationship"}),
                delete_unselected_accepted=False,
                delete_pending=True,
                delete_rejected=True,
                delete_expired=True,
                remove_diagnostics=True,
                remove_probability_vectors=True,
                remove_temporary_artifact_references=True,
                remove_media_cache_references=True,
                remove_ocr_intermediates=True,
                remove_source_package_references=True,
            )
        if name is RetentionProfileName.RESEARCH:
            return cls(
                profile=name,
                delete_pending=False,
                delete_rejected=False,
                delete_expired=False,
                remove_diagnostics=False,
                remove_probability_vectors=False,
                remove_temporary_artifact_references=False,
                remove_media_cache_references=False,
                remove_ocr_intermediates=False,
                remove_source_package_references=False,
            )
        return cls(profile=name)


@dataclass(frozen=True, slots=True)
class EnrichmentSlimmingReport:
    records_deleted: int = 0
    accepted_records_deleted: int = 0
    accepted_records_preserved: int = 0
    evidence_documents_slimmed: int = 0
    payload_documents_slimmed: int = 0
    probability_vectors_removed: int = 0
    diagnostics_removed: int = 0
    temporary_artifacts_removed: int = 0
    media_cache_references_removed: int = 0
    ocr_intermediates_removed: int = 0
    source_package_references_removed: int = 0
    reproducibility_impacted_records: int = 0

    @property
    def artifact_references_removed(self) -> int:
        return (
            self.temporary_artifacts_removed
            + self.media_cache_references_removed
            + self.ocr_intermediates_removed
            + self.source_package_references_removed
        )


class EnrichmentSlimmingService:
    """Slim canonical enrichment without touching observations or media rows."""

    _VECTOR_KEYS = frozenset(
        {
            "probabilities",
            "probability_vector",
            "raw_probabilities",
            "logits",
            "embedding",
            "embeddings",
        }
    )
    _DIAGNOSTIC_KEYS = frozenset({"diagnostics", "debug", "trace", "raw_output", "ocr_diagnostics"})
    _TEMPORARY_KEYS = frozenset({"temporary_artifact", "temporary_artifacts", "temporary_path"})
    _MEDIA_CACHE_KEYS = frozenset(
        {
            "cache_path",
            "cache_paths",
            "thumbnail_path",
            "waveform_path",
            "spectrogram_path",
            "extracted_frame",
            "extracted_frames",
            "frame_cache",
            "render_cache",
        }
    )
    _OCR_INTERMEDIATE_KEYS = frozenset(
        {
            "ocr_intermediate",
            "ocr_intermediates",
            "ocr_image",
            "binarized_image",
            "deskewed_image",
            "layout_debug_image",
        }
    )
    _SOURCE_PACKAGE_KEYS = frozenset(
        {
            "source_package",
            "source_package_path",
            "downloaded_package",
            "map_package_path",
            "index_path",
            "source_index_path",
        }
    )

    def __init__(self, database_path: Path) -> None:
        self._factory = SqliteConnectionFactory(database_path)

    def preview(self, policy: EnrichmentRetentionPolicy) -> EnrichmentSlimmingReport:
        return self._apply(policy, dry_run=True)

    def apply(self, policy: EnrichmentRetentionPolicy) -> EnrichmentSlimmingReport:
        return self._apply(policy, dry_run=False)

    def _apply(
        self, policy: EnrichmentRetentionPolicy, *, dry_run: bool
    ) -> EnrichmentSlimmingReport:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                "SELECT enrichment_id,enrichment_type,status,payload_json,evidence_json "
                "FROM enrichment_records ORDER BY enrichment_id"
            ).fetchall()
            delete_ids: list[str] = []
            accepted_deleted = accepted_preserved = payload_slimmed = evidence_slimmed = 0
            category_totals = {
                "probability": 0,
                "diagnostic": 0,
                "temporary": 0,
                "cache": 0,
                "ocr": 0,
                "source_package": 0,
            }
            reproducibility_impacted: set[str] = set()
            updates: list[tuple[str, str | None, str]] = []
            for row in rows:
                enrichment_id = str(row[0])
                shape = str(row[1])
                status = str(row[2])
                delete = (
                    (status == "pending_review" and policy.delete_pending)
                    or (status == "rejected" and policy.delete_rejected)
                    or (status == "expired" and policy.delete_expired)
                )
                if (
                    status == "accepted"
                    and policy.delete_unselected_accepted
                    and policy.keep_accepted_shapes is not None
                    and shape not in policy.keep_accepted_shapes
                ):
                    delete = True
                    accepted_deleted += 1
                elif status == "accepted":
                    accepted_preserved += 1
                if delete:
                    delete_ids.append(enrichment_id)
                    continue

                payload = json.loads(str(row[3]) or "{}")
                evidence = None if row[4] is None else json.loads(str(row[4]))
                new_payload, payload_counts = self._slim_document(payload, policy)
                new_evidence, evidence_counts = self._slim_document(evidence, policy)
                payload_removed = sum(payload_counts.values())
                evidence_removed = sum(evidence_counts.values())
                if payload_removed:
                    payload_slimmed += 1
                if evidence_removed:
                    evidence_slimmed += 1
                for key in category_totals:
                    category_totals[key] += payload_counts[key] + evidence_counts[key]
                if any(
                    (payload_counts[k] + evidence_counts[k])
                    for k in ("probability", "temporary", "cache", "ocr", "source_package")
                ):
                    reproducibility_impacted.add(enrichment_id)
                if payload_removed or evidence_removed:
                    updates.append(
                        (
                            json.dumps(new_payload, separators=(",", ":")),
                            None
                            if new_evidence is None
                            else json.dumps(new_evidence, separators=(",", ":")),
                            enrichment_id,
                        )
                    )
            if not dry_run:
                connection.executemany(
                    "UPDATE enrichment_records SET payload_json=?,evidence_json=? WHERE enrichment_id=?",
                    updates,
                )
                connection.executemany(
                    "DELETE FROM enrichment_records WHERE enrichment_id=?",
                    [(item,) for item in delete_ids],
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS enrichment_retention_audit("
                    "audit_id INTEGER PRIMARY KEY AUTOINCREMENT,profile TEXT NOT NULL,"
                    "applied_at_us INTEGER NOT NULL,report_json TEXT NOT NULL CHECK(json_valid(report_json)))"
                )
                report = self._report(
                    len(delete_ids),
                    accepted_deleted,
                    accepted_preserved,
                    evidence_slimmed,
                    payload_slimmed,
                    category_totals,
                    len(reproducibility_impacted),
                )
                import time

                connection.execute(
                    "INSERT INTO enrichment_retention_audit(profile,applied_at_us,report_json) VALUES(?,?,?)",
                    (
                        policy.profile.value,
                        time.time_ns() // 1000,
                        json.dumps(
                            report.__dict__
                            if hasattr(report, "__dict__")
                            else {
                                name: getattr(report, name) for name in report.__dataclass_fields__
                            },
                            separators=(",", ":"),
                        ),
                    ),
                )
                connection.execute("COMMIT")
                return report
            connection.execute("ROLLBACK")
            return self._report(
                len(delete_ids),
                accepted_deleted,
                accepted_preserved,
                evidence_slimmed,
                payload_slimmed,
                category_totals,
                len(reproducibility_impacted),
            )
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    @staticmethod
    def _report(
        records_deleted: int,
        accepted_deleted: int,
        accepted_preserved: int,
        evidence_slimmed: int,
        payload_slimmed: int,
        counts: dict[str, int],
        impacted: int,
    ) -> EnrichmentSlimmingReport:
        return EnrichmentSlimmingReport(
            records_deleted=records_deleted,
            accepted_records_deleted=accepted_deleted,
            accepted_records_preserved=accepted_preserved,
            evidence_documents_slimmed=evidence_slimmed,
            payload_documents_slimmed=payload_slimmed,
            probability_vectors_removed=counts["probability"],
            diagnostics_removed=counts["diagnostic"],
            temporary_artifacts_removed=counts["temporary"],
            media_cache_references_removed=counts["cache"],
            ocr_intermediates_removed=counts["ocr"],
            source_package_references_removed=counts["source_package"],
            reproducibility_impacted_records=impacted,
        )

    def _slim_document(
        self, document: Any, policy: EnrichmentRetentionPolicy
    ) -> tuple[Any, dict[str, int]]:
        counts = {
            "probability": 0,
            "diagnostic": 0,
            "temporary": 0,
            "cache": 0,
            "ocr": 0,
            "source_package": 0,
        }
        if isinstance(document, dict):
            result: dict[str, Any] = {}
            for key, value in document.items():
                normalized = str(key).casefold()
                category = None
                if policy.remove_probability_vectors and normalized in self._VECTOR_KEYS:
                    category = "probability"
                elif policy.remove_diagnostics and normalized in self._DIAGNOSTIC_KEYS:
                    category = "diagnostic"
                elif (
                    policy.remove_temporary_artifact_references
                    and normalized in self._TEMPORARY_KEYS
                ):
                    category = "temporary"
                elif policy.remove_media_cache_references and normalized in self._MEDIA_CACHE_KEYS:
                    category = "cache"
                elif policy.remove_ocr_intermediates and normalized in self._OCR_INTERMEDIATE_KEYS:
                    category = "ocr"
                elif (
                    policy.remove_source_package_references
                    and normalized in self._SOURCE_PACKAGE_KEYS
                ):
                    category = "source_package"
                if category is not None:
                    counts[category] += 1
                    continue
                slimmed, nested = self._slim_document(value, policy)
                for name, amount in nested.items():
                    counts[name] += amount
                result[key] = slimmed
            return result, counts
        if isinstance(document, list):
            values = []
            for item in document:
                slimmed, nested = self._slim_document(item, policy)
                for name, amount in nested.items():
                    counts[name] += amount
                values.append(slimmed)
            return values, counts
        return document, counts

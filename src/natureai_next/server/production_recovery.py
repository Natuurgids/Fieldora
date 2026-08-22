"""Fail-closed validation of production backup, PITR, and DR contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class RecoveryIssue:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class RecoveryAssessment:
    recovery_ready: bool
    issues: tuple[RecoveryIssue, ...]
    rpo_seconds: int
    rto_seconds: int

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fieldora.production-recovery-assessment",
            "format_version": 1,
            "recovery_ready": self.recovery_ready,
            "rpo_seconds": self.rpo_seconds,
            "rto_seconds": self.rto_seconds,
            "issues": [issue.as_dict() for issue in self.issues],
        }


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def assess_recovery_plan(document: dict[str, Any]) -> RecoveryAssessment:
    issues: list[RecoveryIssue] = []

    def require(condition: bool, code: str, message: str) -> None:
        if not condition:
            issues.append(RecoveryIssue(code, message))

    require(
        document.get("format") == "fieldora.production-recovery"
        and document.get("format_version") == 1,
        "recovery.format",
        "Use fieldora.production-recovery format version 1.",
    )
    require(
        bool(str(document.get("environment_id", "")).strip()),
        "recovery.environment",
        "A stable environment identifier is required.",
    )
    objectives = _mapping(document.get("objectives"))
    rpo = _integer(objectives.get("rpo_seconds"))
    rto = _integer(objectives.get("rto_seconds"))
    require(0 < rpo <= 300, "objectives.rpo", "RPO must be between 1 and 300 seconds.")
    require(0 < rto <= 3600, "objectives.rto", "RTO must be between 1 and 3600 seconds.")

    database = _mapping(document.get("postgresql"))
    require(database.get("base_backups") is True, "postgres.backups", "Verified base backups are required.")
    require(database.get("continuous_wal_archive") is True, "postgres.wal", "Continuous WAL archiving is required.")
    require(database.get("encrypted") is True, "postgres.encryption", "Database backups must be encrypted.")
    require(database.get("immutable") is True, "postgres.immutable", "Database backups must be immutable.")
    require(_integer(database.get("retention_days")) >= 7, "postgres.retention", "Retain at least seven days of recovery points.")
    require(database.get("restore_to_new_target") is True, "postgres.restore_target", "Drills must restore to a new target.")
    require(database.get("integrity_verification") is True, "postgres.verify", "Restored databases require integrity verification.")

    objects = _mapping(document.get("object_storage"))
    require(objects.get("versioning") is True, "objects.versioning", "Object versioning is required.")
    require(objects.get("cross_zone_replication") is True, "objects.replication", "Cross-zone object replication is required.")
    require(objects.get("inventory_digest") is True, "objects.inventory", "A checksummed object inventory is required.")
    require(objects.get("legal_holds_preserved") is True, "objects.legal_holds", "Recovery must preserve legal holds.")
    require(objects.get("delete_markers_preserved") is True, "objects.deletes", "Recovery must preserve deletion state.")

    search = _mapping(document.get("search"))
    require(search.get("rebuild_from_authority") is True, "search.authority", "Search must rebuild from authoritative repositories.")
    require(search.get("atomic_alias_switch") is True, "search.alias", "Projection recovery requires an atomic alias switch.")

    keys = _mapping(document.get("key_custody"))
    require(
        keys.get("provider") in {"vault", "cloud-kms", "external-secrets"},
        "keys.provider",
        "Recovery keys require an external custody provider.",
    )
    require(keys.get("separate_from_backups") is True, "keys.separation", "Recovery keys must be stored separately.")
    require(keys.get("rotation_tested") is True, "keys.rotation", "Restores must test rotated key versions.")

    drills = _mapping(document.get("drills"))
    require(_integer(drills.get("maximum_interval_days")) <= 90 and _integer(drills.get("maximum_interval_days")) > 0, "drills.interval", "Run restore drills at least every 90 days.")
    require(drills.get("authorization_probe") is True, "drills.authorization", "Restores require authorization-denial probes.")
    require(drills.get("audit_chain_verification") is True, "drills.audit", "Restores require audit-chain verification.")
    require(drills.get("source_untouched") is True, "drills.non_destructive", "Drills must not overwrite the source environment.")
    return RecoveryAssessment(not issues, tuple(issues), rpo, rto)


def assess_recovery_file(source: Path, report: Path | None = None) -> RecoveryAssessment:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("recovery plan must be a JSON object")
    assessment = assess_recovery_plan(payload)
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        temporary = report.with_suffix(report.suffix + ".tmp")
        temporary.write_text(
            json.dumps(assessment.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(report)
    return assessment

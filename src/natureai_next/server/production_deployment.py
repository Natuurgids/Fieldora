"""Fail-closed assessment of declarative Fieldora production deployments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DeploymentIssue:
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class DeploymentAssessment:
    configuration_ready: bool
    certification_status: str
    issues: tuple[DeploymentIssue, ...]
    pending_exercises: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "fieldora.phase-f-deployment-assessment",
            "format_version": 1,
            "configuration_ready": self.configuration_ready,
            "certification_status": self.certification_status,
            "issues": [issue.as_dict() for issue in self.issues],
            "pending_exercises": list(self.pending_exercises),
        }


_PENDING_EXERCISES = (
    "api-node-loss",
    "worker-node-loss",
    "postgres-primary-failover",
    "object-storage-replica-loss",
    "search-node-loss",
    "ingress-certificate-rotation",
    "rolling-upgrade-and-rollback",
    "point-in-time-recovery",
    "zone-failure",
)


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _integer(value: object) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def assess_production_deployment(document: dict[str, Any]) -> DeploymentAssessment:
    """Validate the minimum safe Phase F production topology."""
    issues: list[DeploymentIssue] = []

    def require(condition: bool, code: str, message: str) -> None:
        if not condition:
            issues.append(DeploymentIssue(code, message))

    require(
        document.get("format") == "fieldora.production-deployment"
        and document.get("format_version") == 1,
        "deployment.format",
        "Use fieldora.production-deployment format version 1.",
    )
    require(
        document.get("mode") == "multi-server",
        "deployment.mode",
        "Production mode must be multi-server.",
    )

    api = _mapping(document.get("api"))
    require(_integer(api.get("replicas")) >= 2, "api.replicas", "At least two API replicas are required.")
    require(_integer(api.get("zones")) >= 2, "api.zones", "API replicas must span at least two zones.")
    require(api.get("readiness_probe") is True, "api.readiness", "API readiness probes are required.")
    require(api.get("pod_disruption_budget") is True, "api.pdb", "API disruption protection is required.")

    workers = _mapping(document.get("workers"))
    require(
        _integer(workers.get("replicas")) >= 2,
        "workers.replicas",
        "At least two independently fenced workers are required.",
    )
    require(_integer(workers.get("zones")) >= 2, "workers.zones", "Workers must span at least two zones.")
    require(
        workers.get("fenced_leases") is True,
        "workers.fencing",
        "Workers must use renewable fenced leases.",
    )

    database = _mapping(document.get("database"))
    require(database.get("backend") == "postgresql", "database.backend", "PostgreSQL is required.")
    require(database.get("tls") is True, "database.tls", "Database transport must use TLS.")
    require(database.get("automatic_failover") is True, "database.failover", "Automatic database failover is required.")
    require(database.get("point_in_time_recovery") is True, "database.pitr", "Point-in-time recovery is required.")
    require(_integer(database.get("synchronous_replicas")) >= 1, "database.replication", "At least one synchronous replica is required.")

    objects = _mapping(document.get("object_storage"))
    require(objects.get("backend") == "s3", "objects.backend", "S3-compatible object storage is required.")
    require(objects.get("tls") is True, "objects.tls", "Object storage transport must use TLS.")
    require(objects.get("versioning") is True, "objects.versioning", "Object versioning is required.")
    require(objects.get("encryption_at_rest") is True, "objects.encryption", "Object encryption at rest is required.")
    require(_integer(objects.get("replicas")) >= 2, "objects.replication", "At least two object replicas are required.")

    search = _mapping(document.get("search"))
    require(search.get("backend") == "opensearch", "search.backend", "OpenSearch is required.")
    require(search.get("tls") is True, "search.tls", "Search transport must use TLS.")
    require(_integer(search.get("nodes")) >= 3, "search.nodes", "At least three search nodes are required.")
    require(search.get("zone_awareness") is True, "search.zones", "Search zone awareness is required.")

    ingress = _mapping(document.get("ingress"))
    require(ingress.get("tls") is True, "ingress.tls", "TLS ingress is required.")
    require(ingress.get("minimum_tls") in ("1.2", "1.3"), "ingress.minimum_tls", "Ingress must require TLS 1.2 or newer.")
    require(ingress.get("hsts") is True, "ingress.hsts", "Ingress must publish HSTS.")

    secrets = _mapping(document.get("secrets"))
    require(
        secrets.get("provider") in {"external-secrets", "vault", "cloud-kms"},
        "secrets.provider",
        "Use an external secret provider; inline production secrets are forbidden.",
    )
    rotation_days = _integer(secrets.get("rotation_days"))
    require(0 < rotation_days <= 90, "secrets.rotation", "Secret rotation must be configured for 90 days or less.")

    upgrades = _mapping(document.get("upgrades"))
    require(upgrades.get("strategy") == "rolling", "upgrades.strategy", "Rolling upgrades are required.")
    require(_integer(upgrades.get("max_unavailable")) == 0, "upgrades.availability", "API rolling upgrades must keep all current capacity available.")
    require(upgrades.get("automatic_rollback") is True, "upgrades.rollback", "Automatic rollback is required.")

    evidence = _mapping(document.get("certification_evidence"))
    completed = {
        str(item) for item in evidence.get("completed_exercises", [])
        if isinstance(item, str)
    }
    pending = tuple(item for item in _PENDING_EXERCISES if item not in completed)
    return DeploymentAssessment(
        configuration_ready=not issues,
        certification_status="passed" if not issues and not pending else "conditional",
        issues=tuple(issues),
        pending_exercises=pending,
    )


def assess_file(source: Path, report_path: Path | None = None) -> DeploymentAssessment:
    document = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("deployment document must be a JSON object")
    assessment = assess_production_deployment(document)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = report_path.with_suffix(report_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(assessment.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(report_path)
    return assessment

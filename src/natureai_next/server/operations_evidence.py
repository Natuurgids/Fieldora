"""Verifiable records for Phase F failure, recovery, and upgrade exercises."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PHASE_F_EXERCISES = (
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


@dataclass(frozen=True, slots=True)
class ExerciseEvidence:
    exercise: str
    environment_id: str
    executed_at_utc: str
    result: str
    objective: str
    observed: str
    artifact_file: str
    artifact_sha256: str
    operator: str


@dataclass(frozen=True, slots=True)
class ExerciseDefinition:
    exercise: str
    objective: str
    required_observations: tuple[str, ...]
    artifact_guidance: str


PHASE_F_EXERCISE_DEFINITIONS = (
    ExerciseDefinition(
        "api-node-loss",
        "Prove client traffic continues while one API replica is unavailable.",
        ("No unauthorized disclosure", "Readiness removes the failed replica", "Requests recover within the service objective"),
        "Ingress, readiness, request-success, and authorization-denial logs.",
    ),
    ExerciseDefinition(
        "worker-node-loss",
        "Prove fenced work resumes without stale-worker completion.",
        ("Lease expires or transfers", "Fence token advances", "Exactly one durable completion"),
        "Worker lease, token, retry, and completion records.",
    ),
    ExerciseDefinition(
        "postgres-primary-failover",
        "Prove authoritative repositories recover through primary failover.",
        ("New primary is writable", "Committed records remain", "Applications regain readiness"),
        "Provider failover timeline, database checks, and readiness logs.",
    ),
    ExerciseDefinition(
        "object-storage-replica-loss",
        "Prove governed objects remain available after replica loss.",
        ("Checksums match", "Range reads succeed", "Revocation remains enforced"),
        "Provider event, object checksums, read probes, and revocation probe.",
    ),
    ExerciseDefinition(
        "search-node-loss",
        "Prove search projection remains bounded and authorization-filtered.",
        ("Alias remains usable", "Queries recover", "PBAC denial remains effective"),
        "Cluster health, query probes, and authorization-denial results.",
    ),
    ExerciseDefinition(
        "ingress-certificate-rotation",
        "Prove trusted TLS service continues through certificate rotation.",
        ("New chain is served", "Trust validation succeeds", "No plaintext fallback"),
        "Certificate fingerprints, trust probes, and ingress rollout timeline.",
    ),
    ExerciseDefinition(
        "rolling-upgrade-and-rollback",
        "Prove a version rollout and rollback preserve service and data contracts.",
        ("No unavailable API capacity", "Workers drain cleanly", "Rollback restores the prior release"),
        "Rollout status, probes, schema checks, and rollback status.",
    ),
    ExerciseDefinition(
        "point-in-time-recovery",
        "Prove recovery to a new target satisfies declared RPO and RTO.",
        ("Target time is reached", "Integrity checks pass", "Measured RPO and RTO meet limits"),
        "Backup/WAL records, restore timeline, integrity output, and measured objectives.",
    ),
    ExerciseDefinition(
        "zone-failure",
        "Prove the platform continues safely after loss of one deployment zone.",
        ("Surviving replicas serve traffic", "Authoritative data remains consistent", "Recovery avoids cross-tenant disclosure"),
        "Provider zone event, topology status, consistency checks, and security probes.",
    ),
)


def write_certification_plan(
    destination: Path,
    *,
    environment_id: str,
    release: str,
) -> Path:
    if destination.exists():
        raise FileExistsError(destination)
    if not environment_id.strip() or not release.strip():
        raise ValueError("environment and release are required")
    payload = {
        "format": "fieldora.phase-f-certification-plan",
        "format_version": 1,
        "environment_id": environment_id,
        "release": release,
        "certification_rule": (
            "Every exercise must have verified passing evidence from this environment."
        ),
        "exercises": [
            {
                "exercise": definition.exercise,
                "objective": definition.objective,
                "required_observations": list(definition.required_observations),
                "artifact_guidance": definition.artifact_guidance,
            }
            for definition in PHASE_F_EXERCISE_DEFINITIONS
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def certification_status(root: Path, environment_id: str) -> dict[str, object]:
    evidence = load_exercise_evidence(root)
    matching = tuple(
        item for item in evidence if item.environment_id == environment_id
    )
    foreign = sorted(
        {
            item.environment_id
            for item in evidence
            if item.environment_id != environment_id
        }
    )
    passed = sorted(item.exercise for item in matching if item.result == "passed")
    failed = sorted(item.exercise for item in matching if item.result == "failed")
    pending = sorted(set(PHASE_F_EXERCISES) - set(passed))
    certified = not pending and not failed and not foreign
    return {
        "format": "fieldora.phase-f-certification-status",
        "format_version": 1,
        "environment_id": environment_id,
        "certification_status": "passed" if certified else "conditional",
        "passed_exercises": passed,
        "failed_exercises": failed,
        "pending_exercises": pending,
        "foreign_evidence_environments": foreign,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_exercise_evidence(root: Path) -> tuple[ExerciseEvidence, ...]:
    if not root.exists():
        return ()
    records = []
    exercises: set[str] = set()
    for path in sorted(root.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("format") != "fieldora.phase-f-exercise-evidence":
            raise ValueError(f"unsupported evidence file: {path.name}")
        evidence = ExerciseEvidence(
            exercise=str(payload["exercise"]),
            environment_id=str(payload["environment_id"]),
            executed_at_utc=str(payload["executed_at_utc"]),
            result=str(payload["result"]),
            objective=str(payload["objective"]),
            observed=str(payload["observed"]),
            artifact_file=str(payload["artifact_file"]),
            artifact_sha256=str(payload["artifact_sha256"]),
            operator=str(payload["operator"]),
        )
        if evidence.exercise not in PHASE_F_EXERCISES:
            raise ValueError(f"unknown Phase F exercise: {evidence.exercise}")
        if evidence.result not in {"passed", "failed"}:
            raise ValueError(f"invalid exercise result: {evidence.exercise}")
        if evidence.exercise in exercises:
            raise ValueError(f"duplicate exercise evidence: {evidence.exercise}")
        exercises.add(evidence.exercise)
        try:
            datetime.fromisoformat(evidence.executed_at_utc.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"invalid exercise timestamp: {evidence.exercise}"
            ) from exc
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", evidence.artifact_file):
            raise ValueError(f"invalid artifact filename: {evidence.exercise}")
        artifact = root / evidence.artifact_file
        if not artifact.is_file():
            raise ValueError(f"exercise artifact is missing: {evidence.exercise}")
        if not re.fullmatch(r"[0-9a-f]{64}", evidence.artifact_sha256):
            raise ValueError(f"invalid artifact digest: {evidence.exercise}")
        if _sha256(artifact) != evidence.artifact_sha256:
            raise ValueError(f"exercise artifact digest mismatch: {evidence.exercise}")
        if not evidence.environment_id.strip() or not evidence.operator.strip():
            raise ValueError(f"exercise attribution is incomplete: {evidence.exercise}")
        if not evidence.objective.strip() or not evidence.observed.strip():
            raise ValueError(f"exercise observation is incomplete: {evidence.exercise}")
        records.append(evidence)
    return tuple(records)


def evidence_digest(evidence: ExerciseEvidence) -> str:
    payload = json.dumps(
        {
            "exercise": evidence.exercise,
            "environment_id": evidence.environment_id,
            "executed_at_utc": evidence.executed_at_utc,
            "result": evidence.result,
            "objective": evidence.objective,
            "observed": evidence.observed,
            "artifact_file": evidence.artifact_file,
            "artifact_sha256": evidence.artifact_sha256,
            "operator": evidence.operator,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def record_exercise_evidence(
    root: Path,
    *,
    exercise: str,
    environment_id: str,
    executed_at_utc: str,
    result: str,
    objective: str,
    observed: str,
    artifact: Path,
    operator: str,
) -> Path:
    if exercise not in PHASE_F_EXERCISES:
        raise ValueError(f"unknown Phase F exercise: {exercise}")
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{exercise}.artifact"
    metadata = root / f"{exercise}.json"
    if destination.exists() or metadata.exists():
        raise FileExistsError(f"evidence already exists for {exercise}")
    shutil.copy2(artifact.resolve(strict=True), destination)
    payload = {
        "format": "fieldora.phase-f-exercise-evidence",
        "exercise": exercise,
        "environment_id": environment_id,
        "executed_at_utc": executed_at_utc,
        "result": result,
        "objective": objective,
        "observed": observed,
        "artifact_file": destination.name,
        "artifact_sha256": _sha256(destination),
        "operator": operator,
    }
    temporary = metadata.with_suffix(".json.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(metadata)
        load_exercise_evidence(root)
    except BaseException:
        temporary.unlink(missing_ok=True)
        metadata.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    return metadata

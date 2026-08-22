import hashlib
import json
from pathlib import Path

from natureai_next.server.operations_evidence import (
    evidence_digest,
    load_exercise_evidence,
    record_exercise_evidence,
)
from natureai_next.server.secret_rotation import SecretRotationRegistry


def test_secret_rotation_keeps_only_external_references(tmp_path: Path) -> None:
    registry = SecretRotationRegistry(tmp_path / "secrets.sqlite3")
    registry.stage("database", "v1", "vault://fieldora/database/v1", 100)
    first = registry.activate(
        "database", "v1", 101, expected_active_version=None
    )
    assert first.version_id == "v1"
    registry.stage("database", "v2", "vault://fieldora/database/v2", 200)
    second = registry.activate(
        "database", "v2", 201, expected_active_version="v1"
    )
    assert second.version_id == "v2"
    try:
        registry.stage("api", "bad", "plaintext-secret", 300)
    except ValueError:
        pass
    else:
        raise AssertionError("inline secret material was accepted")


def test_secret_rotation_rejects_stale_activation(tmp_path: Path) -> None:
    registry = SecretRotationRegistry(tmp_path / "secrets.sqlite3")
    registry.stage("signing", "v1", "kms://fieldora/signing/v1", 100)
    registry.activate("signing", "v1", 101, expected_active_version=None)
    registry.stage("signing", "v2", "kms://fieldora/signing/v2", 200)
    try:
        registry.activate(
            "signing", "v2", 201, expected_active_version=None
        )
    except ValueError as exc:
        assert str(exc) == "active_version_conflict"
    else:
        raise AssertionError("stale rotation was accepted")


def test_failure_evidence_is_strict_and_digestible(tmp_path: Path) -> None:
    artifact = tmp_path / "api-node-loss.artifact"
    artifact.write_bytes(b"exercise log")
    payload = {
        "format": "fieldora.phase-f-exercise-evidence",
        "exercise": "api-node-loss",
        "environment_id": "staging-eu-1",
        "executed_at_utc": "2026-07-29T10:00:00Z",
        "result": "passed",
        "objective": "no unauthorized disclosure and less than 30 seconds disruption",
        "observed": "zero disclosure; 4 seconds disruption",
        "artifact_file": artifact.name,
        "artifact_sha256": hashlib.sha256(b"exercise log").hexdigest(),
        "operator": "release-engineer",
    }
    (tmp_path / "api-node-loss.json").write_text(json.dumps(payload))
    evidence = load_exercise_evidence(tmp_path)
    assert len(evidence) == 1
    assert len(evidence_digest(evidence[0])) == 64


def test_evidence_recorder_copies_and_verifies_artifact(tmp_path: Path) -> None:
    source = tmp_path / "raw.log"
    source.write_text("verified provider output")
    evidence_root = tmp_path / "evidence"
    metadata = record_exercise_evidence(
        evidence_root,
        exercise="zone-failure",
        environment_id="staging-eu-1",
        executed_at_utc="2026-07-29T11:00:00Z",
        result="passed",
        objective="remain authorized and available",
        observed="objective met",
        artifact=source,
        operator="release-engineer",
    )
    assert metadata.is_file()
    assert load_exercise_evidence(evidence_root)[0].exercise == "zone-failure"
    (evidence_root / "zone-failure.artifact").write_text("tampered")
    try:
        load_exercise_evidence(evidence_root)
    except ValueError as exc:
        assert "digest mismatch" in str(exc)
    else:
        raise AssertionError("tampered exercise artifact was accepted")

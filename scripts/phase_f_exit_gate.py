"""Fail-closed Phase F exit-gate audit."""

from __future__ import annotations

import json
from pathlib import Path

from natureai_next import __version__
from natureai_next.server.operations_evidence import (
    PHASE_F_EXERCISES,
    load_exercise_evidence,
)
from natureai_next.server.production_deployment import assess_file
from natureai_next.server.production_recovery import assess_recovery_file


ROOT = Path(__file__).resolve().parents[1]


def evaluate(evidence_root: Path | None = None) -> dict[str, object]:
    deployment = assess_file(ROOT / "deployment/reference-production.json")
    recovery = assess_recovery_file(ROOT / "deployment/reference-recovery.json")
    platform_manifest = (
        ROOT / "deployment/kubernetes/base/platform.yaml"
    ).read_text(encoding="utf-8")
    exports_source = (
        ROOT / "src/natureai_next/server/exports.py"
    ).read_text(encoding="utf-8")
    api_source = (
        ROOT / "src/natureai_next/server/api.py"
    ).read_text(encoding="utf-8")
    server_cli_source = (
        ROOT / "src/natureai_next/bootstrap/server_cli.py"
    ).read_text(encoding="utf-8")
    evidence = load_exercise_evidence(
        ROOT / "deployment/evidence" if evidence_root is None else evidence_root
    )
    passed = {item.exercise for item in evidence if item.result == "passed"}
    failed = sorted(item.exercise for item in evidence if item.result == "failed")
    pending = sorted(set(PHASE_F_EXERCISES) - passed)
    environments = sorted({item.environment_id for item in evidence})
    environment_consistent = len(environments) <= 1
    implementation = {
        "deployment_contract": deployment.configuration_ready,
        "production_recovery_contract": recovery.recovery_ready,
        "kubernetes_reference": (
            ROOT / "deployment/kubernetes/base/platform.yaml"
        ).is_file(),
        "shared_export_objects": (
            "object_store: ObjectStore | None" in exports_source
            and "--s3-export-prefix" in platform_manifest
        ),
        "continuous_shared_workers": (
            "--continuous" in platform_manifest
            and "--export-metadata-backend" in platform_manifest
            and "--search-backend" in platform_manifest
        ),
        "dependency_readiness": (
            "/api/v1/health/ready" in api_source
            and "/api/v1/health/live" in platform_manifest
            and "/api/v1/health/ready" in platform_manifest
        ),
        "graceful_rolling_lifecycle": (
            "readiness.begin_draining" in server_cli_source
            and "not shutdown.requested" in server_cli_source
            and "terminationGracePeriodSeconds" in platform_manifest
        ),
        "tenant_governance": (ROOT / "src/natureai_next/server/tenant_governance.py").is_file(),
        "governance_administration": (
            ROOT / "src/natureai_next/bootstrap/governance_cli.py"
        ).is_file(),
        "retention_and_legal_holds": (ROOT / "src/natureai_next/server/retention.py").is_file(),
        "distributed_retention_administration": (
            ROOT / "src/natureai_next/server/postgres_retention.py"
        ).is_file()
        and (
            ROOT / "src/natureai_next/bootstrap/retention_cli.py"
        ).is_file(),
        "audit_export": (ROOT / "src/natureai_next/server/audit_export.py").is_file(),
        "audit_export_administration": (
            ROOT / "src/natureai_next/bootstrap/audit_export_cli.py"
        ).is_file(),
        "secret_rotation": (ROOT / "src/natureai_next/server/secret_rotation.py").is_file(),
        "distributed_secret_rotation_administration": (
            ROOT / "src/natureai_next/server/postgres_secret_rotation.py"
        ).is_file()
        and (
            ROOT / "src/natureai_next/bootstrap/secret_rotation_cli.py"
        ).is_file(),
        "threat_model": (ROOT / "docs/security/PHASE_F_THREAT_MODEL.md").is_file(),
        "incident_response": (ROOT / "docs/operations/incident-response.md").is_file(),
        "administrator_runbook": (ROOT / "docs/operations/phase-f-administrator-runbook.md").is_file(),
        "certification_workflow": (
            ROOT / "src/natureai_next/bootstrap/phase_f_certification_cli.py"
        ).is_file(),
        "sbom": (ROOT / "FIELDORA_SBOM.json").is_file(),
    }
    implementation_ready = all(implementation.values())
    certification_passed = (
        implementation_ready
        and not pending
        and not failed
        and len(environments) == 1
    )
    return {
        "format": "fieldora.phase-f-exit-gate",
        "format_version": 1,
        "phase": "F",
        "release": __version__,
        "implementation_ready": implementation_ready,
        "certification_status": "passed" if certification_passed else "conditional",
        "implementation": implementation,
        "passed_exercises": sorted(passed),
        "failed_exercises": failed,
        "pending_exercises": pending,
        "evidence_environments": environments,
        "environment_consistent": environment_consistent,
    }


def main() -> int:
    report = evaluate()
    destination = ROOT / "PHASE_F_EXIT_GATE.json"
    destination.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["implementation_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

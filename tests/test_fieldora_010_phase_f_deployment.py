import json
from pathlib import Path

from natureai_next.server.production_deployment import (
    assess_file,
    assess_production_deployment,
)


def test_reference_production_topology_is_ready_but_not_certified(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    report_path = tmp_path / "assessment.json"
    result = assess_file(root / "deployment/reference-production.json", report_path)
    assert result.configuration_ready is True
    assert result.certification_status == "conditional"
    assert "zone-failure" in result.pending_exercises
    assert json.loads(report_path.read_text())["configuration_ready"] is True


def test_single_node_or_inline_topology_fails_closed() -> None:
    result = assess_production_deployment(
        {
            "format": "fieldora.production-deployment",
            "format_version": 1,
            "mode": "single-node",
            "api": {"replicas": 1},
            "workers": {"replicas": 1},
            "database": {"backend": "sqlite"},
            "object_storage": {"backend": "filesystem"},
            "search": {"backend": "sqlite"},
            "ingress": {"tls": False},
            "secrets": {"provider": "inline", "rotation_days": 0},
            "upgrades": {"strategy": "replace", "max_unavailable": 1},
        }
    )
    assert result.configuration_ready is False
    codes = {issue.code for issue in result.issues}
    assert {
        "deployment.mode",
        "api.replicas",
        "workers.replicas",
        "database.backend",
        "objects.backend",
        "search.backend",
        "ingress.tls",
        "secrets.provider",
        "upgrades.strategy",
    } <= codes


def test_completed_failure_exercises_close_certification() -> None:
    root = Path(__file__).parents[1]
    document = json.loads(
        (root / "deployment/reference-production.json").read_text(encoding="utf-8")
    )
    first = assess_production_deployment(document)
    document["certification_evidence"]["completed_exercises"] = list(
        first.pending_exercises
    )
    result = assess_production_deployment(document)
    assert result.configuration_ready is True
    assert result.certification_status == "passed"
    assert result.pending_exercises == ()

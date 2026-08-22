import json
from pathlib import Path

from natureai_next.server.api import FieldoraApi
from natureai_next.server.readiness import ReadinessMonitor


def test_liveness_does_not_depend_on_external_services(tmp_path: Path) -> None:
    monitor = ReadinessMonitor(
        {"database": lambda: (_ for _ in ()).throw(OSError("secret endpoint"))},
        cache_seconds=0,
    )
    api = FieldoraApi(None, None, None, tmp_path, readiness=monitor)
    live = api.dispatch("GET", "/api/v1/health/live", {}, b"")
    ready = api.dispatch("GET", "/api/v1/health/ready", {}, b"")
    assert live.status == 200
    assert ready.status == 503
    payload = json.loads(ready.body)
    assert payload["checks"] == {"database": False}
    assert b"secret endpoint" not in ready.body


def test_readiness_requires_every_dependency(tmp_path: Path) -> None:
    state = {"database": True, "objects": True, "search": True}
    monitor = ReadinessMonitor(
        {name: lambda name=name: state[name] for name in state},
        cache_seconds=0,
    )
    api = FieldoraApi(None, None, None, tmp_path, readiness=monitor)
    assert api.dispatch("GET", "/api/v1/health/ready", {}, b"").status == 200
    state["search"] = False
    assert api.dispatch("GET", "/api/v1/health/ready", {}, b"").status == 503


def test_production_manifest_separates_readiness_and_liveness() -> None:
    root = Path(__file__).parents[1]
    manifest = (root / "deployment/kubernetes/base/platform.yaml").read_text()
    assert "path: /api/v1/health/ready" in manifest
    assert manifest.count("path: /api/v1/health/live") >= 2
    server = (root / "src/natureai_next/bootstrap/server_cli.py").read_text()
    assert 'readiness_checks["object-storage"]' in server
    assert 'readiness_checks["search"]' in server
    assert 'cursor.execute("SELECT 1")' in server

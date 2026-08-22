import json
from pathlib import Path

from natureai_next.server.api import FieldoraApi
from natureai_next.server.lifecycle import ShutdownCoordinator
from natureai_next.server.readiness import ReadinessMonitor


def test_shutdown_callbacks_are_idempotent() -> None:
    calls = []
    shutdown = ShutdownCoordinator((lambda: calls.append("drain"),))
    shutdown.request()
    shutdown.request()
    assert shutdown.requested
    assert calls == ["drain"]


def test_api_becomes_unready_when_drain_begins(tmp_path: Path) -> None:
    readiness = ReadinessMonitor({"database": lambda: True}, cache_seconds=60)
    api = FieldoraApi(None, None, None, tmp_path, readiness=readiness)
    assert api.dispatch("GET", "/api/v1/health/ready", {}, b"").status == 200
    readiness.begin_draining()
    response = api.dispatch("GET", "/api/v1/health/ready", {}, b"")
    assert response.status == 503
    assert json.loads(response.body)["checks"] == {"draining": False}
    assert api.dispatch("GET", "/api/v1/health/live", {}, b"").status == 200


def test_workers_stop_claiming_and_api_has_drain_window() -> None:
    root = Path(__file__).parents[1]
    cli = (root / "src/natureai_next/bootstrap/server_cli.py").read_text()
    http = (root / "src/natureai_next/server/http.py").read_text()
    manifest = (root / "deployment/kubernetes/base/platform.yaml").read_text()
    assert "while processed < args.max_jobs and not shutdown.requested" in cli
    assert "shutdown.wait(args.poll_seconds)" in cli
    assert "shutdown_grace_seconds=args.drain_seconds" in cli
    assert "time.sleep(shutdown_grace_seconds)" in http
    assert "terminationGracePeriodSeconds: 60" in manifest
    assert "terminationGracePeriodSeconds: 360" in manifest

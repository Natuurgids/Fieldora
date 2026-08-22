from pathlib import Path

from natureai_next.application.platform_features import parity_payload

ROOT = Path(__file__).parents[1]
HTML = (ROOT / "src/natureai_next/resources/server_web/index.html").read_text(encoding="utf-8")
JS = (ROOT / "src/natureai_next/resources/server_web/app.js").read_text(encoding="utf-8")
API = (ROOT / "src/natureai_next/server/api.py").read_text(encoding="utf-8")


def test_server_feature_registry_has_no_partial_or_missing_capabilities():
    server = parity_payload()["platforms"]["server"]
    assert server["implemented"] == server["total"]
    assert server["partial"] == 0
    assert server["missing"] == 0
    assert server["functionally_complete"] is True


def test_server_web_exposes_parity_workspaces():
    for page in ("projects", "capacity", "dossiers", "aiadmin", "reference", "connectors"):
        assert f'data-page="{page}"' in HTML
        assert f'id="page-{page}"' in HTML
        assert f'if(name==="{page}")' in JS


def test_server_api_exposes_shared_business_record_routes():
    for route in (
        "/api/v1/phases", "/api/v1/tasks", "/api/v1/sprints",
        "/api/v1/work-schedules", "/api/v1/absences", "/api/v1/obligations",
        "/api/v1/allocations", "/api/v1/dossier-reviews", "/api/v1/specimens",
        "/api/v1/encounters", "/api/v1/protocols", "/api/v1/survey-events",
        "/api/v1/enrichments", "/api/v1/samples", "/api/v1/laboratory-records",
        "/api/v1/reference-values", "/api/v1/ai-providers", "/api/v1/ai-models",
        "/api/v1/mcp-servers", "/api/v1/connectors",
    ):
        assert route in API
        slug = route.removeprefix("/api/v1/")
        assert slug in JS or slug in HTML


def test_server_observation_review_actions_are_visible_and_wired():
    for label in (
        "Accept selected", "Reject selected", "Defer selected",
        "Accept one; reject rest", "Reject all unconfirmed",
    ):
        assert label in HTML
    assert "reviewSelected" in JS
    assert "acceptOneRejectRest" in JS
    assert "rejectAllUnconfirmed" in JS

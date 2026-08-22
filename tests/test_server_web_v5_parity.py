from pathlib import Path


ROOT = Path(__file__).parents[1]
WEB = ROOT / "src" / "natureai_next" / "resources" / "server_web"
APP = (WEB / "app.js").read_text(encoding="utf-8")
HTML = (WEB / "index.html").read_text(encoding="utf-8")
API = (ROOT / "src" / "natureai_next" / "server" / "api.py").read_text(
    encoding="utf-8"
)


def test_six_offline_workspaces_are_present_in_server_web() -> None:
    for page in (
        "home", "library", "observations", "research", "knowledge",
        "administration",
    ):
        assert f'id="page-{page}"' in HTML
        assert f'data-page="{page}"' in HTML


def test_application_api_routes_have_web_workflows() -> None:
    routes = (
        "/api/v1/status", "/api/v1/health/live", "/api/v1/health/ready",
        "/api/v1/runtime", "/api/v1/session", "/api/v1/me", "/api/v1/audit",
        "/api/v1/projects", "/api/v1/dossiers", "/api/v1/collections",
        "/api/v1/observations", "/api/v1/knowledge", "/api/v1/search",
        "/api/v1/media", "/api/v1/uploads", "/api/v1/staged-submissions",
        "/api/v1/staged-files", "/api/v1/jobs", "/api/v1/exports",
        "/api/v1/admin/contracts", "/api/v1/admin/contract-approvals",
        "/api/v1/admin/contract-expiry", "/api/v1/device/code",
        "/api/v1/device/approve", "/api/v1/device/token",
        "/api/v1/help",
    )
    for route in routes:
        assert route in API
        assert route in APP


def test_protected_downloads_use_authenticated_fetch() -> None:
    assert 'async function download(path,filename)' in APP
    assert 'location.href=`/api/v1/exports/' not in APP
    assert 'id="media-download"' in APP


def test_postgresql_runtime_profile_is_visible() -> None:
    cli = (ROOT / "src" / "natureai_next" / "bootstrap" / "server_cli.py").read_text(
        encoding="utf-8"
    )
    for backend in (
        "access_backend", "science_backend", "media_metadata_backend",
        "job_backend", "export_metadata_backend", "governance_backend",
    ):
        assert f"args.{backend}" in cli
    assert 'api/v1/runtime' in API
    assert 'runtime.backends' in APP

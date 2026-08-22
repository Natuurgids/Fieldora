from natureai_next.server.api import ApiResponse
from natureai_next.server.web_compatibility import (
    openapi_document,
    patch_web_response,
    public_response,
    rewrite_public_target,
)


def test_short_health_paths_map_to_public_api_probes() -> None:
    assert rewrite_public_target("GET", "/health") == "/api/v1/health/ready"
    assert rewrite_public_target("GET", "/health/live") == "/api/v1/health/live"
    assert rewrite_public_target("GET", "/health/ready") == "/api/v1/health/ready"
    assert rewrite_public_target("POST", "/health") == "/health"


def test_openapi_and_docs_are_public_transport_responses() -> None:
    openapi = public_response("GET", "/openapi.json")
    assert openapi is not None
    assert openapi.status == 200
    assert b'"openapi":"3.1.0"' in openapi.body
    assert b'"/api/v1/health/ready"' in openapi.body

    docs = public_response("GET", "/docs")
    assert docs is not None
    assert docs.status == 200
    assert docs.content_type.startswith("text/html")
    assert b"/openapi.json" in docs.body


def test_openapi_contract_marks_governed_routes_as_authenticated() -> None:
    document = openapi_document()
    paths = document["paths"]
    assert paths["/api/v1/health/live"]["get"].get("security") is None
    assert paths["/api/v1/me"]["get"]["security"] == [{"bearerAuth": []}]
    assert paths["/api/v1/media"]["get"]["security"] == [{"bearerAuth": []}]


def test_app_bundle_patch_turns_header_import_into_file_picker_action() -> None:
    original = ApiResponse(200, b"console.log('fieldora');", "text/javascript")
    patched = patch_web_response("/app.js", original)

    assert patched.status == 200
    assert patched.body.startswith(original.body)
    assert b'.go-import' in patched.body
    assert b'picker.click()' in patched.body
    assert b'import-card' in patched.body

    # Applying the helper twice must not duplicate browser handlers.
    assert patch_web_response("/app.js", patched).body == patched.body


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_web_response("/api/v1/status", original) is original

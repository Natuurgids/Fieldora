from natureai_next.server.api import ApiResponse
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.http import patch_managed_web_response
from natureai_next.server.linked_storage_operator_web import (
    patch_linked_storage_operator_web_response,
)
from natureai_next.server.navigation_web_compatibility import (
    patch_navigation_web_response,
)
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


def test_navigation_patch_wires_history_and_cross_screen_project_opening() -> None:
    original = ApiResponse(200, b"console.log('fieldora');", "text/javascript")
    patched = patch_navigation_web_response("/app.js", original)

    assert patched.status == 200
    assert b"history.pushState" in patched.body
    assert b'window.addEventListener("popstate"' in patched.body
    assert b'window.addEventListener("hashchange"' in patched.body
    assert b"Open project workspace" in patched.body
    assert b"Open related project" in patched.body
    assert b"openProject(row.dataset.portfolioId)" in patched.body
    assert patch_navigation_web_response("/app.js", patched).body == patched.body


def test_contract_web_patch_exposes_owner_precedence_and_double_attestation() -> None:
    original = ApiResponse(200, b"console.log('fieldora');", "text/javascript")
    patched = patch_contract_web_response("/app.js", original)

    assert b"Data Access &amp; Contracts" in patched.body
    assert b"Evidence-owner restrictions are upstream" in patched.body
    assert b"two separate attestations" in patched.body
    assert b"/api/v1/access-barriers/evidence/" in patched.body
    assert b"/api/v1/access-barriers/projects/" in patched.body
    assert patch_contract_web_response("/app.js", patched).body == patched.body


def test_linked_storage_operator_patch_exposes_lifecycle_history_without_paths() -> None:
    original = ApiResponse(200, b"console.log('fieldora');", "text/javascript")
    patched = patch_linked_storage_operator_web_response("/app.js", original)

    assert b"Recent lifecycle activity" in patched.body
    assert b"linked_archive_events" in patched.body
    assert b"operator-linked-archive-events" in patched.body
    assert b"data-linked-archive-event" in patched.body
    assert b"root_alias" not in patched.body
    assert b"root_path" not in patched.body
    assert patch_linked_storage_operator_web_response("/app.js", patched).body == patched.body


def test_production_web_composition_includes_certified_browser_surfaces() -> None:
    original = ApiResponse(200, b"console.log('fieldora');", "text/javascript")
    patched = patch_managed_web_response("/app.js", original)

    assert b"Fieldora browser functionality: recursive intake" in patched.body
    assert b"Data Access &amp; Contracts" in patched.body
    assert b"Folder validation" in patched.body
    assert b"Fieldora linked archives" in patched.body
    assert b"Recent lifecycle activity" in patched.body
    assert b"fieldoraDesktopAlignmentWired" in patched.body
    assert b"Continue scientific work" in patched.body
    assert b"Create and inspect scientific records here" in patched.body
    assert b"New research record" in patched.body
    assert b"fieldoraLibraryCollectionsWired" in patched.body
    assert b"Collections & Datasets" in patched.body
    assert b"fieldoraScienceWorkflowWired" in patched.body
    assert b"Review observations" in patched.body
    assert b"Add identification" in patched.body
    assert patched.body.rfind(b"fieldoraDesktopAlignmentWired") > patched.body.rfind(
        b"Fieldora linked archives"
    )
    assert patched.body.rfind(b"fieldoraLibraryCollectionsWired") > patched.body.rfind(
        b"fieldoraDesktopAlignmentWired"
    )
    assert patched.body.rfind(b"fieldoraScienceWorkflowWired") > patched.body.rfind(
        b"fieldoraLibraryCollectionsWired"
    )


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})
    assert patch_web_response("/api/v1/status", original) is original
    assert patch_contract_web_response("/api/v1/status", original) is original
    assert patch_navigation_web_response("/api/v1/status", original) is original
    assert patch_linked_storage_operator_web_response("/api/v1/status", original) is original

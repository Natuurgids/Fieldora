from natureai_next.server.api import ApiResponse
from natureai_next.server.library_collections_web import (
    patch_library_collections_web_response,
)


def test_library_collection_patch_exposes_full_non_destructive_parity_controls() -> None:
    response = patch_library_collections_web_response(
        "/app.js", ApiResponse(200, b"window.baseApp=true;", "text/javascript")
    )

    assert response.status == 200
    script = response.body.decode()
    assert "Collections & Datasets" in script
    assert "Create collection" in script
    assert "Edit" in script
    assert "Add evidence" in script
    assert "Remove from collection" in script
    assert "Delete collection" in script
    assert "/api/v1/library/collections" in script
    assert "membership is reference-only" in script.casefold()
    assert "never deletes the governed evidence or its provenance" in script
    assert "Evidence public IDs to remove from this collection only" in script
    assert "evidence and provenance will not be deleted" in script


def test_library_collection_patch_is_app_js_only_and_idempotent() -> None:
    original = ApiResponse(200, b"window.baseApp=true;", "text/javascript")
    unchanged = patch_library_collections_web_response("/index.html", original)
    assert unchanged is original

    first = patch_library_collections_web_response("/app.js?v=38", original)
    second = patch_library_collections_web_response("/app.js?v=38", first)
    assert second.body == first.body
    assert second.body.count(b"window.__fieldoraLibraryCollectionsWired") == 2

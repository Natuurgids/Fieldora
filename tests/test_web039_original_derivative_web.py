from natureai_next.server.api import ApiResponse
from natureai_next.server.original_derivative_web import (
    patch_original_derivative_response,
)


def test_app_patch_labels_original_authoritative_and_derivatives_separate() -> None:
    base = ApiResponse(200, b"window.baseApp=true;", "text/javascript")
    response = patch_original_derivative_response("/app.js", base)
    script = response.body.decode()

    assert "__fieldoraOriginalDerivativeWired" in script
    assert "/derivatives" in script
    assert "Governed original" in script
    assert "Thumbnails, previews, transcodes, and analysis outputs" in script
    assert "never replace or silently mutate it" in script
    assert "source_sha256" in script


def test_app_patch_is_idempotent_and_ignores_non_app_responses() -> None:
    base = ApiResponse(200, b"window.baseApp=true;", "text/javascript")
    once = patch_original_derivative_response("/app.js", base)
    twice = patch_original_derivative_response("/app.js", once)
    assert twice.body == once.body

    untouched = patch_original_derivative_response(
        "/api/v1/media/example/derivatives",
        ApiResponse.json(200, {"items": []}),
    )
    assert untouched.body == b'{"items":[]}'

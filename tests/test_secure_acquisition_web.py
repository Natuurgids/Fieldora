from natureai_next.server.api import ApiResponse
from natureai_next.server.secure_acquisition_web import patch_secure_acquisition_web_response


def _response(body: bytes = b"base") -> ApiResponse:
    return ApiResponse(200, body, "application/javascript", ())


def test_secure_acquisition_patch_is_app_js_only_and_idempotent() -> None:
    original = _response()
    assert patch_secure_acquisition_web_response("/index.html", original) is original

    patched = patch_secure_acquisition_web_response("/app.js", original)
    assert patched.body != original.body
    assert patch_secure_acquisition_web_response("/app.js", patched).body == patched.body


def test_secure_acquisition_web_projects_transfer_broker_contract() -> None:
    text = patch_secure_acquisition_web_response("/app.js", _response()).body.decode()

    for required in (
        "Secure acquisition",
        "FieldoraBastion",
        "secure transfer broker",
        "collection requests",
        "delivery requests",
        "quarantines",
        "scans",
        "verifies",
        "approved",
        "broadcast",
        "claimed",
        "transferred",
        "collector-verifying",
        "accepted",
        "authenticated collector",
        "recomputes the digest",
        "integrity-failed",
        "package_integrity_mismatch",
        "security monitoring host",
        "browser cannot mark content clean",
        "/api/v1/models/installed",
        "/api/v1/maps/installed",
        "Signed + clean scanned",
    ):
        assert required in text

    for forbidden in (
        "mark-clean",
        "approve-scan",
        "quarantine-path",
        "filesystem-path",
        "/api/v1/bastion/approve",
    ):
        assert forbidden not in text

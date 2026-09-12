from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.directory_intake_web import patch_directory_intake_response


def _patched_app() -> str:
    response = patch_directory_intake_response(
        "/app.js",
        ApiResponse(200, b"const existingApp=true;", "application/javascript", {}),
    )
    return response.body.decode("utf-8")


def test_background_folder_import_keeps_durable_safe_submission_context() -> None:
    script = _patched_app()

    assert 'fieldora.background-folder-imports.v1' in script
    assert "submission_id" in script
    assert "expected_files" in script
    assert "completed_files" in script
    assert "updated_at" in script
    assert "Background imports" in script
    assert "Refresh" in script
    assert "Dismiss" in script
    assert "localStorage" in script

    # Browser persistence is intentionally bounded metadata. Local filesystem paths,
    # filenames, payload bytes, credentials, and contract IDs are not persisted.
    persistence = script[script.index("function readBackgroundImports"):script.index("function removeBackgroundImport")]
    for forbidden in (
        "relative_path",
        "filename",
        "quarantine_path",
        "contract_id",
        "bytes",
        "token",
        "password",
    ):
        assert forbidden not in persistence


def test_background_timeout_is_not_presented_as_failure_and_can_reconcile() -> None:
    script = _patched_app()

    assert "class BackgroundImportContinues extends Error" in script
    assert "this.background=true" in script
    assert "Folder publication continues in the background" in script
    assert 'status("upload-status",e.message||String(e),false)' in script
    assert "refreshBackgroundImport(item.submission_id,{quiet:true})" in script
    assert 'if(summary.state==="published")' in script
    assert 'if(typeof loadMedia==="function")await loadMedia()' in script


def test_folder_submission_id_is_saved_before_upload_and_never_recreated_on_refresh() -> None:
    script = _patched_app()

    create = 'api("/api/v1/staged-submissions",{method:"POST"'
    refresh = "refreshBackgroundImport(submissionId"
    assert script.count(create) == 1
    assert refresh in script
    assert "rememberBackgroundImport(sid,{state:created.submission.state" in script
    assert "encodeURIComponent(submissionId)" in script

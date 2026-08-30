from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.intake_review_web import patch_intake_review_web_response


def test_intake_review_patch_connects_submission_to_review_and_acceptance() -> None:
    response = patch_intake_review_web_response(
        "/app.js",
        ApiResponse(200, b"const fieldora=true;", "application/javascript"),
    )
    script = response.body.decode("utf-8")

    assert 'action.textContent="Request review"' in script
    assert 'byId("review-subject-type").value="submission"' in script
    assert 'byId("review-subject").value=submissionId' in script
    assert 'byId("review-project").value=project==="General Library"?"":project' in script
    assert 'action.textContent="Accept determination"' in script
    assert 'byId("review-accept-id").value=determinationId' in script
    assert 'byId("review-accept").click()' in script


def test_intake_review_patch_only_changes_the_app_bundle() -> None:
    untouched = ApiResponse.json(200, {"ok": True})
    assert patch_intake_review_web_response("/api/v1/me", untouched) is untouched

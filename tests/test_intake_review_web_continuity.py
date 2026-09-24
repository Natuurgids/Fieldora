from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.intake_review_web import patch_intake_review_web_response


def _script() -> str:
    response = patch_intake_review_web_response(
        "/app.js",
        ApiResponse(200, b"const fieldora=true;", "application/javascript"),
    )
    return response.body.decode("utf-8")


def test_intake_review_patch_connects_submission_to_review_and_acceptance() -> None:
    script = _script()

    assert 'action.textContent="Request review"' in script
    assert 'byId("review-subject-type").value="submission"' in script
    assert 'byId("review-subject").value=submissionId' in script
    assert 'byId("review-project").value=project' in script
    assert 'action.textContent="Accept determination"' in script
    assert 'byId("review-accept-id").value=determinationId' in script
    assert 'byId("review-accept").click()' in script


def test_intake_review_refreshes_real_lists_when_research_subnav_opens() -> None:
    script = _script()

    assert 'api("/api/v1/submissions?limit=100")' in script
    assert 'api("/api/v1/review-cases?limit=100")' in script
    assert 'refresh.id="intake-review-refresh"' in script
    assert 'data-workspace-target="intake-review"' in script
    assert "setTimeout(refreshIntakeReview,0)" in script
    assert 'data-submission-id="${html(item.submission_id)}"' in script
    assert 'data-review-case-id="${html(item.review_case_id)}"' in script


def test_review_selection_loads_determinations_and_keeps_case_selected() -> None:
    script = _script()

    assert 'api(`/api/v1/review-cases/${encodeURIComponent(reviewCaseId)}`)' in script
    assert 'byId("review-case-id").value=reviewCaseId' in script
    assert 'data-determination-id="${html(d.determination_id)}"' in script
    assert "loadReviewCase(row.dataset.reviewCaseId)" in script
    assert 'setTimeout(refreshIntakeReview,250)' in script


def test_intake_review_patch_only_changes_the_app_bundle() -> None:
    untouched = ApiResponse.json(200, {"ok": True})
    assert patch_intake_review_web_response("/api/v1/me", untouched) is untouched


def test_intake_review_is_owned_by_research_workspace_navigation() -> None:
    from natureai_next.server.desktop_alignment_web import patch_desktop_alignment_web_response

    response = patch_desktop_alignment_web_response(
        "/app.js",
        ApiResponse(200, b"const fieldora=true;", "application/javascript"),
    )
    script = response.body.decode("utf-8")

    research = script.split("const researchPages=[", 1)[1].split("];", 1)[0]
    administration = script.split("const adminPages=[", 1)[1].split("];", 1)[0]
    assert '["intake-review","Intake & Expert Review"]' in research
    assert '"intake-review"' not in administration


def test_system_health_is_separate_from_governance_workspace() -> None:
    from natureai_next.server.administration_workspace_web import (
        patch_administration_workspace_web_response,
    )
    from natureai_next.server.desktop_alignment_web import (
        patch_desktop_alignment_web_response,
    )

    response = patch_administration_workspace_web_response(
        "/app.js",
        ApiResponse(200, b"const fieldora=true;", "application/javascript"),
    )
    response = patch_desktop_alignment_web_response("/app.js", response)
    script = response.body.decode("utf-8")

    assert 'healthPage.id="page-system-health"' in script
    assert "healthPage.appendChild(runtimeCard)" in script
    assert 'legacyRefresh.remove()' in script
    assert 'page==="system-health"' in script
    assert '["system-health","System health"]' in script


def test_desktop_sidebar_preserves_whiteboards_destination() -> None:
    from natureai_next.server.desktop_alignment_web import (
        patch_desktop_alignment_web_response,
    )
    from natureai_next.server.excalidraw_web import ExcalidrawWebMixin

    html = ApiResponse(200, b"<nav></nav>", "text/html")
    shell = ExcalidrawWebMixin._excalidraw_shell_link(html).body.decode("utf-8")
    assert 'id="whiteboards-link"' in shell
    assert 'data-fieldora-external-route="/whiteboards/"' in shell

    response = patch_desktop_alignment_web_response(
        "/app.js",
        ApiResponse(200, b"const fieldora=true;", "application/javascript"),
    )
    script = response.body.decode("utf-8")
    assert 'document.getElementById("whiteboards-link")' in script
    assert "sidebar.appendChild(whiteboards)" in script


def test_whiteboards_uses_canonical_project_context() -> None:
    from natureai_next.server.excalidraw_web import ExcalidrawWebMixin

    response = ExcalidrawWebMixin._excalidraw_shell_script(
        ApiResponse(200, b"", "application/javascript")
    )
    script = response.body.decode("utf-8")
    assert 'resolve?.("projects.context.select")' in script
    assert "projectContext?.current?.()" in script
    assert "selectedProject" not in script
    assert "projects[0]" not in script

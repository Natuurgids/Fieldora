from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.observation_parity_api import ObservationParityApiMixin
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.science_workflow_web import patch_science_workflow_web_response
from natureai_next.server.web_module_contracts import foundation_registry


def test_managed_api_composes_observation_parity_before_legacy_science_mutations() -> None:
    assert issubclass(OfflineFirstFieldoraApi, ObservationParityApiMixin)
    assert OfflineFirstFieldoraApi.__mro__.index(ObservationParityApiMixin) < (
        OfflineFirstFieldoraApi.__mro__.index(
            next(
                cls
                for cls in OfflineFirstFieldoraApi.__mro__
                if cls.__name__ == "FieldoraApi"
            )
        )
    )


def test_observation_browser_patch_is_evidence_first_and_revisioned() -> None:
    response = patch_science_workflow_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "Create a field observation from existing governed evidence" in script
    assert "Existing evidence" in script
    assert "asset_id:asset" in script
    assert 'method:"PATCH"' in script
    assert '"If-Match"' in script
    assert "links it without cloning" in script
    assert "crypto.randomUUID()" not in script


def test_observation_project_defaults_use_optional_runtime_contracts() -> None:
    response = patch_science_workflow_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")
    observations = foundation_registry().resolve("/observations")

    assert observations is not None
    assert observations.module_id == "observations.core"
    assert observations.dependencies == ()
    assert observations.requires_contracts == ()
    assert 'resolve?.("projects.context.select")' in script
    assert 'resolve?.("projects.list.read")' in script
    assert "projectContext()?.current?.()" in script
    assert "projectList()?.items?.()" in script
    assert 'name==="projects.list.read"' in script
    assert "fieldora:project-list-changed" in script
    assert "selectedProject" not in script
    assert "projects[0]" not in script
    assert "projectOptions()" not in script


def test_observation_browser_supports_revisioned_many_to_many_evidence_links() -> None:
    response = patch_science_workflow_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "Supporting evidence" in script
    assert "Link evidence" in script
    assert "supporting_asset_ids" in script
    assert "/evidence`" in script
    assert "/evidence/${encodeURIComponent(asset)}`" in script
    assert 'method:"DELETE"' in script
    assert '"If-Match":String(editingObservation.revision||1)' in script
    assert "without changing or copying the primary evidence" in script


def test_observation_workspace_state_is_owned_inside_science_module() -> None:
    script = patch_science_workflow_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    ).body.decode("utf-8")

    assert 'let observationItems=Object.freeze([]),observationFilterState="all"' in script
    assert "const selectedObservationIds=new Set()" in script
    assert "fieldora:observation-state-changed" in script
    assert "items:observationItems" in script
    assert "selected:Object.freeze([...selectedObservationIds])" in script
    assert "replaceObservationItems((await api(\"/api/v1/observations\")).items)" in script
    assert "toggleObservationSelection(id,event.target.checked)" in script
    assert "setObservationFilter(button.dataset.observationFilter)" in script
    assert "observations.find(" not in script
    assert "selectedObservations" not in script
    assert 'let observationFilter="all"' not in script
    assert "observations=(await" not in script


def test_observation_filter_presentation_is_not_owned_by_generic_navigation() -> None:
    science_script = patch_science_workflow_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    ).body.decode("utf-8")
    navigation_script = patch_navigation_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    ).body.decode("utf-8")

    assert "function projectObservationFilterState()" in science_script
    assert 'button.classList.toggle("primary",active)' in science_script
    assert 'button.setAttribute("aria-selected",String(active))' in science_script
    assert 'button.setAttribute("role","tab")' in science_script
    assert "projectObservationFilterState();" in science_script
    assert '"observation-filter"' not in navigation_script

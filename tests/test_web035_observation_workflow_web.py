from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.observation_parity_api import ObservationParityApiMixin
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi
from natureai_next.server.science_workflow_web import patch_science_workflow_web_response


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

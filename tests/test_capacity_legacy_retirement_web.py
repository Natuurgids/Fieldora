from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.capacity_availability_module_web import (
    CapacityAvailabilityModuleWebApiMixin,
)
from natureai_next.server.capacity_legacy_retirement_web import (
    CapacityLegacyRetirementWebApiMixin,
    patch_capacity_legacy_retirement_response,
)
from natureai_next.server.capacity_module_web import patch_capacity_module_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


def _legacy_capacity_app() -> ApiResponse:
    body = (
        b'if(name==="capacity")loadCapacity();'
        b"async function loadCapacity(){const legacyLoad=true;}"
        b"async function saveCapacity(){const legacySave=true;}"
        b"async function loadDossierWorkspace(){const dossier=true;}"
        b'q("capacity-refresh").onclick=loadCapacity;'
        b'q("capacity-save").onclick=saveCapacity;'
    )
    return ApiResponse(200, body, "text/javascript; charset=utf-8")


def test_capacity_load_retirement_requires_both_modular_owners() -> None:
    base = _legacy_capacity_app()

    availability_only = CapacityAvailabilityModuleWebApiMixin._patch_browser(
        "/app.js", base
    )
    preserved = patch_capacity_legacy_retirement_response(
        "/app.js", availability_only
    ).body.decode("utf-8")

    assert "WEB-CAPACITY-AVAILABILITY-MODULE" in preserved
    assert "WEB-CAPACITY-MODULE" not in preserved
    assert "async function loadCapacity(){" in preserved
    assert 'if(name==="capacity")loadCapacity();' in preserved
    assert 'q("capacity-refresh").onclick=loadCapacity;' in preserved


def test_capacity_load_retirement_removes_only_competing_legacy_loader() -> None:
    allocation_owned = patch_capacity_module_response("/app.js", _legacy_capacity_app())
    fully_owned = CapacityAvailabilityModuleWebApiMixin._patch_browser(
        "/app.js", allocation_owned
    )
    final = patch_capacity_legacy_retirement_response("/app.js", fully_owned)
    script = final.body.decode("utf-8")

    assert "WEB-CAPACITY-MODULE" in script
    assert "WEB-CAPACITY-AVAILABILITY-MODULE" in script
    assert "async function loadCapacity(){" not in script
    assert "async function saveCapacity(){" not in script
    assert 'if(name==="capacity")loadCapacity();' not in script
    assert 'q("capacity-refresh").onclick=loadCapacity;' not in script
    assert 'q("capacity-save").onclick=saveCapacity;' not in script
    assert "async function loadDossierWorkspace(){const dossier=true;}" in script
    assert patch_capacity_legacy_retirement_response("/app.js", final).body == final.body


def test_capacity_legacy_retirement_is_composed_after_capacity_owners() -> None:
    mro = OfflineFirstFieldoraApi.__mro__

    assert CapacityLegacyRetirementWebApiMixin in mro
    availability = next(
        base for base in mro if base.__name__ == "CapacityAvailabilityModuleWebApiMixin"
    )
    allocation = next(base for base in mro if base.__name__ == "CapacityModuleWebApiMixin")
    assert mro.index(CapacityLegacyRetirementWebApiMixin) < mro.index(availability)
    assert mro.index(availability) < mro.index(allocation)


def test_non_app_response_is_untouched() -> None:
    original = ApiResponse.json(200, {"ok": True})

    assert (
        patch_capacity_legacy_retirement_response("/api/v1/status", original)
        is original
    )

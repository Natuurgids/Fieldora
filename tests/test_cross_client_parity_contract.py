from natureai_next.application.platform_features import (
    FeatureStatus,
    Platform,
    feature_registry,
    parity_payload,
)


def _feature(feature_id: str):
    return next(item for item in feature_registry() if item.feature_id == feature_id)


def _status(feature_id: str, platform: Platform) -> FeatureStatus:
    feature = _feature(feature_id)
    return next(
        item.status for item in feature.implementations if item.platform == platform
    )


def test_facility_capabilities_are_explicitly_shared_across_clients() -> None:
    expected = {
        "operations.facility_floorplans",
        "operations.facility_planning",
        "operations.relocation",
    }
    assert expected.issubset({item.feature_id for item in feature_registry()})

    for feature_id in expected:
        assert _status(feature_id, Platform.WINDOWS_DESKTOP) == FeatureStatus.IMPLEMENTED
        assert _status(feature_id, Platform.LINUX_DESKTOP) == FeatureStatus.IMPLEMENTED
        assert _status(feature_id, Platform.SERVER) == FeatureStatus.PARTIAL


def test_server_parity_stays_incomplete_until_browser_facility_workspaces_exist() -> None:
    server = parity_payload()["platforms"][Platform.SERVER.value]
    assert server["partial"] >= 3
    assert server["functionally_complete"] is False


def test_planning_contract_keeps_live_location_authoritative() -> None:
    planning = _feature("operations.facility_planning")
    assert "never changes authoritative current physical placement" in planning.description

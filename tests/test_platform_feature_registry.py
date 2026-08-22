from natureai_next.application.platform_features import (
    FeatureStatus, Platform, feature_registry, parity_payload, validate_registry,
)

def test_registry_declares_every_platform_and_unique_features():
    validate_registry()
    features=feature_registry()
    assert len({f.feature_id for f in features})==len(features)
    assert all({i.platform for i in f.implementations}==set(Platform) for f in features)

def test_windows_and_linux_share_complete_desktop_capabilities():
    payload=parity_payload()["platforms"]
    for name in ("windows_desktop","linux_desktop"):
        assert payload[name]["missing"]==0
        assert payload[name]["partial"]==0
        assert payload[name]["functionally_complete"] is True

def test_server_capabilities_are_functionally_complete():
    payload=parity_payload()["platforms"]["server"]
    assert payload["implemented"]==payload["total"]
    assert payload["partial"]==0
    assert payload["missing"]==0
    assert payload["functionally_complete"] is True

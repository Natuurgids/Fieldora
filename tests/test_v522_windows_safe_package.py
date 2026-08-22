from scripts.deployment_preflight import windows_path_failures


def test_windows_path_validator_rejects_openseamap_colon() -> None:
    assert windows_path_failures(["maps/openseamap:abc-current.mbtiles"])


def test_windows_path_validator_accepts_portable_openseamap_id() -> None:
    assert windows_path_failures(["maps/openseamap-abc-current.mbtiles"]) == ()


def test_windows_path_validator_rejects_reserved_names() -> None:
    assert windows_path_failures(["maps/CON.mbtiles"])

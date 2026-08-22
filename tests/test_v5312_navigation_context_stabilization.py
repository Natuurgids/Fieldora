from natureai_next.ui.qt.navigation_contracts import workspace_names


def test_administration_tile_pages_are_registered_for_direct_routing() -> None:
    registered = set(workspace_names())
    assert "Administration Governance" in registered
    assert "Research Reference Data" in registered

from natureai_next.ui.qt.navigation_contracts import workspace_names


def test_research_tile_and_hidden_workspace_route_are_connected():
    assert "Measurements & Protocols" in workspace_names()

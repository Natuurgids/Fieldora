from natureai_next.ui.qt.navigation_contracts import workspace_names


def test_platform_parity_is_in_canonical_workspace_registry():
    names = workspace_names()
    assert "Platform Parity" in names
    assert names.index("Platform Parity") == names.index("Administration Governance") + 1


def test_build_pages_and_registry_have_same_order():
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "src/natureai_next/ui/qt/v5_desktop.py"
    ).read_text(encoding="utf-8")
    for name in workspace_names():
        assert f'"{name}"' in source

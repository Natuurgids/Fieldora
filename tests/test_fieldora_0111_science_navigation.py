from pathlib import Path


def test_navigation_separates_science_from_platform_management() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert '"Science Workspace"' in source
    assert '"Platform Management"' in source
    for group in (
        "Research",
        "Library",
        "Scientific Records",
        "Knowledge",
        "Analysis",
        "People & Governance",
        "AI & Processing",
        "Knowledge Configuration",
        "Library Administration",
        "Operations",
        "Appearance",
    ):
        assert f'"{group}"' in source
    assert '("Plants & Fungi", "Plant & Flower Records")' in source
    assert '("Operations Center", "Activity Center")' in source


def test_menu_bar_has_balanced_research_and_platform_taxonomy() -> None:
    source = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    for menu in ("&File", "&Research", "&Data", "&Analyse", "&Collaborate", "&Platform", "&Help"):
        assert f'addMenu("{menu}")' in source
    for retired in ("&Library", "&Observations", "&Knowledge", "&Science", "&Tools && Resources",
                    "&Settings", "&About Fieldora"):
        assert f'addMenu("{retired}")' not in source
    assert 'platform_menu.addMenu("AI & Processing")' in source
    assert 'platform_menu.addMenu("Library Administration")' in source
    assert 'help_menu.addAction(self._about_action)' in source


def test_science_screen_labels_follow_approved_language() -> None:
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    assert '"Plants & Fungi"' in source
    assert '"Research Calendar"' in source
    assert '"Other Specimens & Artifacts"' in source
    assert '"Whiteboards"' in source

from pathlib import Path

from natureai_next.application.project_management import ProjectManagementService


def test_public_holidays_are_available_on_clean_service(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    assert service.public_holidays("2026-01-01", "2026-12-31") == ()
    service.add_public_holiday("2026-12-25", "Christmas Day")
    assert service.public_holidays("2026-12-25", "2026-12-25") == (
        {"date": "2026-12-25", "name": "Christmas Day"},
    )


def test_public_holidays_accept_reversed_range(tmp_path: Path) -> None:
    service = ProjectManagementService(tmp_path / "science.sqlite3")
    service.add_public_holiday("2026-01-01", "New Year")
    assert service.public_holidays("2026-01-02", "2025-12-31")[0]["name"] == "New Year"


def test_science_workspace_defines_dossier_project_refresh_callback() -> None:
    source = Path("src/natureai_next/ui/qt/science.py").read_text(encoding="utf-8")
    assert "def _refresh_dossier_project_choices(self)" in source
    assert "self._refresh_dossier_project_choices()" in source

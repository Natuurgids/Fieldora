from pathlib import Path


def test_measurements_workspace_selects_first_accessible_project() -> None:
    source = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    assert "if choice==0 and projects:choice=1" in source


def test_no_project_actions_are_visibly_disabled_with_explanation() -> None:
    source = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    assert "button.setEnabled(allowed)" in source
    assert "Select a project to use this action" in source
    assert "Select a project to continue" in source


def test_sample_workflow_actions_require_project_then_sample() -> None:
    source = Path('src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    assert "def _custody(self):\n  if not self._active_project():return\n  sample=self._selected_sample()" in source
    assert "def _laboratory(self):\n  if not self._active_project():return\n  sample=self._selected_sample()" in source

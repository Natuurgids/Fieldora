from pathlib import Path


def _class_block(source: str, name: str, next_name: str) -> str:
    return source[source.index(f"class {name}(Page):"):source.index(f"class {next_name}(Page):")]


def test_observations_context_callback_is_defined_on_observations_class() -> None:
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    observations = _class_block(source, "Observations", "AIChatWorkspace")
    library = _class_block(source, "Library", "Observations")

    assert "self.context.subscribe(self._context_event)" in observations
    assert "def _context_event(self,event):" in observations
    assert "def _notify_changed(self):" in observations
    assert "def _update_review_actions(self):" in observations
    assert "def _context_event(self,event):" not in library
    assert "self.review_buttons" not in library

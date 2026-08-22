from pathlib import Path


def test_measurements_sampling_constructor_does_not_reference_admin_buttons() -> None:
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    start = source.index("class MeasurementsSampling(Page):")
    end = source.index("\nclass ", start + 1)
    class_source = source[start:end]
    assert "self.admin_buttons" not in class_source
    assert "self.action_buttons" in class_source


def test_admin_buttons_is_initialized_before_governance_uses_it() -> None:
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    first_initialization = source.index("self.admin_buttons=[]")
    first_append = source.index("self.admin_buttons.append", first_initialization)
    assert first_initialization < first_append

from pathlib import Path


SOURCE = Path("src/natureai_next/ui/qt/v5_desktop.py")


def test_tool_cards_do_not_clip_wrapped_titles_or_buttons():
    source = SOURCE.read_text(encoding="utf-8")
    card = source[source.index(" def card("):source.index(" def tabs(")]

    assert "heading.setWordWrap(False)" in card
    assert "heading.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)" in card
    assert "QSizePolicy.Policy.MinimumExpanding" in card
    assert "setMaximumHeight" not in card


def test_shared_buttons_keep_a_readable_single_row_height():
    source = SOURCE.read_text(encoding="utf-8")
    button = source[source.index(" def button("):source.index(" def label(")]

    assert "b.setMinimumHeight(36)" in button
    assert "QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Fixed" in button


def test_reported_long_tool_titles_are_present():
    source = SOURCE.read_text(encoding="utf-8")

    assert "Projects & research maps" in source
    assert "Observation.org exchange" in source

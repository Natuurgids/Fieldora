from pathlib import Path

import natureai_next


def test_v3_rc1_version_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    assert natureai_next.__version__ == "5.4.0"
    assert (root / "VERSION").read_text(encoding="utf-8").strip() == "5.4.0"
    assert 'version = "5.4.0"' in (root / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert "Build 6" in (root / "RELEASE_NOTES.md").read_text(encoding="utf-8")

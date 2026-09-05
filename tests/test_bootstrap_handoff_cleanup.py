from pathlib import Path

import pytest

from natureai_next.bootstrap.bootstrap_handoff_cleanup_cli import expire_handoff


def _write_handoff(root: Path, expires_at: int) -> None:
    root.mkdir()
    (root / "ADMIN-CREDENTIALS.txt").write_text("temporary-secret\n", encoding="utf-8")
    (root / "EXPIRES-AT-EPOCH").write_text(str(expires_at), encoding="ascii")


def test_handoff_is_preserved_before_expiry(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    _write_handoff(handoff, 200)

    assert not expire_handoff(handoff, now_epoch=199)
    assert (handoff / "ADMIN-CREDENTIALS.txt").is_file()
    assert (handoff / "EXPIRES-AT-EPOCH").is_file()


def test_handoff_is_deleted_at_expiry_without_touching_other_files(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    _write_handoff(handoff, 200)
    retained = handoff / "INSTALLATION-RECEIPT.txt"
    retained.write_text("keep\n", encoding="utf-8")

    assert expire_handoff(handoff, now_epoch=200)
    assert not (handoff / "ADMIN-CREDENTIALS.txt").exists()
    assert not (handoff / "EXPIRES-AT-EPOCH").exists()
    assert retained.read_text(encoding="utf-8") == "keep\n"


def test_missing_or_invalid_expiry_never_deletes_credentials(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    handoff.mkdir()
    credentials = handoff / "ADMIN-CREDENTIALS.txt"
    credentials.write_text("temporary-secret\n", encoding="utf-8")

    assert not expire_handoff(handoff, now_epoch=999)
    assert credentials.is_file()

    (handoff / "EXPIRES-AT-EPOCH").write_text("invalid", encoding="ascii")
    assert not expire_handoff(handoff, now_epoch=999)
    assert credentials.is_file()


def test_handoff_names_cannot_escape_the_directory(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    handoff.mkdir()

    with pytest.raises(ValueError):
        expire_handoff(handoff, credentials_name="../outside.txt", now_epoch=999)

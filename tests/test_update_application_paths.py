from __future__ import annotations

from pathlib import Path

from natureai_next.bootstrap.paths import resolve_application_paths


def test_update_state_and_trust_anchor_are_bound_to_explicit_application_root(
    tmp_path: Path, monkeypatch,
) -> None:
    explicit_root = tmp_path / "administrator-root"
    inherited_root = tmp_path / "inherited-root"
    monkeypatch.setenv("APERTURE_DATA_ROOT", str(inherited_root))
    monkeypatch.setenv("NATUREAI_DATA_ROOT", str(inherited_root))

    paths = resolve_application_paths(explicit_root)

    assert paths.local_root == explicit_root.resolve()
    assert paths.updates_dir == explicit_root.resolve() / "updates"
    assert paths.update_trust_anchor_file == explicit_root.resolve() / "update-trust-anchors.json"
    assert inherited_root.resolve() not in paths.updates_dir.parents
    assert inherited_root.resolve() not in paths.update_trust_anchor_file.parents

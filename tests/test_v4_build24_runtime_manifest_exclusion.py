from pathlib import Path

from release_manifest import build_manifest, verify_manifest


def test_v4_runtime_tree_is_not_release_content(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='aperture'\n")
    manifest = build_manifest(tmp_path, version="4.0.0.dev1", build="24")

    runtime_files = [
        "FieldoraData-V5/config/installation.json",
        "FieldoraData-V5/launchers/launcher_common.ps1",
        "FieldoraData-V5/launchers/repair_shortcuts.ps1",
        "FieldoraData-V5/cache/huggingface/hub/models--imageomics--bioclip/refs/main",
        "FieldoraData-V5/cache/huggingface/hub/datasets--imageomics--TreeOfLife-10M/refs/main",
    ]
    for relative in runtime_files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime")

    result = verify_manifest(tmp_path, manifest)
    assert result.passed, result.failures

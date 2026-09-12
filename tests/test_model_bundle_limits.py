from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from natureai_next.bootstrap import model_bundle_cli as model_bundle


def test_rejects_manifest_with_excessive_file_count(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    entries = [
        {
            "path": f"model/{index}.json",
            "sha256": hashlib.sha256(b"").hexdigest(),
            "size_bytes": 0,
        }
        for index in range(model_bundle._MAX_MANIFEST_FILES + 1)
    ]
    (bundle / "manifest.json").write_text(
        json.dumps({"model_id": "bounded", "version": "1", "files": entries}),
        encoding="utf-8",
    )

    with pytest.raises(model_bundle.ModelBundleError, match="too many files"):
        model_bundle.verify_model_bundle(bundle)


def test_rejects_excessive_manifest_metadata(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    model = bundle / "model.gguf"
    model.write_bytes(b"model")
    (bundle / "manifest.json").write_text(
        json.dumps(
            {
                "model_id": "bounded",
                "version": "1",
                "source": "x" * (model_bundle._MAX_METADATA_TEXT + 1),
                "files": [
                    {
                        "path": "model.gguf",
                        "sha256": hashlib.sha256(b"model").hexdigest(),
                        "size_bytes": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(model_bundle.ModelBundleError, match="source is too long"):
        model_bundle.verify_model_bundle(bundle)


def test_rejects_symlinked_bundle_root(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "manifest.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "bundle"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable on this test platform")

    with pytest.raises(model_bundle.ModelBundleError, match="root must not be a symlink"):
        model_bundle.verify_model_bundle(link)

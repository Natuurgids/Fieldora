from __future__ import annotations

import hashlib
import json
from pathlib import Path

from natureai_next.application.ai_setup import (
    BIOCLIP_CHECKPOINT_FILENAME,
    BIOCLIP_CHECKPOINT_URL,
    BIOCLIP_MODEL_NAME,
    BIOCLIP_REPOSITORY,
    BIOCLIP_RESOURCE_DESCRIPTOR,
    BIOCLIP_REVISION,
)
from natureai_next.application.bioclip_audit import audit_bioclip_resource


def test_official_bioclip_source_is_pinned() -> None:
    assert BIOCLIP_REPOSITORY == "imageomics/bioclip"
    assert BIOCLIP_MODEL_NAME == "ViT-B-16"
    assert BIOCLIP_REVISION != "main"
    assert BIOCLIP_REVISION in BIOCLIP_CHECKPOINT_URL
    assert BIOCLIP_CHECKPOINT_FILENAME in BIOCLIP_CHECKPOINT_URL


def test_bioclip_audit_verifies_descriptor_and_checksum(tmp_path: Path) -> None:
    checkpoint = tmp_path / BIOCLIP_CHECKPOINT_FILENAME
    checkpoint.write_bytes(b"test-checkpoint")
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (tmp_path / BIOCLIP_RESOURCE_DESCRIPTOR).write_text(
        json.dumps(
            {
                "repository": BIOCLIP_REPOSITORY,
                "revision": BIOCLIP_REVISION,
                "model_name": BIOCLIP_MODEL_NAME,
                "checkpoint_filename": BIOCLIP_CHECKPOINT_FILENAME,
                "checkpoint_sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    result = audit_bioclip_resource(checkpoint)
    assert result.ready is True
    assert result.checksum_ok is True


def test_legacy_unpinned_checkpoint_requires_repair(tmp_path: Path) -> None:
    checkpoint = tmp_path / BIOCLIP_CHECKPOINT_FILENAME
    checkpoint.write_bytes(b"legacy")
    result = audit_bioclip_resource(checkpoint)
    assert result.ready is False
    assert "Legacy checkpoint" in result.detail

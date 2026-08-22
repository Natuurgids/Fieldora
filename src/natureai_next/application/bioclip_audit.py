"""BioCLIP/OpenCLIP resource identity and installation diagnostics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from natureai_next.application.ai_setup import (
    BIOCLIP_CHECKPOINT_FILENAME,
    BIOCLIP_MODEL_NAME,
    BIOCLIP_REPOSITORY,
    BIOCLIP_RESOURCE_DESCRIPTOR,
    BIOCLIP_REVISION,
)


@dataclass(frozen=True, slots=True)
class BioCLIPResourceAudit:
    ready: bool
    checkpoint: Path | None
    repository: str
    revision: str
    model_name: str
    checksum_ok: bool | None
    detail: str


def audit_bioclip_resource(checkpoint: Path | None) -> BioCLIPResourceAudit:
    if checkpoint is None or not checkpoint.is_file():
        return BioCLIPResourceAudit(
            False,
            checkpoint,
            BIOCLIP_REPOSITORY,
            BIOCLIP_REVISION,
            BIOCLIP_MODEL_NAME,
            None,
            "Official BioCLIP checkpoint is not installed.",
        )
    descriptor_path = checkpoint.with_name(BIOCLIP_RESOURCE_DESCRIPTOR)
    if not descriptor_path.is_file():
        return BioCLIPResourceAudit(
            False,
            checkpoint,
            BIOCLIP_REPOSITORY,
            BIOCLIP_REVISION,
            BIOCLIP_MODEL_NAME,
            None,
            "Legacy checkpoint found without a pinned BioCLIP resource descriptor; repair is recommended.",
        )
    try:
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        expected = str(descriptor.get("checkpoint_sha256") or "").casefold()
        actual = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        identity_ok = (
            descriptor.get("repository") == BIOCLIP_REPOSITORY
            and descriptor.get("revision") == BIOCLIP_REVISION
            and descriptor.get("model_name") == BIOCLIP_MODEL_NAME
            and descriptor.get("checkpoint_filename") == BIOCLIP_CHECKPOINT_FILENAME
        )
        checksum_ok = bool(expected and actual == expected)
        ready = identity_ok and checksum_ok
        detail = (
            "Pinned official BioCLIP paper model is verified."
            if ready
            else "BioCLIP resource identity or checksum does not match this build; repair is required."
        )
        return BioCLIPResourceAudit(
            ready,
            checkpoint,
            str(descriptor.get("repository") or ""),
            str(descriptor.get("revision") or ""),
            str(descriptor.get("model_name") or ""),
            checksum_ok,
            detail,
        )
    except Exception as exc:
        return BioCLIPResourceAudit(
            False,
            checkpoint,
            BIOCLIP_REPOSITORY,
            BIOCLIP_REVISION,
            BIOCLIP_MODEL_NAME,
            False,
            f"BioCLIP descriptor could not be read: {exc}",
        )

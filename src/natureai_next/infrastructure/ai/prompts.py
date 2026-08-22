"""Versioned local prompt-set manifests with deterministic checksums."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packaging.version import InvalidVersion, Version

from natureai_next.domain.ai import PromptDefinition, PromptSetManifest

SUPPORTED_PROMPT_SCHEMA_VERSION = 1
MAX_PROMPTS = 100_000
MAX_PROMPT_TEXT_LENGTH = 4_096


def canonical_prompt_manifest(manifest: PromptSetManifest) -> bytes:
    payload = {
        "schema_version": manifest.schema_version,
        "identity": manifest.identity,
        "semantic_version": manifest.semantic_version,
        "model_family": manifest.model_family,
        "minimum_application_version": manifest.minimum_application_version,
        "prompts": [
            {
                "label": prompt.label,
                "text": prompt.text,
                "taxon_public_id": prompt.taxon_public_id,
                "broad_group": prompt.broad_group,
            }
            for prompt in manifest.prompts
        ],
    }
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def prompt_set_checksum(manifest: PromptSetManifest) -> str:
    return hashlib.sha256(canonical_prompt_manifest(manifest)).hexdigest()


def validate_prompt_set(
    manifest: PromptSetManifest,
    *,
    application_version: str,
    model_family: str | None = None,
) -> None:
    if manifest.schema_version != SUPPORTED_PROMPT_SCHEMA_VERSION:
        raise ValueError("unsupported prompt-set schema")
    if not manifest.identity.strip():
        raise ValueError("prompt-set identity is required")
    if not manifest.model_family.strip():
        raise ValueError("prompt-set model family is required")
    if model_family is not None and manifest.model_family != model_family:
        raise ValueError("prompt set is incompatible with the selected model family")
    try:
        if Version(application_version) < Version(manifest.minimum_application_version):
            raise ValueError("prompt set requires a newer application version")
        Version(manifest.semantic_version)
    except InvalidVersion as exc:
        raise ValueError("prompt set contains an invalid semantic version") from exc
    if not manifest.prompts:
        raise ValueError("prompt set requires non-empty prompts")
    if len(manifest.prompts) > MAX_PROMPTS:
        raise ValueError("prompt set exceeds the prompt-count limit")
    labels: set[str] = set()
    identities: set[tuple[str | None, str | None, str]] = set()
    for prompt in manifest.prompts:
        label = prompt.label.strip()
        text = prompt.text.strip()
        if not label or not text:
            raise ValueError("prompt set requires non-empty labels and prompt text")
        if len(text) > MAX_PROMPT_TEXT_LENGTH:
            raise ValueError("prompt text exceeds the length limit")
        normalized_label = label.casefold()
        if normalized_label in labels:
            raise ValueError("duplicate prompt label")
        labels.add(normalized_label)
        identity = (prompt.taxon_public_id, prompt.broad_group, text.casefold())
        if identity in identities:
            raise ValueError("duplicate prompt identity")
        identities.add(identity)


def load_prompt_set(path: Path) -> PromptSetManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    prompts = tuple(
        PromptDefinition(
            label=str(item["label"]).strip(),
            text=str(item["text"]).strip(),
            taxon_public_id=(
                None if item.get("taxon_public_id") is None else str(item["taxon_public_id"])
            ),
            broad_group=(None if item.get("broad_group") is None else str(item["broad_group"])),
        )
        for item in data.get("prompts", [])
    )
    manifest = PromptSetManifest(
        schema_version=int(data.get("schema_version", 0)),
        identity=str(data.get("identity", "")).strip(),
        semantic_version=str(data.get("semantic_version", "")).strip(),
        model_family=str(data.get("model_family", "")).strip(),
        minimum_application_version=str(data.get("minimum_application_version", "0.1.0")).strip(),
        prompts=prompts,
    )
    # Structural validation is independent from the running application version.
    validate_prompt_set(manifest, application_version=manifest.minimum_application_version)
    return manifest

"""Administrative CLI for building and validating offline AI resource packages."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next import __version__
from natureai_next.domain.taxonomy import LicenseMetadata
from natureai_next.infrastructure.ai.package import (
    ModelPackageVerifier,
    build_model_package,
)
from natureai_next.infrastructure.ai.prompts import load_prompt_set, validate_prompt_set
from natureai_next.infrastructure.taxonomy.package import (
    Ed25519TaxonomyPackageVerifier,
    build_taxonomy_package,
)


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    value = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(value, Ed25519PrivateKey):
        raise ValueError("an Ed25519 private key is required")
    return value


def _load_trusted_keys(path: Path) -> dict[str, bytes]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not value:
        raise ValueError("trusted-key file must contain a non-empty JSON object")
    result: dict[str, bytes] = {}
    for key_id, encoded in value.items():
        if not isinstance(key_id, str) or not isinstance(encoded, str):
            raise ValueError("trusted-key entries must map string identifiers to base64 strings")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != 32:
            raise ValueError(f"trusted key {key_id!r} must be 32 bytes")
        result[key_id] = raw
    return result


def _json_lines(path: Path) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    if not path.exists():
        return result
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number} must contain a JSON object")
        result.append(value)
    return result


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="natureai-next-resources")
    sub = parser.add_subparsers(dest="command", required=True)

    keygen = sub.add_parser("key-generate", help="generate a local Ed25519 signing key pair")
    keygen.add_argument("--key-id", required=True)
    keygen.add_argument("--private-key", type=Path, required=True)
    keygen.add_argument("--trusted-keys", type=Path, required=True)
    keygen.add_argument("--force", action="store_true")

    model_build = sub.add_parser("model-build", help="build a signed model package")
    model_build.add_argument("--config", type=Path, required=True)
    model_build.add_argument("--private-key", type=Path, required=True)
    model_build.add_argument("--output", type=Path, required=True)

    model_verify = sub.add_parser("model-verify", help="verify a signed model package")
    model_verify.add_argument("package", type=Path)
    model_verify.add_argument("--trusted-keys", type=Path, required=True)

    taxonomy_build = sub.add_parser("taxonomy-build", help="build a signed taxonomy package")
    taxonomy_build.add_argument("--config", type=Path, required=True)
    taxonomy_build.add_argument("--source", type=Path, required=True)
    taxonomy_build.add_argument("--private-key", type=Path, required=True)
    taxonomy_build.add_argument("--output", type=Path, required=True)

    taxonomy_verify = sub.add_parser("taxonomy-verify", help="verify a signed taxonomy package")
    taxonomy_verify.add_argument("package", type=Path)
    taxonomy_verify.add_argument("--trusted-keys", type=Path, required=True)

    prompt_verify = sub.add_parser("prompt-verify", help="validate a prompt-set manifest")
    prompt_verify.add_argument("manifest", type=Path)
    prompt_verify.add_argument("--model-family")

    workspace = sub.add_parser(
        "workspace-init",
        help="create a reproducible local AI resource workspace with absolute paths",
    )
    workspace.add_argument("--root", type=Path, required=True)
    workspace.add_argument("--key-id", default="natureai-local")
    workspace.add_argument("--force", action="store_true")

    return parser


def _key_generate(args: argparse.Namespace) -> dict[str, object]:
    for path in (args.private_key, args.trusted_keys):
        if path.exists() and not args.force:
            raise FileExistsError(f"refusing to overwrite {path}; pass --force explicitly")
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_raw = key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    args.private_key.parent.mkdir(parents=True, exist_ok=True)
    args.private_key.write_bytes(private_pem)
    _write_json(args.trusted_keys, {args.key_id: base64.b64encode(public_raw).decode("ascii")})
    return {
        "key_id": args.key_id,
        "private_key": str(args.private_key),
        "trusted_keys": str(args.trusted_keys),
    }


def _model_build(args: argparse.Namespace) -> dict[str, object]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("model config must contain a JSON object")
    artifact_root = args.config.parent
    artifact_paths = config.pop("artifact_files", None)
    if not isinstance(artifact_paths, dict) or not artifact_paths:
        raise ValueError("model config requires a non-empty artifact_files object")
    artifacts: dict[str, bytes] = {}
    for relative_name, source_name in artifact_paths.items():
        source = (artifact_root / str(source_name)).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        artifacts[str(relative_name)] = source.read_bytes()
    package = build_model_package(
        args.output,
        private_key=_load_private_key(args.private_key),
        manifest=config,
        artifacts=artifacts,
    )
    return {"package": str(package), "artifacts": len(artifacts)}


def _model_verify(args: argparse.Namespace) -> dict[str, object]:
    manifest, payloads, checksum = ModelPackageVerifier(
        _load_trusted_keys(args.trusted_keys)
    ).verify(args.package)
    return {
        "package_id": manifest.package_id,
        "model_identity": manifest.model_identity,
        "semantic_version": manifest.semantic_version,
        "variants": [item.identity for item in manifest.variants],
        "artifacts": sorted(payloads),
        "sha256": checksum,
    }


def _taxonomy_build(args: argparse.Namespace) -> dict[str, object]:
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("taxonomy config must contain a JSON object")
    license_value = config.get("license")
    if not isinstance(license_value, dict):
        raise ValueError("taxonomy config requires license metadata")
    license_metadata = LicenseMetadata(
        name=str(license_value.get("name", "")),
        url=None if license_value.get("url") is None else str(license_value["url"]),
        attribution=str(license_value.get("attribution", "")),
        redistribution_allowed=bool(license_value.get("redistribution_allowed", False)),
    )
    package = build_taxonomy_package(
        args.output,
        private_key=_load_private_key(args.private_key),
        key_id=str(config["key_id"]),
        package_id=str(config["package_id"]),
        source_name=str(config["source_name"]),
        source_version=str(config["source_version"]),
        minimum_app_version=str(config.get("minimum_app_version", __version__)),
        license_metadata=license_metadata,
        taxa=_json_lines(args.source / "taxa.jsonl"),
        names=_json_lines(args.source / "names.jsonl"),
        regions=_json_lines(args.source / "regions.jsonl"),
        attribution_text=None
        if config.get("attribution_text") is None
        else str(config["attribution_text"]),
    )
    return {"package": str(package)}


def _taxonomy_verify(args: argparse.Namespace) -> dict[str, object]:
    package = Ed25519TaxonomyPackageVerifier(_load_trusted_keys(args.trusted_keys)).verify(
        args.package
    )
    return {
        "package_id": package.package_id,
        "source_name": package.source_name,
        "source_version": package.source_version,
        "taxa": len(package.taxa),
        "names": len(package.names),
        "regions": len(package.regions),
        "sha256": package.checksum,
    }


def _prompt_verify(args: argparse.Namespace) -> dict[str, object]:
    manifest = load_prompt_set(args.manifest)
    validate_prompt_set(
        manifest,
        application_version=__version__,
        model_family=args.model_family,
    )
    return {
        "identity": manifest.identity,
        "semantic_version": manifest.semantic_version,
        "model_family": manifest.model_family,
        "prompts": len(manifest.prompts),
    }


def _workspace_init(args: argparse.Namespace) -> dict[str, object]:
    root = args.root.expanduser().resolve()
    files: dict[Path, object] = {
        root / "build" / "model-package.json": {
            "package_id": "natureai-local-bioclip-1",
            "model_identity": "bioclip",
            "semantic_version": "1.0.0",
            "model_family": "bioclip",
            "upstream_source": "REPLACE_WITH_UPSTREAM_SOURCE_AND_CHECKSUM",
            "license_name": "REPLACE_WITH_UPSTREAM_LICENSE",
            "attribution_text": "REPLACE_WITH_REQUIRED_ATTRIBUTION",
            "minimum_application_version": __version__,
            "signing_key_id": args.key_id,
            "artifact_files": {
                "model.pt": str(root / "source" / "model" / "bioclip-checkpoint.pt")
            },
            "variants": [
                {
                    "identity": "cuda-fp16",
                    "runtime": "torch",
                    "precision": "fp16",
                    "providers": ["cuda"],
                    "preprocessing_identity": "openclip-model-transform-v1",
                    "embedding_dimension": 512,
                    "input_size": 224,
                    "normalized_output": True,
                    "artifact_path": "model.pt",
                }
            ],
        },
        root / "build" / "taxonomy-package.json": {
            "key_id": args.key_id,
            "package_id": "natureai-local-europe-taxonomy-1",
            "source_name": "REPLACE_WITH_TAXONOMY_SOURCE",
            "source_version": "REPLACE_WITH_SOURCE_VERSION",
            "minimum_app_version": __version__,
            "license": {
                "name": "REPLACE_WITH_SOURCE_LICENSE",
                "url": None,
                "attribution": "REPLACE_WITH_REQUIRED_ATTRIBUTION",
                "redistribution_allowed": False,
            },
            "attribution_text": "REPLACE_WITH_REQUIRED_ATTRIBUTION",
        },
        root / "prompts" / "prompt-set.json": {
            "schema_version": 1,
            "identity": "natureai-local-europe-prompts",
            "semantic_version": "1.0.0",
            "model_family": "bioclip",
            "minimum_application_version": __version__,
            "prompts": [],
        },
    }
    created: list[str] = []
    for directory in (
        root / "signing",
        root / "source" / "model",
        root / "source" / "taxonomy",
        root / "build",
        root / "packages",
        root / "prompts",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for path, value in files.items():
        if path.exists() and not args.force:
            raise FileExistsError(f"refusing to overwrite {path}; pass --force explicitly")
        _write_json(path, value)
        created.append(str(path))
    for name in ("taxa.jsonl", "names.jsonl", "regions.jsonl"):
        path = root / "source" / "taxonomy" / name
        if path.exists() and not args.force:
            raise FileExistsError(f"refusing to overwrite {path}; pass --force explicitly")
        path.write_text("", encoding="utf-8")
        created.append(str(path))
    commands = root / "BUILD_COMMANDS.ps1"
    if commands.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite {commands}; pass --force explicitly")
    executable = "natureai-next-resources"
    commands.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f'$root = "{root}"',
                f'$privateKey = "{root / "signing" / (args.key_id + "-private.pem")}"',
                f'$trustedKeys = "{root / "signing" / (args.key_id + "-trusted.json")}"',
                f'& {executable} model-build --config "{root / "build" / "model-package.json"}" --private-key $privateKey --output "{root / "packages" / "bioclip-model.zip"}"',
                f'& {executable} model-verify "{root / "packages" / "bioclip-model.zip"}" --trusted-keys $trustedKeys',
                f'& {executable} taxonomy-build --config "{root / "build" / "taxonomy-package.json"}" --source "{root / "source" / "taxonomy"}" --private-key $privateKey --output "{root / "packages" / "taxonomy.zip"}"',
                f'& {executable} taxonomy-verify "{root / "packages" / "taxonomy.zip"}" --trusted-keys $trustedKeys',
                f'& {executable} prompt-verify "{root / "prompts" / "prompt-set.json"}" --model-family bioclip',
                "",
            ]
        ),
        encoding="utf-8",
    )
    created.append(str(commands))
    return {
        "root": str(root),
        "created": created,
        "checkpoint_path": str(root / "source" / "model" / "bioclip-checkpoint.pt"),
    }


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers: dict[str, Any] = {
        "key-generate": _key_generate,
        "model-build": _model_build,
        "model-verify": _model_verify,
        "taxonomy-build": _taxonomy_build,
        "taxonomy-verify": _taxonomy_verify,
        "prompt-verify": _prompt_verify,
        "workspace-init": _workspace_init,
    }
    try:
        result = handlers[args.command](args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

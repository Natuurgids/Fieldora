"""Guided, local-first BioCLIP resource setup without hand-edited manifests."""

from __future__ import annotations

import base64
import csv
import hashlib
import http.client
import json
import shutil
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from natureai_next import __version__
from natureai_next.application.ai_resources import LocalAIResourceService
from natureai_next.domain.taxonomy import LicenseMetadata
from natureai_next.infrastructure.ai.tree_of_life_resources import (
    bootstrap_tree_of_life_resources,
)
from natureai_next.ports.model_packages import ModelPackageBuildRequest
from natureai_next.ports.taxonomy_packages import TaxonomyPackageBuildRequest

BIOCLIP_REPOSITORY = "imageomics/bioclip"
# Pin the original paper model. The upstream ``main`` branch can change while
# retaining the same filename, which previously made Aperture installations
# non-reproducible and could pair a newer checkpoint with the older runtime
# declaration.
BIOCLIP_REVISION = "1f135cb2599b3c076efaa7a101f47b40e068878c"
BIOCLIP_MODEL_NAME = "ViT-B-16"
BIOCLIP_CHECKPOINT_FILENAME = "open_clip_pytorch_model.bin"
BIOCLIP_CHECKPOINT_URL = (
    f"https://huggingface.co/{BIOCLIP_REPOSITORY}/resolve/{BIOCLIP_REVISION}/"
    f"{BIOCLIP_CHECKPOINT_FILENAME}?download=true"
)
BIOCLIP_RESOURCE_DESCRIPTOR = "bioclip_resource.json"

BIOCLIP_DEFAULT_PROMPT_IDENTITY = "imageomics-bioclip-tree-of-life-prompts"
BIOCLIP_DEFAULT_PROMPT_VERSION = "1.0.0"
BIOCLIP_DEFAULT_PROMPTS = (
    {
        "label": "scientific-name",
        "text": "a photo of a {scientific_name}",
        "broad_group": "taxonomy",
    },
    {
        "label": "species-scientific-name",
        "text": "a photograph of the species {scientific_name}",
        "broad_group": "taxonomy-species",
    },
    {
        "label": "common-name",
        "text": "a photo of a {common_name}",
        "broad_group": "taxonomy-common-name",
    },
    {
        "label": "wildlife-scientific-name",
        "text": "a wildlife photograph of a {scientific_name}",
        "broad_group": "taxonomy-wildlife",
    },
)

BIOCLIP_ATTRIBUTION = (
    "BioCLIP by Samuel Stevens et al., Imageomics Institute; trained with "
    "TreeOfLife-10M and OpenCLIP. DOI: 10.57967/hf/1511."
)


@dataclass(frozen=True, slots=True)
class BioCLIPSetupRequest:
    workspace: Path
    checkpoint: Path | None = None
    model_folder: Path | None = None
    download_official_checkpoint: bool = False
    taxonomy_csv: Path | None = None
    key_id: str = "natureai-local"


@dataclass(frozen=True, slots=True)
class BioCLIPSetupResult:
    model_package: Path
    model_public_id: str
    trusted_keys: Path
    taxonomy_package: Path | None = None
    taxonomy_source_public_id: str | None = None
    prompt_manifest: Path | None = None
    prompt_public_id: str | None = None
    embedding_counts: tuple[int, int] | None = None
    tree_of_life_ready: bool = False
    tree_of_life_taxa_count: int | None = None
    tree_of_life_resource_note: str | None = None


class BioCLIPQuickSetupService:
    """Builds, signs, installs and activates local BioCLIP resources."""

    def __init__(self, resources: LocalAIResourceService) -> None:
        self._resources = resources

    def run(
        self,
        request: BioCLIPSetupRequest,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> BioCLIPSetupResult:
        report = progress or (lambda _current, _total, _message: None)
        is_cancelled = cancelled or (lambda: False)
        root = request.workspace.expanduser().resolve()
        signing = root / "signing"
        source_model = root / "source" / "model"
        packages = root / "packages"
        prompts = root / "prompts"
        for directory in (signing, source_model, packages, prompts):
            directory.mkdir(parents=True, exist_ok=True)

        private_key_path = signing / f"{request.key_id}-private.pem"
        trusted_keys_path = signing / f"{request.key_id}-trusted.json"
        report(1, 7, "Preparing local signing identity…")
        private_key = self._ensure_signing_identity(
            request.key_id, private_key_path, trusted_keys_path
        )

        checkpoint = request.checkpoint
        if request.model_folder is not None:
            folder = request.model_folder.expanduser().resolve()
            if not folder.is_dir():
                raise FileNotFoundError(f"BioCLIP model folder does not exist: {folder}")
            checkpoint = folder / BIOCLIP_CHECKPOINT_FILENAME
            if not checkpoint.is_file():
                candidates = tuple(folder.rglob(BIOCLIP_CHECKPOINT_FILENAME))
                if len(candidates) == 1:
                    checkpoint = candidates[0]
                else:
                    raise FileNotFoundError(
                        f"The selected folder does not contain {BIOCLIP_CHECKPOINT_FILENAME}. "
                        "Select the complete imageomics/bioclip repository folder."
                    )
            config = checkpoint.parent / "open_clip_config.json"
            descriptor = checkpoint.parent / BIOCLIP_RESOURCE_DESCRIPTOR
            if not config.is_file() and not descriptor.is_file():
                report(
                    2,
                    7,
                    "Using the local BioCLIP checkpoint; repository configuration was not present.",
                )
            else:
                report(2, 7, "Validated the local BioCLIP model folder.")
        if request.download_official_checkpoint:
            checkpoint = source_model / BIOCLIP_CHECKPOINT_FILENAME
            if not checkpoint.is_file():
                report(2, 7, "Downloading the official BioCLIP checkpoint…")
                self._download_official_checkpoint(
                    checkpoint, progress=report, cancelled=is_cancelled
                )
        if checkpoint is None or not checkpoint.is_file():
            raise FileNotFoundError(
                "Select a complete BioCLIP folder, choose a checkpoint, or enable official download."
            )

        report(3, 7, "Building and signing the BioCLIP model package…")
        checksum = self._sha256_file(checkpoint)
        # Package identity and install version are content-addressed. A prior
        # setup may have installed another valid BioCLIP checkpoint; reusing a
        # fixed identity for different bytes correctly triggers the package
        # integrity guard. Content addressing makes repeated setup idempotent
        # while allowing a changed checkpoint to install as a new version.
        model_token = checksum[:16]
        model_package_id = f"natureai-local-bioclip-{model_token}"
        model_version = f"1.0.0+sha.{model_token}"
        model_package = packages / f"{model_package_id}.zip"
        self._resources.build_model_package(
            ModelPackageBuildRequest(
                package_path=model_package,
                private_key=private_key,
                manifest={
                    "package_id": model_package_id,
                    "model_identity": f"{BIOCLIP_REPOSITORY}@{BIOCLIP_REVISION}",
                    "semantic_version": model_version,
                    "model_family": "bioclip",
                    "upstream_source": (
                        f"https://huggingface.co/{BIOCLIP_REPOSITORY}/tree/{BIOCLIP_REVISION} ; "
                        f"DOI 10.57967/hf/1511 ; SHA256 {checksum}"
                    ),
                    "license_name": "MIT",
                    "attribution_text": BIOCLIP_ATTRIBUTION,
                    "minimum_application_version": __version__,
                    "signing_key_id": request.key_id,
                    "variants": [
                        {
                            "identity": "cpu-fp32",
                            "runtime": "torch",
                            "precision": "fp32",
                            "providers": ["cpu"],
                            "preprocessing_identity": "imageomics-bioclip-openclip-vit-b-16-v1",
                            "embedding_dimension": 512,
                            "input_size": 224,
                            "normalized_output": True,
                            "artifact_path": BIOCLIP_CHECKPOINT_FILENAME,
                        },
                        {
                            "identity": "cuda-fp16",
                            "runtime": "torch",
                            "precision": "fp16",
                            "providers": ["cuda"],
                            "preprocessing_identity": "imageomics-bioclip-openclip-vit-b-16-v1",
                            "embedding_dimension": 512,
                            "input_size": 224,
                            "normalized_output": True,
                            "artifact_path": BIOCLIP_CHECKPOINT_FILENAME,
                        },
                    ],
                },
                artifacts={
                    BIOCLIP_CHECKPOINT_FILENAME: checkpoint.read_bytes(),
                    BIOCLIP_RESOURCE_DESCRIPTOR: (
                        json.dumps(
                            {
                                "schema_version": 1,
                                "repository": BIOCLIP_REPOSITORY,
                                "revision": BIOCLIP_REVISION,
                                "model_name": BIOCLIP_MODEL_NAME,
                                "checkpoint_filename": BIOCLIP_CHECKPOINT_FILENAME,
                                "checkpoint_sha256": checksum,
                                "embedding_dimension": 512,
                                "input_size": 224,
                                "runtime": "open_clip",
                                "offline": True,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8"),
                },
            )
        )
        report(4, 7, "Verifying, installing and activating the model…")
        model_public_id = self._resources.install_model(model_package, trusted_keys_path)

        taxonomy_package: Path | None = None
        taxonomy_source_id: str | None = None
        prompt_manifest: Path | None = None
        prompt_public_id: str | None = None
        embedding_counts: tuple[int, int] | None = None
        if request.taxonomy_csv is not None:
            report(5, 7, "Converting the taxonomy CSV into a signed package…")
            taxa, names, prompt_rows = self._load_taxonomy_csv(request.taxonomy_csv)
            taxonomy_checksum = self._sha256_file(request.taxonomy_csv)
            taxonomy_token = taxonomy_checksum[:16]
            taxonomy_package_id = f"natureai-local-taxonomy-{taxonomy_token}"
            taxonomy_version = f"1.0.0+sha.{taxonomy_token}"
            taxonomy_package = packages / f"{taxonomy_package_id}.zip"
            self._resources.build_taxonomy_package(
                TaxonomyPackageBuildRequest(
                    package_path=taxonomy_package,
                    private_key=private_key,
                    key_id=request.key_id,
                    package_id=taxonomy_package_id,
                    source_name="natureai-local-taxonomy",
                    source_version=taxonomy_version,
                    minimum_app_version=__version__,
                    license_metadata=LicenseMetadata(
                        "User supplied local taxonomy",
                        None,
                        "Locally supplied by the NatureAI user.",
                        False,
                    ),
                    taxa=taxa,
                    names=names,
                    regions=(),
                    attribution_text="Locally supplied by the NatureAI user.",
                )
            )
            taxonomy_source_id = self._resources.install_taxonomy(
                taxonomy_package, trusted_keys_path
            )
            report(6, 7, "Creating and activating taxonomy prompts…")
            prompt_identity = f"natureai-local-taxonomy-prompts-{taxonomy_token}"
            prompt_manifest = prompts / f"{prompt_identity}.json"
            prompt_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "identity": prompt_identity,
                        "semantic_version": taxonomy_version,
                        "model_family": "bioclip",
                        "minimum_application_version": __version__,
                        "prompts": prompt_rows,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            prompt_public_id = self._resources.install_prompt_set(
                prompt_manifest, model_family="bioclip"
            )
            report(7, 7, "Building taxonomy text embeddings…")
            embedding_counts = self._resources.build_taxonomy_embeddings()
        else:
            # The original NatureAI engine is BioCLIP plus pybioclip's matching
            # TreeOfLife-10M classifier resources.  The prompt-set record is kept
            # for Aperture provenance and compatibility, but the labels and text
            # embeddings are owned by pybioclip and do not come from GBIF or CSV.
            report(5, 8, "Installing and activating the NatureAI Tree of Life profile…")
            prompt_manifest, prompt_public_id, _ = self.install_default_prompt_set(
                root, build_aperture_embeddings=False
            )
            report(6, 8, "Loading the original BioCLIP TreeOfLifeClassifier…")
            tree_of_life = bootstrap_tree_of_life_resources(device="cpu")
            report(8, 8, "NatureAI BioCLIP and Tree-of-Life resources are active and ready.")

        return BioCLIPSetupResult(
            model_package=model_package,
            model_public_id=model_public_id,
            trusted_keys=trusted_keys_path,
            taxonomy_package=taxonomy_package,
            taxonomy_source_public_id=taxonomy_source_id,
            prompt_manifest=prompt_manifest,
            prompt_public_id=prompt_public_id,
            embedding_counts=embedding_counts,
            tree_of_life_ready=(tree_of_life.ready if request.taxonomy_csv is None else False),
            tree_of_life_taxa_count=(
                tree_of_life.taxa_count if request.taxonomy_csv is None else None
            ),
            tree_of_life_resource_note=(
                tree_of_life.note if request.taxonomy_csv is None else None
            ),
        )

    def install_default_prompt_set(
        self, workspace: Path, *, build_aperture_embeddings: bool = True
    ) -> tuple[Path, str, tuple[int, int] | None]:
        """Install the built-in BioCLIP taxonomy prompt profile and build embeddings.

        The legacy NatureAI TreeOfLifeClassifier supplied its own text prompt
        profile. Aperture's component registry requires an explicit prompt-set
        record, so this method registers the equivalent built-in profile and
        materializes embeddings from the active taxonomy release.
        """
        root = workspace.expanduser().resolve()
        prompts = root / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        manifest = prompts / f"{BIOCLIP_DEFAULT_PROMPT_IDENTITY}.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "identity": BIOCLIP_DEFAULT_PROMPT_IDENTITY,
                    "semantic_version": BIOCLIP_DEFAULT_PROMPT_VERSION,
                    "model_family": "bioclip",
                    "minimum_application_version": __version__,
                    "prompts": list(BIOCLIP_DEFAULT_PROMPTS),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        public_id = self._resources.install_prompt_set(manifest, model_family="bioclip")
        if not build_aperture_embeddings:
            return manifest, public_id, None
        try:
            counts = self._resources.build_taxonomy_embeddings()
        except RuntimeError as exc:
            message = str(exc)
            if "No active model variant" in message or "No active prompt" in message:
                counts = None
            else:
                raise
        return manifest, public_id, counts

    @staticmethod
    def _ensure_signing_identity(
        key_id: str, private_path: Path, trusted_path: Path
    ) -> Ed25519PrivateKey:
        if private_path.is_file() and trusted_path.is_file():
            return serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        if private_path.exists() or trusted_path.exists():
            raise RuntimeError(
                "The signing identity is incomplete; restore or remove both key files."
            )
        key = Ed25519PrivateKey.generate()
        private_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        public_raw = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        trusted_path.write_text(
            json.dumps({key_id: base64.b64encode(public_raw).decode("ascii")}, indent=2) + "\n",
            encoding="utf-8",
        )
        return key

    @staticmethod
    def _download_official_checkpoint(
        destination: Path,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        """Fetch the official BioCLIP checkpoint through the Hugging Face cache.

        ``hf_hub_download`` is deliberately preferred over a raw ``urlopen``
        transfer.  It uses resumable cache files, understands redirects/Xet, and
        can continue after an application or network interruption.  The raw HTTP
        downloader remains as an offline-compatible fallback for minimal installs.
        """
        report = progress or (lambda _current, _total, _message: None)
        is_cancelled = cancelled or (lambda: False)
        if is_cancelled():
            raise InterruptedError("BioCLIP download cancelled before it started.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            from huggingface_hub import hf_hub_download

            report(
                0,
                0,
                "Downloading complete supported BioCLIP model through the resumable Hugging Face cache…",
            )
            cached = Path(
                hf_hub_download(
                    repo_id=BIOCLIP_REPOSITORY,
                    filename=BIOCLIP_CHECKPOINT_FILENAME,
                    revision=BIOCLIP_REVISION,
                    local_dir=destination.parent,
                )
            )
            if is_cancelled():
                raise InterruptedError("BioCLIP download cancelled; cached bytes were retained.")
            if cached.resolve() != destination.resolve():
                shutil.copy2(cached, destination)
            if destination.stat().st_size < 100_000_000:
                raise RuntimeError("The downloaded BioCLIP checkpoint is unexpectedly small.")
            report(
                destination.stat().st_size,
                destination.stat().st_size,
                "BioCLIP model download completed.",
            )
            return
        except InterruptedError:
            raise
        except Exception as hub_error:
            report(
                0,
                0,
                f"Hugging Face cache download was unavailable ({hub_error}); trying direct resumable transfer…",
            )
            BioCLIPQuickSetupService._download(
                BIOCLIP_CHECKPOINT_URL,
                destination,
                progress=report,
                cancelled=is_cancelled,
                label="complete supported BioCLIP model",
            )

    @staticmethod
    def _download(
        url: str,
        destination: Path,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
        label: str = "BioCLIP checkpoint",
    ) -> None:
        """Download a large file with persistent range resume and byte progress."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = progress or (lambda _current, _total, _message: None)
        is_cancelled = cancelled or (lambda: False)
        partial = destination.with_suffix(destination.suffix + ".part")
        transient = (
            urllib.error.URLError,
            ssl.SSLError,
            ConnectionResetError,
            TimeoutError,
            EOFError,
            http.client.IncompleteRead,
            http.client.RemoteDisconnected,
            RuntimeError,
        )
        # Retry quickly. Long server lockout delays make the UI appear blocked and
        # do not improve resumability; the partial file is retained for an
        # immediate user-triggered retry.
        delays = (0, 1, 2, 4, 8, 10)
        last_error: Exception | None = None
        for attempt, delay in enumerate(delays, 1):
            if delay:
                time.sleep(delay)
            if is_cancelled():
                raise InterruptedError(
                    f"{label} download cancelled; the partial file was kept for resume."
                )
            offset = partial.stat().st_size if partial.is_file() else 0
            headers = {
                "User-Agent": f"Aperture/{__version__} BioCLIP downloader",
                "Accept": "application/octet-stream",
                "Accept-Encoding": "identity",
                "Connection": "close",
            }
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    status = getattr(response, "status", response.getcode())
                    if offset and status != 206:
                        # The remote ignored Range; restart once from zero rather than
                        # appending duplicate bytes to a valid partial file.
                        partial.unlink(missing_ok=True)
                        offset = 0
                    mode = "ab" if offset and status == 206 else "wb"
                    remaining = int(response.headers.get("Content-Length") or 0)
                    total = offset + remaining if remaining else 0
                    report(
                        offset,
                        total,
                        f"Downloading {label}… {offset / (1024 * 1024):,.1f} MiB received",
                    )
                    with partial.open(mode) as target:
                        last_report = time.monotonic()
                        while True:
                            if is_cancelled():
                                raise InterruptedError(
                                    f"{label} download cancelled; the partial file was kept for resume."
                                )
                            block = response.read(8 * 1024 * 1024)
                            if not block:
                                break
                            target.write(block)
                            current = target.tell()
                            now = time.monotonic()
                            if now - last_report >= 0.25 or (total and current >= total):
                                report(
                                    current,
                                    total,
                                    f"Downloading {label}… {current / (1024 * 1024):,.1f} MiB received",
                                )
                                last_report = now
                        target.flush()
                if partial.stat().st_size < 100_000_000:
                    raise RuntimeError(f"Downloaded {label} is unexpectedly small.")
                partial.replace(destination)
                return
            except transient as exc:
                last_error = exc
                if attempt == len(delays):
                    break
        raise RuntimeError(
            f"{label} download was interrupted after "
            f"{len(delays)} attempts. Aperture kept {partial} and will resume from "
            "the downloaded byte position on Retry. You can also select a local checkpoint. "
            f"Last error: {last_error}"
        ) from last_error

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _load_taxonomy_csv(
        path: Path,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
        if not path.is_file():
            raise FileNotFoundError(path)
        taxa: list[dict[str, object]] = []
        names: list[dict[str, object]] = []
        prompts: list[dict[str, object]] = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"scientific_name"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("Taxonomy CSV requires a scientific_name column.")
            for index, row in enumerate(reader, 1):
                scientific = (row.get("scientific_name") or "").strip()
                if not scientific:
                    continue
                source_id = (row.get("source_taxon_id") or f"local-{index}").strip()
                common = (row.get("common_name") or "").strip()
                rank = (row.get("rank") or "species").strip()
                taxa.append(
                    {
                        "source_taxon_id": source_id,
                        "scientific_name": scientific,
                        "rank": rank,
                        "status": "accepted",
                        "parent_source_taxon_id": None,
                        "accepted_source_taxon_id": None,
                        "authorship": None,
                        "kingdom": (row.get("kingdom") or None),
                        "major_group": (row.get("major_group") or None),
                        "extinct": False,
                    }
                )
                if common:
                    names.append(
                        {
                            "source_taxon_id": source_id,
                            "name": common,
                            "name_type": "vernacular",
                            "source": "local-csv",
                            "language_tag": (row.get("language_tag") or "en"),
                            "region_code": (row.get("region_code") or None),
                            "preferred": True,
                        }
                    )
                label = common or scientific
                prompts.append(
                    {
                        "label": f"{label} [{source_id}]",
                        "text": f"a wildlife photograph of {common + ', ' if common else ''}{scientific}",
                        "taxon_public_id": None,
                        "broad_group": (row.get("major_group") or "organism"),
                    }
                )
        if not taxa:
            raise ValueError("Taxonomy CSV contains no usable records.")
        # taxon_public_id is resolved after package installation by the embedding label source;
        # broad-group prompts make the manifest valid while installed taxonomy names supply taxa.
        return taxa, names, prompts

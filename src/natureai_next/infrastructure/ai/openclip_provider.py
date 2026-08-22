"""Optional OpenCLIP/BioCLIP execution adapter with owned tokenizer lifecycle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from natureai_next.domain.ai import EmbeddingVector, ProviderDiagnostics


@dataclass(slots=True)
class OpenClipModelHandle:
    model: object
    tokenizer: object
    device: str
    precision: str
    model_name: str
    image_transform: object


class OpenClipExecutionProvider:
    """Loads local OpenCLIP-compatible checkpoints without network access."""

    identity = "openclip-local-v1"

    def __init__(self, model_name: str = "ViT-B-16") -> None:
        self._model_name = model_name

    def diagnostics(self) -> ProviderDiagnostics:
        try:
            import open_clip
            import torch

            available = True
            detail = f"open_clip={getattr(open_clip, '__version__', 'unknown')}"
            cuda = bool(torch.cuda.is_available())
            return ProviderDiagnostics(
                provider=self.identity,
                available=available,
                torch_version=str(torch.__version__),
                cuda_runtime=str(torch.version.cuda) if torch.version.cuda else None,
                device_name=torch.cuda.get_device_name(0) if cuda else None,
                compute_capability=".".join(map(str, torch.cuda.get_device_capability(0)))
                if cuda
                else None,
                total_memory_bytes=int(torch.cuda.get_device_properties(0).total_memory)
                if cuda
                else None,
                detail=detail,
            )
        except Exception as exc:
            return ProviderDiagnostics(self.identity, False, None, None, None, None, None, str(exc))

    def load(self, artifact_path: Path, *, device: str, precision: str) -> OpenClipModelHandle:
        if not artifact_path.is_file():
            raise FileNotFoundError(artifact_path)
        model_name = self._model_name
        descriptor_path = artifact_path.with_name("bioclip_resource.json")
        if descriptor_path.is_file():
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            declared = str(descriptor.get("model_name") or "").strip()
            if declared:
                model_name = declared
            expected = str(descriptor.get("checkpoint_sha256") or "").casefold()
            if expected:
                digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                if digest != expected:
                    raise RuntimeError(
                        "The installed BioCLIP checkpoint failed integrity verification. "
                        "Repair or reinstall the BioCLIP component."
                    )
            if model_name != "ViT-B-16":
                raise RuntimeError(
                    f"Unsupported BioCLIP OpenCLIP architecture: {model_name}. "
                    "This Aperture build supports the official ViT-B-16 resource."
                )
        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise RuntimeError("OpenCLIP runtime is not installed") from exc
        model, _, image_transform = open_clip.create_model_and_transforms(
            model_name, pretrained=None
        )
        state = torch.load(artifact_path, map_location="cpu", weights_only=True)
        if isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]
        model.load_state_dict(state, strict=True)
        model.eval().to(device)
        if precision == "fp16" and device == "cuda":
            model.half()
        tokenizer = open_clip.get_tokenizer(model_name)
        return OpenClipModelHandle(model, tokenizer, device, precision, model_name, image_transform)

    def embed_images(self, model: object, images: Sequence[object]) -> tuple[EmbeddingVector, ...]:
        handle = self._require_handle(model)
        import torch

        if not images:
            return ()
        tensors = [
            image if hasattr(image, "shape") else handle.image_transform(image) for image in images
        ]
        batch = torch.stack(tensors).to(handle.device)
        if handle.precision == "fp16" and handle.device == "cuda":
            batch = batch.half()
        with torch.inference_mode():
            output = handle.model.encode_image(batch)
            output = output / output.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return tuple(
            EmbeddingVector(tuple(float(v) for v in row.float().cpu().tolist())) for row in output
        )

    def embed_text(self, model: object, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        handle = self._require_handle(model)
        import torch

        if not texts:
            return ()
        tokens = handle.tokenizer(list(texts)).to(handle.device)
        with torch.inference_mode():
            output = handle.model.encode_text(tokens)
            output = output / output.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        return tuple(
            EmbeddingVector(tuple(float(v) for v in row.float().cpu().tolist())) for row in output
        )

    def unload(self, model: object) -> None:
        handle = self._require_handle(model)
        handle.model.to("cpu")
        self.clear_device_cache()

    def clear_device_cache(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            return

    @staticmethod
    def _require_handle(model: object) -> OpenClipModelHandle:
        if not isinstance(model, OpenClipModelHandle):
            raise TypeError("OpenClipModelHandle is required")
        return model

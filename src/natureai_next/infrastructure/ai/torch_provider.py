"""Optional Torch execution adapter with explicit runtime diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from natureai_next.domain.ai import EmbeddingVector, ProviderDiagnostics


class TorchExecutionProvider:
    @property
    def identity(self) -> str:
        return "torch"

    def _torch(self):
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("Torch is not installed; install the ai dependency group") from exc
        return torch

    def diagnostics(self) -> ProviderDiagnostics:
        try:
            torch = self._torch()
        except RuntimeError as exc:
            return ProviderDiagnostics("torch", False, None, None, None, None, None, str(exc))
        cuda = bool(torch.cuda.is_available())
        device_name = torch.cuda.get_device_name(0) if cuda else None
        capability = ".".join(str(x) for x in torch.cuda.get_device_capability(0)) if cuda else None
        memory = int(torch.cuda.get_device_properties(0).total_memory) if cuda else None
        return ProviderDiagnostics(
            "torch",
            True,
            str(torch.__version__),
            str(torch.version.cuda) if torch.version.cuda else None,
            device_name,
            capability,
            memory,
        )

    def load(self, artifact_path: Path, *, device: str, precision: str) -> object:
        torch = self._torch()
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is not available")
        model = torch.jit.load(str(artifact_path), map_location=device)
        model.eval()
        if precision == "fp16":
            model.half()
        else:
            model.float()
        return model

    def embed_images(self, model: object, images: Sequence[object]) -> tuple[EmbeddingVector, ...]:
        torch = self._torch()
        if not images:
            return ()
        tensors = []
        for image in images:
            raw = torch.ByteTensor(torch.ByteStorage.from_buffer(image.tobytes()))
            tensor = raw.view(image.height, image.width, 3).permute(2, 0, 1).float().div_(255.0)
            tensors.append(tensor)
        batch = torch.stack(tensors)
        device = next(model.parameters()).device
        batch = batch.to(device=device, dtype=next(model.parameters()).dtype)
        with torch.inference_mode():
            output = model.encode_image(batch) if hasattr(model, "encode_image") else model(batch)
            output = torch.nn.functional.normalize(output.float(), dim=-1)
        return tuple(EmbeddingVector(tuple(float(v) for v in row.cpu().tolist())) for row in output)

    def embed_text(self, model: object, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        if not hasattr(model, "encode_texts"):
            raise RuntimeError("loaded Torch model does not expose encode_texts")
        torch = self._torch()
        with torch.inference_mode():
            output = torch.nn.functional.normalize(model.encode_texts(list(texts)).float(), dim=-1)
        return tuple(EmbeddingVector(tuple(float(v) for v in row.cpu().tolist())) for row in output)

    def unload(self, model: object) -> None:
        del model
        self.clear_device_cache()

    def clear_device_cache(self) -> None:
        try:
            torch = self._torch()
        except RuntimeError:
            return
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

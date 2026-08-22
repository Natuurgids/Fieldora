"""Optional upstream model adapters installed through the Models workspace."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from natureai_next.domain.enrichment import CanonicalCandidate, CanonicalShape
from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    CapabilityRequest,
    CapabilityResult,
    InputKind,
    ParameterDefinition,
)


class BirdNETCapability:
    descriptor = CapabilityDescriptor(
        capability_id="aperture.birdnet",
        display_name="BirdNET Sound Identification",
        version="2.4.0",
        inputs=frozenset({InputKind.SOUND, InputKind.VIDEO}),
        outputs=frozenset(
            {CanonicalShape.TIME_SEGMENT.value, CanonicalShape.TAXONOMY_CANDIDATE.value}
        ),
        parameters=(
            ParameterDefinition(
                "minimum_confidence", "float", default=0.25, minimum=0.0, maximum=1.0
            ),
            ParameterDefinition("threads", "integer", default=4, minimum=1, maximum=32),
        ),
        offline=True,
    )

    def __init__(self) -> None:
        self._artifact_root: Path | None = None
        self._dependency_root: Path | None = None

    def configure_runtime(self, cache_root: Path, *, dependency_root: Path | None = None) -> None:
        self._artifact_root = cache_root
        self._dependency_root = dependency_root
        cache_root.mkdir(parents=True, exist_ok=True)

    def health_check(self) -> str:
        return self.health_check_with_context(cancellation=None, progress=None)

    def health_check_with_context(self, *, cancellation=None, progress=None) -> str:
        result = _run_worker(
            "birdnet-health",
            {},
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
            cancellation=cancellation,
            progress=progress,
            timeout_seconds=20 * 60,
        )
        return str(result["detail"])

    def artifact_paths(self) -> tuple[Path, ...]:
        paths = []
        if self._dependency_root is not None:
            package = self._dependency_root / "birdnet_analyzer"
            paths.extend((package / "checkpoints", package / "labels"))
        if self._artifact_root is not None:
            paths.append(self._artifact_root)
        return tuple(paths)

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        return self.execute_with_context(
            request, cancellation=_NoCancellation(), progress=lambda *_args: None
        )

    def execute_with_context(self, request, *, cancellation, progress) -> CapabilityResult:
        if request.input_kind not in self.descriptor.inputs or request.input_path is None:
            raise ValueError("BirdNET requires a sound or video input_path")
        source = request.input_path
        if not source.is_file():
            raise FileNotFoundError(source)
        threshold = float(request.parameters.get("minimum_confidence", 0.25))
        threads = int(request.parameters.get("threads", 4))
        progress(1, 3, "Running BirdNET in its isolated model process")
        result = _run_worker(
            "birdnet-run",
            {
                "source": str(source),
                "input_kind": request.input_kind.value,
                "minimum_confidence": threshold,
                "threads": threads,
            },
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
            cancellation=cancellation,
        )
        cancellation.raise_if_requested()
        progress(2, 3, "Normalizing BirdNET detections")
        candidates = _birdnet_candidates_from_rows(result.get("rows") or ())
        if not candidates:
            raise RuntimeError("BirdNET returned no detections at the selected threshold")
        return CapabilityResult(
            capability_id=self.descriptor.capability_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=candidates,
            source_name="BirdNET GLOBAL",
            source_version="2.4",
            attribution="BirdNET, K. Lisa Yang Center for Conservation Bioacoustics",
            licence="CC BY-NC-SA 4.0 model; MIT source",
            diagnostics={"detection_count": len(candidates), "minimum_confidence": threshold},
        )

    def release(self) -> None:
        return None


class WildlifeVideoCapability:
    descriptor = CapabilityDescriptor(
        capability_id="aperture.wildlife-video",
        display_name="Wildlife Video Review",
        version="5.0.5",
        inputs=frozenset({InputKind.PHOTO, InputKind.VIDEO}),
        outputs=frozenset(
            {
                CanonicalShape.TAXONOMY_CANDIDATE.value,
                CanonicalShape.BOUNDING_BOX.value,
            }
        ),
        parameters=(
            ParameterDefinition(
                "sample_interval_seconds", "float", default=2.0, minimum=0.25, maximum=60.0
            ),
            ParameterDefinition(
                "minimum_confidence", "float", default=0.2, minimum=0.0, maximum=1.0
            ),
            ParameterDefinition("batch_size", "integer", default=4, minimum=1, maximum=32),
        ),
        offline=True,
    )

    def __init__(self) -> None:
        self._artifact_root: Path | None = None
        self._dependency_root: Path | None = None

    def configure_runtime(self, cache_root: Path, *, dependency_root: Path | None = None) -> None:
        self._artifact_root = cache_root
        self._dependency_root = dependency_root
        cache_root.mkdir(parents=True, exist_ok=True)

    def health_check(self) -> str:
        return self.health_check_with_context(cancellation=None, progress=None)

    def health_check_with_context(self, *, cancellation=None, progress=None) -> str:
        result = _run_worker(
            "speciesnet-health",
            {},
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
            cancellation=cancellation,
            progress=progress,
            timeout_seconds=30 * 60,
        )
        return str(result["detail"])

    def artifact_paths(self) -> tuple[Path, ...]:
        return (self._artifact_root,) if self._artifact_root is not None else ()

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        return self.execute_with_context(
            request, cancellation=_NoCancellation(), progress=lambda *_args: None
        )

    def execute_with_context(self, request, *, cancellation, progress) -> CapabilityResult:
        if request.input_kind not in self.descriptor.inputs or request.input_path is None:
            raise ValueError("Wildlife Video Review requires a photo or video input_path")
        source = request.input_path
        if not source.is_file():
            raise FileNotFoundError(source)
        interval = float(request.parameters.get("sample_interval_seconds", 2.0))
        threshold = float(request.parameters.get("minimum_confidence", 0.2))
        batch_size = int(request.parameters.get("batch_size", 4))
        progress(1, 3, "Reviewing media in the isolated SpeciesNet process")
        result = _run_worker(
            "speciesnet-run",
            {
                "source": str(source),
                "input_kind": request.input_kind.value,
                "sample_interval_seconds": interval,
                "batch_size": batch_size,
            },
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
            cancellation=cancellation,
        )
        cancellation.raise_if_requested()
        progress(2, 3, "Normalizing wildlife detections")
        samples = [
            (Path(item["path"]), float(item["seconds"])) for item in result.get("samples") or ()
        ]
        candidates = _speciesnet_candidates(result.get("predictions") or {}, samples, threshold)
        if not candidates:
            raise RuntimeError("SpeciesNet returned no wildlife detections at this threshold")
        return CapabilityResult(
            capability_id=self.descriptor.capability_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=candidates,
            source_name="SpeciesNet with MegaDetector-compatible detector",
            source_version="v4.0.3a",
            attribution="Google SpeciesNet and conservation dataset contributors",
            licence="Apache-2.0 software; model terms supplied by SpeciesNet",
            diagnostics={"sample_count": len(samples), "candidate_count": len(candidates)},
        )

    def release(self) -> None:
        return None


class _ExternalModelCapability:
    """Common isolated adapter for optional upstream test-subject models."""

    worker_prefix = ""
    source_name = ""
    source_version = ""
    attribution = ""
    licence = ""

    def __init__(self) -> None:
        self._artifact_root: Path | None = None
        self._dependency_root: Path | None = None

    def configure_runtime(self, cache_root: Path, *, dependency_root: Path | None = None) -> None:
        self._artifact_root = cache_root
        self._dependency_root = dependency_root
        cache_root.mkdir(parents=True, exist_ok=True)

    def health_check(self) -> str:
        result = _run_worker(
            f"{self.worker_prefix}-health",
            {},
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
        )
        return str(result["detail"])

    def health_check_with_context(self, *, cancellation=None, progress=None) -> str:
        result = _run_worker(
            f"{self.worker_prefix}-health",
            {},
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
            cancellation=cancellation,
            progress=progress,
            timeout_seconds=30 * 60,
        )
        return str(result["detail"])

    def artifact_paths(self) -> tuple[Path, ...]:
        return (self._artifact_root,) if self._artifact_root is not None else ()

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        return self.execute_with_context(
            request, cancellation=_NoCancellation(), progress=lambda *_args: None
        )

    def execute_with_context(self, request, *, cancellation, progress) -> CapabilityResult:
        if request.input_kind not in self.descriptor.inputs or request.input_path is None:
            raise ValueError(
                f"{self.descriptor.display_name} requires one of "
                f"{sorted(item.value for item in self.descriptor.inputs)}"
            )
        if not request.input_path.is_file():
            raise FileNotFoundError(request.input_path)
        progress(1, 3, f"Running {self.descriptor.display_name} in its isolated process")
        result = _run_worker(
            f"{self.worker_prefix}-run",
            {
                "source": str(request.input_path),
                "input_kind": request.input_kind.value,
                "parameters": dict(request.parameters),
                "artifact_root": str(self._artifact_root) if self._artifact_root else None,
                "offline": True,
            },
            dependency_root=self._dependency_root,
            artifact_root=self._artifact_root,
            cancellation=cancellation,
        )
        cancellation.raise_if_requested()
        progress(2, 3, "Normalizing model results")
        candidates = _canonical_candidates(result.get("candidates") or ())
        if not candidates:
            raise RuntimeError(
                f"{self.descriptor.display_name} returned no candidates at the selected threshold"
            )
        return CapabilityResult(
            capability_id=self.descriptor.capability_id,
            producer_name=self.descriptor.display_name,
            producer_version=self.descriptor.version,
            candidates=candidates,
            source_name=self.source_name,
            source_version=self.source_version,
            attribution=self.attribution,
            licence=self.licence,
            diagnostics={
                "candidate_count": len(candidates),
                "runtime": result.get("runtime") or self.worker_prefix,
                "model": result.get("model") or self.source_name,
                "taxonomy_embeddings": result.get("taxonomy_embeddings"),
            },
        )

    def release(self) -> None:
        return None


class MegaDetectorCapability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.megadetector",
        display_name="MegaDetector",
        version="5a",
        inputs=frozenset({InputKind.PHOTO, InputKind.VIDEO}),
        outputs=frozenset({CanonicalShape.BOUNDING_BOX.value}),
        parameters=(
            ParameterDefinition(
                "minimum_confidence", "float", default=0.2, minimum=0.0, maximum=1.0
            ),
            ParameterDefinition(
                "sample_interval_seconds", "float", default=2.0, minimum=0.25, maximum=60.0
            ),
        ),
        offline=True,
    )
    worker_prefix = "megadetector"
    source_name = "MegaDetector"
    source_version = "5a"
    attribution = "MegaDetector contributors"
    licence = "MIT"


class Yolo11DetectionCapability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.yolo11-detect",
        display_name="YOLO 11 Detection",
        version="11n",
        inputs=frozenset({InputKind.PHOTO, InputKind.VIDEO}),
        outputs=frozenset({CanonicalShape.BOUNDING_BOX.value}),
        parameters=(
            ParameterDefinition("minimum_confidence", "float", default=0.25, minimum=0.0, maximum=1.0),
            ParameterDefinition("sample_interval_seconds", "float", default=2.0, minimum=0.25, maximum=60.0),
        ),
        offline=True,
    )
    worker_prefix = "yolo11detect"
    source_name = "Ultralytics YOLO 11 Detection"
    source_version = "11n"
    attribution = "Ultralytics YOLO contributors"
    licence = "AGPL-3.0; commercial licensing may be required"


class Yolo11SegmentationCapability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.yolo11-segment",
        display_name="YOLO 11 Instance Segmentation",
        version="11n-seg",
        inputs=frozenset({InputKind.PHOTO, InputKind.VIDEO}),
        outputs=frozenset({CanonicalShape.BOUNDING_BOX.value, CanonicalShape.SEGMENTATION.value}),
        parameters=(
            ParameterDefinition("minimum_confidence", "float", default=0.25, minimum=0.0, maximum=1.0),
            ParameterDefinition("sample_interval_seconds", "float", default=2.0, minimum=0.25, maximum=60.0),
        ),
        offline=True,
    )
    worker_prefix = "yolo11segment"
    source_name = "Ultralytics YOLO 11 Instance Segmentation"
    source_version = "11n-seg"
    attribution = "Ultralytics YOLO contributors"
    licence = "AGPL-3.0; commercial licensing may be required"


class SegmentAnythingVitBCapability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.sam-vit-b",
        display_name="Segment Anything ViT-B",
        version="1-vit-b",
        inputs=frozenset({InputKind.PHOTO}),
        outputs=frozenset({CanonicalShape.SEGMENTATION.value}),
        parameters=(
            ParameterDefinition("minimum_area", "integer", default=256, minimum=1, maximum=10000000),
            ParameterDefinition("maximum_masks", "integer", default=32, minimum=1, maximum=256),
        ),
        offline=True,
    )
    worker_prefix = "samvitb"
    source_name = "Meta Segment Anything ViT-B"
    source_version = "1"
    attribution = "Meta AI Segment Anything contributors"
    licence = "Apache-2.0"


class BioCLIP2Capability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.bioclip2",
        display_name="BioCLIP 2",
        version="2",
        inputs=frozenset({InputKind.PHOTO}),
        outputs=frozenset({CanonicalShape.TAXONOMY_CANDIDATE.value}),
        parameters=(ParameterDefinition("limit", "integer", default=10, minimum=1, maximum=50),),
        offline=True,
    )
    worker_prefix = "bioclip2"
    source_name = "Imageomics BioCLIP 2"
    source_version = "2"
    attribution = "Imageomics BioCLIP 2 and TreeOfLife contributors"
    licence = "See upstream model card"


class BioCLIP25HugeCapability(BioCLIP2Capability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.bioclip25-huge",
        display_name="BioCLIP 2.5 Huge",
        version="2.5",
        inputs=frozenset({InputKind.PHOTO}),
        outputs=frozenset({CanonicalShape.TAXONOMY_CANDIDATE.value}),
        parameters=(ParameterDefinition("limit", "integer", default=10, minimum=1, maximum=50),),
        offline=True,
    )
    worker_prefix = "bioclip25"
    source_name = "Imageomics BioCLIP 2.5 Huge"
    source_version = "2.5"


class Perch2Capability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.perch2",
        display_name="Perch 2 Bioacoustics",
        version="2",
        inputs=frozenset({InputKind.SOUND, InputKind.VIDEO}),
        outputs=frozenset(
            {CanonicalShape.TIME_SEGMENT.value, CanonicalShape.TAXONOMY_CANDIDATE.value}
        ),
        parameters=(
            ParameterDefinition(
                "minimum_confidence", "float", default=0.25, minimum=0.0, maximum=1.0
            ),
        ),
        offline=True,
    )
    worker_prefix = "perch2"
    source_name = "Google Perch 2"
    source_version = "2"
    attribution = "Google Research Perch contributors"
    licence = "Apache-2.0 code; see Kaggle model terms"


class BatDetect2Capability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="aperture.batdetect2",
        display_name="BatDetect2",
        version="1",
        inputs=frozenset({InputKind.SOUND}),
        outputs=frozenset(
            {CanonicalShape.TIME_SEGMENT.value, CanonicalShape.TAXONOMY_CANDIDATE.value}
        ),
        parameters=(
            ParameterDefinition(
                "minimum_confidence", "float", default=0.25, minimum=0.0, maximum=1.0
            ),
        ),
        offline=True,
    )
    worker_prefix = "batdetect2"
    source_name = "BatDetect2"
    source_version = "1"
    attribution = "BatDetect2 contributors"
    licence = "See upstream package and model licence"


class DocumentOCRCapability(_ExternalModelCapability):
    descriptor = CapabilityDescriptor(
        capability_id="fieldora.document-ocr",
        display_name="Fieldora Offline Document OCR",
        version="1",
        inputs=frozenset({InputKind.DOCUMENT}),
        outputs=frozenset(
            {CanonicalShape.TRANSCRIPT_SEGMENT.value, CanonicalShape.DOCUMENT_REGION.value}
        ),
        parameters=(
            ParameterDefinition(
                "render_dpi", "integer", default=180, minimum=96, maximum=400
            ),
            ParameterDefinition(
                "minimum_confidence", "float", default=0.35, minimum=0.0, maximum=1.0
            ),
        ),
        offline=True,
    )
    worker_prefix = "documentocr"
    source_name = "RapidOCR ONNX Runtime"
    source_version = "1"
    attribution = "RapidOCR and ONNX Runtime contributors"
    licence = "Apache-2.0 software; bundled model licences apply"


def _canonical_candidates(rows) -> tuple[CanonicalCandidate, ...]:
    candidates = []
    for row in rows:
        shape = CanonicalShape(str(row["shape"]))
        candidates.append(
            CanonicalCandidate(
                shape,
                dict(row.get("payload") or {}),
                confidence=float(row.get("confidence") or 0),
                target=dict(row.get("target") or {}),
            )
        )
    return tuple(candidates)


def _birdnet_candidates(path: Path) -> tuple[CanonicalCandidate, ...]:
    if not path.is_file():
        raise RuntimeError("BirdNET did not create its result CSV")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return _birdnet_candidates_from_rows(csv.DictReader(handle))


def _birdnet_candidates_from_rows(rows) -> tuple[CanonicalCandidate, ...]:
    candidates = []
    for row in rows:
        scientific = str(row.get("Scientific name") or "").strip()
        common = str(row.get("Common name") or "").strip()
        confidence = float(row.get("Confidence") or 0)
        candidates.append(
            CanonicalCandidate(
                CanonicalShape.TIME_SEGMENT,
                {
                    "label": common or scientific,
                    "scientific_name": scientific,
                    "common_name": common,
                },
                confidence=max(0.0, min(1.0, confidence)),
                target={
                    "start_seconds": float(row.get("Start (s)") or 0),
                    "end_seconds": float(row.get("End (s)") or 0),
                },
            )
        )
    return tuple(candidates)


def _speciesnet_candidates(
    predictions: dict[str, dict[str, Any]],
    samples: list[tuple[Path, float]],
    threshold: float,
) -> tuple[CanonicalCandidate, ...]:
    seconds_by_path = {
        value: seconds for path, seconds in samples for value in (str(path), path.name)
    }
    candidates: list[CanonicalCandidate] = []
    for path, result in predictions.items():
        seconds = seconds_by_path.get(str(path), seconds_by_path.get(Path(path).name, 0.0))
        label = str(result.get("prediction") or "").strip()
        score = float(result.get("prediction_score") or 0)
        if label and score >= threshold:
            parts = label.split(";")
            scientific = parts[-2].strip() if len(parts) >= 2 else label
            common = parts[-1].strip() if len(parts) >= 2 else ""
            candidates.append(
                CanonicalCandidate(
                    CanonicalShape.TAXONOMY_CANDIDATE,
                    {
                        "label": common or scientific,
                        "scientific_name": scientific,
                        "common_name": common,
                    },
                    confidence=max(0.0, min(1.0, score)),
                    target={"time_seconds": seconds, "frame_path": Path(path).name},
                )
            )
        for detection in result.get("detections") or ():
            confidence = float(detection.get("conf") or detection.get("confidence") or 0)
            if confidence < threshold:
                continue
            bbox = tuple(float(value) for value in detection.get("bbox") or ())
            if len(bbox) != 4:
                continue
            candidates.append(
                CanonicalCandidate(
                    CanonicalShape.BOUNDING_BOX,
                    {"label": str(detection.get("label") or "animal")},
                    confidence=max(0.0, min(1.0, confidence)),
                    target={
                        "time_seconds": seconds,
                        "x": bbox[0],
                        "y": bbox[1],
                        "width": bbox[2],
                        "height": bbox[3],
                        "normalized": True,
                    },
                )
            )
    return tuple(candidates)


class _NoCancellation:
    def raise_if_requested(self) -> None:
        return None


def _run_worker(
    action: str,
    request: dict[str, object],
    *,
    dependency_root: Path | None,
    artifact_root: Path | None,
    cancellation=None,
    progress=None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aperture-model-worker-") as temporary_name:
        temporary = Path(temporary_name)
        request_path = temporary / "request.json"
        output_path = temporary / "result.json"
        log_path = temporary / "worker.log"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "natureai_next.synthesis_core.optional_model_worker",
            action,
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ]
        environment = os.environ.copy()
        if dependency_root is not None:
            previous = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = (
                str(dependency_root)
                if not previous
                else str(dependency_root) + os.pathsep + previous
            )
        if artifact_root is not None:
            environment["APERTURE_MODEL_ARTIFACT_ROOT"] = str(artifact_root)
            environment["KAGGLEHUB_CACHE"] = str(artifact_root)
            environment["HF_HOME"] = str(artifact_root / "huggingface")
            environment["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        # Installation health checks may acquire verified resources. Actual
        # enrichment runs are strictly local once a model is marked ready.
        if action.endswith("-run"):
            environment["HF_HUB_OFFLINE"] = "1"
            environment["TRANSFORMERS_OFFLINE"] = "1"
            environment["KAGGLE_HUB_OFFLINE"] = "1"
            environment["APERTURE_MODEL_OFFLINE"] = "1"
        started = time.monotonic()
        last_reported_second = -1
        with log_path.open("w+", encoding="utf-8", errors="replace") as worker_log:
            # A PIPE can fill while model installers emit download progress and
            # deadlock the child. A file keeps draining regardless of output size.
            process = subprocess.Popen(
                command,
                stdout=worker_log,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
            )
            while process.poll() is None:
                try:
                    if callable(cancellation):
                        if cancellation():
                            raise InterruptedError("Model operation cancelled")
                    elif cancellation is not None:
                        cancellation.raise_if_requested()
                    elapsed = time.monotonic() - started
                    if timeout_seconds is not None and elapsed > timeout_seconds:
                        raise TimeoutError(
                            f"{action} exceeded its {int(timeout_seconds // 60)} minute limit"
                        )
                    elapsed_second = int(elapsed)
                    if callable(progress) and elapsed_second // 10 != last_reported_second // 10:
                        progress(
                            3,
                            4,
                            f"Model health check is running in an isolated process "
                            f"({elapsed_second}s elapsed)",
                        )
                        last_reported_second = elapsed_second
                except Exception:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise
                time.sleep(0.1)
            worker_log.flush()
            worker_log.seek(0)
            worker_output = worker_log.read()
        if process.returncode != 0:
            detail = (worker_output or f"{action} worker failed").strip()
            raise RuntimeError(detail[-4000:])
        if not output_path.is_file():
            raise RuntimeError(f"{action} worker did not produce a result")
        result = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise RuntimeError(f"{action} worker returned an invalid result")
        return result

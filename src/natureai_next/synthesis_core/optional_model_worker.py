"""Isolated worker entry point for optional third-party enrichment stacks."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=(
            "birdnet-health",
            "birdnet-run",
            "speciesnet-health",
            "speciesnet-run",
            "megadetector-health",
            "megadetector-run",
            "yolo11detect-health",
            "yolo11detect-run",
            "yolo11segment-health",
            "yolo11segment-run",
            "samvitb-health",
            "samvitb-run",
            "bioclip2-health",
            "bioclip2-run",
            "bioclip25-health",
            "bioclip25-run",
            "perch2-health",
            "perch2-run",
            "batdetect2-health",
            "batdetect2-run",
            "documentocr-health",
            "documentocr-run",
        ),
    )
    parser.add_argument("--request", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = (
        json.loads(args.request.read_text(encoding="utf-8")) if args.request is not None else {}
    )
    if args.action == "birdnet-health":
        from birdnet_analyzer.utils import ensure_model_exists

        ensure_model_exists()
        result = {"detail": "BirdNET Analyzer 2.4.0 model and labels ready"}
    elif args.action == "birdnet-run":
        result = _run_birdnet(request)
    elif args.action == "speciesnet-health":
        _health_speciesnet()
        result = {"detail": "SpeciesNet detector, classifier, taxonomy and weights ready"}
    elif args.action == "speciesnet-run":
        result = _run_speciesnet(request)
    elif args.action.endswith("-health"):
        result = _health_external(args.action.removesuffix("-health"))
    else:
        result = _run_external(args.action.removesuffix("-run"), request)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return 0


def _health_external(provider: str) -> dict:
    if provider == "megadetector":
        import megadetector

        model_path = _ensure_megadetector_model()
        detail = (
            f"MegaDetector runtime ready ({getattr(megadetector, '__version__', 'installed')}); "
            f"offline model={model_path.name}"
        )
    elif provider in {"yolo11detect", "yolo11segment"}:
        from ultralytics import YOLO
        checkpoint = _ensure_yolo_model(provider)
        YOLO(str(checkpoint))
        detail = f"Ultralytics runtime ready; offline model={checkpoint.name}"
    elif provider == "samvitb":
        from segment_anything import sam_model_registry
        checkpoint = _ensure_sam_model()
        sam_model_registry["vit_b"](checkpoint=str(checkpoint))
        detail = f"Segment Anything runtime ready; offline model={checkpoint.name}"
    elif provider in {"bioclip2", "bioclip25"}:
        import bioclip
        import open_clip

        if provider == "bioclip2":
            from bioclip import TreeOfLifeClassifier
            TreeOfLifeClassifier(model_str="hf-hub:imageomics/bioclip-2")
            model_detail = "BioCLIP 2 TreeOfLife resources cached"
        else:
            _ensure_bioclip25_resources()
            model_detail = "BioCLIP 2.5 model and taxonomy resources cached"
        detail = (
            f"BioCLIP runtime ready (pybioclip={getattr(bioclip, '__version__', 'installed')}; "
            f"open_clip={getattr(open_clip, '__version__', 'installed')}); {model_detail}"
        )
    elif provider == "perch2":
        model = _initialize_perch2()
        detail = f"Perch 2 runtime ready ({type(model).__module__}.{type(model).__name__})"
    elif provider == "batdetect2":
        import batdetect2

        detail = f"BatDetect2 runtime ready ({getattr(batdetect2, '__version__', 'installed')})"
    elif provider == "documentocr":
        import fitz
        from rapidocr_onnxruntime import RapidOCR

        RapidOCR()
        detail = (
            "Offline document OCR ready "
            f"(PyMuPDF {getattr(fitz, '__version__', 'installed')}; RapidOCR ONNX)"
        )
    else:  # pragma: no cover - argparse constrains providers
        raise ValueError(provider)
    return {"detail": detail}


def _run_external(provider: str, request: dict) -> dict:
    if provider == "megadetector":
        return _run_megadetector(request)
    if provider in {"yolo11detect", "yolo11segment"}:
        return _run_yolo(request, segmentation=provider == "yolo11segment")
    if provider == "samvitb":
        return _run_sam(request)
    if provider in {"bioclip2", "bioclip25"}:
        return _run_bioclip(request, provider)
    if provider == "perch2":
        return _run_perch2(request)
    if provider == "batdetect2":
        return _run_batdetect2(request)
    if provider == "documentocr":
        return _run_document_ocr(request)
    raise ValueError(provider)


def _run_document_ocr(request: dict) -> dict:
    """Extract embedded PDF text and OCR image-only pages without network access."""
    import fitz
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    source = Path(request["source"])
    parameters = dict(request.get("parameters") or {})
    dpi = int(parameters.get("render_dpi", 180))
    threshold = float(parameters.get("minimum_confidence", 0.35))
    engine = RapidOCR()
    candidates: list[dict] = []
    document = fitz.open(str(source))
    try:
        for page_number, page in enumerate(document, start=1):
            embedded = page.get_text("text").strip()
            if embedded:
                candidates.append(
                    {
                        "shape": "transcript_segment",
                        "payload": {"text": embedded, "method": "embedded_pdf_text"},
                        "confidence": 1.0,
                        "target": {"page": page_number},
                    }
                )
                continue
            scale = dpi / 72.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            result, _elapsed = engine(image)
            lines = []
            for entry in result or ():
                box, text, confidence = entry
                score = float(confidence)
                if score < threshold or not str(text).strip():
                    continue
                xs = [float(point[0]) / pixmap.width for point in box]
                ys = [float(point[1]) / pixmap.height for point in box]
                lines.append(str(text).strip())
                candidates.append(
                    {
                        "shape": "document_region",
                        "payload": {"text": str(text).strip(), "method": "rapidocr"},
                        "confidence": max(0.0, min(1.0, score)),
                        "target": {
                            "page": page_number,
                            "x": min(xs),
                            "y": min(ys),
                            "width": max(xs) - min(xs),
                            "height": max(ys) - min(ys),
                            "normalized": True,
                        },
                    }
                )
            if lines:
                candidates.append(
                    {
                        "shape": "transcript_segment",
                        "payload": {"text": "\n".join(lines), "method": "rapidocr"},
                        "confidence": 1.0,
                        "target": {"page": page_number},
                    }
                )
    finally:
        document.close()
    return {
        "candidates": candidates,
        "runtime": "rapidocr-onnxruntime",
        "model": "RapidOCR default multilingual detector/recognizer",
    }


def _run_birdnet(request: dict) -> dict:
    source = Path(request["source"])
    input_kind = str(request["input_kind"])
    with tempfile.TemporaryDirectory(prefix="aperture-birdnet-worker-") as temporary_name:
        temporary = Path(temporary_name)
        audio = source
        if input_kind == "video":
            audio = temporary / f"{source.stem}.wav"
            _extract_audio(source, audio)
        from birdnet_analyzer.analyze import analyze

        analyze(
            str(audio),
            str(temporary),
            min_conf=float(request["minimum_confidence"]),
            rtype="csv",
            threads=int(request["threads"]),
            locale="en",
        )
        result_path = temporary / f"{audio.stem}.BirdNET.results.csv"
        if not result_path.is_file():
            matches = tuple(temporary.rglob("*.BirdNET.results.csv"))
            result_path = matches[0] if len(matches) == 1 else result_path
        if not result_path.is_file():
            raise RuntimeError("BirdNET did not create its result CSV")
        with result_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    return {"rows": rows}


def _run_speciesnet(request: dict) -> dict:
    source = Path(request["source"])
    input_kind = str(request["input_kind"])
    with tempfile.TemporaryDirectory(prefix="aperture-speciesnet-worker-") as temporary_name:
        temporary = Path(temporary_name)
        samples = (
            [(temporary / source.name, 0.0)]
            if input_kind == "photo"
            else _sample_video(source, temporary, float(request["sample_interval_seconds"]))
        )
        if input_kind == "photo":
            shutil.copy2(source, samples[0][0])
        if not samples:
            raise RuntimeError("No decodable video frames were found")
        output_path = temporary / "speciesnet-predictions.json"
        _invoke_speciesnet(
            temporary,
            output_path,
            batch_size=int(request["batch_size"]),
        )
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        prediction_rows = payload.get("predictions") or ()
        predictions = {
            str(item.get("filepath")): item
            for item in prediction_rows
            if isinstance(item, dict) and item.get("filepath")
        }
        return {
            "predictions": predictions,
            "samples": [{"path": str(path), "seconds": seconds} for path, seconds in samples],
        }


def _health_speciesnet() -> None:
    with tempfile.TemporaryDirectory(prefix="aperture-speciesnet-health-") as temporary_name:
        temporary = Path(temporary_name)
        # A valid dependency-free PPM image forces model acquisition and one real inference.
        sample = temporary / "health.ppm"
        sample.write_bytes(b"P6\n2 2\n255\n" + b"\x00" * 12)
        output_path = temporary / "health-result.json"
        _invoke_speciesnet(temporary, output_path, batch_size=1)
        if not output_path.is_file():
            raise RuntimeError("SpeciesNet health check did not produce predictions")


def _invoke_speciesnet(folder: Path, output_path: Path, *, batch_size: int) -> None:
    command = [
        sys.executable,
        "-m",
        "speciesnet.scripts.run_model",
        "--folders",
        str(folder),
        "--predictions_json",
        str(output_path),
        "--batch_size",
        str(batch_size),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "SpeciesNet failed").strip()
        raise RuntimeError(detail[-4000:])


YOLO11_DETECT_URLS = (
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
)
YOLO11_SEGMENT_URLS = (
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-seg.pt",
)
SAM_VIT_B_URLS = (
    "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth",
)


MEGADETECTOR_MODEL_URLS = (
    "https://github.com/agentmorris/MegaDetector/releases/download/v5.0/md_v5a.0.1.pt",
)


def _artifact_root(request: dict | None = None) -> Path:
    value = (request or {}).get("artifact_root") or os.environ.get("APERTURE_MODEL_ARTIFACT_ROOT") or os.environ.get("KAGGLEHUB_CACHE")
    if not value:
        raise RuntimeError("Aperture model artifact storage is not configured.")
    root = Path(str(value))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _download_once(urls: tuple[str, ...], destination: Path) -> Path:
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    errors = []
    for url in urls:
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            urllib.request.urlretrieve(url, temporary)
            if temporary.stat().st_size <= 0:
                raise RuntimeError("downloaded file is empty")
            temporary.replace(destination)
            return destination
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Model acquisition failed from every configured source. " + " | ".join(errors))


def _ensure_yolo_model(provider: str, request: dict | None = None) -> Path:
    root = _artifact_root(request) / "weights"
    if provider == "yolo11segment":
        return _download_once(YOLO11_SEGMENT_URLS, root / "yolo11n-seg.pt")
    return _download_once(YOLO11_DETECT_URLS, root / "yolo11n.pt")


def _ensure_sam_model(request: dict | None = None) -> Path:
    return _download_once(SAM_VIT_B_URLS, _artifact_root(request) / "weights" / "sam_vit_b_01ec64.pth")


def _ensure_megadetector_model(request: dict | None = None) -> Path:
    root = _artifact_root(request) / "weights"
    return _download_once(MEGADETECTOR_MODEL_URLS, root / "md_v5a.0.1.pt")


def _ensure_bioclip25_resources() -> None:
    import os
    import open_clip
    from huggingface_hub import hf_hub_download
    cache_dir = os.environ.get("HF_HOME")
    hf_hub_download(repo_id="imageomics/TreeOfLife-200M", repo_type="dataset", filename="embeddings/txt_emb_bioclip-2.5-vith14.npy", cache_dir=cache_dir)
    hf_hub_download(repo_id="imageomics/TreeOfLife-200M", repo_type="dataset", filename="embeddings/txt_emb_bioclip-2.5-vith14.json", cache_dir=cache_dir)
    open_clip.create_model_and_transforms("hf-hub:imageomics/bioclip-2.5-vith14", cache_dir=cache_dir)


def _run_megadetector(request: dict) -> dict:
    from megadetector.detection.run_detector import load_detector

    source = Path(request["source"])
    parameters = request.get("parameters") or {}
    threshold = float(parameters.get("minimum_confidence", 0.2))
    model_path = _ensure_megadetector_model(request)
    with tempfile.TemporaryDirectory(prefix="aperture-megadetector-") as temporary_name:
        temporary = Path(temporary_name)
        samples = (
            [(source, 0.0)]
            if request["input_kind"] == "photo"
            else _sample_video(
                source, temporary, float(parameters.get("sample_interval_seconds", 2.0))
            )
        )
        detector = load_detector(str(model_path))
        candidates = []
        for path, seconds in samples:
            result = detector.generate_detections_one_image(str(path))
            for detection in result.get("detections") or ():
                confidence = float(detection.get("conf") or 0)
                if confidence < threshold:
                    continue
                category = str(detection.get("category") or "1")
                label = {"1": "animal", "2": "person", "3": "vehicle"}.get(category, category)
                bbox = list(detection.get("bbox") or ())
                if len(bbox) != 4:
                    continue
                candidates.append(
                    {
                        "shape": "bounding_box",
                        "payload": {"label": label},
                        "confidence": confidence,
                        "target": {
                            "time_seconds": seconds,
                            "x": bbox[0],
                            "y": bbox[1],
                            "width": bbox[2],
                            "height": bbox[3],
                            "normalized": True,
                        },
                    }
                )
    return {"candidates": candidates}



def _run_yolo(request: dict, *, segmentation: bool) -> dict:
    from ultralytics import YOLO
    source = Path(request["source"])
    params = request.get("parameters") or {}
    threshold = float(params.get("minimum_confidence", 0.25))
    checkpoint = _ensure_yolo_model("yolo11segment" if segmentation else "yolo11detect", request)
    model = YOLO(str(checkpoint))
    with tempfile.TemporaryDirectory(prefix="aperture-yolo-") as temporary_name:
        temporary = Path(temporary_name)
        samples = [(source, 0.0)] if request["input_kind"] == "photo" else _sample_video(source, temporary, float(params.get("sample_interval_seconds", 2.0)))
        candidates = []
        for path, seconds in samples:
            for result in model.predict(source=str(path), conf=threshold, verbose=False, device=None):
                names = result.names or {}
                boxes = result.boxes
                if boxes is None:
                    continue
                xyxyn = boxes.xyxyn.detach().cpu().tolist()
                confs = boxes.conf.detach().cpu().tolist()
                classes = boxes.cls.detach().cpu().tolist()
                polygons = result.masks.xyn if segmentation and result.masks is not None else None
                for index, (coords, confidence, class_id) in enumerate(zip(xyxyn, confs, classes, strict=True)):
                    x1, y1, x2, y2 = [float(v) for v in coords]
                    label = str(names.get(int(class_id), int(class_id)))
                    target = {"time_seconds": seconds, "x": x1, "y": y1, "width": x2-x1, "height": y2-y1, "normalized": True}
                    candidates.append({"shape":"bounding_box", "payload":{"label":label, "class_id":int(class_id)}, "confidence":float(confidence), "target":target})
                    if polygons is not None and index < len(polygons):
                        polygon = [[float(x), float(y)] for x, y in polygons[index].tolist()]
                        candidates.append({"shape":"segmentation", "payload":{"label":label, "class_id":int(class_id), "polygon":polygon}, "confidence":float(confidence), "target":target})
    return {"candidates": candidates, "runtime":"ultralytics", "model":checkpoint.name}


def _mask_to_rle(mask) -> list[int]:
    import numpy as np
    flat = np.asarray(mask, dtype=np.uint8).reshape(-1, order="F")
    counts=[]; previous=0; run=0
    for value in flat:
        value=int(value)
        if value == previous:
            run += 1
        else:
            counts.append(run); run=1; previous=value
    counts.append(run)
    return counts


def _run_sam(request: dict) -> dict:
    import cv2
    from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
    params = request.get("parameters") or {}
    minimum_area = int(params.get("minimum_area", 256))
    maximum_masks = int(params.get("maximum_masks", 32))
    checkpoint = _ensure_sam_model(request)
    sam = sam_model_registry["vit_b"](checkpoint=str(checkpoint))
    try:
        import torch
        if torch.cuda.is_available():
            sam.to(device="cuda")
    except Exception:
        pass
    image = cv2.imread(str(request["source"]))
    if image is None:
        raise RuntimeError("Segment Anything could not decode the source image")
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    masks = SamAutomaticMaskGenerator(sam, min_mask_region_area=minimum_area).generate(image)
    masks = sorted(masks, key=lambda row: float(row.get("area") or 0), reverse=True)[:maximum_masks]
    height, width = image.shape[:2]
    candidates=[]
    for index, row in enumerate(masks):
        x,y,w,h=[float(v) for v in row["bbox"]]
        candidates.append({"shape":"segmentation", "payload":{"label":f"subject region {index+1}", "area_pixels":int(row.get("area") or 0), "rle_counts":_mask_to_rle(row["segmentation"]), "mask_size":[height,width]}, "confidence":float(row.get("predicted_iou") or row.get("stability_score") or 0), "target":{"x":x/width,"y":y/height,"width":w/width,"height":h/height,"normalized":True}})
    return {"candidates":candidates, "runtime":"segment_anything", "model":checkpoint.name}


def _run_bioclip(request: dict, provider: str) -> dict:
    if provider == "bioclip25":
        return _run_bioclip25_openclip(request)

    from bioclip import Rank, TreeOfLifeClassifier

    import torch

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    classifier = TreeOfLifeClassifier(
        model_str="hf-hub:imageomics/bioclip-2",
        device=device,
    )
    limit = int((request.get("parameters") or {}).get("limit", 10))
    predictions = classifier.predict(request["source"], Rank.SPECIES)
    return {
        "candidates": _taxonomy_candidates(predictions, limit),
        "runtime": "pybioclip",
        "device": device,
        "cuda_available": bool(torch.cuda.is_available()),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def _run_bioclip25_openclip(request: dict) -> dict:
    """Run BioCLIP 2.5 with its supported OpenCLIP and matching ToL embeddings.

    pybioclip 2.1.x intentionally restricts ``TreeOfLifeClassifier`` to the
    original BioCLIP and BioCLIP 2 checkpoints. Imageomics publishes a
    separate BioCLIP 2.5 text-embedding matrix and label JSON, so Aperture
    loads those resources directly and performs the same normalized
    image/text similarity ranking without routing the model through the
    incompatible classifier.
    """
    import json as _json
    import os

    import numpy as np
    import open_clip
    import torch
    from huggingface_hub import hf_hub_download
    from PIL import Image

    model_id = "hf-hub:imageomics/bioclip-2.5-vith14"
    dataset_id = "imageomics/TreeOfLife-200M"
    cache_dir = os.environ.get("HF_HOME")
    embeddings_path = hf_hub_download(
        repo_id=dataset_id,
        repo_type="dataset",
        filename="embeddings/txt_emb_bioclip-2.5-vith14.npy",
        cache_dir=cache_dir,
    )
    labels_path = hf_hub_download(
        repo_id=dataset_id,
        repo_type="dataset",
        filename="embeddings/txt_emb_bioclip-2.5-vith14.json",
        cache_dir=cache_dir,
    )
    model, _preprocess_train, preprocess = open_clip.create_model_and_transforms(
        model_id, cache_dir=cache_dir
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.eval().to(device)
    with Image.open(request["source"]) as opened:
        image = preprocess(opened.convert("RGB")).unsqueeze(0).to(device)
    with torch.inference_mode():
        if device == "cuda":
            with torch.autocast("cuda"):
                image_features = model.encode_image(image)
        else:
            image_features = model.encode_image(image)
        image_features = image_features.float()
        image_features /= image_features.norm(dim=-1, keepdim=True).clamp_min(1e-12)

    embeddings = np.load(embeddings_path, mmap_mode="r")
    if embeddings.ndim != 2 or embeddings.shape[1] != image_features.shape[1]:
        raise RuntimeError(
            "BioCLIP 2.5 taxonomy embeddings are incompatible with the loaded model "
            f"({embeddings.shape} versus image dimension {image_features.shape[1]})."
        )
    limit = max(1, int((request.get("parameters") or {}).get("limit", 10)))
    best_scores: list[float] = []
    best_indices: list[int] = []
    log_denominator = None
    chunk_size = 8192 if device == "cuda" else 2048
    for start in range(0, embeddings.shape[0], chunk_size):
        chunk_np = np.asarray(embeddings[start : start + chunk_size], dtype=np.float32)
        chunk = torch.from_numpy(chunk_np).to(device)
        chunk /= chunk.norm(dim=-1, keepdim=True).clamp_min(1e-12)
        scores = (100.0 * image_features @ chunk.T).squeeze(0)
        chunk_logsum = torch.logsumexp(scores, dim=0)
        log_denominator = (
            chunk_logsum
            if log_denominator is None
            else torch.logaddexp(log_denominator, chunk_logsum)
        )
        local_k = min(limit, scores.numel())
        values, indices = torch.topk(scores, local_k)
        best_scores.extend(float(value) for value in values.detach().cpu())
        best_indices.extend(start + int(index) for index in indices.detach().cpu())
        if len(best_scores) > limit * 4:
            order = sorted(range(len(best_scores)), key=best_scores.__getitem__, reverse=True)[:limit]
            best_scores = [best_scores[index] for index in order]
            best_indices = [best_indices[index] for index in order]
    order = sorted(range(len(best_scores)), key=best_scores.__getitem__, reverse=True)[:limit]
    with open(labels_path, "r", encoding="utf-8") as handle:
        labels = _json.load(handle)
    if not isinstance(labels, list) or len(labels) != embeddings.shape[0]:
        raise RuntimeError(
            "BioCLIP 2.5 taxonomy labels do not match the embedding matrix "
            f"({len(labels) if isinstance(labels, list) else 'invalid'} versus {embeddings.shape[0]})."
        )
    predictions = []
    for position in order:
        label = labels[best_indices[position]]
        if not isinstance(label, dict):
            label = {"species": str(label)}
        prediction = dict(label)
        if log_denominator is None:
            raise RuntimeError("BioCLIP 2.5 taxonomy embedding matrix is empty.")
        prediction["score"] = float(
            torch.exp(
                torch.tensor(best_scores[position], device=log_denominator.device)
                - log_denominator
            ).detach().cpu()
        )
        predictions.append(prediction)
    return {
        "candidates": _taxonomy_candidates(predictions, limit),
        "runtime": "open_clip",
        "model": model_id,
        "taxonomy_embeddings": "imageomics/TreeOfLife-200M:txt_emb_bioclip-2.5-vith14",
    }


def _taxonomy_candidates(predictions, limit: int) -> list[dict]:
    candidates = []
    for prediction in list(predictions)[:limit]:
        scientific = str(
            prediction.get("scientific_name") or prediction.get("species") or ""
        ).strip()
        common = str(prediction.get("common_name") or "").strip()
        candidates.append(
            {
                "shape": "taxonomy_candidate",
                "payload": {
                    "label": common or scientific,
                    "scientific_name": scientific,
                    "common_name": common,
                    "kingdom": str(prediction.get("kingdom") or ""),
                    "phylum": str(prediction.get("phylum") or ""),
                    "class": str(prediction.get("class") or ""),
                    "order": str(prediction.get("order") or ""),
                    "family": str(prediction.get("family") or ""),
                    "genus": str(prediction.get("genus") or ""),
                },
                "confidence": float(prediction.get("score") or 0),
                "target": {},
            }
        )
    return candidates


def _initialize_perch2():
    try:
        import kagglehub  # noqa: F401 - required by Perch model acquisition
        import bioacoustics_model_zoo as model_zoo
        return model_zoo.Perch2()
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Perch 2 dependency is missing: {exc.name}. Reinstall the Perch model dependencies."
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Perch 2 initialization failed: {type(exc).__name__}: {exc}") from exc


def _run_perch2(request: dict) -> dict:
    model = _initialize_perch2()
    predictions = model.predict([request["source"]])
    threshold = float((request.get("parameters") or {}).get("minimum_confidence", 0.25))
    candidates = []
    for _, row in predictions.iterrows():
        score = float(row.get("score") or row.get("confidence") or 0)
        if score < threshold:
            continue
        label = str(row.get("label") or row.get("class") or row.get("species") or "")
        candidates.append(
            {
                "shape": "time_segment",
                "payload": {"label": label, "scientific_name": label},
                "confidence": score,
                "target": {
                    "start_seconds": float(row.get("start_time") or 0),
                    "end_seconds": float(row.get("end_time") or 0),
                },
            }
        )
    return {"candidates": candidates}


def _run_batdetect2(request: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="aperture-batdetect2-") as temporary_name:
        output = Path(temporary_name) / "results.json"
        command = [
            sys.executable,
            "-m",
            "batdetect2",
            "process",
            request["source"],
            "--output",
            str(output),
            "--format",
            "json",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0 or not output.is_file():
            detail = (completed.stderr or completed.stdout or "BatDetect2 failed").strip()
            raise RuntimeError(detail[-4000:])
        document = json.loads(output.read_text(encoding="utf-8"))
    threshold = float((request.get("parameters") or {}).get("minimum_confidence", 0.25))
    candidates = []
    for row in document.get("predictions") or document.get("annotations") or ():
        score = float(row.get("class_prob") or row.get("confidence") or 0)
        if score < threshold:
            continue
        label = str(row.get("class") or row.get("species") or "bat")
        candidates.append(
            {
                "shape": "time_segment",
                "payload": {"label": label, "scientific_name": label},
                "confidence": score,
                "target": {
                    "start_seconds": float(row.get("start_time") or 0),
                    "end_seconds": float(row.get("end_time") or 0),
                },
            }
        )
    return {"candidates": candidates}


def _extract_audio(source: Path, destination: Path) -> None:
    import imageio_ffmpeg

    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-nostdin",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or completed.stdout or "audio extraction failed").strip()
        raise RuntimeError(detail[-2000:])


def _sample_video(source: Path, destination: Path, interval: float):
    import cv2

    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to decode video: {source.name}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    if fps <= 0:
        capture.release()
        raise RuntimeError("Video frame rate is unavailable")
    step = max(1, round(fps * interval))
    samples = []
    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % step == 0:
                path = destination / f"frame-{frame_index:09d}.jpg"
                if not cv2.imwrite(str(path), frame):
                    raise RuntimeError(f"Unable to write sampled frame {frame_index}")
                samples.append((path, frame_index / fps))
            frame_index += 1
    finally:
        capture.release()
    return samples


if __name__ == "__main__":
    raise SystemExit(main())

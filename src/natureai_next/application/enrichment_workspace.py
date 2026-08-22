"""Subject-workspace orchestration for running, reviewing and projecting enrichment."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Any

from natureai_next.application.capability_execution import (
    AsyncCapabilityRun,
    CapabilityExecutionPool,
    compatible_capabilities,
    validate_parameters,
)
from natureai_next.application.capability_translation import CapabilityTranslationService
from natureai_next.application.enrichment import CanonicalEnrichmentService
from natureai_next.application.enrichment_projection import (
    EnrichmentProjectionService,
    SubjectEnrichmentView,
)
from natureai_next.domain.enrichment import (
    CanonicalCandidate,
    CanonicalShape,
    EnrichmentStatus,
    SubjectRef,
)
from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    CapabilityRequest,
    CapabilityResult,
    CapabilityRouter,
    InputKind,
)


@dataclass(frozen=True, slots=True)
class WorkspaceRunOutcome:
    created_enrichment_ids: tuple[str, ...]
    projection: SubjectEnrichmentView


@dataclass(frozen=True, slots=True)
class WorkspaceBatchItem:
    subject: SubjectRef
    input_path: Path | None = None
    structured_input: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceBatchFailure:
    subject: SubjectRef
    error: str


@dataclass(frozen=True, slots=True)
class WorkspaceBatchOutcome:
    requested: int
    completed: int
    created_enrichment_ids: tuple[str, ...]
    failures: tuple[WorkspaceBatchFailure, ...]


class WorkspaceBatchRun:
    """Async run plus thread-safe per-subject state for a dedicated batch screen."""

    def __init__(self, run, states: dict[str, str], lock: Lock) -> None:
        self._run = run
        self._states = states
        self._lock = lock

    @property
    def progress(self):
        return self._run.progress

    @property
    def done(self) -> bool:
        return self._run.done

    @property
    def item_states(self) -> dict[str, str]:
        with self._lock:
            return dict(self._states)

    def cancel(self) -> None:
        self._run.cancel()

    def result(self, timeout: float | None = None) -> WorkspaceBatchOutcome:
        return self._run.result(timeout)


class EnrichmentWorkspaceService:
    """Application-owned façade used by photo, sound, video and document workspaces."""

    def __init__(
        self,
        database_path: Path,
        router: CapabilityRouter,
        *,
        id_factory,
        clock_us=None,
    ) -> None:
        self._router = router
        self._translation = CapabilityTranslationService(
            database_path, id_factory=id_factory, clock_us=clock_us
        )
        self._store = CanonicalEnrichmentService(database_path)
        self._projection = EnrichmentProjectionService(database_path)
        self._execution_pool = CapabilityExecutionPool(max_workers=2)

    def capabilities_for(self, input_kind: InputKind):
        return compatible_capabilities(self._router.discover(), input_kind)

    @property
    def capability_router(self) -> CapabilityRouter:
        return self._router

    def descriptor(self, capability_id: str) -> CapabilityDescriptor:
        for descriptor in self._router.discover():
            if descriptor.capability_id == capability_id:
                return descriptor
        raise KeyError(f"unknown capability: {capability_id}")

    def run(
        self,
        subject: SubjectRef,
        *,
        capability_id: str,
        input_kind: InputKind,
        input_path: Path | None = None,
        structured_input: Mapping[str, Any] | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> WorkspaceRunOutcome:
        descriptor = self.descriptor(capability_id)
        if input_kind not in descriptor.inputs:
            raise ValueError(f"{capability_id} does not accept {input_kind.value} input")
        normalized_parameters = validate_parameters(descriptor.parameters, parameters or {})
        request = CapabilityRequest(
            capability_id=capability_id,
            subject_public_id=subject.public_id,
            input_kind=input_kind,
            input_path=input_path,
            structured_input=structured_input,
            parameters=normalized_parameters,
        )
        result = self._router.execute(request)
        translated = self._translation.translate(subject, result)
        return WorkspaceRunOutcome(
            translated.enrichment_ids,
            self._projection.for_subject(subject, include_rejected=True),
        )

    def run_async(
        self,
        subject: SubjectRef,
        *,
        capability_id: str,
        input_kind: InputKind,
        input_path: Path | None = None,
        structured_input: Mapping[str, Any] | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> AsyncCapabilityRun[WorkspaceRunOutcome]:
        """Run a capability away from the GUI thread with cooperative cancellation.

        Engines may optionally expose ``execute_with_context(request, cancellation, progress)``.
        Existing engines remain compatible and receive truthful coarse progress.
        """
        descriptor = self.descriptor(capability_id)
        if input_kind not in descriptor.inputs:
            raise ValueError(f"{capability_id} does not accept {input_kind.value} input")
        normalized_parameters = validate_parameters(descriptor.parameters, parameters or {})
        request = CapabilityRequest(
            capability_id=capability_id,
            subject_public_id=subject.public_id,
            input_kind=input_kind,
            input_path=input_path,
            structured_input=structured_input,
            parameters=normalized_parameters,
        )

        def operation(cancellation, progress):
            progress(1, 3, "Running capability")
            engine_execute = getattr(self._router, "execute_with_context", None)
            if callable(engine_execute):
                result = engine_execute(request, cancellation=cancellation, progress=progress)
            else:
                cancellation.raise_if_requested()
                result = self._router.execute(request)
            cancellation.raise_if_requested()
            progress(2, 3, "Saving canonical enrichment")
            translated = self._translation.translate(subject, result)
            cancellation.raise_if_requested()
            return WorkspaceRunOutcome(
                translated.enrichment_ids,
                self._projection.for_subject(subject, include_rejected=True),
            )

        run_key = f"{subject.subject_type.value}:{subject.public_id}:{capability_id}"
        return self._execution_pool.submit(operation, run_key=run_key)

    def run_batch_async(
        self,
        items: tuple[WorkspaceBatchItem, ...],
        *,
        capability_id: str,
        input_kind: InputKind,
        parameters: Mapping[str, Any] | None = None,
        max_parallel: int = 4,
    ) -> WorkspaceBatchRun:
        """Run one capability concurrently with per-item failure isolation."""
        if not items:
            raise ValueError("at least one media item is required")
        subjects = tuple(item.subject for item in items)
        if len(set(subjects)) != len(subjects):
            raise ValueError("batch subjects must be unique")
        descriptor = self.descriptor(capability_id)
        if input_kind not in descriptor.inputs:
            raise ValueError(f"{capability_id} does not accept {input_kind.value} input")
        normalized_parameters = validate_parameters(descriptor.parameters, parameters or {})
        if max_parallel < 1 or max_parallel > 16:
            raise ValueError("max_parallel must be between 1 and 16")
        state_lock = Lock()
        states = {item.subject.public_id: "Queued" for item in items}

        def set_state(item: WorkspaceBatchItem, value: str) -> None:
            with state_lock:
                states[item.subject.public_id] = value

        def execute_item(item, cancellation):
            cancellation.raise_if_requested()
            set_state(item, "Running")
            request = CapabilityRequest(
                capability_id=capability_id,
                subject_public_id=item.subject.public_id,
                input_kind=input_kind,
                input_path=item.input_path,
                structured_input=item.structured_input,
                parameters=normalized_parameters,
            )
            engine_execute = getattr(self._router, "execute_with_context", None)
            try:
                if callable(engine_execute):
                    result = engine_execute(
                        request,
                        cancellation=cancellation,
                        progress=lambda _current, _total, message: set_state(item, message),
                    )
                else:
                    result = self._router.execute(request)
                cancellation.raise_if_requested()
                translated = self._translation.translate(item.subject, result)
                set_state(item, "Succeeded")
                return tuple(translated.enrichment_ids), None
            except InterruptedError:
                set_state(item, "Cancelled")
                raise
            except Exception as exc:
                set_state(item, f"Failed: {exc}")
                return (), WorkspaceBatchFailure(item.subject, str(exc))

        def operation(cancellation, progress):
            created: list[str] = []
            failures: list[WorkspaceBatchFailure] = []
            total = len(items)
            workers = min(max_parallel, total)
            progress(0, total, f"Starting {total} items with {workers} parallel workers")
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="fieldora-media-batch"
            ) as executor:
                futures = {
                    executor.submit(execute_item, item, cancellation): item for item in items
                }
                completed = 0
                for future in as_completed(futures):
                    cancellation.raise_if_requested()
                    enrichment_ids, failure = future.result()
                    created.extend(enrichment_ids)
                    if failure is not None:
                        failures.append(failure)
                    completed += 1
                    progress(
                        completed,
                        total,
                        f"{descriptor.display_name}: {completed}/{total} completed",
                    )
            if failures and len(failures) == total:
                detail = failures[0].error if total == 1 else "every selected item failed"
                raise RuntimeError(f"Batch enrichment failed: {detail}")
            return WorkspaceBatchOutcome(
                requested=total,
                completed=total - len(failures),
                created_enrichment_ids=tuple(created),
                failures=tuple(failures),
            )

        identity = ",".join(
            f"{item.subject.subject_type.value}:{item.subject.public_id}" for item in items
        )
        run = self._execution_pool.submit(
            operation,
            run_key=f"batch:{capability_id}:{identity}",
        )
        return WorkspaceBatchRun(run, states, state_lock)

    def run_region_pipeline_async(
        self,
        subject: SubjectRef,
        *,
        detector_id: str,
        classifier_id: str,
        input_path: Path | None,
        detector_parameters: Mapping[str, Any] | None = None,
        classifier_parameters: Mapping[str, Any] | None = None,
    ) -> AsyncCapabilityRun[WorkspaceRunOutcome]:
        """Run detector → per-box image crop → taxonomy classifier."""
        if input_path is None:
            raise ValueError("region classification requires a local photo")
        detector = self.descriptor(detector_id)
        classifier = self.descriptor(classifier_id)
        if CanonicalShape.BOUNDING_BOX.value not in detector.outputs:
            raise ValueError(f"{detector_id} does not produce bounding boxes")
        if CanonicalShape.TAXONOMY_CANDIDATE.value not in classifier.outputs:
            raise ValueError(f"{classifier_id} does not produce taxonomy candidates")
        detector_values = validate_parameters(detector.parameters, detector_parameters or {})
        classifier_values = validate_parameters(
            classifier.parameters, classifier_parameters or {}
        )

        def operation(cancellation, progress):
            from PIL import Image

            progress(1, 3, f"Detecting regions with {detector.display_name}")
            detected = self._router.execute(
                CapabilityRequest(
                    detector_id,
                    subject.public_id,
                    InputKind.PHOTO,
                    input_path=input_path,
                    parameters=detector_values,
                )
            )
            cancellation.raise_if_requested()
            detected_translation = self._translation.translate(subject, detected)
            boxes = tuple(
                candidate
                for candidate in detected.candidates
                if candidate.shape is CanonicalShape.BOUNDING_BOX
            )
            if not boxes:
                raise RuntimeError("The detector found no regions to classify")
            progress(2, 3, f"Classifying {len(boxes)} detected region(s)")
            classified_ids: list[str] = []
            with Image.open(input_path) as image, TemporaryDirectory(
                prefix="aperture-region-pipeline-"
            ) as temporary_name:
                width, height = image.size
                for index, box in enumerate(boxes, start=1):
                    cancellation.raise_if_requested()
                    target = dict(box.target)
                    x = float(target.get("x", 0))
                    y = float(target.get("y", 0))
                    box_width = float(target.get("width", 0))
                    box_height = float(target.get("height", 0))
                    if target.get("normalized", False):
                        x, box_width = x * width, box_width * width
                        y, box_height = y * height, box_height * height
                    left, top = max(0, int(x)), max(0, int(y))
                    right = min(width, int(x + box_width))
                    bottom = min(height, int(y + box_height))
                    if right <= left or bottom <= top:
                        continue
                    crop_path = Path(temporary_name) / f"region-{index}.png"
                    image.crop((left, top, right, bottom)).save(crop_path)
                    result = self._router.execute(
                        CapabilityRequest(
                            classifier_id,
                            subject.public_id,
                            InputKind.PHOTO,
                            input_path=crop_path,
                            parameters=classifier_values,
                        )
                    )
                    linked = tuple(
                        CanonicalCandidate(
                            candidate.shape,
                            candidate.value,
                            candidate.confidence,
                            {
                                **dict(candidate.target),
                                **target,
                                "region_index": index,
                                "detector_capability_id": detector_id,
                                "detector_confidence": box.confidence,
                                "detector_label": box.value.get("label"),
                            },
                            candidate.external_id,
                        )
                        for candidate in result.candidates
                    )
                    translated = self._translation.translate(
                        subject,
                        CapabilityResult(
                            capability_id=result.capability_id,
                            producer_name=result.producer_name,
                            producer_version=result.producer_version,
                            candidates=linked,
                            run_id=result.run_id,
                            source_name=result.source_name,
                            source_version=result.source_version,
                            source_checksum=result.source_checksum,
                            attribution=result.attribution,
                            licence=result.licence,
                            diagnostics={
                                **dict(result.diagnostics),
                                "pipeline_detector": detector_id,
                                "region_index": index,
                            },
                            artifacts=result.artifacts,
                        ),
                    )
                    classified_ids.extend(translated.enrichment_ids)
            if not classified_ids:
                raise RuntimeError("No detected region produced taxonomy candidates")
            return WorkspaceRunOutcome(
                detected_translation.enrichment_ids + tuple(classified_ids),
                self._projection.for_subject(subject, include_rejected=True),
            )

        run_key = (
            f"{subject.subject_type.value}:{subject.public_id}:"
            f"{detector_id}:{classifier_id}:region-pipeline"
        )
        return self._execution_pool.submit(operation, run_key=run_key)

    def shutdown(self) -> None:
        self._execution_pool.shutdown(wait=False, cancel_futures=True)

    def review(
        self,
        subject: SubjectRef,
        enrichment_id: str,
        status: EnrichmentStatus,
        *,
        reviewer: str,
    ) -> SubjectEnrichmentView:
        record = self._store.get(enrichment_id)
        if (
            record.subject_type != subject.subject_type.value
            or record.subject_public_id != subject.public_id
        ):
            raise ValueError("enrichment does not belong to the requested subject workspace")
        self._store.review(enrichment_id, status, reviewer=reviewer)
        return self._projection.for_subject(subject, include_rejected=True)

    def assign_review(
        self,
        subject: SubjectRef,
        enrichment_id: str,
        *,
        assigned_to: str | None,
        assigned_by: str,
        note: str = "",
    ) -> SubjectEnrichmentView:
        record = self._store.get(enrichment_id)
        if (
            record.subject_type != subject.subject_type.value
            or record.subject_public_id != subject.public_id
        ):
            raise ValueError("enrichment does not belong to the requested subject workspace")
        self._store.assign_review(
            enrichment_id,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            note=note,
        )
        return self._projection.for_subject(subject, include_rejected=True)

    def project(
        self, subject: SubjectRef, *, include_rejected: bool = False
    ) -> SubjectEnrichmentView:
        return self._projection.for_subject(subject, include_rejected=include_rejected)

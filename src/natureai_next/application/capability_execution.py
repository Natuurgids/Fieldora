"""Producer-neutral capability discovery and parameter validation for desktop execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from natureai_next.synthesis_core.contracts import (
    CapabilityDescriptor,
    InputKind,
    ParameterDefinition,
)


@dataclass(frozen=True, slots=True)
class CapabilityChoice:
    descriptor: CapabilityDescriptor
    available: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CapabilityExecutionInput:
    capability_id: str
    input_kind: InputKind
    input_path: Path | None
    parameters: Mapping[str, Any]
    structured_input: Mapping[str, Any] | None = None


def compatible_capabilities(
    descriptors: Sequence[CapabilityDescriptor], input_kind: InputKind
) -> tuple[CapabilityChoice, ...]:
    """Return deterministic capability choices for one subject/input kind."""
    choices = []
    for descriptor in sorted(
        descriptors, key=lambda item: (item.display_name.casefold(), item.capability_id)
    ):
        if input_kind not in descriptor.inputs:
            continue
        choices.append(
            CapabilityChoice(
                descriptor, True, "Available offline" if descriptor.offline else "Available"
            )
        )
    return tuple(choices)


def validate_parameters(
    definitions: Sequence[ParameterDefinition], values: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate and normalize manifest-derived values without producer-specific rules."""
    normalized: dict[str, Any] = {}
    known = {definition.name for definition in definitions}
    unknown = sorted(set(values) - known)
    if unknown:
        raise ValueError(f"unknown parameters: {', '.join(unknown)}")
    for definition in definitions:
        raw = values.get(definition.name, definition.default)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            if definition.required and definition.default is None:
                raise ValueError(f"{definition.name} is required")
            normalized[definition.name] = definition.default
            continue
        value = _coerce(definition, raw)
        if definition.choices and value not in definition.choices:
            allowed = ", ".join(str(item) for item in definition.choices)
            raise ValueError(f"{definition.name} must be one of: {allowed}")
        if isinstance(value, int | float) and not isinstance(value, bool):
            if definition.minimum is not None and value < definition.minimum:
                raise ValueError(f"{definition.name} must be at least {definition.minimum}")
            if definition.maximum is not None and value > definition.maximum:
                raise ValueError(f"{definition.name} must be at most {definition.maximum}")
        normalized[definition.name] = value
    return normalized


def _coerce(definition: ParameterDefinition, raw: Any) -> Any:
    kind = definition.value_type.casefold().strip()
    try:
        if kind in {"string", "text", "path"}:
            return str(raw).strip()
        if kind in {"integer", "int"}:
            if isinstance(raw, bool):
                raise ValueError
            return int(raw)
        if kind in {"number", "float", "double"}:
            value = float(raw)
            if value != value or value in {float("inf"), float("-inf")}:
                raise ValueError
            return value
        if kind in {"boolean", "bool"}:
            if isinstance(raw, bool):
                return raw
            text = str(raw).strip().casefold()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
            raise ValueError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{definition.name} must be {definition.value_type}") from exc
    raise ValueError(f"unsupported parameter type for {definition.name}: {definition.value_type}")


# ---- asynchronous desktop execution -------------------------------------------------
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from enum import StrEnum
from threading import Event, Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class CapabilityRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CapabilityProgress:
    state: CapabilityRunState
    current: int
    total: int | None
    message: str
    error: str | None = None


class CapabilityCancellation:
    """Cooperative cancellation shared by UI and capability engines."""

    def __init__(self) -> None:
        self._event = Event()

    def request(self) -> None:
        self._event.set()

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def raise_if_requested(self) -> None:
        if self.requested:
            raise InterruptedError("capability execution cancelled")


class AsyncCapabilityRun(Generic[T]):
    def __init__(self, cancellation: CapabilityCancellation) -> None:
        self.cancellation = cancellation
        self._lock = Lock()
        self._progress = CapabilityProgress(CapabilityRunState.QUEUED, 0, None, "Queued")
        self._future: Future[T] | None = None

    def _bind(self, future: Future[T]) -> None:
        self._future = future

    def update(
        self,
        state: CapabilityRunState,
        current: int,
        total: int | None,
        message: str,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self._progress = CapabilityProgress(state, current, total, message, error)

    @property
    def progress(self) -> CapabilityProgress:
        with self._lock:
            return self._progress

    @property
    def done(self) -> bool:
        return self._future is not None and self._future.done()

    def cancel(self) -> None:
        self.cancellation.request()
        if self.progress.state in {CapabilityRunState.QUEUED, CapabilityRunState.RUNNING}:
            self.update(
                CapabilityRunState.CANCELLING,
                self.progress.current,
                self.progress.total,
                "Cancelling…",
            )
        if self._future is not None:
            self._future.cancel()

    def result(self, timeout: float | None = None) -> T:
        if self._future is None:
            raise RuntimeError("capability run has not started")
        return self._future.result(timeout=timeout)


class CapabilityExecutionPool:
    """Bounded worker pool with deduplication, cancellation and shutdown safety."""

    def __init__(self, max_workers: int = 2, max_pending: int = 8) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be at least one")
        if max_pending < max_workers:
            raise ValueError("max_pending must be at least max_workers")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="aperture-capability"
        )
        self._max_pending = max_pending
        self._lock = Lock()
        self._active: dict[str, AsyncCapabilityRun[Any]] = {}
        self._closed = False

    def submit(
        self,
        operation: Callable[[CapabilityCancellation, Callable[[int, int | None, str], None]], T],
        *,
        run_key: str | None = None,
    ) -> AsyncCapabilityRun[T]:
        cancellation = CapabilityCancellation()
        run: AsyncCapabilityRun[T] = AsyncCapabilityRun(cancellation)
        key = run_key or f"anonymous:{id(run)}"
        with self._lock:
            if self._closed:
                raise RuntimeError("capability execution pool is shut down")
            existing = self._active.get(key)
            if existing is not None and not existing.done:
                raise RuntimeError(
                    "an equivalent capability execution is already queued or running"
                )
            if sum(1 for item in self._active.values() if not item.done) >= self._max_pending:
                raise RuntimeError("capability execution queue is full")
            self._active[key] = run

        def report(current: int, total: int | None, message: str) -> None:
            cancellation.raise_if_requested()
            if current < 0:
                raise ValueError("progress current cannot be negative")
            if total is not None and (total < 0 or current > total):
                raise ValueError("progress current cannot exceed total")
            run.update(CapabilityRunState.RUNNING, current, total, message)

        def execute() -> T:
            try:
                cancellation.raise_if_requested()
                run.update(CapabilityRunState.RUNNING, 0, 3, "Preparing capability request")
                value = operation(cancellation, report)
                cancellation.raise_if_requested()
                run.update(CapabilityRunState.SUCCEEDED, 3, 3, "Enrichment complete")
                return value
            except InterruptedError:
                run.update(
                    CapabilityRunState.CANCELLED,
                    run.progress.current,
                    run.progress.total,
                    "Cancelled",
                )
                raise
            except Exception as exc:
                run.update(
                    CapabilityRunState.FAILED,
                    run.progress.current,
                    run.progress.total,
                    "Enrichment failed",
                    str(exc),
                )
                raise
            finally:
                with self._lock:
                    self._active.pop(key, None)

        try:
            future = self._executor.submit(execute)
        except Exception:
            with self._lock:
                self._active.pop(key, None)
            raise
        run._bind(future)
        return run

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for run in self._active.values() if not run.done)

    def cancel_all(self) -> int:
        with self._lock:
            runs = tuple(self._active.values())
        for run in runs:
            run.cancel()
        return len(runs)

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            runs = tuple(self._active.values()) if cancel_futures else ()
        for run in runs:
            run.cancel()
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)

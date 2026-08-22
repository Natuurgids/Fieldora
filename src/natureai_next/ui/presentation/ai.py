"""GUI-independent AI administration and embedding state."""

from __future__ import annotations

from dataclasses import dataclass

from natureai_next.domain.ai import ProviderDiagnostics


@dataclass(frozen=True, slots=True)
class AIState:
    diagnostics: tuple[ProviderDiagnostics, ...] = ()
    active_model: str | None = None
    embedding_pending: int = 0
    busy: bool = False
    error: str | None = None


class AIPresentationModel:
    def __init__(self) -> None:
        self._state = AIState()

    @property
    def state(self) -> AIState:
        return self._state

    def diagnostics_loaded(self, diagnostics: tuple[ProviderDiagnostics, ...]) -> None:
        self._state = AIState(
            diagnostics, self._state.active_model, self._state.embedding_pending, False, None
        )

    def embedding_status(self, active_model: str | None, pending: int, busy: bool) -> None:
        if pending < 0:
            raise ValueError("pending embedding count cannot be negative")
        self._state = AIState(self._state.diagnostics, active_model, pending, busy, None)

    def failed(self, message: str) -> None:
        self._state = AIState(
            self._state.diagnostics,
            self._state.active_model,
            self._state.embedding_pending,
            False,
            message,
        )

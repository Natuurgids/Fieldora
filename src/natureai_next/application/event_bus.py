"""Typed in-process domain event dispatch for capability integration."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: str
    aggregate_public_id: str | None
    payload: dict[str, object]
    schema_version: int = 1


EventHandler = Callable[[DomainEvent], None]


class DomainEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    def publish(self, event: DomainEvent) -> tuple[Exception, ...]:
        errors: list[Exception] = []
        for handler in tuple(self._handlers.get(event.event_type, ())):
            try:
                handler(event)
            except Exception as exc:  # subscriber failures are isolated
                errors.append(exc)
        return tuple(errors)

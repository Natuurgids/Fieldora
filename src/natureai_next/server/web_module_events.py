"""Typed ownership declarations for cross-module browser events."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from natureai_next.server.web_module_contracts import WebModuleRegistry, foundation_registry


class WebModuleEventError(ValueError):
    """Raised when an event-boundary declaration is invalid."""


def _token(value: str, kind: str) -> str:
    token = value.strip()
    if not token:
        raise WebModuleEventError(f"{kind} may not be blank")
    return token


@dataclass(frozen=True, slots=True)
class WebModuleEventSpec:
    """One declared cross-module event producer and its known consumers."""

    event_name: str
    producer_module_id: str
    consumer_module_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        event_name = _token(self.event_name, "event name")
        producer = _token(self.producer_module_id, "producer module_id")
        consumers = tuple(
            _token(value, "consumer module_id") for value in self.consumer_module_ids
        )
        if len(set(consumers)) != len(consumers):
            raise WebModuleEventError(
                f"event {event_name!r} declares duplicate consumers"
            )
        object.__setattr__(self, "event_name", event_name)
        object.__setattr__(self, "producer_module_id", producer)
        object.__setattr__(self, "consumer_module_ids", consumers)


class WebModuleEventRegistry:
    """Validated event-boundary declarations against the module registry."""

    def __init__(
        self,
        modules: WebModuleRegistry,
        events: Iterable[WebModuleEventSpec] = (),
    ) -> None:
        self._modules = modules
        self._events: dict[str, WebModuleEventSpec] = {}
        for event in events:
            self.register(event)

    def register(self, event: WebModuleEventSpec) -> None:
        if not isinstance(event, WebModuleEventSpec):
            raise WebModuleEventError(
                "event registry accepts WebModuleEventSpec instances only"
            )
        if event.event_name in self._events:
            owner = self._events[event.event_name].producer_module_id
            raise WebModuleEventError(
                f"event {event.event_name!r} is already produced by {owner!r}"
            )
        module_ids = set(self._modules.as_mapping())
        if event.producer_module_id not in module_ids:
            raise WebModuleEventError(
                f"event {event.event_name!r} has unknown producer "
                f"{event.producer_module_id!r}"
            )
        unknown_consumers = [
            module_id
            for module_id in event.consumer_module_ids
            if module_id not in module_ids
        ]
        if unknown_consumers:
            raise WebModuleEventError(
                f"event {event.event_name!r} has unknown consumers "
                f"{unknown_consumers!r}"
            )
        self._events[event.event_name] = event

    def event(self, event_name: str) -> WebModuleEventSpec | None:
        return self._events.get(event_name.strip())

    def as_mapping(self) -> Mapping[str, WebModuleEventSpec]:
        return dict(self._events)


FOUNDATION_WEB_MODULE_EVENTS: tuple[WebModuleEventSpec, ...] = (
    WebModuleEventSpec(
        "fieldora:project-context-changed",
        "projects.core",
        ("capacity", "research.dossiers", "dossiers.workspace"),
    ),
)


def foundation_event_registry(
    modules: WebModuleRegistry | None = None,
) -> WebModuleEventRegistry:
    """Return validated production event ownership for evidenced boundaries."""

    return WebModuleEventRegistry(modules or foundation_registry(), FOUNDATION_WEB_MODULE_EVENTS)

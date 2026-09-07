from __future__ import annotations

import pytest

from natureai_next.server.dossier_module_web import _DOSSIER_MODULE_PATCH
from natureai_next.server.project_capacity_integration_web import (
    _PROJECT_CAPACITY_INTEGRATION_PATCH,
)
from natureai_next.server.project_context_provider_web import (
    _PROJECT_CONTEXT_PROVIDER_PATCH,
)
from natureai_next.server.project_creation_module_web import _PROJECT_CREATION_MODULE_PATCH
from natureai_next.server.project_research_integration_web import (
    _PROJECT_RESEARCH_INTEGRATION_PATCH,
)
from natureai_next.server.web_module_contracts import WebModuleRegistry, WebModuleSpec
from natureai_next.server.web_module_events import (
    WebModuleEventError,
    WebModuleEventRegistry,
    WebModuleEventSpec,
    foundation_event_registry,
)


def _modules() -> WebModuleRegistry:
    return WebModuleRegistry(
        (
            WebModuleSpec("producer", "/producer", "Producer"),
            WebModuleSpec("consumer.a", "/consumer-a", "Consumer A"),
            WebModuleSpec("consumer.b", "/consumer-b", "Consumer B"),
        )
    )


def test_event_registry_records_one_producer_and_known_consumers() -> None:
    event = WebModuleEventSpec(
        "fieldora:example-changed",
        "producer",
        ("consumer.a", "consumer.b"),
    )
    registry = WebModuleEventRegistry(_modules(), (event,))

    resolved = registry.event("fieldora:example-changed")
    assert resolved is event
    assert resolved.producer_module_id == "producer"
    assert resolved.consumer_module_ids == ("consumer.a", "consumer.b")
    assert registry.as_mapping() == {"fieldora:example-changed": event}


def test_event_spec_normalizes_tokens_and_rejects_duplicate_consumers() -> None:
    event = WebModuleEventSpec(
        " fieldora:example-changed ",
        " producer ",
        (" consumer.a ",),
    )
    assert event.event_name == "fieldora:example-changed"
    assert event.producer_module_id == "producer"
    assert event.consumer_module_ids == ("consumer.a",)

    with pytest.raises(WebModuleEventError, match="duplicate consumers"):
        WebModuleEventSpec(
            "fieldora:duplicate",
            "producer",
            ("consumer.a", "consumer.a"),
        )


def test_event_registry_rejects_duplicate_producer_declaration() -> None:
    registry = WebModuleEventRegistry(
        _modules(),
        (WebModuleEventSpec("fieldora:example-changed", "producer"),),
    )

    with pytest.raises(WebModuleEventError, match="already produced"):
        registry.register(
            WebModuleEventSpec("fieldora:example-changed", "consumer.a")
        )


def test_event_registry_rejects_unknown_producer_or_consumer() -> None:
    modules = _modules()

    with pytest.raises(WebModuleEventError, match="unknown producer"):
        WebModuleEventRegistry(
            modules,
            (WebModuleEventSpec("fieldora:bad-producer", "missing"),),
        )

    with pytest.raises(WebModuleEventError, match="unknown consumers"):
        WebModuleEventRegistry(
            modules,
            (
                WebModuleEventSpec(
                    "fieldora:bad-consumer",
                    "producer",
                    ("consumer.a", "missing"),
                ),
            ),
        )


def test_event_registry_rejects_non_event_specs() -> None:
    registry = WebModuleEventRegistry(_modules())

    with pytest.raises(WebModuleEventError, match="WebModuleEventSpec"):
        registry.register(object())  # type: ignore[arg-type]


def test_foundation_project_context_event_matches_managed_producer_and_consumers() -> None:
    event = foundation_event_registry().event("fieldora:project-context-changed")

    assert event is not None
    assert event.producer_module_id == "projects.core"
    assert event.consumer_module_ids == (
        "capacity",
        "research.dossiers",
        "dossiers.workspace",
    )

    producer = _PROJECT_CONTEXT_PROVIDER_PATCH.decode("utf-8")
    assert 'const moduleId="projects.core"' in producer
    assert 'new CustomEvent("fieldora:project-context-changed"' in producer

    capacity = _PROJECT_CAPACITY_INTEGRATION_PATCH.decode("utf-8")
    assert 'const ownerModule="capacity"' in capacity
    assert 'addEventListener("fieldora:project-context-changed"' in capacity

    research = _PROJECT_RESEARCH_INTEGRATION_PATCH.decode("utf-8")
    assert 'const ownerModule="research.dossiers"' in research
    assert 'addEventListener("fieldora:project-context-changed"' in research

    dossiers = _DOSSIER_MODULE_PATCH.decode("utf-8")
    assert 'const moduleId="dossiers.workspace"' in dossiers
    assert 'addEventListener("fieldora:project-context-changed"' in dossiers


def test_foundation_project_create_request_matches_research_producer_and_projects_consumer() -> None:
    event = foundation_event_registry().event("fieldora:projects-create-requested")

    assert event is not None
    assert event.producer_module_id == "research.dossiers"
    assert event.consumer_module_ids == ("projects.core",)

    research = _PROJECT_RESEARCH_INTEGRATION_PATCH.decode("utf-8")
    assert 'const ownerModule="research.dossiers"' in research
    assert 'new CustomEvent("fieldora:projects-create-requested"' in research

    projects = _PROJECT_CREATION_MODULE_PATCH.decode("utf-8")
    assert 'const moduleId="projects.core"' in projects
    assert 'addEventListener("fieldora:projects-create-requested",handleCreateRequest)' in projects

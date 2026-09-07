from __future__ import annotations

import pytest

from natureai_next.server.web_module_contracts import WebModuleRegistry, WebModuleSpec
from natureai_next.server.web_module_events import (
    WebModuleEventError,
    WebModuleEventRegistry,
    WebModuleEventSpec,
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

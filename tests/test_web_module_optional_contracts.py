from __future__ import annotations

import pytest

from natureai_next.server.web_module_contracts import (
    WebModuleContractError,
    WebModuleRegistry,
    WebModuleSpec,
)


def test_optional_contract_can_be_absent_without_failing_registry_validation() -> None:
    consumer = WebModuleSpec(
        "portfolio",
        "/portfolio",
        "Portfolio",
        optional_contracts=("projects.toolbar.extend",),
    )
    registry = WebModuleRegistry((consumer,))

    registry.validate_dependencies()
    registry.validate_contracts()

    assert registry.module("portfolio").optional_contracts == (
        "projects.toolbar.extend",
    )
    assert registry.contract_provider("projects.toolbar.extend") is None


def test_optional_contract_resolves_replacement_provider_when_present() -> None:
    replacement = WebModuleSpec(
        "projects.replacement",
        "/projects",
        "Replacement Projects",
        provides_contracts=("projects.toolbar.extend",),
    )
    consumer = WebModuleSpec(
        "portfolio",
        "/portfolio",
        "Portfolio",
        optional_contracts=("projects.toolbar.extend",),
    )
    registry = WebModuleRegistry((replacement, consumer))

    registry.validate_contracts()

    provider = registry.contract_provider("projects.toolbar.extend")
    assert provider is not None
    assert provider.module_id == "projects.replacement"


def test_contract_cannot_be_declared_as_both_required_and_optional() -> None:
    with pytest.raises(
        WebModuleContractError,
        match="cannot declare contracts as both required and optional",
    ):
        WebModuleSpec(
            "portfolio",
            "/portfolio",
            "Portfolio",
            requires_contracts=("projects.context.select",),
            optional_contracts=("projects.context.select",),
        )

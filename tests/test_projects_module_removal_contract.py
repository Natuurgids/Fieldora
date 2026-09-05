from __future__ import annotations

from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleRegistry,
)


_PROJECT_CONTRACTS = {
    "projects.list.read",
    "projects.context.select",
    "projects.toolbar.extend",
}


def test_projects_removal_preserves_unrelated_module_registry() -> None:
    projects = next(spec for spec in FOUNDATION_WEB_MODULES if spec.module_id == "projects.core")
    project_consumers = {
        spec.module_id
        for spec in FOUNDATION_WEB_MODULES
        if _PROJECT_CONTRACTS.intersection(spec.requires_contracts)
    }

    assert project_consumers == {
        "portfolio",
        "capacity",
        "research.dossiers",
        "dossiers.workspace",
    }

    remaining = tuple(
        spec
        for spec in FOUNDATION_WEB_MODULES
        if spec.module_id != projects.module_id
        and spec.module_id not in project_consumers
    )
    registry = WebModuleRegistry(remaining)

    registry.validate_dependencies()
    registry.validate_contracts()

    assert tuple(registry.as_mapping()) == (
        "home.activity",
        "library.catalog",
        "observations.core",
        "knowledge.center",
        "admin.shell",
    )
    assert registry.resolve("/projects") is None
    assert registry.resolve("/home").module_id == "home.activity"
    assert registry.resolve("/library").module_id == "library.catalog"
    assert registry.resolve("/observations").module_id == "observations.core"
    assert registry.resolve("/knowledge").module_id == "knowledge.center"
    assert registry.resolve("/administration").module_id == "admin.shell"


def test_unrelated_modules_have_no_hidden_projects_contract_requirement() -> None:
    unrelated = {
        "home.activity",
        "library.catalog",
        "observations.core",
        "knowledge.center",
        "admin.shell",
    }

    for spec in FOUNDATION_WEB_MODULES:
        if spec.module_id not in unrelated:
            continue
        assert not _PROJECT_CONTRACTS.intersection(spec.requires_contracts)
        assert "projects.core" not in spec.dependencies

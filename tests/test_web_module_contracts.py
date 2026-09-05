from __future__ import annotations

import pytest

from natureai_next.server.web_module_contracts import (
    FOUNDATION_WEB_MODULES,
    WebModuleContractError,
    WebModuleRegistry,
    WebModuleSpec,
    foundation_registry,
    normalize_route,
)


def test_normalize_route_removes_shell_state_and_trailing_slash() -> None:
    assert normalize_route(" /projects/?tab=tasks#active ") == "/projects"
    assert normalize_route("/") == "/"


def test_foundation_registry_has_separate_projects_and_portfolio_ownership() -> None:
    registry = foundation_registry()

    projects = registry.resolve("/projects")
    portfolio = registry.resolve("/portfolio")

    assert projects is not None
    assert projects.module_id == "projects.core"
    assert projects.provides_contracts == (
        "projects.list.read",
        "projects.context.select",
        "projects.toolbar.extend",
    )
    assert portfolio is not None
    assert portfolio.module_id == "portfolio"
    assert portfolio.dependencies == ()
    assert portfolio.requires_contracts == (
        "projects.list.read",
        "projects.context.select",
    )
    assert registry.contract_provider("projects.list.read") is projects
    assert registry.contract_provider("projects.context.select") is projects
    assert registry.contract_provider("projects.toolbar.extend") is projects


def test_project_integrations_are_owned_by_bounded_modules() -> None:
    registry = foundation_registry()

    projects = registry.resolve("/projects")
    capacity = registry.resolve("/capacity")
    research = registry.resolve("/research")
    dossiers = registry.resolve("/dossiers")

    assert projects is not None
    assert capacity is not None
    assert research is not None
    assert dossiers is not None
    assert capacity.module_id == "capacity"
    assert capacity.dependencies == ()
    assert capacity.requires_contracts == (
        "projects.context.select",
        "projects.toolbar.extend",
    )
    assert research.module_id == "research.dossiers"
    assert research.dependencies == ()
    assert research.requires_contracts == (
        "projects.context.select",
        "projects.toolbar.extend",
    )
    assert dossiers.module_id == "dossiers.workspace"
    assert dossiers.dependencies == ()
    assert dossiers.requires_contracts == ("projects.context.select",)
    assert dossiers.owns_actions == (
        "dossiers.workspace.view",
        "dossiers.create",
        "dossiers.review.create",
    )
    assert registry.action_owner("capacity.project.allocations.view") is capacity
    assert registry.action_owner("research.project.records.view") is research
    assert registry.action_owner("dossiers.workspace.view") is dossiers
    assert registry.action_owner("dossiers.create") is dossiers
    assert registry.action_owner("dossiers.review.create") is dossiers
    assert "capacity.project.allocations.view" not in projects.owns_actions
    assert "research.project.records.view" not in projects.owns_actions
    assert "dossiers.workspace.view" not in projects.owns_actions
    assert "dossiers.create" not in projects.owns_actions
    assert "dossiers.review.create" not in projects.owns_actions


def test_registry_rejects_duplicate_route_ownership() -> None:
    registry = WebModuleRegistry(
        (WebModuleSpec("projects.core", "/projects", "Projects"),)
    )

    with pytest.raises(WebModuleContractError, match="already owned"):
        registry.register(WebModuleSpec("portfolio", "/projects", "Portfolio"))


def test_registry_rejects_duplicate_action_ownership() -> None:
    registry = WebModuleRegistry(
        (
            WebModuleSpec(
                "projects.core",
                "/projects",
                "Projects",
                owns_actions=("project.open",),
            ),
        )
    )

    with pytest.raises(WebModuleContractError, match="already owned"):
        registry.register(
            WebModuleSpec(
                "portfolio",
                "/portfolio",
                "Portfolio",
                owns_actions=("project.open",),
            )
        )


def test_registry_rejects_unknown_dependencies() -> None:
    registry = WebModuleRegistry(
        (
            WebModuleSpec(
                "portfolio",
                "/portfolio",
                "Portfolio",
                dependencies=("projects.core",),
            ),
        )
    )

    with pytest.raises(WebModuleContractError, match="unknown module dependencies"):
        registry.validate_dependencies()


def test_registry_rejects_missing_contract_provider() -> None:
    registry = WebModuleRegistry(
        (
            WebModuleSpec(
                "portfolio",
                "/portfolio",
                "Portfolio",
                requires_contracts=("projects.list.read",),
            ),
        )
    )

    with pytest.raises(WebModuleContractError, match="missing contract providers"):
        registry.validate_contracts()


def test_registry_rejects_duplicate_contract_provider() -> None:
    registry = WebModuleRegistry(
        (
            WebModuleSpec(
                "projects.core",
                "/projects",
                "Projects",
                provides_contracts=("projects.list.read",),
            ),
        )
    )

    with pytest.raises(WebModuleContractError, match="already provided"):
        registry.register(
            WebModuleSpec(
                "projects.replacement",
                "/replacement-projects",
                "Replacement Projects",
                provides_contracts=("projects.list.read",),
            )
        )


def test_contract_consumer_can_bind_to_replacement_provider() -> None:
    replacement = WebModuleSpec(
        "projects.replacement",
        "/projects",
        "Projects replacement",
        provides_contracts=("projects.list.read", "projects.context.select"),
    )
    portfolio = WebModuleSpec(
        "portfolio",
        "/portfolio",
        "Portfolio",
        requires_contracts=("projects.list.read", "projects.context.select"),
    )
    registry = WebModuleRegistry((replacement, portfolio))

    registry.validate_dependencies()
    registry.validate_contracts()

    assert registry.contract_provider("projects.list.read") is replacement
    assert registry.contract_provider("projects.context.select") is replacement
    assert portfolio.dependencies == ()


def test_capacity_can_bind_to_replacement_projects_contract_provider() -> None:
    replacement = WebModuleSpec(
        "projects.replacement",
        "/projects",
        "Projects replacement",
        provides_contracts=("projects.context.select", "projects.toolbar.extend"),
    )
    capacity = WebModuleSpec(
        "capacity",
        "/capacity",
        "Capacity",
        requires_contracts=("projects.context.select", "projects.toolbar.extend"),
    )
    registry = WebModuleRegistry((replacement, capacity))

    registry.validate_dependencies()
    registry.validate_contracts()

    assert registry.contract_provider("projects.context.select") is replacement
    assert registry.contract_provider("projects.toolbar.extend") is replacement
    assert capacity.dependencies == ()


def test_research_can_bind_to_replacement_projects_contract_provider() -> None:
    replacement = WebModuleSpec(
        "projects.replacement",
        "/projects",
        "Projects replacement",
        provides_contracts=("projects.context.select", "projects.toolbar.extend"),
    )
    research = WebModuleSpec(
        "research.dossiers",
        "/research",
        "Research",
        requires_contracts=("projects.context.select", "projects.toolbar.extend"),
    )
    registry = WebModuleRegistry((replacement, research))

    registry.validate_dependencies()
    registry.validate_contracts()

    assert registry.contract_provider("projects.context.select") is replacement
    assert registry.contract_provider("projects.toolbar.extend") is replacement
    assert research.dependencies == ()


def test_dossiers_can_bind_to_replacement_projects_context_provider() -> None:
    replacement = WebModuleSpec(
        "projects.replacement",
        "/projects",
        "Projects replacement",
        provides_contracts=("projects.context.select",),
    )
    dossiers = WebModuleSpec(
        "dossiers.workspace",
        "/dossiers",
        "Dossiers",
        owns_actions=(
            "dossiers.workspace.view",
            "dossiers.create",
            "dossiers.review.create",
        ),
        requires_contracts=("projects.context.select",),
    )
    registry = WebModuleRegistry((replacement, dossiers))

    registry.validate_dependencies()
    registry.validate_contracts()

    assert registry.contract_provider("projects.context.select") is replacement
    assert dossiers.dependencies == ()
    assert "projects.list.read" not in dossiers.requires_contracts
    assert "projects.toolbar.extend" not in dossiers.requires_contracts


def test_capability_projection_only_controls_visibility() -> None:
    registry = WebModuleRegistry(
        (
            WebModuleSpec("home.activity", "/home", "Home"),
            WebModuleSpec(
                "admin.shell",
                "/administration",
                "Administration",
                capability="administration.view",
            ),
        )
    )

    assert tuple(spec.module_id for spec in registry.visible_specs(())) == (
        "home.activity",
    )
    assert tuple(
        spec.module_id
        for spec in registry.visible_specs(("administration.view",))
    ) == ("home.activity", "admin.shell")

    # The registry continues to resolve the protected module even when it is not
    # visible. Server/API authorization remains an independent requirement.
    assert registry.resolve("/administration").module_id == "admin.shell"


def test_foundation_specs_have_unique_module_ids_and_routes() -> None:
    module_ids = [spec.module_id for spec in FOUNDATION_WEB_MODULES]
    routes = [spec.route for spec in FOUNDATION_WEB_MODULES]

    assert len(module_ids) == len(set(module_ids))
    assert len(routes) == len(set(routes))

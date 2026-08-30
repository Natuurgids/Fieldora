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
    assert portfolio is not None
    assert portfolio.module_id == "portfolio"
    assert portfolio.dependencies == ("projects.core",)


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
    # visible.  Server/API authorization remains an independent requirement.
    assert registry.resolve("/administration").module_id == "admin.shell"


def test_foundation_specs_have_unique_module_ids_and_routes() -> None:
    module_ids = [spec.module_id for spec in FOUNDATION_WEB_MODULES]
    routes = [spec.route for spec in FOUNDATION_WEB_MODULES]

    assert len(module_ids) == len(set(module_ids))
    assert len(routes) == len(set(routes))

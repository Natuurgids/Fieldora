from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.portfolio_module_web import patch_portfolio_module_response
from natureai_next.server.web_module_contract_runtime import runtime_contract_manifest
from natureai_next.server.web_module_contracts import foundation_registry


def test_portfolio_routes_errors_through_notifications_contract() -> None:
    portfolio = foundation_registry().resolve("/portfolio")
    assert portfolio is not None
    assert portfolio.requires_contracts == (
        "auth.current-user",
        "navigation.navigate",
        "notifications.publish",
        "projects.list.read",
        "projects.context.select",
    )

    by_id = {item["module_id"]: item for item in runtime_contract_manifest()}
    assert by_id["portfolio"]["requires_contracts"] == [
        "auth.current-user",
        "navigation.navigate",
        "notifications.publish",
        "projects.list.read",
        "projects.context.select",
    ]

    script = patch_portfolio_module_response(
        "/app.js", ApiResponse(200, b"", "text/javascript; charset=utf-8")
    ).body.decode("utf-8")
    assert 'resolve?.("notifications.publish")' in script
    assert 'notifications()?.publish?.(String(message),{level:"error",source_module:moduleId})' in script
    assert 'new CustomEvent("fieldora:module-error"' not in script

from __future__ import annotations

from natureai_next.server import modular_shell_composition
from natureai_next.server.modular_shell_web import modular_shell_manifest
from natureai_next.server.web_module_contracts import (
    WebModuleRegistry,
    WebModuleSpec,
    foundation_registry,
)


def test_browser_manifest_contract_metadata_matches_typed_registry() -> None:
    registry = foundation_registry()
    manifest = {item["module_id"]: item for item in modular_shell_manifest()}

    assert set(manifest) == set(registry.as_mapping())
    for module_id, spec in registry.as_mapping().items():
        item = manifest[module_id]
        assert item["provides_contracts"] == list(spec.provides_contracts)
        assert item["requires_contracts"] == list(spec.requires_contracts)
        assert item["optional_contracts"] == list(spec.optional_contracts)

    assert manifest["projects.core"]["provides_contracts"] == [
        "projects.list.read",
        "projects.context.select",
        "projects.toolbar.extend",
    ]
    assert manifest["portfolio"]["requires_contracts"] == [
        "projects.list.read",
        "projects.context.select",
    ]
    assert manifest["projects.core"]["optional_contracts"] == []


def test_custom_registry_bootstrap_preserves_all_contract_metadata() -> None:
    registry = WebModuleRegistry(
        (
            WebModuleSpec(
                "projects.replacement",
                "/projects",
                "Projects replacement",
                owns_actions=("projects.context.select",),
                provides_contracts=("projects.list.read",),
                requires_contracts=("identity.current",),
                optional_contracts=("projects.toolbar.extend",),
            ),
        )
    )

    script = modular_shell_composition.modular_shell_bootstrap(registry).decode("utf-8")

    assert '"module_id":"projects.replacement"' in script
    assert '"owns_actions":["projects.context.select"]' in script
    assert '"provides_contracts":["projects.list.read"]' in script
    assert '"requires_contracts":["identity.current"]' in script
    assert '"optional_contracts":["projects.toolbar.extend"]' in script

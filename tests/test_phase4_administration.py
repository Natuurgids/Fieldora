from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from natureai_next.application.phase4_administration import Phase4AdministrationService


def service(tmp_path: Path) -> Phase4AdministrationService:
    database = tmp_path / "science.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE pm_project_members(project_id TEXT,user_id TEXT,role TEXT)")
    return Phase4AdministrationService(database)


def test_phase4_master_data_and_audit(tmp_path: Path) -> None:
    admin = service(tmp_path)
    party_id = admin.save("parties", {"party_type": "laboratory", "display_name": "North Sea Lab", "email": "lab@example.test"}, actor_id="local-user")
    unit_id = admin.save("units", {"code": "mg", "symbol": "mg", "display_name": "milligram", "quantity_kind": "mass", "factor": 0.000001}, actor_id="local-user")
    instrument_id = admin.save("instruments", {"name": "Precision balance", "instrument_type": "balance", "serial_number": "PB-1", "owner_party_id": party_id}, actor_id="local-user")
    calibration_id = admin.calibrate_instrument(instrument_id, actor_id="local-user", calibrated_at="2026-08-03T10:00:00Z", result="passed", next_due="2027-08-03")
    laboratory_id = admin.save("laboratories", {"display_name": "North Sea Lab", "party_id": party_id, "capabilities": ["haematology", "xray"]}, actor_id="local-user")
    assert {row["unit_id"] for row in admin.list_domain("units")} >= {unit_id}
    assert {row["instrument_id"] for row in admin.list_domain("instruments")} == {instrument_id}
    assert {row["laboratory_id"] for row in admin.list_domain("laboratories")} == {laboratory_id}
    assert calibration_id
    assert any(row["actor_id"] == "local-user" for row in admin.audit_events())


def test_identity_provider_stores_secret_reference_not_secret(tmp_path: Path) -> None:
    admin = service(tmp_path)
    admin.save("identity_providers", {
        "provider_type": "oidc", "display_name": "Organisation SSO", "issuer": "https://identity.example.test",
        "metadata_url": "https://identity.example.test/.well-known/openid-configuration", "client_id": "fieldora",
        "secret_reference": "secret-store://fieldora/organisation-sso", "enabled": True,
    }, actor_id="local-user")
    provider = admin.list_domain("identity_providers")[0]
    assert provider["secret_reference"].startswith("secret-store://")
    assert "client-secret" not in provider["secret_reference"]


def test_asset_rbac_abac_pbac_default_deny_and_explicit_deny(tmp_path: Path) -> None:
    admin = service(tmp_path)
    admin.save_role(code="researcher", display_name="Researcher", permissions=["asset.preview.view"], actor_id="local-user")
    admin.set_asset_security("asset-1", actor_id="local-user", owner_user_id="alice", sensitivity="protected", purposes=["scientific_research"], classifications={"contains_exact_location": "yes"})
    no_policy = admin.evaluate_asset_access(asset_id="asset-1", role_code="researcher", action_code="asset.preview.view", purpose_code="scientific_research")
    assert not no_policy.allowed and "default deny" in no_policy.reason
    admin.save("asset_policies", {"display_name": "Research preview", "effect": "allow", "role_code": "researcher", "action_code": "asset.preview.view", "asset_type": "*", "purpose_code": "scientific_research", "state": "active"}, actor_id="local-user")
    assert admin.evaluate_asset_access(asset_id="asset-1", role_code="researcher", action_code="asset.preview.view", purpose_code="scientific_research").allowed
    wrong_purpose = admin.evaluate_asset_access(asset_id="asset-1", role_code="researcher", action_code="asset.preview.view", purpose_code="public_portal")
    assert not wrong_purpose.allowed
    admin.save("asset_policies", {"display_name": "Deny protected locations", "effect": "deny", "role_code": "researcher", "action_code": "asset.preview.view", "asset_type": "*", "purpose_code": "scientific_research", "conditions": {"contains_exact_location": "yes"}, "priority": 1, "state": "active"}, actor_id="local-user")
    denied = admin.evaluate_asset_access(asset_id="asset-1", role_code="researcher", action_code="asset.preview.view", purpose_code="scientific_research")
    assert not denied.allowed and "explicit deny" in denied.reason


def test_non_admin_cannot_change_configuration(tmp_path: Path) -> None:
    admin = service(tmp_path)
    with pytest.raises(PermissionError):
        admin.save("purposes", {"code": "illegal", "display_name": "Not permitted"}, actor_id="ordinary-user")


def test_scientific_templates_and_transitions_are_managed(tmp_path: Path) -> None:
    admin = service(tmp_path)
    template_id = admin.save("templates", {"template_type": "measurement", "code": "bird-biometry", "display_name": "Bird biometry", "taxon_rule": "class:Aves", "definition": {"items": [{"code": "wing_chord", "unit": "mm"}]}}, actor_id="local-user")
    transition_id = admin.save("workflow_transitions", {"domain": "laboratory", "from_status": "received", "to_status": "in_progress", "required_role": "laboratory_technician", "requires_reason": False}, actor_id="local-user")
    assert {x["template_id"] for x in admin.list_domain("templates")} == {template_id}
    assert {x["transition_id"] for x in admin.list_domain("workflow_transitions")} == {transition_id}

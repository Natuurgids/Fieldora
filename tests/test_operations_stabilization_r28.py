from pathlib import Path

from natureai_next.application.operations_assets import OperationsAssetService
from natureai_next.application.phase4_administration import Phase4AdministrationService


def test_operations_crud_and_audit(tmp_path: Path, monkeypatch):
    db = tmp_path / "science.sqlite3"
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "admin")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    service = OperationsAssetService(db)
    location = service.add_location("building", "B1", "Main Building", actor="admin")
    asset = service.add_asset("CAM-1", "Camera", "camera", "admin", location_id=location, owner_id="admin")
    service.set_asset_image(asset, str(tmp_path / "camera.jpg"), "admin")
    document = service.add_document(asset, "manual", "Manual", str(tmp_path / "manual.pdf"), "admin")
    service.update_asset(asset, actor="admin", status="maintenance", notes="check")
    service.move_asset(asset, None, actor="admin", moved_at="2026-08-05T12:00:00", reason="service")
    assert service.asset(asset, "admin")["status"] == "maintenance"
    assert service.documents(asset, "admin")[0]["id"] == document
    assert any(event["event_type"] == "asset.moved" for event in service.audit_events("admin"))


def test_operations_non_admin_default_denied(tmp_path: Path, monkeypatch):
    db = tmp_path / "science.sqlite3"
    admin = OperationsAssetService(db)
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "admin")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    admin.add_asset("EQ-1", "Equipment", "equipment", "admin", owner_id="owner")
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "reader")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "researcher")
    service = OperationsAssetService(db)
    assert service.assets("reader") == ()


def test_operations_access_matrix_allows_scoped_read(tmp_path: Path, monkeypatch):
    db = tmp_path / "science.sqlite3"
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "admin")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "administrator")
    service = OperationsAssetService(db)
    asset = service.add_asset("EQ-2", "Equipment", "equipment", "admin", owner_id="reader")
    governance = Phase4AdministrationService(db)
    governance.save_access_matrix(
        actor_id="admin",
        display_name="Reader owns assets",
        principal_type="user",
        principal_id="reader",
        resource_type="operations.asset",
        data_scope="user",
        representation="individual",
        permissions={"read": True},
    )
    monkeypatch.setenv("FIELDORA_IDENTITY_ID", "reader")
    monkeypatch.setenv("FIELDORA_PROFILE_ROLE", "researcher")
    visible = OperationsAssetService(db).assets("reader")
    assert [row["id"] for row in visible] == [asset]


def test_operations_qt_uses_service_not_private_sql():
    source = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    start = source.index("class AssetEquipmentOperations")
    end = source.index("class LocalProfiles", start)
    section = source[start:end]
    assert "service._connect" not in section
    assert "itemDoubleClicked.connect" in section
    assert "set_asset_image" in section
    assert "Open / edit" in section
    assert "Open drawing" in section


def test_operations_navigation_tiles_and_module_toggle_mapping():
    desktop = Path("src/natureai_next/ui/qt/v5_desktop.py").read_text(encoding="utf-8")
    application = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    capabilities = Path("src/natureai_next/application/science_capabilities.py").read_text(encoding="utf-8")
    assert desktop.count("'Asset & equipment operations'") >= 2
    assert '"workspace.operations": "Asset & Equipment Operations"' in application
    assert '("workspace.operations", "Asset & Equipment Operations"' in capabilities
    assert 'item is not None and item.isHidden()' in application


def test_postgres_operations_schema_wired_and_extra_routes_present():
    repository = Path("src/natureai_next/server/postgres_science.py").read_text(encoding="utf-8")
    api = Path("src/natureai_next/server/api.py").read_text(encoding="utf-8")
    assert "PostgresOperationsSchema.statements()" in repository
    assert '"ops_asset_documents"' in repository
    assert '"/api/v1/operations/documents"' in api
    assert '"/api/v1/operations/storage-conditions"' in api
    assert '"/api/v1/operations/drawing-markers"' in api
    assert '"/api/v1/operations/movements"' in api

"""Clean-install asset, equipment, facilities and storage operations service."""
from __future__ import annotations

import mimetypes
import os
import sqlite3
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from natureai_next.application.phase4_administration import Phase4AdministrationService


def _id() -> str:
    return str(uuid4())


def _now() -> int:
    return time.time_ns() // 1000


_RESOURCE_TYPES = {
    "asset": "operations.asset",
    "location": "operations.location",
    "drawing": "operations.drawing",
    "maintenance": "operations.maintenance",
    "calibration": "operations.calibration",
    "document": "operations.document",
    "movement": "operations.movement",
    "storage_condition": "operations.storage_condition",
}


class OperationsAssetService:
    """Typed Operations application service with centralized authorization.

    The service is deliberately repository-facing: Qt and server adapters use
    these methods rather than issuing SQL directly.  Platform administrators
    retain the global override implemented by the access-matrix service.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._access = Phase4AdministrationService(self.database_path)

    def _connect(self):
        cx = sqlite3.connect(self.database_path)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys=ON")
        cx.execute("PRAGMA busy_timeout=5000")
        return cx

    def _ensure_schema(self) -> None:
        with self._connect() as cx:
            cx.executescript('''
CREATE TABLE IF NOT EXISTS ops_locations(
 id TEXT PRIMARY KEY,parent_id TEXT REFERENCES ops_locations(id) ON DELETE RESTRICT,
 location_type TEXT NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
 drawing_id TEXT,sort_order INTEGER NOT NULL DEFAULT 0,active INTEGER NOT NULL DEFAULT 1,
 created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,UNIQUE(parent_id,code));
CREATE INDEX IF NOT EXISTS ix_ops_locations_parent ON ops_locations(parent_id,sort_order,code);
CREATE TABLE IF NOT EXISTS ops_storage_conditions(
 id TEXT PRIMARY KEY,location_id TEXT REFERENCES ops_locations(id) ON DELETE CASCADE,
 name TEXT NOT NULL,temperature_min REAL,temperature_max REAL,humidity_min REAL,humidity_max REAL,
 light_limit_lux REAL,hazard_class TEXT NOT NULL DEFAULT '',monitoring_required INTEGER NOT NULL DEFAULT 0,
 notes TEXT NOT NULL DEFAULT '',created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_equipment_assets(
 id TEXT PRIMARY KEY,asset_code TEXT NOT NULL UNIQUE,name TEXT NOT NULL,category TEXT NOT NULL,
 manufacturer TEXT NOT NULL DEFAULT '',model TEXT NOT NULL DEFAULT '',serial_number TEXT NOT NULL DEFAULT '',
 owner_id TEXT NOT NULL DEFAULT '',custodian_id TEXT NOT NULL DEFAULT '',responsible_team TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'in_service',serviceability_status TEXT NOT NULL DEFAULT 'serviceable',
 calibration_required INTEGER NOT NULL DEFAULT 0,calibration_interval_days INTEGER,
 last_calibration_at TEXT NOT NULL DEFAULT '',next_calibration_at TEXT NOT NULL DEFAULT '',
 maintenance_interval_days INTEGER,last_maintenance_at TEXT NOT NULL DEFAULT '',next_maintenance_at TEXT NOT NULL DEFAULT '',
 warranty_until TEXT NOT NULL DEFAULT '',service_provider TEXT NOT NULL DEFAULT '',location_id TEXT REFERENCES ops_locations(id),
 image_path TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ops_assets_location ON ops_equipment_assets(location_id,status);
CREATE TABLE IF NOT EXISTS ops_asset_documents(
 id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES ops_equipment_assets(id) ON DELETE CASCADE,
 document_type TEXT NOT NULL,title TEXT NOT NULL,file_path TEXT NOT NULL,mime_type TEXT NOT NULL DEFAULT '',
 version TEXT NOT NULL DEFAULT '',effective_at TEXT NOT NULL DEFAULT '',expires_at TEXT NOT NULL DEFAULT '',
 checksum TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_maintenance_events(
 id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES ops_equipment_assets(id) ON DELETE CASCADE,
 maintenance_type TEXT NOT NULL,status TEXT NOT NULL,scheduled_start TEXT NOT NULL DEFAULT '',scheduled_end TEXT NOT NULL DEFAULT '',
 performed_start TEXT NOT NULL DEFAULT '',performed_end TEXT NOT NULL DEFAULT '',provider TEXT NOT NULL DEFAULT '',technician TEXT NOT NULL DEFAULT '',
 cost REAL NOT NULL DEFAULT 0,currency TEXT NOT NULL DEFAULT 'EUR',result TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',
 evidence_document_id TEXT REFERENCES ops_asset_documents(id),created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_calibration_events(
 id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES ops_equipment_assets(id) ON DELETE CASCADE,
 status TEXT NOT NULL,standard_reference TEXT NOT NULL DEFAULT '',method TEXT NOT NULL DEFAULT '',tolerance TEXT NOT NULL DEFAULT '',
 measured_deviation TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '',performed_at TEXT NOT NULL DEFAULT '',valid_until TEXT NOT NULL DEFAULT '',
 provider TEXT NOT NULL DEFAULT '',technician TEXT NOT NULL DEFAULT '',certificate_document_id TEXT REFERENCES ops_asset_documents(id),
 impact_assessment TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_building_drawings(
 id TEXT PRIMARY KEY,location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,title TEXT NOT NULL,
 source_format TEXT NOT NULL,file_path TEXT NOT NULL,preview_path TEXT NOT NULL DEFAULT '',version TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'active',effective_at TEXT NOT NULL DEFAULT '',superseded_at TEXT NOT NULL DEFAULT '',
 width REAL,height REAL,metadata_json TEXT NOT NULL DEFAULT '{}',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_drawing_markers(
 id TEXT PRIMARY KEY,drawing_id TEXT NOT NULL REFERENCES ops_building_drawings(id) ON DELETE CASCADE,
 location_id TEXT REFERENCES ops_locations(id) ON DELETE CASCADE,asset_id TEXT REFERENCES ops_equipment_assets(id) ON DELETE CASCADE,
 marker_code TEXT NOT NULL,label TEXT NOT NULL DEFAULT '',x REAL NOT NULL,y REAL NOT NULL,width REAL NOT NULL DEFAULT 0,height REAL NOT NULL DEFAULT 0,
 geometry_json TEXT NOT NULL DEFAULT '{}',created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_asset_movements(
 id TEXT PRIMARY KEY,asset_id TEXT NOT NULL REFERENCES ops_equipment_assets(id) ON DELETE CASCADE,
 from_location_id TEXT REFERENCES ops_locations(id),to_location_id TEXT REFERENCES ops_locations(id),
 moved_at TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',condition_before TEXT NOT NULL DEFAULT '',condition_after TEXT NOT NULL DEFAULT '',
 moved_by TEXT NOT NULL,confirmed_by TEXT NOT NULL DEFAULT '',created_at_us INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ops_audit_events(
 id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,event_type TEXT NOT NULL,resource_type TEXT NOT NULL,
 resource_id TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '',created_at_us INTEGER NOT NULL);
''')

    @staticmethod
    def _role() -> str:
        return os.environ.get("FIELDORA_PROFILE_ROLE", "administrator" if os.environ.get("FIELDORA_IDENTITY_ID", "local-user") == "local-user" else "")

    def decision(self, action: str, kind: str, actor: str, *, owner_user_id: str = "", team_id: str = "", representation: str = "individual"):
        return self._access.evaluate_access_matrix(
            actor_id=actor,
            role_code=self._role(),
            action=action,
            resource_type=_RESOURCE_TYPES[kind],
            owner_user_id=owner_user_id,
            team_id=team_id,
            representation=representation,
        )

    def can(self, action: str, kind: str, actor: str, **scope: Any) -> bool:
        return bool(self.decision(action, kind, actor, **scope).allowed)

    def _require(self, action: str, kind: str, actor: str, **scope: Any) -> None:
        decision = self.decision(action, kind, actor, **scope)
        if not decision.allowed:
            raise PermissionError(decision.reason)

    def _audit(self, cx: sqlite3.Connection, actor: str, event: str, kind: str, identity: str, detail: str = "") -> None:
        cx.execute(
            "INSERT INTO ops_audit_events VALUES(?,?,?,?,?,?,?)",
            (_id(), actor, event, _RESOURCE_TYPES[kind], identity, detail, _now()),
        )

    def locations(self, actor: str = "local-user"):
        self._require("read", "location", actor)
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute("SELECT * FROM ops_locations ORDER BY sort_order,code"))

    def location_path(self, location_id: str | None, actor: str = "local-user") -> str:
        if not location_id:
            return ""
        rows = {r["id"]: r for r in self.locations(actor)}
        parts: list[str] = []
        cur = rows.get(location_id)
        seen: set[str] = set()
        while cur and cur["id"] not in seen:
            seen.add(cur["id"])
            parts.append(f"{cur['location_type'].title()} {cur['code']} – {cur['name']}")
            cur = rows.get(cur["parent_id"])
        return " / ".join(reversed(parts))

    def add_location(self, location_type, code, name, parent_id=None, description="", actor="local-user"):
        self._require("create", "location", actor)
        now, rid = _now(), _id()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_locations(id,parent_id,location_type,code,name,description,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?)", (rid,parent_id or None,location_type,code.strip(),name.strip(),description,now,now))
            self._audit(cx, actor, "location.created", "location", rid, code)
        return rid

    def update_location(self, location_id: str, *, actor: str, name: str, description: str = "", parent_id: str | None = None) -> None:
        self._require("update", "location", actor)
        with self._connect() as cx:
            cx.execute("UPDATE ops_locations SET name=?,description=?,parent_id=?,updated_at_us=? WHERE id=?", (name.strip(), description, parent_id or None, _now(), location_id))
            self._audit(cx, actor, "location.updated", "location", location_id, name)

    def storage_conditions(self, location_id: str | None = None, actor: str = "local-user"):
        self._require("read", "storage_condition", actor)
        with self._connect() as cx:
            sql = "SELECT * FROM ops_storage_conditions"; args: tuple[Any,...] = ()
            if location_id: sql += " WHERE location_id=?"; args = (location_id,)
            return tuple(dict(r) for r in cx.execute(sql + " ORDER BY name", args))

    def assets(self, actor: str = "local-user"):
        with self._connect() as cx:
            rows = tuple(dict(r) for r in cx.execute("SELECT a.*,l.code location_code,l.name location_name FROM ops_equipment_assets a LEFT JOIN ops_locations l ON l.id=a.location_id ORDER BY a.asset_code"))
        return tuple(r for r in rows if self.can("read", "asset", actor, owner_user_id=str(r.get("owner_id") or ""), team_id=str(r.get("responsible_team") or "")))

    def asset(self, asset_id: str, actor: str = "local-user") -> dict[str, Any]:
        with self._connect() as cx:
            row = cx.execute("SELECT * FROM ops_equipment_assets WHERE id=?", (asset_id,)).fetchone()
        if row is None: raise KeyError(asset_id)
        result = dict(row)
        self._require("read", "asset", actor, owner_user_id=result.get("owner_id", ""), team_id=result.get("responsible_team", ""))
        return result

    def add_asset(self, asset_code, name, category, actor, location_id=None, **fields):
        self._require("create", "asset", actor, owner_user_id=str(fields.get("owner_id") or actor), team_id=str(fields.get("responsible_team") or ""))
        rid, now = _id(), _now()
        cols = ["id","asset_code","name","category","created_by","created_at_us","updated_at_us","location_id"]
        vals: list[Any] = [rid,asset_code.strip(),name.strip(),category.strip(),actor,now,now,location_id or None]
        allowed = {"manufacturer","model","serial_number","owner_id","custodian_id","responsible_team","status","serviceability_status","image_path","notes","calibration_required","calibration_interval_days","maintenance_interval_days","service_provider","warranty_until"}
        for key, value in fields.items():
            if key in allowed: cols.append(key); vals.append(value)
        with self._connect() as cx:
            cx.execute(f"INSERT INTO ops_equipment_assets({','.join(cols)}) VALUES({','.join('?' for _ in cols)})", vals)
            self._audit(cx, actor, "asset.created", "asset", rid, asset_code)
        return rid

    def update_asset(self, asset_id: str, *, actor: str, **fields: Any) -> None:
        current = self.asset(asset_id, actor)
        self._require("update", "asset", actor, owner_user_id=current.get("owner_id", ""), team_id=current.get("responsible_team", ""))
        allowed = {"name","category","manufacturer","model","serial_number","owner_id","custodian_id","responsible_team","status","serviceability_status","location_id","notes","calibration_required","calibration_interval_days","maintenance_interval_days","service_provider","warranty_until"}
        values = {k:v for k,v in fields.items() if k in allowed}
        if not values: return
        with self._connect() as cx:
            cx.execute("UPDATE ops_equipment_assets SET " + ",".join(f"{k}=?" for k in values) + ",updated_at_us=? WHERE id=?", (*values.values(), _now(), asset_id))
            self._audit(cx, actor, "asset.updated", "asset", asset_id, ",".join(values))

    def set_asset_image(self, asset_id: str, image_path: str, actor: str) -> None:
        current = self.asset(asset_id, actor)
        self._require("update", "asset", actor, owner_user_id=current.get("owner_id", ""), team_id=current.get("responsible_team", ""))
        with self._connect() as cx:
            cx.execute("UPDATE ops_equipment_assets SET image_path=?,updated_at_us=? WHERE id=?", (image_path, _now(), asset_id))
            self._audit(cx, actor, "asset.image.changed", "asset", asset_id, image_path)

    def documents(self, asset_id: str, actor: str = "local-user"):
        self.asset(asset_id, actor)
        self._require("read", "document", actor)
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute("SELECT * FROM ops_asset_documents WHERE asset_id=? ORDER BY created_at_us DESC", (asset_id,)))

    def add_document(self, asset_id, document_type, title, file_path, actor, mime_type=""):
        self.asset(asset_id, actor); self._require("create", "document", actor)
        rid = _id(); mime_type = mime_type or (mimetypes.guess_type(file_path)[0] or "")
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_asset_documents(id,asset_id,document_type,title,file_path,mime_type,created_by,created_at_us) VALUES(?,?,?,?,?,?,?,?)", (rid,asset_id,document_type,title,file_path,mime_type,actor,_now()))
            self._audit(cx, actor, "document.added", "document", rid, title)
        return rid

    def add_storage_condition(self, location_id, name, temperature_min=None, temperature_max=None, humidity_min=None, humidity_max=None, light_limit_lux=None, hazard_class="", monitoring_required=False, notes="", actor="local-user"):
        self._require("create", "storage_condition", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_storage_conditions(id,location_id,name,temperature_min,temperature_max,humidity_min,humidity_max,light_limit_lux,hazard_class,monitoring_required,notes,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (rid,location_id,name,temperature_min,temperature_max,humidity_min,humidity_max,light_limit_lux,hazard_class,1 if monitoring_required else 0,notes,now,now))
            self._audit(cx, actor, "storage-condition.created", "storage_condition", rid, name)
        return rid

    def drawings(self, actor: str = "local-user"):
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute("SELECT d.*,l.code location_code,l.name location_name FROM ops_building_drawings d LEFT JOIN ops_locations l ON l.id=d.location_id ORDER BY d.title,d.version"))

    def add_drawing(self, title, source_format, file_path, actor, location_id=None, preview_path="", version=""):
        self._require("create", "drawing", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_building_drawings(id,location_id,title,source_format,file_path,preview_path,version,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?,?,?)", (rid,location_id or None,title,source_format,file_path,preview_path,version,actor,now,now))
            self._audit(cx, actor, "drawing.created", "drawing", rid, title)
        return rid

    def drawing_markers(self, drawing_id=None, actor: str = "local-user"):
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            sql = "SELECT m.*,d.title drawing_title,l.code location_code,a.asset_code FROM ops_drawing_markers m JOIN ops_building_drawings d ON d.id=m.drawing_id LEFT JOIN ops_locations l ON l.id=m.location_id LEFT JOIN ops_equipment_assets a ON a.id=m.asset_id"; args: tuple[Any,...] = ()
            if drawing_id: sql += " WHERE m.drawing_id=?"; args = (drawing_id,)
            return tuple(dict(r) for r in cx.execute(sql + " ORDER BY d.title,m.marker_code", args))

    def add_drawing_marker(self, drawing_id, marker_code, x, y, location_id=None, asset_id=None, label="", width=0, height=0, actor="local-user"):
        self._require("update", "drawing", actor)
        if not location_id and not asset_id: raise ValueError("A drawing marker must reference a location or asset")
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_drawing_markers(id,drawing_id,location_id,asset_id,marker_code,label,x,y,width,height,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (rid,drawing_id,location_id,asset_id,marker_code,label,float(x),float(y),float(width),float(height),now,now))
            self._audit(cx, actor, "drawing.marker.added", "drawing", drawing_id, marker_code)
        return rid

    def maintenance(self, actor: str = "local-user"):
        self._require("read", "maintenance", actor)
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute("SELECT m.*,a.asset_code,a.name asset_name FROM ops_maintenance_events m JOIN ops_equipment_assets a ON a.id=m.asset_id ORDER BY m.created_at_us DESC"))

    def add_maintenance(self, asset_id, maintenance_type, status, actor, notes=""):
        self.asset(asset_id, actor); self._require("create", "maintenance", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_maintenance_events(id,asset_id,maintenance_type,status,notes,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?)", (rid,asset_id,maintenance_type,status,notes,actor,now,now))
            self._audit(cx, actor, "maintenance.created", "maintenance", rid, maintenance_type)
        return rid

    def update_maintenance(self, event_id: str, *, actor: str, status: str, provider: str = "", technician: str = "", result: str = "", notes: str = "") -> None:
        self._require("update", "maintenance", actor)
        with self._connect() as cx:
            cx.execute("UPDATE ops_maintenance_events SET status=?,provider=?,technician=?,result=?,notes=?,updated_at_us=? WHERE id=?", (status,provider,technician,result,notes,_now(),event_id))
            self._audit(cx, actor, "maintenance.updated", "maintenance", event_id, status)

    def calibrations(self, actor: str = "local-user"):
        self._require("read", "calibration", actor)
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute("SELECT c.*,a.asset_code,a.name asset_name FROM ops_calibration_events c JOIN ops_equipment_assets a ON a.id=c.asset_id ORDER BY c.created_at_us DESC"))

    def add_calibration(self, asset_id, status, actor, standard_reference="", result="", notes=""):
        self.asset(asset_id, actor); self._require("create", "calibration", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_calibration_events(id,asset_id,status,standard_reference,result,notes,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?,?)", (rid,asset_id,status,standard_reference,result,notes,actor,now,now))
            self._audit(cx, actor, "calibration.created", "calibration", rid, standard_reference)
        return rid

    def update_calibration(self, event_id: str, *, actor: str, status: str, result: str = "", performed_at: str = "", valid_until: str = "", impact_assessment: str = "", notes: str = "") -> None:
        self._require("update", "calibration", actor)
        with self._connect() as cx:
            cx.execute("UPDATE ops_calibration_events SET status=?,result=?,performed_at=?,valid_until=?,impact_assessment=?,notes=?,updated_at_us=? WHERE id=?", (status,result,performed_at,valid_until,impact_assessment,notes,_now(),event_id))
            self._audit(cx, actor, "calibration.updated", "calibration", event_id, status)

    def move_asset(self, asset_id: str, to_location_id: str | None, *, actor: str, moved_at: str, reason: str = "", condition_before: str = "", condition_after: str = "") -> str:
        current = self.asset(asset_id, actor); self._require("update", "movement", actor, owner_user_id=current.get("owner_id", ""), team_id=current.get("responsible_team", ""))
        rid = _id()
        with self._connect() as cx:
            cx.execute("INSERT INTO ops_asset_movements VALUES(?,?,?,?,?,?,?,?,?,?,?)", (rid,asset_id,current.get("location_id"),to_location_id,moved_at,reason,condition_before,condition_after,actor,"",_now()))
            cx.execute("UPDATE ops_equipment_assets SET location_id=?,updated_at_us=? WHERE id=?", (to_location_id,_now(),asset_id))
            self._audit(cx, actor, "asset.moved", "movement", rid, reason)
        return rid

    def audit_events(self, actor: str = "local-user", limit: int = 500):
        self._require("read", "asset", actor)
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute("SELECT * FROM ops_audit_events ORDER BY created_at_us DESC LIMIT ?", (limit,)))

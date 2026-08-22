"""Asset, equipment, facilities, floorplan and physical-placement operations.

The facilities hierarchy in :mod:`operations_assets` is the canonical physical
location model.  Drawings and floorplans are representations of that hierarchy;
planned layouts never mutate the live location of a resource until a movement
is explicitly executed.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable
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
    "floorplan": "operations.drawing",
    "layout": "operations.drawing",
    "maintenance": "operations.maintenance",
    "calibration": "operations.calibration",
    "document": "operations.document",
    "movement": "operations.movement",
    "relocation": "operations.movement",
    "storage_condition": "operations.storage_condition",
}

_DRAWING_STATUSES = {
    "draft",
    "planned",
    "approved",
    "scheduled",
    "current",
    "superseded",
    "archived",
    # Compatibility with pre-floorplan-revision installations.
    "active",
}

_GEOMETRY_TYPES = {"point", "rectangle", "polygon", "polyline"}
_LAYOUT_STATUSES = {"draft", "planned", "approved", "scheduled", "active", "completed", "cancelled", "archived"}
_RELOCATION_STATUSES = {"draft", "ready", "in_progress", "paused", "completed", "cancelled", "archived"}
_STEP_STATUSES = {"pending", "ready", "removed", "in_transit", "staging", "stored", "placed", "displayed", "completed", "exception", "cancelled"}


class OperationsAssetService:
    """Typed Operations application service with centralized authorization.

    The service is deliberately repository-facing: Qt, mobile and server
    adapters use these methods rather than issuing SQL directly.  The physical
    location hierarchy remains authoritative.  Floorplan geometry, planned
    placement and relocation workflow are reversible enrichments around it.
    """

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._access = Phase4AdministrationService(self.database_path)

    def _connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.database_path)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys=ON")
        cx.execute("PRAGMA busy_timeout=5000")
        return cx

    @staticmethod
    def _ensure_column(cx: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {str(row[1]) for row in cx.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            cx.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_schema(self) -> None:
        with self._connect() as cx:
            cx.executescript(
                """
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

CREATE TABLE IF NOT EXISTS ops_drawing_sources(
 id TEXT PRIMARY KEY,drawing_id TEXT NOT NULL REFERENCES ops_building_drawings(id) ON DELETE CASCADE,
 library_asset_id TEXT NOT NULL DEFAULT '',source_drawing_id TEXT REFERENCES ops_building_drawings(id) ON DELETE SET NULL,
 relationship TEXT NOT NULL DEFAULT 'reference',title TEXT NOT NULL DEFAULT '',source_format TEXT NOT NULL DEFAULT '',
 file_path TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,
 created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ops_drawing_sources_drawing ON ops_drawing_sources(drawing_id,relationship);

CREATE TABLE IF NOT EXISTS ops_layout_plans(
 id TEXT PRIMARY KEY,location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 drawing_id TEXT REFERENCES ops_building_drawings(id) ON DELETE SET NULL,name TEXT NOT NULL,
 version TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'draft',effective_at TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ops_layout_plans_location ON ops_layout_plans(location_id,status);

CREATE TABLE IF NOT EXISTS ops_planned_placements(
 id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES ops_layout_plans(id) ON DELETE CASCADE,
 resource_type TEXT NOT NULL,resource_id TEXT NOT NULL,
 current_location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 target_location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 target_geometry_id TEXT REFERENCES ops_drawing_markers(id) ON DELETE SET NULL,
 sequence INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'planned',notes TEXT NOT NULL DEFAULT '',
 created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL,
 UNIQUE(plan_id,resource_type,resource_id));
CREATE INDEX IF NOT EXISTS ix_ops_planned_placements_target ON ops_planned_placements(plan_id,target_location_id,sequence);

CREATE TABLE IF NOT EXISTS ops_relocation_campaigns(
 id TEXT PRIMARY KEY,plan_id TEXT REFERENCES ops_layout_plans(id) ON DELETE SET NULL,name TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft',scheduled_start TEXT NOT NULL DEFAULT '',scheduled_end TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',created_by TEXT NOT NULL,created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ops_relocation_campaigns_plan ON ops_relocation_campaigns(plan_id,status);

CREATE TABLE IF NOT EXISTS ops_relocation_steps(
 id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL REFERENCES ops_relocation_campaigns(id) ON DELETE CASCADE,
 placement_id TEXT REFERENCES ops_planned_placements(id) ON DELETE SET NULL,
 resource_type TEXT NOT NULL,resource_id TEXT NOT NULL,
 from_location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 to_location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 sequence INTEGER NOT NULL DEFAULT 0,action TEXT NOT NULL DEFAULT 'move',status TEXT NOT NULL DEFAULT 'pending',
 assigned_to TEXT NOT NULL DEFAULT '',completed_at TEXT NOT NULL DEFAULT '',completed_by TEXT NOT NULL DEFAULT '',
 movement_id TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',created_at_us INTEGER NOT NULL,updated_at_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ops_relocation_steps_campaign ON ops_relocation_steps(campaign_id,status,sequence);

CREATE TABLE IF NOT EXISTS ops_resource_movements(
 id TEXT PRIMARY KEY,resource_type TEXT NOT NULL,resource_id TEXT NOT NULL,
 from_location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 to_location_id TEXT REFERENCES ops_locations(id) ON DELETE SET NULL,
 moved_at TEXT NOT NULL,action TEXT NOT NULL DEFAULT 'move',state TEXT NOT NULL DEFAULT 'completed',
 moved_by TEXT NOT NULL,confirmed_by TEXT NOT NULL DEFAULT '',evidence_library_asset_id TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',created_at_us INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ix_ops_resource_movements_resource ON ops_resource_movements(resource_type,resource_id,created_at_us);
"""
            )
            # Non-destructive upgrades for databases created by earlier Fieldora
            # builds.  SQLite CREATE TABLE IF NOT EXISTS does not add columns.
            self._ensure_column(cx, "ops_building_drawings", "drawing_role", "TEXT NOT NULL DEFAULT 'operational'")
            self._ensure_column(cx, "ops_building_drawings", "library_asset_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cx, "ops_building_drawings", "operational_svg_asset_id", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cx, "ops_building_drawings", "operational_svg_path", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(cx, "ops_drawing_markers", "geometry_type", "TEXT NOT NULL DEFAULT 'point'")
            self._ensure_column(cx, "ops_drawing_markers", "coordinate_space", "TEXT NOT NULL DEFAULT 'normalized'")
            self._ensure_column(cx, "ops_drawing_markers", "layer", "TEXT NOT NULL DEFAULT 'locations'")
            self._ensure_column(cx, "ops_drawing_markers", "z_order", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(cx, "ops_drawing_markers", "active", "INTEGER NOT NULL DEFAULT 1")

    @staticmethod
    def _role() -> str:
        return os.environ.get(
            "FIELDORA_PROFILE_ROLE",
            "administrator"
            if os.environ.get("FIELDORA_IDENTITY_ID", "local-user") == "local-user"
            else "",
        )

    def decision(
        self,
        action: str,
        kind: str,
        actor: str,
        *,
        owner_user_id: str = "",
        team_id: str = "",
        representation: str = "individual",
    ):
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

    def _audit(
        self,
        cx: sqlite3.Connection,
        actor: str,
        event: str,
        kind: str,
        identity: str,
        detail: str = "",
    ) -> None:
        cx.execute(
            "INSERT INTO ops_audit_events VALUES(?,?,?,?,?,?,?)",
            (_id(), actor, event, _RESOURCE_TYPES[kind], identity, detail, _now()),
        )

    # ------------------------------------------------------------------
    # Canonical physical location hierarchy
    # ------------------------------------------------------------------
    def locations(self, actor: str = "local-user"):
        self._require("read", "location", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT * FROM ops_locations ORDER BY sort_order,code"
                )
            )

    def location(self, location_id: str, actor: str = "local-user") -> dict[str, Any]:
        self._require("read", "location", actor)
        with self._connect() as cx:
            row = cx.execute("SELECT * FROM ops_locations WHERE id=?", (location_id,)).fetchone()
        if row is None:
            raise KeyError(location_id)
        return dict(row)

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

    def location_ancestor_ids(self, location_id: str, actor: str = "local-user") -> tuple[str, ...]:
        rows = {r["id"]: r for r in self.locations(actor)}
        result: list[str] = []
        current = rows.get(location_id)
        seen: set[str] = set()
        while current and current["id"] not in seen:
            seen.add(current["id"])
            result.append(str(current["id"]))
            current = rows.get(current["parent_id"])
        return tuple(result)

    def add_location(
        self,
        location_type,
        code,
        name,
        parent_id=None,
        description="",
        actor="local-user",
    ):
        self._require("create", "location", actor)
        now, rid = _now(), _id()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_locations(id,parent_id,location_type,code,name,description,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (rid, parent_id or None, location_type, code.strip(), name.strip(), description, now, now),
            )
            self._audit(cx, actor, "location.created", "location", rid, code)
        return rid

    def update_location(
        self,
        location_id: str,
        *,
        actor: str,
        name: str,
        description: str = "",
        parent_id: str | None = None,
    ) -> None:
        self._require("update", "location", actor)
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_locations SET name=?,description=?,parent_id=?,updated_at_us=? WHERE id=?",
                (name.strip(), description, parent_id or None, _now(), location_id),
            )
            self._audit(cx, actor, "location.updated", "location", location_id, name)

    def storage_conditions(self, location_id: str | None = None, actor: str = "local-user"):
        self._require("read", "storage_condition", actor)
        with self._connect() as cx:
            sql = "SELECT * FROM ops_storage_conditions"
            args: tuple[Any, ...] = ()
            if location_id:
                sql += " WHERE location_id=?"
                args = (location_id,)
            return tuple(dict(r) for r in cx.execute(sql + " ORDER BY name", args))

    def add_storage_condition(
        self,
        location_id,
        name,
        temperature_min=None,
        temperature_max=None,
        humidity_min=None,
        humidity_max=None,
        light_limit_lux=None,
        hazard_class="",
        monitoring_required=False,
        notes="",
        actor="local-user",
    ):
        self._require("create", "storage_condition", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_storage_conditions(id,location_id,name,temperature_min,temperature_max,humidity_min,humidity_max,light_limit_lux,hazard_class,monitoring_required,notes,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    location_id,
                    name,
                    temperature_min,
                    temperature_max,
                    humidity_min,
                    humidity_max,
                    light_limit_lux,
                    hazard_class,
                    1 if monitoring_required else 0,
                    notes,
                    now,
                    now,
                ),
            )
            self._audit(cx, actor, "storage-condition.created", "storage_condition", rid, name)
        return rid

    # ------------------------------------------------------------------
    # Operations assets and their current live placement
    # ------------------------------------------------------------------
    def assets(self, actor: str = "local-user"):
        with self._connect() as cx:
            rows = tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT a.*,l.code location_code,l.name location_name FROM ops_equipment_assets a LEFT JOIN ops_locations l ON l.id=a.location_id ORDER BY a.asset_code"
                )
            )
        return tuple(
            r
            for r in rows
            if self.can(
                "read",
                "asset",
                actor,
                owner_user_id=str(r.get("owner_id") or ""),
                team_id=str(r.get("responsible_team") or ""),
            )
        )

    def asset(self, asset_id: str, actor: str = "local-user") -> dict[str, Any]:
        with self._connect() as cx:
            row = cx.execute("SELECT * FROM ops_equipment_assets WHERE id=?", (asset_id,)).fetchone()
        if row is None:
            raise KeyError(asset_id)
        result = dict(row)
        self._require(
            "read",
            "asset",
            actor,
            owner_user_id=result.get("owner_id", ""),
            team_id=result.get("responsible_team", ""),
        )
        return result

    def add_asset(self, asset_code, name, category, actor, location_id=None, **fields):
        self._require(
            "create",
            "asset",
            actor,
            owner_user_id=str(fields.get("owner_id") or actor),
            team_id=str(fields.get("responsible_team") or ""),
        )
        rid, now = _id(), _now()
        cols = [
            "id",
            "asset_code",
            "name",
            "category",
            "created_by",
            "created_at_us",
            "updated_at_us",
            "location_id",
        ]
        vals: list[Any] = [rid, asset_code.strip(), name.strip(), category.strip(), actor, now, now, location_id or None]
        allowed = {
            "manufacturer",
            "model",
            "serial_number",
            "owner_id",
            "custodian_id",
            "responsible_team",
            "status",
            "serviceability_status",
            "image_path",
            "notes",
            "calibration_required",
            "calibration_interval_days",
            "maintenance_interval_days",
            "service_provider",
            "warranty_until",
        }
        for key, value in fields.items():
            if key in allowed:
                cols.append(key)
                vals.append(value)
        with self._connect() as cx:
            cx.execute(
                f"INSERT INTO ops_equipment_assets({','.join(cols)}) VALUES({','.join('?' for _ in cols)})",
                vals,
            )
            self._audit(cx, actor, "asset.created", "asset", rid, asset_code)
        return rid

    def update_asset(self, asset_id: str, *, actor: str, **fields: Any) -> None:
        current = self.asset(asset_id, actor)
        self._require(
            "update",
            "asset",
            actor,
            owner_user_id=current.get("owner_id", ""),
            team_id=current.get("responsible_team", ""),
        )
        allowed = {
            "name",
            "category",
            "manufacturer",
            "model",
            "serial_number",
            "owner_id",
            "custodian_id",
            "responsible_team",
            "status",
            "serviceability_status",
            "location_id",
            "notes",
            "calibration_required",
            "calibration_interval_days",
            "maintenance_interval_days",
            "service_provider",
            "warranty_until",
        }
        values = {k: v for k, v in fields.items() if k in allowed}
        if not values:
            return
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_equipment_assets SET "
                + ",".join(f"{k}=?" for k in values)
                + ",updated_at_us=? WHERE id=?",
                (*values.values(), _now(), asset_id),
            )
            self._audit(cx, actor, "asset.updated", "asset", asset_id, ",".join(values))

    def set_asset_image(self, asset_id: str, image_path: str, actor: str) -> None:
        current = self.asset(asset_id, actor)
        self._require(
            "update",
            "asset",
            actor,
            owner_user_id=current.get("owner_id", ""),
            team_id=current.get("responsible_team", ""),
        )
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_equipment_assets SET image_path=?,updated_at_us=? WHERE id=?",
                (image_path, _now(), asset_id),
            )
            self._audit(cx, actor, "asset.image.changed", "asset", asset_id, image_path)

    def documents(self, asset_id: str, actor: str = "local-user"):
        self.asset(asset_id, actor)
        self._require("read", "document", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT * FROM ops_asset_documents WHERE asset_id=? ORDER BY created_at_us DESC",
                    (asset_id,),
                )
            )

    def add_document(self, asset_id, document_type, title, file_path, actor, mime_type=""):
        self.asset(asset_id, actor)
        self._require("create", "document", actor)
        rid = _id()
        mime_type = mime_type or (mimetypes.guess_type(file_path)[0] or "")
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_asset_documents(id,asset_id,document_type,title,file_path,mime_type,created_by,created_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (rid, asset_id, document_type, title, file_path, mime_type, actor, _now()),
            )
            self._audit(cx, actor, "document.added", "document", rid, title)
        return rid

    # ------------------------------------------------------------------
    # Versioned building drawings and operational floorplans
    # ------------------------------------------------------------------
    def drawings(self, actor: str = "local-user"):
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT d.*,l.code location_code,l.name location_name FROM ops_building_drawings d LEFT JOIN ops_locations l ON l.id=d.location_id ORDER BY d.title,d.version"
                )
            )

    def drawing(self, drawing_id: str, actor: str = "local-user") -> dict[str, Any]:
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            row = cx.execute("SELECT * FROM ops_building_drawings WHERE id=?", (drawing_id,)).fetchone()
        if row is None:
            raise KeyError(drawing_id)
        return dict(row)

    def add_drawing(
        self,
        title,
        source_format,
        file_path,
        actor,
        location_id=None,
        preview_path="",
        version="",
        *,
        status="active",
        drawing_role="operational",
        effective_at="",
        library_asset_id="",
        operational_svg_asset_id="",
        operational_svg_path="",
    ):
        self._require("create", "drawing", actor)
        status = str(status or "draft").casefold()
        if status not in _DRAWING_STATUSES:
            raise ValueError(f"Unsupported drawing status: {status}")
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                """INSERT INTO ops_building_drawings(
                    id,location_id,title,source_format,file_path,preview_path,version,status,effective_at,
                    created_by,created_at_us,updated_at_us,drawing_role,library_asset_id,
                    operational_svg_asset_id,operational_svg_path)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    location_id or None,
                    title,
                    source_format,
                    file_path,
                    preview_path,
                    version,
                    status,
                    effective_at,
                    actor,
                    now,
                    now,
                    drawing_role,
                    library_asset_id,
                    operational_svg_asset_id,
                    operational_svg_path,
                ),
            )
            self._audit(cx, actor, "drawing.created", "drawing", rid, f"{title} [{status}]")
        return rid

    def update_drawing_revision(
        self,
        drawing_id: str,
        *,
        actor: str,
        status: str | None = None,
        effective_at: str | None = None,
        version: str | None = None,
        title: str | None = None,
    ) -> None:
        self._require("update", "drawing", actor)
        values: dict[str, Any] = {}
        if status is not None:
            normalized = status.casefold()
            if normalized not in _DRAWING_STATUSES:
                raise ValueError(f"Unsupported drawing status: {status}")
            values["status"] = normalized
        if effective_at is not None:
            values["effective_at"] = effective_at
        if version is not None:
            values["version"] = version
        if title is not None:
            values["title"] = title.strip()
        if not values:
            return
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_building_drawings SET "
                + ",".join(f"{key}=?" for key in values)
                + ",updated_at_us=? WHERE id=?",
                (*values.values(), _now(), drawing_id),
            )
            self._audit(cx, actor, "drawing.revision.updated", "drawing", drawing_id, json.dumps(values, sort_keys=True))

    def activate_drawing_revision(
        self,
        drawing_id: str,
        *,
        actor: str,
        effective_at: str = "",
    ) -> None:
        """Make a revision current without destroying its predecessors."""
        self._require("update", "drawing", actor)
        drawing = self.drawing(drawing_id, actor)
        location_id = drawing.get("location_id")
        now = _now()
        with self._connect() as cx:
            if location_id:
                cx.execute(
                    """UPDATE ops_building_drawings
                          SET status='superseded',superseded_at=?,updated_at_us=?
                        WHERE location_id=? AND id<>? AND status IN ('active','current')""",
                    (effective_at, now, location_id, drawing_id),
                )
            cx.execute(
                "UPDATE ops_building_drawings SET status='current',effective_at=?,superseded_at='',updated_at_us=? WHERE id=?",
                (effective_at, now, drawing_id),
            )
            self._audit(cx, actor, "drawing.activated", "drawing", drawing_id, effective_at)

    def set_operational_svg(
        self,
        drawing_id: str,
        *,
        actor: str,
        svg_path: str,
        library_asset_id: str = "",
    ) -> None:
        self._require("update", "drawing", actor)
        if svg_path and Path(svg_path).suffix.casefold() != ".svg":
            raise ValueError("Operational floorplans must use SVG")
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_building_drawings SET operational_svg_path=?,operational_svg_asset_id=?,updated_at_us=? WHERE id=?",
                (svg_path, library_asset_id, _now(), drawing_id),
            )
            self._audit(cx, actor, "drawing.operational-svg.changed", "drawing", drawing_id, library_asset_id or svg_path)

    def link_drawing_source(
        self,
        drawing_id: str,
        *,
        actor: str,
        library_asset_id: str = "",
        source_drawing_id: str | None = None,
        relationship: str = "reference",
        title: str = "",
        source_format: str = "",
        file_path: str = "",
        notes: str = "",
    ) -> str:
        """Link preserved Library/design evidence to an operational floorplan."""
        self._require("update", "drawing", actor)
        self.drawing(drawing_id, actor)
        if not library_asset_id and not source_drawing_id and not file_path:
            raise ValueError("A drawing source must reference a Library asset, drawing or source path")
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                """INSERT INTO ops_drawing_sources(
                    id,drawing_id,library_asset_id,source_drawing_id,relationship,title,source_format,
                    file_path,notes,created_by,created_at_us,updated_at_us)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    drawing_id,
                    library_asset_id,
                    source_drawing_id,
                    relationship,
                    title,
                    source_format,
                    file_path,
                    notes,
                    actor,
                    now,
                    now,
                ),
            )
            self._audit(cx, actor, "drawing.source.linked", "drawing", drawing_id, relationship)
        return rid

    def drawing_sources(self, drawing_id: str, actor: str = "local-user"):
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT * FROM ops_drawing_sources WHERE drawing_id=? ORDER BY relationship,title,created_at_us",
                    (drawing_id,),
                )
            )

    # ------------------------------------------------------------------
    # Interactive geometry linked to canonical location records
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_geometry(geometry_type: str, coordinates: Iterable[Any]) -> tuple[str, list[list[float]]]:
        geometry_type = str(geometry_type).casefold().strip()
        if geometry_type not in _GEOMETRY_TYPES:
            raise ValueError(f"Unsupported geometry type: {geometry_type}")
        points: list[list[float]] = []
        for coordinate in coordinates:
            if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                raise ValueError("Each floorplan coordinate must contain x and y")
            x, y = float(coordinate[0]), float(coordinate[1])
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("Floorplan coordinates must be normalized between 0 and 1")
            points.append([x, y])
        minimum = {"point": 1, "rectangle": 2, "polygon": 3, "polyline": 2}[geometry_type]
        if len(points) < minimum:
            raise ValueError(f"{geometry_type} requires at least {minimum} coordinate(s)")
        return geometry_type, points

    def drawing_markers(self, drawing_id=None, actor: str = "local-user"):
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            sql = (
                "SELECT m.*,d.title drawing_title,l.code location_code,l.name location_name,a.asset_code "
                "FROM ops_drawing_markers m JOIN ops_building_drawings d ON d.id=m.drawing_id "
                "LEFT JOIN ops_locations l ON l.id=m.location_id "
                "LEFT JOIN ops_equipment_assets a ON a.id=m.asset_id"
            )
            args: tuple[Any, ...] = ()
            if drawing_id:
                sql += " WHERE m.drawing_id=?"
                args = (drawing_id,)
            return tuple(dict(r) for r in cx.execute(sql + " ORDER BY d.title,m.z_order,m.marker_code", args))

    def add_drawing_marker(
        self,
        drawing_id,
        marker_code,
        x,
        y,
        location_id=None,
        asset_id=None,
        label="",
        width=0,
        height=0,
        actor="local-user",
    ):
        """Compatibility point/rectangle marker API used by existing Qt builds."""
        self._require("update", "drawing", actor)
        if not location_id and not asset_id:
            raise ValueError("A drawing marker must reference a location or asset")
        rid, now = _id(), _now()
        geometry_type = "rectangle" if float(width or 0) or float(height or 0) else "point"
        geometry: dict[str, Any] = {}
        with self._connect() as cx:
            cx.execute(
                """INSERT INTO ops_drawing_markers(
                    id,drawing_id,location_id,asset_id,marker_code,label,x,y,width,height,geometry_json,
                    created_at_us,updated_at_us,geometry_type,coordinate_space,layer,z_order,active)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    drawing_id,
                    location_id,
                    asset_id,
                    marker_code,
                    label,
                    float(x),
                    float(y),
                    float(width),
                    float(height),
                    json.dumps(geometry),
                    now,
                    now,
                    geometry_type,
                    "legacy",
                    "locations",
                    0,
                    1,
                ),
            )
            self._audit(cx, actor, "drawing.marker.added", "drawing", drawing_id, marker_code)
        return rid

    def add_floorplan_geometry(
        self,
        drawing_id: str,
        *,
        actor: str,
        geometry_type: str,
        coordinates: Iterable[Any],
        location_id: str | None = None,
        asset_id: str | None = None,
        label: str = "",
        marker_code: str = "",
        layer: str = "locations",
        z_order: int = 0,
    ) -> str:
        """Add normalized interactive geometry to a floorplan.

        Geometry represents an existing location or operations asset.  It never
        becomes the authority for the hierarchy itself.
        """
        self._require("update", "drawing", actor)
        if not location_id and not asset_id:
            raise ValueError("Floorplan geometry must reference a location or asset")
        self.drawing(drawing_id, actor)
        if location_id:
            self.location(location_id, actor)
        if asset_id:
            self.asset(asset_id, actor)
        kind, points = self._normalize_geometry(geometry_type, coordinates)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x, y = min(xs), min(ys)
        width, height = max(xs) - x, max(ys) - y
        payload = {
            "type": kind,
            "coordinates": points,
            "coordinate_space": "normalized",
        }
        rid, now = _id(), _now()
        code = marker_code.strip() or f"geometry-{rid[:8]}"
        with self._connect() as cx:
            cx.execute(
                """INSERT INTO ops_drawing_markers(
                    id,drawing_id,location_id,asset_id,marker_code,label,x,y,width,height,geometry_json,
                    created_at_us,updated_at_us,geometry_type,coordinate_space,layer,z_order,active)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    drawing_id,
                    location_id,
                    asset_id,
                    code,
                    label,
                    x,
                    y,
                    width,
                    height,
                    json.dumps(payload, separators=(",", ":")),
                    now,
                    now,
                    kind,
                    "normalized",
                    layer,
                    int(z_order),
                    1,
                ),
            )
            self._audit(cx, actor, "floorplan.geometry.added", "drawing", drawing_id, f"{kind}:{code}")
        return rid

    def update_floorplan_geometry(
        self,
        geometry_id: str,
        *,
        actor: str,
        geometry_type: str,
        coordinates: Iterable[Any],
        label: str | None = None,
    ) -> None:
        self._require("update", "drawing", actor)
        kind, points = self._normalize_geometry(geometry_type, coordinates)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        payload = {"type": kind, "coordinates": points, "coordinate_space": "normalized"}
        values: list[Any] = [
            kind,
            json.dumps(payload, separators=(",", ":")),
            min(xs),
            min(ys),
            max(xs) - min(xs),
            max(ys) - min(ys),
        ]
        sql = "UPDATE ops_drawing_markers SET geometry_type=?,geometry_json=?,x=?,y=?,width=?,height=?"
        if label is not None:
            sql += ",label=?"
            values.append(label)
        sql += ",updated_at_us=? WHERE id=?"
        values.extend((_now(), geometry_id))
        with self._connect() as cx:
            cx.execute(sql, values)
            self._audit(cx, actor, "floorplan.geometry.updated", "drawing", geometry_id, kind)

    def geometries_for_location(
        self,
        location_id: str,
        *,
        actor: str = "local-user",
        drawing_id: str | None = None,
        include_inactive: bool = False,
    ):
        self._require("read", "drawing", actor)
        sql = (
            "SELECT m.*,d.title drawing_title,d.version drawing_version,d.status drawing_status,"
            "d.operational_svg_path,d.location_id drawing_location_id "
            "FROM ops_drawing_markers m JOIN ops_building_drawings d ON d.id=m.drawing_id "
            "WHERE m.location_id=?"
        )
        args: list[Any] = [location_id]
        if drawing_id:
            sql += " AND m.drawing_id=?"
            args.append(drawing_id)
        if not include_inactive:
            sql += " AND m.active=1"
        sql += " ORDER BY CASE d.status WHEN 'current' THEN 0 WHEN 'active' THEN 0 WHEN 'scheduled' THEN 1 WHEN 'approved' THEN 2 WHEN 'planned' THEN 3 ELSE 4 END,d.updated_at_us DESC,m.z_order"
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute(sql, args))

    def locations_on_drawing(self, drawing_id: str, actor: str = "local-user"):
        self._require("read", "drawing", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    """SELECT l.*,m.id geometry_id,m.geometry_type,m.geometry_json,m.label geometry_label,m.layer,m.z_order
                         FROM ops_drawing_markers m JOIN ops_locations l ON l.id=m.location_id
                        WHERE m.drawing_id=? AND m.active=1
                        ORDER BY m.z_order,l.sort_order,l.code""",
                    (drawing_id,),
                )
            )

    def location_drawing_context(
        self,
        location_id: str,
        *,
        actor: str = "local-user",
        include_planned: bool = False,
    ) -> dict[str, Any] | None:
        """Resolve the best floorplan for a location, walking up its hierarchy."""
        ancestors = self.location_ancestor_ids(location_id, actor)
        preferred = ("current", "active", "scheduled", "approved", "planned") if include_planned else ("current", "active")
        with self._connect() as cx:
            # Exact geometry is strongest: it says where this specific location is.
            for status in preferred:
                row = cx.execute(
                    """SELECT d.*,m.id geometry_id,m.geometry_type,m.geometry_json,m.label geometry_label
                         FROM ops_drawing_markers m JOIN ops_building_drawings d ON d.id=m.drawing_id
                        WHERE m.location_id=? AND m.active=1 AND d.status=?
                        ORDER BY d.updated_at_us DESC LIMIT 1""",
                    (location_id, status),
                ).fetchone()
                if row:
                    return dict(row)
            # Otherwise use the closest ancestor's current/planned drawing.
            for ancestor_id in ancestors:
                placeholders = ",".join("?" for _ in preferred)
                row = cx.execute(
                    f"""SELECT d.* FROM ops_building_drawings d
                          WHERE d.location_id=? AND d.status IN ({placeholders})
                          ORDER BY CASE d.status WHEN 'current' THEN 0 WHEN 'active' THEN 0 WHEN 'scheduled' THEN 1 WHEN 'approved' THEN 2 ELSE 3 END,
                                   d.updated_at_us DESC LIMIT 1""",
                    (ancestor_id, *preferred),
                ).fetchone()
                if row:
                    result = dict(row)
                    geometry = cx.execute(
                        "SELECT id geometry_id,geometry_type,geometry_json,label geometry_label FROM ops_drawing_markers WHERE drawing_id=? AND location_id=? AND active=1 ORDER BY z_order LIMIT 1",
                        (result["id"], location_id),
                    ).fetchone()
                    if geometry:
                        result.update(dict(geometry))
                    return result
        return None

    # ------------------------------------------------------------------
    # Planned future layouts.  These do not change live placement.
    # ------------------------------------------------------------------
    def create_layout_plan(
        self,
        name: str,
        *,
        actor: str,
        location_id: str | None = None,
        drawing_id: str | None = None,
        version: str = "",
        status: str = "draft",
        effective_at: str = "",
        notes: str = "",
    ) -> str:
        self._require("create", "layout", actor)
        status = status.casefold()
        if status not in _LAYOUT_STATUSES:
            raise ValueError(f"Unsupported layout status: {status}")
        if drawing_id:
            self.drawing(drawing_id, actor)
        if location_id:
            self.location(location_id, actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_layout_plans VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (rid, location_id, drawing_id, name.strip(), version, status, effective_at, notes, actor, now, now),
            )
            self._audit(cx, actor, "layout.created", "layout", rid, name)
        return rid

    def layout_plans(self, actor: str = "local-user", location_id: str | None = None):
        self._require("read", "layout", actor)
        sql = (
            "SELECT p.*,d.title drawing_title,d.version drawing_version,l.code location_code,l.name location_name "
            "FROM ops_layout_plans p LEFT JOIN ops_building_drawings d ON d.id=p.drawing_id "
            "LEFT JOIN ops_locations l ON l.id=p.location_id"
        )
        args: tuple[Any, ...] = ()
        if location_id:
            sql += " WHERE p.location_id=?"
            args = (location_id,)
        sql += " ORDER BY p.updated_at_us DESC"
        with self._connect() as cx:
            return tuple(dict(r) for r in cx.execute(sql, args))

    def set_layout_status(self, plan_id: str, status: str, *, actor: str) -> None:
        self._require("update", "layout", actor)
        status = status.casefold()
        if status not in _LAYOUT_STATUSES:
            raise ValueError(f"Unsupported layout status: {status}")
        with self._connect() as cx:
            cx.execute("UPDATE ops_layout_plans SET status=?,updated_at_us=? WHERE id=?", (status, _now(), plan_id))
            self._audit(cx, actor, "layout.status.changed", "layout", plan_id, status)

    def plan_placement(
        self,
        plan_id: str,
        *,
        actor: str,
        resource_type: str,
        resource_id: str,
        target_location_id: str | None,
        current_location_id: str | None = None,
        target_geometry_id: str | None = None,
        sequence: int = 0,
        notes: str = "",
    ) -> str:
        self._require("update", "layout", actor)
        if target_location_id:
            self.location(target_location_id, actor)
        if current_location_id:
            self.location(current_location_id, actor)
        if resource_type == "operations.asset":
            current = self.asset(resource_id, actor)
            if current_location_id is None:
                current_location_id = current.get("location_id")
        rid, now = _id(), _now()
        with self._connect() as cx:
            existing = cx.execute(
                "SELECT id FROM ops_planned_placements WHERE plan_id=? AND resource_type=? AND resource_id=?",
                (plan_id, resource_type, resource_id),
            ).fetchone()
            if existing:
                rid = str(existing[0])
                cx.execute(
                    """UPDATE ops_planned_placements
                          SET current_location_id=?,target_location_id=?,target_geometry_id=?,sequence=?,status='planned',notes=?,updated_at_us=?
                        WHERE id=?""",
                    (current_location_id, target_location_id, target_geometry_id, int(sequence), notes, now, rid),
                )
            else:
                cx.execute(
                    "INSERT INTO ops_planned_placements VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        plan_id,
                        resource_type,
                        resource_id,
                        current_location_id,
                        target_location_id,
                        target_geometry_id,
                        int(sequence),
                        "planned",
                        notes,
                        now,
                        now,
                    ),
                )
            self._audit(cx, actor, "layout.placement.planned", "layout", plan_id, f"{resource_type}:{resource_id}")
        return rid

    def plan_asset_placement(
        self,
        plan_id: str,
        asset_id: str,
        target_location_id: str | None,
        *,
        actor: str,
        target_geometry_id: str | None = None,
        sequence: int = 0,
        notes: str = "",
    ) -> str:
        return self.plan_placement(
            plan_id,
            actor=actor,
            resource_type="operations.asset",
            resource_id=asset_id,
            target_location_id=target_location_id,
            target_geometry_id=target_geometry_id,
            sequence=sequence,
            notes=notes,
        )

    def planned_placements(self, plan_id: str, actor: str = "local-user"):
        self._require("read", "layout", actor)
        with self._connect() as cx:
            rows = cx.execute(
                """SELECT p.*,fl.code from_code,fl.name from_name,tl.code to_code,tl.name to_name,
                          a.asset_code,a.name asset_name,g.label geometry_label
                     FROM ops_planned_placements p
                     LEFT JOIN ops_locations fl ON fl.id=p.current_location_id
                     LEFT JOIN ops_locations tl ON tl.id=p.target_location_id
                     LEFT JOIN ops_equipment_assets a ON p.resource_type='operations.asset' AND a.id=p.resource_id
                     LEFT JOIN ops_drawing_markers g ON g.id=p.target_geometry_id
                    WHERE p.plan_id=? ORDER BY p.sequence,p.created_at_us""",
                (plan_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def placement_picklist(self, plan_id: str, actor: str = "local-user") -> tuple[dict[str, Any], ...]:
        """Return export-friendly current/target paths for a future layout."""
        result: list[dict[str, Any]] = []
        for row in self.planned_placements(plan_id, actor):
            item = dict(row)
            item["current_path"] = self.location_path(item.get("current_location_id"), actor)
            item["target_path"] = self.location_path(item.get("target_location_id"), actor)
            result.append(item)
        return tuple(result)

    # ------------------------------------------------------------------
    # Relocation campaigns execute a plan; planning itself changes nothing.
    # ------------------------------------------------------------------
    def create_relocation_campaign(
        self,
        name: str,
        *,
        actor: str,
        plan_id: str | None = None,
        scheduled_start: str = "",
        scheduled_end: str = "",
        notes: str = "",
        populate_from_plan: bool = True,
    ) -> str:
        self._require("create", "relocation", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_relocation_campaigns VALUES(?,?,?,?,?,?,?,?,?,?)",
                (rid, plan_id, name.strip(), "draft", scheduled_start, scheduled_end, notes, actor, now, now),
            )
            if plan_id and populate_from_plan:
                placements = cx.execute(
                    "SELECT * FROM ops_planned_placements WHERE plan_id=? ORDER BY sequence,created_at_us",
                    (plan_id,),
                ).fetchall()
                for placement in placements:
                    cx.execute(
                        "INSERT INTO ops_relocation_steps VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            _id(),
                            rid,
                            placement["id"],
                            placement["resource_type"],
                            placement["resource_id"],
                            placement["current_location_id"],
                            placement["target_location_id"],
                            placement["sequence"],
                            "move",
                            "pending",
                            "",
                            "",
                            "",
                            "",
                            placement["notes"],
                            now,
                            now,
                        ),
                    )
            self._audit(cx, actor, "relocation.created", "relocation", rid, name)
        return rid

    def relocation_campaigns(self, actor: str = "local-user", plan_id: str | None = None):
        self._require("read", "relocation", actor)
        sql = "SELECT * FROM ops_relocation_campaigns"
        args: tuple[Any, ...] = ()
        if plan_id:
            sql += " WHERE plan_id=?"
            args = (plan_id,)
        with self._connect() as cx:
            return tuple(dict(row) for row in cx.execute(sql + " ORDER BY updated_at_us DESC", args))

    def relocation_steps(self, campaign_id: str, actor: str = "local-user"):
        self._require("read", "relocation", actor)
        with self._connect() as cx:
            rows = cx.execute(
                """SELECT s.*,fl.code from_code,fl.name from_name,tl.code to_code,tl.name to_name,
                          a.asset_code,a.name asset_name
                     FROM ops_relocation_steps s
                     LEFT JOIN ops_locations fl ON fl.id=s.from_location_id
                     LEFT JOIN ops_locations tl ON tl.id=s.to_location_id
                     LEFT JOIN ops_equipment_assets a ON s.resource_type='operations.asset' AND a.id=s.resource_id
                    WHERE s.campaign_id=? ORDER BY s.sequence,s.created_at_us""",
                (campaign_id,),
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["from_path"] = self.location_path(item.get("from_location_id"), actor)
            item["to_path"] = self.location_path(item.get("to_location_id"), actor)
            result.append(item)
        return tuple(result)

    def set_relocation_status(self, campaign_id: str, status: str, *, actor: str) -> None:
        self._require("update", "relocation", actor)
        status = status.casefold()
        if status not in _RELOCATION_STATUSES:
            raise ValueError(f"Unsupported relocation status: {status}")
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_relocation_campaigns SET status=?,updated_at_us=? WHERE id=?",
                (status, _now(), campaign_id),
            )
            self._audit(cx, actor, "relocation.status.changed", "relocation", campaign_id, status)

    def record_relocation_step_state(
        self,
        step_id: str,
        status: str,
        *,
        actor: str,
        notes: str | None = None,
        evidence_library_asset_id: str = "",
        moved_at: str = "",
    ) -> str | None:
        """Record mobile/desktop move progress and execute final placement.

        Intermediate states such as ``removed`` or ``staging`` never change the
        canonical live location.  ``stored``, ``placed``, ``displayed`` and
        ``completed`` execute the physical move for operations assets.
        """
        self._require("update", "relocation", actor)
        status = status.casefold()
        if status not in _STEP_STATUSES:
            raise ValueError(f"Unsupported relocation step status: {status}")
        final_states = {"stored", "placed", "displayed", "completed"}
        with self._connect() as cx:
            row = cx.execute("SELECT * FROM ops_relocation_steps WHERE id=?", (step_id,)).fetchone()
        if row is None:
            raise KeyError(step_id)
        movement_id: str | None = None
        completed_at = moved_at if status in final_states else ""
        if status in final_states and row["resource_type"] == "operations.asset":
            current = self.asset(str(row["resource_id"]), actor)
            target = row["to_location_id"]
            # Idempotence: a scanner may retry after network loss.
            if current.get("location_id") != target:
                movement_id = self.move_asset(
                    str(row["resource_id"]),
                    target,
                    actor=actor,
                    moved_at=moved_at or str(_now()),
                    reason=f"Relocation campaign {row['campaign_id']}: {status}",
                )
        elif status in final_states:
            movement_id = self.record_resource_movement(
                str(row["resource_type"]),
                str(row["resource_id"]),
                row["from_location_id"],
                row["to_location_id"],
                actor=actor,
                moved_at=moved_at or str(_now()),
                action=str(row["action"] or "move"),
                state=status,
                evidence_library_asset_id=evidence_library_asset_id,
                notes=notes or str(row["notes"] or ""),
            )
        with self._connect() as cx:
            values = [status]
            sql = "UPDATE ops_relocation_steps SET status=?"
            if notes is not None:
                sql += ",notes=?"
                values.append(notes)
            if status in final_states:
                sql += ",completed_at=?,completed_by=?"
                values.extend((completed_at or moved_at, actor))
            if movement_id:
                sql += ",movement_id=?"
                values.append(movement_id)
            sql += ",updated_at_us=? WHERE id=?"
            values.extend((_now(), step_id))
            cx.execute(sql, values)
            if row["placement_id"] and status in final_states:
                cx.execute(
                    "UPDATE ops_planned_placements SET status='completed',updated_at_us=? WHERE id=?",
                    (_now(), row["placement_id"]),
                )
            self._audit(cx, actor, "relocation.step.changed", "relocation", step_id, status)
        return movement_id

    def relocation_progress(self, campaign_id: str, actor: str = "local-user") -> dict[str, int]:
        self._require("read", "relocation", actor)
        with self._connect() as cx:
            rows = cx.execute(
                "SELECT status,COUNT(*) count FROM ops_relocation_steps WHERE campaign_id=? GROUP BY status",
                (campaign_id,),
            ).fetchall()
        counts = {str(row[0]): int(row[1]) for row in rows}
        total = sum(counts.values())
        completed = sum(counts.get(state, 0) for state in ("stored", "placed", "displayed", "completed"))
        exceptions = counts.get("exception", 0)
        return {"total": total, "completed": completed, "outstanding": total - completed, "exceptions": exceptions}

    # ------------------------------------------------------------------
    # Movement history
    # ------------------------------------------------------------------
    def move_asset(
        self,
        asset_id: str,
        to_location_id: str | None,
        *,
        actor: str,
        moved_at: str,
        reason: str = "",
        condition_before: str = "",
        condition_after: str = "",
    ) -> str:
        current = self.asset(asset_id, actor)
        self._require(
            "update",
            "movement",
            actor,
            owner_user_id=current.get("owner_id", ""),
            team_id=current.get("responsible_team", ""),
        )
        if to_location_id:
            self.location(to_location_id, actor)
        rid = _id()
        generic_id = _id()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_asset_movements VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    asset_id,
                    current.get("location_id"),
                    to_location_id,
                    moved_at,
                    reason,
                    condition_before,
                    condition_after,
                    actor,
                    "",
                    _now(),
                ),
            )
            cx.execute(
                "UPDATE ops_equipment_assets SET location_id=?,updated_at_us=? WHERE id=?",
                (to_location_id, _now(), asset_id),
            )
            cx.execute(
                "INSERT INTO ops_resource_movements VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    generic_id,
                    "operations.asset",
                    asset_id,
                    current.get("location_id"),
                    to_location_id,
                    moved_at,
                    "move",
                    "completed",
                    actor,
                    "",
                    "",
                    reason,
                    _now(),
                ),
            )
            self._audit(cx, actor, "asset.moved", "movement", rid, reason)
        return rid

    def record_resource_movement(
        self,
        resource_type: str,
        resource_id: str,
        from_location_id: str | None,
        to_location_id: str | None,
        *,
        actor: str,
        moved_at: str,
        action: str = "move",
        state: str = "completed",
        confirmed_by: str = "",
        evidence_library_asset_id: str = "",
        notes: str = "",
    ) -> str:
        """Record movement for domain resources not stored as operations assets."""
        self._require("update", "movement", actor)
        if from_location_id:
            self.location(from_location_id, actor)
        if to_location_id:
            self.location(to_location_id, actor)
        rid = _id()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_resource_movements VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rid,
                    resource_type,
                    resource_id,
                    from_location_id,
                    to_location_id,
                    moved_at,
                    action,
                    state,
                    actor,
                    confirmed_by,
                    evidence_library_asset_id,
                    notes,
                    _now(),
                ),
            )
            self._audit(cx, actor, "resource.moved", "movement", rid, f"{resource_type}:{resource_id}")
        return rid

    def resource_movements(self, resource_type: str, resource_id: str, actor: str = "local-user"):
        self._require("read", "movement", actor)
        with self._connect() as cx:
            return tuple(
                dict(row)
                for row in cx.execute(
                    "SELECT * FROM ops_resource_movements WHERE resource_type=? AND resource_id=? ORDER BY created_at_us DESC",
                    (resource_type, resource_id),
                )
            )

    # ------------------------------------------------------------------
    # Maintenance, calibration and audit (existing API retained)
    # ------------------------------------------------------------------
    def maintenance(self, actor: str = "local-user"):
        self._require("read", "maintenance", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT m.*,a.asset_code,a.name asset_name FROM ops_maintenance_events m JOIN ops_equipment_assets a ON a.id=m.asset_id ORDER BY m.created_at_us DESC"
                )
            )

    def add_maintenance(self, asset_id, maintenance_type, status, actor, notes=""):
        self.asset(asset_id, actor)
        self._require("create", "maintenance", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_maintenance_events(id,asset_id,maintenance_type,status,notes,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?)",
                (rid, asset_id, maintenance_type, status, notes, actor, now, now),
            )
            self._audit(cx, actor, "maintenance.created", "maintenance", rid, maintenance_type)
        return rid

    def update_maintenance(
        self,
        event_id: str,
        *,
        actor: str,
        status: str,
        provider: str = "",
        technician: str = "",
        result: str = "",
        notes: str = "",
    ) -> None:
        self._require("update", "maintenance", actor)
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_maintenance_events SET status=?,provider=?,technician=?,result=?,notes=?,updated_at_us=? WHERE id=?",
                (status, provider, technician, result, notes, _now(), event_id),
            )
            self._audit(cx, actor, "maintenance.updated", "maintenance", event_id, status)

    def calibrations(self, actor: str = "local-user"):
        self._require("read", "calibration", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT c.*,a.asset_code,a.name asset_name FROM ops_calibration_events c JOIN ops_equipment_assets a ON a.id=c.asset_id ORDER BY c.created_at_us DESC"
                )
            )

    def add_calibration(self, asset_id, status, actor, standard_reference="", result="", notes=""):
        self.asset(asset_id, actor)
        self._require("create", "calibration", actor)
        rid, now = _id(), _now()
        with self._connect() as cx:
            cx.execute(
                "INSERT INTO ops_calibration_events(id,asset_id,status,standard_reference,result,notes,created_by,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,?,?,?)",
                (rid, asset_id, status, standard_reference, result, notes, actor, now, now),
            )
            self._audit(cx, actor, "calibration.created", "calibration", rid, standard_reference)
        return rid

    def update_calibration(
        self,
        event_id: str,
        *,
        actor: str,
        status: str,
        result: str = "",
        performed_at: str = "",
        valid_until: str = "",
        impact_assessment: str = "",
        notes: str = "",
    ) -> None:
        self._require("update", "calibration", actor)
        with self._connect() as cx:
            cx.execute(
                "UPDATE ops_calibration_events SET status=?,result=?,performed_at=?,valid_until=?,impact_assessment=?,notes=?,updated_at_us=? WHERE id=?",
                (status, result, performed_at, valid_until, impact_assessment, notes, _now(), event_id),
            )
            self._audit(cx, actor, "calibration.updated", "calibration", event_id, status)

    def audit_events(self, actor: str = "local-user", limit: int = 500):
        self._require("read", "asset", actor)
        with self._connect() as cx:
            return tuple(
                dict(r)
                for r in cx.execute(
                    "SELECT * FROM ops_audit_events ORDER BY created_at_us DESC LIMIT ?",
                    (limit,),
                )
            )

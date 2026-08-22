"""Shared facility planning repository for the Fieldora Platform.

Canonical Operations locations and asset placement remain authoritative. Future layouts
are proposals. A relocation step changes an asset's live ``location_id`` only when the
step reaches a final placement state.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

_FINAL_PLACEMENT_STATES = frozenset({"stored", "placed", "displayed", "completed"})
_ALLOWED_STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"ready", "removed", "cancelled", "exception"}),
    "ready": frozenset({"removed", "cancelled", "exception"}),
    "removed": frozenset({"in_transit", "staging", "exception"}),
    "in_transit": frozenset({"staging", "stored", "placed", "displayed", "exception"}),
    "staging": frozenset({"in_transit", "stored", "placed", "displayed", "exception"}),
    "stored": frozenset({"completed", "exception"}),
    "placed": frozenset({"completed", "exception"}),
    "displayed": frozenset({"completed", "exception"}),
    "exception": frozenset({"ready", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


class PostgresFacilityPlatformRepository:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in self._schema():
                    cursor.execute(statement)

    @staticmethod
    def _schema() -> tuple[str, ...]:
        return (
            """
            CREATE TABLE IF NOT EXISTS ops_facility_geometries(
                id UUID PRIMARY KEY,
                drawing_id UUID NOT NULL REFERENCES ops_building_drawings(id) ON DELETE CASCADE,
                location_id UUID REFERENCES ops_locations(id),
                geometry_type TEXT NOT NULL,
                geometry_json JSONB NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                created_at_us BIGINT NOT NULL,
                updated_at_us BIGINT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ops_layout_plans(
                id UUID PRIMARY KEY,
                drawing_id UUID REFERENCES ops_building_drawings(id),
                name TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                effective_at TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                created_at_us BIGINT NOT NULL,
                updated_at_us BIGINT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ops_planned_placements(
                id UUID PRIMARY KEY,
                plan_id UUID NOT NULL REFERENCES ops_layout_plans(id) ON DELETE CASCADE,
                resource_type TEXT NOT NULL,
                resource_id UUID NOT NULL,
                current_location_id UUID REFERENCES ops_locations(id),
                target_location_id UUID REFERENCES ops_locations(id),
                target_geometry_id UUID REFERENCES ops_facility_geometries(id),
                sequence INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'planned',
                notes TEXT NOT NULL DEFAULT '',
                created_at_us BIGINT NOT NULL,
                updated_at_us BIGINT NOT NULL,
                UNIQUE(plan_id,resource_type,resource_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ops_relocation_campaigns(
                id UUID PRIMARY KEY,
                plan_id UUID REFERENCES ops_layout_plans(id),
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                scheduled_start TEXT NOT NULL DEFAULT '',
                scheduled_end TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                created_at_us BIGINT NOT NULL,
                updated_at_us BIGINT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ops_relocation_steps(
                id UUID PRIMARY KEY,
                campaign_id UUID NOT NULL REFERENCES ops_relocation_campaigns(id) ON DELETE CASCADE,
                placement_id UUID REFERENCES ops_planned_placements(id),
                resource_type TEXT NOT NULL,
                resource_id UUID NOT NULL,
                from_location_id UUID REFERENCES ops_locations(id),
                to_location_id UUID REFERENCES ops_locations(id),
                sequence INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'pending',
                assigned_to TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                evidence_library_asset_id TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                completed_by TEXT NOT NULL DEFAULT '',
                movement_id UUID,
                created_at_us BIGINT NOT NULL,
                updated_at_us BIGINT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS ix_ops_layout_plans_status_pg "
            "ON ops_layout_plans(status,effective_at,updated_at_us)",
            "CREATE INDEX IF NOT EXISTS ix_ops_relocation_steps_campaign_pg "
            "ON ops_relocation_steps(campaign_id,sequence,created_at_us)",
        )

    def drawings(self) -> tuple[dict[str, Any], ...]:
        return self._rows(
            "SELECT d.*,l.code location_code,l.name location_name "
            "FROM ops_building_drawings d LEFT JOIN ops_locations l ON l.id=d.location_id "
            "ORDER BY d.updated_at_us DESC,d.id"
        )

    def drawing(self, drawing_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            "SELECT d.*,l.code location_code,l.name location_name "
            "FROM ops_building_drawings d LEFT JOIN ops_locations l ON l.id=d.location_id "
            "WHERE d.id=%s",
            (drawing_id,),
        )
        if not rows:
            return None
        item = dict(rows[0])
        item["geometries"] = self._rows(
            "SELECT g.*,l.code location_code,l.name location_name "
            "FROM ops_facility_geometries g LEFT JOIN ops_locations l ON l.id=g.location_id "
            "WHERE g.drawing_id=%s ORDER BY g.created_at_us,g.id",
            (drawing_id,),
        )
        return item

    def add_geometry(
        self,
        drawing_id: str,
        *,
        location_id: str,
        geometry_type: str,
        geometry: dict[str, Any],
        label: str = "",
    ) -> dict[str, Any]:
        if geometry_type not in {"point", "rectangle", "polygon", "polyline"}:
            raise ValueError("invalid geometry type")
        now = time.time_ns() // 1000
        geometry_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM ops_building_drawings WHERE id=%s", (drawing_id,))
                if cursor.fetchone() is None:
                    raise KeyError(drawing_id)
                if location_id:
                    cursor.execute("SELECT 1 FROM ops_locations WHERE id=%s", (location_id,))
                    if cursor.fetchone() is None:
                        raise KeyError(location_id)
                cursor.execute(
                    "INSERT INTO ops_facility_geometries VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s)",
                    (
                        geometry_id,
                        drawing_id,
                        location_id or None,
                        geometry_type,
                        json.dumps(geometry, separators=(",", ":"), sort_keys=True),
                        label.strip(),
                        now,
                        now,
                    ),
                )
        return self.geometry(geometry_id) or {}

    def geometry(self, geometry_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM ops_facility_geometries WHERE id=%s", (geometry_id,))
        return None if not rows else rows[0]

    def create_plan(
        self,
        *,
        name: str,
        actor: str,
        drawing_id: str = "",
        version: str = "",
        effective_at: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("layout plan name is required")
        now = time.time_ns() // 1000
        plan_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if drawing_id:
                    cursor.execute("SELECT 1 FROM ops_building_drawings WHERE id=%s", (drawing_id,))
                    if cursor.fetchone() is None:
                        raise KeyError(drawing_id)
                cursor.execute(
                    "INSERT INTO ops_layout_plans VALUES(%s,%s,%s,%s,'draft',%s,%s,%s,%s,%s)",
                    (
                        plan_id,
                        drawing_id or None,
                        name.strip(),
                        version.strip(),
                        effective_at.strip(),
                        notes.strip(),
                        actor,
                        now,
                        now,
                    ),
                )
        return self.plan(plan_id) or {}

    def plans(self) -> tuple[dict[str, Any], ...]:
        return self._rows(
            "SELECT * FROM ops_layout_plans ORDER BY effective_at,updated_at_us DESC,id"
        )

    def plan(self, plan_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM ops_layout_plans WHERE id=%s", (plan_id,))
        if not rows:
            return None
        item = dict(rows[0])
        item["placements"] = self._rows(
            "SELECT p.*,a.asset_code,a.name asset_name,tl.code target_code,"
            "tl.name target_name FROM ops_planned_placements p "
            "LEFT JOIN ops_equipment_assets a ON p.resource_type='operations.asset' "
            "AND a.id=p.resource_id LEFT JOIN ops_locations tl ON tl.id=p.target_location_id "
            "WHERE p.plan_id=%s ORDER BY p.sequence,p.created_at_us,p.id",
            (plan_id,),
        )
        return item

    def plan_asset(
        self,
        plan_id: str,
        *,
        asset_id: str,
        target_location_id: str,
        target_geometry_id: str = "",
        sequence: int = 0,
        notes: str = "",
    ) -> dict[str, Any]:
        now = time.time_ns() // 1000
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT location_id FROM ops_equipment_assets WHERE id=%s", (asset_id,))
                asset = cursor.fetchone()
                if asset is None:
                    raise KeyError(asset_id)
                cursor.execute("SELECT 1 FROM ops_locations WHERE id=%s", (target_location_id,))
                if cursor.fetchone() is None:
                    raise KeyError(target_location_id)
                cursor.execute("SELECT 1 FROM ops_layout_plans WHERE id=%s", (plan_id,))
                if cursor.fetchone() is None:
                    raise KeyError(plan_id)
                placement_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO ops_planned_placements(
                        id,plan_id,resource_type,resource_id,current_location_id,
                        target_location_id,target_geometry_id,sequence,status,notes,
                        created_at_us,updated_at_us
                    ) VALUES(%s,%s,'operations.asset',%s,%s,%s,%s,%s,'planned',%s,%s,%s)
                    ON CONFLICT(plan_id,resource_type,resource_id) DO UPDATE SET
                        current_location_id=EXCLUDED.current_location_id,
                        target_location_id=EXCLUDED.target_location_id,
                        target_geometry_id=EXCLUDED.target_geometry_id,
                        sequence=EXCLUDED.sequence,status='planned',notes=EXCLUDED.notes,
                        updated_at_us=EXCLUDED.updated_at_us
                    RETURNING id
                    """,
                    (
                        placement_id,
                        plan_id,
                        asset_id,
                        asset[0],
                        target_location_id,
                        target_geometry_id or None,
                        int(sequence),
                        notes.strip(),
                        now,
                        now,
                    ),
                )
                placement_id = str(cursor.fetchone()[0])
        rows = self._rows("SELECT * FROM ops_planned_placements WHERE id=%s", (placement_id,))
        return rows[0]

    def create_campaign(
        self,
        *,
        name: str,
        actor: str,
        plan_id: str,
        scheduled_start: str = "",
        scheduled_end: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        if not name.strip():
            raise ValueError("campaign name is required")
        now = time.time_ns() // 1000
        campaign_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM ops_layout_plans WHERE id=%s", (plan_id,))
                if cursor.fetchone() is None:
                    raise KeyError(plan_id)
                cursor.execute(
                    "INSERT INTO ops_relocation_campaigns VALUES(%s,%s,%s,'draft',%s,%s,%s,%s,%s,%s)",
                    (
                        campaign_id,
                        plan_id,
                        name.strip(),
                        scheduled_start.strip(),
                        scheduled_end.strip(),
                        notes.strip(),
                        actor,
                        now,
                        now,
                    ),
                )
                cursor.execute(
                    "SELECT id,resource_type,resource_id,current_location_id,"
                    "target_location_id,sequence,notes FROM ops_planned_placements "
                    "WHERE plan_id=%s ORDER BY sequence,created_at_us,id",
                    (plan_id,),
                )
                for placement in cursor.fetchall():
                    cursor.execute(
                        """
                        INSERT INTO ops_relocation_steps(
                            id,campaign_id,placement_id,resource_type,resource_id,
                            from_location_id,to_location_id,sequence,state,assigned_to,
                            notes,evidence_library_asset_id,completed_at,completed_by,
                            movement_id,created_at_us,updated_at_us
                        ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'pending','','%s','','','','',%s,%s)
                        """.replace("'%s'", "%s"),
                        (
                            str(uuid4()),
                            campaign_id,
                            placement[0],
                            placement[1],
                            placement[2],
                            placement[3],
                            placement[4],
                            placement[5],
                            placement[6],
                            now,
                            now,
                        ),
                    )
        return self.campaign(campaign_id) or {}

    def campaigns(self) -> tuple[dict[str, Any], ...]:
        return self._rows(
            "SELECT * FROM ops_relocation_campaigns ORDER BY created_at_us DESC,id"
        )

    def campaign(self, campaign_id: str) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM ops_relocation_campaigns WHERE id=%s", (campaign_id,))
        if not rows:
            return None
        item = dict(rows[0])
        item["steps"] = self._rows(
            "SELECT s.*,a.asset_code,a.name asset_name,fl.code from_code,fl.name from_name,"
            "tl.code to_code,tl.name to_name FROM ops_relocation_steps s "
            "LEFT JOIN ops_equipment_assets a ON s.resource_type='operations.asset' "
            "AND a.id=s.resource_id LEFT JOIN ops_locations fl ON fl.id=s.from_location_id "
            "LEFT JOIN ops_locations tl ON tl.id=s.to_location_id "
            "WHERE s.campaign_id=%s ORDER BY s.sequence,s.created_at_us,s.id",
            (campaign_id,),
        )
        return item

    def transition_step(
        self,
        step_id: str,
        state: str,
        *,
        actor: str,
        notes: str = "",
        evidence_library_asset_id: str = "",
    ) -> dict[str, Any]:
        state = state.strip()
        now_us = time.time_ns() // 1000
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT campaign_id,resource_type,resource_id,from_location_id,"
                    "to_location_id,state FROM ops_relocation_steps WHERE id=%s FOR UPDATE",
                    (step_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(step_id)
                current = str(row[5])
                if state == current:
                    return self.step(step_id) or {}
                if state not in _ALLOWED_STEP_TRANSITIONS.get(current, frozenset()):
                    raise ValueError(f"invalid relocation transition: {current} -> {state}")
                movement_id = None
                completed_at = ""
                completed_by = ""
                if state in _FINAL_PLACEMENT_STATES:
                    completed_at = datetime_utc()
                    completed_by = actor
                    if row[1] == "operations.asset" and row[4] is not None:
                        movement_id = str(uuid4())
                        cursor.execute(
                            "UPDATE ops_equipment_assets SET location_id=%s,updated_at_us=%s "
                            "WHERE id=%s",
                            (row[4], now_us, row[2]),
                        )
                        cursor.execute(
                            "INSERT INTO ops_asset_movements("
                            "id,asset_id,from_location_id,to_location_id,moved_at,reason,"
                            "condition_before,condition_after,moved_by,confirmed_by,created_at_us"
                            ") VALUES(%s,%s,%s,%s,%s,%s,'','',%s,%s,%s)",
                            (
                                movement_id,
                                row[2],
                                row[3],
                                row[4],
                                completed_at,
                                "relocation campaign",
                                actor,
                                actor,
                                now_us,
                            ),
                        )
                cursor.execute(
                    "UPDATE ops_relocation_steps SET state=%s,notes=%s,"
                    "evidence_library_asset_id=%s,completed_at=%s,completed_by=%s,"
                    "movement_id=%s,updated_at_us=%s WHERE id=%s",
                    (
                        state,
                        notes.strip(),
                        evidence_library_asset_id.strip(),
                        completed_at,
                        completed_by,
                        movement_id,
                        now_us,
                        step_id,
                    ),
                )
        return self.step(step_id) or {}

    def step(self, step_id: str) -> dict[str, Any] | None:
        rows = self._rows(
            "SELECT s.*,a.asset_code,a.name asset_name,tl.code to_code,tl.name to_name "
            "FROM ops_relocation_steps s LEFT JOIN ops_equipment_assets a "
            "ON s.resource_type='operations.asset' AND a.id=s.resource_id "
            "LEFT JOIN ops_locations tl ON tl.id=s.to_location_id WHERE s.id=%s",
            (step_id,),
        )
        return None if not rows else rows[0]

    def _rows(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                names = tuple(item[0] for item in cursor.description)
                rows = cursor.fetchall()
        return tuple(
            {
                name: _json_value(value)
                for name, value in zip(names, row, strict=True)
            }
            for row in rows
        )


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, dict, list)):
        return value
    return str(value)


def datetime_utc() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()

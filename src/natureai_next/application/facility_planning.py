"""Facility layout and relocation planning built on canonical Operations locations.

This focused service keeps planned state separate from live physical placement.
It subclasses :class:`OperationsAssetService` so existing facilities, storage,
drawing, maintenance and movement APIs remain the single source of truth while
future-layout workflows can evolve independently.
"""
from __future__ import annotations

from typing import Any

from natureai_next.application.operations_assets import OperationsAssetService, _id, _now


class FacilityPlanningService(OperationsAssetService):
    """Reliable future-layout and relocation workflow facade.

    Planning never mutates an asset's live ``location_id``.  A live location is
    changed only when an executable relocation step reaches a final placement
    state such as ``stored``, ``placed``, ``displayed`` or ``completed``.
    """

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
            plan = cx.execute("SELECT id FROM ops_layout_plans WHERE id=?", (plan_id,)).fetchone()
            if plan is None:
                raise KeyError(plan_id)
            existing = cx.execute(
                "SELECT id FROM ops_planned_placements WHERE plan_id=? AND resource_type=? AND resource_id=?",
                (plan_id, resource_type, resource_id),
            ).fetchone()
            if existing:
                rid = str(existing[0])
                cx.execute(
                    """UPDATE ops_planned_placements
                          SET current_location_id=?,target_location_id=?,target_geometry_id=?,sequence=?,
                              status='planned',notes=?,updated_at_us=?
                        WHERE id=?""",
                    (
                        current_location_id,
                        target_location_id,
                        target_geometry_id,
                        int(sequence),
                        notes,
                        now,
                        rid,
                    ),
                )
            else:
                cx.execute(
                    """INSERT INTO ops_planned_placements(
                           id,plan_id,resource_type,resource_id,current_location_id,target_location_id,
                           target_geometry_id,sequence,status,notes,created_at_us,updated_at_us)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
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
            self._audit(
                cx,
                actor,
                "layout.placement.planned",
                "layout",
                plan_id,
                f"{resource_type}:{resource_id}",
            )
        return rid

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
            if plan_id:
                plan = cx.execute("SELECT id FROM ops_layout_plans WHERE id=?", (plan_id,)).fetchone()
                if plan is None:
                    raise KeyError(plan_id)
            cx.execute(
                """INSERT INTO ops_relocation_campaigns(
                       id,plan_id,name,status,scheduled_start,scheduled_end,notes,created_by,
                       created_at_us,updated_at_us)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    rid,
                    plan_id,
                    name.strip(),
                    "draft",
                    scheduled_start,
                    scheduled_end,
                    notes,
                    actor,
                    now,
                    now,
                ),
            )
            if plan_id and populate_from_plan:
                placements = cx.execute(
                    "SELECT * FROM ops_planned_placements WHERE plan_id=? ORDER BY sequence,created_at_us",
                    (plan_id,),
                ).fetchall()
                for placement in placements:
                    cx.execute(
                        """INSERT INTO ops_relocation_steps(
                               id,campaign_id,placement_id,resource_type,resource_id,from_location_id,
                               to_location_id,sequence,action,status,assigned_to,completed_at,
                               completed_by,movement_id,notes,created_at_us,updated_at_us)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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

    def current_and_planned_location(
        self,
        *,
        resource_type: str,
        resource_id: str,
        actor: str = "local-user",
    ) -> dict[str, Any]:
        """Return live placement plus all still-relevant planned placements."""
        current_location_id: str | None = None
        if resource_type == "operations.asset":
            current_location_id = self.asset(resource_id, actor).get("location_id")
        with self._connect() as cx:
            rows = cx.execute(
                """SELECT p.*,lp.name plan_name,lp.version plan_version,lp.status plan_status,
                          lp.effective_at,tl.code target_code,tl.name target_name
                     FROM ops_planned_placements p
                     JOIN ops_layout_plans lp ON lp.id=p.plan_id
                     LEFT JOIN ops_locations tl ON tl.id=p.target_location_id
                    WHERE p.resource_type=? AND p.resource_id=?
                      AND lp.status NOT IN ('cancelled','archived','completed')
                    ORDER BY lp.effective_at,lp.updated_at_us DESC""",
                (resource_type, resource_id),
            ).fetchall()
        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "current_location_id": current_location_id,
            "current_path": self.location_path(current_location_id, actor),
            "planned": tuple(
                {
                    **dict(row),
                    "target_path": self.location_path(row["target_location_id"], actor),
                }
                for row in rows
            ),
        }

    def relocation_picklist(
        self,
        campaign_id: str,
        actor: str = "local-user",
    ) -> tuple[dict[str, Any], ...]:
        """Return an execution-ready pick/move list for desktop or mobile."""
        return tuple(
            {
                **row,
                "display_name": row.get("asset_name") or row.get("resource_id") or "",
                "display_code": row.get("asset_code") or row.get("resource_id") or "",
            }
            for row in self.relocation_steps(campaign_id, actor)
        )

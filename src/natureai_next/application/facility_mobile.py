"""Mobile/server contract for facility relocation execution.

The mobile client is an execution edge: it scans a resource or move step, shows
expected current/target placement and records physical state transitions.  The
canonical move semantics remain in :class:`FacilityPlanningService`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from natureai_next.application.facility_planning import FacilityPlanningService


class FacilityMobileService:
    """Small JSON-friendly facade for scanner/mobile workflows."""

    def __init__(self, planning: FacilityPlanningService) -> None:
        self.planning = planning

    def campaign_manifest(self, campaign_id: str, actor: str = "local-user") -> dict[str, Any]:
        campaigns = self.planning.relocation_campaigns(actor)
        campaign = next((row for row in campaigns if str(row.get("id")) == campaign_id), None)
        if campaign is None:
            raise KeyError(campaign_id)
        steps = self.planning.relocation_picklist(campaign_id, actor)
        progress = self.planning.relocation_progress(campaign_id, actor)
        return {
            "schema": "fieldora.facility-relocation.v1",
            "campaign": dict(campaign),
            "progress": progress,
            "steps": tuple(self._step_payload(row, actor) for row in steps),
        }

    def step(self, step_id: str, actor: str = "local-user") -> dict[str, Any]:
        with self.planning._connect() as cx:
            row = cx.execute(
                "SELECT campaign_id FROM ops_relocation_steps WHERE id=?",
                (step_id,),
            ).fetchone()
        if row is None:
            raise KeyError(step_id)
        steps = self.planning.relocation_picklist(str(row[0]), actor)
        step = next((item for item in steps if str(item.get("id")) == step_id), None)
        if step is None:
            raise KeyError(step_id)
        return self._step_payload(step, actor)

    def steps_for_resource(
        self,
        resource_type: str,
        resource_id: str,
        actor: str = "local-user",
        *,
        include_closed: bool = False,
    ) -> tuple[dict[str, Any], ...]:
        sql = (
            """SELECT s.campaign_id,s.id FROM ops_relocation_steps s
                 JOIN ops_relocation_campaigns c ON c.id=s.campaign_id
                WHERE s.resource_type=? AND s.resource_id=?"""
        )
        args: list[Any] = [resource_type, resource_id]
        if not include_closed:
            sql += " AND c.status NOT IN ('completed','cancelled','archived')"
        sql += " ORDER BY c.updated_at_us DESC,s.sequence,s.created_at_us"
        with self.planning._connect() as cx:
            rows = cx.execute(sql, args).fetchall()
        result: list[dict[str, Any]] = []
        for campaign_id, step_id in rows:
            try:
                result.append(self.step(str(step_id), actor))
            except KeyError:
                continue
        return tuple(result)

    def record_state(
        self,
        step_id: str,
        state: str,
        *,
        actor: str,
        notes: str | None = None,
        evidence_library_asset_id: str = "",
        occurred_at: str = "",
    ) -> dict[str, Any]:
        timestamp = occurred_at or datetime.now().isoformat(timespec="seconds")
        movement_id = self.planning.record_relocation_step_state(
            step_id,
            state,
            actor=actor,
            notes=notes,
            evidence_library_asset_id=evidence_library_asset_id,
            moved_at=timestamp,
        )
        payload = self.step(step_id, actor)
        payload["recorded_state"] = state
        payload["movement_id"] = movement_id or ""
        payload["recorded_at"] = timestamp
        return payload

    def destination_drawing(
        self,
        step_id: str,
        actor: str = "local-user",
        *,
        include_planned: bool = True,
    ) -> dict[str, Any] | None:
        step = self.step(step_id, actor)
        target_id = str(step.get("to_location_id") or "")
        if not target_id:
            return None
        context = self.planning.location_drawing_context(
            target_id,
            actor=actor,
            include_planned=include_planned,
        )
        if context is None:
            return None
        return {
            "drawing_id": context.get("id"),
            "title": context.get("title"),
            "version": context.get("version"),
            "status": context.get("status"),
            "operational_svg_path": context.get("operational_svg_path"),
            "geometry_id": context.get("geometry_id"),
            "geometry_type": context.get("geometry_type"),
            "geometry_json": context.get("geometry_json"),
            "target_location_id": target_id,
            "target_path": step.get("to_path"),
        }

    def _step_payload(self, row: dict[str, Any], actor: str) -> dict[str, Any]:
        status = str(row.get("status") or "pending")
        next_actions = self._next_actions(status)
        return {
            "step_id": str(row.get("id") or ""),
            "campaign_id": str(row.get("campaign_id") or ""),
            "resource_type": str(row.get("resource_type") or ""),
            "resource_id": str(row.get("resource_id") or ""),
            "code": str(row.get("display_code") or row.get("asset_code") or row.get("resource_id") or ""),
            "name": str(row.get("display_name") or row.get("asset_name") or row.get("resource_id") or ""),
            "from_location_id": row.get("from_location_id"),
            "from_path": str(row.get("from_path") or ""),
            "to_location_id": row.get("to_location_id"),
            "to_path": str(row.get("to_path") or ""),
            "sequence": int(row.get("sequence") or 0),
            "action": str(row.get("action") or "move"),
            "status": status,
            "assigned_to": str(row.get("assigned_to") or ""),
            "notes": str(row.get("notes") or ""),
            "next_actions": next_actions,
            "is_final": status in {"stored", "placed", "displayed", "completed", "cancelled"},
        }

    @staticmethod
    def _next_actions(status: str) -> tuple[str, ...]:
        transitions = {
            "pending": ("ready", "removed", "exception"),
            "ready": ("removed", "exception"),
            "removed": ("in_transit", "staging", "stored", "exception"),
            "in_transit": ("staging", "stored", "placed", "exception"),
            "staging": ("in_transit", "stored", "placed", "exception"),
            "stored": ("placed", "displayed", "completed", "exception"),
            "placed": ("displayed", "completed", "exception"),
            "displayed": ("completed", "exception"),
            "exception": ("ready", "removed", "in_transit", "staging", "stored", "placed"),
            "completed": (),
            "cancelled": (),
        }
        return transitions.get(status, ("exception",))

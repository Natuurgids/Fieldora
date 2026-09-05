"""WEB-044 Facilities/Operations action contract projection."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_actions_web import patch_facility_actions_response

_ALLOWED_RELOCATION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "pending": ("ready", "removed", "cancelled", "exception"),
    "ready": ("removed", "cancelled", "exception"),
    "removed": ("in_transit", "staging", "exception"),
    "in_transit": ("staging", "stored", "placed", "displayed", "exception"),
    "staging": ("in_transit", "stored", "placed", "displayed", "exception"),
    "stored": ("completed", "exception"),
    "placed": ("completed", "exception"),
    "displayed": ("completed", "exception"),
    "exception": ("ready", "cancelled"),
    "completed": (),
    "cancelled": (),
}
_FINAL_PLACEMENT_STATES = frozenset({"stored", "placed", "displayed", "completed"})


def relocation_action_contract(state: str) -> dict[str, object]:
    """Return the managed relocation action contract for one canonical state."""
    normalized = str(state or "pending").strip().casefold()
    return {
        "next_actions": _ALLOWED_RELOCATION_TRANSITIONS.get(normalized, ()),
        "is_final_placement": normalized in _FINAL_PLACEMENT_STATES,
        "is_terminal": not _ALLOWED_RELOCATION_TRANSITIONS.get(normalized, ()),
    }


class FacilityActionsApiMixin:
    """Project server-owned relocation actions before the final visible-control audit."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        path = urlsplit(target).path
        if (
            method == "GET"
            and response.status == 200
            and path.startswith("/api/v1/facility-planning/")
        ):
            response = self._project_facility_actions(path, response)
        return patch_facility_actions_response(target, response)

    @staticmethod
    def _project_facility_actions(path: str, response: ApiResponse) -> ApiResponse:
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return response
        if not isinstance(payload, dict):
            return response

        changed = False
        if path.startswith("/api/v1/facility-planning/campaigns/"):
            campaign = payload.get("campaign")
            if isinstance(campaign, dict):
                steps = campaign.get("steps")
                if isinstance(steps, list):
                    for step in steps:
                        if isinstance(step, dict):
                            step.update(
                                relocation_action_contract(
                                    str(step.get("state") or "pending")
                                )
                            )
                            changed = True
        elif path.startswith("/api/v1/facility-planning/steps/"):
            step = payload.get("step")
            if isinstance(step, dict):
                step.update(
                    relocation_action_contract(str(step.get("state") or "pending"))
                )
                changed = True
        if not changed:
            return response
        return ApiResponse(
            response.status,
            json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode(),
            response.content_type,
            response.headers,
        )

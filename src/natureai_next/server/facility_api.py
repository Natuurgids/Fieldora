"""HTTP-neutral server adapter for facility floorplans and relocation execution.

The main Fieldora HTTP application can delegate authenticated facility routes to
this adapter without duplicating planning rules.  It returns JSON-friendly
status/payload tuples so WSGI/HTTP and future sync transports may share the same
contract.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from natureai_next.application.facility_mobile import FacilityMobileService


@dataclass(frozen=True, slots=True)
class FacilityApiResult:
    status: int
    payload: Mapping[str, Any] | tuple[dict[str, Any], ...]


class FacilityApiAdapter:
    """Authenticated facility/mobile route facade.

    Authentication and tenant resolution stay in the outer Fieldora server.
    This adapter receives the already-resolved actor and exposes only the
    facility workflow contract.
    """

    PREFIX = "/api/v1/facilities"

    def __init__(self, mobile: FacilityMobileService) -> None:
        self.mobile = mobile

    def dispatch(
        self,
        method: str,
        path: str,
        *,
        actor: str,
        body: Mapping[str, Any] | None = None,
    ) -> FacilityApiResult | None:
        if not path.startswith(self.PREFIX):
            return None
        body = body or {}
        segments = [part for part in path[len(self.PREFIX):].split("/") if part]
        try:
            if method == "GET" and len(segments) == 2 and segments[0] == "campaigns":
                return FacilityApiResult(200, self.mobile.campaign_manifest(segments[1], actor))
            if method == "GET" and len(segments) == 2 and segments[0] == "steps":
                return FacilityApiResult(200, self.mobile.step(segments[1], actor))
            if method == "GET" and len(segments) == 3 and segments[0] == "steps" and segments[2] == "destination":
                drawing = self.mobile.destination_drawing(segments[1], actor)
                return FacilityApiResult(200 if drawing is not None else 404, drawing or {"error": "destination_not_mapped"})
            if method == "POST" and len(segments) == 3 and segments[0] == "steps" and segments[2] == "state":
                state = str(body.get("state") or "").strip()
                if not state:
                    return FacilityApiResult(400, {"error": "state_required"})
                payload = self.mobile.record_state(
                    segments[1],
                    state,
                    actor=actor,
                    notes=str(body["notes"]) if body.get("notes") is not None else None,
                    evidence_library_asset_id=str(body.get("evidence_library_asset_id") or ""),
                    occurred_at=str(body.get("occurred_at") or ""),
                )
                return FacilityApiResult(200, payload)
            if method == "GET" and len(segments) == 3 and segments[0] == "resources":
                resource_type, resource_id = segments[1], segments[2]
                if resource_type == "asset":
                    resource_type = "operations.asset"
                return FacilityApiResult(
                    200,
                    self.mobile.steps_for_resource(resource_type, resource_id, actor),
                )
        except KeyError as exc:
            return FacilityApiResult(404, {"error": "not_found", "id": str(exc.args[0])})
        except ValueError as exc:
            return FacilityApiResult(409, {"error": "invalid_transition", "detail": str(exc)})
        except PermissionError as exc:
            return FacilityApiResult(403, {"error": "forbidden", "detail": str(exc)})
        return FacilityApiResult(404, {"error": "route_not_found"})

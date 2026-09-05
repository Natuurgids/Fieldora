from __future__ import annotations

from dataclasses import dataclass

from natureai_next.server.api import ApiResponse
from natureai_next.server.facility_api import FacilityApiResult
from natureai_next.server.facility_composition import FacilityEnabledApi


@dataclass
class _Identity:
    identity_id: str


class _BaseApi:
    def __init__(self, response: ApiResponse) -> None:
        self.response = response
        self.dispatch_calls = 0
        self.identity_calls = 0

    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes) -> ApiResponse:
        self.dispatch_calls += 1
        return self.response

    def _identity(self, headers: dict[str, str]):
        self.identity_calls += 1
        return "token", _Identity("mobile-user")


class _FacilityAdapter:
    PREFIX = "/api/v1/facilities"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, object]] = []

    def dispatch(self, method: str, path: str, *, actor: str, body=None):
        self.calls.append((method, path, actor, body))
        return FacilityApiResult(200, {"actor": actor, "body": body or {}})


def test_non_facility_request_uses_base_api_only() -> None:
    base = _BaseApi(ApiResponse.json(200, {"ok": True}))
    facility = _FacilityAdapter()
    api = FacilityEnabledApi(base, facility)  # type: ignore[arg-type]

    response = api.dispatch("GET", "/api/v1/status", {}, b"")

    assert response.status == 200
    assert base.dispatch_calls == 1
    assert base.identity_calls == 0
    assert facility.calls == []


def test_authentication_or_quota_failure_is_not_bypassed() -> None:
    base = _BaseApi(ApiResponse.json(401, {"error": "unauthorized"}))
    facility = _FacilityAdapter()
    api = FacilityEnabledApi(base, facility)  # type: ignore[arg-type]

    response = api.dispatch("GET", "/api/v1/facilities/campaigns/c-1", {}, b"")

    assert response.status == 401
    assert base.dispatch_calls == 1
    assert base.identity_calls == 0
    assert facility.calls == []


def test_authenticated_facility_404_is_delegated_with_resolved_actor() -> None:
    base = _BaseApi(ApiResponse.json(404, {"error": "not_found"}))
    facility = _FacilityAdapter()
    api = FacilityEnabledApi(base, facility)  # type: ignore[arg-type]

    response = api.dispatch(
        "POST",
        "/api/v1/facilities/steps/s-1/state?ignored=query",
        {"authorization": "Bearer token"},
        b'{"state":"placed"}',
    )

    assert response.status == 200
    assert base.dispatch_calls == 1
    assert base.identity_calls == 1
    assert facility.calls == [
        (
            "POST",
            "/api/v1/facilities/steps/s-1/state",
            "mobile-user",
            {"state": "placed"},
        )
    ]


def test_invalid_facility_json_is_rejected_after_authentication_gate() -> None:
    base = _BaseApi(ApiResponse.json(404, {"error": "not_found"}))
    facility = _FacilityAdapter()
    api = FacilityEnabledApi(base, facility)  # type: ignore[arg-type]

    response = api.dispatch(
        "POST",
        "/api/v1/facilities/steps/s-1/state",
        {},
        b"not-json",
    )

    assert response.status == 400
    assert base.dispatch_calls == 1
    assert base.identity_calls == 1
    assert facility.calls == []

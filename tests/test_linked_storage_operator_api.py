from __future__ import annotations

import json

from natureai_next.server.api import ApiResponse
from natureai_next.server.linked_storage_operator_api import LinkedStorageOperatorApiMixin
from natureai_next.server.operator_control import ServiceRecord, ServiceState


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _sql: str, parameters: tuple[str]) -> None:
        assert parameters == ("org-1",)

    def fetchall(self):
        return [
            ("archive-healthy", "service-healthy", "Healthy archive", True),
            ("archive-stale", "service-stale", "Stale archive", True),
            ("archive-missing", "service-missing", "Missing service archive", True),
        ]


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self):
        return _Cursor()


class _LinkedStorage:
    def connect_factory(self):
        return _Connection()


class _Operator:
    def __init__(self) -> None:
        self._services = {
            "service-healthy": _service("service-healthy", 950),
            "service-stale": _service("service-stale", 800),
        }

    def service(self, service_id: str):
        return self._services.get(service_id)


def _service(service_id: str, heartbeat: int) -> ServiceRecord:
    return ServiceRecord(
        service_id=service_id,
        organization_id="org-1",
        name=f"Storage {service_id}",
        service_type="linked-storage",
        node_name=f"node-{service_id}",
        state=ServiceState.ACTIVE.value,
        software_version="5.4.0",
        configuration_sha256="",
        certificate_serial="ABCD",
        certificate_not_after_epoch=10_000,
        enrolled_at_epoch=1,
        last_heartbeat_epoch=heartbeat,
        drain_requested_epoch=0,
        stopped_at_epoch=0,
        revoked_at_epoch=0,
    )


class _BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes):
        if target == "/api/v1/operator/overview" and method == "GET":
            return ApiResponse.json(
                200,
                {
                    "organization_id": "org-1",
                    "checked_at_epoch": 1000,
                    "services": [],
                    "storage": [],
                },
            )
        return ApiResponse.json(404, {"error": "not_found"})


class _Api(LinkedStorageOperatorApiMixin, _BaseApi):
    def __init__(self) -> None:
        self._linked_storage = _LinkedStorage()
        self._operator = _Operator()


def test_operator_overview_correlates_linked_archives_without_storage_paths() -> None:
    response = _Api().dispatch("GET", "/api/v1/operator/overview", {}, b"")
    assert response.status == 200
    payload = json.loads(response.body)
    archives = {item["storage_id"]: item for item in payload["linked_archives"]}

    healthy = archives["archive-healthy"]
    assert healthy["service_state"] == "active"
    assert healthy["heartbeat_age_seconds"] == 50
    assert healthy["stale"] is False

    stale = archives["archive-stale"]
    assert stale["heartbeat_age_seconds"] == 200
    assert stale["stale"] is True

    missing = archives["archive-missing"]
    assert missing["service_state"] == "missing"
    assert missing["heartbeat_age_seconds"] is None
    assert missing["stale"] is True

    serialized = response.body.decode()
    assert "root_alias" not in serialized
    assert "root_path" not in serialized
    assert "/mnt/" not in serialized


def test_operator_enrichment_does_not_change_other_routes_or_errors() -> None:
    api = _Api()
    assert api.dispatch("GET", "/api/v1/other", {}, b"").status == 404

    class _Denied(_Api):
        def dispatch_base(self):
            return ApiResponse.json(403, {"error": "forbidden"})

"""Durable service identity, lifecycle, and operator-capacity projections.

The operator registry is deliberately distinct from human access-control identities.
A Fieldora service has a durable enrolled identity even when its process, container,
host, or certificate changes.  Certificates authenticate that identity; revocation and
lifecycle state remain authoritative in this registry.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4


class ServiceState(StrEnum):
    ENROLLED = "enrolled"
    ACTIVE = "active"
    DRAINING = "draining"
    STOPPED = "stopped"
    REVOKED = "revoked"


_ALLOWED_TRANSITIONS: dict[ServiceState, frozenset[ServiceState]] = {
    ServiceState.ENROLLED: frozenset(
        {ServiceState.ACTIVE, ServiceState.STOPPED, ServiceState.REVOKED}
    ),
    ServiceState.ACTIVE: frozenset(
        {ServiceState.DRAINING, ServiceState.STOPPED, ServiceState.REVOKED}
    ),
    ServiceState.DRAINING: frozenset(
        {ServiceState.ACTIVE, ServiceState.STOPPED, ServiceState.REVOKED}
    ),
    ServiceState.STOPPED: frozenset(
        {ServiceState.ACTIVE, ServiceState.REVOKED}
    ),
    ServiceState.REVOKED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class ServiceRecord:
    service_id: str
    organization_id: str
    name: str
    service_type: str
    node_name: str
    state: str
    software_version: str
    configuration_sha256: str
    certificate_serial: str
    certificate_not_after_epoch: int
    enrolled_at_epoch: int
    last_heartbeat_epoch: int
    drain_requested_epoch: int
    stopped_at_epoch: int
    revoked_at_epoch: int

    def as_dict(self, *, now_epoch: int | None = None) -> dict[str, object]:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        value = asdict(self)
        value["certificate_expires_in_seconds"] = max(
            0, self.certificate_not_after_epoch - now
        )
        value["heartbeat_age_seconds"] = max(0, now - self.last_heartbeat_epoch)
        return value


class OperatorRepository(Protocol):
    def enroll(
        self,
        *,
        organization_id: str,
        name: str,
        service_type: str,
        node_name: str,
        software_version: str,
        configuration_sha256: str,
        certificate_serial: str,
        certificate_not_after_epoch: int,
        service_id: str = "",
        now_epoch: int | None = None,
    ) -> ServiceRecord: ...

    def service(self, service_id: str) -> ServiceRecord | None: ...

    def services(self, organization_id: str) -> tuple[ServiceRecord, ...]: ...

    def transition(
        self,
        service_id: str,
        target: ServiceState,
        *,
        now_epoch: int | None = None,
    ) -> ServiceRecord: ...

    def heartbeat(
        self,
        service_id: str,
        *,
        software_version: str = "",
        configuration_sha256: str = "",
        certificate_serial: str = "",
        certificate_not_after_epoch: int | None = None,
        now_epoch: int | None = None,
    ) -> ServiceRecord: ...


_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS operator_services(
    service_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    name TEXT NOT NULL,
    service_type TEXT NOT NULL,
    node_name TEXT NOT NULL,
    state TEXT NOT NULL,
    software_version TEXT NOT NULL,
    configuration_sha256 TEXT NOT NULL,
    certificate_serial TEXT NOT NULL,
    certificate_not_after_epoch INTEGER NOT NULL,
    enrolled_at_epoch INTEGER NOT NULL,
    last_heartbeat_epoch INTEGER NOT NULL,
    drain_requested_epoch INTEGER NOT NULL DEFAULT 0,
    stopped_at_epoch INTEGER NOT NULL DEFAULT 0,
    revoked_at_epoch INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_operator_services_scope
    ON operator_services(organization_id,state,service_type,name);
CREATE TABLE IF NOT EXISTS operator_service_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    occurred_at_epoch INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_operator_service_events_scope
    ON operator_service_events(organization_id,occurred_at_epoch,sequence);
"""


class SqliteOperatorRepository:
    """Single-node operator repository with the same lifecycle contract as PostgreSQL."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA_SQLITE)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, isolation_level=None, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def enroll(
        self,
        *,
        organization_id: str,
        name: str,
        service_type: str,
        node_name: str,
        software_version: str,
        configuration_sha256: str,
        certificate_serial: str,
        certificate_not_after_epoch: int,
        service_id: str = "",
        now_epoch: int | None = None,
    ) -> ServiceRecord:
        values = _validated_enrollment(
            organization_id=organization_id,
            name=name,
            service_type=service_type,
            node_name=node_name,
            software_version=software_version,
            configuration_sha256=configuration_sha256,
            certificate_serial=certificate_serial,
            certificate_not_after_epoch=certificate_not_after_epoch,
            service_id=service_id,
            now_epoch=now_epoch,
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO operator_services(
                    service_id,organization_id,name,service_type,node_name,state,
                    software_version,configuration_sha256,certificate_serial,
                    certificate_not_after_epoch,enrolled_at_epoch,last_heartbeat_epoch,
                    drain_requested_epoch,stopped_at_epoch,revoked_at_epoch
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0,0)
                """,
                values,
            )
            self._event(
                connection,
                str(values[0]),
                str(values[1]),
                "service_enrolled",
                str(values[3]),
                int(values[10]),
            )
            connection.commit()
        result = self.service(str(values[0]))
        assert result is not None
        return result

    def service(self, service_id: str) -> ServiceRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM operator_services WHERE service_id=?", (service_id,)
            ).fetchone()
        return None if row is None else ServiceRecord(*row)

    def services(self, organization_id: str) -> tuple[ServiceRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM operator_services WHERE organization_id=? "
                "ORDER BY service_type,name,service_id",
                (organization_id,),
            ).fetchall()
        return tuple(ServiceRecord(*row) for row in rows)

    def transition(
        self,
        service_id: str,
        target: ServiceState,
        *,
        now_epoch: int | None = None,
    ) -> ServiceRecord:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM operator_services WHERE service_id=?", (service_id,)
            ).fetchone()
            if row is None:
                raise KeyError(service_id)
            current = ServiceState(str(row["state"]))
            if target == current:
                connection.rollback()
                result = self.service(service_id)
                assert result is not None
                return result
            if target not in _ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"invalid service transition: {current} -> {target}")
            drain = now if target is ServiceState.DRAINING else int(row["drain_requested_epoch"])
            stopped = now if target is ServiceState.STOPPED else int(row["stopped_at_epoch"])
            revoked = now if target is ServiceState.REVOKED else int(row["revoked_at_epoch"])
            connection.execute(
                "UPDATE operator_services SET state=?,drain_requested_epoch=?,"
                "stopped_at_epoch=?,revoked_at_epoch=? WHERE service_id=?",
                (target.value, drain, stopped, revoked, service_id),
            )
            self._event(
                connection,
                service_id,
                str(row["organization_id"]),
                f"service_{target.value}",
                current.value,
                now,
            )
            connection.commit()
        result = self.service(service_id)
        assert result is not None
        return result

    def heartbeat(
        self,
        service_id: str,
        *,
        software_version: str = "",
        configuration_sha256: str = "",
        certificate_serial: str = "",
        certificate_not_after_epoch: int | None = None,
        now_epoch: int | None = None,
    ) -> ServiceRecord:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM operator_services WHERE service_id=?", (service_id,)
            ).fetchone()
            if row is None:
                raise KeyError(service_id)
            if ServiceState(str(row["state"])) is ServiceState.REVOKED:
                raise PermissionError("revoked service cannot heartbeat")
            connection.execute(
                """
                UPDATE operator_services SET
                    last_heartbeat_epoch=?,software_version=?,configuration_sha256=?,
                    certificate_serial=?,certificate_not_after_epoch=?
                WHERE service_id=?
                """,
                (
                    now,
                    software_version.strip() or str(row["software_version"]),
                    configuration_sha256.strip() or str(row["configuration_sha256"]),
                    certificate_serial.strip() or str(row["certificate_serial"]),
                    int(certificate_not_after_epoch)
                    if certificate_not_after_epoch is not None
                    else int(row["certificate_not_after_epoch"]),
                    service_id,
                ),
            )
            connection.commit()
        result = self.service(service_id)
        assert result is not None
        return result

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        service_id: str,
        organization_id: str,
        event_type: str,
        detail: str,
        now: int,
    ) -> None:
        connection.execute(
            "INSERT INTO operator_service_events("
            "service_id,organization_id,event_type,detail,occurred_at_epoch"
            ") VALUES(?,?,?,?,?)",
            (service_id, organization_id, event_type, detail, now),
        )


class PostgresOperatorRepository:
    """Shared operator registry for multi-node Fieldora installations."""

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS operator_services(
                        service_id TEXT PRIMARY KEY,
                        organization_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        service_type TEXT NOT NULL,
                        node_name TEXT NOT NULL,
                        state TEXT NOT NULL,
                        software_version TEXT NOT NULL,
                        configuration_sha256 TEXT NOT NULL,
                        certificate_serial TEXT NOT NULL,
                        certificate_not_after_epoch BIGINT NOT NULL,
                        enrolled_at_epoch BIGINT NOT NULL,
                        last_heartbeat_epoch BIGINT NOT NULL,
                        drain_requested_epoch BIGINT NOT NULL DEFAULT 0,
                        stopped_at_epoch BIGINT NOT NULL DEFAULT 0,
                        revoked_at_epoch BIGINT NOT NULL DEFAULT 0
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_operator_services_scope_pg "
                    "ON operator_services(organization_id,state,service_type,name)"
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS operator_service_events(
                        sequence BIGSERIAL PRIMARY KEY,
                        service_id TEXT NOT NULL,
                        organization_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        detail TEXT NOT NULL,
                        occurred_at_epoch BIGINT NOT NULL
                    )
                    """
                )

    def enroll(self, **kwargs: Any) -> ServiceRecord:
        values = _validated_enrollment(**kwargs)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO operator_services(
                        service_id,organization_id,name,service_type,node_name,state,
                        software_version,configuration_sha256,certificate_serial,
                        certificate_not_after_epoch,enrolled_at_epoch,last_heartbeat_epoch,
                        drain_requested_epoch,stopped_at_epoch,revoked_at_epoch
                    ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,0,0)
                    """,
                    values,
                )
                cursor.execute(
                    "INSERT INTO operator_service_events("
                    "service_id,organization_id,event_type,detail,occurred_at_epoch"
                    ") VALUES(%s,%s,%s,%s,%s)",
                    (values[0], values[1], "service_enrolled", values[3], values[10]),
                )
        result = self.service(str(values[0]))
        assert result is not None
        return result

    def service(self, service_id: str) -> ServiceRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT service_id,organization_id,name,service_type,node_name,state,"
                    "software_version,configuration_sha256,certificate_serial,"
                    "certificate_not_after_epoch,enrolled_at_epoch,last_heartbeat_epoch,"
                    "drain_requested_epoch,stopped_at_epoch,revoked_at_epoch "
                    "FROM operator_services WHERE service_id=%s",
                    (service_id,),
                )
                row = cursor.fetchone()
        return None if row is None else ServiceRecord(*row)

    def services(self, organization_id: str) -> tuple[ServiceRecord, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT service_id,organization_id,name,service_type,node_name,state,"
                    "software_version,configuration_sha256,certificate_serial,"
                    "certificate_not_after_epoch,enrolled_at_epoch,last_heartbeat_epoch,"
                    "drain_requested_epoch,stopped_at_epoch,revoked_at_epoch "
                    "FROM operator_services WHERE organization_id=%s "
                    "ORDER BY service_type,name,service_id",
                    (organization_id,),
                )
                rows = cursor.fetchall()
        return tuple(ServiceRecord(*row) for row in rows)

    def transition(
        self,
        service_id: str,
        target: ServiceState,
        *,
        now_epoch: int | None = None,
    ) -> ServiceRecord:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT organization_id,state,drain_requested_epoch,stopped_at_epoch,"
                    "revoked_at_epoch FROM operator_services WHERE service_id=%s FOR UPDATE",
                    (service_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(service_id)
                organization_id, state, drain, stopped, revoked = row
                current = ServiceState(str(state))
                if target == current:
                    return self.service(service_id) or _missing_service(service_id)
                if target not in _ALLOWED_TRANSITIONS[current]:
                    raise ValueError(f"invalid service transition: {current} -> {target}")
                drain = now if target is ServiceState.DRAINING else int(drain)
                stopped = now if target is ServiceState.STOPPED else int(stopped)
                revoked = now if target is ServiceState.REVOKED else int(revoked)
                cursor.execute(
                    "UPDATE operator_services SET state=%s,drain_requested_epoch=%s,"
                    "stopped_at_epoch=%s,revoked_at_epoch=%s WHERE service_id=%s",
                    (target.value, drain, stopped, revoked, service_id),
                )
                cursor.execute(
                    "INSERT INTO operator_service_events("
                    "service_id,organization_id,event_type,detail,occurred_at_epoch"
                    ") VALUES(%s,%s,%s,%s,%s)",
                    (
                        service_id,
                        organization_id,
                        f"service_{target.value}",
                        current.value,
                        now,
                    ),
                )
        result = self.service(service_id)
        assert result is not None
        return result

    def heartbeat(
        self,
        service_id: str,
        *,
        software_version: str = "",
        configuration_sha256: str = "",
        certificate_serial: str = "",
        certificate_not_after_epoch: int | None = None,
        now_epoch: int | None = None,
    ) -> ServiceRecord:
        now = int(time.time()) if now_epoch is None else int(now_epoch)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT state,software_version,configuration_sha256,certificate_serial,"
                    "certificate_not_after_epoch FROM operator_services "
                    "WHERE service_id=%s FOR UPDATE",
                    (service_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise KeyError(service_id)
                if ServiceState(str(row[0])) is ServiceState.REVOKED:
                    raise PermissionError("revoked service cannot heartbeat")
                cursor.execute(
                    "UPDATE operator_services SET last_heartbeat_epoch=%s,"
                    "software_version=%s,configuration_sha256=%s,certificate_serial=%s,"
                    "certificate_not_after_epoch=%s WHERE service_id=%s",
                    (
                        now,
                        software_version.strip() or str(row[1]),
                        configuration_sha256.strip() or str(row[2]),
                        certificate_serial.strip() or str(row[3]),
                        int(certificate_not_after_epoch)
                        if certificate_not_after_epoch is not None
                        else int(row[4]),
                        service_id,
                    ),
                )
        result = self.service(service_id)
        assert result is not None
        return result


def _validated_enrollment(**kwargs: Any) -> tuple[object, ...]:
    now = int(time.time()) if kwargs.get("now_epoch") is None else int(kwargs["now_epoch"])
    organization_id = str(kwargs["organization_id"]).strip()
    name = str(kwargs["name"]).strip()
    service_type = str(kwargs["service_type"]).strip()
    node_name = str(kwargs["node_name"]).strip()
    software_version = str(kwargs["software_version"]).strip()
    configuration_sha256 = str(kwargs["configuration_sha256"]).strip().casefold()
    certificate_serial = str(kwargs["certificate_serial"]).strip()
    certificate_not_after_epoch = int(kwargs["certificate_not_after_epoch"])
    service_id = str(kwargs.get("service_id") or uuid4())
    if not all((organization_id, name, service_type, node_name, certificate_serial)):
        raise ValueError("service enrollment fields are required")
    if configuration_sha256 and (
        len(configuration_sha256) != 64
        or any(char not in "0123456789abcdef" for char in configuration_sha256)
    ):
        raise ValueError("configuration_sha256 must be a SHA-256 digest")
    if certificate_not_after_epoch <= now:
        raise ValueError("service certificate is already expired")
    return (
        service_id,
        organization_id,
        name,
        service_type,
        node_name,
        ServiceState.ENROLLED.value,
        software_version,
        configuration_sha256,
        certificate_serial,
        certificate_not_after_epoch,
        now,
        now,
    )


def _missing_service(service_id: str) -> ServiceRecord:
    raise KeyError(service_id)


def storage_capacity(path: Path) -> dict[str, object]:
    """Return bounded filesystem capacity data for an operator-owned path."""
    resolved = path.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(resolved)
    return {
        "path": str(resolved),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": round((usage.used / usage.total) * 100, 2) if usage.total else 0.0,
    }


def operator_snapshot(
    repository: OperatorRepository,
    organization_id: str,
    *,
    storage_paths: tuple[Path, ...] = (),
    heartbeat_stale_seconds: int = 120,
    certificate_warning_seconds: int = 7 * 24 * 60 * 60,
    now_epoch: int | None = None,
) -> dict[str, object]:
    now = int(time.time()) if now_epoch is None else int(now_epoch)
    services = repository.services(organization_id)
    items = [item.as_dict(now_epoch=now) for item in services]
    stale = sum(
        item.state == ServiceState.ACTIVE.value
        and now - item.last_heartbeat_epoch > heartbeat_stale_seconds
        for item in services
    )
    expiring = sum(
        item.state != ServiceState.REVOKED.value
        and item.certificate_not_after_epoch - now <= certificate_warning_seconds
        for item in services
    )
    state_counts = {
        state.value: sum(item.state == state.value for item in services)
        for state in ServiceState
    }
    return {
        "organization_id": organization_id,
        "checked_at_epoch": now,
        "services": items,
        "service_counts": state_counts,
        "stale_service_count": stale,
        "expiring_certificate_count": expiring,
        "storage": [storage_capacity(path) for path in storage_paths],
    }

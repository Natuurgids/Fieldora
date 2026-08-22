"""Runtime supervision for long-lived, enrolled Fieldora services.

The process lifetime is intentionally independent of certificate and job-lease
lifetimes. A service stays warm while healthy, heartbeats its durable identity, and
honours operator drain/stop/revoke state before accepting new work.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol

from natureai_next.server.operator_control import OperatorRepository, ServiceState


class RuntimeShutdown(Protocol):
    @property
    def requested(self) -> bool: ...

    def wait(self, seconds: float) -> bool: ...


@dataclass(frozen=True, slots=True)
class RuntimeState:
    service_id: str
    state: ServiceState
    may_accept_work: bool
    revoked: bool


class ServiceRuntimeSupervisor:
    """Keep one registered service alive while enforcing its authoritative state."""

    def __init__(
        self,
        repository: OperatorRepository,
        service_id: str,
        *,
        heartbeat_seconds: float = 30.0,
        software_version: str = "",
        configuration_sha256: str = "",
    ) -> None:
        if not service_id.strip():
            raise ValueError("service_id is required")
        if not 5 <= heartbeat_seconds <= 300:
            raise ValueError("heartbeat interval must be between 5 and 300 seconds")
        self.repository = repository
        self.service_id = service_id.strip()
        self.heartbeat_seconds = float(heartbeat_seconds)
        self.software_version = software_version.strip()
        self.configuration_sha256 = configuration_sha256.strip()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        record = self.repository.service(self.service_id)
        if record is None:
            raise PermissionError(f"service is not enrolled: {self.service_id}")
        if record.state == ServiceState.REVOKED.value:
            raise PermissionError(f"service is revoked: {self.service_id}")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"fieldora-service-heartbeat-{self.service_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(2.0, self.heartbeat_seconds + 1.0))
        self._thread = None

    def state(self) -> RuntimeState:
        record = self.repository.service(self.service_id)
        if record is None:
            return RuntimeState(
                self.service_id, ServiceState.REVOKED, False, True
            )
        state = ServiceState(record.state)
        return RuntimeState(
            self.service_id,
            state,
            state in {ServiceState.ENROLLED, ServiceState.ACTIVE},
            state is ServiceState.REVOKED,
        )

    def wait_until_work_allowed(
        self,
        shutdown: RuntimeShutdown | None = None,
        *,
        poll_seconds: float = 2.0,
    ) -> bool:
        """Wait without process churn until work may be claimed.

        Draining and stopped services stay resident/warm but do not claim new work.
        Revoked or disappeared identities fail closed and never resume automatically.
        """
        if not 0.1 <= poll_seconds <= 60:
            raise ValueError("poll_seconds must be between 0.1 and 60")
        while True:
            if shutdown is not None and shutdown.requested:
                return False
            runtime = self.state()
            if runtime.revoked:
                return False
            if runtime.may_accept_work:
                return True
            if shutdown is not None:
                shutdown.wait(poll_seconds)
            else:
                self._stop.wait(poll_seconds)
            if self._stop.is_set():
                return False

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            runtime = self.state()
            if runtime.revoked:
                return
            try:
                self.repository.heartbeat(
                    self.service_id,
                    software_version=self.software_version,
                    configuration_sha256=self.configuration_sha256,
                )
            except (KeyError, PermissionError):
                return
            self._stop.wait(self.heartbeat_seconds)

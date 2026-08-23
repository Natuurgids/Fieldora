"""Managed lifecycle for the internal mTLS linked-storage service listener."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from natureai_next.server.operator_control import OperatorRepository
from natureai_next.server.postgres_linked_preview import PostgresLinkedPreviewLeases
from natureai_next.server.postgres_linked_storage import PostgresLinkedStorageRepository
from natureai_next.server.service_http import MutualTLSServer, create_service_server
from natureai_next.server.storage_service_api import LinkedStorageServiceApi


@dataclass(frozen=True, slots=True)
class StorageServiceListenerConfig:
    host: str
    port: int
    certificate: Path
    private_key: Path
    client_ca: Path

    def validate(self) -> None:
        if not self.host.strip():
            raise ValueError("storage service host is required")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("storage service port must be between 1 and 65535")
        for label, path in (
            ("certificate", self.certificate),
            ("private key", self.private_key),
            ("client CA", self.client_ca),
        ):
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"storage service {label} is missing or empty")


class StorageServiceListenerRuntime:
    """Start/stop the mTLS service listener with the managed Fieldora process."""

    def __init__(
        self,
        config: StorageServiceListenerConfig,
        catalogue: PostgresLinkedStorageRepository,
        leases: PostgresLinkedPreviewLeases,
        operators: OperatorRepository,
    ) -> None:
        config.validate()
        self._config = config
        self._application = LinkedStorageServiceApi(catalogue, leases, operators)
        self._server: MutualTLSServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def endpoint(self) -> str:
        return f"https://{self._config.host}:{self._config.port}"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        server = create_service_server(
            self._application,
            self._config.host,
            self._config.port,
            certificate=self._config.certificate,
            private_key=self._config.private_key,
            client_ca=self._config.client_ca,
        )
        thread = threading.Thread(
            target=server.serve_forever,
            name="fieldora-storage-service-listener",
            daemon=True,
        )
        self._server = server
        self._thread = thread
        thread.start()

    def stop(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=5)

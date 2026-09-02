"""Threaded HTTP adapter for the Fieldora API application."""

from __future__ import annotations

import hashlib
import socket
import ssl
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from natureai_next.server.administration_management_api import (
    dispatch_administration_management,
)
from natureai_next.server.administration_management_web import (
    patch_administration_management_web_response,
)
from natureai_next.server.administration_workspace_web import (
    patch_administration_workspace_web_response,
)
from natureai_next.server.aiadmin_zero_trust_web import (
    patch_aiadmin_zero_trust_response,
)
from natureai_next.server.api import FieldoraApi
from natureai_next.server.browser_functionality_web import (
    patch_browser_functionality_response,
)
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.desktop_alignment_web import patch_desktop_alignment_web_response
from natureai_next.server.directory_intake_web import patch_directory_intake_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.library_collections_web import (
    patch_library_collections_web_response,
)
from natureai_next.server.lifecycle import ShutdownCoordinator
from natureai_next.server.linked_storage_operator_web import (
    patch_linked_storage_operator_web_response,
)
from natureai_next.server.linked_storage_web import patch_linked_storage_web_response
from natureai_next.server.modular_shell_web import finalize_modular_shell_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.offline_maps_web import patch_offline_maps_web_response
from natureai_next.server.offline_models_web import patch_offline_models_web_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_facility_workspace_web import (
    patch_project_facility_workspace_response,
)
from natureai_next.server.project_list_provider_web import (
    patch_project_list_provider_response,
)
from natureai_next.server.science_workflow_web import patch_science_workflow_web_response
from natureai_next.server.web_capabilities import (
    patch_zero_trust_web_response,
    project_help_response,
)
from natureai_next.server.web_compatibility import (
    patch_web_response,
    public_response,
    rewrite_public_target,
)
from natureai_next.server.web_module_contract_runtime import patch_runtime_contracts_response
from natureai_next.server.workspace_language_web import patch_workspace_language_web_response


class ReloadingCertificateChain:
    """Reload replaced TLS material for subsequent connections without a restart."""

    def __init__(
        self,
        context: ssl.SSLContext,
        certificate: Path,
        private_key: Path,
    ) -> None:
        self.context = context
        self.certificate = certificate.resolve(strict=True)
        self.private_key = private_key.resolve(strict=True)
        self._lock = threading.Lock()
        self._fingerprint = b""
        self.reload_if_changed(force=True)

    def reload_if_changed(self, *, force: bool = False) -> bool:
        certificate_bytes = self.certificate.read_bytes()
        key_bytes = self.private_key.read_bytes()
        fingerprint = hashlib.sha256(certificate_bytes + b"\0" + key_bytes).digest()
        with self._lock:
            if not force and fingerprint == self._fingerprint:
                return False
            self.context.load_cert_chain(str(self.certificate), str(self.private_key))
            self._fingerprint = fingerprint
            return True


class ReloadingTLSServer(ThreadingHTTPServer):
    """Threading server that adopts renewed certificates on new connections."""

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        certificate: Path,
        private_key: Path,
    ) -> None:
        super().__init__(server_address, handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.certificate_chain = ReloadingCertificateChain(
            context, certificate, private_key
        )

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        request, address = super().get_request()
        try:
            self.certificate_chain.reload_if_changed()
            wrapped = self.certificate_chain.context.wrap_socket(request, server_side=True)
        except BaseException:
            request.close()
            raise
        return wrapped, address


def patch_managed_web_response(target: str, response):
    """Apply every certified managed-browser patch in production order."""
    for patch in (
        patch_browser_functionality_response,
        patch_web_response,
        patch_contract_web_response,
        patch_facility_web_response,
        patch_navigation_web_response,
        patch_directory_intake_response,
        patch_linked_storage_web_response,
        patch_linked_storage_operator_web_response,
        patch_desktop_alignment_web_response,
        patch_library_collections_web_response,
        patch_science_workflow_web_response,
        patch_administration_workspace_web_response,
        patch_administration_management_web_response,
        patch_workspace_language_web_response,
        patch_project_facility_workspace_response,
        patch_offline_models_web_response,
        patch_offline_maps_web_response,
        patch_zero_trust_web_response,
        patch_aiadmin_zero_trust_response,
        # Finalizer is inert for non-modular applications.  When the API mixin
        # already installed the shell, it removes migrated compatibility code
        # after all append-only patches and moves initial mount to the very end.
        finalize_modular_shell_response,
        # Runtime contract declarations must execute after the finalized shell so
        # consumers can discover providers without depending on implementation IDs.
        patch_runtime_contracts_response,
        # Projects owns the accessible-list snapshot behind the declared read contract.
        patch_project_list_provider_response,
        # Projects exposes context selection through a replaceable public contract.
        patch_project_context_provider_response,
    ):
        response = patch(target, response)
    return response


def handler_for(
    application: FieldoraApi, *, tls_enabled: bool = False
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Fieldora"

        def do_GET(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def do_PUT(self) -> None:
            self._dispatch()

        def do_PATCH(self) -> None:
            self._dispatch()

        def do_DELETE(self) -> None:
            self._dispatch()

        def _dispatch(self) -> None:
            public = public_response(self.command, self.path)
            if public is not None:
                self._write(public)
                return
            target = rewrite_public_target(self.command, self.path)
            content_length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(content_length) if content_length else b""
            headers = {key.lower(): value for key, value in self.headers.items()}
            response = application.dispatch(self.command, target, headers, body)
            if response.status == 404:
                administration = dispatch_administration_management(
                    application, self.command, target, headers, body
                )
                if administration is not None:
                    response = administration
            response = project_help_response(application, target, headers, response)
            response = patch_managed_web_response(target, response)
            self._write(response)

        def _write(self, response) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            for key, value in response.headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def serve(
    application: FieldoraApi,
    host: str,
    port: int,
    *,
    certificate: Path | None = None,
    private_key: Path | None = None,
    on_shutdown: Callable[[], None] | None = None,
    shutdown_grace_seconds: float = 30.0,
) -> None:
    """Serve Fieldora with reloadable TLS and coordinated signal-driven draining."""
    if (certificate is None) != (private_key is None):
        raise ValueError("TLS certificate and private key must be configured together")
    if not 0 <= shutdown_grace_seconds <= 300:
        raise ValueError("shutdown grace period must be between 0 and 300 seconds")

    handler = handler_for(application, tls_enabled=certificate is not None)
    if certificate is not None and private_key is not None:
        server: ThreadingHTTPServer = ReloadingTLSServer(
            (host, port), handler, certificate, private_key
        )
    else:
        server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server.timeout = 0.5

    shutdown = ShutdownCoordinator(() if on_shutdown is None else (on_shutdown,))
    with shutdown.installed():
        try:
            while not shutdown.requested:
                server.handle_request()
        finally:
            server.server_close()

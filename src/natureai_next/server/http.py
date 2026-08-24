"""Threaded HTTP adapter for the Fieldora API application."""

from __future__ import annotations

import hashlib
import socket
import ssl
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from natureai_next.server.api import FieldoraApi
from natureai_next.server.desktop_alignment_web import patch_desktop_alignment_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.lifecycle import ShutdownCoordinator
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.web_compatibility import (
    patch_web_response,
    public_response,
    rewrite_public_target,
)


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
        fingerprint = hashlib.sha256(
            certificate_bytes + b"\0" + key_bytes
        ).digest()
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
            wrapped = self.certificate_chain.context.wrap_socket(
                request, server_side=True
            )
        except BaseException:
            request.close()
            raise
        return wrapped, address


def handler_for(
    application: FieldoraApi, *, tls_enabled: bool = False
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Fieldora"

        def do_GET(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def do_DELETE(self) -> None:
            self._dispatch()

        def do_PUT(self) -> None:
            self._dispatch()

        def _dispatch(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            body = self.rfile.read(min(length, 8 * 1024 * 1024 + 1)) if length else b""
            request_headers = {
                key.casefold(): value for key, value in self.headers.items()
            }
            request_headers["remote-address"] = self.client_address[0]
            response = public_response(self.command, self.path)
            if response is None:
                target = rewrite_public_target(self.command, self.path)
                response = application.dispatch(
                    self.command, target, request_headers, body,
                )
                response = patch_web_response(target, response)
                response = patch_facility_web_response(target, response)
                response = patch_navigation_web_response(target, response)
                response = patch_desktop_alignment_web_response(target, response)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            if not any(
                name.casefold() == "content-length" for name, _ in response.headers
            ):
                self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            if tls_enabled:
                self.send_header(
                    "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
                )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
            )
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            super().log_message(format, *args)

    return Handler


def create_server(
    application: FieldoraApi,
    host: str,
    port: int,
    *,
    certificate: Path | None = None,
    private_key: Path | None = None,
) -> ThreadingHTTPServer:
    if (certificate is None) != (private_key is None):
        raise ValueError("TLS certificate and private key must be configured together")
    tls_enabled = certificate is not None
    handler = handler_for(application, tls_enabled=tls_enabled)
    if certificate is not None and private_key is not None:
        return ReloadingTLSServer((host, port), handler, certificate, private_key)
    return ThreadingHTTPServer((host, port), handler)


def serve(
    application: FieldoraApi,
    host: str,
    port: int,
    *,
    certificate: Path | None = None,
    private_key: Path | None = None,
    on_shutdown: Callable[[], None] | None = None,
    shutdown_grace_seconds: float = 0,
) -> None:
    if not 0 <= shutdown_grace_seconds <= 300:
        raise ValueError("shutdown grace must be between 0 and 300 seconds")
    server = create_server(
        application, host, port, certificate=certificate, private_key=private_key
    )

    def stop_after_drain() -> None:
        def stop() -> None:
            if shutdown_grace_seconds:
                time.sleep(shutdown_grace_seconds)
            server.shutdown()

        threading.Thread(target=stop, daemon=True).start()

    callbacks = (() if on_shutdown is None else (on_shutdown,)) + (stop_after_drain,)
    coordinator = ShutdownCoordinator(callbacks)
    try:
        with coordinator.installed():
            server.serve_forever()
    finally:
        server.server_close()

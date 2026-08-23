"""Mutual-TLS HTTP transport for internal Fieldora service-to-service APIs.

This listener is intentionally separate from the human browser listener.  It requires a
client certificate signed by the configured Fieldora service CA and injects authenticated
peer-certificate metadata into the application request only after the TLS handshake.
Client-supplied headers with the same names are overwritten and therefore cannot spoof
service identity.
"""

from __future__ import annotations

import socket
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol

from natureai_next.server.api import ApiResponse


class ServiceApplication(Protocol):
    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse: ...


_PEER_SERIAL = "fieldora-peer-certificate-serial"
_PEER_SUBJECT = "fieldora-peer-certificate-subject"
_PEER_ISSUER = "fieldora-peer-certificate-issuer"


def _distinguished_name(parts: object) -> str:
    """Render ssl.getpeercert() subject/issuer tuples deterministically."""
    if not isinstance(parts, tuple):
        return ""
    rendered: list[str] = []
    for rdn in parts:
        if not isinstance(rdn, tuple):
            continue
        for item in rdn:
            if (
                isinstance(item, tuple)
                and len(item) == 2
                and all(isinstance(value, str) for value in item)
            ):
                rendered.append(f"{item[0]}={item[1]}")
    return ",".join(rendered)


class MutualTLSServer(ThreadingHTTPServer):
    """Internal server that rejects clients without a trusted certificate."""

    def __init__(
        self,
        server_address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        certificate: Path,
        private_key: Path,
        client_ca: Path,
    ) -> None:
        super().__init__(server_address, handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(str(certificate.resolve(strict=True)), str(private_key.resolve(strict=True)))
        context.load_verify_locations(cafile=str(client_ca.resolve(strict=True)))
        self.context = context

    def get_request(self) -> tuple[socket.socket, tuple[str, int]]:
        request, address = super().get_request()
        try:
            wrapped = self.context.wrap_socket(request, server_side=True)
        except BaseException:
            request.close()
            raise
        return wrapped, address


def service_handler_for(application: ServiceApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Fieldora-Service"

        def do_GET(self) -> None:
            self._dispatch()

        def do_POST(self) -> None:
            self._dispatch()

        def do_PUT(self) -> None:
            self._dispatch()

        def _dispatch(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            body = self.rfile.read(min(length, 8 * 1024 * 1024 + 1)) if length else b""
            request_headers = {key.casefold(): value for key, value in self.headers.items()}
            request_headers["remote-address"] = self.client_address[0]

            if not isinstance(self.connection, ssl.SSLSocket):
                response = ApiResponse.json(403, {"error": "mtls_required"})
            else:
                peer = self.connection.getpeercert()
                serial = str(peer.get("serialNumber", "")).strip().upper()
                if not serial:
                    response = ApiResponse.json(403, {"error": "client_certificate_invalid"})
                else:
                    request_headers[_PEER_SERIAL] = serial
                    request_headers[_PEER_SUBJECT] = _distinguished_name(peer.get("subject"))
                    request_headers[_PEER_ISSUER] = _distinguished_name(peer.get("issuer"))
                    response = application.dispatch(
                        self.command, self.path, request_headers, body
                    )

            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            if not any(name.casefold() == "content-length" for name, _ in response.headers):
                self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            super().log_message(format, *args)

    return Handler


def create_service_server(
    application: ServiceApplication,
    host: str,
    port: int,
    *,
    certificate: Path,
    private_key: Path,
    client_ca: Path,
) -> MutualTLSServer:
    return MutualTLSServer(
        (host, port),
        service_handler_for(application),
        certificate,
        private_key,
        client_ca,
    )

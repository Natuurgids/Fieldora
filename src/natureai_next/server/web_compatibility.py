"""Small compatibility surface for the Fieldora managed-server web client.

The browser client is intentionally not pixel-identical to the Qt desktop client,
but shared concepts and primary workflows should remain recognizable.  This
module keeps transport-level compatibility helpers out of the domain API:
public operations probes, an OpenAPI entry point and narrowly-scoped web fixes.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from natureai_next import __version__
from natureai_next.server.api import ApiResponse

_HEALTH_ALIASES = {
    "/health": "/api/v1/health/ready",
    "/health/live": "/api/v1/health/live",
    "/health/ready": "/api/v1/health/ready",
}

# Keep this deliberately tiny.  It is appended to the existing application
# bundle so the prominent Import action behaves like the corresponding desktop
# workflow: navigate to governed import and immediately offer file selection.
_LIBRARY_IMPORT_PATCH = b"""
\n/* Fieldora cross-client compatibility: governed Library import action. */
document.querySelectorAll(\".go-import\").forEach(button=>button.onclick=()=>{
  showPage(\"library\");
  const card=q(\"import-card\");
  if(card)card.scrollIntoView({behavior:\"smooth\",block:\"start\"});
  const picker=q(\"upload-file\");
  if(picker){picker.focus();picker.click();}
});
"""


def rewrite_public_target(method: str, target: str) -> str:
    """Map short operational probe paths to the canonical public API paths."""
    if method != "GET":
        return target
    route = urlsplit(target)
    replacement = _HEALTH_ALIASES.get(route.path)
    return replacement if replacement is not None else target


def public_response(method: str, target: str) -> ApiResponse | None:
    """Return transport-level public documentation responses when applicable."""
    if method != "GET":
        return None
    path = urlsplit(target).path
    if path == "/openapi.json":
        return ApiResponse.json(200, openapi_document())
    if path in {"/docs", "/api-docs"}:
        return ApiResponse(
            200,
            _documentation_html(),
            "text/html; charset=utf-8",
        )
    return None


def patch_web_response(target: str, response: ApiResponse) -> ApiResponse:
    """Apply narrow browser compatibility fixes without forking the web bundle."""
    if (
        urlsplit(target).path != "/app.js"
        or response.status != 200
        or _LIBRARY_IMPORT_PATCH in response.body
    ):
        return response
    return ApiResponse(
        response.status,
        response.body + _LIBRARY_IMPORT_PATCH,
        response.content_type,
        response.headers,
    )


def openapi_document() -> dict[str, object]:
    """Return the initial stable OpenAPI contract for server operations/auth."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Fieldora Server API",
            "version": __version__,
            "description": (
                "Managed Fieldora server API. Domain endpoints remain governed "
                "by Fieldora authentication, policy and project scope."
            ),
        },
        "servers": [{"url": "/"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "apiKey": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Fieldora service/device API key using Bearer syntax.",
                },
            }
        },
        "paths": {
            "/api/v1/status": {
                "get": {
                    "summary": "Server version/status",
                    "responses": {"200": {"description": "Fieldora server status"}},
                }
            },
            "/api/v1/health/live": {
                "get": {
                    "summary": "Liveness probe",
                    "responses": {"200": {"description": "Process is live"}},
                }
            },
            "/api/v1/health/ready": {
                "get": {
                    "summary": "Readiness probe",
                    "responses": {
                        "200": {"description": "Configured dependencies are ready"},
                        "503": {"description": "A configured dependency is not ready"},
                    },
                }
            },
            "/api/v1/session": {
                "post": {
                    "summary": "Create an authenticated Fieldora session",
                    "requestBody": {"required": True},
                    "responses": {
                        "200": {"description": "Session created"},
                        "401": {"description": "Authentication failed"},
                    },
                },
                "delete": {
                    "summary": "Revoke the current session",
                    "security": [{"bearerAuth": []}],
                    "responses": {"204": {"description": "Session revoked"}},
                },
            },
            "/api/v1/me": {
                "get": {
                    "summary": "Current authenticated identity",
                    "security": [{"bearerAuth": []}],
                    "responses": {
                        "200": {"description": "Identity summary"},
                        "401": {"description": "Authentication required"},
                    },
                }
            },
            "/api/v1/media": {
                "get": {
                    "summary": "List governed Library media",
                    "security": [{"bearerAuth": []}],
                    "responses": {"200": {"description": "Governed media listing"}},
                }
            },
            "/api/v1/uploads": {
                "post": {
                    "summary": "Begin governed Library upload",
                    "security": [{"bearerAuth": []}],
                    "responses": {"200": {"description": "Upload session created"}},
                }
            },
        },
    }


def _documentation_html() -> bytes:
    return b"""<!doctype html>
<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Fieldora API</title></head>
<body><main><h1>Fieldora Server API</h1><p>OpenAPI 3.1 contract: <a href=\"/openapi.json\">/openapi.json</a></p><h2>Operations probes</h2><ul><li><a href=\"/health/live\">/health/live</a></li><li><a href=\"/health/ready\">/health/ready</a></li></ul><p>Governed domain endpoints require a Fieldora bearer session or API key.</p></main></body></html>"""

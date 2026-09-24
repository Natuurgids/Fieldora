"""Self-hosted Excalidraw web surface for authenticated Fieldora collaboration."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlsplit

from natureai_next.server.api import ApiResponse


class ExcalidrawWebMixin:
    """Serve the existing offline Excalidraw bundle through the Fieldora origin."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        route = urlsplit(target)
        if method == "GET" and route.path == "/whiteboards":
            suffix = f"?{route.query}" if route.query else ""
            return ApiResponse(
                302,
                b"",
                headers=(("Location", f"/whiteboards/{suffix}"),),
            )
        if method == "GET" and route.path.startswith("/whiteboards/"):
            return self._excalidraw_asset(route.path)

        response = super().dispatch(method, target, headers, body)
        if method == "GET" and route.path == "/" and response.status == 200:
            return self._excalidraw_shell_link(response)
        if method == "GET" and route.path == "/app.js" and response.status == 200:
            return self._excalidraw_shell_script(response)
        return response

    def _excalidraw_asset(self, route_path: str) -> ApiResponse:
        root = (Path(self._web_root).parent / "excalidraw").resolve()
        relative = route_path.removeprefix("/whiteboards/") or "index.html"
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            return ApiResponse.json(404, {"error": "not_found"})
        if not candidate.is_file():
            return ApiResponse.json(404, {"error": "not_found"})

        content = candidate.read_bytes()
        if candidate.name == "index.html":
            text = content.decode("utf-8")
            text = text.replace(
                "connect-src 'none'",
                "connect-src 'self'",
            )
            text = text.replace(
                '<script src="qrc:///qtwebchannel/qwebchannel.js"></script>',
                '<script src="./web-bridge.js"></script>',
            )
            text = text.replace(
                "Fieldora Offline Excalidraw",
                "Fieldora Whiteboards",
            )
            content = text.encode("utf-8")

        content_type, _encoding = mimetypes.guess_type(candidate.name)
        if candidate.suffix == ".js":
            content_type = "text/javascript"
        elif candidate.suffix == ".css":
            content_type = "text/css"
        return ApiResponse(
            200,
            content,
            f"{content_type or 'application/octet-stream'}; charset=utf-8"
            if (content_type or "").startswith(("text/", "application/javascript"))
            else (content_type or "application/octet-stream"),
            headers=(("Cache-Control", "no-store" if candidate.name == "index.html" else "public, max-age=3600"),),
        )

    @staticmethod
    def _excalidraw_shell_link(response: ApiResponse) -> ApiResponse:
        marker = "</nav>"
        text = response.body.decode("utf-8")
        if marker not in text or 'id="whiteboards-link"' in text:
            return response
        link = (
            '<button class="nav" id="whiteboards-link" type="button" '
            'data-fieldora-external-route="/whiteboards/">'
            '<span class="nav-icon">✎</span>Whiteboards</button>'
        )
        text = text.replace(marker, f"{link}{marker}", 1)
        return ApiResponse(response.status, text.encode("utf-8"), response.content_type, response.headers)

    @staticmethod
    def _excalidraw_shell_script(response: ApiResponse) -> ApiResponse:
        script = r'''
// Fieldora Excalidraw is an independent self-hosted editor. The shell only
// supplies the selected governed project when entering that module.
document.addEventListener("click",event=>{
  const link=event.target.closest?.("#whiteboards-link");
  if(!link)return;
  event.preventDefault();
  const projectContext=window.FieldoraModuleContracts?.resolve?.("projects.context.select");
  const projectId=projectContext?.current?.()||"";
  if(!projectId){window.alert("Create or select a Fieldora project before opening a whiteboard.");return;}
  window.location.assign(`/whiteboards/?project_id=${encodeURIComponent(projectId)}`);
});
'''
        body = response.body + script.encode("utf-8")
        return ApiResponse(response.status, body, response.content_type, response.headers)

from __future__ import annotations

from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.excalidraw_web import ExcalidrawWebMixin


class BaseApi:
    def __init__(self, web_root: Path) -> None:
        self._web_root = web_root

    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes) -> ApiResponse:
        if target == "/":
            return ApiResponse(
                200,
                b'<html><body><nav><button class="nav" data-page="home">Home</button></nav></body></html>',
                "text/html; charset=utf-8",
            )
        if target == "/app.js":
            return ApiResponse(
                200,
                b'let selectedProject="",projects=[];',
                "text/javascript; charset=utf-8",
            )
        return ApiResponse.json(404, {"error": "not_found"})


class TestApi(ExcalidrawWebMixin, BaseApi):
    __test__ = False


def test_whiteboards_redirect_preserves_project_query(tmp_path: Path) -> None:
    api = TestApi(tmp_path / "server_web")
    response = api.dispatch(
        "GET", "/whiteboards?project_id=project-1", {}, b""
    )
    assert response.status == 302
    assert ("Location", "/whiteboards/?project_id=project-1") in response.headers


def test_whiteboard_index_uses_same_origin_web_bridge(tmp_path: Path) -> None:
    web_root = tmp_path / "server_web"
    excalidraw = tmp_path / "excalidraw"
    web_root.mkdir()
    excalidraw.mkdir()
    (excalidraw / "index.html").write_text(
        """<!doctype html><meta http-equiv=\"Content-Security-Policy\" "
        "content=\"connect-src 'none'; frame-src 'none'\">"
        "<title>Fieldora Offline Excalidraw</title>"
        "<script src=\"qrc:///qtwebchannel/qwebchannel.js\"></script>""",
        encoding="utf-8",
    )
    (excalidraw / "web-bridge.js").write_text("window.fieldora=true;", encoding="utf-8")
    api = TestApi(web_root)

    response = api.dispatch("GET", "/whiteboards/", {}, b"")
    text = response.body.decode("utf-8")
    assert response.status == 200
    assert "connect-src 'self'" in text
    assert "connect-src 'none'" not in text
    assert 'src="./web-bridge.js"' in text
    assert "qrc:///qtwebchannel/qwebchannel.js" not in text
    assert "Fieldora Whiteboards" in text
    assert "excalidraw.com" not in text


def test_whiteboard_assets_cannot_escape_self_hosted_resource_root(tmp_path: Path) -> None:
    web_root = tmp_path / "server_web"
    excalidraw = tmp_path / "excalidraw"
    web_root.mkdir()
    excalidraw.mkdir()
    (tmp_path / "secret.txt").write_text("secret", encoding="utf-8")
    api = TestApi(web_root)

    response = api.dispatch("GET", "/whiteboards/../secret.txt", {}, b"")
    assert response.status == 404
    assert b"secret" not in response.body


def test_fieldora_shell_gets_independent_whiteboards_entry(tmp_path: Path) -> None:
    web_root = tmp_path / "server_web"
    web_root.mkdir()
    api = TestApi(web_root)

    html = api.dispatch("GET", "/", {}, b"").body.decode("utf-8")
    javascript = api.dispatch("GET", "/app.js", {}, b"").body.decode("utf-8")
    assert 'id="whiteboards-link"' in html
    assert 'href="/whiteboards/"' in html
    assert "project_id" in javascript
    assert "window.location.assign(`/whiteboards/" in javascript

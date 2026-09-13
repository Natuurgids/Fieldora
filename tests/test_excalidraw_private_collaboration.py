from __future__ import annotations

import json
from dataclasses import dataclass

from natureai_next.application.authentication import AuthenticationFailed
from natureai_next.domain.access_control import AccessDecision, Identity, IdentityKind
from natureai_next.server.api import ApiResponse
from natureai_next.server.excalidraw_api import ExcalidrawApiMixin


class FakeScience:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.revisions: dict[str, int] = {}

    def records(self, collection: str) -> tuple[dict, ...]:
        assert collection == "excalidraw_boards"
        return tuple(dict(value) for value in self.rows.values())

    def put(self, collection: str, record: dict, expected_revision: int | None) -> int:
        assert collection == "excalidraw_boards"
        identity = str(record["id"])
        current = self.revisions.get(identity, 0)
        if expected_revision is not None and expected_revision != current:
            raise ValueError("revision_conflict")
        revision = current + 1
        self.rows[identity] = dict(record)
        self.revisions[identity] = revision
        return revision


@dataclass
class FakeDecisions:
    allowed: bool = True

    def decide(self, request) -> AccessDecision:
        return AccessDecision(self.allowed, "test")


class BaseApi:
    def dispatch(self, method: str, target: str, headers: dict[str, str], body: bytes) -> ApiResponse:
        return ApiResponse.json(404, {"error": "not_found"})


class TestApi(ExcalidrawApiMixin, BaseApi):
    __test__ = False

    def __init__(self, *, authenticated: bool = True, allowed: bool = True) -> None:
        self.authenticated = authenticated
        self._science = FakeScience()
        self._decisions = FakeDecisions(allowed)
        self.identity = Identity("user-1", IdentityKind.USER, "Researcher", "org-1")

    def _identity(self, headers: dict[str, str]):
        if not self.authenticated or headers.get("authorization") != "Bearer session":
            raise AuthenticationFailed("invalid session")
        return "session", self.identity


def request(
    api: TestApi,
    method: str,
    target: str,
    payload: dict | None = None,
    *,
    revision: int | None = None,
) -> ApiResponse:
    headers = {
        "authorization": "Bearer session",
        "x-fieldora-purpose": "research",
    }
    if revision is not None:
        headers["if-match"] = str(revision)
    return api.dispatch(
        method,
        target,
        headers,
        b"" if payload is None else json.dumps(payload).encode("utf-8"),
    )


def payload(response: ApiResponse) -> dict:
    return json.loads(response.body)


def test_whiteboards_require_fieldora_authentication() -> None:
    api = TestApi(authenticated=False)
    response = api.dispatch(
        "GET", "/api/v1/excalidraw/boards?project_id=project-1", {}, b""
    )
    assert response.status == 401
    assert payload(response)["error"] == "unauthorized"


def test_non_member_cannot_list_or_create_whiteboards() -> None:
    api = TestApi(allowed=False)
    listed = request(api, "GET", "/api/v1/excalidraw/boards?project_id=project-1")
    created = request(
        api,
        "POST",
        "/api/v1/excalidraw/boards",
        {"project_id": "project-1", "title": "Private board", "scene": {}},
    )
    assert listed.status == 403
    assert created.status == 403


def test_member_can_create_open_and_revision_sync_board() -> None:
    api = TestApi()
    created = request(
        api,
        "POST",
        "/api/v1/excalidraw/boards",
        {
            "project_id": "project-1",
            "title": "Research sketch",
            "scene": {"elements": [], "appState": {}, "files": {}},
        },
    )
    assert created.status == 201
    board = payload(created)["item"]
    board_id = board["id"]
    assert board["organization_id"] == "org-1"
    assert payload(created)["collaboration"] == "internal"

    opened = request(api, "GET", f"/api/v1/excalidraw/boards/{board_id}")
    assert opened.status == 200
    assert payload(opened)["revision"] == 1

    saved = request(
        api,
        "PUT",
        f"/api/v1/excalidraw/boards/{board_id}",
        {
            "scene": {
                "elements": [{"id": "shape-1", "type": "rectangle"}],
                "appState": {},
                "files": {},
            }
        },
        revision=1,
    )
    assert saved.status == 200
    assert payload(saved)["revision"] == 2

    unchanged = request(
        api,
        "GET",
        f"/api/v1/excalidraw/boards/{board_id}/collaboration?since=2",
    )
    changed = request(
        api,
        "GET",
        f"/api/v1/excalidraw/boards/{board_id}/collaboration?since=1",
    )
    assert payload(unchanged)["changed"] is False
    assert payload(changed)["changed"] is True
    assert payload(changed)["transport"] == "authenticated-revision-sync"


def test_stale_collaborator_cannot_overwrite_newer_revision() -> None:
    api = TestApi()
    created = request(
        api,
        "POST",
        "/api/v1/excalidraw/boards",
        {"project_id": "project-1", "title": "Board", "scene": {}},
    )
    board_id = payload(created)["item"]["id"]
    first = request(
        api,
        "PUT",
        f"/api/v1/excalidraw/boards/{board_id}",
        {"scene": {"elements": [], "appState": {}, "files": {}}},
        revision=1,
    )
    stale = request(
        api,
        "PUT",
        f"/api/v1/excalidraw/boards/{board_id}",
        {"scene": {"elements": [{"id": "stale"}], "appState": {}, "files": {}}},
        revision=1,
    )
    assert first.status == 200
    assert stale.status == 409
    assert payload(stale)["error"] == "revision_conflict"


def test_cross_organization_board_is_not_disclosed() -> None:
    api = TestApi()
    api._science.rows["board-other"] = {
        "id": "board-other",
        "project_id": "project-1",
        "organization_id": "org-2",
        "title": "Other tenant",
        "revision": 1,
        "scene": {"elements": [], "appState": {}, "files": {}},
    }
    api._science.revisions["board-other"] = 1
    response = request(api, "GET", "/api/v1/excalidraw/boards/board-other")
    assert response.status == 404


def test_no_public_share_or_anonymous_room_route_exists() -> None:
    api = TestApi()
    share = request(api, "GET", "/api/v1/excalidraw/share/public-token")
    room = request(api, "GET", "/api/v1/excalidraw/rooms/anonymous")
    assert share.status == 404
    assert room.status == 404

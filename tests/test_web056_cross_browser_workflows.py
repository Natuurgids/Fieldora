from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Route, sync_playwright

from natureai_next.server.api import ApiResponse
from natureai_next.server.browser_functionality_web import (
    patch_browser_functionality_response,
)
from natureai_next.server.contract_web_compatibility import patch_contract_web_response
from natureai_next.server.facility_web_compatibility import patch_facility_web_response
from natureai_next.server.navigation_web_compatibility import patch_navigation_web_response
from natureai_next.server.science_workflow_web import patch_science_workflow_web_response
from natureai_next.server.web_compatibility import patch_web_response


@contextlib.contextmanager
def _web_fixture(tmp_path: Path):
    resource = Path("src/natureai_next/resources/server_web")
    (tmp_path / "index.html").write_bytes((resource / "index.html").read_bytes())
    response = ApiResponse(
        200,
        (resource / "app.js").read_bytes(),
        "text/javascript; charset=utf-8",
    )
    for patch in (
        patch_contract_web_response,
        patch_web_response,
        patch_facility_web_response,
        patch_navigation_web_response,
        patch_browser_functionality_response,
        patch_science_workflow_web_response,
    ):
        response = patch("/app.js", response)
    (tmp_path / "app.js").write_bytes(response.body)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            pass

    def handler(*args: object, **kwargs: object):
        return Handler(*args, directory=str(tmp_path), **kwargs)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class _WorkflowApi:
    def __init__(self) -> None:
        self.projects = [
            {
                "id": "project-existing",
                "name": "Existing Project",
                "status": "active",
                "owner_id": "admin-1",
            }
        ]
        self.media: list[dict[str, object]] = []
        self.observations: list[dict[str, object]] = []
        self.uploads: dict[str, dict[str, object]] = {}
        self.mutations: list[tuple[str, str, dict[str, object], str | None]] = []
        self._upload_number = 0
        self._media_number = 0

    @staticmethod
    def _body(route: Route) -> dict[str, object]:
        data = route.request.post_data
        return {} if not data else json.loads(data)

    @staticmethod
    def _json(route: Route, payload: object, status: int = 200) -> None:
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(payload),
        )

    def _media_items(self, query: str) -> list[dict[str, object]]:
        project_id = (parse_qs(query).get("project_id") or [""])[0]
        if not project_id:
            return list(self.media)
        return [item for item in self.media if item["project_id"] == project_id]

    def _observation(self, observation_id: str) -> dict[str, object]:
        return next(item for item in self.observations if item["id"] == observation_id)

    def _record_mutation(
        self, route: Route, path: str, body: dict[str, object]
    ) -> None:
        self.mutations.append(
            (
                route.request.method,
                path,
                body,
                route.request.headers.get("if-match"),
            )
        )

    def __call__(self, route: Route) -> None:
        parsed = urlsplit(route.request.url)
        path = parsed.path.split("/api/v1/", 1)[-1]
        method = route.request.method

        if path == "me":
            return self._json(
                route,
                {
                    "identity_id": "admin-1",
                    "display_name": "Administrator",
                    "organization_id": "local",
                },
            )
        if path == "runtime":
            return self._json(
                route,
                {"version": "5.4.0", "readiness": {"mode": "managed"}, "backends": {}},
            )
        if path == "dossiers":
            return self._json(route, {"items": []})
        if path == "projects" and method == "GET":
            return self._json(route, {"items": self.projects})
        if path == "projects" and method == "POST":
            body = self._body(route)
            item = {
                **body,
                "status": "active",
                "owner_id": "admin-1",
                "revision": 1,
            }
            self.projects.append(item)
            self._record_mutation(route, path, body)
            return self._json(route, {"item": item, "revision": 1}, 201)
        if path == "media" and method == "GET":
            return self._json(route, {"items": self._media_items(parsed.query)})
        if path == "uploads" and method == "POST":
            body = self._body(route)
            self._upload_number += 1
            upload_id = f"upload-{self._upload_number}"
            self.uploads[upload_id] = body
            self._record_mutation(route, path, body)
            return self._json(route, {"upload_id": upload_id}, 201)
        if path.startswith("uploads/") and method == "PUT":
            upload_id = path.rsplit("/", 1)[-1]
            pending = self.uploads[upload_id]
            self._media_number += 1
            media_id = f"imported-{self._media_number}"
            item = {
                "media_id": media_id,
                "mime_type": pending["mime_type"],
                "size_bytes": pending["size_bytes"],
                "project_id": pending["project_id"],
                "sha256": pending["sha256"],
                "download_url": f"/api/v1/media/{media_id}",
            }
            self.media.append(item)
            self._record_mutation(route, path, {},)
            return self._json(route, {"media_id": media_id})
        if path == "observations" and method == "GET":
            return self._json(route, {"items": self.observations})
        if path == "observations" and method == "POST":
            body = self._body(route)
            item = {
                "id": "observation-1",
                **body,
                "supporting_asset_ids": [],
                "confirmation_state": "unconfirmed",
                "revision": 1,
            }
            self.observations.append(item)
            self._record_mutation(route, path, body)
            return self._json(route, {"item": item, "revision": 1}, 201)
        if path.endswith("/evidence") and method == "POST":
            observation_id = path.split("/")[1]
            item = self._observation(observation_id)
            body = self._body(route)
            assert route.request.headers.get("if-match") == str(item["revision"])
            asset_id = str(body["asset_id"])
            supporting = list(item["supporting_asset_ids"])
            if asset_id not in supporting:
                supporting.append(asset_id)
            item["supporting_asset_ids"] = supporting
            item["revision"] = int(item["revision"]) + 1
            self._record_mutation(route, path, body)
            return self._json(route, {"item": item, "revision": item["revision"]})
        if path.startswith("observations/") and method == "PATCH":
            observation_id = path.split("/")[1]
            item = self._observation(observation_id)
            body = self._body(route)
            assert route.request.headers.get("if-match") == str(item["revision"])
            item.update(body)
            item["revision"] = int(item["revision"]) + 1
            self._record_mutation(route, path, body)
            return self._json(route, {"item": item, "revision": item["revision"]})

        return self._json(route, {"items": []})


@pytest.mark.parametrize("browser_name", ("chromium", "firefox", "webkit"))
def test_web056_complete_create_import_link_edit_review_workflow(
    tmp_path: Path, browser_name: str
) -> None:
    backend = _WorkflowApi()
    with _web_fixture(tmp_path) as url, sync_playwright() as playwright:
        browser = getattr(playwright, browser_name).launch(headless=True)
        page = browser.new_page()
        page.route("**/api/v1/**", backend)
        page.add_init_script(
            "sessionStorage.setItem('fieldora-session','browser-certification-token')"
        )
        page.goto(url)
        page.wait_for_selector("#workspace:not([hidden])")

        page.locator('.nav[data-page="projects"]').click()
        page.locator("#portfolio-new-project").click()
        page.locator("#portfolio-project-name").fill("Cross-browser Survey")
        page.locator("#portfolio-project-save").click()
        page.wait_for_selector("#portfolio-project-editor[hidden]")
        created = next(
            project for project in backend.projects if project["name"] == "Cross-browser Survey"
        )
        project_id = str(created["id"])

        page.locator('.nav[data-page="library"]').click()
        page.locator("#upload-project").select_option(project_id)
        page.locator("#upload-file").set_input_files(
            [
                {
                    "name": "primary.jpg",
                    "mimeType": "image/jpeg",
                    "buffer": b"primary evidence",
                },
                {
                    "name": "support.jpg",
                    "mimeType": "image/jpeg",
                    "buffer": b"supporting evidence",
                },
            ]
        )
        page.locator("#upload-start").click()
        page.wait_for_function(
            "document.querySelector('#upload-status').textContent.includes('2 files verified')"
        )
        assert [item["media_id"] for item in backend.media] == ["imported-1", "imported-2"]
        assert {item["project_id"] for item in backend.media} == {project_id}

        page.locator('.nav[data-page="observations"]').click()
        page.locator('[data-task-view="create"]').click()
        page.locator("#obs-project").select_option(project_id)
        page.locator("#obs-asset").select_option("imported-1")
        page.locator("#obs-type").select_option("organism")
        page.locator("#obs-count").fill("3")
        page.locator("#obs-notes").fill("Created in browser workflow")
        page.locator("#obs-save-aligned").click()
        page.wait_for_selector('[data-observation="observation-1"]')
        assert backend.observations[0]["asset_id"] == "imported-1"
        assert backend.observations[0]["revision"] == 1

        page.locator('[data-observation="observation-1"]').click()
        page.wait_for_selector("#observation-editor-title:text('Edit observation')")
        page.locator("#obs-supporting-select").select_option("imported-2")
        page.locator("#obs-supporting-link").click()
        page.wait_for_function(
            "document.querySelector('#obs-supporting-list').textContent.includes('imported-2')"
        )
        assert backend.observations[0]["supporting_asset_ids"] == ["imported-2"]
        assert backend.observations[0]["asset_id"] == "imported-1"
        assert backend.observations[0]["revision"] == 2

        page.locator("#obs-notes").fill("Edited after supporting evidence link")
        page.locator("#obs-save-aligned").click()
        page.wait_for_selector('[data-observation="observation-1"]')
        assert backend.observations[0]["notes"] == "Edited after supporting evidence link"
        assert backend.observations[0]["revision"] == 3

        checkbox = page.locator('[data-observation-select="observation-1"]')
        checkbox.check()
        page.locator('[data-observation-decision="confirmed"]').click()
        page.wait_for_function(
            "document.querySelector('[data-observation=\"observation-1\"] .pill').textContent.includes('confirmed')"
        )
        assert backend.observations[0]["confirmation_state"] == "confirmed"
        assert backend.observations[0]["revision"] == 4
        assert backend.observations[0]["asset_id"] == "imported-1"
        assert backend.observations[0]["supporting_asset_ids"] == ["imported-2"]

        observation_mutations = [
            mutation for mutation in backend.mutations if "observation" in mutation[1]
        ]
        assert [mutation[3] for mutation in observation_mutations] == [None, "1", "2", "3"]
        browser.close()

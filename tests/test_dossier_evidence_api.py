from __future__ import annotations

import json
from types import SimpleNamespace

from natureai_next.server.api import ApiResponse
from natureai_next.server.dossier_evidence_api import DossierEvidenceApiMixin
from natureai_next.server.dossier_module_web import patch_dossier_module_response
from natureai_next.server.media_links import new_association
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


class _BaseApi:
    def dispatch(self, method, target, headers, body):
        return ApiResponse.json(404, {"error": "not_found"})


class _Decisions:
    def __init__(self, denied_actions=()):
        self.denied_actions = set(denied_actions)
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return SimpleNamespace(allowed=request.action not in self.denied_actions)


class _Science:
    def records(self, collection):
        assert collection == "dossiers"
        return (
            {
                "id": "dossier-1",
                "project_id": "project-1",
                "name": "Research dossier",
            },
        )


class _Associations:
    def __init__(self):
        self.items = []

    def link(self, association):
        self.items = [
            item
            for item in self.items
            if not (
                item.media_id == association.media_id
                and item.association_type == association.association_type
                and item.target_id == association.target_id
            )
        ]
        self.items.append(association)

    def unlink(self, media_id, organization_id, association_type, target_id):
        self.items = [
            item
            for item in self.items
            if not (
                item.media_id == media_id
                and item.organization_id == organization_id
                and item.association_type == association_type
                and item.target_id == target_id
            )
        ]

    def links(self, media_id, organization_id):
        return tuple(
            item
            for item in self.items
            if item.media_id == media_id and item.organization_id == organization_id
        )

    def linked_media_ids(self, organization_id, association_type, target_id):
        return tuple(
            item.media_id
            for item in self.items
            if item.organization_id == organization_id
            and item.association_type == association_type
            and item.target_id == target_id
        )


class _Media:
    def __init__(self):
        self.associations = _Associations()
        self._record = SimpleNamespace(
            media_id="media-1",
            organization_id="org-1",
            project_id="project-source",
            mime_type="image/jpeg",
            size_bytes=123,
            sha256="abc123",
        )

    def record(self, media_id):
        return self._record if media_id == self._record.media_id else None


class _Api(DossierEvidenceApiMixin, _BaseApi):
    def __init__(self, denied_actions=()):
        self._science = _Science()
        self._media = _Media()
        self._decisions = _Decisions(denied_actions)

    def _identity(self, headers):
        return "token", SimpleNamespace(identity_id="user-1", organization_id="org-1")


def _json(response):
    return json.loads(response.body)


def test_dossier_media_association_preserves_canonical_library_identity() -> None:
    api = _Api()
    before = vars(api._media._record).copy()

    linked = api.dispatch(
        "POST",
        "/api/v1/dossiers/dossier-1/media-links",
        {"x-fieldora-purpose": "research"},
        b'{"media_id":"media-1"}',
    )

    assert linked.status == 201
    item = _json(linked)["item"]
    assert item["media_id"] == "media-1"
    assert item["association_type"] == "dossier"
    assert item["target_id"] == "dossier-1"
    assert item["linked_by"] == "user-1"
    assert vars(api._media._record) == before
    assert api._media.associations.items[0].media_id == api._media._record.media_id


def test_dossier_evidence_read_returns_stable_media_id_and_provenance() -> None:
    api = _Api()
    api._media.associations.link(
        new_association(
            media_id="media-1",
            organization_id="org-1",
            association_type="dossier",
            target_id="dossier-1",
            purpose="research",
            linked_by="user-1",
            now_epoch=1234,
        )
    )

    response = api.dispatch(
        "GET",
        "/api/v1/dossiers/dossier-1/media-links",
        {"x-fieldora-purpose": "research"},
        b"",
    )

    assert response.status == 200
    item = _json(response)["items"][0]
    assert item == {
        "media_id": "media-1",
        "mime_type": "image/jpeg",
        "size_bytes": 123,
        "sha256": "abc123",
        "linked_by": "user-1",
        "linked_at_epoch": 1234,
    }


def test_dossier_evidence_link_requires_dossier_edit_asset_view_and_link_authority() -> None:
    for denied in ("edit", "view", "link"):
        api = _Api({denied})
        response = api.dispatch(
            "POST",
            "/api/v1/dossiers/dossier-1/media-links",
            {"x-fieldora-purpose": "research"},
            b'{"media_id":"media-1"}',
        )
        expected = 404 if denied == "edit" else 403
        assert response.status == expected
        assert api._media.associations.items == []


def test_dossier_evidence_unlink_removes_only_association_not_library_record() -> None:
    api = _Api()
    record = api._media._record
    api._media.associations.link(
        new_association(
            media_id="media-1",
            organization_id="org-1",
            association_type="dossier",
            target_id="dossier-1",
            purpose="research",
            linked_by="user-1",
            now_epoch=1234,
        )
    )

    response = api.dispatch(
        "DELETE",
        "/api/v1/dossiers/dossier-1/media-links/media-1",
        {"x-fieldora-purpose": "research"},
        b"",
    )

    assert response.status == 204
    assert api._media.associations.items == []
    assert api._media.record("media-1") is record


def test_dossier_browser_uses_data_service_for_stable_media_associations() -> None:
    response = patch_dossier_module_response(
        "/app.js",
        ApiResponse(200, b"const baseApp=true;", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")
    provider = script.split("WEB-DOSSIER-DATA-SERVICE", 1)[1].split(
        "WEB-DOSSIER-MODULE", 1
    )[0]
    presentation = script.split("WEB-DOSSIER-MODULE", 1)[1]

    assert "/api/v1/media?limit=200" in provider
    assert "/media-links" in provider
    assert "media_id:mid" in provider
    assert "linkEvidence" in provider
    assert "unlinkEvidence" in provider
    assert "await service.linkEvidence(dossierId,mediaId)" in presentation
    assert "await service.unlinkEvidence(dossierId,mediaId)" in presentation
    assert "item.media_id" in presentation
    assert "item.sha256" in presentation
    assert "api(" not in presentation
    assert "fieldora:dossier-evidence-changed" in presentation


def test_dossier_evidence_api_is_composed_below_dossier_presentation_owner() -> None:
    mro = OfflineFirstFieldoraApi.__mro__
    presentation = next(base for base in mro if base.__name__ == "DossierModuleWebApiMixin")
    api = next(base for base in mro if base.__name__ == "DossierEvidenceApiMixin")

    assert mro.index(presentation) < mro.index(api)

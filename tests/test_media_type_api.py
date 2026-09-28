from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from natureai_next.domain.access_control import Identity, IdentityKind
from natureai_next.server.media_type_api import CanonicalMediaTypeApiMixin


class _AllowDecisions:
    def decide(self, request):
        return SimpleNamespace(allowed=True)


class _Media:
    def __init__(self) -> None:
        self.mime_type = ""

    def begin_upload(
        self,
        subject_id,
        organization_id,
        project_id,
        filename,
        mime_type,
        expected_size,
        expected_sha256,
    ):
        self.mime_type = mime_type
        return SimpleNamespace(upload_id="upload-1")


class _Api(CanonicalMediaTypeApiMixin):
    def __init__(self) -> None:
        self._media = _Media()
        self._decisions = _AllowDecisions()


def _identity() -> Identity:
    return Identity("user-1", IdentityKind.USER, "Researcher", "org-1")


def test_direct_upload_recovers_pdf_from_generic_browser_type():
    api = _Api()
    payload = {
        "project_id": "project-1",
        "filename": "evidence.pdf",
        "mime_type": "application/octet-stream",
        "size_bytes": 3,
        "sha256": hashlib.sha256(b"pdf").hexdigest(),
    }
    response = api._begin_upload({}, json.dumps(payload).encode(), _identity())
    assert response.status == 201
    assert api._media.mime_type == "application/pdf"


def test_direct_upload_preserves_specific_declared_type():
    api = _Api()
    payload = {
        "project_id": "project-1",
        "filename": "evidence.bin",
        "mime_type": "application/vnd.example.field-data",
        "size_bytes": 3,
        "sha256": hashlib.sha256(b"bin").hexdigest(),
    }
    response = api._begin_upload({}, json.dumps(payload).encode(), _identity())
    assert response.status == 201
    assert api._media.mime_type == "application/vnd.example.field-data"

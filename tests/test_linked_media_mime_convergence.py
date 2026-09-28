from __future__ import annotations

from types import SimpleNamespace

from natureai_next.server.linked_media_convergence import converge_linked_media


class _Linked:
    def __init__(self) -> None:
        self.record = SimpleNamespace(
            relative_path="survey/photo.jpg",
            mime_type="application/octet-stream",
            size_bytes=123,
            sha256="a" * 64,
            availability="available",
        )

    def records(self, organization_id, source_id):
        return (self.record,)


class _Media:
    def __init__(self) -> None:
        self.mime_type = ""

    def attach_referenced(self, **kwargs):
        self.mime_type = kwargs["mime_type"]
        return SimpleNamespace(media_id="media-1")


def test_linked_media_convergence_recovers_type_from_relative_filename():
    linked = _Linked()
    media = _Media()
    converge_linked_media(
        linked_storage=linked,
        media=media,
        organization_id="org-1",
        project_id="project-1",
        source_id="source-1",
    )
    assert media.mime_type == "image/jpeg"

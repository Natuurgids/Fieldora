from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.knowledge_parity_api import KnowledgeParityApiMixin
from natureai_next.server.knowledge_review_web import patch_knowledge_review_web_response
from natureai_next.server.offline_first_api import OfflineFirstFieldoraApi


def test_managed_api_composes_knowledge_parity_before_legacy_collection_mutations() -> None:
    assert issubclass(OfflineFirstFieldoraApi, KnowledgeParityApiMixin)
    assert OfflineFirstFieldoraApi.__mro__.index(KnowledgeParityApiMixin) < (
        OfflineFirstFieldoraApi.__mro__.index(
            next(
                cls
                for cls in OfflineFirstFieldoraApi.__mro__
                if cls.__name__ == "FieldoraApi"
            )
        )
    )


def test_knowledge_browser_renders_review_state_provenance_and_accepted_trace() -> None:
    response = patch_knowledge_review_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "Provenance" in script
    assert "review_state" in script
    assert "pending" in script
    assert "deferred" in script
    assert "Accepted conclusion" in script
    assert "source_suggestion_public_id" in script
    assert "acceptance_action_public_id" in script
    assert "source_snapshot" in script


def test_knowledge_browser_uses_explicit_revisioned_review_actions() -> None:
    response = patch_knowledge_review_web_response(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "Accept" in script
    assert "Reject" in script
    assert "Defer" in script
    assert "/review`" in script
    assert 'method:"POST"' in script
    assert '"If-Match":String(item.revision||1)' in script
    assert "JSON.stringify({action})" in script
    assert 'api("/api/v1/knowledge")' in script
    assert 'method:"PUT"' not in script
    assert 'review_state:"accepted"' not in script
    assert "crypto.randomUUID()" not in script

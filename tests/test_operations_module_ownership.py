from __future__ import annotations

from natureai_next.server.operations_module_ownership import (
    FACILITIES_OPERATIONS_API_DOMAINS,
    OPERATIONS_API_DOMAINS,
    operations_api_domain,
    operations_api_owner,
)
from natureai_next.server.web_module_extensions import (
    FACILITIES_WEB_MODULE_ID,
    OPERATIONS_WEB_MODULE_ID,
)


def test_shared_operations_api_domains_have_single_module_owner() -> None:
    assert OPERATIONS_API_DOMAINS.isdisjoint(FACILITIES_OPERATIONS_API_DOMAINS)

    for domain in OPERATIONS_API_DOMAINS:
        path = f"/api/v1/operations/{domain}/example"
        assert operations_api_domain(path) == domain
        assert operations_api_owner(path) == OPERATIONS_WEB_MODULE_ID

    for domain in FACILITIES_OPERATIONS_API_DOMAINS:
        path = f"/api/v1/operations/{domain}/example"
        assert operations_api_domain(path) == domain
        assert operations_api_owner(path) == FACILITIES_WEB_MODULE_ID


def test_shared_operations_api_classifier_does_not_claim_unknown_paths() -> None:
    assert operations_api_domain("/api/v1/projects") is None
    assert operations_api_domain("/api/v1/operations/") is None
    assert operations_api_owner("/api/v1/operations/unknown") is None

from __future__ import annotations

from pathlib import Path

import pytest

from natureai_next.application.deletion_approvals import (
    ApprovalPrincipal,
    ApproverResolver,
    DeletionApprovalService,
)


def _principals() -> tuple[ApprovalPrincipal, ...]:
    return (
        ApprovalPrincipal("requester", "Researcher", "org-1", ("contributor",)),
        ApprovalPrincipal("steward", "Data Steward", "org-1", ("data-steward",)),
        ApprovalPrincipal("admin", "Administrator", "org-1", ("administrator",)),
    )


def test_function_person_and_administrator_fallback_routing() -> None:
    assert ApproverResolver.resolve(
        requester_id="requester", organization_id="org-1",
        target_kind="function", target_value="data-steward",
        principals=_principals(),
    ) == ("steward", "organization-function:data-steward")
    assert ApproverResolver.resolve(
        requester_id="requester", organization_id="org-1",
        target_kind="person", target_value="missing-person",
        principals=_principals(),
    ) == ("admin", "administrator-fallback")


def test_sole_administrator_is_final_local_approver() -> None:
    principals = (
        ApprovalPrincipal("only-admin", "Only administrator", "org-1", ("admin",)),
    )
    assert ApproverResolver.resolve(
        requester_id="only-admin", organization_id="org-1",
        target_kind="function", target_value="data-steward", principals=principals,
    ) == ("only-admin", "sole-administrator-fallback")


def test_request_resolution_is_assigned_and_audited(tmp_path: Path) -> None:
    service = DeletionApprovalService(tmp_path / "deletion-approvals.sqlite3")
    request = service.request(
        resource_id="asset-1", organization_id="org-1",
        requested_by="requester", target_kind="function",
        target_value="data-steward", reason="Private document",
        principals=_principals(),
    )
    assert request.assigned_to == "steward"
    with pytest.raises(PermissionError):
        service.resolve(request.request_id, approver_id="requester", approve=True)
    assert service.resolve(
        request.request_id, approver_id="steward", approve=True
    ).state == "approved"


def test_desktop_exposes_trash_approval_queue() -> None:
    trash = Path("src/natureai_next/ui/qt/trash_manager.py").read_text(encoding="utf-8")
    shell = Path("src/natureai_next/ui/qt/application.py").read_text(encoding="utf-8")
    assert "Trash & Deletion Approvals" in trash
    assert "Pending Server Approval" in trash
    assert '"Trash & Deletion Approvals", "Trash Manager"' in shell

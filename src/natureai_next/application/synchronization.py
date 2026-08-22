"""Application service for Phase E endpoint, device, enrollment, and rights management."""

from __future__ import annotations

from natureai_next.domain.synchronization import (
    PlatformAccount,
    ProjectEnrollment,
    RegisteredDesktopDevice,
    SyncChange,
)
from natureai_next.ports.synchronization import DesktopSynchronizationRepository


class DesktopSynchronizationService:
    def __init__(self, repository: DesktopSynchronizationRepository) -> None:
        self._repository = repository

    def save_account(self, account: PlatformAccount) -> None:
        self._repository.put_account(account)

    def register_device(self, device: RegisteredDesktopDevice) -> None:
        if not any(item.account_id == device.account_id for item in self._repository.accounts()):
            raise KeyError(device.account_id)
        self._repository.put_device(device)

    def enroll_project(self, enrollment: ProjectEnrollment) -> None:
        if not any(
            item.account_id == enrollment.account_id for item in self._repository.accounts()
        ):
            raise KeyError(enrollment.account_id)
        self._repository.put_enrollment(enrollment)

    def rights_view(self, account_id: str, *, at_utc: str) -> dict[str, tuple[str, ...]]:
        return {
            enrollment.project_id: enrollment.effective_rights(at_utc)
            for enrollment in self._repository.enrollments(account_id)
        }

    def queue_contribution(self, change: SyncChange, *, at_utc: str) -> bool:
        enrollment = next(
            (
                item
                for account in self._repository.accounts()
                for item in self._repository.enrollments(account.account_id)
                if item.enrollment_id == change.enrollment_id
            ),
            None,
        )
        if enrollment is None or "contribute" not in enrollment.effective_rights(at_utc):
            raise PermissionError("active contribute right is required")
        return self._repository.enqueue_outbox(change)

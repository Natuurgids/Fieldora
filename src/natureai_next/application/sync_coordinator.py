"""Rights-gated orchestration between durable journals and a remote transport."""

from __future__ import annotations

from natureai_next.domain.sync_protocol import PushDisposition
from natureai_next.domain.synchronization import SyncConflict
from natureai_next.ports.sync_transport import SynchronizationTransport
from natureai_next.ports.synchronization import DesktopSynchronizationRepository


class DesktopSyncCoordinator:
    def __init__(
        self,
        repository: DesktopSynchronizationRepository,
        transport: SynchronizationTransport,
    ) -> None:
        self._repository = repository
        self._transport = transport

    def _rights(self, enrollment_id: str, at_utc: str) -> tuple[str, ...]:
        for account in self._repository.accounts():
            for enrollment in self._repository.enrollments(account.account_id):
                if enrollment.enrollment_id == enrollment_id:
                    return enrollment.effective_rights(at_utc)
        return ()

    def push_once(
        self,
        enrollment_id: str,
        *,
        now_utc: str,
        lease_until_utc: str,
        limit: int = 100,
    ) -> int:
        enrollment = None
        for account in self._repository.accounts():
            enrollment = next(
                (item for item in self._repository.enrollments(account.account_id)
                 if item.enrollment_id == enrollment_id),
                enrollment,
            )
        if enrollment is None or "contribute" not in enrollment.effective_rights(now_utc):
            raise PermissionError("active contribute right is required")
        if not self._repository.has_current_acknowledgment(
            enrollment_id, enrollment.revision
        ):
            raise PermissionError("current contract and license acknowledgment is required")
        claimed = self._repository.claim_outbox(
            enrollment_id=enrollment_id,
            now_utc=now_utc,
            lease_until_utc=lease_until_utc,
            limit=limit,
        )
        if not claimed:
            return 0
        results = self._transport.push(enrollment_id=enrollment_id, changes=claimed)
        by_id = {result.change_id: result for result in results}
        for change in claimed:
            result = by_id.get(change.change_id)
            if result is None or result.disposition is PushDisposition.RETRY:
                retry_at = result.retry_at_utc if result is not None else lease_until_utc
                self._repository.retry_outbox(
                    change.change_id, next_attempt_at_utc=retry_at or lease_until_utc
                )
            elif result.disposition in {PushDisposition.APPLIED, PushDisposition.DUPLICATE}:
                self._repository.complete_outbox(change.change_id)
            elif result.disposition is PushDisposition.REJECTED:
                self._repository.stop_outbox(change.change_id, state="rejected")
            else:
                self._repository.stop_outbox(change.change_id, state="conflict")
                self._repository.put_conflict(
                    SyncConflict(
                        f"conflict:{change.change_id}", enrollment_id,
                        change.aggregate_type, change.aggregate_id, change.base_revision,
                        result.remote_revision, change.payload, result.remote_payload or {},
                        now_utc,
                    )
                )
        return len(claimed)

    def pull_once(self, enrollment_id: str, *, at_utc: str, limit: int = 100) -> int:
        if "view" not in self._rights(enrollment_id, at_utc):
            raise PermissionError("active view right is required")
        cursor = self._repository.cursor(enrollment_id)
        page = self._transport.pull(
            enrollment_id=enrollment_id, cursor=cursor, limit=limit
        )
        if page.enrollment_id != enrollment_id:
            raise ValueError("pull response enrollment mismatch")
        for change in page.changes:
            if change.enrollment_id != enrollment_id:
                raise ValueError("pull change enrollment mismatch")
            self._repository.accept_inbox(change)
        # Advance only after every item is durably accepted. Replaying a page is
        # safe because inbox idempotency keys are unique.
        self._repository.put_cursor(enrollment_id, page.next_cursor)
        return len(page.changes)

"""Adapters from independent durable stores to the shared Activity Centre contract."""
from __future__ import annotations
from natureai_next.application.activity_contracts import ActivitySnapshot, ActivityState
from natureai_next.domain.jobs import JobState

_JOB_STATES={JobState.QUEUED:ActivityState.QUEUED,JobState.RUNNING:ActivityState.RUNNING,JobState.PAUSED:ActivityState.PAUSED,JobState.SUCCEEDED:ActivityState.COMPLETED,JobState.FAILED:ActivityState.FAILED,JobState.CANCELLED:ActivityState.CANCELLED,JobState.INTERRUPTED:ActivityState.INTERRUPTED}
class JobActivitySource:
    def __init__(self, jobs): self.jobs=jobs
    def list_activity(self, limit=100):
        return tuple(ActivitySnapshot(j.public_id,"jobs",j.job_type,j.job_type.replace("."," ").title(),_JOB_STATES[j.state],j.progress_current,j.progress_total,j.progress_unit,j.progress_message,j.error_code,j.state in {JobState.FAILED,JobState.INTERRUPTED},str(j.resource_class),j.modified_at_us) for j in self.jobs.recent(limit))
    def cancel_activity(self, activity_id): return self.jobs.cancel(activity_id)
    def retry_activity(self, activity_id): return self.jobs.resume(activity_id)

class StorageJournalActivitySource:
    def __init__(self, journal): self.journal=journal
    def list_activity(self, limit=100):
        states={"pending":ActivityState.QUEUED,"running":ActivityState.RUNNING,"completed":ActivityState.COMPLETED,"failed":ActivityState.FAILED,"cancelled":ActivityState.CANCELLED}
        return tuple(ActivitySnapshot(r["public_id"],"storage",r["kind"],f"{r['kind'].title()} {r['source_path']}",states.get(r["state"],ActivityState.BLOCKED),0,None,"file",r["error"],r["error"],r["state"]=="failed","io",r["modified_at_us"]) for r in self.journal.list_recent(limit))
    def cancel_activity(self, activity_id): return self.journal.cancel(activity_id)
    def retry_activity(self, activity_id): return self.journal.retry(activity_id)

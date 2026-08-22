from pathlib import Path
from natureai_next.application.activity_contracts import ActivityRegistry, ActivitySnapshot, ActivityState
from natureai_next.application.resources import ResourceBroker
from natureai_next.application.storage_transactions import StorageTransactionJournal

def test_activity_registry_federates_without_shared_store():
    class Source:
        def list_activity(self, limit=100): return (ActivitySnapshot("1","x","k","Work",ActivityState.RUNNING,1,2,modified_at_us=5),)
        def cancel_activity(self, activity_id): return True
        def retry_activity(self, activity_id): return False
    r=ActivityRegistry(); r.register("x",Source())
    assert r.list_activity()[0].source=="x" and r.cancel("x","1")

def test_storage_failed_requires_explicit_retry(tmp_path):
    journal=StorageTransactionJournal(tmp_path/'ops.sqlite3')
    op=journal.queue('copy',tmp_path/'missing',tmp_path/'out')
    assert journal.run_pending()[0].state=='failed'
    assert journal.run_pending()==()
    assert journal.retry(op) is True

def test_resource_broker_independent_slots():
    broker=ResourceBroker({'io':1,'gpu':1})
    with broker.acquire('io'):
        with broker.acquire('gpu'): pass

def test_build30_identity():
    import natureai_next
    assert natureai_next.__version__ == "5.4.0"

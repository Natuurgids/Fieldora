from __future__ import annotations
import hashlib, sqlite3, time
from pathlib import Path
from PIL import Image
from natureai_next.application.storage_transactions import StorageTransactionJournal
from natureai_next.infrastructure.imaging.catalog_thumbnails import PillowCatalogThumbnailProvider


def test_offline_browsing_uses_persistent_thumbnail(tmp_path: Path):
    src=tmp_path/'linked.jpg'; Image.new('RGB',(800,600)).save(src)
    p=PillowCatalogThumbnailProvider(thumbnail_root=tmp_path/'thumbs')
    assert p.materialize(source_path=src,max_size=256)
    cached=p.cache_path(source_path=src,max_size=256)
    assert cached is not None
    src.unlink()
    data=p.load(source_path=src,cached_path=cached,max_size=256)
    assert data and data.startswith(b'\xff\xd8')
    p.close()


def test_gallery_provider_persists_worker_generated_thumbnail(tmp_path: Path):
    src=tmp_path/'a.jpg'; Image.new('RGB',(100,100)).save(src)
    p=PillowCatalogThumbnailProvider(thumbnail_root=tmp_path/'thumbs',background_workers=1)
    stable=p.asset_cache_path('asset-1')
    assert stable is not None
    assert not p.enqueue(source_path=src,max_size=256)
    first=p.load(source_path=src,cached_path=stable,max_size=256)
    assert first and stable.is_file()
    src.unlink()
    assert p.load(source_path=src,cached_path=stable,max_size=256)==first
    p.close()


def test_copy_failure_does_not_abort_batch_and_resume_is_idempotent(tmp_path: Path):
    db=tmp_path/'journal.db'; j=StorageTransactionJournal(db)
    good=tmp_path/'good'; good.write_bytes(b'good')
    missing=tmp_path/'missing'
    j.queue('copy',missing,tmp_path/'bad-copy')
    j.queue('copy',good,tmp_path/'good-copy',hashlib.sha256(b'good').hexdigest())
    r=j.run_pending(); assert [x.state for x in r]==['failed','completed']
    assert (tmp_path/'good-copy').read_bytes()==b'good'
    r2=j.run_pending(); assert r2==()
    failed_id=next(x.public_id for x in r if x.state=='failed')
    assert j.retry(failed_id)
    r3=j.run_pending(); assert len(r3)==1 and r3[0].state=='failed'


def test_move_deletes_source_only_after_verified_destination(tmp_path: Path):
    db=tmp_path/'journal.db'; j=StorageTransactionJournal(db)
    src=tmp_path/'source'; src.write_bytes(b'data')
    j.queue('move',src,tmp_path/'dest',hashlib.sha256(b'data').hexdigest())
    result=j.run_pending()[0]
    assert result.state=='completed' and not src.exists() and (tmp_path/'dest').read_bytes()==b'data'


def test_graceful_cancellation_leaves_pending_work(tmp_path: Path):
    db=tmp_path/'journal.db'; j=StorageTransactionJournal(db)
    for i in range(2):
        s=tmp_path/f's{i}'; s.write_bytes(b'x'); j.queue('copy',s,tmp_path/f'd{i}')
    def cancel(): raise RuntimeError('cancel')
    assert j.run_pending(cancel=cancel)==()
    with sqlite3.connect(db) as c:
        assert c.execute("select count(*) from storage_operation_journal where state='pending'").fetchone()[0]==2

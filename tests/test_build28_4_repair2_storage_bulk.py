from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from natureai_next.application.storage import AssetStorageService
from natureai_next.infrastructure.database.migrations import CORE_MIGRATIONS
from natureai_next.infrastructure.database.migrations.core import MigrationRunner


def _catalog(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    MigrationRunner(CORE_MIGRATIONS, "test").apply(c)
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _hybrid_asset(c: sqlite3.Connection, root: Path, name: str) -> tuple[int, Path, Path]:
    now = 1
    source = root / "source" / name
    managed = root / "managed" / "originals" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    managed.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(name.encode())
    managed.write_bytes(name.encode())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    asset_id = int(c.execute(
        "INSERT INTO assets(public_id,media_type,lifecycle_state,created_at_us,modified_at_us,revision) VALUES(?,?, 'active',?,?,1)",
        (f"asset-{name}", "image", now, now),
    ).lastrowid)
    provider = int(c.execute(
        "INSERT INTO storage_providers(public_id,kind,display_name,configuration_json,created_at_us,modified_at_us) VALUES(?, 'local_filesystem','Local','{}',?,?)",
        (f"provider-{name}", now, now),
    ).lastrowid)
    source_file = int(c.execute(
        "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,sha256,availability_state,created_at_us,modified_at_us) VALUES(?,?, 'referenced','alternate',?,?,?,?, 'available',?,?)",
        (f"source-file-{name}", asset_id, str(source), str(source).casefold(), source.stat().st_size, digest, now, now),
    ).lastrowid)
    managed_file = int(c.execute(
        "INSERT INTO file_instances(public_id,asset_id,storage_mode,role,normalized_path,path_key,file_size,sha256,availability_state,created_at_us,modified_at_us) VALUES(?,?, 'managed','original',?,?,?,?, 'available',?,?)",
        (f"managed-file-{name}", asset_id, str(managed), str(managed).casefold(), managed.stat().st_size, digest, now, now),
    ).lastrowid)
    c.execute("UPDATE assets SET primary_file_instance_id=? WHERE id=?", (managed_file, asset_id))
    c.execute("INSERT INTO library_assets(asset_public_id,asset_type,primary_file_public_id,availability_state,created_at_us,updated_at_us) VALUES(?, 'photo',?, 'available',?,?)", (f"asset-{name}", f"managed-file-{name}", now, now))
    c.execute("INSERT INTO asset_storage_policies(asset_id,policy,created_at_us,modified_at_us) VALUES(?, 'hybrid',?,?)", (asset_id, now, now))
    for role, path, file_id, primary, provenance in (
        ("source", source, source_file, 0, "initial"),
        ("aperture_master", managed, managed_file, 1, "managed_copy"),
    ):
        c.execute(
            "INSERT INTO asset_storage_locations(public_id,asset_id,provider_id,file_instance_id,role,normalized_path,path_key,file_size,sha256,health,is_primary,created_at_us,modified_at_us,provenance_role,discovered_at_us) VALUES(?,?,?,?,?,?,?,?,?,'available',?,?,?,?,?)",
            (f"{role}-{name}", asset_id, provider, file_id, role, str(path), str(path).casefold(), path.stat().st_size, digest, primary, now, now, provenance, now),
        )
    plan = int(c.execute("INSERT INTO import_plans(public_id,schema_version,duplicate_policy,state,created_at_us) VALUES(?,1,'skip_exact','completed',?)", (f"plan-{name}", now)).lastrowid)
    c.execute(
        "INSERT INTO import_plan_items(plan_id,item_key,source_path,source_size,source_modified_at_us,sha256,fast_fingerprint,storage_policy,source_disposition,decision,state,asset_id,file_instance_id,modified_at_us) VALUES(?,?,?,?,?,?,?,?,?,'new','succeeded',?,?,?)",
        (plan, name, str(source), source.stat().st_size, now, digest, digest[:16], "hybrid", "keep", asset_id, managed_file, now),
    )
    c.commit()
    return asset_id, source, managed


def test_bulk_remove_rebinds_foreign_keys_and_deletes_managed_files(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    c = _catalog(db)
    asset_id, source, managed = _hybrid_asset(c, tmp_path, "a.jpg")
    c.close()

    service = AssetStorageService(db, tmp_path / "managed" / "originals")
    preview = service.managed_removal_preview([asset_id])
    assert preview.removable_asset_ids == (asset_id,)
    assert preview.reclaimable_bytes == managed.stat().st_size
    service.remove_aperture_masters([asset_id])

    assert source.exists()
    assert not managed.exists()
    with sqlite3.connect(db) as check:
        check.row_factory = sqlite3.Row
        assert check.execute("SELECT policy FROM asset_storage_policies WHERE asset_id=?", (asset_id,)).fetchone()[0] == "referenced"
        assert check.execute("SELECT COUNT(*) FROM file_instances WHERE asset_id=? AND storage_mode='managed'", (asset_id,)).fetchone()[0] == 0
        assert check.execute("SELECT fi.storage_mode FROM import_plan_items i JOIN file_instances fi ON fi.id=i.file_instance_id WHERE i.asset_id=?", (asset_id,)).fetchone()[0] == "referenced"


def test_scope_matches_source_directory_and_blocks_offline_source(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    c = _catalog(db)
    first, source, _managed = _hybrid_asset(c, tmp_path, "a.jpg")
    second, offline, _managed2 = _hybrid_asset(c, tmp_path, "b.jpg")
    offline.unlink()
    c.close()

    service = AssetStorageService(db, tmp_path / "managed" / "originals")
    assets = service.assets_in_storage_scope(source.parent)
    assert assets == [first, second]
    preview = service.managed_removal_preview(assets)
    assert preview.removable_asset_ids == (first,)
    assert preview.blocked_asset_ids == (second,)

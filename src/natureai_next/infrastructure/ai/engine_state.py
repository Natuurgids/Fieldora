"""NatureAI-owned engine state and Aperture bridge registration.

NatureAI owns its runtime database. Aperture stores only a lightweight bridge
record in the currently opened library so its UI and review provenance can refer
to the active engine without taking ownership of BioCLIP or Tree-of-Life files.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NatureAIEngineState:
    ready: bool
    engine_version: str
    provider: str
    model_identity: str
    model_version: str
    variant_identity: str
    classifier: str
    taxonomy_source: str
    taxa_count: int | None
    device: str
    updated_at_us: int


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS engine_state(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        state_json TEXT NOT NULL CHECK(json_valid(state_json)),
        updated_at_us INTEGER NOT NULL)"""
    )
    return connection


def write_engine_state(path: Path, state: NatureAIEngineState) -> None:
    payload = json.dumps(
        {
            "ready": state.ready,
            "engine_version": state.engine_version,
            "provider": state.provider,
            "model_identity": state.model_identity,
            "model_version": state.model_version,
            "variant_identity": state.variant_identity,
            "classifier": state.classifier,
            "taxonomy_source": state.taxonomy_source,
            "taxa_count": state.taxa_count,
            "device": state.device,
        },
        sort_keys=True,
    )
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO engine_state(singleton,state_json,updated_at_us) VALUES(1,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET state_json=excluded.state_json,updated_at_us=excluded.updated_at_us",
            (payload, state.updated_at_us),
        )


def read_engine_state(path: Path) -> NatureAIEngineState | None:
    if not path.is_file():
        return None
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT state_json,updated_at_us FROM engine_state WHERE singleton=1"
        ).fetchone()
    if row is None:
        return None
    data = json.loads(str(row[0]))
    return NatureAIEngineState(
        ready=bool(data.get("ready")),
        engine_version=str(data.get("engine_version", "")),
        provider=str(data.get("provider", "")),
        model_identity=str(data.get("model_identity", "")),
        model_version=str(data.get("model_version", "")),
        variant_identity=str(data.get("variant_identity", "")),
        classifier=str(data.get("classifier", "")),
        taxonomy_source=str(data.get("taxonomy_source", "")),
        taxa_count=None if data.get("taxa_count") is None else int(data["taxa_count"]),
        device=str(data.get("device", "cpu")),
        updated_at_us=int(row[1]),
    )


def ensure_aperture_bridge(factory, state: NatureAIEngineState) -> None:
    """Create/update non-owning library records for a ready NatureAI engine."""
    if not state.ready:
        return
    now = int(time.time() * 1_000_000)
    connection = factory.connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE model_packages SET active=0 WHERE model_family='bioclip' AND active=1"
        )
        row = connection.execute(
            "SELECT id FROM model_packages WHERE model_identity=? AND semantic_version=?",
            (state.model_identity, state.model_version),
        ).fetchone()
        manifest = json.dumps(
            {
                "component": "natureai",
                "ownership": "external-engine",
                "provider": state.provider,
                "classifier": state.classifier,
                "taxonomy_source": state.taxonomy_source,
                "taxa_count": state.taxa_count,
            },
            sort_keys=True,
        )
        if row is None:
            cursor = connection.execute(
                """INSERT INTO model_packages(public_id,model_identity,semantic_version,model_family,
                artifact_checksum,manifest_json,license_json,install_path_token,installation_state,
                installed_at_us,package_id,signature_key_id,activated_at_us,active)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    str(uuid.uuid4()),
                    state.model_identity,
                    state.model_version,
                    "bioclip",
                    "0" * 64,
                    manifest,
                    json.dumps({"managed_by": "pybioclip"}),
                    "natureai://tree-of-life",
                    "external-ready",
                    now,
                    "natureai-engine",
                    "natureai-runtime",
                    now,
                ),
            )
            package_id = int(cursor.lastrowid)
        else:
            package_id = int(row[0])
            connection.execute(
                "UPDATE model_packages SET manifest_json=?,installation_state='external-ready',activated_at_us=?,active=1 WHERE id=?",
                (manifest, now, package_id),
            )
        connection.execute("UPDATE model_variants SET active=0 WHERE package_id=?", (package_id,))
        variant = connection.execute(
            "SELECT id FROM model_variants WHERE package_id=? AND variant_identity=?",
            (package_id, state.variant_identity),
        ).fetchone()
        requirements = json.dumps(
            {
                "providers": [state.device],
                "external_engine": "natureai",
                "classifier": state.classifier,
            }
        )
        if variant is None:
            connection.execute(
                """INSERT INTO model_variants(public_id,package_id,variant_identity,runtime,precision,
                device_requirements_json,preprocessing_identity,embedding_dimension,active,input_size,artifact_relative_path)
                VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                (
                    str(uuid.uuid4()),
                    package_id,
                    state.variant_identity,
                    "torch",
                    "fp16" if "fp16" in state.variant_identity else "fp32",
                    requirements,
                    "pybioclip-tree-of-life-v1",
                    512,
                    224,
                    "",
                ),
            )
        else:
            connection.execute(
                "UPDATE model_variants SET active=1,device_requirements_json=?,artifact_relative_path='' WHERE id=?",
                (requirements, int(variant[0])),
            )
        # TreeOfLifeClassifier owns its prompts; this bridge profile is descriptive,
        # never an empty Aperture embedding set.
        connection.execute(
            "UPDATE prompt_sets SET active=0 WHERE model_family='bioclip' AND active=1"
        )
        prompt = connection.execute(
            "SELECT id FROM prompt_sets WHERE identity='natureai-tree-of-life-managed' AND semantic_version=?",
            (state.engine_version,),
        ).fetchone()
        prompt_manifest = json.dumps(
            {
                "managed_by": "pybioclip",
                "classifier": state.classifier,
                "taxonomy_source": state.taxonomy_source,
                "taxa_count": state.taxa_count,
            },
            sort_keys=True,
        )
        if prompt is None:
            connection.execute(
                """INSERT INTO prompt_sets(public_id,identity,semantic_version,model_family,checksum,
                manifest_json,active,installed_at_us) VALUES(?,?,?,?,?,?,1,?)""",
                (
                    str(uuid.uuid4()),
                    "natureai-tree-of-life-managed",
                    state.engine_version,
                    "bioclip",
                    "0" * 64,
                    prompt_manifest,
                    now,
                ),
            )
        else:
            connection.execute(
                "UPDATE prompt_sets SET active=1,manifest_json=? WHERE id=?",
                (prompt_manifest, int(prompt[0])),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

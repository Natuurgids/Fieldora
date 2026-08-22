"""SQLite suggestion-generation prerequisite queries."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from natureai_next.domain.ai import ActiveAIContext
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


def _cuda_runtime_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except (ImportError, RuntimeError):
        return False


def _select_best_active_variant(rows):
    """Prefer runnable CUDA, then CPU, within the newest active package."""
    if not rows:
        return None
    newest_activation = rows[0][11]
    candidates = [row for row in rows if row[11] == newest_activation]
    cuda_available = _cuda_runtime_available()

    def score(row):
        requirements = json.loads(str(row[10] or "{}"))
        providers = {str(value).casefold() for value in requirements.get("providers", ())}
        supports_cuda = any("cuda" in value for value in providers)
        supports_cpu = any("cpu" in value for value in providers) or not providers
        if cuda_available and supports_cuda:
            return (0, -int(row[0]))
        if supports_cpu:
            return (1, -int(row[0]))
        return (2, -int(row[0]))

    return min(candidates, key=score)


class SqliteSuggestionGenerationSource:
    def __init__(self, factory: SqliteConnectionFactory, model_manager=None) -> None:
        self._factory = factory
        self._model_manager = model_manager

    def active_context(self) -> ActiveAIContext:
        if self._model_manager is not None:
            sync_active_photo_taxonomy_model(self._factory, self._model_manager)
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT v.id,p.model_identity,p.semantic_version,v.variant_identity,
                          v.precision,v.preprocessing_identity,v.input_size,
                          p.install_path_token,v.artifact_relative_path,ps.public_id,
                          v.device_requirements_json,
                          COALESCE(p.activated_at_us,p.installed_at_us) AS package_activated_at_us
                   FROM model_packages p
                   JOIN model_variants v ON v.package_id=p.id
                   LEFT JOIN prompt_sets ps ON ps.model_family=p.model_family AND ps.active=1
                   WHERE p.active=1 AND v.active=1
                   ORDER BY package_activated_at_us DESC, v.id DESC"""
            ).fetchall()
            row = _select_best_active_variant(rows)
            if row is None:
                raise RuntimeError(
                    "No active NatureAI BioCLIP engine or local model package is installed."
                )
            requirements = json.loads(str(row[10] or "{}"))
            external_tree_of_life = (
                requirements.get("external_engine") == "natureai"
                and requirements.get("classifier") == "TreeOfLifeClassifier"
            )
            catalog_key = str(requirements.get("catalog_model_key") or "")
            external_catalog = requirements.get("external_engine") == "catalog-capability" and bool(catalog_key)
            if row[9] is None and not external_tree_of_life and not external_catalog:
                raise RuntimeError("No active prompt set is installed for the active model.")
            input_size = int(row[6] or 0)
            if input_size <= 0:
                raise RuntimeError("The active model variant has no valid input size.")
            relative = str(row[8] or "").strip()
            if external_tree_of_life:
                artifact = Path("natureai-tree-of-life-managed")
            elif external_catalog:
                artifact = Path(f"catalog-model://{catalog_key}")
            else:
                if not relative:
                    raise RuntimeError("The active model variant has no artifact path.")
                artifact = Path(str(row[7])) / relative
                if not artifact.is_file():
                    raise RuntimeError(f"The active model artifact is missing: {artifact}")
            providers = tuple(str(value).casefold() for value in requirements.get("providers", ()))
            device = "cuda" if any("cuda" in value for value in providers) else "cpu"
            prompt_public_id = "natureai-tree-of-life-managed" if row[9] is None else str(row[9])
            provider = (
                "pybioclip-tree-of-life"
                if external_tree_of_life
                else f"catalog-capability:{catalog_key}"
                if external_catalog
                else "openclip-local-v1"
            )
            return ActiveAIContext(
                int(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                str(row[4]),
                str(row[5]),
                input_size,
                artifact,
                prompt_public_id,
                provider,
                device,
            )
        finally:
            connection.close()

    def asset_paths(self, public_ids: Sequence[str]) -> tuple[tuple[str, Path], ...]:
        ordered = tuple(dict.fromkeys(str(value) for value in public_ids if str(value)))
        if not ordered:
            return ()
        placeholders = ",".join("?" for _ in ordered)
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                f"""SELECT a.public_id,f.normalized_path FROM assets a
                    JOIN file_instances f ON f.id=a.primary_file_instance_id
                    WHERE a.lifecycle_state='active' AND a.public_id IN ({placeholders})""",
                ordered,
            ).fetchall()
        finally:
            connection.close()
        by_id = {str(row[0]): Path(str(row[1])) for row in rows}
        return tuple((public_id, by_id[public_id]) for public_id in ordered if public_id in by_id)


def _active_photo_taxonomy_key(manager) -> str | None:
    matches = []
    for key in manager.active_keys:
        spec = manager.catalog.get(key)
        assets = set(spec.input_contract.get("asset_types", ()))
        output = str(spec.output_contract.get("enrichment_type") or "")
        instance = manager.instantiate(key)
        descriptor = getattr(instance, "descriptor", None)
        if (
            "photo" in assets
            and output == "taxonomy.classification"
            and descriptor is not None
            and callable(getattr(instance, "execute", None))
        ):
            matches.append(key)
    if not matches:
        return None
    return sorted(matches, key=lambda key: (manager.catalog.get(key).built_in, key))[0]


def sync_active_photo_taxonomy_model(factory: SqliteConnectionFactory, manager) -> str | None:
    key = _active_photo_taxonomy_key(manager)
    if key is None:
        return None
    spec = manager.catalog.get(key)
    instance = manager.instantiate(key)
    descriptor = instance.descriptor
    now = __import__("time").time_ns() // 1_000
    connection = factory.connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE model_packages SET active=0 WHERE model_family='bioclip' AND active=1")
        row = connection.execute(
            "SELECT id FROM model_packages WHERE package_id=?", (f"catalog:{key}",)
        ).fetchone()
        manifest = json.dumps({
            "ownership": "catalog-capability",
            "catalog_model_key": key,
            "display_name": spec.display_name,
            "capability_id": descriptor.capability_id,
        }, sort_keys=True)
        install_token = str((manager.runtime_root / key).resolve())
        if row is None:
            cursor = connection.execute(
                """INSERT INTO model_packages(public_id,model_identity,semantic_version,model_family,
                artifact_checksum,manifest_json,license_json,install_path_token,installation_state,
                installed_at_us,package_id,signature_key_id,activated_at_us,active)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (__import__("uuid").uuid4().hex, spec.display_name, spec.version or descriptor.version,
                 "bioclip", "0"*64, manifest, json.dumps({"license": spec.license_name}),
                 install_token, "catalog-ready", now, f"catalog:{key}", "catalog", now),
            )
            package_id = int(cursor.lastrowid)
        else:
            package_id = int(row[0])
            connection.execute(
                "UPDATE model_packages SET model_identity=?,semantic_version=?,manifest_json=?,install_path_token=?,installation_state='catalog-ready',activated_at_us=?,active=1 WHERE id=?",
                (spec.display_name, spec.version or descriptor.version, manifest, install_token, now, package_id),
            )
        connection.execute("UPDATE model_variants SET active=0 WHERE package_id=?", (package_id,))
        variant = connection.execute("SELECT id FROM model_variants WHERE package_id=?", (package_id,)).fetchone()
        requirements = json.dumps({"providers": ["cuda", "cpu"], "external_engine": "catalog-capability", "catalog_model_key": key})
        preprocessing = f"{key}-managed"
        if variant is None:
            connection.execute(
                """INSERT INTO model_variants(public_id,package_id,variant_identity,runtime,precision,
                device_requirements_json,preprocessing_identity,embedding_dimension,active,input_size,artifact_relative_path)
                VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                (__import__("uuid").uuid4().hex, package_id, descriptor.capability_id, "torch", "fp16",
                 requirements, preprocessing, None, 224, ""),
            )
        else:
            connection.execute(
                "UPDATE model_variants SET variant_identity=?,precision='fp16',device_requirements_json=?,preprocessing_identity=?,input_size=224,artifact_relative_path='',active=1 WHERE id=?",
                (descriptor.capability_id, requirements, preprocessing, int(variant[0])),
            )
        connection.execute("COMMIT")
        return key
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()

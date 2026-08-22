"""SQLite adapters for taxonomy text embeddings and AI review state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence

from natureai_next.domain.ai import (
    AIReviewSessionState,
    EmbeddingVector,
    NearDuplicateGroup,
    NearDuplicateMember,
    TaxonomyEmbeddingRefreshPlan,
    TaxonomyTextEmbedding,
    TaxonomyTextLabel,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqliteTaxonomyEmbeddingRefreshPlanSource:
    """Resolves active model variants and their active compatible prompt sets."""

    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def active_plans(self) -> tuple[TaxonomyEmbeddingRefreshPlan, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT v.id,v.preprocessing_identity,p.model_family,ps.public_id
                   FROM model_variants v
                   JOIN model_packages p ON p.id=v.package_id
                   LEFT JOIN prompt_sets ps
                     ON ps.model_family=p.model_family AND ps.active=1
                   WHERE p.active=1 AND v.active=1
                   ORDER BY p.model_identity,p.semantic_version,v.variant_identity,ps.identity"""
            ).fetchall()
            return tuple(
                TaxonomyEmbeddingRefreshPlan(
                    model_variant_id=int(row[0]),
                    preprocessing_identity=str(row[1]),
                    model_family=str(row[2]),
                    prompt_set_public_id=None if row[3] is None else str(row[3]),
                )
                for row in rows
            )
        finally:
            connection.close()


class SqliteTaxonomyEmbeddingStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def replace_generation(
        self,
        *,
        model_variant_id: int,
        preprocessing_identity: str,
        prompt_set_public_id: str | None,
        embeddings: Sequence[TaxonomyTextEmbedding],
        now_us: int,
        generation_identity: str = "legacy",
        taxonomy_source_public_ids: Sequence[str] = (),
    ) -> int:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            prompt_set_id = None
            if prompt_set_public_id is not None:
                row = connection.execute(
                    "SELECT id FROM prompt_sets WHERE public_id=?", (prompt_set_public_id,)
                ).fetchone()
                if row is None:
                    raise KeyError(f"unknown prompt set: {prompt_set_public_id}")
                prompt_set_id = int(row[0])
            connection.execute(
                "UPDATE taxonomy_text_embeddings SET valid=0 WHERE model_variant_id=? AND preprocessing_identity=? AND COALESCE(prompt_set_id,-1)=COALESCE(?,-1)",
                (model_variant_id, preprocessing_identity, prompt_set_id),
            )
            inserted = 0
            for item in embeddings:
                taxon_id = None
                if item.taxon_public_id is not None:
                    row = connection.execute(
                        "SELECT id FROM taxa WHERE public_id=?", (item.taxon_public_id,)
                    ).fetchone()
                    if row is None:
                        raise KeyError(f"unknown taxon: {item.taxon_public_id}")
                    taxon_id = int(row[0])
                if (taxon_id is None) == (item.broad_group is None):
                    raise ValueError("exactly one of taxon_public_id and broad_group is required")
                vector = item.vector.normalized()
                source_hash = hashlib.sha256(item.source_text.encode("utf-8")).hexdigest()
                connection.execute(
                    """INSERT INTO taxonomy_text_embeddings(
                        public_id,taxon_id,broad_group,label_kind,language_tag,region_code,
                        source_text,source_text_sha256,model_variant_id,preprocessing_identity,
                        prompt_set_id,dimension,vector_blob,vector_sha256,valid,created_at_us,
                        generation_identity,taxonomy_source_ids_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                    (
                        item.public_id,
                        taxon_id,
                        item.broad_group,
                        item.label_kind,
                        item.language_tag,
                        item.region_code,
                        item.source_text,
                        source_hash,
                        model_variant_id,
                        preprocessing_identity,
                        prompt_set_id,
                        vector.dimension,
                        vector.to_blob(),
                        vector.checksum,
                        now_us,
                        generation_identity,
                        json.dumps(tuple(taxonomy_source_public_ids), separators=(",", ":")),
                    ),
                )
                inserted += 1
            connection.execute("COMMIT")
            return inserted
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def candidates(
        self,
        *,
        model_variant_id: int,
        preprocessing_identity: str,
        broad_group: str | None = None,
        region_code: str | None = None,
    ) -> tuple[tuple[str, str, EmbeddingVector], ...]:
        clauses = ["e.valid=1", "e.model_variant_id=?", "e.preprocessing_identity=?"]
        params: list[object] = [model_variant_id, preprocessing_identity]
        if broad_group is not None:
            clauses.append("(e.broad_group=? OR t.rank IS NOT NULL)")
            params.append(broad_group)
        if region_code is not None:
            clauses.append("(e.region_code IS NULL OR e.region_code=?)")
            params.append(region_code)
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT COALESCE(t.public_id,'group:'||e.broad_group),e.source_text,
                          e.dimension,e.vector_blob,e.vector_sha256
                   FROM taxonomy_text_embeddings e
                   LEFT JOIN taxa t ON t.id=e.taxon_id
                   WHERE """
                + " AND ".join(clauses)
                + " ORDER BY e.id",
                params,
            ).fetchall()
        finally:
            connection.close()
        result: list[tuple[str, str, EmbeddingVector]] = []
        for row in rows:
            vector = EmbeddingVector.from_blob(bytes(row[3]), int(row[2]))
            if vector.checksum != str(row[4]):
                raise ValueError("taxonomy text embedding checksum mismatch")
            result.append((str(row[0]), str(row[1]), vector))
        return tuple(result)

    def invalidate(
        self,
        *,
        model_variant_id: int | None = None,
        preprocessing_identity: str | None = None,
        prompt_set_public_id: str | None = None,
    ) -> int:
        clauses = ["valid=1"]
        params: list[object] = []
        if model_variant_id is not None:
            clauses.append("model_variant_id=?")
            params.append(model_variant_id)
        if preprocessing_identity is not None:
            clauses.append("preprocessing_identity=?")
            params.append(preprocessing_identity)
        if prompt_set_public_id is not None:
            clauses.append("prompt_set_id=(SELECT id FROM prompt_sets WHERE public_id=?)")
            params.append(prompt_set_public_id)
        connection = self._factory.connect()
        try:
            cursor = connection.execute(
                "UPDATE taxonomy_text_embeddings SET valid=0 WHERE " + " AND ".join(clauses),
                params,
            )
            connection.commit()
            return int(cursor.rowcount)
        finally:
            connection.close()


class SqliteNearDuplicateStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def replace_groups(
        self,
        *,
        model_variant_id: int,
        preprocessing_identity: str,
        threshold: float,
        groups: Sequence[Sequence[tuple[str, float]]],
        group_id_factory: Callable[[], str],
        now_us: int,
    ) -> tuple[str, ...]:
        if not -1.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between -1 and 1")
        connection = self._factory.connect()
        created: list[str] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT id FROM near_duplicate_groups WHERE model_variant_id=? AND preprocessing_identity=?",
                (model_variant_id, preprocessing_identity),
            ).fetchall()
            for row in old:
                connection.execute("DELETE FROM near_duplicate_groups WHERE id=?", (int(row[0]),))
            for group in groups:
                members = tuple(group)
                if len(members) < 2:
                    continue
                public_id = str(group_id_factory())
                cursor = connection.execute(
                    "INSERT INTO near_duplicate_groups(public_id,model_variant_id,preprocessing_identity,threshold,created_at_us) VALUES(?,?,?,?,?)",
                    (public_id, model_variant_id, preprocessing_identity, threshold, now_us),
                )
                group_id = int(cursor.lastrowid)
                for position, (asset_public_id, similarity) in enumerate(members):
                    row = connection.execute(
                        "SELECT id FROM assets WHERE public_id=?", (asset_public_id,)
                    ).fetchone()
                    if row is None:
                        raise KeyError(f"unknown asset: {asset_public_id}")
                    connection.execute(
                        "INSERT INTO near_duplicate_group_members(group_id,asset_id,similarity,position) VALUES(?,?,?,?)",
                        (group_id, int(row[0]), float(similarity), position),
                    )
                created.append(public_id)
            connection.execute("COMMIT")
            return tuple(created)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def page_groups(
        self, *, cursor: int | None = None, page_size: int = 50
    ) -> tuple[NearDuplicateGroup, ...]:
        page_size = max(1, min(page_size, 200))
        params: list[object] = []
        where = ""
        if cursor is not None:
            where = "WHERE g.id>?"
            params.append(cursor)
        params.append(page_size)
        connection = self._factory.connect(read_only=True)
        try:
            groups = connection.execute(
                f"SELECT g.id,g.public_id,g.threshold FROM near_duplicate_groups g {where} ORDER BY g.id LIMIT ?",
                params,
            ).fetchall()
            result: list[NearDuplicateGroup] = []
            for group in groups:
                members = connection.execute(
                    """SELECT a.public_id,m.similarity,m.position
                       FROM near_duplicate_group_members m JOIN assets a ON a.id=m.asset_id
                       WHERE m.group_id=? ORDER BY m.position""",
                    (int(group[0]),),
                ).fetchall()
                result.append(
                    NearDuplicateGroup(
                        str(group[1]),
                        float(group[2]),
                        tuple(
                            NearDuplicateMember(str(row[0]), float(row[1]), int(row[2]))
                            for row in members
                        ),
                    )
                )
            return tuple(result)
        finally:
            connection.close()


class SqliteReviewSessionStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def load(self) -> AIReviewSessionState | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT state_json,modified_at_us FROM ai_review_sessions ORDER BY id LIMIT 1"
            ).fetchone()
            return None if row is None else AIReviewSessionState(str(row[0]), int(row[1]))
        finally:
            connection.close()

    def save(self, state_json: str, *, public_id: str, now_us: int) -> None:
        parsed = json.loads(state_json)
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM ai_review_sessions")
            connection.execute(
                "INSERT INTO ai_review_sessions(public_id,state_json,modified_at_us) VALUES(?,?,?)",
                (public_id, canonical, now_us),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()


class SqliteTaxonomyLabelSource:
    """Reads deterministic embedding labels from active taxonomy releases."""

    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def active_release_ids(self) -> tuple[str, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            return tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT public_id FROM taxonomy_sources WHERE active=1 ORDER BY name,source_version,public_id"
                )
            )
        finally:
            connection.close()

    def active_labels(
        self,
        *,
        language_tags: Sequence[str] = (),
        region_codes: Sequence[str] = (),
        include_synonyms: bool = True,
    ) -> tuple[TaxonomyTextLabel, ...]:
        languages = tuple(dict.fromkeys(tag.strip() for tag in language_tags if tag.strip()))
        regions = tuple(
            dict.fromkeys(code.strip().upper() for code in region_codes if code.strip())
        )
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(
                """SELECT t.public_id,t.scientific_name,t.major_group,t.kingdom
                   FROM taxa t JOIN taxonomy_sources s ON s.id=t.source_id
                   WHERE s.active=1 AND t.status='accepted'
                   ORDER BY lower(t.scientific_name),t.public_id"""
            ).fetchall()
            labels: list[TaxonomyTextLabel] = [
                TaxonomyTextLabel(str(row[0]), None, "scientific", str(row[1])) for row in rows
            ]
            clauses = ["s.active=1"]
            params: list[object] = []
            if languages:
                clauses.append("n.language_tag IN (" + ",".join("?" for _ in languages) + ")")
                params.extend(languages)
            if regions:
                clauses.append(
                    "(n.region_code IS NULL OR n.region_code IN ("
                    + ",".join("?" for _ in regions)
                    + "))"
                )
                params.extend(regions)
            name_rows = connection.execute(
                """SELECT t.public_id,n.name,n.language_tag,n.region_code
                   FROM taxon_names n JOIN taxa t ON t.id=n.taxon_id
                   JOIN taxonomy_sources s ON s.id=t.source_id
                   WHERE """
                + " AND ".join(clauses)
                + " ORDER BY t.public_id,n.preferred DESC,lower(n.name),n.id",
                params,
            ).fetchall()
            labels.extend(
                TaxonomyTextLabel(
                    str(row[0]),
                    None,
                    "vernacular",
                    str(row[1]),
                    None if row[2] is None else str(row[2]),
                    None if row[3] is None else str(row[3]),
                )
                for row in name_rows
            )
            if include_synonyms:
                synonym_rows = connection.execute(
                    """SELECT accepted.public_id,synonym.scientific_name
                       FROM taxa synonym
                       JOIN taxonomy_sources source ON source.id=synonym.source_id
                       JOIN taxa accepted ON accepted.id=synonym.accepted_taxon_id
                       WHERE source.active=1 AND synonym.status='synonym'
                       ORDER BY accepted.public_id,lower(synonym.scientific_name),synonym.id"""
                ).fetchall()
                labels.extend(
                    TaxonomyTextLabel(str(row[0]), None, "synonym", str(row[1]))
                    for row in synonym_rows
                )
            groups = sorted(
                {
                    str(value).strip()
                    for row in rows
                    for value in (row[2], row[3])
                    if value is not None and str(value).strip()
                },
                key=str.casefold,
            )
            labels.extend(
                TaxonomyTextLabel(None, group.casefold(), "broad_group", group) for group in groups
            )
            return tuple(labels)
        finally:
            connection.close()

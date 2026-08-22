"""SQLite persistence for prompt sets, immutable suggestions, and review actions."""

from __future__ import annotations

import json
import json
import sqlite3
from pathlib import Path

from collections.abc import Callable, Sequence

from natureai_next.application.ai_review import AIReviewOverview
from natureai_next.domain.ai import (
    ConfidenceBand,
    PromptSetManifest,
    PromptSetRecord,
    ReviewBatchResult,
    SuggestionDetail,
    SuggestionPage,
    SuggestionProjection,
    SuggestionReviewState,
)
from natureai_next.infrastructure.ai.prompts import canonical_prompt_manifest
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory


class SqlitePromptSetStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def install(
        self,
        manifest: PromptSetManifest,
        *,
        checksum: str,
        public_id: str,
        now_us: int,
        activate: bool,
    ) -> PromptSetRecord:
        manifest_json = canonical_prompt_manifest(manifest).decode("utf-8")
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM prompt_sets WHERE identity=? AND semantic_version=?",
                (manifest.identity, manifest.semantic_version),
            ).fetchone()
            if existing is not None:
                if str(existing["checksum"]) != checksum:
                    raise ValueError("prompt-set version already exists with different content")
                if activate and not bool(existing["active"]):
                    self._activate_row(connection, int(existing["id"]), manifest.identity)
                connection.execute("COMMIT")
                return self._get_by_id(int(existing["id"]))
            if activate:
                connection.execute(
                    "UPDATE prompt_sets SET active=0 WHERE identity=? AND active=1",
                    (manifest.identity,),
                )
            cursor = connection.execute(
                """INSERT INTO prompt_sets(
                    public_id,identity,semantic_version,model_family,checksum,
                    manifest_json,active,installed_at_us
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    public_id,
                    manifest.identity,
                    manifest.semantic_version,
                    manifest.model_family,
                    checksum,
                    manifest_json,
                    int(activate),
                    now_us,
                ),
            )
            row_id = int(cursor.lastrowid)
            connection.execute("COMMIT")
            return self._get_by_id(row_id)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def activate(self, public_id: str, *, now_us: int) -> PromptSetRecord:
        del now_us  # activation is represented by the active flag; installation time is immutable.
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id,identity FROM prompt_sets WHERE public_id=?",
                (public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown prompt set: {public_id}")
            self._activate_row(connection, int(row["id"]), str(row["identity"]))
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        return self._get_by_public_id(public_id)

    def list(self, identity: str | None = None) -> tuple[PromptSetRecord, ...]:
        connection = self._factory.connect(read_only=True)
        try:
            if identity is None:
                rows = connection.execute(
                    "SELECT * FROM prompt_sets ORDER BY identity,semantic_version,id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM prompt_sets WHERE identity=? ORDER BY semantic_version,id",
                    (identity,),
                ).fetchall()
            return tuple(_prompt_set_record(row) for row in rows)
        finally:
            connection.close()

    def active_for_model_family(self, model_family: str) -> PromptSetRecord | None:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                """SELECT * FROM prompt_sets
                   WHERE model_family=? AND active=1
                   ORDER BY installed_at_us DESC,id DESC LIMIT 1""",
                (model_family,),
            ).fetchone()
            return None if row is None else _prompt_set_record(row)
        finally:
            connection.close()

    def _get_by_id(self, row_id: int) -> PromptSetRecord:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute("SELECT * FROM prompt_sets WHERE id=?", (row_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown prompt-set row: {row_id}")
            return _prompt_set_record(row)
        finally:
            connection.close()

    def _get_by_public_id(self, public_id: str) -> PromptSetRecord:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                "SELECT * FROM prompt_sets WHERE public_id=?", (public_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown prompt set: {public_id}")
            return _prompt_set_record(row)
        finally:
            connection.close()

    @staticmethod
    def _activate_row(connection: sqlite3.Connection, row_id: int, identity: str) -> None:
        connection.execute(
            "UPDATE prompt_sets SET active=0 WHERE identity=? AND active=1", (identity,)
        )
        connection.execute("UPDATE prompt_sets SET active=1 WHERE id=?", (row_id,))


class SqliteSuggestionStore:
    def __init__(self, factory: SqliteConnectionFactory) -> None:
        self._factory = factory

    def overview(self) -> AIReviewOverview:
        connection = self._factory.connect(read_only=True)
        try:
            model = connection.execute(
                """SELECT p.model_identity,p.semantic_version,v.variant_identity
                   FROM model_packages p
                   JOIN model_variants v ON v.package_id=p.id
                   WHERE p.active=1 AND v.active=1
                   ORDER BY COALESCE(p.activated_at_us,p.installed_at_us) DESC,v.id DESC
                   LIMIT 1"""
            ).fetchone()
            prompt = connection.execute(
                "SELECT identity,semantic_version FROM prompt_sets WHERE active=1 ORDER BY installed_at_us DESC,id DESC LIMIT 1"
            ).fetchone()
            counts = connection.execute(
                "SELECT review_state,COUNT(*) FROM ai_suggestions GROUP BY review_state ORDER BY review_state"
            ).fetchall()
            run = connection.execute(
                """SELECT outcome,COALESCE(completed_item_count,0),COALESCE(failed_item_count,0)
                   FROM inference_runs ORDER BY started_at_us DESC,id DESC LIMIT 1"""
            ).fetchone()
            return AIReviewOverview(
                active_model_identity=None if model is None else str(model[0]),
                active_model_version=None if model is None else str(model[1]),
                active_variant_identity=None if model is None else str(model[2]),
                active_prompt_set=None if prompt is None else f"{prompt[0]} {prompt[1]}",
                suggestion_counts=tuple((str(row[0]), int(row[1])) for row in counts),
                latest_run_outcome=None if run is None else str(run[0]),
                latest_run_completed=0 if run is None else int(run[1]),
                latest_run_failed=0 if run is None else int(run[2]),
            )
        finally:
            connection.close()

    def create_suggestions(self, **kwargs: object) -> tuple[str, ...]:
        asset_public_id = str(kwargs["asset_public_id"])
        inference_run_id = int(kwargs["inference_run_id"])
        suggestions = tuple(kwargs["suggestions"])
        prompt_set_id = kwargs.get("prompt_set_id")
        roi_public_id = kwargs.get("region_of_interest_public_id")
        analysis_public_id = kwargs.get("analysis_public_id")
        provenance = dict(kwargs.get("provenance", {}))
        geographic_context = dict(kwargs.get("geographic_context", {}))
        now_us = int(kwargs["now_us"])
        id_factory = kwargs["id_factory"]
        if not callable(id_factory):
            raise TypeError("id_factory must be callable")

        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            asset = connection.execute(
                "SELECT id FROM assets WHERE public_id=?", (asset_public_id,)
            ).fetchone()
            if asset is None:
                raise KeyError(f"unknown asset: {asset_public_id}")
            roi_id = self._resolve_roi(connection, roi_public_id, int(asset[0]))
            resolved_prompt_set_id = self._resolve_prompt_set(connection, prompt_set_id)
            analysis_id = None
            if analysis_public_id is not None:
                analysis = connection.execute(
                    "SELECT id,asset_id FROM asset_analyses WHERE public_id=?",
                    (str(analysis_public_id),),
                ).fetchone()
                if analysis is None or int(analysis[1]) != int(asset[0]):
                    raise KeyError("analysis does not belong to suggestion asset")
                analysis_id = int(analysis[0])
            created: list[str] = []
            for item in suggestions:
                public_id = str(id_factory())
                taxon_id = self._resolve_taxon(connection, item.taxon_public_id)
                connection.execute(
                    """INSERT INTO ai_suggestions(
                        public_id,asset_id,region_of_interest_id,inference_run_id,prompt_set_id,
                        suggestion_type,candidate_taxon_id,candidate_label,raw_score,rank,
                        calibrated_score,calibration_identity,score_type,confidence_band,
                        taxonomic_level,geographic_context_json,provenance_json,review_state,
                        created_at_us,analysis_id
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
                    (
                        public_id,
                        int(asset[0]),
                        roi_id,
                        inference_run_id,
                        resolved_prompt_set_id,
                        str(kwargs.get("suggestion_type", "taxon")),
                        taxon_id,
                        item.label,
                        item.raw_score,
                        item.rank,
                        item.calibrated_score,
                        kwargs.get("calibration_identity"),
                        str(kwargs.get("score_type", "cosine")),
                        item.confidence_band.value,
                        item.taxonomic_level,
                        json.dumps(geographic_context, sort_keys=True, separators=(",", ":")),
                        json.dumps(provenance, sort_keys=True, separators=(",", ":")),
                        now_us,
                        analysis_id,
                    ),
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

    def page(self, **kwargs: object) -> SuggestionPage:
        state = str(kwargs.get("state", "pending"))
        confidence = tuple(str(value) for value in kwargs.get("confidence", ()))
        taxonomic_level = kwargs.get("taxonomic_level")
        assigned_to = kwargs.get("assigned_to")
        cursor = kwargs.get("cursor")
        page_size = max(1, min(int(kwargs.get("page_size", 100)), 500))
        clauses = ["s.review_state=?"]
        params: list[object] = [state]
        if confidence:
            clauses.append("s.confidence_band IN (" + ",".join("?" * len(confidence)) + ")")
            params.extend(confidence)
        if taxonomic_level is not None:
            clauses.append("s.taxonomic_level=?")
            params.append(str(taxonomic_level))
        if assigned_to == "":
            clauses.append("ra.suggestion_id IS NULL")
        elif assigned_to is not None:
            clauses.append("ra.assigned_to=?")
            params.append(str(assigned_to))
        if cursor is not None:
            clauses.append("s.id>?")
            params.append(int(cursor))
        params.append(page_size + 1)
        sql = (
            """SELECT s.id,s.public_id,a.public_id,t.public_id,s.candidate_label,
                      s.raw_score,s.calibrated_score,s.rank,s.confidence_band,
                      s.taxonomic_level,s.review_state,s.provenance_json,roi.public_id,
                      ra.assigned_to
               FROM ai_suggestions s
               JOIN assets a ON a.id=s.asset_id
                LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
               LEFT JOIN taxa t ON t.id=s.candidate_taxon_id
               LEFT JOIN regions_of_interest roi ON roi.id=s.region_of_interest_id
               LEFT JOIN ai_review_assignments ra ON ra.suggestion_id=s.id
               WHERE """
            + " AND ".join(clauses)
            + " ORDER BY s.id LIMIT ?"
        )
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(sql, params).fetchall()
        finally:
            connection.close()
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        items = tuple(_suggestion_projection(row) for row in rows)
        return SuggestionPage(items, int(rows[-1][0]) if has_more and rows else None)

    def page_for_asset(self, asset_public_id: str, **kwargs: object) -> SuggestionPage:
        state = str(kwargs.get("state", "pending"))
        confidence = tuple(str(value) for value in kwargs.get("confidence", ()))
        taxonomic_level = kwargs.get("taxonomic_level")
        assigned_to = kwargs.get("assigned_to")
        cursor = kwargs.get("cursor")
        page_size = max(1, min(int(kwargs.get("page_size", 100)), 500))
        clauses = ["a.public_id=?", "s.review_state=?"]
        params: list[object] = [asset_public_id, state]
        if confidence:
            clauses.append("s.confidence_band IN (" + ",".join("?" * len(confidence)) + ")")
            params.extend(confidence)
        if taxonomic_level is not None:
            clauses.append("s.taxonomic_level=?")
            params.append(str(taxonomic_level))
        if assigned_to == "":
            clauses.append("ra.suggestion_id IS NULL")
        elif assigned_to is not None:
            clauses.append("ra.assigned_to=?")
            params.append(str(assigned_to))
        if cursor is not None:
            clauses.append("s.id>?")
            params.append(int(cursor))
        params.append(page_size + 1)
        sql = (
            """SELECT s.id,s.public_id,a.public_id,t.public_id,s.candidate_label,
                      s.raw_score,s.calibrated_score,s.rank,s.confidence_band,
                      s.taxonomic_level,s.review_state,s.provenance_json,roi.public_id,
                      ra.assigned_to
               FROM ai_suggestions s
               JOIN assets a ON a.id=s.asset_id
               LEFT JOIN taxa t ON t.id=s.candidate_taxon_id
               LEFT JOIN regions_of_interest roi ON roi.id=s.region_of_interest_id
               LEFT JOIN ai_review_assignments ra ON ra.suggestion_id=s.id
               WHERE """
            + " AND ".join(clauses)
            + " ORDER BY s.rank,s.id LIMIT ?"
        )
        connection = self._factory.connect(read_only=True)
        try:
            rows = connection.execute(sql, params).fetchall()
        finally:
            connection.close()
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        items = tuple(_suggestion_projection(row) for row in rows)
        return SuggestionPage(items, int(rows[-1][0]) if has_more and rows else None)

    def detail(
        self, suggestion_public_id: str, *, region_code: str | None = None
    ) -> SuggestionDetail:
        connection = self._factory.connect(read_only=True)
        try:
            row = connection.execute(
                """SELECT
                    s.id,s.public_id,a.public_id,t.public_id,s.candidate_label,s.raw_score,
                    s.calibrated_score,s.rank,s.confidence_band,s.taxonomic_level,
                    s.review_state,s.provenance_json,roi.public_id,
                    a.title,a.caption,t.scientific_name,t.rank,
                    tr.occurrence_status,s.geographic_context_json,s.score_type,
                    s.calibration_identity,ps.identity,ps.semantic_version,
                    ir.public_id,mv.public_id,mv.preprocessing_identity,
                    ir.execution_provider,ir.precision,s.created_at_us,
                    f.normalized_path,
                    (SELECT d.relative_path FROM derivative_cache_entries d WHERE d.source_file_instance_id=f.id AND d.derivative_kind='thumbnail' AND d.state='valid' ORDER BY d.created_at_us DESC LIMIT 1),
                    a.capture_time_utc_us,a.capture_local_text
                FROM ai_suggestions s
                JOIN assets a ON a.id=s.asset_id
                LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id
                JOIN inference_runs ir ON ir.id=s.inference_run_id
                JOIN model_variants mv ON mv.id=ir.model_variant_id
                LEFT JOIN taxa t ON t.id=s.candidate_taxon_id
                LEFT JOIN regions_of_interest roi ON roi.id=s.region_of_interest_id
                LEFT JOIN prompt_sets ps ON ps.id=s.prompt_set_id
                LEFT JOIN taxon_regions tr ON tr.taxon_id=t.id AND tr.region_code=?
                WHERE s.public_id=?
                ORDER BY tr.source LIMIT 1""",
                (region_code, suggestion_public_id),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown suggestion: {suggestion_public_id}")
            provenance = json.loads(str(row[11]) or "{}")
            inference_relative = str(provenance.get("inference_image_relative_path") or "").strip()
            inference_path = None
            if inference_relative:
                candidate = Path(inference_relative)
                inference_path = str(
                    candidate if candidate.is_absolute() else self._factory.database_path.parent / candidate
                )
            return SuggestionDetail(
                suggestion=_suggestion_projection(row),
                asset_title=None if row[13] is None else str(row[13]),
                asset_caption=None if row[14] is None else str(row[14]),
                taxon_scientific_name=None if row[15] is None else str(row[15]),
                taxon_rank=None if row[16] is None else str(row[16]),
                regional_occurrence_status=None if row[17] is None else str(row[17]),
                geographic_context_json=str(row[18]),
                score_type=str(row[19]),
                calibration_identity=None if row[20] is None else str(row[20]),
                prompt_set_identity=None if row[21] is None else str(row[21]),
                prompt_set_version=None if row[22] is None else str(row[22]),
                inference_run_public_id=str(row[23]),
                model_variant_public_id=str(row[24]),
                preprocessing_identity=str(row[25]),
                execution_provider=str(row[26]),
                precision=None if row[27] is None else str(row[27]),
                created_at_us=int(row[28]),
                asset_primary_path=None if row[29] is None else str(row[29]),
                asset_thumbnail_path=None if row[30] is None else str(row[30]),
                asset_capture_time_utc_us=None if row[31] is None else int(row[31]),
                asset_capture_local_text=None if row[32] is None else str(row[32]),
                inference_image_path=inference_path,
                inference_image_width=(
                    None if provenance.get("inference_image_width") is None
                    else int(provenance["inference_image_width"])
                ),
                inference_image_height=(
                    None if provenance.get("inference_image_height") is None
                    else int(provenance["inference_image_height"])
                ),
            )
        finally:
            connection.close()

    def review(self, **kwargs: object) -> None:
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._review_in_transaction(
                connection,
                suggestion_public_id=str(kwargs["suggestion_public_id"]),
                action=str(kwargs["action"]),
                action_public_id=str(kwargs["action_public_id"]),
                now_us=int(kwargs["now_us"]),
                reason=None if kwargs.get("reason") is None else str(kwargs["reason"]),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def assign_review(self, **kwargs: object) -> None:
        public_id = str(kwargs["suggestion_public_id"])
        target_value = kwargs.get("assigned_to")
        target = "" if target_value is None else str(target_value).strip()
        actor = str(kwargs["assigned_by"]).strip()
        now_us = int(kwargs["now_us"])
        note = "" if kwargs.get("note") is None else str(kwargs["note"]).strip()
        if not actor:
            raise ValueError("assigned_by must not be blank")
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id,review_state FROM ai_suggestions WHERE public_id=?",
                (public_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown suggestion: {public_id}")
            if str(row["review_state"]) not in {"pending", "deferred"}:
                raise ValueError("only pending or deferred suggestions can be assigned")
            suggestion_id = int(row["id"])
            previous = connection.execute(
                "SELECT assigned_to FROM ai_review_assignments WHERE suggestion_id=?",
                (suggestion_id,),
            ).fetchone()
            if target:
                connection.execute(
                    """INSERT INTO ai_review_assignments(
                        suggestion_id,assigned_to,assigned_by,assigned_at_us,note
                    ) VALUES(?,?,?,?,?)
                    ON CONFLICT(suggestion_id) DO UPDATE SET
                        assigned_to=excluded.assigned_to,
                        assigned_by=excluded.assigned_by,
                        assigned_at_us=excluded.assigned_at_us,
                        note=excluded.note""",
                    (suggestion_id, target, actor, now_us, note),
                )
                action = "reassigned" if previous is not None else "assigned"
            else:
                connection.execute(
                    "DELETE FROM ai_review_assignments WHERE suggestion_id=?",
                    (suggestion_id,),
                )
                action = "unassigned"
            connection.execute(
                """INSERT INTO ai_review_assignment_events(
                    suggestion_id,assigned_to,assigned_by,action,note,created_at_us
                ) VALUES(?,?,?,?,?,?)""",
                (suggestion_id, target or None, actor, action, note, now_us),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def batch_review(
        self,
        suggestion_public_ids: Sequence[str],
        *,
        action: str,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult:
        if action not in {"accept", "reject", "defer"}:
            raise ValueError("unsupported batch action")
        public_ids = tuple(dict.fromkeys(suggestion_public_ids))
        connection = self._factory.connect()
        reviewed: list[str] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            for suggestion_public_id in public_ids:
                self._review_in_transaction(
                    connection,
                    suggestion_public_id=suggestion_public_id,
                    action=action,
                    action_public_id=str(action_id_factory()),
                    now_us=now_us,
                    reason=reason,
                )
                reviewed.append(suggestion_public_id)
            connection.execute("COMMIT")
            return ReviewBatchResult(tuple(reviewed), ())
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def reject_other_suggestions(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
        reason: str | None = None,
    ) -> ReviewBatchResult:
        connection = self._factory.connect()
        reviewed: list[str] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            selected = connection.execute(
                "SELECT id,asset_id FROM ai_suggestions WHERE public_id=?",
                (suggestion_public_id,),
            ).fetchone()
            if selected is None:
                raise KeyError(f"unknown suggestion: {suggestion_public_id}")
            rows = connection.execute(
                """SELECT public_id FROM ai_suggestions
                   WHERE asset_id=? AND id<>? AND review_state='pending'
                   ORDER BY rank,id""",
                (int(selected["asset_id"]), int(selected["id"])),
            ).fetchall()
            for row in rows:
                public_id = str(row[0])
                self._review_in_transaction(
                    connection,
                    suggestion_public_id=public_id,
                    action="reject",
                    action_public_id=str(action_id_factory()),
                    now_us=now_us,
                    reason=reason or "Alternative rejected after resolving photograph taxonomy.",
                )
                reviewed.append(public_id)
            connection.execute("COMMIT")
            return ReviewBatchResult(tuple(reviewed), ())
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def accept_and_reject_others(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
    ) -> ReviewBatchResult:
        connection = self._factory.connect()
        reviewed: list[str] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            selected = connection.execute(
                "SELECT id,asset_id FROM ai_suggestions WHERE public_id=?",
                (suggestion_public_id,),
            ).fetchone()
            if selected is None:
                raise KeyError(f"unknown suggestion: {suggestion_public_id}")
            self._review_in_transaction(
                connection,
                suggestion_public_id=suggestion_public_id,
                action="accept",
                action_public_id=str(action_id_factory()),
                now_us=now_us,
                reason=None,
            )
            reviewed.append(suggestion_public_id)
            rows = connection.execute(
                """SELECT public_id FROM ai_suggestions
                   WHERE asset_id=? AND id<>? AND review_state='pending'
                   ORDER BY rank,id""",
                (int(selected["asset_id"]), int(selected["id"])),
            ).fetchall()
            for row in rows:
                public_id = str(row[0])
                self._review_in_transaction(
                    connection,
                    suggestion_public_id=public_id,
                    action="reject",
                    action_public_id=str(action_id_factory()),
                    now_us=now_us,
                    reason="Alternative rejected after accepting taxonomy for this photograph.",
                )
                reviewed.append(public_id)
            connection.execute("COMMIT")
            return ReviewBatchResult(tuple(reviewed), ())
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def accept_all_pending_for_asset(
        self,
        suggestion_public_id: str,
        *,
        action_id_factory: Callable[[], str],
        now_us: int,
    ) -> ReviewBatchResult:
        """Accept every currently pending suggestion for the selected photograph atomically."""
        connection = self._factory.connect()
        reviewed: list[str] = []
        try:
            connection.execute("BEGIN IMMEDIATE")
            selected = connection.execute(
                "SELECT asset_id FROM ai_suggestions WHERE public_id=?",
                (suggestion_public_id,),
            ).fetchone()
            if selected is None:
                raise KeyError(f"unknown suggestion: {suggestion_public_id}")
            rows = connection.execute(
                """SELECT public_id FROM ai_suggestions
                   WHERE asset_id=? AND review_state='pending'
                   ORDER BY rank,id""",
                (int(selected["asset_id"]),),
            ).fetchall()
            for row in rows:
                public_id = str(row[0])
                self._review_in_transaction(
                    connection,
                    suggestion_public_id=public_id,
                    action="accept",
                    action_public_id=str(action_id_factory()),
                    now_us=now_us,
                    reason="Accepted with all pending suggestions for this photograph.",
                )
                reviewed.append(public_id)
            connection.execute("COMMIT")
            return ReviewBatchResult(tuple(reviewed), ())
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def supersede(
        self,
        old_suggestion_public_id: str,
        new_suggestion_public_id: str,
        *,
        action_public_id: str,
        now_us: int,
        reason: str | None = None,
    ) -> None:
        if old_suggestion_public_id == new_suggestion_public_id:
            raise ValueError("a suggestion cannot supersede itself")
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT id,asset_id,review_state FROM ai_suggestions WHERE public_id=?",
                (old_suggestion_public_id,),
            ).fetchone()
            new = connection.execute(
                "SELECT id,asset_id,review_state FROM ai_suggestions WHERE public_id=?",
                (new_suggestion_public_id,),
            ).fetchone()
            if old is None or new is None:
                raise KeyError("unknown suggestion in supersession request")
            if int(old["asset_id"]) != int(new["asset_id"]):
                raise ValueError("superseding suggestions must belong to the same asset")
            if str(old["review_state"]) not in {"pending", "deferred"}:
                raise ValueError("only pending or deferred suggestions may be superseded")
            if str(new["review_state"]) not in {"pending", "deferred"}:
                raise ValueError("replacement suggestion must be pending or deferred")
            connection.execute(
                """UPDATE ai_suggestions
                   SET review_state='superseded',reviewed_at_us=?,user_action_public_id=?
                   WHERE id=?""",
                (now_us, action_public_id, int(old["id"])),
            )
            connection.execute(
                "UPDATE ai_suggestions SET supersedes_suggestion_id=? WHERE id=?",
                (int(old["id"]), int(new["id"])),
            )
            self._record_action(
                connection,
                action_public_id=action_public_id,
                suggestion_id=int(old["id"]),
                action="supersede",
                prior_state=str(old["review_state"]),
                resulting_state="superseded",
                now_us=now_us,
                reason=reason,
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def reverse_acceptance(self, **kwargs: object) -> None:
        suggestion_public_id = str(kwargs["suggestion_public_id"])
        action_public_id = str(kwargs["action_public_id"])
        now_us = int(kwargs["now_us"])
        connection = self._factory.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT s.id,s.review_state,a.created_observation_id,
                          a.created_observation_revision,o.revision,a.id AS review_action_id
                   FROM ai_suggestions s
                   JOIN ai_review_actions a
                     ON a.suggestion_id=s.id AND a.action='accept'
                   LEFT JOIN observations o ON o.id=a.created_observation_id
                   WHERE s.public_id=?
                   ORDER BY a.id DESC LIMIT 1""",
                (suggestion_public_id,),
            ).fetchone()
            if row is None or str(row[1]) != "accepted":
                raise ValueError("suggestion has no reversible acceptance")
            if row[2] is None or row[4] is None or int(row[3]) != int(row[4]):
                raise ValueError("accepted observation has diverged")
            observation_id = int(row[2])
            next_revision = int(row[4]) + 1
            connection.execute(
                """UPDATE observations
                   SET confirmation_state='unconfirmed',modified_at_us=?,revision=?
                   WHERE id=?""",
                (now_us, next_revision, observation_id),
            )
            snapshot = json.dumps(
                {
                    "reversed_suggestion": suggestion_public_id,
                    "confirmation_state": "unconfirmed",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute(
                """INSERT INTO observation_revisions(
                    observation_id,revision,snapshot_json,changed_at_us
                ) VALUES(?,?,?,?)""",
                (observation_id, next_revision, snapshot, now_us),
            )
            connection.execute(
                """UPDATE canonical_enrichments
                   SET lifecycle_status='reversed',valid_to_us=?,reversed_at_us=?,
                       reversed_by='local_user',reversal_reason=?,modified_at_us=?
                   WHERE source_review_action_id=? AND lifecycle_status='active'""",
                (
                    now_us,
                    now_us,
                    None if kwargs.get("reason") is None else str(kwargs["reason"]),
                    now_us,
                    int(row["review_action_id"]),
                ),
            )
            connection.execute(
                """UPDATE ai_suggestions
                   SET review_state='pending',observation_id=NULL,reviewed_at_us=?,
                       user_action_public_id=? WHERE id=?""",
                (now_us, action_public_id, int(row[0])),
            )
            self._record_action(
                connection,
                action_public_id=action_public_id,
                suggestion_id=int(row[0]),
                action="reverse_accept",
                prior_state="accepted",
                resulting_state="pending",
                now_us=now_us,
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _review_in_transaction(
        self,
        connection: sqlite3.Connection,
        *,
        suggestion_public_id: str,
        action: str,
        action_public_id: str,
        now_us: int,
        reason: str | None,
    ) -> None:
        target = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}.get(action)
        if target is None:
            raise ValueError("unsupported review action")
        row = connection.execute(
            """SELECT s.id,s.review_state,s.asset_id,s.candidate_taxon_id,
                      s.region_of_interest_id,a.public_id,s.candidate_label,
                      s.raw_score,s.calibrated_score,s.confidence_band,
                      s.taxonomic_level,s.provenance_json,t.public_id AS taxon_public_id,
                      t.scientific_name,
                      (SELECT n.name FROM taxon_names n
                       WHERE n.taxon_id=t.id AND n.preferred=1
                       ORDER BY n.id LIMIT 1) AS vernacular_name,
                      t.rank
               FROM ai_suggestions s
               JOIN assets a ON a.id=s.asset_id
               LEFT JOIN taxa t ON t.id=s.candidate_taxon_id
               WHERE s.public_id=?""",
            (suggestion_public_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown suggestion: {suggestion_public_id}")
        prior_state = str(row["review_state"])
        if prior_state not in {"pending", "deferred"}:
            raise ValueError(f"suggestion is already {prior_state}")
        observation_id: int | None = None
        observation_revision: int | None = None
        if action == "accept" and row["candidate_taxon_id"] is not None:
            # A linked Aperture taxon allows acceptance to create a confirmed
            # observation. BioCLIP can also emit valid label-only suggestions
            # (for example when the installed taxonomy does not contain the
            # candidate). Those suggestions are still accepted as canonical
            # Aperture-owned enrichment below, but do not fabricate a taxon or
            # observation relationship.
            observation_public_id = f"obs-ai-{action_public_id}"
            cursor = connection.execute(
                """INSERT INTO observations(
                    public_id,asset_id,taxon_id,observation_type,confirmation_state,
                    source,region_of_interest_id,created_at_us,modified_at_us,revision
                ) VALUES(?,?,?,'organism','confirmed','user',?,?,?,1)""",
                (
                    observation_public_id,
                    int(row["asset_id"]),
                    int(row["candidate_taxon_id"]),
                    row["region_of_interest_id"],
                    now_us,
                    now_us,
                ),
            )
            observation_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT INTO observation_assets(observation_id,asset_id,role,linked_at_us) VALUES(?,?,'primary',?)",
                (observation_id, int(row["asset_id"]), now_us),
            )
            observation_revision = 1
            snapshot = json.dumps(
                {
                    "accepted_suggestion": suggestion_public_id,
                    "taxon_id": int(row["candidate_taxon_id"]),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute(
                """INSERT INTO observation_revisions(
                    observation_id,revision,snapshot_json,changed_at_us
                ) VALUES(?,?,?,?)""",
                (observation_id, observation_revision, snapshot, now_us),
            )
            connection.execute(
                "UPDATE ai_suggestions SET observation_id=? WHERE id=?",
                (observation_id, int(row["id"])),
            )
        connection.execute(
            """UPDATE ai_suggestions
               SET review_state=?,reviewed_at_us=?,user_action_public_id=?
               WHERE id=?""",
            (target, now_us, action_public_id, int(row["id"])),
        )
        self._record_action(
            connection,
            action_public_id=action_public_id,
            suggestion_id=int(row["id"]),
            action=action,
            prior_state=prior_state,
            resulting_state=target,
            now_us=now_us,
            reason=reason,
            observation_id=observation_id,
            observation_revision=observation_revision,
        )
        assignment = connection.execute(
            "SELECT assigned_to FROM ai_review_assignments WHERE suggestion_id=?",
            (int(row["id"]),),
        ).fetchone()
        if assignment is not None and action in {"accept", "reject"}:
            connection.execute(
                """INSERT INTO ai_review_assignment_events(
                    suggestion_id,assigned_to,assigned_by,action,note,created_at_us
                ) VALUES(?,?,?,?,?,?)""",
                (
                    int(row["id"]),
                    str(assignment["assigned_to"]),
                    "review-action",
                    "completed",
                    "",
                    now_us,
                ),
            )
            connection.execute(
                "DELETE FROM ai_review_assignments WHERE suggestion_id=?",
                (int(row["id"]),),
            )
        if action == "accept":
            self._create_canonical_enrichment(
                connection,
                row=row,
                suggestion_public_id=suggestion_public_id,
                action_public_id=action_public_id,
                observation_id=observation_id,
                now_us=now_us,
            )

    @staticmethod
    def _create_canonical_enrichment(
        connection: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        suggestion_public_id: str,
        action_public_id: str,
        observation_id: int | None,
        now_us: int,
    ) -> None:
        provider = connection.execute(
            "SELECT id FROM enrichment_providers WHERE provider_key='aperture.bioclip'"
        ).fetchone()
        if provider is None:
            raise RuntimeError("BioCLIP enrichment provider is not registered")
        field = connection.execute(
            """SELECT id FROM enrichment_provider_fields
               WHERE provider_id=? AND field_key='taxonomy.accepted'""",
            (int(provider[0]),),
        ).fetchone()
        if field is None:
            raise RuntimeError("BioCLIP accepted-taxonomy field is not registered")
        review_action = connection.execute(
            "SELECT id FROM ai_review_actions WHERE public_id=?",
            (action_public_id,),
        ).fetchone()
        if review_action is None:
            raise RuntimeError("acceptance action was not persisted")

        scientific_name = (
            str(row["scientific_name"])
            if row["scientific_name"] is not None
            else str(row["candidate_label"] or "")
        )
        value = {
            "taxon_public_id": None
            if row["taxon_public_id"] is None
            else str(row["taxon_public_id"]),
            "scientific_name": scientific_name,
            "vernacular_name": None
            if row["vernacular_name"] is None
            else str(row["vernacular_name"]),
            "rank": None if row["rank"] is None else str(row["rank"]),
            "taxonomic_level": None
            if row["taxonomic_level"] is None
            else str(row["taxonomic_level"]),
        }
        provenance = json.loads(str(row["provenance_json"]))
        provenance.update(
            {
                "provider_key": "aperture.bioclip",
                "source_suggestion_public_id": suggestion_public_id,
                "acceptance_action_public_id": action_public_id,
            }
        )
        connection.execute(
            """INSERT INTO canonical_enrichments(
                public_id,asset_id,provider_id,field_id,source_suggestion_id,
                source_review_action_id,source_observation_id,source_record_reference,
                value_type,display_value,normalized_value,value_json,confidence,
                provenance_json,lifecycle_status,valid_from_us,accepted_at_us,
                accepted_by,supersedes_enrichment_id,created_at_us,modified_at_us
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,'local_user',?,?,?)""",
            (
                f"enrichment-{action_public_id}",
                int(row["asset_id"]),
                int(provider[0]),
                int(field[0]),
                int(row["id"]),
                int(review_action[0]),
                observation_id,
                suggestion_public_id,
                "taxonomy",
                scientific_name,
                scientific_name.casefold(),
                json.dumps(value, sort_keys=True, separators=(",", ":")),
                row["calibrated_score"]
                if row["calibrated_score"] is not None
                else row["raw_score"],
                json.dumps(provenance, sort_keys=True, separators=(",", ":")),
                now_us,
                now_us,
                None,
                now_us,
                now_us,
            ),
        )

    @staticmethod
    def _record_action(
        connection: sqlite3.Connection,
        *,
        action_public_id: str,
        suggestion_id: int,
        action: str,
        prior_state: str,
        resulting_state: str,
        now_us: int,
        reason: str | None = None,
        observation_id: int | None = None,
        observation_revision: int | None = None,
    ) -> None:
        connection.execute(
            """INSERT INTO ai_review_actions(
                public_id,suggestion_id,action,prior_state,resulting_state,
                created_observation_id,created_observation_revision,reason,created_at_us
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                action_public_id,
                suggestion_id,
                action,
                prior_state,
                resulting_state,
                observation_id,
                observation_revision,
                reason,
                now_us,
            ),
        )
        suggestion_public_id = str(
            connection.execute(
                "SELECT public_id FROM ai_suggestions WHERE id=?", (suggestion_id,)
            ).fetchone()[0]
        )
        payload = json.dumps(
            {
                "suggestion_public_id": suggestion_public_id,
                "action": action,
                "prior_state": prior_state,
                "resulting_state": resulting_state,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            """INSERT INTO audit_log(
                public_id,actor,action_type,target_public_id,before_json,after_json,
                created_at_us,correlation_id
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                f"audit-{action_public_id}",
                "local_user",
                f"ai_review.{action}",
                suggestion_public_id,
                json.dumps({"review_state": prior_state}, sort_keys=True),
                json.dumps({"review_state": resulting_state}, sort_keys=True),
                now_us,
                action_public_id,
            ),
        )
        connection.execute(
            """INSERT INTO event_outbox(
                public_id,event_type,schema_version,aggregate_public_id,payload_json,
                created_at_us,dispatch_state,attempt_count
            ) VALUES(?,?,?,?,?,?,'pending',0)""",
            (
                f"event-{action_public_id}",
                "ai.review.changed",
                1,
                suggestion_public_id,
                payload,
                now_us,
            ),
        )

    @staticmethod
    def _resolve_taxon(connection: sqlite3.Connection, public_id: str | None) -> int | None:
        if public_id is None:
            return None
        row = connection.execute("SELECT id FROM taxa WHERE public_id=?", (public_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown taxon: {public_id}")
        return int(row[0])

    @staticmethod
    def _resolve_prompt_set(connection: sqlite3.Connection, value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            row = connection.execute("SELECT id FROM prompt_sets WHERE id=?", (value,)).fetchone()
        else:
            row = connection.execute(
                "SELECT id FROM prompt_sets WHERE public_id=?", (str(value),)
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown prompt set: {value}")
        return int(row[0])

    @staticmethod
    def _resolve_roi(
        connection: sqlite3.Connection, public_id: object, asset_id: int
    ) -> int | None:
        if public_id is None:
            return None
        row = connection.execute(
            "SELECT id,asset_id FROM regions_of_interest WHERE public_id=?", (str(public_id),)
        ).fetchone()
        if row is None or int(row[1]) != asset_id:
            raise ValueError("ROI does not belong to asset")
        return int(row[0])


def _prompt_set_record(row: sqlite3.Row) -> PromptSetRecord:
    return PromptSetRecord(
        public_id=str(row["public_id"]),
        identity=str(row["identity"]),
        semantic_version=str(row["semantic_version"]),
        model_family=str(row["model_family"]),
        checksum=str(row["checksum"]),
        active=bool(row["active"]),
        installed_at_us=int(row["installed_at_us"]),
    )


def _suggestion_projection(row: sqlite3.Row | Sequence[object]) -> SuggestionProjection:
    return SuggestionProjection(
        public_id=str(row[1]),
        asset_public_id=str(row[2]),
        candidate_taxon_public_id=None if row[3] is None else str(row[3]),
        candidate_label=None if row[4] is None else str(row[4]),
        raw_score=float(row[5]),
        calibrated_score=None if row[6] is None else float(row[6]),
        rank=int(row[7]),
        confidence_band=ConfidenceBand(str(row[8])),
        taxonomic_level=None if row[9] is None else str(row[9]),
        review_state=SuggestionReviewState(str(row[10])),
        provenance_json=str(row[11]),
        region_of_interest_public_id=None if row[12] is None else str(row[12]),
        assigned_to=(
            None if len(row) < 14 or row[13] is None else str(row[13])
        ),
    )

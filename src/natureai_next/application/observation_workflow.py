"""Unified, append-only observation identification and review workflow."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Assertion:
    public_id: str
    observation_public_id: str
    kind: str
    proposed_name: str
    author: str
    authority_level: int
    confidence: float | None
    status: str
    rationale: str
    created_at_us: int


class ObservationWorkflowService:
    """Owns assertions, decisions, referrals and research-context links."""

    def __init__(self, database: Path):
        self.database = Path(database)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def assert_identification(self, observation_public_id: str, *, kind: str,
                              proposed_name: str, author: str, authority_level: int = 0,
                              confidence: float | None = None, rationale: str = "",
                              evidence: tuple[str, ...] = (), parent_public_id: str | None = None) -> str:
        if kind not in {"observer", "ai", "specialist", "authority", "reference"}:
            raise ValueError("unsupported assertion kind")
        if not proposed_name.strip() or not author.strip():
            raise ValueError("identification and author are required")
        if not 0 <= authority_level <= 9 or confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("invalid authority level or confidence")
        assertion_id = f"assertion-{uuid.uuid4()}"; now = time.time_ns() // 1000
        with self._connect() as cx:
            observation = cx.execute("SELECT id FROM observations WHERE public_id=?", (observation_public_id,)).fetchone()
            if not observation: raise KeyError(observation_public_id)
            parent = cx.execute("SELECT id FROM observation_assertions WHERE public_id=?", (parent_public_id,)).fetchone() if parent_public_id else None
            cx.execute("""INSERT INTO observation_assertions(public_id,observation_id,parent_assertion_id,assertion_kind,
                proposed_name,author,authority_level,confidence,status,rationale,evidence_json,created_at_us)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (assertion_id, observation[0], parent[0] if parent else None,
                kind, proposed_name.strip(), author.strip(), authority_level, confidence, "proposed",
                rationale.strip(), json.dumps(evidence), now))
        return assertion_id

    def decide(self, assertion_public_id: str, *, status: str, reviewer: str, rationale: str = "") -> None:
        if status not in {"accepted", "rejected", "deferred", "disputed", "superseded"}: raise ValueError("invalid decision")
        now = time.time_ns() // 1000
        with self._connect() as cx:
            row = cx.execute("SELECT id,observation_id FROM observation_assertions WHERE public_id=?", (assertion_public_id,)).fetchone()
            if not row: raise KeyError(assertion_public_id)
            if status == "accepted":
                cx.execute("UPDATE observation_assertions SET status='superseded',decided_at_us=?,decided_by=? WHERE observation_id=? AND status='accepted' AND id<>?", (now, reviewer, row[1], row[0]))
                cx.execute("UPDATE observations SET confirmation_state='confirmed',modified_at_us=?,revision=revision+1 WHERE id=?", (now, row[1]))
            elif status == "disputed":
                cx.execute("UPDATE observations SET confirmation_state='unconfirmed',modified_at_us=?,revision=revision+1 WHERE id=?", (now, row[1]))
            cx.execute("UPDATE observation_assertions SET status=?,rationale=CASE WHEN ?='' THEN rationale ELSE ? END,decided_at_us=?,decided_by=? WHERE id=?", (status, rationale, rationale, now, reviewer, row[0]))


    def decide_many(self, assertion_public_ids: tuple[str, ...], *, status: str, reviewer: str, rationale: str = "") -> None:
        """Apply one review decision atomically to multiple assertion rows."""
        if status not in {"accepted", "rejected", "deferred", "disputed", "superseded"}:
            raise ValueError("invalid decision")
        ids = tuple(dict.fromkeys(str(value) for value in assertion_public_ids if str(value)))
        if not ids:
            return
        now = time.time_ns() // 1000
        with self._connect() as cx:
            placeholders = ",".join("?" for _ in ids)
            rows = cx.execute(
                f"SELECT id,public_id,observation_id FROM observation_assertions WHERE public_id IN ({placeholders})",
                ids,
            ).fetchall()
            found = {str(row["public_id"]): row for row in rows}
            missing = [value for value in ids if value not in found]
            if missing:
                raise KeyError(", ".join(missing))
            if status == "accepted":
                by_observation: dict[int, list[sqlite3.Row]] = {}
                for value in ids:
                    row = found[value]
                    by_observation.setdefault(int(row["observation_id"]), []).append(row)
                if any(len(values) > 1 for values in by_observation.values()):
                    raise ValueError("only one identification per observation can be accepted at a time")
                for observation_id, values in by_observation.items():
                    selected = values[0]
                    cx.execute(
                        "UPDATE observation_assertions SET status='superseded',decided_at_us=?,decided_by=? WHERE observation_id=? AND status='accepted' AND id<>?",
                        (now, reviewer, observation_id, selected["id"]),
                    )
                    cx.execute(
                        "UPDATE observations SET confirmation_state='confirmed',modified_at_us=?,revision=revision+1 WHERE id=?",
                        (now, observation_id),
                    )
            elif status == "disputed":
                observation_ids = tuple(dict.fromkeys(int(found[value]["observation_id"]) for value in ids))
                for observation_id in observation_ids:
                    cx.execute(
                        "UPDATE observations SET confirmation_state='unconfirmed',modified_at_us=?,revision=revision+1 WHERE id=?",
                        (now, observation_id),
                    )
            for value in ids:
                row = found[value]
                cx.execute(
                    "UPDATE observation_assertions SET status=?,rationale=CASE WHEN ?='' THEN rationale ELSE ? END,decided_at_us=?,decided_by=? WHERE id=?",
                    (status, rationale, rationale, now, reviewer, row["id"]),
                )

    def accept_one_reject_remaining(self, assertion_public_id: str, *, reviewer: str, rationale: str = "") -> None:
        """Accept one candidate and reject all still-unconfirmed siblings atomically."""
        now = time.time_ns() // 1000
        with self._connect() as cx:
            row = cx.execute("SELECT id,observation_id FROM observation_assertions WHERE public_id=?", (assertion_public_id,)).fetchone()
            if not row:
                raise KeyError(assertion_public_id)
            cx.execute(
                "UPDATE observation_assertions SET status='superseded',decided_at_us=?,decided_by=? WHERE observation_id=? AND status='accepted' AND id<>?",
                (now, reviewer, row["observation_id"], row["id"]),
            )
            cx.execute(
                "UPDATE observation_assertions SET status='rejected',decided_at_us=?,decided_by=? WHERE observation_id=? AND id<>? AND status IN ('proposed','deferred','disputed')",
                (now, reviewer, row["observation_id"], row["id"]),
            )
            cx.execute(
                "UPDATE observation_assertions SET status='accepted',rationale=CASE WHEN ?='' THEN rationale ELSE ? END,decided_at_us=?,decided_by=? WHERE id=?",
                (rationale, rationale, now, reviewer, row["id"]),
            )
            cx.execute(
                "UPDATE observations SET confirmation_state='confirmed',modified_at_us=?,revision=revision+1 WHERE id=?",
                (now, row["observation_id"]),
            )

    def reject_unconfirmed(self, observation_public_id: str, *, reviewer: str) -> int:
        """Reject every proposed/deferred/disputed candidate for one observation atomically."""
        now = time.time_ns() // 1000
        with self._connect() as cx:
            observation = cx.execute("SELECT id FROM observations WHERE public_id=?", (observation_public_id,)).fetchone()
            if not observation:
                raise KeyError(observation_public_id)
            cursor = cx.execute(
                "UPDATE observation_assertions SET status='rejected',decided_at_us=?,decided_by=? WHERE observation_id=? AND status IN ('proposed','deferred','disputed')",
                (now, reviewer, observation["id"]),
            )
            cx.execute(
                "UPDATE observations SET confirmation_state='unconfirmed',modified_at_us=?,revision=revision+1 WHERE id=?",
                (now, observation["id"]),
            )
            return int(cursor.rowcount)

    def refer(self, observation_public_id: str, *, referred_by: str, referred_to: str,
              authority_level: int, question: str, assertion_public_id: str | None = None,
              parent_referral_public_id: str | None = None) -> str:
        if not 1 <= authority_level <= 9 or not referred_to.strip(): raise ValueError("referral target and level are required")
        public_id=f"referral-{uuid.uuid4()}";now=time.time_ns()//1000
        with self._connect() as cx:
            obs=cx.execute("SELECT id FROM observations WHERE public_id=?",(observation_public_id,)).fetchone()
            if not obs: raise KeyError(observation_public_id)
            assertion=cx.execute("SELECT id FROM observation_assertions WHERE public_id=?",(assertion_public_id,)).fetchone() if assertion_public_id else None
            parent=cx.execute("SELECT id FROM observation_review_referrals WHERE public_id=?",(parent_referral_public_id,)).fetchone() if parent_referral_public_id else None
            cx.execute("INSERT INTO observation_review_referrals(public_id,observation_id,assertion_id,referred_by,referred_to,authority_level,status,question,parent_referral_id,created_at_us,updated_at_us) VALUES(?,?,?,?,?,?,'open',?,?,?,?)",(public_id,obs[0],assertion[0] if assertion else None,referred_by,referred_to,authority_level,question,parent[0] if parent else None,now,now))
        return public_id

    def link(self, observation_public_id: str, context_type: str, context_public_id: str, *, linked_by: str) -> None:
        if context_type not in {"project","dossier","collection"}: raise ValueError("invalid context type")
        with self._connect() as cx:
            obs=cx.execute("SELECT id FROM observations WHERE public_id=?",(observation_public_id,)).fetchone()
            if not obs: raise KeyError(observation_public_id)
            cx.execute("INSERT OR IGNORE INTO observation_context_links VALUES(?,?,?,?,?)",(obs[0],context_type,context_public_id,linked_by,time.time_ns()//1000))

    def history(self, observation_public_id: str) -> tuple[Assertion, ...]:
        with self._connect() as cx:
            rows=cx.execute("""SELECT a.public_id,o.public_id,a.assertion_kind,a.proposed_name,a.author,a.authority_level,
                a.confidence,a.status,a.rationale,a.created_at_us FROM observation_assertions a JOIN observations o ON o.id=a.observation_id
                WHERE o.public_id=? ORDER BY a.created_at_us,a.id""",(observation_public_id,)).fetchall()
        return tuple(Assertion(*row) for row in rows)

    def record_contribution(self, observation_public_id: str, *, connector_id: str,
                            payload: dict, state: str, response: dict | None = None,
                            remote_id: str | None = None, remote_url: str | None = None,
                            error: str = "") -> str:
        if state not in {"draft","validated","queued","submitted","synchronised","failed","withdrawn"}:
            raise ValueError("invalid contribution state")
        encoded=json.dumps(payload,sort_keys=True,separators=(",",":"));fingerprint=hashlib.sha256(encoded.encode()).hexdigest();now=time.time_ns()//1000
        with self._connect() as cx:
            obs=cx.execute("SELECT id FROM observations WHERE public_id=?",(observation_public_id,)).fetchone()
            if not obs: raise KeyError(observation_public_id)
            public_id=f"contribution-{uuid.uuid4()}"
            cx.execute("""INSERT INTO external_contributions(public_id,observation_id,connector_id,state,remote_id,remote_url,request_fingerprint,response_json,last_error,created_at_us,updated_at_us)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(observation_id,connector_id,request_fingerprint) DO UPDATE SET state=excluded.state,remote_id=excluded.remote_id,remote_url=excluded.remote_url,response_json=excluded.response_json,last_error=excluded.last_error,updated_at_us=excluded.updated_at_us""",
                (public_id,obs[0],connector_id,state,remote_id,remote_url,fingerprint,json.dumps(response or {}),error,now,now))
            row=cx.execute("SELECT public_id FROM external_contributions WHERE observation_id=? AND connector_id=? AND request_fingerprint=?",(obs[0],connector_id,fingerprint)).fetchone()
        return str(row[0])

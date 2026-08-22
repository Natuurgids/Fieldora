from __future__ import annotations
import sqlite3
from pathlib import Path
from natureai_next.application.observation_workflow import ObservationWorkflowService
from natureai_next.application.workspace_context import WorkspaceContext

def _observation_db(path: Path) -> None:
    with sqlite3.connect(path) as cx:
        cx.executescript("""
        CREATE TABLE observations(id INTEGER PRIMARY KEY, public_id TEXT UNIQUE, confirmation_state TEXT, modified_at_us INTEGER DEFAULT 0, revision INTEGER DEFAULT 0);
        CREATE TABLE observation_assertions(id INTEGER PRIMARY KEY, public_id TEXT UNIQUE, observation_id INTEGER, status TEXT, rationale TEXT DEFAULT '', decided_at_us INTEGER, decided_by TEXT);
        """)
        cx.execute("INSERT INTO observations(public_id,confirmation_state) VALUES('obs-1','unconfirmed')")
        oid=cx.execute("SELECT id FROM observations").fetchone()[0]
        cx.executemany("INSERT INTO observation_assertions(public_id,observation_id,status) VALUES(?,?,?)", [('a-1',oid,'proposed'),('a-2',oid,'proposed'),('a-3',oid,'deferred')])

def test_accept_one_rejects_remaining_atomically(tmp_path: Path) -> None:
    db=tmp_path/'obs.sqlite';_observation_db(db);service=ObservationWorkflowService(db)
    service.accept_one_reject_remaining('a-2',reviewer='reviewer')
    with sqlite3.connect(db) as cx:
        assert cx.execute("SELECT public_id,status FROM observation_assertions ORDER BY public_id").fetchall()==[('a-1','rejected'),('a-2','accepted'),('a-3','rejected')]
        assert cx.execute("SELECT confirmation_state FROM observations").fetchone()[0]=='confirmed'

def test_accept_many_rejects_multiple_candidates_for_same_observation(tmp_path: Path) -> None:
    db=tmp_path/'obs.sqlite';_observation_db(db);service=ObservationWorkflowService(db)
    try:service.decide_many(('a-1','a-2'),status='accepted',reviewer='reviewer')
    except ValueError as exc:assert 'only one identification' in str(exc)
    else:raise AssertionError('expected duplicate acceptance guard')
    with sqlite3.connect(db) as cx:assert cx.execute("SELECT count(*) FROM observation_assertions WHERE status='accepted'").fetchone()[0]==0

def test_workspace_context_data_changed_is_broadcast() -> None:
    context=WorkspaceContext();events=[];context.subscribe(events.append);context.data_changed('project-1',source='test')
    assert events[0].topic=='data.changed' and events[0].project_id=='project-1' and events[0].source=='test'

def test_dossier_workspace_has_parent_column_and_hierarchy_renderer() -> None:
    text=(Path(__file__).parents[1]/'src/natureai_next/ui/qt/science.py').read_text(encoding='utf-8')
    assert '"Parent dossier"' in text
    assert 'def append_branch(dossier: dict, depth: int)' in text
    assert "'↳ ' if depth else ''" in text

def test_research_actions_refresh_other_workspaces() -> None:
    text=(Path(__file__).parents[1]/'src/natureai_next/ui/qt/v5_desktop.py').read_text(encoding='utf-8')
    assert 'def _refresh_after_mutation' in text
    assert "self.context.data_changed(pid,source='research-operations')" in text
    assert 'accept_one_reject_remaining' in text

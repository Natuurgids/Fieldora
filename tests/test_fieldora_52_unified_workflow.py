import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from natureai_next.application.observation_workflow import ObservationWorkflowService
from natureai_next.application.project_export_v5 import ProjectExportSelection, SelectableProjectExporter
from natureai_next.infrastructure.database.migrations.v039_unified_observation_workflow import SQL
from natureai_next.infrastructure.connectors.observation_org import ObservationOrgClient


def workflow_database(path: Path) -> Path:
    with sqlite3.connect(path) as cx:
        cx.executescript("""
        CREATE TABLE assets(id INTEGER PRIMARY KEY,public_id TEXT,modified_at_us INTEGER DEFAULT 0);
        CREATE TABLE observations(id INTEGER PRIMARY KEY,public_id TEXT UNIQUE,asset_id INTEGER REFERENCES assets(id),confirmation_state TEXT DEFAULT 'unconfirmed',modified_at_us INTEGER DEFAULT 0,revision INTEGER DEFAULT 1);
        INSERT INTO assets VALUES(1,'asset-1',0);
        INSERT INTO observations VALUES(1,'observation-1',1,'unconfirmed',0,1);
        """ + SQL)
    return path


def test_assertion_dispute_referral_link_and_contribution_are_append_only(tmp_path):
    db=workflow_database(tmp_path/'library.sqlite3');service=ObservationWorkflowService(db)
    first=service.assert_identification('observation-1',kind='observer',proposed_name='Ardea alba',author='Observer')
    second=service.assert_identification('observation-1',kind='specialist',proposed_name='Ardea cinerea',author='Specialist',authority_level=2,parent_public_id=first)
    service.decide(second,status='accepted',reviewer='Reviewer')
    service.decide(first,status='disputed',reviewer='Observer',rationale='Plumage differs')
    referral=service.refer('observation-1',referred_by='Reviewer',referred_to='National authority',authority_level=4,question='Resolve conflict',assertion_public_id=second)
    service.link('observation-1','project','project-1',linked_by='Observer')
    contribution=service.record_contribution('observation-1',connector_id='observation-org',payload={'species':'Ardea cinerea'},state='submitted',remote_id='42')
    history=service.history('observation-1')
    assert [row.public_id for row in history]==[first,second]
    assert history[0].status=='disputed' and history[1].status=='accepted'
    assert referral.startswith('referral-') and contribution.startswith('contribution-')


def test_selectable_project_export_contains_index_map_and_manifest(tmp_path):
    science=tmp_path/'science.sqlite3';library=tmp_path/'library.sqlite3';snapshot=tmp_path/'map.png';snapshot.write_bytes(b'png')
    with sqlite3.connect(science) as cx:
        cx.executescript("""CREATE TABLE pm_projects(project_id TEXT PRIMARY KEY,name TEXT,description TEXT,status TEXT,owner_id TEXT,start_date TEXT,due_date TEXT,budget REAL,currency TEXT,template_id TEXT,client_name TEXT,created_at_us INTEGER,updated_at_us INTEGER);
        CREATE TABLE pm_tasks(task_id TEXT,project_id TEXT,title TEXT);CREATE TABLE pm_project_notes(note_id TEXT,project_id TEXT,title TEXT);CREATE TABLE pm_research_areas(area_id TEXT,project_id TEXT,name TEXT,geojson TEXT);CREATE TABLE pm_project_map_snapshots(snapshot_id TEXT,project_id TEXT,name TEXT,image_path TEXT);CREATE TABLE pm_project_media(project_id TEXT,asset_public_id TEXT,media_type TEXT,note TEXT,included_default INTEGER);
        INSERT INTO pm_projects VALUES('p1','Wetland','Survey','active','u','','',0,'EUR',NULL,'',0,0);INSERT INTO pm_tasks VALUES('t1','p1','Survey');INSERT INTO pm_project_notes VALUES('n1','p1','Note');INSERT INTO pm_research_areas VALUES('a1','p1','Area','{}');INSERT INTO pm_project_media VALUES('p1','asset-1','image','',1);""")
        cx.execute("INSERT INTO pm_project_map_snapshots VALUES('s1','p1','Map',?)",(str(snapshot),))
    sqlite3.connect(library).close();out=tmp_path/'project.zip'
    SelectableProjectExporter(science,library).export('p1',out,ProjectExportSelection())
    with zipfile.ZipFile(out) as z:
        assert {'manifest.json','data/project.json','index/index.html','index/media.csv','maps/map.png'} <= set(z.namelist())
        assert json.loads(z.read('manifest.json'))['format']=='fieldora.project-package'


def test_observation_org_is_test_first_and_requires_authentication():
    client=ObservationOrgClient()
    assert client.base_url=='https://test.observation.org'
    with pytest.raises(PermissionError):client.create_observation({'species':'x','date':'2026-01-01','lat':1,'lng':2})
    production=ObservationOrgClient(access_token='token',production=True)
    assert production.base_url=='https://observation.org'


def test_v52_screens_are_live_and_quarantined_adapter_is_removed():
    root=Path(__file__).resolve().parents[1]
    ui=(root/'src/natureai_next/ui/qt/v5_desktop.py').read_text()
    science=(root/'src/natureai_next/ui/qt/science.py').read_text()
    for feature in ('DataTable','observation_assertions','Refer to specialist','Link to research','Export project package'):
        assert feature in ui
    assert 'Pre-0.06 persistence adapter retained' not in science
    assert 'CREATE TABLE IF NOT EXISTS science_projects' not in science

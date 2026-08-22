"""Selectable, integrity-addressed Fieldora project archive."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import sqlite3
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectExportSelection:
    tasks: bool = True
    notes: bool = True
    research_areas: bool = True
    map_snapshots: bool = True
    media_index: bool = True
    original_media: bool = False
    surveys: bool = True


class SelectableProjectExporter:
    def __init__(self, science_database: Path, library_database: Path):
        self.science_database=Path(science_database);self.library_database=Path(library_database)

    @staticmethod
    def _rows(cx,table,project_id):
        return [dict(row) for row in cx.execute(f"SELECT * FROM {table} WHERE project_id=?",(project_id,))]

    @staticmethod
    def _has_table(cx, table):
        return cx.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None

    def export(self, project_id: str, destination: Path, selection: ProjectExportSelection) -> Path:
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.science_database) as cx:
            cx.row_factory=sqlite3.Row
            row=cx.execute("SELECT * FROM pm_projects WHERE project_id=?",(project_id,)).fetchone()
            if not row: raise KeyError(project_id)
            project=dict(row);records={"project":project}
            if selection.tasks:records["tasks"]=self._rows(cx,"pm_tasks",project_id)
            if selection.notes:records["notes"]=self._rows(cx,"pm_project_notes",project_id)
            if selection.research_areas:records["research_areas"]=self._rows(cx,"pm_research_areas",project_id)
            if selection.surveys and self._has_table(cx, "pm_survey_protocols"):
                records["survey_protocols"] = self._rows(cx, "pm_survey_protocols", project_id)
                records["survey_events"] = self._rows(cx, "pm_survey_events", project_id)
                event_ids = [row["survey_event_id"] for row in records["survey_events"]]
                records["survey_results"] = [
                    dict(row) for event_id in event_ids
                    for row in cx.execute("SELECT * FROM pm_survey_detections WHERE survey_event_id=?", (event_id,))
                ]
            snapshots=self._rows(cx,"pm_project_map_snapshots",project_id) if selection.map_snapshots else []
            media=self._rows(cx,"pm_project_media",project_id) if selection.media_index else []
            records["map_snapshots"]=snapshots;records["media"]=media
        manifest={"format":"fieldora.project-package","format_version":2,"fieldora_version":"5.4.0",
                  "created_at_us":time.time_ns()//1000,"project_id":project_id,"selection":asdict(selection),"files":[]}
        with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as z:
            def put(name,data):
                raw=data if isinstance(data,bytes) else data.encode("utf-8");z.writestr(name,raw)
                manifest["files"].append({"path":name,"size":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
            put("data/project.json",json.dumps(records,indent=2,ensure_ascii=False))
            out=io.StringIO();writer=csv.DictWriter(out,fieldnames=("asset_public_id","media_type","note","included_default"));writer.writeheader()
            for item in media:writer.writerow({key:item.get(key,"") for key in writer.fieldnames})
            put("index/media.csv",out.getvalue())
            items="".join(f"<li>{html.escape(m.get('media_type',''))}: {html.escape(m.get('asset_public_id',''))}</li>" for m in media)
            put("index/index.html",f"<!doctype html><meta charset=utf-8><title>{html.escape(project['name'])}</title><h1>{html.escape(project['name'])}</h1><p>{html.escape(project['description'])}</p><h2>Evidence index</h2><ul>{items}</ul>")
            for snap in snapshots:
                path=Path(str(snap.get("image_path", "")))
                if path.is_file():put(f"maps/{path.name}",path.read_bytes())
            if selection.original_media:
                with sqlite3.connect(self.library_database) as lib:
                    for item in media:
                        found=lib.execute("""SELECT f.normalized_path FROM assets a JOIN file_instances f ON f.id=a.primary_file_instance_id
                            WHERE a.public_id=? AND f.availability_state='available'""",(item["asset_public_id"],)).fetchone()
                        if found and Path(found[0]).is_file():put(f"media/{item['asset_public_id']}/{Path(found[0]).name}",Path(found[0]).read_bytes())
            z.writestr("manifest.json",json.dumps(manifest,indent=2))
        return destination

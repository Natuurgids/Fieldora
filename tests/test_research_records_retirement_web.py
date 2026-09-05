from __future__ import annotations

from pathlib import Path

from natureai_next.server.api import ApiResponse
from natureai_next.server.research_records_web import patch_research_records_response


def test_research_records_owner_retires_only_legacy_save_competitor() -> None:
    legacy = b"""
const beforeResearchSave = true;
async function saveScienceRecord(){
  const project=q("science-project").value;
  return project;
}
async function reviewSelected(statusValue){
  return statusValue;
}
async function loadResearchDomain(){
  return q("science-project").value;
}
q("science-save").onclick=saveScienceRecord;
const afterResearchSave = true;
"""

    response = patch_research_records_response(
        "/app.js",
        ApiResponse(200, legacy, "text/javascript; charset=utf-8"),
    )
    script = response.body.decode("utf-8")

    assert "WEB-042: Research records use server-owned identity and revisions." in script
    assert "async function saveScienceRecord(){" not in script
    assert 'q("science-save").onclick=saveScienceRecord;' not in script
    assert "async function reviewSelected(statusValue){" in script
    assert "async function loadResearchDomain(){" in script
    assert 'q("science-project").value' in script
    assert "const beforeResearchSave = true;" in script
    assert "const afterResearchSave = true;" in script


def test_research_records_retirement_matches_bundled_app() -> None:
    app_path = (
        Path(__file__).parents[1]
        / "src"
        / "natureai_next"
        / "resources"
        / "server_web"
        / "app.js"
    )
    base = ApiResponse(200, app_path.read_bytes(), "text/javascript; charset=utf-8")

    response = patch_research_records_response("/app.js", base)
    script = response.body.decode("utf-8")

    assert "async function saveScienceRecord(){" not in script
    assert 'q("science-save").onclick=saveScienceRecord;' not in script
    assert "async function reviewSelected(statusValue){" in script
    assert "async function loadResearchDomain(){" in script
    assert "loadResearchDomain=async function(){" in script
    assert 'byId("science-project")' in script
    assert "WEB-042: Research records use server-owned identity and revisions." in script

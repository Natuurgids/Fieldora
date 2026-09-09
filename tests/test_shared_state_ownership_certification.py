from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.knowledge_review_web import patch_knowledge_review_web_response
from natureai_next.server.library_media_state_provider_web import (
    _LIBRARY_MEDIA_STATE_PROVIDER_PATCH,
)
from natureai_next.server.modular_shell_web import patch_modular_shell_response
from natureai_next.server.portfolio_module_web import patch_portfolio_module_response
from natureai_next.server.project_context_provider_web import (
    patch_project_context_provider_response,
)
from natureai_next.server.project_list_provider_web import patch_project_list_provider_response
from natureai_next.server.research_records_web import patch_research_records_response
from natureai_next.server.science_workflow_web import patch_science_workflow_web_response
from natureai_next.server.web_module_contract_runtime import patch_runtime_contracts_response


def _script(patch) -> str:
    return patch(
        "/app.js",
        ApiResponse(200, b"", "text/javascript; charset=utf-8"),
    ).body.decode("utf-8")


def test_a06_shared_state_owner_inventory() -> None:
    observations = _script(patch_science_workflow_web_response)
    knowledge = _script(patch_knowledge_review_web_response)
    research = _script(patch_research_records_response)
    portfolio = _script(patch_portfolio_module_response)
    library = _LIBRARY_MEDIA_STATE_PROVIDER_PATCH.decode("utf-8")

    shell = patch_modular_shell_response(
        "/app.js",
        ApiResponse(
            200,
            b'let operationsDomain="assets";async function loadOperations(){}',
            "text/javascript; charset=utf-8",
        ),
    )
    runtime_response = patch_runtime_contracts_response("/app.js", shell)
    runtime = runtime_response.body.decode("utf-8")
    project_list_response = patch_project_list_provider_response(
        "/app.js", runtime_response
    )
    projects = patch_project_context_provider_response(
        "/app.js", project_list_response
    ).body.decode("utf-8")

    # Projects: one immutable list owner plus one validated context owner.
    assert "WEB-PROJECT-LIST-PROVIDER" in projects
    assert "Object.freeze(state.items.map" in projects
    assert 'contractName="projects.context.select"' in projects
    assert 'const state={projectId:""};' in projects
    assert "selectedProject" not in projects

    # Observation workspace: canonical items/filter/selection stay inside its module.
    assert 'let observationItems=Object.freeze([]),observationFilterState="all"' in observations
    assert "const selectedObservationIds=new Set()" in observations
    assert "fieldora:observation-state-changed" in observations
    assert "selectedObservations" not in observations

    # Library: immutable snapshots/events replace ambient media and mediaFilter integration.
    assert 'const snapshot=()=>Object.freeze({module_id:"library.catalog",items,filter})' in library
    assert "fieldora:library-media-state-changed" in library
    assert "media=reset?" not in library
    assert "mediaFilter=" not in library

    # Knowledge: governed state is private and is no longer mirrored to ambient knowledge.
    assert "let governedKnowledge=[];" in knowledge
    assert "governedKnowledge.findIndex" in knowledge
    assert 'if(typeof knowledge!=="undefined")knowledge=governedKnowledge;' not in knowledge

    # Research and Portfolio each keep their active view/domain state inside their module.
    assert 'let researchDomain=document.querySelector("[data-research-domain].primary")?.dataset.researchDomain||"specimens";' in research
    assert 'const state={mounted:false,controller:null,view:"hierarchy"};' in portfolio

    # Application-owned contracts expose copied/read-only state instead of mutable globals.
    assert "register('auth.current-user','application.auth',Object.freeze({current:()=>typeof me==='undefined'||!me?null:Object.freeze({...me})}))" in runtime
    assert "let operationsWorkspaceDomain=typeof operationsDomain==='undefined'?null:String(operationsDomain)" in runtime
    assert "const currentDomain=()=>operationsWorkspaceDomain" in runtime
    assert "operationsWorkspaceDomain=next;return loadOperations()" in runtime
    assert "let operationsWorkspaceRecords=Object.freeze([])" in runtime
    assert "operationsWorkspaceRecords=freezeRecords(result)" in runtime
    assert "const currentRecords=()=>operationsWorkspaceRecords" in runtime
    assert "records:currentRecords" in runtime

    # A07 owns DOM boundaries: the application workspace host no longer reaches into
    # Operations' private list DOM to reconstruct its public records snapshot.
    assert "document.getElementById('operations-list')" not in runtime
    assert "dataset.records" not in runtime

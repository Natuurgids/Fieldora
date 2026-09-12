from natureai_next.server.api import ApiResponse
from natureai_next.server.web_capabilities import patch_zero_trust_web_response


def test_home_projects_read_modular_project_list_contract() -> None:
    base = ApiResponse(
        200,
        b"let projects=[];function loadHome(){}",
        "text/javascript; charset=utf-8",
    )

    projected = patch_zero_trust_web_response("/app.js", base)
    script = projected.body.decode("utf-8")

    assert "const projectItems=()=>{" in script
    assert "FieldoraModuleContracts?.resolve?.('projects.list.read')" in script
    assert "const homeProjects=allowed('projects')?projectItems():[];" in script
    assert "metrics.push(['Projects',homeProjects.length])" in script
    assert "cards('home-projects',homeProjects" in script
    assert "metrics.push(['Projects',projects.length])" not in script
    assert "cards('home-projects',projects" not in script

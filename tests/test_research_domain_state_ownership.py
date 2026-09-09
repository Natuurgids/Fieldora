from __future__ import annotations

from natureai_next.server.api import ApiResponse
from natureai_next.server.research_records_web import patch_research_records_response


def test_research_records_owns_active_domain_state_and_rebinds_legacy_controls() -> None:
    legacy_handler = (
        'document.querySelectorAll("[data-research-domain]").forEach('
        'b=>b.onclick=()=>{researchDomain=b.dataset.researchDomain;loadResearchDomain()});'
    )
    response = ApiResponse(
        200,
        ('let researchDomain="specimens";' + legacy_handler).encode(),
        "text/javascript; charset=utf-8",
    )

    script = patch_research_records_response("/app.js", response).body.decode("utf-8")
    legacy, managed = script.split("WEB-042: Research records use server-owned identity and revisions.", 1)

    assert legacy_handler in legacy
    assert 'let researchDomain=document.querySelector("[data-research-domain].primary")?.dataset.researchDomain||"specimens";' in managed
    assert 'button.onclick=()=>{researchDomain=button.dataset.researchDomain||"specimens";' in managed
    assert 'item.classList.toggle("primary",item===button)' in managed
    assert "clearEditor();loadResearchDomain()" in managed
    assert 'button.addEventListener("click"' not in managed

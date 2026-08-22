from pathlib import Path

from natureai_next.server.help import SERVER_HELP_TOPICS, help_topic


ROOT = Path(__file__).parents[1]
HTML = (ROOT / "src/natureai_next/resources/server_web/index.html").read_text()
APP = (ROOT / "src/natureai_next/resources/server_web/app.js").read_text()
API = (ROOT / "src/natureai_next/server/api.py").read_text()


def test_every_server_help_topic_resolves_to_packaged_content() -> None:
    for topic in SERVER_HELP_TOPICS:
        resolved = help_topic(topic.topic_id)
        assert resolved is not None
        assert len(resolved["content"]) > 80
        assert "This packaged guide is unavailable." not in resolved["content"]


def test_web_help_navigation_and_f1_are_wired() -> None:
    assert 'data-page="help"' in HTML
    assert 'id="page-help"' in HTML
    assert 'id="context-help"' in HTML
    assert 'e.key==="F1"' in APP and "e.preventDefault()" in APP
    assert "contextHelp()" in APP and 'openHelp(topic)' in APP


def test_help_catalogue_and_topic_endpoints_are_consumed() -> None:
    assert 'route.path == "/api/v1/help"' in API
    assert 'route.path.startswith("/api/v1/help/")' in API
    assert 'api("/api/v1/help")' in APP
    assert "`/api/v1/help/${encodeURIComponent(topicId)}`" in APP


def test_desktop_help_page_and_v5_f1_contexts_are_reachable() -> None:
    application = (ROOT / "src/natureai_next/ui/qt/application.py").read_text()
    help_system = (ROOT / "src/natureai_next/ui/qt/help_system.py").read_text()
    assert '"Help & Guides",\n    )' in application
    assert 'context_help_action.setShortcut(QKeySequence("F1"))' in application
    for workspace in (
        "Library Overview", "Observations Overview", "Research Overview",
        "Knowledge & AI Overview", "Administration Overview", "Help & Guides",
    ):
        assert f'"{workspace}":' in help_system

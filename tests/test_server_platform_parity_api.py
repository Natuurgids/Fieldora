import json
from natureai_next.application.platform_features import parity_payload, registry_payload

def test_server_parity_payload_is_json_serializable():
    assert json.loads(json.dumps(parity_payload()))["feature_count"]>0
    assert json.loads(json.dumps(registry_payload()))["items"]

def test_server_web_contains_platform_parity_surface():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    html=(root/"src/natureai_next/resources/server_web/index.html").read_text()
    js=(root/"src/natureai_next/resources/server_web/app.js").read_text()
    assert 'data-page="platform"' in html
    assert 'id="page-platform"' in html
    assert '/api/v1/platform/features' in js
    assert '/api/v1/platform/parity' in js

import json, os, sqlite3
from pathlib import Path
from natureai_next.application.ai_platform import AIPlatformService


def test_local_provider_allowed_and_remote_default_denied(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELDORA_PROFILE_ROLE','administrator')
    service=AIPlatformService(tmp_path/'science.sqlite3')
    providers={x['code']:x for x in service.providers()}
    assert service.network_decision(providers['lm-studio']).allowed
    remote_id=service.save_provider(code='remote-test',display_name='Remote',provider_type='openai_compatible',endpoint='https://example.invalid/v1',locality='remote',network_required=True,actor_id='admin')
    remote=next(x for x in service.providers() if x['provider_id']==remote_id)
    assert not service.network_decision(remote).allowed


def test_remote_requires_global_enable_and_explicit_approval(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELDORA_PROFILE_ROLE','administrator')
    service=AIPlatformService(tmp_path/'science.sqlite3')
    pid=service.save_provider(code='remote-test',display_name='Remote',provider_type='openai_compatible',endpoint='https://example.invalid/v1',locality='remote',network_required=True,actor_id='admin')
    provider=next(x for x in service.providers() if x['provider_id']==pid)
    service.approve_network(subject_type='provider',subject_id=pid,actor_id='admin',reason='approved test')
    assert not service.network_decision(provider).allowed
    service.set_offline_only(False,'admin')
    assert service.network_decision(provider).allowed


def test_existing_models_seeded_and_lm_studio_model_can_be_added(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELDORA_PROFILE_ROLE','administrator')
    service=AIPlatformService(tmp_path/'science.sqlite3')
    providers={x['code']:x for x in service.providers()}
    existing=[x for x in service.models() if x['model_key']=='existing-fieldora-models']
    assert existing
    model=service.save_model(provider_id=providers['lm-studio']['provider_id'],model_key='hermes-3',display_name='Hermes 3',actor_id='admin')
    assert any(x['model_id']==model for x in service.models())


def test_non_admin_cannot_change_governance(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELDORA_PROFILE_ROLE','viewer')
    service=AIPlatformService(tmp_path/'science.sqlite3')
    try:
        service.set_offline_only(False,'viewer')
    except PermissionError:
        pass
    else:
        raise AssertionError('expected PermissionError')

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body=json.dumps({'data':[{'id':'hermes-test'}]}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'));doc=json.loads(self.rfile.read(length) or b'{}')
        if doc.get('method')=='tools/list':out={'jsonrpc':'2.0','id':doc.get('id'),'result':{'tools':[{'name':'fieldora.search','description':'Search authorized local records','inputSchema':{'type':'object'}}]}}
        elif doc.get('method')=='tools/call':out={'jsonrpc':'2.0','id':doc.get('id'),'result':{'content':[{'type':'text','text':'ok'}]}}
        else:out={'choices':[{'message':{'content':'Hermes local reply'}}]}
        body=json.dumps(out).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass

def _server():
    server=HTTPServer(('127.0.0.1',0),_Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start();return server

def test_local_openai_compatible_chat_and_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv('FIELDORA_PROFILE_ROLE','administrator')
    server=_server()
    try:
        service=AIPlatformService(tmp_path/'science.sqlite3')
        provider=service.save_provider(code='local-chat',display_name='Local Chat',provider_type='openai_compatible',endpoint=f'http://127.0.0.1:{server.server_port}/v1',locality='local',network_required=False,actor_id='admin')
        model=service.save_model(provider_id=provider,model_key='hermes-test',display_name='Hermes Test',actor_id='admin')
        convo=service.create_conversation(title='Test',owner_user_id='admin',provider_id=provider,model_id=model)
        assert service.send_chat(conversation_id=convo,user_text='hello',actor_id='admin')=='Hermes local reply'
        mcp=service.save_mcp_server(code='local-mcp',display_name='Local MCP',transport='http',endpoint_or_command=f'http://127.0.0.1:{server.server_port}/mcp',locality='local',internet_capable=False,actor_id='admin')
        assert service.mcp_tools(mcp)[0]['name']=='fieldora.search'
        assert service.call_mcp_tool(mcp,'fieldora.search',{},'admin')['content'][0]['text']=='ok'
    finally:
        server.shutdown()

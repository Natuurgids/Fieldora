from __future__ import annotations

import json
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


class AIPlatformService:
    """Provider-neutral, offline-first AI and MCP configuration/service layer.

    Existing Fieldora AI pipelines remain untouched. This service owns chat/provider
    configuration only and uses explicit network-policy checks before any outbound call.
    """

    def __init__(self, database: str | Path):
        self.database = str(database)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.database)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys=ON")
        return cx

    def _ensure_schema(self) -> None:
        with self._connect() as cx:
            cx.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_platform_settings(
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    updated_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_providers(
                    provider_id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    endpoint TEXT NOT NULL DEFAULT '',
                    api_key_reference TEXT NOT NULL DEFAULT '',
                    locality TEXT NOT NULL CHECK(locality IN ('local','lan','remote')),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    network_required INTEGER NOT NULL DEFAULT 0,
                    allow_streaming INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,
                    updated_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_models_catalog(
                    model_id TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL REFERENCES ai_providers(provider_id),
                    model_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    context_length INTEGER,
                    multimodal INTEGER NOT NULL DEFAULT 0,
                    tool_capable INTEGER NOT NULL DEFAULT 0,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(provider_id,model_key)
                );
                CREATE TABLE IF NOT EXISTS ai_mcp_servers(
                    server_id TEXT PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    transport TEXT NOT NULL CHECK(transport IN ('http','stdio')),
                    endpoint_or_command TEXT NOT NULL,
                    locality TEXT NOT NULL CHECK(locality IN ('local','lan','remote')),
                    enabled INTEGER NOT NULL DEFAULT 1,
                    internet_capable INTEGER NOT NULL DEFAULT 0,
                    allowed_tools_json TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,
                    updated_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_network_approvals(
                    approval_id TEXT PRIMARY KEY,
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    purpose_code TEXT NOT NULL DEFAULT '',
                    max_sensitivity TEXT NOT NULL DEFAULT 'public',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    valid_until_us INTEGER,
                    approved_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_conversations(
                    conversation_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    project_id TEXT NOT NULL DEFAULT '',
                    provider_id TEXT NOT NULL REFERENCES ai_providers(provider_id),
                    model_id TEXT NOT NULL REFERENCES ai_models_catalog(model_id),
                    purpose_code TEXT NOT NULL DEFAULT 'scientific_research',
                    created_at_us INTEGER NOT NULL,
                    updated_at_us INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ai_messages(
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES ai_conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('system','user','assistant','tool')),
                    content TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at_us INTEGER NOT NULL,
                    provider_code TEXT NOT NULL DEFAULT '',
                    model_key TEXT NOT NULL DEFAULT '',
                    network_mode TEXT NOT NULL DEFAULT 'offline',
                    tool_calls_json TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS ai_platform_audit(
                    audit_id TEXT PRIMARY KEY,
                    occurred_at_us INTEGER NOT NULL,
                    actor_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
                """
            )
            now = self._now()
            cx.execute(
                "INSERT OR IGNORE INTO ai_platform_settings(key,value_json,updated_by,updated_at_us) VALUES('offline_only','true','system',?)",
                (now,),
            )
            # Existing Fieldora/native models remain represented and available.
            self._seed_provider(cx, 'fieldora-native', 'Fieldora native AI', 'native', '', 'local', False, 'system')
            self._seed_provider(cx, 'lm-studio', 'LM Studio', 'openai_compatible', 'http://127.0.0.1:1234/v1', 'local', False, 'system')
            self._seed_provider(cx, 'ollama', 'Ollama', 'openai_compatible', 'http://127.0.0.1:11434/v1', 'local', False, 'system')
            self._seed_model(cx, 'fieldora-native', 'existing-fieldora-models', 'Existing Fieldora models', False, False)
            cx.commit()

    @staticmethod
    def _now() -> int:
        return time.time_ns() // 1000

    def _seed_provider(self, cx: sqlite3.Connection, code: str, name: str, provider_type: str, endpoint: str, locality: str, network_required: bool, actor: str) -> str:
        row = cx.execute("SELECT provider_id FROM ai_providers WHERE code=?", (code,)).fetchone()
        if row:
            return str(row[0])
        identity = str(uuid.uuid4())
        now = self._now()
        cx.execute(
            "INSERT INTO ai_providers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (identity, code, name, provider_type, endpoint, '', locality, 1, int(network_required), 1, actor, now, now),
        )
        return identity

    def _seed_model(self, cx: sqlite3.Connection, provider_code: str, key: str, name: str, multimodal: bool, tools: bool) -> str:
        provider = cx.execute("SELECT provider_id FROM ai_providers WHERE code=?", (provider_code,)).fetchone()
        assert provider is not None
        row = cx.execute("SELECT model_id FROM ai_models_catalog WHERE provider_id=? AND model_key=?", (provider[0], key)).fetchone()
        if row:
            return str(row[0])
        identity = str(uuid.uuid4())
        cx.execute("INSERT INTO ai_models_catalog VALUES(?,?,?,?,?,?,?,1)", (identity, provider[0], key, name, None, int(multimodal), int(tools)))
        return identity

    def _audit(self, cx: sqlite3.Connection, actor: str, event: str, entity_type: str, entity_id: str, details: dict[str, Any]) -> None:
        cx.execute(
            "INSERT INTO ai_platform_audit VALUES(?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), self._now(), actor, event, entity_type, entity_id, json.dumps(details, sort_keys=True)),
        )

    def offline_only(self) -> bool:
        with self._connect() as cx:
            row = cx.execute("SELECT value_json FROM ai_platform_settings WHERE key='offline_only'").fetchone()
        return True if row is None else bool(json.loads(str(row[0])))

    def set_offline_only(self, enabled: bool, actor_id: str) -> None:
        self._require_admin()
        with self._connect() as cx:
            cx.execute("INSERT OR REPLACE INTO ai_platform_settings VALUES('offline_only',?,?,?)", (json.dumps(bool(enabled)), actor_id, self._now()))
            self._audit(cx, actor_id, 'ai.network_policy.updated', 'setting', 'offline_only', {'enabled': bool(enabled)})
            cx.commit()

    @staticmethod
    def _require_admin() -> None:
        import os
        if os.environ.get('FIELDORA_PROFILE_ROLE') != 'administrator':
            raise PermissionError('Administrator permission required')

    def providers(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM ai_providers" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY display_name"
        with self._connect() as cx:
            return [dict(x) for x in cx.execute(sql)]

    def models(self, provider_id: str | None = None, enabled_only: bool = False) -> list[dict[str, Any]]:
        where, args = [], []
        if provider_id:
            where.append('m.provider_id=?'); args.append(provider_id)
        if enabled_only:
            where.append('m.enabled=1 AND p.enabled=1')
        sql = "SELECT m.*,p.code provider_code,p.display_name provider_name,p.locality,p.endpoint,p.network_required FROM ai_models_catalog m JOIN ai_providers p ON p.provider_id=m.provider_id"
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.display_name,m.display_name"
        with self._connect() as cx:
            return [dict(x) for x in cx.execute(sql, args)]

    def save_provider(self, *, code: str, display_name: str, provider_type: str, endpoint: str, locality: str, network_required: bool, actor_id: str, enabled: bool = True) -> str:
        self._require_admin()
        if locality not in {'local','lan','remote'}: raise ValueError('invalid locality')
        with self._connect() as cx:
            row = cx.execute("SELECT provider_id FROM ai_providers WHERE code=?", (code.strip(),)).fetchone()
            identity = str(row[0]) if row else str(uuid.uuid4()); now=self._now()
            if row:
                cx.execute("UPDATE ai_providers SET display_name=?,provider_type=?,endpoint=?,locality=?,network_required=?,enabled=?,updated_at_us=? WHERE provider_id=?", (display_name,provider_type,endpoint,locality,int(network_required),int(enabled),now,identity))
            else:
                cx.execute("INSERT INTO ai_providers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (identity,code,display_name,provider_type,endpoint,'',locality,int(enabled),int(network_required),1,actor_id,now,now))
            self._audit(cx, actor_id, 'ai.provider.saved', 'provider', identity, {'code':code,'locality':locality})
            cx.commit(); return identity

    def save_model(self, *, provider_id: str, model_key: str, display_name: str, actor_id: str, context_length: int | None = None, multimodal: bool = False, tool_capable: bool = False, enabled: bool = True) -> str:
        self._require_admin()
        with self._connect() as cx:
            row=cx.execute("SELECT model_id FROM ai_models_catalog WHERE provider_id=? AND model_key=?",(provider_id,model_key)).fetchone(); identity=str(row[0]) if row else str(uuid.uuid4())
            if row:cx.execute("UPDATE ai_models_catalog SET display_name=?,context_length=?,multimodal=?,tool_capable=?,enabled=? WHERE model_id=?",(display_name,context_length,int(multimodal),int(tool_capable),int(enabled),identity))
            else:cx.execute("INSERT INTO ai_models_catalog VALUES(?,?,?,?,?,?,?,?)",(identity,provider_id,model_key,display_name,context_length,int(multimodal),int(tool_capable),int(enabled)))
            self._audit(cx,actor_id,'ai.model.saved','model',identity,{'model_key':model_key});cx.commit();return identity

    def mcp_servers(self) -> list[dict[str, Any]]:
        with self._connect() as cx:return [dict(x) for x in cx.execute("SELECT * FROM ai_mcp_servers ORDER BY display_name")]

    def save_mcp_server(self, *, code: str, display_name: str, transport: str, endpoint_or_command: str, locality: str, internet_capable: bool, actor_id: str, enabled: bool = True) -> str:
        self._require_admin()
        with self._connect() as cx:
            row=cx.execute("SELECT server_id FROM ai_mcp_servers WHERE code=?",(code,)).fetchone();identity=str(row[0]) if row else str(uuid.uuid4());now=self._now()
            if row:cx.execute("UPDATE ai_mcp_servers SET display_name=?,transport=?,endpoint_or_command=?,locality=?,internet_capable=?,enabled=?,updated_at_us=? WHERE server_id=?",(display_name,transport,endpoint_or_command,locality,int(internet_capable),int(enabled),now,identity))
            else:cx.execute("INSERT INTO ai_mcp_servers VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(identity,code,display_name,transport,endpoint_or_command,locality,int(enabled),int(internet_capable),'[]',actor_id,now,now))
            self._audit(cx,actor_id,'ai.mcp.saved','mcp_server',identity,{'code':code});cx.commit();return identity

    def approve_network(self, *, subject_type: str, subject_id: str, actor_id: str, reason: str, project_id: str = '', purpose_code: str = '', max_sensitivity: str = 'public', valid_until_us: int | None = None) -> str:
        self._require_admin();identity=str(uuid.uuid4())
        with self._connect() as cx:
            cx.execute("INSERT INTO ai_network_approvals VALUES(?,?,?,?,?,?,?,?,?,?,?)",(identity,subject_type,subject_id,project_id,purpose_code,max_sensitivity,1,valid_until_us,actor_id,reason,self._now()))
            self._audit(cx,actor_id,'ai.network.approved',subject_type,subject_id,{'approval_id':identity,'reason':reason});cx.commit()
        return identity

    def network_decision(self, provider: dict[str, Any], *, project_id: str = '', purpose_code: str = '', sensitivity: str = 'public') -> AccessDecision:
        if provider['locality'] == 'local' and not provider['network_required']:
            return AccessDecision(True, 'local provider; no external network required')
        if self.offline_only():
            return AccessDecision(False, 'global offline-only mode blocks LAN and internet providers')
        now=self._now()
        with self._connect() as cx:
            rows=cx.execute("SELECT * FROM ai_network_approvals WHERE enabled=1 AND subject_type='provider' AND subject_id=? AND (valid_until_us IS NULL OR valid_until_us>?)",(provider['provider_id'],now)).fetchall()
        for row in rows:
            if row['project_id'] and row['project_id'] != project_id: continue
            if row['purpose_code'] and row['purpose_code'] != purpose_code: continue
            return AccessDecision(True, f"approved by {row['approved_by']}: {row['reason']}")
        return AccessDecision(False, 'no active administrator network approval for this provider/context')

    def mcp_tools(self, server_id: str) -> list[dict[str, Any]]:
        server = next((x for x in self.mcp_servers() if x["server_id"] == server_id), None)
        if server is None:
            raise KeyError(server_id)
        if not server["enabled"]:
            return []
        if server["locality"] != "local" or server["internet_capable"]:
            if self.offline_only():
                raise PermissionError("global offline-only mode blocks this MCP server")
        if server["transport"] != "http":
            return []
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode("utf-8")
        request = urllib.request.Request(str(server["endpoint_or_command"]), data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                document = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(f"MCP server unavailable: {exc}") from exc
        tools = document.get("result", {}).get("tools", [])
        if not isinstance(tools, list):
            raise RuntimeError("MCP server returned an invalid tools/list response")
        with self._connect() as cx:
            cx.execute("UPDATE ai_mcp_servers SET allowed_tools_json=?,updated_at_us=? WHERE server_id=?", (json.dumps([str(x.get('name','')) for x in tools]), self._now(), server_id))
            cx.commit()
        return [dict(x) for x in tools if isinstance(x, dict)]

    def call_mcp_tool(self, server_id: str, tool_name: str, arguments: dict[str, Any], actor_id: str) -> Any:
        server = next((x for x in self.mcp_servers() if x["server_id"] == server_id), None)
        if server is None:
            raise KeyError(server_id)
        if server["locality"] != "local" or server["internet_capable"]:
            if self.offline_only():
                raise PermissionError("global offline-only mode blocks this MCP tool")
        if server["transport"] != "http":
            raise NotImplementedError("stdio MCP execution is configured but not launched by the desktop client")
        payload = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool_name, "arguments": arguments}}).encode("utf-8")
        request = urllib.request.Request(str(server["endpoint_or_command"]), data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                document = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ConnectionError(f"MCP server unavailable: {exc}") from exc
        if "error" in document:
            raise RuntimeError(str(document["error"]))
        with self._connect() as cx:
            self._audit(cx, actor_id, "ai.mcp.tool.called", "mcp_server", server_id, {"tool": tool_name})
            cx.commit()
        return document.get("result")

    def create_conversation(self, *, title: str, owner_user_id: str, provider_id: str, model_id: str, project_id: str = '', purpose_code: str = 'scientific_research') -> str:
        identity=str(uuid.uuid4());now=self._now()
        with self._connect() as cx:
            cx.execute("INSERT INTO ai_conversations VALUES(?,?,?,?,?,?,?,?,?)",(identity,title,owner_user_id,project_id,provider_id,model_id,purpose_code,now,now));self._audit(cx,owner_user_id,'ai.conversation.created','conversation',identity,{'title':title});cx.commit()
        return identity

    def conversations(self, owner_user_id: str) -> list[dict[str, Any]]:
        with self._connect() as cx:return [dict(x) for x in cx.execute("SELECT c.*,p.display_name provider_name,m.display_name model_name FROM ai_conversations c JOIN ai_providers p ON p.provider_id=c.provider_id JOIN ai_models_catalog m ON m.model_id=c.model_id WHERE owner_user_id=? ORDER BY updated_at_us DESC",(owner_user_id,))]

    def messages(self, conversation_id: str) -> list[dict[str, Any]]:
        with self._connect() as cx:return [dict(x) for x in cx.execute("SELECT * FROM ai_messages WHERE conversation_id=? ORDER BY created_at_us",(conversation_id,))]

    def _store_message(self, cx: sqlite3.Connection, conversation_id: str, role: str, content: str, actor: str, provider_code: str = '', model_key: str = '', network_mode: str = 'offline') -> str:
        identity=str(uuid.uuid4());cx.execute("INSERT INTO ai_messages VALUES(?,?,?,?,?,?,?,?,?,?)",(identity,conversation_id,role,content,actor,self._now(),provider_code,model_key,network_mode,'[]'));cx.execute("UPDATE ai_conversations SET updated_at_us=? WHERE conversation_id=?",(self._now(),conversation_id));return identity

    def send_chat(self, *, conversation_id: str, user_text: str, actor_id: str, context: dict[str, Any] | None = None) -> str:
        if not user_text.strip(): raise ValueError('message is required')
        with self._connect() as cx:
            convo=cx.execute("SELECT c.*,p.*,m.model_key FROM ai_conversations c JOIN ai_providers p ON p.provider_id=c.provider_id JOIN ai_models_catalog m ON m.model_id=c.model_id WHERE c.conversation_id=?",(conversation_id,)).fetchone()
            if convo is None: raise KeyError(conversation_id)
            provider=dict(convo);decision=self.network_decision(provider,project_id=str(convo['project_id']),purpose_code=str(convo['purpose_code']))
            if not decision.allowed: raise PermissionError(decision.reason)
            prior=[dict(x) for x in cx.execute("SELECT role,content FROM ai_messages WHERE conversation_id=? ORDER BY created_at_us",(conversation_id,))]
            self._store_message(cx,conversation_id,'user',user_text,actor_id,str(convo['code']),str(convo['model_key']),'offline' if provider['locality']=='local' else 'approved-network')
            cx.commit()
        if provider['provider_type']=='native':
            answer='Existing Fieldora AI models remain available through their current workflows. Select a conversational provider/model for free-form chat.'
        else:
            messages=[]
            if context: messages.append({'role':'system','content':'Fieldora context (authorized fields only): '+json.dumps(context,sort_keys=True)})
            messages.extend(prior);messages.append({'role':'user','content':user_text})
            answer=self._openai_chat(str(provider['endpoint']),str(convo['model_key']),messages)
        with self._connect() as cx:
            self._store_message(cx,conversation_id,'assistant',answer,actor_id,str(provider['code']),str(convo['model_key']),'offline' if provider['locality']=='local' else 'approved-network')
            self._audit(cx,actor_id,'ai.chat.completed','conversation',conversation_id,{'provider':provider['code'],'model':convo['model_key'],'network_reason':decision.reason});cx.commit()
        return answer

    @staticmethod
    def _openai_chat(endpoint: str, model: str, messages: list[dict[str, str]]) -> str:
        url=endpoint.rstrip('/')+'/chat/completions';payload=json.dumps({'model':model,'messages':messages,'stream':False}).encode('utf-8')
        request=urllib.request.Request(url,data=payload,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=60) as response:data=json.loads(response.read().decode('utf-8'))
        except urllib.error.URLError as exc:raise ConnectionError(f'AI provider unavailable: {exc}') from exc
        try:return str(data['choices'][0]['message']['content'])
        except Exception as exc:raise RuntimeError('provider returned an invalid chat response') from exc

    def test_provider(self, provider_id: str) -> str:
        provider=next((x for x in self.providers() if x['provider_id']==provider_id),None)
        if provider is None:raise KeyError(provider_id)
        decision=self.network_decision(provider)
        if not decision.allowed:raise PermissionError(decision.reason)
        if provider['provider_type']=='native':return 'Native Fieldora AI is available through existing workflows.'
        url=str(provider['endpoint']).rstrip('/')+'/models'
        try:
            with urllib.request.urlopen(url,timeout=5) as response:return f"Connected ({response.status})"
        except urllib.error.URLError as exc:raise ConnectionError(str(exc)) from exc

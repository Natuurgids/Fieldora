from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _id() -> str:
    return str(uuid.uuid4())


def _now_us() -> int:
    return int(datetime.now(UTC).timestamp() * 1_000_000)


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    matched_policy_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MatrixDecision:
    allowed: bool
    detail_visible: bool
    aggregate_allowed: bool
    reason: str
    matched_rule_ids: tuple[str, ...] = ()


class Phase4AdministrationService:
    """Governed administration for master data, workflows and enrichment assets.

    The service deliberately shares the Science database so configuration changes,
    scientific records and their audit trail can be backed up and restored together.
    """

    DOMAINS = (
        "roles", "parties", "units", "instruments", "laboratories", "templates",
        "workflow_transitions", "identity_providers", "security_attributes",
        "purposes", "asset_policies", "access_matrices",
    )

    def __init__(self, database: str | Path):
        self.database = Path(database)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self.database)
        cx.row_factory = sqlite3.Row
        cx.execute("PRAGMA foreign_keys=ON")
        return cx

    def _initialize(self) -> None:
        with self._connect() as cx:
            cx.executescript(
                """
                CREATE TABLE IF NOT EXISTS adm_roles(
                  role_id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '', scope TEXT NOT NULL DEFAULT 'organisation',
                  active INTEGER NOT NULL DEFAULT 1, system_value INTEGER NOT NULL DEFAULT 0,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_role_permissions(
                  role_id TEXT NOT NULL REFERENCES adm_roles(role_id) ON DELETE CASCADE,
                  permission_code TEXT NOT NULL, PRIMARY KEY(role_id,permission_code));
                CREATE TABLE IF NOT EXISTS adm_parties(
                  party_id TEXT PRIMARY KEY, party_type TEXT NOT NULL, display_name TEXT NOT NULL,
                  organisation_id TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
                  address TEXT NOT NULL DEFAULT '', external_identifier TEXT NOT NULL DEFAULT '',
                  accreditation TEXT NOT NULL DEFAULT '', linked_identity_id TEXT NOT NULL DEFAULT '',
                  active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
                  created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_units(
                  unit_id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, symbol TEXT NOT NULL, display_name TEXT NOT NULL,
                  quantity_kind TEXT NOT NULL, factor REAL NOT NULL DEFAULT 1, offset REAL NOT NULL DEFAULT 0,
                  precision_digits INTEGER NOT NULL DEFAULT 3, active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_instruments(
                  instrument_id TEXT PRIMARY KEY, name TEXT NOT NULL, instrument_type TEXT NOT NULL,
                  manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '', serial_number TEXT NOT NULL DEFAULT '',
                  owner_party_id TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
                  calibration_interval_days INTEGER, active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_instrument_calibrations(
                  calibration_id TEXT PRIMARY KEY, instrument_id TEXT NOT NULL REFERENCES adm_instruments(instrument_id),
                  calibrated_at TEXT NOT NULL, calibrated_by_user TEXT NOT NULL, calibrated_by_party_id TEXT NOT NULL DEFAULT '',
                  result TEXT NOT NULL, certificate_asset_id TEXT NOT NULL DEFAULT '', next_due TEXT NOT NULL DEFAULT '',
                  notes TEXT NOT NULL DEFAULT '', created_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_laboratories(
                  laboratory_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, party_id TEXT NOT NULL DEFAULT '',
                  address TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '', accreditation TEXT NOT NULL DEFAULT '',
                  capabilities_json TEXT NOT NULL DEFAULT '[]', integration_id TEXT NOT NULL DEFAULT '',
                  active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
                  created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_templates(
                  template_id TEXT PRIMARY KEY, template_type TEXT NOT NULL, code TEXT NOT NULL,
                  display_name TEXT NOT NULL, taxon_rule TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'draft',
                  version INTEGER NOT NULL DEFAULT 1, definition_json TEXT NOT NULL DEFAULT '{}',
                  owner_organisation_id TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL,
                  UNIQUE(template_type,code,version));
                CREATE TABLE IF NOT EXISTS adm_workflow_transitions(
                  transition_id TEXT PRIMARY KEY, domain TEXT NOT NULL, from_status TEXT NOT NULL,
                  to_status TEXT NOT NULL, required_role TEXT NOT NULL DEFAULT '', required_permission TEXT NOT NULL DEFAULT '',
                  requires_reason INTEGER NOT NULL DEFAULT 0, requires_approval INTEGER NOT NULL DEFAULT 0,
                  terminal INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL,
                  UNIQUE(domain,from_status,to_status));
                CREATE TABLE IF NOT EXISTS adm_identity_providers(
                  provider_id TEXT PRIMARY KEY, provider_type TEXT NOT NULL, display_name TEXT NOT NULL,
                  issuer TEXT NOT NULL DEFAULT '', metadata_url TEXT NOT NULL DEFAULT '', client_id TEXT NOT NULL DEFAULT '',
                  secret_reference TEXT NOT NULL DEFAULT '', claim_mapping_json TEXT NOT NULL DEFAULT '{}',
                  group_mapping_json TEXT NOT NULL DEFAULT '{}', jit_provisioning INTEGER NOT NULL DEFAULT 0,
                  enabled INTEGER NOT NULL DEFAULT 0, created_by TEXT NOT NULL,
                  created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_security_attributes(
                  attribute_id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                  value_type TEXT NOT NULL DEFAULT 'choice', allowed_values_json TEXT NOT NULL DEFAULT '[]',
                  default_value TEXT NOT NULL DEFAULT '', required_for_json TEXT NOT NULL DEFAULT '[]',
                  inheritance_mode TEXT NOT NULL DEFAULT 'most_restrictive', active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_purposes(
                  purpose_id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                  description TEXT NOT NULL DEFAULT '', legal_basis TEXT NOT NULL DEFAULT '',
                  requires_selection INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_asset_policies(
                  policy_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, effect TEXT NOT NULL,
                  role_code TEXT NOT NULL DEFAULT '', action_code TEXT NOT NULL,
                  asset_type TEXT NOT NULL DEFAULT '*', purpose_code TEXT NOT NULL DEFAULT '*',
                  organisation_id TEXT NOT NULL DEFAULT '', project_id TEXT NOT NULL DEFAULT '',
                  conditions_json TEXT NOT NULL DEFAULT '{}', priority INTEGER NOT NULL DEFAULT 100,
                  state TEXT NOT NULL DEFAULT 'draft', valid_from TEXT NOT NULL DEFAULT '', valid_until TEXT NOT NULL DEFAULT '',
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_asset_security(
                  asset_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, organisation_id TEXT NOT NULL DEFAULT '',
                  project_id TEXT NOT NULL DEFAULT '', sensitivity TEXT NOT NULL DEFAULT 'internal',
                  classifications_json TEXT NOT NULL DEFAULT '{}', permitted_purposes_json TEXT NOT NULL DEFAULT '[]',
                  embargo_until TEXT NOT NULL DEFAULT '', licence TEXT NOT NULL DEFAULT '', consent_state TEXT NOT NULL DEFAULT '',
                  retention_class TEXT NOT NULL DEFAULT '', residency TEXT NOT NULL DEFAULT '', source_asset_id TEXT NOT NULL DEFAULT '',
                  updated_by TEXT NOT NULL, updated_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_audit(
                  audit_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, event_type TEXT NOT NULL,
                  entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, before_json TEXT NOT NULL DEFAULT '{}',
                  after_json TEXT NOT NULL DEFAULT '{}', reason TEXT NOT NULL DEFAULT '', created_at_us INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS adm_access_matrices(
                  rule_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, principal_type TEXT NOT NULL DEFAULT 'role',
                  principal_id TEXT NOT NULL DEFAULT '', resource_type TEXT NOT NULL, project_id TEXT NOT NULL DEFAULT '',
                  team_id TEXT NOT NULL DEFAULT '', data_scope TEXT NOT NULL DEFAULT 'project',
                  representation TEXT NOT NULL DEFAULT 'individual', create_allowed INTEGER NOT NULL DEFAULT 0,
                  read_allowed INTEGER NOT NULL DEFAULT 0, update_allowed INTEGER NOT NULL DEFAULT 0,
                  delete_allowed INTEGER NOT NULL DEFAULT 0, assign_allowed INTEGER NOT NULL DEFAULT 0,
                  review_allowed INTEGER NOT NULL DEFAULT 0, approve_allowed INTEGER NOT NULL DEFAULT 0,
                  export_allowed INTEGER NOT NULL DEFAULT 0, publish_allowed INTEGER NOT NULL DEFAULT 0,
                  aggregate_allowed INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
                  created_by TEXT NOT NULL, created_at_us INTEGER NOT NULL, updated_at_us INTEGER NOT NULL);
                """
            )
            self._seed(cx)

    def _seed(self, cx: sqlite3.Connection) -> None:
        now = _now_us()
        roles = {
            "viewer": ("Viewer", ("asset.metadata.view", "asset.preview.view")),
            "researcher": ("Researcher", ("asset.metadata.view", "asset.preview.view", "asset.original.view", "asset.upload", "asset.annotate")),
            "principal_investigator": ("Principal investigator", ("asset.metadata.view", "asset.preview.view", "asset.original.view", "asset.upload", "asset.annotate", "asset.export", "asset.classify")),
            "administrator": ("Administrator", ("*",)),
        }
        for code, (name, permissions) in roles.items():
            row = cx.execute("SELECT role_id FROM adm_roles WHERE code=?", (code,)).fetchone()
            if row: continue
            rid = _id(); cx.execute("INSERT INTO adm_roles VALUES(?,?,?,?,?,?,?,?,?,?)", (rid,code,name,"System role","system",1,1,"system",now,now))
            cx.executemany("INSERT INTO adm_role_permissions VALUES(?,?)", ((rid,p) for p in permissions))
        for code,name in (("scientific_research","Scientific research"),("laboratory_diagnosis","Laboratory diagnosis"),("publication","Publication"),("public_portal","Public portal"),("ai_inference","AI inference"),("ai_training","AI training")):
            if not cx.execute("SELECT 1 FROM adm_purposes WHERE code=?",(code,)).fetchone():
                cx.execute("INSERT INTO adm_purposes VALUES(?,?,?,?,?,?,?,?,?,?)",(_id(),code,name,"","",1,1,"system",now,now))
        for code,name,values in (("sensitivity","Sensitivity",["public","internal","protected","restricted"]),("contains_exact_location","Contains exact location",["no","yes"]),("contains_people","Contains people",["no","yes"]),("ai_use","AI use",["prohibited","inference_only","training_allowed"])):
            if not cx.execute("SELECT 1 FROM adm_security_attributes WHERE code=?",(code,)).fetchone():
                cx.execute("INSERT INTO adm_security_attributes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(_id(),code,name,"choice",json.dumps(values),values[0],"[]","most_restrictive",1,"system",now,now))
        for code,symbol,name,kind,factor in (("mm","mm","millimetre","length",0.001),("cm","cm","centimetre","length",0.01),("m","m","metre","length",1.0),("g","g","gram","mass",0.001),("kg","kg","kilogram","mass",1.0)):
            if not cx.execute("SELECT 1 FROM adm_units WHERE code=?",(code,)).fetchone():
                cx.execute("INSERT INTO adm_units VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(_id(),code,symbol,name,kind,factor,0,3,1,"system",now,now))

    def _require_admin(self, actor_id: str) -> None:
        import os
        if actor_id == "local-user" or os.environ.get("FIELDORA_PROFILE_ROLE") == "administrator": return
        with self._connect() as cx:
            if cx.execute("SELECT 1 FROM pm_project_members WHERE user_id=? AND role='admin' LIMIT 1", (actor_id,)).fetchone(): return
        raise PermissionError("administrator permission is required")

    def _audit(self, cx: sqlite3.Connection, actor: str, event: str, entity_type: str, entity_id: str, before: Any = None, after: Any = None, reason: str = "") -> None:
        cx.execute("INSERT INTO adm_audit VALUES(?,?,?,?,?,?,?,?,?)",(_id(),actor,event,entity_type,entity_id,json.dumps(before or {},sort_keys=True),json.dumps(after or {},sort_keys=True),reason,_now_us()))

    def list_domain(self, domain: str) -> tuple[dict[str, Any], ...]:
        mapping = {
            "roles": "SELECT r.*,group_concat(p.permission_code, ', ') permissions FROM adm_roles r LEFT JOIN adm_role_permissions p ON p.role_id=r.role_id GROUP BY r.role_id ORDER BY r.display_name",
            "parties": "SELECT * FROM adm_parties ORDER BY display_name",
            "units": "SELECT * FROM adm_units ORDER BY quantity_kind,display_name",
            "instruments": "SELECT * FROM adm_instruments ORDER BY name",
            "laboratories": "SELECT * FROM adm_laboratories ORDER BY display_name",
            "templates": "SELECT * FROM adm_templates ORDER BY template_type,display_name,version DESC",
            "workflow_transitions": "SELECT * FROM adm_workflow_transitions ORDER BY domain,from_status,to_status",
            "identity_providers": "SELECT * FROM adm_identity_providers ORDER BY display_name",
            "security_attributes": "SELECT * FROM adm_security_attributes ORDER BY display_name",
            "purposes": "SELECT * FROM adm_purposes ORDER BY display_name",
            "asset_policies": "SELECT * FROM adm_asset_policies ORDER BY priority,display_name",
            "access_matrices": "SELECT * FROM adm_access_matrices ORDER BY resource_type,project_id,principal_type,principal_id,display_name",
        }
        if domain not in mapping: raise KeyError(domain)
        with self._connect() as cx: return tuple(dict(x) for x in cx.execute(mapping[domain]).fetchall())

    def save(self, domain: str, values: dict[str, Any], *, actor_id: str, reason: str = "") -> str:
        self._require_admin(actor_id); now=_now_us()
        specs = {
            "parties": ("adm_parties",("party_id","party_type","display_name","organisation_id","email","phone","address","external_identifier","accreditation","linked_identity_id","active","created_by","created_at_us","updated_at_us"),(lambda v:(v.get("party_type","organisation"),v["display_name"],v.get("organisation_id",""),v.get("email",""),v.get("phone",""),v.get("address",""),v.get("external_identifier",""),v.get("accreditation",""),v.get("linked_identity_id",""),int(v.get("active",1))))),
            "units": ("adm_units",("unit_id","code","symbol","display_name","quantity_kind","factor","offset","precision_digits","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["code"],v.get("symbol",v["code"]),v["display_name"],v["quantity_kind"],float(v.get("factor",1)),float(v.get("offset",0)),int(v.get("precision_digits",3)),int(v.get("active",1))))),
            "instruments": ("adm_instruments",("instrument_id","name","instrument_type","manufacturer","model","serial_number","owner_party_id","location","status","calibration_interval_days","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["name"],v["instrument_type"],v.get("manufacturer",""),v.get("model",""),v.get("serial_number",""),v.get("owner_party_id",""),v.get("location",""),v.get("status","active"),v.get("calibration_interval_days"),int(v.get("active",1))))),
            "laboratories": ("adm_laboratories",("laboratory_id","display_name","party_id","address","contact","accreditation","capabilities_json","integration_id","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["display_name"],v.get("party_id",""),v.get("address",""),v.get("contact",""),v.get("accreditation",""),json.dumps(v.get("capabilities",[])),v.get("integration_id",""),int(v.get("active",1))))),
            "templates": ("adm_templates",("template_id","template_type","code","display_name","taxon_rule","state","version","definition_json","owner_organisation_id","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["template_type"],v["code"],v["display_name"],v.get("taxon_rule",""),v.get("state","draft"),int(v.get("version",1)),json.dumps(v.get("definition",{})),v.get("owner_organisation_id",""),int(v.get("active",1))))),
            "workflow_transitions": ("adm_workflow_transitions",("transition_id","domain","from_status","to_status","required_role","required_permission","requires_reason","requires_approval","terminal","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["domain"],v["from_status"],v["to_status"],v.get("required_role",""),v.get("required_permission",""),int(v.get("requires_reason",0)),int(v.get("requires_approval",0)),int(v.get("terminal",0)),int(v.get("active",1))))),
            "identity_providers": ("adm_identity_providers",("provider_id","provider_type","display_name","issuer","metadata_url","client_id","secret_reference","claim_mapping_json","group_mapping_json","jit_provisioning","enabled","created_by","created_at_us","updated_at_us"),(lambda v:(v["provider_type"],v["display_name"],v.get("issuer",""),v.get("metadata_url",""),v.get("client_id",""),v.get("secret_reference",""),json.dumps(v.get("claim_mapping",{})),json.dumps(v.get("group_mapping",{})),int(v.get("jit_provisioning",0)),int(v.get("enabled",0))))),
            "security_attributes": ("adm_security_attributes",("attribute_id","code","display_name","value_type","allowed_values_json","default_value","required_for_json","inheritance_mode","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["code"],v["display_name"],v.get("value_type","choice"),json.dumps(v.get("allowed_values",[])),v.get("default_value",""),json.dumps(v.get("required_for",[])),v.get("inheritance_mode","most_restrictive"),int(v.get("active",1))))),
            "purposes": ("adm_purposes",("purpose_id","code","display_name","description","legal_basis","requires_selection","active","created_by","created_at_us","updated_at_us"),(lambda v:(v["code"],v["display_name"],v.get("description",""),v.get("legal_basis",""),int(v.get("requires_selection",1)),int(v.get("active",1))))),
            "asset_policies": ("adm_asset_policies",("policy_id","display_name","effect","role_code","action_code","asset_type","purpose_code","organisation_id","project_id","conditions_json","priority","state","valid_from","valid_until","created_by","created_at_us","updated_at_us"),(lambda v:(v["display_name"],v.get("effect","deny"),v.get("role_code",""),v["action_code"],v.get("asset_type","*"),v.get("purpose_code","*"),v.get("organisation_id",""),v.get("project_id",""),json.dumps(v.get("conditions",{})),int(v.get("priority",100)),v.get("state","draft"),v.get("valid_from",""),v.get("valid_until","")))),
        }
        if domain not in specs: raise KeyError(domain)
        table, columns, payload_factory=specs[domain]; payload=payload_factory(values); identity=str(values.get(columns[0]) or _id())
        if any(v is None for v in payload): pass
        with self._connect() as cx:
            before=dict(cx.execute(f"SELECT * FROM {table} WHERE {columns[0]}=?",(identity,)).fetchone() or {})
            vals=(identity,*payload,actor_id,now,now)
            placeholders=','.join('?' for _ in columns)
            cx.execute(f"INSERT OR REPLACE INTO {table}({','.join(columns)}) VALUES({placeholders})",vals)
            after=dict(cx.execute(f"SELECT * FROM {table} WHERE {columns[0]}=?",(identity,)).fetchone())
            self._audit(cx,actor_id,"administration.saved",domain,identity,before,after,reason)
        return identity

    def save_role(self, *, code: str, display_name: str, permissions: list[str], actor_id: str, description: str = "", scope: str = "organisation", active: bool = True) -> str:
        self._require_admin(actor_id); now=_now_us()
        with self._connect() as cx:
            row=cx.execute("SELECT role_id FROM adm_roles WHERE code=?",(code,)).fetchone(); rid=str(row[0]) if row else _id()
            before=dict(cx.execute("SELECT * FROM adm_roles WHERE role_id=?",(rid,)).fetchone() or {})
            cx.execute("INSERT OR REPLACE INTO adm_roles VALUES(?,?,?,?,?,?,?,?,?,?)",(rid,code,display_name,description,scope,int(active),int(before.get('system_value',0)),actor_id,int(before.get('created_at_us',now)),now))
            cx.execute("DELETE FROM adm_role_permissions WHERE role_id=?",(rid,));cx.executemany("INSERT INTO adm_role_permissions VALUES(?,?)",((rid,p.strip()) for p in permissions if p.strip()))
            self._audit(cx,actor_id,"role.saved","role",rid,before,{"code":code,"permissions":permissions})
        return rid

    def save_access_matrix(self, *, actor_id: str, display_name: str, principal_type: str, principal_id: str, resource_type: str, project_id: str = "", team_id: str = "", data_scope: str = "project", representation: str = "individual", permissions: dict[str, bool] | None = None, active: bool = True, rule_id: str = "", reason: str = "") -> str:
        self._require_admin(actor_id)
        if principal_type not in {"user", "role", "team", "all"}: raise ValueError("invalid principal type")
        if data_scope not in {"user", "team", "project", "organisation", "all"}: raise ValueError("invalid data scope")
        if representation not in {"individual", "aggregated", "anonymized", "statistical", "export"}: raise ValueError("invalid representation")
        permissions = permissions or {}
        rid = rule_id or _id(); now = _now_us()
        fields = ("create","read","update","delete","assign","review","approve","export","publish","aggregate")
        flags = tuple(int(bool(permissions.get(name, False))) for name in fields)
        with self._connect() as cx:
            before=dict(cx.execute("SELECT * FROM adm_access_matrices WHERE rule_id=?",(rid,)).fetchone() or {})
            created=int(before.get("created_at_us",now))
            cx.execute("INSERT OR REPLACE INTO adm_access_matrices VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(rid,display_name,principal_type,principal_id,resource_type,project_id,team_id,data_scope,representation,*flags,int(active),actor_id,created,now))
            after=dict(cx.execute("SELECT * FROM adm_access_matrices WHERE rule_id=?",(rid,)).fetchone())
            self._audit(cx,actor_id,"access.matrix.saved","access_matrix",rid,before,after,reason)
        return rid

    def evaluate_access_matrix(self, *, actor_id: str, role_code: str, action: str, resource_type: str, project_id: str = "", team_id: str = "", owner_user_id: str = "", representation: str = "individual") -> MatrixDecision:
        import os
        if actor_id == "local-user" or role_code == "administrator" or os.environ.get("FIELDORA_PROFILE_ROLE") == "administrator":
            return MatrixDecision(True, True, True, "platform administrator override")
        column={"create":"create_allowed","read":"read_allowed","update":"update_allowed","delete":"delete_allowed","assign":"assign_allowed","review":"review_allowed","approve":"approve_allowed","export":"export_allowed","publish":"publish_allowed","aggregate":"aggregate_allowed"}.get(action)
        if not column: return MatrixDecision(False,False,False,"unknown action")
        with self._connect() as cx:
            rows=cx.execute("SELECT * FROM adm_access_matrices WHERE active=1 AND resource_type IN (?, '*') AND project_id IN ('', ?) AND team_id IN ('', ?) ORDER BY CASE WHEN project_id=? THEN 0 ELSE 1 END, CASE principal_type WHEN 'user' THEN 0 WHEN 'team' THEN 1 WHEN 'role' THEN 2 ELSE 3 END",(resource_type,project_id,team_id,project_id)).fetchall()
        matched=[]
        for row in rows:
            pt,pid=row['principal_type'],row['principal_id']
            if pt=='user' and pid!=actor_id: continue
            if pt=='role' and pid!=role_code: continue
            if pt=='team' and pid!=team_id: continue
            scope=row['data_scope']
            if scope=='user' and owner_user_id!=actor_id: continue
            if scope=='team' and not team_id: continue
            matched.append(str(row['rule_id']))
            detail = row['representation']=='individual' and bool(row['read_allowed'])
            aggregate = bool(row['aggregate_allowed']) or row['representation'] in {'aggregated','anonymized','statistical'}
            allowed = aggregate if representation in {'aggregated','anonymized','statistical'} else bool(row[column])
            return MatrixDecision(allowed, detail, aggregate, f"matched access matrix: {row['display_name']}", tuple(matched))
        return MatrixDecision(False,False,False,"default deny: no access matrix matched")

    def calibrate_instrument(self, instrument_id: str, *, actor_id: str, result: str, calibrated_at: str, next_due: str = "", party_id: str = "", certificate_asset_id: str = "", notes: str = "") -> str:
        self._require_admin(actor_id)
        if not result.strip() or not calibrated_at.strip(): raise ValueError("calibration date and result are required")
        cid=_id()
        with self._connect() as cx:
            if not cx.execute("SELECT 1 FROM adm_instruments WHERE instrument_id=?",(instrument_id,)).fetchone(): raise KeyError(instrument_id)
            cx.execute("INSERT INTO adm_instrument_calibrations VALUES(?,?,?,?,?,?,?,?,?,?)",(cid,instrument_id,calibrated_at,actor_id,party_id,result,certificate_asset_id,next_due,notes,_now_us()))
            self._audit(cx,actor_id,"instrument.calibrated","instrument",instrument_id,after={"calibration_id":cid,"result":result,"next_due":next_due})
        return cid

    def set_asset_security(self, asset_id: str, *, actor_id: str, owner_user_id: str, project_id: str = "", organisation_id: str = "", sensitivity: str = "internal", classifications: dict[str,Any] | None = None, purposes: list[str] | None = None, embargo_until: str = "", licence: str = "", consent_state: str = "", retention_class: str = "", residency: str = "", source_asset_id: str = "") -> None:
        self._require_admin(actor_id); now=_now_us()
        with self._connect() as cx:
            before=dict(cx.execute("SELECT * FROM adm_asset_security WHERE asset_id=?",(asset_id,)).fetchone() or {})
            cx.execute("INSERT OR REPLACE INTO adm_asset_security VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(asset_id,owner_user_id,organisation_id,project_id,sensitivity,json.dumps(classifications or {}),json.dumps(purposes or []),embargo_until,licence,consent_state,retention_class,residency,source_asset_id,actor_id,now))
            self._audit(cx,actor_id,"asset.security.changed","asset",asset_id,before,{"sensitivity":sensitivity,"purposes":purposes or [],"classifications":classifications or {}})

    def evaluate_asset_access(self, *, asset_id: str, role_code: str, action_code: str, purpose_code: str, project_id: str = "", organisation_id: str = "", attributes: dict[str,Any] | None = None, now_iso: str | None = None) -> AccessDecision:
        now_iso=now_iso or datetime.now(UTC).isoformat(); attributes=attributes or {}
        with self._connect() as cx:
            security=dict(cx.execute("SELECT * FROM adm_asset_security WHERE asset_id=?",(asset_id,)).fetchone() or {})
            inherited=json.loads(security.get("classifications_json","{}") or "{}"); effective={**inherited,**attributes}
            rows=cx.execute("SELECT * FROM adm_asset_policies WHERE state='active' AND action_code=? AND (role_code='' OR role_code=?) AND (asset_type='*' OR asset_type=?) AND (purpose_code='*' OR purpose_code=?) AND (project_id='' OR project_id=?) AND (organisation_id='' OR organisation_id=?) ORDER BY priority",(action_code,role_code,effective.get('asset_type','*'),purpose_code,project_id,organisation_id)).fetchall()
        matched=[];allows=[];denies=[]
        for row in rows:
            if row['valid_from'] and now_iso < row['valid_from']: continue
            if row['valid_until'] and now_iso > row['valid_until']: continue
            conditions=json.loads(row['conditions_json'] or '{}')
            if any(effective.get(k)!=v for k,v in conditions.items()): continue
            matched.append(str(row['policy_id'])); (denies if row['effect']=='deny' else allows).append(row)
        if denies:return AccessDecision(False,"explicit deny policy matched",tuple(matched))
        if not allows:return AccessDecision(False,"default deny: no active allow policy matched",tuple(matched))
        permitted=json.loads(security.get('permitted_purposes_json','[]') or '[]')
        if permitted and purpose_code not in permitted:return AccessDecision(False,"purpose is not permitted by the asset security record",tuple(matched))
        if security.get('embargo_until') and now_iso < security['embargo_until']:return AccessDecision(False,"asset is under embargo",tuple(matched))
        return AccessDecision(True,"allow policy matched",tuple(matched))

    def audit_events(self, limit: int = 500) -> tuple[dict[str,Any], ...]:
        with self._connect() as cx:return tuple(dict(x) for x in cx.execute("SELECT * FROM adm_audit ORDER BY created_at_us DESC LIMIT ?",(limit,)).fetchall())

from __future__ import annotations
import hashlib,hmac,json,os,secrets,time
from pathlib import Path

ITERATIONS=240_000
DEFAULTS=(
 ('admin','Platform Administrator','administrator'),
 ('project_manager','Project Manager','manager'),
 ('researcher','Researcher','researcher'),
 ('reviewer','Quality Reviewer','reviewer'),
 ('viewer','Read-only Viewer','viewer'),
)
class LocalProfileStore:
 def __init__(self,path:Path):self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self._failed={};self.ensure_defaults()
 def _load(self):
  if not self.path.exists():return {'users':[]}
  return json.loads(self.path.read_text(encoding='utf-8'))
 def _save(self,data):
  tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,sort_keys=True),encoding='utf-8');os.replace(tmp,self.path)
 def _hash(self,password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
 def ensure_defaults(self):
  data=self._load();existing={u['username'] for u in data['users']}
  for username,name,role in DEFAULTS:
   if username in existing:continue
   salt=secrets.token_bytes(32).hex();data['users'].append({'username':username,'display_name':name,'role':role,'salt':salt,'hash':self._hash('admin',salt),'enabled':True,'must_change_password':False})
  self._save(data)
 def authenticate(self,username,password):
  key=username.strip().casefold();now=time.monotonic();count,until=self._failed.get(key,(0,0))
  if until>now:raise PermissionError('Too many failed attempts. Try again shortly.')
  user=next((u for u in self._load()['users'] if u['username'].casefold()==key and u.get('enabled',True)),None)
  dummy='00'*32;expected=user['hash'] if user else dummy;salt=user['salt'] if user else '00'*32
  ok=hmac.compare_digest(self._hash(password,salt),expected)
  if not ok:
   count+=1;self._failed[key]=(count,now+30 if count>=5 else 0);raise PermissionError('Invalid username or password')
  self._failed.pop(key,None);return dict(user)
 def users(self):return tuple({k:v for k,v in u.items() if k not in ('salt','hash')} for u in self._load()['users'])
 def copy_profile(self,source_username,new_username,display_name,password='admin'):
  new_username=new_username.strip();display_name=display_name.strip()
  if not new_username or not display_name:raise ValueError('Username and display name are required')
  data=self._load()
  if any(u['username'].casefold()==new_username.casefold() for u in data['users']):raise ValueError('Username already exists')
  source=next((u for u in data['users'] if u['username']==source_username),None)
  if not source:raise KeyError(source_username)
  salt=secrets.token_bytes(32).hex();data['users'].append({'username':new_username,'display_name':display_name,'role':source['role'],'salt':salt,'hash':self._hash(password,salt),'enabled':True,'must_change_password':False});self._save(data)
 def set_enabled(self,username,enabled):
  data=self._load();user=next((u for u in data['users'] if u['username']==username),None)
  if not user:raise KeyError(username)
  if username=='admin' and not enabled:raise ValueError('The bootstrap administrator cannot be disabled')
  user['enabled']=bool(enabled);self._save(data)

def provision_project_access(database:Path,username:str,role:str):
 import sqlite3
 role_map={'administrator':'admin','manager':'manager','researcher':'contributor','reviewer':'guest','viewer':'guest'}
 project_role=role_map.get(role,'viewer')
 with sqlite3.connect(database) as cx:
  try:projects=[r[0] for r in cx.execute('SELECT project_id FROM pm_projects')]
  except sqlite3.Error:return
  for pid in projects:
   cx.execute('INSERT OR REPLACE INTO pm_project_members(project_id,user_id,role) VALUES(?,?,?)',(pid,username,project_role))

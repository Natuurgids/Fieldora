from __future__ import annotations
import json,sqlite3,os
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QPointF,QSettings,QSize,Qt,Signal,QTimer,QUrl
from PySide6.QtGui import QColor,QDesktopServices,QPainter,QPainterPath,QPen,QPixmap
from PySide6.QtWidgets import QAbstractItemView,QCalendarWidget,QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QFrame,QGridLayout,QHBoxLayout,QInputDialog,QLabel,QLineEdit,QMessageBox,QPushButton,QScrollArea,QSizePolicy,QSplitter,QTableWidget,QTableWidgetItem,QTabWidget,QTextBrowser,QTextEdit,QListWidget,QVBoxLayout,QWidget
from natureai_next.ui.qt.v5_icons import icon,route_icon
from natureai_next.ui.qt.date_time_input import get_datetime_text
from natureai_next.application.observation_workflow import ObservationWorkflowService
from natureai_next.application.project_export_v5 import ProjectExportSelection,SelectableProjectExporter
from natureai_next.application.project_management import ProjectManagementService
from natureai_next.application.phase4_administration import Phase4AdministrationService
from natureai_next.application.local_profiles import LocalProfileStore
from natureai_next.application.ai_platform import AIPlatformService
from natureai_next.application.workspace_context import WorkspaceContext
from natureai_next.application.asset_catalog import AssetCatalogService, classify_asset_type
from natureai_next.application.platform_features import feature_registry, parity_payload
from natureai_next.application.operations_assets import OperationsAssetService

STYLE="""QWidget#page,QWidget#canvas{background:#11181b;color:#eef4f1}QFrame#card,QFrame#panel,QFrame#side{background:#1a2327;border:1px solid #303b3f;border-radius:11px}QFrame#mapFrame{background:#172521;border:1px solid #355047;border-radius:11px}QLabel#title{font-size:25px;font-weight:700}QLabel#head{font-size:16px;font-weight:650}QLabel#value{font-size:23px;font-weight:700}QLabel#muted{color:#a9b6b2}QLabel#accent{color:#75c98d;font-weight:600}QLineEdit,QComboBox{background:#141c1f;border:1px solid #3a464a;border-radius:8px;padding:8px 11px;color:#eef4f1;min-width:190px}QComboBox::drop-down{border:0;width:26px}QPushButton#primary,QPushButton[fieldoraStyle="primary"]{background:#176c49;border:1px solid #29875f;border-radius:8px;color:white;font-weight:600;padding:9px 15px}QPushButton#tool,QPushButton[fieldoraStyle="tool"],QPushButton#tab{background:#1d272a;border:1px solid #3b494c;border-radius:7px;color:#e7eeea;padding:7px 11px}QPushButton#tool:hover,QPushButton[fieldoraStyle="tool"]:hover,QPushButton#tab:hover{border-color:#67b07d;background:#24332f}QPushButton#tab:checked{background:#234136;color:#82d49b;border-color:#4d9567}"""
def scalar(db,sql,args=()):
 try:
  with sqlite3.connect(db) as cx:return cx.execute(sql,args).fetchone()
 except Exception:return None
def many(db,sql,args=()):
 try:
  with sqlite3.connect(db) as cx:return list(cx.execute(sql,args))
 except Exception:return []

def hierarchical_task_rows(rows):
 """Keep sibling ordering while placing every subtask under its parent."""
 by_id={str(row[0]):row for row in rows};children={};roots=[]
 for row in rows:
  parent=str(row[1] or '')
  if parent and parent in by_id and parent!=str(row[0]):children.setdefault(parent,[]).append(row)
  else:roots.append(row)
 ordered=[];visited=set()
 def add(row,depth=0):
  task_id=str(row[0])
  if task_id in visited:return
  visited.add(task_id);ordered.append((row,depth))
  for child in children.get(task_id,()):add(child,depth+1)
 for row in roots:add(row)
 for row in rows:add(row)
 return ordered

class ResponsiveTools(QWidget):
 def __init__(self,cards,parent=None):
  super().__init__(parent);self.cards=list(cards);self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(9);self._columns=0;self._reflow(4)
 def _reflow(self,cols):
  if cols==self._columns:return
  self._columns=cols
  while self.grid.count():self.grid.takeAt(0)
  for i,w in enumerate(self.cards):self.grid.addWidget(w,i//cols,i%cols)
 def resizeEvent(self,event):
  width=event.size().width();self._reflow(4 if width>=1320 else 3 if width>=950 else 2 if width>=620 else 1);super().resizeEvent(event)

class ProjectMapPreview(QWidget):
 activate_requested=Signal()
 def __init__(self,db,parent=None):super().__init__(parent);self.db=db;self.project_id='';self.pix=QPixmap();self.polygons=[];self.source_label='No project selected';self.setMinimumHeight(280);self.setToolTip('Double-click to open the project in the full map workspace')
 def select_project(self,pid):
  self.project_id=pid;self.pix=QPixmap();self.polygons=[];self.source_label='No project selected'
  if pid:
   snap=scalar(self.db,'SELECT image_path FROM pm_project_map_snapshots WHERE project_id=? ORDER BY created_at_us DESC LIMIT 1',(pid,))
   if snap and Path(str(snap[0])).is_file():
    self.pix=QPixmap(str(snap[0]));self.source_label='Project stored map'
   else:self.source_label='Installed OpenStreetMap/offline basemap available in Full Map'
   for row in many(self.db,'SELECT geojson FROM pm_research_areas WHERE project_id=? ORDER BY updated_at_us DESC',(pid,)):
    try:
     data=json.loads(row[0]);geom=data.get('geometry',data);coords=geom.get('coordinates',[])
     if geom.get('type')=='Polygon' and coords:self.polygons.append(coords[0])
    except Exception:pass
  self.update()
 def paintEvent(self,event):
  p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);r=self.rect();p.fillRect(r,QColor('#172521'))
  if not self.pix.isNull():p.drawPixmap(r,self.pix.scaled(r.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation))
  else:
   p.setPen(QPen(QColor('#29413a'),1));step=max(36,r.width()//18)
   for x in range(0,r.width(),step):p.drawLine(x,0,x,r.height())
   for y in range(0,r.height(),step):p.drawLine(0,y,r.width(),y)
  # A saved StreetMaps snapshot already contains the correctly georeferenced
  # project boundary.  Drawing the raw WGS84 ring over that bitmap without the
  # snapshot viewport transform produces a second, wildly displaced polygon.
  # Keep the vector rendering only as the useful no-snapshot fallback.
  pts=[] if not self.pix.isNull() else [q for poly in self.polygons for q in poly if isinstance(q,list) and len(q)>=2]
  if pts:
   xs=[q[0] for q in pts];ys=[q[1] for q in pts];dx=max(max(xs)-min(xs),1e-9);dy=max(max(ys)-min(ys),1e-9)
   p.setPen(QPen(QColor('#3b9d66'),3));p.setBrush(QColor(65,154,99,55))
   for poly in self.polygons:
    path=QPainterPath()
    for i,q in enumerate(poly):
     x=25+(q[0]-min(xs))/dx*(r.width()-50);y=25+(max(ys)-q[1])/dy*(r.height()-50)
     path.moveTo(QPointF(x,y)) if i==0 else path.lineTo(QPointF(x,y))
    path.closeSubpath();p.drawPath(path)
  p.setPen(QColor('#d7e3de'));p.drawText(r.adjusted(12,8,-12,-8),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop,self.source_label)
  if not self.project_id:
   p.setPen(QColor('#a9b6b2'));p.drawText(r,Qt.AlignmentFlag.AlignCenter,'Select a project to show its research area and map')
  elif self.pix.isNull():
   p.setPen(QColor('#a9b6b2'));p.drawText(r.adjusted(24,36,-24,-24),Qt.AlignmentFlag.AlignCenter,'No project map snapshot is stored.\nDouble-click or use Open full map to load the available OpenStreetMap/offline basemap and project overlays.')
 def mouseDoubleClickEvent(self,event):
  if self.project_id:self.activate_requested.emit()
  super().mouseDoubleClickEvent(event)

class Page(QWidget):
 route_requested=Signal(str)
 def __init__(self,title,action,parent=None):
  super().__init__(parent);self.setObjectName('page');self.setStyleSheet(STYLE);self.bindings=[];canvas=QWidget();canvas.setObjectName('canvas');self.body=QVBoxLayout(canvas);self.body.setContentsMargins(24,18,24,22);self.body.setSpacing(12)
  self.header=QHBoxLayout();t=QLabel(title);t.setObjectName('title');self.header.addWidget(t);self.header.addStretch();self.search=QLineEdit();self.search.setPlaceholderText('Search');self.search.addAction(icon('search'),QLineEdit.ActionPosition.LeadingPosition);self.search.textChanged.connect(self._search_changed);self.header.addWidget(self.search);
  if action is not None:self.header.addWidget(self.button(*action,True))
  self.body.addLayout(self.header)
  sc=QScrollArea();sc.setFrameShape(QFrame.Shape.NoFrame);sc.setWidgetResizable(True);sc.setWidget(canvas);outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(sc)
 def button(self,text,route,primary=False):b=QPushButton(text);b.setIcon(route_icon(route));b.setIconSize(QSize(18,18));b.setObjectName('primary' if primary else 'tool');b.setMinimumHeight(36);b.setSizePolicy(QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Fixed);b.clicked.connect(lambda _=False,r=route:self.route_requested.emit(r));return b
 def label(self,text,obj='muted'):q=QLabel(text);q.setObjectName(obj);q.setWordWrap(True);return q
 def card(self,title,lines=(),action=None,height=116,obj='card'):
  f=QFrame();f.setObjectName(obj);f.setMinimumHeight(height);f.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.MinimumExpanding if obj=='card' else QSizePolicy.Policy.Expanding);b=QVBoxLayout(f);h=QHBoxLayout();im=QLabel();im.setPixmap(route_icon(action[1] if action else 'Documents').pixmap(20,20));h.addWidget(im);heading=self.label(title,'head');heading.setWordWrap(False);heading.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);h.addWidget(heading,1);b.addLayout(h)
  for line in lines:b.addWidget(self.label(line));b.addStretch()
  if action:b.addWidget(self.button(*action),0,Qt.AlignmentFlag.AlignLeft)
  return f
 def tabs(self,items,key):
  row=QHBoxLayout();group=[];saved=str(QSettings().value(key,items[0][0]))
  for label,route,value in items:
   b=QPushButton(label);b.setObjectName('tab');b.setCheckable(True);b.setChecked(value==saved);group.append(b);row.addWidget(b)
   def click(_=False,v=value,r=route,button=b):
    for other in group:other.setChecked(other is button)
    QSettings().setValue(key,v)
    if r:self.route_requested.emit(r)
    else:self.refresh()
   b.clicked.connect(click)
  row.addStretch();self.body.addLayout(row)
 def tools(self,items):self.body.addWidget(self.label('Tools','head'));self.body.addWidget(ResponsiveTools([self.card(n,(d,),('Open',r)) for n,d,r in items]))
 def compact_tools(self,items):
  self.body.addWidget(self.label('Tools','head'));cards=[]
  for n,d,r in items:
   card=self.card(n,(d,),('Open',r),82);card.setMaximumHeight(112);cards.append(card)
  self.body.addWidget(ResponsiveTools(cards))
 def _search_changed(self,text):
  self.refresh();query=text.strip().casefold()
  for frame in self.findChildren(QFrame):
   if frame.objectName()=='card':frame.setVisible(not query or query in ' '.join(label.text() for label in frame.findChildren(QLabel)).casefold())
 def search_text(self):return self.search.text().strip().casefold()
 def refresh(self):pass

class Research(Page):
 def __init__(self,science,library,parent=None):
  super().__init__('Research',('＋  New project','Science Projects'),parent);self.db=science;self.library=library;self.context=WorkspaceContext.current();self._unsubscribe_context=self.context.subscribe(self._context_event);self.combo=QComboBox();self.combo.setMinimumWidth(260);self.combo.setToolTip('Select the active research project');self.header.insertWidget(1,self.combo);self.combo.currentIndexChanged.connect(self._changed)
  top=QHBoxLayout();mf=QFrame();mf.setObjectName('mapFrame');ml=QVBoxLayout(mf);hh=QHBoxLayout();hh.addWidget(self.label('Project map','head'));hh.addStretch();fullmap=QPushButton('Open full map');fullmap.setObjectName('tool');fullmap.clicked.connect(lambda:self._project_route('__project_map__'));hh.addWidget(fullmap);ml.addLayout(hh);self.map=ProjectMapPreview(science);self.map.activate_requested.connect(lambda:self._project_route('__project_map__'));ml.addWidget(self.map,1);top.addWidget(mf,4)
  side=QFrame();side.setObjectName('side');sl=QVBoxLayout(side);sl.addWidget(self.label('Project overview','head'));self.details=QLabel('Select a project');self.details.setObjectName('muted');self.details.setWordWrap(True);sl.addWidget(self.details);sl.addStretch();openproject=QPushButton('Open project');openproject.setObjectName('tool');openproject.clicked.connect(lambda:self._project_route('__project_open__'));sl.addWidget(openproject);export=QPushButton('Export project package');export.setObjectName('tool');export.clicked.connect(self._export);sl.addWidget(export);top.addWidget(side,1);self.body.addLayout(top)
  live=QHBoxLayout();task_panel=QFrame();task_panel.setObjectName('panel');task_panel.setMaximumHeight(270);tl=QVBoxLayout(task_panel);th=QHBoxLayout();th.addWidget(self.label('Project tasks','head'));th.addStretch();open_tasks=QPushButton('Manage tasks');open_tasks.setObjectName('tool');open_tasks.clicked.connect(lambda:self._project_route('__project_open__'));th.addWidget(open_tasks);tl.addLayout(th);self.tasks=QTableWidget(0,4);self.tasks.setHorizontalHeaderLabels(('Task','Due','Status','Progress'));self.tasks.verticalHeader().hide();self.tasks.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.tasks.horizontalHeader().setStretchLastSection(True);tl.addWidget(self.tasks);live.addWidget(task_panel,3)
  calendar_panel=QFrame();calendar_panel.setObjectName('panel');calendar_panel.setMaximumHeight(270);cl=QVBoxLayout(calendar_panel);ch=QHBoxLayout();ch.addWidget(self.label('Project calendar','head'));ch.addStretch();open_calendar=QPushButton('Open calendar');open_calendar.setObjectName('tool');open_calendar.clicked.connect(lambda:self.route_requested.emit('Science Calendar'));ch.addWidget(open_calendar);cl.addLayout(ch);self.calendar=QCalendarWidget();self.calendar.setGridVisible(True);self.calendar.setMaximumHeight(220);cl.addWidget(self.calendar);live.addWidget(calendar_panel,2);self.body.addLayout(live)
  self.compact_tools((('Dossiers','Curated project or longitudinal subject records','Science Dossiers'),('Collections','Working groups of selected material','Collections'),('Whiteboards','Visual scientific documents','Science Whiteboard'),('Notebook','Working notes','Notebook'),('Maritime operations','Vessels, dives and tracks','Maritime Operations'),('Measurements & protocols','Samples, survey protocols and animal measurements','Measurements & Protocols'),('Export','Structured project packages','Export')));self.refresh()
 def _context_event(self,event):
  if event.source=='research-overview':return
  if event.topic in {'identity.changed','permissions.changed','data.changed'}:self.refresh()
  elif event.topic=='project.changed' and event.project_id:
   idx=self.combo.findData(event.project_id)
   if idx>=0:self.combo.setCurrentIndex(idx)
 def closeEvent(self,event):
  try:self._unsubscribe_context()
  except Exception:pass
  super().closeEvent(event)
 def refresh(self):
  selected=str(self.combo.currentData() or QSettings().value('v5/active_project_id','') or self.context.active_project_id);projects=many(self.db,'SELECT project_id,name,status FROM pm_projects ORDER BY updated_at_us DESC');self.combo.blockSignals(True);self.combo.clear();self.combo.addItem('Select a project…','')
  choice=0
  for i,(pid,name,status) in enumerate(projects,1):self.combo.addItem(f'{name}  ·  {status}',pid);choice=i if pid==selected else choice
  self.combo.setCurrentIndex(choice);self.combo.blockSignals(False);self._changed(choice)
 def _changed(self,index):
  pid=str(self.combo.currentData() or '');QSettings().setValue('v5/active_project_id',pid);self.context.set_active_project(pid,source='research-overview');self.map.select_project(pid)
  self.tasks.setRowCount(0)
  if not pid:
   self.details.setText('Select a project to show its status, progress, milestone, team, linked evidence and map.')
   return
  project=scalar(self.db,'SELECT name,description,status,start_date,due_date,owner_id FROM pm_projects WHERE project_id=?',(pid,));progress=scalar(self.db,'SELECT COALESCE(ROUND(AVG(progress)),0),COUNT(*) FROM pm_tasks WHERE project_id=?',(pid,));members=scalar(self.db,'SELECT COUNT(*) FROM pm_project_members WHERE project_id=?',(pid,));milestone=scalar(self.db,"SELECT title,due_date FROM pm_tasks WHERE project_id=? AND milestone=1 AND progress<100 ORDER BY CASE WHEN due_date='' THEN 1 ELSE 0 END,due_date LIMIT 1",(pid,));areas=scalar(self.db,'SELECT COUNT(*) FROM pm_research_areas WHERE project_id=?',(pid,));media=scalar(self.db,'SELECT COUNT(*) FROM pm_project_media WHERE project_id=?',(pid,))
  lines=[f'<b>{project[0]}</b>',project[1] or 'No description',f'Status: {project[2]}',f'Progress: {progress[0]}% across {progress[1]} tasks',f'Next milestone: {milestone[0]} · {milestone[1] or "No date"}' if milestone else 'Next milestone: none',f'Team: {members[0]} member(s)',f'Research areas: {areas[0]}',f'Linked evidence: {media[0]}'];self.details.setText('<br><br>'.join(lines))
  raw_tasks=many(self.db,"""SELECT t.task_id,t.parent_task_id,t.title,t.due_date,COALESCE(s.name,t.status_id),t.progress FROM pm_tasks t LEFT JOIN pm_statuses s ON s.status_id=t.status_id WHERE t.project_id=? ORDER BY CASE WHEN t.progress>=100 THEN 1 ELSE 0 END,CASE WHEN t.due_date='' THEN 1 ELSE 0 END,t.due_date,t.position,t.task_id""",(pid,));tasks=hierarchical_task_rows(raw_tasks)[:12];self.tasks.setRowCount(len(tasks))
  for row,(task,depth) in enumerate(tasks):
   values=((('    '*depth+'↳ ') if depth else '')+str(task[2]),task[3],task[4],task[5])
   for column,value in enumerate(values):self.tasks.setItem(row,column,QTableWidgetItem(f'{value}%' if column==3 else str(value or '—')))
  dated=[task[3] for task,_depth in tasks if task[3]]
  if dated:
   from PySide6.QtCore import QDate
   selected=QDate.fromString(str(dated[0]),'yyyy-MM-dd')
   if selected.isValid():self.calendar.setSelectedDate(selected);self.calendar.showSelectedDate()
 def _export(self):
  pid=str(self.combo.currentData() or '')
  if not pid:QMessageBox.information(self,'Project export','Select a project first.');return
  dialog=QDialog(self);dialog.setWindowTitle('Select project export contents');layout=QVBoxLayout(dialog);checks=[]
  for label,checked in (('Tasks and milestones',True),('Notes',True),('Research areas (GeoJSON)',True),('Map snapshots',True),('Evidence index',True),('Original photos, sounds, videos and documents',False)):
   box=QCheckBox(label);box.setChecked(checked);layout.addWidget(box);checks.append(box)
  buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
  if dialog.exec()!=QDialog.DialogCode.Accepted:return
  path,_=QFileDialog.getSaveFileName(self,'Export project',f'{pid}.fieldora-project.zip','Fieldora project (*.zip)')
  if not path:return
  selection=ProjectExportSelection(*(box.isChecked() for box in checks))
  try:SelectableProjectExporter(self.db,self.library).export(pid,Path(path),selection)
  except Exception as exc:QMessageBox.critical(self,'Project export failed',str(exc));return
  QMessageBox.information(self,'Project exported',f'Created structured project package:\n{path}')
 def _project_route(self,prefix):
  pid=str(self.combo.currentData() or '')
  if not pid:QMessageBox.information(self,'Project','Select a project to continue.');return
  self.route_requested.emit(f'{prefix}:{pid}')

class MeasurementsSampling(Page):
 def __init__(self,science,parent=None,actor_provider=None):
  super().__init__('Specimen Enrichments, Samples & Protocols',None,parent);self.db=science;self.service=ProjectManagementService(science);self.admin_service=Phase4AdministrationService(science);self.context=WorkspaceContext.current();self.actor_provider=actor_provider or (lambda:self.context.actor_id);self.action_buttons={};self._unsubscribe_context=self.context.subscribe(self._context_event)
  self.combo=QComboBox();self.combo.setObjectName('measurementsProjectSelector');self.combo.setMinimumWidth(300);self.header.insertWidget(1,self.combo);self.combo.currentIndexChanged.connect(self._changed)
  intro=QFrame();intro.setObjectName('panel');il=QVBoxLayout(intro);il.addWidget(self.label('Longitudinal specimen enrichment workspace','head'));il.addWidget(self.label('Protocols define what may be recorded. Specimens remain stable; measurements, identifiers, encounters, samples, custody, laboratory results and media are append-only, time-stamped enrichments with an explicit user and audit trail.'));self.body.addWidget(intro)
  self.actions=QHBoxLayout();specs=(('New specimen',self._new_specimen,True,'newSpecimenButton'),('Add identifier',self._identifier,False,'identifierButton'),('New encounter',self._new_encounter,False,'newEncounterButton'),('Specimen timeline',self._timeline,False,'specimenTimelineButton'),('Merge specimens',self._merge_specimens,False,'mergeSpecimensButton'),('New protocol',self._new_protocol,True,'newProtocolButton'),('New survey event',self._new_survey_event,True,'newSurveyEventButton'),('New sample',self._new_sample,True,'newSampleButton'),('Record enrichment',self._record_enrichment,True,'recordEnrichmentButton'),('Templates',self._templates,False,'templatesButton'),('Custody event',self._custody,True,'custodyEventButton'),('Laboratory record',self._laboratory,True,'laboratoryRecordButton'),('Add media',self._media,True,'laboratoryMediaButton'),('Change status',self._change_status,False,'changeStatusButton'),('Run quality checks',self._run_quality,True,'qualityChecksButton'))
  for text,slot,primary,name in specs:
   b=QPushButton(text);b.setObjectName(name);b.setProperty('fieldoraStyle','primary' if primary else 'tool');b.clicked.connect(slot);self.actions.addWidget(b);self.action_buttons[name]=b
  self.actions.addStretch();self.body.addLayout(self.actions)
  self.metrics=QHBoxLayout();self.metric_labels=[]
  for title in ('Specimens','Enrichments','Samples','Active protocols'):
   f=QFrame();f.setObjectName('card');l=QVBoxLayout(f);l.addWidget(self.label(title));v=self.label('0','value');l.addWidget(v);self.metric_labels.append(v);self.metrics.addWidget(f)
  self.body.addLayout(self.metrics)
  self.tabs=QTabWidget();self.specimens=self._table(('Specimen','Taxon','Sex','Life stage','Status','User','ID'));self.identifiers=self._table(('Specimen','Type','Identifier','Authority','Status','Applied','User','ID'));self.encounters=self._table(('Specimen','Type','Status','Occurred','Location','Method','User','ID'));self.timeline=self._table(('When','Kind','Title','Detail','User','ID'));self.protocols=self._table(('Protocol','Method','Target','Version','Active','User','ID'));self.events=self._table(('Event','Protocol','Status','Start','Location','User','ID'));self.definitions=self._table(('Definition','Group','Unit','Expected range','User','ID'));self.enrichments=self._table(('Specimen','Type / definition','Value','Status','Occurred','User','ID'));self.samples=self._table(('Sample','Specimen','Type','Collected','Status','User','ID'));self.workflow=self._table(('Kind','Sample','Action / test','From party','To / responsible party','Status','Time','User','ID'));self.media=self._table(('Sample','Laboratory record','Media type','Modality','File','Captured','User','ID'));self.quality=self._table(('Rule','Entity','State','Evidence','Updated','ID'));self.audit=self._table(('Time','User','Event','Details'))
  for title,table in (('Specimens',self.specimens),('Identifiers',self.identifiers),('Encounters',self.encounters),('Timeline',self.timeline),('Protocols',self.protocols),('Survey events',self.events),('Definitions',self.definitions),('Enrichments',self.enrichments),('Samples',self.samples),('Custody & laboratory',self.workflow),('Laboratory media',self.media),('Data quality',self.quality),('Audit',self.audit)):self.tabs.addTab(self._panel(title,table),title)
  self.tabs.currentChanged.connect(self._update_actions)
  for table in (self.specimens,self.identifiers,self.encounters,self.timeline,self.protocols,self.events,self.definitions,self.enrichments,self.samples,self.workflow,self.media,self.quality):table.itemSelectionChanged.connect(self._update_actions)
  self.body.addWidget(self.tabs,1);self.refresh()
 def _context_event(self,event):
  if event.source=='research-operations':return
  if event.topic in {'identity.changed','permissions.changed'}:self.refresh()
  elif event.topic=='project.changed' and event.project_id:
   idx=self.combo.findData(event.project_id)
   if idx>=0:self.combo.setCurrentIndex(idx)
  elif event.topic=='data.changed' and (not event.project_id or event.project_id==str(self.combo.currentData() or '')):self._refresh_after_mutation()
 def _actor(self):return str(self.actor_provider() or 'local-user')
 def _refresh_after_mutation(self):
  pid=str(self.combo.currentData() or '');self._changed(self.combo.currentIndex());self.context.data_changed(pid,source='research-operations')
 def _table(self,headers):
  t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers);t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);t.verticalHeader().hide();t.horizontalHeader().setStretchLastSection(True);return t
 def _panel(self,title,table):
  f=QFrame();f.setObjectName('panel');l=QVBoxLayout(f);l.addWidget(self.label(title,'head'));l.addWidget(table);return f
 def _load(self,table,rows):
  table.setRowCount(len(rows))
  for r,vals in enumerate(rows):
   for c,val in enumerate(vals):table.setItem(r,c,QTableWidgetItem(str(val if val not in (None,'') else '—')))
 def _refs(self,domain):return self.service.reference_values(domain)
 def _ref_choice(self,title,label,domain,current=''):
  rows=self._refs(domain);labels=[x['display_name'] for x in rows];codes=[x['code'] for x in rows]
  if not labels:return '',False
  idx=codes.index(current) if current in codes else 0;value,ok=QInputDialog.getItem(self,title,label,labels,idx,False);return (codes[labels.index(value)] if ok else ''),ok
 def refresh(self):
  selected=str(self.combo.currentData() or QSettings().value('v5/active_project_id','') or self.context.active_project_id);projects=self.context.accessible_projects(self.service);self.combo.blockSignals(True);self.combo.clear();self.combo.addItem('Select a project…','');choice=0
  for i,row in enumerate(projects,1):self.combo.addItem(f"{row['name']}  ·  {row['status']}",row['project_id']);choice=i if row['project_id']==selected else choice
  if choice==0 and projects:choice=1
  self.combo.setCurrentIndex(choice);self.combo.blockSignals(False);self._changed(choice)
 def _changed(self,index):
  pid=str(self.combo.currentData() or '');QSettings().setValue('v5/active_project_id',pid);self.context.set_active_project(pid,source='research-operations')
  for t in (self.specimens,self.identifiers,self.encounters,self.timeline,self.protocols,self.events,self.definitions,self.enrichments,self.samples,self.workflow,self.media,self.quality,self.audit):t.setRowCount(0)
  editable=bool(pid and self.service.can(pid,self._actor(),'edit'))
  self._editable=editable;self._update_actions()
  if not pid:
   for x in self.metric_labels:x.setText('0')
   return
  specs=self.service.specimens(pid);ids=self.service.specimen_identifiers(pid);encounters=self.service.specimen_encounters(pid);protocols=self.service.survey_protocols(pid);events=self.service.survey_events(pid);defs=self.service.measurement_definitions(pid);enrs=self.service.specimen_enrichments(pid);samples=self.service.samples(pid);records=self.service.sample_workflow_records(pid);media=self.service.laboratory_media(pid);findings=self.service.quality_findings(pid);activity=self.service.activity(pid,limit=400)
  for l,v in zip(self.metric_labels,(len(specs),len(enrs),len(samples),sum(bool(x['active']) for x in protocols))):l.setText(str(v))
  self._load(self.specimens,[(x['specimen_code'],x['taxon_name'],x['sex_code'],x['life_stage_code'],x['status_code'],x['created_by'],x['specimen_id']) for x in specs])
  self._load(self.identifiers,[(x['specimen_code'],x['identifier_type'],x['identifier_value'],x['authority'],x['status_code'],x['applied_at'],x['recorded_by'],x['identifier_id']) for x in ids])
  self._load(self.encounters,[(x['specimen_code'],x['encounter_type'],x['status_code'],x['occurred_at'],x['location_name'],x['capture_method'],x['recorded_by'],x['encounter_id']) for x in encounters])
  self._load(self.protocols,[(x['name'],x['method'],x['target_group'],x['version'],'Yes' if x['active'] else 'No',x['created_by'],x['protocol_id']) for x in protocols])
  self._load(self.events,[(x['name'],x.get('protocol_name') or '—',x['status'],x['start_text'],x['location_name'],x['created_by'],x['survey_event_id']) for x in events])
  self._load(self.definitions,[(x['name'],x['category'],x['unit'],f"{x['minimum'] if x['minimum'] is not None else '…'} – {x['maximum'] if x['maximum'] is not None else '…'}",x['created_by'],x['definition_id']) for x in defs])
  self._load(self.enrichments,[(x['specimen_code'],x.get('definition_name') or x['enrichment_type'],f"{x['value_text']} {x['unit']}".strip(),x['status_code'],x['occurred_at'],x['recorded_by'],x['enrichment_id']) for x in enrs])
  self._load(self.samples,[(x['sample_code'],x['specimen_code'],x['sample_type'],x['collected_at'],x['status'],x['created_by'],x['sample_id']) for x in samples])
  sn={x['sample_id']:x['sample_code'] for x in samples};flow=[]
  for x in records['chain_of_custody']:flow.append(('Custody',sn.get(x['sample_id'],x['sample_id']),x['action'],x['from_party'],x['to_party'],x.get('condition') or 'recorded',x['occurred_at'],x['recorded_by'],x['custody_id']))
  for x in records['laboratory_records']:flow.append(('Laboratory',sn.get(x['sample_id'],x['sample_id']),x['requested_test'] or x['record_type'],'—',x['laboratory'],x['status'],x['recorded_at'],x['recorded_by'],x['laboratory_id']))
  self._load(self.workflow,flow);self._load(self.media,[(x['sample_code'],x['record_type'],x['media_type'],x['modality'],x['file_name'],x['captured_at'],x['uploaded_by'],x['media_id']) for x in media]);self._load(self.quality,[(x['rule_name'],f"{x['entity_type']}:{x['entity_id']}",x['state'],json.dumps(x['evidence'],sort_keys=True),x['updated_at_us'],x['finding_id']) for x in findings]);self._load(self.audit,[(datetime.fromtimestamp(x['created_at_us']/1_000_000).isoformat(timespec='seconds'),x['actor_id'],x['event_type'],x['details_json']) for x in activity if x['event_type'].startswith(('survey_','sample.','measurement','laboratory.','quality.','specimen.','enrichment.'))])
 def _pid(self):
  pid=str(self.combo.currentData() or '')
  if not pid:QMessageBox.information(self,'Project','Select a project to continue.')
  return pid
 def _active_project(self):
  return bool(self._pid())
 def _choose_specimen(self,title='Select specimen'):
  pid=self._pid();rows=self.service.specimens(pid) if pid else ()
  if not rows:QMessageBox.information(self,title,'No specimens are available in this project.');return ''
  labels=[f"{x['specimen_code']} · {x.get('taxon_name') or 'unclassified'}" for x in rows];value,ok=QInputDialog.getItem(self,title,'Specimen',labels,0,False);return rows[labels.index(value)]['specimen_id'] if ok else ''
 def _choose_sample(self,title='Select sample'):
  pid=self._pid();rows=self.service.samples(pid) if pid else ()
  if not rows:QMessageBox.information(self,title,'No samples are available in this project.');return ''
  labels=[f"{x['sample_code']} · {x.get('sample_type') or ''}" for x in rows];value,ok=QInputDialog.getItem(self,title,'Sample',labels,0,False);return rows[labels.index(value)]['sample_id'] if ok else ''
 def _choose_laboratory_record(self):
  pid=self._pid();records=self.service.sample_workflow_records(pid).get('laboratory_records',[]) if pid else []
  if not records:QMessageBox.information(self,'Laboratory media','No laboratory records are available in this project.');return ''
  samples={x['sample_id']:x['sample_code'] for x in self.service.samples(pid)};labels=[f"{samples.get(x['sample_id'],'')} · {x['record_type']} · {x['status']}" for x in records];value,ok=QInputDialog.getItem(self,'Laboratory media','Laboratory record',labels,0,False);return records[labels.index(value)]['laboratory_id'] if ok else ''
 def _selected_sample(self):
  items=self.samples.selectedItems();return items[-1].text() if items else self._choose_sample()
 def _selected(self,table,label):
  items=table.selectedItems()
  if not items:QMessageBox.information(self,label,f'Select a {label.lower()} row first.');return ''
  return items[-1].text()
 def _new_specimen(self):
  pid=self._pid();
  if not pid:return
  code,ok=QInputDialog.getText(self,'New specimen','Stable specimen identifier');
  if not ok or not code.strip():return
  known=sorted({str(x.get('taxon_name') or '').strip() for x in self.service.specimens(pid) if str(x.get('taxon_name') or '').strip()});known=['Unclassified / enter new']+known
  choice,ok=QInputDialog.getItem(self,'New specimen','Species / taxon',known,0,False);
  if not ok:return
  taxon=choice
  if choice==known[0]:
   taxon,ok=QInputDialog.getText(self,'New specimen','Scientific name (validated taxonomy mapping can be added later)');
   if not ok:return
  status,ok=self._ref_choice('New specimen','Status','specimen_status');
  if not ok:return
  try:self.service.create_specimen(pid,specimen_code=code,taxon_name=taxon,status_code=status,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'New specimen',str(e));return
  self._refresh_after_mutation()
 def _identifier(self):
  sid=self._choose_specimen('Add identifier');
  if not sid:return
  typ,ok=self._ref_choice('Add identifier','Identifier type','identifier_type');
  if not ok:return
  value,ok=QInputDialog.getText(self,'Add identifier','Ring, tag or identifier value');
  if not ok or not value.strip():return
  authority,ok=QInputDialog.getText(self,'Add identifier','Issuing authority / organisation');
  if not ok:return
  applied,ok=get_datetime_text(self,'Add identifier','Applied date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  try:self.service.add_specimen_identifier(sid,identifier_type=typ,identifier_value=value,authority=authority,applied_at=applied,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'Add identifier',str(e));return
  self._refresh_after_mutation()
 def _new_encounter(self):
  pid=self._pid();sid=self._choose_specimen('New encounter') if pid else ''
  if not sid:return
  kind,ok=self._ref_choice('New encounter','Encounter type','encounter_type');
  if not ok:return
  occurred,ok=get_datetime_text(self,'New encounter','Occurred date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok or not occurred.strip():return
  location,ok=QInputDialog.getText(self,'New encounter','Location');
  if not ok:return
  method,ok=QInputDialog.getText(self,'New encounter','Capture/observation method');
  if not ok:return
  try:self.service.create_specimen_encounter(pid,sid,encounter_type=kind,occurred_at=occurred,location_name=location,capture_method=method,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'New encounter',str(e));return
  self._refresh_after_mutation();self.tabs.setCurrentWidget(self.encounters.parentWidget())
 def _timeline(self):
  sid=self._choose_specimen('Specimen timeline')
  if not sid:return
  try:rows=self.service.specimen_timeline(sid,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'Specimen timeline',str(e));return
  self._load(self.timeline,[(x['happened'],x['kind'],x['title'],x['detail'],x['actor'],x['id']) for x in rows]);self.tabs.setCurrentWidget(self.timeline.parentWidget())
 def _merge_specimens(self):
  pid=self._pid()
  if not pid:return
  rows=self.service.specimens(pid)
  if len(rows)<2:QMessageBox.information(self,'Merge specimens','At least two specimens are required.');return
  labels=[f"{x['specimen_code']} · {x['taxon_name']}" for x in rows];lookup={label:x['specimen_id'] for label,x in zip(labels,rows)}
  canonical,ok=QInputDialog.getItem(self,'Merge specimens','Canonical specimen:',labels,0,False);
  if not ok:return
  duplicate,ok=QInputDialog.getItem(self,'Merge specimens','Duplicate specimen:',labels,1 if len(labels)>1 else 0,False);
  if not ok:return
  reason,ok=QInputDialog.getMultiLineText(self,'Merge specimens','Reason and evidence:');
  if not ok:return
  try:self.service.merge_specimens(lookup[canonical],lookup[duplicate],actor_id=self._actor(),reason=reason)
  except Exception as e:QMessageBox.warning(self,'Merge specimens',str(e));return
  self._refresh_after_mutation()
 def _new_protocol(self):
  pid=self._pid();
  if not pid:return
  name,ok=QInputDialog.getText(self,'New protocol','Protocol name');
  if not ok or not name.strip():return
  method,ok=self._ref_choice('New protocol','Method','protocol_method')
  if not ok:return
  target,ok=QInputDialog.getText(self,'New protocol','Target species or group');
  if not ok:return
  try:self.service.create_survey_protocol(pid,name=name,method=method,target_group=target,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'New protocol',str(e));return
  self._refresh_after_mutation()
 def _new_survey_event(self):
  pid=self._pid();
  if not pid:return
  name,ok=QInputDialog.getText(self,'New survey event','Event name');
  if not ok or not name.strip():return
  protocols=self.service.survey_protocols(pid);labels=['No protocol']+[f"{x['name']} · {x['method']}" for x in protocols];protocol_choice,ok=QInputDialog.getItem(self,'New survey event','Protocol',labels,0,False)
  if not ok:return
  protocol_id='' if protocol_choice==labels[0] else protocols[labels.index(protocol_choice)-1]['protocol_id']
  status,ok=self._ref_choice('New survey event','Status','survey_event_status');
  if not ok:return
  start,ok=get_datetime_text(self,'New survey event','Start date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  location,ok=QInputDialog.getText(self,'New survey event','Location / site');
  if not ok:return
  try:self.service.create_survey_event(pid,name=name,protocol_id=protocol_id,status=status,start_text=start,location_name=location,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'New survey event',str(e));return
  self._refresh_after_mutation()
 def _new_sample(self):
  pid=self._pid();
  if not pid:return
  code,ok=QInputDialog.getText(self,'New sample','Sample identifier');
  if not ok or not code.strip():return
  typ,ok=self._ref_choice('New sample','Sample type','sample_type');
  if not ok or not typ:return
  specimens=self.service.specimens(pid);labels=[f"{x['specimen_code']} · {x.get('taxon_name') or 'unclassified'}" for x in specimens]
  labels=['Unlinked sample']+labels;specimen_choice,ok=QInputDialog.getItem(self,'New sample','Specimen',labels,0,False)
  if not ok:return
  specimen='' if specimen_choice==labels[0] else specimens[labels.index(specimen_choice)-1]['specimen_code']
  when,ok=get_datetime_text(self,'New sample','Collected date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  try:self.service.create_sample(pid,sample_code=code,sample_type=typ,specimen_code=specimen,collected_at=when,collector=self._actor(),actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'New sample',str(e));return
  self._refresh_after_mutation()
 def _record_enrichment(self):
  pid=self._pid();sid=self._choose_specimen('Record enrichment')
  if not pid or not sid:return
  defs=self.service.measurement_definitions(pid);labels=['General observation']+[f"{x['name']} ({x['unit']})" for x in defs];choice,ok=QInputDialog.getItem(self,'Record enrichment','Definition',labels,0,False)
  if not ok:return
  definition=None if choice==labels[0] else defs[labels.index(choice)-1];etype='observation' if definition is None else 'measurement';value,ok=QInputDialog.getText(self,'Record enrichment','Value / finding');
  if not ok:return
  when,ok=get_datetime_text(self,'Record enrichment','Occurred date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  status,ok=self._ref_choice('Record enrichment','Status','enrichment_status');
  if not ok:return
  try:self.service.record_specimen_enrichment(pid,sid,enrichment_type=etype,definition_id=definition and definition['definition_id'],value_text=value,unit=definition and definition['unit'] or '',occurred_at=when,status_code=status,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'Record enrichment',str(e));return
  self._refresh_after_mutation()
 def _templates(self):
  pid=self._pid()
  if not pid:return
  templates=[x for x in self.admin_service.list_domain('templates') if x.get('active') and x.get('state')=='published' and x.get('template_type') in ('measurement','enrichment')]
  if not templates:
   QMessageBox.information(self,'Templates','No published measurement or enrichment templates are available. Publish templates in Administration → Governance & security.')
   return
  labels=[f"{x['display_name']} · v{x['version']}" for x in templates];choice,ok=QInputDialog.getItem(self,'Scientific templates','Template',labels,0,False)
  if not ok:return
  template=templates[labels.index(choice)]
  try:definition=json.loads(template.get('definition_json') or '{}')
  except json.JSONDecodeError:QMessageBox.warning(self,'Templates','The selected template definition is invalid.');return
  items=definition.get('items',[]) if isinstance(definition,dict) else []
  if not items:QMessageBox.information(self,'Templates','The selected template contains no measurement items.');return
  existing={(x['name'].casefold(),x['unit'].casefold()) for x in self.service.measurement_definitions(pid)};created=0
  for item in items:
   name=str(item.get('name','')).strip();unit=str(item.get('unit','')).strip();category=str(item.get('category') or template['display_name'])
   if name and unit and (name.casefold(),unit.casefold()) not in existing:
    self.service.create_measurement_definition(pid,name=name,category=category,unit=unit,actor_id=self._actor());created+=1
  QMessageBox.information(self,'Templates',f'Installed {created} definition(s) from {template["display_name"]}.');self._refresh_after_mutation()
 def _custody(self):
  if not self._active_project():return
  sample=self._selected_sample();
  if not sample:return
  action,ok=self._ref_choice('Custody event','Action','custody_action')
  if not ok:return
  parties=[x for x in self.admin_service.list_domain('parties') if x.get('active')];labels=[x['display_name'] for x in parties];codes=[x['party_id'] for x in parties]
  if not labels:QMessageBox.information(self,'Custody event','No active parties are configured in Administration.');return
  frm,ok=QInputDialog.getItem(self,'Custody event','From party',labels,0,False);
  if not ok:return
  to,ok=QInputDialog.getItem(self,'Custody event','To party',labels,0,False);
  if not ok:return
  status,ok=self._ref_choice('Custody event','Status','custody_status');
  if not ok:return
  when,ok=get_datetime_text(self,'Custody event','Effective date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  try:self.service.add_custody_event(sample,action=action,from_party=codes[labels.index(frm)],to_party=codes[labels.index(to)],condition=status,occurred_at=when,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'Custody event',str(e));return
  self._refresh_after_mutation()
 def _laboratory(self):
  if not self._active_project():return
  sample=self._selected_sample();
  if not sample:return
  typ,ok=self._ref_choice('Laboratory record','Record type / test','laboratory_record_type')
  if not ok:return
  labs=[x for x in self.admin_service.list_domain('laboratories') if x.get('active')];lab_labels=[x['display_name'] for x in labs]
  if not lab_labels:QMessageBox.information(self,'Laboratory record','No active laboratories are configured in Administration.');return
  lab,ok=QInputDialog.getItem(self,'Laboratory record','Laboratory',lab_labels,0,False)
  if not ok:return
  status,ok=self._ref_choice('Laboratory record','Status','laboratory_status');
  if not ok:return
  result,ok=QInputDialog.getMultiLineText(self,'Laboratory record','Result / notes');
  if not ok:return
  try:self.service.add_laboratory_record(sample,record_type=typ,requested_test=typ,laboratory=lab,status=status,result=result,recorded_at=datetime.now().isoformat(timespec='minutes'),actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'Laboratory record',str(e));return
  self._refresh_after_mutation()
 def _media(self):
  lab_id=self._choose_laboratory_record()
  if not lab_id:return
  path,_=QFileDialog.getOpenFileName(self,'Add laboratory evidence')
  if not path:return
  media,ok=self._ref_choice('Laboratory media','Media type','media_type');
  if not ok:return
  modality,ok=self._ref_choice('Laboratory media','Scientific modality','modality');
  if not ok:return
  captured,ok=get_datetime_text(self,'Laboratory media','Captured date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  try:self.service.add_laboratory_media(lab_id,Path(path),media_type=media,modality=modality,captured_at=captured,actor_id=self._actor())
  except Exception as e:QMessageBox.warning(self,'Laboratory media',str(e));return
  self._refresh_after_mutation()
 def _change_status(self):
  idx=self.tabs.currentIndex();title=self.tabs.tabText(idx)
  try:
   if title=='Samples':
    identity=self._selected(self.samples,'Sample');status,ok=self._ref_choice('Change sample status','Status','sample_status');
    if identity and ok:self.service.update_sample_status(identity,status,actor_id=self._actor())
   elif title=='Survey events':
    identity=self._selected(self.events,'Survey event');status,ok=self._ref_choice('Change survey status','Status','survey_event_status');
    if identity and ok:self.service.update_survey_event_status(identity,status,actor_id=self._actor())
   elif title=='Custody & laboratory':
    items=self.workflow.selectedItems()
    if not items or items[0].text()!='Laboratory':QMessageBox.information(self,'Status','Select a laboratory record.');return
    status,ok=self._ref_choice('Change laboratory status','Status','laboratory_status');
    if ok:self.service.update_laboratory_status(items[-1].text(),status,actor_id=self._actor())
   else:QMessageBox.information(self,'Status','Open Samples, Survey events, or Custody & laboratory and select a row.');return
  except Exception as e:QMessageBox.warning(self,'Status',str(e));return
  self._refresh_after_mutation()
 def _update_actions(self,*_):
  title=self.tabs.tabText(self.tabs.currentIndex()) if hasattr(self,'tabs') else ''
  visible={
   'Specimens':('newSpecimenButton','newEncounterButton','specimenTimelineButton','mergeSpecimensButton'),
   'Identifiers':('identifierButton',),
   'Encounters':('newEncounterButton','specimenTimelineButton'),
   'Timeline':('specimenTimelineButton',),
   'Protocols':('newProtocolButton','templatesButton'),
   'Survey events':('newSurveyEventButton','changeStatusButton'),
   'Definitions':('templatesButton',),
   'Enrichments':('recordEnrichmentButton',),
   'Samples':('newSampleButton','changeStatusButton','custodyEventButton','laboratoryRecordButton'),
   'Custody & laboratory':('custodyEventButton','laboratoryRecordButton','changeStatusButton'),
   'Laboratory media':('laboratoryMediaButton',),
   'Data quality':('qualityChecksButton',),
   'Audit':(),
  }.get(title,())
  pid=str(self.combo.currentData() or '') if hasattr(self,'combo') else ''
  permission_by_action={'specimenTimelineButton':'view','newSpecimenButton':'create','identifierButton':'edit','newEncounterButton':'create','mergeSpecimensButton':'manage','newProtocolButton':'create','newSurveyEventButton':'create','newSampleButton':'create','recordEnrichmentButton':'edit','templatesButton':'manage','custodyEventButton':'edit','laboratoryRecordButton':'edit','laboratoryMediaButton':'edit','changeStatusButton':'edit','qualityChecksButton':'manage'}
  for name,button in self.action_buttons.items():
   button.setVisible(name in visible)
   permission=permission_by_action.get(name,'edit');allowed=bool(pid and self.service.can(pid,self._actor(),permission))
   if name=='changeStatusButton' and title in {'Samples','Survey events','Custody & laboratory'}:
    active_table={'Samples':self.samples,'Survey events':self.events,'Custody & laboratory':self.workflow}.get(title);allowed=allowed and bool(active_table and active_table.selectedItems())
   if name=='mergeSpecimensButton':allowed=allowed and self.specimens.rowCount()>=2
   button.setEnabled(allowed)
   if not pid:button.setToolTip('Select a project to use this action')
   elif not allowed:button.setToolTip('This project is read-only for the current user')
   else:button.setToolTip('')
 def select_project(self,project_id,section=''):
  for index in range(self.combo.count()):
   if str(self.combo.itemData(index) or '')==str(project_id):self.combo.setCurrentIndex(index);break
  if section:
   for index in range(self.tabs.count()):
    if self.tabs.tabText(index)==section:self.tabs.setCurrentIndex(index);break
  self._update_actions()
 def _run_quality(self):
  pid=self._pid();
  if not pid:return
  try:count=len(self.service.run_quality_checks(pid,actor_id=self._actor()))
  except Exception as e:QMessageBox.warning(self,'Data quality',str(e));return
  QMessageBox.information(self,'Data quality',f'Quality checks completed. {count} active finding(s).');self._refresh_after_mutation()

class DataTable(QTableWidget):
 def __init__(self,headers,parent=None):super().__init__(0,len(headers),parent);self.setHorizontalHeaderLabels(headers);self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.verticalHeader().hide();self.horizontalHeader().setStretchLastSection(True)
 def load(self,rows):
  self.setRowCount(len(rows))
  for r,row in enumerate(rows):
   for c,value in enumerate(row):self.setItem(r,c,QTableWidgetItem('' if value is None else str(value)))
 def filter_text(self,text):
  query=text.strip().casefold()
  for row in range(self.rowCount()):
   haystack=' '.join(self.item(row,column).text() for column in range(self.columnCount()) if self.item(row,column)).casefold()
   self.setRowHidden(row,bool(query) and query not in haystack)
 def selected_id(self,column=-1):
  items=self.selectedItems();return items[column].text() if items else ''

class Library(Page):
 def __init__(self,database,parent=None):
  super().__init__('Library',('＋  Import files','Imports'),parent);self.db=database;self.catalog=AssetCatalogService(database);self._filter='all';self._page_size=200;self._offset=0;self._refresh_pending=False;self.tabs((('All media',None,'all'),('Collections','Collections','collections'),('Trash','Trash Manager','trash')),'v5/library_tab')
  split=QSplitter();self.table=DataTable(('Type','Title / filename','Captured','Rating','Asset id'));self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.preview=QLabel('Select an asset');self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter);self.preview.setMinimumHeight(220);self.preview.setWordWrap(True);self.detail=QTextBrowser();self.detail.setObjectName('side');side=QWidget();side_layout=QVBoxLayout(side);side_layout.setContentsMargins(8,8,8,8);side_layout.addWidget(self.preview);side_layout.addWidget(self.detail,1);split.addWidget(self.table);split.addWidget(side);split.setStretchFactor(0,4);split.setStretchFactor(1,1);self.body.addWidget(split,1);self.table.itemSelectionChanged.connect(self._selected);self.table.itemDoubleClicked.connect(lambda _item:self._open_selected())
  self.filter_row=QHBoxLayout()
  all_button=QPushButton('All media');all_button.setObjectName('tool');all_button.clicked.connect(lambda:self._set_filter('all'));self.filter_row.addWidget(all_button)
  for text,route in (('Photos','Photos'),('Sounds','Sounds'),('Videos','Videos'),('Documents','Documents'),('Maps / GIS','Map')):
   button=QPushButton(text);button.setObjectName('tool');button.clicked.connect(lambda _=False,r=route:self.route_requested.emit(r));self.filter_row.addWidget(button)
  other_button=QPushButton('Other media');other_button.setObjectName('tool');other_button.clicked.connect(lambda:self._set_filter('other'));self.filter_row.addWidget(other_button)
  self.filter_row.addStretch();self.body.addLayout(self.filter_row)
  navigation=QHBoxLayout()
  for text,route in (('Maps & project areas','Map'),('Offline map packages','Offline Maps')):navigation.addWidget(self.button(text,route))
  navigation.addStretch();self.body.addLayout(navigation)
  row=QHBoxLayout();add=QPushButton('Add to collection');add.setObjectName('tool');add.clicked.connect(lambda:self._with_asset('__asset_collection__'));row.addWidget(add);export=QPushButton('Export selected');export.setObjectName('tool');export.clicked.connect(lambda:self._with_asset('__asset_export__'));row.addWidget(export);open_button=QPushButton('Open selected');open_button.setObjectName('primary');open_button.clicked.connect(self._open_selected);row.addWidget(open_button);row.addStretch();self.body.addLayout(row)
  pager=QHBoxLayout();self.page_status=QLabel('Library not loaded');self.page_status.setObjectName('muted');pager.addWidget(self.page_status);pager.addStretch();self.previous_page=QPushButton('Previous');self.previous_page.setObjectName('tool');self.previous_page.clicked.connect(self._previous_page);pager.addWidget(self.previous_page);self.next_page=QPushButton('Next');self.next_page.setObjectName('tool');self.next_page.clicked.connect(self._next_page);pager.addWidget(self.next_page);self.body.addLayout(pager)
 def _normalized_type(self,value):
  return classify_asset_type(mime_type=None,path=None,media_type=value)

 def _set_filter(self,kind):self._filter=kind;self._offset=0;self.refresh()
 def _previous_page(self):
  self._offset=max(0,self._offset-self._page_size);self.refresh()
 def _next_page(self):
  self._offset+=self._page_size;self.refresh()
 def refresh(self):
  if self._refresh_pending:return
  self._refresh_pending=True;QTimer.singleShot(0,self._perform_refresh)
 def _perform_refresh(self):
  self._refresh_pending=False
  selected=self.table.selected_id()
  total=self.catalog.count_assets(search=self.search_text())
  if self._offset>=total and total:self._offset=max(0,((total-1)//self._page_size)*self._page_size)
  records=self.catalog.list_assets(asset_type=self._filter,search=self.search_text(),limit=self._page_size,offset=self._offset)
  rows=[(row.asset_type,row.title,row.captured,row.rating,row.asset_id) for row in records]
  self.table.setUpdatesEnabled(False);self.table.load(rows);self.table.setUpdatesEnabled(True)
  first=self._offset+1 if rows else 0;last=self._offset+len(rows);self.page_status.setText(f'Showing {first:,}–{last:,} of {total:,} active assets');self.previous_page.setEnabled(self._offset>0);self.next_page.setEnabled(self._offset+self._page_size<total)
  if selected:
   for index in range(self.table.rowCount()):
    item=self.table.item(index,4)
    if item and item.text()==selected:
     self.table.selectRow(index);break
  if not self.table.selectedItems():
   self.preview.setText('Select an asset to preview it. Double-click to open the exact item.');self.preview.setPixmap(QPixmap());self.detail.setHtml(f'<h3>Digital asset library</h3><p>{total:,} matching assets; this page contains {len(rows):,}. Photos, sounds, videos, documents, maps and other files share one governed catalogue.</p>')

 def _type_metadata(self,aid,kind):
  if kind=='photo':
   row=scalar(self.db,"SELECT pixel_width,pixel_height,bit_depth,color_space,camera_make,camera_model,lens_model,capture_time_us,exposure_json FROM photo_assets WHERE asset_public_id=?",(aid,))
   if row:return f'<p><b>Resolution</b> {row[0] or "—"} × {row[1] or "—"}<br><b>Bit depth</b> {row[2] or "—"}<br><b>Colour space</b> {row[3] or "—"}<br><b>Camera</b> {" ".join(str(x) for x in row[4:6] if x) or "—"}<br><b>Lens</b> {row[6] or "—"}<br><b>EXIF exposure</b> {row[8] or "—"}</p>'
  if kind=='sound':
   row=scalar(self.db,"SELECT duration_ms,sample_rate_hz,channel_count,bit_depth,codec,bitrate_bps,recorder_make,recorder_model,microphone,latitude,longitude FROM sound_assets WHERE asset_public_id=?",(aid,))
   if row:return f'<p><b>Duration</b> {(row[0] or 0)/1000:g} s<br><b>Sample rate</b> {row[1] or "—"} Hz<br><b>Channels</b> {row[2] or "—"}<br><b>Bit depth</b> {row[3] or "—"}<br><b>Codec</b> {row[4] or "—"}<br><b>Bitrate</b> {row[5] or "—"}<br><b>Recorder</b> {" ".join(str(x) for x in row[6:8] if x) or "—"}<br><b>Microphone</b> {row[8] or "—"}<br><b>GPS</b> {row[9] if row[9] is not None else "—"}, {row[10] if row[10] is not None else "—"}</p>'
  if kind=='video':
   row=scalar(self.db,"SELECT duration_ms,pixel_width,pixel_height,frame_rate,video_codec,audio_codec,bitrate_bps,camera_make,camera_model,latitude,longitude FROM video_assets WHERE asset_public_id=?",(aid,))
   if row:return f'<p><b>Duration</b> {(row[0] or 0)/1000:g} s<br><b>Resolution</b> {row[1] or "—"} × {row[2] or "—"}<br><b>Frame rate</b> {row[3] or "—"} fps<br><b>Video codec</b> {row[4] or "—"}<br><b>Audio codec</b> {row[5] or "—"}<br><b>Bitrate</b> {row[6] or "—"}<br><b>Camera</b> {" ".join(str(x) for x in row[7:9] if x) or "—"}<br><b>GPS</b> {row[9] if row[9] is not None else "—"}, {row[10] if row[10] is not None else "—"}</p>'
  if kind=='document':
   row=scalar(self.db,"SELECT document_format,page_count,author,subject,language_code,searchable_text_available,password_protected FROM document_assets WHERE asset_public_id=?",(aid,))
   if row:return f'<p><b>Format</b> {row[0] or "—"}<br><b>Pages</b> {row[1] or "—"}<br><b>Author</b> {row[2] or "—"}<br><b>Subject</b> {row[3] or "—"}<br><b>Language</b> {row[4] or "—"}<br><b>Searchable text</b> {"Yes" if row[5] else "No"}<br><b>Password protected</b> {"Yes" if row[6] else "No"}</p>'
  return ''
 def _selected(self):
  items=self.table.selectedItems()
  if not items:return
  aid=items[4].text();row=scalar(self.db,"""SELECT a.title,a.caption,a.user_notes,f.normalized_path,f.mime_type,f.file_size,a.capture_local_text,a.rating,a.media_type FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id WHERE a.public_id=?""",(aid,));
  if not row:return
  title=items[1].text();path=str(row[3] or '');mime=str(row[4] or '');size=int(row[5] or 0);kind=self.catalog.asset_type(aid);self.preview.setPixmap(QPixmap());
  if kind=='photo' and path and Path(path).is_file():
   pix=QPixmap(path);self.preview.setPixmap(pix.scaled(360,240,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)) if not pix.isNull() else self.preview.setText('Photo preview unavailable')
  elif kind=='sound':self.preview.setText('♫ Sound asset\nUse Open selected for playback and waveform tools.')
  elif kind=='video':self.preview.setText('▶ Video asset\nUse Open selected for video playback and frame tools.')
  elif kind=='document':self.preview.setText('▤ Document asset\nUse Open selected for the document viewer.')
  elif kind=='map':self.preview.setText('⌖ Map / GIS asset\nUse Open selected for the map workspace.')
  else:self.preview.setText('Asset preview is not available for this file type.')
  metadata=self._type_metadata(aid,kind);relationships=self.catalog.relationships(aid);related=''.join(f'<li><b>{label}</b>: {identity}</li>' for label,identity in relationships) or '<li>No linked records</li>'
  self.detail.setHtml(f'<h3>{title}</h3><p><b>Asset</b> {aid}</p><p><b>Type</b> {kind}</p><p><b>MIME</b> {mime or "—"}</p><p><b>Size</b> {size:,} bytes</p><p><b>Captured</b> {row[6] or "—"}</p><p><b>Rating</b> {row[7] or "—"}</p><p><b>Path</b> {path or "—"}</p>{metadata}<p>{(row[1] or row[2] or "No notes")}</p><h3>Related</h3><ul>{related}</ul>')
 def _open_selected(self):
  aid=self.table.selected_id()
  if not aid:QMessageBox.information(self,'Library','Select an asset first.');return
  self.route_requested.emit(f'__asset_open__:{aid}')
 def _with_asset(self,prefix):
  aid=self.table.selected_id()
  if not aid:QMessageBox.information(self,'Evidence','Select an asset first.');return
  self.route_requested.emit(f'{prefix}:{aid}')

class Observations(Page):
 def __init__(self,database,science,parent=None):
  super().__init__('Observations',('＋  New observation','__observation_new__'),parent);self.db=database;self.science=science;self.workflow=ObservationWorkflowService(database);self.context=WorkspaceContext.current();self._unsubscribe_context=self.context.subscribe(self._context_event);self.review_buttons=[];self.tabs((('All records',None,'all'),('Confirmed',None,'confirmed'),('Needs review',None,'unconfirmed'),('Disputed',None,'disputed')),'v5/observation_filter')
  split=QSplitter();self.table=DataTable(('Identification','Date','Location','Status','Observation id'));self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection);self.table.setToolTip('Select multiple rows with Ctrl/Shift-click, then accept, reject, or defer them together.');self.detail=QTextBrowser();self.detail.setObjectName('side');split.addWidget(self.table);split.addWidget(self.detail);split.setStretchFactor(0,3);split.setStretchFactor(1,2);self.body.addWidget(split,1);self.table.itemSelectionChanged.connect(self._selected)
  self._row_assertions=[];self._row_observations=[]
  review=QHBoxLayout()
  for text,slot,primary in (('Accept selected',lambda:self._apply_selected('accepted'),True),('Reject selected',lambda:self._apply_selected('rejected'),False),('Defer selected',lambda:self._apply_selected('deferred'),False),('Accept one; reject rest',self._accept_one_reject_rest,False),('Reject all unconfirmed',self._reject_all_unconfirmed,False)):
   button=QPushButton(text);button.setObjectName('primary' if primary else 'tool');button.clicked.connect(slot);review.addWidget(button);self.review_buttons.append(button)
  review.addStretch();self.body.addLayout(review)
  actions=QHBoxLayout()
  for text,slot in (('Add identification',self._assert),('Refer to specialist',self._refer),('Link to research',self._link)):
   button=QPushButton(text);button.setObjectName('tool');button.clicked.connect(slot);actions.addWidget(button)
  for text,prefix in (('Evidence','__observation_evidence__'),('Map','__observation_map__'),('Full record','__observation_record__')):
   button=QPushButton(text);button.setObjectName('tool');button.clicked.connect(lambda _=False,p=prefix:self._observation_route(p));actions.addWidget(button)
  actions.addStretch();self.body.addLayout(actions);self.refresh()
 def _context_event(self,event):
  if event.source=='observations':return
  if event.topic in {'identity.changed','permissions.changed','data.changed'}:self.refresh()
 def _notify_changed(self):self.context.data_changed(source='observations')
 def _update_review_actions(self):
  count=len(self._selected_assertions());rows=self._selected_rows()
  for index,button in enumerate(self.review_buttons):button.setEnabled((count>0) if index<3 else ((count==1) if index==3 else bool(rows)))
 def closeEvent(self,event):
  unsubscribe=getattr(self,'_unsubscribe_context',None)
  if callable(unsubscribe):unsubscribe();self._unsubscribe_context=None
  super().closeEvent(event)
 def refresh(self):
  rows=many(self.db,"""SELECT COALESCE(oa.proposed_name,t.scientific_name,ut.display_name,'Unidentified'),COALESCE(a.capture_local_text,''),COALESCE(l.place_name,l.locality,''),COALESCE(oa.status,CASE WHEN EXISTS(SELECT 1 FROM observation_assertions od WHERE od.observation_id=o.id AND od.status='disputed') THEN 'disputed' ELSE o.confirmation_state END),o.public_id,COALESCE(oa.public_id,'') FROM observations o JOIN assets a ON a.id=o.asset_id LEFT JOIN observation_assertions oa ON oa.observation_id=o.id LEFT JOIN taxa t ON t.id=o.taxon_id LEFT JOIN user_taxa ut ON ut.id=o.user_taxon_id LEFT JOIN asset_locations al ON al.asset_id=a.id AND al.role='capture' LEFT JOIN locations l ON l.id=al.location_id ORDER BY o.modified_at_us DESC,oa.created_at_us DESC LIMIT 1000""");state=str(QSettings().value('v5/observation_filter','all'));rows=[row for row in rows if state=='all' or (state=='confirmed' and str(row[3]) in ('confirmed','accepted')) or (state=='disputed' and str(row[3])=='disputed') or (state=='unconfirmed' and str(row[3]) not in ('confirmed','accepted','rejected','superseded'))];self._row_observations=[str(row[4]) for row in rows];self._row_assertions=[str(row[5] or '') for row in rows];self.table.load([row[:5] for row in rows]);self.table.filter_text(self.search_text());self.detail.setHtml('<h3>Observation details</h3><p>Select one or more identification rows. Bulk decisions update each candidate while preserving its observation relationship.</p>');self._update_review_actions()
 def _selected_rows(self):return sorted({index.row() for index in self.table.selectionModel().selectedRows()})
 def _selected(self):
  rows=self._selected_rows()
  self._update_review_actions()
  if not rows:return
  row=rows[0];oid=self._row_observations[row];assertions=many(self.db,"""SELECT assertion_kind,proposed_name,author,status,confidence,rationale FROM observation_assertions oa JOIN observations o ON o.id=oa.observation_id WHERE o.public_id=? ORDER BY oa.created_at_us""",(oid,));refs=many(self.db,"""SELECT referred_to,authority_level,status,question FROM observation_review_referrals r JOIN observations o ON o.id=r.observation_id WHERE o.public_id=? ORDER BY r.created_at_us""",(oid,));links=many(self.db,"""SELECT context_type,context_public_id FROM observation_context_links l JOIN observations o ON o.id=l.observation_id WHERE o.public_id=?""",(oid,));a=''.join(f'<li><b>{x[0]}</b>: {x[1]} — {x[3]} by {x[2]} ({"—" if x[4] is None else round(x[4]*100)}%)<br>{x[5]}</li>' for x in assertions) or '<li>No identification assertions yet</li>';r=''.join(f'<li>Level {x[1]} → {x[0]}: {x[2]} — {x[3]}</li>' for x in refs) or '<li>No open referrals</li>';l=''.join(f'<li>{x[0]}: {x[1]}</li>' for x in links) or '<li>Not linked to research yet</li>';self.detail.setHtml(f'<h2>{self.table.item(row,0).text()}</h2><p>{self.table.item(row,1).text()} · {self.table.item(row,2).text()} · <b>{self.table.item(row,3).text()}</b></p><p>{len(rows)} row(s) selected.</p><h3>Identification history</h3><ol>{a}</ol><h3>Specialist referrals</h3><ul>{r}</ul><h3>Projects, dossiers & collections</h3><ul>{l}</ul>')
 def _oid(self):
  rows=self._selected_rows();return self._row_observations[rows[0]] if rows else ''
 def _selected_assertions(self):return [(self._row_assertions[row],self._row_observations[row]) for row in self._selected_rows() if self._row_assertions[row]]
 def _apply_selected(self,status):
  selected=self._selected_assertions()
  if not selected:QMessageBox.information(self,'Observation review','Select one or more identification rows first.');return
  try:self.workflow.decide_many(tuple(aid for aid,_oid in selected),status=status,reviewer=self.context.actor_id)
  except Exception as exc:QMessageBox.warning(self,'Observation review',str(exc));return
  self.refresh();self._notify_changed()
 def _accept_one_reject_rest(self):
  selected=self._selected_assertions()
  if len(selected)!=1:QMessageBox.information(self,'Observation review','Select exactly one identification row to accept.');return
  aid,_oid=selected[0]
  try:self.workflow.accept_one_reject_remaining(aid,reviewer=self.context.actor_id)
  except Exception as exc:QMessageBox.warning(self,'Observation review',str(exc));return
  self.refresh();self._notify_changed()
 def _reject_all_unconfirmed(self):
  oid=self._oid()
  if not oid:QMessageBox.information(self,'Observation review','Select a row for the observation first.');return
  try:self.workflow.reject_unconfirmed(oid,reviewer=self.context.actor_id)
  except Exception as exc:QMessageBox.warning(self,'Observation review',str(exc));return
  self.refresh();self._notify_changed()
 def _observation_route(self,prefix):
  oid=self._oid()
  if not oid:QMessageBox.information(self,'Observation','Select an observation first.');return
  self.route_requested.emit(f'{prefix}:{oid}')
 def _assert(self):
  oid=self._oid()
  if not oid:return
  name,ok=QInputDialog.getText(self,'Identification','Proposed scientific or common name:')
  if not ok or not name.strip():return
  author,ok=QInputDialog.getText(self,'Identification','Observer or specialist name:',text=os.environ.get('FIELDORA_IDENTITY_ID','Local user'))
  if not ok:return
  self.workflow.assert_identification(oid,kind='observer',proposed_name=name,author=author);self.refresh();self._notify_changed()
 def _latest_assertion(self):
  row=scalar(self.db,"""SELECT oa.public_id FROM observation_assertions oa JOIN observations o ON o.id=oa.observation_id WHERE o.public_id=? ORDER BY oa.created_at_us DESC LIMIT 1""",(self._oid(),));return row[0] if row else ''
 def _refer(self):
  oid=self._oid()
  if not oid:return
  target,ok=QInputDialog.getText(self,'Specialist referral','Specialist, team or authority:')
  if not ok or not target.strip():return
  level,ok=QInputDialog.getInt(self,'Specialist referral','Authority level (1–9):',1,1,9)
  if not ok:return
  question,ok=QInputDialog.getMultiLineText(self,'Specialist referral','Question or reason for referral:')
  if not ok:return
  self.workflow.refer(oid,referred_by=os.environ.get('FIELDORA_IDENTITY_ID','Local reviewer'),referred_to=target,authority_level=level,question=question,assertion_public_id=self._latest_assertion() or None);self._selected()
 def _link(self):
  oid=self._oid()
  if not oid:return
  kind,ok=QInputDialog.getItem(self,'Link observation','Research context:',('project','dossier','collection'),0,False)
  if not ok:return
  if kind=='project':options=[(row[1],row[0]) for row in many(self.science,'SELECT project_id,name FROM pm_projects ORDER BY name')]
  elif kind=='collection':options=[(row[1],row[0]) for row in many(self.db,'SELECT public_id,name FROM collections ORDER BY name')]
  else:options=[(row[1],row[0]) for row in many(self.science,"SELECT record_id,json_extract(payload_json,'$.title') FROM science_records WHERE collection_name='dossiers' ORDER BY 2")]
  if not options:QMessageBox.information(self,'Link observation',f'No {kind}s are available.');return
  label,ok=QInputDialog.getItem(self,'Link observation',f'Select {kind}:',tuple(x[0] for x in options),0,False)
  if ok:self.workflow.link(oid,kind,dict(options)[label],linked_by=self.context.actor_id);self._selected();self._notify_changed()

class AIChatWorkspace(Page):
 def __init__(self,science,parent=None,actor_provider=None):
  super().__init__('AI Chat & MCP',None,parent);self.service=AIPlatformService(science);self.actor_provider=actor_provider or (lambda:os.environ.get('FIELDORA_IDENTITY_ID','local-user'));self.current_conversation=''
  status=QFrame();status.setObjectName('panel');sl=QHBoxLayout(status);self.mode=self.label('Offline-first','accent');sl.addWidget(self.mode);sl.addWidget(self.label('Providers and MCP tools may use LAN/internet only when explicitly approved in Administration.'));sl.addStretch();self.body.addWidget(status)
  controls=QHBoxLayout();self.provider=QComboBox();self.provider.setObjectName('aiProviderSelector');self.provider.currentIndexChanged.connect(self._provider_changed);controls.addWidget(self.label('Provider'));controls.addWidget(self.provider);self.model=QComboBox();self.model.setObjectName('aiModelSelector');controls.addWidget(self.label('Model'));controls.addWidget(self.model);self.purpose=QComboBox();self.purpose.addItems(('scientific_research','species_identification','laboratory_diagnosis','internal_qa','report_drafting'));controls.addWidget(self.label('Purpose'));controls.addWidget(self.purpose);self.mcp_server=QComboBox();controls.addWidget(self.label('MCP'));controls.addWidget(self.mcp_server);refresh_tools=QPushButton('Load tools');refresh_tools.setObjectName('tool');refresh_tools.clicked.connect(self._load_mcp_tools);controls.addWidget(refresh_tools);new=QPushButton('New chat');new.setObjectName('primary');new.clicked.connect(self._new_chat);controls.addWidget(new);test=QPushButton('Test provider');test.setObjectName('tool');test.clicked.connect(self._test_provider);controls.addWidget(test);controls.addStretch();self.body.addLayout(controls)
  split=QSplitter();left=QFrame();left.setObjectName('panel');ll=QVBoxLayout(left);ll.addWidget(self.label('Conversations','head'));self.conversations=QListWidget();self.conversations.currentRowChanged.connect(self._select_conversation);ll.addWidget(self.conversations);ll.addWidget(self.label('MCP tools','head'));self.tools_list=QListWidget();self.tools_list.setMaximumHeight(160);ll.addWidget(self.tools_list);split.addWidget(left);right=QFrame();right.setObjectName('panel');rl=QVBoxLayout(right);rl.addWidget(self.label('Conversation','head'));self.transcript=QTextBrowser();rl.addWidget(self.transcript,1);entry=QHBoxLayout();self.input=QTextEdit();self.input.setObjectName('aiChatInput');self.input.setPlaceholderText('Ask Fieldora AI…');self.input.setMaximumHeight(100);entry.addWidget(self.input,1);send=QPushButton('Send');send.setObjectName('primary');send.clicked.connect(self._send);entry.addWidget(send);rl.addLayout(entry);split.addWidget(right);split.setStretchFactor(1,3);self.body.addWidget(split,1);self.refresh()
 def _context_event(self,event):
  if event.source=='research-operations':return
  if event.topic in {'identity.changed','permissions.changed'}:self.refresh()
  elif event.topic=='project.changed' and event.project_id:
   idx=self.combo.findData(event.project_id)
   if idx>=0:self.combo.setCurrentIndex(idx)
  elif event.topic=='data.changed' and (not event.project_id or event.project_id==str(self.combo.currentData() or '')):self._changed(self.combo.currentIndex())
 def _actor(self):return str(self.actor_provider() or 'local-user')
 def refresh(self):
  current=str(self.provider.currentData() or '');self.provider.blockSignals(True);self.provider.clear()
  for row in self.service.providers(enabled_only=True):self.provider.addItem(f"{row['display_name']} · {row['locality']}",row['provider_id'])
  if current:
   idx=self.provider.findData(current);self.provider.setCurrentIndex(max(0,idx))
  self.provider.blockSignals(False);self._provider_changed();self.mcp_server.clear();self.mcp_server.addItem('No MCP server','');[self.mcp_server.addItem(x['display_name'],x['server_id']) for x in self.service.mcp_servers() if x['enabled']];self.tools_list.clear();self._load_conversations();self.mode.setText('Offline-only' if self.service.offline_only() else 'Governed network mode')
 def _provider_changed(self,*_):
  # Provider-specific model and capability state must never leak across providers.
  pid=str(self.provider.currentData() or '');self.model.clear();self.tools_list.clear()
  for row in self.service.models(pid,enabled_only=True):self.model.addItem(row['display_name'],row['model_id'])
 def _load_conversations(self):
  selected=self.current_conversation;self._conversation_rows=self.service.conversations(self._actor());self.conversations.blockSignals(True);self.conversations.clear();choice=-1
  for i,row in enumerate(self._conversation_rows):self.conversations.addItem(f"{row['title']}\n{row['provider_name']} · {row['model_name']}");choice=i if row['conversation_id']==selected else choice
  self.conversations.setCurrentRow(choice);self.conversations.blockSignals(False);self._render()
 def _new_chat(self):
  pid=str(self.provider.currentData() or '');mid=str(self.model.currentData() or '')
  if not pid or not mid:QMessageBox.information(self,'AI Chat','Select a provider and model.');return
  title,ok=QInputDialog.getText(self,'New AI chat','Conversation title',text='New conversation')
  if not ok:return
  try:self.current_conversation=self.service.create_conversation(title=title or 'New conversation',owner_user_id=self._actor(),provider_id=pid,model_id=mid,purpose_code=self.purpose.currentText());self._load_conversations()
  except Exception as exc:QMessageBox.warning(self,'AI Chat',str(exc))
 def _select_conversation(self,row):
  self.current_conversation=self._conversation_rows[row]['conversation_id'] if 0<=row<len(getattr(self,'_conversation_rows',())) else '';self._render()
 def _render(self):
  if not self.current_conversation:self.transcript.setHtml('<p>Select or create a conversation.</p>');return
  blocks=[]
  for msg in self.service.messages(self.current_conversation):blocks.append(f"<p><b>{msg['role'].title()}</b><br>{str(msg['content']).replace('&','&amp;').replace('<','&lt;').replace(chr(10),'<br>')}</p>")
  self.transcript.setHtml(''.join(blocks));self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())
 def _send(self):
  text=self.input.toPlainText().strip()
  if not self.current_conversation:QMessageBox.information(self,'AI Chat','Create or select a conversation first.');return
  if not text:return
  try:self.service.send_chat(conversation_id=self.current_conversation,user_text=text,actor_id=self._actor(),context={'workspace':'AI Chat'});self.input.clear();self._render();self._load_conversations()
  except Exception as exc:QMessageBox.warning(self,'AI Chat',str(exc))
 def _load_mcp_tools(self):
  sid=str(self.mcp_server.currentData() or '')
  self.tools_list.clear()
  if not sid:return
  try:
   for tool in self.service.mcp_tools(sid):self.tools_list.addItem(f"{tool.get('name','')} — {tool.get('description','')}")
  except Exception as exc:QMessageBox.warning(self,'MCP tools',str(exc))
 def _test_provider(self):
  pid=str(self.provider.currentData() or '')
  if not pid:return
  try:QMessageBox.information(self,'Provider test',self.service.test_provider(pid))
  except Exception as exc:QMessageBox.warning(self,'Provider test',str(exc))

class AIPlatformAdministration(Page):
 def __init__(self,science,parent=None,actor_provider=None):
  super().__init__('AI Platform administration',None,parent);self.service=AIPlatformService(science);self.actor_provider=actor_provider or (lambda:os.environ.get('FIELDORA_IDENTITY_ID','local-user'));self.is_admin=os.environ.get('FIELDORA_PROFILE_ROLE')=='administrator'
  intro=QFrame();intro.setObjectName('panel');il=QVBoxLayout(intro);il.addWidget(self.label('Provider-neutral and offline-first','head'));il.addWidget(self.label('Existing Fieldora models remain available. Providers supply models; MCP servers supply tools/resources/prompts. LAN and internet access is denied unless global policy and a specific administrator approval both allow it.'));self.body.addWidget(intro)
  policy=QHBoxLayout();self.offline=QCheckBox('Global offline-only mode');self.offline.setChecked(self.service.offline_only());self.offline.setEnabled(self.is_admin);self.offline.toggled.connect(self._offline_changed);policy.addWidget(self.offline);policy.addStretch();self.body.addLayout(policy)
  self.tabs=QTabWidget();self.providers=DataTable(('Code','Provider','Type','Endpoint','Locality','Enabled','ID'));self.models=DataTable(('Provider','Model key','Model','Context','Multimodal','Tools','Enabled','ID'));self.mcp=DataTable(('Code','MCP server','Transport','Endpoint / command','Locality','Internet capable','Enabled','ID'));self.approvals=DataTable(('Subject','Project','Purpose','Sensitivity','Approved by','Reason','Valid until','ID'));self.audit=DataTable(('Time','User','Event','Entity','Details','ID'))
  self.tabs.addTab(self._admin_panel(self.providers,(('Add provider',self._add_provider),('Test selected',self._test_selected_provider))),'Providers');self.tabs.addTab(self._admin_panel(self.models,(('Add model',self._add_model),)),'Models');self.tabs.addTab(self._admin_panel(self.mcp,(('Add MCP server',self._add_mcp),)),'MCP servers');self.tabs.addTab(self._admin_panel(self.approvals,(('Approve selected provider',self._approve_provider),)),'Network approvals');panel=QWidget();QVBoxLayout(panel).addWidget(self.audit);self.tabs.addTab(panel,'AI audit');self.body.addWidget(self.tabs,1);self.refresh()
 def _context_event(self,event):
  if event.source=='research-operations':return
  if event.topic in {'identity.changed','permissions.changed'}:self.refresh()
  elif event.topic=='project.changed' and event.project_id:
   idx=self.combo.findData(event.project_id)
   if idx>=0:self.combo.setCurrentIndex(idx)
  elif event.topic=='data.changed' and (not event.project_id or event.project_id==str(self.combo.currentData() or '')):self._changed(self.combo.currentIndex())
 def _actor(self):return str(self.actor_provider() or 'local-user')
 def _admin_panel(self,table,actions):
  p=QWidget();l=QVBoxLayout(p);r=QHBoxLayout()
  for text,slot in actions:b=QPushButton(text);b.setObjectName('primary' if text.startswith('Add') or text.startswith('Approve') else 'tool');b.clicked.connect(slot);b.setEnabled(self.is_admin or text.startswith('Test'));r.addWidget(b)
  r.addStretch();l.addLayout(r);l.addWidget(table);return p
 def refresh(self):
  ps=self.service.providers();self.providers.load([(x['code'],x['display_name'],x['provider_type'],x['endpoint'],x['locality'],'Yes' if x['enabled'] else 'No',x['provider_id']) for x in ps]);self.models.load([(x['provider_name'],x['model_key'],x['display_name'],x['context_length'] or '—','Yes' if x['multimodal'] else 'No','Yes' if x['tool_capable'] else 'No','Yes' if x['enabled'] else 'No',x['model_id']) for x in self.service.models()]);self.mcp.load([(x['code'],x['display_name'],x['transport'],x['endpoint_or_command'],x['locality'],'Yes' if x['internet_capable'] else 'No','Yes' if x['enabled'] else 'No',x['server_id']) for x in self.service.mcp_servers()])
  with self.service._connect() as cx:
   approvals=[dict(x) for x in cx.execute('SELECT * FROM ai_network_approvals ORDER BY created_at_us DESC')];audit=[dict(x) for x in cx.execute('SELECT * FROM ai_platform_audit ORDER BY occurred_at_us DESC LIMIT 500')]
  self.approvals.load([(f"{x['subject_type']}:{x['subject_id']}",x['project_id'] or 'All',x['purpose_code'] or 'All',x['max_sensitivity'],x['approved_by'],x['reason'],datetime.fromtimestamp(x['valid_until_us']/1e6).isoformat(timespec='minutes') if x['valid_until_us'] else 'No expiry',x['approval_id']) for x in approvals]);self.audit.load([(datetime.fromtimestamp(x['occurred_at_us']/1e6).isoformat(timespec='seconds'),x['actor_id'],x['event_type'],f"{x['entity_type']}:{x['entity_id']}",x['details_json'],x['audit_id']) for x in audit])
 def _offline_changed(self,value):
  try:self.service.set_offline_only(bool(value),self._actor());self.refresh()
  except Exception as exc:self.offline.blockSignals(True);self.offline.setChecked(self.service.offline_only());self.offline.blockSignals(False);QMessageBox.warning(self,'AI network policy',str(exc))
 def _ask(self,title,label,default=''):
  return QInputDialog.getText(self,title,label,text=default)
 def _add_provider(self):
  code,ok=self._ask('Provider','Code','lm-studio-custom');
  if not ok or not code.strip():return
  name,ok=self._ask('Provider','Display name','LM Studio');
  if not ok:return
  ptype,ok=QInputDialog.getItem(self,'Provider','Type',('openai_compatible','native','custom'),0,False);
  if not ok:return
  endpoint,ok=self._ask('Provider','Endpoint','http://127.0.0.1:1234/v1');
  if not ok:return
  locality,ok=QInputDialog.getItem(self,'Provider','Locality',('local','lan','remote'),0,False);
  if not ok:return
  try:self.service.save_provider(code=code.strip(),display_name=name.strip(),provider_type=ptype,endpoint=endpoint.strip(),locality=locality,network_required=locality!='local',actor_id=self._actor());self.refresh()
  except Exception as exc:QMessageBox.warning(self,'Provider',str(exc))
 def _selected_id(self,table):
  items=table.selectedItems();return table.item(items[0].row(),table.columnCount()-1).text() if items else ''
 def _add_model(self):
  providers=self.service.providers();
  if not providers:QMessageBox.information(self,'Model','Create a provider first.');return
  label,ok=QInputDialog.getItem(self,'Model','Provider',tuple(x['display_name'] for x in providers),0,False);
  if not ok:return
  provider=next(x for x in providers if x['display_name']==label);key,ok=self._ask('Model','Model key (as exposed by provider)','hermes-3');
  if not ok or not key.strip():return
  name,ok=self._ask('Model','Display name',key);
  if not ok:return
  try:self.service.save_model(provider_id=provider['provider_id'],model_key=key.strip(),display_name=name.strip(),actor_id=self._actor(),tool_capable=True);self.refresh()
  except Exception as exc:QMessageBox.warning(self,'Model',str(exc))
 def _add_mcp(self):
  code,ok=self._ask('MCP server','Code','fieldora-local');
  if not ok or not code.strip():return
  name,ok=self._ask('MCP server','Display name','Fieldora local MCP');
  if not ok:return
  transport,ok=QInputDialog.getItem(self,'MCP server','Transport',('http','stdio'),0,False);
  if not ok:return
  endpoint,ok=self._ask('MCP server','Endpoint or command','http://127.0.0.1:8765/mcp');
  if not ok:return
  locality,ok=QInputDialog.getItem(self,'MCP server','Locality',('local','lan','remote'),0,False);
  if not ok:return
  try:self.service.save_mcp_server(code=code.strip(),display_name=name.strip(),transport=transport,endpoint_or_command=endpoint.strip(),locality=locality,internet_capable=locality=='remote',actor_id=self._actor());self.refresh()
  except Exception as exc:QMessageBox.warning(self,'MCP server',str(exc))
 def _approve_provider(self):
  pid=self._selected_id(self.providers)
  if not pid:QMessageBox.information(self,'Network approval','Select a provider on the Providers tab first.');return
  reason,ok=self._ask('Network approval','Reason for allowing network access');
  if not ok or not reason.strip():return
  try:self.service.approve_network(subject_type='provider',subject_id=pid,actor_id=self._actor(),reason=reason.strip());self.refresh()
  except Exception as exc:QMessageBox.warning(self,'Network approval',str(exc))
 def _test_selected_provider(self):
  pid=self._selected_id(self.providers)
  if not pid:QMessageBox.information(self,'Provider','Select a provider.');return
  try:QMessageBox.information(self,'Provider test',self.service.test_provider(pid))
  except Exception as exc:QMessageBox.warning(self,'Provider test',str(exc))


class Knowledge(Page):
 def __init__(self,enrichment,parent=None):
  super().__init__('Knowledge & AI',('▷  Run analysis','AI Review'),parent);self.db=enrichment;self.tabs((('Review queue',None,'review'),('Accepted knowledge',None,'accepted'),('Taxonomy','Taxonomy','taxonomy'),('Models','Models','models')),'v5/knowledge_tab');self.table=DataTable(('Subject','Enrichment','Producer','Confidence','State','Assigned to','Updated'));self.body.addWidget(self.table,1);self.refresh();self.tools((('AI Chat & MCP','Provider-neutral governed chat with local and approved remote models','AI Chat & MCP'),('Import GBIF','Backbone and Darwin Core import','Taxonomy Resources'),('Regional knowledge','Regional GBIF acquisition','Regional Knowledge'),('AI resources','CPU/CUDA and processing','AI Resources'),('Sources','Human, AI and reference providers','Knowledge Sources'),('Observation.org exchange','OAuth, validation, media and provenance','Export')))
 def refresh(self):
  rows=many(self.db,"""SELECT e.subject_public_id,e.enrichment_type,e.producer_id,CASE WHEN e.confidence IS NULL THEN '' ELSE ROUND(e.confidence*100)||'%' END,e.status,COALESCE(a.assigned_to,''),datetime(e.updated_at_us/1000000,'unixepoch') FROM enrichment_records e LEFT JOIN enrichment_review_assignments a ON a.enrichment_id=e.enrichment_id ORDER BY e.updated_at_us DESC LIMIT 500""");state=str(QSettings().value('v5/knowledge_tab','review'));rows=[row for row in rows if state not in ('review','accepted') or (state=='accepted' and str(row[4]) in ('accepted','approved')) or (state=='review' and str(row[4]) not in ('accepted','approved','rejected'))];self.table.load(rows);self.table.filter_text(self.search_text())
class Home(Page):
 def __init__(self,library,science,enrichment,parent=None):
  super().__init__('Good morning',('＋  Import evidence','Imports'),parent);self.library=library;self.science=science;self.enrichment=enrichment;self.metrics=QHBoxLayout();self.metric_labels=[]
  for title in ('Library assets','Open project tasks','AI reviews','Projects'):
   frame=QFrame();frame.setObjectName('card');box=QVBoxLayout(frame);box.addWidget(self.label(title));value=self.label('0','value');box.addWidget(value);self.metric_labels.append(value);self.metrics.addWidget(frame)
  self.body.addLayout(self.metrics);self.recent=DataTable(('Recent work','Type','Status','Updated','Context id'));self.recent.setColumnHidden(4,True);self.recent.itemDoubleClicked.connect(self._open_recent);self.body.addWidget(self.recent,1);self.tools((('Start observation','Location, evidence and measurements','__observation_new__'),('Start project','Area, tasks and team','Science Projects'),('Review identifications','AI and specialist assertions','AI Review'),('Asset & equipment operations','Facilities, storage, maintenance and calibration','Asset & Equipment Operations'),('Help & guides','Manuals, shortcuts and troubleshooting','Help & Guides')));self.refresh()
 def refresh(self):
  values=(scalar(self.library,"SELECT COUNT(*) FROM assets WHERE lifecycle_state='active'"),scalar(self.science,"SELECT COUNT(*) FROM pm_tasks WHERE progress<100"),scalar(self.enrichment,"SELECT COUNT(*) FROM enrichment_records WHERE status IN ('generated','pending_review')"),scalar(self.science,"SELECT COUNT(*) FROM pm_projects"))
  for label,value in zip(self.metric_labels,values):label.setText(str(value[0] if value else 0))
  rows=[]
  rows += [(r[0],'Project',r[1],r[2],r[3]) for r in many(self.science,"SELECT name,status,datetime(updated_at_us/1000000,'unixepoch'),project_id FROM pm_projects ORDER BY updated_at_us DESC LIMIT 5")]
  rows += [(r[0] or r[1],'Evidence',r[2],r[3],r[4]) for r in many(self.library,"""SELECT a.title,f.normalized_path,a.media_type,datetime(a.modified_at_us/1000000,'unixepoch'),a.public_id FROM assets a LEFT JOIN file_instances f ON f.id=a.primary_file_instance_id WHERE a.lifecycle_state='active' ORDER BY a.modified_at_us DESC LIMIT 5""")]
  self.recent.load(rows[:10]);self.recent.filter_text(self.search_text())
 def _open_recent(self,item):
  row=item.row();kind=self.recent.item(row,1).text();identity=self.recent.item(row,4).text();self.route_requested.emit(('__project_open__:' if kind=='Project' else '__asset_open__:')+identity)

class AdministrationGovernance(Page):
 def __init__(self,science,parent=None,actor_provider=None):
  super().__init__('Administration governance',None,parent);self.service=Phase4AdministrationService(science);self.actor_provider=actor_provider or (lambda:os.environ.get('FIELDORA_IDENTITY_ID','local-user'))
  intro=QFrame();intro.setObjectName('panel');il=QVBoxLayout(intro);il.addWidget(self.label('Governed configuration','head'));il.addWidget(self.label('Manage roles, parties, units, instruments, laboratories, scientific templates, workflow transitions, OAuth/SAML providers and enrichment-asset policies. All changes record the responsible user.'));self.body.addWidget(intro)
  self.tabs=QTabWidget();self.tables={};self.admin_buttons=[]
  specs={
   'roles':('Code','Name','Scope','Active','Permissions','ID'),
   'parties':('Type','Party','Organisation','Email','Active','ID'),
   'units':('Code','Symbol','Name','Quantity','Factor','Active','ID'),
   'instruments':('Instrument','Type','Manufacturer / model','Serial','Status','ID'),
   'laboratories':('Laboratory','Party','Accreditation','Contact','Active','ID'),
   'templates':('Type','Code','Name','Version','State','Taxon rule','ID'),
   'workflow_transitions':('Domain','From','To','Role / permission','Approval','Active','ID'),
   'identity_providers':('Type','Provider','Issuer / metadata','Client ID','Enabled','ID'),
   'security_attributes':('Code','Attribute','Type','Default','Inheritance','Active','ID'),
   'purposes':('Code','Purpose','Legal basis','Selection required','Active','ID'),
   'asset_policies':('Policy','Effect','Role','Action','Asset / purpose','State','ID'),
   'access_matrices':('Matrix','Principal','Resource','Project / scope','Representation','CRUD + functions','ID'),
  }
  labels={'roles':'Roles & permissions','parties':'Party directory','units':'Units','instruments':'Instruments & calibration','laboratories':'Laboratories','templates':'Scientific templates','workflow_transitions':'Workflow transitions','identity_providers':'OAuth / SAML','security_attributes':'Asset attributes','purposes':'Purposes','asset_policies':'Asset policies','access_matrices':'Access matrices'}
  for domain,headers in specs.items():
   panel=QWidget();layout=QVBoxLayout(panel);row=QHBoxLayout();add=QPushButton('Add or update');add.setObjectName('primary');add.clicked.connect(lambda _=False,d=domain:self._add(d));row.addWidget(add)
   if domain=='instruments':cal=QPushButton('Record calibration');cal.setObjectName('tool');cal.clicked.connect(self._calibrate);row.addWidget(cal);self.admin_buttons.append(cal)
   if domain=='asset_policies':sim=QPushButton('Simulate access');sim.setObjectName('tool');sim.clicked.connect(self._simulate);row.addWidget(sim);self.admin_buttons.append(sim);sec=QPushButton('Classify asset');sec.setObjectName('tool');sec.clicked.connect(self._classify);row.addWidget(sec);self.admin_buttons.append(sec)
   if domain=='access_matrices':sim=QPushButton('Effective access');sim.setObjectName('tool');sim.clicked.connect(self._simulate_matrix);row.addWidget(sim);self.admin_buttons.append(sim)
   row.addStretch();layout.addLayout(row);table=DataTable(headers);layout.addWidget(table);self.tables[domain]=table;self.tabs.addTab(panel,labels[domain])
  audit_panel=QWidget();al=QVBoxLayout(audit_panel);self.audit=DataTable(('Time','User','Event','Entity','Reason','ID'));al.addWidget(self.audit);self.tabs.addTab(audit_panel,'Administration audit');self.body.addWidget(self.tabs,1);self.refresh()
 def _context_event(self,event):
  if event.source=='research-operations':return
  if event.topic in {'identity.changed','permissions.changed'}:self.refresh()
  elif event.topic=='project.changed' and event.project_id:
   idx=self.combo.findData(event.project_id)
   if idx>=0:self.combo.setCurrentIndex(idx)
  elif event.topic=='data.changed' and (not event.project_id or event.project_id==str(self.combo.currentData() or '')):self._changed(self.combo.currentIndex())
 def _actor(self):return str(self.actor_provider() or 'local-user')
 def refresh(self):
  for domain,table in self.tables.items():
   rows=self.service.list_domain(domain);out=[]
   for x in rows:
    if domain=='roles':out.append((x['code'],x['display_name'],x['scope'],'Yes' if x['active'] else 'No',x.get('permissions') or '',x['role_id']))
    elif domain=='parties':out.append((x['party_type'],x['display_name'],x['organisation_id'],x['email'],'Yes' if x['active'] else 'No',x['party_id']))
    elif domain=='units':out.append((x['code'],x['symbol'],x['display_name'],x['quantity_kind'],x['factor'],'Yes' if x['active'] else 'No',x['unit_id']))
    elif domain=='instruments':out.append((x['name'],x['instrument_type'],f"{x['manufacturer']} {x['model']}".strip(),x['serial_number'],x['status'],x['instrument_id']))
    elif domain=='laboratories':out.append((x['display_name'],x['party_id'],x['accreditation'],x['contact'],'Yes' if x['active'] else 'No',x['laboratory_id']))
    elif domain=='templates':out.append((x['template_type'],x['code'],x['display_name'],x['version'],x['state'],x['taxon_rule'],x['template_id']))
    elif domain=='workflow_transitions':out.append((x['domain'],x['from_status'],x['to_status'],x['required_role'] or x['required_permission'],'Yes' if x['requires_approval'] else 'No','Yes' if x['active'] else 'No',x['transition_id']))
    elif domain=='identity_providers':out.append((x['provider_type'],x['display_name'],x['issuer'] or x['metadata_url'],x['client_id'],'Yes' if x['enabled'] else 'No',x['provider_id']))
    elif domain=='security_attributes':out.append((x['code'],x['display_name'],x['value_type'],x['default_value'],x['inheritance_mode'],'Yes' if x['active'] else 'No',x['attribute_id']))
    elif domain=='purposes':out.append((x['code'],x['display_name'],x['legal_basis'],'Yes' if x['requires_selection'] else 'No','Yes' if x['active'] else 'No',x['purpose_id']))
    elif domain=='asset_policies':out.append((x['display_name'],x['effect'],x['role_code'],x['action_code'],f"{x['asset_type']} / {x['purpose_code']}",x['state'],x['policy_id']))
    elif domain=='access_matrices':
     perms=[n for n in ('create','read','update','delete','assign','review','approve','export','publish','aggregate') if x.get(n+'_allowed')]
     out.append((x['display_name'],f"{x['principal_type']}:{x['principal_id'] or '*'}",x['resource_type'],f"{x['project_id'] or '*'} / {x['data_scope']}",x['representation'],', '.join(perms),x['rule_id']))
   table.load(out);table.filter_text(self.search_text())
  self.audit.load([(datetime.fromtimestamp(x['created_at_us']/1_000_000).isoformat(timespec='seconds'),x['actor_id'],x['event_type'],f"{x['entity_type']}:{x['entity_id']}",x['reason'],x['audit_id']) for x in self.service.audit_events()])
 def _text(self,title,label,default=''):
  value,ok=QInputDialog.getText(self,title,label,text=str(default));return (value.strip(),ok)
 def _choice(self,title,label,items,default=0):return QInputDialog.getItem(self,title,label,items,default,False)
 def _json(self,text,default):
  if not text.strip():return default
  return json.loads(text)
 def _add(self,domain):
  try:
   if domain=='roles':
    code,ok=self._text('Role','Code');
    if not ok or not code:return
    name,ok=self._text('Role','Display name');
    if not ok or not name:return
    permissions,ok=self._text('Role','Permissions (comma separated)','asset.metadata.view, asset.preview.view');
    if not ok:return
    self.service.save_role(code=code,display_name=name,permissions=[x.strip() for x in permissions.split(',')],actor_id=self._actor())
   elif domain=='parties':
    typ,ok=self._choice('Party','Party type',('person','organisation','laboratory','courier','field_team'));
    if not ok:return
    name,ok=self._text('Party','Display name');
    if not ok or not name:return
    email,ok=self._text('Party','Email');
    if not ok:return
    identity,ok=self._text('Party','Linked user / identity ID');
    if not ok:return
    self.service.save(domain,{'party_type':typ,'display_name':name,'email':email,'linked_identity_id':identity},actor_id=self._actor())
   elif domain=='units':
    code,ok=self._text('Unit','Code');
    if not ok or not code:return
    symbol,ok=self._text('Unit','Symbol',code);
    if not ok:return
    name,ok=self._text('Unit','Display name');
    if not ok or not name:return
    kind,ok=self._text('Unit','Quantity kind (length, mass, temperature, …)');
    if not ok or not kind:return
    factor,ok=QInputDialog.getDouble(self,'Unit','Factor to canonical SI unit',1,0,1e18,12);
    if not ok:return
    self.service.save(domain,{'code':code,'symbol':symbol,'display_name':name,'quantity_kind':kind,'factor':factor},actor_id=self._actor())
   elif domain=='instruments':
    name,ok=self._text('Instrument','Name');
    if not ok or not name:return
    typ,ok=self._text('Instrument','Type');
    if not ok or not typ:return
    manufacturer,ok=self._text('Instrument','Manufacturer');
    if not ok:return
    model,ok=self._text('Instrument','Model');
    if not ok:return
    serial,ok=self._text('Instrument','Serial number');
    if not ok:return
    self.service.save(domain,{'name':name,'instrument_type':typ,'manufacturer':manufacturer,'model':model,'serial_number':serial},actor_id=self._actor())
   elif domain=='laboratories':
    name,ok=self._text('Laboratory','Display name');
    if not ok or not name:return
    party,ok=self._text('Laboratory','Party ID');
    if not ok:return
    accreditation,ok=self._text('Laboratory','Accreditation');
    if not ok:return
    capabilities,ok=self._text('Laboratory','Capabilities (comma separated)');
    if not ok:return
    self.service.save(domain,{'display_name':name,'party_id':party,'accreditation':accreditation,'capabilities':[x.strip() for x in capabilities.split(',') if x.strip()]},actor_id=self._actor())
   elif domain=='templates':
    typ,ok=self._choice('Template','Type',('protocol','measurement','enrichment','laboratory'));
    if not ok:return
    code,ok=self._text('Template','Code');
    if not ok or not code:return
    name,ok=self._text('Template','Display name');
    if not ok:return
    taxon,ok=self._text('Template','Taxon applicability rule');
    if not ok:return
    definition,ok=QInputDialog.getMultiLineText(self,'Template','Definition JSON','{}');
    if not ok:return
    self.service.save(domain,{'template_type':typ,'code':code,'display_name':name,'taxon_rule':taxon,'definition':self._json(definition,{})},actor_id=self._actor())
   elif domain=='workflow_transitions':
    dom,ok=self._text('Workflow transition','Domain (sample, survey_event, laboratory, …)');
    if not ok or not dom:return
    before,ok=self._text('Workflow transition','From status');
    if not ok:return
    after,ok=self._text('Workflow transition','To status');
    if not ok:return
    role,ok=self._text('Workflow transition','Required role');
    if not ok:return
    approval=QMessageBox.question(self,'Workflow transition','Require approval?')==QMessageBox.StandardButton.Yes
    self.service.save(domain,{'domain':dom,'from_status':before,'to_status':after,'required_role':role,'requires_approval':approval},actor_id=self._actor())
   elif domain=='identity_providers':
    typ,ok=self._choice('Identity provider','Protocol',('oidc','oauth2','saml2'));
    if not ok:return
    name,ok=self._text('Identity provider','Display name');
    if not ok:return
    issuer,ok=self._text('Identity provider','Issuer / entity ID');
    if not ok:return
    metadata,ok=self._text('Identity provider','Discovery / metadata URL');
    if not ok:return
    client,ok=self._text('Identity provider','Client ID');
    if not ok:return
    secret,ok=self._text('Identity provider','Secret-store reference (never the raw secret)');
    if not ok:return
    self.service.save(domain,{'provider_type':typ,'display_name':name,'issuer':issuer,'metadata_url':metadata,'client_id':client,'secret_reference':secret},actor_id=self._actor())
   elif domain=='security_attributes':
    code,ok=self._text('Asset attribute','Code');
    if not ok or not code:return
    name,ok=self._text('Asset attribute','Display name');
    if not ok:return
    values,ok=self._text('Asset attribute','Allowed values (comma separated)');
    if not ok:return
    self.service.save(domain,{'code':code,'display_name':name,'allowed_values':[x.strip() for x in values.split(',') if x.strip()]},actor_id=self._actor())
   elif domain=='purposes':
    code,ok=self._text('Purpose','Code');
    if not ok or not code:return
    name,ok=self._text('Purpose','Display name');
    if not ok:return
    legal,ok=self._text('Purpose','Legal basis / policy reference');
    if not ok:return
    self.service.save(domain,{'code':code,'display_name':name,'legal_basis':legal},actor_id=self._actor())
   elif domain=='access_matrices':
    name,ok=self._text('Access matrix','Display name');
    if not ok or not name:return
    ptype,ok=self._choice('Access matrix','Principal type',('user','role','team','all'));
    if not ok:return
    principal,ok=self._text('Access matrix','User, role or team identifier (* for all)','*');
    if not ok:return
    resource,ok=self._text('Access matrix','Resource type','project');
    if not ok or not resource:return
    project,ok=self._text('Access matrix','Project ID (blank for all permitted projects)','');
    if not ok:return
    scope,ok=self._choice('Access matrix','Data scope',('user','team','project','organisation','all'));
    if not ok:return
    representation,ok=self._choice('Access matrix','Maximum representation',('individual','aggregated','anonymized','statistical','export'));
    if not ok:return
    permissions,ok=self._text('Access matrix','Allowed actions (comma separated)','create, read, update, delete, assign, review, approve, export, publish, aggregate');
    if not ok:return
    allowed={x.strip().lower():True for x in permissions.split(',') if x.strip()}
    self.service.save_access_matrix(actor_id=self._actor(),display_name=name,principal_type=ptype,principal_id='' if principal=='*' else principal,resource_type=resource,project_id=project,data_scope=scope,representation=representation,permissions=allowed)
   elif domain=='asset_policies':
    name,ok=self._text('Asset policy','Display name');
    if not ok:return
    effect,ok=self._choice('Asset policy','Effect',('deny','allow'));
    if not ok:return
    role,ok=self._text('Asset policy','Role code');
    if not ok:return
    action,ok=self._text('Asset policy','Action (asset.preview.view, asset.export, ai.training, …)');
    if not ok:return
    asset_type,ok=self._text('Asset policy','Asset type or *','*');
    if not ok:return
    purpose,ok=self._text('Asset policy','Purpose code or *','*');
    if not ok:return
    conditions,ok=QInputDialog.getMultiLineText(self,'Asset policy','ABAC conditions JSON','{}');
    if not ok:return
    state,ok=self._choice('Asset policy','State',('draft','active','retired'));
    if not ok:return
    self.service.save(domain,{'display_name':name,'effect':effect,'role_code':role,'action_code':action,'asset_type':asset_type,'purpose_code':purpose,'conditions':self._json(conditions,{}),'state':state},actor_id=self._actor())
   self.refresh()
  except Exception as e:QMessageBox.warning(self,'Administration',str(e))
 def _selected_id(self,domain):
  identity=self.tables[domain].selected_id();
  if not identity:QMessageBox.information(self,'Administration',f'Select a {domain.replace("_"," ")} row first.')
  return identity
 def _calibrate(self):
  iid=self._selected_id('instruments');
  if not iid:return
  date,ok=get_datetime_text(self,'Calibration','Calibrated date/time',value=datetime.now().strftime('%Y-%m-%d %H:%M'));
  if not ok:return
  result,ok=self._choice('Calibration','Result',('passed','limited','failed'));
  if not ok:return
  due,ok=self._text('Calibration','Next due');
  if not ok:return
  try:self.service.calibrate_instrument(iid,actor_id=self._actor(),result=result,calibrated_at=date,next_due=due);self.refresh()
  except Exception as e:QMessageBox.warning(self,'Calibration',str(e))
 def _classify(self):
  asset,ok=self._text('Asset security','Asset ID');
  if not ok or not asset:return
  sensitivity,ok=self._choice('Asset security','Sensitivity',('public','internal','protected','restricted'));
  if not ok:return
  purposes,ok=self._text('Asset security','Permitted purposes (comma separated)','scientific_research');
  if not ok:return
  attrs,ok=QInputDialog.getMultiLineText(self,'Asset security','Classifications JSON','{}');
  if not ok:return
  try:self.service.set_asset_security(asset,actor_id=self._actor(),owner_user_id=self._actor(),sensitivity=sensitivity,purposes=[x.strip() for x in purposes.split(',') if x.strip()],classifications=self._json(attrs,{}));self.refresh()
  except Exception as e:QMessageBox.warning(self,'Asset security',str(e))
 def _simulate_matrix(self):
  user,ok=self._text('Effective access','User ID',self._actor());
  if not ok:return
  role,ok=self._text('Effective access','Role','researcher');
  if not ok:return
  action,ok=self._choice('Effective access','Action',('create','read','update','delete','assign','review','approve','export','publish','aggregate'));
  if not ok:return
  resource,ok=self._text('Effective access','Resource type','project');
  if not ok:return
  project,ok=self._text('Effective access','Project ID','');
  if not ok:return
  representation,ok=self._choice('Effective access','Requested representation',('individual','aggregated','anonymized','statistical','export'));
  if not ok:return
  result=self.service.evaluate_access_matrix(actor_id=user,role_code=role,action=action,resource_type=resource,project_id=project,representation=representation)
  QMessageBox.information(self,'Effective access',f"{'ALLOWED' if result.allowed else 'DENIED'}\nDetail visible: {'Yes' if result.detail_visible else 'No'}\nAggregate allowed: {'Yes' if result.aggregate_allowed else 'No'}\n\n{result.reason}")
 def _simulate(self):
  asset,ok=self._text('Policy simulation','Asset ID');
  if not ok:return
  role,ok=self._text('Policy simulation','Role code','researcher');
  if not ok:return
  action,ok=self._text('Policy simulation','Action','asset.preview.view');
  if not ok:return
  purpose,ok=self._text('Policy simulation','Purpose','scientific_research');
  if not ok:return
  try:
   result=self.service.evaluate_asset_access(asset_id=asset,role_code=role,action_code=action,purpose_code=purpose)
   QMessageBox.information(self,'Policy simulation',f"{'ALLOWED' if result.allowed else 'DENIED'}\n\n{result.reason}\n\nMatched policies: {', '.join(result.matched_policy_ids) or 'none'}")
  except Exception as e:QMessageBox.warning(self,'Policy simulation',str(e))

class Administration(Page):
 def __init__(self,library,science,enrichment,parent=None):
  super().__init__('Administration',('Run health check','Health Check'),parent);self.library=library;self.science=science;self.enrichment=enrichment;status=QFrame();status.setObjectName('panel');layout=QVBoxLayout(status);layout.addWidget(self.label('System health','head'));self.health=QLabel();self.health.setWordWrap(True);layout.addWidget(self.health);self.body.addWidget(status);self.tools((('Storage & libraries','Databases and originals','Storage Manager'),('Back up library','Create a verified library backup','__backup__'),('Restore library','Verify and stage a backup restoration','__restore__'),('Operations Center','Running, queued, completed and failed jobs','Activity Center'),('Screens & modules','Show or hide Library and Science workspaces','Library Types'),('AI & source switches','Enable or disable GBIF and BioCLIP components','Resource Components'),('AI models','Installations and runtime','Models'),('Offline maps','StreetMaps packages','Offline Maps'),('Users & access','Roles and authorities','Access & Contracts'),('Local users & profiles','Evaluation users and copyable permission profiles','Local Profiles'),('Governance & security','Roles, parties, workflows, OAuth/SAML and asset policies','Administration Governance'),('Platform parity','Windows, Linux and server feature coverage','Platform Parity'),('Asset & equipment operations','Facilities, storage, maintenance and calibration','Asset & Equipment Operations'),('AI Platform','Providers, models, MCP servers and offline network policy','AI Platform Administration'),('Research reference data','Manage statuses, parties, modalities and workflow values','Research Reference Data'),('Integrations','API connections','Integrations'),('Taxonomy resources','GBIF packages','Taxonomy Resources'),('Diagnostics','Support and logs','Diagnostics'),('Updates','Offline releases','Updates'),('Preferences','Display and storage','Preferences'),('Help & guides','Searchable manuals','Help & Guides')));self.refresh()
 def refresh(self):
  states=[]
  for name,path in (('Library',self.library),('Science',self.science),('Enrichment',self.enrichment)):
   result=scalar(path,'PRAGMA integrity_check');states.append((name,result and result[0]=='ok',Path(path).stat().st_size if Path(path).is_file() else 0))
  self.health.setText('<br>'.join(f'<b>{name}</b>: {"Healthy" if ok else "Needs attention"} · {size/1048576:.1f} MB' for name,ok,size in states)+f'<br><br><b>Version</b>: Fieldora 5.4.0')

class PlatformParity(Page):
 def __init__(self,parent=None):
  super().__init__('Platform feature registry & parity',None,parent);self.summary=QLabel();self.summary.setWordWrap(True);self.body.addWidget(self.summary);self.filter=QComboBox();self.filter.addItems(('All modules',)+tuple(sorted({f.module for f in feature_registry()})));self.filter.currentTextChanged.connect(self.refresh);self.header.insertWidget(1,self.filter);self.table=QTableWidget(0,8);self.table.setHorizontalHeaderLabels(('Feature','Module','Windows','Linux','Server','Permission','Certified','Evidence required'));self.table.horizontalHeader().setStretchLastSection(True);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.body.addWidget(self.table,1);self.refresh()
 def refresh(self,*_):
  payload=parity_payload()['platforms'];self.summary.setText(' · '.join(f"<b>{name.replace('_',' ').title()}</b>: {value['implemented']}/{value['total']} implemented, {value['partial']} partial, {value['missing']} missing" for name,value in payload.items()));module=self.filter.currentText() if hasattr(self,'filter') else 'All modules';rows=[f for f in feature_registry() if module=='All modules' or f.module==module];self.table.setRowCount(len(rows))
  for r,feature in enumerate(rows):
   implementations={item.platform.value:item for item in feature.implementations};certified=all(item.certified for item in feature.implementations);evidence='; '.join(sorted({item.evidence_required for item in feature.implementations}));values=(feature.name,feature.module,implementations['windows_desktop'].status.value,implementations['linux_desktop'].status.value,implementations['server'].status.value,feature.permission,'Yes' if certified else 'No',evidence)
   for c,value in enumerate(values):self.table.setItem(r,c,QTableWidgetItem(str(value)))

class ResearchReferenceData(Page):
 def __init__(self,science,parent=None,actor_provider=None):
  super().__init__('Research reference data',None,parent);self.service=ProjectManagementService(science);self.actor_provider=actor_provider or (lambda:os.environ.get('FIELDORA_IDENTITY_ID','local-user'));self.domain=QComboBox();self.domain.addItems(('specimen_status','sample_type','sample_status','survey_event_status','laboratory_status','laboratory_record_type','custody_status','custody_action','party','identifier_type','media_type','modality','enrichment_status','encounter_type','encounter_status'));self.domain.currentTextChanged.connect(self.refresh);self.header.insertWidget(1,self.domain);add=QPushButton('Add or update value');add.setObjectName('primary');add.clicked.connect(self._add);add.setEnabled(os.environ.get('FIELDORA_PROFILE_ROLE')=='administrator');add.setToolTip('Administrator permission required' if not add.isEnabled() else '');self.header.addWidget(add);self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(('Code','Display name','Active','System','ID'));self.table.horizontalHeader().setStretchLastSection(True);self.body.addWidget(self.table,1);self.refresh()
 def refresh(self,*_):
  rows=self.service.reference_values(self.domain.currentText(),active_only=False);self.table.setRowCount(len(rows))
  for r,x in enumerate(rows):
   for c,v in enumerate((x['code'],x['display_name'],'Yes' if x['active'] else 'No','Yes' if x['system_value'] else 'No',x['value_id'])):self.table.setItem(r,c,QTableWidgetItem(str(v)))
 def _add(self):
  code,ok=QInputDialog.getText(self,'Reference value','Code');
  if not ok or not code.strip():return
  name,ok=QInputDialog.getText(self,'Reference value','Display name');
  if not ok or not name.strip():return
  try:self.service.save_reference_value(self.domain.currentText(),code,name,actor_id=str(self.actor_provider() or 'local-user'))
  except Exception as e:QMessageBox.warning(self,'Reference value',str(e));return
  self.refresh()

class AssetEquipmentOperations(Page):
 def __init__(self,science,parent=None):
  super().__init__('Asset, Equipment & Facilities Operations',None,parent);self.db=Path(science);self.service=OperationsAssetService(self.db);self.actor=lambda:os.environ.get('FIELDORA_IDENTITY_ID','local-user');self.role=lambda:os.environ.get('FIELDORA_PROFILE_ROLE','administrator');self.tabs_widget=QTabWidget();self.body.addWidget(self.tabs_widget,1);self.action_buttons={}
  self.asset_table=DataTable(('Code','Name','Category','Status','Location','Image'));self.location_table=DataTable(('Path','Type','Code','Name','Conditions'));self.drawing_table=DataTable(('Title','Format','Version','Location','Markers','Source'));self.maintenance_table=DataTable(('Asset','Type','Status','Provider','Result'));self.calibration_table=DataTable(('Asset','Status','Standard','Result','Valid until'))
  self._tables=(self.asset_table,self.location_table,self.drawing_table,self.maintenance_table,self.calibration_table)
  for title,table in (('Equipment & assets',self.asset_table),('Facilities & storage',self.location_table),('Building drawings',self.drawing_table),('Maintenance',self.maintenance_table),('Calibration',self.calibration_table)):
   page=QWidget();layout=QVBoxLayout(page);split=QSplitter();split.addWidget(table);details=QTextBrowser();details.setMinimumWidth(310);split.addWidget(details);split.setStretchFactor(0,3);split.setStretchFactor(1,2);layout.addWidget(split,1);row=QHBoxLayout()
   actions={'Equipment & assets':(('New asset',self._new_asset,'create','asset'),('Open / edit',self._open_asset,'update','asset'),('Move asset',self._move_asset,'update','movement'),('Add image',self._add_image,'update','asset'),('Documents',self._asset_documents,'read','document')),'Facilities & storage':(('New location',self._new_location,'create','location'),('Open / edit',self._open_location,'update','location'),('Add storage conditions',self._add_condition,'create','storage_condition')),'Building drawings':(('Add drawing',self._add_drawing,'create','drawing'),('Open drawing',self._open_drawing,'read','drawing'),('Place location code',self._add_marker,'update','drawing')),'Maintenance':(('New maintenance',self._new_maintenance,'create','maintenance'),('Open / complete',self._open_maintenance,'update','maintenance')),'Calibration':(('New calibration',self._new_calibration,'create','calibration'),('Open / record result',self._open_calibration,'update','calibration'))}[title]
   for label,handler,action,kind in actions:
    b=QPushButton(label);b.setObjectName('primary' if label.startswith('New') or label.startswith('Add drawing') else 'tool');b.clicked.connect(handler);row.addWidget(b);self.action_buttons[label]=(b,action,kind)
   row.addStretch();layout.addLayout(row);self.tabs_widget.addTab(page,title);table.itemSelectionChanged.connect(lambda t=table,d=details:self._selection_changed(t,d));table.itemDoubleClicked.connect(lambda _item,t=table:self._open_for_table(t))
  self.tabs_widget.currentChanged.connect(lambda _index:self._update_actions());self.refresh();self._update_actions()
 def _allowed(self,action,kind):
  try:return self.service.can(action,kind,self.actor())
  except Exception:return False
 def _update_actions(self):
  selected={'asset':bool(self.asset_table.selectedItems()),'location':bool(self.location_table.selectedItems()),'drawing':bool(self.drawing_table.selectedItems()),'maintenance':bool(self.maintenance_table.selectedItems()),'calibration':bool(self.calibration_table.selectedItems()),'document':bool(self.asset_table.selectedItems()),'movement':bool(self.asset_table.selectedItems())}
  needs_selection={'Open / edit','Move asset','Add image','Documents','Open drawing','Place location code','Open / complete','Open / record result'}
  for label,(button,action,kind) in self.action_buttons.items():button.setEnabled(self._allowed(action,kind) and (label not in needs_selection or selected.get(kind,False)))
 def refresh(self):
  actor=self.actor()
  try:assets=self.service.assets(actor)
  except PermissionError:assets=()
  self._asset_rows=assets;self.asset_table.load([(a['asset_code'],a['name'],a['category'],a['status'],self.service.location_path(a['location_id'],actor) if a['location_id'] else 'Unassigned',Path(a['image_path']).name if a['image_path'] else '') for a in assets])
  try:conditions={};[conditions.setdefault(r['location_id'],[]).append(r['name']) for r in self.service.storage_conditions(actor=actor)];locations=self.service.locations(actor)
  except PermissionError:conditions={};locations=()
  self._location_rows=locations;self.location_table.load([(self.service.location_path(r['id'],actor),r['location_type'],r['code'],r['name'],', '.join(conditions.get(r['id'],()))) for r in locations])
  try:drawings=self.service.drawings(actor);markers=self.service.drawing_markers(actor=actor)
  except PermissionError:drawings=();markers=()
  self._drawing_rows=drawings;marker_counts={};[marker_counts.__setitem__(m['drawing_id'],marker_counts.get(m['drawing_id'],0)+1) for m in markers];self.drawing_table.load([(r['title'],r['source_format'],r['version'],self.service.location_path(r['location_id'],actor) if r['location_id'] else '',str(marker_counts.get(r['id'],0)),r['file_path']) for r in drawings])
  try:maintenance=self.service.maintenance(actor)
  except PermissionError:maintenance=()
  self._maintenance_rows=maintenance;self.maintenance_table.load([(r['asset_code'],r['maintenance_type'],r['status'],r['provider'],r['result']) for r in maintenance])
  try:calibrations=self.service.calibrations(actor)
  except PermissionError:calibrations=()
  self._calibration_rows=calibrations;self.calibration_table.load([(r['asset_code'],r['status'],r['standard_reference'],r['result'],r['valid_until']) for r in calibrations]);self._update_actions()
 def _row_for_table(self,table):
  items=table.selectedItems();idx=items[0].row() if items else -1
  rows={self.asset_table:getattr(self,'_asset_rows',()),self.location_table:getattr(self,'_location_rows',()),self.drawing_table:getattr(self,'_drawing_rows',()),self.maintenance_table:getattr(self,'_maintenance_rows',()),self.calibration_table:getattr(self,'_calibration_rows',())}[table]
  return rows[idx] if 0<=idx<len(rows) else None
 def _selection_changed(self,table,details):
  row=self._row_for_table(table);self._update_actions()
  if not row:details.clear();return
  lines=[]
  for key,value in row.items():
   if key.endswith('_us') and value:
    try:value=datetime.fromtimestamp(int(value)/1_000_000).isoformat(timespec='seconds')
    except Exception:pass
   if value not in (None,''):lines.append(f'<b>{key.replace("_"," ").title()}</b>: {str(value)}')
  if table is self.asset_table:
   try:
    docs=self.service.documents(str(row['id']),self.actor());lines.append(f'<b>Documents</b>: {len(docs)}')
    if row.get('image_path'):lines.append(f'<b>Image</b>: {row["image_path"]}')
   except Exception:pass
  details.setHtml('<br>'.join(lines))
 def _open_for_table(self,table):
  {self.asset_table:self._open_asset,self.location_table:self._open_location,self.drawing_table:self._open_drawing,self.maintenance_table:self._open_maintenance,self.calibration_table:self._open_calibration}[table]()
 def _selected_asset_id(self):
  row=self._row_for_table(self.asset_table)
  if not row:QMessageBox.information(self,'Equipment','Select an asset first.');return ''
  return str(row['id'])
 def _choose_location(self,title='Location',allow_unassigned=True):
  rows=self.service.locations(self.actor());labels=(['Unassigned'] if allow_unassigned else [])+[self.service.location_path(r['id'],self.actor()) for r in rows];choice,ok=QInputDialog.getItem(self,title,'Select location',labels,0,False)
  if not ok:return False,None
  if allow_unassigned and choice=='Unassigned':return True,None
  offset=1 if allow_unassigned else 0;return True,rows[labels.index(choice)-offset]['id']
 def _new_location(self):
  kinds=('institution','site','building','floor','wing','hall','room','zone','cabinet','freezer','rack','compartment','drawer','shelf','box','tray','part');kind,ok=QInputDialog.getItem(self,'New storage location','Type',kinds,0,False)
  if not ok:return
  code,ok=QInputDialog.getText(self,'New storage location','Code / tag')
  if not ok or not code.strip():return
  name,ok=QInputDialog.getText(self,'New storage location','Name')
  if not ok or not name.strip():return
  rows=self.service.locations(self.actor());labels=['Top level']+[self.service.location_path(r['id'],self.actor()) for r in rows];parent,ok=QInputDialog.getItem(self,'New storage location','Parent',labels,0,False)
  if not ok:return
  try:self.service.add_location(kind,code,name,None if parent=='Top level' else rows[labels.index(parent)-1]['id'],actor=self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Storage location',str(e))
 def _open_location(self):
  row=self._row_for_table(self.location_table)
  if not row:return
  name,ok=QInputDialog.getText(self,'Location','Name',text=str(row['name']))
  if not ok:return
  desc,ok=QInputDialog.getMultiLineText(self,'Location','Description',str(row.get('description') or ''))
  if not ok:return
  try:self.service.update_location(str(row['id']),actor=self.actor(),name=name,description=desc,parent_id=row.get('parent_id'));self.refresh()
  except Exception as e:QMessageBox.warning(self,'Location',str(e))
 def _add_condition(self):
  rows=self.service.locations(self.actor())
  if not rows:QMessageBox.information(self,'Storage conditions','Create a location first.');return
  labels=[self.service.location_path(r['id'],self.actor()) for r in rows];choice,ok=QInputDialog.getItem(self,'Storage conditions','Location',labels,0,False)
  if not ok:return
  name,ok=QInputDialog.getText(self,'Storage conditions','Condition profile name')
  if not ok or not name.strip():return
  tmin,ok=QInputDialog.getDouble(self,'Storage conditions','Minimum temperature °C',0,-273,1000,1)
  if not ok:return
  tmax,ok=QInputDialog.getDouble(self,'Storage conditions','Maximum temperature °C',20,-273,1000,1)
  if not ok:return
  hmin,ok=QInputDialog.getDouble(self,'Storage conditions','Minimum humidity %',30,0,100,1)
  if not ok:return
  hmax,ok=QInputDialog.getDouble(self,'Storage conditions','Maximum humidity %',60,0,100,1)
  if not ok:return
  try:self.service.add_storage_condition(rows[labels.index(choice)]['id'],name,tmin,tmax,hmin,hmax,monitoring_required=True,actor=self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Storage conditions',str(e))
 def _new_asset(self):
  code,ok=QInputDialog.getText(self,'New asset','Asset code')
  if not ok or not code.strip():return
  name,ok=QInputDialog.getText(self,'New asset','Name')
  if not ok or not name.strip():return
  category,ok=QInputDialog.getText(self,'New asset','Category')
  if not ok or not category.strip():return
  accepted,location=self._choose_location('Asset location')
  if not accepted:return
  try:self.service.add_asset(code,name,category,self.actor(),location_id=location,owner_id=self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Asset',str(e))
 def _open_asset(self):
  aid=self._selected_asset_id()
  if not aid:return
  try:row=self.service.asset(aid,self.actor())
  except Exception as e:QMessageBox.warning(self,'Asset',str(e));return
  name,ok=QInputDialog.getText(self,'Asset details','Name',text=str(row['name']))
  if not ok:return
  status,ok=QInputDialog.getItem(self,'Asset details','Status',('in_service','out_of_service','maintenance','calibration','retired'),max(0,('in_service','out_of_service','maintenance','calibration','retired').index(row['status']) if row['status'] in ('in_service','out_of_service','maintenance','calibration','retired') else 0),False)
  if not ok:return
  notes,ok=QInputDialog.getMultiLineText(self,'Asset details','Notes',str(row.get('notes') or ''))
  if not ok:return
  try:self.service.update_asset(aid,actor=self.actor(),name=name,status=status,notes=notes);self.refresh()
  except Exception as e:QMessageBox.warning(self,'Asset',str(e))
 def _move_asset(self):
  aid=self._selected_asset_id()
  if not aid:return
  accepted,location=self._choose_location('Move asset to')
  if not accepted:return
  reason,ok=QInputDialog.getText(self,'Move asset','Reason')
  if not ok:return
  try:self.service.move_asset(aid,location,actor=self.actor(),moved_at=datetime.now().isoformat(timespec='seconds'),reason=reason);self.refresh()
  except Exception as e:QMessageBox.warning(self,'Move asset',str(e))
 def _add_image(self):
  aid=self._selected_asset_id()
  if not aid:return
  path,_=QFileDialog.getOpenFileName(self,'Select asset image','','Images (*.png *.jpg *.jpeg *.webp *.tif *.tiff);;All files (*)')
  if not path:return
  try:self.service.set_asset_image(aid,path,self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Asset image',str(e))
 def _asset_documents(self):
  aid=self._selected_asset_id()
  if not aid:return
  try:docs=self.service.documents(aid,self.actor())
  except Exception as e:QMessageBox.warning(self,'Documentation',str(e));return
  labels=[f"{d['document_type']} — {d['title']}" for d in docs]+['Add documentation…'];choice,ok=QInputDialog.getItem(self,'Asset documentation','Select document',labels,max(0,len(labels)-1),False)
  if not ok:return
  if choice=='Add documentation…':self._add_document();return
  path=docs[labels.index(choice)]['file_path']
  if Path(path).exists():QDesktopServices.openUrl(QUrl.fromLocalFile(path))
  else:QMessageBox.warning(self,'Documentation','The linked file is unavailable.')
 def _add_document(self):
  aid=self._selected_asset_id()
  if not aid:return
  path,_=QFileDialog.getOpenFileName(self,'Add asset documentation','','Documents (*.pdf *.doc *.docx *.xls *.xlsx *.csv *.txt *.svg);;All files (*)')
  if not path:return
  dtype,ok=QInputDialog.getItem(self,'Documentation','Type',('manual','certificate','service report','calibration certificate','warranty','drawing','other'),0,False)
  if not ok:return
  try:self.service.add_document(aid,dtype,Path(path).name,path,self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Documentation',str(e))
 def _add_drawing(self):
  path,_=QFileDialog.getOpenFileName(self,'Add building/storage drawing','','Drawings (*.pdf *.svg *.vsdx *.vdx *.eddx *.edxz *.ifc *.dwg *.dxf *.png *.jpg *.jpeg);;All files (*)')
  if not path:return
  title,ok=QInputDialog.getText(self,'Building drawing','Title',text=Path(path).stem)
  if not ok or not title.strip():return
  accepted,location=self._choose_location('Drawing location')
  if not accepted:return
  version,ok=QInputDialog.getText(self,'Building drawing','Version')
  if not ok:return
  try:self.service.add_drawing(title,Path(path).suffix.lower().lstrip('.') or 'unknown',path,self.actor(),location_id=location,version=version);self.refresh()
  except Exception as e:QMessageBox.warning(self,'Building drawing',str(e))
 def _open_drawing(self):
  row=self._row_for_table(self.drawing_table)
  if not row:return
  path=str(row.get('preview_path') or row.get('file_path') or '')
  if path and Path(path).exists():QDesktopServices.openUrl(QUrl.fromLocalFile(path))
  else:QMessageBox.warning(self,'Building drawing','The drawing or preview file is unavailable.')
 def _add_marker(self):
  drawings=self.service.drawings(self.actor());locations=self.service.locations(self.actor())
  if not drawings or not locations:QMessageBox.information(self,'Drawing marker','Create a drawing and a location first.');return
  dlabels=[f"{d['title']} ({d['version']})" for d in drawings];dchoice,ok=QInputDialog.getItem(self,'Place location code','Drawing',dlabels,0,False)
  if not ok:return
  llabels=[self.service.location_path(r['id'],self.actor()) for r in locations];lchoice,ok=QInputDialog.getItem(self,'Place location code','Storage location',llabels,0,False)
  if not ok:return
  code,ok=QInputDialog.getText(self,'Place location code','Marker code / label')
  if not ok or not code.strip():return
  x,ok=QInputDialog.getDouble(self,'Place location code','X coordinate',0,0,100000,2)
  if not ok:return
  y,ok=QInputDialog.getDouble(self,'Place location code','Y coordinate',0,0,100000,2)
  if not ok:return
  try:self.service.add_drawing_marker(drawings[dlabels.index(dchoice)]['id'],code,x,y,location_id=locations[llabels.index(lchoice)]['id'],label=lchoice,actor=self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Drawing marker',str(e))
 def _new_maintenance(self):
  assets=self.service.assets(self.actor())
  if not assets:QMessageBox.information(self,'Maintenance','Create or obtain access to an asset first.');return
  labels=[f"{a['asset_code']} — {a['name']}" for a in assets];choice,ok=QInputDialog.getItem(self,'Maintenance','Asset',labels,0,False)
  if not ok:return
  kind,ok=QInputDialog.getItem(self,'Maintenance','Type',('preventive','corrective','inspection','cleaning','decontamination','firmware update','safety check','replacement','decommissioning'),0,False)
  if not ok:return
  try:self.service.add_maintenance(assets[labels.index(choice)]['id'],kind,'planned',self.actor());self.refresh()
  except Exception as e:QMessageBox.warning(self,'Maintenance',str(e))
 def _open_maintenance(self):
  row=self._row_for_table(self.maintenance_table)
  if not row:return
  status,ok=QInputDialog.getItem(self,'Maintenance','Status',('planned','scheduled','in_progress','completed','failed','cancelled'),0,False)
  if not ok:return
  result,ok=QInputDialog.getMultiLineText(self,'Maintenance','Result / remarks',str(row.get('result') or ''))
  if not ok:return
  try:self.service.update_maintenance(str(row['id']),actor=self.actor(),status=status,provider=str(row.get('provider') or ''),technician=str(row.get('technician') or ''),result=result,notes=str(row.get('notes') or ''));self.refresh()
  except Exception as e:QMessageBox.warning(self,'Maintenance',str(e))
 def _new_calibration(self):
  assets=self.service.assets(self.actor())
  if not assets:QMessageBox.information(self,'Calibration','Create or obtain access to an asset first.');return
  labels=[f"{a['asset_code']} — {a['name']}" for a in assets];choice,ok=QInputDialog.getItem(self,'Calibration','Asset',labels,0,False)
  if not ok:return
  standard,ok=QInputDialog.getText(self,'Calibration','Standard / reference')
  if not ok:return
  try:self.service.add_calibration(assets[labels.index(choice)]['id'],'planned',self.actor(),standard_reference=standard);self.refresh()
  except Exception as e:QMessageBox.warning(self,'Calibration',str(e))
 def _open_calibration(self):
  row=self._row_for_table(self.calibration_table)
  if not row:return
  status,ok=QInputDialog.getItem(self,'Calibration','Status',('planned','in_progress','passed','failed','expired','cancelled'),0,False)
  if not ok:return
  result,ok=QInputDialog.getMultiLineText(self,'Calibration','Result',str(row.get('result') or ''))
  if not ok:return
  valid,ok=QInputDialog.getText(self,'Calibration','Valid until',text=str(row.get('valid_until') or ''))
  if not ok:return
  try:self.service.update_calibration(str(row['id']),actor=self.actor(),status=status,result=result,performed_at=datetime.now().isoformat(timespec='seconds'),valid_until=valid,impact_assessment=str(row.get('impact_assessment') or ''),notes=str(row.get('notes') or ''));self.refresh()
  except Exception as e:QMessageBox.warning(self,'Calibration',str(e))

class LocalProfiles(Page):
 def __init__(self,parent=None):
  super().__init__('Local users & profiles',None,parent);self.store=LocalProfileStore(Path(os.environ.get('FIELDORA_PROFILE_STORE','local-profiles.json')));self.table=DataTable(('Username','Display name','Profile','Enabled'));self.body.addWidget(self.table,1);row=QHBoxLayout();copy=QPushButton('Copy selected profile');copy.setObjectName('primary');copy.clicked.connect(self._copy);row.addWidget(copy);toggle=QPushButton('Enable / disable selected');toggle.setObjectName('tool');toggle.clicked.connect(self._toggle);row.addWidget(toggle);row.addStretch();self.body.addLayout(row);is_admin=os.environ.get('FIELDORA_PROFILE_ROLE')=='administrator';copy.setEnabled(is_admin);toggle.setEnabled(is_admin);self.refresh()
 def refresh(self):self.table.load([(u['username'],u['display_name'],u['role'],'Yes' if u.get('enabled',True) else 'No') for u in self.store.users()])
 def _selected_user(self):
  items=self.table.selectedItems();
  if not items:QMessageBox.information(self,'Profiles','Select a profile first.');return ''
  return self.table.item(items[0].row(),0).text()
 def _copy(self):
  source=self._selected_user();
  if not source:return
  username,ok=QInputDialog.getText(self,'Copy profile','New username');
  if not ok:return
  name,ok=QInputDialog.getText(self,'Copy profile','Display name');
  if not ok:return
  try:self.store.copy_profile(source,username,name,'admin');self.refresh();QMessageBox.information(self,'Profiles','Profile copied. Initial password: admin')
  except Exception as exc:QMessageBox.warning(self,'Profiles',str(exc))
 def _toggle(self):
  username=self._selected_user();
  if not username:return
  user=next(u for u in self.store.users() if u['username']==username)
  try:self.store.set_enabled(username,not user.get('enabled',True));self.refresh()
  except Exception as exc:QMessageBox.warning(self,'Profiles',str(exc))

class Help(Page):
 def __init__(self,parent=None):
  super().__init__('Help & Guides',('Open all manuals','__manuals__'),parent)
  try:self.search.textChanged.disconnect(self._search_changed)
  except (RuntimeError,TypeError):pass
  self.search.setPlaceholderText('Search guides and press Enter');self.search.returnPressed.connect(lambda:self.route_requested.emit(f'__help_search__:{self.search.text().strip()}') if self.search.text().strip() else None)
  self.body.addWidget(self.card('How can we help?',('Search the complete offline documentation with the field above, or open a practical guide below.','Press F1 anywhere in Fieldora for help about the screen you are using.'),('Read the quick start','__help_topic__:quick-start'),170,'panel'))
  self.tools((('Quick start','Set up Fieldora and complete a first workflow','__help_topic__:quick-start'),('Observations & evidence','Unified evidence, assertions, disputes and referral','__help_topic__:observation-workflow'),('Import & export','Import folders and build structured exchange packages','__help_topic__:import'),('AI identification','BioCLIP, BirdNET, review, referral and provenance','__help_topic__:ai-review'),('Projects & research maps','Projects, areas, snapshots, tasks and dossiers','__help_topic__:home-calendar'),('Offline maps','Install and use StreetMaps packages without a network','__help_topic__:offline-maps'),('Taxonomy & GBIF','Taxonomy library, GBIF resources and regional knowledge','__help_topic__:taxonomy'),('Backup & recovery','Protect and restore the library safely','__help_topic__:backup-recovery'),('Troubleshooting','Installation, display, processing and diagnostics','__help_topic__:troubleshooting'),('Keyboard shortcuts','Navigation and accessibility reference','__shortcuts__'),('What is new','Release notes for this Fieldora version','__help_topic__:release-notes'),('Roadmap','Planned capabilities and future releases','__help_topic__:roadmap')))
def build_pages(*, library_database, science_database, enrichment_database, parent=None, **_):
    """Construct and validate every current-interface workspace.

    Keeping this registry explicit makes startup failures deterministic: every
    page is constructed once, checked against the central contract, and then
    connected by MainWindow.
    """
    from natureai_next.ui.qt.navigation_contracts import validate_page_mapping

    pages = {
        "Home": Home(library_database, science_database, enrichment_database, parent),
        "Library Overview": Library(library_database, parent),
        "Observations Overview": Observations(library_database, science_database, parent),
        "Research Overview": Research(science_database, library_database, parent),
        "Measurements & Protocols": MeasurementsSampling(science_database, parent),
        "Knowledge & AI Overview": Knowledge(enrichment_database, parent),
        "AI Chat & MCP": AIChatWorkspace(science_database, parent),
        "AI Platform Administration": AIPlatformAdministration(science_database, parent),
        "Administration Overview": Administration(
            library_database, science_database, enrichment_database, parent
        ),
        "Research Reference Data": ResearchReferenceData(science_database, parent),
        "Administration Governance": AdministrationGovernance(science_database, parent),
        "Platform Parity": PlatformParity(parent),
        "Asset & Equipment Operations": AssetEquipmentOperations(science_database, parent),
        "Local Profiles": LocalProfiles(parent),
        "Help & Guides": Help(parent),
    }
    validate_page_mapping(pages)
    return pages


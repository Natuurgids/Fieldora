"""Dedicated high-throughput Trash Manager workspace."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Literal, Protocol

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)
from natureai_next.application.deletion_approvals import (
    ApprovalPrincipal,
    DeletionApprovalService,
)


class MaintenanceService(Protocol):
    def restore(self, asset_public_id: str) -> bool: ...
    def removal_preview(self, asset_public_id: str) -> object: ...
    def permanently_delete(self, asset_public_id: str, *, observation_policy: Literal["block", "unlink", "delete"] = "block") -> object: ...


class _TrashWorker(QObject):
    progress = Signal(int, int, str)
    completed = Signal(str, object)
    failed = Signal(str)

    def __init__(self, service: MaintenanceService, operation: str, ids: tuple[str, ...], policy: str = "block") -> None:
        super().__init__(); self.service=service; self.operation=operation; self.ids=ids; self.policy=policy

    @Slot()
    def run(self) -> None:
        try:
            results=[]; total=len(self.ids)
            for index, public_id in enumerate(self.ids, 1):
                self.progress.emit(index-1,total,public_id)
                if self.operation == "restore": results.append(self.service.restore(public_id))
                else: results.append(self.service.permanently_delete(public_id, observation_policy=self.policy))
            self.progress.emit(total,total,"")
            self.completed.emit(self.operation, tuple(results))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class TrashManagerWorkspace(QWidget):
    """Table-based trash maintenance without gallery thumbnails or live layout churn."""
    def __init__(
        self,
        database_path: Path,
        maintenance: MaintenanceService,
        parent: QWidget | None = None,
        *,
        approval_database_path: Path | None = None,
        access_database_path: Path | None = None,
    ) -> None:
        super().__init__(parent); self.database_path=database_path; self.maintenance=maintenance
        self.access_database_path = access_database_path
        self.approvals = DeletionApprovalService(
            approval_database_path or database_path.with_name("deletion-approvals.sqlite3")
        )
        self.current_identity = os.environ.get(
            "FIELDORA_IDENTITY_ID", "fieldora-tool-administrator"
        )
        self._thread: QThread|None=None; self._worker: QObject|None=None
        self._loaded_once = False
        title=QLabel("Trash & Deletion Approvals"); title.setObjectName("libraryTitle")
        intro=QLabel("Remove private or non-company material locally, or route permanent organizational deletion to a named person or function. If no eligible approver exists, Fieldora assigns the tool administrator.")
        intro.setWordWrap(True)
        self.select_all=QCheckBox("Select all")
        self.refresh_button=QPushButton("Refresh"); self.refresh_button.clicked.connect(self.refresh)
        self.restore_button=QPushButton("Restore selected"); self.restore_button.clicked.connect(self.restore_selected)
        self.delete_button=QPushButton("Request permanent deletion…"); self.delete_button.clicked.connect(self.delete_selected)
        top=QHBoxLayout(); top.addWidget(self.select_all); top.addStretch(1); top.addWidget(self.refresh_button); top.addWidget(self.restore_button); top.addWidget(self.delete_button)
        self.table=QTableWidget(0,5); self.table.setHorizontalHeaderLabels(("Delete","Name","Type","Trashed/modified","Asset ID")); self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.select_all.toggled.connect(self._select_all)
        self.approval_table=QTableWidget(0,7)
        self.approval_table.setHorizontalHeaderLabels(
            ("Select","Asset ID","Organization","Requested by","Assigned to","Routing","Reason")
        )
        self.approval_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.approve_button=QPushButton("Approve selected deletion")
        self.reject_button=QPushButton("Reject selected request")
        self.approve_button.clicked.connect(lambda: self._resolve_selected(True))
        self.reject_button.clicked.connect(lambda: self._resolve_selected(False))
        approval_buttons=QHBoxLayout(); approval_buttons.addStretch(1)
        approval_buttons.addWidget(self.reject_button); approval_buttons.addWidget(self.approve_button)
        approval_page=QWidget(); approval_layout=QVBoxLayout(approval_page)
        approval_layout.addWidget(self.approval_table); approval_layout.addLayout(approval_buttons)
        trash_page=QWidget(); trash_layout=QVBoxLayout(trash_page)
        trash_layout.addLayout(top); trash_layout.addWidget(self.table)
        tabs=QTabWidget(); tabs.addTab(trash_page,"Local Trash"); tabs.addTab(approval_page,"Pending Server Approval")
        self.status=QLabel("Ready"); self.progress=QProgressBar(); self.progress.hide()
        layout=QVBoxLayout(self); layout.addWidget(title); layout.addWidget(intro); layout.addWidget(tabs,1); layout.addWidget(self.progress); layout.addWidget(self.status)
        self.status.setText("Open Trash Manager to load trashed items")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded_once:
            self._loaded_once = True
            self.refresh()

    @Slot()
    def refresh(self) -> None:
        try:
            with sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True) as connection:
                rows=connection.execute("""SELECT a.public_id, a.title, fi.normalized_path, a.media_type, a.modified_at_us FROM assets a LEFT JOIN file_instances fi ON fi.id=a.primary_file_instance_id WHERE a.lifecycle_state='trashed' ORDER BY a.modified_at_us DESC, a.id DESC""").fetchall()
        except sqlite3.Error as exc:
            self.table.setRowCount(0)
            self.status.setText(f"Trash Manager unavailable: {exc}")
            return
        self.table.setRowCount(len(rows))
        for row,(public_id,title,normalized_path,media_type,modified) in enumerate(rows):
            name = str(title).strip() if title else (Path(str(normalized_path)).name if normalized_path else str(public_id))
            check=QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable); check.setCheckState(Qt.CheckState.Unchecked); check.setData(Qt.ItemDataRole.UserRole,str(public_id))
            self.table.setItem(row,0,check); self.table.setItem(row,1,QTableWidgetItem(str(name))); self.table.setItem(row,2,QTableWidgetItem(str(media_type))); self.table.setItem(row,3,QTableWidgetItem(str(modified))); self.table.setItem(row,4,QTableWidgetItem(str(public_id)))
        self.status.setText(f"{len(rows)} item{'s' if len(rows)!=1 else ''} in Trash")
        self._refresh_approvals()

    def _ids(self)->tuple[str,...]:
        return tuple(str(self.table.item(row,0).data(Qt.ItemDataRole.UserRole)) for row in range(self.table.rowCount()) if self.table.item(row,0).checkState()==Qt.CheckState.Checked)

    @Slot(bool)
    def _select_all(self, checked: bool)->None:
        state=Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()): self.table.item(row,0).setCheckState(state)

    @Slot()
    def restore_selected(self)->None:
        ids=self._ids()
        if ids: self._run("restore",ids)

    @Slot()
    def delete_selected(self)->None:
        ids=self._ids()
        if not ids: return
        organization, accepted = QInputDialog.getText(
            self, "Deletion organization", "Organization ID", text="local"
        )
        if not accepted or not organization.strip(): return
        kind_label, accepted = QInputDialog.getItem(
            self, "Approval route", "Assign approval to", ("Organization function","Named person"), 0, False
        )
        if not accepted: return
        target, accepted = QInputDialog.getText(
            self, "Approval target",
            "Role/function name" if kind_label == "Organization function" else "Identity ID",
        )
        if not accepted: return
        reason, accepted = QInputDialog.getText(
            self, "Deletion reason", "Why must this organizational item be deleted?"
        )
        if not accepted or not reason.strip(): return
        principals = self._principals()
        created = [
            self.approvals.request(
                resource_id=public_id,
                organization_id=organization.strip(),
                requested_by=self.current_identity,
                target_kind="function" if kind_label == "Organization function" else "person",
                target_value=target.strip(),
                reason=reason,
                principals=principals,
            )
            for public_id in ids
        ]
        self.status.setText(
            f"Submitted {len(created)} deletion request(s); assigned to "
            f"{created[0].assigned_to}"
        )
        self._refresh_approvals()

    def _principals(self) -> tuple[ApprovalPrincipal, ...]:
        if self.access_database_path is None or not self.access_database_path.is_file():
            return ()
        with sqlite3.connect(self.access_database_path) as connection:
            identities = connection.execute(
                "SELECT identity_id,display_name,organization_id,enabled "
                "FROM access_identities"
            ).fetchall()
            roles = connection.execute(
                "SELECT subject_id,role_id FROM access_role_assignments"
            ).fetchall()
        by_subject: dict[str,list[str]] = {}
        for subject_id, role_id in roles:
            by_subject.setdefault(str(subject_id), []).append(str(role_id))
        return tuple(
            ApprovalPrincipal(
                str(identity_id), str(name), str(organization_id),
                tuple(by_subject.get(str(identity_id), ())), bool(enabled),
            )
            for identity_id,name,organization_id,enabled in identities
        )

    def _refresh_approvals(self) -> None:
        rows=self.approvals.list("pending"); self.approval_table.setRowCount(len(rows))
        for row,request in enumerate(rows):
            check=QTableWidgetItem(); check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked); check.setData(Qt.ItemDataRole.UserRole,request.request_id)
            values=(request.resource_id,request.organization_id,request.requested_by,request.assigned_to,request.routing_reason,request.reason)
            self.approval_table.setItem(row,0,check)
            for column,value in enumerate(values,1): self.approval_table.setItem(row,column,QTableWidgetItem(value))

    def _resolve_selected(self, approve: bool) -> None:
        selected=[
            str(self.approval_table.item(row,0).data(Qt.ItemDataRole.UserRole))
            for row in range(self.approval_table.rowCount())
            if self.approval_table.item(row,0).checkState()==Qt.CheckState.Checked
        ]
        if not selected: return
        resources=[]
        try:
            for request_id in selected:
                result=self.approvals.resolve(
                    request_id,approver_id=self.current_identity,approve=approve
                )
                if approve: resources.append(result.resource_id)
        except (PermissionError,ValueError,KeyError) as exc:
            QMessageBox.warning(self,"Deletion approval",str(exc)); return
        self._refresh_approvals()
        if resources: self._run("delete",tuple(resources),"block")
        else: self.status.setText(f"Rejected {len(selected)} deletion request(s)")

    def _run(self, operation:str, ids:tuple[str,...], policy:str="block")->None:
        self._set_busy(True); self.progress.setRange(0,len(ids)); self.progress.setValue(0); self.progress.show()
        thread=QThread(self); worker=_TrashWorker(self.maintenance,operation,ids,policy); worker.moveToThread(thread); thread.started.connect(worker.run); worker.progress.connect(self._progress); worker.completed.connect(self._completed); worker.failed.connect(self._failed); worker.completed.connect(thread.quit); worker.failed.connect(thread.quit); thread.finished.connect(thread.deleteLater); thread.finished.connect(worker.deleteLater); self._thread=thread; self._worker=worker; thread.start()

    def _set_busy(self,busy:bool)->None:
        for widget in (self.refresh_button,self.restore_button,self.delete_button,self.select_all,self.table): widget.setEnabled(not busy)

    @Slot(int,int,str)
    def _progress(self,current:int,total:int,public_id:str)->None:
        self.progress.setMaximum(total); self.progress.setValue(current); self.status.setText(f"Processing {current} of {total}…")

    @Slot(str,object)
    def _completed(self,operation:str,results:object)->None:
        self._set_busy(False); self.progress.hide(); count=len(tuple(results)); self.status.setText(f"{'Restored' if operation=='restore' else 'Permanently deleted'} {count} item(s)"); self.refresh()

    @Slot(str)
    def _failed(self,message:str)->None:
        self._set_busy(False); self.progress.hide(); QMessageBox.critical(self,"Trash Manager",message); self.refresh()

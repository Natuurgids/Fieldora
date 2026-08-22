"""Local identity, contract, policy, and decision-audit administration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from natureai_next.application.access_control import AccessAdministrationService
from natureai_next.domain.access_control import (
    IdentityKind,
    PolicyEffect,
    PolicySource,
)


class AccessControlWorkspace(QWidget):
    def __init__(
        self, service: AccessAdministrationService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._organizations = QTableWidget(0, 3)
        self._organizations.setHorizontalHeaderLabels(
            ("Organization ID", "Name", "Enabled")
        )
        self._identities = QTableWidget(0, 4)
        self._identities.setHorizontalHeaderLabels(
            ("Identity ID", "Name", "Kind", "Organization")
        )
        self._contracts = QTableWidget(0, 6)
        self._contracts.setHorizontalHeaderLabels(
            ("Contract ID", "Title", "Organization", "Starts", "Ends", "Status")
        )
        self._policies = QTableWidget(0, 8)
        self._policies.setHorizontalHeaderLabels(
            (
                "Policy ID", "Name", "Effect", "Source", "Subject / role",
                "Actions", "Resources", "Scope",
            )
        )
        self._audit = QTableWidget(0, 7)
        self._audit.setHorizontalHeaderLabels(
            ("Time", "Subject", "Action", "Resource", "Allowed", "Reason", "Policies")
        )
        create_organization = QPushButton("New Organization")
        create_organization.clicked.connect(self._new_organization)
        create_identity = QPushButton("New Identity")
        create_identity.clicked.connect(self._new_identity)
        add_to_group = QPushButton("Add to Group")
        add_to_group.clicked.connect(self._add_to_group)
        assign_role = QPushButton("Assign Role")
        assign_role.clicked.connect(self._assign_role)
        create_contract = QPushButton("New Contract")
        create_contract.clicked.connect(self._new_contract)
        create_policy = QPushButton("New Policy")
        create_policy.clicked.connect(self._new_policy)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        actions = QHBoxLayout()
        for button in (
            create_organization, create_identity, add_to_group, assign_role,
            create_contract, create_policy, refresh
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        tabs = QTabWidget()
        tabs.addTab(self._organizations, "Organizations")
        tabs.addTab(self._identities, "Identities")
        tabs.addTab(self._contracts, "Contracts")
        tabs.addTab(self._policies, "PBAC Policies")
        tabs.addTab(self._audit, "Decision Audit")
        intro = QLabel(
            "Local administration foundation for users, groups, services, devices, "
            "roles, contracts, and policy-based access control. Default policy is deny. "
            "Authentication and federation arrive with the server platform."
        )
        intro.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Access & Contracts</h2>"))
        layout.addWidget(intro)
        layout.addLayout(actions)
        layout.addWidget(tabs, 1)
        self.refresh()

    def _new_organization(self) -> None:
        organization_id, accepted = QInputDialog.getText(
            self, "New organization", "Organization ID"
        )
        if not accepted or not organization_id.strip():
            return
        name, accepted = QInputDialog.getText(
            self, "New organization", "Display name"
        )
        if not accepted or not name.strip():
            return
        self._service.create_organization(organization_id, name)
        self.refresh()

    def _add_to_group(self) -> None:
        group_id, accepted = QInputDialog.getText(
            self, "Add to group", "Group identity ID"
        )
        if not accepted or not group_id.strip():
            return
        member_id, accepted = QInputDialog.getText(
            self, "Add to group", "Member identity ID"
        )
        if not accepted or not member_id.strip():
            return
        self._service.add_group_member(group_id, member_id)
        QMessageBox.information(self, "Group updated", "The membership was saved.")

    def _new_identity(self) -> None:
        name, accepted = QInputDialog.getText(self, "New identity", "Display name")
        if not accepted or not name.strip():
            return
        organization, accepted = QInputDialog.getText(
            self, "New identity", "Organization ID"
        )
        if not accepted or not organization.strip():
            return
        kind_name, accepted = QInputDialog.getItem(
            self, "New identity", "Kind",
            tuple(kind.value for kind in IdentityKind), 0, False,
        )
        if not accepted:
            return
        self._service.create_identity(
            name, organization, IdentityKind(str(kind_name))
        )
        self.refresh()

    def _assign_role(self) -> None:
        subject, accepted = QInputDialog.getText(
            self, "Assign role", "Subject identity ID"
        )
        if not accepted or not subject.strip():
            return
        role, accepted = QInputDialog.getText(
            self, "Assign role", "Role ID (for example researcher or reviewer)"
        )
        if not accepted or not role.strip():
            return
        organization, accepted = QInputDialog.getText(
            self, "Assign role", "Organization ID"
        )
        if not accepted:
            return
        project, accepted = QInputDialog.getText(
            self, "Assign role", "Project ID (optional)"
        )
        if not accepted:
            return
        self._service.grant_role(
            subject.strip(), role.strip(), organization.strip(), project.strip()
        )
        QMessageBox.information(self, "Role assigned", "The role assignment was saved.")

    def _new_contract(self) -> None:
        title, accepted = QInputDialog.getText(self, "New contract", "Contract title")
        if not accepted or not title.strip():
            return
        organization, accepted = QInputDialog.getText(
            self, "New contract", "Organization ID"
        )
        if not accepted or not organization.strip():
            return
        today = datetime.now(UTC)
        starts, accepted = QInputDialog.getText(
            self, "New contract", "Starts at (ISO UTC)", text=today.isoformat()
        )
        if not accepted:
            return
        ends, accepted = QInputDialog.getText(
            self, "New contract", "Ends at (ISO UTC)",
            text=(today + timedelta(days=365)).isoformat(),
        )
        if not accepted:
            return
        self._service.create_contract(title, organization, starts, ends)
        self.refresh()

    def _new_policy(self) -> None:
        name, accepted = QInputDialog.getText(self, "New PBAC policy", "Policy name")
        if not accepted or not name.strip():
            return
        effect_name, accepted = QInputDialog.getItem(
            self, "New PBAC policy", "Effect", ("allow", "deny"), 0, False
        )
        if not accepted:
            return
        source_name, accepted = QInputDialog.getItem(
            self, "New PBAC policy", "Policy source",
            tuple(source.value for source in PolicySource), 0, False,
        )
        if not accepted:
            return
        subject, accepted = QInputDialog.getText(
            self, "New PBAC policy", "Subject identity ID (blank for role policy)"
        )
        if not accepted:
            return
        role, accepted = QInputDialog.getText(
            self, "New PBAC policy", "Role ID (blank for subject policy)"
        )
        if not accepted or (not subject.strip() and not role.strip()):
            return
        action, accepted = QInputDialog.getText(
            self, "New PBAC policy", "Action (view, edit, download, export, train_ai…)"
        )
        if not accepted or not action.strip():
            return
        resource, accepted = QInputDialog.getText(
            self, "New PBAC policy", "Resource type (asset, dossier, project…)"
        )
        if not accepted or not resource.strip():
            return
        organization, accepted = QInputDialog.getText(
            self, "New PBAC policy", "Organization ID"
        )
        if not accepted:
            return
        project, accepted = QInputDialog.getText(
            self, "New PBAC policy", "Project ID (optional)"
        )
        if not accepted:
            return
        source_id = ""
        if source_name == PolicySource.CONTRACT.value:
            source_id, accepted = QInputDialog.getText(
                self, "Contract policy", "Contract ID"
            )
            if not accepted or not source_id.strip():
                return
        self._service.create_policy(
            name=name,
            effect=PolicyEffect(str(effect_name)),
            source=PolicySource(str(source_name)),
            source_id=source_id.strip(),
            subject_id=subject.strip(),
            role_id=role.strip(),
            actions=(action.strip(),),
            resource_types=(resource.strip(),),
            organization_id=organization.strip(),
            project_id=project.strip(),
        )
        self.refresh()

    def refresh(self) -> None:
        repository = self._service.repository
        organizations = repository.organizations()
        self._organizations.setRowCount(len(organizations))
        for row, organization in enumerate(organizations):
            self._set_row(
                self._organizations, row,
                (
                    organization.organization_id, organization.name,
                    "Yes" if organization.enabled else "No",
                ),
            )
        identities = repository.identities()
        self._identities.setRowCount(len(identities))
        for row, identity in enumerate(identities):
            self._set_row(
                self._identities, row,
                (
                    identity.identity_id, identity.display_name, identity.kind.value,
                    identity.organization_id,
                ),
            )
        contracts = repository.contracts()
        self._contracts.setRowCount(len(contracts))
        for row, contract in enumerate(contracts):
            self._set_row(
                self._contracts, row,
                (
                    contract.contract_id, contract.title, contract.organization_id,
                    contract.starts_at_utc, contract.ends_at_utc, contract.status,
                ),
            )
        policies = repository.policies()
        self._policies.setRowCount(len(policies))
        for row, policy in enumerate(policies):
            self._set_row(
                self._policies, row,
                (
                    policy.policy_id, policy.name, policy.effect.value,
                    policy.source.value, policy.subject_id or policy.role_id,
                    ", ".join(policy.actions), ", ".join(policy.resource_types),
                    f"{policy.organization_id} / {policy.project_id}",
                ),
            )
        audit = repository.audit_events()
        self._audit.setRowCount(len(audit))
        for row, event in enumerate(audit):
            self._set_row(
                self._audit, row,
                (
                    event["occurred_at_utc"], event["subject_id"], event["action"],
                    f"{event['resource_type']}:{event['resource_id']}",
                    "Yes" if event["allowed"] else "No", event["reason"],
                    event["policy_ids_json"],
                ),
            )

    @staticmethod
    def _set_row(table: QTableWidget, row: int, values: tuple[object, ...]) -> None:
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, column, item)

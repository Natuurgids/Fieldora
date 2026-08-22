"""In-window settings workspaces for AI and regional resources."""

from __future__ import annotations

import os
from html import escape
from pathlib import Path

try:
    from PySide6.QtCore import Qt, Signal, Slot
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class AIResourcesWorkspace(QWidget):
    def __init__(
        self,
        *,
        resource_service,
        suggestion_service,
        regional_service,
        regional_acquisition_service,
        activity_open,
        resources_ready=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._resource_service = resource_service
        self._suggestion_service = suggestion_service
        self._regional_service = regional_service
        self._regional_acquisition_service = regional_acquisition_service
        self._activity_open = activity_open
        self._resources_ready = resources_ready
        self._activity_open = activity_open
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        quick = QPushButton("BioCLIP Quick Setup…")
        quick.clicked.connect(self._quick_setup)
        regional = QPushButton("Regional Knowledge")
        regional.clicked.connect(self.open_regional_setup)
        advanced = QPushButton("Advanced resource installation…")
        advanced.clicked.connect(self.open_advanced_resources)
        activity = QPushButton("Open Activity Center")
        activity.clicked.connect(activity_open)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        buttons = QHBoxLayout()
        for b in (quick, regional, activity, advanced, refresh):
            buttons.addWidget(b)
        buttons.addStretch(1)
        from natureai_next.infrastructure.ai.diagnostic_logging import (
            DiagnosticSettings,
            load_settings,
            log_path,
            save_settings,
        )

        current = load_settings()
        self._diagnostic_enabled = QCheckBox("Enable NatureAI diagnostic logging")
        self._diagnostic_enabled.setChecked(current.enabled)
        self._diagnostic_level = QComboBox()
        self._diagnostic_level.addItems(["Errors", "Standard", "Detailed"])
        self._diagnostic_level.setCurrentText(current.level.title())
        self._diagnostic_path = QLabel(str(log_path()))
        self._diagnostic_path.setWordWrap(True)

        def persist_diagnostics() -> None:
            save_settings(
                DiagnosticSettings(
                    self._diagnostic_enabled.isChecked(),
                    self._diagnostic_level.currentText().lower(),
                    current.max_bytes,
                )
            )
            self._diagnostic_path.setText(str(log_path()))

        self._diagnostic_enabled.toggled.connect(persist_diagnostics)
        self._diagnostic_level.currentTextChanged.connect(persist_diagnostics)
        clear_logs = QPushButton("Clear diagnostic logs")

        def clear_diagnostic_logs() -> None:
            try:
                log_path().unlink(missing_ok=True)
                log_path().with_suffix(log_path().suffix + ".1").unlink(missing_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, "Diagnostic logging", str(exc))

        clear_logs.clicked.connect(clear_diagnostic_logs)
        diagnostics = QHBoxLayout()
        diagnostics.addWidget(self._diagnostic_enabled)
        diagnostics.addWidget(QLabel("Level:"))
        diagnostics.addWidget(self._diagnostic_level)
        diagnostics.addWidget(clear_logs)
        diagnostics.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>AI Resources</h2>"))
        layout.addWidget(self._summary)
        layout.addLayout(buttons)
        layout.addWidget(QLabel("<h3>Diagnostics</h3>"))
        layout.addLayout(diagnostics)
        layout.addWidget(QLabel("Log file:"))
        layout.addWidget(self._diagnostic_path)
        layout.addStretch(1)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        try:
            o = self._suggestion_service.overview()
            model = (
                "Not installed"
                if o.active_model_identity is None
                else f"{escape(o.active_model_identity)} {escape(o.active_model_version or '')}"
            )
            variant = escape(o.active_variant_identity or "None")
            prompt = escape(o.active_prompt_set or "Not installed")
        except Exception as exc:
            model = f"Unavailable: {escape(str(exc))}"
            variant = "Unknown"
            prompt = "Unknown"
        region = "Not configured"
        if self._regional_service is not None:
            try:
                p = self._regional_service.load()
                countries = (
                    ", ".join(
                        getattr(c, "country_name", getattr(c, "country_code", str(c)))
                        for c in p.countries
                    )
                    or "continent-wide"
                )
                region = f"{escape(p.primary_continent_code or 'Global')} · {escape(countries)}"
            except Exception:
                pass
        self._summary.setText(
            f"<p><b>BioCLIP model:</b> {model}</p><p><b>Variant:</b> {variant}</p><p><b>Prompt set:</b> {prompt}</p><p><b>Regional profile:</b> {region}</p><p>Long-running downloads and embedding jobs are shown in Activity Center.</p>"
        )

    def _quick_setup(self) -> None:
        if self._resource_service is None:
            return
        from natureai_next.application.ai_setup import BioCLIPQuickSetupService
        from natureai_next.ui.qt.ai_setup import BioCLIPSetupDialog

        dialog = BioCLIPSetupDialog(BioCLIPQuickSetupService(self._resource_service), self)
        dialog.exec()
        self.refresh()
        if getattr(dialog, "setup_succeeded", False) and callable(self._resources_ready):
            self._resources_ready()

    def open_regional_setup(self) -> None:
        if self._regional_service is None:
            return
        from natureai_next.ui.qt.regional_setup import RegionalSetupDialog

        dialog = RegionalSetupDialog(
            self._regional_service, self, acquisition_service=self._regional_acquisition_service
        )
        dialog.exec()
        self.refresh()
        if callable(self._resources_ready):
            self._resources_ready()

    def open_advanced_resources(self) -> None:
        if self._resource_service is None:
            return
        from natureai_next.ui.qt.ai_resources import AIResourcesDialog

        AIResourcesDialog(
            self._resource_service,
            self,
            regional_service=self._regional_service,
            regional_acquisition_service=self._regional_acquisition_service,
        ).exec()
        self.refresh()
        if callable(self._resources_ready):
            self._resources_ready()


class RegionalKnowledgeWorkspace(QWidget):
    def __init__(self, *, regional_service, regional_acquisition_service, parent=None) -> None:
        super().__init__(parent)
        self._service = regional_service
        self._acquisition = regional_acquisition_service
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        configure = QPushButton("Configure regional knowledge…")
        configure.clicked.connect(self.configure)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Regional Knowledge</h2>"))
        layout.addWidget(self._summary)
        layout.addWidget(configure, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self.refresh()

    @Slot()
    def refresh(self) -> None:
        try:
            p = self._service.load()
            countries = (
                ", ".join(
                    getattr(c, "country_name", getattr(c, "country_code", str(c)))
                    for c in p.countries
                )
                or "No individual countries selected"
            )
            langs = ", ".join(p.preferred_languages)
            self._summary.setText(
                f"<p><b>Continent:</b> {escape(p.primary_continent_code or 'None')}</p><p><b>Countries:</b> {escape(countries)}</p><p><b>Languages:</b> {escape(langs)}</p><p><b>Rest-of-world fallback:</b> {'Enabled' if p.include_global_fallback else 'Disabled'}</p>"
            )
        except Exception as exc:
            self._summary.setText(f"Regional profile unavailable: {escape(str(exc))}")

    def configure(self) -> None:
        from natureai_next.ui.qt.regional_setup import RegionalSetupDialog

        RegionalSetupDialog(self._service, self, acquisition_service=self._acquisition).exec()
        self.refresh()


class OfflineMapsResourcesWorkspace(QWidget):
    """Navigation-page entry for offline map acquisition and installed coverage."""

    def __init__(self, *, open_manager, parent=None) -> None:
        super().__init__(parent)
        self._open_manager = open_manager
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setText(
            "<p>Offline map coverage is optional and remains visible when the computer is offline.</p>"
            "<p>Select continent, country, and provider-defined province/state/region packages in the map setup. "
            "Installed maps can be enabled, disabled, updated, imported from .apkg, or removed to recover space.</p>"
        )
        manage = QPushButton("Open Offline Map Setup…")
        manage.clicked.connect(self._open_manager)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Offline Maps</h2>"))
        layout.addWidget(self._summary)
        layout.addWidget(manage, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


GBIF_BACKBONE_DWCA_URL = "https://hosted-datasets.gbif.org/datasets/backbone/current/backbone.zip"


class TaxonomyResourcesWorkspace(QWidget):
    """Taxonomy acquisition kept separate from model installation."""

    taxonomy_ready = Signal()

    def __init__(
        self,
        *,
        resource_service,
        configure_regional,
        open_advanced,
        activity_open=None,
        resources_ready=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._resource_service = resource_service
        self._configure_regional = configure_regional
        self._open_advanced = open_advanced
        self._resources_ready = resources_ready
        self._activity_open = activity_open
        if callable(self._resources_ready):
            self.taxonomy_ready.connect(self._resources_ready)
        from natureai_next.ui.qt.activity import activity_center

        activity_center().register_recovery(
            "gbif-taxonomy-import", self._taxonomy_activity_from_payload
        )
        activity_center().register_recovery(
            "gbif-backbone-download-import", self._backbone_activity_from_payload
        )
        summary = QLabel(
            "<p>Taxonomy resources are independent from AI model packages. Import a raw GBIF Darwin Core Archive here to extend scientific/common names and the Knowledge Center.</p>"
            "<p>When a compatible model and prompt set are active, Aperture reconciles the installed taxonomy by rebuilding taxonomy embeddings. The original GBIF ZIP or extracted folder remains unchanged.</p>"
            "<p><b>Complete worldwide option:</b> download the GBIF Backbone Taxonomy Darwin Core Archive. This contains the worldwide taxonomic names and hierarchy needed for AI labels; it is not GBIF’s multi-terabyte occurrence/image dataset.</p>"
        )
        summary.setWordWrap(True)
        download_backbone = QPushButton("Download complete GBIF Backbone Taxonomy…")
        download_backbone.clicked.connect(self._download_full_gbif_backbone)
        gbif = QPushButton("Import GBIF Darwin Core Archive…")
        gbif.clicked.connect(self._import_gbif_dwca)
        gbif_folder = QPushButton("Import Extracted Darwin Core Folder…")
        gbif_folder.clicked.connect(self._import_gbif_dwca_folder)
        regional = QPushButton("Select Regional Taxonomy…")
        regional.clicked.connect(self._configure_regional)
        working_sets = QPushButton("Manage Working Taxonomy Sets…")
        working_sets.clicked.connect(self._manage_working_sets)
        advanced = QPushButton("Import Signed Taxonomy Package…")
        advanced.clicked.connect(self._open_advanced)
        buttons = QHBoxLayout()
        buttons.addWidget(download_backbone)
        buttons.addWidget(gbif)
        buttons.addWidget(gbif_folder)
        buttons.addWidget(regional)
        buttons.addWidget(working_sets)
        buttons.addWidget(advanced)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Taxonomy Resources</h2>"))
        layout.addWidget(summary)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _download_full_gbif_backbone(self) -> None:
        answer = QMessageBox.question(
            self,
            "Complete GBIF Backbone Taxonomy",
            "Download the complete worldwide GBIF Backbone Taxonomy and build Aperture's independent read-only taxonomy database?\n\n"
            "This downloads the taxonomy archive only—not the approximately multi-terabyte GBIF occurrence corpus. "
            "The download is resumable and both download and database construction continue through Activity Center.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        root = (
            Path(os.getenv("LOCALAPPDATA", Path.home()))
            / "NatureAI"
            / "NatureAI Next"
            / "taxonomy-sources"
        )
        source = root / "downloads" / "gbif-backbone-current.zip"
        from natureai_next.application.ai_setup import BioCLIPQuickSetupService
        from natureai_next.application.dwca_taxonomy import run_dwca_taxonomy_import_isolated
        from natureai_next.ui.qt.activity import activity_center

        def operation(progress, cancelled) -> str:
            BioCLIPQuickSetupService._download(
                GBIF_BACKBONE_DWCA_URL,
                source,
                progress=progress,
                cancelled=cancelled,
                label="complete GBIF Backbone Taxonomy",
            )
            result = run_dwca_taxonomy_import_isolated(
                source, progress=progress, cancelled=cancelled
            )
            self.taxonomy_ready.emit()
            return (
                f"Downloaded and published complete GBIF taxonomy {result.source_public_id}: "
                f"{result.taxa_count:,} taxa and {result.names_count:,} names. "
                f"Independent database: {result.package_path}"
            )

        activity_center().start(
            "Complete GBIF Backbone Taxonomy",
            str(source),
            operation,
            kind="gbif-backbone-download-import",
            payload={"source": str(source), "url": GBIF_BACKBONE_DWCA_URL},
        )
        if callable(self._activity_open):
            self._activity_open()

    def _backbone_activity_from_payload(self, payload):
        source = Path(str(payload["source"]))
        url = str(payload.get("url") or GBIF_BACKBONE_DWCA_URL)

        def operation(progress, cancelled) -> str:
            from natureai_next.application.ai_setup import BioCLIPQuickSetupService
            from natureai_next.application.dwca_taxonomy import run_dwca_taxonomy_import_isolated

            BioCLIPQuickSetupService._download(
                url,
                source,
                progress=progress,
                cancelled=cancelled,
                label="complete GBIF Backbone Taxonomy",
            )
            result = run_dwca_taxonomy_import_isolated(
                source, progress=progress, cancelled=cancelled
            )
            self.taxonomy_ready.emit()
            return (
                f"Downloaded and published complete GBIF taxonomy {result.source_public_id}: "
                f"{result.taxa_count:,} taxa and {result.names_count:,} names. "
                f"Independent database: {result.package_path}"
            )

        return operation

    def _taxonomy_activity_from_payload(self, payload):
        source = Path(str(payload["source"]))

        def operation(progress, cancelled) -> str:
            from natureai_next.application.dwca_taxonomy import run_dwca_taxonomy_import_isolated

            result = run_dwca_taxonomy_import_isolated(
                source, progress=progress, cancelled=cancelled
            )
            self.taxonomy_ready.emit()
            return (
                f"Published isolated GBIF taxonomy source {result.source_public_id}: "
                f"{result.taxa_count:,} taxa and {result.names_count:,} names. "
                f"Independent database: {result.package_path}"
            )

        return operation

    def _manage_working_sets(self) -> None:
        from natureai_next.ui.qt.taxonomy_sets import TaxonomyWorkingSetDialog

        TaxonomyWorkingSetDialog(self).exec()

    def _import_gbif_dwca(self) -> None:
        value, _ = QFileDialog.getOpenFileName(
            self, "Select GBIF Darwin Core Archive", "", "Darwin Core Archives (*.zip)"
        )
        if value:
            self._run_gbif_dwca_import(Path(value))

    def _import_gbif_dwca_folder(self) -> None:
        value = QFileDialog.getExistingDirectory(
            self, "Select extracted Darwin Core Archive folder"
        )
        if value:
            self._run_gbif_dwca_import(Path(value))

    def _run_gbif_dwca_import(self, source: Path) -> None:
        from natureai_next.application.dwca_taxonomy import run_dwca_taxonomy_import_isolated
        from natureai_next.ui.qt.activity import activity_center

        def operation(progress, cancelled) -> str:
            result = run_dwca_taxonomy_import_isolated(
                source, progress=progress, cancelled=cancelled
            )
            self.taxonomy_ready.emit()
            return (
                f"Published isolated GBIF taxonomy source {result.source_public_id}: "
                f"{result.taxa_count:,} taxa and {result.names_count:,} names. "
                f"Independent database: {result.package_path}"
            )

        activity_center().start(
            "GBIF taxonomy import",
            str(source),
            operation,
            kind="gbif-taxonomy-import",
            payload={"source": str(source)},
        )
        if callable(self._activity_open):
            self._activity_open()


class ResourceComponentsWorkspace(QWidget):
    """Persistent switches for optional engines and independent knowledge sources."""

    components_changed = Signal()

    def __init__(self, registry=None, parent=None) -> None:
        super().__init__(parent)
        from natureai_next.application.components import ResourceComponentRegistry
        from natureai_next.application.external_taxonomy import GbifTaxonomyLibrary
        from natureai_next.infrastructure.ai.openclip_provider import OpenClipExecutionProvider

        self._registry = registry or ResourceComponentRegistry()
        self._gbif = QCheckBox("Enable GBIF taxonomy")
        self._bioclip = QCheckBox("Enable BioCLIP / OpenCLIP AI engine")
        self._gbif.setChecked(self._registry.enabled("gbif"))
        self._bioclip.setChecked(self._registry.enabled("bioclip"))
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._gbif.toggled.connect(lambda value: self._set("gbif", value))
        self._bioclip.toggled.connect(lambda value: self._set("bioclip", value))
        refresh = QPushButton("Refresh diagnostics")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Resource Components</h2>"))
        intro = QLabel(
            "Turn optional engines and sources on or off without removing installed databases, models, or previous enrichment. Changes take effect when their screen is refreshed."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        layout.addWidget(self._gbif)
        layout.addWidget(self._bioclip)
        layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self._gbif_source = GbifTaxonomyLibrary()
        self._provider = OpenClipExecutionProvider()
        self.refresh()

    def _set(self, key, enabled) -> None:
        self._registry.set_enabled(key, enabled)
        self.refresh()
        self.components_changed.emit()

    def refresh(self) -> None:
        self._gbif_source = type(self._gbif_source)(self._gbif_source.root)
        db = self._gbif_source.database
        gbif_detail = (
            f"ready: {db}" if db.is_file() else f"not found under {self._gbif_source.root}"
        )
        diagnostic = self._provider.diagnostics()
        ai_detail = (
            diagnostic.detail
            if diagnostic.available
            else f"runtime unavailable: {diagnostic.detail}"
        )
        self._status.setText(
            f"<b>GBIF:</b> {'enabled' if self._registry.enabled('gbif') else 'disabled'} · {gbif_detail}<br>"
            f"<b>BioCLIP / OpenCLIP:</b> {'enabled' if self._registry.enabled('bioclip') else 'disabled'} · {ai_detail}"
        )


class LibraryTypesWorkspace(QWidget):
    """Switches for Library and Science workspaces; retained data is never deleted."""

    capabilities_changed = Signal()

    def __init__(
        self, database_path: Path, parent=None, *, science_database_path: Path | None = None
    ) -> None:
        super().__init__(parent)
        from natureai_next.application.library_capabilities import LibraryCapabilityService

        self._service = LibraryCapabilityService(database_path)
        self._science_service = None
        if science_database_path is not None:
            from natureai_next.application.science_capabilities import (
                ScienceCapabilityService,
            )

            self._science_service = ScienceCapabilityService(science_database_path)
        self._boxes: dict[str, QCheckBox] = {}
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Library & Science Workspaces</h2>"))
        intro = QLabel(
            "Photographs, sounds, videos, documents, and Fieldora Science tools are "
            "enabled by default. Turning one off hides its navigation item; existing "
            "files, research records, notes, metadata, and enrichment are retained."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for capability in self._service.list():
            box = QCheckBox(f"Enable {capability.display_name}")
            box.setChecked(capability.enabled)
            box.toggled.connect(lambda value, key=capability.capability_id: self._set(key, value))
            self._boxes[capability.capability_id] = box
            layout.addWidget(box)
        if self._science_service is not None:
            layout.addWidget(QLabel("<h3>Science workspaces</h3>"))
            for capability in self._science_service.list():
                box = QCheckBox(f"Enable {capability.display_name}")
                box.setChecked(capability.enabled)
                box.toggled.connect(
                    lambda value, key=capability.capability_id: self._set_science(
                        key, value
                    )
                )
                self._boxes[capability.capability_id] = box
                layout.addWidget(box)
        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addStretch(1)
        self.refresh()

    def _set(self, capability_id: str, enabled: bool) -> None:
        self._service.set_enabled(capability_id, enabled)
        self.refresh()
        self.capabilities_changed.emit()

    def _set_science(self, capability_id: str, enabled: bool) -> None:
        if self._science_service is None:
            return
        self._science_service.set_enabled(capability_id, enabled)
        self.refresh()
        self.capabilities_changed.emit()

    def refresh(self) -> None:
        enabled = [item.display_name for item in self._service.list() if item.enabled]
        self._status.setText(
            "<b>Visible Library types:</b> " + escape(", ".join(enabled) or "None")
            + (
                "<br><b>Visible Science workspaces:</b> "
                + escape(
                    ", ".join(
                        item.display_name
                        for item in self._science_service.list()
                        if item.enabled
                    )
                    or "None"
                )
                if self._science_service is not None
                else ""
            )
        )


class IntegrationsWorkspace(QWidget):
    """Unified settings page for enrichment systems and optional integrations."""

    integrations_changed = Signal()

    def __init__(self, database_path: Path, parent=None) -> None:
        super().__init__(parent)
        from natureai_next.application.integrations import IntegrationRegistryService

        self._library_root = database_path.parent
        self._service = IntegrationRegistryService(database_path)
        self._boxes: dict[str, QCheckBox] = {}
        self._details = QLabel()
        self._details.setWordWrap(True)
        self._details.setTextFormat(Qt.TextFormat.RichText)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Integrations</h2>"))
        intro = QLabel(
            "Integrations create or process information, but Aperture owns persisted enrichment. "
            "Disabling an integration stops new work without removing earlier enrichment or accepted observations."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for integration in self._service.list():
            box = QCheckBox(f"Enable {integration.display_name}")
            box.setChecked(integration.enabled)
            box.toggled.connect(lambda value, key=integration.integration_id: self._set(key, value))
            self._boxes[integration.integration_id] = box
            layout.addWidget(box)
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._details)
        layout.addStretch(1)
        self.refresh()

    def _set(self, integration_id: str, enabled: bool) -> None:
        self._service.set_enabled(integration_id, enabled)
        self.refresh()
        self.integrations_changed.emit()

    def refresh(self) -> None:
        lines = []
        for item in self._service.list():
            path = (
                "No independent database"
                if not item.database_relative_path
                else str(self._library_root / item.database_relative_path)
            )
            capabilities = ", ".join(item.capabilities) or "none"
            lines.append(
                f"<p><b>{escape(item.display_name)}</b> · {'enabled' if item.enabled else 'disabled'} · "
                f"{escape(item.availability_state)}<br>Capabilities: {escape(capabilities)}<br>Database: {escape(path)}</p>"
            )
        self._details.setText("".join(lines))

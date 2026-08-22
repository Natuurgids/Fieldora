"""Reporting and export workspace for portable Aperture data and media packages."""

from __future__ import annotations

import time
import uuid
import secrets
import webbrowser
from collections import Counter
from html import escape
from pathlib import Path

from natureai_next.application.exporting import ExportService
from natureai_next.application.connectors import ConnectorRegistry
from natureai_next.application.localization import LocaleService
from natureai_next.domain.export_packages import (
    ExportPackageAttachment,
    ExportPackageOriginal,
    ExportPackagePlan,
    MissingOriginalPolicy,
)
from natureai_next.domain.exporting import (
    CollisionPolicy,
    ExportFormat,
    ExportPlan,
    ExportSelection,
)
from natureai_next.infrastructure.database.connection import SqliteConnectionFactory
from natureai_next.infrastructure.database.exporting import SqliteExportCatalogReader
from natureai_next.infrastructure.exporting.metadata import LocalMetadataExportWriter
from natureai_next.infrastructure.exporting.exchange import ExchangeFormatWriter
from natureai_next.infrastructure.exporting.packages import LocalExportPackageBuilder
from natureai_next.application.reporting_analytics import AnalyticsFilters, ReportingAnalyticsReader
from natureai_next.infrastructure.connectors.observation_org import ObservationOrgClient
from natureai_next.application.observation_workflow import ObservationWorkflowService

try:
    from PySide6.QtCore import QRectF, Qt, Signal
    from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFileDialog,
        QDateEdit,
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QPlainTextEdit,
        QRadioButton,
        QScrollArea,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class ExportWorkspace(QWidget):
    """Visible home for portable data and asset export."""

    def __init__(
        self, library_database: Path, selected_asset_ids, activity_center, parent=None
    ) -> None:
        super().__init__(parent)
        self._database = library_database
        self._selected_asset_ids = selected_asset_ids
        self._activity_center = activity_center
        self._reader = SqliteExportCatalogReader(SqliteConnectionFactory(library_database))
        self._locale = LocaleService()
        self._connectors = ConnectorRegistry()

        layout = QVBoxLayout(self)
        title = QLabel(
            f"<h2>{self._locale.translate('workspace.export', 'Export')}</h2>"
            f"<p>{self._locale.translate('export.subtitle', 'Exchange observations, media, and portable packages.')}</p>"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        scope_box = QGroupBox("Source")
        scope_layout = QVBoxLayout(scope_box)
        self._selected_scope = QRadioButton("Current selection")
        self._all_scope = QRadioButton("All active library assets")
        self._selected_scope.setChecked(True)
        scope_layout.addWidget(self._selected_scope)
        scope_layout.addWidget(self._all_scope)
        layout.addWidget(scope_box)

        tabs = QTabWidget()
        tabs.addTab(self._asset_export_tab(), self._locale.translate("export.assets", "Assets"))
        tabs.addTab(self._data_export_tab(), self._locale.translate("export.data", "Data"))
        tabs.addTab(self._connector_tab(), self._locale.translate("export.connectors", "Connectors"))
        layout.addWidget(tabs, 1)

        self._status = QLabel("Ready")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    def _asset_export_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "Create one portable directory containing a manifest, selected Aperture data, "
                "and optionally the original photos, sounds, videos, and documents."
            )
        )
        self._include_originals = QCheckBox("Include original media files")
        self._include_originals.setChecked(True)
        layout.addWidget(self._include_originals)
        form = QFormLayout()
        self._missing_policy = QComboBox()
        self._missing_policy.addItem(
            "Continue and report unavailable originals", MissingOriginalPolicy.CONTINUE
        )
        self._missing_policy.addItem("Require every original", MissingOriginalPolicy.REQUIRE_ALL)
        self._missing_policy.addItem("Exclude originals", MissingOriginalPolicy.EXCLUDE_ORIGINALS)
        form.addRow("Unavailable originals", self._missing_policy)
        layout.addLayout(form)
        button = QPushButton("Export portable package…")
        button.clicked.connect(self._export_package)
        layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _data_export_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel("Export selected Aperture records and metadata without copying original media.")
        )
        row = QHBoxLayout()
        json_button = QPushButton("Export JSON…")
        csv_button = QPushButton("Export CSV…")
        json_button.clicked.connect(lambda: self._export_data(ExportFormat.JSON))
        csv_button.clicked.connect(lambda: self._export_data(ExportFormat.CSV))
        row.addWidget(json_button)
        row.addWidget(csv_button)
        row.addStretch(1)
        layout.addLayout(row)

        scientific = QGroupBox("Scientific exchange")
        scientific_layout = QFormLayout(scientific)
        self._export_language = QComboBox()
        for info in self._locale.available_locales():
            self._export_language.addItem(info.name, info.code)
        scientific_layout.addRow(self._locale.translate("export.language", "Export language"), self._export_language)
        dwca_button = QPushButton("Export Darwin Core Archive…")
        dwca_button.clicked.connect(self._export_darwin_core)
        scientific_layout.addRow(dwca_button)
        layout.addWidget(scientific)
        layout.addStretch(1)
        return page


    def _connector_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel(self._locale.translate(
            "connector.offline",
            "Connector uploads require an explicit online session. Export and mapping remain available offline.",
        )))
        self._connector_choice = QComboBox()
        for connector in self._connectors.list():
            self._connector_choice.addItem(connector.display_name, connector.connector_id)
        layout.addWidget(self._connector_choice)
        button = QPushButton(self._locale.translate("connector.preview", "Validate and preview"))
        button.clicked.connect(self._validate_connector)
        layout.addWidget(button)
        exchange = QPushButton("Authenticate and send to Observation.org…")
        exchange.clicked.connect(self._exchange_observation_org)
        layout.addWidget(exchange)
        self._connector_result = QLabel("Select a connector and validate the current scope.")
        self._connector_result.setWordWrap(True)
        layout.addWidget(self._connector_result)
        layout.addStretch(1)
        return page

    def _export_darwin_core(self) -> None:
        selected = self._selection()
        if selected == ():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Darwin Core Archive", str(Path.home() / "aperture-dwca.zip"), "Darwin Core Archive (*.zip)"
        )
        if not path:
            return
        destination = Path(path)
        language = str(self._export_language.currentData() or "en")
        def operation(progress, cancelled) -> str:
            progress(0, 2, "Reading observations")
            records = self._reader.read_active_assets(selected)
            if cancelled():
                raise InterruptedError
            progress(1, 2, "Writing Darwin Core Archive")
            size, digest = ExchangeFormatWriter().write_darwin_core(destination, records, language)
            progress(2, 2, "Darwin Core export complete")
            return f"Exported {len(records)} assets ({size} bytes, SHA-256 {digest[:12]}…)"
        self._activity_center.start("Export Darwin Core", str(destination), operation, kind="export.dwca")
        self._status.setText("Darwin Core export queued in Activity Center.")

    def _validate_connector(self) -> None:
        selected = self._selection()
        if selected == ():
            return
        records = self._reader.read_active_assets(selected)
        connector_id = str(self._connector_choice.currentData())
        result = self._connectors.validate(connector_id, records)
        details = "<br>".join(escape(item) for item in result.warnings[:8])
        self._connector_result.setText(
            f"<b>{result.valid_count} ready; {result.invalid_count} need attention.</b>"
            + (f"<br>{details}" if details else "")
        )

    def _exchange_observation_org(self) -> None:
        if str(self._connector_choice.currentData()) != "observation-org":
            QMessageBox.information(self, "Observation.org", "Select Observation.org in the connector list first.")
            return
        selected = self._selection()
        if selected == ():
            return
        records = self._reader.read_active_assets(selected)
        observation = next((o for record in records for o in record.observations), None)
        if observation is None:
            QMessageBox.information(self, "Observation.org", "The selection has no observation to send.")
            return
        payload = {
            "species": observation.get("scientific_name") or observation.get("user_taxon") or "",
            "date": records[0].capture_local_text or "",
            "lat": observation.get("latitude") or "",
            "lng": observation.get("longitude") or "",
            "number": observation.get("count") or 1,
            "notes": observation.get("notes") or "",
        }
        dialog = QDialog(self); dialog.setWindowTitle("Observation.org authenticated exchange")
        form = QFormLayout(dialog)
        token = QLineEdit(); token.setEchoMode(QLineEdit.EchoMode.Password); token.setPlaceholderText("Existing OAuth2 access token (optional; not stored)")
        client_id = QLineEdit(); client_id.setPlaceholderText("OAuth client ID")
        client_secret = QLineEdit(); client_secret.setEchoMode(QLineEdit.EchoMode.Password); client_secret.setPlaceholderText("OAuth client secret (not stored)")
        redirect_uri = QLineEdit("http://127.0.0.1:8765/observation-org/callback")
        authorization_code = QLineEdit(); authorization_code.setPlaceholderText("Paste the returned authorization code")
        production = QCheckBox("Send to production observation.org"); production.setToolTip("Off uses the Observation.org test environment")
        upload_media = QCheckBox("Upload selected original photos, sounds or videos after creating the observation")
        editor = QPlainTextEdit(); editor.setPlainText(__import__("json").dumps(payload, indent=2)); editor.setMinimumHeight(220)
        authorize = QPushButton("Open OAuth authorization page")
        def open_authorization():
            if not client_id.text().strip():
                QMessageBox.information(dialog, "Observation.org OAuth", "Enter the OAuth client ID first."); return
            client = ObservationOrgClient(production=production.isChecked())
            url = client.authorization_url(client_id=client_id.text().strip(), redirect_uri=redirect_uri.text().strip(), state=secrets.token_urlsafe(24))
            webbrowser.open(url)
        authorize.clicked.connect(open_authorization)
        form.addRow("Access token", token); form.addRow("Client ID", client_id); form.addRow("Client secret", client_secret)
        form.addRow("Redirect URI", redirect_uri); form.addRow(authorize); form.addRow("Authorization code", authorization_code)
        form.addRow("Environment", production); form.addRow("Media", upload_media); form.addRow("Observation payload", editor)
        warning = QLabel("Nothing is uploaded until you confirm. Production must be selected explicitly."); warning.setWordWrap(True); form.addRow(warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Send observation")
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        try:
            data = __import__("json").loads(editor.toPlainText())
            client = ObservationOrgClient(access_token=token.text().strip() or None, production=production.isChecked())
            if not client.access_token:
                if not all((authorization_code.text().strip(), client_id.text().strip(), client_secret.text(), redirect_uri.text().strip())):
                    raise ValueError("Provide an access token, or complete the OAuth client/code fields.")
                client.exchange_code(code=authorization_code.text().strip(), client_id=client_id.text().strip(), client_secret=client_secret.text(), redirect_uri=redirect_uri.text().strip())
            response = client.create_observation(data)
            remote_id = response.get("id") or response.get("pk") or "created"
            media_results = []
            if upload_media.isChecked():
                for record in records:
                    source = Path(record.primary_path) if record.primary_path else None
                    if source and source.is_file() and str(record.mime_type or "").split("/", 1)[0] in ("image", "audio", "video"):
                        media_results.append(client.upload_media(remote_id, source))
        except Exception as exc:
            QMessageBox.critical(self, "Observation.org exchange failed", str(exc)); return
        observation_public_id = str(observation.get("public_id") or observation.get("observation_public_id") or "")
        if observation_public_id:
            ObservationWorkflowService(self._database).record_contribution(
                observation_public_id, connector_id="observation-org", payload=data,
                state="submitted", response=response, remote_id=str(remote_id),
                remote_url=f"https://observation.org/observation/{remote_id}",
            )
        self._connector_result.setText(f"<b>Observation.org accepted the observation.</b><br>Remote id: {escape(str(remote_id))}<br>Uploaded media: {len(media_results)}")

    def _report_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(
            QLabel(
                "Generate an HTML summary with total assets, media-format counts, observation totals, "
                "and the active selection scope."
            )
        )
        button = QPushButton("Generate summary report…")
        button.clicked.connect(self._generate_report)
        layout.addWidget(button)
        layout.addStretch(1)
        return page

    def _selection(self) -> tuple[str, ...] | None:
        if self._all_scope.isChecked():
            return None
        selected = tuple(dict.fromkeys(self._selected_asset_ids()))
        if not selected:
            QMessageBox.information(
                self,
                "Nothing selected",
                "Select assets in Photos or Collections, or choose All active library assets.",
            )
            return ()
        return selected

    def _export_selection(self, selected: tuple[str, ...] | None) -> ExportSelection:
        return (
            ExportSelection(include_all_active=True)
            if selected is None
            else ExportSelection(asset_public_ids=selected)
        )

    def _export_data(self, format: ExportFormat) -> None:
        selected = self._selection()
        if selected == ():
            return
        suffix = ".json" if format is ExportFormat.JSON else ".csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Aperture Data",
            str(Path.home() / f"aperture-export{suffix}"),
            f"{format.value.upper()} (*{suffix})",
        )
        if not path:
            return
        destination = Path(path)
        plan = ExportPlan(
            public_id=str(uuid.uuid4()),
            destination=destination,
            format=format,
            selection=self._export_selection(selected),
            collision_policy=CollisionPolicy.FAIL,
            created_at_us=time.time_ns() // 1000,
        )

        def operation(progress, cancelled) -> str:
            progress(0, 1, "Reading Aperture records")
            if cancelled():
                raise InterruptedError
            result = ExportService(self._reader, LocalMetadataExportWriter()).execute(plan)
            progress(1, 1, "Data export complete")
            return f"Exported {result.asset_count} assets to {result.destination}"

        self._activity_center.start(
            "Export Aperture data", str(destination), operation, kind="export.data"
        )
        self._status.setText("Data export queued in Activity Center.")

    def _export_package(self) -> None:
        selected = self._selection()
        if selected == ():
            return
        path = QFileDialog.getExistingDirectory(
            self, "Choose empty destination folder for export package", str(Path.home())
        )
        if not path:
            return
        destination = Path(path)
        if any(destination.iterdir()):
            destination = destination / f"Aperture-Export-{time.strftime('%Y%m%d-%H%M%S')}"
        policy = MissingOriginalPolicy(str(self._missing_policy.currentData()))
        include_originals = self._include_originals.isChecked()

        def operation(progress, cancelled) -> str:
            progress(0, 4, "Reading selected records")
            records = self._reader.read_active_assets(selected)
            if cancelled():
                raise InterruptedError
            files = self._reader.read_primary_files(selected)
            progress(1, 4, "Preparing metadata")
            temp_data = destination.parent / f".{destination.name}-{uuid.uuid4().hex}.json"
            LocalMetadataExportWriter().write(
                destination=temp_data,
                format=ExportFormat.JSON,
                records=records,
                collision_policy=CollisionPolicy.FAIL,
                include_provenance=True,
                plan_public_id=str(uuid.uuid4()),
                created_at_us=time.time_ns() // 1000,
            )
            originals = tuple(
                ExportPackageOriginal(
                    asset_public_id=item.asset_public_id,
                    asset_type=_asset_type(item.source_path),
                    source_path=item.source_path,
                    relative_path=f"media/{_asset_type(item.source_path)}s/{item.asset_public_id}-{item.original_name}",
                    expected_size_bytes=item.source_size_bytes,
                    expected_sha256=item.source_sha256,
                )
                for item in files
            )
            progress(2, 4, "Copying package contents in parallel")
            try:
                result = LocalExportPackageBuilder().build(
                    ExportPackagePlan(
                        public_id=str(uuid.uuid4()),
                        destination_directory=destination,
                        attachments=(
                            ExportPackageAttachment(temp_data, "records/assets.json", "data"),
                        ),
                        originals=originals,
                        include_originals=include_originals,
                        missing_original_policy=policy,
                        created_at_us=time.time_ns() // 1000,
                    )
                )
            finally:
                temp_data.unlink(missing_ok=True)
            progress(4, 4, "Package verified")
            return f"Created {result.destination_directory} ({result.included_count} included; {result.unavailable_count} unavailable)"

        self._activity_center.start(
            "Build portable export package", str(destination), operation, kind="export.package"
        )
        self._status.setText("Portable package queued in Activity Center.")

    def _generate_report(self) -> None:
        selected = self._selection()
        if selected == ():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Generate Aperture Report",
            str(Path.home() / "Aperture-Summary.html"),
            "HTML report (*.html)",
        )
        if not path:
            return
        destination = Path(path)

        def operation(progress, cancelled) -> str:
            progress(0, 2, "Reading report data")
            records = self._reader.read_active_assets(selected)
            if cancelled():
                raise InterruptedError
            formats = Counter(
                (record.format_name or record.mime_type or "Unknown") for record in records
            )
            observation_count = sum(len(record.observations) for record in records)
            rows = "".join(
                f"<tr><td>{name}</td><td>{count}</td></tr>"
                for name, count in sorted(formats.items())
            )
            html = (
                "<!doctype html><meta charset='utf-8'><title>Aperture Summary</title>"
                "<style>body{font-family:system-ui;max-width:900px;margin:3rem auto;padding:0 1rem}"
                "table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:.5rem;text-align:left}</style>"
                f"<h1>Aperture Summary</h1><p>Generated {time.strftime('%Y-%m-%d %H:%M:%S')}</p>"
                f"<h2>Totals</h2><p>Assets: <strong>{len(records)}</strong><br>Observations: <strong>{observation_count}</strong></p>"
                f"<h2>Formats</h2><table><tr><th>Format</th><th>Count</th></tr>{rows}</table>"
            ).encode()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(html)
            progress(2, 2, "Report complete")
            return f"Generated report {destination}"

        self._activity_center.start(
            "Generate Aperture report", str(destination), operation, kind="report.generate"
        )
        self._status.setText("Report queued in Activity Center.")


class _MetricCard(QFrame):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        self._value = QLabel("0")
        self._value.setStyleSheet("font-size: 24px; font-weight: 600")
        caption = QLabel(label)
        caption.setStyleSheet("color: palette(mid)")
        layout.addWidget(self._value)
        layout.addWidget(caption)

    def set_value(self, value: int) -> None:
        self._value.setText(f"{value:,}")


class _ChartWidget(QWidget):
    """Dependency-free, theme-aware chart used by reporting dashboards."""

    selected = Signal(str)

    def __init__(self, title: str, chart_type: str = "bar", parent=None) -> None:
        super().__init__(parent)
        self.title = title
        self.chart_type = chart_type
        self.data: tuple[tuple[str, int], ...] = ()
        self._hit_regions: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(260)
        self.setToolTip("Click a segment or bar to drill down")

    def set_data(self, data: tuple[tuple[str, int], ...]) -> None:
        self.data = tuple(item for item in data if item[1] >= 0)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        point = event.position()
        for rect, label in self._hit_regions:
            if rect.contains(point):
                self.selected.emit(label)
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        palette = self.palette()
        text = palette.text().color()
        muted = palette.mid().color()
        accent = palette.highlight().color()
        painter.setPen(text)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(12, 8, self.width() - 24, 28), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        font.setBold(False)
        painter.setFont(font)
        self._hit_regions.clear()
        if not self.data or sum(v for _, v in self.data) == 0:
            painter.setPen(muted)
            painter.drawText(self.rect().adjusted(12, 42, -12, -12), Qt.AlignCenter, "No matching observations")
            return
        if self.chart_type == "pie":
            self._paint_pie(painter, accent, text, muted)
        else:
            self._paint_bars(painter, accent, text, muted)

    def _paint_pie(self, painter: QPainter, accent: QColor, text: QColor, muted: QColor) -> None:
        total = sum(value for _, value in self.data)
        diameter = min(self.height() - 70, self.width() * 0.42)
        pie = QRectF(18, 48, diameter, diameter)
        start = 90 * 16
        for index, (label, value) in enumerate(self.data[:8]):
            span = -round(360 * 16 * value / total)
            color = QColor(accent)
            color.setHsv((color.hue() + index * 43) % 360, max(80, color.saturation()), max(90, color.value()))
            painter.setBrush(color)
            painter.setPen(QPen(self.palette().base().color(), 1))
            painter.drawPie(pie, start, span)
            start += span
        legend_x = pie.right() + 20
        fm = QFontMetrics(painter.font())
        y = 52
        for index, (label, value) in enumerate(self.data[:8]):
            color = QColor(accent)
            color.setHsv((color.hue() + index * 43) % 360, max(80, color.saturation()), max(90, color.value()))
            painter.fillRect(QRectF(legend_x, y + 3, 11, 11), color)
            painter.setPen(text)
            display = fm.elidedText(f"{label}  {value:,} ({value/total:.0%})", Qt.ElideRight, max(80, self.width() - int(legend_x) - 16))
            rect = QRectF(legend_x + 18, y, self.width() - legend_x - 24, 20)
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, display)
            self._hit_regions.append((rect.adjusted(-18, 0, 0, 0), label))
            y += 25
        painter.setPen(muted)
        painter.drawText(QRectF(18, pie.bottom() + 4, diameter, 22), Qt.AlignCenter, f"Total {total:,}")

    def _paint_bars(self, painter: QPainter, accent: QColor, text: QColor, muted: QColor) -> None:
        data = self.data[:12]
        maximum = max(v for _, v in data) or 1
        left = 120
        top = 48
        usable = max(80, self.width() - left - 54)
        row_h = max(18, min(29, (self.height() - top - 12) / max(1, len(data))))
        fm = QFontMetrics(painter.font())
        for index, (label, value) in enumerate(data):
            y = top + index * row_h
            label_rect = QRectF(10, y, left - 16, row_h - 3)
            painter.setPen(text)
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, fm.elidedText(label, Qt.ElideLeft, int(label_rect.width())))
            track = QRectF(left, y + 4, usable, max(8, row_h - 11))
            painter.setBrush(self.palette().alternateBase())
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(track, 4, 4)
            bar = QRectF(track.x(), track.y(), max(2, usable * value / maximum), track.height())
            color = QColor(accent)
            color.setAlpha(max(100, 235 - index * 8))
            painter.setBrush(color)
            painter.drawRoundedRect(bar, 4, 4)
            painter.setPen(muted)
            painter.drawText(QRectF(track.right() + 6, y, 46, row_h - 3), Qt.AlignLeft | Qt.AlignVCenter, f"{value:,}")
            self._hit_regions.append((QRectF(4, y, self.width() - 8, row_h), label))


class ReportingWorkspace(QWidget):
    """Interactive observation analytics and publication-ready reporting."""

    def __init__(self, library_database: Path, selected_asset_ids, activity_center, parent=None) -> None:
        super().__init__(parent)
        self._database = library_database
        self._selected_asset_ids = selected_asset_ids
        self._activity_center = activity_center
        self._reader = SqliteExportCatalogReader(SqliteConnectionFactory(library_database))
        self._locale = LocaleService()
        self._connectors = ConnectorRegistry()
        self._analytics = ReportingAnalyticsReader(library_database)
        self._cards: dict[str, _MetricCard] = {}
        self._charts: dict[str, _ChartWidget] = {}

        outer = QVBoxLayout(self)
        title = QLabel("<h2>Analytics</h2><p>Explore curated observations across media, biodiversity, place, time, and review status.</p>")
        title.setWordWrap(True)
        outer.addWidget(title)

        scope_row = QHBoxLayout()
        self._selected_scope = QRadioButton("Current selection")
        self._all_scope = QRadioButton("All active library assets")
        self._all_scope.setChecked(True)
        scope_row.addWidget(QLabel("Source:"))
        scope_row.addWidget(self._selected_scope)
        scope_row.addWidget(self._all_scope)
        scope_row.addStretch(1)
        refresh = QPushButton("Refresh analytics")
        refresh.clicked.connect(self.refresh)
        scope_row.addWidget(refresh)
        reconstruct = QPushButton("Reconstruct country / region…")
        reconstruct.clicked.connect(self._reconstruct_locations)
        scope_row.addWidget(reconstruct)
        outer.addLayout(scope_row)

        tabs = QTabWidget()
        tabs.addTab(self._dashboard_page(), "Overview")
        tabs.addTab(self._biodiversity_page(), "Biodiversity")
        tabs.addTab(self._geography_page(), "Geography")
        tabs.addTab(self._time_page(), "Time")
        tabs.addTab(self._quality_page(), "Quality")
        tabs.addTab(self._report_page(), "Generate Report")
        outer.addWidget(tabs, 1)
        self._status = QLabel("Ready")
        self._status.setWordWrap(True)
        outer.addWidget(self._status)
        self._load_filter_options()
        self.refresh()

    def _filter_bar(self) -> QWidget:
        box = QGroupBox("Cross filters")
        grid = QGridLayout(box)
        self._media_filter = QComboBox(); self._media_filter.addItems(["All", "Photos", "Videos", "Sounds", "Documents"])
        self._group_filter = QComboBox(); self._group_filter.addItem("All")
        self._country_filter = QComboBox(); self._country_filter.addItem("All")
        self._region_filter = QComboBox(); self._region_filter.addItem("All")
        self._review_filter = QComboBox(); self._review_filter.addItems(["All", "confirmed", "proposed", "rejected", "unreviewed"])
        self._date_from = QDateEdit(); self._date_from.setCalendarPopup(True); self._date_from.setSpecialValueText("Any"); self._date_from.setMinimumDate(self._date_from.minimumDate()); self._date_from.setDate(self._date_from.minimumDate())
        self._date_to = QDateEdit(); self._date_to.setCalendarPopup(True); self._date_to.setSpecialValueText("Any"); self._date_to.setMinimumDate(self._date_to.minimumDate()); self._date_to.setDate(self._date_to.minimumDate())
        controls = [("Media", self._media_filter), ("Species group", self._group_filter), ("Country", self._country_filter), ("Region", self._region_filter), ("Review", self._review_filter), ("From", self._date_from), ("To", self._date_to)]
        for i, (label, widget) in enumerate(controls):
            grid.addWidget(QLabel(label), 0, i)
            grid.addWidget(widget, 1, i)
            if isinstance(widget, QComboBox): widget.currentIndexChanged.connect(self.refresh)
            else: widget.dateChanged.connect(self.refresh)
        return box

    def _dashboard_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(self._filter_bar())
        cards = QHBoxLayout()
        for key, label in (("assets", "Media entries"), ("observations", "Observations"), ("identified", "Identified"), ("confirmed", "Confirmed")):
            card = _MetricCard(label); self._cards[key] = card; cards.addWidget(card)
        layout.addLayout(cards)
        grid = QGridLayout()
        for key, title, kind, row, col in (("media", "Media entries by type", "pie", 0, 0), ("identified_media", "Identified observations by media", "bar", 0, 1), ("groups", "Observation groups", "bar", 1, 0), ("review", "Review status", "pie", 1, 1)):
            chart = _ChartWidget(title, kind); self._charts[key] = chart; grid.addWidget(chart, row, col)
        self._charts["media"].selected.connect(self._drill_media)
        self._charts["groups"].selected.connect(self._drill_group)
        self._charts["review"].selected.connect(self._drill_review)
        layout.addLayout(grid, 1)
        return self._scroll(page)

    def _biodiversity_page(self) -> QWidget:
        return self._single_chart_page("biodiversity", "Observations by species group", self._drill_group)

    def _geography_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        grid = QGridLayout()
        country = _ChartWidget("Observations by country", "bar"); region = _ChartWidget("Observations by region or locality", "bar")
        self._charts["country"] = country; self._charts["region"] = region
        country.selected.connect(self._drill_country); region.selected.connect(self._drill_region)
        grid.addWidget(country, 0, 0); grid.addWidget(region, 1, 0); layout.addLayout(grid)
        return self._scroll(page)

    def _time_page(self) -> QWidget:
        return self._single_chart_page("time", "Observations by capture month", None)

    def _quality_page(self) -> QWidget:
        return self._single_chart_page("quality", "Confirmed, proposed, rejected, and unreviewed", self._drill_review, "pie")

    def _single_chart_page(self, key: str, title: str, callback, kind: str = "bar") -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); chart = _ChartWidget(title, kind); self._charts[key] = chart
        if callback: chart.selected.connect(callback)
        layout.addWidget(chart); layout.addStretch(1); return self._scroll(page)

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea(); area.setWidgetResizable(True); area.setWidget(widget); return area

    def _report_page(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        text = QLabel("Generate a standalone HTML analytics report using the current scope and filters. The report contains summary metrics and accessible bar-chart tables.")
        text.setWordWrap(True); layout.addWidget(text)
        button = QPushButton("Generate analytics report…"); button.clicked.connect(self._generate_report); layout.addWidget(button); layout.addStretch(1)
        return page

    def _scope_ids(self, *, warn: bool = False) -> tuple[str, ...] | None:
        if self._all_scope.isChecked(): return None
        selected = tuple(dict.fromkeys(self._selected_asset_ids()))
        if not selected and warn: QMessageBox.information(self, "Nothing selected", "Select assets in a media workspace, or choose All active library assets.")
        return selected

    def _load_filter_options(self) -> None:
        try:
            options = self._analytics.filter_options(self._scope_ids())
            for combo, values in ((self._group_filter, options["groups"]), (self._country_filter, options["countries"]), (self._region_filter, options["regions"])):
                current = combo.currentText(); combo.blockSignals(True); combo.clear(); combo.addItem("All"); combo.addItems(values); combo.setCurrentText(current if current in values else "All"); combo.blockSignals(False)
        except Exception as exc:
            self._status.setText(f"Filter options unavailable: {exc}")

    def _filters(self) -> AnalyticsFilters:
        minimum = self._date_from.minimumDate()
        return AnalyticsFilters(asset_public_ids=self._scope_ids(), media_type=self._media_filter.currentText(), taxon_group=self._group_filter.currentText(), country=self._country_filter.currentText(), region=self._region_filter.currentText(), review_state=self._review_filter.currentText(), date_from="" if self._date_from.date() == minimum else self._date_from.date().toString("yyyy-MM-dd"), date_to="" if self._date_to.date() == minimum else self._date_to.date().toString("yyyy-MM-dd"))

    def refresh(self) -> None:
        try:
            snapshot = self._analytics.snapshot(self._filters())
            for key, value in (("assets", snapshot.asset_count), ("observations", snapshot.observation_count), ("identified", snapshot.identified_count), ("confirmed", snapshot.confirmed_count)): self._cards[key].set_value(value)
            datasets = {"media": snapshot.media_assets, "identified_media": snapshot.identified_by_media, "groups": snapshot.observations_by_group, "biodiversity": snapshot.observations_by_group, "country": snapshot.observations_by_country, "region": snapshot.observations_by_region, "time": snapshot.observations_by_month, "review": snapshot.review_states, "quality": snapshot.review_states}
            for key, data in datasets.items(): self._charts[key].set_data(data)
            self._status.setText(f"Showing {snapshot.observation_count:,} observations across {snapshot.asset_count:,} media entries. Click a chart value to drill down.")
        except Exception as exc:
            self._status.setText(f"Analytics could not be refreshed: {exc}")

    def _reconstruct_locations(self) -> None:
        scope = self._scope_ids(warn=True)
        if scope == ():
            return
        answer = QMessageBox.question(
            self,
            "Reconstruct reporting locations",
            "Resolve coordinates that are missing country or region information?\n\n"
            "This uses OpenStreetMap Nominatim, requires internet access, and runs "
            "in the Activity Center at a respectful rate.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        from natureai_next.application.location_enrichment import MediaLocationEnrichmentService

        service = MediaLocationEnrichmentService(self._database)

        def operation(progress, cancelled) -> str:
            result = service.reconstruct_missing(
                asset_public_ids=scope,
                progress=progress,
                cancelled=cancelled,
            )
            return (
                f"Location reconstruction examined {result.examined} media entries: "
                f"{result.resolved} resolved, {result.failed} failed."
            )

        self._activity_center.start(
            "Reconstruct country and region",
            "Library coordinates",
            operation,
            kind="location.reverse_geocode",
        )
        self._status.setText(
            "Location reconstruction queued. Refresh analytics when the Activity Center reports completion."
        )

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index < 0: combo.addItem(value); index = combo.findText(value)
        combo.setCurrentIndex(index)

    def _drill_media(self, value: str) -> None: self._set_combo(self._media_filter, value)
    def _drill_group(self, value: str) -> None: self._set_combo(self._group_filter, value)
    def _drill_country(self, value: str) -> None: self._set_combo(self._country_filter, value)
    def _drill_region(self, value: str) -> None: self._set_combo(self._region_filter, value)
    def _drill_review(self, value: str) -> None: self._set_combo(self._review_filter, value)

    @staticmethod
    def _html_table(title: str, data: tuple[tuple[str, int], ...]) -> str:
        maximum = max((v for _, v in data), default=1)
        rows = "".join(f"<tr><th>{escape(k)}</th><td>{v:,}</td><td><div class='track'><span style='width:{100*v/maximum:.1f}%'></span></div></td></tr>" for k, v in data)
        return f"<section><h2>{escape(title)}</h2><table>{rows or '<tr><td>No matching data</td></tr>'}</table></section>"

    def _generate_report(self) -> None:
        if self._scope_ids(warn=True) == (): return
        path, _ = QFileDialog.getSaveFileName(self, "Generate Aperture Analytics Report", str(Path.home() / "Aperture-Analytics.html"), "HTML report (*.html)")
        if not path: return
        destination = Path(path); filters = self._filters()
        def operation(progress, cancelled) -> str:
            progress(0, 2, "Reading analytics data"); snapshot = self._analytics.snapshot(filters)
            if cancelled(): raise InterruptedError
            cards = "".join(f"<div class='metric'><strong>{value:,}</strong><span>{label}</span></div>" for label, value in (("Media entries", snapshot.asset_count), ("Observations", snapshot.observation_count), ("Identified", snapshot.identified_count), ("Confirmed", snapshot.confirmed_count)))
            sections = "".join((self._html_table("Media entries by type", snapshot.media_assets), self._html_table("Identified observations by media", snapshot.identified_by_media), self._html_table("Observation groups", snapshot.observations_by_group), self._html_table("Countries", snapshot.observations_by_country), self._html_table("Regions", snapshot.observations_by_region), self._html_table("Capture timeline", snapshot.observations_by_month), self._html_table("Review status", snapshot.review_states)))
            html = f"""<!doctype html><meta charset='utf-8'><title>Aperture Analytics</title><style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#222}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem}}.metric{{border:1px solid #bbb;border-radius:10px;padding:1rem}}.metric strong{{font-size:1.8rem;display:block}}.metric span{{color:#666}}section{{margin-top:2rem}}table{{border-collapse:collapse;width:100%}}th,td{{padding:.45rem;border-bottom:1px solid #ddd;text-align:left}}th{{width:25%}}.track{{height:12px;background:#eee;border-radius:6px}}.track span{{display:block;height:100%;background:#3478c4;border-radius:6px}}@media(max-width:700px){{.metrics{{grid-template-columns:repeat(2,1fr)}}}}</style><h1>Aperture Analytics</h1><p>Generated {time.strftime('%Y-%m-%d %H:%M:%S')}</p><div class='metrics'>{cards}</div>{sections}"""
            destination.parent.mkdir(parents=True, exist_ok=True); destination.write_text(html, encoding="utf-8"); progress(2, 2, "Report complete"); return f"Generated report {destination}"
        self._activity_center.start("Generate Aperture analytics report", str(destination), operation, kind="report.generate")
        self._status.setText("Analytics report queued in Activity Center.")


def _asset_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".wav", ".flac", ".mp3", ".m4a", ".ogg", ".aac"}:
        return "sound"
    if suffix in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
        return "video"
    if suffix in {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf"}:
        return "document"
    return "photo"

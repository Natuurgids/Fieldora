"""Fieldora product identity, About and diagnostics UI.

Default footer: Powered by NatureAI_Next.
"""

from __future__ import annotations

import os
import platform
import webbrowser
from html import escape
from pathlib import Path

from natureai_next import __version__
from natureai_next.application.branding import BrandingSettings, BrandingStore

try:
    from PySide6 import __version__ as pyside_version
    from PySide6.QtCore import Qt, Signal, Slot
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QStyle,
        QStackedWidget,
        QTextBrowser,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class BrandingWorkspace(QWidget):
    branding_changed = Signal(object)

    def __init__(self, path: Path, store: BrandingStore, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._store = store
        self._fields = {name: QLineEdit() for name in BrandingSettings.__dataclass_fields__}
        form = QFormLayout()
        labels = {
            "application_name": "Application name",
            "powered_by": "Powered by",
            "organization_name": "Organization",
            "project_website": "Project website",
            "donation_label": "Donation label",
            "donation_url": "Donation URL",
        }
        for key, widget in self._fields.items():
            form.addRow(labels[key], widget)
        save = QPushButton("Save")
        save.clicked.connect(self.save)
        reset = QPushButton("Reset to project defaults")
        reset.clicked.connect(self.reset_defaults)
        buttons = QHBoxLayout()
        buttons.addWidget(save)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        note = QLabel(
            "These user-facing values are editable for open-source forks. NatureAI_Next technical identifiers remain unchanged."
        )
        note.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Branding & Project</h2>"))
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addStretch(1)
        self.refresh()

    @property
    def settings(self) -> BrandingSettings:
        return self._store.load(self._path)

    def refresh(self) -> None:
        settings = self.settings
        for key, widget in self._fields.items():
            widget.setText(getattr(settings, key))

    @Slot()
    def save(self) -> None:
        try:
            settings = BrandingSettings(
                **{key: widget.text().strip() for key, widget in self._fields.items()}
            )
            self._store.save(self._path, settings)
        except Exception as exc:
            QMessageBox.warning(self, "Branding settings", str(exc))
            return
        self.branding_changed.emit(settings)
        QMessageBox.information(self, "Branding settings", "Branding settings saved.")

    @Slot()
    def reset_defaults(self) -> None:
        defaults = BrandingSettings()
        self._store.save(self._path, defaults)
        self.refresh()
        self.branding_changed.emit(defaults)


class DiagnosticsWorkspace(QWidget):
    def __init__(
        self,
        *,
        library_name: str,
        session_path: Path,
        branding_path: Path,
        branding_store: BrandingStore,
        resource_service=None,
        ecology_service=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._library_name = library_name
        self._session_path = session_path
        self._branding_path = branding_path
        self._branding_store = branding_store
        self._resource_service = resource_service
        self._ecology_service = ecology_service
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        copy = QPushButton("Copy system information")
        copy.clicked.connect(self.copy_information)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(refresh)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>Diagnostics</h2>"))
        layout.addWidget(self._text)
        layout.addLayout(row)
        self.refresh()

    def information(self) -> str:
        branding = self._branding_store.load(self._branding_path)
        lines = [
            f"{branding.application_name} {__version__}",
            f"Powered by {branding.powered_by} {__version__}",
            f"Library: {self._library_name}",
            f"Session path: {self._session_path}",
            f"Python: {platform.python_version()}",
            f"PySide6 / Qt: {pyside_version}",
            "Embedded whiteboard: Excalidraw 0.18.1 (offline)",
            f"Operating system: {platform.platform()}",
        ]
        try:
            import torch

            lines.extend(
                [f"PyTorch: {torch.__version__}", f"CUDA available: {torch.cuda.is_available()}"]
            )
            if torch.cuda.is_available():
                lines.append(f"CUDA device: {torch.cuda.get_device_name(0)}")
        except Exception:
            lines.append("PyTorch: not available")
        if self._resource_service is not None:
            try:
                overview = self._resource_service.overview()
                lines.extend(
                    [
                        f"Active model: {overview.active_model_identity or 'None'} {overview.active_model_version or ''}".rstrip(),
                        f"Active prompt set: {overview.active_prompt_set or 'None'}",
                    ]
                )
            except Exception as exc:
                lines.append(f"AI resources: unavailable ({exc})")

        lines.extend(
            [
                "",
                "Developer performance snapshot",
                f"Logical processors: {os.cpu_count() or 'unknown'}",
            ]
        )
        try:
            import psutil

            process = psutil.Process()
            memory = process.memory_info()
            io = process.io_counters()
            lines.extend(
                [
                    f"Process CPU: {process.cpu_percent(interval=0.05):.1f}%",
                    f"Process memory: {memory.rss / (1024 * 1024):.1f} MiB",
                    f"Process threads: {process.num_threads()}",
                    f"Disk read: {io.read_bytes / (1024 * 1024):.1f} MiB",
                    f"Disk written: {io.write_bytes / (1024 * 1024):.1f} MiB",
                ]
            )
        except Exception:
            lines.append(
                "Detailed process metrics: unavailable (optional psutil dependency not installed)"
            )
        try:
            from natureai_next.ui.qt.activity import activity_center

            center = activity_center()
            records = center.records
            lines.extend(
                [
                    f"Activity jobs: {len(records)} total, {center.running_count} running",
                    f"Activity failures: {sum(1 for item in records if item.state in {'failed', 'interrupted'})}",
                ]
            )
        except Exception as exc:
            lines.append(f"Activity metrics: unavailable ({exc})")
        return "\n".join(lines)

    @Slot()
    def refresh(self) -> None:
        self._text.setPlainText(self.information())

    @Slot()
    def copy_information(self) -> None:
        QGuiApplication.clipboard().setText(self.information())


class AboutDialog(QDialog):
    """Browsable About Center with the existing overview as its landing page."""

    def __init__(
        self, *, branding: BrandingSettings, diagnostics: DiagnosticsWorkspace, parent=None
    ) -> None:
        super().__init__(parent)
        self._branding = branding
        self._diagnostics = diagnostics
        self.setWindowTitle(f"About {branding.application_name}")
        self.resize(900, 680)

        navigation = QListWidget(self)
        navigation.setFixedWidth(210)
        pages = QStackedWidget(self)

        entries = (
            ("About Fieldora", self._overview_page()),
            ("Donate", self._donate_page()),
            ("Licences & Attribution", self._licences_page()),
            ("Acknowledgements", self._acknowledgements_page()),
            ("System Information", self._system_information_page()),
        )
        for title, page in entries:
            navigation.addItem(QListWidgetItem(title))
            pages.addWidget(page)
        navigation.currentRowChanged.connect(pages.setCurrentIndex)
        navigation.setCurrentRow(0)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        body = QHBoxLayout()
        body.addWidget(navigation)
        body.addWidget(pages, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addWidget(buttons)

    def _overview_page(self) -> QWidget:
        page = QWidget(self)
        title = QLabel(
            f"<h1>{escape(self._branding.application_name)}</h1>"
            f"<p><b>Version {escape(__version__)}</b></p>"
            f"<p>Powered by {escape(self._branding.powered_by)} {escape(__version__)}</p>"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(
            f"<h3>Project</h3><p>Created by ChatGPT working together with {escape(self._branding.organization_name)}.</p>"
            "<h3>Fieldora and NatureAI Next</h3>"
            "<p>Fieldora is the complete suite, user experience, library, and data model. "
            "NatureAI Next is the main software engine and integration layer that connects Fieldora with external open-source technologies.</p>"
            "<h3>Core technologies</h3><p>NatureAI Next, Excalidraw 0.18.1 (embedded offline), "
            "BioCLIP, OpenCLIP, PyTorch, PySide6 / Qt, SQLite and Python.</p>"
        )
        body.setWordWrap(True)
        website = QPushButton("Fieldora project website")
        website.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon))
        website.setToolTip(self._branding.project_website)
        website.clicked.connect(lambda: self._open_url(self._branding.project_website))
        donation = QPushButton("Donate")
        donation.clicked.connect(lambda: self._open_url(self._branding.donation_url))
        donation.setVisible(bool(self._branding.donation_url))
        copy = QPushButton("Copy system information")
        copy.clicked.connect(self._diagnostics.copy_information)
        row = QHBoxLayout()
        row.addWidget(website)
        row.addWidget(donation)
        row.addWidget(copy)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _donate_page(self) -> QWidget:
        page = QWidget(self)
        text = QLabel(
            "<h2>Donate</h2>"
            "<p>Fieldora is an ongoing open project. Donations can support development, documentation, testing, hosting, and future integrations.</p>"
            "<p>Using Fieldora never requires a donation.</p>"
        )
        text.setWordWrap(True)
        button = QPushButton(self._branding.donation_label or "Donate")
        button.clicked.connect(lambda: self._open_url(self._branding.donation_url))
        button.setEnabled(bool(self._branding.donation_url))
        layout = QVBoxLayout(page)
        layout.addWidget(text)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return page

    def _licences_page(self) -> QWidget:
        page = QWidget(self)
        browser = QTextBrowser(page)
        browser.setMarkdown(
            "# Licences and Attribution\n\n"
            "Fieldora integrates open-source software and separately packaged models, taxonomy, ecological, and map resources. "
            "Each component retains its own version, licence, and attribution. Review the shipped licence files and package manifests before redistribution.\n\n"
            "**Excalidraw 0.18.1** is embedded as Fieldora's full offline whiteboard editor under the MIT License. "
            "Its JavaScript, fonts, and supporting assets are bundled locally and do not require a separate installation.\n\n"
            "NatureAI Next provides the integration layer; it does not replace or relicense third-party components."
        )
        layout = QVBoxLayout(page)
        layout.addWidget(browser)
        return page

    def _acknowledgements_page(self) -> QWidget:
        page = QWidget(self)
        browser = QTextBrowser(page)
        browser.setMarkdown(
            "# Acknowledgements\n\n"
            f"Fieldora is created by ChatGPT working together with {self._branding.organization_name}.\n\n"
            "The project builds on the work of open-source communities and data providers, including Excalidraw, Python, Qt/PySide, SQLite, PyTorch, OpenCLIP, BioCLIP, OpenStreetMap contributors, taxonomy providers, and the maintainers of every integrated dependency."
        )
        layout = QVBoxLayout(page)
        layout.addWidget(browser)
        return page

    def _system_information_page(self) -> QWidget:
        page = QWidget(self)
        text = QPlainTextEdit(page)
        text.setReadOnly(True)
        text.setPlainText(self._diagnostics.information())
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(lambda: text.setPlainText(self._diagnostics.information()))
        copy = QPushButton("Copy system information")
        copy.clicked.connect(self._diagnostics.copy_information)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addStretch(1)
        layout = QVBoxLayout(page)
        layout.addWidget(text, 1)
        layout.addLayout(row)
        return page

    def _open_url(self, url: str) -> None:
        if url:
            webbrowser.open(url)

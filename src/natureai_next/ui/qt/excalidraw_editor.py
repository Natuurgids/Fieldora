"""Bundled, network-blocked Excalidraw editor with a Qt document bridge."""

from __future__ import annotations

import json
from pathlib import Path

from natureai_next.application.excalidraw_documents import OfflineExcalidrawDocuments

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QLabel, QStackedLayout, QVBoxLayout, QWidget


class _OfflineRequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Allow only the packaged application, Qt bridge, and embedded scene data."""

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:  # noqa: N802
        if info.requestUrl().scheme().casefold() not in {"file", "qrc", "data", "blob"}:
            info.block(True)


class _DocumentBridge(QObject):
    saved = Signal()

    def __init__(self, service: OfflineExcalidrawDocuments, document: Path) -> None:
        super().__init__()
        self._service = service
        self._document = document

    @Slot(result=str)
    def loadDocument(self) -> str:  # noqa: N802
        payload = json.loads(self._document.read_text(encoding="utf-8"))
        return json.dumps(
            {
                "elements": payload.get("elements", []),
                "appState": payload.get("appState", {}),
                "files": payload.get("files", {}),
                "scrollToContent": True,
            },
            ensure_ascii=False,
        )

    @Slot(str, result=str)
    def saveDocument(self, payload: str) -> str:  # noqa: N802
        try:
            self._service.save_payload(self._document, payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return f"Save failed: {exc}"
        self.saved.emit()
        return "Offline · saved in Fieldora Documents"


class _ExcalidrawPage(QWebEnginePage):
    runtime_error = Signal(str)

    def javaScriptConsoleMessage(  # noqa: N802
        self, level, message: str, line_number: int, source_id: str
    ) -> None:
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            source = Path(source_id).name if source_id else "embedded application"
            self.runtime_error.emit(f"{source}:{line_number}: {message}")
        super().javaScriptConsoleMessage(level, message, line_number, source_id)


class EmbeddedExcalidrawEditor(QWidget):
    """A complete local Excalidraw component embedded in the Science workspace."""

    document_saved = Signal()

    def __init__(self, service: OfflineExcalidrawDocuments, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._last_runtime_error = ""
        self._bridge: _DocumentBridge | None = None
        self._channel: QWebChannel | None = None
        self._interceptor = _OfflineRequestInterceptor(self)
        self._profile = QWebEngineProfile(self)
        self._profile.setUrlRequestInterceptor(self._interceptor)
        self._page = _ExcalidrawPage(self._profile, self)
        self._page.runtime_error.connect(self._remember_runtime_error)
        self._page.loadFinished.connect(self._load_finished)
        settings = self._page.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True
        )
        self._view = QWebEngineView(self)
        self._view.setPage(self._page)
        self._placeholder = QLabel(
            "Select a whiteboard or create a new Excalidraw document."
        )
        self._placeholder.setStyleSheet("color:#607d8b;padding:24px")
        self._stack = QStackedLayout()
        placeholder_page = QWidget()
        placeholder_layout = QVBoxLayout(placeholder_page)
        placeholder_layout.addWidget(self._placeholder)
        placeholder_layout.addStretch(1)
        self._stack.addWidget(placeholder_page)
        self._stack.addWidget(self._view)
        self.setLayout(self._stack)

    def _show_runtime_error(self, detail: str) -> None:
        self._placeholder.setText(
            "The bundled Excalidraw application could not start.\n\n" + detail
        )
        self._placeholder.setWordWrap(True)
        self._stack.setCurrentIndex(0)

    def _remember_runtime_error(self, detail: str) -> None:
        self._last_runtime_error = detail

    def _load_finished(self, succeeded: bool) -> None:
        if not succeeded:
            self._show_runtime_error("Qt WebEngine could not load the offline application.")
            return
        QTimer.singleShot(
            750,
            lambda: self._page.runJavaScript(
                "Boolean(document.querySelector('.excalidraw'))",
                self._editor_ready,
            ),
        )

    def _editor_ready(self, ready: object) -> None:
        if ready is not True:
            self._show_runtime_error(
                "The offline page loaded, but the Excalidraw toolbar and canvas "
                "did not initialize.\n\n"
                + (self._last_runtime_error or "No JavaScript error was reported.")
                + "\n\nRepair the Fieldora GUI installation."
            )

    def open_document(self, document: Path) -> None:
        self._bridge = _DocumentBridge(self._service, document)
        self._bridge.saved.connect(self.document_saved)
        self._channel = QWebChannel(self._page)
        self._channel.registerObject("fieldoraDocuments", self._bridge)
        self._page.setWebChannel(self._channel)
        application = (
            Path(__file__).resolve().parents[2]
            / "resources"
            / "excalidraw"
            / "index.html"
        )
        if not application.is_file():
            self._placeholder.setText("The bundled Excalidraw application is unavailable.")
            self._stack.setCurrentIndex(0)
            return
        self._view.setUrl(QUrl.fromLocalFile(str(application)))
        self._stack.setCurrentIndex(1)

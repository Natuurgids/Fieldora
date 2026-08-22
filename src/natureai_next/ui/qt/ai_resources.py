"""Qt dialog for user-controlled installation of offline AI resources."""

from __future__ import annotations

from pathlib import Path

from natureai_next.application.ai_resources import LocalAIResourceService

try:
    from PySide6.QtWidgets import (
        QDialog,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required") from exc


class AIResourcesDialog(QDialog):
    def __init__(
        self,
        service: LocalAIResourceService,
        parent: QWidget | None = None,
        regional_service: object | None = None,
        regional_acquisition_service: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._regional_service = regional_service
        self._regional_acquisition_service = regional_acquisition_service
        self.setWindowTitle("Local AI Resources")
        self.setMinimumWidth(680)
        intro = QLabel(
            "NatureAI installs signed local resources. Downloads occur only after an explicit setup action, and photographs are never sent to a cloud service."
        )
        intro.setWordWrap(True)

        self._model = QLineEdit()
        self._model.setReadOnly(True)
        self._model_keys = QLineEdit()
        self._model_keys.setReadOnly(True)
        self._prompt = QLineEdit()
        self._prompt.setReadOnly(True)
        self._family = QLineEdit("bioclip")
        self._taxonomy = QLineEdit()
        self._taxonomy.setReadOnly(True)
        self._taxonomy_keys = QLineEdit()
        self._taxonomy_keys.setReadOnly(True)
        form = QFormLayout()
        form.addRow("Model package (.zip)", self._pick_row(self._model, "ZIP files (*.zip)"))
        form.addRow(
            "Model trusted keys (.json)", self._pick_row(self._model_keys, "JSON files (*.json)")
        )
        form.addRow("Prompt manifest (.json)", self._pick_row(self._prompt, "JSON files (*.json)"))
        form.addRow("Prompt model family", self._family)
        form.addRow("Taxonomy package (.zip)", self._pick_row(self._taxonomy, "ZIP files (*.zip)"))
        form.addRow(
            "Taxonomy trusted keys (.json)",
            self._pick_row(self._taxonomy_keys, "JSON files (*.json)"),
        )

        quick_setup = QPushButton("BioCLIP Quick Setup…")
        regional_setup = QPushButton("Regional knowledge setup…")
        install_model = QPushButton("Install and activate model")
        install_prompt = QPushButton("Install and activate prompt set")
        install_taxonomy = QPushButton("Install and activate taxonomy")
        build = QPushButton("Build taxonomy embeddings")
        close = QPushButton("Close")
        quick_setup.clicked.connect(self._quick_setup)
        regional_setup.clicked.connect(self._regional_setup)
        regional_setup.setEnabled(self._regional_service is not None)
        install_model.clicked.connect(self._install_model)
        install_prompt.clicked.connect(self._install_prompt)
        install_taxonomy.clicked.connect(self._install_taxonomy)
        build.clicked.connect(self._build)
        close.clicked.connect(self.accept)
        buttons = QVBoxLayout()
        for button in (
            quick_setup,
            regional_setup,
            install_model,
            install_prompt,
            install_taxonomy,
            build,
            close,
        ):
            buttons.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addLayout(buttons)

    def _pick_row(self, field: QLineEdit, pattern: str) -> QWidget:
        host = QWidget(self)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse…")
        button.clicked.connect(lambda: self._pick(field, pattern))
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return host

    def _pick(self, field: QLineEdit, pattern: str) -> None:
        value, _ = QFileDialog.getOpenFileName(self, "Select local resource", "", pattern)
        if value:
            field.setText(value)

    def _regional_setup(self) -> None:
        if self._regional_service is None:
            return
        from natureai_next.ui.qt.regional_setup import RegionalSetupDialog

        RegionalSetupDialog(
            self._regional_service, self, acquisition_service=self._regional_acquisition_service
        ).exec()

    def _quick_setup(self) -> None:
        from natureai_next.application.ai_setup import BioCLIPQuickSetupService
        from natureai_next.ui.qt.ai_setup import BioCLIPSetupDialog

        dialog = BioCLIPSetupDialog(BioCLIPQuickSetupService(self._service), self)
        dialog.exec()

    def _install_model(self) -> None:
        self._run(
            lambda: self._service.install_model(
                Path(self._required(self._model)), Path(self._required(self._model_keys))
            ),
            "Model package installed and activated.",
        )

    def _install_prompt(self) -> None:
        family = self._family.text().strip() or None
        self._run(
            lambda: self._service.install_prompt_set(
                Path(self._required(self._prompt)), model_family=family
            ),
            "Prompt set installed and activated.",
        )

    def _install_taxonomy(self) -> None:
        self._run(
            lambda: self._service.install_taxonomy(
                Path(self._required(self._taxonomy)), Path(self._required(self._taxonomy_keys))
            ),
            "Taxonomy package installed and activated.",
        )

    def _build(self) -> None:
        self._run(
            self._service.build_taxonomy_embeddings, "Taxonomy embeddings built successfully."
        )

    @staticmethod
    def _required(field: QLineEdit) -> str:
        value = field.text().strip()
        if not value:
            raise ValueError("Select the required local file first.")
        return value

    def _run(self, operation: object, success: str) -> None:
        try:
            result = operation()
        except Exception as exc:
            QMessageBox.warning(self, "Local AI resources", str(exc))
            return
        QMessageBox.information(self, "Local AI resources", f"{success}\n\n{result}")

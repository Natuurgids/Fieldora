"""Qt entry point for verified offline capability/source bundle installation."""

from __future__ import annotations

from natureai_next.plugins.bundles import OfflineBundleInstaller

try:
    from PySide6.QtCore import Slot
    from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


class OfflineBundleInstallAction:
    def __init__(self, installer: OfflineBundleInstaller, parent: QWidget) -> None:
        self._installer = installer
        self._parent = parent

    @Slot()
    def run(self) -> bool:
        filename, _ = QFileDialog.getOpenFileName(
            self._parent,
            "Install offline enrichment bundle",
            "",
            "Aperture bundles (*.zip);;All files (*)",
        )
        if not filename:
            return False
        try:
            installed = self._installer.install(__import__("pathlib").Path(filename))
        except Exception as exc:
            QMessageBox.critical(self._parent, "Bundle installation failed", str(exc))
            return False
        QMessageBox.information(
            self._parent,
            "Bundle installed",
            f"Installed {installed.manifest.display_name} {installed.manifest.version}\n"
            f"Verified {len(installed.verified_files)} file(s).",
        )
        return True

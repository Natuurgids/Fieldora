"""Storage-policy preferences for Build 28."""
from __future__ import annotations
from natureai_next.domain.importing import ImportStoragePolicy
try:
    from PySide6.QtCore import QSettings, Slot
    from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc

class StoragePreferencesWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title=QLabel("Preferences"); title.setObjectName("libraryTitle")
        self._policy=QComboBox()
        self._policy.addItem("Create an Aperture original (managed)", ImportStoragePolicy.MANAGED.value)
        self._policy.addItem("Leave in current location (Linked)", ImportStoragePolicy.REFERENCED.value)
        self._policy.addItem("Create both (hybrid)", ImportStoragePolicy.HYBRID.value)
        saved=str(QSettings().value("import/default_storage_policy", ImportStoragePolicy.MANAGED.value))
        self._policy.setCurrentIndex(max(0,self._policy.findData(saved)))
        self._policy.currentIndexChanged.connect(self._save)
        self._help=QLabel(); self._help.setWordWrap(True); self._save()
        form=QFormLayout(); form.addRow("Default original handling",self._policy); form.addRow("",self._help)
        layout=QVBoxLayout(self); layout.addWidget(title); layout.addLayout(form); layout.addStretch(1)
    @Slot(int)
    def _save(self,_index:int=-1)->None:
        value=str(self._policy.currentData()); QSettings().setValue("import/default_storage_policy",value)
        self._help.setText({
            "managed":"Aperture stores and owns a verified full-size original. Source provenance is retained.",
            "referenced":"Linked: Aperture keeps the original in its current location and stores catalog data and derivatives.",
            "hybrid":"Aperture stores a verified original and keeps the external source as an active reference.",
        }[value])

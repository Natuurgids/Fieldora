"""Goal-oriented continent/country regional profile setup."""

from __future__ import annotations

from natureai_next.domain.regional import RegionalCountry, RegionalProfile

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise RuntimeError("PySide6 is required") from exc

COUNTRIES = {
    "AF": (
        ("ZA", "South Africa"),
        ("KE", "Kenya"),
        ("TZ", "Tanzania"),
        ("MA", "Morocco"),
        ("EG", "Egypt"),
    ),
    "AS": (
        ("IN", "India"),
        ("JP", "Japan"),
        ("CN", "China"),
        ("ID", "Indonesia"),
        ("TH", "Thailand"),
    ),
    "EU": (
        ("BG", "Bulgaria"),
        ("NL", "Netherlands"),
        ("BE", "Belgium"),
        ("DE", "Germany"),
        ("FR", "France"),
        ("ES", "Spain"),
        ("GB", "United Kingdom"),
        ("GR", "Greece"),
        ("IT", "Italy"),
        ("NO", "Norway"),
        ("PL", "Poland"),
        ("PT", "Portugal"),
        ("RO", "Romania"),
        ("SE", "Sweden"),
    ),
    "NA": (("CA", "Canada"), ("US", "United States"), ("MX", "Mexico"), ("CR", "Costa Rica")),
    "SA": (
        ("AR", "Argentina"),
        ("BR", "Brazil"),
        ("CL", "Chile"),
        ("CO", "Colombia"),
        ("PE", "Peru"),
    ),
    "OC": (("AU", "Australia"), ("NZ", "New Zealand"), ("PG", "Papua New Guinea")),
    "AN": (("AQ", "Antarctica"),),
}
CONTINENTS = (
    ("AF", "Africa"),
    ("AS", "Asia"),
    ("EU", "Europe"),
    ("NA", "North America"),
    ("SA", "South America"),
    ("OC", "Oceania"),
    ("AN", "Antarctica"),
)


class RegionalSetupDialog(QDialog):
    def __init__(
        self,
        service: object,
        parent: QWidget | None = None,
        acquisition_service: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._acquisition = acquisition_service
        self.setWindowTitle("Regional knowledge setup")
        self.resize(940, 700)
        self.setMinimumSize(820, 620)
        intro = QLabel(
            "Choose the continent and countries you photograph in. If no country is selected, NatureAI uses the selected continent. When countries are selected, evidence is ranked as: selected countries, the selected continent, then rest of world."
        )
        intro.setWordWrap(True)
        notice = QLabel(
            "<b>First-time regional installation can take multiple minutes.</b><br>NatureAI retrieves occurrence and taxonomy details, builds and signs the package, installs prompts, and may build embeddings. Use View → Activity Center to follow progress while continuing to use NatureAI."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "padding: 10px; border: 1px solid palette(mid); background: palette(alternate-base);"
        )
        self._continents = QListWidget()
        self._countries = QListWidget()
        self._global = QCheckBox("Include rest-of-world fallback")
        self._global.setChecked(True)
        self._en = QCheckBox("English names")
        self._en.setChecked(True)
        self._nl = QCheckBox("Dutch names")
        self._bg = QCheckBox("Bulgarian names")
        self._scientific = QCheckBox("Scientific names")
        self._scientific.setChecked(True)
        for code, name in CONTINENTS:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._continents.addItem(item)
        self._continents.itemChanged.connect(self._rebuild_countries)
        current = service.load()
        for i in range(self._continents.count()):
            it = self._continents.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == current.primary_continent_code:
                it.setCheckState(Qt.CheckState.Checked)
        self._global.setChecked(current.include_global_fallback)
        self._en.setChecked("en" in current.preferred_languages)
        self._nl.setChecked("nl" in current.preferred_languages)
        self._bg.setChecked("bg" in current.preferred_languages)
        self._scientific.setChecked("scientific" in current.preferred_languages)
        self._rebuild_countries()
        selected = {x.country_code for x in current.countries}
        for i in range(self._countries.count()):
            it = self._countries.item(i)
            if it.data(Qt.ItemDataRole.UserRole)[0] in selected:
                it.setCheckState(Qt.CheckState.Checked)
        cancel = QPushButton("Cancel")
        save = QPushButton("Save")
        self._download = QPushButton("Save & Install")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        self._download.clicked.connect(self._save_and_download)
        self._download.setEnabled(self._acquisition is not None)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        buttons.addWidget(self._download)
        form = QFormLayout()
        form.addRow("Continents", self._continents)
        form.addRow("Countries", self._countries)
        langs = QVBoxLayout()
        [langs.addWidget(x) for x in (self._en, self._nl, self._bg, self._scientific)]
        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(notice)
        layout.addLayout(form, 1)
        layout.addWidget(self._global)
        layout.addLayout(langs)
        layout.addLayout(buttons)

    def reject(self) -> None:
        super().reject()

    def _checked_continent(self) -> str | None:
        for i in range(self._continents.count()):
            it = self._continents.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                return str(it.data(Qt.ItemDataRole.UserRole))
        return None

    def _rebuild_countries(self, *_args: object) -> None:
        existing = {}
        for i in range(self._countries.count()):
            it = self._countries.item(i)
            code, _cont, _name = it.data(Qt.ItemDataRole.UserRole)
            existing[code] = it.checkState()
        self._countries.clear()
        for i in range(self._continents.count()):
            cont = self._continents.item(i)
            if cont.checkState() != Qt.CheckState.Checked:
                continue
            cc = str(cont.data(Qt.ItemDataRole.UserRole))
            for code, name in COUNTRIES.get(cc, ()):
                it = QListWidgetItem(name)
                it.setData(Qt.ItemDataRole.UserRole, (code, cc, name))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(existing.get(code, Qt.CheckState.Unchecked))
                self._countries.addItem(it)

    def _profile(self) -> RegionalProfile:
        continent = self._checked_continent()
        countries = []
        for i in range(self._countries.count()):
            it = self._countries.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                code, cont, name = it.data(Qt.ItemDataRole.UserRole)
                countries.append(
                    RegionalCountry(code, cont, name, len(countries), "GBIF occurrence search")
                )
        languages = tuple(
            code
            for code, box in (
                ("en", self._en),
                ("nl", self._nl),
                ("bg", self._bg),
                ("scientific", self._scientific),
            )
            if box.isChecked()
        )
        return RegionalProfile(continent, tuple(countries), self._global.isChecked(), languages)

    def _save(self) -> None:
        try:
            self._service.save(self._profile())
        except Exception as exc:
            QMessageBox.warning(self, "Regional knowledge", str(exc))
            return
        self.accept()

    def _save_and_download(self) -> None:
        if self._acquisition is None:
            return
        try:
            profile = self._service.save(self._profile())
        except Exception as exc:
            QMessageBox.warning(self, "Regional knowledge", str(exc))
            return
        from natureai_next.ui.qt.activity import activity_center

        countries = ", ".join(item.country_name for item in profile.countries) or "continent-wide"
        continent = profile.primary_continent_code or "World"
        activity_center().start(
            "Regional Knowledge",
            f"{continent} — {countries}",
            lambda progress, cancelled: self._acquisition.acquire(
                profile, progress=progress, cancelled=cancelled
            ),
            kind="regional-knowledge",
            payload=self._acquisition.profile_payload(profile),
        )
        self.accept()

"""Standalone Aperture Maintenance Center desktop application."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from natureai_next.application.backup import LibraryBackupService, suggested_backup_name
from natureai_next.application.certification import PlatformCertificationService
from natureai_next.application.geofabrik_maps import GeofabrikCatalogProvider
from natureai_next.application.health import LibraryHealthService
from natureai_next.application.jobs import JobService
from natureai_next.application.launcher_configuration import (
    LauncherConfigurationStore,
    is_aperture_library,
)
from natureai_next.application.library_service import LibraryService
from natureai_next.application.maintenance_inventory import MaintenanceInventoryReader
from natureai_next.application.platform_completion import PlatformSnapshotReader
from natureai_next.application.map_acquisition import MapCatalogLoader, OfflineMapAcquisitionService
from natureai_next.application.recovery import LibraryRecoveryService
from natureai_next.application.retention import WorkflowCleanupService
from natureai_next.bootstrap.startup_timing import latest_startup_summary
from natureai_next.bootstrap.paths import resolve_application_paths
from natureai_next.domain.workflows import RetentionPolicy
from natureai_next.ports.maintenance_platform import MaintenancePlatform
from natureai_next.ports.offline_map_setup import OfflineMapSetupPlatform
from natureai_next.ui.qt.activity import activity_center

_platform: MaintenancePlatform

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QTableWidget,
        QTableWidgetItem,
        QTreeWidget,
        QTreeWidgetItem,
        QTreeWidgetItemIterator,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 is required; install natureai-next[gui]") from exc


def _last_library() -> Path | None:
    return LauncherConfigurationStore().load().last_library


def _select_library(parent: QWidget | None = None) -> Path | None:
    selected = QFileDialog.getExistingDirectory(parent, "Select Aperture Library")
    if not selected:
        return None
    library = Path(selected)
    if not is_aperture_library(library):
        QMessageBox.critical(
            parent,
            "Invalid Aperture Library",
            "The selected folder does not contain library.json and library.sqlite3.",
        )
        return None
    LauncherConfigurationStore().remember_library(library)
    return library


def _request_aperture_close(timeout: float = 20.0) -> bool:
    """Ask running Aperture windows to close cleanly; never terminate them forcibly."""
    if os.name != "nt":
        return True
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    current_pid = os.getpid()
    pids: set[int] = set()
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value and pid.value != current_pid:
            length = user32.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title, length + 1)
            if title.value.startswith("Aperture —") or title.value == "Aperture":
                pids.add(int(pid.value))
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    deadline = time.monotonic() + timeout
    while pids and time.monotonic() < deadline:
        remaining: set[int] = set()
        for pid in pids:
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                remaining.add(pid)
        pids = remaining
        if pids:
            time.sleep(0.25)
    return not pids


def _wait_for_library_unlock(library: Path, timeout: float = 10.0) -> bool:
    """Wait for clean lock release; remove only a demonstrably stale local lock."""
    lock_path = library / ".natureai-next.lock"
    deadline = time.monotonic() + timeout
    while lock_path.exists() and time.monotonic() < deadline:
        owner = _platform.read_lock_owner(lock_path)
        if owner is not None and not _platform.process_is_alive(owner.pid):
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                return False
            return True
        time.sleep(0.2)
    return not lock_path.exists()


def _append_restore_log(library: Path, status: str, detail: str = "", **extra: Any) -> None:
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Aperture" / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "library": str(library.resolve()),
        "status": status,
        "detail": detail,
    }
    payload.update(extra)
    with (log_dir / "restore-history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _create_emergency_backup(library: Path) -> object:
    """Create and verify a SQLite online backup without acquiring the library lock."""
    source = (library / "library.sqlite3").resolve()
    if not source.is_file():
        raise FileNotFoundError(f"library database not found: {source}")
    backup_dir = library / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads((library / "library.json").read_text(encoding="utf-8-sig"))
        library_name = str(
            manifest.get("display_name") or manifest.get("library_name") or library.name
        )
    except (OSError, ValueError, TypeError):
        library_name = library.name

    def backup_database(destination: Path) -> Path:
        source_connection: sqlite3.Connection | None = None
        destination_connection: sqlite3.Connection | None = None
        cursor: sqlite3.Cursor | None = None
        try:
            source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
            destination_connection = sqlite3.connect(str(destination))
            source_connection.backup(destination_connection)
            cursor = destination_connection.cursor()
            result = cursor.execute("PRAGMA integrity_check").fetchone()
            if result is None or str(result[0]).casefold() != "ok":
                raise RuntimeError(f"Emergency backup integrity check failed: {result}")
        finally:
            if cursor is not None:
                cursor.close()
            if destination_connection is not None:
                destination_connection.close()
            if source_connection is not None:
                source_connection.close()
        return destination

    result = LibraryBackupService(
        backup_database,
        library_name=library_name,
        additional_databases={
            "science": resolve_application_paths().subsystem_databases_dir
            / "science.sqlite3",
            "marine-maritime": resolve_application_paths().subsystem_databases_dir
            / "marine-maritime.sqlite3",
            "deletion-approvals": resolve_application_paths().subsystem_databases_dir
            / "deletion-approvals.sqlite3",
            "access-control": resolve_application_paths().subsystem_databases_dir
            / "access-control.sqlite3",
            "server-media": resolve_application_paths().subsystem_databases_dir
            / "server-media.sqlite3",
            "server-jobs": resolve_application_paths().subsystem_databases_dir
            / "server-jobs.sqlite3",
            "server-exports": resolve_application_paths().subsystem_databases_dir
            / "server-exports.sqlite3",
        },
    ).create(
        backup_dir / suggested_backup_name(f"{library_name}-pre-restore")
    )
    LibraryRecoveryService().verify(result.database_path)
    return result


def _launch_aperture(library: Path) -> None:
    scripts_dir = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    executable = scripts_dir / ("natureai-next.exe" if os.name == "nt" else "natureai-next")
    if executable.is_file():
        command = [str(executable)]
    else:
        base = Path(getattr(sys, "_base_executable", sys.executable))
        if base.name.casefold().startswith("python") and base.is_file():
            command = [str(base), "-m", "natureai_next.bootstrap.cli"]
        else:
            # In an installed console-script process sys.executable may itself be
            # natureai-next.exe. Passing -m to that launcher causes argparse code 2.
            command = [str(sys.executable)]
    command += ["--library", str(library)]
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


class OfflineMapPackageDialog(QDialog):
    """Select, acquire, and manage regional offline map packages."""

    def __init__(self, parent: QWidget | None = None, *, platform: OfflineMapSetupPlatform) -> None:
        super().__init__(parent)
        self.setWindowTitle("Offline map setup")
        self.resize(980, 760)
        self.setMinimumSize(860, 650)
        self._container = platform.foundation_factory()
        factory = self._container.subsystem_registry.activate("maps.offline")
        self._catalog_repo = platform.map_catalog_factory(factory)
        self._package_service = platform.map_package_service_factory(factory)
        self._acquisition = OfflineMapAcquisitionService(
            self._catalog_repo,
            self._package_service,
            self._container.paths.offline_map_packages_dir,
            vector_converter=platform.vector_map_converter_factory(),
        )
        self._activities = activity_center()
        self._activities.register_recovery("offline-map.prepare", self._map_activity_from_payload)
        self._activities.register_recovery(
            "offline-map.import-openseamap", self._openseamap_activity_from_payload
        )
        self._activities.changed.connect(self._activity_changed)
        self._map_activity_states: dict[str, str] = {}
        self._installed_refresh_pending = False
        self._loaded_catalog = None
        self._catalog_entries_by_id: dict[str, object] = {}
        self._catalog_cache_path = (
            self._container.paths.offline_map_packages_dir.parent / "catalogs" / "offline-maps.json"
        )

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Choose the continents and countries needed for field work, then select one or more "
            "downloadable leaf regions. Aperture downloads official Geofabrik OpenStreetMap extracts "
            "and builds them locally with open-source Planetiler into independent offline MBTiles databases. An internet connection is required "
            "for download; installed maps remain available completely offline."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        notice = QLabel(
            "<b>Prepare map coverage in manageable increments.</b><br>"
            "Large regional collections can require substantial storage and download time. "
            "For a complete prepared collection, import a verified Aperture map bundle (.apkg)."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "padding: 10px; border: 1px solid palette(mid); background: palette(alternate-base);"
        )
        layout.addWidget(notice)

        provider_row = QHBoxLayout()
        self.provider_label = QLabel(
            "Default online provider: <b>Geofabrik (OpenStreetMap regional extracts)</b>"
        )
        self.download_catalog_button = QPushButton("Download Region Catalog")
        self.download_catalog_button.setToolTip(
            "Internet connection required. Downloads the official Geofabrik region index."
        )
        self.download_catalog_button.clicked.connect(self.load_default_catalog)
        provider_row.addWidget(self.provider_label, 1)
        provider_row.addWidget(self.download_catalog_button)
        layout.addLayout(provider_row)

        filters = QHBoxLayout()
        continent_group = QGroupBox("Continents")
        continent_layout = QVBoxLayout(continent_group)
        self.continent_list = QListWidget()
        self.continent_list.itemChanged.connect(self._apply_region_filter)
        continent_layout.addWidget(self.continent_list)
        country_group = QGroupBox("Countries")
        country_layout = QVBoxLayout(country_group)
        self.country_list = QListWidget()
        self.country_list.itemChanged.connect(self._apply_region_filter)
        country_layout.addWidget(self.country_list)
        filters.addWidget(continent_group, 1)
        filters.addWidget(country_group, 2)
        layout.addLayout(filters, 1)

        self.catalog_tree = QTreeWidget()
        self.catalog_tree.setHeaderLabels(
            ["Available region", "Level", "Version", "Download", "Installed size"]
        )
        self.catalog_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.catalog_tree, 2)

        actions = QHBoxLayout()
        self.install_button = QPushButton("Download / Update Selected")
        self.install_button.setEnabled(False)
        self.install_button.setToolTip("Download requires the online or cached regional catalog.")
        self.install_button.clicked.connect(self.install_selected)
        import_bundle = QPushButton("Import Map Bundle…")
        import_bundle.clicked.connect(self.import_bundle)
        import_nautical = QPushButton("Import OpenSeaMap Overlay…")
        import_nautical.setToolTip(
            "Import a prepared transparent raster MBTiles seamark overlay; Fieldora never bulk-downloads public tiles."
        )
        import_nautical.clicked.connect(self.import_openseamap)
        remove = QPushButton("Remove Installed Selected")
        remove.clicked.connect(self.remove_selected)
        enable = QPushButton("Enable Installed Selected")
        enable.clicked.connect(lambda: self.set_enabled_selected(True))
        disable = QPushButton("Disable Installed Selected")
        disable.clicked.connect(lambda: self.set_enabled_selected(False))
        refresh = QPushButton("Refresh Installed")
        refresh.clicked.connect(self.refresh_installed)
        for button in (
            self.install_button,
            import_bundle,
            import_nautical,
            remove,
            enable,
            disable,
            refresh,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        advanced = QGroupBox("Advanced map source")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_layout = QHBoxLayout(advanced)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Approved HTTPS catalog URL or local catalog JSON file")
        load_button = QPushButton("Load")
        load_button.clicked.connect(self.load_catalog)
        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(self.browse_catalog)
        advanced_layout.addWidget(self.source_edit, 1)
        advanced_layout.addWidget(browse_button)
        advanced_layout.addWidget(load_button)
        layout.addWidget(advanced)
        advanced.toggled.connect(lambda checked: self._set_advanced_visible(advanced, checked))
        self._set_advanced_visible(advanced, False)

        self.installed_table = QTableWidget(0, 7)
        self.installed_table.setHorizontalHeaderLabels(
            ["Installed package", "Version", "Format", "State", "Enabled", "Size", "File"]
        )
        self.installed_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.installed_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.installed_table, 1)
        self.status = QLabel(
            "No map catalog has been downloaded yet. Connect to the internet and choose Download Region Catalog, "
            "or import a local catalog or verified .apkg bundle. Installed maps remain available offline."
        )
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh_installed()
        self._load_cached_catalog()

    def load_default_catalog(self) -> None:
        self.status.setText("Downloading the official Geofabrik region catalog…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            self._loaded_catalog = GeofabrikCatalogProvider().load()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Offline maps",
                "The Geofabrik region catalog could not be downloaded. Check the internet connection and try again.\n\n"
                f"{exc}\n\nInstalled maps and local bundle import remain available offline.",
            )
            self.status.setText(
                "Online catalog unavailable. Installed maps remain usable; local catalog and .apkg import remain available."
            )
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._catalog_entries_by_id = {
            entry.entry_id: entry for entry in self._loaded_catalog.entries
        }
        self._save_catalog_cache()
        self._populate_region_selectors()
        self._populate_package_tree()
        self.install_button.setEnabled(True)
        self.status.setText(
            f"Loaded the Geofabrik OpenStreetMap region catalog ({len(self._loaded_catalog.entries)} regions). "
            "Choose a continent/country and tick one or more downloadable leaf regions."
        )

    def _load_cached_catalog(self) -> None:
        if not self._catalog_cache_path.is_file():
            return
        try:
            self._loaded_catalog = MapCatalogLoader().load(self._catalog_cache_path)
        except Exception as exc:
            self.status.setText(
                f"Cached map catalog is unavailable: {exc}. Installed maps remain usable; import a local catalog or bundle."
            )
            return
        self._catalog_entries_by_id = {
            entry.entry_id: entry for entry in self._loaded_catalog.entries
        }
        self._save_catalog_cache()
        self._populate_region_selectors()
        self._populate_package_tree()
        self.install_button.setEnabled(True)
        self.status.setText(
            f"Offline/cached catalog: {self._loaded_catalog.catalog_id} version {self._loaded_catalog.catalog_version}. "
            "Installed maps remain usable; downloading requires a connection to the package URLs."
        )

    def _save_catalog_cache(self) -> None:
        if self._loaded_catalog is None:
            return
        self._catalog_cache_path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for entry in self._loaded_catalog.entries:
            item = asdict(entry)
            item["bounds"] = [
                item.pop("west"),
                item.pop("south"),
                item.pop("east"),
                item.pop("north"),
            ]
            entries.append(item)
        payload = {
            "catalog_id": self._loaded_catalog.catalog_id,
            "catalog_version": self._loaded_catalog.catalog_version,
            "entries": entries,
        }
        temporary = self._catalog_cache_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self._catalog_cache_path)

    @staticmethod
    def _set_advanced_visible(group: QGroupBox, checked: bool) -> None:
        group_layout = group.layout()
        if group_layout is None:
            return
        for index in range(group_layout.count()):
            widget = group_layout.itemAt(index).widget()
            if widget is not None:
                widget.setVisible(checked)

    def browse_catalog(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Map Package Catalog", "", "JSON files (*.json);;All files (*)"
        )
        if filename:
            self.source_edit.setText(filename)
            self.load_catalog()

    def load_catalog(self) -> None:
        source = self.source_edit.text().strip()
        if not source:
            QMessageBox.information(
                self,
                "Offline maps",
                "Enter an approved catalog URL or choose a local catalog file.",
            )
            return
        try:
            self._loaded_catalog = MapCatalogLoader().load(source)
        except Exception as exc:
            QMessageBox.critical(self, "Map catalog", str(exc))
            return
        self._catalog_entries_by_id = {
            entry.entry_id: entry for entry in self._loaded_catalog.entries
        }
        self._populate_region_selectors()
        self._populate_package_tree()
        self._save_catalog_cache()
        self.install_button.setEnabled(True)
        self.status.setText(
            f"Loaded {self._loaded_catalog.catalog_id} version {self._loaded_catalog.catalog_version}. "
            "Choose continent/country filters and tick the regional packages to download."
        )

    def _populate_region_selectors(self) -> None:
        for widget in (self.continent_list, self.country_list):
            widget.blockSignals(True)
            widget.clear()
        for entry in self._loaded_catalog.entries:
            kind = entry.region_type.casefold()
            target = (
                self.continent_list
                if kind == "continent"
                else self.country_list
                if kind == "country"
                else None
            )
            if target is None:
                continue
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry.entry_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            target.addItem(item)
        self.continent_list.blockSignals(False)
        self.country_list.blockSignals(False)

    def _populate_package_tree(self) -> None:
        self.catalog_tree.clear()
        items: dict[str, QTreeWidgetItem] = {}
        for entry in self._loaded_catalog.entries:
            item = QTreeWidgetItem(
                [
                    entry.name,
                    entry.region_type,
                    entry.package_version,
                    self._format_bytes(entry.download_size_bytes),
                    self._format_bytes(entry.installed_size_bytes),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, entry.entry_id)
            if entry.downloadable:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(0, Qt.CheckState.Unchecked)
            items[entry.entry_id] = item
        for entry in self._loaded_catalog.entries:
            item = items[entry.entry_id]
            if entry.parent_id is None:
                self.catalog_tree.addTopLevelItem(item)
            else:
                items[entry.parent_id].addChild(item)
        self.catalog_tree.expandToDepth(1)
        self._apply_region_filter()

    def _descends_from(self, entry_id: str, selected_ids: set[str]) -> bool:
        current = self._catalog_entries_by_id.get(entry_id)
        while current is not None:
            if current.entry_id in selected_ids:
                return True
            current = (
                self._catalog_entries_by_id.get(current.parent_id) if current.parent_id else None
            )
        return False

    def _apply_region_filter(self, *_args: object) -> None:
        if self._loaded_catalog is None:
            return
        selected: set[str] = set()
        for widget in (self.continent_list, self.country_list):
            for index in range(widget.count()):
                item = widget.item(index)
                if item.checkState() == Qt.CheckState.Checked:
                    selected.add(str(item.data(Qt.ItemDataRole.UserRole)))

        def visit(item: QTreeWidgetItem) -> bool:
            visible_child = any(visit(item.child(index)) for index in range(item.childCount()))
            entry_id = str(item.data(0, Qt.ItemDataRole.UserRole))
            visible_self = not selected or self._descends_from(entry_id, selected)
            visible = visible_self or visible_child
            item.setHidden(not visible)
            return visible

        for index in range(self.catalog_tree.topLevelItemCount()):
            visit(self.catalog_tree.topLevelItem(index))

    def import_bundle(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Aperture Map Bundle", "", "Aperture map bundles (*.apkg);;All files (*)"
        )
        if not filename:
            return
        bundle = Path(filename)
        try:
            free = shutil.disk_usage(self._container.paths.offline_map_packages_dir.parent).free
            bundle_size = bundle.stat().st_size
        except OSError as exc:
            QMessageBox.critical(self, "Map bundle", str(exc))
            return
        if free < bundle_size * 2:
            QMessageBox.critical(
                self,
                "Insufficient storage",
                f"Importing this bundle requires working space for verification and installation.\n\nBundle: {self._format_bytes(bundle_size)}\nFree space: {self._format_bytes(free)}",
            )
            return
        answer = QMessageBox.question(
            self,
            "Import offline map bundle",
            f"Import and verify this complete offline map bundle?\n\n{bundle.name}\nBundle size: {self._format_bytes(bundle_size)}\nFree space: {self._format_bytes(free)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = self._acquisition.import_bundle(bundle)
        except Exception as exc:
            QMessageBox.critical(self, "Map bundle import failed", str(exc))
        else:
            QMessageBox.information(
                self,
                "Map bundle imported",
                f"Imported {len(result.installed_package_ids)} package(s) from {result.bundle_name}.\n\nInstalled storage: {self._format_bytes(result.installed_bytes)}",
            )
            self.refresh_installed()
        finally:
            QApplication.restoreOverrideCursor()

    def import_openseamap(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import OpenSeaMap Nautical Overlay",
            "",
            "MBTiles databases (*.mbtiles);;All files (*)",
        )
        if not filename:
            return
        source = Path(filename)
        answer = QMessageBox.question(
            self,
            "Import OpenSeaMap overlay",
            "Import this prepared nautical seamark overlay?\n\n"
            f"{source.name}\n\n"
            "It will be verified and copied in the background. OpenSeaMap is reference "
            "material and is not a certified navigational chart. Do not use it as the "
            "sole source for navigation.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        payload = {"source_path": str(source)}
        self._activities.start(
            title=f"Import OpenSeaMap overlay — {source.name}",
            detail="Verify, copy and register offline nautical seamarks",
            operation=self._openseamap_activity_from_payload(payload),
            kind="offline-map.import-openseamap",
            payload=payload,
        )
        self.status.setText(
            "OpenSeaMap overlay import queued. Follow progress in Activity Center; this window may be closed."
        )

    def _openseamap_activity_from_payload(self, payload: dict[str, object]):
        source = Path(str(payload.get("source_path") or ""))

        def operation(progress, cancelled) -> str:
            if cancelled():
                raise InterruptedError("OpenSeaMap import cancelled")
            progress(5, 100, "Validating nautical MBTiles metadata…")
            result = self._acquisition.import_openseamap_mbtiles(source)
            if cancelled():
                raise InterruptedError("OpenSeaMap import cancelled")
            progress(100, 100, "OpenSeaMap overlay ready")
            return f"Installed OpenSeaMap overlay: {result.package_path}"

        return operation

    def _checked_catalog_entries(self):
        if self._loaded_catalog is None:
            return ()
        entries = []
        iterator = QTreeWidgetItemIterator(self.catalog_tree)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.CheckState.Checked:
                entry = self._loaded_catalog.entry(str(item.data(0, Qt.ItemDataRole.UserRole)))
                if entry.downloadable:
                    entries.append(entry)
            iterator += 1
        return tuple(entries)

    def install_selected(self) -> None:
        entries = self._checked_catalog_entries()
        if not entries:
            QMessageBox.information(
                self,
                "Offline maps",
                "Tick one or more downloadable provinces, states, or regional packages before continuing.",
            )
            return
        estimate = self._acquisition.estimate(entries)
        unknown_notice = (
            f"\nSize unavailable from provider: {estimate.unknown_size_count} region(s)\n"
            f"Conservative conversion reserve: {self._format_bytes(estimate.reserve_bytes)}"
            if estimate.unknown_size_count
            else ""
        )
        if not estimate.sufficient_space:
            QMessageBox.critical(
                self,
                "Insufficient storage",
                f"Selected regions: {estimate.package_count}\nDownload: {self._format_bytes(estimate.download_bytes)}\nEstimated installed: {self._format_bytes(estimate.installed_bytes)}\nTemporary working space: {self._format_bytes(estimate.temporary_bytes)}{unknown_notice}\nFree space: {self._format_bytes(estimate.free_bytes)}",
            )
            return
        warning = ""
        if (
            estimate.package_count >= 8
            or estimate.download_bytes >= 2 * 1024**3
            or estimate.installed_bytes >= 4 * 1024**3
        ):
            warning = "\n\nPreparing many regions at once is not recommended. Queue smaller increments or import a verified .apkg bundle."
        names = ", ".join(entry.name for entry in entries[:6])
        if len(entries) > 6:
            names += f", and {len(entries) - 6} more"
        answer = QMessageBox.question(
            self,
            "Prepare offline maps",
            f"Queue {estimate.package_count} selected region(s) for background download and map creation?\n\n{names}\n\nDownload: {self._format_bytes(estimate.download_bytes)}\nEstimated installed: {self._format_bytes(estimate.installed_bytes)}\nTemporary working space: {self._format_bytes(estimate.temporary_bytes)}{unknown_notice}\nFree space: {self._format_bytes(estimate.free_bytes)}"
            + warning,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for entry in entries:
            payload = {"entry": asdict(entry)}
            self._activities.start(
                title=f"Prepare offline map — {entry.name}",
                detail="Geofabrik download, verification, vector map creation, and MBTiles installation",
                operation=self._map_activity_from_payload(payload),
                kind="offline-map.prepare",
                payload=payload,
            )
        self.status.setText(
            f"Queued {len(entries)} offline map region(s). Follow progress in Activity Center; this window may be closed."
        )
        QMessageBox.information(
            self,
            "Offline maps queued",
            f"Queued {len(entries)} region(s) for background preparation.\n\nOpen Activity Center to follow download speed, rendering progress, cancellation, or retry.",
        )

    def _map_activity_from_payload(self, payload: dict[str, object]):
        raw = payload.get("entry")
        if not isinstance(raw, dict):
            raise ValueError("offline map activity payload is missing its catalog entry")
        from natureai_next.application.map_acquisition import MapCatalogEntry

        entry = MapCatalogEntry(**raw)

        def operation(progress, cancelled) -> str:
            last_emit = 0.0
            pending = (0, 100, "Starting…")

            def throttled(current: int, total: int, message: str) -> None:
                nonlocal last_emit, pending
                pending = (current, total, message)
                now = time.monotonic()
                if current >= total or now - last_emit >= 1.0:
                    progress(current, total, message)
                    last_emit = now

            result = self._acquisition.install(entry, progress=throttled, cancelled=cancelled)
            if pending[0] < pending[1]:
                progress(*pending)
            return f"Installed independent map database for {entry.name}: {result.package_path}"

        return operation

    def _activity_changed(self) -> None:
        """Refresh installed maps only after a map activity reaches a terminal state.

        Generic progress notifications are intentionally ignored here. With many map
        workers, refreshing the SQLite-backed table for every progress signal can flood
        the GUI event queue and make Windows report the application as not responding.
        """
        terminal = {"completed", "failed", "cancelled", "interrupted"}
        refresh_needed = False
        current_ids: set[str] = set()
        for record in self._activities.records:
            if record.kind not in {"offline-map.prepare", "offline-map.import-openseamap"}:
                continue
            current_ids.add(record.activity_id)
            previous = self._map_activity_states.get(record.activity_id)
            self._map_activity_states[record.activity_id] = record.state
            if record.state in terminal and previous != record.state:
                refresh_needed = True
        for activity_id in tuple(self._map_activity_states):
            if activity_id not in current_ids:
                self._map_activity_states.pop(activity_id, None)
        if refresh_needed and not self._installed_refresh_pending:
            self._installed_refresh_pending = True
            QTimer.singleShot(250, self._refresh_installed_after_activity)

    def _refresh_installed_after_activity(self) -> None:
        self._installed_refresh_pending = False
        self.refresh_installed()

    def _selected_installed_id(self) -> str | None:
        row = self.installed_table.currentRow()
        if row < 0:
            return None
        item = self.installed_table.item(row, 0)
        return None if item is None else str(item.data(Qt.ItemDataRole.UserRole))

    def remove_selected(self) -> None:
        package_id = self._selected_installed_id()
        if package_id is None:
            QMessageBox.information(self, "Offline maps", "Select an installed map package first.")
            return
        package = self._catalog_repo.get(package_id)
        answer = QMessageBox.question(
            self,
            "Remove offline map",
            f"Remove {package.package_name}?\n\nPhoto coordinates, observation locations, and other scientific data are not removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            reclaimed = self._acquisition.remove(package_id)
        except Exception as exc:
            QMessageBox.critical(self, "Offline maps", str(exc))
            return
        QMessageBox.information(
            self, "Offline map removed", f"Recovered {self._format_bytes(reclaimed)}."
        )
        self.refresh_installed()

    def set_enabled_selected(self, enabled: bool) -> None:
        package_id = self._selected_installed_id()
        if package_id is None:
            QMessageBox.information(self, "Offline maps", "Select an installed map package first.")
            return
        try:
            self._package_service.enable(package_id) if enabled else self._package_service.disable(
                package_id
            )
        except Exception as exc:
            QMessageBox.critical(self, "Offline maps", str(exc))
            return
        self.refresh_installed()

    def refresh_installed(self) -> None:
        try:
            packages = self._catalog_repo.list_all()
        except Exception as exc:
            self.status.setText(str(exc))
            return
        self.installed_table.setRowCount(len(packages))
        for row, package in enumerate(packages):
            display_state = (
                "Installed — vector renderer pending"
                if package.format in {"vector-mbtiles", "pmtiles"} and package.status == "installed"
                else package.status
            )
            values = [
                package.package_name,
                package.package_version,
                package.format,
                display_state,
                "Yes" if package.enabled else "No",
                self._format_bytes(package.verified_size_bytes),
                package.package_path,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, package.public_id)
                self.installed_table.setItem(row, column, item)
        self.installed_table.resizeColumnsToContents()

    @staticmethod
    def _format_bytes(value: int | None) -> str:
        if value is None:
            return "—"
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"


class MaintenanceCenterWindow(QMainWindow):
    def __init__(
        self,
        library: Path,
        inventory_reader_factory: Callable[[Path], MaintenanceInventoryReader],
        cleanup_service_factory: Callable[[object, tuple[Path, ...]], WorkflowCleanupService],
        job_service_factory: Callable[[object], JobService],
        *,
        launch_intent: str | None = None,
    ) -> None:
        super().__init__()
        self.library = library.resolve()
        self._inventory_reader_factory = inventory_reader_factory
        self._cleanup_service_factory = cleanup_service_factory
        self._job_service_factory = job_service_factory
        self._launch_intent = launch_intent
        self.recovery = LibraryRecoveryService()
        self.setWindowTitle("Aperture Maintenance Center")
        icon = Path(__file__).resolve().parents[2] / "resources" / "fieldora.ico"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel("<h2>Aperture Maintenance Center</h2>")
        detail = QLabel(
            f"Library: {self.library}<br><br>Manage verified backups, restore operations, operational locations, and maintenance history. Aperture libraries and photographs are never removed by routine maintenance actions."
        )
        detail.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(detail)
        self.status_label = QLabel("Ready")
        self.status_label.setAccessibleName("Maintenance Center status")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setAccessibleName("Maintenance operation progress")
        layout.addWidget(self.progress)

        paths_group = QGroupBox("Operational locations")
        paths_form = QFormLayout(paths_group)
        self._path_values: dict[str, Path] = {
            "Library root": self.library,
            "SQLite database": self.library / "library.sqlite3",
            "Library manifest": self.library / "library.json",
            "Backups": self.library / "backups",
            "Cache": self.library / "cache",
            "Temporary files": self.library / "temp",
            "Application logs": Path(os.environ.get("LOCALAPPDATA", Path.home()))
            / "Aperture"
            / "Logs",
        }
        for label, path in self._path_values.items():
            row = QHBoxLayout()
            value = QLabel(str(path))
            value.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            value.setAccessibleName(f"{label} path")
            copy_button = QPushButton("Copy Path")
            copy_button.clicked.connect(
                lambda _checked=False, p=path: QGuiApplication.clipboard().setText(str(p))
            )
            open_button = QPushButton("Open Folder")
            open_button.clicked.connect(
                lambda _checked=False, p=path: self._open_operational_path(p)
            )
            row.addWidget(value, 1)
            row.addWidget(copy_button)
            row.addWidget(open_button)
            paths_form.addRow(label, row)
        layout.addWidget(paths_group)

        performance_group = QGroupBox("Startup performance")
        performance_form = QFormLayout(performance_group)
        latest = latest_startup_summary()
        if latest is None:
            startup_text = "No startup timing record is available yet."
        else:
            events = latest.get("events", [])
            visible = next(
                (
                    event
                    for event in reversed(events)
                    if event.get("stage") == "main-window-visible"
                ),
                None,
            )
            startup_text = (
                f"{visible.get('elapsed_ms')} ms to first visible window"
                if visible
                else "Startup record does not contain first-paint timing."
            )
        self.startup_summary_label = QLabel(startup_text)
        self.startup_summary_label.setAccessibleName("Latest Aperture startup timing")
        performance_form.addRow("Latest startup", self.startup_summary_label)
        open_startup_log = QPushButton("Open Startup Log")
        open_startup_log.clicked.connect(
            lambda: self._open_operational_path(
                self._path_values["Application logs"] / "startup-timing.jsonl"
            )
        )
        performance_form.addRow("Diagnostics", open_startup_log)
        layout.addWidget(performance_group)

        support_group = QGroupBox("Diagnostics and support")
        support_layout = QVBoxLayout(support_group)
        support_text = QLabel(
            "Create a read-only JSON snapshot of database integrity, workflow state, backup verification, storage use, and platform details. No media content is included."
        )
        support_text.setWordWrap(True)
        support_layout.addWidget(support_text)
        export_snapshot = QPushButton("Export Platform Snapshot…")
        export_snapshot.clicked.connect(self.export_platform_snapshot)
        support_layout.addWidget(export_snapshot, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(support_group)

        health_group = QGroupBox("Health and background work")
        health_layout = QVBoxLayout(health_group)
        self.health_summary_label = QLabel(
            "Use the existing Aperture health checks and stop/continue controls for Version 2 work."
        )
        self.health_summary_label.setWordWrap(True)
        health_layout.addWidget(self.health_summary_label)
        health_actions = QHBoxLayout()
        run_health = QPushButton("Run Health Check")
        run_health.clicked.connect(self.run_health_check)
        refresh_jobs = QPushButton("Refresh Work")
        refresh_jobs.clicked.connect(self.refresh_jobs)
        pause_job = QPushButton("Pause Selected")
        pause_job.clicked.connect(self.pause_selected_job)
        resume_job = QPushButton("Continue Selected")
        resume_job.clicked.connect(self.resume_selected_job)
        stop_job = QPushButton("Stop Selected")
        stop_job.clicked.connect(self.cancel_selected_job)
        for button in (run_health, refresh_jobs, pause_job, resume_job, stop_job):
            health_actions.addWidget(button)
        health_actions.addStretch(1)
        health_layout.addLayout(health_actions)
        self.job_table = QTableWidget(0, 5)
        self.job_table.setHorizontalHeaderLabels(
            ["Type", "State", "Progress", "Message", "Updated"]
        )
        self.job_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.job_table.setAccessibleName("Aperture background work")
        health_layout.addWidget(self.job_table)
        layout.addWidget(health_group)

        certification_group = QGroupBox("Version 2 platform certification")
        certification_layout = QVBoxLayout(certification_group)
        self.certification_summary_label = QLabel(
            "Run read-only certification against the approved Version 2 platform boundaries."
        )
        self.certification_summary_label.setWordWrap(True)
        certification_layout.addWidget(self.certification_summary_label)
        run_certification = QPushButton("Run Platform Certification")
        run_certification.clicked.connect(self.run_platform_certification)
        certification_layout.addWidget(run_certification)
        layout.addWidget(certification_group)

        inventory_group = QGroupBox("Storage overview")
        inventory_layout = QVBoxLayout(inventory_group)
        self.inventory_summary_label = QLabel(
            "Inspect storage used by Aperture-owned library and application locations."
        )
        self.inventory_summary_label.setWordWrap(True)
        inventory_layout.addWidget(self.inventory_summary_label)
        refresh_inventory = QPushButton("Refresh Storage")
        refresh_inventory.clicked.connect(self.refresh_inventory)
        inventory_layout.addWidget(refresh_inventory, 0, Qt.AlignmentFlag.AlignLeft)
        self.storage_table = QTableWidget(0, 4)
        self.storage_table.setHorizontalHeaderLabels(["Category", "Size", "Files", "Data class"])
        self.storage_table.setAccessibleName("Aperture storage inventory")
        inventory_layout.addWidget(self.storage_table)
        layout.addWidget(inventory_group)

        ai_group = QGroupBox("BioCLIP / OpenCLIP resources")
        ai_layout = QVBoxLayout(ai_group)
        ai_text = QLabel(
            "Install the supported BioCLIP model from this maintenance environment, or import a complete "
            "model folder downloaded with the Hugging Face CLI or copied from another computer. Local import "
            "does not require a network connection."
        )
        ai_text.setWordWrap(True)
        ai_layout.addWidget(ai_text)
        ai_actions = QHBoxLayout()
        setup_bioclip = QPushButton("Download or Import BioCLIP…")
        setup_bioclip.clicked.connect(self.manage_bioclip_resources)
        repair_prompts = QPushButton("Activate NatureAI Prompts")
        repair_prompts.setToolTip(
            "Install the built-in BioCLIP Tree of Life prompt profile and rebuild taxonomy embeddings."
        )
        repair_prompts.clicked.connect(self.repair_bioclip_prompts)
        open_models = QPushButton("Open Model Storage")
        open_models.clicked.connect(self.open_model_storage)
        ai_actions.addWidget(setup_bioclip)
        ai_actions.addWidget(repair_prompts)
        ai_actions.addWidget(open_models)
        ai_actions.addStretch(1)
        ai_layout.addLayout(ai_actions)
        layout.addWidget(ai_group)

        maps_group = QGroupBox("Offline maps")
        maps_layout = QVBoxLayout(maps_group)
        maps_text = QLabel(
            "Download, import, update, enable, disable, or remove offline map regions. "
            "Installed map packages are managed inside the Offline Map Packages window."
        )
        maps_text.setWordWrap(True)
        maps_layout.addWidget(maps_text)
        manage_maps = QPushButton("Manage Offline Maps…")
        manage_maps.clicked.connect(self.manage_offline_maps)
        maps_layout.addWidget(manage_maps, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(maps_group)

        cleanup_group = QGroupBox("Lean storage cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)
        self.cleanup_summary_label = QLabel(
            "Scan temporary files and bounded job/event history without touching photographs, observations, or analyses."
        )
        self.cleanup_summary_label.setWordWrap(True)
        cleanup_layout.addWidget(self.cleanup_summary_label)
        cleanup_actions = QHBoxLayout()
        preview_cleanup = QPushButton("Preview Cleanup")
        preview_cleanup.clicked.connect(self.preview_cleanup)
        run_cleanup = QPushButton("Run Cleanup…")
        run_cleanup.clicked.connect(self.run_cleanup)
        cleanup_actions.addWidget(preview_cleanup)
        cleanup_actions.addWidget(run_cleanup)
        cleanup_actions.addStretch(1)
        cleanup_layout.addLayout(cleanup_actions)
        layout.addWidget(cleanup_group)

        self.backup_group = QGroupBox("Backup and restore")
        backup_layout = QVBoxLayout(self.backup_group)
        backup_help = QLabel(
            "Create verified database backups or restore a selected verified backup. "
            "Restore closes Aperture only after confirmation and preserves rollback data."
        )
        backup_help.setWordWrap(True)
        backup_layout.addWidget(backup_help)
        self.backup_table = QTableWidget(0, 4)
        self.backup_table.setHorizontalHeaderLabels(["Created", "Library", "Size", "File"])
        self.backup_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.backup_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.backup_table.setAccessibleName("Verified backup history")
        backup_layout.addWidget(self.backup_table)
        actions = QHBoxLayout()
        self._action_buttons: list[QPushButton] = []
        for text, handler in (
            ("Back Up Library…", self.backup),
            ("Restore Selected", self.restore_selected),
            ("Verify Selected", self.verify_selected),
            ("Delete Selected", self.delete_selected),
            ("Open Backup Folder", self.open_folder),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            actions.addWidget(button)
            self._action_buttons.append(button)
        backup_layout.addLayout(actions)
        layout.addWidget(self.backup_group)
        layout.addStretch(1)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(panel)
        self._scroll_area = scroll
        self.setCentralWidget(scroll)
        self.resize(960, 760)
        self.setMinimumSize(720, 560)
        for button in self._action_buttons:
            button.setEnabled(False)
        QTimer.singleShot(0, self.refresh_backups)
        QTimer.singleShot(0, self.refresh_jobs)
        QTimer.singleShot(0, self.refresh_inventory)
        if self._launch_intent == "restore":
            QTimer.singleShot(0, self._focus_restore_controls)


    def export_platform_snapshot(self) -> None:
        suggested = f"Aperture-platform-snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        selected, _filter = QFileDialog.getSaveFileName(
            self, "Export Platform Snapshot", str(Path.home() / suggested), "JSON files (*.json)"
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.casefold() != ".json":
            destination = destination.with_suffix(".json")
        try:
            version_path = Path(__file__).resolve().parents[3] / "VERSION"
            version = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else "unknown"
            PlatformSnapshotReader(self.library, aperture_version=version).write(destination)
        except Exception as exc:
            QMessageBox.critical(self, "Platform snapshot failed", str(exc))
            return
        self.status_label.setText(f"Platform snapshot written to {destination}")
        QMessageBox.information(self, "Platform Snapshot", f"Snapshot created:\n{destination}")

    def _focus_restore_controls(self) -> None:
        """Bring the backup/restore controls into view for a Restore Library launch."""
        self.backup_group.setFocus(Qt.FocusReason.OtherFocusReason)
        self._scroll_area.ensureWidgetVisible(self.backup_group, 24, 24)
        if self.backup_table.rowCount() > 0:
            self.backup_table.selectRow(0)
        self.status_label.setText(
            "Restore Library — select a verified backup, then choose Restore Selected."
        )

    def _opened_library_context(self):
        service = self._library_service()
        return service.open(self.library)

    def run_health_check(self) -> None:
        opened = None
        try:
            self._set_operation_status("Running library and subsystem health checks…")
            container = _platform.foundation_factory()
            opened = LibraryService(container.clock, container.uuid_generator).open(self.library)
            service = LibraryHealthService(
                layout=opened.layout,
                connection_factory=opened.connection_factory,
                integrity_checker=_platform.integrity_checker,
                update_settings_path=container.paths.state_dir / "updates.json",
                subsystem_registry=container.subsystem_registry,
                capability_registry=container.capability_registry,
            )
            report = service.assess()
        except Exception as exc:
            self._set_operation_status("Health check failed", busy=False)
            QMessageBox.critical(self, "Health check failed", str(exc))
            return
        finally:
            if opened is not None:
                opened.close()
        status = (
            f"{report.error_count} error(s), {report.warning_count} warning(s)"
            if report.error_count or report.warning_count
            else "All checks passed"
        )
        self.health_summary_label.setText(status)
        details = "\n".join(
            f"{check.severity.value.upper()}: {check.title} — {check.summary}"
            for check in report.checks
        )
        self._set_operation_status("Health check complete", busy=False)
        QMessageBox.information(self, "Aperture Health", details)

    def run_platform_certification(self) -> None:
        opened = None
        try:
            self._set_operation_status("Running Version 2 platform certification…")
            container = _platform.foundation_factory()
            opened = LibraryService(container.clock, container.uuid_generator).open(self.library)
            health = LibraryHealthService(
                layout=opened.layout,
                connection_factory=opened.connection_factory,
                integrity_checker=_platform.integrity_checker,
                update_settings_path=container.paths.state_dir / "updates.json",
                subsystem_registry=container.subsystem_registry,
                capability_registry=container.capability_registry,
            )
            report = PlatformCertificationService(
                health_service=health,
                subsystem_registry=container.subsystem_registry,
                capability_registry=container.capability_registry,
            ).run()
        except Exception as exc:
            message = str(exc)
            locked = "lock" in message.casefold() or (
                "already" in message.casefold() and "open" in message.casefold()
            )
            if locked:
                self._set_operation_status(
                    "Platform certification waiting for library access", busy=False
                )
                answer = QMessageBox.question(
                    self,
                    "Platform Certification",
                    "The selected Aperture Library is currently in use.\n\n"
                    f"Library: {self.library}\n\nClose Aperture, then choose Retry.",
                    QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if answer == QMessageBox.StandardButton.Retry:
                    QTimer.singleShot(0, self.run_platform_certification)
                return
            self._set_operation_status("Platform certification failed", busy=False)
            QMessageBox.critical(self, "Platform certification failed", message)
            return
        finally:
            if opened is not None:
                opened.close()
        self.certification_summary_label.setText(
            f"{report.overall_status.value.upper()}: {report.failure_count} failure(s), "
            f"{report.warning_count} warning section(s)."
        )
        details = []
        for section in report.sections:
            details.append(
                f"{section.status.value.upper()}: {section.title} ({section.duration_ms} ms)"
            )
            details.extend(f"  - {finding.message}" for finding in section.findings)
        self._set_operation_status("Platform certification complete", busy=False)
        QMessageBox.information(self, "Version 2 Platform Certification", "\n".join(details))

    def manage_bioclip_resources(self) -> None:
        opened = None
        try:
            container = _platform.foundation_factory()
            opened = LibraryService(container.clock, container.uuid_generator).open(self.library)
            from natureai_next.application.ai_resources import LocalAIResourceService
            from natureai_next.application.ai_setup import BioCLIPQuickSetupService
            from natureai_next.infrastructure.ai.package_builder import Ed25519ModelPackageBuilder
            from natureai_next.infrastructure.ai.resources import LocalAIResourceBackend
            from natureai_next.infrastructure.taxonomy.package_builder import (
                Ed25519TaxonomyPackageBuilder,
            )
            from natureai_next.ui.qt.ai_setup import BioCLIPSetupDialog

            resources = LocalAIResourceService(
                backend=LocalAIResourceBackend(
                    factory=opened.connection_factory,
                    models_root=container.paths.models_dir,
                    id_factory=lambda: str(container.uuid_generator.new_uuid()),
                    now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
                ),
                model_package_builder=Ed25519ModelPackageBuilder(),
                taxonomy_package_builder=Ed25519TaxonomyPackageBuilder(),
            )
            dialog = BioCLIPSetupDialog(BioCLIPQuickSetupService(resources), self)
            dialog.exec()
            if getattr(dialog, "setup_succeeded", False):
                self._set_operation_status("BioCLIP resource setup completed", busy=False)
                self.refresh_inventory()
        except Exception as exc:
            QMessageBox.critical(self, "BioCLIP resource setup failed", str(exc))
        finally:
            if opened is not None:
                opened.close()

    def repair_bioclip_prompts(self) -> None:
        opened = None
        try:
            container = _platform.foundation_factory()
            opened = LibraryService(container.clock, container.uuid_generator).open(self.library)
            from natureai_next.application.ai_resources import LocalAIResourceService
            from natureai_next.application.ai_setup import BioCLIPQuickSetupService
            from natureai_next.infrastructure.ai.package_builder import Ed25519ModelPackageBuilder
            from natureai_next.infrastructure.ai.resources import LocalAIResourceBackend
            from natureai_next.infrastructure.taxonomy.package_builder import (
                Ed25519TaxonomyPackageBuilder,
            )

            resources = LocalAIResourceService(
                backend=LocalAIResourceBackend(
                    factory=opened.connection_factory,
                    models_root=container.paths.models_dir,
                    id_factory=lambda: str(container.uuid_generator.new_uuid()),
                    now_us=lambda: int(container.clock.now_utc().timestamp() * 1_000_000),
                ),
                model_package_builder=Ed25519ModelPackageBuilder(),
                taxonomy_package_builder=Ed25519TaxonomyPackageBuilder(),
            )
            workspace = container.paths.models_dir / "bioclip-resource-workspace"
            _manifest, prompt_id, counts = BioCLIPQuickSetupService(
                resources
            ).install_default_prompt_set(workspace)
            if counts is None or counts[0] == 0:
                message = (
                    "The NatureAI BioCLIP prompt profile is now active. No taxonomy labels were available, "
                    "so install or activate GBIF/regional taxonomy data before analysing photographs."
                )
            else:
                message = (
                    f"NatureAI prompts activated and {counts[1]} taxonomy text embeddings built."
                )
            self._set_operation_status("BioCLIP prompts activated", busy=False)
            QMessageBox.information(self, "BioCLIP prompts activated", message)
        except Exception as exc:
            QMessageBox.critical(self, "BioCLIP prompt repair failed", str(exc))
        finally:
            if opened is not None:
                opened.close()

    def open_model_storage(self) -> None:
        try:
            models_dir = _platform.foundation_factory().paths.models_dir
            models_dir.mkdir(parents=True, exist_ok=True)
            self._open_operational_path(models_dir)
        except Exception as exc:
            QMessageBox.warning(self, "Model storage unavailable", str(exc))

    def manage_offline_maps(self) -> None:
        dialog = OfflineMapPackageDialog(
            self,
            platform=OfflineMapSetupPlatform(
                foundation_factory=_platform.foundation_factory,
                map_catalog_factory=_platform.map_catalog_factory,
                map_package_service_factory=_platform.map_package_service_factory,
                vector_map_converter_factory=_platform.vector_map_converter_factory,
            ),
        )
        dialog.exec()
        self.refresh_inventory()

    def refresh_inventory(self) -> None:
        try:
            inventory = self._inventory_reader_factory(self.library).inspect()
        except Exception as exc:
            self.inventory_summary_label.setText(f"Storage inventory unavailable: {exc}")
            return

        self.storage_table.setRowCount(len(inventory.storage))
        for row, entry in enumerate(inventory.storage):
            values = (
                entry.title,
                self._format_bytes(entry.size_bytes),
                str(entry.file_count),
                "Authoritative" if entry.authoritative else "Derived / managed",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(str(entry.path))
                self.storage_table.setItem(row, column, item)
        self.storage_table.resizeColumnsToContents()

        self.inventory_summary_label.setText(
            f"{self._format_bytes(inventory.total_bytes)} across Aperture-owned locations."
        )

    def _job_service_context(self):
        container = _platform.foundation_factory()
        opened = LibraryService(container.clock, container.uuid_generator).open(self.library)
        return opened, self._job_service_factory(opened.connection_factory)

    def refresh_jobs(self) -> None:
        opened = None
        try:
            opened, jobs = self._job_service_context()
            records = jobs.recent(100)
        except Exception as exc:
            self.health_summary_label.setText(f"Background work unavailable: {exc}")
            return
        finally:
            if opened is not None:
                opened.close()
        self.job_table.setRowCount(len(records))
        for row, job in enumerate(records):
            total = job.progress_total
            progress = (
                str(job.progress_current) if total is None else f"{job.progress_current}/{total}"
            )
            updated = datetime.fromtimestamp(job.modified_at_us / 1_000_000, tz=UTC).isoformat(
                timespec="seconds"
            )
            values = (
                job.job_type,
                job.state.value,
                progress,
                job.progress_message or job.error_code or "",
                updated,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, job.public_id)
                self.job_table.setItem(row, column, item)
        self.job_table.resizeColumnsToContents()
        active = sum(
            job.state.value in {"queued", "running", "paused", "interrupted"} for job in records
        )
        self.health_summary_label.setText(
            f"{active} active or resumable job(s); {len(records)} recent job(s) shown"
        )

    def _selected_job_public_id(self) -> str | None:
        row = self.job_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select work", "Select a background job first.")
            return None
        item = self.job_table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else None

    def _change_selected_job(self, action: str) -> None:
        public_id = self._selected_job_public_id()
        if public_id is None:
            return
        opened = None
        try:
            opened, jobs = self._job_service_context()
            changed = getattr(jobs, action)(public_id)
        except Exception as exc:
            QMessageBox.critical(self, "Background work", str(exc))
            return
        finally:
            if opened is not None:
                opened.close()
        if not changed:
            QMessageBox.information(
                self,
                "Background work",
                "The selected job cannot be changed from its current state.",
            )
        self.refresh_jobs()

    def pause_selected_job(self) -> None:
        self._change_selected_job("pause")

    def resume_selected_job(self) -> None:
        self._change_selected_job("resume")

    def cancel_selected_job(self) -> None:
        public_id = self._selected_job_public_id()
        if public_id is None:
            return
        answer = QMessageBox.warning(
            self,
            "Stop background work",
            "Request that the selected job stop? Completed authoritative data is retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._change_selected_job("cancel")

    def _set_operation_status(self, text: str, *, busy: bool = True) -> None:
        self.status_label.setText(text)
        self.progress.setVisible(busy)
        for button in self._action_buttons:
            button.setEnabled(not busy)
        QApplication.processEvents()

    def _open_operational_path(self, path: Path) -> None:
        target = path if path.is_dir() else path.parent
        target.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(target)  # type: ignore[attr-defined]

    def refresh_backups(self) -> None:
        self.status_label.setText("Refreshing verified backup history…")
        self.progress.setVisible(True)
        backups = self.recovery.list_backups(self.library / "backups")
        self.backup_table.setRowCount(len(backups))
        for row, backup in enumerate(backups):
            values = (
                backup.created_at_utc.replace("T", " ").replace("+00:00", " UTC"),
                backup.library_name,
                f"{backup.size_bytes / (1024 * 1024):.1f} MB",
                backup.database_path.name,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, str(backup.database_path))
                self.backup_table.setItem(row, column, item)
        self.backup_table.resizeColumnsToContents()
        self.status_label.setText(f"Ready — {len(backups)} verified backup(s) found")
        self.progress.setVisible(False)
        for button in self._action_buttons:
            button.setEnabled(True)

    def _selected_backup_path(self) -> Path | None:
        row = self.backup_table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Select a backup", "Select a verified backup from the list first."
            )
            return None
        item = self.backup_table.item(row, 0)
        return Path(str(item.data(Qt.ItemDataRole.UserRole))) if item is not None else None

    def verify_selected(self) -> None:
        selected = self._selected_backup_path()
        if selected is not None:
            self._verify_path(selected)

    def restore_selected(self) -> None:
        selected = self._selected_backup_path()
        if selected is not None:
            self._restore_path(selected)

    def delete_selected(self) -> None:
        selected = self._selected_backup_path()
        if selected is None:
            return
        answer = QMessageBox.warning(
            self,
            "Delete backup",
            f"Delete this verified backup and its manifest?\n\n{selected.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        selected.unlink(missing_ok=True)
        selected.with_suffix(selected.suffix + ".manifest.json").unlink(missing_ok=True)
        self.refresh_backups()

    def _library_service(self) -> LibraryService:
        container = _platform.foundation_factory()
        return LibraryService(container.clock, container.uuid_generator)

    def _cleanup_context(self):
        service = self._library_service()
        opened = service.open(self.library)
        roots = tuple(
            path
            for path in (self.library / "temp", self.library / "cache" / "temporary")
            if path.exists()
        )
        cleanup = self._cleanup_service_factory(opened.connection_factory, roots)
        now_us = int(datetime.now(UTC).timestamp() * 1_000_000)
        return opened, cleanup, now_us, RetentionPolicy()

    @staticmethod
    def _format_bytes(value: int) -> str:
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024
        return f"{amount:.1f} TB"

    def preview_cleanup(self) -> None:
        opened = None
        try:
            opened, cleanup, now_us, policy = self._cleanup_context()
            preview = cleanup.preview(now_us=now_us, policy=policy)
        except Exception as exc:
            QMessageBox.critical(self, "Cleanup preview failed", str(exc))
            return
        finally:
            if opened is not None:
                opened.close()
        text = (
            f"Eligible completed jobs: {preview.jobs_eligible}\n"
            f"Eligible dispatched events: {preview.events_eligible}\n"
            f"Stale temporary files: {preview.temporary_files_eligible}\n"
            f"Potential space recovery: {self._format_bytes(preview.temporary_bytes_eligible)}"
        )
        self.cleanup_summary_label.setText(text.replace("\n", " • "))
        QMessageBox.information(
            self,
            "Cleanup preview",
            text + "\n\nAuthoritative library data is never included.",
        )

    def run_cleanup(self) -> None:
        answer = QMessageBox.question(
            self,
            "Run lean cleanup",
            "Remove eligible completed-job history, dispatched events, and stale temporary files?\n\n"
            "Photographs, observations, AI enrichment, taxonomy, and map packages are not removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        opened = None
        try:
            self._set_operation_status("Running bounded cleanup…")
            opened, cleanup, now_us, policy = self._cleanup_context()
            report = cleanup.cleanup(now_us=now_us, policy=policy)
        except Exception as exc:
            self._set_operation_status("Cleanup failed", busy=False)
            QMessageBox.critical(self, "Cleanup failed", str(exc))
            return
        finally:
            if opened is not None:
                opened.close()
        self._set_operation_status("Cleanup complete", busy=False)
        detail = (
            f"Jobs removed: {report.jobs_removed}\n"
            f"Events removed: {report.events_removed}\n"
            f"Temporary files removed: {report.temporary_files_removed}\n"
            f"Empty folders removed: {report.empty_directories_removed}\n"
            f"Space recovered: {self._format_bytes(report.temporary_bytes_removed)}"
        )
        self.cleanup_summary_label.setText(detail.replace("\n", " • "))
        QMessageBox.information(self, "Cleanup complete", detail)

    def backup(self) -> None:
        default = self.library / "backups" / suggested_backup_name(self.library.name)
        selected, _ = QFileDialog.getSaveFileName(
            self, "Back Up Aperture Library", str(default), "SQLite backup (*.sqlite3)"
        )
        if not selected:
            return
        try:
            with self._library_service().open(self.library) as opened:
                result = LibraryBackupService(
                    opened.backup_database,
                    library_name=opened.manifest.display_name,
                    additional_databases={
                        "science": resolve_application_paths().subsystem_databases_dir
                        / "science.sqlite3",
                        "marine-maritime": resolve_application_paths().subsystem_databases_dir
                        / "marine-maritime.sqlite3",
                        "deletion-approvals": resolve_application_paths().subsystem_databases_dir
                        / "deletion-approvals.sqlite3",
                        "access-control": resolve_application_paths().subsystem_databases_dir
                        / "access-control.sqlite3",
                        "server-media": resolve_application_paths().subsystem_databases_dir
                        / "server-media.sqlite3",
                        "server-jobs": resolve_application_paths().subsystem_databases_dir
                        / "server-jobs.sqlite3",
                        "server-exports": resolve_application_paths().subsystem_databases_dir
                        / "server-exports.sqlite3",
                    },
                ).create(Path(selected))
        except Exception as exc:
            QMessageBox.critical(self, "Backup failed", str(exc))
            return
        QMessageBox.information(
            self,
            "Backup complete",
            f"Backup verified and saved:\n{result.database_path}\n\nSHA-256: {result.sha256}",
        )
        self.refresh_backups()

    def verify(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Verify Aperture Backup",
            str(self.library / "backups"),
            "SQLite backup (*.sqlite3 *.db)",
        )
        if selected:
            self._verify_path(Path(selected))

    def _verify_path(self, selected: Path) -> None:
        try:
            item = self.recovery.verify(selected)
        except Exception as exc:
            QMessageBox.critical(self, "Backup invalid", str(exc))
            return
        QMessageBox.information(
            self,
            "Backup verified",
            f"Library: {item.library_name}\nCreated: {item.created_at_utc}\nSHA-256: {item.sha256}",
        )

    def restore(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Restore Aperture Library",
            str(self.library / "backups"),
            "SQLite backup (*.sqlite3 *.db)",
        )
        if selected:
            self._restore_path(Path(selected))

    def _restore_path(self, selected: Path) -> None:
        try:
            verified = self.recovery.verify(selected)
        except Exception as exc:
            QMessageBox.critical(self, "Restore unavailable", str(exc))
            return

        prompt = QMessageBox(self)
        prompt.setIcon(QMessageBox.Icon.Warning)
        prompt.setWindowTitle("Restore Aperture library")
        prompt.setText(
            "Aperture will close while the selected database is restored. "
            "The Maintenance Center will remain visible and show progress. "
            "After validation, Aperture will restart automatically."
        )
        prompt.setInformativeText(
            f"Restore backup: {verified.database_path.name}\nCreated: {verified.created_at_utc}"
        )
        backup_button = prompt.addButton("Back Up and Restore", QMessageBox.ButtonRole.AcceptRole)
        no_backup_button = prompt.addButton(
            "Restore Without Backup", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_button = prompt.addButton(QMessageBox.StandardButton.Cancel)
        prompt.setDefaultButton(backup_button)
        prompt.exec()
        clicked = prompt.clickedButton()
        if clicked is cancel_button or clicked not in (backup_button, no_backup_button):
            return
        create_emergency_backup = clicked is backup_button

        emergency = None
        target = self.library / "library.sqlite3"
        rollback = target.with_suffix(target.suffix + ".pre-restore-rollback")
        temp = target.with_suffix(target.suffix + ".restore.tmp")
        _append_restore_log(
            self.library,
            "started",
            backup=str(verified.database_path),
            emergency_backup=create_emergency_backup,
        )
        try:
            self.show()
            self.raise_()
            self.activateWindow()
            if create_emergency_backup:
                self._set_operation_status("Creating and verifying the emergency backup…")
                emergency = _create_emergency_backup(self.library)
                _append_restore_log(
                    self.library, "emergency-backup-created", path=str(emergency.database_path)
                )

            self._set_operation_status("Closing Aperture safely before restore…")
            if not _request_aperture_close():
                raise RuntimeError(
                    "Aperture did not close. Save your work, close Aperture, and try again."
                )

            self._set_operation_status("Waiting for the library lock to be released…")
            if not _wait_for_library_unlock(self.library):
                raise RuntimeError("Aperture closed, but the library lock was not released safely.")

            self._set_operation_status("Restoring the selected database…")
            shutil.copy2(target, rollback)
            shutil.copy2(verified.database_path, temp)
            # Runs PRAGMA integrity_check and PRAGMA foreign_key_check, then closes every SQLite handle.
            _platform.validate_database(temp)
            _append_restore_log(self.library, "validated-and-closed", database=str(temp))
            _platform.replace_database(
                temp,
                target,
                retry_logger=lambda attempt, exc: _append_restore_log(
                    self.library,
                    "replace-retry",
                    str(exc),
                    attempt=attempt,
                    source=str(temp),
                    target=str(target),
                ),
            )
            _append_restore_log(
                self.library, "restored", restored_database=str(verified.database_path)
            )
        except Exception as exc:
            if rollback.is_file():
                shutil.copy2(rollback, target)
            _append_restore_log(self.library, "failed", str(exc))
            self._set_operation_status("Restore failed", busy=False)
            QMessageBox.critical(
                self, "Restore failed", f"The previous database was preserved or restored.\n\n{exc}"
            )
            return
        finally:
            temp.unlink(missing_ok=True)

        self._set_operation_status("Restore complete. Restarting Aperture…")
        detail = "The database was restored and validated successfully."
        if emergency is not None:
            detail += f"\n\nEmergency backup: {emergency.database_path}"
        detail += "\n\nAperture will now restart."
        QMessageBox.information(self, "Restore complete", detail)
        _launch_aperture(self.library)
        QTimer.singleShot(1500, self.close)

    def open_folder(self) -> None:
        folder = self.library / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]


def main(
    argv: Sequence[str] | None = None,
    *,
    inventory_reader_factory: Callable[[Path], MaintenanceInventoryReader],
    cleanup_service_factory: Callable[[object, tuple[Path, ...]], WorkflowCleanupService],
    job_service_factory: Callable[[object], JobService],
    platform: MaintenancePlatform,
) -> int:
    global _platform
    _platform = platform
    import argparse

    parser = argparse.ArgumentParser(prog="aperture-maintenance-center")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--intent", choices=("restore", "maintenance"), default="maintenance")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication([])
    library = args.library or _last_library()
    if library is None or not is_aperture_library(library):
        library = _select_library(None)
    if library is None:
        return 2
    LauncherConfigurationStore().remember_library(library)
    window = MaintenanceCenterWindow(
        library, inventory_reader_factory, cleanup_service_factory, job_service_factory,
        launch_intent=args.intent,
    )
    window.show()
    window.raise_()
    window.activateWindow()
    app.processEvents()
    if args.ready_file is not None:
        args.ready_file.parent.mkdir(parents=True, exist_ok=True)
        temp = args.ready_file.with_suffix(args.ready_file.suffix + ".tmp")
        temp.write_text(
            json.dumps({"status": "window-ready", "pid": os.getpid()}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp.replace(args.ready_file)
    return app.exec()

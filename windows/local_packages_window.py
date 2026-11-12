#----------------------------------------
# Súbor: windows/local_packages_window.py
#----------------------------------------

import os
import json
from PyQt6.QtWidgets import (QDialog, QTableWidgetItem, QHeaderView, QWidget, QHBoxLayout)
from PyQt6 import uic
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from core._path import Paths
from core.logic.language_manager import LanguageManager
from windows.custom_title_bar import CustomTitleBar
from windows.custom_message_box import CustomMessageBox

from core.core_bridge import CoreBridge
from core.core_states import LinkerOperationStatus

class LinkerWorker(QThread):
    """Vlákno na pozadí, ktoré volá službu v CoreBridge a zabraňuje zamrznutiu okna."""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(LinkerOperationStatus, str)

    def __init__(self, core, venv_path, selected_items):
        super().__init__()
        self.core = core
        self.venv_path = venv_path
        self.selected_items = selected_items

    def run(self):
        status, error_msg = CoreBridge.apply_local_links(
            self.core, 
            self.venv_path, 
            self.selected_items, 
            self.log_signal.emit
        )
        self.finished_signal.emit(status, error_msg)


class LocalPackagesWindow(QDialog):
    def __init__(self, parent, venv_path):
        super().__init__(parent)
        self.core = parent.core
        self.venv_path = venv_path
        
        self.linker_thread = None
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("LocalPackagesWindow")
        
        uic.loadUi(Paths.get_ui_file_path("local_packages_window.ui"), self)
        
        self.title_bar = CustomTitleBar(self)
        self.main_layout.insertWidget(0, self.title_bar)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        
        self.setup_ui()
        self.connect_signals()
        self.retranslate_ui()
        
        self.refresh_list()

    def setup_ui(self):
        header = self.table_packages.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)
        self.table_packages.horizontalHeaderItem(0).setText(LanguageManager.get("col_local_pkg_name", "Názov balíčka"))
        self.table_packages.horizontalHeaderItem(1).setText(LanguageManager.get("col_local_pkg_version", "Verzia"))
        self.table_packages.horizontalHeaderItem(2).setText(LanguageManager.get("col_local_pkg_status", "Stav"))
        self.table_packages.horizontalHeaderItem(3).setText(LanguageManager.get("col_local_pkg_description", "Stručný popis"))
        if hasattr(self, 'title_bar'):
            self.title_bar.lbl_title.setText(self.windowTitle())
            
        venv_name = os.path.basename(self.venv_path)
        self.lbl_header.setText(LanguageManager.get("local_pkg_header", "Lokálne balíčky pre: {name}").format(name=venv_name))

    def connect_signals(self):
        self.btn_refresh.clicked.connect(self.refresh_list)
        self.btn_apply.clicked.connect(self.apply_changes)

    @pyqtSlot(str)
    def log(self, message):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_ui_locked(self, locked: bool):
        self.btn_refresh.setEnabled(not locked)
        self.btn_apply.setEnabled(not locked)
        self.table_packages.setEnabled(not locked)

    def _get_state_file_path(self):
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_packages_dir = os.path.join(self.venv_path, site_folder, "site-packages")
        os.makedirs(site_packages_dir, exist_ok=True)
        return os.path.join(site_packages_dir, "venvhub.json")

    def refresh_list(self):
        self.table_packages.setRowCount(0)
        local_root = getattr(self.core, 'local_packages_root', "")
        
        if not local_root or not os.path.exists(local_root):
            self.log(LanguageManager.get("local_pkg_err_no_root", "⚠️ Upozornenie: Cesta k lokálnym balíčkom nie je nastavená alebo neexistuje."))
            return
            
        state_path = self._get_state_file_path()
        linked_packages = set()
        if os.path.exists(state_path):
            try:
                with open(state_path, 'r', encoding='utf-8') as f:
                    linked_packages = set(json.load(f).keys())
            except Exception as e:
                self.log(f"Chyba pri čítaní stavového súboru: {e}")

        self.log(LanguageManager.get("local_pkg_log_loading", "\n🔄 Načítavam dostupné lokálne balíčky..."))
        loaded_count = 0
        
        for item in os.listdir(local_root):
            pkg_path = os.path.join(local_root, item)
            if os.path.isdir(pkg_path):
                meta_path = os.path.join(pkg_path, "local_meta.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            
                        display_name = meta.get("name", item)
                        pkg_version = meta.get("version", "1.0.0")
                        pkg_desc = str(meta.get("short_description", ""))
                        is_linked = item in linked_packages
                        
                        self._add_row_to_table(display_name, pkg_version, pkg_path, is_linked, pkg_desc)
                        loaded_count += 1
                    except Exception as e:
                        self.log(f"⚠️ Chyba pri čítaní {meta_path}: {e}")

        self.log(LanguageManager.get("local_pkg_log_loaded", "✅ Boli úspešne načítané {count} lokálne balíčky.").format(count=loaded_count))

    def _add_row_to_table(self, display_name, version, full_path, is_linked, description):
        row = self.table_packages.rowCount()
        self.table_packages.insertRow(row)
        
        item_name = QTableWidgetItem(display_name)
        item_name.setFlags(item_name.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item_name.setCheckState(Qt.CheckState.Checked if is_linked else Qt.CheckState.Unchecked)
        item_name.setData(Qt.ItemDataRole.UserRole, os.path.normpath(full_path))
        self.table_packages.setItem(row, 0, item_name)
        
        item_ver = QTableWidgetItem(version)
        item_ver.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_packages.setItem(row, 1, item_ver)
        
        status_text = LanguageManager.get("local_pkg_status_linked", "✅ Prelinkované") if is_linked else "-"
        item_status = QTableWidgetItem(status_text)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_packages.setItem(row, 2, item_status)
        
        self.table_packages.setItem(row, 3, QTableWidgetItem(description))

    def apply_changes(self):
        if self.linker_thread and self.linker_thread.isRunning():
            return
            
        selected_items_data = []
        for row in range(self.table_packages.rowCount()):
            item_name = self.table_packages.item(row, 0)
            if item_name.checkState() == Qt.CheckState.Checked:
                selected_items_data.append({
                    'name': item_name.text(), 
                    'path': item_name.data(Qt.ItemDataRole.UserRole)
                })

        self._set_ui_locked(True)

        self.linker_thread = LinkerWorker(self.core, self.venv_path, selected_items_data)
        self.linker_thread.log_signal.connect(self.log, Qt.ConnectionType.QueuedConnection)
        self.linker_thread.finished_signal.connect(self._on_apply_finished, Qt.ConnectionType.QueuedConnection)
        
        self.linker_thread.finished.connect(self.linker_thread.deleteLater)
        self.linker_thread.start()

    @pyqtSlot(LinkerOperationStatus, str)
    def _on_apply_finished(self, status: LinkerOperationStatus, error_msg: str):
        self._set_ui_locked(False)
        self.linker_thread = None

        if status == LinkerOperationStatus.SUCCESS:
            self.refresh_list()
        elif status == LinkerOperationStatus.MISSING_LOCAL_DEP:
            CustomMessageBox.critical(self, LanguageManager.get("title_error", "Chyba"), error_msg)
        elif status == LinkerOperationStatus.DEPENDENCY_ERROR:
            CustomMessageBox.warning(self, LanguageManager.get("title_warning", "Upozornenie"), LanguageManager.get("msg_dep_install_err", "Inštalácia externých závislostí zlyhala.\nSkontrolujte log pre viac informácií."))
        elif status == LinkerOperationStatus.ERROR:
            CustomMessageBox.critical(self, LanguageManager.get("title_critical_error", "Kritická chyba"), error_msg)
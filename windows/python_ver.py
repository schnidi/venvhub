#----------------------------------------
# Súbor: windows/python_ver.py
#----------------------------------------

import os
from PyQt6.QtWidgets import QWidget, QTableWidgetItem, QHeaderView, QMessageBox
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QColor
from PyQt6 import uic
from core._path import Paths
from core.logic.language_manager import LanguageManager

from core.logic.python_installer.box.python_ver_json import PythonVersionJsonManager
from core.logic.python_installer.box.source_path import SourcePathManager
from core.logic.python_installer.button.python_install import PythonInstaller

from core.logic.sluzby.delete import UniversalDeleter
from core.logic.python_installer.button.pip_installer import PipInstaller

from core.logic.sluzby.python_runtime_inspector import PipStatusWorker
from core.logic.python_detector import PythonDetector
from PyQt6.QtCore import pyqtSignal

# --- PRIDANÝ IMPORT PRE NAŠU VLASTNÚ LIŠTU ---
from windows.custom_message_box import CustomMessageBox

class RuntimeDeleteWorker(QThread):
    """Asynchrónny robot na postupné mazanie runtimu s odosielaním priebehu."""
    progress = pyqtSignal(int)
    log_msg = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)

    def __init__(self, target_path):
        super().__init__()
        self.target_path = target_path

    def run(self):
        from core.logic.sluzby.copy_del import CopyDelService
        result = CopyDelService.safe_delete_with_progress(
            target_path=self.target_path,
            log_func=self.log_msg.emit,
            progress_func=self.progress.emit
        )
        self.finished_signal.emit(result)

class PythonVerWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        ui_path = Paths.get_ui_file_path("python_ver.ui")
        uic.loadUi(ui_path, self)

        self.json_manager = PythonVersionJsonManager(self.combo_urls)
        self.source_path_manager = SourcePathManager(self.edit_path, self.btn_browse, self)
        self.installer = PythonInstaller(self.log_output, self.progress_bar, self.btn_install)
        self.pip_installer = PipInstaller(self.log_output, self.btn_repair)

        self.check_thread = None
        self.check_worker = None

        self._setup_table()
        self._connect_signals()

        self.json_manager.load_versions()
        self.retranslate_ui()
        self.refresh_table()

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)
        if self.table_runtimes.columnCount() >= 3:
            if not self.table_runtimes.horizontalHeaderItem(0):
                self.table_runtimes.setHorizontalHeaderLabels(["", "", ""])
            self.table_runtimes.horizontalHeaderItem(0).setText(LanguageManager.get("col_runtime_ver", "Verzia"))
            self.table_runtimes.horizontalHeaderItem(1).setText(LanguageManager.get("col_runtime_path", "Cesta"))
            self.table_runtimes.horizontalHeaderItem(2).setText(LanguageManager.get("col_runtime_pip", "Stav PIP"))
            
        self.log_output.clear()
        self.refresh_table()

    def _setup_table(self):
        header = self.table_runtimes.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.table_runtimes.setSelectionBehavior(self.table_runtimes.SelectionBehavior.SelectRows)
        self.table_runtimes.setEditTriggers(self.table_runtimes.EditTrigger.NoEditTriggers)

    def _connect_signals(self):
        self.btn_edit_urls.clicked.connect(self._on_edit_urls_clicked)
        self.combo_urls.currentIndexChanged.connect(self._on_version_selected)
        self.btn_install.clicked.connect(self.start_installation)
        
        self.btn_refresh.clicked.connect(self.force_refresh_table)
        
        self.btn_delete.clicked.connect(self.delete_selected_runtime)
        self.btn_repair.clicked.connect(self.repair_selected_pip)
        self.table_runtimes.itemSelectionChanged.connect(self.on_row_selected)
        
        self.installer.installation_finished.connect(
            lambda result: self.refresh_table() if result.get('success') else None
        )
        self.pip_installer.installation_finished.connect(
            lambda result: self.refresh_table() if result.get('success') else None
        )
        
        # --- NOVÉ: Prepojenie pre živú kontrolu, či zložka z cesty náhodou už neexistuje ---
        self.edit_path.textChanged.connect(self._check_install_status)

    def start_installation(self):
        source_info = self.source_path_manager.get_source_info()
        if not source_info['is_valid']:
            self.log_output.append(f"CHYBA: {source_info['error']}")
            return

        self.installer.install(source_info)

    def force_refresh_table(self):
        self.log_output.append(LanguageManager.get("msg_force_scan", "Vynútené skenovanie disku (tvrdý reset pamäte)..."))
        PythonDetector.get_installed_pythons(force_refresh=True)
        self.refresh_table()

    def refresh_table(self):
        self.table_runtimes.setRowCount(0)
        self.btn_repair.setEnabled(False) 
        
        all_pythons = PythonDetector.get_installed_pythons()
        local_pythons = [p for p in all_pythons if p.get('is_local')]
        
        paths_to_check = []
        
        for p in local_pythons:
            row = self.table_runtimes.rowCount()
            self.table_runtimes.insertRow(row)
            
            status_text = p['pip_status']
            
            if status_text == "OK":
                display_status = LanguageManager.get("status_ok_fmt", "✅ OK")
                status_color = QColor("#2ecc71")
            elif status_text == "checking":
                display_status = LanguageManager.get("status_checking_fmt", "⏳ Kontrolujem...")
                status_color = QColor("#f39c12")
                paths_to_check.append(p['path'])
            else:
                display_status = LanguageManager.get("status_missing_fmt", "❌ Chýba")
                status_color = QColor("#e74c3c")
                
            ver_name = p['display'].replace("[Local] ", "").strip()
            folder_path = os.path.dirname(p['path'])
            
            item_ver = QTableWidgetItem(ver_name)
            item_path = QTableWidgetItem(folder_path)
            item_pip = QTableWidgetItem(display_status)
            
            item_pip.setForeground(status_color)
            item_pip.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            item_pip.setData(Qt.ItemDataRole.UserRole, status_text)
            
            self.table_runtimes.setItem(row, 0, item_ver)
            self.table_runtimes.setItem(row, 1, item_path)
            self.table_runtimes.setItem(row, 2, item_pip)
            
        self.log_output.append(LanguageManager.get("msg_loaded_from_mem", "Zoznam načítaný rýchlo z pamäte."))
        
        if paths_to_check:
            self._start_pip_check(paths_to_check)
            
        # --- NOVÉ: Po obnove (aj po mazaní) skontrolujeme stav tlačidla install ---
        self._check_install_status()

    def _start_pip_check(self, paths):
        try:
            if self.check_thread and self.check_thread.isRunning():
                return
        except RuntimeError:
            self.check_thread = None
            self.check_worker = None
            
        self.check_thread = QThread()
        self.check_worker = PipStatusWorker(paths)
        self.check_worker.moveToThread(self.check_thread)
        
        self.check_worker.result_ready.connect(self._on_pip_check_result)
        self.check_worker.finished.connect(self.check_thread.quit)
        self.check_worker.finished.connect(self.check_worker.deleteLater)
        self.check_thread.finished.connect(self.check_thread.deleteLater)
        
        self.check_thread.finished.connect(self._cleanup_check_thread)
        
        self.check_thread.started.connect(self.check_worker.run)
        self.check_thread.start()

    def _cleanup_check_thread(self):
        self.check_thread = None
        self.check_worker = None

    def _on_pip_check_result(self, python_path, is_ok):
        status_str = "OK" if is_ok else "ERROR"
        PythonDetector.update_pip_status(python_path, status_str)
        
        expected_dir = os.path.normpath(os.path.dirname(python_path)).lower()
        
        for row in range(self.table_runtimes.rowCount()):
            path_in_table = os.path.normpath(self.table_runtimes.item(row, 1).text()).lower()
            if path_in_table == expected_dir:
                item_pip = self.table_runtimes.item(row, 2)
                if is_ok:
                    item_pip.setText(LanguageManager.get("status_ok_fmt", "✅ OK"))
                    item_pip.setForeground(QColor("#2ecc71"))
                else:
                    item_pip.setText(LanguageManager.get("status_missing_fmt", "❌ Chýba"))
                    item_pip.setForeground(QColor("#e74c3c"))
                    
                item_pip.setData(Qt.ItemDataRole.UserRole, status_str)
                break
                
        self.on_row_selected()

    def on_row_selected(self):
        selected_items = self.table_runtimes.selectedItems()
        if not selected_items:
            self.btn_repair.setEnabled(False)
            return

        row = selected_items[0].row()
        pip_status_item = self.table_runtimes.item(row, 2)
        
        raw_status = pip_status_item.data(Qt.ItemDataRole.UserRole)
        is_broken = (raw_status not in ["OK", "checking"])
        
        self.btn_repair.setEnabled(is_broken)

    def repair_selected_pip(self):
        selected_items = self.table_runtimes.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        runtime_path = self.table_runtimes.item(row, 1).text()
        python_exe_path = os.path.join(runtime_path, 'python.exe')
        
        self.log_output.append(LanguageManager.get("msg_starting_pip_repair", "Spúšťam opravu PIP pre: {0}...").format(os.path.basename(runtime_path)))
        self.pip_installer.install(python_exe_path)
        
    def _on_edit_urls_clicked(self):
        self.json_manager.edit_jsonl_file_as_admin(parent_widget=self)
        self.log_output.append(LanguageManager.get("msg_jsonl_editor_opened", "Editor JSONL otvorený. Po úprave obnovte zoznam."))

    def _on_version_selected(self):
        url = self.json_manager.get_selected_url()
        self.edit_path.setText(url if url else "")
            
    def delete_selected_runtime(self):
        selected_items = self.table_runtimes.selectedItems()
        if not selected_items:
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(self, LanguageManager.get("title_warning", "Upozornenie"), LanguageManager.get("msg_select_version_first", "Najskôr vyberte verziu zo zoznamu."))
            return
            
        row = selected_items[0].row()
        version_name = self.table_runtimes.item(row, 0).text()
        target_path = self.table_runtimes.item(row, 1).text()
        
        # --- ZMENA NA NAŠU LIŠTU ---
        reply = CustomMessageBox.question(self, LanguageManager.get("title_confirm", "Potvrdenie"), LanguageManager.get("msg_confirm_delete_runtime", "Naozaj chcete natrvalo odstrániť túto položku?\n\n{0}").format(version_name), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            from windows.progress_dialog import ProgressDialog
            
            # 1. Zostavíme Progress Dialog
            progress_title = LanguageManager.get("title_deleting", "Prebieha mazanie...")
            progress_msg = LanguageManager.get("msg_deleting_progress", "Mažem: {0}").format(version_name)
            
            progress_dialog = ProgressDialog(self)
            progress_dialog.setWindowTitle(progress_title)
            progress_dialog.set_message(progress_msg)
            progress_dialog.set_progress_mode(indeterminate=False) # Ukazuje presný stav 0-100%
            
            # 2. Vytvoríme a naštartujeme asynchrónne vlákno
            self._delete_worker = RuntimeDeleteWorker(target_path)

            def on_finished(result):
                progress_dialog.accept() # Bezpečné zatvorenie dialógu na hlavnom vlákne
                
                if result.get("success"):
                    self.log_output.append(LanguageManager.get("msg_runtime_deleted_success", "Položka '{0}' bola úspešne vymazaná.").format(version_name))
                    
                    python_exe_path = os.path.join(target_path, 'python.exe')
                    PythonDetector.remove_local_python(python_exe_path)
                    
                    self.refresh_table()
                else:
                    error_reason = result.get("error", "Neznáma chyba")
                    self.log_output.append(f"CHYBA: {error_reason}")
                    # --- ZMENA NA NAŠU LIŠTU ---
                    CustomMessageBox.critical(self, LanguageManager.get("title_error", "Chyba"), error_reason)

            # 3. Bezpečné medzivláknové prepojenie do GUI
            self._delete_worker.progress.connect(progress_dialog.set_progress_value, Qt.ConnectionType.QueuedConnection)
            self._delete_worker.log_msg.connect(self.log_output.append, Qt.ConnectionType.QueuedConnection)
            self._delete_worker.finished_signal.connect(on_finished, Qt.ConnectionType.QueuedConnection)
            
            # Uvoľnenie prostriedkov z pamäte po skončení
            self._delete_worker.finished.connect(self._delete_worker.deleteLater)
            
            self._delete_worker.start()
            progress_dialog.exec()

    def _check_install_status(self):
        """
        Skontroluje, či očakávaná zložka z URL už existuje.
        Ak áno, prepne inštalačné tlačidlo do stavu 'NAINŠTALOVANÉ'.
        """
        expected_dir = self.source_path_manager.get_expected_install_dir()
        is_installed = False
        
        if expected_dir and os.path.exists(expected_dir):
            if os.path.exists(os.path.join(expected_dir, "python.exe")):
                is_installed = True
            else:
                for item in os.listdir(expected_dir):
                    sub = os.path.join(expected_dir, item)
                    if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "python.exe")):
                        is_installed = True
                        break
                        
        if is_installed:
            self.btn_install.setText(LanguageManager.get("btn_already_installed", "✅ NAINŠTALOVANÉ"))
            self.btn_install.setEnabled(False)
        else:
            self.btn_install.setText(LanguageManager.get("btn_install", "🛠 INŠTALOVAŤ"))
            self.btn_install.setEnabled(True)
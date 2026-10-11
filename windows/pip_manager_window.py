#----------------------------------------
# Súbor: windows/pip_manager_window.py
#----------------------------------------

import os
from PyQt6.QtWidgets import (QDialog, QTableWidgetItem, QHeaderView, QVBoxLayout, 
                             QWidget, QMessageBox)
from PyQt6 import uic
from PyQt6.QtCore import Qt, QThread, pyqtSlot, pyqtSignal

from core._path import Paths
from windows.pip_package_widget import PipPackageWidget

from core.logic.button.pip.pip_list_worker import PipListWorker 
from core.logic.button.pip.pip_worker_allupdate import PipWorkerAllUpdate
from core.logic.language_manager import LanguageManager

from windows.custom_title_bar import CustomTitleBar


class FreezeWorker(QThread):
    """Asynchrónny robot, ktorý na pozadí generuje requirements.txt."""
    log_msg = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, venv_path, project_root, manager_type):
        super().__init__()
        self.venv_path = venv_path
        self.project_root = project_root
        self.manager_type = manager_type

    def run(self):
        from core.logic.button.pip.freeze import FreezeHandler
        # Spustenie existujúcej synchrónnej logiky na pozadí tohto vlákna
        success = FreezeHandler.run(
            self.venv_path, 
            self.project_root, 
            self.manager_type, 
            self.log_msg.emit
        )
        self.finished_signal.emit(success)


class PipManagerWindow(QDialog):
    def __init__(self, parent, venv_path, project_root):
        super().__init__(parent)
        self.venv_path = venv_path
        self.project_root = project_root
        
        self.thread = None
        self.worker = None
        self._pending_refresh = False
        
        # 1. Nastavíme okno bez rámov (Frameless)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        
        # --- OPRAVA: Povolíme QSS rámček a definujeme presné meno pre CSS ---
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("PipManagerWindow")
        
        uic.loadUi(Paths.get_ui_file_path("pip_manager_window.ui"), self)
        
        # 2. Vložíme Custom Title Bar
        self.title_bar = CustomTitleBar(self)
        self.main_layout.insertWidget(0, self.title_bar)
        
        # --- OPRAVA: Vložíme 1px okraj, inak obsah okna prekryje QSS rámček ---
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        
        self.lbl_header.setContentsMargins(0, 10, 0, 0)

        # Najprv nastavíme UI
        self.setup_ui()
        self.connect_signals()
        
        # Aplikujeme preklady
        self.retranslate_ui()
        
        # Prvé načítanie dát
        self.refresh_list()

    def setup_ui(self):
        header = self.table_packages.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        
        # Nastavenie počiatočných šírok stĺpcov
        self.table_packages.setColumnWidth(0, 200)
        self.table_packages.setColumnWidth(1, 150)
        self.table_packages.setColumnWidth(2, 150)
        
        self.table_packages.setColumnHidden(3, True) 

        # Vytvoríme layout pre pravý panel
        self.actions_layout = QVBoxLayout(self.group_package_actions)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        
        # Vytvoríme pravý panel IBA RAZ a vložíme ho tam nastálo
        self.package_actions_widget = PipPackageWidget(self, self.venv_path)
        self.actions_layout.addWidget(self.package_actions_widget)

    def retranslate_ui(self):
        """Preloží hlavné okno a pošle signál aj do vnútorného widgetu."""
        LanguageManager.translate_ui(self)
        
        # !!! NAVŽDY VYMAZAŤ TEXT NA VONKAJŠOM RÁME !!!
        self.group_package_actions.setTitle("")
        
        if hasattr(self, 'title_bar'):
            self.title_bar.lbl_title.setText(self.windowTitle())
            
        venv_name = os.path.basename(self.venv_path)
        fmt_header = LanguageManager.get("lbl_header_fmt", "Správca balíčkov pre: {0}")
        self.lbl_header.setText(fmt_header.format(venv_name))
        
        # Preložíme vnútorný widget
        if hasattr(self, 'package_actions_widget'):
            self.package_actions_widget.retranslate_ui()

        headers = [
            LanguageManager.get("col_pkg_name", "Názov balíčka"),
            LanguageManager.get("col_installed_ver", "Nainštalovaná verzia"),
            LanguageManager.get("col_latest_ver", "Najnovšia verzia"),
            "Akcie"
        ]
        
        for i, text in enumerate(headers):
            item = self.table_packages.horizontalHeaderItem(i)
            if item:
                item.setText(text)
            else:
                self.table_packages.setHorizontalHeaderItem(i, QTableWidgetItem(text))

    def connect_signals(self):
        self.btn_refresh.clicked.connect(self.refresh_list)
        self.btn_update_all.clicked.connect(self.on_update_all)
        self.btn_freeze.clicked.connect(self.on_freeze)
        self.table_packages.itemSelectionChanged.connect(self.on_package_selected)

    def safe_stop_thread(self):
        if self.thread is not None:
            if self.thread.isRunning():
                self.thread.quit()
                self.thread.wait() 
            self.thread.deleteLater()
            self.thread = None
        
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def refresh_list(self):
        self.safe_stop_thread()
        
        if hasattr(self, 'package_actions_widget'):
            self.package_actions_widget.clear_data()
            
        self.group_package_actions.setTitle("")
        
        self.table_packages.setRowCount(1)
        msg_loading = LanguageManager.get("msg_loading_pkgs", "🔄 Načítavam zoznam balíčkov, prosím čakajte...")
        loading_item = QTableWidgetItem(msg_loading)
        loading_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_item.setFlags(loading_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.table_packages.setItem(0, 0, loading_item)
        self.table_packages.setSpan(0, 0, 1, self.table_packages.columnCount()) 
        
        self.log_output.append("\n--- " + msg_loading + " ---")
        self.set_buttons_enabled(False)

        manager_type = self.parent().core.package_manager
        
        self.thread = QThread()
        self.worker = PipListWorker(self.venv_path, manager_type)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.handle_load_finished, Qt.ConnectionType.QueuedConnection)
        self.worker.error.connect(self.handle_load_error, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.cleanup_thread, Qt.ConnectionType.QueuedConnection)
        
        self.thread.start()

    @pyqtSlot(list)
    def handle_load_finished(self, packages):
        self.table_packages.setRowCount(0)
        self.table_packages.setRowCount(len(packages))
        
        for row, pkg in enumerate(packages):
            self.table_packages.setItem(row, 0, QTableWidgetItem(pkg['name']))
            self.table_packages.setItem(row, 1, QTableWidgetItem(pkg['version']))
            
            item_latest = QTableWidgetItem(pkg['latest'])
            
            if pkg['version'] != pkg['latest']:
                item_latest.setForeground(Qt.GlobalColor.red)
                tooltip = LanguageManager.get("tip_newer_version", "Dostupná novšia verzia!")
                item_latest.setToolTip(tooltip)
            else:
                item_latest.setForeground(Qt.GlobalColor.green)
            
            self.table_packages.setItem(row, 2, item_latest)
            self.table_packages.item(row, 0).setData(Qt.ItemDataRole.UserRole, pkg)

        msg_success = LanguageManager.get("msg_loaded_count", "Úspešne načítaných {0} balíčkov.").format(len(packages))
        self.log_output.append(msg_success)
        self.set_buttons_enabled(True)

    @pyqtSlot(str)
    def handle_load_error(self, error_message):
        self.table_packages.setRowCount(0)
        self.log_output.append(f"CHYBA: {error_message}")
        title = LanguageManager.get("title_error_loading", "Chyba pri načítavaní")
        QMessageBox.critical(self, title, error_message)
        self.set_buttons_enabled(True)

    def set_buttons_enabled(self, enabled: bool):
        self.btn_refresh.setEnabled(enabled)
        self.btn_update_all.setEnabled(enabled)
        self.btn_freeze.setEnabled(enabled)

    def on_package_selected(self):
        selected_items = self.table_packages.selectedItems()
        self.group_package_actions.setTitle("")

        if not selected_items:
            self.package_actions_widget.clear_data()
            return
            
        row = selected_items[0].row()
        pkg_data = self.table_packages.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        if pkg_data:
            self.package_actions_widget.set_package_data(pkg_data)

    def on_update_all(self):
        self.safe_stop_thread()
        
        msg_start = LanguageManager.get("msg_start_update_all", "\n--- Inicializujem hromadnú aktualizáciu ---")
        self.log_output.append(msg_start)
        self.set_buttons_enabled(False)
        self._pending_refresh = False

        manager_type = self.parent().core.package_manager

        self.thread = QThread()
        self.worker = PipWorkerAllUpdate(self.venv_path, manager_type)
        self.worker.moveToThread(self.thread)

        self.worker.output_line.connect(self.append_log, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.on_update_all_finished, Qt.ConnectionType.QueuedConnection)
        self.worker.error.connect(self.handle_update_error, Qt.ConnectionType.QueuedConnection)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.cleanup_thread, Qt.ConnectionType.QueuedConnection)

        self.thread.start()

    @pyqtSlot(str)
    def append_log(self, text):
        self.log_output.append(text)

    @pyqtSlot(str)
    def handle_update_error(self, err_msg):
        self.log_output.append(f"CHYBA: {err_msg}")

    @pyqtSlot(bool)
    def on_update_all_finished(self, success):
        if success:
            msg = LanguageManager.get("msg_update_finished_refreshing", "Aktualizácia dokončená. Pripravujem obnovu zoznamu...")
            self.log_output.append(msg)
            self._pending_refresh = True
        else:
            msg = LanguageManager.get("msg_update_finished_error", "Aktualizácia skončila s chybou.")
            self.log_output.append(msg)
            self.set_buttons_enabled(True)

    def on_freeze(self):
        self.safe_stop_thread() # Upraceme staré bežiace vlákna
        self.log_output.append("\n--- Spúšťam asynchrónny export (Freeze) ---")
        self.set_buttons_enabled(False)
        manager_type = self.parent().core.package_manager

        # Príprava asynchrónneho vlákna
        self.thread = QThread()
        self.worker = FreezeWorker(self.venv_path, self.project_root, manager_type)
        self.worker.moveToThread(self.thread)

        # Prepojenie signálov
        self.thread.started.connect(self.worker.run)
        self.worker.log_msg.connect(self.append_log, Qt.ConnectionType.QueuedConnection)
        self.worker.finished_signal.connect(self.on_freeze_finished, Qt.ConnectionType.QueuedConnection)
        
        # Bezpečné uvoľnenie prostriedkov po dokončení
        self.worker.finished_signal.connect(self.cleanup_thread)
        self.thread.start()

    @pyqtSlot(bool)
    def on_freeze_finished(self, success):
        """Vyvolá sa na hlavnom grafickom vlákne po dokončení zápisu do requirements.txt."""
        self.set_buttons_enabled(True)

    @pyqtSlot()
    def cleanup_thread(self):
        if self.thread:
            if self.thread.isRunning():
                self.thread.quit()
                self.thread.wait()
            self.thread.deleteLater()
            self.thread = None
        
        if self.worker:
            self.worker.deleteLater()
            self.worker = None
            
            # Ak sme upratovali po aktualizácii (Update), zoznam načítame znova
            if self._pending_refresh:
                self._pending_refresh = False
                self.refresh_list()
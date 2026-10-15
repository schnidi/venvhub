#----------------------------------------
# Súbor: windows/pip_e_window.py
#----------------------------------------

import os
from PyQt6.QtWidgets import (QDialog, QTableWidgetItem, QHeaderView,
                             QMessageBox, QFileDialog)
from PyQt6 import uic
from PyQt6.QtCore import Qt, QThread, pyqtSlot

from core._path import Paths
from core.logic.language_manager import LanguageManager
from windows.custom_title_bar import CustomTitleBar

from core.logic.pip_e import PipEListWorker, PipEInstallWorker, PipEUninstallWorker


class PipEWindow(QDialog):
    def __init__(self, parent, venv_path):
        super().__init__(parent)
        self.core = parent.core
        self.venv_path = venv_path

        self.active_thread = None
        self.active_worker = None
        self._pending_refresh = False

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("PipEWindow")

        uic.loadUi(Paths.get_ui_file_path("pip_e_window.ui"), self)

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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)

        self.table_packages.horizontalHeaderItem(0).setText(LanguageManager.get("col_pipe_name", "Názov balíčka"))
        self.table_packages.horizontalHeaderItem(1).setText(LanguageManager.get("col_pipe_version", "Verzia"))
        self.table_packages.horizontalHeaderItem(2).setText(LanguageManager.get("col_pipe_path", "Lokálna cesta"))

        if hasattr(self, 'title_bar'):
            self.title_bar.lbl_title.setText(LanguageManager.get("title_pip_e_manager", "Editovateľné balíčky (pip -e)"))

        venv_name = os.path.basename(self.venv_path)
        self.lbl_header.setText(LanguageManager.get("pip_e_header", "Inštalované cez pip -e pre: {name}").format(name=venv_name))

    def connect_signals(self):
        self.btn_refresh.clicked.connect(self.refresh_list)
        self.btn_add_package.clicked.connect(self.add_new_package)
        self.btn_remove_package.clicked.connect(self.remove_selected_package)

    @pyqtSlot(str)
    def log(self, message):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_ui_locked(self, locked: bool):
        self.btn_refresh.setEnabled(not locked)
        self.btn_add_package.setEnabled(not locked)
        self.btn_remove_package.setEnabled(not locked)
        self.table_packages.setEnabled(not locked)

    # =========================================================================
    # --- SPRÁVA VLÁKNA (bez wait() v GUI vlákne) ---
    # =========================================================================
    def _is_busy(self) -> bool:
        return self.active_thread is not None

    def _start_worker(self, worker, on_finished):
        """Spustí worker v novom vlákne. Vlákno sa po dokončení samo uprace."""
        if self._is_busy():
            return

        self._set_ui_locked(True)

        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.log_msg.connect(self.log)
        worker.error.connect(self._handle_error)
        worker.finished.connect(on_finished)

        # Upratovanie: worker skončí -> thread.quit -> deleteLater oboch
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished)

        self.active_thread = thread
        self.active_worker = worker
        thread.start()

    @pyqtSlot()
    def _on_thread_finished(self):
        """Vlákno je naozaj dokončené – až teraz sa dá spustiť ďalšie."""
        self.active_thread = None
        self.active_worker = None
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh_list()

    # =========================================================================
    # --- AKCIA 1: NAČÍTANIE ZOZNAMU ---
    # =========================================================================
    def refresh_list(self):
        if self._is_busy():
            self._pending_refresh = True
            return

        self.table_packages.setRowCount(0)
        manager_type = getattr(self.core, 'package_manager', 'pip')
        self._start_worker(PipEListWorker(self.venv_path, manager_type), self._on_list_loaded)

    @pyqtSlot(list)
    def _on_list_loaded(self, packages):
        self.table_packages.setRowCount(0)

        for pkg in packages:
            row = self.table_packages.rowCount()
            self.table_packages.insertRow(row)

            name = pkg.get("name", "Neznámy")
            version = pkg.get("version", "")
            local_path = pkg.get("editable_project_location", "")

            item_ver = QTableWidgetItem(version)
            item_ver.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table_packages.setItem(row, 0, QTableWidgetItem(name))
            self.table_packages.setItem(row, 1, item_ver)
            self.table_packages.setItem(row, 2, QTableWidgetItem(local_path))

        self._set_ui_locked(False)

    # =========================================================================
    # --- AKCIA 2: INŠTALÁCIA ---
    # =========================================================================
    def add_new_package(self):
        if self._is_busy():
            return

        initial_dir = getattr(self.core, 'pip_e_packages_root', os.path.expanduser("~"))
        if not os.path.exists(initial_dir):
            initial_dir = os.path.expanduser("~")

        dir_path = QFileDialog.getExistingDirectory(
            self,
            LanguageManager.get("title_select_pkg_dir", "Vybrať priečinok s balíčkom (setup.py / pyproject.toml)"),
            initial_dir
        )
        if not dir_path:
            return

        manager_type = getattr(self.core, 'package_manager', 'pip')
        self._start_worker(
            PipEInstallWorker(self.venv_path, dir_path, manager_type),
            self._on_action_finished
        )

    # =========================================================================
    # --- AKCIA 3: ODINŠTALÁCIA ---
    # =========================================================================
    def remove_selected_package(self):
        if self._is_busy():
            return

        selected_row = self.table_packages.currentRow()
        if selected_row == -1:
            QMessageBox.warning(
                self,
                LanguageManager.get("title_warning", "Upozornenie"),
                LanguageManager.get("pip_e_select_to_remove", "Najprv kliknite na balíček v tabuľke, ktorý chcete odinštalovať.")
            )
            return

        pkg_name = self.table_packages.item(selected_row, 0).text()

        confirm = QMessageBox.question(
            self,
            LanguageManager.get("title_confirm", "Potvrdenie"),
            LanguageManager.get("pip_e_uninstall_confirm", "Naozaj chcete odinštalovať editovateľný balíček '{0}' z tohto venv?").format(pkg_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.No:
            return

        manager_type = getattr(self.core, 'package_manager', 'pip')
        self._start_worker(
            PipEUninstallWorker(self.venv_path, pkg_name, manager_type),
            self._on_action_finished
        )

    # =========================================================================
    # --- CHYBY A DOKONČENIE ---
    # =========================================================================
    @pyqtSlot(str)
    def _handle_error(self, err_msg):
        self.log(err_msg)
        QMessageBox.critical(self, LanguageManager.get("title_error", "Chyba"), err_msg)

    @pyqtSlot(bool)
    def _on_action_finished(self, success):
        if not success:
            self._set_ui_locked(False)
            return
        # Zoznam sa obnoví hneď po tom, ako sa vlákno skutočne ukončí
        self._pending_refresh = True

    def done(self, result):
        """Pri zatváraní okna počkaj na bežiace vlákno, aby nepadol Qt."""
        if self.active_thread is not None and self.active_thread.isRunning():
            self.active_thread.quit()
            self.active_thread.wait(5000)
        super().done(result)

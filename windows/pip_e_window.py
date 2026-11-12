#----------------------------------------
# Súbor: windows/pip_e_window.py
# Moderné okno pre správu pip -e balíčkov napojené na CoreBridge a PipManager
#----------------------------------------

import os
from PyQt6.QtWidgets import QDialog, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox
from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSlot

from core._path import Paths
from core.core_bridge import CoreBridge
from core.core_states import EditableOperationStatus
from core.logic.pip_manager import PipManager

from windows.custom_title_bar import CustomTitleBar
from windows.custom_message_box import CustomMessageBox


class PipEWindow(QDialog):
    def __init__(self, parent, venv_path):
        super().__init__(parent)
        self.core = parent.core
        self.venv_path = venv_path

        # 1. Frameless nastavenia okna
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("PipEWindow")

        uic.loadUi(Paths.get_ui_file_path("pip_e_window.ui"), self)

        # 2. Vloženie CustomTitleBar
        self.title_bar = CustomTitleBar(self)
        self.main_layout.insertWidget(0, self.title_bar)
        self.main_layout.setContentsMargins(1, 1, 1, 1)

        self.setup_ui()
        self.connect_signals()
        self.retranslate_ui()

        # 3. Načítanie zoznamu balíčkov pri štarte
        self.refresh_list()

    def setup_ui(self):
        header = self.table_packages.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def retranslate_ui(self):
        CoreBridge.translate_window(self)

        self.table_packages.horizontalHeaderItem(0).setText(CoreBridge.translate("col_pipe_name", "Názov balíčka"))
        self.table_packages.horizontalHeaderItem(1).setText(CoreBridge.translate("col_pipe_version", "Verzia"))
        self.table_packages.horizontalHeaderItem(2).setText(CoreBridge.translate("col_pipe_path", "Lokálna cesta"))

        if hasattr(self, 'title_bar'):
            self.title_bar.lbl_title.setText(CoreBridge.translate("title_pip_e_manager", "Editovateľné balíčky (pip -e)"))

        venv_name = os.path.basename(self.venv_path)
        fmt = CoreBridge.translate("pip_e_header", "Inštalované cez pip -e pre: {name}")
        self.lbl_header.setText(fmt.format(name=venv_name))

    def connect_signals(self):
        self.btn_refresh.clicked.connect(self.refresh_list)
        self.btn_add_package.clicked.connect(self.add_new_package)
        self.btn_remove_package.clicked.connect(self.remove_selected_package)

    def log(self, message: str):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_ui_locked(self, locked: bool):
        self.btn_refresh.setEnabled(not locked)
        self.btn_add_package.setEnabled(not locked)
        self.btn_remove_package.setEnabled(not locked)
        self.table_packages.setEnabled(not locked)

    # =========================================================================
    # 1. NAČÍTANIE ZOZNAMU CEZ FASÁDU
    # =========================================================================
    def refresh_list(self):
        self._set_ui_locked(True)
        self.table_packages.setRowCount(0)
        
        manager_type = getattr(self.core, 'package_manager', 'pip')
        PipManager.list_editable_packages(
            venv_path=self.venv_path,
            manager_type=manager_type,
            on_loaded=self._on_list_loaded,
            log_widget=self.log_output
        )

    @pyqtSlot(list)
    def _on_list_loaded(self, packages: list):
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
    # 2. INŠTALÁCIA Z PRIEČINKA CEZ FASÁDU
    # =========================================================================
    def add_new_package(self):
        initial_dir = getattr(self.core, 'pip_e_packages_root', os.path.expanduser("~"))
        if not os.path.exists(initial_dir):
            initial_dir = os.path.expanduser("~")

        title = CoreBridge.translate("title_select_pkg_dir", "Vybrať priečinok s balíčkom (setup.py / pyproject.toml)")
        dir_path = QFileDialog.getExistingDirectory(self, title, initial_dir)
        if not dir_path:
            return

        self._set_ui_locked(True)
        manager_type = getattr(self.core, 'package_manager', 'pip')

        PipManager.install_editable(
            core=self.core,
            venv_path=self.venv_path,
            target_path=dir_path,
            log_widget=self.log_output,
            manager_type=manager_type
        )

        if PipManager._current_worker:
            PipManager._current_worker.signals.finished_with_status.connect(self._on_operation_finished)

    # =========================================================================
    # 3. ODINŠTALÁCIA S APT OCHRANOU CEZ FASÁDU
    # =========================================================================
    def remove_selected_package(self):
        selected_row = self.table_packages.currentRow()
        if selected_row == -1:
            CustomMessageBox.warning(
                self,
                CoreBridge.translate("title_warning", "Upozornenie"),
                CoreBridge.translate("pip_e_select_to_remove", "Najprv kliknite na balíček v tabuľke, ktorý chcete odinštalovať.")
            )
            return

        pkg_name = self.table_packages.item(selected_row, 0).text()

        title = CoreBridge.translate("title_confirm", "Potvrdenie")
        msg = CoreBridge.translate("pip_e_uninstall_confirm", "Naozaj chcete odinštalovať editovateľný balíček '{0}' z tohto venv?").format(pkg_name)
        
        reply = CustomMessageBox.question(self, title, msg)
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set_ui_locked(True)
        manager_type = getattr(self.core, 'package_manager', 'pip')

        PipManager.uninstall_editable(
            core=self.core,
            venv_path=self.venv_path,
            package_name=pkg_name,
            log_widget=self.log_output,
            manager_type=manager_type
        )

        if PipManager._current_worker:
            PipManager._current_worker.signals.finished_with_status.connect(self._on_operation_finished)

    # =========================================================================
    # 4. VYHODNOTENIE STAVOVÉHO ENUMU (EditableOperationStatus)
    # =========================================================================
    @pyqtSlot(EditableOperationStatus)
    def _on_operation_finished(self, status: EditableOperationStatus):
        self._set_ui_locked(False)

        if status in (EditableOperationStatus.SUCCESS, EditableOperationStatus.SUCCESS_WITH_CONFLICTS):
            self.refresh_list()
            if status == EditableOperationStatus.SUCCESS_WITH_CONFLICTS:
                CustomMessageBox.warning(
                    self,
                    CoreBridge.translate("title_warning", "Upozornenie"),
                    CoreBridge.translate("msg_installed_with_conflicts", "Balíček bol nainštalovaný, ale boli zistené konflikty v závislostiach.\nSkontrolujte log.")
                )
        elif status == EditableOperationStatus.INVALID_PROJECT:
            CustomMessageBox.warning(
                self,
                CoreBridge.translate("title_warning", "Neplatný projekt"),
                CoreBridge.translate("pipe_err_invalid_folder", "Vybraný priečinok neobsahuje súbor 'setup.py' ani 'pyproject.toml'.")
            )
        elif status == EditableOperationStatus.BLOCKED:
            CustomMessageBox.warning(
                self,
                CoreBridge.translate("title_warning", "Zablokované"),
                CoreBridge.translate("msg_op_blocked", "Operácia bola zablokovaná systémovou ochranou (APT Guard).\nSkontrolujte log pre viac informácií.")
            )
        elif status == EditableOperationStatus.ERROR:
            CustomMessageBox.critical(
                self,
                CoreBridge.translate("title_error", "Chyba"),
                CoreBridge.translate("msg_check_log", "Operácia zlyhala. Skontrolujte log pre viac detailov.")
            )
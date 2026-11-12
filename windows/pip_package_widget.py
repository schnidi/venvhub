#----------------------------------------
# Súbor: windows/pip_package_widget.py
#----------------------------------------

import os
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6 import uic
from PyQt6.QtCore import Qt

from core._path import Paths
from core.logic.language_manager import LanguageManager
from core.core_states import PackageOperationStatus
from core.logic.pip_manager import PipManager

# --- BEZRÁMOVÉ OKNO ---
from windows.custom_message_box import CustomMessageBox

class PipPackageWidget(QWidget):
    def __init__(self, parent_window, venv_path):
        super().__init__()
        self.parent_window = parent_window
        self.venv_path = venv_path
        self.package_data = None
        
        uic.loadUi(Paths.get_ui_file_path("pip_package_actions_widget.ui"), self)
        
        self.connect_signals()
        self.clear_data()

    def connect_signals(self):
        self.btn_update.clicked.connect(self.on_update)
        self.btn_uninstall.clicked.connect(self.on_uninstall)
        self.btn_install_specific.clicked.connect(self.on_install_specific)

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)
        if self.package_data:
            self.set_package_data(self.package_data)
        else:
            self.clear_data()

    def clear_data(self):
        self.package_data = None
        self.group_actions.setTitle(LanguageManager.get("group_package_actions_default", "Vyberte balíček v tabuľke"))
        self.lbl_installed_version.setText(LanguageManager.get("lbl_installed_fmt", "Nainštalovaná verzia: {0}").format("-"))
        self.lbl_latest_version.setText(LanguageManager.get("lbl_latest_fmt", "Najnovšia verzia: {0}").format("-"))
        self.btn_update.setText(LanguageManager.get("btn_update_fmt", "⬆️ Aktualizovať na {0}").format(LanguageManager.get("word_latest", "najnovšiu")))
        self.edit_specific_version.clear()
        self.set_buttons_enabled(False)

    def set_package_data(self, package_data):
        self.package_data = package_data
        if not self.package_data:
            self.clear_data()
            return
            
        pkg_name = self.package_data['name']
        current_ver = self.package_data['version']
        latest_ver = self.package_data['latest']

        self.group_actions.setTitle(LanguageManager.get("group_actions_fmt", "Akcie pre: {0}").format(pkg_name))
        self.lbl_installed_version.setText(LanguageManager.get("lbl_installed_fmt", "Nainštalovaná verzia: {0}").format(current_ver))
        self.lbl_latest_version.setText(LanguageManager.get("lbl_latest_fmt", "Najnovšia verzia: {0}").format(latest_ver))
        
        self.set_buttons_enabled(True)
        
        if current_ver == latest_ver:
            self.btn_update.setEnabled(False)
            self.btn_update.setText(LanguageManager.get("btn_update_uptodate", "✅ Verzia je aktuálna"))
        else:
            self.btn_update.setEnabled(True)
            self.btn_update.setText(LanguageManager.get("btn_update_fmt", "⬆️ Aktualizovať na {0}").format(latest_ver))

    def set_buttons_enabled(self, enabled):
        if enabled and not self.package_data: return
        self.btn_update.setEnabled(enabled)
        self.btn_uninstall.setEnabled(enabled)
        self.btn_install_specific.setEnabled(enabled)
        self.edit_specific_version.setEnabled(enabled)
        
        if enabled and self.package_data:
            if self.package_data['version'] == self.package_data['latest']:
                self.btn_update.setEnabled(False)

    def log(self, message):
        if hasattr(self.parent_window, "log_output"):
            self.parent_window.log_output.append(message)

    def _get_core(self):
        return self.parent_window.parent().core

    def _get_manager_type(self):
        return self._get_core().package_manager

    def _on_operation_finished(self, status: PackageOperationStatus):
        """Vyhodnocuje Enum, ktorý sa vrátil po dokončení inštalácie / odinštalácie."""
        self.set_buttons_enabled(True)
        
        if status in (PackageOperationStatus.SUCCESS, PackageOperationStatus.SUCCESS_WITH_CONFLICTS):
            self.parent_window.refresh_list()
            
        elif status == PackageOperationStatus.BLOCKED:
            title = LanguageManager.get("title_warning", "Upozornenie")
            # Presný dôvod zablokovania (napr. že to drží requirements) je už vypísaný v logu!
            msg = LanguageManager.get("msg_op_blocked", "Operácia bola zablokovaná systémovou ochranou.\nSkontrolujte log pre viac informácií.")
            CustomMessageBox.warning(self, title, msg)
            
        elif status == PackageOperationStatus.ERROR:
            title = LanguageManager.get("title_error", "Chyba")
            msg = LanguageManager.get("msg_check_log", "Operácia zlyhala. Skontrolujte log pre viac detailov.")
            CustomMessageBox.warning(self, title, msg)

    def on_update(self):
        if not self.package_data: return
        pkg_name = self.package_data['name']
        latest_ver = self.package_data['latest']
        
        # Keď inštalujeme špecifickú verziu, naša nová služba ju sama stiahne a preinštaluje
        package_spec = f"{pkg_name}=={latest_ver}"
        
        self.set_buttons_enabled(False)
        
        # --- ZMENA: Prepojenie signálu vložené priamo do volania (on_finished) ---
        PipManager.install_package(
            self.venv_path, 
            package_spec, 
            self.parent_window.log_output, 
            self._get_manager_type(), 
            core=self._get_core(),
            on_finished=self._on_operation_finished
        )

    def on_uninstall(self):
        if not self.package_data: return
        pkg_name = self.package_data['name']

        # Už žiadne dlhé kontroly requirements.txt! Pýtame sa priamo:
        title = LanguageManager.get("title_confirm", "Potvrdenie")
        msg = LanguageManager.get("msg_confirm_uninstall", "Naozaj chcete odinštalovať balíček '{0}'?").format(pkg_name)
        
        reply = CustomMessageBox.question(self, title, msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.set_buttons_enabled(False)
            
            # --- ZMENA: Prepojenie signálu vložené priamo do volania (on_finished) ---
            PipManager.uninstall_package(
                self.venv_path, 
                pkg_name, 
                self.parent_window.log_output, 
                self._get_manager_type(), 
                core=self._get_core(),
                on_finished=self._on_operation_finished
            )

    def on_install_specific(self):
        if not self.package_data: return
        pkg_name = self.package_data['name']
        version = self.edit_specific_version.text().strip()
        
        if not version:
            title = LanguageManager.get("title_error", "Chyba")
            msg = LanguageManager.get("msg_enter_version", "Zadajte verziu (napr. 1.2.3)")
            CustomMessageBox.warning(self, title, msg)
            return
            
        package_spec = f"{pkg_name}=={version}"
        
        self.set_buttons_enabled(False)
        self.edit_specific_version.clear()
        
        # --- ZMENA: Prepojenie signálu vložené priamo do volania (on_finished) ---
        PipManager.install_package(
            self.venv_path, 
            package_spec, 
            self.parent_window.log_output, 
            self._get_manager_type(), 
            core=self._get_core(),
            on_finished=self._on_operation_finished
        )
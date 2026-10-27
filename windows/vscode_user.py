#----------------------------------------
# Súbor: windows/vscode_user.py
#----------------------------------------

import os
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QWidget, QFileDialog, QMessageBox, QListWidgetItem
from PyQt6 import uic
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from core._path import Paths
from windows.custom_title_bar import CustomTitleBar

from core.logic.vscode_user.profile_manager import VSCodeProfileManager, ProfileDeleteWorker
from core.logic.language_manager import LanguageManager
from core.logic.vscode_user.system_sync import SystemSyncWorker
from windows.progress_dialog import ProgressDialog

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox


class VSCodeUserWindow(QDialog):
    # Signál: Informuje hlavné okno, že sa zmenili profily alebo aktívny používateľ
    profiles_changed = pyqtSignal()

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        
        # Zistenie aktívneho editora ('vscode' alebo 'cursor')
        self.ide_type = getattr(self.core, 'active_ide', 'vscode')

        self.sync_thread = None
        self.sync_worker = None
        self.delete_thread = None
        self.delete_worker = None
        self.progress_dialog = None 
        
        self.operation_running = False
        self.current_sync_user_id = ""
        self.current_sync_is_new = False
        self.current_delete_user_id = ""
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        uic.loadUi(Paths.get_ui_file_path("vscode_user.ui"), self)
        
        self.setObjectName("VSCodeUserWindow")
        self.retranslate_ui()
        
        inner_content = QWidget()
        inner_layout = QVBoxLayout(inner_content)
        inner_layout.setContentsMargins(15, 10, 15, 15)
        inner_layout.setSpacing(10)
        
        while self.main_layout.count() > 0:
            item = self.main_layout.takeAt(0)
            if item.widget():
                inner_layout.addWidget(item.widget())
            elif item.layout():
                inner_layout.addLayout(item.layout())
                
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)
        
        self.title_bar = CustomTitleBar(self)
        self.main_layout.addWidget(self.title_bar)
        self.main_layout.addWidget(inner_content)
        
        self.connect_signals()
        
        self.refresh_ui_from_config()
        self.refresh_profiles_list()

    def get_current_profiles_dir(self) -> str:
        """Vráti cestu k podpriečinku aktuálneho editora (root/vscode alebo root/cursor)."""
        root_path = getattr(self.core, 'vscode_users_root', '')
        if not root_path:
            return ""
        return VSCodeProfileManager.get_ide_profiles_dir(root_path, self.ide_type)

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)
        
        # 1. Dynamické premenné podľa zvoleného editora
        if self.ide_type == "cursor":
            ide_name = "Cursor"
            sys_user = r"%APPDATA%\Cursor\User"
            sys_ext = r"%USERPROFILE%\.cursor\extensions"
        else:
            ide_name = "VS Code"
            sys_user = r"%APPDATA%\Code\User"
            sys_ext = r"%USERPROFILE%\.vscode\extensions"

        # 2. Dynamické nastavenie titulku okna a lišty
        title_text = LanguageManager.get("vscode_user_win_title", "Správa {0} Používateľov").format(ide_name)
        self.setWindowTitle(title_text)
        if hasattr(self, 'title_bar') and self.title_bar:
            self.title_bar.lbl_title.setText(title_text)

        # 3. Dynamické prepísanie skupín a popisov v okne
        if hasattr(self, 'group_root'):
            self.group_root.setTitle(
                LanguageManager.get("group_root_fmt", "Konfigurácia prenosného prostredia {0}").format(ide_name)
            )
            
        if hasattr(self, 'lbl_root_info'):
            self.lbl_root_info.setText(
                LanguageManager.get(
                    "lbl_root_info_fmt",
                    "Definujte spoločný priečinok, kde budú uložené všetky používateľské profily (nastavenia a rozšírenia {0})."
                ).format(ide_name)
            )

        if hasattr(self, 'group_profiles_list'):
            self.group_profiles_list.setTitle(
                LanguageManager.get("group_profiles_list_fmt", "Používateľské profily {0}").format(ide_name)
            )

        # 4. Dynamické texty a nápovedy pre import
        if hasattr(self, 'chk_copy_from_system'):
            self.chk_copy_from_system.setText(
                LanguageManager.get("chk_copy_from_system_fmt", "Pri vytvorení kopírovať zo systému ({0})").format(ide_name)
            )
            self.chk_copy_from_system.setToolTip(
                LanguageManager.get(
                    "chk_copy_from_system_tip_fmt",
                    "Skopíruje nastavenia ({0}) a rozšírenia ({1}) do nového profilu."
                ).format(sys_user, sys_ext)
            )

        if hasattr(self, 'btn_vscode_user_import_system'):
            self.btn_vscode_user_import_system.setText(
                LanguageManager.get("btn_import_system_fmt", "📥 Importovať zo systému teraz ({0})").format(ide_name)
            )
            self.btn_vscode_user_import_system.setToolTip(
                LanguageManager.get(
                    "btn_import_system_tip_fmt",
                    "Prepíše vybraný profil aktuálnymi systémovými nastaveniami a rozšíreniami {0}."
                ).format(ide_name)
            )

    def closeEvent(self, event):
        if self.operation_running:
            CustomMessageBox.warning(
                self, 
                LanguageManager.get("title_warning", "Upozornenie"), 
                LanguageManager.get("msg_background_op_running", "Prebieha operácia na pozadí.\n\nProsím, počkajte na jej dokončenie alebo ju zrušte.")
            )
            event.ignore()
            return
        event.accept()

    def refresh_ui_from_config(self):
        saved_path = getattr(self.core, 'vscode_users_root', '')
        self.edit_vscode_users_root.blockSignals(True)
        self.edit_vscode_users_root.setText(saved_path)
        self.edit_vscode_users_root.blockSignals(False)

    def refresh_profiles_list(self):
        self.list_vscode_users.clear()
        
        profiles_dir = self.get_current_profiles_dir()
        if not profiles_dir or not os.path.exists(profiles_dir):
            self.log_message(LanguageManager.get("msg_profiles_root_not_set", "Koreňový priečinok profilov nie je nastavený alebo neexistuje."))
            return

        profiles = VSCodeProfileManager.get_profiles(profiles_dir)
        active_user_id = self.core.get_active_ide_user()

        for p in profiles:
            display_text = f"{p['display_name']} ({p['id']})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            
            if p["id"] == active_user_id:
                active_lbl = LanguageManager.get("lbl_active_prefix", "★ [AKTÍVNY]")
                item.setText(f"{active_lbl} {display_text}")
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                
            self.list_vscode_users.addItem(item)

    @pyqtSlot(str)
    def log_message(self, text):
        if hasattr(self, "log_output"):
            self.log_output.append(text)
        if self.progress_dialog and self.progress_dialog.isVisible():
            self.progress_dialog.add_log_message(text)

    def connect_signals(self):
        self.btn_browse_users_root.clicked.connect(self.on_browse_users_root)
        self.edit_vscode_users_root.textChanged.connect(self.on_path_manually_changed)
        self.btn_vscode_user_add.clicked.connect(self.on_add_user)
        self.btn_vscode_user_remove.clicked.connect(self.on_remove_user)
        self.btn_vscode_user_import_system.clicked.connect(self.on_import_system)
        self.btn_vscode_user_set_active.clicked.connect(self.on_set_active)
        self.btn_vscode_user_open_folder.clicked.connect(self.on_open_folder)
        self.list_vscode_users.itemSelectionChanged.connect(self.on_profile_selected)

    def on_browse_users_root(self):
        current_path = self.edit_vscode_users_root.text().strip()
        path = QFileDialog.getExistingDirectory(self, LanguageManager.get("dialog_select_profiles_root", "Vyberte priečinok pre profily VS Code"), current_path)
        if path:
            self.edit_vscode_users_root.setText(path)
            self.core.vscode_users_root = path
            self.core.save_config()
            self.log_message(LanguageManager.get("msg_profiles_root_set_to", "Koreňový priečinok profilov bol nastavený na:\n{0}").format(path))
            self.refresh_profiles_list()
            self.profiles_changed.emit()

    def on_path_manually_changed(self, text):
        self.core.vscode_users_root = text.strip()
        self.core.save_config()

    def on_profile_selected(self):
        selected_items = self.list_vscode_users.selectedItems()
        if not selected_items: return
        user_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        self.log_message(LanguageManager.get("msg_profile_selected", "Vybraný profil: {0}").format(user_id))
        
    def on_open_folder(self):
        selected_items = self.list_vscode_users.selectedItems()
        if not selected_items:
            CustomMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_select_profile_first", "Najprv vyberte profil zo zoznamu."))
            return
        user_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        profile_path = os.path.join(self.get_current_profiles_dir(), user_id)
        if os.path.exists(profile_path): os.startfile(profile_path)
        else: self.log_message(LanguageManager.get("msg_profile_dir_not_exists", "Priečinok profilu na disku neexistuje!"))

    def on_set_active(self):
        selected_items = self.list_vscode_users.selectedItems()
        if not selected_items:
            CustomMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_select_profile_first", "Najprv vyberte profil zo zoznamu."))
            return
        user_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Uloženie aktívneho profilu pre aktuálne zvolený editor
        self.core.set_active_ide_user(user_id)
        self.core.save_config()
        self.log_message(LanguageManager.get("msg_profile_set_active", "Profil '{0}' bol nastavený ako aktívny.").format(user_id))
        
        current_row = self.list_vscode_users.currentRow()
        self.refresh_profiles_list()
        if current_row >= 0 and current_row < self.list_vscode_users.count():
            self.list_vscode_users.setCurrentRow(current_row)
            
        self.profiles_changed.emit()

    def on_add_user(self):
        user_id = self.edit_user_id.text().strip()
        display_name = self.edit_display_name.text().strip()
        
        if not user_id:
            CustomMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_must_enter_user_id", "Musíte zadať ID Používateľa."))
            return
            
        profiles_dir = self.get_current_profiles_dir()
        result = VSCodeProfileManager.create_profile(profiles_dir, user_id, display_name)
        
        if result["success"]:
            self.log_message(LanguageManager.get("msg_profile_created_on_disk", "Profil '{0}' úspešne vytvorený na disku.").format(result['id']))
            self.edit_user_id.clear()
            self.edit_display_name.clear()
            
            if self.chk_copy_from_system.isChecked():
                self.start_system_import(result["path"], result["id"], is_new_profile=True)
            else:
                self.refresh_profiles_list()
                self.profiles_changed.emit()
        else:
            err_title = LanguageManager.get("title_error", "Chyba")
            self.log_message(f"{err_title}: {result['error']}")
            CustomMessageBox.critical(self, err_title, result['error'])

    def on_remove_user(self):
        selected_items = self.list_vscode_users.selectedItems()
        if not selected_items:
            CustomMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_select_profile_to_delete", "Najprv vyberte profil, ktorý chcete zmazať."))
            return
            
        user_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        reply = CustomMessageBox.question(
            self, LanguageManager.get("title_delete_profile", "Zmazať profil?"), 
            LanguageManager.get("msg_confirm_delete_profile", "Naozaj chcete natrvalo vymazať profil '{0}' a VŠETKY jeho nastavenia a rozšírenia z disku?").format(user_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            target_dir = os.path.join(self.get_current_profiles_dir(), user_id)
            self.start_deletion_process(target_dir, user_id)

    def start_deletion_process(self, target_dir, user_id):
        if self.operation_running:
            self.log_message(LanguageManager.get("msg_another_bg_op_running", "⚠️ Iná operácia na pozadí už prebieha. Počkajte, prosím."))
            return

        self.current_delete_user_id = user_id

        self.operation_running = True
        self.set_ui_locked(True)
        
        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.set_message(LanguageManager.get("msg_deleting_profile_progress", "Mažem profil: {0}\nToto môže trvať niekoľko minút...").format(user_id))
        self.progress_dialog.set_progress_mode(indeterminate=False) 
        
        self.delete_thread = QThread()
        self.delete_worker = ProfileDeleteWorker(target_dir)
        self.delete_worker.moveToThread(self.delete_thread)

        self.delete_thread.started.connect(self.delete_worker.run)
        self.delete_worker.log_msg.connect(self.log_message, Qt.ConnectionType.QueuedConnection)
        self.delete_worker.progress_percent.connect(self.progress_dialog.set_progress_value, Qt.ConnectionType.QueuedConnection)
        
        self.delete_worker.finished.connect(self.delete_thread.quit)
        self.delete_worker.finished.connect(self.delete_worker.deleteLater)
        self.delete_thread.finished.connect(self.delete_thread.deleteLater)
        
        self.delete_worker.finished.connect(self._on_delete_finished, Qt.ConnectionType.QueuedConnection)
        
        self.delete_thread.start()
        self.progress_dialog.show()

    @pyqtSlot(bool, str)
    def _on_delete_finished(self, success, error_msg):
        user_id = self.current_delete_user_id
        
        self.operation_running = False
        self.set_ui_locked(False)
        
        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None
            
        if success:
            self.log_message(LanguageManager.get("msg_profile_deleted_success", "Profil '{0}' bol úspešne a natrvalo zmazaný.").format(user_id))
            if self.core.get_active_ide_user() == user_id:
                self.core.set_active_ide_user("")
                self.core.save_config()
            self.refresh_profiles_list()
            self.profiles_changed.emit()
        else:
            err_title = LanguageManager.get("title_error", "Chyba")
            self.log_message(f"{err_title}: {error_msg}")
            CustomMessageBox.critical(self, err_title, error_msg)

    def on_import_system(self):
        selected_items = self.list_vscode_users.selectedItems()
        if not selected_items:
            CustomMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_select_profile_first", "Najprv vyberte profil zo zoznamu."))
            return
            
        user_id = selected_items[0].data(Qt.ItemDataRole.UserRole)
        profile_path = os.path.join(self.get_current_profiles_dir(), user_id)
        
        reply = CustomMessageBox.question(
            self, LanguageManager.get("title_warning", "Upozornenie"), 
            LanguageManager.get("msg_confirm_overwrite_profile", "Naozaj chcete prepísať tento profil ('{0}') aktuálnymi systémovými nastaveniami a rozšíreniami?\n\nPôvodné nastavenia profilu budú zmazané.").format(user_id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.start_system_import(profile_path, user_id, is_new_profile=False)

    def set_ui_locked(self, locked: bool):
        self.btn_vscode_user_import_system.setEnabled(not locked)
        self.btn_vscode_user_add.setEnabled(not locked)
        self.btn_vscode_user_remove.setEnabled(not locked)
        self.btn_vscode_user_set_active.setEnabled(not locked)
        self.btn_vscode_user_open_folder.setEnabled(not locked)
        self.list_vscode_users.setEnabled(not locked)
        self.edit_user_id.setEnabled(not locked)
        self.edit_display_name.setEnabled(not locked)
        self.chk_copy_from_system.setEnabled(not locked)

    def start_system_import(self, profile_path, user_id, is_new_profile=False):
        if self.operation_running:
            self.log_message(LanguageManager.get("msg_another_bg_op_running", "⚠️ Iná operácia na pozadí už prebieha. Počkajte, prosím."))
            return

        self.current_sync_user_id = user_id
        self.current_sync_is_new = is_new_profile

        ide_name = "Cursor" if self.ide_type == "cursor" else "VS Code"
        self.operation_running = True
        start_msg = LanguageManager.get(
            "msg_starting_system_import_fmt",
            "\n--- Štartujem import systémového profilu {0} ---"
        ).format(ide_name)
        self.log_message(start_msg)
        self.set_ui_locked(True)
        
        self.progress_dialog = ProgressDialog(self)
        prog_msg = LanguageManager.get(
            "msg_copying_ide_data",
            "Kopírujem systémové dáta {0}.\nToto môže trvať niekoľko minút..."
        ).format(ide_name)
        self.progress_dialog.set_message(prog_msg)
        
        self.progress_dialog.set_progress_mode(indeterminate=False) 
        self.progress_dialog.enable_cancel_button() 
        
        self.sync_thread = QThread()
        # Odovzdávame self.ide_type pre správny výber systémových zložiek
        self.sync_worker = SystemSyncWorker(profile_path, is_new_profile, self.ide_type)
        self.sync_worker.moveToThread(self.sync_thread)

        self.sync_thread.started.connect(self.sync_worker.run)
        self.sync_worker.log_msg.connect(self.log_message, Qt.ConnectionType.QueuedConnection)
        self.sync_worker.progress_percent.connect(self.progress_dialog.set_progress_value, Qt.ConnectionType.QueuedConnection)
        self.progress_dialog.cancelled.connect(self.sync_worker.cancel)
        
        self.sync_worker.finished.connect(self.sync_thread.quit)
        self.sync_worker.finished.connect(self.sync_worker.deleteLater)
        self.sync_thread.finished.connect(self.sync_thread.deleteLater)
        
        self.sync_worker.finished.connect(self._on_sync_finished, Qt.ConnectionType.QueuedConnection)
        
        self.sync_thread.start()
        self.progress_dialog.show()

    @pyqtSlot(bool, str)
    def _on_sync_finished(self, success, reason):
        self.operation_running = False
        self.set_ui_locked(False)
        
        if self.progress_dialog:
            self.progress_dialog.accept() 
            self.progress_dialog = None
            
        if success:
            self.log_message(LanguageManager.get("msg_import_finished_ok", "--- Import zo systému kompletne hotový ---"))
        elif reason == "INSUFFICIENT_SPACE":
            CustomMessageBox.critical(self, LanguageManager.get("title_insufficient_space", "Nedostatok miesta"), LanguageManager.get("msg_insufficient_space", "Na cieľovom disku nie je dostatok voľného miesta pre import rozšírení."))
        elif reason == "CANCELLED":
            self.log_message(LanguageManager.get("msg_import_cancelled", "--- Import zo systému bol zrušený používateľom a dáta boli prečistené ---"))
        else:
            self.log_message(LanguageManager.get("msg_import_failed", "--- Import zo systému zlyhal ---"))

        self.refresh_profiles_list()
        self.profiles_changed.emit()
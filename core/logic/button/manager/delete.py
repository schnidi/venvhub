#----------------------------------------
# Súbor: core/logic/button/manager/delete.py
# Logika a asynchrónny worker pre bezpečné mazanie virtuálnych prostredí.
# Plne prepojené na DialogBridge a LanguageBridge (0 priamych väzieb na windows/).
#----------------------------------------

import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core._path import Paths
from core.logic.vs_code_json import VSCodeIntegration
from core.logic.sluzby.copy_del import CopyDelService

# --- ČISTÉ MOSTY (0 VÄZIEB NA WINDOWS) ---
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.dialog_bridge import DialogBridge


class DeleteWorker(QThread):
    progress = pyqtSignal(int)
    log_msg = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)

    def __init__(self, venv_path):
        super().__init__()
        self.venv_path = venv_path

    def run(self):
        result = CopyDelService.safe_delete_with_progress(
            target_path=self.venv_path,
            log_func=lambda msg: self.log_msg.emit(msg),
            progress_func=lambda val: self.progress.emit(val)
        )
        self.finished_signal.emit(result)


class DeleteHandler:
    @staticmethod
    def run(core, venv_path, parent_window):
        name = os.path.basename(venv_path)
        
        title = LanguageBridge.translate("title_delete", "Zmazať?")
        msg = LanguageBridge.translate("msg_confirm_delete", "Naozaj chcete úplne vymazať venv:\n{0}?").format(name)
        
        # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
        confirm = DialogBridge.question(
            parent_window, 
            title, 
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            
            progress_title = LanguageBridge.translate("title_deleting", "Prebieha mazanie...")
            progress_msg = LanguageBridge.translate("msg_deleting_progress", "Mažem: {0}").format(name)
            
            # --- PROGRESS DIALOG CEZ DIALOG BRIDGE ---
            progress_dialog = DialogBridge.progress_dialog(parent_window)
            progress_dialog.setWindowTitle(progress_title)
            progress_dialog.set_message(progress_msg)
            progress_dialog.set_progress_mode(indeterminate=False) # Ukazuje presne 0-100%
            
            # Vytvoríme a spustíme vlákno pre zmazanie
            parent_window._delete_worker = DeleteWorker(venv_path)

            def on_finished(result):
                progress_dialog.accept() # Bezpečné zatvorenie okna
                
                if result.get("success"):
                    if core.active_venv_path == venv_path:
                        core.active_venv_path = "" 
                        project_path = Paths.get_project_path(core.projects_root, core.active_project)
                        VSCodeIntegration.remove_vscode_sync(project_path)
                    
                    core.save_config()
                    parent_window.refresh_table()
                    parent_window.config_changed.emit()
                else:
                    title_err = LanguageBridge.translate("title_error", "Chyba")
                    error_reason = result.get("error", "Neznáma chyba")
                    msg_err = LanguageBridge.translate("msg_delete_failed", "Nepodarilo sa zmazať: {0}").format(error_reason)
                    
                    # --- KRITICKÁ CHYBA CEZ DIALOG BRIDGE ---
                    DialogBridge.critical(parent_window, title_err, msg_err)

            # Prepojíme signály z vlákna s naším oknom (percentá aj text)
            parent_window._delete_worker.progress.connect(progress_dialog.set_progress_value)
            parent_window._delete_worker.log_msg.connect(progress_dialog.add_log_message)
            parent_window._delete_worker.finished_signal.connect(on_finished)
            
            # Štart!
            parent_window._delete_worker.start()
            progress_dialog.exec()
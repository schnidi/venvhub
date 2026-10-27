#----------------------------------------
# Súbor: core/logic/py_installer/buttons/agree_exe_button.py
#----------------------------------------

import subprocess
import os
from PyQt6.QtWidgets import QMessageBox, QApplication
from PyQt6.QtCore import Qt, QThread
from core.logic.language_manager import LanguageManager
from windows.build_log_dialog import BuildLogDialog
from core._path import Paths

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox

# --- BEZPEČNÝ IMPORT PRE UV.EXE ---
try:
    from core.logic.box.uv_exe_install import UVExeInstaller
    UV_INSTALLER_AVAILABLE = True
except ImportError:
    UV_INSTALLER_AVAILABLE = False


class AgreeExeButtonHandler:

    @staticmethod
    def show_custom_message(parent, title, text, icon, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No):
        """Pomocná metóda na vytvorenie bezrámového a štýlovateľného hlásenia cez CustomMessageBox."""
        dialog = CustomMessageBox(parent, title, text, icon, buttons)
        dialog.exec()
        return dialog.result

    @staticmethod
    def run(window):
        script_name = window.combo_script.currentText()
        if not script_name:
            title = LanguageManager.get("title_error", "Chyba")
            msg = LanguageManager.get("msg_no_script_selected", "Nie je vybraný žiadny spúšťací skript pre build.")
            AgreeExeButtonHandler.show_custom_message(
                window, title, msg, QMessageBox.Icon.Warning, QMessageBox.StandardButton.Ok
            )
            return

        venv_path = window.combo_venv.currentData()
        if not venv_path:
            AgreeExeButtonHandler.show_custom_message(
                window, 
                LanguageManager.get("title_error", "Chyba"), 
                LanguageManager.get("msg_no_venv_selected", "Nie je vybraný žiadny Venv."),
                QMessageBox.Icon.Warning,
                QMessageBox.StandardButton.Ok
            )
            return
            
        python_exe = Paths.get_venv_python_exe_path(venv_path)

        if not AgreeExeButtonHandler.check_pyinstaller_installed(python_exe):
            msg = LanguageManager.get("msg_pyinstaller_missing", "V prostredí '{0}' chýba balíček PyInstaller.\n\nChcete ho teraz nainštalovať?").format(os.path.basename(venv_path))
            
            reply = AgreeExeButtonHandler.show_custom_message(
                window, 
                LanguageManager.get("title_pyinstaller_missing", "Chýba PyInstaller"), 
                msg, 
                QMessageBox.Icon.Question
            )
            if reply == QMessageBox.StandardButton.Yes:
                if not AgreeExeButtonHandler.install_pyinstaller(window, venv_path):
                    return 
            else:
                return 

        # === BEZPEČNÁ KONTROLA PRE PRIBALENIE UV.EXE ===
        if UV_INSTALLER_AVAILABLE and hasattr(window, 'chk_pack_uv') and window.chk_pack_uv.isChecked():
            if not UVExeInstaller.is_uv_in_venv(venv_path):
                msg_uv = LanguageManager.get("msg_uv_missing", "Nástroj 'uv' nie je v tomto prostredí, ale vyžiadali ste jeho pribalenie do .exe.\n\nChcete ho teraz stiahnuť a nainštalovať? (Vyžaduje internet)")
                
                reply_uv = AgreeExeButtonHandler.show_custom_message(
                    window, 
                    LanguageManager.get("title_uv_missing_no_uv", "Chýba UV"), 
                    msg_uv, 
                    QMessageBox.Icon.Question
                )
                
                if reply_uv == QMessageBox.StandardButton.Yes:
                    success = AgreeExeButtonHandler.install_uv_to_venv_async(window, venv_path)
                    
                    if not success:
                        AgreeExeButtonHandler.show_custom_message(
                            window,
                            LanguageManager.get("title_network_install_error", "Chyba siete / Inštalácie"),
                            LanguageManager.get("msg_download_uv_failed_simple", "Nepodarilo sa stiahnuť UV do Venvu. Skontrolujte pripojenie k internetu a výstupný log."),
                            QMessageBox.Icon.Critical,
                            QMessageBox.StandardButton.Ok
                        )
                        return

        if hasattr(window, 'get_final_parsed_command'):
            cmd_list = window.get_final_parsed_command()
        else:
            return

        if not cmd_list:
            AgreeExeButtonHandler.show_custom_message(
                window,
                LanguageManager.get("title_error", "Chyba"),
                LanguageManager.get("msg_cmd_gen_failed", "Nepodarilo sa vygenerovať príkaz."),
                QMessageBox.Icon.Critical,
                QMessageBox.StandardButton.Ok
            )
            return

        project_name = window.combo_project.currentText()
        project_path = Paths.get_project_path(window.core.projects_root, project_name)

        log_dialog = BuildLogDialog(window, cmd_list, project_path)
        log_dialog.exec()

    @staticmethod
    def check_pyinstaller_installed(python_exe):
        try:
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            result = subprocess.run(
                [python_exe, "-m", "pip", "show", "pyinstaller"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def install_pyinstaller(window, venv_path):
        """Asynchrónna inštalácia PyInstalleru s plnou vizuálnou odozvou cez ProgressDialog."""
        from windows.progress_dialog import ProgressDialog
        from core.logic.button.pip.pip_command_worker import PipCommandWorker

        manager_type = getattr(window.core, 'package_manager', 'pip')
        python_exe = Paths.get_venv_python_exe_path(venv_path)
        
        from core.logic.commands.command_factory import PackageManagerFactory
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("install", package_name="pyinstaller")

        progress = ProgressDialog(window)
        progress.setWindowTitle(LanguageManager.get("title_installing_pyinstaller", "Inštalácia PyInstaller"))
        progress.set_message(LanguageManager.get("msg_installing_pyinstaller", "Sťahujem a inštalujem balíček PyInstaller do prostredia..."))
        progress.set_progress_mode(indeterminate=True)

        thread = QThread()
        worker = PipCommandWorker(venv_path, cmd)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.output_line.connect(progress.add_log_message)
        
        worker.finished.connect(progress.accept)
        
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        progress.exec()

        success = AgreeExeButtonHandler.check_pyinstaller_installed(python_exe)
        
        if not success:
            AgreeExeButtonHandler.show_custom_message(
                window,
                LanguageManager.get("title_install_error", "Chyba inštalácie"),
                LanguageManager.get("msg_install_pyinstaller_failed_simple", "Inštalácia balíčka PyInstaller zlyhala. Skontrolujte pripojenie k internetu a výstupný log."),
                QMessageBox.Icon.Critical,
                QMessageBox.StandardButton.Ok
            )
        return success

    @staticmethod
    def install_uv_to_venv_async(window, venv_path):
        """Asynchrónna inštalácia UV inštalátora s plnou odozvou cez ProgressDialog."""
        from windows.progress_dialog import ProgressDialog
        from core.logic.button.pip.pip_command_worker import PipCommandWorker

        manager_type = getattr(window.core, 'package_manager', 'pip')

        from core.logic.commands.command_factory import PackageManagerFactory
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("install", package_name="uv")

        progress = ProgressDialog(window)
        progress.setWindowTitle(LanguageManager.get("title_installing_uv", "Inštalácia UV"))
        progress.set_message(LanguageManager.get("msg_installing_uv", "Sťahujem a inštalujem inštalátor UV (Astral) do prostredia..."))
        progress.set_progress_mode(indeterminate=True)

        thread = QThread()
        worker = PipCommandWorker(venv_path, cmd)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.output_line.connect(progress.add_log_message)
        
        worker.finished.connect(progress.accept)
        
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()
        progress.exec()

        success = UVExeInstaller.is_uv_in_venv(venv_path)
        return success
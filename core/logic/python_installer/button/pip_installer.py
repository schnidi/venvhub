#-------------------------------------------------------------------------------
# Súbor: core/logic/python_installer/button/pip_installer.py
# Logika a asynchrónny worker pre opravu a inštaláciu PIPu do Embed Pythonu.
# Aktualizuje stav prostredia v mostíku CoreBridge na Enum PythonPipStatus.OK.
#-------------------------------------------------------------------------------

"""
Tento modul zabezpečuje:
- Stiahnutie oficiálneho inštalačného bootstrap skriptu get-pip.py.
- Spustenie bootstrap inštalácie PIPu (v prípade potreby s asistenciou UAC).
- Odkomentovanie a aktiváciu direktívy 'import site' v ._pth súbore.
- Do-inštalovanie balíčka 'virtualenv' pre sebestačnosť prostredia.
- Aktualizáciu stavu interpreteru v pamäti CoreBridge na PythonPipStatus.OK.
"""

import os
import subprocess
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core._path import Paths
from core.core_bridge import CoreBridge
from core.core_states import PythonPipStatus
from core.logic.sluzby.downloader import Downloader
from core.logic.sluzby.python_runtime_inspector import PythonRuntimeInspector
from core.logic.sluzby.win_admin import WinAdmin


class PipInstallWorker(QObject):
    """
    Pracovník vykonávajúci stiahnutie a inštaláciu nástroja PIP do daného runtimu.
    Beží na pozadí a komunikuje cez Qt signály.
    """
    progress_log = pyqtSignal(str)
    finished = pyqtSignal(dict)
    
    def __init__(self, python_exe_path: str):
        """
        Inicializuje opravného workera.

        Args:
            python_exe_path (str): Absolútna cesta k python.exe, ktorý sa má opraviť.
        """
        super().__init__()
        self.python_exe_path = os.path.normpath(python_exe_path)
        self.get_pip_url = "https://bootstrap.pypa.io/get-pip.py"

    def run(self):
        """Vykoná stiahnutie get-pip.py, inštaláciu a aktiváciu site-packages."""
        if not os.path.exists(self.python_exe_path):
            error_msg = CoreBridge.translate(
                "err_py_exe_not_found", "Kritická chyba: python.exe sa nenašiel: {0}"
            ).format(self.python_exe_path)
            self.finished.emit({'success': False, 'error': error_msg})
            return

        msg_download = CoreBridge.translate(
            "msg_downloading_get_pip", "Sťahujem inštalačný skript get-pip.py..."
        )
        self.progress_log.emit(msg_download)
        temp_dir = Paths.get_python_downloads_dir()
        script_path = os.path.join(temp_dir, "get-pip.py")
        
        download_result = Downloader.download_file(self.get_pip_url, script_path)
        if not download_result['success']:
            err_msg = CoreBridge.translate(
                "msg_download_err", "Chyba pri sťahovaní: {0}"
            ).format(download_result['error'])
            self.finished.emit({'success': False, 'error': err_msg})
            return
            
        runtime_path = os.path.dirname(self.python_exe_path)
        
        # === A. REŽIM S UAC (Ak je Python v Program Files alebo chránenom priečinku) ===
        if WinAdmin.needs_admin_for_path(self.python_exe_path):
            self.progress_log.emit(
                CoreBridge.translate("msg_uac_needed", "Vyžadujú sa práva Administrátora. Prosím, potvrďte systémové UAC okno...")
            )
            marker_file = os.path.join(temp_dir, "pip_done.marker")
            
            pth_fix_code = "import os, glob; [open(p, 'w', encoding='utf-8').write(open(p, 'r', encoding='utf-8').read().replace('#import site', 'import site')) for p in glob.glob('*._pth')]"
            
            cmd_string = (
                f'cd /d "{runtime_path}"\n'
                f'echo [STATUS] INSTALLING_PIP > "{marker_file}"\n'
                f'"{self.python_exe_path}" "{script_path}"\n'
                f'if %errorlevel% neq 0 exit /b %errorlevel%\n'
                f'echo [STATUS] FIXING_PTH > "{marker_file}"\n'
                f'"{self.python_exe_path}" -c "{pth_fix_code}"\n'
                f'if %errorlevel% neq 0 exit /b %errorlevel%\n'
                f'echo [STATUS] INSTALLING_VENV > "{marker_file}"\n'
                f'"{self.python_exe_path}" -m pip install virtualenv\n'
            )
            
            def on_state_changed(state_str):
                if state_str == "[STATUS] UAC_APPROVED":
                    self.progress_log.emit(CoreBridge.translate("msg_pip_uac_approved", "✅ UAC schválené. Inštalátor prevzal kontrolu..."))
                elif state_str == "[STATUS] INSTALLING_PIP":
                    self.progress_log.emit(CoreBridge.translate("msg_pip_installing_base", "Inštalujem základný balíček PIP..."))
                elif state_str == "[STATUS] FIXING_PTH":
                    self.progress_log.emit(CoreBridge.translate("msg_pip_fixing_pth", "Aktivujem prístup k balíčkom (site-packages)..."))
                elif state_str == "[STATUS] INSTALLING_VENV":
                    self.progress_log.emit(CoreBridge.translate("msg_pip_installing_venv_admin", "Inštalujem modul 'virtualenv'..."))
                elif state_str == "[STATUS] DONE":
                    self.progress_log.emit(CoreBridge.translate("msg_pip_done", "✅ Oprava administrátorom úspešne dokončená."))
                elif state_str == "[STATUS] ERROR":
                    self.progress_log.emit(CoreBridge.translate("msg_pip_error_admin", "❌ Proces zlyhal počas vykonávania administrátorských opráv."))

            success = WinAdmin.run_cmd_with_uac_and_wait(cmd_string, marker_file, state_callback=on_state_changed)
            
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass

            if not success:
                err_uac = CoreBridge.translate("msg_pip_install_fail_uac", "Inštalácia zlyhala (UAC zamietnuté alebo proces havaroval).")
                self.finished.emit({'success': False, 'error': err_uac})
                return
                
            self.progress_log.emit(CoreBridge.translate("msg_pip_activated_admin", "PIP, site-packages a virtualenv boli plne aktivované."))
            self.progress_log.emit(CoreBridge.translate("msg_pip_repair_complete", "Oprava hotová. Runtime je plne funkčný."))
            
            # Aktualizácia stavového Enumu v pamäti CoreBridge
            CoreBridge.update_python_pip_status(self.python_exe_path, PythonPipStatus.OK)
            self.finished.emit({'success': True})
            return

        # === B. ŠTANDARDNÝ REŽIM (Bez UAC) ===
        try:
            self.progress_log.emit(CoreBridge.translate("msg_pip_script_downloaded", "Skript stiahnutý. Začína sa inštalácia PIPu..."))
            pip_command = [self.python_exe_path, script_path]
            subprocess.run(
                pip_command, 
                check=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.progress_log.emit(CoreBridge.translate("msg_pip_installed_ok", "PIP bol úspešne nainštalovaný."))

            self.progress_log.emit(CoreBridge.translate("msg_pip_activating_site", "Aktivujem prístup k balíčkom (site-packages)..."))
            if not PythonRuntimeInspector.ensure_site_packages_enabled(runtime_path):
                self.progress_log.emit(CoreBridge.translate("msg_pip_site_fail_warn", "UPOZORNENIE: Nepodarilo sa automaticky aktivovať site-packages."))
            else:
                self.progress_log.emit(CoreBridge.translate("msg_pip_site_activated", "Prístup k balíčkom bol aktivovaný."))

            self.progress_log.emit(CoreBridge.translate("msg_pip_installing_venv", "Inštalujem balíček 'virtualenv'..."))
            virtualenv_command = [self.python_exe_path, "-m", "pip", "install", "virtualenv"]
            subprocess.run(
                virtualenv_command,
                check=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.progress_log.emit(CoreBridge.translate("msg_pip_venv_installed", "'virtualenv' úspešne nainštalovaný."))
            self.progress_log.emit(CoreBridge.translate("msg_pip_repair_complete", "Oprava hotová. Runtime je plne funkčný."))
            
            # Aktualizácia stavového Enumu v pamäti CoreBridge
            CoreBridge.update_python_pip_status(self.python_exe_path, PythonPipStatus.OK)
            self.finished.emit({'success': True})

        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode('utf-8', errors='ignore') if e.stderr else CoreBridge.translate("err_unknown", "Neznáma chyba.")
            err_formatted = CoreBridge.translate("msg_pip_install_fail", "Inštalácia zlyhala: {0}").format(error_output)
            self.finished.emit({'success': False, 'error': err_formatted})
        
        finally:
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass


class PipInstaller(QObject):
    """
    Riadiaci manažér pre proces opravy PIPu.
    Zabezpečuje spustenie vo vlákne a prepínanie stavov tlačidla.
    """
    installation_finished = pyqtSignal(dict)

    def __init__(self, log_widget, repair_button):
        """
        Inicializuje opravára PIPu.

        Args:
            log_widget: Textové pole pre výpis logov (QTextEdit).
            repair_button: Tlačidlo pre spustenie opravy (QPushButton).
        """
        super().__init__()
        self.log_widget = log_widget
        self.repair_button = repair_button
        self.thread = None
        self.worker = None

    def install(self, python_exe_path: str):
        """Spustí opravu zadaného python.exe vo vyhradenom vlákne."""
        if self.thread and self.thread.isRunning():
            self.log_widget.append(CoreBridge.translate("msg_pip_repair_in_progress", "! Iná oprava už prebieha."))
            return

        self.repair_button.setEnabled(False)
        self.repair_button.setText(CoreBridge.translate("txt_repairing", "⏳ OPRAVUJEM..."))

        self.thread = QThread()
        self.worker = PipInstallWorker(python_exe_path)
        self.worker.moveToThread(self.thread)

        self.worker.progress_log.connect(self.log_widget.append)
        self.worker.finished.connect(self.on_install_finished)
        self.thread.started.connect(self.worker.run)
        
        self.thread.start()

    def on_install_finished(self, result: dict):
        """Vyvolá sa po dokončení opravy a odomkne tlačidlo v UI."""
        if not result['success']:
            err_title = CoreBridge.translate("title_error", "Chyba")
            self.log_widget.append(f"{err_title}: {result['error']}")
        
        self.repair_button.setEnabled(True)
        self.repair_button.setText(CoreBridge.translate("btn_repair", "✅ Opraviť PIP"))
        
        self.installation_finished.emit(result)
        
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.worker.deleteLater()
            self.thread.deleteLater()
            self.thread = None
            self.worker = None
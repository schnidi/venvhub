#-------------------------------------------------------------------------------
# Súbor: core/logic/button/manager/create.py
# Logika a asynchrónny worker pre vytváranie nových virtuálnych prostredí (Venv).
# Podporuje štandardný venv aj špeciálny virtualenv režim pre Embed Python.
# Plne prepojené na centrálny mostík CoreBridge, DialogBridge a LanguageBridge.
#-------------------------------------------------------------------------------

"""
Tento modul zabezpečuje:
- Vytvorenie čistého prostredia podľa typu Pythonu (Systémový vs. Lokálny Embed).
- Opravu konfiguračného súboru ._pth a overenie PIPu pre embed runtime prostredia.
- Zabezpečenie inštalácie základných nástrojov (setuptools, wheel).
- Snímku systémových balíčkov pre ochranu APT a vytvorenie rodného listu prostredia.
- Evidenciu hardvérového kľúča pre ochranu prenosnosti (Portability Guard).
"""

import os
import subprocess
from PyQt6.QtWidgets import QInputDialog
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.core_bridge import CoreBridge
from core._path import Paths
from core.logic.vs_code_json import VSCodeIntegration
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.sanitize_venv_name import sanitize_venv_name
from core.logic.sluzby.log_print_desktop import DesktopLogger
from core.logic.sluzby.embed_python_created import EmbedPythonCreated
from core.logic.sluzby.apt_logic import AptLogic

# --- ČISTÉ MOSTY (0 VÄZIEB NA WINDOWS PRIAMO V LOGIKE) ---
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.dialog_bridge import DialogBridge

LOGGING_ENABLED = False
create_logger = DesktopLogger(is_enabled=LOGGING_ENABLED, filename="VENV_CREATE_LOG.txt")


class VenvCreatorWorker(QObject):
    """
    Asynchrónny pracovník bežiaci vo vedľajšom vlákne.
    Zabezpečuje samotnú tvorbu venvu na disku bez blokovania používateľského rozhrania.
    """
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress_log = pyqtSignal(str)

    def __init__(
        self,
        python_exe: str,
        venv_path: str,
        is_local: bool = False,
        is_portable: bool = True,
        project_name: str = "",
        parent_py_path: str = "",
    ):
        super().__init__()
        self.python_exe = os.path.normpath(python_exe)
        self.venv_path = os.path.normpath(venv_path)
        self.is_local = is_local
        self.is_portable = is_portable
        self.project_name = project_name
        self.parent_py_path = parent_py_path
        self.is_running = True

    def run(self):
        """Vykoná proces tvorby virtuálneho prostredia krok za krokom."""
        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        create_logger.write(f"\nŠTART PROCESU: {self.python_exe} -> {self.venv_path}")

        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("PYTHONHOME", None)
        clean_env["PATH"] = ";".join([
            os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32"),
            os.path.dirname(self.python_exe),
            clean_env.get("PATH", ""),
        ])

        try:
            # --- 1. VYTVORENIE VENVU PODĽA TYPU PYTHONU ---
            if self.is_local:
                msg_step1 = LanguageBridge.translate(
                    "msg_create_step1_virtualenv", "Krok 1: Spúšťam virtualenv pre lokálny embed..."
                )
                self.progress_log.emit(msg_step1)

                command = [
                    self.python_exe,
                    "-I",
                    "-B",
                    "-m",
                    "virtualenv",
                    "--no-download",
                    self.venv_path,
                ]

                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                    env=clean_env,
                    cwd=os.path.dirname(self.python_exe),
                )

                if result.returncode != 0:
                    raise RuntimeError(f"virtualenv zlyhal s kódom {result.returncode}:\n{result.stderr}")

                msg_step2 = LanguageBridge.translate(
                    "msg_create_step2_pth", "Krok 2: Opravujem konfiguráciu (._pth)..."
                )
                self.progress_log.emit(msg_step2)
                EmbedPythonCreated.fix_pth_file(self.venv_path, self.python_exe)

                msg_step3 = LanguageBridge.translate(
                    "msg_create_step3_pip", "Krok 3: Overujem funkčnosť PIP..."
                )
                self.progress_log.emit(msg_step3)
                if not EmbedPythonCreated.verify_pip_functional(self.venv_path):
                    raise RuntimeError("PIP bol vytvorený, ale nefunguje (Access Violation / poškodené binárky).")

            else:
                msg_std = LanguageBridge.translate(
                    "msg_create_standard_venv", "Metóda: Štandardný systémový venv..."
                )
                self.progress_log.emit(msg_std)
                command = [self.python_exe, "-m", "venv", self.venv_path]

                res = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                    env=clean_env,
                )
                if res.returncode != 0:
                    raise RuntimeError(f"venv zlyhal s kódom {res.returncode}:\n{res.stderr}")

            # --- 2. DOINŠTALOVANIE NÁSTROJOV (SETUPTOOLS, WHEEL) ---
            pip_exe = os.path.join(self.venv_path, "Scripts", "pip.exe") if os.name == 'nt' else os.path.join(self.venv_path, "bin", "pip")
            if os.path.exists(pip_exe):
                msg_tools = LanguageBridge.translate(
                    "msg_create_install_tools", "4. Inštalujem základné nástroje (setuptools, wheel)..."
                )
                self.progress_log.emit(msg_tools)
                tools_result = subprocess.run(
                    [pip_exe, "install", "setuptools", "wheel"],
                    capture_output=True,
                    text=True,
                    creationflags=CREATE_NO_WINDOW
                )
                if tools_result.returncode != 0:
                    create_logger.write(f"UPOZORNENIE: setuptools/wheel sa nenainštalovali:\n{tools_result.stderr}")
                    warn_tools = LanguageBridge.translate(
                        "msg_create_tools_failed", "Upozornenie: setuptools/wheel sa nepodarilo doinštalovať."
                    )
                    self.progress_log.emit(warn_tools)

            # --- 3. SNÍMKA SYSTÉMOVÝCH BALÍČKOV (Základ venvu pre APT) ---
            msg_snap = LanguageBridge.translate(
                "msg_create_system_snapshot", "Zapisujem systémové balíčky prostredia pre ochranu APT..."
            )
            self.progress_log.emit(msg_snap)
            try:
                snapshot = AptLogic.snapshot_system_packages(self.venv_path)
                create_logger.write(f"SYSTÉMOVÉ BALÍČKY: {snapshot}")
            except Exception as snap_err:
                create_logger.write(f"UPOZORNENIE: snímku systémových balíčkov sa nepodarilo zapísať: {snap_err}")

            # --- 4. ZÁPIS RODNÉHO LISTU ---
            msg_cert = LanguageBridge.translate(
                "msg_create_cert", "Zapisujem rodný list prostredia..."
            )
            self.progress_log.emit(msg_cert)
            new_venv_python = Paths.get_venv_python_exe_path(self.venv_path)
            folder_name = os.path.basename(self.venv_path)

            BirthCertificateGenerator.create_venv_certificate(
                project_name=self.project_name,
                venv_name=folder_name,
                venv_path=self.venv_path,
                python_exe=new_venv_python,
                source_python_path=self.parent_py_path,
            )
            BirthCertificateGenerator.update_venv_certificate(self.venv_path)

            # --- 5. EVIDENCIA PRE OCHRANU PRENOSNOSTI (PORTABILITY GUARD) ---
            CoreBridge.register_venv_creation(self.venv_path, self.parent_py_path)

            msg_ok = LanguageBridge.translate(
                "msg_create_ok", "Všetko v poriadku, prostredie je aktívne a pripravené."
            )
            self.progress_log.emit(msg_ok)
            self.finished.emit()

        except Exception as e:
            create_logger.write(f"KRITICKÁ CHYBA: {str(e)}")
            self.error.emit(str(e))
        finally:
            self.is_running = False


class VenvCreationBridge(QObject):
    """Pomocný mostík signálov na bezpečné doručenie výsledkov do GUI okna."""
    success_signal = pyqtSignal()
    error_signal = pyqtSignal(str)


class CreateVenvHandler:
    """
    Statický handler, ktorý zachytáva kliknutie na tlačidlo '+ VYTVORIŤ' v GUI.
    Získava dáta o zvolenom Pythone cez mostík CoreBridge a spúšťa ProgressDialog cez DialogBridge.
    """
    _thread = None
    _worker = None

    @staticmethod
    def run(parent, core, py_list: list[dict]):
        if not core.active_project:
            DialogBridge.warning(
                parent,
                LanguageBridge.translate("title_error", "Chyba"),
                LanguageBridge.translate("err_select_project", "Najprv vyberte projekt."),
            )
            return

        title_input = LanguageBridge.translate("title_new_venv", "Nové prostredie")
        label_input = LanguageBridge.translate("msg_venv_name_for", "Meno pre '{0}':").format(core.active_project)
        
        venv_name, ok = QInputDialog.getText(parent, title_input, label_input)

        raw_venv_name = venv_name.strip()
        if not ok or not raw_venv_name:
            return

        safe_venv_name = sanitize_venv_name(raw_venv_name)
        folder_name = f"{core.active_project}_{safe_venv_name}"
        full_path = Paths.get_venv_path(core.venv_hub_root, folder_name)

        if os.path.exists(full_path):
            DialogBridge.warning(
                parent,
                LanguageBridge.translate("title_error", "Chyba"),
                LanguageBridge.translate("msg_venv_exists_simple", "Virtuálne prostredie s týmto názvom už existuje."),
            )
            return

        selected_idx = parent.combo_py.currentIndex()
        if selected_idx < 0 or selected_idx >= len(py_list):
            DialogBridge.warning(
                parent,
                LanguageBridge.translate("title_error", "Chyba"),
                LanguageBridge.translate("err_select_python", "Vyberte platný Python interpreter."),
            )
            return

        selected_python_data = py_list[selected_idx]
        python_exe = selected_python_data["path"]
        
        is_local = selected_python_data.get("is_local", False) or "[Local]" in selected_python_data.get("display", "")

        parent_py_path = python_exe
        if is_local:
            app_root = Paths.get_app_root_path()
            try:
                rel_path = os.path.relpath(python_exe, app_root)
                parent_py_path = f"[REL_TO_APP]/{rel_path}".replace("\\", "/")
            except ValueError:
                pass

        # Použitie čistého DialogBridge namiesto priameho importu ProgressDialogu
        progress_dialog = DialogBridge.progress_dialog(parent)
        dialog_msg = LanguageBridge.translate("msg_creating_venv", "Vytváram venv: {0}...").format(safe_venv_name)
        progress_dialog.set_message(dialog_msg)

        CreateVenvHandler._thread = QThread()
        CreateVenvHandler._worker = VenvCreatorWorker(
            python_exe,
            full_path,
            is_local,
            core.is_portable,
            project_name=core.active_project,
            parent_py_path=parent_py_path,
        )
        CreateVenvHandler._worker.moveToThread(CreateVenvHandler._thread)

        CreateVenvHandler._thread.started.connect(CreateVenvHandler._worker.run)
        CreateVenvHandler._worker.progress_log.connect(progress_dialog.add_log_message)

        CreateVenvHandler._worker.finished.connect(CreateVenvHandler._thread.quit)
        CreateVenvHandler._worker.finished.connect(CreateVenvHandler._worker.deleteLater)
        CreateVenvHandler._worker.error.connect(CreateVenvHandler._thread.quit)
        CreateVenvHandler._worker.error.connect(CreateVenvHandler._worker.deleteLater)
        CreateVenvHandler._thread.finished.connect(CreateVenvHandler._thread.deleteLater)

        def on_success():
            progress_dialog.accept()
            try:
                project_path = Paths.get_project_path(
                    getattr(core, "projects_root", ""), core.active_project
                )
                VSCodeIntegration.initialize_project_settings(project_path, full_path)
            except Exception as e:
                DialogBridge.critical(
                    parent,
                    LanguageBridge.translate("title_vscode_error", "Chyba VS Code"),
                    LanguageBridge.translate("msg_vscode_config_failed", "Zápis konfigurácie pre editor zlyhal:\n{0}").format(str(e)),
                )

            parent.refresh_table()

        def on_error(msg: str):
            progress_dialog.reject()
            DialogBridge.critical(
                parent,
                LanguageBridge.translate("title_error", "Chyba"),
                LanguageBridge.translate("msg_create_failed_log_desktop", "Zlyhanie pri tvorbe prostredia:\n\n{0}").format(msg),
            )

        bridge = VenvCreationBridge(parent)
        bridge.success_signal.connect(on_success)
        bridge.error_signal.connect(on_error)

        CreateVenvHandler._worker.finished.connect(bridge.success_signal)
        CreateVenvHandler._worker.error.connect(bridge.error_signal)

        CreateVenvHandler._thread.start()
        progress_dialog.exec()
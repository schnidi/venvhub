# ----------------------------------------
# Súbor: core/logic/button/manager/create.py
# ----------------------------------------

import os
import subprocess
import re
import json
from datetime import datetime
from PyQt6.QtWidgets import QInputDialog, QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.logic.language_manager import LanguageManager
from windows.progress_dialog import ProgressDialog
from core._path import Paths
from core.logic.vs_code_json import VSCodeIntegration
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.sanitize_venv_name import sanitize_venv_name

from core.logic.sluzby.log_print_desktop import DesktopLogger
from core.logic.sluzby.embed_python_created import EmbedPythonCreated
from core.logic.sluzby.apt_logic import AptLogic

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox

LOGGING_ENABLED = False
create_logger = DesktopLogger(is_enabled=LOGGING_ENABLED, filename="VENV_CREATE_LOG.txt")


class VenvCreatorWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress_log = pyqtSignal(str)

    def __init__(
        self,
        python_exe,
        venv_path,
        is_local=False,
        is_portable=True,
        project_name="",
        parent_py_path="",
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
        CREATE_NO_WINDOW = 0x08000000
        create_logger.write(f"\nŠTART PROCESU: {self.python_exe} -> {self.venv_path}")

        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env.pop("PYTHONHOME", None)
        clean_env["PATH"] = ";".join([
            os.path.join(
                os.environ.get("SystemRoot", "C:\\Windows"), "System32"
            ),
            os.path.dirname(self.python_exe),
            clean_env.get("PATH", ""),
        ])

        try:
            if self.is_local:
                self.progress_log.emit(
                    LanguageManager.get(
                        "msg_create_step1_virtualenv",
                        "Krok 1: Spúšťam virtualenv...",
                    )
                )
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
                    raise RuntimeError(
                        f"virtualenv zlyhal s kódom {result.returncode}:\n"
                        f"{result.stderr}"
                    )

                self.progress_log.emit(
                    LanguageManager.get(
                        "msg_create_step2_pth",
                        "Krok 2: Opravujem konfiguráciu (._pth)...",
                    )
                )
                EmbedPythonCreated.fix_pth_file(self.venv_path, self.python_exe)

                self.progress_log.emit(
                    LanguageManager.get(
                        "msg_create_step3_pip",
                        "Krok 3: Overujem funkčnosť PIP...",
                    )
                )
                if not EmbedPythonCreated.verify_pip_functional(self.venv_path):
                    raise RuntimeError(
                        "PIP bol vytvorený, ale nefunguje (Access Violation)."
                    )

            else:
                self.progress_log.emit(
                    LanguageManager.get(
                        "msg_create_standard_venv", "Metóda: Štandardný venv..."
                    )
                )
                command = [self.python_exe, "-m", "venv", self.venv_path]

                res = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                    env=clean_env,
                )
                if res.returncode != 0:
                    raise RuntimeError(
                        f"venv zlyhal s kódom {res.returncode}:\n{res.stderr}"
                    )

            # --- DOINŠTALOVANIE SETUOTOOLS A WHEEL PRIAMO TU V CREATE.PY ---
            pip_exe = os.path.join(self.venv_path, "Scripts", "pip.exe")
            if os.path.exists(pip_exe):
                self.progress_log.emit(
                    LanguageManager.get(
                        "msg_create_install_tools",
                        "4. Inštalujem základné nástroje (setuptools, wheel)...",
                    )
                )
                tools_result = subprocess.run(
                    [pip_exe, "install", "setuptools", "wheel"],
                    capture_output=True,
                    text=True,
                    creationflags=CREATE_NO_WINDOW
                )
                if tools_result.returncode != 0:
                    # Nie je fatálne (napr. offline), ale snímka systémových balíčkov
                    # zachytí len to, čo na disku naozaj je.
                    create_logger.write(f"UPOZORNENIE: setuptools/wheel sa nenainštalovali:\n{tools_result.stderr}")
                    self.progress_log.emit(
                        LanguageManager.get(
                            "msg_create_tools_failed",
                            "Upozornenie: setuptools/wheel sa nepodarilo nainštalovať.",
                        )
                    )

            # --- SNÍMKA SYSTÉMOVÝCH BALÍČKOV (základ venvu, ktorý sa nikdy nemaže) ---
            self.progress_log.emit(
                LanguageManager.get(
                    "msg_create_system_snapshot", "Zapisujem systémové balíčky prostredia..."
                )
            )
            try:
                snapshot = AptLogic.snapshot_system_packages(self.venv_path)
                create_logger.write(f"SYSTÉMOVÉ BALÍČKY: {snapshot}")
            except Exception as snap_err:
                # Nie je fatálne: pri prvom použití APT sa snímka odhadne z CORE_TOOLS.
                create_logger.write(f"UPOZORNENIE: snímku systémových balíčkov sa nepodarilo zapísať: {snap_err}")

            # Rodný list generujeme priamo tu na pozadí!
            self.progress_log.emit(
                LanguageManager.get(
                    "msg_create_cert", "Zapisujem rodný list prostredia..."
                )
            )
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

            self.progress_log.emit(
                LanguageManager.get(
                    "msg_create_ok", "Všetko v poriadku, prostredie je aktívne."
                )
            )
            self.finished.emit()

        except Exception as e:
            create_logger.write(f"KRITICKÁ CHYBA: {str(e)}")
            self.error.emit(str(e))
        finally:
            self.is_running = False


class VenvCreationBridge(QObject):
    success_signal = pyqtSignal()
    error_signal = pyqtSignal(str)


class CreateVenvHandler:
    _thread = None
    _worker = None

    @staticmethod
    def run(parent, core, py_list):
        if not core.active_project:
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(
                parent,
                LanguageManager.get("title_error", "Chyba"),
                LanguageManager.get("err_select_project", "Vyberte projekt."),
            )
            return

        venv_name, ok = QInputDialog.getText(
            parent,
            LanguageManager.get("title_new_venv", "Nové prostredie"),
            LanguageManager.get("msg_venv_name_for", "Meno pre '{0}':").format(
                core.active_project
            ),
        )

        raw_venv_name = venv_name.strip()
        if not ok or not raw_venv_name:
            return

        safe_venv_name = sanitize_venv_name(raw_venv_name)
        folder_name = f"{core.active_project}_{safe_venv_name}"
        full_path = Paths.get_venv_path(core.venv_hub_root, folder_name)

        if os.path.exists(full_path):
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(
                parent,
                LanguageManager.get("title_error", "Chyba"),
                LanguageManager.get(
                    "msg_venv_exists_simple", "Venv už existuje."
                ),
            )
            return

        selected_idx = parent.combo_py.currentIndex()
        python_exe = py_list[selected_idx]["path"]
        is_local = "[Local]" in py_list[selected_idx]["display"]

        parent_py_path = python_exe
        if is_local:
            app_root = Paths.get_app_root_path()
            try:
                rel_path = os.path.relpath(python_exe, app_root)
                parent_py_path = f"[REL_TO_APP]/{rel_path}".replace("\\", "/")
            except ValueError:
                pass

        progress_dialog = ProgressDialog(parent)
        progress_dialog.set_message(
            LanguageManager.get(
                "msg_creating_venv", "Vytváram venv: {0}..."
            ).format(safe_venv_name)
        )

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
        CreateVenvHandler._worker.progress_log.connect(
            progress_dialog.add_log_message
        )

        CreateVenvHandler._worker.finished.connect(
            CreateVenvHandler._thread.quit
        )
        CreateVenvHandler._worker.finished.connect(
            CreateVenvHandler._worker.deleteLater
        )
        CreateVenvHandler._worker.error.connect(CreateVenvHandler._thread.quit)
        CreateVenvHandler._worker.error.connect(
            CreateVenvHandler._worker.deleteLater
        )
        CreateVenvHandler._thread.finished.connect(
            CreateVenvHandler._thread.deleteLater
        )

        def on_success():
            progress_dialog.accept()
            try:
                project_path = Paths.get_project_path(
                    getattr(core, "projects_root", ""), core.active_project
                )
                VSCodeIntegration.initialize_project_settings(
                    project_path, full_path
                )
            except Exception as e:
                # --- ZMENA NA NAŠU LIŠTU ---
                CustomMessageBox.critical(
                    parent,
                    LanguageManager.get("title_vscode_error", "Chyba VS Code"),
                    LanguageManager.get(
                        "msg_vscode_config_failed",
                        "Zápis konfigurácie pre VS Code zlyhal:\n{0}",
                    ).format(str(e)),
                )

            parent.refresh_table()

        def on_error(msg):
            progress_dialog.reject()
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.critical(
                parent,
                LanguageManager.get("title_error", "Chyba"),
                LanguageManager.get(
                    "msg_create_failed_log_desktop",
                    "Zlyhanie pri tvorbe prostredia:\n\n{0}",
                ).format(msg),
            )

        bridge = VenvCreationBridge(parent)
        bridge.success_signal.connect(on_success)
        bridge.error_signal.connect(on_error)

        CreateVenvHandler._worker.finished.connect(bridge.success_signal)
        CreateVenvHandler._worker.error.connect(bridge.error_signal)

        CreateVenvHandler._thread.start()
        progress_dialog.exec()
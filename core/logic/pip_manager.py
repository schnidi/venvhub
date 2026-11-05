#----------------------------------------------------
# Súbor: core/logic/pip_manager.py
#----------------------------------------------------

import os
import json
import subprocess
import threading
import re
from PyQt6.QtCore import QObject, pyqtSignal

from core._path import Paths
from core.core_bridge import CoreBridge
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.path_normalizer import PathNormalizer
from core.logic.sluzby.apt_logic import AptLogic


class PipSignalEmitter(QObject):
    log_message = pyqtSignal(str)
    finished = pyqtSignal()


class PipWorker:
    def __init__(self, cmd, start_msg, venv_path=None, manager_type="pip"):
        self.cmd = cmd
        self.start_msg = start_msg
        self.venv_path = venv_path
        self.manager_type = manager_type
        self.signals = PipSignalEmitter()
        self.success = False
        
    def run(self):
        self.signals.log_message.emit(f"\n--- {self.start_msg} ---")
        self.success = False
        try:
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            process = subprocess.Popen(
                self.cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding="utf-8", 
                errors="replace", 
                creationflags=CREATE_NO_WINDOW
            )
            for line in process.stdout: 
                self.signals.log_message.emit(line.strip())
            process.wait()
            
            self.success = (process.returncode == 0)
            
            if self.success and self.venv_path:
                # UNIVERZÁLNA KONTROLA ZÁVISLOSTÍ (pre UV aj pre PIP)
                msg_check = CoreBridge.translate(
                    "apt_checking_deps", 
                    "--- Vykonávam {0} kontrolu závislostí... ---"
                ).format(self.manager_type.upper())
                self.signals.log_message.emit(msg_check)

                dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.venv_path)
                cmd_check = dispatcher.get("check")
                check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                
                if check_proc.returncode == 0:
                    msg_ok = CoreBridge.translate("apt_deps_compatible", "✅ Všetky závislosti sú kompatibilné.")
                    self.signals.log_message.emit(msg_ok)
                else:
                    output_text = (check_proc.stdout + "\n" + check_proc.stderr).strip()
                    msg_err = CoreBridge.translate(
                        "apt_deps_conflicts", 
                        "⚠️ [{0} Check] Zistené nezrovnalosti v závislostiach:\n{1}"
                    ).format(self.manager_type.upper(), output_text)
                    self.signals.log_message.emit(msg_err)

                    if self.manager_type == "uv":
                        conflicts = list(set(re.findall(r"requires\s+`([^`]+)`", output_text)))
                        if conflicts:
                            self.signals.log_message.emit(CoreBridge.translate("uv_found_conflicts", "Zistené konflikty: {0}").format(', '.join(conflicts)))
                            self.signals.log_message.emit(CoreBridge.translate("uv_fixing_downgrade", "Pokúšam sa o automatickú opravu (downgrade/inštaláciu presných verzií)..."))
                            
                            cmd_fix = dispatcher.get("install_multiple_exact", packages=conflicts)
                            fix_proc = subprocess.Popen(
                                cmd_fix, 
                                stdout=subprocess.PIPE, 
                                stderr=subprocess.STDOUT, 
                                text=True, 
                                encoding='utf-8',
                                bufsize=1,
                                creationflags=CREATE_NO_WINDOW
                            )
                            for line in fix_proc.stdout:
                                self.signals.log_message.emit(line.strip())
                            fix_proc.wait()
                            
                            if fix_proc.returncode == 0:
                                self.signals.log_message.emit(CoreBridge.translate("uv_verifying", "Overujem stav po oprave..."))
                                check2_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                                if check2_proc.returncode == 0 or "All installed packages are compatible" in check2_proc.stdout:
                                    self.signals.log_message.emit(CoreBridge.translate("uv_fix_ok", "✅ Všetky konflikty boli úspešne vyriešené."))
                                else:
                                    self.signals.log_message.emit(CoreBridge.translate("uv_fix_fail_check_log", "⚠️ Nepodarilo sa vyriešiť všetky konflikty. Skontrolujte log."))
                            else:
                                self.signals.log_message.emit(CoreBridge.translate("uv_fix_error_manual", "⚠️ Automatická oprava zlyhala. Opravte závislosti manuálne."))
                        else:
                            self.signals.log_message.emit(CoreBridge.translate("uv_parse_error_worker", "⚠️ Boli nájdené problémy so závislosťami, ale aplikácia ich nedokázala automaticky vyparsovať."))

                BirthCertificateGenerator.update_venv_certificate(self.venv_path)

            msg_done = CoreBridge.translate("msg_done", "--- HOTOVO ---")
            self.signals.log_message.emit(msg_done)
            
        except FileNotFoundError: 
            msg = CoreBridge.translate("err_cmd_not_found", "KRITICKÁ CHYBA: Príkaz nebol nájdený: {0}").format(' '.join(self.cmd))
            self.signals.log_message.emit(msg)
            self.success = False
        except Exception as e: 
            msg = CoreBridge.translate("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e))
            self.signals.log_message.emit(msg)
            self.success = False
        finally: 
            self.signals.finished.emit()


class UpdateAllWorker:
    """Deleguje kompletnú hromadnú aktualizáciu balíčkov na CoreBridge."""
    def __init__(self, venv_path, manager_type="pip", core=None):
        self.venv_path = venv_path
        self.manager_type = manager_type
        self.core = core
        self.signals = PipSignalEmitter()
        self.success = False

    def run(self):
        self.success = CoreBridge.update_all_packages(
            venv_path=self.venv_path,
            core=self.core,
            manager_type=self.manager_type,
            log_callback=self.signals.log_message.emit
        )
        self.signals.finished.emit()


class RequirementsInstallWorker:
    def __init__(self, venv_path, project_root, manager_type="pip", core=None):
        self.venv_path = venv_path
        self.project_root = project_root
        self.manager_type = manager_type
        self.core = core
        self.signals = PipSignalEmitter()
        self.success = False

        if not self.core or not hasattr(self.core, 'pip_e_packages_root'):
            pip_e_root = ""
            try:
                cfg_path = Paths.get_config_file_path()
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        pip_e_root = json.load(f).get("pip_e_packages_root", "")
            except Exception:
                pass

            class _FallbackCore:
                def __init__(self, mgr, root, proj, pe_root):
                    self.package_manager = mgr
                    self.pip_e_packages_root = pe_root
                    self.projects_root = root
                    self.active_project = proj

            proj_name = os.path.basename(os.path.normpath(self.project_root)) if self.project_root else ""
            proj_root = os.path.dirname(os.path.normpath(self.project_root)) if self.project_root else ""
            self.core = _FallbackCore(self.manager_type, proj_root, proj_name, pip_e_root)
        else:
            if not hasattr(self.core, 'package_manager'):
                self.core.package_manager = self.manager_type

        req_path = Paths.get_requirements_txt_path(self.project_root)
        self.cmd = ["apt-sync", req_path]

    def run(self):
        req_path = Paths.get_requirements_txt_path(self.project_root)
        if not os.path.exists(req_path):
            msg = CoreBridge.translate("err_req_not_found", "CHYBA: Súbor 'requirements.txt' nebol nájdený.")
            self.signals.log_message.emit(msg)
            self.success = False
            self.signals.finished.emit()
            return

        try:
            self.signals.log_message.emit(
                CoreBridge.translate("apt_requirements_sync_start", "\n--- Inicializujem požiadavky z requirements.txt (APT) ---")
            )

            PathNormalizer.sanitize_requirements_file(req_path)

            self.success = AptLogic.install_sync(
                core=self.core,
                venv_path=self.venv_path,
                log_callback=self.signals.log_message.emit,
                req_file_path=req_path
            )

            if self.success:
                BirthCertificateGenerator.update_venv_certificate(self.venv_path)
                msg_done = CoreBridge.translate("msg_done", "--- HOTOVO ---")
                self.signals.log_message.emit(msg_done)
            else:
                self.signals.log_message.emit(
                    CoreBridge.translate("apt_requirements_sync_fail", "⚠️ Synchronizácia požiadaviek nebola úspešná.")
                )

        except Exception as e:
            msg_err = CoreBridge.translate("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e))
            self.signals.log_message.emit(msg_err)
            self.success = False
        finally:
            self.signals.finished.emit()


class PipManager:
    _current_thread = None
    _current_worker = None

    @staticmethod
    def _run_pip_task(worker, log_widget):
        if PipManager._current_thread and PipManager._current_thread.is_alive():
            msg = CoreBridge.translate("msg_busy", "!!! Už prebieha iná operácia, počkajte na jej dokončenie. !!!")
            log_widget.append(msg)
            return
        worker.signals.log_message.connect(log_widget.append)
        PipManager._current_worker = worker
        PipManager._current_thread = threading.Thread(target=worker.run, daemon=True)
        PipManager._current_thread.start()
        
    @staticmethod
    def install_package(venv_path, package_name, log_widget, manager_type="pip"):
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("install", package_name=package_name)
        except (ValueError, KeyError) as e:
            log_widget.append(f"CHYBA: {e}")
            return
            
        start_msg = CoreBridge.translate("msg_installing", "Inštalujem {0}...").format(package_name)
        worker = PipWorker(cmd, start_msg, venv_path, manager_type)
        PipManager._run_pip_task(worker, log_widget)
        
    @staticmethod
    def uninstall_package(venv_path, package_name, log_widget, manager_type="pip"):
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("uninstall", package_name=package_name)
        except (ValueError, KeyError) as e:
            log_widget.append(f"CHYBA: {e}")
            return
            
        start_msg = CoreBridge.translate("msg_uninstalling", "Odinštalujem {0}...").format(package_name)
        worker = PipWorker(cmd, start_msg, venv_path, manager_type)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def install_requirements(venv_path, project_root, log_widget, manager_type="pip", core=None, *args, **kwargs):
        if not core:
            for a in args:
                if hasattr(a, 'projects_root'):
                    core = a
                    break

        worker = RequirementsInstallWorker(venv_path, project_root, manager_type, core)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def update_all_packages(venv_path, log_widget, manager_type="pip", core=None):
        worker = UpdateAllWorker(venv_path, manager_type, core=core)
        PipManager._run_pip_task(worker, log_widget)
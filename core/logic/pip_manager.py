#----------------------------------------
# Súbor: core/logic/pip_manager.py
#----------------------------------------

import os
import subprocess
import threading
import re
from PyQt6.QtCore import QObject, pyqtSignal

from core.logic.language_manager import LanguageManager
from core._path import Paths
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.path_normalizer import PathNormalizer
from core.logic.sluzby.requirements_parser import RequirementsParser

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
        self.success = False  # Predvolený stav
        
    def run(self):
        self.signals.log_message.emit(f"\n--- {self.start_msg} ---")
        self.success = False
        try:
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            # >>> OPRAVA KÓDOVANIA (UTF-8 pre UV a moderné pip výstupy)
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
            
            # --- ZÁZNAM O ÚSPECHU ---
            self.success = (process.returncode == 0)
            
            if self.success and self.venv_path:
                # --- KONTROLA ZÁVISLOSTÍ PRE UV VETVU ---
                if self.manager_type == "uv":
                    self.signals.log_message.emit(LanguageManager.get("uv_checking_deps", "--- Vykonávam UV kontrolu závislostí... ---"))
                    dispatcher = PackageManagerFactory.get_dispatcher("uv", self.venv_path)
                    cmd_check = dispatcher.get("check")
                    check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                    
                    if check_proc.returncode != 0:
                        output_text = check_proc.stdout + "\n" + check_proc.stderr
                        conflicts = list(set(re.findall(r"requires\s+`([^`]+)`", output_text)))
                        
                        if conflicts:
                            self.signals.log_message.emit(LanguageManager.get("uv_found_conflicts", "Zistené konflikty: {0}").format(', '.join(conflicts)))
                            self.signals.log_message.emit(LanguageManager.get("uv_fixing_downgrade", "Pokúšam sa o automatickú opravu (downgrade/inštaláciu presných verzií)..."))
                            
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
                                self.signals.log_message.emit(LanguageManager.get("uv_verifying", "Overujem stav po oprave..."))
                                check2_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                                if check2_proc.returncode == 0 or "All installed packages are compatible" in check2_proc.stdout:
                                    self.signals.log_message.emit(LanguageManager.get("uv_fix_ok", "✅ Všetky konflikty boli úspešne vyriešené."))
                                else:
                                    self.signals.log_message.emit(LanguageManager.get("uv_fix_fail_check_log", "⚠️ Nepodarilo sa vyriešiť všetky konflikty. Skontrolujte log."))
                            else:
                                self.signals.log_message.emit(LanguageManager.get("uv_fix_error_manual", "⚠️ Automatická oprava zlyhala. Opravte závislosti manuálne."))
                        else:
                            self.signals.log_message.emit(LanguageManager.get("uv_parse_error_worker", "⚠️ Boli nájdené problémy so závislosťami, ale aplikácia ich nedokázala automaticky vyparsovať."))
                    else:
                        self.signals.log_message.emit(LanguageManager.get("uv_compatible", "✅ Všetky závislosti sú kompatibilné."))

                BirthCertificateGenerator.update_venv_certificate(self.venv_path)

            msg_done = LanguageManager.get("msg_done", "--- HOTOVO ---")
            self.signals.log_message.emit(msg_done)
            
        except FileNotFoundError: 
            msg = LanguageManager.get("err_cmd_not_found", "KRITICKÁ CHYBA: Príkaz nebol nájdený: {0}").format(' '.join(self.cmd))
            self.signals.log_message.emit(msg)
            self.success = False
        except Exception as e: 
            msg = LanguageManager.get("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e))
            self.signals.log_message.emit(msg)
            self.success = False
        finally: 
            self.signals.finished.emit()

class UpdateAllWorker:
    def __init__(self, venv_path, manager_type):
        self.venv_path = venv_path
        self.manager_type = manager_type
        self.signals = PipSignalEmitter()
        self.success = False  # Predvolený stav

    def run(self):
        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        self.success = False
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.venv_path)
            
            msg_step1 = LanguageManager.get("msg_step1_pip", "\n--- Krok 1: Kontrolujem a aktualizujem inštalátor... ---")
            self.signals.log_message.emit(msg_step1)
            
            cmd_update_pip = dispatcher.get("upgrade_pip")
            pip_process = subprocess.run(cmd_update_pip, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            
            if pip_process.returncode == 0:
                BirthCertificateGenerator.update_venv_certificate(self.venv_path)

            full_output = (pip_process.stdout + pip_process.stderr).strip()
            for line in full_output.split('\n'):
                if line: self.signals.log_message.emit(line)

            msg_step2 = LanguageManager.get("msg_step2_outdated", "\n--- Krok 2: Hľadám ostatné zastarané balíčky... ---")
            self.signals.log_message.emit(msg_step2)
            
            cmd_list = dispatcher.get("list_outdated")
            list_process = subprocess.run(cmd_list, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)

            if list_process.returncode != 0:
                msg_err = LanguageManager.get("err_list_failed", "CHYBA: Nepodarilo sa získať zoznam balíčkov.")
                self.signals.log_message.emit(msg_err)
                self.signals.log_message.emit(list_process.stderr)
                self.success = False
                return

            lines = list_process.stdout.strip().split('\n')[2:]
            outdated_packages = [line.split()[0] for line in lines if line.strip()]

            if not outdated_packages:
                msg_all_ok = LanguageManager.get("msg_all_pkgs_ok", ">>> Zhrnutie: Všetky ostatné balíčky sú aktuálne. Niet čo robiť.")
                msg_done = LanguageManager.get("msg_done", "--- HOTOVO ---")
                self.signals.log_message.emit(msg_all_ok)
                self.signals.log_message.emit(msg_done)
                self.success = True  # Všetko bolo OK, nemali sme čo robiť
                return

            msg_found = LanguageManager.get("msg_found_outdated", "Nájdené zastarané balíčky: {0}").format(', '.join(outdated_packages))
            self.signals.log_message.emit(msg_found)
            
            cmd_upgrade = dispatcher.get("upgrade_multiple", packages=outdated_packages)
            
            msg_step3 = LanguageManager.get("msg_step3_upgrade", "\n--- Krok 3: Aktualizujem nájdené balíčky... ---")
            self.signals.log_message.emit(msg_step3)
            
            upgrade_process = subprocess.Popen(
                cmd_upgrade, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding="utf-8", 
                errors="replace", 
                creationflags=CREATE_NO_WINDOW
            )
            # <<< KONIEC OPRAVY
            for line in upgrade_process.stdout: self.signals.log_message.emit(line.strip())
            upgrade_process.wait()

            # --- ZÁZNAM O ÚSPECHU ---
            self.success = (upgrade_process.returncode == 0)

            if self.success:
                # --- KROK 4: KONTROLA A OPRAVA UV ZÁVISLOSTÍ ---
                if self.manager_type == "uv":
                    self.signals.log_message.emit("\n--- Krok 4: Kontrola a oprava závislostí (UV Check) ---")
                    cmd_check = dispatcher.get("check")
                    check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                    
                    if check_proc.returncode != 0:
                        output_text = check_proc.stdout + "\n" + check_proc.stderr
                        
                        conflicts = list(set(re.findall(r"requires\s+`([^`]+)`", output_text)))
                        
                        if conflicts:
                            self.signals.log_message.emit(LanguageManager.get("uv_found_conflicts", "Zistené konflikty: {0}").format(', '.join(conflicts)))
                            self.signals.log_message.emit(LanguageManager.get("uv_fixing", "Pokúšam sa o automatickú opravu (downgrade na presné verzie)..."))
                            
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
                                self.signals.log_message.emit(LanguageManager.get("uv_verifying", "Overujem stav po oprave..."))
                                check2_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                                if check2_proc.returncode == 0 or "All installed packages are compatible" in check2_proc.stdout:
                                    self.signals.log_message.emit(LanguageManager.get("uv_fix_ok", "✅ Všetky konflikty boli úspešne vyriešené."))
                                else:
                                    self.signals.log_message.emit(LanguageManager.get("uv_fix_fail", "⚠️ Nepodarilo sa vyriešiť všetky konflikty."))
                            else:
                                self.signals.log_message.emit(LanguageManager.get("uv_fix_error", "⚠️ Automatická oprava zlyhala."))
                        else:
                            self.signals.log_message.emit(LanguageManager.get("uv_parse_error", "⚠️ Našli sa problémy, ale aplikácia ich nedokázala vyparsovať."))
                            for line in output_text.splitlines():
                                if line.strip(): self.signals.log_message.emit(line.strip())
                    else:
                        self.signals.log_message.emit(LanguageManager.get("uv_compatible", "✅ Všetky závislosti sú kompatibilné."))

                BirthCertificateGenerator.update_venv_certificate(self.venv_path)
            
            msg_all_updated = LanguageManager.get("msg_all_updated", "--- Všetko aktualizované ---")
            self.signals.log_message.emit(msg_all_updated)

        except Exception as e:
            msg_crit = LanguageManager.get("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e))
            self.signals.log_message.emit(msg_crit)
            self.success = False
        finally:
            self.signals.finished.emit()


class PipManager:
    _current_thread = None
    _current_worker = None

    @staticmethod
    def _run_pip_task(worker, log_widget):
        if PipManager._current_thread and PipManager._current_thread.is_alive():
            msg = LanguageManager.get("msg_busy", "!!! Už prebieha iná operácia, počkajte na jej dokončenie. !!!")
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
            
        start_msg = LanguageManager.get("msg_installing", "Inštalujem {0}...").format(package_name)
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
            
        start_msg = LanguageManager.get("msg_uninstalling", "Odinštalujem {0}...").format(package_name)
        worker = PipWorker(cmd, start_msg, venv_path, manager_type)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def _get_all_requirement_files(file_path, visited=None):
        """
        Rekurzívne nájde hlavný súbor requirements.txt aj všetky vnorené súbory (-r / --requirement).
        """
        if visited is None:
            visited = set()

        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path) or file_path in visited:
            return visited

        visited.add(file_path)
        base_dir = os.path.dirname(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("-r ") or line.startswith("--requirement "):
                        parts = line.split(maxsplit=1)
                        if len(parts) > 1:
                            nested_ref = parts[1].strip().strip("'\"")
                            nested_path = os.path.normpath(os.path.join(base_dir, nested_ref))
                            PipManager._get_all_requirement_files(nested_path, visited)
        except Exception:
            pass

        return visited

    @staticmethod
    def install_requirements(venv_path, project_root, log_widget, manager_type="pip"):
        req_path = Paths.get_requirements_txt_path(project_root)
        if not os.path.exists(req_path):
            msg = LanguageManager.get("err_req_not_found", "CHYBA: Súbor 'requirements.txt' nebol nájdený.")
            log_widget.append(msg)
            return

        # 1. Nájdi hlavný aj VŠETKY vnorené requirements súbory
        all_req_files = PipManager._get_all_requirement_files(req_path)

        # 2. Normalizuj lomítka vo všetkých nájdených súboroch na disku
        for file_path in all_req_files:
            PathNormalizer.sanitize_requirements_file(file_path)

        # 3. Získaj a spusti štandardný príkaz pre pip / uv (pip install -r ...)
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("install_requirements", project_root=project_root)
        except (ValueError, KeyError) as e:
            log_widget.append(f"CHYBA: {e}")
            return
            
        start_msg = LanguageManager.get("msg_installing_req", "Inštalujem z requirements.txt...")
        worker = PipWorker(cmd, start_msg, venv_path, manager_type)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def update_all_packages(venv_path, log_widget, manager_type="pip"):
        worker = UpdateAllWorker(venv_path, manager_type)
        PipManager._run_pip_task(worker, log_widget)
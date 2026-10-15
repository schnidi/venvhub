#----------------------------------------
# Súbor: core/logic/pip_manager.py
#----------------------------------------

import os
import json
import subprocess
import threading
import re
from PyQt6.QtCore import QObject, pyqtSignal

from core.logic.language_manager import LanguageManager
from core._path import Paths
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.path_normalizer import PathNormalizer


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
        self.success = False

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
                self.success = True
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
            for line in upgrade_process.stdout: self.signals.log_message.emit(line.strip())
            upgrade_process.wait()

            self.success = (upgrade_process.returncode == 0)

            if self.success:
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


class RequirementsInstallWorker:
    def __init__(self, venv_path, project_root, manager_type="pip", core=None):
        self.venv_path = venv_path
        self.project_root = project_root
        self.manager_type = manager_type
        self.core = core
        self.signals = PipSignalEmitter()
        self.success = False

        # Zabezpečenie cesty k súboru requirements.txt
        req_path = Paths.get_requirements_txt_path(self.project_root)
        python_exe = Paths.get_venv_python_exe_path(self.venv_path)

        # KĽÚČOVÉ PRE AptListener:
        # AptListener kontroluje worker.cmd na prítomnosť "install" a "-r".
        # Vďaka tomuto záznamu AptListener po úspechu automaticky spustí AptLogic.install_sync.
        self.cmd = [python_exe, "-m", "pip", "install", "-r", req_path]

    @staticmethod
    def _collect_full_install_specs(file_path: str, visited: set = None, base_dir: str = None, pip_e_root: str = "") -> list:
        """
        Zozbiera v pamäti RAM kompletné inštalačné špecifikácie balíčkov (vrátane [extras], verzií a -e).
        Nezahadzuje zátvorky [socks], aby pip/uv reálne nainštaloval aj podmienené závislosti.
        """
        if visited is None:
            visited = set()

        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path) or file_path in visited:
            return []

        visited.add(file_path)
        current_dir = os.path.dirname(file_path)
        if base_dir is None:
            base_dir = current_dir

        specs = []

        try:
            with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                content = f.read()
        except Exception:
            return []

        # Zlúčenie viacriadkových zápisov cez '\' a očistenie komentárov
        merged_lines = []
        lines_buffer = []
        for raw_line in content.splitlines():
            line_str = raw_line.strip()
            if not line_str or line_str.startswith("#"):
                continue

            line_no_comment = re.sub(r'[\t ]+#.*', '', line_str).strip()
            if not line_no_comment:
                continue

            if line_no_comment.endswith('\\'):
                lines_buffer.append(line_no_comment[:-1].strip())
            else:
                lines_buffer.append(line_no_comment)
                merged_lines.append(' '.join(lines_buffer).strip())
                lines_buffer = []

        if lines_buffer:
            merged_lines.append(' '.join(lines_buffer).strip())

        for line in merged_lines:
            if not line or line.startswith("#"):
                continue

            # 1. Rekurzia: -r alebo --requirement
            req_match = re.match(r'^(?:-r[\s=]+|--requirement[\s=]+|-r(?=[./\\]))(.+)$', line)
            if req_match:
                raw_nested = req_match.group(1).strip().strip('\'"')
                if raw_nested.startswith(('http://', 'https://')):
                    continue
                nested_path = os.path.normpath(os.path.join(current_dir, raw_nested))
                if os.path.exists(nested_path):
                    specs.extend(RequirementsInstallWorker._collect_full_install_specs(nested_path, visited, base_dir, pip_e_root))
                continue

            # 2. Ignorovanie globálnych prepínačov inštalátora
            if line.startswith(('-f', '--find-links', '-i', '--index-url', '--extra-index-url', '--no-index', '-c', '--constraint')):
                continue

            # 3. Ošetrenie -e / --editable
            editable_match = re.match(r'^(?:-e\s+|--editable[\s=]+)(.+)$', line)
            if editable_match:
                raw_target = editable_match.group(1).strip().strip('\'"')
                if raw_target.startswith(('http://', 'https://', 'git+', 'git@', 'svn+', 'hg+')):
                    specs.append(['-e', raw_target])
                    continue

                target_dir = raw_target
                if os.path.isdir(os.path.normpath(raw_target)):
                    target_dir = os.path.normpath(raw_target)
                elif os.path.isdir(os.path.normpath(os.path.join(current_dir, raw_target))):
                    target_dir = os.path.normpath(os.path.join(current_dir, raw_target))
                elif os.path.isdir(os.path.normpath(os.path.join(base_dir, raw_target))):
                    target_dir = os.path.normpath(os.path.join(base_dir, raw_target))
                elif pip_e_root:
                    cand = os.path.normpath(os.path.join(pip_e_root, os.path.basename(raw_target.rstrip('/\\'))))
                    if os.path.isdir(cand):
                        target_dir = cand

                safe_path = PathNormalizer.to_safe_pip_path(target_dir)
                specs.append(['-e', safe_path])
            else:
                # Plná špecifikácia balíčka pre pip/uv (napr. 'requests[socks]', 'flask==2.3.0')
                specs.append(line)

        return specs

    def run(self):
        req_path = Paths.get_requirements_txt_path(self.project_root)
        if not os.path.exists(req_path):
            msg = LanguageManager.get("err_req_not_found", "CHYBA: Súbor 'requirements.txt' nebol nájdený.")
            self.signals.log_message.emit(msg)
            self.success = False
            self.signals.finished.emit()
            return

        # 1. Získanie pip_e_root
        pip_e_root = getattr(self.core, 'pip_e_packages_root', '') if self.core else ''
        if not pip_e_root:
            try:
                cfg_path = Paths.get_config_file_path()
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        pip_e_root = json.load(f).get("pip_e_packages_root", "")
            except Exception:
                pass

        # 2. Zozbieranie plných inštalačných špecifikácií do pamäte RAM
        items = self._collect_full_install_specs(req_path, pip_e_root=pip_e_root)

        if not items:
            self.signals.log_message.emit(LanguageManager.get("msg_req_empty", "Žiadne balíčky na inštaláciu."))
            self.success = True
            self.signals.finished.emit()
            return

        # 3. Dávkovanie (chunking) po 30 položkách
        CHUNK_SIZE = 30
        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.venv_path)

        total_chunks = (len(items) + CHUNK_SIZE - 1) // CHUNK_SIZE
        total_installed_ok = True

        for c_idx in range(0, len(items), CHUNK_SIZE):
            chunk_items = items[c_idx:c_idx + CHUNK_SIZE]
            
            chunk_args = []
            for itm in chunk_items:
                if isinstance(itm, list):
                    chunk_args.extend(itm)
                else:
                    chunk_args.append(itm)

            chunk_num = (c_idx // CHUNK_SIZE) + 1
            if total_chunks > 1:
                self.signals.log_message.emit(f"\n--- Inštalujem dávku {chunk_num}/{total_chunks} ({len(chunk_items)} balíčkov) ---")
            else:
                self.signals.log_message.emit(f"\n--- Inštalujem balíčky z requirements.txt ({len(chunk_items)} balíčkov) ---")

            cmd = dispatcher.get("install_multiple_exact", packages=chunk_args)

            try:
                process = subprocess.Popen(
                    cmd,
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

                if process.returncode != 0:
                    total_installed_ok = False
                    self.signals.log_message.emit(f"❌ Dávka {chunk_num} zlyhala s kódom {process.returncode}")
                    break
            except Exception as e:
                total_installed_ok = False
                self.signals.log_message.emit(f"❌ Kritická chyba procesu: {e}")
                break

        # 4. Dokončenie a verifikácia inštalácie
        if total_installed_ok:
            self.success = True

            if self.manager_type == "uv":
                self.signals.log_message.emit(LanguageManager.get("uv_checking_deps", "--- Vykonávam UV kontrolu závislostí... ---"))
                cmd_check = dispatcher.get("check")
                check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                if check_proc.returncode == 0:
                    self.signals.log_message.emit(LanguageManager.get("uv_compatible", "✅ Všetky závislosti sú kompatibilné."))

            BirthCertificateGenerator.update_venv_certificate(self.venv_path)

            msg_done = LanguageManager.get("msg_done", "--- HOTOVO ---")
            self.signals.log_message.emit(msg_done)
        else:
            self.success = False
            self.signals.log_message.emit("⚠️ Inštalácia požiadaviek nebola úspešná, APT stav ostáva nezmenený.")

        # Vystrelenie signálu: AptListener na základe self.cmd rozpozná úspešnú inštaláciu a spustí AptLogic.install_sync
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
        if visited is None:
            visited = set()

        file_path = os.path.abspath(file_path)
        if not os.path.exists(file_path) or file_path in visited:
            return visited

        visited.add(file_path)
        base_dir = os.path.dirname(file_path)

        try:
            with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("-r ") or line.startswith("--requirement ") or line.startswith("-r\t"):
                        parts = line.split(maxsplit=1)
                        if len(parts) > 1:
                            nested_ref = parts[1].strip().strip("'\"")
                            nested_path = os.path.normpath(os.path.join(base_dir, nested_ref))
                            PipManager._get_all_requirement_files(nested_path, visited)
        except Exception:
            pass

        return visited

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
    def update_all_packages(venv_path, log_widget, manager_type="pip"):
        worker = UpdateAllWorker(venv_path, manager_type)
        PipManager._run_pip_task(worker, log_widget)
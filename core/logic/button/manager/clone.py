#----------------------------------------
# Súbor: core/logic/button/manager/clone.py
#----------------------------------------

import os
import re
import subprocess
import datetime
import json
import shutil
from PyQt6.QtCore import QObject, pyqtSignal, QThread, Qt
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from core._path import Paths
from windows.progress_dialog import ProgressDialog
from core.logic.language_manager import LanguageManager
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.sanitize_venv_name import sanitize_venv_name

# Využívame centrálneho dispečera namiesto manuálneho skladania príkazov
from core.logic.commands.command_factory import PackageManagerFactory

# --- NAŠE NOVÉ SLUŽBY ---
from core.logic.sluzby.log_print_desktop import DesktopLogger
from core.logic.sluzby.embed_python_created import EmbedPythonCreated

# --- NEZÁVISLÝ PREPÍNAČ PRE LOGOVANIE (Iba pre clone.py) ---
LOGGING_ENABLED = False
clone_logger = DesktopLogger(is_enabled=LOGGING_ENABLED, filename="VENV_CLONE_LOG.txt")


class CloneWorker(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress_msg = pyqtSignal(str)

    def __init__(self, source_venv_path, target_venv_path, is_embed, parent_python, project_name, manager_type="pip", local_packages_root=""):
        super().__init__()
        self.source_venv_path = source_venv_path
        self.target_venv_path = target_venv_path
        self.is_embed = is_embed
        self.parent_python = parent_python
        self.project_name = project_name
        self.manager_type = manager_type
        self.local_packages_root = local_packages_root

    def _stream_subprocess(self, cmd, task_name):
        """Spustí proces a číta jeho výstup riadok po riadku bez sekania GUI."""
        clone_logger.write(f"\n--- ŠTART: {task_name} ---")
        clone_logger.write(f"Príkaz: {' '.join(cmd)}")
        
        env = os.environ.copy()
        env["PIP_PROGRESS_BAR"] = "off"
        env["UV_NO_PROGRESS"] = "1"
        
        try:
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                creationflags=0x08000000,
                encoding='utf-8',
                errors='replace',
                env=env
            )
        except FileNotFoundError:
            err_msg = f"Kritická chyba: Spúšťací súbor alebo inštalátor neexistuje -> {cmd[0]}"
            clone_logger.write(err_msg)
            return 1, err_msg
        except Exception as e:
            err_msg = f"Neznáma chyba pri štarte procesu: {e}"
            clone_logger.write(err_msg)
            return 1, err_msg
            
        output_history = []
        for line in iter(process.stdout.readline, ''):
            clean_line = line.strip()
            if clean_line:
                clone_logger.write(f"[{task_name}] {clean_line}")
                self.progress_msg.emit(clean_line)
                output_history.append(clean_line)
                
        process.stdout.close()
        process.wait()
        
        clone_logger.write(f"--- KONIEC: {task_name} (Návratový kód: {process.returncode}) ---")
        return process.returncode, "\n".join(output_history)
        
    def _clone_local_packages(self):
        """Kopíruje VenvHub Import Hooky pre lokálne balíčky a stav APT do nového Venvu."""
        site_folder = "Lib" if os.name == 'nt' else "lib"
        source_site = os.path.join(self.source_venv_path, site_folder, "site-packages")
        target_site = os.path.join(self.target_venv_path, site_folder, "site-packages")
        
        files_to_copy = [
            "venvhub.json", 
            "venvhub_bootstrap.py", 
            "venvhub_bootstrap.pth",
            "venvhub_apt_state.json"  # Prenos APT stavu a explicitných balíčkov
        ]
        
        has_local = False
        has_apt = False
        os.makedirs(target_site, exist_ok=True)
        
        for file_name in files_to_copy:
            src_f = os.path.join(source_site, file_name)
            dst_f = os.path.join(target_site, file_name)
            if os.path.exists(src_f):
                try:
                    shutil.copy2(src_f, dst_f)
                    if file_name == "venvhub_apt_state.json":
                        has_apt = True
                    else:
                        has_local = True
                except Exception as e:
                    clone_logger.write(f"Nepodarilo sa skopírovať {file_name}: {e}")
                    
        if has_local:
            msg_local = LanguageManager.get("clone_local_pkgs_transferred", "🔗 Lokálne balíčky (VenvHub Hook) boli úspešne prenesené.")
            self.progress_msg.emit(msg_local)
            
        if has_apt:
            msg_apt = LanguageManager.get("clone_apt_state_transferred", "🧠 APT história a pravidlá závislostí boli úspešne prenesené.")
            self.progress_msg.emit(msg_apt)

    def run(self):
        try:
            CREATE_NO_WINDOW = 0x08000000
            clone_logger.write("\n" + "="*80)
            clone_logger.write(f"ZACIATOK KLONOVANIA: {self.source_venv_path} -> {self.target_venv_path}")
            clone_logger.write(f"Režim Embed: {self.is_embed}")

            source_python = Paths.get_venv_python_exe_path(self.source_venv_path)

            # 1. Získanie zoznamu balíčkov pôvodného prostredia
            self.progress_msg.emit(LanguageManager.get("clone_getting_pkgs", "Získavam zoznam balíčkov (freeze)..."))
            
            source_dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.source_venv_path)
            freeze_cmd = source_dispatcher.get("freeze")
                
            try:
                freeze_proc = subprocess.run(freeze_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=30)
            except FileNotFoundError:
                raise Exception(f"Inštalátor pre '{self.manager_type}' nebol vo vašom systéme nájdený!")
            except subprocess.TimeoutExpired:
                raise Exception("Príkaz freeze neodpovedal v časovom limite (30s)!")

            if freeze_proc.returncode != 0:
                err_msg = LanguageManager.get("clone_err_freeze", "Chyba pri 'freeze': {0}").format(freeze_proc.stderr)
                raise Exception(err_msg)

            filtered_reqs = []
            editable_reqs = []
            
            for line in freeze_proc.stdout.splitlines():
                clean_line = line.strip()
                if not clean_line: continue
                
                if clean_line.startswith("-e "):
                    path_part = clean_line[3:].strip()
                    editable_reqs.append(path_part)
                    clone_logger.write(f"Extrahujem editable balíček pre bezpečnú inštaláciu: {path_part}")
                else:
                    filtered_reqs.append(clean_line)
                    
            requirements_data = "\n".join(filtered_reqs)
            clone_logger.write(f"Filtrované balíčky pre inštaláciu:\n{requirements_data}")

            fmt_creating = LanguageManager.get("clone_creating_venv", "Vytváram nové prostredie: {0}...")
            self.progress_msg.emit(fmt_creating.format(os.path.basename(self.target_venv_path)))
            
            # 2. Vytvorenie nového prostredia
            if self.is_embed:
                if self.parent_python and os.path.exists(self.parent_python):
                    self.progress_msg.emit(LanguageManager.get("clone_plan_a", "Používam rýchle klonovanie (rodičovský Python)..."))
                    create_cmd = [self.parent_python, "-m", "virtualenv", "--no-download", self.target_venv_path]
                else:
                    self.progress_msg.emit(LanguageManager.get("clone_plan_b", "Pripravujem staré prostredie (inštalujem virtualenv)..."))
                    inject_cmd = [source_python, "-m", "pip", "install", "virtualenv"]
                    ret_code, _ = self._stream_subprocess(inject_cmd, "INJECT_VIRTUALENV")
                    if ret_code != 0:
                        raise Exception("Nepodarilo sa nainštalovať 'virtualenv' do zdrojového prostredia.")
                    
                    self.progress_msg.emit("Vytváram klon (záložná metóda)...")
                    create_cmd = [source_python, "-m", "virtualenv", "--no-download", self.target_venv_path]

                ret_code, err_txt = self._stream_subprocess(create_cmd, "CREATE_VENV_EMBED")
                if ret_code != 0:
                    raise Exception(LanguageManager.get("clone_err_create_embed", "Chyba pri vytváraní venv (virtualenv):\n{0}").format(err_txt))

                self.progress_msg.emit(LanguageManager.get("clone_fixing_pth", "Opravujem konfiguráciu (._pth)..."))
                # OPRAVA: Použitie spoločnej služby pre opravu cesty
                EmbedPythonCreated.fix_pth_file(self.target_venv_path, source_python)
                
                self.progress_msg.emit(LanguageManager.get("clone_verifying_pip", "Overujem funkčnosť PIP..."))
                # OPRAVA: Použitie spoločnej služby pre verifikáciu
                if not EmbedPythonCreated.verify_pip_functional(self.target_venv_path):
                     raise Exception(LanguageManager.get("clone_err_pip_verify", "PIP v novom prostredí nefunguje!"))

            else:
                self.progress_msg.emit(LanguageManager.get("clone_creating_system", "Vytváram venv (metóda pre systémový Python)..."))
                create_cmd = [source_python, "-m", "venv", self.target_venv_path]
                ret_code, err_txt = self._stream_subprocess(create_cmd, "CREATE_VENV_SYSTEM")
                if ret_code != 0:
                    raise Exception(LanguageManager.get("clone_err_create_system", "Chyba pri vytváraní venv:\n{0}").format(err_txt))

            # 3. Inštalácia ŠTANDARDNÝCH balíčkov do nového prostredia
            target_python = Paths.get_venv_python_exe_path(self.target_venv_path)
            target_dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.target_venv_path)
            
            if requirements_data.strip():
                self.progress_msg.emit(LanguageManager.get("clone_installing_pkgs", "\n--- SŤAHUJEM A INŠTALUJEM BALÍČKY (čakajte prosím) ---"))

                temp_req_path = os.path.join(self.target_venv_path, "clone_reqs.txt")
                with open(temp_req_path, "w", encoding="utf-8") as f:
                    f.write(requirements_data)

                if self.is_embed:
                    self.progress_msg.emit("🛠 Zabezpečujem build nástroje (setuptools, wheel)...")
                    build_tools_cmd = target_dispatcher.get("install_multiple_exact", packages=["setuptools", "wheel"])
                    ret_code, err_txt = self._stream_subprocess(build_tools_cmd, "INSTALL_BUILD_TOOLS")

                install_cmd = target_dispatcher.get("install_req_file", file_path=temp_req_path)
                ret_code, err_txt = self._stream_subprocess(install_cmd, "INSTALL_REQUIREMENTS")

                if os.path.exists(temp_req_path):
                    try: os.remove(temp_req_path)
                    except: pass

                if ret_code != 0:
                    short_err = err_txt[-1500:] if len(err_txt) > 1500 else err_txt
                    raise Exception(LanguageManager.get("clone_err_install", "Chyba pri inštalácii balíčkov:\n{0}").format(short_err))

            # 3.5: Inštalácia EDITOVATEĽNÝCH balíčkov (pip -e)
            if editable_reqs:
                self.progress_msg.emit("Inštalujem editovateľné balíčky (pip -e)...")
                for req_path in editable_reqs:
                    cmd_e = target_dispatcher.get("install_editable", path=req_path)
                    ret_code, err_txt = self._stream_subprocess(cmd_e, f"INSTALL_EDITABLE: {req_path}")
                    if ret_code != 0:
                        self.progress_msg.emit(f"⚠️ Upozornenie: Nepodarilo sa prelinkovať {req_path}")

            # 4. Prenos VenvHub lokálnych balíčkov (Import Hook)
            self._clone_local_packages()

            # 5. Zápis finálneho rodného listu pre novovytvorený klon
            self.progress_msg.emit(LanguageManager.get("clone_finalizing", "\nZapisujem rodný list prostredia..."))
            
            source_path_for_json = None
            if self.is_embed:
                cert_path = os.path.join(self.source_venv_path, "venv_birth_certificate.json")
                if os.path.exists(cert_path):
                    try:
                        with open(cert_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            source_path_for_json = data.get("source_python_path")
                    except Exception:
                        pass
            
            BirthCertificateGenerator.create_venv_certificate(
                project_name=self.project_name, 
                venv_name=os.path.basename(self.target_venv_path),
                venv_path=self.target_venv_path, 
                python_exe=target_python,
                source_python_path=source_path_for_json 
            )
            BirthCertificateGenerator.update_venv_certificate(self.target_venv_path)

            self.progress_msg.emit("✅ Klonovanie úspešne dokončené!")
            clone_logger.write("--- KLONOVANIE ÚSPEŠNE DOKONČENÉ ---")
            self.finished.emit()

        except Exception as e:
            clone_logger.write(f"KRITICKÁ CHYBA: {str(e)}")
            self.error.emit(str(e))


class CloneHandler:
    _thread = None
    _worker = None

    @staticmethod
    def _analyze_source(source_venv_path):
        parent_python = None
        cert_path = os.path.join(source_venv_path, "venv_birth_certificate.json")
        if os.path.exists(cert_path):
            try:
                with open(cert_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sp = data.get("source_python_path")
                    if sp:
                        if sp.startswith("[REL_TO_APP]"):
                            rel_part = sp.replace("[REL_TO_APP]/", "")
                            parent_python = os.path.normpath(os.path.join(Paths.get_app_root_path(), rel_part))
                        else:
                            parent_python = os.path.normpath(sp)
            except Exception:
                pass

        pyvenv_cfg_path = os.path.join(source_venv_path, "pyvenv.cfg")
        if not parent_python and os.path.exists(pyvenv_cfg_path):
            try:
                with open(pyvenv_cfg_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("home ="):
                            home_dir = line.split("=")[1].strip()
                            parent_python = os.path.normpath(os.path.join(home_dir, "python.exe"))
                            break
            except Exception:
                pass

        if parent_python:
            expected_runtimes_dir = os.path.normpath(Paths.get_python_runtimes_install_dir()).lower()
            parent_dir = os.path.normpath(os.path.dirname(parent_python)).lower()
            if expected_runtimes_dir in parent_dir:
                return True, parent_python

        if os.path.exists(pyvenv_cfg_path):
            try:
                with open(pyvenv_cfg_path, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                    if "virtualenv" in content:
                        return True, parent_python
            except Exception:
                pass

        return False, parent_python

    @staticmethod
    def run(parent, core, source_venv_path):
        if not source_venv_path or not os.path.exists(source_venv_path):
            return

        venv_name = os.path.basename(source_venv_path)
        prefix = f"{core.active_project}_"
        clean_name = venv_name[len(prefix):] if venv_name.startswith(prefix) else venv_name

        now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        default_new_name = f"{clean_name}_backup_{now}"

        title = LanguageManager.get("clone_dialog_title", "Klonovať / Zálohovať Venv")
        label = LanguageManager.get("clone_dialog_label", "Zadajte názov pre kópiu prostredia '{0}':").format(clean_name)
        
        new_name, ok = QInputDialog.getText(parent, title, label, text=default_new_name)

        raw_new_name = new_name.strip()
        if not ok or not raw_new_name:
            return

        safe_new_name = sanitize_venv_name(raw_new_name)
        full_new_folder_name = f"{core.active_project}_{safe_new_name}"
        target_path = Paths.get_venv_path(core.venv_hub_root, full_new_folder_name)

        if os.path.exists(target_path):
            err_title = LanguageManager.get("title_error", "Chyba")
            err_msg = LanguageManager.get("msg_venv_exists", "Prostredie '{0}' už existuje!").format(full_new_folder_name)
            QMessageBox.warning(parent, err_title, err_msg)
            return

        is_embed, parent_python = CloneHandler._analyze_source(source_venv_path)

        progress = ProgressDialog(parent)
        progress.add_log_message(LanguageManager.get("clone_preparing", "Pripravujem klonovanie..."))
        
        CloneHandler._thread = QThread()
        CloneHandler._worker = CloneWorker(
            source_venv_path, 
            target_path, 
            is_embed, 
            parent_python, 
            core.active_project,
            getattr(core, 'package_manager', 'pip'),
            getattr(core, 'local_packages_root', '')
        )
        CloneHandler._worker.moveToThread(CloneHandler._thread)

        CloneHandler._thread.started.connect(CloneHandler._worker.run)
        CloneHandler._worker.progress_msg.connect(progress.add_log_message) 
        
        def on_error(err):
            progress.accept()
            err_title = LanguageManager.get("clone_err_title", "Chyba klonovania")
            err_msg = LanguageManager.get("clone_err_generic", "Nastala chyba:\n{0}").format(err)
            QMessageBox.critical(parent, err_title, err_msg)

        CloneHandler._worker.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
        
        CloneHandler._worker.finished.connect(CloneHandler._thread.quit)
        CloneHandler._worker.finished.connect(CloneHandler._worker.deleteLater)
        CloneHandler._worker.error.connect(CloneHandler._thread.quit)
        CloneHandler._worker.error.connect(CloneHandler._worker.deleteLater)
        CloneHandler._thread.finished.connect(CloneHandler._thread.deleteLater)
        
        CloneHandler._worker.finished.connect(progress.accept)
        CloneHandler._worker.finished.connect(parent.refresh_table)

        CloneHandler._thread.start()
        progress.exec()
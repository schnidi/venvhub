#----------------------------------------
# Súbor: core/logic/system_listener.py
#----------------------------------------

import os
import json
import socket
import re
import threading
from datetime import datetime

from core._path import Paths
from core.logic.language_manager import LanguageManager

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox


def normalize_venv_name(path_or_name):
    """
    Robustne očistí a zjednotí názov priečinka venvu pre bezpečné porovnanie na Windows.
    Rieši: medzery, veľké/malé písmená, opačné lomky a rozdiely v kódovaní diakritiky.
    """
    if not path_or_name:
        return ""
    
    val = str(path_or_name).strip()
    val = os.path.basename(os.path.normpath(val))
    
    import unicodedata
    val = unicodedata.normalize('NFC', val)
    
    return val.strip().casefold()


# --- Cache pre machine_id ---
_MACHINE_ID_CACHE = None
_MACHINE_ID_LOCK = threading.Lock()

def get_machine_id():
    """
    Zistí hardvérový podpis jadra PC a zahashuje ho cez SHA-256.
    Výsledok sa cachuje v pamäti (_MACHINE_ID_CACHE).
    """
    global _MACHINE_ID_CACHE
    with _MACHINE_ID_LOCK:
        if _MACHINE_ID_CACHE is not None:
            return _MACHINE_ID_CACHE

        import hashlib
        hostname = socket.gethostname()
        hardware_guid = "UNKNOWN_HARDWARE"

        if os.name == 'nt':
            import winreg
            try:
                reg_path = r"SYSTEM\CurrentControlSet\Control\SystemInformation"
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                    hardware_guid, _ = winreg.QueryValueEx(key, "ComputerHardwareId")
            except Exception:
                pass

        raw_signature = f"{hostname}_{hardware_guid}"
        scrambled_hash = hashlib.sha256(raw_signature.encode('utf-8')).hexdigest()
        _MACHINE_ID_CACHE = scrambled_hash
        return _MACHINE_ID_CACHE


def is_portable_mode():
    return os.path.exists(os.path.join(Paths.get_app_root_path(), Paths.PORTABLE_MARKER_FILENAME))


def is_system_venv(venv_path):
    if not venv_path: 
        return False
    cfg_path = os.path.join(venv_path, "pyvenv.cfg")
    if not os.path.exists(cfg_path): 
        return False
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            content = f.read().lower()
        return "virtualenv" not in content
    except Exception:
        return False


def get_embedinstall_config_path():
    """Vráti cestu k novému súboru, ktorý leží presne vedľa hlavného configu."""
    base_dir = os.path.dirname(Paths.get_config_file_path())
    return os.path.join(base_dir, "portable_system_py.json")


# =====================================================================
# --- IN-MEMORY CACHE + ATOMICKÝ ZÁPIS PRE portable_system_py.json ---
# =====================================================================

_CONFIG_CACHE = None
_CONFIG_CACHE_LOCK = threading.Lock()

def _log_config_error(action, error):
    try:
        msg = f"[SystemListener] CHYBA pri '{action}' portable_system_py.json: {error}"
        print(msg)
        base_dir = os.path.dirname(get_embedinstall_config_path())
        log_path = os.path.join(base_dir, "system_listener_errors.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


def _load_config_cache():
    global _CONFIG_CACHE
    with _CONFIG_CACHE_LOCK:
        if _CONFIG_CACHE is None:
            config_path = get_embedinstall_config_path()
            try:
                if os.path.exists(config_path):
                    with open(config_path, 'r', encoding='utf-8') as f:
                        _CONFIG_CACHE = json.load(f)
                else:
                    _CONFIG_CACHE = {}
            except Exception as e:
                _log_config_error("čítanie (read)", e)
                _CONFIG_CACHE = {}
        return _CONFIG_CACHE


def _save_config_cache(cfg):
    global _CONFIG_CACHE
    config_path = get_embedinstall_config_path()
    tmp_path = config_path + ".tmp"

    with _CONFIG_CACHE_LOCK:
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, config_path)

        except Exception as e:
            _log_config_error("zápis (write)", e)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return

        _CONFIG_CACHE = cfg


def _preload_cache_async():
    def _worker():
        try:
            if is_portable_mode():
                _load_config_cache()
                get_machine_id()
        except Exception as e:
            _log_config_error("predhriatie cache (preload)", e)

    threading.Thread(target=_worker, daemon=True).start()


# =====================================================================
# --- BEZPEČNOSTNÉ KONTROLY & DIALOGY ---
# =====================================================================

def verify_access(venv_path):
    """
    Kľúčová kontrola: 
    Vráti True -> Pusti akciu
    Vráti False -> Zastav akciu (Je to Systémový Venv vytvorený v Portable na cudzom PC)
    """
    if not venv_path: 
        return True
    if not is_portable_mode(): 
        return True
    if not is_system_venv(venv_path): 
        return True
    
    venv_name = normalize_venv_name(venv_path)
    if not venv_name: 
        return True
    
    try:
        cfg = _load_config_cache()
        allowed_pc = cfg.get(venv_name)
        current_pc = get_machine_id()
        
        if allowed_pc and allowed_pc != current_pc:
            return False
    except Exception:
        pass
    return True


def show_blocked_warning(venv_name=""):
    title = LanguageManager.get("portability_protection_title", "Ochrana prenosnosti: Prístup zablokovaný")
    
    default_text = (
        f"Prostredie '{venv_name}' bolo vytvorené pomocou Systémového Pythonu na INOM počítači!\n\n"
        "Z dôvodu nekompatibility systémových ciest a C-knižníc je na tomto PC ZAKÁZANÉ "
        "ho spúšťať, klonovať, otvárať v ňom balíčky alebo ho spúšťať v skupine.\n\n"
        "Keď prenesiete USB kľúč späť na pôvodný PC, okamžite sa odomkne a bude fungovať.\n"
        "(Embed prostredia fungujú všade, toto platí len pre systémové)."
    )
    
    raw_text = LanguageManager.get("portability_protection_text", default_text)
    try:
        formatted_text = raw_text.format(venv_name=venv_name)
    except Exception:
        formatted_text = raw_text
        
    # --- ZMENA NA NAŠU LIŠTU ---
    CustomMessageBox.critical(None, title, formatted_text)


# =====================================================================
# --- HLAVNÁ TRIEDA SYSTEM LISTENER ---
# =====================================================================

class SystemListener:
    
    @staticmethod
    def start_listening():
        _preload_cache_async()

        from core.logic.button.manager.actions import ActionHandler
        from core.logic.button.manager.clone import CloneHandler
        from core.logic.vscode_user.start_vs_code_user import VSCodeLauncher
        from core.logic.birth_certificate import BirthCertificateGenerator
        from core.logic.containers.button.autostart_actions import AutostartActionHandler
        from windows.manager import MasterManager

        # ==========================================
        # 1. NAČÚVANIE SINGLE PLAY
        # ==========================================
        orig_term = ActionHandler.start_terminal_process
        orig_silent = ActionHandler.start_silent_process
        orig_open_term = ActionHandler.open_terminal_only

        @staticmethod
        def patched_term(project_path, venv_path, script_to_run):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                return
            orig_term(project_path, venv_path, script_to_run)

        @staticmethod
        def patched_silent(project_path, venv_path, script_to_run):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                return
            orig_silent(project_path, venv_path, script_to_run)

        @staticmethod
        def patched_open_term(project_path, venv_path):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                return
            orig_open_term(project_path, venv_path)

        ActionHandler.start_terminal_process = patched_term
        ActionHandler.start_silent_process = patched_silent
        ActionHandler.open_terminal_only = patched_open_term

        # ==========================================
        # 2. NAČÚVANIE MULTI PLAY
        # ==========================================
        orig_start_group = AutostartActionHandler.start_group
        @staticmethod
        def patched_start_group(core, group_name, log_callback=None):
            members = core.multi_groups.get(group_name, [])
            for m in members:
                venv_path = m.get("venv_path")
                if venv_path and not verify_access(venv_path):
                    v_name = os.path.basename(venv_path)
                    show_blocked_warning(v_name)
                    if log_callback:
                        default_msg = f"🛑 FATAL: Štart skupiny zablokovaný! Venv '{v_name}' patrí inému PC."
                        raw_msg = LanguageManager.get("group_start_blocked_log", default_msg)
                        try:
                            formatted_msg = raw_msg.format(venv_name=v_name)
                        except Exception:
                            formatted_msg = raw_msg
                        log_callback(formatted_msg)
                    return 
            orig_start_group(core, group_name, log_callback)
        AutostartActionHandler.start_group = patched_start_group

        # ==========================================
        # 3. NAČÚVANIE KLONOVANIA (Clone)
        # ==========================================
        orig_clone = CloneHandler.run
        @staticmethod
        def patched_clone(parent, core, source_venv_path):
            if not verify_access(source_venv_path):
                show_blocked_warning(os.path.basename(source_venv_path))
                return
            orig_clone(parent, core, source_venv_path)
        CloneHandler.run = patched_clone

        # ==========================================
        # 4. NAČÚVANIE SPUSTENIA VS CODE
        # ==========================================
        orig_vscode = VSCodeLauncher.launch
        @staticmethod
        def patched_vscode(core, project_path, venv_path):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                blocked_msg = LanguageManager.get("blocked_by_portability", "Zablokované ochranou prenosnosti.")
                return False, blocked_msg
            return orig_vscode(core, project_path, venv_path)
        VSCodeLauncher.launch = patched_vscode

        # ==========================================
        # 5. NAČÚVANIE PIP MANAŽÉROV A LOKÁLNYCH BALÍČKOV
        # ==========================================
        orig_open_pip = MasterManager.open_pip_manager
        def patched_open_pip(self):
            if not verify_access(self.selected_venv_path):
                show_blocked_warning(os.path.basename(self.selected_venv_path))
                return
            orig_open_pip(self)
        MasterManager.open_pip_manager = patched_open_pip

        orig_open_local = MasterManager.open_local_packages_window
        def patched_open_local(self):
            if not verify_access(self.selected_venv_path):
                show_blocked_warning(os.path.basename(self.selected_venv_path))
                return
            orig_open_local(self)
        MasterManager.open_local_packages_window = patched_open_local

        orig_open_pipe = MasterManager.open_pip_e_window
        def patched_open_pipe(self):
            if not verify_access(self.selected_venv_path):
                show_blocked_warning(os.path.basename(self.selected_venv_path))
                return
            orig_open_pipe(self)
        MasterManager.open_pip_e_window = patched_open_pipe

        # ==========================================
        # 6. ZÁPIS DO NOVÉHO SÚBORU (Pri vytvorení Venvu)
        # ==========================================
        orig_create_cert = BirthCertificateGenerator.create_venv_certificate
        
        @staticmethod
        def patched_create_cert(project_name, venv_name, venv_path, python_exe, source_python_path=None):
            res = orig_create_cert(project_name, venv_name, venv_path, python_exe, source_python_path)
            
            is_system = False
            if source_python_path:
                is_system = "[REL_TO_APP]" not in source_python_path
            else:
                is_system = is_system_venv(venv_path)

            if is_portable_mode() and is_system:
                cfg = dict(_load_config_cache())
                norm_name = normalize_venv_name(venv_path)
                if norm_name:
                    cfg[norm_name] = get_machine_id()
                
                threading.Thread(target=_save_config_cache, args=(cfg,), daemon=True).start()
                    
            return res

        BirthCertificateGenerator.create_venv_certificate = patched_create_cert

        # ==========================================
        # 7. ZÁKAZ PREPISOVANIA PRE SYSTÉMOVÝ PYTHON V PORTABLE
        # ==========================================
        from core.logic.path_logic.portable import PortablePathLogic
        orig_repair = PortablePathLogic.check_and_repair_venv_if_needed

        @staticmethod
        def patched_repair(venv_path, local_packages_root=""):
            if not venv_path: 
                return

            if is_portable_mode() and is_system_venv(venv_path):
                return

            orig_repair(venv_path, local_packages_root)

        PortablePathLogic.check_and_repair_venv_if_needed = patched_repair

        # ==========================================
        # 8. NAČÚVANIE PRIAMYCH PIP OPERÁCIÍ, FREEZE A MAZANIA
        # ==========================================
        from core.logic.pip_manager import PipManager
        from core.logic.button.pip.freeze import FreezeHandler
        from core.logic.button.manager.delete import DeleteHandler

        orig_pip_install = PipManager.install_package
        @staticmethod
        def patched_pip_install(venv_path, package_name, log_widget, manager_type="pip"):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                if hasattr(log_widget, 'append'):
                    msg = LanguageManager.get("blocked_portability_system_venv", "🛑 Zablokované: Ochrana prenosnosti (Systémový Venv).")
                    log_widget.append(msg)
                return
            orig_pip_install(venv_path, package_name, log_widget, manager_type)
        PipManager.install_package = patched_pip_install

        orig_pip_uninstall = PipManager.uninstall_package
        @staticmethod
        def patched_pip_uninstall(venv_path, package_name, log_widget, manager_type="pip"):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                if hasattr(log_widget, 'append'):
                    msg = LanguageManager.get("blocked_portability_system_venv", "🛑 Zablokované: Ochrana prenosnosti (Systémový Venv).")
                    log_widget.append(msg)
                return
            orig_pip_uninstall(venv_path, package_name, log_widget, manager_type)
        PipManager.uninstall_package = patched_pip_uninstall

        orig_pip_reqs = PipManager.install_requirements
        @staticmethod
        def patched_pip_reqs(venv_path, project_root, log_widget, manager_type="pip"):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                if hasattr(log_widget, 'append'):
                    msg = LanguageManager.get("blocked_portability_system_venv", "🛑 Zablokované: Ochrana prenosnosti (Systémový Venv).")
                    log_widget.append(msg)
                return
            orig_pip_reqs(venv_path, project_root, log_widget, manager_type)
        PipManager.install_requirements = patched_pip_reqs

        orig_pip_update_all = PipManager.update_all_packages
        @staticmethod
        def patched_pip_update_all(venv_path, log_widget, manager_type="pip"):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                if hasattr(log_widget, 'append'):
                    msg = LanguageManager.get("blocked_portability_system_venv", "🛑 Zablokované: Ochrana prenosnosti (Systémový Venv).")
                    log_widget.append(msg)
                return
            orig_pip_update_all(venv_path, log_widget, manager_type)
        PipManager.update_all_packages = patched_pip_update_all

        orig_freeze = FreezeHandler.run
        @staticmethod
        def patched_freeze(venv_path, project_root, manager_type="pip", log_callback=None):
            if not verify_access(venv_path):
                show_blocked_warning(os.path.basename(venv_path))
                if log_callback:
                    msg = LanguageManager.get("blocked_portability_system_venv", "🛑 Zablokované: Ochrana prenosnosti (Systémový Venv).")
                    log_callback(msg)
                return False
            return orig_freeze(venv_path, project_root, manager_type, log_callback)
        FreezeHandler.run = patched_freeze
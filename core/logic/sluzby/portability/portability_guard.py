#----------------------------------------------------
# Súbor: core/logic/sluzby/portability/portability_guard.py
# Jadrová služba pre ochranu prenosnosti (PORTABILITY_GUARD).
# Stráži spustenie systémových venvov na cudzích počítačoch.
# 0 importov z CoreBridge, 0 importov z windows/ (GUI).
#----------------------------------------------------

import os
import json
import socket
import threading
import unicodedata

from core._path import Paths


class PortabilityGuardService:
    """
    Služba pre overovanie integrity a kompatibility venvov na prenosných diskoch.
    Zabraňuje haváriám spôsobeným spustením systémového venvu na inom počítači.
    """

    _machine_id_cache: str | None = None
    _machine_id_lock = threading.Lock()

    _config_cache: dict | None = None
    _config_cache_lock = threading.Lock()

    # =========================================================================
    # 1. HARDWARE ID & DETEKCIA REŽIMU
    # =========================================================================

    @classmethod
    def get_machine_id(cls) -> str:
        """Vygeneruje a nacachuje unikátny bezpečný hash počítača."""
        with cls._machine_id_lock:
            if cls._machine_id_cache is not None:
                return cls._machine_id_cache

            import hashlib
            hostname = socket.gethostname()
            hardware_guid = "UNKNOWN_HARDWARE"

            if os.name == 'nt':
                try:
                    import winreg
                    reg_path = r"SYSTEM\CurrentControlSet\Control\SystemInformation"
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                        hardware_guid, _ = winreg.QueryValueEx(key, "ComputerHardwareId")
                except Exception:
                    pass

            raw_signature = f"{hostname}_{hardware_guid}"
            cls._machine_id_cache = hashlib.sha256(raw_signature.encode('utf-8')).hexdigest()
            return cls._machine_id_cache

    @classmethod
    def is_portable_mode(cls) -> bool:
        """Zistí, či aplikácia beží v USB prenosnom režime."""
        marker = os.path.join(Paths.get_app_root_path(), Paths.PORTABLE_MARKER_FILENAME)
        return os.path.exists(marker)

    @classmethod
    def is_system_venv(cls, venv_path: str) -> bool:
        """
        Zistí, či venv vznikol zo systémového Pythonu (nie z Embedu).
        Embed venvy obsahujú značku 'virtualenv' a fungujú všade.
        """
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

    @staticmethod
    def normalize_venv_name(path_or_name: str) -> str:
        """Zjednotí názov priečinka pre bezpečné porovnávanie."""
        if not path_or_name:
            return ""
        val = str(path_or_name).strip()
        val = os.path.basename(os.path.normpath(val))
        val = unicodedata.normalize('NFC', val)
        return val.strip().casefold()

    # =========================================================================
    # 2. PRÁCA S portable_system_py.json (EVIDENCIA POČÍTAČA)
    # =========================================================================

    @classmethod
    def _get_config_path(cls) -> str:
        base_dir = os.path.dirname(Paths.get_config_file_path())
        return os.path.join(base_dir, "portable_system_py.json")

    @classmethod
    def _load_config_cache(cls) -> dict:
        with cls._config_cache_lock:
            if cls._config_cache is None:
                config_path = cls._get_config_path()
                try:
                    if os.path.exists(config_path):
                        with open(config_path, 'r', encoding='utf-8') as f:
                            cls._config_cache = json.load(f)
                    else:
                        cls._config_cache = {}
                except Exception:
                    cls._config_cache = {}
            return cls._config_cache

    @classmethod
    def _save_config_cache(cls, cfg: dict):
        config_path = cls._get_config_path()
        tmp_path = config_path + ".tmp"
        with cls._config_cache_lock:
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, config_path)
            except Exception:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                return
            cls._config_cache = cfg

    @classmethod
    def register_venv_creation(cls, venv_path: str, source_python_path: str = None):
        """
        Zavolá sa pri vzniku venvu. Ak je to systémový venv v Portable režime,
        zapíše aktuálny machine_id do databázy.
        """
        is_system = False
        if source_python_path:
            is_system = "[REL_TO_APP]" not in source_python_path
        else:
            is_system = cls.is_system_venv(venv_path)

        if cls.is_portable_mode() and is_system:
            cfg = dict(cls._load_config_cache())
            norm_name = cls.normalize_venv_name(venv_path)
            if norm_name:
                cfg[norm_name] = cls.get_machine_id()
                threading.Thread(target=cls._save_config_cache, args=(cfg,), daemon=True).start()

    # =========================================================================
    # 3. VEREJNÉ OVERENIE PRÍSTUPU (ČISTÉ TRUE / FALSE)
    # =========================================================================

    @classmethod
    def verify_access(cls, venv_path: str) -> bool:
        """
        Čistá biznis logika bez GUI.
        Vráti True, ak je venv bezpečné použiť.
        Vráti False, ak venv patrí inému PC a nesmie sa spustiť.
        """
        if not venv_path:
            return True
        if not cls.is_portable_mode():
            return True
        if not cls.is_system_venv(venv_path):
            return True

        norm_name = cls.normalize_venv_name(venv_path)
        if not norm_name:
            return True

        try:
            cfg = cls._load_config_cache()
            allowed_pc = cfg.get(norm_name)
            current_pc = cls.get_machine_id()

            if allowed_pc and allowed_pc != current_pc:
                return False
        except Exception:
            pass

        return True
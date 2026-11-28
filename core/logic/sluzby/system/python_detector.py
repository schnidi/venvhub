#----------------------------------------------------
# Súbor: core/logic/sluzby/system/python_detector.py
# Nízkoúrovňová multiplatformová STAVOVÁ služba pre detekciu Pythonu
# Podpora: Windows, Linux, macOS
# Všetky výsledky sú striktne riadené Enumami z core_states.py
# 0 závislostí na GUI, 0 závislostí na LanguageManageri
#----------------------------------------------------

import os
import sys
import re
import glob
import time
import shutil
import platform
import threading
import subprocess
import json
from dataclasses import dataclass

from core._path import Paths
from core.core_states import PythonOrigin, PythonPipStatus, PythonDetectorStatus


@dataclass(frozen=True)
class PythonRuntimeInfo:
    """Nemenný stavový model jedného nájdeného Python runtime prostredia."""
    path: str
    version: str
    origin: PythonOrigin
    pip_status: PythonPipStatus
    is_valid: bool

    def to_dict(self) -> dict:
        """Serializácia pre Bridge a spätnú kompatibilitu."""
        # Názov pre zobrazenie sa generuje odvodením zo stavov, nie hardkódom
        if self.origin == PythonOrigin.LOCAL:
            folder_name = os.path.basename(os.path.dirname(self.path))
            display = f"[Local] {folder_name}"
        elif self.version:
            display = f"Python {self.version}"
        else:
            display = os.path.basename(self.path)

        return {
            "display": display,
            "path": self.path,
            "version": self.version,
            "origin": self.origin,
            "pip_status": self.pip_status,
            "is_local": (self.origin == PythonOrigin.LOCAL),
            "is_valid": self.is_valid
        }


class PythonDetector:
    """
    Stavový detektor Python interpretrov pre Windows, Linux a macOS.
    Výsledky drží v pamäti výhradne cez stavové dátové modely a Enumy.
    """

    _cached_runtimes: list[PythonRuntimeInfo] | None = None
    _active_python_path: str | None = None
    _detector_status: PythonDetectorStatus = PythonDetectorStatus.SUCCESS
    
    _target_environments_cache: dict = {}

    _lock = threading.RLock()

    # =========================================================================
    # 1. SPRÁVA AKTÍVNEHO INTERPRETRA A PEP-508 PROSTREDIA
    # =========================================================================

    @classmethod
    def set_active_python_path(cls, python_path: str | None) -> None:
        """Nastaví globálny aktívny interpreter."""
        with cls._lock:
            cls._active_python_path = os.path.normpath(python_path) if python_path else None

    @classmethod
    def get_active_python_path(cls) -> str:
        """Vráti aktívny interpreter, inak sys.executable."""
        with cls._lock:
            return cls._active_python_path or os.path.normpath(sys.executable)

    @classmethod
    def get_pep508_environment(cls, python_path: str) -> dict | None:
        """
        Zistí PEP-508 environment parametre (sys_platform, python_version...) 
        z konkrétneho Python interpretra. Výsledky kešuje pre maximálny výkon.
        """
        if not python_path or not os.path.exists(python_path):
            return None

        canonical = os.path.realpath(os.path.normpath(python_path))
        
        with cls._lock:
            if canonical in cls._target_environments_cache:
                return cls._target_environments_cache[canonical]

            script = "import json; from packaging.markers import default_environment; print(json.dumps(default_environment()))"
            
            try:
                CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
                res = subprocess.run(
                    [canonical, "-c", script],
                    capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=2.0
                )
                if res.returncode == 0:
                    env_data = json.loads(res.stdout.strip())
                    cls._target_environments_cache[canonical] = env_data
                    return env_data
            except Exception:
                pass
            
            return None

    # =========================================================================
    # 2. RESOLVE MATERSKÉHO PYTHONU Z VENV (pyvenv.cfg)
    # =========================================================================

    @staticmethod
    def resolve_parent_python(venv_path: str) -> str:
        """Zistí materský Python z pyvenv.cfg multiplatformovo."""
        fallback = os.path.normpath(sys.executable)
        if not venv_path or not os.path.exists(venv_path):
            return fallback

        cfg_path = os.path.join(venv_path, "pyvenv.cfg")
        if not os.path.exists(cfg_path):
            return fallback

        for _ in range(3):
            try:
                with open(cfg_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    for line in f:
                        if line.strip().startswith("home ="):
                            parts = line.strip().split("=", 1)
                            if len(parts) > 1:
                                home_dir = parts[1].strip()
                                candidates = (
                                    ["python.exe", "pythonw.exe"]
                                    if os.name == "nt"
                                    else ["python3", "python"]
                                )
                                for cand in candidates:
                                    target = os.path.join(home_dir, cand)
                                    if os.path.isfile(target):
                                        return os.path.normpath(target)
                break
            except (PermissionError, OSError):
                time.sleep(0.05)
            except Exception:
                break

        return fallback

    # =========================================================================
    # 3. STAVOVÉ SKENOVANIE RUNTIMOV
    # =========================================================================

    @classmethod
    def get_detector_status(cls) -> PythonDetectorStatus:
        """Vráti výsledný Enum stav poslednej detekcie."""
        with cls._lock:
            return cls._detector_status

    @classmethod
    def get_installed_pythons(cls, force_refresh: bool = False) -> list[dict]:
        """
        Hlavná detekcia. Vracia zoznam slovníkov s typovanými Enumami:
          - 'origin': PythonOrigin
          - 'pip_status': PythonPipStatus
        """
        with cls._lock:
            if cls._cached_runtimes is not None and not force_refresh:
                return [r.to_dict() for r in cls._cached_runtimes]

            discovered: list[PythonRuntimeInfo] = []
            seen_canonical: set[str] = set()

            def _register(exe_path: str, origin: PythonOrigin, pip_status: PythonPipStatus) -> None:
                if not exe_path or not os.path.isfile(exe_path):
                    return

                try:
                    canonical = os.path.realpath(os.path.normpath(exe_path))
                    key = canonical.lower() if os.name == "nt" or sys.platform == "darwin" else canonical
                    if key in seen_canonical:
                        return
                    seen_canonical.add(key)
                except Exception:
                    canonical = os.path.normpath(exe_path)

                version_str = cls._probe_version(canonical)
                is_valid = bool(version_str)

                # Ak je runtime neplatný (napr. pád pri --version), nastavíme presný stav chyby
                effective_pip_status = pip_status if is_valid else PythonPipStatus.ERROR

                discovered.append(PythonRuntimeInfo(
                    path=canonical,
                    version=version_str,
                    origin=origin,
                    pip_status=effective_pip_status,
                    is_valid=is_valid
                ))

            # --- A. SKENOVANIE SYSTÉMU PODĽA OS ---
            current_os = platform.system()
            try:
                if current_os == "Windows":
                    cls._scan_windows(_register)
                elif current_os == "Linux":
                    cls._scan_linux(_register)
                elif current_os == "Darwin":
                    cls._scan_macos(_register)
            except Exception as e:
                print(f"[PythonDetector] Chyba pri skenovaní OS: {e}")
                cls._detector_status = PythonDetectorStatus.ERROR

            has_system_pythons = any(r.origin == PythonOrigin.SYSTEM for r in discovered)

            # --- B. FALLBACK: sys.executable ---
            sys_canonical = os.path.realpath(sys.executable)
            sys_key = sys_canonical.lower() if os.name == "nt" or sys.platform == "darwin" else sys_canonical
            if sys_key not in seen_canonical:
                _register(
                    exe_path=sys.executable,
                    origin=PythonOrigin.SYSTEM,
                    pip_status=PythonPipStatus.OK
                )

            # --- C. LOKÁLNE EMBED RUNTIMY (PyRuntimes) ---
            cls._scan_local_runtimes(_register)

            # --- D. VYHODNOTENIE VÝSLEDNÉHO STAVU (Enum) ---
            if not discovered:
                cls._detector_status = PythonDetectorStatus.NO_PYTHONS_FOUND
            elif not has_system_pythons:
                cls._detector_status = PythonDetectorStatus.FALLBACK_ONLY
            else:
                cls._detector_status = PythonDetectorStatus.SUCCESS

            cls._cached_runtimes = discovered
            return [r.to_dict() for r in cls._cached_runtimes]

    # =========================================================================
    # 4. OS-ŠPECIFICKÉ SKENERY (Čistá detekcia bez stringov)
    # =========================================================================

    @staticmethod
    def _scan_windows(register_callback) -> None:
        """Detekcia na Windows cez py.exe launcher + štandardné cesty."""
        CREATE_NO_WINDOW = 0x08000000

        # 1. py launcher
        try:
            out = subprocess.check_output(
                ["py", "--list-paths"],
                text=True,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
                timeout=3.0
            )
            for line in out.strip().splitlines():
                match = re.search(r'-V:[\d\.]+.*?\s+([a-zA-Z]:\\.*)', line)
                if match:
                    exe = match.group(1).strip()
                    register_callback(exe, PythonOrigin.SYSTEM, PythonPipStatus.OK)
        except Exception:
            pass

        # 2. Priečinky inštalácií
        roots = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python"),
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        ]
        for root in roots:
            if root and os.path.exists(root):
                for p in glob.glob(os.path.join(root, "*Python*", "python.exe")):
                    if os.path.isfile(p):
                        register_callback(p, PythonOrigin.SYSTEM, PythonPipStatus.OK)

    @staticmethod
    def _scan_linux(register_callback) -> None:
        """Detekcia na Linuxe cez PATH a známe binárne zložky."""
        search_dirs = [
            "/usr/bin",
            "/usr/local/bin",
            os.path.expanduser("~/.local/bin"),
            os.path.expanduser("~/.pyenv/shims")
        ]
        candidates = set()
        for d in search_dirs:
            if os.path.exists(d):
                for p in glob.glob(os.path.join(d, "python3*")):
                    if re.match(r"^python3(?:\.\d+)?$", os.path.basename(p)) and os.path.isfile(p):
                        candidates.add(p)

        which_py3 = shutil.which("python3")
        if which_py3:
            candidates.add(which_py3)

        for p in sorted(candidates):
            register_callback(p, PythonOrigin.SYSTEM, PythonPipStatus.OK)

    @staticmethod
    def _scan_macos(register_callback) -> None:
        """Detekcia na macOS cez Homebrew, Frameworks a systémové cesty."""
        search_dirs = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/Library/Frameworks/Python.framework/Versions",
            os.path.expanduser("~/.pyenv/shims"),
            os.path.expanduser("~/.local/bin"),
            "/usr/bin"
        ]
        candidates = set()
        for d in search_dirs:
            if not os.path.exists(d):
                continue
            if "Python.framework" in d:
                for fw_exe in glob.glob(os.path.join(d, "*", "bin", "python3*")):
                    if re.match(r"^python3(?:\.\d+)?$", os.path.basename(fw_exe)) and os.path.isfile(fw_exe):
                        candidates.add(fw_exe)
            else:
                for p in glob.glob(os.path.join(d, "python3*")):
                    if re.match(r"^python3(?:\.\d+)?$", os.path.basename(p)) and os.path.isfile(p):
                        candidates.add(p)

        for p in sorted(candidates):
            register_callback(p, PythonOrigin.SYSTEM, PythonPipStatus.OK)

    @staticmethod
    def _scan_local_runtimes(register_callback) -> None:
        """Prehľadá lokálny prenosný priečinok PyRuntimes."""
        try:
            install_dir = Paths.get_python_runtimes_install_dir()
            if not os.path.exists(install_dir):
                return

            candidates = (
                ["python.exe", os.path.join("bin", "python.exe")]
                if os.name == "nt"
                else ["python3", "python", os.path.join("bin", "python3"), os.path.join("bin", "python")]
            )

            for item in os.listdir(install_dir):
                sub = os.path.join(install_dir, item)
                if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "install.ini")):
                    for rel in candidates:
                        target = os.path.join(sub, rel)
                        if os.path.isfile(target):
                            # Lokálne embed interpretre idú do stavu CHECKING (pip sa overí neskôr)
                            register_callback(target, PythonOrigin.LOCAL, PythonPipStatus.CHECKING)
                            break
        except Exception as e:
            print(f"[PythonDetector] Chyba pri skenovaní PyRuntimes: {e}")

    @staticmethod
    def _probe_version(exe_path: str) -> str:
        """Zistí číslo verzie cez subproces."""
        CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
        try:
            res = subprocess.run(
                [exe_path, "--version"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=2.0
            )
            raw = (res.stdout or res.stderr).strip()
            match = re.search(r"Python\s+([\d\.]+)", raw)
            if match:
                return match.group(1).strip()
        except Exception:
            pass
        return ""

    # =========================================================================
    # 5. STAVOVÉ OPERÁCIE S PAMÄŤOU
    # =========================================================================

    @classmethod
    def add_local_python(
        cls, 
        folder_name: str, 
        python_path: str, 
        pip_status: PythonPipStatus | str = PythonPipStatus.OK
    ) -> None:
        """Pridá lokálny runtime s explicitným Enumom stavu."""
        with cls._lock:
            if cls._cached_runtimes is None:
                cls.get_installed_pythons(force_refresh=True)

            norm_status = PythonPipStatus(pip_status) if isinstance(pip_status, str) else pip_status
            norm_path = os.path.realpath(os.path.normpath(python_path))

            # Aktualizácia ak už existuje
            updated = []
            found = False
            for r in cls._cached_runtimes:
                if os.path.realpath(r.path).lower() == norm_path.lower():
                    updated.append(PythonRuntimeInfo(
                        path=norm_path,
                        version=r.version,
                        origin=PythonOrigin.LOCAL,
                        pip_status=norm_status,
                        is_valid=r.is_valid
                    ))
                    found = True
                else:
                    updated.append(r)

            if not found:
                ver = cls._probe_version(norm_path)
                updated.append(PythonRuntimeInfo(
                    path=norm_path,
                    version=ver,
                    origin=PythonOrigin.LOCAL,
                    pip_status=norm_status,
                    is_valid=bool(ver)
                ))

            cls._cached_runtimes = updated

    @classmethod
    def remove_local_python(cls, python_path: str) -> None:
        """Odstráni runtime zo zoznamu podľa cesty."""
        with cls._lock:
            if cls._cached_runtimes:
                target = os.path.realpath(os.path.normpath(python_path)).lower()
                cls._cached_runtimes = [
                    r for r in cls._cached_runtimes 
                    if os.path.realpath(r.path).lower() != target
                ]

    @classmethod
    def update_pip_status(cls, python_path: str, status: PythonPipStatus | str) -> None:
        """Aktualizuje stav pipu na prísny Enum (OK, MISSING, ERROR, CHECKING)."""
        with cls._lock:
            if not cls._cached_runtimes:
                return

            norm_status = PythonPipStatus(status) if isinstance(status, str) else status
            target = os.path.realpath(os.path.normpath(python_path)).lower()

            updated = []
            for r in cls._cached_runtimes:
                if os.path.realpath(r.path).lower() == target:
                    updated.append(PythonRuntimeInfo(
                        path=r.path,
                        version=r.version,
                        origin=r.origin,
                        pip_status=norm_status,
                        is_valid=r.is_valid
                    ))
                else:
                    updated.append(r)

            cls._cached_runtimes = updated
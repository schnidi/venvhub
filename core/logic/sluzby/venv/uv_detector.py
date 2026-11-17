#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/uv_detector.py
# Nízkoúrovňová multiplatformová služba pre detekciu UV
# Podpora: Windows, Linux, macOS
# Závislosti: Iba štandardná knižnica Pythonu + Paths + core_states
# 0 importov na PythonDetector, 0 importov na CoreBridge
#----------------------------------------------------

import os
import shutil
import subprocess
from pathlib import Path
from core._path import Paths
from core.core_states import UVStatus


class UVDetector:
    """
    Samostatná nízkoúrovňová služba pre detekciu prítomnosti a stavu binárky UV.
    Nepripája sa na žiadne iné služby; informáciu o aktívnom Pythone prijíma
    výhradne ako voliteľný argument.
    """

    _cached_path: str | None = None
    _cached_status: UVStatus = UVStatus.NOT_FOUND
    _cached_version: str | None = None
    _was_searched: bool = False

    @classmethod
    def get_uv_state(cls, active_python_path: str | None = None, force_refresh: bool = False) -> dict:
        """
        Vykoná detekciu a vráti kompletný stavový slovník s Enumom UVStatus:
        {
            "status": UVStatus,
            "is_ready": bool,
            "executable": str | None,
            "version": str | None
        }
        """
        if cls._was_searched and not force_refresh:
            return {
                "status": cls._cached_status,
                "is_ready": (cls._cached_status != UVStatus.NOT_FOUND and cls._cached_status != UVStatus.ERROR),
                "executable": cls._cached_path,
                "version": cls._cached_version
            }

        exe_path, status = cls._discover_uv(active_python_path)
        version_str = cls._probe_version(exe_path) if exe_path else None

        # Ak súbor existuje, ale nefunguje (napr. havaruje pri --version), nastavíme stav ERROR
        if exe_path and not version_str:
            status = UVStatus.ERROR
            exe_path = None

        cls._cached_path = exe_path
        cls._cached_status = status
        cls._cached_version = version_str
        cls._was_searched = True

        return {
            "status": status,
            "is_ready": (status != UVStatus.NOT_FOUND and status != UVStatus.ERROR),
            "executable": exe_path,
            "version": version_str
        }

    @classmethod
    def get_uv_path(cls, active_python_path: str | None = None, force_refresh: bool = False) -> str | None:
        """Rýchla metóda pre získanie cesty k binárke UV."""
        state = cls.get_uv_state(active_python_path=active_python_path, force_refresh=force_refresh)
        return state["executable"]

    @classmethod
    def is_uv_installed(cls, active_python_path: str | None = None) -> bool:
        """Overí pripravenosť UV (True/False)."""
        state = cls.get_uv_state(active_python_path=active_python_path)
        return state["is_ready"]

    @classmethod
    def reset_cache(cls) -> None:
        """Vynuluje medzipamäť detektora."""
        cls._was_searched = False
        cls._cached_path = None
        cls._cached_status = UVStatus.NOT_FOUND
        cls._cached_version = None

    # =========================================================================
    # VNÚTORNÉ VYHĽADÁVACIE STRATÉGIE
    # =========================================================================

    @classmethod
    def _discover_uv(cls, active_python_path: str | None) -> tuple[str | None, UVStatus]:
        """
        Prehľadá systém v prísnom poradí priorít:
        1. BUNDLED (zabalené priamo v distribúcii aplikácie)
        2. ACTIVE_VENV (v odovzdanom aktívnom Pythone / venv)
        3. STANDALONE (štandardné inštalačné lokality: Cargo, Local bin, Homebrew)
        4. SYSTEM_PATH (systémová premenná PATH)
        """
        exe_name = "uv.exe" if os.name == "nt" else "uv"

        # --- 1. Stratégia: Vstavané priamo v aplikácii (PyInstaller MEIPASS / root) ---
        internal_path = os.path.join(Paths.get_base_path(), exe_name)
        if os.path.isfile(internal_path):
            return os.path.normpath(internal_path), UVStatus.BUNDLED

        # --- 2. Stratégia: V odovzdanom aktívnom Pythone (Scripts / bin) ---
        if active_python_path and os.path.isfile(active_python_path):
            py_dir = os.path.dirname(active_python_path)
            scripts_dir = "Scripts" if os.name == "nt" else "bin"
            venv_candidate = os.path.join(py_dir, scripts_dir, exe_name)
            if os.path.isfile(venv_candidate):
                return os.path.normpath(venv_candidate), UVStatus.ACTIVE_VENV

            # Ak je active_python_path už priamo interpreter vo vnútri Scripts/bin
            direct_candidate = os.path.join(py_dir, exe_name)
            if os.path.isfile(direct_candidate):
                return os.path.normpath(direct_candidate), UVStatus.ACTIVE_VENV

        # --- 3. Stratégia: Standalone cesty (Cargo, Local, Homebrew) ---
        home = Path.home()
        standalone_dirs = [
            home / ".cargo" / "bin",
            home / ".local" / "bin",
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin")
        ]

        if os.name == "nt":
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                standalone_dirs.append(Path(local_appdata) / "bin")

        for s_dir in standalone_dirs:
            candidate = s_dir / exe_name
            if candidate.is_file():
                return os.path.normpath(str(candidate)), UVStatus.STANDALONE

        # --- 4. Stratégia: Systémová PATH ---
        path_in_env = shutil.which("uv")
        if path_in_env and os.path.isfile(path_in_env):
            return os.path.normpath(path_in_env), UVStatus.SYSTEM_PATH

        return None, UVStatus.NOT_FOUND

    @staticmethod
    def _probe_version(exe_path: str) -> str | None:
        """Zistí verziu UV spustením príkazového riadka s flagom --version."""
        CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
        try:
            res = subprocess.run(
                [exe_path, "--version"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=2.0
            )
            out = (res.stdout or res.stderr).strip()
            # Typický formát výstupu: "uv 0.4.18 (b4e3c9a 2024-09-24)"
            if out.lower().startswith("uv"):
                return out
        except Exception:
            pass
        return None
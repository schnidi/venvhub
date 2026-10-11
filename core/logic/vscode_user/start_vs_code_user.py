#----------------------------------------
# Súbor: core/logic/vscode_user/start_vs_code_user.py
#----------------------------------------

import os
import subprocess
from core.logic.vs_code_json import VSCodeIntegration
from core.logic.language_manager import LanguageManager
from core.logic.ide_detector import IDEDetector
from core.logic.commands.vscode_commands import VSCodeCommandDispatcher
from core.logic.commands.cursor_commands import CursorAICommandDispatcher
from core.logic.vscode_user.profile_manager import VSCodeProfileManager


class VSCodeLauncher:
    """
    Univerzálna logika pre spustenie aktívneho editora (VS Code / Cursor AI).
    Dynamicky skladá CLI príkazy, nastavuje cesty, profily a interpreter.
    """

    @staticmethod
    def _find_executable_in_dir(directory: str, candidates: list[str]) -> str | None:
        """Nájde spustiteľný súbor v zadanom priečinku alebo jeho podadresári bin."""
        if not directory or not os.path.exists(directory):
            return None

        for cand in candidates:
            # Priamo v priečinku
            p = os.path.join(directory, cand)
            if os.path.exists(p):
                return p
            # V podpriečinku bin
            p_bin = os.path.join(directory, "bin", cand)
            if os.path.exists(p_bin):
                return p_bin
            # V podpriečinku resources/app/bin (špecifikum Electron aplikácií)
            p_res = os.path.join(directory, "resources", "app", "bin", cand)
            if os.path.exists(p_res):
                return p_res
        return None

    @staticmethod
    def launch(core, project_path: str, venv_path: str) -> tuple[bool, str]:
        """
        Dynamicky spustí zvolený editor (VS Code alebo Cursor) s príslušným profilom.
        """
        if not project_path or not os.path.exists(project_path):
            return False, LanguageManager.get("err_project_path_not_exist", "Cesta k projektu neexistuje.")

        # 1. Zosynchronizujeme predvolený Venv pre projekt
        if venv_path and os.path.exists(venv_path):
            VSCodeIntegration.set_default_interpreter(project_path, venv_path)

        active_ide = getattr(core, "active_ide", "vscode")

        # 2. Určenie spustiteľného súboru (Portable vs Systém)
        custom_exe = None
        if active_ide == "cursor":
            port_dir = getattr(core, "portable_cursor_path", "")
            if port_dir and os.path.exists(port_dir):
                custom_exe = VSCodeLauncher._find_executable_in_dir(port_dir, ["cursor.cmd", "cursor.exe", "Cursor.exe"])
            if not custom_exe:
                custom_exe = IDEDetector.get_cursor_executable()
            dispatcher = CursorAICommandDispatcher(custom_executable=custom_exe)
        else:
            port_dir = getattr(core, "portable_vscode_path", "")
            if port_dir and os.path.exists(port_dir):
                custom_exe = VSCodeLauncher._find_executable_in_dir(port_dir, ["code.cmd", "code.exe", "Code.exe"])
            if not custom_exe:
                custom_exe = IDEDetector.get_vscode_executable()
            dispatcher = VSCodeCommandDispatcher(custom_executable=custom_exe)

        # 3. Určenie používateľského profilu pre dané IDE
        active_user_id = core.get_active_ide_user() if hasattr(core, "get_active_ide_user") else getattr(core, "active_vscode_user", "")
        users_root = getattr(core, "vscode_users_root", "")

        user_data_dir = None
        extensions_dir = None

        if active_user_id and users_root and os.path.exists(users_root):
            ide_profiles_root = VSCodeProfileManager.get_ide_profiles_dir(users_root, active_ide)
            profile_dir = os.path.join(ide_profiles_root, active_user_id)
            if os.path.exists(profile_dir):
                user_data_dir = os.path.join(profile_dir, "data")
                extensions_dir = os.path.join(profile_dir, "data", "extensions")

        # 4. Poskladanie finálneho príkazu cez príslušný dispečer
        cmd = dispatcher.get(
            "launch_project",
            project_path=project_path,
            user_data_dir=user_data_dir,
            extensions_dir=extensions_dir
        )

        # 5. Spustenie procesu
        try:
            is_windows = (os.name == "nt")
            creation_flags = 0x08000000 if is_windows else 0

            subprocess.Popen(
                cmd,
                shell=is_windows,
                creationflags=creation_flags
            )
            return True, ""
        except Exception as e:
            ide_display_name = "Cursor AI" if active_ide == "cursor" else "VS Code"
            return False, LanguageManager.get("err_launch_vscode", "Nepodarilo sa spustiť {0}:\n{1}").format(ide_display_name, str(e))
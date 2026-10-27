#----------------------------------------
# Súbor: core/logic/vscode_user/start_vs_code_user.py
#----------------------------------------

import os
import subprocess
from core.core_states import IDEType, IDEStatus
from core.core_bridge import CoreBridge
from core.logic.vs_code_json import VSCodeIntegration
from core.logic.language_manager import LanguageManager
from core.logic.commands.vscode_commands import VSCodeCommandDispatcher
from core.logic.commands.cursor_commands import CursorAICommandDispatcher
from core.logic.sluzby.apt_ide_logic import AptIDELogic


class VSCodeLauncher:
    """
    Univerzálna logika pre spustenie aktívneho editora (VS Code / Cursor AI).
    Využíva nízkoúrovňovú službu CoreBridge na získanie overených ciest a profilov.
    """

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

        active_ide = getattr(core, "active_ide", IDEType.VSCODE)
        portable_path = getattr(core, f"portable_{active_ide}_path", "")
        users_root = getattr(core, "vscode_users_root", "")
        active_user_id = core.get_active_ide_user() if hasattr(core, "get_active_ide_user") else getattr(core, "active_vscode_user", "")

        # 👉 2. Získanie kompletného overeného stavu z nízkoúrovňovej služby cez CoreBridge
        ide_state = CoreBridge.get_ide_state(
            ide_type=active_ide,
            portable_path=portable_path,
            users_root=users_root,
            active_user_id=active_user_id
        )

        # Kontrola, či binárka fyzicky existuje (pomocou stavov)
        if ide_state["status"] == IDEStatus.NOT_FOUND or not ide_state["is_ready"]:
            ide_display_name = "Cursor AI" if ide_state["ide_type"] == IDEType.CURSOR else "VS Code"
            return False, LanguageManager.get("err_ide_not_found", "Editor {0} sa nenašiel v systéme ani na prenosnom disku.").format(ide_display_name)

        executable = ide_state["executable"]
        user_data_dir = ide_state["user_data_dir"]
        extensions_dir = ide_state["extensions_dir"]

        if extensions_dir:
            os.makedirs(extensions_dir, exist_ok=True)

        # 3. Vytvorenie dispečera s overenou binárkou podľa typu editora
        if ide_state["ide_type"] == IDEType.CURSOR:
            dispatcher = CursorAICommandDispatcher(custom_executable=executable)
        else:
            dispatcher = VSCodeCommandDispatcher(custom_executable=executable)

        # 👉 4. Blesková poistka pred spustením (kontrola rozšírení z balíčkov)
        AptIDELogic.verify_and_heal_profile_on_launch(core, venv_path, dispatcher)

        # 5. Poskladanie finálneho príkazu cez príslušný dispečer
        cmd = dispatcher.get(
            "launch_project",
            project_path=project_path,
            user_data_dir=user_data_dir,
            extensions_dir=extensions_dir
        )

        # 6. Spustenie procesu
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
            ide_display_name = "Cursor AI" if ide_state["ide_type"] == IDEType.CURSOR else "VS Code"
            return False, LanguageManager.get("err_launch_vscode", "Nepodarilo sa spustiť {0}:\n{1}").format(ide_display_name, str(e))
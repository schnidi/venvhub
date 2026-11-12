#----------------------------------------
# Súbor: core/logic/button/manager/actions.py
#----------------------------------------
import subprocess
import os
import tempfile
import psutil
from core.logic.process_registry import process_registry
from core._path import Paths
from core.logic.containers.logic.check_multi_venv import MultiVenvChecker
from core.core_bridge import CoreBridge

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_CONSOLE = 0x00000010

class ActionHandler:

    # ==========================================================
    # --- NÍZKOÚROVŇOVÝ MOTOR (volajú ho ostatné súbory) ---
    # ==========================================================

    @staticmethod
    def _build_run_bat(project_path: str, activate_bat: str, script_to_run: str = None) -> str:
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="venvhub_run_")
        with os.fdopen(fd, "w", encoding="mbcs") as f:
            f.write("@echo off\r\n")
            f.write(f'cd /d "{project_path}"\r\n')
            f.write(f'call "{activate_bat}"\r\n')
            if script_to_run:
                f.write(f'python "{script_to_run}"\r\n')
        return bat_path

    @staticmethod
    def start_terminal_process(project_path: str, venv_path: str, script_to_run: str):
        """Univerzálna funkcia na spustenie procesu v novom termináli."""
        if not all([project_path, venv_path, script_to_run]): return
        if not CoreBridge.verify_venv_access(venv_path): return

        process_registry.cleanup_dead_processes(venv_path)
        if process_registry.is_running(venv_path):
            print(f"PROCES IGNOROVANÝ: Proces pre {os.path.basename(venv_path)} už beží.")
            return

        activate_bat = Paths.get_venv_activate_bat_path(venv_path)

        bat_path = ActionHandler._build_run_bat(project_path, activate_bat, script_to_run)
        cmd = f'cmd.exe /k "{bat_path}"'

        process = subprocess.Popen(cmd, creationflags=CREATE_NEW_CONSOLE)
        
        # ---> OPRAVA: TOTO TU CHÝBALO! ZAREGISTROVANIE PROCESU <---
        process_registry.register(venv_path, pid=process.pid, process_type='terminal')

    @staticmethod
    def start_silent_process(project_path: str, venv_path: str, script_to_run: str):
        """Univerzálna funkcia na spustenie procesu na pozadí."""
        if not all([project_path, venv_path, script_to_run]): return
        if not CoreBridge.verify_venv_access(venv_path): return

        process_registry.cleanup_dead_processes(venv_path)
        if process_registry.is_running(venv_path):
            print(f"PROCES IGNOROVANÝ (SILENT): Proces pre {os.path.basename(venv_path)} už beží.")
            return

        python_exe = Paths.get_venv_python_exe_path(venv_path)
        script_path = Paths.get_script_in_project_path(project_path, script_to_run)
        if not os.path.exists(script_path): return
        
        process = subprocess.Popen([python_exe, script_path], cwd=project_path, creationflags=CREATE_NO_WINDOW)
        process_registry.register(venv_path, pid=process.pid, process_type='silent')

    @staticmethod
    def open_terminal_only(project_path: str, venv_path: str):
        """Univerzálna funkcia na otvorenie aktivovaného terminálu."""
        if not all([project_path, venv_path]): return
        if not CoreBridge.verify_venv_access(venv_path): return

        activate_bat = Paths.get_venv_activate_bat_path(venv_path)

        bat_path = ActionHandler._build_run_bat(project_path, activate_bat, script_to_run=None)
        cmd = f'cmd.exe /k "{bat_path}"'

        process = subprocess.Popen(cmd, creationflags=CREATE_NEW_CONSOLE)
        process_registry.register(venv_path, pid=process.pid, process_type='terminal')
        
    @staticmethod
    def stop_single(venv_path):
        """Zastaví konkrétny proces podľa venv_path."""
        if venv_path:
            process_registry.kill_and_unregister(venv_path)

    # ==========================================================
    # --- VYSOKOÚROVŇOVÉ FUNKCIE (volá ich dispatcher a iní) ---
    # ==========================================================

    @staticmethod
    def run_single_terminal(core):
        """Spustí terminál pre globálne aktívny projekt."""
        ActionHandler.start_terminal_process(
            project_path=Paths.get_project_path(core.projects_root, core.active_project),
            venv_path=core.active_venv_path,
            script_to_run=core.last_script
        )

    @staticmethod
    def run_single_silent(core):
        """Spustí na pozadí globálne aktívny projekt."""
        ActionHandler.start_silent_process(
            project_path=Paths.get_project_path(core.projects_root, core.active_project),
            venv_path=core.active_venv_path,
            script_to_run=core.last_script
        )

    @staticmethod
    def stop_multiple(core, group_name):
        """Zastaví všetky procesy, ktoré patria danej skupine."""
        group_members = core.multi_groups.get(group_name, [])
        if not group_members: return
        
        print(f"--- Zastavujem multi-run skupinu: {group_name} ---")
        for member in group_members:
            venv_path = member.get("venv_path")
            if venv_path:
                if MultiVenvChecker.is_owner(venv_path, group_name):
                    process_registry.kill_and_unregister(venv_path)
                    MultiVenvChecker.remove_owner(venv_path)
                    
        print(f"--- Zastavenie skupiny {group_name} dokončené ---")
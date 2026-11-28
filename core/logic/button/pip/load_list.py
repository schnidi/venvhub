#----------------------------------------
# Súbor: core/logic/button/pip/load_list.py
#----------------------------------------

import json
import subprocess
import os
from core.logic.commands.command_factory import PackageManagerFactory


class LoadListHandler:
    @staticmethod
    def _get_clean_env() -> dict:
        """
        Vytvorí čisté systémové prostredie bez premenných PyInstalleru.
        Zabráni úniku PYTHONPATH / PYTHONHOME do subprocesu Venvu.
        """
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONEXECUTABLE", None)
        env.pop("_MEIPASS2", None)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return env

    @staticmethod
    def get_packages(venv_path, manager_type="pip"):
        """
        Univerzálny načítavač balíčkov (Paralelná verzia pre bežný aj PyInstaller režim).
        """
        from concurrent.futures.thread import ThreadPoolExecutor

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        clean_env = LoadListHandler._get_clean_env()

        cmd_list = dispatcher.get("list_json")
        cmd_outdated = dispatcher.get("list_outdated_json")

        def run_command(cmd):
            """Bezpečne spustí príkaz s izolovaným prostredím."""
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                    env=clean_env,
                    encoding='utf-8',
                    errors='replace'
                )
                if result.returncode == 0 and result.stdout.strip():
                    return json.loads(result.stdout)
            except Exception:
                pass
            return []

        # 1. Paralelné získanie zoznamov
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_installed = executor.submit(run_command, cmd_list)
            future_outdated = executor.submit(run_command, cmd_outdated)

            installed_data = future_installed.result()
            outdated_data = future_outdated.result()

        if not installed_data or not isinstance(installed_data, list):
            return []
        if not isinstance(outdated_data, list):
            outdated_data = []

        # 2. Spárovanie verzií
        installed_map = {item['name']: item['version'] for item in installed_data if 'name' in item}
        outdated_map = {item['name']: item.get('latest_version', item.get('version')) for item in outdated_data if 'name' in item}

        packages = []
        for name, version in installed_map.items():
            latest = outdated_map.get(name, version)
            packages.append({
                'name': name,
                'version': version,
                'latest': latest
            })

        return sorted(packages, key=lambda x: x['name'].lower())
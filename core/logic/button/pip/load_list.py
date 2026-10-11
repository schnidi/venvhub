#----------------------------------------
# Súbor: core/logic/button/pip/load_list.py
#----------------------------------------

import json
import subprocess
import os
import concurrent.futures
from core.logic.commands.command_factory import PackageManagerFactory

class LoadListHandler:
    @staticmethod
    def get_packages(venv_path, manager_type="pip"):
        """
        Univerzálny načítavač balíčkov (Paralelná verzia).
        """
        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        
        cmd_list = dispatcher.get("list_json")
        cmd_outdated = dispatcher.get("list_outdated_json")

        def run_command(cmd):
            """Pomocná funkcia na spustenie príkazu a vrátenie JSON výsledku."""
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                if result.returncode == 0:
                    return json.loads(result.stdout)
            except Exception:
                pass
            return []

        # =========================================================
        # 1. PARALELNÉ SPUSTENIE OBOCH PRÍKAZOV SÚČASNE
        # =========================================================
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Tieto dve úlohy sa spustia presne v tej istej milisekunde
            future_installed = executor.submit(run_command, cmd_list)
            future_outdated = executor.submit(run_command, cmd_outdated)

            # Čakáme, kým obe dobehnú (čas = dĺžka pomalšieho príkazu)
            installed_data = future_installed.result()
            outdated_data = future_outdated.result()

        # =========================================================
        # 2. SPRACOVANIE VÝSLEDKOV
        # =========================================================
        installed_map = {item['name']: item['version'] for item in installed_data}
        outdated_map = {item['name']: item.get('latest_version', item.get('version')) for item in outdated_data}
        
        packages = []
        for name, version in installed_map.items():
            latest = outdated_map.get(name, version) 
            packages.append({
                'name': name,
                'version': version,
                'latest': latest
            })
            
        return sorted(packages, key=lambda x: x['name'].lower())
#----------------------------------------
# Súbor: core/logic/button/manager/row_actions.py
#----------------------------------------

import subprocess
import os
from core.logic.button.manager.actions import ActionHandler # Volá centrálny motor
from core._path import Paths

class RowActionHandler:
    """
    Handler pre akcie v riadkoch tabuľky (Manager Window).
    Zabezpečuje, aby sa spúšťali konkrétne venvy nezávisle od globálneho nastavenia.
    """

    @staticmethod
    def run_venv(core, venv_path):
        """
        Zistí kontext z riadku a zavolá centrálnu funkciu na spustenie.
        """
        project_path = Paths.get_project_path(core.projects_root, core.active_project)
        
        # BEZPEČNOSŤ PRE TENTO SÚBOR: vždy zaistí, že sa skript spustí.
        script_to_run = core.last_script or "main.py"
        
        # Rešpektuje nastavenie aplikácie a volá bezpečné low-level funkcie:
        if core.run_mode == "run_silent":
            ActionHandler.start_silent_process(project_path, venv_path, script_to_run)
        elif core.run_mode == "open_terminal":
            ActionHandler.open_terminal_only(project_path, venv_path)
        else:
            ActionHandler.start_terminal_process(project_path, venv_path, script_to_run)

    @staticmethod
    def stop_venv(venv_path):
        """
        Zavolá centrálnu funkciu na zastavenie.
        Vďaka zápisu vo funkcii start_terminal_process to konečne funguje.
        """
        ActionHandler.stop_single(venv_path)
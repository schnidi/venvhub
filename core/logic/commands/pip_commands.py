#----------------------------------------
# Súbor: core/logic/commands/pip_commands.py
#----------------------------------------

from core._path import Paths
from typing import Callable, Any
import os

class PipCommandDispatcher:
    def __init__(self, venv_path: str):
        python_exe_path = Paths.get_venv_python_exe_path(venv_path)
        if not venv_path or not os.path.exists(python_exe_path):
            raise ValueError(f"Cesta k python.exe neexistuje alebo je neplatná: {python_exe_path}")
            
        self.venv_path = venv_path
        self.python_exe = python_exe_path
        
        self._commands: dict[str, Callable[..., list[str]]] = {
            "install": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", kwargs['package_name']],
            
            "install_specific": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", f"{kwargs['package_name']}=={kwargs['version']}"],

            "install_multiple_exact": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install"] + kwargs['packages'],

            "uninstall": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "uninstall", kwargs['package_name'], "-y"],

            "upgrade": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", "--upgrade", kwargs['package_name']],

            "upgrade_multiple": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", "--upgrade"] + kwargs['packages'],
            
            "upgrade_pip": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", "--upgrade", "pip"],

            "install_requirements": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", "-r", Paths.get_requirements_txt_path(kwargs['project_root'])],
            
            # --- NOVÉ PRE CLONE.PY (Z externého súboru) ---
            "install_req_file": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", "-r", kwargs['file_path']],
                
            # --- NOVÉ PRE CLONE.PY (Pip -e) ---
            "install_editable": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "install", "-e", kwargs['path']],
            
            "freeze": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "freeze"],

            "list": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "list"],

            "list_json": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "list", "--format=json"],

            # --- NOVÉ PRE EDITABLE SERVICE ---
            "list_editable_json": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "list", "--editable", "--format=json"],

            "list_outdated": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "list", "--outdated"],

            "list_outdated_json": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "list", "--outdated", "--format=json"],
                
            "show": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "show", kwargs['package_name']],

            "search": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "search", kwargs['query']],
            
            "check": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "check"],

            # --- NOVÉ PRÍKAZY PRE APT LOGIKU ---

            "show_multiple": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "show"] + kwargs['packages'],

            "uninstall_multiple": lambda **kwargs: 
                [self.python_exe, "-m", "pip", "uninstall", "-y"] + kwargs['packages'],
        }

    def get(self, command_key: str, **kwargs: Any) -> list[str]:
        if command_key not in self._commands:
            raise KeyError(f"Príkaz s kľúčom '{command_key}' neexistuje v PipCommandDispatcher.")
        return self._commands[command_key](**kwargs)
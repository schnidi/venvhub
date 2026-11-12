#----------------------------------------
# Súbor: core/logic/commands/uv_commands.py
#----------------------------------------

from core._path import Paths
from core.logic.uv_detector import UVDetector
from core.logic.language_manager import LanguageManager
from typing import Callable, Any
import os

class UvCommandDispatcher:
    def __init__(self, venv_path: str):
        python_exe_path = Paths.get_venv_python_exe_path(venv_path)
        if not venv_path or not os.path.exists(python_exe_path):
            err_msg = LanguageManager.get("uv_cmd_err_no_python", "Cesta k python.exe neexistuje: {path}").format(path=python_exe_path)
            raise ValueError(err_msg)
            
        self.python_exe = python_exe_path
        uv_exe = UVDetector.get_uv_path() or "uv"
        
        self.uv_base = [uv_exe, "pip"]
        self.python_arg = ["--python", self.python_exe]
        self.base_pip = [self.python_exe, "-m", "pip"]
        
        self._commands: dict[str, Callable[..., list[str]]] = {
            "install": lambda **kwargs: 
                self.uv_base + ["install"] + [kwargs['package_name']] + self.python_arg,
            
            "install_specific": lambda **kwargs: 
                self.uv_base + ["install"] + [f"{kwargs['package_name']}=={kwargs['version']}"] + self.python_arg,

            "install_multiple_exact": lambda **kwargs: 
                self.uv_base + ["install"] + kwargs['packages'] + self.python_arg,

            "uninstall": lambda **kwargs: 
                self.uv_base + ["uninstall"] + [kwargs['package_name']] + self.python_arg,

            "upgrade": lambda **kwargs: 
                self.uv_base + ["install", "--upgrade"] + [kwargs['package_name']] + self.python_arg,

            "upgrade_multiple": lambda **kwargs: 
                self.uv_base + ["install", "--upgrade"] + kwargs['packages'] + self.python_arg,
            
            "upgrade_pip": lambda **kwargs: 
                self.uv_base + ["install", "--upgrade", "pip"] + self.python_arg,

            "install_requirements": lambda **kwargs: 
                self.uv_base + ["install", "-r", Paths.get_requirements_txt_path(kwargs['project_root'])] + self.python_arg,
            
            # --- NOVÉ PRE CLONE.PY (Bez no-build-isolation, ktorá mrazila UV) ---
            "install_req_file": lambda **kwargs: 
                self.uv_base + ["install", "-r", kwargs['file_path']] + self.python_arg,
                
            # --- NOVÉ PRE CLONE.PY (UV pip -e) ---
            "install_editable": lambda **kwargs: 
                self.uv_base + ["install", "-e", kwargs['path']] + self.python_arg,

            "freeze": lambda **kwargs: 
                self.uv_base + ["freeze"] + self.python_arg,

            "list": lambda **kwargs: 
                self.uv_base + ["list"] + self.python_arg,

            "list_json": lambda **kwargs: 
                self.uv_base + ["list", "--format=json"] + self.python_arg,

            # --- NOVÉ PRE EDITABLE SERVICE ---
            "list_editable_json": lambda **kwargs: 
                self.uv_base + ["list", "--editable", "--format=json"] + self.python_arg,

            "list_outdated": lambda **kwargs: 
                self.uv_base + ["list", "--outdated"] + self.python_arg,

            "list_outdated_json": lambda **kwargs: 
                self.uv_base + ["list", "--outdated", "--format=json"] + self.python_arg,
                
            "show": lambda **kwargs: 
                self.uv_base + ["show"] + [kwargs['package_name']] + self.python_arg,

            "search": lambda **kwargs: 
                ["echo", LanguageManager.get("uv_cmd_no_search", "UV nepodporuje 'search'.")],
            
            "check": lambda **kwargs: 
                self.uv_base + ["check"] + self.python_arg,

            # --- NOVÉ PRÍKAZY PRE APT LOGIKU ---

            "show_multiple": lambda **kwargs: 
                self.uv_base + ["show"] + kwargs['packages'] + self.python_arg,

            "uninstall_multiple": lambda **kwargs: 
                self.uv_base + ["uninstall"] + kwargs['packages'] + self.python_arg,
        }

    def get(self, command_key: str, **kwargs: Any) -> list[str]:
        if command_key not in self._commands:
            err_msg = LanguageManager.get("uv_cmd_err_invalid", "Príkaz '{cmd}' neexistuje.").format(cmd=command_key)
            raise KeyError(err_msg)
        return self._commands[command_key](**kwargs)
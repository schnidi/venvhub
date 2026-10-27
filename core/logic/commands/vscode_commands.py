#----------------------------------------
# Súbor: core/logic/commands/vscode_commands.py
#----------------------------------------

import os
from typing import Callable, Any
from core.logic.language_manager import LanguageManager


class VSCodeCommandDispatcher:
    """
    Dispečer pre generovanie CLI príkazov editora Visual Studio Code.
    Rieši spustenie projektu, izoláciu profilov (user-data-dir, extensions-dir)
    a správu rozšírení.
    """

    def __init__(self, custom_executable: str = None):
        # Na Windows je 'code' v PATH typicky code.cmd alebo code.exe
        self.executable = custom_executable or ("code.cmd" if os.name == "nt" else "code")

        self._commands: dict[str, Callable[..., list[str]]] = {
            "launch_project": self._build_launch_project_command,
            "launch_file": self._build_launch_file_command,
            "install_extension": lambda **kwargs: [
                self.executable,
                "--install-extension",
                kwargs["extension_id"],
            ],
            "list_extensions": lambda **kwargs: [
                self.executable,
                "--list-extensions",
            ],
            "version": lambda **kwargs: [
                self.executable,
                "--version",
            ],
            "uninstall_extension": lambda **kwargs: [
                self.executable,
                "--uninstall-extension",
                kwargs["extension_id"],
            ],
        }

    def _build_launch_project_command(self, **kwargs: Any) -> list[str]:
        """
        Zostaví príkaz pre otvorenie celého projektu vo VS Code.
        Podporuje voliteľné oddelené používateľské dáta a rozšírenia.
        """
        project_path = kwargs.get("project_path", "")
        user_data_dir = kwargs.get("user_data_dir")
        extensions_dir = kwargs.get("extensions_dir")
        extra_args = kwargs.get("extra_args", [])

        cmd = [self.executable]

        if user_data_dir and os.path.exists(user_data_dir):
            cmd.extend(["--user-data-dir", user_data_dir])

        if extensions_dir and os.path.exists(extensions_dir):
            cmd.extend(["--extensions-dir", extensions_dir])

        if extra_args:
            cmd.extend(extra_args)

        if project_path:
            cmd.append(project_path)

        return cmd

    def _build_launch_file_command(self, **kwargs: Any) -> list[str]:
        """Zostaví príkaz pre otvorenie konkrétneho súboru (voliteľne aj s číslom riadku)."""
        file_path = kwargs.get("file_path", "")
        line_number = kwargs.get("line_number")
        user_data_dir = kwargs.get("user_data_dir")
        extensions_dir = kwargs.get("extensions_dir")

        cmd = [self.executable]

        if user_data_dir and os.path.exists(user_data_dir):
            cmd.extend(["--user-data-dir", user_data_dir])

        if extensions_dir and os.path.exists(extensions_dir):
            cmd.extend(["--extensions-dir", extensions_dir])

        if line_number:
            cmd.extend(["-g", f"{file_path}:{line_number}"])
        elif file_path:
            cmd.append(file_path)

        return cmd

    def get(self, command_key: str, **kwargs: Any) -> list[str]:
        """Vráti hotový poskladaný zoznam CLI argumentov podľa kľúča."""
        if command_key not in self._commands:
            err_msg = LanguageManager.get(
                "vscode_cmd_err_invalid",
                "Príkaz '{cmd}' neexistuje v VSCodeCommandDispatcher."
            ).format(cmd=command_key)
            raise KeyError(err_msg)

        return self._commands[command_key](**kwargs)
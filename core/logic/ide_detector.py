#----------------------------------------
# Súbor: core/logic/ide_detector.py
#----------------------------------------

import os
import shutil
import threading
import time


class IDEDetector:
    """
    Bleskový detektor dostupnosti systémových inštalácií VS Code a Cursor AI.
    Prehľadáva Windows Register, systémovú premennú PATH a štandardné cesty.
    Stav drží v pamäti (RAM) pre okamžitý prístup.
    """

    # --- PAMÄŤOVÉ PREMENNÉ (STAVY V RAM) ---
    vs_code_system: bool = False
    cursor_system: bool = False

    vs_code_path: str | None = None
    cursor_path: str | None = None

    _was_checked: bool = False

    @classmethod
    def detect_all(cls, force_refresh: bool = False):
        """
        Vykoná kompletnú detekciu oboch editorov v systéme
        a zapíše stavy True / False priamo do pamäte triedy.
        """
        if cls._was_checked and not force_refresh:
            return

        cls.vs_code_path = cls._find_vscode()
        cls.vs_code_system = cls.vs_code_path is not None

        cls.cursor_path = cls._find_cursor()
        cls.cursor_system = cls.cursor_path is not None

        cls._was_checked = True

    # =========================================================================
    # --- DETEKCIA VS CODE ---
    # =========================================================================
    @classmethod
    def _find_vscode(cls) -> str | None:
        # 1. Kontrola v systémovej PATH
        cmd_path = shutil.which("code.cmd") or shutil.which("code")
        if cmd_path and os.path.exists(cmd_path):
            return os.path.normpath(cmd_path)

        # 2. Kontrola vo Windows Registri
        if os.name == "nt":
            reg_path = cls._check_registry_app_paths("Code.exe")
            if reg_path:
                bin_cmd = os.path.join(os.path.dirname(reg_path), "bin", "code.cmd")
                return os.path.normpath(bin_cmd if os.path.exists(bin_cmd) else reg_path)

            reg_uninstall = cls._check_registry_uninstall("Visual Studio Code", "code.cmd")
            if reg_uninstall:
                return os.path.normpath(reg_uninstall)

            # 3. Priama kontrola predvolených systémových priečinkov
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")

            candidates = [
                os.path.join(local_appdata, "Programs", "Microsoft VS Code", "bin", "code.cmd"),
                os.path.join(local_appdata, "Programs", "Microsoft VS Code", "Code.exe"),
                os.path.join(program_files, "Microsoft VS Code", "bin", "code.cmd"),
                os.path.join(program_files, "Microsoft VS Code", "Code.exe"),
            ]
            for p in candidates:
                if p and os.path.exists(p):
                    return os.path.normpath(p)

        return None

    # =========================================================================
    # --- DETEKCIA CURSOR AI ---
    # =========================================================================
    @classmethod
    def _find_cursor(cls) -> str | None:
        # 1. Kontrola v systémovej PATH
        cmd_path = shutil.which("cursor.cmd") or shutil.which("cursor")
        if cmd_path and os.path.exists(cmd_path):
            return os.path.normpath(cmd_path)

        # 2. Kontrola vo Windows Registri
        if os.name == "nt":
            reg_path = cls._check_registry_app_paths("Cursor.exe")
            if reg_path:
                # Skúsime nájsť CLI skript v resources/app/bin alebo bin
                parent = os.path.dirname(reg_path)
                candidates = [
                    os.path.join(parent, "resources", "app", "bin", "cursor.cmd"),
                    os.path.join(parent, "bin", "cursor.cmd"),
                    reg_path
                ]
                for c in candidates:
                    if os.path.exists(c):
                        return os.path.normpath(c)

            reg_uninstall = cls._check_registry_uninstall("Cursor", "cursor.cmd")
            if reg_uninstall:
                return os.path.normpath(reg_uninstall)

            # 3. Priama kontrola predvolených systémových priečinkov
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            program_files = os.environ.get("ProgramFiles", "C:\\Program Files")

            candidates = [
                os.path.join(local_appdata, "Programs", "cursor", "resources", "app", "bin", "cursor.cmd"),
                os.path.join(local_appdata, "Programs", "cursor", "Cursor.exe"),
                os.path.join(local_appdata, "Programs", "Cursor", "Cursor.exe"),
                os.path.join(program_files, "Cursor", "resources", "app", "bin", "cursor.cmd"),
                os.path.join(program_files, "Cursor", "Cursor.exe"),
            ]
            for p in candidates:
                if p and os.path.exists(p):
                    return os.path.normpath(p)

        return None

    # =========================================================================
    # --- POMOCNÉ METÓDY PRE WINDOWS REGISTER ---
    # =========================================================================
    @staticmethod
    def _check_registry_app_paths(exe_name: str) -> str | None:
        """Hľadá v kľúčoch App Paths (HKEY_CURRENT_USER a HKEY_LOCAL_MACHINE)."""
        import winreg
        sub_key = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"

        for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            try:
                with winreg.OpenKey(root, sub_key) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
        return None

    @staticmethod
    def _check_registry_uninstall(search_name: str, cli_name: str) -> str | None:
        """Prehľadá záznamy v Uninstall vetvách Windows Registra."""
        import winreg
        roots = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        for root_key, sub_path in roots:
            try:
                with winreg.OpenKey(root_key, sub_path) as parent_key:
                    num_subkeys = winreg.QueryInfoKey(parent_key)[0]
                    for i in range(num_subkeys):
                        try:
                            key_name = winreg.EnumKey(parent_key, i)
                            with winreg.OpenKey(parent_key, key_name) as app_key:
                                try:
                                    disp_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                except Exception:
                                    disp_name = ""

                                if search_name.lower() in str(disp_name).lower():
                                    try:
                                        install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                    except Exception:
                                        install_loc = ""

                                    if install_loc and os.path.exists(install_loc):
                                        # Hľadáme bin/code.cmd alebo bin/cursor.cmd
                                        cli_path = os.path.join(install_loc, "bin", cli_name)
                                        if os.path.exists(cli_path):
                                            return cli_path
                                        res_cli = os.path.join(install_loc, "resources", "app", "bin", cli_name)
                                        if os.path.exists(res_cli):
                                            return res_cli
                                        return install_loc
                        except Exception:
                            continue
            except Exception:
                pass

        return None

    # =========================================================================
    # --- VEREJNÉ METÓDY PRE CELÚ APLIKÁCIU ---
    # =========================================================================
    @classmethod
    def is_vscode_available(cls) -> bool:
        """Vráti True, ak je VS Code nainštalovaný v systéme."""
        cls.detect_all()
        return cls.vs_code_system

    @classmethod
    def is_cursor_available(cls) -> bool:
        """Vráti True, ak je Cursor AI nainštalovaný v systéme."""
        cls.detect_all()
        return cls.cursor_system

    @classmethod
    def get_vscode_executable(cls) -> str:
        """Vráti cestu k binárke VS Code alebo predvolený 'code' príkaz."""
        cls.detect_all()
        return cls.vs_code_path or "code"

    @classmethod
    def get_cursor_executable(cls) -> str:
        """Vráti cestu k binárke Cursor alebo predvolený 'cursor' príkaz."""
        cls.detect_all()
        return cls.cursor_path or "cursor"
    
    # --- PREMENNÉ PRE 2s SCANNER ---
    _is_running: bool = False
    _scan_thread: threading.Thread | None = None

    @classmethod
    def start_listening(cls):
        """
        1. Okamžitý scan pri štarte (T = 0s).
        2. Spustenie samostatného vlákna na pozadí každé 2s (T = 2s, 4s, 6s...).
        """
        # Okamžitá detekcia pri štarte
        cls.detect_all(force_refresh=True)

        if cls._is_running:
            return

        cls._is_running = True

        def _loop():
            while cls._is_running:
                time.sleep(2)
                if not cls._is_running:
                    break
                cls.detect_all(force_refresh=True)

        cls._scan_thread = threading.Thread(target=_loop, daemon=True, name="IDEDetectorScanner")
        cls._scan_thread.start()

    @classmethod
    def stop_listening(cls):
        """Zastaví bežiaci 2s scan na pozadí."""
        cls._is_running = False
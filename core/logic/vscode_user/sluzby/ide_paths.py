#----------------------------------------------------
# Súbor: core/logic/vscode_user/sluzby/ide_paths.py
# Nízkoúrovňová služba pre detekciu ciest na disku.
# ZÁVISLOSTI: 0 (Iba štandardná knižnica Pythonu: os, sys, shutil).
#----------------------------------------------------

import os
import sys
import shutil


class IDEPaths:
    """
    Čistý nízkoúrovňový detektor ciest.
    Nerieši žiadne Enumy ani biznis logiku – len holé súbory na disku.
    """

    CANDIDATES = {
        "vscode": ["code.cmd", "code.exe", "Code.exe"],
        "cursor": ["cursor.cmd", "cursor.exe", "Cursor.exe"]
    }

    # =========================================================================
    # 1. PREHĽADÁVANIE PRIEČINKA (PORTABLE / USB)
    # =========================================================================
    @staticmethod
    def find_executable_in_dir(directory: str, candidates: list[str]) -> str | None:
        if not directory or not os.path.exists(directory):
            return None

        for cand in candidates:
            p_root = os.path.join(directory, cand)
            if os.path.isfile(p_root):
                return os.path.normpath(p_root)

            p_bin = os.path.join(directory, "bin", cand)
            if os.path.isfile(p_bin):
                return os.path.normpath(p_bin)

            p_res = os.path.join(directory, "resources", "app", "bin", cand)
            if os.path.isfile(p_res):
                return os.path.normpath(p_res)

        return None

    # =========================================================================
    # 2. PREHĽADÁVANIE SYSTÉMU (PATH, REGISTRE, DEFAULT CESTY)
    # =========================================================================
    @classmethod
    def find_system_executable(cls, ide_type: str) -> str | None:
        key = "cursor" if ide_type == "cursor" else "vscode"
        candidates = cls.CANDIDATES.get(key, [])

        # 1. PATH
        for cand in candidates:
            found = shutil.which(cand)
            if found and os.path.isfile(found):
                return os.path.normpath(found)

        if os.name != "nt":
            return None

        # 2. Windows Register
        reg_exe = "Cursor.exe" if key == "cursor" else "Code.exe"
        reg_path = cls._check_registry_app_paths(reg_exe)
        if reg_path and os.path.exists(reg_path):
            parent = os.path.dirname(reg_path)
            found = cls.find_executable_in_dir(parent, candidates)
            if found:
                return found
            if os.path.isfile(reg_path):
                return os.path.normpath(reg_path)

        reg_search_name = "Cursor" if key == "cursor" else "Visual Studio Code"
        reg_cli_name = "cursor.cmd" if key == "cursor" else "code.cmd"
        reg_uninstall = cls._check_registry_uninstall(reg_search_name, reg_cli_name)
        if reg_uninstall and os.path.exists(reg_uninstall):
            return os.path.normpath(reg_uninstall)

        # 3. Predvolené priečinky
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")

        if key == "cursor":
            search_dirs = [
                os.path.join(local_appdata, "Programs", "cursor"),
                os.path.join(local_appdata, "Programs", "Cursor"),
                os.path.join(program_files, "Cursor"),
            ]
        else:
            search_dirs = [
                os.path.join(local_appdata, "Programs", "Microsoft VS Code"),
                os.path.join(program_files, "Microsoft VS Code"),
            ]

        for s_dir in search_dirs:
            found = cls.find_executable_in_dir(s_dir, candidates)
            if found:
                return found

        return None

    # =========================================================================
    # 3. ZISTENIE CIEL CIEL PRE SÚBORY A PROFILY
    # =========================================================================
    @classmethod
    def get_raw_executable_info(cls, ide_type: str, portable_path: str = "") -> tuple[str, str | None]:
        """
        Zistí holý fakt: ("portable" | "system" | "not_found", cesta_k_binarke | None)
        """
        key = "cursor" if ide_type == "cursor" else "vscode"
        candidates = cls.CANDIDATES.get(key, [])

        if portable_path and os.path.exists(portable_path):
            port_exe = cls.find_executable_in_dir(portable_path, candidates)
            if port_exe:
                return "portable", port_exe

        sys_exe = cls.find_system_executable(key)
        if sys_exe:
            return "system", sys_exe

        return "not_found", None

    @staticmethod
    def get_raw_profile_paths(users_root: str, active_user_id: str, ide_type: str = "vscode") -> tuple[str, str, str]:
        """
        Zistí holý fakt o cestách: ("custom" | "system_default", user_data_dir, extensions_dir)
        """
        key = "cursor" if ide_type == "cursor" else "vscode"

        # 1. Custom profil
        if users_root and active_user_id and os.path.exists(users_root):
            profile_dir = os.path.join(users_root, key, active_user_id)
            if os.path.exists(profile_dir):
                user_data_dir = os.path.join(profile_dir, "data")
                extensions_dir = os.path.join(profile_dir, "data", "extensions")
                return "custom", user_data_dir, extensions_dir

        # 2. Systémový profil OS
        userprofile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
        appdata = os.environ.get("APPDATA", os.path.join(userprofile, "AppData", "Roaming"))

        if key == "cursor":
            extensions_dir = os.path.join(userprofile, ".cursor", "extensions")
            user_data_dir = os.path.join(appdata, "Cursor", "User")
        else:
            extensions_dir = os.path.join(userprofile, ".vscode", "extensions")
            user_data_dir = os.path.join(appdata, "Code", "User")

        return "system_default", user_data_dir, extensions_dir

    # =========================================================================
    # 4. INTERNÉ POMOCNÉ METÓDY PRE REGISTER
    # =========================================================================
    @staticmethod
    def _check_registry_app_paths(exe_name: str) -> str | None:
        try:
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
        except ImportError:
            pass
        return None

    @staticmethod
    def _check_registry_uninstall(search_name: str, cli_name: str) -> str | None:
        try:
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
                                            cli_path = os.path.join(install_loc, "bin", cli_name)
                                            if os.path.isfile(cli_path):
                                                return cli_path
                                            res_cli = os.path.join(install_loc, "resources", "app", "bin", cli_name)
                                            if os.path.isfile(res_cli):
                                                return res_cli
                                            return install_loc
                            except Exception:
                                continue
                except Exception:
                    pass
        except ImportError:
            pass
        return None
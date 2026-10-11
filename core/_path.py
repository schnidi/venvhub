#----------------------------------------
# Súbor: core/_path.py (FINÁLNA VERZIA PRE DUAL-THEME SYSTÉM + PYTHON INSTALLER + AUTOSTART + IDE)
#----------------------------------------

import os
import sys

class Paths:
    """
    Centrálna trieda pre správu ciest.
    Podporuje "Hybridný" systém tém (Vstavané v jadre + Užívateľské vedľa EXE alebo v AppData).
    """
    
    # --- Názvy súborov a priečinkov ---
    TRANSLATIONS_DIR_NAME = "translations"
    UI_DIR_NAME = "ui"
    STYLE_QSS_NAME = "style.qss"
    ICON_DIR_NAME = "icon"
    THEMES_DIR_NAME = "themes"
    
    CONFIG_FILE_NAME = "venv_hub_pro_config.json"
    PYVENV_CFG_NAME = "pyvenv.cfg"
    VENV_SCRIPTS_DIR_NAME = "Scripts"
    PYTHON_EXE_NAME = "python.exe"
    REQUIREMENTS_FILE_NAME = "requirements.txt"
    VENV_ACTIVATE_BAT_NAME = "activate.bat"
    
    APP_DATA_DIR_NAME = "VenvHubPro"
    PORTABLE_MARKER_FILENAME = "_is_portable.ini"
    APP_ICON_NAME = "app.ico"
    
    # --- KONŠTANTY PRE PYTHON INSTALLER A AUTOSTART ---
    ASSETS_DIR_NAME = "assets"
    PYTHON_VERSIONS_JSONL_NAME = "jso_python_ver.jsonl"
    AUTOSTART_DIR_NAME = "autostart_multi"

    # --- KONŠTANTY PRE IDE EDITORY (VS CODE & CURSOR) ---
    VSCODE_DIR_NAME = ".vscode"
    CURSOR_DIR_NAME = ".cursor"
    IDE_CONFIG_DIR_NAMES = [".vscode", ".cursor"]

    SETTINGS_JSON_NAME = "settings.json"
    TASKS_JSON_NAME = "tasks.json"
    KEYBINDINGS_JSON_NAME = "keybindings.json"
    VENVHUB_TRACKER_JSON_NAME = "venvhub_tracker.json"

    @staticmethod
    def get_base_path() -> str:
        """Vráti cestu k interným súborom (_internal)."""
        if getattr(sys, 'frozen', False):
            return sys._MEIPASS
        else:
            return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    @staticmethod
    def get_app_root_path() -> str:
        """Vráti cestu kde leží .exe súbor (alebo main.py)."""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        else:
            return os.path.dirname(os.path.abspath(sys.argv[0]))

    @staticmethod
    def get_themes_dir() -> str:
        return os.path.join(Paths.get_base_path(), "core", Paths.THEMES_DIR_NAME)

    @staticmethod
    def get_user_themes_dir() -> str:
        exe_dir = Paths.get_app_root_path()
        portable_marker = os.path.join(exe_dir, Paths.PORTABLE_MARKER_FILENAME)
        
        if os.path.exists(portable_marker) or not getattr(sys, 'frozen', False):
            path_to_create = os.path.join(exe_dir, Paths.THEMES_DIR_NAME)
        else:
            try:
                appdata_path = os.environ['APPDATA']
                path_to_create = os.path.join(appdata_path, Paths.APP_DATA_DIR_NAME, Paths.THEMES_DIR_NAME)
            except Exception:
                path_to_create = os.path.join(exe_dir, Paths.THEMES_DIR_NAME)

        if not os.path.exists(path_to_create):
            try: os.makedirs(path_to_create, exist_ok=True)
            except OSError: pass
                
        return path_to_create

    @staticmethod
    def get_autostart_multi_dir() -> str:
        exe_dir = Paths.get_app_root_path()
        portable_marker = os.path.join(exe_dir, Paths.PORTABLE_MARKER_FILENAME)
        
        if os.path.exists(portable_marker) or not getattr(sys, 'frozen', False):
            path_to_create = os.path.join(exe_dir, Paths.ASSETS_DIR_NAME, Paths.AUTOSTART_DIR_NAME)
        else:
            try:
                appdata_path = os.environ['APPDATA']
                path_to_create = os.path.join(appdata_path, Paths.APP_DATA_DIR_NAME, Paths.AUTOSTART_DIR_NAME)
            except Exception:
                path_to_create = os.path.join(exe_dir, Paths.ASSETS_DIR_NAME, Paths.AUTOSTART_DIR_NAME)

        if not os.path.exists(path_to_create):
            try: os.makedirs(path_to_create, exist_ok=True)
            except OSError: pass
            
        return path_to_create

    @staticmethod
    def get_autostart_file_path(group_name: str) -> str:
        safe_name = "".join(c for c in group_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_name}.json"
        return os.path.join(Paths.get_autostart_multi_dir(), filename)

    @staticmethod
    def get_config_file_path() -> str:
        exe_dir = Paths.get_app_root_path()
        portable_marker = os.path.join(exe_dir, Paths.PORTABLE_MARKER_FILENAME)
        if os.path.exists(portable_marker) or not getattr(sys, 'frozen', False):
            return os.path.join(exe_dir, Paths.CONFIG_FILE_NAME)
        try:
            appdata_path = os.environ['APPDATA']
            app_dir = os.path.join(appdata_path, Paths.APP_DATA_DIR_NAME)
            if not os.path.exists(app_dir): os.makedirs(app_dir, exist_ok=True)
            return os.path.join(app_dir, Paths.CONFIG_FILE_NAME)
        except Exception:
            return os.path.join(exe_dir, Paths.CONFIG_FILE_NAME)

    @staticmethod
    def get_translations_dir() -> str: return os.path.join(Paths.get_base_path(), Paths.TRANSLATIONS_DIR_NAME)
    @staticmethod
    def get_ui_file_path(ui_filename: str) -> str: return os.path.join(Paths.get_base_path(), Paths.UI_DIR_NAME, ui_filename)
    @staticmethod
    def get_translation_file_path(lang_filename: str) -> str: return os.path.join(Paths.get_base_path(), Paths.TRANSLATIONS_DIR_NAME, lang_filename)
    @staticmethod
    def get_qss_style_path() -> str: return os.path.join(Paths.get_base_path(), "core", Paths.THEMES_DIR_NAME, Paths.STYLE_QSS_NAME)
    @staticmethod
    def get_icon_path(icon_filename: str) -> str: return os.path.join(Paths.get_base_path(), "core", Paths.THEMES_DIR_NAME, Paths.ICON_DIR_NAME, icon_filename)
    @staticmethod
    def get_app_icon_path() -> str: return os.path.join(Paths.get_app_root_path(), Paths.APP_ICON_NAME)
    @staticmethod
    def get_project_path(projects_root: str, project_name: str) -> str: return os.path.join(projects_root, project_name)
    @staticmethod
    def get_venv_path(venv_hub_root: str, venv_full_name: str) -> str: return os.path.join(venv_hub_root, venv_full_name)
    @staticmethod
    def get_pyvenv_cfg_path(venv_path: str) -> str: return os.path.join(venv_path, Paths.PYVENV_CFG_NAME)
    @staticmethod
    def get_venv_python_exe_path(venv_path: str) -> str: return os.path.join(venv_path, Paths.VENV_SCRIPTS_DIR_NAME, Paths.PYTHON_EXE_NAME)
    @staticmethod
    def get_requirements_txt_path(project_root: str) -> str: return os.path.join(project_root, Paths.REQUIREMENTS_FILE_NAME)
    @staticmethod
    def get_venv_activate_bat_path(venv_path: str) -> str: return os.path.join(venv_path, Paths.VENV_SCRIPTS_DIR_NAME, Paths.VENV_ACTIVATE_BAT_NAME)
    @staticmethod
    def get_script_in_project_path(project_path: str, script_name: str) -> str: return os.path.join(project_path, script_name)
    @staticmethod
    def get_python_executable_path(venv_path):
        if sys.platform == "win32": return os.path.join(venv_path, "Scripts", "python.exe")
        else: return os.path.join(venv_path, "bin", "python")
    @staticmethod
    def get_python_versions_jsonl_path() -> str: return os.path.join(Paths.get_base_path(), Paths.ASSETS_DIR_NAME, Paths.PYTHON_VERSIONS_JSONL_NAME)
    
    @staticmethod
    def get_python_runtimes_install_dir() -> str:
        exe_dir = Paths.get_app_root_path()
        portable_marker = os.path.join(exe_dir, Paths.PORTABLE_MARKER_FILENAME)
        
        # 1. Prenosný (portable) alebo vývojársky režim
        if os.path.exists(portable_marker) or not getattr(sys, 'frozen', False):
            return os.path.join(exe_dir, "PyRuntimes")
            
        # 2. Prvoradá voľba pre inštalovaný režim: Spoločný priečinok v ProgramData (NEPOTREBUJE UAC)
        program_data = os.environ.get('PROGRAMDATA', "C:\\ProgramData")
        shared_dir = os.path.join(program_data, "VenvHubPro", "PyRuntimes")
        
        try:
            os.makedirs(shared_dir, exist_ok=True)
            test_file = os.path.join(shared_dir, ".write_test")
            with open(test_file, 'w', encoding='utf-8') as f:
                f.write('test')
            os.remove(test_file)
            return shared_dir
            
        except (OSError, PermissionError):
            # 3. Druhoradá voľba (Fallback): Používateľské AppData
            local_appdata = os.environ.get('LOCALAPPDATA')
            if not local_appdata:
                local_appdata = os.path.expanduser('~\\AppData\\Local')
            return os.path.join(local_appdata, Paths.APP_DATA_DIR_NAME, "PyRuntimes")
            
    @staticmethod
    def get_python_downloads_dir() -> str:
        exe_dir = Paths.get_app_root_path()
        portable_marker = os.path.join(exe_dir, Paths.PORTABLE_MARKER_FILENAME)
        
        # 1. Ak bežíme v prenosnom (portable) alebo vývojárskom režime, downloady smerujú výhradne vedľa appky
        if os.path.exists(portable_marker) or not getattr(sys, 'frozen', False):
            temp_dir = os.path.join(exe_dir, "Downloads")
            try:
                os.makedirs(temp_dir, exist_ok=True)
                return temp_dir
            except OSError:
                pass
                
        # 2. Ak ide o štandardnú inštaláciu, ukladáme do bezpečného APPDATA hostiteľa
        try:
            appdata_path = os.environ['APPDATA']
            temp_dir = os.path.join(appdata_path, Paths.APP_DATA_DIR_NAME, "Downloads")
            os.makedirs(temp_dir, exist_ok=True)
            return temp_dir
        except Exception:
            # Krajný fallback, ak by systémové APPDATA zlyhalo
            temp_dir = os.path.join(exe_dir, "Downloads")
            os.makedirs(temp_dir, exist_ok=True)
            return temp_dir

    # --- METÓDY PRE PROJEKTOVÉ IDE CIESTY (VS CODE & CURSOR) ---
    @staticmethod
    def get_project_ide_dir(project_path: str, ide_dir_name: str) -> str:
        """Vráti cestu k priečinku editora v projekte (napr. /Projekt/.vscode alebo /Projekt/.cursor)."""
        return os.path.join(project_path, ide_dir_name)

    @staticmethod
    def get_all_project_ide_dirs(project_path: str) -> list[str]:
        """Vráti zoznam všetkých IDE priečinkov v projekte (.vscode a .cursor)."""
        return [os.path.join(project_path, name) for name in Paths.IDE_CONFIG_DIR_NAMES]

    @staticmethod
    def get_project_ide_file_path(project_path: str, ide_dir_name: str, file_name: str) -> str:
        """Vráti cestu ku konkrétnemu súboru (napr. /Projekt/.cursor/settings.json)."""
        return os.path.join(project_path, ide_dir_name, file_name)
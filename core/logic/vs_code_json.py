#----------------------------------------
# Súbor: core/logic/vs_code_json.py (DUÁLNA SYNCHRONIZÁCIA: VS CODE + CURSOR)
#----------------------------------------

import os
import json
from core._path import Paths
from core.logic.language_manager import LanguageManager


class VSCodeIntegration:
    """
    Centrálny manažér konfigurácií pre vývojové editory (VS Code a Cursor AI).
    Všetky nastavenia (interpreter, venvPath, extraPaths, tasks, keybindings, settings)
    udržiava v plnej a nezávislej synchronizácii pre oba editory.
    """

    # =========================================================================
    # 1. INICIALIZÁCIA A NASTAVENIE INTERPRETRA (PRE OBA EDITORY)
    # =========================================================================

    @staticmethod
    def initialize_project_settings(project_path: str, venv_path: str):
        """Vytvorí počiatočné nastavenia pre .vscode aj .cursor pri vzniku venvu."""
        if not project_path or not venv_path:
            return

        python_exe = Paths.get_venv_python_exe_path(venv_path).replace("\\", "/")
        venv_hub_root = os.path.dirname(os.path.normpath(venv_path)).replace("\\", "/")

        for ide_dir_name in Paths.IDE_CONFIG_DIR_NAMES:
            ide_folder = Paths.get_project_ide_dir(project_path, ide_dir_name)
            settings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.SETTINGS_JSON_NAME)

            try:
                os.makedirs(ide_folder, exist_ok=True)
            except OSError:
                continue

            config = VSCodeIntegration._load_json(settings_file) or {}

            # Ak interpreter ešte nie je definovaný, zapíšeme ho aj s venvPath
            if "python.defaultInterpreterPath" not in config:
                config["python.defaultInterpreterPath"] = python_exe
                config["python.venvPath"] = venv_hub_root
                config["python.terminal.activateEnvironment"] = True
                VSCodeIntegration._save_json(settings_file, config)

    @staticmethod
    def set_default_interpreter(project_path: str, venv_path: str):
        """Nastaví a prepíše predvolený interpreter a venvPath v .vscode aj .cursor."""
        if not project_path or not venv_path:
            return

        python_exe = Paths.get_venv_python_exe_path(venv_path).replace("\\", "/")
        venv_hub_root = os.path.dirname(os.path.normpath(venv_path)).replace("\\", "/")

        for ide_dir_name in Paths.IDE_CONFIG_DIR_NAMES:
            ide_folder = Paths.get_project_ide_dir(project_path, ide_dir_name)
            settings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.SETTINGS_JSON_NAME)

            try:
                os.makedirs(ide_folder, exist_ok=True)
            except OSError:
                continue

            config = VSCodeIntegration._load_json(settings_file) or {}

            # Zápis oboch kľúčov pre plnú funkčnosť VS Code aj Cursoru
            config["python.defaultInterpreterPath"] = python_exe
            config["python.venvPath"] = venv_hub_root
            config["python.terminal.activateEnvironment"] = True

            # Odstránenie starého nepoužívaného envFile
            if "python.envFile" in config:
                del config["python.envFile"]

            VSCodeIntegration._save_json(settings_file, config)

    @staticmethod
    def remove_vscode_sync(project_path: str):
        """Odstráni väzbu na venv zo všetkých IDE priečinkov pri zmazaní venvu."""
        if not project_path or not os.path.exists(project_path):
            return

        for ide_dir_name in Paths.IDE_CONFIG_DIR_NAMES:
            ide_folder = Paths.get_project_ide_dir(project_path, ide_dir_name)
            settings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.SETTINGS_JSON_NAME)

            if not os.path.exists(settings_file):
                continue

            config = VSCodeIntegration._load_json(settings_file)
            if not config:
                continue

            keys_to_remove = ["python.defaultInterpreterPath", "python.venvPath", "python.terminal.activateEnvironment"]
            modified = False
            for key in keys_to_remove:
                if key in config:
                    del config[key]
                    modified = True

            if modified:
                if not config:
                    try:
                        os.remove(settings_file)
                        if os.path.exists(ide_folder) and not os.listdir(ide_folder):
                            os.rmdir(ide_folder)
                    except OSError:
                        pass
                else:
                    VSCodeIntegration._save_json(settings_file, config)

    # =========================================================================
    # 2. OPRAVA CIEST PRI PRENOSE (PORTABLE AUTO-REPAIR)
    # =========================================================================

    @staticmethod
    def repair_portable_path(project_path: str, new_venv_path: str, local_packages_root: str = ""):
        """Opraví cesty v .vscode aj .cursor po zmene písmena USB disku."""
        if not project_path or not new_venv_path:
            return

        new_py_path = Paths.get_venv_python_exe_path(new_venv_path).replace("\\", "/")
        new_hub_root = os.path.dirname(os.path.normpath(new_venv_path)).replace("\\", "/")

        for ide_dir_name in Paths.IDE_CONFIG_DIR_NAMES:
            settings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.SETTINGS_JSON_NAME)

            if not os.path.exists(settings_file):
                continue

            try:
                config = VSCodeIntegration._load_json(settings_file)
                if not config:
                    continue

                old_py_path = config.get("python.defaultInterpreterPath")
                if not old_py_path:
                    continue

                modified = False

                if old_py_path.lower() != new_py_path.lower():
                    config["python.defaultInterpreterPath"] = new_py_path
                    config["python.venvPath"] = new_hub_root
                    modified = True

                if local_packages_root and "python.analysis.extraPaths" in config:
                    old_extra_paths = config["python.analysis.extraPaths"]
                    new_extra_paths = []
                    for path in old_extra_paths:
                        if "site-packages" in path:
                            parts = path.replace("\\", "/").split("/site-packages/")
                            if len(parts) == 2:
                                site_folder = "Lib" if os.name == 'nt' else "lib"
                                new_site_path = os.path.join(new_venv_path, site_folder, "site-packages", parts[1]).replace("\\", "/")
                                new_extra_paths.append(new_site_path)
                                if new_site_path != path:
                                    modified = True
                                continue
                        new_extra_paths.append(path)
                    config["python.analysis.extraPaths"] = new_extra_paths

                if modified:
                    VSCodeIntegration._save_json(settings_file, config)

            except Exception:
                pass

    # =========================================================================
    # 3. SYNCHRONIZÁCIA LOKÁLNYCH BALÍČKOV (EXTRA PATHS)
    # =========================================================================

    @staticmethod
    def sync_local_packages(project_path: str, selected_paths: list[str], local_packages_root: str):
        """Zosynchronizuje cesty lokálnych balíčkov pre Pylance v .vscode aj .cursor."""
        if not project_path:
            return

        for ide_dir_name in Paths.IDE_CONFIG_DIR_NAMES:
            ide_folder = Paths.get_project_ide_dir(project_path, ide_dir_name)
            settings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.SETTINGS_JSON_NAME)

            try:
                os.makedirs(ide_folder, exist_ok=True)
            except OSError:
                continue

            config = VSCodeIntegration._load_json(settings_file) or {}

            extra_paths = config.get("python.analysis.extraPaths", [])
            if not isinstance(extra_paths, list):
                extra_paths = []

            # Prečistíme staré cesty z nášho lokálneho priečinka
            if local_packages_root and os.path.exists(local_packages_root):
                norm_root = os.path.normpath(local_packages_root).replace("\\", "/").lower()
                extra_paths = [
                    p for p in extra_paths
                    if not os.path.normpath(p).replace("\\", "/").lower().startswith(norm_root)
                ]

            # Pridáme aktuálne vybrané
            for p in selected_paths:
                clean_p = os.path.normpath(p).replace("\\", "/")
                if clean_p not in extra_paths:
                    extra_paths.append(clean_p)

            if extra_paths:
                config["python.analysis.extraPaths"] = extra_paths
            else:
                if "python.analysis.extraPaths" in config:
                    del config["python.analysis.extraPaths"]

            VSCodeIntegration._save_json(settings_file, config)

    # =========================================================================
    # 4. TASKS, KEYBINDINGS, SETTINGS A TRACKER (ÚČTENKA) PRE OBA EDITORY
    # =========================================================================

    @staticmethod
    def sync_vscode_tasks_and_keybindings(project_path: str, selected_paths: list[str], local_packages_root: str, log_callback=None):
        """
        Vykoná synchronizáciu úloh, klávesových skratiek a nastavení pre všetky podporované IDE.
        Používa účtenku (tracker), takže nikdy nezmaže vlastné nastavenia ani úlohy používateľa.
        """
        def log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        log(LanguageManager.get("vscode_sync_start", "\n[IDE INTEGRATION SYNC] Spúšťam synchronizáciu IDE konfigurácie..."))

        if not project_path or not os.path.exists(project_path):
            log(LanguageManager.get("vscode_sync_err_no_project", "❌ CHYBA: project_path neexistuje."))
            return

        new_package_names = [os.path.basename(p) for p in selected_paths]

        for ide_dir_name in Paths.IDE_CONFIG_DIR_NAMES:
            ide_dir = Paths.get_project_ide_dir(project_path, ide_dir_name)
            os.makedirs(ide_dir, exist_ok=True)

            settings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.SETTINGS_JSON_NAME)
            tasks_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.TASKS_JSON_NAME)
            keybindings_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.KEYBINDINGS_JSON_NAME)
            tracker_file = Paths.get_project_ide_file_path(project_path, ide_dir_name, Paths.VENVHUB_TRACKER_JSON_NAME)

            existing_settings = VSCodeIntegration._load_json(settings_file) or {}
            existing_tasks = VSCodeIntegration._load_json(tasks_file) or {"version": "2.0.0", "tasks": []}
            existing_keybindings = VSCodeIntegration._load_json(keybindings_file) or []
            tracker = VSCodeIntegration._load_json(tracker_file) or {}

            old_package_names = list(tracker.keys())
            packages_to_remove = [pkg for pkg in old_package_names if pkg not in new_package_names]

            modified_settings = False
            modified_tasks = False
            modified_keys = False

            # --- FÁZA 1: MAZANIE DEAKTIVOVANÝCH POLOŽIEK ---
            for pkg_name in packages_to_remove:
                tasks_to_remove = []
                keys_to_remove = []
                settings_to_remove = []

                pkg_dir = os.path.join(local_packages_root, pkg_name)
                meta_path = os.path.join(pkg_dir, "local_meta.json")
                read_from_disk = False

                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            vscode_int = meta.get("vscode_integration", {})
                            tasks_to_remove = [t.get("label") for t in vscode_int.get("tasks", []) if t.get("label")]
                            keys_to_remove = [{"key": k.get("key"), "command": k.get("command")} for k in vscode_int.get("keybindings", []) if k.get("key") and k.get("command")]
                            settings_to_remove = list(vscode_int.get("settings", {}).keys())
                            read_from_disk = True
                    except Exception:
                        pass

                if not read_from_disk:
                    tracker_data = tracker.get(pkg_name, {})
                    tasks_to_remove = tracker_data.get("tasks", [])
                    keys_to_remove = tracker_data.get("keybindings", [])
                    settings_to_remove = tracker_data.get("settings", [])

                # Čistenie Tasks
                if tasks_to_remove:
                    orig_len = len(existing_tasks.get("tasks", []))
                    existing_tasks["tasks"] = [t for t in existing_tasks.get("tasks", []) if t.get("label") not in tasks_to_remove]
                    if len(existing_tasks["tasks"]) != orig_len:
                        modified_tasks = True

                # Čistenie Keybindings
                if keys_to_remove:
                    orig_len = len(existing_keybindings)
                    existing_keybindings = [
                        k for k in existing_keybindings
                        if not any(rem.get("key") == k.get("key") and rem.get("command") == k.get("command") for rem in keys_to_remove)
                    ]
                    if len(existing_keybindings) != orig_len:
                        modified_keys = True

                # Čistenie Settings (iba kľúče pridané týmto balíčkom!)
                if settings_to_remove:
                    for s_key in settings_to_remove:
                        if s_key in existing_settings:
                            del existing_settings[s_key]
                            modified_settings = True

                del tracker[pkg_name]

            # --- FÁZA 2: INJEKCIA NOVÝCH POLOŽIEK ---
            for pkg_dir in selected_paths:
                pkg_name = os.path.basename(pkg_dir)
                meta_path = os.path.join(pkg_dir, "local_meta.json")

                if not os.path.exists(meta_path):
                    continue

                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)

                    vscode_int = meta.get("vscode_integration", {})
                    tasks = vscode_int.get("tasks", [])
                    keybindings = vscode_int.get("keybindings", [])
                    custom_settings = vscode_int.get("settings", {})

                    injected_tasks = []
                    injected_keys = []
                    injected_settings = []

                    # Injekcia úloh (Tasks)
                    for task in tasks:
                        label = task.get("label")
                        if label and not any(t.get("label") == label for t in existing_tasks.get("tasks", [])):
                            existing_tasks.setdefault("tasks", []).append(task)
                            modified_tasks = True
                            injected_tasks.append(label)

                    # Injekcia skratiek (Keybindings)
                    for kb in keybindings:
                        key = kb.get("key")
                        command = kb.get("command")
                        if key and command and not any(k.get("key") == key and k.get("command") == command for k in existing_keybindings):
                            existing_keybindings.append(kb)
                            modified_keys = True
                            injected_keys.append({"key": key, "command": command})

                    # Injekcia nastavení (Settings)
                    if custom_settings and isinstance(custom_settings, dict):
                        for s_key, s_val in custom_settings.items():
                            existing_settings[s_key] = s_val
                            modified_settings = True
                            injected_settings.append(s_key)

                    # Zápis do Trackeru
                    if injected_tasks or injected_keys or injected_settings or pkg_name in tracker:
                        tracker[pkg_name] = {
                            "tasks": injected_tasks,
                            "keybindings": injected_keys,
                            "settings": injected_settings
                        }

                except Exception as e:
                    msg = LanguageManager.get(
                        "vscode_sync_err_read",
                        "❌ Chyba pri čítaní {path}: {error}"
                    ).format(path=meta_path, error=e)
                    log(msg)

            # --- FÁZA 3: UKLADANIE SÚBOROV PRE DANÝ EDITOR ---
            if modified_settings:
                VSCodeIntegration._save_json(settings_file, existing_settings)

            if not existing_tasks.get("tasks"):
                if os.path.exists(tasks_file):
                    try:
                        os.remove(tasks_file)
                    except OSError:
                        pass
            elif modified_tasks:
                VSCodeIntegration._save_json(tasks_file, existing_tasks)

            if not existing_keybindings:
                if os.path.exists(keybindings_file):
                    try:
                        os.remove(keybindings_file)
                    except OSError:
                        pass
            elif modified_keys:
                VSCodeIntegration._save_json(keybindings_file, existing_keybindings)

            if not tracker:
                if os.path.exists(tracker_file):
                    try:
                        os.remove(tracker_file)
                    except OSError:
                        pass
            else:
                VSCodeIntegration._save_json(tracker_file, tracker)

        log(LanguageManager.get("vscode_sync_end", "--- Synchronizácia IDE ukončená ---"))

    # =========================================================================
    # 5. POMOCNÉ METÓDY PRE ČÍTANIE A ZÁPIS JSON
    # =========================================================================

    @staticmethod
    def _load_json(file_path: str):
        if not os.path.exists(file_path):
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                return json.loads(content) if content.strip() else None
        except Exception:
            return None

    @staticmethod
    def _save_json(file_path: str, data: dict) -> bool:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False
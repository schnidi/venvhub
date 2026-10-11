#----------------------------------------
# Súbor: core/logic/project_manager.py
#----------------------------------------

import os
import json
import re
from core._path import Paths

# --- IMPORTY LOGIKY CIEST ---
from core.logic.path_logic.portable import PortablePathLogic
from core.logic.path_logic.win_static import WinStaticPathLogic
from core.logic.path_logic.network_path import NetworkPathLogic

# --- IMPORT PRE PAMÄŤ PYTHONOV ---
from core.logic.python_detector import PythonDetector

# --- IMPORT PRE OPRAVU VS CODE CIEST ---
from core.logic.vs_code_json import VSCodeIntegration

class ProjectCore:
    def __init__(self):
        self.project_data = {}
        
        self.projects_root = ""
        self.venv_hub_root = ""
        self.local_packages_root = "" 
        self.pip_e_packages_root = ""
        self.vscode_users_root = ""  

        # --- ODDELENÉ PROFILY PRE VS CODE A CURSOR ---
        self.active_vscode_user = "" 
        self.active_cursor_user = "" 
        # ---------------------------------------------

        # --- NASTAVENIA PRE IDE EDITORY ---
        self.active_ide = "vscode"
        self.portable_vscode_path = ""
        self.portable_cursor_path = ""
        # ----------------------------------
        
        self._active_project = "" 
        self._temp_venv = None 

        self.run_mode = "run_in_terminal"
        self.last_pos = None
        self.language = "auto"
        self.active_theme = "default"
        self.app_mode = "single"
        self.active_multi_group = ""
        self.multi_groups = {}
        
        self.package_manager = "pip"

        self.is_portable = self._detect_portable_mode()

        self.load_config()
        
        PythonDetector.get_installed_pythons(force_refresh=True)

    def _detect_portable_mode(self) -> bool:
        app_root = Paths.get_app_root_path()
        marker_path = os.path.join(app_root, Paths.PORTABLE_MARKER_FILENAME)
        return os.path.exists(marker_path)

    # =========================================================================
    # --- POMOCNÉ METÓDY PRE ZÍSKANIE / NASTAVENIE PROFILU PODĽA AKTÍVNEHO IDE ---
    # =========================================================================
    def get_active_ide_user(self) -> str:
        """Vráti ID aktívneho profilu podľa toho, ktorý editor (IDE) je momentálne zvolený."""
        if self.active_ide == "cursor":
            return self.active_cursor_user
        return self.active_vscode_user

    def set_active_ide_user(self, user_id: str) -> None:
        """Nastaví ID profilu pre aktuálne zvolený editor (IDE)."""
        if self.active_ide == "cursor":
            self.active_cursor_user = user_id
        else:
            self.active_vscode_user = user_id

    # =========================================================================

    @property
    def active_project(self):
        return self._active_project

    @active_project.setter
    def active_project(self, value):
        if self._active_project != value:
            self._temp_venv = None
        self._active_project = value

    @property
    def active_venv_path(self):
        if self._temp_venv:
            return self._temp_venv
        if self._active_project and self._active_project in self.project_data:
            return self.project_data[self._active_project].get("venv", "")
        return ""

    @active_venv_path.setter
    def active_venv_path(self, value):
        if not self._active_project: return
        self._ensure_project_entry()
        self.project_data[self._active_project]["venv"] = value
        self._temp_venv = None

    def set_temporary_venv(self, value):
        self._temp_venv = value

    def get_project_default_venv(self):
        if self._active_project and self._active_project in self.project_data:
            return self.project_data[self._active_project].get("venv", "")
        return ""

    @property
    def last_script(self):
        if self._active_project and self._active_project in self.project_data:
            return self.project_data[self._active_project].get("script", "main.py")
        return "main.py"

    @last_script.setter
    def last_script(self, value):
        if not self._active_project: return
        self._ensure_project_entry()
        self.project_data[self._active_project]["script"] = value

    def _ensure_project_entry(self):
        if self._active_project not in self.project_data:
            self.project_data[self._active_project] = {}

    def load_config(self):
        config_path = Paths.get_config_file_path()
        if not os.path.exists(config_path):
            self.cfg = {}
            return

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.cfg = json.load(f)
        except:
            self.cfg = {}
            return

        self.projects_root = self.cfg.get("projects_root", "")
        self.venv_hub_root = self.cfg.get("venv_hub_root", "")
        self.local_packages_root = self.cfg.get("local_packages_root", "")
        self.pip_e_packages_root = self.cfg.get("pip_e_packages_root", "")
        self.vscode_users_root = self.cfg.get("vscode_users_root", "") 

        # --- NAČÍTANIE ODDELENÝCH PROFILOV ---
        self.active_vscode_user = self.cfg.get("active_vscode_user", "") 
        self.active_cursor_user = self.cfg.get("active_cursor_user", "") 
        # -------------------------------------

        # --- NAČÍTANIE NASTAVENÍ IDE ---
        self.active_ide = self.cfg.get("active_ide", "vscode")
        self.portable_vscode_path = self.cfg.get("portable_vscode_path", "")
        self.portable_cursor_path = self.cfg.get("portable_cursor_path", "")
        # -------------------------------
        
        # 1. DEKÓDOVANIE Z UUID DO REÁLNYCH CIEST V RAM
        if self.is_portable:
            self._apply_portable_path_fixes()

        self._active_project = self.cfg.get("active_project", "")
        self.run_mode = self.cfg.get("run_mode", "run_in_terminal")
        self.last_pos = self.cfg.get("last_pos", None)
        self.language = self.cfg.get("language", "auto")
        self.active_theme = self.cfg.get("active_theme", "default")
        self.app_mode = self.cfg.get("app_mode", "single")
        self.active_multi_group = self.cfg.get("active_multi_group", "")
        self.multi_groups = self.cfg.get("multi_groups", {})
        
        self.package_manager = self.cfg.get("package_manager", "pip")

        raw_project_data = self.cfg.get("project_data", {})
        root_missing = bool(self.projects_root) and not os.path.exists(self.projects_root)
        
        # 2. DEKÓDOVANIE CIEST PRE VENVY V JEDNOTLIVÝCH PROJEKTOCH
        cleaned_project_data = self._process_and_clean_data(raw_project_data)
        self.project_data = cleaned_project_data
        
        # 3. Uloženie len ak sa dáta skutočne zmenili
        if not (root_missing and cleaned_project_data == raw_project_data):
            self.save_config()

    def _apply_portable_path_fixes(self):
        new_proj_root, changed_p = PortablePathLogic.resolve_path(self.projects_root)
        if changed_p:
            self.projects_root = new_proj_root
            
        new_hub_root, changed_h = PortablePathLogic.resolve_path(self.venv_hub_root)
        if changed_h:
            self.venv_hub_root = new_hub_root

        new_local_root, changed_l = PortablePathLogic.resolve_path(self.local_packages_root)
        if changed_l:
            self.local_packages_root = new_local_root

        new_pip_e_root, changed_pe = PortablePathLogic.resolve_path(self.pip_e_packages_root)
        if changed_pe:
            self.pip_e_packages_root = new_pip_e_root

        new_vscode_root, changed_v = PortablePathLogic.resolve_path(self.vscode_users_root)
        if changed_v:
            self.vscode_users_root = new_vscode_root

        # --- PRENOSNÉ OPRAVY CIEST PRE IDE EDITORY ---
        new_port_vscode, changed_pvc = PortablePathLogic.resolve_path(self.portable_vscode_path)
        if changed_pvc:
            self.portable_vscode_path = new_port_vscode

        new_port_cursor, changed_pcur = PortablePathLogic.resolve_path(self.portable_cursor_path)
        if changed_pcur:
            self.portable_cursor_path = new_port_cursor
        # ---------------------------------------------

    def _process_and_clean_data(self, raw_data):
        clean_data = {}
        
        root_missing = not os.path.exists(self.projects_root)
        
        if root_missing:
            if NetworkPathLogic.is_unc_path(self.projects_root) or \
               not NetworkPathLogic.is_drive_root_available(self.projects_root):
                return raw_data
            return raw_data

        for proj_name, data in raw_data.items():
            full_project_path = Paths.get_project_path(self.projects_root, proj_name)
            
            if not os.path.exists(full_project_path):
                continue

            venv_path = data.get("venv", "")
            script_name = data.get("script", "") or "main.py"
            
            if venv_path:
                if self.is_portable:
                    fixed_venv, changed = PortablePathLogic.resolve_path(venv_path)
                    if changed:
                        venv_path = fixed_venv
                        # ========================================================
                        # OPRAVA PRE VS CODE / IDE: Tichá úprava settings.json
                        # ========================================================
                        VSCodeIntegration.repair_portable_path(full_project_path, fixed_venv, self.local_packages_root)
                
                if not os.path.exists(venv_path):
                    if NetworkPathLogic.is_unc_path(venv_path) or \
                       not NetworkPathLogic.is_drive_root_available(venv_path):
                        pass 
                    else:
                        venv_path = "" 

            full_script_path = Paths.get_script_in_project_path(full_project_path, script_name)
            if not os.path.exists(full_script_path):
                script_name = "main.py"

            clean_data[proj_name] = {
                "venv": venv_path,
                "script": script_name
            }
            
        self._cleanup_multi_groups(clean_data)
        return clean_data

    def _cleanup_multi_groups(self, valid_project_data):
        valid_projects = set(valid_project_data.keys())
        keys_to_delete = []

        for group_name, members in self.multi_groups.items():
            new_members = []
            for m in members:
                if m.get("project") in valid_projects:
                    
                    if self.is_portable:
                        p_name = m.get("project")
                        v_name = m.get("venv_name")
                        if p_name and v_name:
                            full_venv_name = f"{p_name}_{v_name}"
                            m["venv_path"] = Paths.get_venv_path(self.venv_hub_root, full_venv_name)

                    new_members.append(m)
                    
            self.multi_groups[group_name] = new_members
            if not new_members:
                keys_to_delete.append(group_name)
        
        for k in keys_to_delete:
            del self.multi_groups[k]

    def save_config(self):
        """Ukladá nastavenia do JSONu. V Portable režime pred uložením zakóduje cesty do UUID."""
        if self._active_project and self._active_project not in self.project_data:
             self.project_data[self._active_project] = {}

        # Pripravíme si kópie pre zápis do JSONu
        s_projects_root = self.projects_root
        s_venv_hub_root = self.venv_hub_root
        s_local_packages_root = self.local_packages_root
        s_pip_e_packages_root = self.pip_e_packages_root
        s_vscode_users_root = self.vscode_users_root
        s_portable_vscode_path = self.portable_vscode_path
        s_portable_cursor_path = self.portable_cursor_path
        s_project_data = self.project_data.copy()
        s_multi_groups = self.multi_groups.copy()

        # Ak sme v Portable režime, vykonáme ZAKÓDOVANIE (UUID)
        if self.is_portable:
            s_projects_root = PortablePathLogic.encode_path(self.projects_root)
            s_venv_hub_root = PortablePathLogic.encode_path(self.venv_hub_root)
            s_local_packages_root = PortablePathLogic.encode_path(self.local_packages_root)
            s_pip_e_packages_root = PortablePathLogic.encode_path(self.pip_e_packages_root)
            s_vscode_users_root = PortablePathLogic.encode_path(self.vscode_users_root)
            s_portable_vscode_path = PortablePathLogic.encode_path(self.portable_vscode_path)
            s_portable_cursor_path = PortablePathLogic.encode_path(self.portable_cursor_path)
            
            # Kódovanie ciest pre jednotlivé Venvy projektov
            s_project_data = {}
            for p_name, p_data in self.project_data.items():
                s_project_data[p_name] = {
                    "venv": PortablePathLogic.encode_path(p_data.get("venv", "")),
                    "script": p_data.get("script", "main.py")
                }
                
            # Kódovanie ciest v Autostart/Multi skupinách
            s_multi_groups = {}
            for g_name, members in self.multi_groups.items():
                s_members = []
                for m in members:
                    new_m = m.copy()
                    if new_m.get("venv_path"):
                        new_m["venv_path"] = PortablePathLogic.encode_path(new_m["venv_path"])
                    s_members.append(new_m)
                s_multi_groups[g_name] = s_members

        # Vytvorenie finálneho slovníka pre JSON
        data = {
            "projects_root": s_projects_root,
            "venv_hub_root": s_venv_hub_root,
            "local_packages_root": s_local_packages_root,
            "pip_e_packages_root": s_pip_e_packages_root,
            "vscode_users_root": s_vscode_users_root, 
            "active_vscode_user": self.active_vscode_user,
            "active_cursor_user": self.active_cursor_user,
            "active_ide": self.active_ide,
            "portable_vscode_path": s_portable_vscode_path,
            "portable_cursor_path": s_portable_cursor_path,
            "active_project": self._active_project,
            "run_mode": self.run_mode,
            "last_pos": self.last_pos,
            "language": self.language,
            "app_mode": self.app_mode,
            "active_multi_group": self.active_multi_group,
            "multi_groups": s_multi_groups,
            "active_theme": self.active_theme,
            "package_manager": self.package_manager, 
            "project_data": s_project_data
        }
        
        config_path = Paths.get_config_file_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"CHYBA pri ukladaní configu: {e}")

    def get_projects(self):
        if not self.projects_root or not os.path.exists(self.projects_root): return []
        try:
            return sorted([d for d in os.listdir(self.projects_root) if os.path.isdir(Paths.get_project_path(self.projects_root, d))])
        except OSError:
            return []

    def get_venvs_for_active_project(self):
        if not self.venv_hub_root or not self._active_project: return []
        prefix = f"{self._active_project}_"; results = []
        if os.path.exists(self.venv_hub_root):
            try:
                for d in os.listdir(self.venv_hub_root):
                    if d.startswith(prefix):
                        v_path = Paths.get_venv_path(self.venv_hub_root, d)
                        if os.path.isdir(v_path):
                            if self.is_portable:
                                PortablePathLogic.check_and_repair_venv_if_needed(v_path, self.local_packages_root)
                            version = self.get_python_version(v_path)
                            results.append({"name": d.replace(prefix, "", 1), "path": v_path, "version": version})
            except OSError:
                pass
        return sorted(results, key=lambda x: x['name'])

    def get_venvs_for_project(self, project_name):
        if not self.venv_hub_root or not project_name: return []
        prefix = f"{project_name}_"; results = []
        if os.path.exists(self.venv_hub_root):
            try:
                venvs = sorted([d for d in os.listdir(self.venv_hub_root) if d.startswith(prefix)])
                for d in venvs:
                    v_path = Paths.get_venv_path(self.venv_hub_root, d)
                    if os.path.isdir(v_path):
                        if self.is_portable:
                            PortablePathLogic.check_and_repair_venv_if_needed(v_path, self.local_packages_root)
                        version = self.get_python_version(v_path)
                        results.append({"name": d.replace(prefix, "", 1), "path": v_path, "version": version, "full_name": d})
            except OSError:
                pass
        return results

    def get_python_version(self, venv_path):
        cfg_path = Paths.get_pyvenv_cfg_path(venv_path)
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    match = re.search(r'version\s*=\s*([\d\.]+)', f.read())
                    return match.group(1) if match else "???"
            except:
                return "???"
        return "???"
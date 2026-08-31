#----------------------------------------
# Súbor: windows/quick_settings.py
#----------------------------------------

import os
import json
from PyQt6.QtWidgets import QWidget
from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSignal

from core.logic.pip_manager import PipManager
from core.logic.language_manager import LanguageManager
from core._path import Paths
from core.logic.resource_manager import ResourceManager
from core.logic.skin_manager import SkinManager 

from core.logic.vscode_user.profile_manager import VSCodeProfileManager
# Potrebné pre hard-sync pri prepnutí Venv-u (aby sa správal ako Master)
from core.logic.vs_code_json import VSCodeIntegration


class QuickSettingsWindow(QWidget):
    status_changed = pyqtSignal()
    language_changed = pyqtSignal(str)
    skin_changed = pyqtSignal() 
    vscode_user_changed = pyqtSignal()
    venv_changed = pyqtSignal()

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        
        # Predvolene je na vrchu (ako MiniBar), neskôr s ním bude MiniBar manipulovať
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        
        # --- PRIDANÉ: Povolí QSS a nastaví presný názov (musí byť pred loadUi) ---
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("QuickSettings")
        
        uic.loadUi(Paths.get_ui_file_path("quick_settings.ui"), self)
        
        # --- PRIDANÉ: Vytvorí 1px miesto pre prípadný budúci rámček z QSS ---
        self.main_v_layout.setContentsMargins(1, 1, 1, 1)
        
        self.edit_script.setReadOnly(True)
        
        self.retranslate_ui()
        self.venvs_cache = []
        self.connect_signals()

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)

    def connect_signals(self):
        self.combo_project.currentTextChanged.connect(self.on_project_selected)
        self.combo_venv.currentIndexChanged.connect(self.on_venv_selected)
        
        if hasattr(self, 'combo_vscode_user'):
            self.combo_vscode_user.currentIndexChanged.connect(self.on_vscode_user_changed)
        
        self.radioButton.toggled.connect(lambda checked: self.on_run_mode_changed("open_terminal", checked))
        self.radioButton_2.toggled.connect(lambda checked: self.on_run_mode_changed("run_in_terminal", checked))
        self.radioButton_3.toggled.connect(lambda checked: self.on_run_mode_changed("run_silent", checked))
        self.btn_pip_install.clicked.connect(self.run_pip_install)
        self.combo_language.currentIndexChanged.connect(self.on_language_changed)

        if hasattr(self, 'combo_skins'):
            self.combo_skins.currentIndexChanged.connect(self.on_skin_changed)
        if hasattr(self, 'btn_import_skin'):
            self.btn_import_skin.clicked.connect(self.import_new_skin)

    def run_pip_install(self):
        pkg = self.edit_pip_pkg.text().strip()
        log = self.log_output
        if not self.core.active_venv_path: 
            msg = LanguageManager.get("err_select_venv", "CHYBA: Najprv vyberte platné prostredie (venv).")
            log.append(msg)
            return
        if pkg: 
            PipManager.install_package(self.core.active_venv_path, pkg, log, self.core.package_manager)
            self.edit_pip_pkg.clear()

    def populate_panel(self):
        self.combo_project.blockSignals(True)
        self.combo_project.clear()
        projects = self.core.get_projects()
        self.combo_project.addItems(projects)
        
        if self.core.active_project in projects:
            self.combo_project.setCurrentText(self.core.active_project)
        elif projects:
            self.combo_project.setCurrentText(projects[0])
            self.core.active_project = projects[0]
            self.core.save_config()
            
        self.combo_project.blockSignals(False)
        self.on_project_selected(self.combo_project.currentText())
        
        if self.core.run_mode == "open_terminal": self.radioButton.setChecked(True)
        elif self.core.run_mode == "run_in_terminal": self.radioButton_2.setChecked(True)
        elif self.core.run_mode == "run_silent": self.radioButton_3.setChecked(True)
        
        self.populate_language_combo()
        self.populate_skins_combo()
        self.load_saved_skin()
        self.populate_vscode_users_combo()

    def populate_vscode_users_combo(self):
        if not hasattr(self, 'combo_vscode_user'): return
        
        self.combo_vscode_user.blockSignals(True)
        self.combo_vscode_user.clear()
        self.combo_vscode_user.addItem(LanguageManager.get("vscode_user_none", "--- Žiadny ---"), "")
        
        root_path = getattr(self.core, 'vscode_users_root', '')
        if root_path and os.path.exists(root_path):
            profiles = VSCodeProfileManager.get_profiles(root_path)
            for p in profiles:
                display_text = f"{p['display_name']} ({p['id']})"
                self.combo_vscode_user.addItem(display_text, p["id"])
                
        active_user = getattr(self.core, 'active_vscode_user', '')
        idx = self.combo_vscode_user.findData(active_user)
        if idx != -1:
            self.combo_vscode_user.setCurrentIndex(idx)
        else:
            self.combo_vscode_user.setCurrentIndex(0)
            
        self.combo_vscode_user.blockSignals(False)

    def on_vscode_user_changed(self, index):
        if index == -1 or not hasattr(self, 'combo_vscode_user'): return
        
        selected_user_id = self.combo_vscode_user.itemData(index)
        
        if selected_user_id != getattr(self.core, 'active_vscode_user', None):
            self.core.active_vscode_user = selected_user_id
            self.core.save_config()
            self.status_changed.emit()
            self.vscode_user_changed.emit()

    def populate_language_combo(self):
        self.combo_language.blockSignals(True)
        self.combo_language.clear()
        self.combo_language.addItem(LanguageManager.get("lang_auto", "Automaticky / Auto"), "auto")
        
        trans_dir = Paths.get_translations_dir()
        found_codes = set(ResourceManager.find_resources(trans_dir, ".json"))
        found_codes.add("en_US")
        
        sorted_codes = sorted(list(found_codes))
        for code in sorted_codes:
            display_name = code 
            content = ResourceManager.read_resource_file(trans_dir, code, ".json")
            if content:
                try:
                    data = json.loads(content)
                    display_name = data.get("_language_name", code)
                except:
                    pass
            self.combo_language.addItem(display_name, code)

        current_lang_code = self.core.language
        index = self.combo_language.findData(current_lang_code)
        self.combo_language.setCurrentIndex(index if index != -1 else 0)
        self.combo_language.blockSignals(False)

    def on_language_changed(self, index):
        if index == -1: return
        lang_code = self.combo_language.itemData(index)
        if lang_code and lang_code != self.core.language:
            self.core.language = lang_code
            self.core.save_config()
            # --- DOPLNENÉ: Načítanie nového jazyka (tým sa odošle signál do TitleBaru a celej appky) ---
            LanguageManager.load_language(lang_code)
            self.retranslate_ui()
            self.language_changed.emit(lang_code)

    def on_project_selected(self, project_name):
        if not project_name: return
        self.core.active_project = project_name
        self.core.save_config()
        self.edit_script.setText(self.core.last_script)
        self.populate_venvs_combo(project_name)

    def populate_venvs_combo(self, project_name):
        self.combo_venv.blockSignals(True)
        self.combo_venv.clear()
        self.venvs_cache = self.core.get_venvs_for_project(project_name)
        saved_default_path = self.core.get_project_default_venv()
        current_active = self.core.active_venv_path

        for venv in self.venvs_cache:
            path = venv['path']
            is_default = (path == saved_default_path)
            marker = " ★" if is_default else ""
            fmt = LanguageManager.get("fmt_venv_display", "{0} (Python {1})")
            display_text = fmt.format(venv['name'], venv['version']) + marker
            self.combo_venv.addItem(display_text, path)
            
        idx = self.combo_venv.findData(current_active)
        if idx != -1: self.combo_venv.setCurrentIndex(idx)
        elif self.venvs_cache: self.combo_venv.setCurrentIndex(0)
            
        self.combo_venv.blockSignals(False)
        current_selected_path = self.combo_venv.currentData()
        # Nechceme tu natvrdo nastavovať Master pri načítaní panelu.
        # Ak chceme iba udržať kompatibilitu so starým systémom:
        if current_selected_path and current_selected_path != self.core.active_venv_path:
            self.core.set_temporary_venv(current_selected_path)
        self.status_changed.emit()

    def on_venv_selected(self, index):
        if index == -1: return
        venv_path = self.combo_venv.itemData(index)
        
        if venv_path and venv_path != self.core.active_venv_path:
            # 1. Zrušíme len temporary, robíme plný zápis ako "Master/Predvolený"
            self.core.active_venv_path = venv_path
            
            # 2. Reálna inštalácia Mastera aj pre VS Code
            try:
                self.core.save_config()
                
                project_path = Paths.get_project_path(self.core.projects_root, self.core.active_project)
                VSCodeIntegration.set_default_interpreter(project_path, venv_path)
                
                # ZAVOLÁME CENTRÁLNU SLUŽBU
                from core.logic.sluzby.local_packages_sync import LocalPackagesSyncService
                LocalPackagesSyncService.sync_venv_to_vscode(self.core, venv_path)
                    
            except Exception as e:
                print(LanguageManager.get("err_quick_venv_switch", "Chyba pri prepínaní Venvu z Rýchlych nastavení: {error}").format(error=e))

            # 3. Vyšleme signály pre vizuálne prekreslenie
            self.status_changed.emit()
            self.venv_changed.emit()

    def on_run_mode_changed(self, mode, is_checked):
        if is_checked: self.core.run_mode = mode; self.core.save_config()

    def populate_skins_combo(self):
        if not hasattr(self, 'combo_skins'): return
        self.combo_skins.blockSignals(True)
        self.combo_skins.clear()
        self.combo_skins.addItem("Default", "default")
        skins_dict = SkinManager.get_available_skins()
        for filename, display_name in skins_dict.items():
            self.combo_skins.addItem(display_name, filename)
        self.combo_skins.blockSignals(False)
    
    def load_saved_skin(self):
        if not hasattr(self, 'combo_skins'): return
        saved_skin_filename = self.core.active_theme
        index = self.combo_skins.findData(saved_skin_filename)
        if index != -1: self.combo_skins.setCurrentIndex(index)

    def on_skin_changed(self, index):
        if index == -1 or not hasattr(self, 'combo_skins'): return
        skin_filename = self.combo_skins.itemData(index)
        if skin_filename:
            if SkinManager.apply_skin(skin_filename):
                self.core.active_theme = skin_filename
                self.core.save_config()
                self.skin_changed.emit()

    def import_new_skin(self):
        new_skin_filename = SkinManager.import_new_skin(self)
        if new_skin_filename:
            self.populate_skins_combo()
            index = self.combo_skins.findData(new_skin_filename)
            if index != -1: self.combo_skins.setCurrentIndex(index)
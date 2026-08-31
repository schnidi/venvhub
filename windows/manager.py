#----------------------------------------
# Súbor: windows/manager.py
#----------------------------------------

import os
from PyQt6.QtWidgets import (QWidget, QFileDialog, QTableWidgetItem, QHeaderView, 
                             QTextEdit, QTreeWidget, QTreeWidgetItem, QInputDialog,
                             QMessageBox, QTreeWidgetItemIterator, QMenu, QVBoxLayout)
from PyQt6 import uic
from PyQt6.QtCore import pyqtSignal, Qt

from core.logic.python_detector import PythonDetector
from core.logic.button.manager.create import CreateVenvHandler
from core.logic.button.manager.activate import ActivateHandler
from core.logic.button.manager.delete import DeleteHandler
from core.logic.button.manager.actions import ActionHandler
from core.logic.button.manager.row_actions import RowActionHandler 
from core.logic.pip_manager import PipManager
from core.logic.language_manager import LanguageManager
from core._path import Paths

from windows.pip_manager_window import PipManagerWindow
from core.logic.button.manager.clone import CloneHandler
from core.logic.skin_manager import SkinManager
from windows.builder_window import BuilderWindow 

from windows.custom_title_bar import CustomTitleBar
from core.logic.button.manager.py_launcher import ScriptLauncherHandler

# Import pre Drag and Drop tabuľku
from core.logic.sluzby.drag_and_drop import AdvancedDragDropTable

# --- UV DETECTOR ---
from core.logic.uv_detector import UVDetector

from windows.python_ver import PythonVerWindow
from windows.autostart_window import AutostartWindow
from windows.pip_e_window import PipEWindow
# --- IMPORT PRE LOKÁLNE BALÍČKY A VS CODE KONTÁ ---
from windows.local_packages_window import LocalPackagesWindow

from windows.vscode_user import VSCodeUserWindow
from core.logic.vscode_user.profile_manager import VSCodeProfileManager
from core.logic.vscode_user.start_vs_code_user import VSCodeLauncher # <--- PRIDANÝ IMPORT
from core.logic.sluzby.windows_location import WindowLocation


class MasterManager(QWidget):
    config_changed = pyqtSignal()
    theme_changed = pyqtSignal()

    def __init__(self, core):
        super().__init__()
        self.core = core
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        # Povolenie vykresľovania QSS rámčekov pre toto okno
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        uic.loadUi(Paths.get_ui_file_path("manager.ui"), self)

        # Dynamická výmena tabuľky
        old_table = self.table_group_members
        parent_layout = old_table.parentWidget().layout()
        self.table_group_members = AdvancedDragDropTable(self.group_multi_members, orientation="vertical")
        self.table_group_members.setObjectName("table_group_members")
        self.table_group_members.setColumnCount(3)
        parent_layout.replaceWidget(old_table, self.table_group_members)
        old_table.deleteLater()

        self.pip_window = None
        self.local_pkg_window = None 
        self.pip_e_window = None
        self.vscode_user_window = None 
        
        self.title_bar = CustomTitleBar(self)
        self.title_bar_layout.addWidget(self.title_bar)
        
        self.main_layout_manager.setContentsMargins(1, 1, 1, 1)
        self.setWindowTitle(LanguageManager.get("manager_window_title", "VenvHub Pro - Správca")) 
        
        self.selected_venv_path = None
        
        self.py_list = []
        self.refresh_python_combo()
        
        if not hasattr(self, 'log_output'):
            self.log_output = QTextEdit(self)
            self.log_output.setReadOnly(True)
            self.main_layout.addWidget(self.log_output)
            
        self.setup_table_style()
        self.init_connections()
        self.setup_multi_run_tab()

        self.builder_window = BuilderWindow(self.core, self)
        self.builder_v_layout.addWidget(self.builder_window)
        
        self.python_ver_window = PythonVerWindow(self)
        self.local_python_v_layout.addWidget(self.python_ver_window)

        # Inicializácia a vloženie AutostartWindow
        self.autostart_window = AutostartWindow(self.core, self)
        self.container_v_layout.addWidget(self.autostart_window)
        
        # Prepojíme ukladanie skupín so synchronizáciou Kontajnera
        self.config_changed.connect(self.autostart_window.sync_with_core)
        
        self.retranslate_ui()
        self.refresh_ui_from_config()
        WindowLocation.restore_position(self, "manager_window")


    def closeEvent(self, event):
        """Uloží pozíciu okna tesne predtým, než sa Správca zatvorí."""
        WindowLocation.save_position(self, "manager_window")
        event.accept()

    def retranslate_ui(self):
        LanguageManager.translate_ui(self)
        
        # 1. Získame preklad pre Manažéra zo slovníka
        title_text = LanguageManager.get("manager_window_title", "VenvHub Pro - Správca")
        self.setWindowTitle(title_text)
        
        # 2. PRIAME ODOVZDANIE DO TITLE BARU (Stará funkčná metóda):
        if hasattr(self, 'title_bar') and self.title_bar:
            self.title_bar.lbl_title.setText(title_text)
        
        # 3. Preklady záložiek
        self.tab_widget.setTabText(0, LanguageManager.get("tab_venvs", "Správa Venvs"))
        self.tab_widget.setTabText(1, LanguageManager.get("tab_multi", "Hromadné Spúšťanie (Multi-run)"))
        self.tab_widget.setTabText(2, LanguageManager.get("tab_container", "Kontajner / Autostart"))
        self.tab_widget.setTabText(3, LanguageManager.get("tab_settings", "Nastavenia"))
        self.tab_widget.setTabText(4, LanguageManager.get("tab_builder", "PyInstaller Builder"))
        self.tab_widget.setTabText(5, LanguageManager.get("tab_local_python", "Local Python"))

        if hasattr(self, 'autostart_window') and self.autostart_window:
            self.autostart_window.retranslate_ui()
        
        if hasattr(self, 'lbl_manager_script'):
            self.lbl_manager_script.setText(LanguageManager.get("lbl_manager_script", "Spúšťací skript:"))
        if hasattr(self, 'edit_manager_script'):
            self.edit_manager_script.setPlaceholderText(LanguageManager.get("ph_manager_script", "napr. main.py"))
        
        self.table_venvs.horizontalHeaderItem(0).setText(LanguageManager.get("col_venv_name_1", "Názov venv"))
        self.table_venvs.horizontalHeaderItem(1).setText(LanguageManager.get("col_version", "Verzia"))
        self.table_venvs.horizontalHeaderItem(2).setText(LanguageManager.get("col_status", "Stav"))
        self.table_venvs.horizontalHeaderItem(3).setText(LanguageManager.get("col_actions", "Akcie"))
        self.group_pip.setTitle(LanguageManager.get("group_pip", "Pip Manažér (vyberte venv v tabuľke)"))
        self.lbl_selected_venv.setText(LanguageManager.get("lbl_selected_venv_none", "Zvolený: ---"))
        self.group_multi_groups.setTitle(LanguageManager.get("group_multi_groups", "Skupiny"))
        self.group_multi_available.setTitle(LanguageManager.get("group_multi_available", "Dostupné projekty"))
        self.btn_save_group.setText(LanguageManager.get("btn_save_group", "Uložiť zmeny v skupine"))
        self.tree_all_projects.headerItem().setText(0, LanguageManager.get("col_project_venv", "Projekt / Venv"))
        
        if not self.table_group_members.horizontalHeaderItem(0): self.table_group_members.setHorizontalHeaderLabels(["", "", ""])
        self.table_group_members.horizontalHeaderItem(0).setText(LanguageManager.get("col_project", "Projekt"))
        self.table_group_members.horizontalHeaderItem(1).setText(LanguageManager.get("col_venv_name", "Venv"))
        self.table_group_members.horizontalHeaderItem(2).setText(LanguageManager.get("col_script", "Spúšťací skript"))
        
        current_group_item = self.list_multi_groups.currentItem()
        if current_group_item:
            group_name = current_group_item.text()
            self.group_multi_members.setTitle(LanguageManager.get("fmt_group_members", "Členovia skupiny: {0}").format(group_name))
        else:
            self.group_multi_members.setTitle(LanguageManager.get("fmt_group_members_none", "Členovia skupiny: ---"))

        self.group_paths.setTitle(LanguageManager.get("group_paths", "Základné cesty"))
        if hasattr(self, 'lbl_pip_e_pkg'):
            self.lbl_pip_e_pkg.setText(LanguageManager.get("lbl_pip_e_pkg", "Lokálne balíčky (pip -e):"))
        self.group_themes.setTitle(LanguageManager.get("group_themes", "Vzhľad aplikácie (Skiny)"))
        self.lbl_active_theme.setText(LanguageManager.get("lbl_active_theme", "Aktívna téma:"))
        self.btn_import_theme.setText(LanguageManager.get("btn_import_theme", "Importovať tému..."))
        
        if hasattr(self, 'group_package_manager'):
            self.group_package_manager.setTitle(LanguageManager.get("group_pkg_manager", "Správca balíčkov (Rýchlosť inštalácie)"))
            self.lbl_pkg_manager.setText(LanguageManager.get("lbl_pkg_manager", "Predvolený inštalátor:"))
            self.combo_pkg_manager.setItemText(0, LanguageManager.get("opt_pip", "Základný (Pip)"))
            self.combo_pkg_manager.setItemText(1, LanguageManager.get("opt_uv", "Ultra rýchly (UV - Astral)"))
        
        self.refresh_table() 
        self.populate_projects_tree()
        self.populate_multi_groups_list()

        if hasattr(self, 'python_ver_window') and self.python_ver_window:
            self.python_ver_window.retranslate_ui()
        if hasattr(self, 'vscode_user_window') and self.vscode_user_window and self.vscode_user_window.isVisible():
            self.vscode_user_window.retranslate_ui()
        if hasattr(self, 'local_pkg_window') and self.local_pkg_window and self.local_pkg_window.isVisible():
            self.local_pkg_window.retranslate_ui()
        if self.pip_window and self.pip_window.isVisible():
            self.pip_window.retranslate_ui()
        if hasattr(self, 'builder_window') and self.builder_window:
            self.builder_window.retranslate_ui()

    def init_connections(self):
        self.btn_set_proj.clicked.connect(self.select_projects_root)
        self.btn_set_hub.clicked.connect(self.select_hub_root)
        self.btn_refresh_projs.clicked.connect(self.refresh_projects_combo)
        self.combo_projs.currentTextChanged.connect(self.on_project_changed)
        
        if hasattr(self, 'btn_set_local_pkg'):
            self.btn_set_local_pkg.clicked.connect(self.select_local_pkg_root)

        if hasattr(self, 'btn_set_pip_e_pkg'):
            self.btn_set_pip_e_pkg.clicked.connect(self.select_pip_e_root)
            
        if hasattr(self, 'btn_manage_vscode_users'):
            self.btn_manage_vscode_users.clicked.connect(self.open_vscode_user_window)
            
        if hasattr(self, 'combo_vscode_user'):
            self.combo_vscode_user.currentIndexChanged.connect(self.on_vscode_user_changed)
        
        self.btn_create_venv.clicked.connect(lambda: CreateVenvHandler.run(self, self.core, self.py_list))
        self.table_venvs.itemSelectionChanged.connect(self.on_venv_selected)
        
        if hasattr(self, 'btn_browse_script'):
            self.btn_browse_script.clicked.connect(lambda: ScriptLauncherHandler.browse_script(self, self.core))
        if hasattr(self, 'edit_manager_script'):
            self.edit_manager_script.textChanged.connect(lambda text: ScriptLauncherHandler.manual_text_changed(text, self.core, self))

        self.btn_pip_install.clicked.connect(self.run_pip_install)
        self.btn_pip_uninstall.clicked.connect(self.run_pip_uninstall)
        self.btn_pip_reqs.clicked.connect(self.run_pip_reqs)
        self.btn_pip_upgrade_all.clicked.connect(self.run_pip_upgrade_all)
        
        self.btn_add_group.clicked.connect(self.add_new_multi_group)
        self.list_multi_groups.currentItemChanged.connect(self.on_multi_group_selected)
        self.tree_all_projects.itemChanged.connect(self.on_project_tree_item_changed)
        
        self.btn_save_group.clicked.connect(lambda: self.save_current_group(silent=False))
        self.table_group_members.order_changed.connect(lambda: self.save_current_group(silent=True))
        
        self.btn_remove_group.clicked.connect(self.remove_selected_group)

        self.table_venvs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_venvs.customContextMenuRequested.connect(self.open_pip_manager_context)
        self.table_venvs.doubleClicked.connect(self.open_pip_manager_doubleclick)

        self.btn_import_theme.clicked.connect(self.import_skin)
        self.combo_themes.currentIndexChanged.connect(self.on_theme_changed)
        
        if hasattr(self, 'combo_pkg_manager'):
            self.combo_pkg_manager.currentIndexChanged.connect(self.on_package_manager_changed)
            
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def refresh_python_combo(self):
        current_selection = self.combo_py.currentText()
        self.combo_py.blockSignals(True)
        self.combo_py.clear()
        self.py_list = PythonDetector.get_installed_pythons()
        self.combo_py.addItems([p['display'] for p in self.py_list])
        idx = self.combo_py.findText(current_selection)
        if idx != -1:
            self.combo_py.setCurrentIndex(idx)
        self.combo_py.blockSignals(False)

    def on_tab_changed(self, index):
        if index == 0:
            self.refresh_python_combo()

    def open_pip_manager(self):
        if not self.selected_venv_path:
            title = LanguageManager.get("title_error", "Chyba")
            msg = LanguageManager.get("msg_no_venv_selected_for_pip", "Nie je vybrané žiadne prostredie.")
            QMessageBox.warning(self, title, msg)
            return
        project_root = Paths.get_project_path(self.core.projects_root, self.core.active_project)
        if self.pip_window is None:
            self.pip_window = PipManagerWindow(self, self.selected_venv_path, project_root)
        else:
            self.pip_window.close()
            self.pip_window = PipManagerWindow(self, self.selected_venv_path, project_root)
        self.pip_window.show(); self.pip_window.raise_(); self.pip_window.activateWindow()

    def open_local_packages_window(self):
        if not self.selected_venv_path:
            QMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_select_venv_first", "Najprv vyberte prostredie v tabuľke."))
            return
            
        local_root = getattr(self.core, 'local_packages_root', '')
        if not local_root or not os.path.exists(local_root):
            QMessageBox.warning(self, LanguageManager.get("title_warning", "Upozornenie"), LanguageManager.get("msg_set_local_pkg_root", "Prejdite na záložku 'Nastavenia' a zvoľte platnú zložku pre 'Lokálne balíčky'."))
            return

        if self.local_pkg_window is not None:
            self.local_pkg_window.close()
            
        self.local_pkg_window = LocalPackagesWindow(self, self.selected_venv_path)
        self.local_pkg_window.show()
        self.local_pkg_window.raise_()
        self.local_pkg_window.activateWindow()

    def open_pip_e_window(self):
        if not self.selected_venv_path:
            QMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_select_venv_first", "Najprv vyberte prostredie v tabuľke."))
            return

        if self.pip_e_window is not None:
            self.pip_e_window.close()
            
        self.pip_e_window = PipEWindow(self, self.selected_venv_path)
        self.pip_e_window.show()
        self.pip_e_window.raise_()
        self.pip_e_window.activateWindow()

    def open_vscode_user_window(self):
        """Otvorí okno pre správu VS Code používateľských profilov."""
        if self.vscode_user_window is not None:
            self.vscode_user_window.close()
            
        self.vscode_user_window = VSCodeUserWindow(self.core, self)
        
        # --- ZMENA: Ak vytvorím/vymažem/nastavím profil, synchronizujem to okamžite ---
        self.vscode_user_window.profiles_changed.connect(self.on_vscode_profiles_changed_externally)
        
        self.vscode_user_window.show()
        self.vscode_user_window.raise_()
        self.vscode_user_window.activateWindow()

    def on_vscode_profiles_changed_externally(self):
        """Vyvolá sa, ak sa v podrobnom okne VS Code Users pridá/zmaže/zvolí profil."""
        self.populate_vscode_users_combo()
        self.config_changed.emit() # Dá signál MiniBaru, ktorý to prenesie do Rýchlych nastavení

    def populate_vscode_users_combo(self):
        """Načíta a naplní zoznam dostupných profilov do ComboBoxu v Nastaveniach."""
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
        """Vyvolá sa, keď používateľ zmení profil v ComboBoxe v podrobnom Správcovi."""
        if index == -1 or not hasattr(self, 'combo_vscode_user'): return
        
        selected_user_id = self.combo_vscode_user.itemData(index)
        
        if selected_user_id != getattr(self.core, 'active_vscode_user', None):
            self.core.active_vscode_user = selected_user_id
            self.core.save_config()
            self.config_changed.emit() # Dá signál MiniBaru, ktorý to prenesie do Rýchlych nastavení
            
            # --- ZMENA: Ak je otvorené aj podrobné okno VS Profilov, aktualizujeme hviezdičku aj tam ---
            if hasattr(self, 'vscode_user_window') and self.vscode_user_window and self.vscode_user_window.isVisible():
                self.vscode_user_window.refresh_profiles_list()

    def open_pip_manager_context(self, position):
        index = self.table_venvs.indexAt(position)
        if not index.isValid(): return
        self.table_venvs.selectRow(index.row()); self.on_venv_selected()
        if self.selected_venv_path:
            menu = QMenu()
            action_manage = menu.addAction(LanguageManager.get("ctx_manage_packages", "📦 Spravovať balíčky (Pip Manager)"))
            action_manage.triggered.connect(self.open_pip_manager)
            
            action_local_pkg = menu.addAction(LanguageManager.get("ctx_local_packages", "🔗 Lokálne balíčky"))
            action_local_pkg.triggered.connect(self.open_local_packages_window)

            action_pip_e = menu.addAction(LanguageManager.get("ctx_pip_e_packages", "✏️ Lokálne balíčky (pip -e)"))
            action_pip_e.triggered.connect(self.open_pip_e_window)
            
            menu.addSeparator()
            action_clone = menu.addAction(LanguageManager.get("ctx_clone_venv", "🐑 Klonovať / Zálohovať Venv"))
            action_clone.triggered.connect(lambda: CloneHandler.run(self, self.core, self.selected_venv_path))
            menu.exec(self.table_venvs.viewport().mapToGlobal(position))

    def open_pip_manager_doubleclick(self, index):
        if index.isValid(): self.on_venv_selected(); self.open_pip_manager()

    def setup_multi_run_tab(self):
        self.populate_multi_groups_list(); self.populate_projects_tree()
        header = self.table_group_members.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

    def populate_multi_groups_list(self):
        self.list_multi_groups.clear()
        groups = self.core.multi_groups.keys()
        self.list_multi_groups.addItems(sorted(list(groups)))

    def populate_projects_tree(self):
        self.tree_all_projects.clear()
        projects = self.core.get_projects()
        project_data = self.core.project_data if hasattr(self.core, 'project_data') else {}

        for proj_name in projects:
            project_item = QTreeWidgetItem(self.tree_all_projects, [proj_name])
            project_item.setFlags(project_item.flags() & ~Qt.ItemFlag.ItemIsSelectable) 
            
            saved_script = "main.py"
            if proj_name in project_data:
                saved_script = project_data[proj_name].get("script", "main.py")

            venvs = self.core.get_venvs_for_project(proj_name)
            for venv in venvs:
                venv_item_text = f"{venv['name']} (Python {venv['version']})"
                venv_item = QTreeWidgetItem(project_item, [venv_item_text])
                venv_item.setFlags(venv_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                venv_item.setCheckState(0, Qt.CheckState.Unchecked)
                venv_item.setData(0, Qt.ItemDataRole.UserRole, {
                    "project": proj_name, 
                    "venv_name": venv['name'], 
                    "venv_path": venv['path'], 
                    "script_to_run": saved_script
                })
        self.tree_all_projects.expandAll()

    def add_new_multi_group(self):
        title = LanguageManager.get("title_new_group", "Nová Skupina")
        label = LanguageManager.get("lbl_enter_group_name", "Zadajte názov pre novú skupinu:")
        text, ok = QInputDialog.getText(self, title, label)
        if ok and text:
            if text in self.core.multi_groups:
                QMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_group_exists", "Skupina už existuje."))
                return
            self.core.multi_groups[text] = []
            self.core.save_config()
            self.populate_multi_groups_list()
            
            items = self.list_multi_groups.findItems(text, Qt.MatchFlag.MatchExactly)
            if items:
                self.list_multi_groups.setCurrentItem(items[0])
            
            self.config_changed.emit()
    
    def on_multi_group_selected(self, current_item, previous_item):
        self.tree_all_projects.blockSignals(True)
        if not current_item:
            self.table_group_members.setRowCount(0)
            self.group_multi_members.setTitle(LanguageManager.get("fmt_group_members_none", "Členovia skupiny: ---"))
            self.uncheck_all_projects()
            self.tree_all_projects.blockSignals(False)
            return
            
        group_name = current_item.text()
        self.group_multi_members.setTitle(LanguageManager.get("fmt_group_members", "Členovia skupiny: {0}").format(group_name))
        members = self.core.multi_groups.get(group_name, [])
        self.table_group_members.setRowCount(len(members))
        
        readonly_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        editable_flags = readonly_flags | Qt.ItemFlag.ItemIsEditable
        
        for row, member in enumerate(members):
            p_item = QTableWidgetItem(member.get("project"))
            v_item = QTableWidgetItem(member.get("venv_name"))
            s_item = QTableWidgetItem(member.get("script_to_run", "main.py"))
            
            p_item.setFlags(readonly_flags)
            v_item.setFlags(readonly_flags)
            s_item.setFlags(editable_flags)
            
            self.table_group_members.setItem(row, 0, p_item)
            self.table_group_members.setItem(row, 1, v_item)
            self.table_group_members.setItem(row, 2, s_item)
        
        member_paths = {m['venv_path'] for m in members}
        it = QTreeWidgetItemIterator(self.tree_all_projects)
        while it.value():
            item = it.value(); d = item.data(0, Qt.ItemDataRole.UserRole)
            if d: item.setCheckState(0, Qt.CheckState.Checked if d['venv_path'] in member_paths else Qt.CheckState.Unchecked)
            it += 1
        self.tree_all_projects.blockSignals(False)

    def on_project_tree_item_changed(self, item, column):
        venv_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not venv_data: return
        is_checked = item.checkState(0) == Qt.CheckState.Checked
        
        readonly_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        editable_flags = readonly_flags | Qt.ItemFlag.ItemIsEditable

        if is_checked:
            if self.find_row_by_venv_path(venv_data['venv_path']) is None:
                row = self.table_group_members.rowCount()
                self.table_group_members.insertRow(row)
                
                p = QTableWidgetItem(venv_data["project"])
                v = QTableWidgetItem(venv_data["venv_name"])
                script_val = venv_data.get("script_to_run", "main.py")
                s = QTableWidgetItem(script_val) 
                
                p.setFlags(readonly_flags)
                v.setFlags(readonly_flags)
                s.setFlags(editable_flags)
                
                self.table_group_members.setItem(row, 0, p)
                self.table_group_members.setItem(row, 1, v)
                self.table_group_members.setItem(row, 2, s)
        else:
            row = self.find_row_by_venv_path(venv_data['venv_path'])
            if row is not None: self.table_group_members.removeRow(row)

    def find_row_by_venv_path(self, venv_path):
        for row in range(self.table_group_members.rowCount()):
            p_name = self.table_group_members.item(row, 0).text()
            v_name = self.table_group_members.item(row, 1).text()
            
            full_name = f"{p_name}_{v_name}"
            check_path = Paths.get_venv_path(self.core.venv_hub_root, full_name)
            
            if check_path == venv_path: return row
        return None

    def save_current_group(self, silent=False):
        cur = self.list_multi_groups.currentItem()
        if not cur: 
            if not silent:
                QMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), LanguageManager.get("msg_no_group_selected_save", "Nie je vybraná žiadna skupina na uloženie."))
            return
            
        group_name = cur.text()
        new_members = []
        
        for row in range(self.table_group_members.rowCount()):
            p_name = self.table_group_members.item(row, 0).text()
            v_name = self.table_group_members.item(row, 1).text()
            s_name = self.table_group_members.item(row, 2).text()
            
            full_venv_name = f"{p_name}_{v_name}"
            venv_path = Paths.get_venv_path(self.core.venv_hub_root, full_venv_name)
            
            member_data = {
                "project": p_name,
                "venv_name": v_name,
                "venv_path": venv_path,
                "script_to_run": s_name
            }
            new_members.append(member_data)
            
        self.core.multi_groups[group_name] = new_members
        self.core.save_config()
        self.config_changed.emit()
        
        if not silent:
            QMessageBox.information(self, LanguageManager.get("title_saved", "Uložené"), LanguageManager.get("msg_group_saved", "Skupina bola uložená."))

    def uncheck_all_projects(self):
        it = QTreeWidgetItemIterator(self.tree_all_projects)
        while it.value():
            if it.value().data(0, Qt.ItemDataRole.UserRole): it.value().setCheckState(0, Qt.CheckState.Unchecked)
            it += 1

    def remove_selected_group(self):
        cur = self.list_multi_groups.currentItem()
        if not cur: return
        group_name = cur.text()
        title = LanguageManager.get("title_delete", "Zmazať?")
        msg = LanguageManager.get("msg_delete_group_confirm", "Zmazať skupinu {group}?").format(group=group_name)
        if QMessageBox.question(self, title, msg) == QMessageBox.StandardButton.Yes:
            if group_name in self.core.multi_groups:
                del self.core.multi_groups[group_name]
                self.core.save_config(); self.populate_multi_groups_list(); self.config_changed.emit()

    def setup_table_style(self):
        header = self.table_venvs.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table_venvs.setColumnWidth(3, 200)

    def run_pip_install(self):
        pkg = self.edit_pip_pkg.text().strip()
        if self.selected_venv_path and pkg:
            PipManager.install_package(self.selected_venv_path, pkg, self.log_output, self.core.package_manager)
            self.edit_pip_pkg.clear()

    def run_pip_uninstall(self):
        pkg = self.edit_pip_pkg.text().strip()
        if self.selected_venv_path and pkg:
            PipManager.uninstall_package(self.selected_venv_path, pkg, self.log_output, self.core.package_manager)
            self.edit_pip_pkg.clear()

    def run_pip_reqs(self):
        if self.selected_venv_path:
            project_path = Paths.get_project_path(self.core.projects_root, self.core.active_project)
            PipManager.install_requirements(self.selected_venv_path, project_path, self.log_output, self.core.package_manager)

    def run_pip_upgrade_all(self):
        if self.selected_venv_path: 
            PipManager.update_all_packages(self.selected_venv_path, self.log_output, self.core.package_manager)

    def refresh_ui_from_config(self):
        self.edit_proj.setText(self.core.projects_root)
        self.edit_hub.setText(self.core.venv_hub_root)
        
        if hasattr(self, 'edit_local_pkg'):
            self.edit_local_pkg.setText(getattr(self.core, 'local_packages_root', ''))

        if hasattr(self, 'edit_pip_e_pkg'):
            self.edit_pip_e_pkg.setText(getattr(self.core, 'pip_e_packages_root', ''))
            
        if hasattr(self, 'edit_manager_script'):
            self.edit_manager_script.blockSignals(True)
            self.edit_manager_script.setText(self.core.last_script)
            self.edit_manager_script.blockSignals(False)
            
        self.refresh_projects_combo()
        self.populate_themes_combo()
        self.populate_package_manager_combo()
        self.populate_vscode_users_combo()

    def select_projects_root(self):
        path = QFileDialog.getExistingDirectory(self, LanguageManager.get("dialog_select_projects_root", "Vyberte priečinok projektov"))
        if path: self.core.projects_root = path; self.core.save_config(); self.refresh_ui_from_config(); self.populate_projects_tree()

    def select_hub_root(self):
        path = QFileDialog.getExistingDirectory(self, LanguageManager.get("dialog_select_hub_root", "Vyberte priečinok Venv Hub"))
        if path: self.core.venv_hub_root = path; self.core.save_config(); self.refresh_ui_from_config(); self.populate_projects_tree()

    def select_local_pkg_root(self):
        path = QFileDialog.getExistingDirectory(self, LanguageManager.get("dialog_select_local_pkg_root", "Vyberte priečinok s lokálnymi balíčkami"))
        if path: 
            self.core.local_packages_root = path
            self.core.save_config()
            self.refresh_ui_from_config()

    def select_pip_e_root(self):
        path = QFileDialog.getExistingDirectory(self, LanguageManager.get("dialog_select_pip_e_root", "Vyberte priečinok pre Pip-e balíčky"))
        if path: 
            self.core.pip_e_packages_root = path
            self.core.save_config()
            self.refresh_ui_from_config()

    def refresh_projects_combo(self):
        self.combo_projs.blockSignals(True); self.combo_projs.clear()
        projs = self.core.get_projects(); self.combo_projs.addItems(projs)
        if self.core.active_project in projs: self.combo_projs.setCurrentText(self.core.active_project)
        elif projs: self.core.active_project = projs[0]; self.combo_projs.setCurrentText(projs[0])
        self.combo_projs.blockSignals(False); self.on_project_changed(self.combo_projs.currentText())
        self.populate_projects_tree()

    def on_project_changed(self, text):
        if text: 
            self.core.active_project = text
            self.core.save_config()
            if hasattr(self, 'edit_manager_script'):
                self.edit_manager_script.blockSignals(True)
                self.edit_manager_script.setText(self.core.last_script)
                self.edit_manager_script.blockSignals(False)
            self.refresh_table()
            self.config_changed.emit()

    def on_venv_selected(self):
        sel = self.table_venvs.selectionModel().selectedRows()
        if not sel: self.selected_venv_path = None; self.lbl_selected_venv.setText(LanguageManager.get("lbl_selected_venv_none", "Zvolený: ---")); return
        row = sel[0].row(); name = self.table_venvs.item(row, 0).text(); ver = self.table_venvs.item(row, 1).text()
        self.selected_venv_path = Paths.get_venv_path(self.core.venv_hub_root, f"{self.core.active_project}_{name}")
        self.lbl_selected_venv.setText(LanguageManager.get("fmt_selected_venv", "Zvolený: {0} (Python {1})").format(name, ver))

    def refresh_table(self):
        self.selected_venv_path = None; self.lbl_selected_venv.setText(LanguageManager.get("lbl_selected_venv_none", "Zvolený: ---"))
        venvs = self.core.get_venvs_for_active_project(); self.table_venvs.setRowCount(0)
        
        default_venv_path = self.core.get_project_default_venv()
        
        for v in venvs:
            row = self.table_venvs.rowCount(); self.table_venvs.insertRow(row)
            self.table_venvs.setItem(row, 0, QTableWidgetItem(v['name']))
            ver_item = QTableWidgetItem(v['version']); ver_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table_venvs.setItem(row, 1, ver_item)
            
            is_def = (v['path'] == default_venv_path)
            stat_item = QTableWidgetItem("★" if is_def else ""); stat_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.table_venvs.setItem(row, 2, stat_item)
            
            act = QWidget(); uic.loadUi(Paths.get_ui_file_path("venv_actions.ui"), act)
            act.rb_default.setChecked(is_def)
            act.rb_default.clicked.connect(lambda ch, p=v['path']: ActivateHandler.set_default(self.core, p, self))
            
            act.btn_vscode.clicked.connect(lambda ch, p=v['path']: self.launch_vscode_for_venv(p))
            
            # --- OPRAVA: POUŽIJEME LAMBDA, KTORÁ ZACHYTÍ BOOLEAN A SPUSTÍ OBA PRÍKAZY ---
            act.btn_run.clicked.connect(lambda ch, p=v['path']: [
                ActivateHandler.set_default(self.core, p, self),
                RowActionHandler.run_venv(self.core, p)
            ])
            # ----------------------------------------------------------------------------

            act.btn_stop.clicked.connect(lambda ch, p=v['path']: RowActionHandler.stop_venv(p))

            act.btn_venv_update.clicked.connect(lambda ch, p=v['path']: PipManager.update_all_packages(p, self.log_output, self.core.package_manager))
            act.btn_delete.clicked.connect(lambda ch, p=v['path']: DeleteHandler.run(self.core, p, self))
            self.table_venvs.setCellWidget(row, 3, act)

    def launch_vscode_for_venv(self, venv_path):
        """Vyvolá spustenie VS Code s vybraným Venv a profilom a nastaví ho ako predvolený."""
        # 1. Nastaví vybraný Venv ako aktívny v aplikácii aj vo VS Code settings.json
        ActivateHandler.set_default(self.core, venv_path, self)
        
        # 2. Spustí VS Code
        project_path = Paths.get_project_path(self.core.projects_root, self.core.active_project)
        success, err_msg = VSCodeLauncher.launch(self.core, project_path, venv_path)
        
        if not success:
            QMessageBox.warning(self, LanguageManager.get("title_error", "Chyba"), err_msg)

    def populate_themes_combo(self):
        self.combo_themes.blockSignals(True); self.combo_themes.clear()
        self.combo_themes.addItem(LanguageManager.get("theme_default", "Default"), "default")
        skins = SkinManager.get_available_skins()
        for f, d in skins.items(): self.combo_themes.addItem(d, f)
        idx = self.combo_themes.findData(self.core.active_theme)
        self.combo_themes.setCurrentIndex(idx if idx != -1 else 0); self.combo_themes.blockSignals(False)

    def on_theme_changed(self, index):
        if index == -1: return
        theme = self.combo_themes.itemData(index)
        if SkinManager.apply_skin(theme): self.core.active_theme = theme; self.core.save_config(); self.config_changed.emit(); self.theme_changed.emit()

    def import_skin(self):
        new = SkinManager.import_new_skin(self)
        if new: self.populate_themes_combo()

    def populate_package_manager_combo(self):
        if not hasattr(self, 'combo_pkg_manager'): return
        
        self.combo_pkg_manager.blockSignals(True)
        self.combo_pkg_manager.clear()
        
        self.combo_pkg_manager.addItem(LanguageManager.get("opt_pip", "Základný (Pip)"), "pip")
        self.combo_pkg_manager.addItem(LanguageManager.get("opt_uv", "Ultra rýchly (UV - Astral)"), "uv")
        
        idx = self.combo_pkg_manager.findData(self.core.package_manager)
        if idx != -1:
            self.combo_pkg_manager.setCurrentIndex(idx)
            
        self.combo_pkg_manager.blockSignals(False)

    def on_package_manager_changed(self, index):
        if index == -1 or not hasattr(self, 'combo_pkg_manager'): return
        
        selected_manager = self.combo_pkg_manager.itemData(index)
        
        if selected_manager == "uv":
            # --- AKTUALIZÁCIA AKTÍVNEHO PYTHONU PRE UV PRED KONTROLOU ---
            active_venv = self.core.active_venv_path
            if active_venv:
                parent_py = PythonDetector.resolve_parent_python(active_venv)
                PythonDetector.set_active_python_path(parent_py)
            else:
                PythonDetector.set_active_python_path(None)
                
            # Resetujeme cache pre zaručenie čerstvého overenia
            UVDetector.reset_cache()
            
            if not UVDetector.is_uv_installed():
                title = LanguageManager.get("title_uv_missing", "UV nie je nainštalované")
                
                # Zistíme zobrazenie názvu aktívneho Pythonu pre lepšiu lokalizáciu chyby
                active_py_name = os.path.basename(PythonDetector.get_active_python_path())
                
                # Zostavíme detailnú správu pre používateľa
                msg = LanguageManager.get(
                    "msg_uv_missing_for_active", 
                    "Nástroj 'uv' nebol pre aktívny Python ({0}) nájdený.\n\n"
                    "Ak chcete využívať inštalátor UV, nainštalujte ho najprv do vášho aktívneho prostredia,\n"
                    "alebo preň v systéme Windows nakonfigurujte premennú PATH."
                ).format(active_py_name)
                
                QMessageBox.warning(self, title, msg)
                
                # Vrátenie výberu v ComboBoxe späť na predvolený Pip
                self.combo_pkg_manager.blockSignals(True)
                self.combo_pkg_manager.setCurrentIndex(self.combo_pkg_manager.findData("pip"))
                self.combo_pkg_manager.blockSignals(False)
                return

        self.core.package_manager = selected_manager
        self.core.save_config()
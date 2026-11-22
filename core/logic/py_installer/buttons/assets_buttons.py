#----------------------------------------
# Súbor: core/logic/py_installer/buttons/assets_buttons.py
# Logika pre správu súborov a priečinkov v PyInstaller Builderi.
# Plne prepojené na DialogBridge a LanguageBridge (0 priamych väzieb na windows/).
#----------------------------------------

import os
from PyQt6.QtWidgets import QFileDialog, QTableWidgetItem
from core._path import Paths

# --- ČISTÉ MOSTY (0 VÄZIEB NA WINDOWS) ---
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.dialog_bridge import DialogBridge

class AssetsButtonsHandler:
    
    @staticmethod
    def add_file(window):
        title = LanguageBridge.translate("dialog_add_data_file", "Pridať súbor")
        
        current_dir = ""
        active_project = window.combo_project.currentText()
        if active_project and window.core.projects_root:
            current_dir = Paths.get_project_path(window.core.projects_root, active_project)
            
        file_paths, _ = QFileDialog.getOpenFileNames(window, title, current_dir)
        
        for path in file_paths:
            AssetsButtonsHandler._add_row_to_table(window, os.path.normpath(path), ".")
            
        if file_paths and hasattr(window, 'update_live_preview'):
            window.update_live_preview()

    @staticmethod
    def add_dir(window):
        title = LanguageBridge.translate("dialog_add_data_dir", "Pridať priečinok")
        
        current_dir = ""
        active_project = window.combo_project.currentText()
        if active_project and window.core.projects_root:
            current_dir = Paths.get_project_path(window.core.projects_root, active_project)
            
        dir_path = QFileDialog.getExistingDirectory(window, title, current_dir)
        
        if dir_path:
            # 1. Zistíme koreň aktuálneho projektu
            project_name = window.combo_project.currentText()
            project_root = os.path.normpath(os.path.join(window.core.projects_root, project_name))
            dir_path_norm = os.path.normpath(dir_path)

            # 2. Vypočítame relatívnu cestu a spravíme prísnu kontrolu
            try:
                relative_path = os.path.relpath(dir_path_norm, project_root)
                
                # Ak cesta začína na "..", používateľ vybral priečinok mimo projektu
                if relative_path.startswith(".."):
                    # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
                    DialogBridge.warning(
                        window,
                        LanguageBridge.translate("title_warning_outside_project", "Pozor - Mimo projektu!"),
                        LanguageBridge.translate(
                            "msg_folder_outside_project_detail", 
                            "Vybraný priečinok sa nenachádza v aktuálnom projekte '{0}'.\n\nOčakávaný koreň: {1}\nVybrali ste: {2}\n\nAkcia bola zrušená."
                        ).format(project_name, project_root, dir_path_norm)
                    )
                    return
                
                # Pre PyInstaller nahradíme spätné lomítka doprednými
                folder_dest = relative_path.replace("\\", "/")
                
            except ValueError:
                # Ak je priečinok na úplne inom disku
                # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
                DialogBridge.critical(
                    window, 
                    LanguageBridge.translate("title_critical_error", "Kritická Chyba"), 
                    LanguageBridge.translate("msg_folder_on_different_drive", "Vybraný priečinok sa nachádza na inom disku ako aktuálny projekt!\nAkcia bola zrušená.")
                )
                return

            # 3. Zápis do tabuľky
            AssetsButtonsHandler._add_row_to_table(window, dir_path_norm, folder_dest)
            
            if hasattr(window, 'update_live_preview'):
                window.update_live_preview()

    @staticmethod
    def remove_selected(window):
        selected_rows = set(item.row() for item in window.table_data.selectedItems())
        
        for row in sorted(selected_rows, reverse=True):
            window.table_data.removeRow(row)
            
        if selected_rows and hasattr(window, 'update_live_preview'):
            window.update_live_preview()

    @staticmethod
    def _add_row_to_table(window, source: str, destination: str):
        """Pomocná metóda na vloženie dát do QTableWidget"""
        row_count = window.table_data.rowCount()
        window.table_data.insertRow(row_count)
        
        src_item = QTableWidgetItem(source)
        dst_item = QTableWidgetItem(destination)
        
        window.table_data.setItem(row_count, 0, src_item)
        window.table_data.setItem(row_count, 1, dst_item)
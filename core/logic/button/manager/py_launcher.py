#----------------------------------------
# Súbor: core/logic/button/manager/py_launcher.py
#----------------------------------------

import os
from PyQt6.QtWidgets import QFileDialog
from core._path import Paths
from core.logic.language_manager import LanguageManager

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox


class ScriptLauncherHandler:
    @staticmethod
    def browse_script(parent_window, core):
        """
        Otvorí dialóg pre výber spúšťacieho skriptu (.py).
        Zabezpečí, že skript sa nachádza vo vnútri vybraného projektu.
        """
        project_name = core.active_project
        if not project_name:
            title = LanguageManager.get("title_error", "Chyba")
            msg = LanguageManager.get("msg_no_project_selected", "Najprv vyberte projekt.")
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(parent_window, title, msg)
            return

        project_path = Paths.get_project_path(core.projects_root, project_name)
        
        if not os.path.exists(project_path):
            title = LanguageManager.get("title_error", "Chyba")
            msg = LanguageManager.get("msg_project_not_found", "Priečinok projektu neexistuje.")
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(parent_window, title, msg)
            return

        # Preklady pre dialóg
        dialog_title = LanguageManager.get("title_select_script", "Vybrať spúšťací skript")
        file_filter = "Python Scripts (*.py);;All Files (*.*)"
        
        # Otvorenie dialógu priamo v priečinku projektu
        file_path, _ = QFileDialog.getOpenFileName(parent_window, dialog_title, project_path, file_filter)

        if not file_path:
            return  # Užívateľ zavrel dialóg

        # Normalizácia ciest pre bezpečné porovnanie
        project_path_norm = os.path.normpath(project_path)
        file_path_norm = os.path.normpath(file_path)

        try:
            # Vypočítame relatívnu cestu súboru voči projektu
            rel_path = os.path.relpath(file_path_norm, project_path_norm)
            
            # Ak relatívna cesta začína na "..", znamená to, že súbor je MIMO projektu
            if rel_path.startswith(".."):
                raise ValueError("Skript je mimo projektu")
                
        except ValueError:
            title_warn = LanguageManager.get("title_warning__selection_title", "Nedovolený výber")
            msg_warn = LanguageManager.get("msg_script_outside", "Vybraný skript sa nenachádza v aktuálnom projekte '{0}'!\n\nVyberte súbor priamo z tohto priečinka.").format(project_name)
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(parent_window, title_warn, msg_warn)
            return

        # Nastavíme relatívnu cestu do textového poľa
        if hasattr(parent_window, 'edit_manager_script'):
            parent_window.edit_manager_script.setText(rel_path)
        
        # Uložíme do Core (to automaticky uloží pre aktuálny projekt vďaka novej logike)
        core.last_script = rel_path
        core.save_config()
        
        parent_window.config_changed.emit()

    @staticmethod
    def manual_text_changed(text, core, parent_window):
        """
        Spracuje situáciu, ak sa text v poli zmení (napr. pri načítaní configu).
        """
        script_name = text.strip()
        # Uložíme len ak sa líši, aby sme nespustili nekonečnú slučku
        if script_name and script_name != core.last_script:
            core.last_script = script_name
            core.save_config()
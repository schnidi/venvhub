#----------------------------------------
# Súbor: core/logic/box/metadata_exe.py
#----------------------------------------

import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from core.logic.language_manager import LanguageManager
from core._path import Paths

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox


class MetadataHandler:
    """
    Logika pre výber cieľového priečinka pre "Rodný list" aplikácie.
    """

    @staticmethod
    def browse_path(window):
        """
        Otvorí dialóg na výber priečinka a zapíše relatívnu cestu.
        """
        project_name = window.combo_project.currentText()
        if not project_name:
            return

        project_root = Paths.get_project_path(window.core.projects_root, project_name)

        # Otvorí dialóg v koreni aktuálneho projektu
        selected_dir = QFileDialog.getExistingDirectory(
            window,
            LanguageManager.get("dialog_select_metadata_folder", "Vyberte cieľový priečinok pre metadáta"),
            project_root
        )

        if not selected_dir:
            return

        # Vypočítame relatívnu cestu a spravíme prísnu kontrolu
        try:
            project_root_norm = os.path.normpath(project_root)
            selected_dir_norm = os.path.normpath(selected_dir)
            
            relative_path = os.path.relpath(selected_dir_norm, project_root_norm)

            # Ak cesta začína na "..", používateľ vybral priečinok mimo projektu
            if relative_path.startswith(".."):
                raise ValueError("Priečinok je mimo projektu")

            # Pre PyInstaller nahradíme spätné lomítka doprednými (pre multiplatformovú kompatibilitu)
            final_path = relative_path.replace("\\", "/")
            
            # Zapíšeme do UI
            window.edit_birth_cert_path.setText(final_path)

        except ValueError:
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(
                window,
                LanguageManager.get("title_outside_project_error", "Chyba - Mimo projektu!"),
                LanguageManager.get("msg_folder_outside_project", "Vybraný priečinok sa nenachádza v aktuálnom projekte '{0}'.\n\nProsím, vyberte alebo vytvorte priečinok priamo v štruktúre projektu.").format(project_name)
            )
            return
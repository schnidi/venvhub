#----------------------------------------
# Súbor: core/logic/skin_manager.py
#----------------------------------------

from PyQt6.QtWidgets import QApplication
import os
from core._path import Paths
from core.logic.resource_manager import ResourceManager

class SkinManager:
    """
    Špecializovaný manažér pre Skiny.
    Podporuje Dual-Theme systém s metadátami.
    """

    @staticmethod
    def get_available_skins() -> dict[str, str]:
        """
        Vráti slovník dostupných skinov vo formáte {názov_súboru: zobrazovaný_názov}.
        Ak má .qss súbor metadáta "Theme Name", použije sa ten. Inak sa použije názov súboru.
        Užívateľské témy majú prednosť pred internými.
        """
        skins = {}
        
        for directory in [Paths.get_user_themes_dir(), Paths.get_themes_dir()]:
            if not os.path.exists(directory):
                continue

            filenames = ResourceManager.find_resources(directory, ".qss")
            
            for filename in filenames:
                if filename in skins:
                    continue

                full_path = os.path.join(directory, f"{filename}.qss")
                metadata = ResourceManager.parse_qss_metadata(full_path)
                
                display_name = metadata.get("Theme Name", filename)
                skins[filename] = display_name
                
        return skins

    @staticmethod
    def apply_skin(skin_name: str) -> bool:
        """
        Načíta a aplikuje skin podľa názvu súboru.
        Hľadá najprv v užívateľských, potom v interných.
        """
        app = QApplication.instance()
        if not app: return False

        if not skin_name or skin_name.lower() == "default":
            app.setStyleSheet("")
            return True

        user_dir = Paths.get_user_themes_dir()
        content = ResourceManager.read_resource_file(user_dir, skin_name, ".qss")
        
        if not content:
            internal_dir = Paths.get_themes_dir()
            content = ResourceManager.read_resource_file(internal_dir, skin_name, ".qss")
        
        if content:
            # --- NOVÁ LOGIKA PRE DYNAMICKÉ CESTY ---
            # Získame absolútnu cestu k témam a upravíme lomítka na dopredné (pre QSS)
            themes_abs_path = Paths.get_themes_dir().replace('\\', '/')
            # Nahradíme zástupný znak reálnou cestou
            content = content.replace("url({{CORE_THEMES_DIR}}", f'url("{themes_abs_path}')
            content = content.replace("{{CORE_THEMES_DIR}}", themes_abs_path)
            import re
            content = re.sub(r'url\("([^"\)]+)\)', r'url("\1")', content)
            # ---------------------------------------
            
            app.setStyleSheet(content)
            return True
        else:
            print(f"Chyba: Téma '{skin_name}' sa nenašla ani v jednom priečinku.")
            app.setStyleSheet("")
            return False

    @staticmethod
    def import_new_skin(parent_widget) -> str | None:
        """
        Importuje novú tému. VŽDY ukladá do užívateľského priečinka vedľa .exe.
        """
        target_directory = Paths.get_user_themes_dir()
        
        return ResourceManager.import_resource(
            parent_widget=parent_widget,
            target_directory=target_directory,
            dialog_title="Importovať Skin (.qss)",
            file_filter="QSS Files (*.qss)"
        )
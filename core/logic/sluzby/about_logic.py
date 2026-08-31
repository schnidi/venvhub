#----------------------------------------
# Súbor: core/logic/sluzby/about_logic.py
#----------------------------------------

import os
import json
from core._path import Paths
from core.logic.language_manager import LanguageManager


class AboutLogic:
    """Služba na prácu s dátami a načítavanie informácií pre okno 'O programe'."""

    _about_dialog_class = None
    _cached_version = None  # Uložená verzia v pamäti pre rýchle volanie odkiaľkoľvek

    @classmethod
    def register_about_dialog(cls, dialog_class):
        """Umožňuje zaregistrovať triedu AboutDialog pri štarte aplikácie."""
        cls._about_dialog_class = dialog_class

    @classmethod
    def show_about_dialog(cls, parent_window):
        """Získa HTML a otvorí okno 'O programe' bez priamej závislosti na UI."""
        if cls._about_dialog_class is None:
            print("[AboutLogic] CHYBA: Trieda AboutDialog nie je zaregistrovaná!")
            return

        html_content = cls.get_about_html()
        dialog = cls._about_dialog_class(parent_window, html_content)
        dialog.exec()

    @classmethod
    def get_app_version(cls) -> str:
        """
        Vráti aktuálnu verziu aplikácie z pamäte alebo zo súboru about.json.
        Túto metódu volá GitHub Update Checker aj dialóg O programe.
        """
        if cls._cached_version:
            return cls._cached_version

        json_path = os.path.join(Paths.get_base_path(), Paths.ASSETS_DIR_NAME, "about.json")
        version = "2.5.27"  # Predvolená záložná hodnota

        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    version = data.get("version", version)
            except Exception as e:
                print(f"[AboutLogic] Varovanie: Nepodarilo sa načítať verziu z about.json: {e}")

        cls._cached_version = version
        return version

    @classmethod
    def get_about_html(cls) -> str:
        """Načíta súbor about.json, dosadí reálnu verziu za {version} a vráti HTML podľa jazyka."""
        json_path = os.path.join(Paths.get_base_path(), Paths.ASSETS_DIR_NAME, "about.json")
        html_content = LanguageManager.get("about_fallback_html", "<p>O programe</p>")
        app_version = cls.get_app_version()
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Aktualizujeme verziu v pamäti, ak je v JSON definovaná
                    if "version" in data:
                        cls._cached_version = data["version"]
                        app_version = cls._cached_version
                        
                    current_lang = LanguageManager._current_lang_code
                    lang_key = f"about_html_{current_lang}"
                    
                    if lang_key in data:
                        html_content = data[lang_key]
                    elif "about_html_en_US" in data:
                        html_content = data["about_html_en_US"]
                    elif "about_html_sk_SK" in data:
                        html_content = data["about_html_sk_SK"]
                    elif "about_html" in data:
                        html_content = data["about_html"]
            except Exception as e:
                html_content = LanguageManager.get("about_err_load", "<p>Chyba: {0}</p>").format(e)
                
        # Dynamické dosadenie čísla verzie namiesto zástupného znaku {version}
        if "{version}" in html_content:
            html_content = html_content.replace("{version}", app_version)
            
        return html_content
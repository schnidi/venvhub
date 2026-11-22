#----------------------------------------
# Súbor: core/logic/language_manager.py
# Prechodová fasáda pre spätnú kompatibilitu.
# Deleguje všetky volania priamo do samostatného LanguageBridge.
#----------------------------------------

from typing import Any
from PyQt6.QtWidgets import QWidget
from core.logic.sluzby.language_bridge import LanguageBridge


class LanguageManager:
    """
    Spätná kompatibilita pre staré moduly.
    Všetky požiadavky transparentne preposiela do samostatného LanguageBridge.
    """

    @classmethod
    @property
    def _current_lang_code(cls) -> str:
        """Vráti kód aktuálneho jazyka (napr. 'sk_SK', 'en_US')."""
        return LanguageBridge.get_current_language()

    @classmethod
    def load_language(cls, lang_code: str = "auto"):
        """Načíta jazyk cez LanguageBridge."""
        return LanguageBridge.load_language(lang_code)

    @classmethod
    def connect_language_changed(cls, slot):
        """Pripojí widget k odberu signálu zmeny jazyka."""
        LanguageBridge.connect_language_changed(slot)

    @classmethod
    def disconnect_language_changed(cls, slot):
        """Odpojí widget z odberu signálu zmeny jazyka."""
        LanguageBridge.disconnect_language_changed(slot)

    @classmethod
    def get(cls, key: str, default: str = None) -> str:
        """Vráti preložený text podľa kľúča."""
        return LanguageBridge.translate(key, default)

    @classmethod
    def translate_ui(cls, window: QWidget):
        """Preloží prvky okna."""
        LanguageBridge.translate_window(window)
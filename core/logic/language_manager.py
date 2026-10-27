#----------------------------------------
# Súbor: core/logic/language_manager.py
# Prechodová fasáda pre spätnú kompatibilitu.
# Deleguje všetky volania priamo do novej služby cez CoreBridge.
#----------------------------------------

from typing import Any
from PyQt6.QtWidgets import QWidget
from core.core_bridge import CoreBridge


class LanguageManager:
    """
    Spätná kompatibilita pre staré moduly, ktoré ešte neboli prerobené na CoreBridge.
    Všetky požiadavky transparentne preposiela do centralizovanej služby v CoreBridge.
    """

    @classmethod
    @property
    def _current_lang_code(cls) -> str:
        """Vráti kód aktuálneho jazyka (napr. 'sk_SK', 'en_US') priamo z jadra."""
        return CoreBridge.get_current_language()

    @classmethod
    def load_language(cls, lang_code: str = "auto"):
        """Načíta jazyk do centrálnej služby v CoreBridge."""
        return CoreBridge.load_language(lang_code)

    @classmethod
    def connect_language_changed(cls, slot):
        """Pripojí widget k odberu signálu zmeny jazyka cez CoreBridge."""
        CoreBridge.connect_language_changed(slot)

    @classmethod
    def disconnect_language_changed(cls, slot):
        """Odpojí widget z odberu signálu zmeny jazyka."""
        CoreBridge.disconnect_language_changed(slot)

    @classmethod
    def get(cls, key: str, default: str = None) -> str:
        """Vráti preložený text podľa kľúča z CoreBridge."""
        return CoreBridge.translate(key, default)

    @classmethod
    def translate_ui(cls, window: QWidget):
        """Preloží prvky okna pomocou novej služby cez CoreBridge."""
        CoreBridge.translate_window(window)
#----------------------------------------------------
# Súbor: core/logic/sluzby/language_bridge.py
# Samostatná služba prekladu (LanguageBridge)
# ZÁVISLOSTI: 0 (Žiadny CoreBridge, žiadne UI)
#----------------------------------------------------

from typing import Any


class LanguageBridge:
    """Samostatná služba pre preklady bez väzieb na jadro."""

    _provider: Any = None

    @classmethod
    def register_provider(cls, provider_instance: Any) -> None:
        """Zaregistruje inštanciu poskytovateľa jazyka (LanguageManager)."""
        cls._provider = provider_instance

    @classmethod
    def translate(cls, key: str, default: str = None) -> str:
        """Vráti preložený text podľa kľúča."""
        if cls._provider and hasattr(cls._provider, "get"):
            return cls._provider.get(key, default)
        return default if default is not None else key

    @classmethod
    def get_current_language(cls) -> str:
        """Vráti aktuálny kód jazyka."""
        if cls._provider and hasattr(cls._provider, "_current_lang_code"):
            return cls._provider._current_lang_code
        return "en_US"

    @classmethod
    def load_language(cls, lang_code: str = "auto"):
        """Načíta jazykový balík."""
        if cls._provider and hasattr(cls._provider, "load_language"):
            return cls._provider.load_language(lang_code)
        return None

    @classmethod
    def translate_window(cls, window: Any) -> None:
        """Preloží prvky okna."""
        if cls._provider and hasattr(cls._provider, "translate_ui"):
            cls._provider.translate_ui(window)

    @classmethod
    def connect_language_changed(cls, slot) -> None:
        if cls._provider and hasattr(cls._provider, "language_changed"):
            cls._provider.language_changed.connect(slot)

    @classmethod
    def disconnect_language_changed(cls, slot) -> None:
        if cls._provider and hasattr(cls._provider, "language_changed"):
            try:
                cls._provider.language_changed.disconnect(slot)
            except Exception:
                pass
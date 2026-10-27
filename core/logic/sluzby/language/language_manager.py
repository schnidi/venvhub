#----------------------------------------
# Súbor: core/logic/sluzby/language/language_manager.py
#----------------------------------------
import json
import locale
import threading
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import QObject, pyqtSignal
from core._path import Paths
from core.logic.resource_manager import ResourceManager
from core.core_states import LanguageStatus  # <--- Import stavov

class LanguageManager(QObject):
    """
    Služba pre správu jazykov. 
    Priamo dedí z QObject, takže sama nesie signály.
    Je pripravená na registráciu do CoreBridge.
    """
    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._current_data = {}
        self._current_lang_code = "en_US"
        self._lock = threading.Lock()

    def load_language(self, lang_code="auto") -> LanguageStatus:
        """Načíta JSON a vráti STAV načítania pre Bridge/Logy."""
        if lang_code == "auto":
            try:
                sys_lang = locale.getdefaultlocale()[0]
                lang_code = sys_lang if sys_lang else "en_US"
            except Exception:
                lang_code = "en_US"

        trans_dir = Paths.get_translations_dir()
        status = LanguageStatus.EXACT_MATCH

        # Pokus 1: Presný kód
        content = ResourceManager.read_resource_file(trans_dir, lang_code, ".json")
        
        # Pokus 2: Skrátený kód
        if not content:
            short_code = lang_code.split('_')[0]
            content = ResourceManager.read_resource_file(trans_dir, short_code, ".json")
            status = LanguageStatus.FALLBACK_SHORT
            
        # Pokus 3: Fallback en_US
        if not content:
            content = ResourceManager.read_resource_file(trans_dir, "en_US", ".json")
            status = LanguageStatus.FALLBACK_EN

        new_data = {}
        if content:
            try:
                new_data = json.loads(content)
            except Exception as e:
                print(f"[LanguageManager] CHYBA JAZYKA (Neplatný JSON): {e}")
                status = LanguageStatus.ERROR

        with self._lock:
            self._current_lang_code = lang_code
            self._current_data = new_data

        # Odpálenie signálu (teraz priamo zo služby)
        self.language_changed.emit(lang_code)
        
        return status

    def get(self, key: str, default: str = None) -> str:
        """Vráti preklad textu podľa kľúča."""
        with self._lock:
            val = self._current_data.get(key)

        text = val if val is not None else (default if default is not None else key)
        if isinstance(text, str):
            text = text.replace("\\n", "\n")
        return text

    def translate_ui(self, window: QWidget):
        """Automaticky preloží widgety okna podľa ich objectName."""
        if not window: return

        with self._lock:
            data_copy = dict(self._current_data)

        for widget in window.findChildren(QWidget):
            name = getattr(widget, "objectName", lambda: "")()
            if not name or name.startswith("qt_"):
                continue

            text = data_copy.get(name)
            if text:
                text_clean = text.replace("\\n", "\n")
                if hasattr(widget, "setPlaceholderText"):
                    widget.setPlaceholderText(text_clean)
                elif hasattr(widget, "setText"):
                    widget.setText(text_clean)
                elif hasattr(widget, "setTitle"):
                    widget.setTitle(text_clean)

        win_name = window.objectName()
        if win_name in data_copy:
            window.setWindowTitle(data_copy[win_name].replace("\\n", "\n"))
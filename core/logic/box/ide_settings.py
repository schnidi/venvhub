#----------------------------------------
# Súbor: core/logic/box/ide_settings.py
#----------------------------------------

import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal, QSize
from PyQt6.QtGui import QIcon
from core._path import Paths
from core.logic.language_manager import LanguageManager
from core.logic.ide_detector import IDEDetector

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox


class _IDESignals(QObject):
    """
    Interný nositeľ signálu pre zmenu stavu IDE.
    Vysiela stavové dáta do všetkých pripojených GUI okien.
    """
    ide_state_changed = pyqtSignal(dict)


class IDESettingsHandler:
    """
    Centrálna logika pre správu a konfiguráciu editorov (VS Code / Cursor AI).
    Rieši stav, ikony, tooltipy, povolenia tlačidiel a vysielanie signálov pre GUI.
    """

    _signals = _IDESignals()

    _last_state = {
        "ide_type": None,
        "is_ready": None
    }

    # =========================================================================
    # --- SIGNÁLOVÝ MECHANIZMUS (PRE ČISTÉ GUI LISTENERY) ---
    # =========================================================================
    @classmethod
    def connect_ide_changed(cls, slot):
        """Prihlásenie pasívneho GUI widgetu k odberu zmeny IDE stavu."""
        cls._signals.ide_state_changed.connect(slot)

    @classmethod
    def disconnect_ide_changed(cls, slot):
        """Odhlásenie GUI widgetu z odberu."""
        try:
            cls._signals.ide_state_changed.disconnect(slot)
        except (TypeError, RuntimeError):
            pass

    @classmethod
    def get_active_ide_tooltip(cls, core) -> str:
        """Vráti lokalizovaný tooltip pre tlačidlo editora."""
        active = getattr(core, "active_ide", "vscode")
        if active == "cursor":
            return LanguageManager.get("tip_open_cursor", "Otvoriť projekt v Cursor AI")
        return LanguageManager.get("tip_open_vscode", "Otvoriť projekt vo VS Code")

    @classmethod
    def is_active_ide_ready(cls, core) -> bool:
        """Vráti True, ak je zvolený editor pripravený (systémový alebo portable)."""
        active = getattr(core, "active_ide", "vscode")
        if active == "cursor":
            return cls.is_cursor_ready(core)
        return cls.is_vscode_ready(core)

    @classmethod
    def get_ide_icon(cls, ide_type: str) -> QIcon:
        """
        Dynamicky načíta a vráti správnu SVG ikonu zo zložky tém.
        Zabezpečuje, že Qt neostane zaseknuté po interakcii (kliknutí).
        """
        if ide_type == "cursor":
            icon_path = os.path.join(Paths.get_themes_dir(), "icon", "cursor", "cursor_icon.svg")
        else:
            icon_path = os.path.join(Paths.get_themes_dir(), "icon", "vscode", "vscode5.svg")

        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon()

    @classmethod
    def apply_ide_button_state(cls, button_widget, core):
        """
        Aplikuje stav a správnu ikonu na tlačidlo:
        1. Explicitne priradí QIcon, čím prebije nacachovaný stav po kliknutí myšou.
        2. Nastaví dynamickú vlastnosť 'ide_type' pre CSS/QSS pravidlá.
        3. Preleští štýl a vynúti okamžité prekreslenie widgetu cez update().
        """
        if not button_widget:
            return

        active_ide = getattr(core, "active_ide", "vscode")
        is_ready = cls.is_active_ide_ready(core)
        tooltip = cls.get_active_ide_tooltip(core)

        # 1. Priame nastavenie ikony odstraňuje zaseknutie Qt cache
        ide_icon = cls.get_ide_icon(active_ide)
        if not ide_icon.isNull():
            button_widget.setIcon(ide_icon)
            button_widget.setIconSize(QSize(18, 18))

        # 2. Nastavenie dynamickej vlastnosti pre QSS
        button_widget.setProperty("ide_type", active_ide)

        # 3. Preleštenie štýlu
        style = button_widget.style()
        if style:
            style.unpolish(button_widget)
            style.polish(button_widget)

        button_widget.setToolTip(tooltip)
        button_widget.setEnabled(is_ready)
        button_widget.update()

    @classmethod
    def notify_ide_state(cls, core, force: bool = False):
        """
        Zostaví aktuálny stav a vystrelí signál pre všetky počúvajúce GUI okná.
        """
        active_ide = getattr(core, "active_ide", "vscode")
        is_ready = cls.is_active_ide_ready(core)

        if not force and cls._last_state["ide_type"] == active_ide and cls._last_state["is_ready"] == is_ready:
            return

        cls._last_state["ide_type"] = active_ide
        cls._last_state["is_ready"] = is_ready

        payload = {
            "ide_type": active_ide,
            "tooltip": cls.get_active_ide_tooltip(core),
            "is_ready": is_ready
        }
        cls._signals.ide_state_changed.emit(payload)

    # =========================================================================
    # --- METÓDY PRE OVERENIE DOSTUPNOSTI A VÝBER EDITORA ---
    # =========================================================================
    @staticmethod
    def is_vscode_ready(core) -> bool:
        """Overí, či je VS Code dostupný buď ako prenosný z konfigurácie, alebo v systéme."""
        portable_path = getattr(core, "portable_vscode_path", "")
        if portable_path and os.path.exists(portable_path):
            return True
        return IDEDetector.is_vscode_available()

    @staticmethod
    def is_cursor_ready(core) -> bool:
        """Overí, či je Cursor AI dostupný buď ako prenosný z konfigurácie, alebo v systéme."""
        portable_path = getattr(core, "portable_cursor_path", "")
        if portable_path and os.path.exists(portable_path):
            return True
        return IDEDetector.is_cursor_available()

    @staticmethod
    def populate_combo(combo_widget, core):
        """
        Dynamicky naplní ComboBox dostupnými editormi a nastaví aktuálne zvolenú hodnotu.
        """
        if not combo_widget:
            return

        combo_widget.blockSignals(True)
        combo_widget.clear()

        # Vynútená čerstvá detekcia stavov
        IDEDetector.detect_all()

        has_vscode = IDESettingsHandler.is_vscode_ready(core)
        has_cursor = IDESettingsHandler.is_cursor_ready(core)

        # 1. Položka: Visual Studio Code
        if has_vscode:
            name_vscode = LanguageManager.get("opt_ide_vscode", "Visual Studio Code")
            combo_widget.addItem(f"🟦 {name_vscode}", "vscode")

        # 2. Položka: Cursor AI
        if has_cursor:
            name_cursor = LanguageManager.get("opt_ide_cursor", "Cursor AI")
            combo_widget.addItem(f"⚡ {name_cursor}", "cursor")

        # 3. Ak nie je dostupný žiadny editor
        if combo_widget.count() == 0:
            none_text = LanguageManager.get("opt_ide_none", "--- Žiadny editor nenájdený ---")
            combo_widget.addItem(none_text, "")
            combo_widget.setEnabled(False)
        else:
            combo_widget.setEnabled(True)
            current_active = getattr(core, "active_ide", "vscode")

            # Nastavenie aktívneho indexu podľa core konfigurácie
            idx = combo_widget.findData(current_active)
            if idx != -1:
                combo_widget.setCurrentIndex(idx)
            else:
                combo_widget.setCurrentIndex(0)
                new_active = combo_widget.currentData()
                if new_active and new_active != getattr(core, "active_ide", None):
                    core.active_ide = new_active
                    core.save_config()

        combo_widget.blockSignals(False)

    @staticmethod
    def handle_selection_change(combo_widget, core, config_changed_signal=None):
        """
        Spracuje zmenu používateľa v ComboBoxe a uloží nový aktívny editor.
        """
        if not combo_widget:
            return

        selected_ide = combo_widget.currentData()
        if selected_ide and selected_ide != getattr(core, "active_ide", None):
            core.active_ide = selected_ide
            core.save_config()

            # Vystrelenie signálu pre zmenu stavu s vynútením (force=True)
            IDESettingsHandler.notify_ide_state(core, force=True)

            if config_changed_signal:
                config_changed_signal.emit()

    @staticmethod
    def browse_portable_path(parent_window, core, ide_type: str, line_edit, combo_widget=None, config_changed_signal=None):
        """
        Otvorí dialóg na výber prenosného priečinka pre VS Code alebo Cursor.
        Overí prítomnosť spustiteľného súboru, zapíše do core a osvieži UI.
        """
        if ide_type == "vscode":
            title = LanguageManager.get("dialog_select_portable_vscode", "Vyberte priečinok s prenosným VS Code")
            expected_files = ["code.cmd", "code.exe", "Code.exe"]
            target_attr = "portable_vscode_path"
        else:
            title = LanguageManager.get("dialog_select_portable_cursor", "Vyberte priečinok s prenosným Cursor AI")
            expected_files = ["cursor.cmd", "cursor.exe", "Cursor.exe"]
            target_attr = "portable_cursor_path"

        current_path = getattr(core, target_attr, "")
        start_dir = current_path if current_path and os.path.exists(current_path) else os.path.expanduser("~")

        selected_dir = QFileDialog.getExistingDirectory(parent_window, title, start_dir)
        if not selected_dir:
            return

        norm_path = os.path.normpath(selected_dir)

        # Overenie integrity vybraného priečinka
        found_executable = False
        for root, _, files in os.walk(norm_path):
            rel = os.path.relpath(root, norm_path)
            if rel not in [".", "bin", "resources\\app\\bin", "resources/app/bin"]:
                continue

            for ef in expected_files:
                if any(f.lower() == ef.lower() for f in files):
                    found_executable = True
                    break
            if found_executable:
                break

        if not found_executable:
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(
                parent_window,
                LanguageManager.get("title_warning", "Upozornenie"),
                LanguageManager.get(
                    "msg_portable_ide_not_found",
                    "Vo vybranom priečinku sa nenašiel spustiteľný súbor pre {0}.\n\nCesta bola napriek tomu uložená."
                ).format(ide_type.upper())
            )

        setattr(core, target_attr, norm_path)
        core.save_config()

        if line_edit:
            line_edit.setText(norm_path)

        if combo_widget:
            IDESettingsHandler.populate_combo(combo_widget, core)

        # Vystrelenie signálu pre zmenu stavu
        IDESettingsHandler.notify_ide_state(core, force=True)

        if config_changed_signal:
            config_changed_signal.emit()
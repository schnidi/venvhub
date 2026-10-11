#----------------------------------------
# Súbor: windows/widget.py
#----------------------------------------

import os
import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication, QSizePolicy
from PyQt6 import uic
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QGuiApplication, QIcon

from windows.quick_settings import QuickSettingsWindow
from core.logic.button.widget.open_manager import OpenManagerHandler
from core.logic.language_manager import LanguageManager
from core._path import Paths
from core.logic.button.widget.widget_dispatcher import WidgetDispatcher
from core.logic.sluzby.windows_location import WindowLocation
from core.logic.box.ide_settings import IDESettingsHandler


class ProjectMiniBar(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("ProjectMiniBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)

        LanguageManager.load_language(self.core.language)

        self.old_pos = None
        self.manager_window = None
        self.settings_window = QuickSettingsWindow(self.core, parent=self)
        self.settings_offset = None

        self.settings_window.status_changed.connect(self.update_status)
        self.settings_window.language_changed.connect(self.on_language_changed)
        self.settings_window.vscode_user_changed.connect(self.on_qs_vscode_user_changed)
        
        # --- NOVÉ PREPOJENIE PRE VENV ---
        self.settings_window.venv_changed.connect(self.on_qs_venv_changed)

        # --- PASÍVNY LISTENER PRE IDE (VS Code / Cursor) ---
        IDESettingsHandler.connect_ide_changed(self.on_ide_state_changed)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(2000)
        
        # Spoločná logika vykresľovania/rebuildu pri štarte aj zmene témy
        self.rebuild_ui()
        WindowLocation.restore_position(self, "widget_minibar")

    def on_ide_state_changed(self, payload=None):
        """Pasívny listener: Z jadra prišla správa o zmene IDE – aplikujeme stav na tlačidlo."""
        if hasattr(self, 'bar_widget') and hasattr(self.bar_widget, 'btn_vscode'):
            IDESettingsHandler.apply_ide_button_state(self.bar_widget.btn_vscode, self.core)

    def on_qs_venv_changed(self):
        """Vyvolá sa, keď používateľ zmení Venv v rýchlych nastaveniach. Zaktualizuje hlavného Správcu."""
        if hasattr(self, 'manager_window') and self.manager_window:
            self.manager_window.refresh_table()

    def rebuild_ui(self):
        """Jednotná logika vykresľovania/zostavenia widgetu pri štarte a pri rebuilde (zmene témy)."""
        old_widget = getattr(self, 'bar_widget', None)
        was_pin_checked = old_widget.btn_pin.isChecked() if old_widget is not None else True

        # 1. Postavíme úplne nový bar_widget - QSS je už v pamäti aplikované,
        #    takže sa rovno načíta so správnymi rozmermi tlačidiel/paddingu.
        new_widget = QWidget()
        uic.loadUi(Paths.get_ui_file_path("widget.ui"), new_widget)

        new_widget.lbl_info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        new_widget.combo_multi_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # 2. Vymeníme starý widget za nový priamo v layout-e MiniBaru, alebo ho len pridáme
        if old_widget is not None:
            self.layout().replaceWidget(old_widget, new_widget)
            old_widget.hide()
            old_widget.deleteLater()
        else:
            self.layout().addWidget(new_widget)
            
        self.bar_widget = new_widget
        self.bar_widget.show()

        # 2b. KĽÚČOVÉ: nový widget potrebuje dostať svoj Polish/Show event
        self.bar_widget.ensurePolished()
        for child in self.bar_widget.findChildren(QWidget):
            child.ensurePolished()
        QApplication.processEvents()

        # 3. Znovu nastavíme jazyk, prepojíme signály a obnovíme stav UI
        self.apply_language()
        self.connect_bar_signals()
        self.bar_widget.btn_pin.setChecked(was_pin_checked)
        self.update_ui_for_mode()

        # 3b. Aplikujeme stav IDE tlačidla (ikona podľa QSS, tooltip, stav)
        IDESettingsHandler.apply_ide_button_state(self.bar_widget.btn_vscode, self.core)

        # 3c. Nastavíme PLNÝ (neorezaný) status text ešte PRED meraním šírky,
        #    aby sizeHint labelu vychádzal z reálneho obsahu (projekt/venv),
        #    nie z krátkeho placeholdera z apply_language().
        if self.core.app_mode != 'multi':
            self.bar_widget.lbl_info.setText(self.get_full_status_text())

        # 4. Necháme layout MiniBaru prepočítať novú (reálnu) šírku
        self.layout().activate()
        QApplication.processEvents()
        self.adjustSize()
        self.layout().activate()
        self.adjustSize()

        # 4b. Až TERAZ, keď má okno finálnu správnu šírku, necháme
        #    update_status() orezať text lbl_info podľa TEJTO (správnej) šírky.
        self.update_status()

        # 5. Ak je panel rýchlych nastavení otvorený, zosúladíme jeho šírku s novým barom
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.isVisible():
            self.settings_window.setMinimumWidth(0)
            self.settings_window.setMaximumWidth(16777215)
            self.settings_window.adjustSize()
            self.settings_window.setFixedWidth(self.geometry().width())

    def on_skin_changed(self):
        """Vyvolá sa po zmene témy v Rýchlych nastaveniach / Manager okne."""
        self.rebuild_ui()

    def toggle_stay_on_top(self, checked):
        """Zapne alebo vypne 'Vždy na vrchu' PRE OBE OKNÁ ZÁROVEŇ."""
        if checked: 
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else: 
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()

        settings_was_visible = self.settings_window.isVisible()
        
        if checked:
            self.settings_window.setWindowFlags(self.settings_window.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.settings_window.setWindowFlags(self.settings_window.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
            
        if settings_was_visible:
            self.settings_window.show()

    def on_qs_vscode_user_changed(self):
        """Vyvolá sa, keď sa zmení profil v Rýchlych nastaveniach. Zabezpečí prenos do ďalších 2 okien."""
        if hasattr(self, 'manager_window') and self.manager_window:
            self.manager_window.populate_vscode_users_combo()
            
            if hasattr(self.manager_window, 'vscode_user_window') and self.manager_window.vscode_user_window:
                self.manager_window.vscode_user_window.refresh_profiles_list()

    def connect_bar_signals(self):
        self.bar_widget.btn_play.clicked.connect(lambda: WidgetDispatcher.handle_play(self))
        self.bar_widget.btn_stop.clicked.connect(lambda: WidgetDispatcher.handle_stop(self))
        
        # --- PREPOJENIE TLAČIDLA IDE ---
        self.bar_widget.btn_vscode.clicked.connect(lambda: WidgetDispatcher.handle_vscode(self))
        
        self.bar_widget.btn_open_mgr.clicked.connect(lambda: OpenManagerHandler.run(self))
        self.bar_widget.btn_pin.toggled.connect(self.toggle_stay_on_top)
        self.bar_widget.btn_mgr.clicked.connect(self.toggle_settings)
        self.bar_widget.btn_close.clicked.connect(self.close)
        
        self.bar_widget.btn_toggle_mode.clicked.connect(self.toggle_app_mode)
        self.bar_widget.combo_multi_group.currentTextChanged.connect(self.on_multi_group_changed)

    def closeEvent(self, event):
        """Vyvolá sa pri zatvorení MiniBaru (krížikom)."""
        WindowLocation.save_position(self, "widget_minibar")
        
        # Odhlásenie z odberu IDE signálu
        IDESettingsHandler.disconnect_ide_changed(self.on_ide_state_changed)

        if hasattr(self, 'settings_window') and self.settings_window:
            self.settings_window.close()
        
        if hasattr(self, 'manager_window') and self.manager_window:
            self.manager_window.close()
            
        QApplication.quit()
        event.accept()

    def toggle_app_mode(self):
        if self.core.app_mode == "single":
            self.core.app_mode = "multi"
        else:
            self.core.app_mode = "single"
        self.core.save_config()
        if self.core.app_mode == "multi":
            self.populate_multi_groups_combo()
        self.update_ui_for_mode()
        self.update_status()
        if self.manager_window:
            self.manager_window.config_changed.emit()

    def update_ui_for_mode(self):
        if self.core.app_mode == 'multi':
            self.bar_widget.lbl_info.hide()
            self.bar_widget.combo_multi_group.show()
            self.bar_widget.btn_mgr.hide()
            self.bar_widget.btn_vscode.hide()
            self.populate_multi_groups_combo()
        else:
            self.bar_widget.lbl_info.show()
            self.bar_widget.combo_multi_group.hide()
            self.bar_widget.btn_mgr.show()
            self.bar_widget.btn_vscode.show()

    def populate_multi_groups_combo(self):
        self.bar_widget.combo_multi_group.blockSignals(True)
        self.bar_widget.combo_multi_group.clear()
        groups = list(self.core.multi_groups.keys())
        if not groups:
            self.bar_widget.combo_multi_group.addItem(LanguageManager.get("msg_no_groups", "Žiadne skupiny"))
        else:
            self.bar_widget.combo_multi_group.addItems(groups)
        
        current_group = self.core.active_multi_group
        if current_group in groups:
            self.bar_widget.combo_multi_group.setCurrentText(current_group)
        elif groups:
            self.bar_widget.combo_multi_group.setCurrentText(groups[0])
            self.on_multi_group_changed(groups[0])
            
        self.bar_widget.combo_multi_group.blockSignals(False)

    def on_multi_group_changed(self, group_name):
        if group_name and group_name in self.core.multi_groups and self.core.active_multi_group != group_name:
            self.core.active_multi_group = group_name
            self.core.save_config()
            self.update_status()

    def get_full_status_text(self):
        """Vráti PLNÝ (neorezaný) text pre lbl_info."""
        proj = self.core.active_project or LanguageManager.get("msg_select_project", "Vyberte projekt")
        v_path = self.core.active_venv_path
        v_name = "---"
        if v_path and self.core.active_project:
            base_name = os.path.basename(v_path)
            prefix = f"{self.core.active_project}_"
            if base_name.startswith(prefix):
                v_name = base_name[len(prefix):]
            else:
                v_name = base_name
        return f"{proj} ({v_name})"

    def update_status(self):
        if self.core.app_mode == 'multi':
            active_group_name = self.core.active_multi_group
            self.bar_widget.lbl_dot.setStyleSheet(f"color: #e74c3c;")
            tip_msg = LanguageManager.get(
                "tip_active_group",
                "Aktívna skupina: {0}"
            ).format(active_group_name)
            self.bar_widget.combo_multi_group.setToolTip(tip_msg)
            return

        full_text = self.get_full_status_text()
        font_metrics = self.bar_widget.lbl_info.fontMetrics()
        elided_text = font_metrics.elidedText(full_text, Qt.TextElideMode.ElideMiddle, self.bar_widget.lbl_info.width())
        self.bar_widget.lbl_info.setText(elided_text)
        self.bar_widget.lbl_info.setToolTip(full_text)
        
        v_path = self.core.active_venv_path
        exists = v_path and os.path.exists(v_path)
        color = "#2ecc71" if exists else "#e74c3c"
        self.bar_widget.lbl_dot.setStyleSheet(f"color: {color};")
        
    def on_language_changed(self, lang_code):
        LanguageManager.load_language(lang_code)
        
        self.apply_language()
        
        if self.settings_window: 
            self.settings_window.retranslate_ui()
            
        if self.manager_window: 
            self.manager_window.retranslate_ui()
            
        self.update_status()

    def apply_language(self, init=False):
        # 1. Automatický preklad všetkého z JSON
        LanguageManager.translate_ui(self.bar_widget)
        
        # 2. Manuálne prepísanie vecí, ktoré sa menia dynamicky
        self.bar_widget.btn_toggle_mode.setText("")
        
        # --- Udržanie správnej ikony (šípka/koleso) po zmene jazyka ---
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.isVisible():
            self.bar_widget.btn_mgr.setText("▼")
        else:
            self.bar_widget.btn_mgr.setText("⚙")
            
        # 3. Tooltipy a ostatné texty
        self.bar_widget.btn_pin.setToolTip(LanguageManager.get("btn_pin_tooltip", "Stále navrchu"))
        self.bar_widget.btn_toggle_mode.setToolTip(LanguageManager.get("btn_toggle_mode_tooltip", "Prepnúť režim Single/Multi"))
        self.bar_widget.lbl_info.setText(LanguageManager.get("lbl_info", "Načítavam..."))
        
        # 4. Aplikujeme preložený tooltip a stav pre tlačidlo IDE
        IDESettingsHandler.apply_ide_button_state(self.bar_widget.btn_vscode, self.core)
        
        if self.core.app_mode == 'multi' and self.bar_widget.combo_multi_group.count() > 0:
            if not list(self.core.multi_groups.keys()):
                self.bar_widget.combo_multi_group.setItemText(0, LanguageManager.get("msg_no_groups", "Žiadne skupiny"))

    def get_position(self):
        pos = self.pos()
        return [pos.x(), pos.y()]

    def toggle_settings(self):
        """Vyroluje alebo skryje panel rýchlych nastavení. S nulovou medzerou (bezšvovo)."""
        if self.settings_window.isVisible():
            self.settings_window.hide()
            self.bar_widget.btn_mgr.setText("⚙")
            self.settings_offset = None
        else:
            self.settings_window.populate_panel()
            self.settings_window.adjustSize() 
            
            screen_geo = QGuiApplication.primaryScreen().availableGeometry()
            bar_geo = self.geometry()
            settings_h = self.settings_window.height()
            
            space_below = screen_geo.height() - (bar_geo.y() + bar_geo.height())
            
            if space_below < settings_h and bar_geo.y() > settings_h:
                pos_y = bar_geo.y() - settings_h
            else:
                pos_y = bar_geo.y() + bar_geo.height()
                
            settings_pos = self.pos()
            settings_pos.setY(pos_y)
            
            self.settings_window.move(settings_pos)
            self.settings_window.setFixedWidth(bar_geo.width())
            self.settings_window.show()
            self.bar_widget.btn_mgr.setText("▼")
            
            self.settings_offset = self.settings_window.pos() - self.pos()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: 
            self.old_pos = event.globalPosition().toPoint()
        
    def mouseMoveEvent(self, event):
        if self.old_pos:
            delta = event.globalPosition().toPoint() - self.old_pos
            new_main_pos = self.pos() + delta
            self.move(new_main_pos)
            self.old_pos = event.globalPosition().toPoint()
            if self.settings_offset is not None and self.settings_window.isVisible():
                self.settings_window.move(new_main_pos + self.settings_offset)
            
    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def on_config_changed(self):
        """Vyvolá sa, ak sa zmení hlavná konfigurácia napr. zo Správcu."""
        if self.core.app_mode == 'multi':
            self.populate_multi_groups_combo()
        self.update_status()
        
        # Aktualizácia stavu IDE tlačidla
        IDESettingsHandler.apply_ide_button_state(self.bar_widget.btn_vscode, self.core)
        
        # Rýchlym nastaveniam vnútime aktualizáciu okamžite bez ohľadu na to, či ich je vidno
        if hasattr(self, 'settings_window') and self.settings_window:
            self.settings_window.populate_vscode_users_combo()
            
            if self.settings_window.isVisible():
                self.settings_window.populate_panel()

            # Vynútime si synchronizáciu s Venv-om
            if self.core.active_venv_path:
                from core.logic.sluzby.local_packages_sync import LocalPackagesSyncService
                LocalPackagesSyncService.sync_venv_to_vscode(self.core, self.core.active_venv_path)
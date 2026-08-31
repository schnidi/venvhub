"""
Súbor: windows/custom_title_bar.py
Univerzálna titulková lišta, ktorú používajú okná v aplikácii.
"""

import os
from PyQt6.QtWidgets import QWidget
from PyQt6 import uic
from PyQt6.QtCore import Qt, QSize, QUrl
from PyQt6.QtGui import QIcon, QDesktopServices

from core._path import Paths
from core.logic.sluzby.about_logic import AboutLogic
from core.logic.sluzby.github_update import GitHubUpdate
from core.logic.language_manager import LanguageManager


class CustomTitleBar(QWidget):
    """Univerzálna titulková lišta, ktorú používajú okná v aplikácii."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_window = parent

        uic.loadUi(Paths.get_ui_file_path("custom_title_bar.ui"), self)
        self.lbl_icon.setScaledContents(False)
        self.old_pos = None

        if hasattr(self, 'btn_update_github'):
            self.btn_update_github.hide()

        self.connect_signals()
        self.setup_from_parent()

        if self.parent_window and hasattr(self.parent_window, 'windowTitleChanged'):
            self.parent_window.windowTitleChanged.connect(self.lbl_title.setText)

        self.refresh_update_button()
        LanguageManager.connect_language_changed(self.retranslate_ui)

    def connect_signals(self):
        """Prepojenie tlačidiel lišty s funkciami rodičovského okna."""
        self.btn_minimize.clicked.connect(self.parent_window.showMinimized)
        self.btn_maximize.clicked.connect(self.toggle_maximize_restore)
        self.btn_close.clicked.connect(self.parent_window.close)
        self.btn_about.clicked.connect(self.show_about_dialog)

        if hasattr(self, 'btn_update_github'):
            self.btn_update_github.clicked.connect(self.open_update_url)

    def set_title(self, text: str):
        """Priame manuálne nastavenie textu do lišty (Stará metóda)."""
        self.lbl_title.setText(text)

    def setup_from_parent(self):
        """Prevezme titulok a ikony pre panel z rodičovského okna."""
        if self.parent_window and self.parent_window.windowTitle():
            self.lbl_title.setText(self.parent_window.windowTitle())

        icon_path = Paths.get_icon_path("app.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            size = 30
            self.lbl_icon.setFixedSize(size, size)
            smooth_pixmap = icon.pixmap(size, size)
            self.lbl_icon.setPixmap(smooth_pixmap)
        else:
            self.lbl_icon.hide()

        about_icon_path = Paths.get_icon_path("about.svg")
        if os.path.exists(about_icon_path) and hasattr(self, 'btn_about'):
            self.btn_about.setIcon(QIcon(about_icon_path))
            self.btn_about.setIconSize(QSize(18, 18))

    def retranslate_ui(self, lang_code: str = None):
        """Znovu nastaví preložiteľné texty titulkovej lišty po zmene jazyka."""
        LanguageManager.translate_ui(self)

        if self.parent_window and self.parent_window.windowTitle():
            self.lbl_title.setText(self.parent_window.windowTitle())

        self.refresh_update_button()

    def refresh_update_button(self):
        """Prečíta stav aktualizácie priamo z pamäte (GitHubUpdate) a nastaví UI."""
        if not hasattr(self, 'btn_update_github'):
            return

        has_update = GitHubUpdate.get_status()
        if has_update:
            self.btn_update_github.show()
        else:
            self.btn_update_github.hide()

    def open_update_url(self):
        """Otvorí webovú stránku projektu v predvolenom prehliadači."""
        url_str = GitHubUpdate.get_download_url()
        QDesktopServices.openUrl(QUrl(url_str))

    def show_about_dialog(self):
        AboutLogic.show_about_dialog(self.parent_window)

    def toggle_maximize_restore(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
            self.btn_maximize.setText("🗖")
        else:
            self.parent_window.showMaximized()
            self.btn_maximize.setText("🗗")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos and not self.parent_window.isMaximized():
            delta = event.globalPosition().toPoint() - self.old_pos
            self.parent_window.move(
                self.parent_window.x() + delta.x(),
                self.parent_window.y() + delta.y()
            )
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize_restore()
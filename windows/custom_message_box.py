#----------------------------------------
# Súbor: windows/custom_message_box.py
#----------------------------------------

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QWidget, QMessageBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from core._path import Paths
from windows.custom_title_bar import CustomTitleBar
from core.logic.language_manager import LanguageManager

class CustomMessageBox(QDialog):
    """
    Vlastný Message Box, ktorý používa CustomTitleBar a vyzerá rovnako 
    ako zvyšok aplikácie (Frameless).
    """
    def __init__(self, parent, title, text, icon_type=QMessageBox.Icon.NoIcon, buttons=QMessageBox.StandardButton.Ok):
        super().__init__(parent)
        
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("CustomMessageBox") # Pre QSS
        
        # Hlavný layout bez okrajov
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)
        
        # Vloženie vlastnej lišty
        self.title_bar = CustomTitleBar(self)
        self.title_bar.btn_minimize.hide()
        self.title_bar.btn_maximize.hide()
        self.title_bar.btn_about.hide()
        self.main_layout.addWidget(self.title_bar)
        
        # Vnútorný kontajner
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)
        
        # Text správy
        self.lbl_text = QLabel(text)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet("font-size: 13px;")
        
        # Môžeš sem neskôr pridať aj logiku pre ikony (Warning, Critical...)
        # nateraz dáme len text
        content_layout.addWidget(self.lbl_text)
        
        # Tlačidlá
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.result = QMessageBox.StandardButton.NoButton
        
        # Vygenerovanie tlačidiel podľa zadania
        if buttons & QMessageBox.StandardButton.Yes:
            btn_yes = QPushButton(LanguageManager.get("btn_yes", "Áno"))
            btn_yes.setMinimumWidth(80)
            btn_yes.clicked.connect(lambda: self.finish(QMessageBox.StandardButton.Yes))
            btn_layout.addWidget(btn_yes)
            
        if buttons & QMessageBox.StandardButton.No:
            btn_no = QPushButton(LanguageManager.get("btn_no", "Nie"))
            btn_no.setMinimumWidth(80)
            btn_no.clicked.connect(lambda: self.finish(QMessageBox.StandardButton.No))
            btn_layout.addWidget(btn_no)
            
        if buttons & QMessageBox.StandardButton.Ok:
            btn_ok = QPushButton("OK")
            btn_ok.setMinimumWidth(80)
            btn_ok.clicked.connect(lambda: self.finish(QMessageBox.StandardButton.Ok))
            btn_layout.addWidget(btn_ok)
            
        content_layout.addLayout(btn_layout)
        self.main_layout.addWidget(self.content_widget)

    def finish(self, result_button):
        self.result = result_button
        self.accept()

    # --- STATICKÉ METÓDY AKO MÁ ŠTANDARDNÝ QMessageBox ---

    @staticmethod
    def warning(parent, title, text, buttons=QMessageBox.StandardButton.Ok):
        dialog = CustomMessageBox(parent, title, text, QMessageBox.Icon.Warning, buttons)
        dialog.exec()
        return dialog.result

    @staticmethod
    def critical(parent, title, text, buttons=QMessageBox.StandardButton.Ok):
        dialog = CustomMessageBox(parent, title, text, QMessageBox.Icon.Critical, buttons)
        dialog.exec()
        return dialog.result

    @staticmethod
    def information(parent, title, text, buttons=QMessageBox.StandardButton.Ok):
        dialog = CustomMessageBox(parent, title, text, QMessageBox.Icon.Information, buttons)
        dialog.exec()
        return dialog.result

    @staticmethod
    def question(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No):
        dialog = CustomMessageBox(parent, title, text, QMessageBox.Icon.Question, buttons)
        dialog.exec()
        return dialog.result
#----------------------------------------
# Súbor: windows/progress_dialog.py
#----------------------------------------

from PyQt6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QTextEdit, QPushButton, QWidget
from PyQt6.QtCore import Qt, pyqtSignal

# --- POUŽITIE ČISTÉHO JAZYKOVÉHO MOSTA ---
from core.logic.sluzby.language_bridge import LanguageBridge
from windows.custom_title_bar import CustomTitleBar


class ProgressDialog(QDialog):
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProgressDialog")
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setModal(True)
        self.setMinimumWidth(450)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        self.title_bar.btn_minimize.hide()
        self.title_bar.btn_maximize.hide()
        self.title_bar.btn_about.hide()
        self.main_layout.addWidget(self.title_bar)

        self.content_widget = QWidget()
        self.layout = QVBoxLayout(self.content_widget)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(10)
        
        self.message_label = QLabel(LanguageBridge.translate("msg_please_wait", "Prosím, čakajte..."))
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.message_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumHeight(150)
        self.log_output.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas; font-size: 12px; padding: 5px;")
        self.layout.addWidget(self.log_output)

        self.btn_cancel = QPushButton(LanguageBridge.translate("btn_cancel", "Zrušiť operáciu"))
        self.btn_cancel.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; padding: 5px;")
        self.btn_cancel.hide() 
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.layout.addWidget(self.btn_cancel)

        self.main_layout.addWidget(self.content_widget)

    def setWindowTitle(self, title):
        super().setWindowTitle(title)
        if hasattr(self, 'title_bar'):
            self.title_bar.lbl_title.setText(title)

    def closeEvent(self, event):
        if self.btn_cancel.isVisible() and self.btn_cancel.isEnabled():
            self._on_cancel_clicked()
            event.ignore()
        else:
            event.ignore()

    def set_message(self, text):
        self.message_label.setText(text)

    def add_log_message(self, message):
        self.log_output.append(message)
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def enable_cancel_button(self):
        self.btn_cancel.show()

    def _on_cancel_clicked(self):
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText(LanguageBridge.translate("msg_cancelling", "Ruším operáciu, prosím čakajte..."))
        self.cancelled.emit()

    def set_progress_mode(self, indeterminate=True):
        if indeterminate:
            self.progress_bar.setRange(0, 0)
            self.progress_bar.setTextVisible(False)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setTextVisible(True)
            self.progress_bar.setValue(0)

    def set_progress_value(self, value):
        self.progress_bar.setValue(value)
#----------------------------------------
# Súbor: core/logic/python_installer/box/python_ver_json.py
#----------------------------------------

import os
import json
import ctypes
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtCore import QObject, QFileSystemWatcher
from core.logic.language_manager import LanguageManager
from core._path import Paths 

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox

class PythonVersionJsonManager(QObject):
    def __init__(self, combo_urls: QComboBox):
        super().__init__()
        self.combo_urls = combo_urls
        self.jsonl_path = Paths.get_python_versions_jsonl_path()
        
        # --- Sledovač zmien súboru ---
        self.watcher = QFileSystemWatcher()
        if os.path.exists(self.jsonl_path):
            self.watcher.addPath(self.jsonl_path)
            
        self.watcher.fileChanged.connect(self._on_file_saved)

    def _on_file_saved(self, path):
        """Táto metóda sa vystrelí okamžite, keď dáš v Notepade 'Uložiť'."""
        self.load_versions()
        
        if os.path.exists(self.jsonl_path) and self.jsonl_path not in self.watcher.files():
            self.watcher.addPath(self.jsonl_path)

    def load_versions(self):
        """
        Načíta dáta z .jsonl súboru a naplní rozbaľovacie menu.
        """
        self.combo_urls.clear()
        
        self.combo_urls.addItem(LanguageManager.get("combo_select_version", "-- Vyberte verziu zo zoznamu --"), userData="")

        if not os.path.exists(self.jsonl_path):
            print(f"Upozornenie: Súbor {self.jsonl_path} nebol nájdený.")
            return

        try:
            with open(self.jsonl_path, 'r', encoding='utf-8') as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        name = data.get("name", LanguageManager.get("txt_unknown_version", "Neznáma verzia"))
                        url = data.get("url", "")
                        
                        self.combo_urls.addItem(name, userData=url)
                        
                    except json.JSONDecodeError:
                        print(f"Chyba pri čítaní riadku v JSONL: {line}")
                        
        except Exception as e:
            print(f"Chyba pri otváraní súboru {self.jsonl_path}: {e}")

    def get_selected_url(self) -> str:
        """
        Vráti URL vybranej položky z comboboxu.
        """
        return self.combo_urls.currentData()

    def edit_jsonl_file_as_admin(self, parent_widget=None):
        """
        Otvorí .jsonl súbor v poznámkovom bloku s administrátorskými právami (UAC).
        """
        if not os.path.exists(self.jsonl_path):
            os.makedirs(os.path.dirname(self.jsonl_path), exist_ok=True)
            with open(self.jsonl_path, 'w', encoding='utf-8') as f:
                f.write('{"name": "Python 3.13.5 (64-bit)", "url": "https://www.python.org/ftp/python/3.13.5/python-3.13.5-embed-amd64.zip"}\n')
            
            if self.jsonl_path not in self.watcher.files():
                self.watcher.addPath(self.jsonl_path)

        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None, 
                "runas", 
                "notepad.exe", 
                self.jsonl_path, 
                None, 
                1
            )
            
            if result <= 32:
                if parent_widget:
                    # --- ZMENA NA NAŠU LIŠTU ---
                    CustomMessageBox.warning(
                        parent_widget,
                        LanguageManager.get("title_access_denied", "Prístup odmietnutý"),
                        LanguageManager.get("msg_admin_rights_required", "Pre úpravu tohto súboru sú potrebné administrátorské práva.\nÚprava bola zrušená.")
                    )
                else:
                    print("UAC zamietnuté alebo chyba pri spúšťaní Notepadu.")
                    
        except Exception as e:
            print(f"Nepodarilo sa otvoriť editor: {e}")
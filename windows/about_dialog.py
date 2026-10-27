#----------------------------------------
# Súbor: windows/about_dialog.py
#----------------------------------------

import os
import json
from datetime import datetime
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QTextEdit, QFrame, QWidget
from PyQt6.QtCore import Qt
from core._path import Paths
from core.core_bridge import CoreBridge
from core.logic.sluzby.about_logic import AboutLogic
from windows.custom_title_bar import CustomTitleBar


class AboutDialog(QDialog):
    """Vlastné okno 'O programe' s našou custom lištou a podporou rodného listu."""
    def __init__(self, parent, html_content):
        super().__init__(parent)
        self.setMinimumWidth(450)
        
        # 1. Zrušíme štandardný Windows rám
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("AboutDialog")

        # 2. Hlavný layout BEZ OKRAJOV, aby naša lišta sadla na milimeter
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)
        self.main_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

        # 3. Vložíme našu Custom Title Bar a skryjeme zbytočné tlačidlá
        self.title_bar = CustomTitleBar(self)
        self.title_bar.btn_minimize.hide()
        self.title_bar.btn_maximize.hide()
        self.title_bar.btn_about.hide()
        self.main_layout.addWidget(self.title_bar)

        # 4. Vnútorný kontajner (s okrajmi pre texty)
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # -- HTML Obsah (Hlavička, Info) --
        self.lbl_info = QLabel(html_content)
        self.lbl_info.setOpenExternalLinks(True)
        self.lbl_info.setWordWrap(True)
        content_layout.addWidget(self.lbl_info)

        # -- Vodorovná oddeľovacia čiara --
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        content_layout.addWidget(line)

        # -- Tlačidlo na zobrazenie rodného listu --
        self.btn_toggle_cert = QPushButton("")
        self.btn_toggle_cert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_cert.setCheckable(True)
        self.btn_toggle_cert.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #007acc;
                border: none;
                text-align: left;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton:hover {
                text-decoration: underline;
            }
        """)
        self.btn_toggle_cert.clicked.connect(self.toggle_certificate)
        content_layout.addWidget(self.btn_toggle_cert)

        # -- Textové pole pre výpis certifikátu (predvolene skryté) --
        self.txt_cert = QTextEdit()
        self.txt_cert.setReadOnly(True)
        self.txt_cert.setMinimumHeight(200)
        self.txt_cert.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas; font-size: 12px; padding: 5px;")
        self.txt_cert.hide()
        content_layout.addWidget(self.txt_cert)

        # -- Spodné tlačidlo OK --
        self.btn_ok = QPushButton("")
        self.btn_ok.setFixedWidth(100)
        self.btn_ok.clicked.connect(self.accept)
        
        # Vycentrovanie tlačidla OK
        bottom_layout = QVBoxLayout()
        bottom_layout.addSpacing(10)
        bottom_layout.addWidget(self.btn_ok, alignment=Qt.AlignmentFlag.AlignCenter)
        content_layout.addLayout(bottom_layout)

        # Vloženie celého kontentu do hlavného layoutu
        self.main_layout.addWidget(self.content_widget)

        # =====================================================================
        # REAL-TIME PREKLAD: Napojenie na most jadra a prvotné načítanie textov
        # =====================================================================
        CoreBridge.connect_language_changed(self.retranslate_ui)
        self.retranslate_ui()

    def closeEvent(self, event):
        """Pri zatvorení okna sa odpojíme od signálu."""
        CoreBridge.disconnect_language_changed(self.retranslate_ui)
        super().closeEvent(event)

    def retranslate_ui(self, lang_code=None):
        """Táto metóda sa spustí IN-TIME pri zmene jazyka a prepíše texty naživo."""
        self.setWindowTitle(CoreBridge.translate("title_about", "O programe"))
        
        # Dynamická aktualizácia celého HTML obsahu podľa nového jazyka
        self.lbl_info.setText(AboutLogic.get_about_html())

        # Ošetrenie stavu tlačidla
        if self.btn_toggle_cert.isChecked():
            self.btn_toggle_cert.setText(CoreBridge.translate("btn_hide_cert", "▼ Skryť technické detaily"))
        else:
            self.btn_toggle_cert.setText(CoreBridge.translate("btn_show_cert", "▶ Zobraziť technické detaily (Rodný list)"))
            
        self.btn_ok.setText(CoreBridge.translate("btn_close_dialog", "Zavrieť"))
        
        # Prekreslíme aj obsah rodného listu
        self.load_latest_certificate()

    def load_latest_certificate(self):
        """Vyhľadávanie a parsovanie najnovšieho rodného listu."""
        search_dirs = [
            Paths.get_app_root_path(),  
            Paths.get_base_path(),      
            os.path.join(Paths.get_app_root_path(), Paths.ASSETS_DIR_NAME),
            os.path.join(Paths.get_base_path(), Paths.ASSETS_DIR_NAME)
        ]

        cert_files = []
        for d in set(search_dirs):
            if os.path.exists(d):
                try:
                    for f in os.listdir(d):
                        if f.endswith("birth_certificate.json"):
                            cert_files.append(os.path.join(d, f))
                except Exception:
                    pass

        latest_cert = None
        latest_sort_key = ""

        for file_path in cert_files:
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                    
                    date_str = str(data.get("build_date") or data.get("last_updated") or data.get("created_at") or "")
                    if not date_str:
                        mtime = os.path.getmtime(file_path)
                        date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

                    if date_str > latest_sort_key:
                        latest_sort_key = date_str
                        latest_cert = data
                        latest_cert['_actual_date_str'] = date_str 
                        latest_cert['_filepath'] = file_path       
            except Exception as e:
                print(f"[AboutDialog] Ignorujem neplatný certifikát: {file_path} - Chyba: {e}")
                continue

        if latest_cert:
            filename = os.path.basename(latest_cert.get('_filepath', ''))
            
            txt_header = CoreBridge.translate("cert_header", "--- NAJNOVŠÍ RODNÝ LIST ({0}) ---").format(filename)
            txt_type = CoreBridge.translate("cert_type", "Typ dokumentu: {0}")
            txt_date = CoreBridge.translate("cert_date", "Dátum buildu: {0}")
            txt_python = CoreBridge.translate("cert_python", "Python: {0}")
            txt_deps = CoreBridge.translate("cert_deps", "Závislosti a balíčky ({0}):")
            
            info = f"{txt_header}\n"
            
            doc_type = latest_cert.get('document_type', CoreBridge.translate("cert_unknown", "Neznámy"))
            info += f"{txt_type.format(doc_type)}\n"
            info += f"{txt_date.format(latest_cert.get('_actual_date_str'))}\n"
            
            env = latest_cert.get('python_environment', {})
            python_ver = env.get('python_version') or latest_cert.get('python_version', CoreBridge.translate("cert_unknown", "Neznámy"))
            info += f"{txt_python.format(python_ver)}\n\n"
            
            packages = env.get('installed_packages') or latest_cert.get('packages', [])
            info += f"{txt_deps.format(len(packages))}\n"
            
            for pkg in sorted(packages, key=lambda x: x.get('name', '').lower()):
                info += f" - {pkg.get('name')} (v{pkg.get('version')})\n"
                
            self.txt_cert.setPlainText(info)
        else:
            fallback_msg = CoreBridge.translate(
                "cert_not_found", 
                "Rodný list nebol nájdený.\n\nAplikácia hľadala súbory končiace na '_birth_certificate.json'\nv priečinku: {0}"
            ).format(Paths.get_app_root_path())
            self.txt_cert.setPlainText(fallback_msg)

    def toggle_certificate(self, checked):
        """Zobrazí alebo skryje pole s technickými detailmi."""
        if checked:
            self.txt_cert.show()
            self.btn_toggle_cert.setText(CoreBridge.translate("btn_hide_cert", "▼ Skryť technické detaily"))
        else:
            self.txt_cert.hide()
            self.btn_toggle_cert.setText(CoreBridge.translate("btn_show_cert", "▶ Zobraziť technické detaily (Rodný list)"))
            
            # --- OPRAVA SKÁKANIA BEZRÁMOVÉHO OKNA ---
            self.layout().invalidate()
            self.layout().activate()
            self.resize(self.width(), self.minimumSizeHint().height())
#----------------------------------------------------
# Súbor: windows/package_security_audit.py
# Bezrámové okno bezpečnostného auditu (Passive View).
# Napojené na SecurityScanWorker a PackageOperationsService.
# 100% textov cez LanguageManager (žiadny hardcoded reťazec).
#----------------------------------------------------

import os
from PyQt6.QtWidgets import QDialog, QTableWidgetItem, QHeaderView, QPushButton, QWidget, QHBoxLayout
from PyQt6 import uic
from PyQt6.QtCore import Qt, pyqtSlot, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from core._path import Paths
from core.logic.language_manager import LanguageManager
from windows.custom_title_bar import CustomTitleBar
from windows.custom_message_box import CustomMessageBox
from core.logic.sluzby.windows_location import WindowLocation

# Import nového univerzálneho workera a služby inštalácie
from core.logic.sluzby.security.security_worker import SecurityScanWorker
from core.logic.sluzby.venv.pack_inst_unis import PackageOperationsService
from core.core_states import PackageOperationStatus


class _QuickFixWorker(QThread):
    """Pomocné asynchrónne vlákno na inštaláciu opravnej verzie balíčka."""
    finished_status = pyqtSignal(object)  # PackageOperationStatus

    def __init__(self, core, venv_path: str, target_spec: str, parent=None):
        super().__init__(parent)
        self.core = core
        self.venv_path = venv_path
        self.target_spec = target_spec

    def run(self):
        # Spustí PackageOperationsService v tichom režime s presmerovaním do printu/konzoly
        status = PackageOperationsService.install_packages(
            core=self.core,
            venv_path=self.venv_path,
            packages=[self.target_spec],
            log_callback=print
        )
        self.finished_status.emit(status)


class PackageSecurityAuditDialog(QDialog):
    """
    Pasívne GUI okno auditu balíčkov.
    Zabezpečuje zobrazenie CVE a umožňuje aplikovať rýchle bezpečnostné opravy.
    """

    def __init__(self, parent, core, venv_path: str):
        super().__init__(parent)
        self.core = core
        self.venv_path = venv_path
        self.scan_worker = None
        self.fix_worker = None

        # 1. Bezrámové okno s jednotným štýlovaním cez QSS
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("PackageSecurityAuditDialog")

        # 2. Načítanie UI layoutu
        uic.loadUi(Paths.get_ui_file_path("package_security_audit.ui"), self)

        # 3. Nastavenie základnej a minimálnej veľkosti (trochu širšie pre stĺpec akcie)
        self.resize(1180, 720)
        self.setMinimumSize(950, 500)

        # 4. Vloženie vlastnej titulkovej lišty (CustomTitleBar)
        self.title_bar = CustomTitleBar(self)
        self.title_bar.btn_minimize.show()
        self.title_bar.btn_maximize.show()
        self.title_bar.btn_about.hide()
        self.main_layout.insertWidget(0, self.title_bar)
        self.main_layout.setContentsMargins(1, 1, 1, 1)

        # 5. Prispôsobenie stĺpcov tabuľky (7 stĺpcov vrátane akcie)
        self._setup_table_headers()
        self._connect_signals()
        self.retranslate_ui()

        # 6. Obnovenie zapamätanej pozície okna
        WindowLocation.restore_position(self, "package_security_audit_dialog")

        # 7. Automatický štart auditu
        self.start_scan()

    def _setup_table_headers(self):
        """Nastaví kompaktné šírky pre kľúčové stĺpce, stretch na popis a fixnú šírku pre akciu."""
        self.table_audit.setColumnCount(7)
        header = self.table_audit.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Stav / Riziko
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Balíček
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Verzia
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Zraniteľnosť
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Opravené v
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)      # Popis
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)        # Tlačidlo akcie

        self.table_audit.setColumnWidth(0, 110)
        self.table_audit.setColumnWidth(1, 150)
        self.table_audit.setColumnWidth(2, 85)
        self.table_audit.setColumnWidth(3, 130)
        self.table_audit.setColumnWidth(4, 105)
        self.table_audit.setColumnWidth(6, 140)

        self.table_audit.setWordWrap(True)
        self.table_audit.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def _connect_signals(self):
        self.btn_rescan.clicked.connect(self.start_scan)
        self.btn_close.clicked.connect(self.close)

    def closeEvent(self, event):
        """Uloží pozíciu okna a bezpečne ukončí bežiace vlákna."""
        WindowLocation.save_position(self, "package_security_audit_dialog")
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.quit()
            self.scan_worker.wait(1000)
        if self.fix_worker and self.fix_worker.isRunning():
            self.fix_worker.wait(2000)
        event.accept()

    def retranslate_ui(self):
        """Načíta preklady cez LanguageManager pre všetky prvky."""
        LanguageManager.translate_ui(self)

        title_text = LanguageManager.get("sec_audit_win_title", "Bezpečnostný audit prostredia")
        self.setWindowTitle(title_text)
        if hasattr(self, 'title_bar') and self.title_bar:
            self.title_bar.lbl_title.setText(title_text)

        venv_name = os.path.basename(self.venv_path) if self.venv_path else "---"
        header_text = LanguageManager.get("sec_audit_header_fmt", "Bezpečnostný audit prostredia: {0}").format(venv_name)
        self.lbl_header.setText(header_text)

        self.btn_rescan.setText(LanguageManager.get("btn_sec_audit_rescan", "🔄 Spustiť audit znova"))
        self.btn_close.setText(LanguageManager.get("btn_close_dialog", "Zavrieť"))
        self.lbl_provider_info.setText(LanguageManager.get("sec_audit_provider_info", "Zdroj dát: OSV.dev (Open Source Vulnerabilities)"))

        headers = [
            LanguageManager.get("col_sec_risk", "Stav / Riziko"),
            LanguageManager.get("col_sec_package", "Balíček"),
            LanguageManager.get("col_sec_version", "Verzia"),
            LanguageManager.get("col_sec_vuln_id", "Zraniteľnosť (ID)"),
            LanguageManager.get("col_sec_fixed_in", "Opravené vo verzii"),
            LanguageManager.get("col_sec_summary", "Popis zraniteľnosti"),
            LanguageManager.get("col_sec_action", "Riešenie")
        ]
        for i, h_text in enumerate(headers):
            item = self.table_audit.horizontalHeaderItem(i)
            if not item:
                item = QTableWidgetItem()
                self.table_audit.setHorizontalHeaderItem(i, item)
            item.setText(h_text)

    # =========================================================================
    # LOGIKA AUDITU (SecurityScanWorker)
    # =========================================================================

    def start_scan(self):
        """Spustí asynchrónny audit cez nový SecurityScanWorker."""
        if (self.scan_worker and self.scan_worker.isRunning()) or (self.fix_worker and self.fix_worker.isRunning()):
            return

        self.btn_rescan.setEnabled(False)
        self.table_audit.setRowCount(0)
        self.lbl_summary.setText(LanguageManager.get("sec_audit_running", "⏳ Prebieha audit prostredia, čakajte prosím..."))
        self.lbl_summary.setStyleSheet("color: #f39c12; font-weight: bold; font-size: 13px;")

        # Vytvorenie a spustenie SecurityScanWorker
        self.scan_worker = SecurityScanWorker(
            venv_path=self.venv_path,
            core=self.core,
            parent=self
        )
        self.scan_worker.progress_msg.connect(self.on_progress_update)
        self.scan_worker.finished_signal.connect(self.render_report_from_dict)
        self.scan_worker.start()

    @pyqtSlot(str)
    def on_progress_update(self, text: str):
        self.lbl_summary.setText(text)

    @pyqtSlot(dict)
    def render_report_from_dict(self, report_dict: dict):
        """Prijíma štandardný slovník z SecurityScanWorker a vykreslí tabuľku."""
        self.btn_rescan.setEnabled(True)

        status = report_dict.get("status", "ERROR")
        error_msg = report_dict.get("error_message", "")
        packages_data = report_dict.get("packages", {})
        total_scanned = report_dict.get("total_scanned", 0)
        vulnerable_count = report_dict.get("vulnerable_count", 0)

        # Ak prišiel slovník (nový worker), prevedieme na zoznam hodnôt
        if isinstance(packages_data, dict):
            packages_list = list(packages_data.values())
        else:
            packages_list = packages_data or []

        # 1. Chyba alebo prázdny stav
        if status == "ERROR":
            self.lbl_summary.setText(LanguageManager.get("sec_audit_err_occurred", "❌ Audit zlyhal"))
            self.lbl_summary.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")
            CustomMessageBox.critical(
                self,
                LanguageManager.get("title_error", "Chyba"),
                error_msg or LanguageManager.get("sec_audit_unknown_err", "Nastala neznáma chyba pri audite.")
            )
            return

        if total_scanned == 0:
            self.lbl_summary.setText(LanguageManager.get("sec_audit_no_pkgs", "ℹ️ Vo venv nie sú žiadne balíčky na audit."))
            self.lbl_summary.setStyleSheet("color: #888888; font-weight: bold; font-size: 13px;")
            return

        # 2. Súhrnný štítok
        if vulnerable_count == 0:
            summary_txt = LanguageManager.get(
                "sec_audit_all_safe_fmt",
                "✅ Všetkých {total} skontrolovaných balíčkov je BEZ známych zraniteľností."
            ).format(total=total_scanned)
            self.lbl_summary.setText(summary_txt)
            self.lbl_summary.setStyleSheet("color: #2ecc71; font-weight: bold; font-size: 13px;")
        else:
            summary_txt = LanguageManager.get(
                "sec_audit_vuln_found_fmt",
                "⚠️ Pozor! Nájdené zraniteľnosti v {vuln} z {total} balíčkov."
            ).format(vuln=vulnerable_count, total=total_scanned)
            self.lbl_summary.setText(summary_txt)
            self.lbl_summary.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")

        # 3. Zotriedenie výsledkov (zraniteľné hore, potom abecedne)
        sorted_packages = sorted(
            packages_list,
            key=lambda p: (len(p.get("vulnerabilities", [])) == 0, p.get("package_name", "").lower())
        )

        # 4. Vykreslenie riadkov
        self.table_audit.setRowCount(0)
        safe_badge_text = LanguageManager.get("sec_badge_safe", "🟢 BEZPEČNÝ")
        safe_desc_text = LanguageManager.get("sec_desc_safe", "Neboli nájdené žiadne evidované zraniteľnosti")
        unknown_fixed_text = LanguageManager.get("sec_fixed_unknown", "Neznáma")

        for pkg in sorted_packages:
            pkg_name = pkg.get("package_name", "")
            pkg_version = pkg.get("installed_version", "")
            vulns = pkg.get("vulnerabilities", [])

            if not vulns:
                self._add_table_row(
                    risk_badge=safe_badge_text,
                    risk_color=QColor("#2ecc71"),
                    package=pkg_name,
                    version=pkg_version,
                    vuln_id="-",
                    fixed_in="-",
                    summary=safe_desc_text,
                    can_upgrade=False
                )
            else:
                for v in vulns:
                    severity = v.get("severity", "UNKNOWN")
                    vuln_id = v.get("cve_id") or v.get("vuln_id", "")
                    fixed_ver = str(v.get("fixed_version") or "").strip()
                    fixed_version_display = fixed_ver if fixed_ver else unknown_fixed_text
                    summary = v.get("summary", "")

                    risk_color, risk_text = self._get_severity_badge(severity)

                    self._add_table_row(
                        risk_badge=risk_text,
                        risk_color=risk_color,
                        package=pkg_name,
                        version=pkg_version,
                        vuln_id=vuln_id,
                        fixed_in=fixed_version_display,
                        summary=summary,
                        can_upgrade=bool(fixed_ver and fixed_ver != unknown_fixed_text),
                        upgrade_version=fixed_ver
                    )

    def _get_severity_badge(self, severity_str: str) -> tuple[QColor, str]:
        """Vráti farbu a lokalizovaný text štítka podľa závažnosti."""
        sev = severity_str.upper()
        if sev == "CRITICAL":
            return QColor("#e74c3c"), LanguageManager.get("sec_badge_critical", "🔴 KRITICKÉ")
        elif sev == "HIGH":
            return QColor("#e67e22"), LanguageManager.get("sec_badge_high", "🟠 VYSOKÉ")
        elif sev == "MEDIUM":
            return QColor("#f39c12"), LanguageManager.get("sec_badge_medium", "🟡 STREDNÉ")
        elif sev == "LOW":
            return QColor("#3498db"), LanguageManager.get("sec_badge_low", "🔵 NÍZKE")
        return QColor("#95a5a6"), LanguageManager.get("sec_badge_unknown", "⚪ NEZNÁME")

    def _add_table_row(
        self,
        risk_badge: str,
        risk_color: QColor,
        package: str,
        version: str,
        vuln_id: str,
        fixed_in: str,
        summary: str,
        can_upgrade: bool = False,
        upgrade_version: str = ""
    ):
        """Vloží riadok do tabuľky a ak je dostupný update, vytvorí tlačidlo na inštaláciu."""
        row = self.table_audit.rowCount()
        self.table_audit.insertRow(row)

        item_risk = QTableWidgetItem(risk_badge)
        item_risk.setForeground(risk_color)
        item_risk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_pkg = QTableWidgetItem(package)
        item_ver = QTableWidgetItem(version)
        item_ver.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_id = QTableWidgetItem(vuln_id)
        item_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        item_fixed = QTableWidgetItem(fixed_in)
        item_fixed.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if fixed_in not in ("-", LanguageManager.get("sec_fixed_unknown", "Neznáma")):
            item_fixed.setForeground(QColor("#2ecc71"))

        item_desc = QTableWidgetItem(summary)
        item_desc.setToolTip(summary)

        self.table_audit.setItem(row, 0, item_risk)
        self.table_audit.setItem(row, 1, item_pkg)
        self.table_audit.setItem(row, 2, item_ver)
        self.table_audit.setItem(row, 3, item_id)
        self.table_audit.setItem(row, 4, item_fixed)
        self.table_audit.setItem(row, 5, item_desc)

        # 7. STĹPEC: Akčné tlačidlo (Riešenie)
        if can_upgrade and upgrade_version:
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_fix = QPushButton(f"⬆️ {upgrade_version}")
            btn_fix.setToolTip(LanguageManager.get("sec_tooltip_fix", "Nainštalovať opravnú verziu {0}").format(upgrade_version))
            btn_fix.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-weight: bold;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
                QPushButton:disabled {
                    background-color: #7f8c8d;
                }
            """)
            target_spec = f"{package}=={upgrade_version}"
            btn_fix.clicked.connect(lambda checked, spec=target_spec: self._apply_package_fix(spec))
            layout.addWidget(btn_fix)

            self.table_audit.setCellWidget(row, 6, container)
        else:
            item_empty = QTableWidgetItem("-" if not can_upgrade else "")
            item_empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_audit.setItem(row, 6, item_empty)

    # =========================================================================
    # AKCIA OPRAVY (PackageOperationsService)
    # =========================================================================

    def _apply_package_fix(self, target_spec: str):
        """Spustí inštaláciu opravenej verzie balíčka na pozadí."""
        msg_confirm = LanguageManager.get(
            "sec_confirm_install_fix",
            "Prajete si nainštalovať opravnú verziu balíčka:\n'{0}'?"
        ).format(target_spec)

        if not CustomMessageBox.question(self, LanguageManager.get("title_confirm", "Potvrdenie"), msg_confirm):
            return

        self.btn_rescan.setEnabled(False)
        self.lbl_summary.setText(LanguageManager.get("sec_installing_fix", "📦 Inštalujem bezpečnostnú opravu: {0}...").format(target_spec))
        self.lbl_summary.setStyleSheet("color: #3498db; font-weight: bold; font-size: 13px;")

        self.fix_worker = _QuickFixWorker(self.core, self.venv_path, target_spec, parent=self)
        self.fix_worker.finished_status.connect(self._on_fix_finished)
        self.fix_worker.start()

    @pyqtSlot(object)
    def _on_fix_finished(self, status: PackageOperationStatus):
        """Vyhodnotí stav inštalácie a znova preskenuje prostredie."""
        if status == PackageOperationStatus.SUCCESS:
            CustomMessageBox.information(
                self,
                LanguageManager.get("title_success", "Úspech"),
                LanguageManager.get("sec_fix_installed_ok", "Bezpečnostná oprava bola úspešne nainštalovaná. Prebieha opätovný audit...")
            )
            # Automatický rescan po oprave
            self.start_scan()
        else:
            self.btn_rescan.setEnabled(True)
            self.lbl_summary.setText(LanguageManager.get("sec_fix_failed", "❌ Inštalácia opravy zlyhala."))
            self.lbl_summary.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")
            CustomMessageBox.critical(
                self,
                LanguageManager.get("title_error", "Chyba"),
                LanguageManager.get("sec_fix_failed_desc", "Nepodarilo sa úspešne nainštalovať opravnú verziu balíčka.")
            )
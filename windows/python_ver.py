#-------------------------------------------------------------------------------
# Súbor: windows/python_ver.py
# Grafické rozhranie (GUI) pre správu a inštaláciu lokálnych Python runtime prostredí.
# Plne prepnuté na stavový mostík CoreBridge s Enumami PythonOrigin a PythonPipStatus.
#-------------------------------------------------------------------------------

"""
Modul PythonVerWindow poskytuje používateľské rozhranie pre:
- Výber a sťahovanie lokálnych Python embed verzií.
- Prehľad nájdených runtimov s ich stavovými farebnými indikátormi.
- Spúšťanie opráv nefunkčného PIPu a bezpečné mazanie runtimov cez ProgressDialog.
"""

import os
from PyQt6.QtWidgets import QWidget, QTableWidgetItem, QHeaderView, QMessageBox
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6 import uic

from core._path import Paths
from core.core_bridge import CoreBridge
from core.core_states import PythonOrigin, PythonPipStatus

from core.logic.python_installer.box.python_ver_json import PythonVersionJsonManager
from core.logic.python_installer.box.source_path import SourcePathManager
from core.logic.python_installer.button.python_install import PythonInstaller
from core.logic.python_installer.button.pip_installer import PipInstaller
from core.logic.sluzby.python_runtime_inspector import PipStatusWorker

from windows.custom_message_box import CustomMessageBox
from windows.progress_dialog import ProgressDialog


class RuntimeDeleteWorker(QThread):
    """
    Asynchrónny pracovník na postupné mazanie runtimu z disku
    s priebežným odosielaním percentuálneho stavu do GUI.
    """
    progress = pyqtSignal(int)
    log_msg = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)

    def __init__(self, target_path: str):
        """
        Inicializuje workera pre vymazanie cieľového priečinka.
        
        Args:
            target_path (str): Absolútna cesta k zložke runtimu, ktorá sa má zmazať.
        """
        super().__init__()
        self.target_path = target_path

    def run(self):
        """Vykoná bezpečné vymazanie na pozadí."""
        from core.logic.sluzby.copy_del import CopyDelService
        result = CopyDelService.safe_delete_with_progress(
            target_path=self.target_path,
            log_func=self.log_msg.emit,
            progress_func=self.progress.emit
        )
        self.finished_signal.emit(result)


class PythonVerWindow(QWidget):
    """
    Klientske okno pre inštaláciu a evidenciu Python runtime verzií.
    Všetky operácie nad interpretmi deleguje na CoreBridge.
    """

    def __init__(self, parent=None):
        """Inicializuje okno, načíta UI šablónu a pripraví ovládacie prvky."""
        super().__init__(parent)
        
        ui_path = Paths.get_ui_file_path("python_ver.ui")
        uic.loadUi(ui_path, self)

        # Inicializácia manažérov formulára
        self.json_manager = PythonVersionJsonManager(self.combo_urls)
        self.source_path_manager = SourcePathManager(self.edit_path, self.btn_browse, self)
        self.installer = PythonInstaller(self.log_output, self.progress_bar, self.btn_install)
        self.pip_installer = PipInstaller(self.log_output, self.btn_repair)

        self.check_thread = None
        self.check_worker = None
        self._delete_worker = None

        self._setup_table()
        self._connect_signals()

        self.json_manager.load_versions()
        self.retranslate_ui()
        self.refresh_table()

    def retranslate_ui(self):
        """Aplikuje lokalizované texty pre hlavičky tabuľky a prvky okna."""
        CoreBridge.translate_window(self)
        if self.table_runtimes.columnCount() >= 3:
            if not self.table_runtimes.horizontalHeaderItem(0):
                self.table_runtimes.setHorizontalHeaderLabels(["", "", ""])
            self.table_runtimes.horizontalHeaderItem(0).setText(
                CoreBridge.translate("col_runtime_ver", "Verzia")
            )
            self.table_runtimes.horizontalHeaderItem(1).setText(
                CoreBridge.translate("col_runtime_path", "Cesta")
            )
            self.table_runtimes.horizontalHeaderItem(2).setText(
                CoreBridge.translate("col_runtime_pip", "Stav PIP")
            )
            
        self.log_output.clear()
        self.refresh_table()

    def _setup_table(self):
        """Nakonfiguruje správanie stĺpcov tabuľky a zakáže priamu editáciu buniek."""
        header = self.table_runtimes.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self.table_runtimes.setSelectionBehavior(self.table_runtimes.SelectionBehavior.SelectRows)
        self.table_runtimes.setEditTriggers(self.table_runtimes.EditTrigger.NoEditTriggers)

    def _connect_signals(self):
        """Prepojí signály tlačidiel, tabuľky a asynchrónnych inštalátorov."""
        self.btn_edit_urls.clicked.connect(self._on_edit_urls_clicked)
        self.combo_urls.currentIndexChanged.connect(self._on_version_selected)
        self.btn_install.clicked.connect(self.start_installation)
        
        self.btn_refresh.clicked.connect(self.force_refresh_table)
        self.btn_delete.clicked.connect(self.delete_selected_runtime)
        self.btn_repair.clicked.connect(self.repair_selected_pip)
        self.table_runtimes.itemSelectionChanged.connect(self.on_row_selected)
        
        # Automatické obnovenie tabuľky po dokončení inštalácie alebo opravy
        self.installer.installation_finished.connect(
            lambda result: self.refresh_table() if result.get('success') else None
        )
        self.pip_installer.installation_finished.connect(
            lambda result: self.refresh_table() if result.get('success') else None
        )
        
        self.edit_path.textChanged.connect(self._check_install_status)

    def start_installation(self):
        """Overí zadaný zdroj (URL alebo lokálny zip) a spustí inštaláciu Pythonu."""
        source_info = self.source_path_manager.get_source_info()
        if not source_info['is_valid']:
            err_title = CoreBridge.translate("title_error", "Chyba")
            self.log_output.append(f"{err_title}: {source_info['error']}")
            return

        self.installer.install(source_info)

    def force_refresh_table(self):
        """Vykoná vynútené (tvrdé) preskenovanie disku a nanovo načíta tabuľku."""
        msg = CoreBridge.translate("msg_force_scan", "Vynútené skenovanie disku (tvrdý reset pamäte)...")
        self.log_output.append(msg)
        CoreBridge.get_installed_pythons(force_refresh=True)
        self.refresh_table()

    def refresh_table(self):
        """
        Naplní tabuľku lokálnymi verziami Pythonu z pamäte CoreBridge.
        Aplikuje presné stavové Enumy: PythonOrigin.LOCAL a PythonPipStatus.
        """
        self.table_runtimes.setRowCount(0)
        self.btn_repair.setEnabled(False) 
        
        all_pythons = CoreBridge.get_installed_pythons(force_refresh=False)
        local_pythons = [p for p in all_pythons if p.get('origin') == PythonOrigin.LOCAL or p.get('is_local')]
        
        paths_to_check = []
        
        for p in local_pythons:
            row = self.table_runtimes.rowCount()
            self.table_runtimes.insertRow(row)
            
            pip_status = p.get('pip_status', PythonPipStatus.MISSING)
            
            # Stavové vyhodnotenie cez Enum
            if pip_status == PythonPipStatus.OK:
                display_status = CoreBridge.translate("status_ok_fmt", "✅ OK")
                status_color = QColor("#2ecc71")
            elif pip_status == PythonPipStatus.CHECKING:
                display_status = CoreBridge.translate("status_checking_fmt", "⏳ Kontrolujem...")
                status_color = QColor("#f39c12")
                paths_to_check.append(p['path'])
            elif pip_status == PythonPipStatus.ERROR:
                display_status = CoreBridge.translate("status_error_fmt", "⚠️ Havária PIP")
                status_color = QColor("#e74c3c")
            else:
                display_status = CoreBridge.translate("status_missing_fmt", "❌ Chýba")
                status_color = QColor("#e74c3c")
                
            ver_name = p['display'].replace("[Local] ", "").strip()
            folder_path = os.path.dirname(p['path'])
            
            item_ver = QTableWidgetItem(ver_name)
            item_path = QTableWidgetItem(folder_path)
            item_pip = QTableWidgetItem(display_status)
            
            item_pip.setForeground(status_color)
            item_pip.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_pip.setData(Qt.ItemDataRole.UserRole, pip_status)
            
            self.table_runtimes.setItem(row, 0, item_ver)
            self.table_runtimes.setItem(row, 1, item_path)
            self.table_runtimes.setItem(row, 2, item_pip)
            
        loaded_msg = CoreBridge.translate("msg_loaded_from_mem", "Zoznam načítaný rýchlo z pamäte.")
        self.log_output.append(loaded_msg)
        
        if paths_to_check:
            self._start_pip_check(paths_to_check)
            
        self._check_install_status()

    def _start_pip_check(self, paths: list[str]):
        """Spustí asynchrónne overenie funkčnosti nástroja PIP pre zvolené runtimy."""
        try:
            if self.check_thread and self.check_thread.isRunning():
                return
        except RuntimeError:
            self.check_thread = None
            self.check_worker = None
            
        self.check_thread = QThread()
        self.check_worker = PipStatusWorker(paths)
        self.check_worker.moveToThread(self.check_thread)
        
        self.check_worker.result_ready.connect(self._on_pip_check_result)
        self.check_worker.finished.connect(self.check_thread.quit)
        self.check_worker.finished.connect(self.check_worker.deleteLater)
        self.check_thread.finished.connect(self.check_thread.deleteLater)
        self.check_thread.finished.connect(self._cleanup_check_thread)
        
        self.check_thread.started.connect(self.check_worker.run)
        self.check_thread.start()

    def _cleanup_check_thread(self):
        """Uvoľní referencie na dokončené kontrolné vlákno."""
        self.check_thread = None
        self.check_worker = None

    def _on_pip_check_result(self, python_path: str, is_ok: bool):
        """Slot: Prijme výsledok overenia PIPu a aktualizuje Enum stav v pamäti aj v UI."""
        status_enum = PythonPipStatus.OK if is_ok else PythonPipStatus.ERROR
        CoreBridge.update_python_pip_status(python_path, status_enum)
        
        expected_dir = os.path.normpath(os.path.dirname(python_path)).lower()
        
        for row in range(self.table_runtimes.rowCount()):
            path_in_table = os.path.normpath(self.table_runtimes.item(row, 1).text()).lower()
            if path_in_table == expected_dir:
                item_pip = self.table_runtimes.item(row, 2)
                if is_ok:
                    item_pip.setText(CoreBridge.translate("status_ok_fmt", "✅ OK"))
                    item_pip.setForeground(QColor("#2ecc71"))
                else:
                    item_pip.setText(CoreBridge.translate("status_missing_fmt", "❌ Chýba"))
                    item_pip.setForeground(QColor("#e74c3c"))
                    
                item_pip.setData(Qt.ItemDataRole.UserRole, status_enum)
                break
                
        self.on_row_selected()

    def on_row_selected(self):
        """Vyhodnotí označený riadok a povolí tlačidlo 'Opraviť PIP', ak je poškodený."""
        selected_items = self.table_runtimes.selectedItems()
        if not selected_items:
            self.btn_repair.setEnabled(False)
            return

        row = selected_items[0].row()
        pip_status_item = self.table_runtimes.item(row, 2)
        
        raw_status = pip_status_item.data(Qt.ItemDataRole.UserRole)
        is_broken = (raw_status not in [PythonPipStatus.OK, PythonPipStatus.CHECKING, "OK", "checking"])
        
        self.btn_repair.setEnabled(is_broken)

    def repair_selected_pip(self):
        """Spustí opravný skript get-pip.py a konfiguráciu site-packages pre zvolený interpreter."""
        selected_items = self.table_runtimes.selectedItems()
        if not selected_items:
            return

        row = selected_items[0].row()
        runtime_path = self.table_runtimes.item(row, 1).text()
        python_exe_path = os.path.join(runtime_path, 'python.exe')
        
        msg_template = CoreBridge.translate("msg_starting_pip_repair", "Spúšťam opravu PIP pre: {0}...")
        self.log_output.append(msg_template.format(os.path.basename(runtime_path)))
        self.pip_installer.install(python_exe_path)
        
    def _on_edit_urls_clicked(self):
        """Otvorí definičný JSONL súbor v editore s administrátorskými právami."""
        self.json_manager.edit_jsonl_file_as_admin(parent_widget=self)
        msg = CoreBridge.translate("msg_jsonl_editor_opened", "Editor JSONL otvorený. Po úprave obnovte zoznam.")
        self.log_output.append(msg)

    def _on_version_selected(self):
        """Vloží URL zvolenú v rozbaľovacom zozname priamo do vstupného poľa."""
        url = self.json_manager.get_selected_url()
        self.edit_path.setText(url if url else "")
            
    def delete_selected_runtime(self):
        """Zobrazí potvrdzovací dialóg a bezpečne zmaže celý lokálny runtime z disku."""
        selected_items = self.table_runtimes.selectedItems()
        if not selected_items:
            CustomMessageBox.warning(
                self, 
                CoreBridge.translate("title_warning", "Upozornenie"), 
                CoreBridge.translate("msg_select_version_first", "Najskôr vyberte verziu zo zoznamu.")
            )
            return
            
        row = selected_items[0].row()
        version_name = self.table_runtimes.item(row, 0).text()
        target_path = self.table_runtimes.item(row, 1).text()
        
        confirm_title = CoreBridge.translate("title_confirm", "Potvrdenie")
        confirm_msg = CoreBridge.translate(
            "msg_confirm_delete_runtime", 
            "Naozaj chcete natrvalo odstrániť túto položku?\n\n{0}"
        ).format(version_name)
        
        reply = CustomMessageBox.question(
            self, confirm_title, confirm_msg, 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            progress_title = CoreBridge.translate("title_deleting", "Prebieha mazanie...")
            progress_msg = CoreBridge.translate("msg_deleting_progress", "Mažem: {0}").format(version_name)
            
            progress_dialog = ProgressDialog(self)
            progress_dialog.setWindowTitle(progress_title)
            progress_dialog.set_message(progress_msg)
            progress_dialog.set_progress_mode(indeterminate=False)
            
            self._delete_worker = RuntimeDeleteWorker(target_path)

            def on_finished(result: dict):
                progress_dialog.accept()
                
                if result.get("success"):
                    msg_success = CoreBridge.translate(
                        "msg_runtime_deleted_success", 
                        "Položka '{0}' bola úspešne vymazaná."
                    ).format(version_name)
                    self.log_output.append(msg_success)
                    
                    python_exe_path = os.path.join(target_path, 'python.exe')
                    CoreBridge.remove_local_python(python_exe_path)
                    
                    self.refresh_table()
                else:
                    error_reason = result.get("error", "Neznáma chyba")
                    self.log_output.append(f"CHYBA: {error_reason}")
                    CustomMessageBox.critical(
                        self, 
                        CoreBridge.translate("title_error", "Chyba"), 
                        error_reason
                    )

            self._delete_worker.progress.connect(progress_dialog.set_progress_value, Qt.ConnectionType.QueuedConnection)
            self._delete_worker.log_msg.connect(self.log_output.append, Qt.ConnectionType.QueuedConnection)
            self._delete_worker.finished_signal.connect(on_finished, Qt.ConnectionType.QueuedConnection)
            self._delete_worker.finished.connect(self._delete_worker.deleteLater)
            
            self._delete_worker.start()
            progress_dialog.exec()

    def _check_install_status(self):
        """
        Zistí, či cieľový priečinok z URL/cesty už náhodou neexistuje na disku.
        Ak áno, prepne inštalačné tlačidlo do stavu 'NAINŠTALOVANÉ' a zablokuje ho.
        """
        expected_dir = self.source_path_manager.get_expected_install_dir()
        is_installed = False
        
        if expected_dir and os.path.exists(expected_dir):
            if os.path.exists(os.path.join(expected_dir, "python.exe")):
                is_installed = True
            else:
                for item in os.listdir(expected_dir):
                    sub = os.path.join(expected_dir, item)
                    if os.path.isdir(sub) and os.path.exists(os.path.join(sub, "python.exe")):
                        is_installed = True
                        break
                        
        if is_installed:
            self.btn_install.setText(CoreBridge.translate("btn_already_installed", "✅ NAINŠTALOVANÉ"))
            self.btn_install.setEnabled(False)
        else:
            self.btn_install.setText(CoreBridge.translate("btn_install", "🛠 INŠTALOVAŤ"))
            self.btn_install.setEnabled(True)
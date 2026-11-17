#-------------------------------------------------------------------------------
# Súbor: core/logic/python_installer/button/python_install.py
# Logika a asynchrónny worker pre sťahovanie, rozbalenie a inštaláciu Python runtimu.
# Registruje nový interpreter do mostíka CoreBridge s Enumom PythonPipStatus.CHECKING.
#-------------------------------------------------------------------------------

"""
Tento modul zabezpečuje:
- Validáciu existencie a predchádzanie duplicite ešte pred sťahovaním.
- Asynchrónne sťahovanie ZIP archívu so sledovaním percentuálneho priebehu.
- Rozbalenie archívu do dočasného priečinka a vytvorenie install.ini markera.
- Bezpečný presun priečinka (v prípade potreby s asistenciou systémového UAC).
- Okamžitú registráciu nového lokálneho prostredia do pamäte CoreBridge.
"""

import os
import shutil
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt

from core._path import Paths
from core.core_bridge import CoreBridge
from core.core_states import PythonPipStatus
from core.logic.sluzby.downloader import Downloader
from core.logic.sluzby.unzip import ZipExtractor
from core.logic.sluzby.win_admin import WinAdmin


class PythonInstallWorker(QObject):
    """
    Pracovník bežiaci vo vedľajšom vlákne.
    Zabezpečuje sťahovanie zo siete, rozbalenie ZIPu a inštaláciu Pythonu bez mrznutia GUI.
    """
    progress_log = pyqtSignal(str)
    progress_percent = pyqtSignal(int)
    finished = pyqtSignal(dict) 

    def __init__(self, source_info: dict):
        """
        Inicializuje inštalačného workera.

        Args:
            source_info (dict): Slovník s údajmi o zdroji {'type': 'url'/'local', 'path': str}.
        """
        super().__init__()
        self.source_info = source_info
        self.is_cancelled = False

    def run(self):
        """Vykoná celý inštalačný cyklus: kontrola -> stiahnutie -> rozbalenie -> presun -> registrácia."""
        source_path = self.source_info['path']
        downloaded_zip_path = None
        temp_dir = Paths.get_python_downloads_dir()
        base_install_dir = Paths.get_python_runtimes_install_dir()

        # === 1. KONTROLA EŠTE PRED SŤAHOVANÍM ===
        filename = os.path.basename(source_path)
        folder_name = os.path.splitext(filename)[0]
        final_destination_dir = os.path.join(base_install_dir, folder_name)
        install_marker_path = os.path.join(final_destination_dir, "install.ini")

        # Ak zložka existuje a má marker, ukončíme bez zbytočného sťahovania dát
        if os.path.exists(final_destination_dir) and os.path.exists(install_marker_path):
            err_msg = CoreBridge.translate(
                "msg_py_already_installed", "Táto verzia Pythonu je už nainštalovaná: {0}"
            ).format(folder_name)
            self.finished.emit({'success': False, 'error': err_msg})
            return

        # === 2. SŤAHOVANIE ALEBO POUŽITIE LOKÁLNEHO SÚBORU ===
        if self.source_info['type'] == 'url':
            msg_downloading = CoreBridge.translate(
                "msg_downloading_from", "Sťahujem súbor z: {0}"
            ).format(source_path)
            self.progress_log.emit(msg_downloading)
            downloaded_zip_path = os.path.join(temp_dir, filename)

            def download_progress(downloaded, total):
                if self.is_cancelled:
                    raise Exception("Sťahovanie bolo prerušené.")
                percent = int((downloaded / total) * 100) if total > 0 else 0
                self.progress_percent.emit(percent)

            result = Downloader.download_file(source_path, downloaded_zip_path, download_progress)
            if not result['success']:
                err_down = CoreBridge.translate(
                    "msg_download_err", "Chyba pri sťahovaní: {0}"
                ).format(result['error'])
                self.finished.emit({'success': False, 'error': err_down})
                return
            
            self.progress_log.emit(CoreBridge.translate("msg_download_success", "Súbor bol úspešne stiahnutý."))
            source_zip_to_extract = downloaded_zip_path
        else:
            source_zip_to_extract = source_path
        
        if self.is_cancelled:
            return

        # === 3. ROZBALENIE ARCHÍVU ===
        zip_filename = os.path.basename(source_zip_to_extract)
        folder_name = os.path.splitext(zip_filename)[0]
        final_destination_dir = os.path.join(base_install_dir, folder_name)

        temp_extract_dir = os.path.join(temp_dir, f"temp_{folder_name}")
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)

        self.progress_log.emit(CoreBridge.translate("msg_extracting", "Rozbaľujem archív..."))
        self.progress_percent.emit(0)
        
        def unzip_progress(current, total, unzip_filename):
            if self.is_cancelled:
                raise Exception("Rozbaľovanie bolo prerušené.")
            percent = int((current / total) * 100) if total > 0 else 0
            self.progress_percent.emit(percent)

        result = ZipExtractor.extract(source_zip_to_extract, temp_extract_dir, unzip_progress)
        if not result['success']:
            err_unzip = CoreBridge.translate(
                "msg_unzip_err", "Chyba pri rozbaľovaní: {0}"
            ).format(result['error'])
            self.finished.emit({'success': False, 'error': err_unzip})
            return

        # Zápis statusu úspešnej inštalácie
        try:
            with open(os.path.join(temp_extract_dir, "install.ini"), "w", encoding="utf-8") as f:
                f.write("[Status]\nstatus=success\n")
        except Exception as e:
            warn_ini = CoreBridge.translate(
                "msg_install_ini_err", "Upozornenie: Nepodarilo sa vytvoriť install.ini: {0}"
            ).format(e)
            self.progress_log.emit(warn_ini)

        # === 4. PRESUN SÚBOROV DO CIEĽA (S ALEBO BEZ UAC) ===
        needs_admin = WinAdmin.needs_admin_for_path(final_destination_dir)

        if needs_admin:
            self.progress_log.emit(
                CoreBridge.translate("msg_uac_needed", "Vyžadujú sa práva Administrátora. Prosím, potvrďte systémové UAC okno...")
            )
            
            def on_state_changed(state_str):
                if state_str == "[STATUS] UAC_APPROVED":
                    self.progress_log.emit(CoreBridge.translate("msg_uac_approved", "✅ UAC schválené. Spúšťam proces s administrátorskými právami..."))
                elif state_str == "[STATUS] PREPARING":
                    self.progress_log.emit(CoreBridge.translate("msg_uac_preparing", "Pripravujem cieľový priečinok..."))
                elif state_str == "[STATUS] COPYING":
                    self.progress_log.emit(CoreBridge.translate("msg_uac_copying", "Kopírujem súbory na systémový disk (môže to chvíľu trvať)..."))
                elif state_str == "[STATUS] CLEANING":
                    self.progress_log.emit(CoreBridge.translate("msg_uac_cleaning", "Mažem dočasné inštalačné súbory..."))
                elif state_str == "[STATUS] ERROR_COPY":
                    self.progress_log.emit(CoreBridge.translate("msg_uac_error_copy", "❌ Nastala chyba pri kopírovaní!"))
                elif state_str == "[STATUS] DONE":
                    self.progress_log.emit(CoreBridge.translate("msg_uac_done", "✅ Operácia na systémovom disku dokončená."))
                
            success = WinAdmin.move_directory_with_uac(temp_extract_dir, final_destination_dir, state_callback=on_state_changed)
            
            if not success:
                err_cancel = CoreBridge.translate(
                    "msg_install_cancelled", "Inštalácia bola zrušená alebo zlyhala (súbory neboli prekopírované)."
                )
                self.finished.emit({'success': False, 'error': err_cancel})
                return
        else:
            try:
                self.progress_log.emit(CoreBridge.translate("msg_preparing_write", "Kopírujem súbory do cieľovej lokácie..."))
                os.makedirs(base_install_dir, exist_ok=True)
                if os.path.exists(final_destination_dir):
                    shutil.rmtree(final_destination_dir, ignore_errors=True)
                shutil.move(temp_extract_dir, final_destination_dir)
            except Exception as e:
                err_move = CoreBridge.translate("msg_move_dir_err", "Chyba pri presune zložky: {0}").format(e)
                self.finished.emit({'success': False, 'error': err_move})
                return

        # Vyčistenie stiahnutého ZIPu
        if downloaded_zip_path and os.path.exists(downloaded_zip_path):
            try:
                os.remove(downloaded_zip_path)
            except Exception:
                pass

        # Nájdenie výsledného python.exe
        final_python_exe = os.path.join(final_destination_dir, 'python.exe')
        if not os.path.exists(final_python_exe):
            for item in os.listdir(final_destination_dir):
                sub = os.path.join(final_destination_dir, item)
                if os.path.isdir(sub) and os.path.exists(os.path.join(sub, 'python.exe')):
                    final_python_exe = os.path.join(sub, 'python.exe')
                    break
        
        # === 5. REGISTRÁCIA DO PAMÄTE CEZ COREBRIDGE S ENUMOM CHECKING ===
        CoreBridge.add_local_python(folder_name, final_python_exe, pip_status=PythonPipStatus.CHECKING)
        
        self.progress_log.emit(CoreBridge.translate("msg_install_success", "Inštalácia bola úspešne dokončená!"))
        self.progress_percent.emit(100)
        self.finished.emit({'success': True, 'path': final_python_exe})

    def cancel(self):
        """Nastaví príznak prerušenia inštalácie."""
        self.is_cancelled = True


class PythonInstaller(QObject):
    """
    Riadiaci manažér pre proces inštalácie Pythonu.
    Prepája inštalačné vlákno s ovládacími prvkami grafického rozhrania.
    """
    installation_finished = pyqtSignal(dict)

    def __init__(self, log_widget, progress_bar, install_button):
        """
        Inicializuje manažéra inštalácie.

        Args:
            log_widget: Textové pole pre výpis logov (QTextEdit).
            progress_bar: Ukazovateľ priebehu (QProgressBar).
            install_button: Tlačidlo pre spustenie inštalácie (QPushButton).
        """
        super().__init__()
        self.log_widget = log_widget
        self.progress_bar = progress_bar
        self.install_button = install_button
        self.install_thread = None
        self.worker = None

    def _handle_log(self, msg: str):
        self.log_widget.append(msg)

    def _handle_progress(self, val: int):
        self.progress_bar.setValue(val)

    def _handle_finished(self, result: dict):
        self.on_installation_finished(result)

    def install(self, source_info: dict):
        """Spustí inštaláciu vo vyhradenom vlákne, ak už nejaká neprebieha."""
        if self.install_thread and self.install_thread.isRunning():
            busy_msg = CoreBridge.translate("msg_install_in_progress", "! Iná inštalácia už prebieha.")
            self.log_widget.append(busy_msg)
            return

        self.install_button.setEnabled(False)
        self.install_button.setText(CoreBridge.translate("btn_installing", "⏳ INŠTALUJEM..."))

        self.install_thread = QThread()
        self.worker = PythonInstallWorker(source_info)
        self.worker.moveToThread(self.install_thread)

        self.worker.progress_log.connect(self._handle_log, Qt.ConnectionType.QueuedConnection)
        self.worker.progress_percent.connect(self._handle_progress, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self._handle_finished, Qt.ConnectionType.QueuedConnection)

        self.install_thread.started.connect(self.worker.run)
        self.install_thread.start()

    def on_installation_finished(self, result: dict):
        """Spracuje ukončenie inštalácie, odomkne tlačidlo a uprace vlákno."""
        if not result['success']:
            err_title = CoreBridge.translate("title_error", "Chyba")
            self.log_widget.append(f"{err_title}: {result['error']}")
        
        self.install_button.setEnabled(True)
        self.install_button.setText(CoreBridge.translate("btn_install", "🛠 INŠTALOVAŤ"))
        
        self.installation_finished.emit(result)
        
        if self.install_thread:
            self.install_thread.quit()
            self.worker.deleteLater()
            self.install_thread.deleteLater()
            self.install_thread = None
            self.worker = None
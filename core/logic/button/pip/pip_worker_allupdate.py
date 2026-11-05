#----------------------------------------------------
# Súbor: core/logic/button/pip/pip_worker_allupdate.py
# Qt Worker pre hromadnú aktualizáciu balíčkov v Pip Manager okne.
# Deleguje kompletnú logiku na CoreBridge (PACKAGE_UPDATE služba).
#----------------------------------------------------

from PyQt6.QtCore import QObject, pyqtSignal
from core.core_bridge import CoreBridge


class PipWorkerAllUpdate(QObject):
    started = pyqtSignal()
    output_line = pyqtSignal(str)
    finished = pyqtSignal(bool) 
    error = pyqtSignal(str)

    def __init__(self, venv_path: str, manager_type: str = "pip", core=None):
        super().__init__()
        self.venv_path = venv_path
        self.manager_type = manager_type
        self.core = core
        self.success = False

    def run(self):
        self.started.emit()
        
        # Volanie centrálnej služby cez mostík jadra
        self.success = CoreBridge.update_all_packages(
            venv_path=self.venv_path,
            core=self.core,
            manager_type=self.manager_type,
            log_callback=self.output_line.emit
        )
        
        self.finished.emit(self.success)
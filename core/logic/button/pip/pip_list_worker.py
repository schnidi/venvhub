#----------------------------------------
# Súbor: core/logic/button/pip/pip_list_worker.py
#----------------------------------------

import traceback
from PyQt6.QtCore import QObject, pyqtSignal
from .load_list import LoadListHandler


class PipListWorker(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, venv_path, manager_type="pip"):
        super().__init__()
        self.venv_path = venv_path
        self.manager_type = manager_type

    def run(self):
        try:
            packages = LoadListHandler.get_packages(self.venv_path, self.manager_type)
            self.finished.emit(packages)
        except Exception as e:
            tb = traceback.format_exc()
            self.error.emit(f"Nastala chyba pri načítavaní balíčkov: {e}\n\n{tb}")
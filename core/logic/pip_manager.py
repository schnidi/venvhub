#----------------------------------------------------
# Súbor: core/logic/pip_manager.py
# Centrálna fasáda a spúšťač úloh pre balíčky (PyPI aj pip -e)
#----------------------------------------------------

import os
import json
import threading
from PyQt6.QtCore import QObject, pyqtSignal

from core._path import Paths
from core.core_bridge import CoreBridge
from core.core_states import PackageOperationStatus, EditableOperationStatus
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.sluzby.path_normalizer import PathNormalizer
from core.logic.sluzby.apt_logic import AptLogic


class PipSignalEmitter(QObject):
    log_message = pyqtSignal(str)
    finished = pyqtSignal()
    finished_with_status = pyqtSignal(PackageOperationStatus)


class EditableSignalEmitter(QObject):
    log_message = pyqtSignal(str)
    packages_loaded = pyqtSignal(list)
    finished_with_status = pyqtSignal(EditableOperationStatus)


class UniversalPackageWorker:
    """Univerzálny worker pre bežné PyPI balíčky."""
    def __init__(self, operation: str, core, venv_path: str, packages: list[str], manager_type: str = "pip"):
        self.operation = operation
        self.core = core
        self.venv_path = venv_path
        self.packages = packages
        self.manager_type = manager_type
        
        self.signals = PipSignalEmitter()
        self.status = PackageOperationStatus.ERROR

    def run(self):
        try:
            if self.operation == "install":
                self.status = CoreBridge.install_packages(
                    core=self.core,
                    venv_path=self.venv_path,
                    packages=self.packages,
                    log_callback=self.signals.log_message.emit
                )
            elif self.operation == "uninstall":
                self.status = CoreBridge.uninstall_packages(
                    core=self.core,
                    venv_path=self.venv_path,
                    packages=self.packages,
                    log_callback=self.signals.log_message.emit
                )
        except Exception as e:
            self.signals.log_message.emit(CoreBridge.translate("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e)))
            self.status = PackageOperationStatus.ERROR
        finally:
            self.signals.log_message.emit(CoreBridge.translate("msg_done", "--- HOTOVO ---"))
            self.signals.finished_with_status.emit(self.status)
            self.signals.finished.emit()


class UniversalEditableWorker:
    """Univerzálny worker pre editovateľné balíčky (pip -e)."""
    def __init__(self, operation: str, core, venv_path: str, target_or_pkg: str = "", manager_type: str = "pip"):
        self.operation = operation
        self.core = core
        self.venv_path = venv_path
        self.target_or_pkg = target_or_pkg
        self.manager_type = manager_type
        
        self.signals = EditableSignalEmitter()
        self.status = EditableOperationStatus.ERROR

    def run(self):
        try:
            if self.operation == "list":
                pkgs = CoreBridge.list_editable_packages(self.venv_path, self.manager_type)
                self.signals.packages_loaded.emit(pkgs)
            elif self.operation == "install":
                self.status = CoreBridge.install_editable_package(
                    core=self.core,
                    venv_path=self.venv_path,
                    target_path=self.target_or_pkg,
                    log_callback=self.signals.log_message.emit
                )
                self.signals.finished_with_status.emit(self.status)
            elif self.operation == "uninstall":
                self.status = CoreBridge.uninstall_editable_package(
                    core=self.core,
                    venv_path=self.venv_path,
                    package_name=self.target_or_pkg,
                    log_callback=self.signals.log_message.emit
                )
                self.signals.finished_with_status.emit(self.status)
        except Exception as e:
            self.signals.log_message.emit(CoreBridge.translate("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e)))
            self.status = EditableOperationStatus.ERROR
            self.signals.finished_with_status.emit(self.status)
        finally:
            self.signals.log_message.emit(CoreBridge.translate("msg_done", "--- HOTOVO ---"))


class UpdateAllWorker:
    def __init__(self, venv_path, manager_type="pip", core=None):
        self.venv_path = venv_path
        self.manager_type = manager_type
        self.core = core
        self.signals = PipSignalEmitter()
        self.success = False

    def run(self):
        self.success = CoreBridge.update_all_packages(
            venv_path=self.venv_path,
            core=self.core,
            manager_type=self.manager_type,
            log_callback=self.signals.log_message.emit
        )
        self.signals.finished.emit()


class RequirementsInstallWorker:
    def __init__(self, venv_path, project_root, manager_type="pip", core=None):
        self.venv_path = venv_path
        self.project_root = project_root
        self.manager_type = manager_type
        self.core = core
        self.signals = PipSignalEmitter()
        self.success = False

    def run(self):
        req_path = Paths.get_requirements_txt_path(self.project_root)
        if not os.path.exists(req_path):
            msg = CoreBridge.translate("err_req_not_found", "CHYBA: Súbor 'requirements.txt' nebol nájdený.")
            self.signals.log_message.emit(msg)
            self.signals.finished.emit()
            return

        try:
            self.signals.log_message.emit(CoreBridge.translate("apt_requirements_sync_start", "\n--- Inicializujem požiadavky z requirements.txt (APT) ---"))
            PathNormalizer.sanitize_requirements_file(req_path)

            self.success = AptLogic.install_sync(
                core=self.core,
                venv_path=self.venv_path,
                log_callback=self.signals.log_message.emit,
                req_file_path=req_path
            )

            if self.success:
                BirthCertificateGenerator.update_venv_certificate(self.venv_path)
                self.signals.log_message.emit(CoreBridge.translate("msg_done", "--- HOTOVO ---"))
            else:
                self.signals.log_message.emit(CoreBridge.translate("apt_requirements_sync_fail", "⚠️ Synchronizácia požiadaviek nebola úspešná."))

        except Exception as e:
            self.signals.log_message.emit(CoreBridge.translate("err_critical", "KRITICKÁ CHYBA: {0}").format(str(e)))
        finally:
            self.signals.finished.emit()


class PipManager:
    _current_thread = None
    _current_worker = None

    @staticmethod
    def _run_pip_task(worker, log_widget=None):
        if PipManager._current_thread and PipManager._current_thread.is_alive():
            msg = CoreBridge.translate("msg_busy", "!!! Už prebieha iná operácia, počkajte na jej dokončenie. !!!")
            if log_widget and hasattr(log_widget, 'append'):
                log_widget.append(msg)
            return
            
        if log_widget and hasattr(log_widget, 'append'):
            worker.signals.log_message.connect(log_widget.append)
            
        PipManager._current_worker = worker
        PipManager._current_thread = threading.Thread(target=worker.run, daemon=True)
        PipManager._current_thread.start()

    # --- ŠTANDARDNÉ BALÍČKY (PyPI) ---
    @staticmethod
    def install_package(venv_path, package_name, log_widget, manager_type="pip", core=None, on_finished=None):
        if not core:
            if log_widget: log_widget.append("CHYBA: Interná chyba - chýba objekt 'core'.")
            return
            
        worker = UniversalPackageWorker("install", core, venv_path, [package_name], manager_type)
        
        if on_finished:
            worker.signals.finished_with_status.connect(on_finished)
            
        PipManager._run_pip_task(worker, log_widget)
        
    @staticmethod
    def uninstall_package(venv_path, package_name, log_widget, manager_type="pip", core=None, on_finished=None):
        if not core:
            if log_widget: log_widget.append("CHYBA: Interná chyba - chýba objekt 'core'.")
            return
            
        worker = UniversalPackageWorker("uninstall", core, venv_path, [package_name], manager_type)
        
        if on_finished:
            worker.signals.finished_with_status.connect(on_finished)
            
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def install_requirements(venv_path, project_root, log_widget, manager_type="pip", core=None):
        worker = RequirementsInstallWorker(venv_path, project_root, manager_type, core)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def update_all_packages(venv_path, log_widget, manager_type="pip", core=None):
        worker = UpdateAllWorker(venv_path, manager_type, core=core)
        PipManager._run_pip_task(worker, log_widget)

    # --- EDITOVATEĽNÉ BALÍČKY (pip -e) ---
    @staticmethod
    def list_editable_packages(venv_path, manager_type, on_loaded, log_widget=None):
        """Asynchrónne načíta zoznam editovateľných balíčkov."""
        worker = UniversalEditableWorker("list", core=None, venv_path=venv_path, manager_type=manager_type)
        worker.signals.packages_loaded.connect(on_loaded)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def install_editable(core, venv_path, target_path, log_widget, manager_type="pip"):
        """Asynchrónne nainštaluje editovateľný balíček cez EDITABLE_OPERATIONS."""
        worker = UniversalEditableWorker("install", core, venv_path, target_or_pkg=target_path, manager_type=manager_type)
        PipManager._run_pip_task(worker, log_widget)

    @staticmethod
    def uninstall_editable(core, venv_path, package_name, log_widget, manager_type="pip"):
        """Asynchrónne odinštaluje editovateľný balíček cez EDITABLE_OPERATIONS s autoremove."""
        worker = UniversalEditableWorker("uninstall", core, venv_path, target_or_pkg=package_name, manager_type=manager_type)
        PipManager._run_pip_task(worker, log_widget)
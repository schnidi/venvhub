#----------------------------------------
# Súbor: core/logic/containers/button/autostart_actions.py
#----------------------------------------

import subprocess
import time
import os
from PyQt6.QtCore import QThread, pyqtSignal

from core.logic.language_manager import LanguageManager
from core._path import Paths
from core.logic.process_registry import process_registry
from core.logic.containers.box.json_projects import AutostartJsonManager
from core.logic.containers.logic.check_multi_venv import MultiVenvChecker
from core.logic.containers.logic.hook import HookManager
from core.core_bridge import CoreBridge


class AutostartLaunchWorker(QThread):
    """
    Vlákno pre sekvenčné spúšťanie projektov (Hlavný dirigent skupín).
    Zabezpečuje absolútne prísnu postupnosť krokov pomocou SekvenceStart.
    """
    log_signal = pyqtSignal(str)

    def __init__(self, core, group_name):
        super().__init__()
        self.core = core
        self.group_name = group_name
        self.is_cancelled = False
        self.runner = None

    def cancel(self):
        """Vyvolá sa pri stlačení tlačidla STOP."""
        self.is_cancelled = True
        if self.runner:
            self.runner.cancel()

    def run(self):
        members = self.core.multi_groups.get(self.group_name, [])
        if not members:
            self.log_signal.emit(LanguageManager.get("msg_group_empty", "Skupina '{0}' je prázdna.").format(self.group_name))
            return

        json_data = AutostartJsonManager.load_group(self.group_name)

        self.log_signal.emit(LanguageManager.get("msg_starting_group_sequence", "--- Štartujem sekvenciu skupiny: {0} ---").format(self.group_name))

        # Reset respawn počítadiel pre celú skupinu pri starte sekvencie
        try:
            from core.logic.containers.logic.respawn_multi import RespawnManager
            venv_paths = [m.get("venv_path") for m in members if m.get("venv_path")]
            RespawnManager.reset_counts(venv_paths)
        except Exception:
            pass

        from core.logic.containers.logic.sekvence_start import SekvenceStart
        self.runner = SekvenceStart(self.core, self.group_name)
        self.runner.log_signal.connect(self.log_signal.emit)

        for member in members:
            if self.is_cancelled or self.runner.is_cancelled:
                self.log_signal.emit(LanguageManager.get("msg_sequence_interrupted", "⏹️ Štartovacia sekvencia bola prerušená používateľom."))
                break

            # Spustenie konkrétneho projektu cez novú unifikovanú logiku
            uspech = self.runner.spusti_projekt(member, json_data)
            if not uspech:
                break

        if not self.is_cancelled and not self.runner.is_cancelled:
            self.log_signal.emit(LanguageManager.get("msg_group_sequence_done", "--- Sekvencia štartu skupiny dokončená ---"))


class AutostartActionHandler:
    @staticmethod
    def start_group(core, group_name, log_callback=None):
        # 1. KONTROLA PRÍSTUPU PRE VŠETKY VENVY V SKUPINE
        members = core.multi_groups.get(group_name, [])
        for m in members:
            venv_path = m.get("venv_path")
            if venv_path and not CoreBridge.verify_venv_access(venv_path):
                v_name = os.path.basename(venv_path)
                if log_callback:
                    default_msg = f"🛑 FATAL: Štart skupiny zablokovaný! Venv '{v_name}' patrí inému PC."
                    raw_msg = CoreBridge.translate("group_start_blocked_log", default_msg)
                    try:
                        formatted_msg = raw_msg.format(venv_name=v_name)
                    except Exception:
                        formatted_msg = raw_msg
                    log_callback(formatted_msg)
                return  # Zablokuje štart celej skupiny

        # 2. SPUSTENIE ŠTARTOVACIEHO VLÁKNA
        thread = AutostartLaunchWorker(core, group_name)
        if log_callback:
            thread.log_signal.connect(log_callback)
        
        thread.finished.connect(thread.deleteLater)
        thread.start()
        
        if not hasattr(core, '_active_autostart_threads'):
            core._active_autostart_threads = []
        core._active_autostart_threads.append(thread)
        
        thread.finished.connect(lambda: core._active_autostart_threads.remove(thread) if thread in core._active_autostart_threads else None)

    @staticmethod
    def stop_group(core, group_name):
        # 1. OKAMŽITE POVIEME RIADIACEMU VLÁKNU, ABY ZASTAVILO A UKONČÍME HO (KILL)
        if hasattr(core, '_active_autostart_threads'):
            for thread in list(core._active_autostart_threads):
                if thread.group_name == group_name:
                    thread.cancel()
                    try:
                        thread.terminate()
                        thread.wait()
                    except Exception:
                        pass

        # 1.5. ZABIJEME VŠETKY AKTÍVNE REŠTARTOVACIE VLÁKNA (RESPAWN WORKERS) PRE TÚTO SKUPINU
        try:
            from core.logic.containers.logic.respawn_multi import RespawnManager
            for worker in list(RespawnManager._active_workers):
                if worker.group_name == group_name:
                    try:
                        worker.terminate()
                        worker.wait()
                    except Exception:
                        pass
                    if worker in RespawnManager._active_workers:
                        RespawnManager._active_workers.remove(worker)
            
            # Vynulujeme počítadlá pádov, aby mali programy pri ďalšom štarte čistý štart
            members = core.multi_groups.get(group_name, [])
            venv_paths = [m.get("venv_path") for m in members if m.get("venv_path")]
            RespawnManager.reset_counts(venv_paths)
        except Exception:
            pass

        # 2. ZABIJEME VŠETKY UŽ BEŽIACE PROCESY
        from core.logic.button.manager.actions import ActionHandler
        ActionHandler.stop_multiple(core, group_name)

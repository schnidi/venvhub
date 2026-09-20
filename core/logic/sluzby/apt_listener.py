#----------------------------------------
# Súbor: core/logic/sluzby/apt_listener.py
#----------------------------------------

import os
import json
import subprocess
from core._path import Paths
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.language_manager import LanguageManager
from core.logic.birth_certificate import BirthCertificateGenerator

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

class AptListener:
    """
    Neviditeľný most (Interceptor), ktorý počúva na pozadí všetky akcie.
    Automaticky zapisuje manuálne inštalácie a odinštalácie do APT logiky.
    """

    @staticmethod
    def start_listening(core):
        AptListener._patch_pip_manager(core)
        AptListener._patch_pip_package_widget(core)
        AptListener._patch_pip_worker_all_update(core)
        AptListener._patch_pipe_install(core)
        AptListener._patch_pipe_uninstall(core)
        AptListener._patch_local_linker(core)

    @staticmethod
    def _get_worker_cmd(worker):
        """Získa príkaz z workera bez ohľadu na to, či je to full_command alebo cmd."""
        if hasattr(worker, 'full_command') and worker.full_command:
            return worker.full_command
        if hasattr(worker, 'cmd') and worker.cmd:
            return worker.cmd
        return None

    @staticmethod
    def _extract_packages_from_install_cmd(cmd_list):
        pkgs = []
        cmd_lower = [x.lower() for x in cmd_list]
        if "install" in cmd_lower and "-r" not in cmd_lower:
            idx = cmd_lower.index("install")
            for arg in cmd_list[idx+1:]:
                if not arg.startswith("-"):
                    clean_pkg = RequirementsParser._extract_package_name(arg)
                    if clean_pkg: 
                        pkgs.append(clean_pkg)
        return pkgs

    @staticmethod
    def _extract_packages_from_uninstall_cmd(cmd_list):
        pkgs = []
        cmd_lower = [x.lower() for x in cmd_list]
        if "uninstall" in cmd_lower:
            idx = cmd_lower.index("uninstall")
            for arg in cmd_list[idx+1:]:
                if not arg.startswith("-"):
                    clean_pkg = RequirementsParser._extract_package_name(arg)
                    if clean_pkg:
                        pkgs.append(clean_pkg)
        return pkgs

    @staticmethod
    def _patch_pip_manager(core):
        from core.logic.pip_manager import PipManager
        orig_run_pip_task = PipManager._run_pip_task

        @staticmethod
        def patched_run_pip_task(worker, log_widget):
            cmd_list = AptListener._get_worker_cmd(worker)
            released_reqs = []

            if cmd_list:
                cmd_lower = [x.lower() for x in cmd_list]
                is_uninstall = "uninstall" in cmd_lower

                if is_uninstall:
                    pkgs_to_uninstall = AptListener._extract_packages_from_uninstall_cmd(cmd_list)
                    for pkg in pkgs_to_uninstall:
                        deps = AptLogic.is_package_required_by_others(worker.venv_path, core, pkg)
                        if deps:
                            msg = LanguageManager.get(
                                "apt_err_cannot_uninstall",
                                "❌ Nemožno odinštalovať '{0}', pretože ho vyžadujú: {1}"
                            ).format(pkg, ", ".join(deps))
                            log_widget.append(msg)
                            worker.success = False
                            if hasattr(worker, 'finished'):
                                worker.finished.emit(1)
                            elif hasattr(worker, 'signals') and hasattr(worker.signals, 'finished'):
                                worker.signals.finished.emit()
                            return

                is_upgrade = "install" in cmd_lower and ("--upgrade" in cmd_list or "-U" in cmd_list)
                is_req_install = "install" in cmd_lower and "-r" in cmd_lower
                
                uninstalled_pkgs = AptListener._extract_packages_from_uninstall_cmd(cmd_list) if is_uninstall else []
                installed_pkgs = AptListener._extract_packages_from_install_cmd(cmd_list) if "install" in cmd_lower else []
                upgraded_pkgs = installed_pkgs if is_upgrade else []

                for pkg in uninstalled_pkgs:
                    released_reqs.extend(AptLogic.get_requires_for_package(worker.venv_path, pkg, core.package_manager))
                for pkg in upgraded_pkgs:
                    released_reqs.extend(AptLogic.get_requires_for_package(worker.venv_path, pkg, core.package_manager))
            else:
                is_uninstall = False
                is_upgrade = True
                is_req_install = False
                uninstalled_pkgs = []
                installed_pkgs = []
                upgraded_pkgs = []

                graph = AptLogic.get_dependency_graph(worker.venv_path, core)
                if graph:
                    for reqs in graph.values():
                        released_reqs.extend(reqs)

            should_autoremove = is_uninstall or is_upgrade

            def apt_callback(*args):
                # Zistíme reálny stav úspechu z workera alebo z odovzdaného argumentu
                if args and isinstance(args[0], (int, bool)):
                    success = (args[0] == 0 or args[0] is True)
                else:
                    success = getattr(worker, 'success', False)
                
                if not success:
                    msg = LanguageManager.get(
                        "apt_op_failed_state_unchanged",
                        "⚠️ [APT] Operácia zlyhala — APT stav ostáva nezmenený."
                    )
                    log_widget.append(msg)
                else:
                    for pkg in uninstalled_pkgs:
                        AptLogic.unmark_explicit(worker.venv_path, pkg)
                    if not is_upgrade and not is_req_install:
                        for pkg in installed_pkgs:
                            # Ak je balíček prinesenou závislosťou iného balíčka, nezapisujeme ho do explicit
                            if not AptLogic.is_package_required_by_others(worker.venv_path, core, pkg):
                                AptLogic.mark_as_explicit(worker.venv_path, pkg)
                    if is_req_install:
                        AptLogic.install_sync(core, worker.venv_path, log_widget.append)
                    if should_autoremove:
                        AptLogic.autoremove(core, worker.venv_path, log_widget.append, released_packages=released_reqs)

            worker._apt_callback = apt_callback

            if hasattr(worker, 'finished'):
                worker.finished.connect(worker._apt_callback)
            elif hasattr(worker, 'signals') and hasattr(worker.signals, 'finished'):
                worker.signals.finished.connect(worker._apt_callback)

            orig_run_pip_task(worker, log_widget)

        PipManager._run_pip_task = patched_run_pip_task

    @staticmethod
    def _patch_pip_package_widget(core):
        from windows.pip_package_widget import PipPackageWidget
        orig_run_pip_command = PipPackageWidget.run_pip_command

        def patched_run_pip_command(self, full_command, start_message):
            cmd_lower = [x.lower() for x in full_command]
            is_uninstall = "uninstall" in cmd_lower
            is_req_install = "install" in cmd_lower and "-r" in cmd_lower

            if is_uninstall:
                pkgs_to_uninstall = AptListener._extract_packages_from_uninstall_cmd(full_command)
                for pkg in pkgs_to_uninstall:
                    deps = AptLogic.is_package_required_by_others(self.venv_path, core, pkg)
                    if deps:
                        msg = LanguageManager.get(
                            "apt_err_cannot_uninstall",
                            "❌ Nemožno odinštalovať '{0}', pretože ho vyžadujú: {1}"
                        ).format(pkg, ", ".join(deps))
                        self.log(msg)
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "Chyba", msg)
                        return

            is_upgrade = "install" in cmd_lower and ("--upgrade" in full_command or "-U" in full_command)
            should_autoremove = is_uninstall or is_upgrade

            uninstalled_pkgs = AptListener._extract_packages_from_uninstall_cmd(full_command) if is_uninstall else []
            installed_pkgs = AptListener._extract_packages_from_install_cmd(full_command) if "install" in cmd_lower else []
            upgraded_pkgs = installed_pkgs if is_upgrade else []

            released_reqs = []
            for pkg in uninstalled_pkgs:
                released_reqs.extend(AptLogic.get_requires_for_package(self.venv_path, pkg, core.package_manager))
            for pkg in upgraded_pkgs:
                released_reqs.extend(AptLogic.get_requires_for_package(self.venv_path, pkg, core.package_manager))

            orig_run_pip_command(self, full_command, start_message)

            def on_finished(exit_code):
                if exit_code != 0:
                    msg = LanguageManager.get(
                        "apt_pip_op_failed_code",
                        "⚠️ [APT] Pip operácia zlyhala (kód={0}) — APT stav ostáva nezmenený."
                    ).format(exit_code)
                    self.log(msg)
                    return
                for pkg in uninstalled_pkgs:
                    AptLogic.unmark_explicit(self.venv_path, pkg)
                if not is_upgrade and not is_req_install:
                    for pkg in installed_pkgs:
                        # Ak je balíček prinesenou závislosťou iného balíčka, nezapisujeme ho do explicit
                        if not AptLogic.is_package_required_by_others(self.venv_path, core, pkg):
                            AptLogic.mark_as_explicit(self.venv_path, pkg)
                if is_req_install:
                    AptLogic.install_sync(core, self.venv_path, self.log)
                if should_autoremove:
                    AptLogic.autoremove(core, self.venv_path, self.log, released_packages=released_reqs)

            if hasattr(self, 'worker') and self.worker:
                self.worker._apt_callback = on_finished
                self.worker.finished.connect(self.worker._apt_callback)

        PipPackageWidget.run_pip_command = patched_run_pip_command

    @staticmethod
    def _patch_pip_worker_all_update(core):
        from core.logic.button.pip.pip_worker_allupdate import PipWorkerAllUpdate
        orig_run = PipWorkerAllUpdate.run

        def patched_run(self):
            graph = AptLogic.get_dependency_graph(self.venv_path, core)
            released_reqs = []
            if graph:
                for reqs in graph.values():
                    released_reqs.extend(reqs)

            def on_finished_update(success):
                if success:
                    AptLogic.autoremove(core, self.venv_path, self.output_line.emit, released_packages=released_reqs)

            self._apt_callback = on_finished_update
            self.finished.connect(self._apt_callback)
            orig_run(self)

        PipWorkerAllUpdate.run = patched_run

    @staticmethod
    def _patch_pipe_install(core):
        from core.logic.pip_e import PipEInstallWorker
        orig_init = PipEInstallWorker.__init__

        def patched_init(self, venv_path, target_path):
            orig_init(self, venv_path, target_path)

            def on_finished_install(success):
                if success:
                    # >>> ZMENA: Označenie nainštalovaného pip -e balíčka ako explicitného
                    pkg_name = RequirementsParser._get_package_name_from_dir(self.target_path)
                    if pkg_name:
                        AptLogic.mark_as_explicit(self.venv_path, pkg_name)
                    # <<< KONIEC ZMENY
                    AptLogic.install_sync(core, self.venv_path, self.log_msg.emit)

            self._apt_callback = on_finished_install
            self.finished.connect(self._apt_callback)

        PipEInstallWorker.__init__ = patched_init

    @staticmethod
    def _patch_pipe_uninstall(core):
        from core.logic.pip_e import PipEUninstallWorker

        # >>> ZMENA: Kompletná synchrónna obsluha odinštalácie a autoremove priamo v tele workera
        def patched_run(self):
            try:
                python_exe = Paths.get_venv_python_exe_path(self.venv_path)
                if not os.path.exists(python_exe):
                    self.error.emit(LanguageManager.get("pipe_err_no_python", "❌ Python executable nebol nájdený: {0}").format(python_exe))
                    self.finished.emit(False)
                    return

                # 1. Kontrola reverzných závislostí
                deps = AptLogic.is_package_required_by_others(self.venv_path, core, self.package_name)
                if deps:
                    msg = LanguageManager.get(
                        "apt_err_cannot_uninstall",
                        "❌ Nemožno odinštalovať '{0}', pretože ho vyžadujú: {1}"
                    ).format(self.package_name, ", ".join(deps))
                    self.log_msg.emit(msg)
                    self.finished.emit(False)
                    return

                # 2. Zistenie uvoľňovaných závislostí EŠTE PRED zmazaním balíčka
                released_reqs = AptLogic.get_requires_for_package(self.venv_path, self.package_name, core.package_manager)

                cmd = [python_exe, "-m", "pip", "uninstall", "-y", self.package_name]
                self.log_msg.emit(LanguageManager.get("pipe_log_uninstalling", "\n🗑️ Odinštalujem balíček '{0}'...").format(self.package_name))

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW
                )

                for line in iter(process.stdout.readline, ''):
                    clean_line = line.strip()
                    if clean_line:
                        self.log_msg.emit(f"  {clean_line}")

                process.wait()

                success = (process.returncode == 0)
                if success:
                    self.log_msg.emit(LanguageManager.get("pipe_log_uninstall_success", "✅ Balíček '{0}' bol úspešne odstránený.").format(self.package_name))
                    BirthCertificateGenerator.update_venv_certificate(self.venv_path)

                    # 3. APT autoremove sa spustí priamo tu v tom istom vlákne pred emitovaním finished!
                    AptLogic.unmark_explicit(self.venv_path, self.package_name)
                    AptLogic.autoremove(core, self.venv_path, self.log_msg.emit, released_packages=released_reqs)
                else:
                    self.error.emit(LanguageManager.get("pipe_err_uninstall_failed", "❌ Odinštalácia zlyhala s kódom {0}.").format(process.returncode))

                # 4. Až po kompletnom vyčistení odovzdáme riadenie oknu
                self.finished.emit(success)

            except Exception as e:
                self.error.emit(LanguageManager.get("pipe_err_critical", "❌ Kritická chyba: {0}").format(e))
                self.finished.emit(False)

        PipEUninstallWorker.run = patched_run
        # <<< KONIEC ZMENY

    @staticmethod
    def _patch_local_linker(core):
        from core.logic.button.manager.local_packages_linker import LocalPackagesLinker
        orig_apply_changes = LocalPackagesLinker.apply_changes

        def patched_apply_changes(self, selected_items_data):
            effective_core = getattr(self, "core", core)
            old_linked = self.parent._get_linked_packages()
            new_linked = set(item['name'] for item in selected_items_data)
            
            released_reqs = []
            for old_pkg in old_linked:
                if old_pkg not in new_linked:
                    pkg_path = os.path.join(effective_core.local_packages_root, old_pkg)
                    meta_path = os.path.join(pkg_path, "local_meta.json")
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                                released_reqs.extend(meta.get("requires_pip", []))
                        except Exception: pass

            result = orig_apply_changes(self, selected_items_data)
            
            if result and released_reqs:
                AptLogic.autoremove(effective_core, self.venv_path, self.log_callback, released_packages=released_reqs)
                
            return result

        LocalPackagesLinker.apply_changes = patched_apply_changes
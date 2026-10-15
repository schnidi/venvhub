#----------------------------------------
# Súbor: core/logic/sluzby/apt_listener.py
#----------------------------------------

import os
import json
import re
import subprocess
from core._path import Paths
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.language_manager import LanguageManager

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

class AptListener:
    """
    Systémový Interceptor (poslucháč na pozadí).

    Zachytáva manuálne príkazy používateľa (napr. 'pip install requests[socks]'):
      1. Pred inštaláciou skontroluje, či balíček už nie je 1:1 prítomný z requirements.txt.
         Ak áno, zastaví zbytočnú inštaláciu a zabráni duplicitnému zápisu do JSON.
      2. Pred odinštalovaním vykonáva ŽIVÚ KONTROLU cez AptLogic.verify_uninstall_safety.
      3. Po úspešnom odinštalovaní vyhladí balíček zo stavu cez AptLogic.scrub_package_completely
         a spustí čisté autoremove.
    """

    @staticmethod
    def _tr(key: str, default: str, *args, **kwargs) -> str:
        """
        Pomocná metóda na bezpečné načítanie preložených textov cez LanguageManager s formátovaním parametrov.
        """
        return AptLogic._tr(key, default, *args, **kwargs)

    @staticmethod
    def start_listening(core):
        """Zaregistruje všetky odchytávacie hooky pre celú aplikáciu."""
        AptListener._patch_pip_manager(core)
        AptListener._patch_pip_package_widget(core)
        AptListener._patch_pip_worker_all_update(core)
        AptListener._patch_pipe_install(core)
        AptListener._patch_pipe_uninstall(core)
        AptListener._patch_local_linker(core)

    @staticmethod
    def _get_worker_cmd(worker) -> list[str] | None:
        """Unifikovane vytiahne zoznam argumentov príkazu z ľubovoľného workera."""
        if hasattr(worker, 'full_command') and worker.full_command:
            return worker.full_command
        if hasattr(worker, 'cmd') and worker.cmd:
            return worker.cmd
        return None

    # =========================================================================
    # --- JEDNOTNÁ EXTRAKCIA POMOCOU RequirementsParser ---
    # =========================================================================

    @staticmethod
    def _extract_package_and_extras_from_arg(arg: str) -> tuple[str | None, list[str]]:
        """
        Zverí extrakciu mena balíčka nášmu RequirementsParseru (podporuje URL, tarbally, verzie).
        Iba vytiahne voliteľný zoznam [extras], ak sa v argumente nachádza.
        """
        # 1. Čisté meno balíčka vyrieši centrálny parser
        clean_pkg = RequirementsParser._extract_package_name(arg)
        if not clean_pkg:
            return None, []

        norm_name = AptLogic._normalize(clean_pkg)

        # 2. Ak argument obsahoval aj [extra1,extra2], vytiahneme ich
        extras = []
        extras_match = re.search(r"\[([^\]]+)\]", arg)
        if extras_match:
            raw_extras = extras_match.group(1)
            extras = [AptLogic._normalize(e) for e in raw_extras.split(",") if e.strip()]

        return norm_name, extras

    @staticmethod
    def _extract_packages_from_install_cmd(cmd_list: list[str]) -> list[tuple[str, list[str]]]:
        """
        Prejde argumenty príkazu install, preskočí prepínače CLI inštalátora
        a každý cieľ pošle priamo nášmu parseru.
        """
        items = []
        cmd_lower = [str(x).lower() for x in cmd_list]
        if "install" in cmd_lower and "-r" not in cmd_lower:
            idx = cmd_lower.index("install")
            skip_next = False
            for arg in cmd_list[idx + 1:]:
                arg_str = str(arg).strip()

                if skip_next:
                    skip_next = False
                    continue

                # Preskočíme prepínače, ktoré očakávajú hodnotu v ďalšom argumente
                if arg_str.startswith("-"):
                    if arg_str in ("--python", "-p", "--target", "-t", "--prefix", "-c", "--constraint", "-r", "--requirement"):
                        skip_next = True
                    continue

                # Všetko ostatné (mená, verzie, tar.gz, URL) spracuje priamo parser
                pkg_name, extras = AptListener._extract_package_and_extras_from_arg(arg_str)
                if pkg_name and pkg_name not in AptLogic.CORE_TOOLS:
                    items.append((pkg_name, extras))
        return items

    @staticmethod
    def _extract_packages_from_uninstall_cmd(cmd_list: list[str]) -> list[str]:
        """Prejde argumenty príkazu uninstall a mená vytiahne priamo cez parser."""
        pkgs = []
        cmd_lower = [str(x).lower() for x in cmd_list]
        if "uninstall" in cmd_lower:
            idx = cmd_lower.index("uninstall")
            skip_next = False
            for arg in cmd_list[idx + 1:]:
                arg_str = str(arg).strip()

                if skip_next:
                    skip_next = False
                    continue

                if arg_str.startswith("-"):
                    if arg_str in ("--python", "-p", "--target", "-t", "--prefix"):
                        skip_next = True
                    continue

                clean_pkg = RequirementsParser._extract_package_name(arg_str)
                if clean_pkg:
                    norm_name = AptLogic._normalize(clean_pkg)
                    if norm_name not in AptLogic.CORE_TOOLS:
                        pkgs.append(norm_name)
        return pkgs

    # =========================================================================
    # --- PATCH PRE PIP MANAGER ---
    # =========================================================================

    @staticmethod
    def _patch_pip_manager(core):
        from core.logic.pip_manager import PipManager
        orig_run_pip_task = PipManager._run_pip_task

        @staticmethod
        def patched_run_pip_task(worker, log_widget):
            cmd_list = AptListener._get_worker_cmd(worker)
            released_reqs = []

            if cmd_list:
                cmd_lower = [str(x).lower() for x in cmd_list]
                is_uninstall = "uninstall" in cmd_lower
                is_upgrade = "install" in cmd_lower and ("--upgrade" in cmd_list or "-U" in cmd_list)
                is_req_install = "install" in cmd_lower and "-r" in cmd_lower
                is_version_change = any("==" in str(arg) or "<" in str(arg) or ">" in str(arg) for arg in cmd_list)

                # ŽIVÁ APT KONTROLA pred povolením odinštalácie
                if is_uninstall:
                    pkgs_to_uninstall = AptListener._extract_packages_from_uninstall_cmd(cmd_list)
                    for pkg in pkgs_to_uninstall:
                        is_safe, err_msg = AptLogic.verify_uninstall_safety(worker.venv_path, core, pkg)
                        if not is_safe:
                            log_widget.append(err_msg)
                            worker.success = False
                            if hasattr(worker, 'finished'):
                                worker.finished.emit(1)
                            elif hasattr(worker, 'signals') and hasattr(worker.signals, 'finished'):
                                worker.signals.finished.emit()
                            return

                # ŽIVÁ APT KONTROLA PRED INŠTALÁCIOU (STAV 1:1)
                if "install" in cmd_lower and not is_req_install and not is_upgrade and not is_version_change:
                    installed_items_check = AptListener._extract_packages_from_install_cmd(cmd_list)
                    if installed_items_check:
                        from PyQt6.QtWidgets import QApplication
                        log_widget.append(AptListener._tr("apt_verifying_reqs", "\n🔍 [APT] Overujem požiadavku voči requirements.txt a prostrediu..."))
                        QApplication.processEvents()

                        can_skip, skip_msg = AptLogic.check_install_necessity(
                            worker.venv_path, core, installed_items_check, log_callback=log_widget.append
                        )
                        if can_skip:
                            log_widget.append(f"\n{skip_msg}")
                            log_widget.append(AptListener._tr("apt_done_separator", "--- HOTOVO ---"))
                            worker.success = True
                            if hasattr(worker, 'finished'):
                                worker.finished.emit(0)
                            elif hasattr(worker, 'signals') and hasattr(worker.signals, 'finished'):
                                worker.signals.finished.emit()
                            return

                uninstalled_pkgs = AptListener._extract_packages_from_uninstall_cmd(cmd_list) if is_uninstall else []
                installed_items = AptListener._extract_packages_from_install_cmd(cmd_list) if "install" in cmd_lower else []

                for pkg in uninstalled_pkgs:
                    released_reqs.extend(AptLogic.get_requires_for_package(worker.venv_path, pkg, core.package_manager))
            else:
                is_uninstall = False
                is_upgrade = False
                is_req_install = False
                is_version_change = False
                uninstalled_pkgs = []
                installed_items = []

            def apt_callback(*args):
                if args and isinstance(args[0], (int, bool)):
                    success = (args[0] == 0 or args[0] is True)
                else:
                    success = getattr(worker, 'success', False)

                if not success:
                    log_widget.append(AptListener._tr("apt_op_failed_state_unchanged", "⚠️ [APT] Operácia zlyhala — stav venv ostáva nezmenený."))
                else:
                    # 1. Pri odinštalovaní: vyhladenie zo stavu + uvoľnenie viazaných extras
                    for pkg in uninstalled_pkgs:
                        kids = AptLogic.scrub_package_completely(worker.venv_path, pkg)
                        released_reqs.extend(kids)

                    # 2. Pri inštalácii: registrácia explicit a extras väzieb
                    if not is_upgrade and not is_req_install:
                        for pkg, extras in installed_items:
                            if is_version_change and AptLogic.is_subpackage_or_managed(worker.venv_path, core, pkg):
                                log_widget.append(AptListener._tr("apt_guard_subpackage_updated", "ℹ️ [APT: STAV 3 - GUARD] Verzia podbalíčka '{pkg}' upravená. Zostáva ako automatická závislosť (nie explicit).", pkg=pkg))
                            else:
                                AptLogic.mark_as_explicit(worker.venv_path, pkg)

                            if extras:
                                AptLogic.resolve_and_bind_extras(worker.venv_path, pkg, extras, context="explicit")

                    # 3. Synchronizácia požiadaviek
                    if is_req_install:
                        actual_req_path = None
                        if cmd_list:
                            for idx, arg in enumerate(cmd_list):
                                if arg in ("-r", "--requirement") and idx + 1 < len(cmd_list):
                                    actual_req_path = cmd_list[idx + 1].strip().strip("'\"")
                                    break
                        AptLogic.install_sync(core, worker.venv_path, log_widget.append, req_file_path=actual_req_path)

                    # 4. Autoremove pri uninstalle
                    if is_uninstall:
                        AptLogic.autoremove(core, worker.venv_path, log_widget.append, released_packages=released_reqs)

            worker._apt_callback = apt_callback

            if hasattr(worker, 'finished'):
                worker.finished.connect(worker._apt_callback)
            elif hasattr(worker, 'signals') and hasattr(worker.signals, 'finished'):
                worker.signals.finished.connect(worker._apt_callback)

            orig_run_pip_task(worker, log_widget)

        PipManager._run_pip_task = patched_run_pip_task

    # =========================================================================
    # --- PATCH PRE PIP PACKAGE WIDGET (PRAVÝ PANEL) ---
    # =========================================================================

    @staticmethod
    def _patch_pip_package_widget(core):
        from windows.pip_package_widget import PipPackageWidget
        orig_run_pip_command = PipPackageWidget.run_pip_command

        def patched_run_pip_command(self, full_command, start_message):
            cmd_lower = [str(x).lower() for x in full_command]
            is_uninstall = "uninstall" in cmd_lower
            is_req_install = "install" in cmd_lower and "-r" in cmd_lower
            is_upgrade = "install" in cmd_lower and ("--upgrade" in full_command or "-U" in full_command)
            is_version_change = any("==" in str(arg) or "<" in str(arg) or ">" in str(arg) for arg in full_command)

            # ŽIVÁ APT KONTROLA pred odinštaláciou v GUI
            if is_uninstall:
                pkgs_to_uninstall = AptListener._extract_packages_from_uninstall_cmd(full_command)
                for pkg in pkgs_to_uninstall:
                    is_safe, err_msg = AptLogic.verify_uninstall_safety(self.venv_path, core, pkg)
                    if not is_safe:
                        self.log(err_msg)
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, LanguageManager.get("title_warning", "Upozornenie"), err_msg)
                        return

            # ŽIVÁ APT KONTROLA PRED INŠTALÁCIOU (STAV 1:1)
            if "install" in cmd_lower and not is_req_install and not is_upgrade and not is_version_change:
                installed_items_check = AptListener._extract_packages_from_install_cmd(full_command)
                if installed_items_check:
                    from PyQt6.QtWidgets import QApplication
                    self.log(AptListener._tr("apt_verifying_reqs", "\n🔍 [APT] Overujem požiadavku voči requirements.txt a prostrediu..."))
                    QApplication.processEvents()

                    can_skip, skip_msg = AptLogic.check_install_necessity(
                        self.venv_path, core, installed_items_check, log_callback=self.log
                    )
                    if can_skip:
                        self.log(f"\n{skip_msg}")
                        self.log(AptListener._tr("apt_done_separator", "--- HOTOVO ---"))
                        return

            uninstalled_pkgs = AptListener._extract_packages_from_uninstall_cmd(full_command) if is_uninstall else []
            installed_items = AptListener._extract_packages_from_install_cmd(full_command) if "install" in cmd_lower else []

            released_reqs = []
            for pkg in uninstalled_pkgs:
                released_reqs.extend(AptLogic.get_requires_for_package(self.venv_path, pkg, core.package_manager))

            orig_run_pip_command(self, full_command, start_message)

            def on_finished(exit_code):
                if exit_code != 0:
                    self.log(AptListener._tr("apt_pip_failed_code", "⚠️ [APT] Pip operácia zlyhala (kód={code}).", code=exit_code))
                    return

                for pkg in uninstalled_pkgs:
                    kids = AptLogic.scrub_package_completely(self.venv_path, pkg)
                    released_reqs.extend(kids)

                if not is_upgrade and not is_req_install:
                    for pkg, extras in installed_items:
                        if is_version_change and AptLogic.is_subpackage_or_managed(self.venv_path, core, pkg):
                            self.log(AptListener._tr("apt_guard_subpackage_updated", "ℹ️ [APT: STAV 3 - GUARD] Verzia podbalíčka '{pkg}' upravená. Zostáva ako automatická závislosť (nie explicit).", pkg=pkg))
                        else:
                            AptLogic.mark_as_explicit(self.venv_path, pkg)

                        if extras:
                            AptLogic.resolve_and_bind_extras(self.venv_path, pkg, extras, context="explicit")

                if is_req_install:
                    AptLogic.install_sync(core, self.venv_path, self.log)
                if is_uninstall:
                    AptLogic.autoremove(core, self.venv_path, self.log, released_packages=released_reqs)

            if hasattr(self, 'worker') and self.worker:
                self.worker._apt_callback = on_finished
                self.worker.finished.connect(self.worker._apt_callback)

        PipPackageWidget.run_pip_command = patched_run_pip_command

    @staticmethod
    def _patch_pip_worker_all_update(core):
        pass

    # =========================================================================
    # --- PATCH PRE PIP -e (EDITOVATEĽNÉ BALÍČKY) ---
    # =========================================================================

    @staticmethod
    def _patch_pipe_install(core):
        from core.logic import pip_e

        def after_install(worker):
            pkg_name = RequirementsParser._get_package_name_from_dir(worker.target_path)
            if pkg_name:
                AptLogic.mark_as_explicit(worker.venv_path, pkg_name)
            AptLogic.install_sync(core, worker.venv_path, worker.log_msg.emit)

        pip_e.HOOKS["install_success"] = after_install

    @staticmethod
    def _patch_pipe_uninstall(core):
        from core.logic import pip_e

        def before_uninstall(worker):
            is_safe, err_msg = AptLogic.verify_uninstall_safety(worker.venv_path, core, worker.package_name)
            if not is_safe:
                return err_msg, None

            released_reqs = AptLogic.get_requires_for_package(worker.venv_path, worker.package_name, core.package_manager)
            return None, released_reqs

        def after_uninstall(worker, released_reqs):
            kids = AptLogic.scrub_package_completely(worker.venv_path, worker.package_name)
            all_released = list(released_reqs or []) + list(kids)
            AptLogic.autoremove(core, worker.venv_path, worker.log_msg.emit, released_packages=all_released)

        pip_e.HOOKS["uninstall_pre"] = before_uninstall
        pip_e.HOOKS["uninstall_success"] = after_uninstall

    # =========================================================================
    # --- PATCH PRE LOKÁLNY LINKER ---
    # =========================================================================

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
                        except Exception:
                            pass

            result = orig_apply_changes(self, selected_items_data)
            if result and released_reqs:
                AptLogic.autoremove(effective_core, self.venv_path, self.log_callback, released_packages=released_reqs)

            return result

        LocalPackagesLinker.apply_changes = patched_apply_changes
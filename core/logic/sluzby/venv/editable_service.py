#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/editable_service.py
# Dedikovaná LAZY služba pre správu editovateľných balíčkov (pip -e)
# VŠETKY PRÍKAZY IDÚ VÝHRADNE CEZ PackageManagerFactory DISPEČER
#----------------------------------------------------

import os
import re
import json
import subprocess
from typing import Callable, Optional

from core._path import Paths
from core.core_states import EditableOperationStatus
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.apt_state import AptState, AptStatusEvent
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.birth_certificate import BirthCertificateGenerator

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


class EditableOperationsService:
    """
    Špecializovaná služba pre prácu s editovateľnými balíčkami (pip install -e / uv pip install -e).
    Všetky systémové príkazy skladá centrálny PackageManagerFactory dispečer.
    Plne integrované na LanguageBridge preklady a pack_operation_state stavový automat.
    """

    @classmethod
    def _analyze_declared_dependencies(cls, venv_path: str, internal_deps: list[str]) -> list[dict]:
        """
        Preskúma každú deklarovanú závislosť voči aktuálnemu stavu na disku.
        Zisťuje verziu, nezhody aj naviazané [extras] balíčky (napr. pysocks pre requests[socks]).
        """
        installed_versions = AptLogic._collect_installed_versions(venv_path)
        analyzed = []

        for dep_spec in internal_deps:
            clean_name = RequirementsParser._extract_package_name(dep_spec)
            if not clean_name:
                continue

            norm_dep = AptLogic._normalize(clean_name)
            inst_ver = installed_versions.get(norm_dep)

            if not inst_ver:
                action = "MISSING"
                status_text = LanguageBridge.translate("edit_dep_missing", "nie je vo venv -> 🔻 CHÝBA (bude sa inštalovať)")
            elif not RequirementsParser.is_satisfied(dep_spec, inst_ver):
                action = "MISMATCH"
                status_text = LanguageBridge.translate(
                    "edit_dep_mismatch",
                    "na disku {0} (požadované: {1}) -> ⚡ ZMENA VERZIE"
                ).format(inst_ver, dep_spec)
            else:
                action = "OK"
                status_text = LanguageBridge.translate(
                    "edit_dep_ok",
                    "na disku {0} -> ✅ VYHOVUJE"
                ).format(inst_ver)

            # Analýza viazaných extras (napr. [socks] -> pysocks)
            req_exts = RequirementsParser.extract_extras(dep_spec)
            extras_detail = []
            if req_exts:
                family = AptLogic.resolve_extras_family(venv_path, norm_dep, req_exts)
                for extra_kid in family:
                    kid_ver = installed_versions.get(extra_kid)
                    k_status = f"✅ na disku {kid_ver}" if kid_ver else "🔻 CHÝBA"
                    extras_detail.append(f"{extra_kid} ({k_status})")

            analyzed.append({
                "package": norm_dep,
                "spec": dep_spec,
                "installed_version": inst_ver,
                "action": action,
                "status_text": status_text,
                "extras": req_exts,
                "extras_detail": extras_detail
            })

        return analyzed

    @classmethod
    def _create_rich_status_handler(cls, log_callback: Callable[[str], None]) -> Callable[[AptStatusEvent], None]:
        """
        Vytvorí handler pre AptStatusEvent, ktorý formátuje štruktúrované dáta
        z AptLogic a EditableService do podrobného stromového výstupu.
        """
        def _handler(event: AptStatusEvent):
            # A) DETAIL SIRÔT (Autoremove)
            if event.state == AptState.REMOVING_ORPHANS:
                orphans = event.get("orphans", [])
                mgr = event.get("manager", "PIP")

                t_title = LanguageBridge.translate("pack_tree_autoremove_detail", "🧹 [DETAIL AUTOREMOVE ({0})]").format(mgr)
                t_count = LanguageBridge.translate("pack_tree_orphans_count", "Počet nájdených sirôt na zmazanie: {0}").format(len(orphans))
                t_list = LanguageBridge.translate("pack_tree_orphans_list", "Zoznam: {0}").format(", ".join(orphans))

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_count}")
                log_callback(f"   └─ {t_list}")

            # B) BEZPEČNOSTNÁ STOPKA
            elif event.state == AptState.FAILED and event.get("can_uninstall") is False:
                reason = event.get("block_reason", "UNKNOWN")
                pkg = event.get("target_package", "?")

                t_title = LanguageBridge.translate("pack_tree_safety_guard", "🛑 [DETAIL BEZPEČNOSTNEJ OCHRANY]")
                t_pkg = LanguageBridge.translate("pack_tree_target_pkg", "Cieľový balíček: {0}").format(pkg)
                t_reason = LanguageBridge.translate("pack_tree_block_reason", "Dôvod zablokovania: {0}").format(reason)

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_pkg}")
                log_callback(f"   ├─ {t_reason}")

                if "broken_dependents" in event.data:
                    dep_str = ", ".join(event.get("broken_dependents", []))
                    t_detail = LanguageBridge.translate("pack_tree_broken_deps", "Balíček vyžadujú tieto komponenty: {0}").format(dep_str)
                elif "required_by_linker_modules" in event.data:
                    mod_str = ", ".join(event.get("required_by_linker_modules", []))
                    t_detail = LanguageBridge.translate("pack_tree_linker_required", "Vyžadované Linker modulmi: {0}").format(mod_str)
                elif "bound_parent" in event.data:
                    t_detail = LanguageBridge.translate("pack_tree_extra_bound_parent", "Balíček je naviazaný cez extra na požiadavku: {0}").format(event.get("bound_parent"))
                elif "defined_in_file" in event.data:
                    t_detail = LanguageBridge.translate("pack_tree_locked_in_reqs", "Natvrdo zapísaný v: {0}").format(event.get("defined_in_file"))
                else:
                    t_detail = LanguageBridge.translate("pack_tree_core_protected", "Chránené jadrom systému.")

                log_callback(f"   └─ {t_detail}")

            # C) DETAILNÁ INŠPEKCIA BALÍČKA A JEHO ZÁVISLOSTÍ
            elif event.state == AptState.ANALYZING and "declared_dependencies" in event.data:
                pkg = event.get("package", "?")
                loc = event.get("path", "")
                deps_analysis = event.get("deps_analysis", [])

                t_title = LanguageBridge.translate("edit_tree_inspect_title", "🔬 [INŠPEKCIA EDITOVATEĽNÉHO BALÍČKA]")
                t_pkg = LanguageBridge.translate("pack_tree_package", "Balíček: {0}").format(pkg)
                t_loc = LanguageBridge.translate("edit_tree_location", "Umiestnenie na disku: {0}").format(loc)
                t_deps_head = LanguageBridge.translate("edit_tree_deps_head", "📋 [ANALÝZA INTERNÝCH ZÁVISLOSTÍ VO VENV]")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_pkg}")
                log_callback(f"   ├─ {t_loc}")
                log_callback(f"   ├─ {t_deps_head}")

                if deps_analysis:
                    for i, d in enumerate(deps_analysis):
                        prefix = "   │  •"
                        label = d.get('spec', d['package'])
                        log_callback(f"{prefix} {label}: {d['status_text']}")
                        if d.get("extras_detail"):
                            ext_str = ", ".join(d["extras_detail"])
                            log_callback(f"   │     └─ extra [{', '.join(d['extras'])}] -> {ext_str}")
                else:
                    log_callback("   │  • " + LanguageBridge.translate("edit_no_internal_deps", "žiadne interné závislosti v setup.py/pyproject.toml"))

                actions = [d["action"] for d in deps_analysis]
                changes_count = actions.count("MISSING") + actions.count("MISMATCH")

                if changes_count > 0:
                    t_summary = LanguageBridge.translate(
                        "edit_summary_changes",
                        "Výsledok inšpekcie: Vyžaduje inštaláciu / zmenu {0} závislostí"
                    ).format(changes_count)
                else:
                    t_summary = LanguageBridge.translate(
                        "edit_summary_all_ok",
                        "Výsledok inšpekcie: Všetky závislosti sú na disku plne splnené"
                    )

                log_callback(f"   └─ {t_summary}")

        return _handler

    @classmethod
    def list_editable_packages(cls, venv_path: str, manager_type: str = "pip") -> list[dict]:
        """Získa zoznam editovateľných balíčkov výhradne cez PackageManagerFactory dispečer."""
        python_exe = Paths.get_venv_python_exe_path(venv_path)
        if not os.path.exists(python_exe):
            return []

        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("list_editable_json")
        except Exception:
            return []

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=CREATE_NO_WINDOW
            )
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout.strip())
        except Exception:
            pass
        return []

    @classmethod
    def _inspect_editable_dir(cls, target_path: str) -> tuple[str | None, list[str]]:
        """Vyparsuje z priečinka názov balíčka a zoznam jeho vlastných deklarovaných závislostí pomocou RequirementsParser."""
        pkg_name = RequirementsParser._get_package_name_from_dir(target_path)
        deps = RequirementsParser.get_project_dependencies(target_path)
        return pkg_name, deps

    @classmethod
    def install_editable_package(
        cls, 
        core, 
        venv_path: str, 
        target_path: str, 
        log_callback: Callable[[str], None] = print,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> EditableOperationStatus:
        rich_handler = cls._create_rich_status_handler(log_callback)

        def _unified_status(ev: AptStatusEvent):
            rich_handler(ev)
            if status_callback:
                try:
                    status_callback(ev)
                except Exception:
                    pass

        # 0. KONTROLA INTEGRITY STAVU (100% ZHODA KĽÚČOV V JSON)
        try:
            AptLogic._load_state_data(venv_path)
        except RuntimeError as e:
            err_msg = str(e)
            log_callback(err_msg)
            _unified_status(AptStatusEvent(
                state=AptState.FAILED,
                message=err_msg,
                data={"reason": "corrupt_state"}
            ))
            return EditableOperationStatus.ERROR

        target_norm = os.path.normpath(target_path)
        has_setup = os.path.exists(os.path.join(target_norm, "setup.py"))
        has_toml = os.path.exists(os.path.join(target_norm, "pyproject.toml"))

        if not has_setup and not has_toml:
            msg_invalid = LanguageBridge.translate(
                "edit_err_no_setup",
                "⚠️ [EditableService] Priečinok '{0}' neobsahuje setup.py ani pyproject.toml."
            ).format(os.path.basename(target_norm))
            log_callback(msg_invalid)
            _unified_status(AptStatusEvent(
                state=AptState.FAILED,
                message=msg_invalid,
                data={"reason": "invalid_project", "path": target_norm}
            ))
            return EditableOperationStatus.INVALID_PROJECT

        # 1. INŠPEKCIA BALÍČKA
        pkg_name, internal_deps = cls._inspect_editable_dir(target_norm)
        if not pkg_name:
            pkg_name = os.path.basename(target_norm)

        norm_name = AptLogic._normalize(pkg_name)

        log_callback("\n" + "="*55)
        log_callback(LanguageBridge.translate(
            "edit_inspect_info",
            "📦 [EditableService] Inšpekcia balíčka: '{0}' (Závislostí v kóde: {1})"
        ).format(norm_name, len(internal_deps)))

        # ANALÝZA ZÁVISLOSTÍ VOČI DISKU
        deps_analysis = cls._analyze_declared_dependencies(venv_path, internal_deps)

        _unified_status(AptStatusEvent(
            state=AptState.ANALYZING,
            message="",
            progress_pct=10,
            data={
                "package": norm_name,
                "path": target_norm,
                "declared_dependencies": internal_deps,
                "deps_analysis": deps_analysis
            }
        ))

        manager_type = getattr(core, "package_manager", "pip")

        # 2. OVERENIE VOČI REQUIREMENTS.TXT
        project_path = Paths.get_project_path(core.projects_root, core.active_project) if hasattr(core, 'projects_root') else ""
        req_file = Paths.get_requirements_txt_path(project_path) if project_path else ""

        is_in_project_reqs = False
        if os.path.exists(req_file):
            try:
                parsed_reqs = RequirementsParser.parse(req_file, pip_e_root=getattr(core, 'pip_e_packages_root', ''))
                if norm_name in parsed_reqs:
                    is_in_project_reqs = True
                    log_callback(LanguageBridge.translate(
                        "edit_in_reqs_info",
                        "ℹ️ [EditableService] Balíček '{0}' je definovaný v requirements.txt projektu."
                    ).format(norm_name))
            except Exception:
                pass

        # 3. APT PREVIERKA: STAV 1:1
        existing_editable = cls.list_editable_packages(venv_path, manager_type)
        already_linked_item = None
        for item in existing_editable:
            if AptLogic._normalize(item.get("name", "")) == norm_name:
                already_linked_item = item
                break

        if already_linked_item:
            raw_loc = already_linked_item.get("editable_project_location", "")
            installed_loc = os.path.normcase(os.path.normpath(raw_loc)) if raw_loc else ""
            requested_loc = os.path.normcase(os.path.normpath(target_norm))

            if installed_loc == requested_loc:
                changes_required = [d for d in deps_analysis if d["action"] in ("MISSING", "MISMATCH")]

                if not changes_required:
                    t_title = LanguageBridge.translate("pack_tree_disk_status", "🎯 [STAV BALÍČKA NA DISKU]")
                    t_pkg = LanguageBridge.translate("pack_tree_package", "Balíček: {0}").format(norm_name)
                    t_loc = LanguageBridge.translate("edit_tree_location", "Umiestnenie na disku: {0}").format(target_norm)
                    t_res = LanguageBridge.translate("pack_tree_result_satisfied", "Výsledok: 1:1 zhoda – inštalácia nie je potrebná")

                    log_callback(f"   ┌─ {t_title}")
                    log_callback(f"   ├─ {t_pkg}")
                    log_callback(f"   ├─ {t_loc}")
                    log_callback(f"   └─ {t_res}")

                    log_callback(LanguageBridge.translate(
                        "edit_skipped_1to1",
                        "✅ [EditableService] Inštalácia nie je potrebná (STAV 1:1)."
                    ))

                    if not is_in_project_reqs:
                        AptLogic.mark_as_explicit(venv_path, norm_name)

                    BirthCertificateGenerator.update_venv_certificate(venv_path)
                    _unified_status(AptStatusEvent(
                        state=AptState.COMPLETED_SKIPPED,
                        message="",
                        progress_pct=100,
                        data={"package": norm_name, "path": target_norm}
                    ))
                    return EditableOperationStatus.SKIPPED
                else:
                    change_labels = [f"{d['package']} ({d['status_text']})" for d in changes_required]
                    log_callback(LanguageBridge.translate(
                        "edit_deps_update_needed",
                        "⚡ [EditableService] Balíček '{0}' je prelinkovaný, ale vyžaduje aktualizáciu závislostí:\n   -> {1}"
                    ).format(norm_name, ', '.join(change_labels)))
            else:
                log_callback(LanguageBridge.translate(
                    "edit_path_changed",
                    "⚡ [EditableService] Zistená zmena cesty balíčka '{0}':\n   Pôvodná: {1}\n   Nová:    {2}"
                ).format(norm_name, raw_loc, target_norm))

        # 4. PRÍPRAVA PRÍKAZOV CEZ DISPEČER
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        except Exception as e:
            err_disp = LanguageBridge.translate("edit_err_dispatcher", "❌ [EditableService] Chyba dispečera: {0}").format(str(e))
            log_callback(err_disp)
            _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_disp, data={"error": str(e)}))
            return EditableOperationStatus.ERROR

        if manager_type == "pip":
            log_callback(LanguageBridge.translate("edit_ensuring_build_tools", "🛠 [EditableService] Zabezpečujem build nástroje (setuptools, wheel)..."))
            try:
                cmd_tools = dispatcher.get("install_multiple_exact", packages=["setuptools", "wheel"])
                subprocess.run(cmd_tools, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

        try:
            cmd = dispatcher.get("install_editable", path=target_norm)
        except Exception as e:
            err_build = LanguageBridge.translate("edit_err_cmd_build", "❌ [EditableService] Chyba pri zostavení príkazu install_editable: {0}").format(str(e))
            log_callback(err_build)
            _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_build, data={"error": str(e)}))
            return EditableOperationStatus.ERROR

        msg_running = LanguageBridge.translate(
            "edit_running_install",
            "⚡ [EditableService] Spúšťam {0} inštaláciu: -e {1}"
        ).format(manager_type.upper(), os.path.basename(target_norm))
        log_callback(msg_running)

        _unified_status(AptStatusEvent(
            state=AptState.INSTALLING,
            message=msg_running,
            progress_pct=40,
            data={"package": norm_name, "path": target_norm, "manager": manager_type}
        ))

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=CREATE_NO_WINDOW
            )
            for line in iter(proc.stdout.readline, ''):
                clean_l = line.strip()
                if clean_l:
                    log_callback(f"  {clean_l}")
            proc.wait()

            if proc.returncode != 0:
                err_code = LanguageBridge.translate("edit_err_install_code", "❌ [EditableService] Inštalácia zlyhala s kódom {0}.").format(proc.returncode)
                log_callback(err_code)
                _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_code, data={"exit_code": proc.returncode}))
                return EditableOperationStatus.ERROR

            # 5. INTEGRÁCIA DO APT MATRIKY (aj pre editable_packages_bound)
            raw_project_deps = RequirementsParser.get_project_dependencies(target_norm)
            deps = []
            extras_bound_map = {}
            
            # Správne volanie systémových balíčkov z AptLogic:
            system_pkgs = AptLogic.ensure_system_packages(venv_path)

            for raw_dep in raw_project_deps:
                clean_name = RequirementsParser._extract_package_name(raw_dep)
                if clean_name:
                    norm_dep = AptLogic._normalize(clean_name)
                    if norm_dep not in system_pkgs and norm_dep != norm_name:
                        deps.append(norm_dep)

                    req_exts = RequirementsParser.extract_extras(raw_dep)
                    if req_exts:
                        family = AptLogic.resolve_extras_family(venv_path, norm_dep, req_exts)
                        if family:
                            extras_bound_map[norm_dep] = family

            deps = sorted(list(set(deps)))

            # Zaregistrujeme väzby do editable_packages_bound
            AptLogic.bind_editable_package(
                venv_path=venv_path,
                pkg_name=norm_name,
                path=target_norm,
                packages=deps,
                extras_bound=extras_bound_map
            )

            if is_in_project_reqs:
                log_callback(LanguageBridge.translate("edit_syncing_project", "🔄 [EditableService] Synchronizujem stav projektu cez APT..."))
                AptLogic.install_sync(core, venv_path, log_callback=log_callback, status_callback=_unified_status)
            else:
                AptLogic.mark_as_explicit(venv_path, norm_name)

            # 6. KONTROLA INTEGRITY ZÁVISLOSTÍ
            cmd_check = dispatcher.get("check")
            check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            status = EditableOperationStatus.SUCCESS

            if check_proc.returncode != 0:
                out_err = (check_proc.stdout + "\n" + check_proc.stderr).strip()
                msg_conflict = LanguageBridge.translate("edit_check_conflicts", "⚠️ [{0} Check] Zistené nezrovnalosti v závislostiach:\n{1}").format(manager_type.upper(), out_err)
                log_callback(msg_conflict)
                status = EditableOperationStatus.SUCCESS_WITH_CONFLICTS
                _unified_status(AptStatusEvent(
                    state=AptState.COMPLETED_WARNING,
                    message=msg_conflict,
                    progress_pct=100,
                    data={"package": norm_name, "conflicts": out_err}
                ))
            else:
                log_callback(LanguageBridge.translate("edit_deps_ok", "✅ [EditableService] Všetky závislosti sú kompatibilné."))
                _unified_status(AptStatusEvent(
                    state=AptState.COMPLETED_SUCCESS,
                    message="",
                    progress_pct=100,
                    data={"package": norm_name}
                ))

            BirthCertificateGenerator.update_venv_certificate(venv_path)
            log_callback(LanguageBridge.translate("edit_install_success", "✅ [EditableService] Balíček '{0}' úspešne nainštalovaný v editovateľnom režime.").format(norm_name))
            return status

        except Exception as e:
            err_crit = LanguageBridge.translate("edit_err_critical", "❌ [EditableService] Kritická chyba: {0}").format(str(e))
            log_callback(err_crit)
            _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_crit, data={"exception": str(e)}))
            return EditableOperationStatus.ERROR

    @classmethod
    def uninstall_editable_package(
        cls, 
        core, 
        venv_path: str, 
        package_name: str, 
        log_callback: Callable[[str], None] = print,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> EditableOperationStatus:
        rich_handler = cls._create_rich_status_handler(log_callback)

        def _unified_status(ev: AptStatusEvent):
            rich_handler(ev)
            if status_callback:
                try:
                    status_callback(ev)
                except Exception:
                    pass

        if not package_name:
            return EditableOperationStatus.SKIPPED

        norm_name = AptLogic._normalize(package_name)
        log_callback("\n" + "="*55)
        log_callback(LanguageBridge.translate("edit_uninstall_start", "🗑️ [EditableService] Spúšťam previerku odinštalovania balíčka: '{0}'...").format(norm_name))

        # 0. KONTROLA INTEGRITY STAVU (100% ZHODA KĽÚČOV V JSON)
        try:
            AptLogic._load_state_data(venv_path)
        except RuntimeError as e:
            err_msg = str(e)
            log_callback(err_msg)
            _unified_status(AptStatusEvent(
                state=AptState.FAILED,
                message=err_msg,
                data={"reason": "corrupt_state"}
            ))
            return EditableOperationStatus.ERROR

        # 1. APT BEZPEČNOSTNÁ PREVIERKA (GUARD)
        is_safe, err_msg = AptLogic.verify_uninstall_safety(venv_path, core, norm_name, status_callback=_unified_status)
        if not is_safe:
            log_callback(LanguageBridge.translate("edit_uninstall_blocked", "🛑 [EditableService] STOP: {0}").format(err_msg))
            return EditableOperationStatus.BLOCKED

        # 2. ZBER ZÁVISLOSTÍ PRED ZMAZANÍM
        manager_type = getattr(core, "package_manager", "pip")
        released_reqs = AptLogic.get_requires_for_package(venv_path, norm_name, manager_type)

        # 3. ODINŠTALÁCIA CEZ DISPEČER
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("uninstall", package_name=norm_name)
        except Exception as e:
            err_un_disp = LanguageBridge.translate("edit_err_disp_uninstall", "❌ [EditableService] Chyba dispečera pri zostavení uninstall: {0}").format(str(e))
            log_callback(err_un_disp)
            _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_un_disp, data={"error": str(e)}))
            return EditableOperationStatus.ERROR

        msg_removing = LanguageBridge.translate("edit_physically_removing", "🚀 Spúšťam fyzickú odinštaláciu: {0} ({1})").format(norm_name, manager_type.upper())
        log_callback(msg_removing)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=CREATE_NO_WINDOW
            )
            for line in iter(proc.stdout.readline, ''):
                clean_l = line.strip()
                if clean_l:
                    log_callback(f"  {clean_l}")
            proc.wait()

            if proc.returncode != 0:
                err_un_code = LanguageBridge.translate("edit_err_uninstall_code", "❌ [EditableService] Odinštalácia zlyhala s kódom {0}.").format(proc.returncode)
                log_callback(err_un_code)
                _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_un_code, data={"exit_code": proc.returncode}))
                return EditableOperationStatus.ERROR

            # 4. SCRUB ZO STAVU A AUTOREMOVE SIROT
            AptLogic._emit(AptState.STATE_UPDATING, log_callback=log_callback, status_callback=_unified_status)

            kids = AptLogic.scrub_package_completely(venv_path, norm_name)
            all_released = list(dict.fromkeys(released_reqs + kids))

            if all_released:
                log_callback(LanguageBridge.translate("edit_checking_released", "🧹 [EditableService] Preverujem uvoľnené závislosti: {0}").format(', '.join(all_released)))
                AptLogic.autoremove(
                    core, 
                    venv_path, 
                    log_callback=log_callback, 
                    status_callback=_unified_status,
                    released_packages=all_released
                )

            BirthCertificateGenerator.update_venv_certificate(venv_path)
            msg_done = LanguageBridge.translate("edit_uninstall_done", "✅ [EditableService] Balíček '{0}' a jeho nepoužívané závislosti boli úspešne odstránené.").format(norm_name)
            log_callback(msg_done)
            _unified_status(AptStatusEvent(
                state=AptState.COMPLETED_SUCCESS,
                message="",
                progress_pct=100,
                data={"package": norm_name}
            ))
            return EditableOperationStatus.SUCCESS

        except Exception as e:
            err_un_crit = LanguageBridge.translate("edit_err_un_critical", "❌ [EditableService] Kritická chyba: {0}").format(str(e))
            log_callback(err_un_crit)
            _unified_status(AptStatusEvent(state=AptState.FAILED, message=err_un_crit, data={"exception": str(e)}))
            return EditableOperationStatus.ERROR
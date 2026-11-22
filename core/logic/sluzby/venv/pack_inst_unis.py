#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/pack_inst_unis.py
#----------------------------------------------------

import os
import re
import subprocess
from typing import Callable, Optional
from core.core_states import PackageOperationStatus
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.apt_state import AptState, AptStatusEvent
from core.logic.commands.command_factory import PackageManagerFactory


class PackageOperationsService:
    """
    Služba pre manuálnu inštaláciu a odinštalovanie balíčkov vo venv.
    Využíva stavový automat AptLogic a formátuje všetky stavy (AptStatusEvent)
    do prehľadného, plne lokalizovaného stromového logu.
    """

    @classmethod
    def _create_rich_status_handler(cls, log_callback: Callable[[str], None]) -> Callable[[AptStatusEvent], None]:
        """
        Formátuje štruktúrované udalosti z AptLogic do vizuálneho stromu.
        """
        def _handler(event: AptStatusEvent):
            # 1. ANALÝZA BALÍČKA
            if event.state == AptState.ANALYZING:
                pkg = event.get("target_package", "?")
                raw_spec = event.get("raw_spec", pkg)
                inst_ver = event.get("installed_version")
                is_inst = event.get("is_installed", False)
                req_extras = event.get("requested_extras", [])

                t_title = LanguageBridge.translate("pack_tree_analyzing_title", "🔬 [DETAIL ANALÝZY POŽIADAVKY]")
                t_pkg = LanguageBridge.translate("pack_tree_target_pkg", "Cieľový balíček: {0}").format(pkg)
                t_spec = LanguageBridge.translate("pack_tree_raw_spec", "Vstupná požiadavka: {0}").format(raw_spec)

                if is_inst:
                    t_disk = LanguageBridge.translate("pack_tree_disk_present", "Stav na disku: Nainštalovaný (verzia {0})").format(inst_ver)
                else:
                    t_disk = LanguageBridge.translate("pack_tree_disk_missing", "Stav na disku: Nenájdený (vyžaduje sa inštalácia)")

                ext_str = ", ".join(req_extras) if req_extras else LanguageBridge.translate("pack_tree_no_extras", "žiadne")
                t_ext = LanguageBridge.translate("pack_tree_extras_requested", "Požadované extras: [{0}]").format(ext_str)

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_pkg}")
                log_callback(f"   ├─ {t_spec}")
                log_callback(f"   ├─ {t_disk}")
                log_callback(f"   └─ {t_ext}")

            # 2. DETAIL O PRESKOČENÍ (Keď je balíček už na disku v správnej verzii)
            elif event.state == AptState.COMPLETED_SKIPPED:
                pkg = event.get("target_package", "?")
                ver = event.get("installed_version", "?")
                spec = event.get("requested_spec", "")

                t_title = LanguageBridge.translate("pack_tree_disk_status", "🎯 [STAV BALÍČKA NA DISKU]")
                t_pkg = LanguageBridge.translate("pack_tree_package", "Balíček: {0}").format(pkg)
                t_ver = LanguageBridge.translate("pack_tree_installed_ver", "Nainštalovaná verzia: {0}").format(ver)
                t_req = LanguageBridge.translate("pack_tree_requirement", "Požiadavka: {0}").format(spec)
                t_res = LanguageBridge.translate("pack_tree_result_satisfied", "Výsledok: 1:1 zhoda – inštalácia nie je potrebná")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_pkg}")
                log_callback(f"   ├─ {t_ver}")
                log_callback(f"   ├─ {t_req}")
                log_callback(f"   └─ {t_res}")

            # 3. BEZPEČNOSTNÁ KONTROLA PRED ODINŠTALÁCIOU
            elif event.state == AptState.VERIFYING_SAFETY:
                pkg = event.get("target_package", "?")
                t_title = LanguageBridge.translate("pack_tree_safety_check_title", "🛡️ [BEZPEČNOSTNÁ KONTROLA]")
                t_pkg = LanguageBridge.translate("pack_tree_target_pkg", "Testovaný balíček: {0}").format(pkg)
                t_info = LanguageBridge.translate("pack_tree_safety_info", "Overujem systémový stav, závislosti venvu, requirements.txt a Linker...")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_pkg}")
                log_callback(f"   └─ {t_info}")

            # 4. BEZPEČNOSTNÁ STOPKA (Presný rozbor prečo nemožno odinštalovať)
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

            # 5. FRONTA INŠTALÁCIE
            elif event.state == AptState.INSTALLING:
                pkgs_queue = event.get("packages_queue", [])
                mgr = event.get("package_manager", "pip").upper()
                if len(pkgs_queue) > 1:
                    t_queue = LanguageBridge.translate("pack_tree_install_queue", "📋 [{0}] Fronta balíčkov na inštaláciu ({1}):").format(mgr, len(pkgs_queue))
                    log_callback(f"   ┌─ {t_queue}")
                    for p in pkgs_queue:
                        log_callback(f"   │  • {p}")
                    log_callback("   └───────────────────────────────")

            # 6. EXTRAS VÄZBY (Strom rodiny naviazaných balíčkov)
            elif event.state == AptState.EXTRAS_SYNCING:
                parent = event.get("parent", "?")
                req_extras = event.get("requested_extras", [])
                children = event.get("resolved_children", [])
                ctx = event.get("context", "general")

                t_title = LanguageBridge.translate("pack_tree_extras_detected", "🧬 [EXTRAS DETEKCIA ({0})]").format(ctx)
                t_parent = LanguageBridge.translate("pack_tree_parent_pkg", "Rodičovský balíček: {0}").format(parent)
                t_req_ext = LanguageBridge.translate("pack_tree_extras_requested", "Požadované prívlastky: [{0}]").format(", ".join(req_extras))

                kids_str = ", ".join(children) if children else LanguageBridge.translate("pack_tree_no_extra_children", "žiadne ďalšie")
                t_children = LanguageBridge.translate("pack_tree_children_bound", "Naviazané závislosti na disku: {0}").format(kids_str)

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_parent}")
                log_callback(f"   ├─ {t_req_ext}")
                log_callback(f"   └─ {t_children}")

            # 7. ZÁPIS STAVU DO JSON-U
            elif event.state == AptState.STATE_UPDATING:
                t_title = LanguageBridge.translate("pack_tree_state_update", "💾 [EVIDENCIA APT STAVU]")
                t_file = LanguageBridge.translate("pack_tree_state_file", "Cieľ: site-packages/venvhub_apt_state.json")
                t_act = LanguageBridge.translate("pack_tree_state_action", "Akcia: Synchronizácia kľúčov 'explicit' a extras väzieb")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_file}")
                log_callback(f"   └─ {t_act}")

            # 8. GRAF ZÁVISLOSTÍ
            elif event.state == AptState.GRAPH_BUILDING:
                t_title = LanguageBridge.translate("pack_tree_graph_title", "📊 [STAVBA GRAFU ZÁVISLOSTÍ]")
                t_info = LanguageBridge.translate("pack_tree_graph_info", "Analyzujem vzájomné prepojenia nainštalovaných balíčkov...")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   └─ {t_info}")

            # 9. DETAIL SIRÔT (Autoremove)
            elif event.state == AptState.REMOVING_ORPHANS:
                orphans = event.get("orphans", [])
                mgr = event.get("manager", "PIP")

                t_title = LanguageBridge.translate("pack_tree_autoremove_detail", "🧹 [DETAIL AUTOREMOVE ({0})]").format(mgr)
                t_count = LanguageBridge.translate("pack_tree_orphans_count", "Počet nájdených sirôt na zmazanie: {0}").format(len(orphans))
                t_list = LanguageBridge.translate("pack_tree_orphans_list", "Zoznam: {0}").format(", ".join(orphans))

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_count}")
                log_callback(f"   └─ {t_list}")

        return _handler

    @classmethod
    def install_packages(
        cls, 
        core, 
        venv_path: str, 
        packages: list[str], 
        log_callback: Callable[[str], None],
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> PackageOperationStatus:
        rich_handler = cls._create_rich_status_handler(log_callback)

        def _unified_status(ev: AptStatusEvent):
            rich_handler(ev)
            if status_callback:
                try:
                    status_callback(ev)
                except Exception:
                    pass

        log_callback("\n" + "="*55)
        msg_start = LanguageBridge.translate("pack_start_install", "📦 [PackService] ŠTART INŠTALÁCIE: {0}").format(", ".join(packages))
        log_callback(msg_start)

        # 1. Pripravíme zoznam balíčkov vrátane extras
        items_to_check = []
        for pkg in packages:
            clean_name = AptLogic._extract_package_name(pkg)
            if not clean_name:
                continue

            extras = []
            match_extras = re.search(r"\[([^\]]+)\]", pkg)
            if match_extras:
                extras = [e.strip() for e in match_extras.group(1).split(",") if e.strip()]

            items_to_check.append((clean_name, pkg, extras))

        # 2. APT STAV 1:1 DIFF KONTROLA
        can_skip, skip_msg = AptLogic.check_install_necessity(
            venv_path, 
            core, 
            items_to_check, 
            log_callback=log_callback,
            status_callback=_unified_status
        )

        if can_skip:
            msg_skipped = LanguageBridge.translate("pack_apt_skipped", "✅ [APT: STAV 1] Všetky požiadavky sú už splnené. Inštalácia sa preskakuje.")
            log_callback(msg_skipped)
            return PackageOperationStatus.SKIPPED

        # 3. OCHRANA PRED PREPÍSANÍM REQUIREMENTS.TXT (UPOZORNENIE NA OVERRIDE)
        try:
            from core._path import Paths
            from core.logic.sluzby.requirements_parser import RequirementsParser

            project_path = Paths.get_project_path(core.projects_root, core.active_project)
            req_file = Paths.get_requirements_txt_path(project_path)

            if os.path.exists(req_file):
                req_map = RequirementsParser.parse_requirements(req_file, pip_e_root=getattr(core, 'pip_e_packages_root', ''))

                for clean_name, raw_spec, extras in items_to_check:
                    if clean_name in req_map:
                        req_spec = req_map[clean_name]
                        is_version_request = any(c in raw_spec for c in ["==", "<", ">", "~="])

                        if is_version_request and raw_spec != req_spec:
                            w_title = LanguageBridge.translate("pack_warn_override_title", "⚠️  [UPOZORNENIE: OVERRIDE]")
                            w_req = LanguageBridge.translate("pack_warn_override_req", "Balíček '{0}' má v requirements.txt verziu: '{1}'").format(clean_name, req_spec)
                            w_man = LanguageBridge.translate("pack_warn_override_manual", "Manuálne inštalujete odlišnú verziu: '{0}'").format(raw_spec)
                            w_temp = LanguageBridge.translate("pack_warn_override_temp", "Táto zmena je dočasná a pri synchronizácii requirements.txt sa vráti späť.")

                            log_callback(w_title)
                            log_callback(f"   ├─ {w_req}")
                            log_callback(f"   ├─ {w_man}")
                            log_callback(f"   └─ {w_temp}")
        except Exception:
            pass

        # 4. FYZICKÁ INŠTALÁCIA
        manager_type = getattr(core, "package_manager", "pip")
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("install_multiple_exact", packages=packages)

        AptLogic._emit(
            AptState.INSTALLING,
            log_callback=log_callback,
            status_callback=_unified_status,
            count=len(packages),
            pkgs=", ".join(packages),
            data={"packages_queue": packages, "package_manager": manager_type}
        )

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW
            )
            for line in process.stdout:
                log_callback(f"  {line.strip()}")
            process.wait()

            if process.returncode != 0:
                err_code = LanguageBridge.translate("pack_apt_err_code", "❌ [APT: CHYBA] Inštalátor zlyhal (kód {0}). Stav JSON ostáva nezmenený.").format(process.returncode)
                log_callback(err_code)
                AptLogic._emit(
                    AptState.FAILED, 
                    log_callback=None,
                    status_callback=_unified_status, 
                    err=err_code,
                    data={"exit_code": process.returncode}
                )
                return PackageOperationStatus.ERROR

        except Exception as e:
            err_crash = LanguageBridge.translate("pack_apt_err_crash", "❌ [APT: KRITICKÁ CHYBA] Subproces havaroval: {0}").format(str(e))
            log_callback(err_crash)
            AptLogic._emit(
                AptState.FAILED, 
                log_callback=None,
                status_callback=_unified_status, 
                err=str(e),
                data={"exception": str(e)}
            )
            return PackageOperationStatus.ERROR

        # 5. RESOLVE A BIND EXTRAS
        for clean_name, raw_spec, extras in items_to_check:
            if extras:
                AptLogic.resolve_and_bind_extras(
                    venv_path=venv_path,
                    parent_pkg=clean_name,
                    requested_extras=extras,
                    context="explicit",
                    status_callback=_unified_status
                )

        # 6. APT OCHRANA A ZÁPIS DO JSONU
        AptLogic._emit(AptState.STATE_UPDATING, log_callback=log_callback, status_callback=_unified_status)

        for clean_name, raw_spec, extras in items_to_check:
            is_version_change = any(c in raw_spec for c in ["==", "<", ">"])

            if is_version_change and AptLogic.is_subpackage_or_managed(venv_path, core, clean_name):
                msg_sub = LanguageBridge.translate("pack_apt_subpkg_updated", "ℹ️ [APT: GUARD] Verzia podbalíčka '{0}' upravená. Zostáva ako automatická závislosť (nie explicit).").format(clean_name)
                log_callback(msg_sub)
            else:
                AptLogic.mark_as_explicit(venv_path, clean_name)
                msg_explicit = LanguageBridge.translate("pack_apt_explicit_registered", "✅ [APT] Balíček '{0}' zaregistrovaný ako manuálny (explicit).").format(clean_name)
                log_callback(msg_explicit)

        AptLogic._emit(AptState.COMPLETED_SUCCESS, log_callback=log_callback, status_callback=_unified_status)
        return PackageOperationStatus.SUCCESS

    @classmethod
    def uninstall_packages(
        cls, 
        core, 
        venv_path: str, 
        packages: list[str], 
        log_callback: Callable[[str], None],
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> PackageOperationStatus:
        rich_handler = cls._create_rich_status_handler(log_callback)

        def _unified_status(ev: AptStatusEvent):
            rich_handler(ev)
            if status_callback:
                try:
                    status_callback(ev)
                except Exception:
                    pass

        log_callback("\n" + "="*55)
        msg_start_un = LanguageBridge.translate("pack_start_uninstall", "🗑️ [PackService] ŠTART ODINŠTALÁCIE: {0}").format(", ".join(packages))
        log_callback(msg_start_un)

        released_reqs = []

        # 1. KONTROLA BEZPEČNOSTI PRED ZMAZANÍM
        for pkg in packages:
            clean_name = AptLogic._extract_package_name(pkg)
            if not clean_name: 
                continue

            is_safe, err_msg = AptLogic.verify_uninstall_safety(
                venv_path, 
                core, 
                clean_name,
                status_callback=_unified_status
            )

            if not is_safe:
                return PackageOperationStatus.BLOCKED

            released_reqs.extend(AptLogic.get_requires_for_package(venv_path, clean_name, core.package_manager))

        # 2. FYZICKÁ ODINŠTALÁCIA
        manager_type = getattr(core, "package_manager", "pip")
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("uninstall_multiple", packages=packages)

        msg_run_un = LanguageBridge.translate("pack_apt_uninstall", "🚀 Spúšťam fyzickú odinštaláciu: {0}").format(", ".join(packages))
        log_callback(msg_run_un)

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW
            )
            for line in process.stdout:
                log_callback(f"  {line.strip()}")
            process.wait()

            if process.returncode != 0:
                err_un_code = LanguageBridge.translate("pack_apt_uninst_err_code", "❌ [APT: CHYBA] Odinštalácia zlyhala (kód {0}). Stav JSON ostáva nezmenený.").format(process.returncode)
                log_callback(err_un_code)
                AptLogic._emit(AptState.FAILED, log_callback=None, status_callback=_unified_status, err=err_un_code, data={"exit_code": process.returncode})
                return PackageOperationStatus.ERROR

        except Exception as e:
            err_crash = LanguageBridge.translate("pack_apt_err_crash", "❌ [APT: KRITICKÁ CHYBA] Subproces havaroval: {0}").format(str(e))
            log_callback(err_crash)
            AptLogic._emit(AptState.FAILED, log_callback=None, status_callback=_unified_status, err=str(e), data={"exception": str(e)})
            return PackageOperationStatus.ERROR

        # 3. VYHLADENIE ZO STAVU (SCRUB)
        AptLogic._emit(AptState.STATE_UPDATING, log_callback=log_callback, status_callback=_unified_status)

        for pkg in packages:
            clean_name = AptLogic._extract_package_name(pkg)
            if clean_name:
                kids = AptLogic.scrub_package_completely(venv_path, clean_name)
                released_reqs.extend(kids)

        # 4. AUTOREMOVE SIRÔT
        AptLogic.autoremove(
            core, 
            venv_path, 
            log_callback=log_callback, 
            status_callback=_unified_status,
            released_packages=released_reqs
        )

        msg_done = LanguageBridge.translate("pack_apt_uninst_done", "✅ [APT] Odinštalácia a čistenie úspešne dokončené.")
        log_callback(msg_done)
        AptLogic._emit(AptState.COMPLETED_SUCCESS, log_callback=None, status_callback=_unified_status)
        return PackageOperationStatus.SUCCESS
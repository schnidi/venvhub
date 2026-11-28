#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/linker_service.py
# Nízkoúrovňová jadrová služba pre lokálny linker (LOCAL_LINKER)
# Zabezpečuje ochranu, diff prostredia a detailný stromový reporting.
#----------------------------------------------------

import os
import json
import subprocess
import re
from collections import deque
from typing import Callable, Optional

from core._path import Paths
from core.logic.sluzby.language_bridge import LanguageBridge
from core.core_states import LinkerOperationStatus
from core.logic.sluzby.apt_state import AptState, AptStatusEvent
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.apt_ide_logic import AptIDELogic
from core.logic.vs_code_json import VSCodeIntegration


class LocalLinkerService:
    """
    Služba jadra pre správu a prelinkovanie lokálnych vývojových balíčkov.
    Implementuje prísnu ochranu stromu závislostí, diff analýzu prostredia 
    a detailné štruktúrované stromové logovanie.
    """

    @classmethod
    def _create_rich_status_handler(cls, log_callback: Callable[[str], None]) -> Callable[[AptStatusEvent], None]:
        """
        Formátuje štruktúrované udalosti z Linkera do vizuálneho stromu
        identicky s formátovaním v PackageOperationsService.
        """
        def _handler(event: AptStatusEvent):
            # 1. ANALÝZA ZÁVISLOSTÍ MODULU
            if event.state == AptState.ANALYZING:
                stage = event.get("stage", "general")
                if stage == "resolve_dependencies":
                    t_title = LanguageBridge.translate("linker_tree_ana_title", "🔍 [LINKER: REKURZÍVNA ANALÝZA METADÁT]")
                    t_sel = LanguageBridge.translate("linker_tree_ana_selected", "Vstupné moduly v UI ({0}): {1}").format(
                        len(event.get("selected", [])), ", ".join(event.get("selected", []))
                    )
                    t_info = LanguageBridge.translate("linker_tree_ana_info", "Prehľadávam local_meta.json a zostavujem kompletný strom závislostí...")
                    
                    log_callback(f"   ┌─ {t_title}")
                    log_callback(f"   ├─ {t_sel}")
                    log_callback(f"   └─ {t_info}")

            # 2. DIFF KONTROLA EXTERNÝCH PIP ZÁVISLOSTÍ
            elif event.state == AptState.DIFF_CALCULATING:
                total_deps = event.get("total_deps", 0)
                t_title = LanguageBridge.translate("linker_tree_diff_title", "⚖️ [LINKER: DIFF ANALÝZA PROSTREDIA]")
                t_total = LanguageBridge.translate("linker_tree_diff_total", "Celkový počet externých PIP požiadaviek na overenie: {0}").format(total_deps)
                t_info = LanguageBridge.translate("linker_tree_diff_action", "Porovnávam site-packages s požiadavkami (kontrola prítomnosti, verzií a extras)...")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_total}")
                log_callback(f"   └─ {t_info}")

            # 3. PRESKOČENIE INŠTALÁCIE (100% ZHODA S DISKOM)
            elif event.state == AptState.COMPLETED_SKIPPED:
                t_title = LanguageBridge.translate("linker_tree_skip_title", "🎯 [DIFF VÝSLEDOK: INŠTALÁCIA NIE JE POTREBNÁ]")
                t_status = LanguageBridge.translate("linker_tree_skip_status", "Stav prostredia: 100% balíčkov na disku už spĺňa verzie aj extras")
                t_action = LanguageBridge.translate("linker_tree_skip_action", "Akcia: Inštalačný proces (pip/uv) bol kompletne preskočený.")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_status}")
                log_callback(f"   └─ {t_action}")

            # 4. INŠTALÁCIA CHÝBAJÚCICH BALÍČKOV
            elif event.state == AptState.INSTALLING:
                pkgs_queue = event.get("packages_queue", [])
                mgr = event.get("package_manager", "pip").upper()
                t_title = LanguageBridge.translate("linker_tree_install_title", "🚀 [LINKER: INŠTALÁCIA ZISTENÝCH ROZDIELOV ({0})]").format(mgr)
                t_count = LanguageBridge.translate("linker_tree_install_count", "Chýbajúce / nevyhovujúce balíčky určené na inštaláciu ({0}):").format(len(pkgs_queue))

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_count}")
                for p in pkgs_queue:
                    log_callback(f"   │  • {p}")
                log_callback("   └────────────────────────────────────────")

            # 5. ZÁPIS HOOK SÚBOROV DO SITE-PACKAGES
            elif event.state == AptState.STATE_UPDATING:
                mode = event.get("mode", "hooks")
                if mode == "hooks":
                    t_title = LanguageBridge.translate("linker_tree_hooks_title", "🛠️ [LINKER: SYSTÉMOVÉ PREPOJENIA (.PTH & JSON)]")
                    t_dest = LanguageBridge.translate("linker_tree_hooks_dest", "Cieľ: site-packages/ (venvhub.json & venvhub_links.pth)")
                    t_add = LanguageBridge.translate("linker_tree_hooks_add", "Nové cesty na prelinkovanie: {0}").format(event.get("added", 0))
                    t_rem = LanguageBridge.translate("linker_tree_hooks_rem", "Odstraňované prepojenia: {0}").format(event.get("removed", 0))

                    log_callback(f"   ┌─ {t_title}")
                    log_callback(f"   ├─ {t_dest}")
                    log_callback(f"   ├─ {t_add}")
                    log_callback(f"   └─ {t_rem}")

                elif mode == "apt_state":
                    t_title = LanguageBridge.translate("linker_tree_apt_title", "🧠 [LINKER: SYNCHRONIZÁCIA 5. STAVU APT]")
                    t_file = LanguageBridge.translate("linker_tree_apt_file", "Zápis: site-packages/venvhub_apt_state.json -> linker_packages_bound")
                    t_mods = LanguageBridge.translate("linker_tree_apt_mods", "Evidované moduly ({0}): {1}").format(
                        len(event.get("modules", [])), ", ".join(event.get("modules", []))
                    )

                    log_callback(f"   ┌─ {t_title}")
                    log_callback(f"   ├─ {t_file}")
                    log_callback(f"   └─ {t_mods}")

            # 6. KONTROLA A SYNCHRONIZÁCIA IDE
            elif event.state == AptState.CHECKING_INTEGRITY:
                t_title = LanguageBridge.translate("linker_tree_ide_title", "💻 [LINKER: INTEGRÁCIA VÝVOJOVÉHO PROSTREDIA (IDE)]")
                t_pylance = LanguageBridge.translate("linker_tree_ide_pylance", "Aktualizácia extraPaths (.vscode/settings.json pre Pylance/Pyright)")
                t_tasks = LanguageBridge.translate("linker_tree_ide_tasks", "Synchronizácia spúšťacích úloh (.vscode/tasks.json & keybindings.json)")

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_pylance}")
                log_callback(f"   └─ {t_tasks}")

        return _handler

    @classmethod
    def _verify_unlink_safety(cls, core, selected_items: list[dict], modules_to_remove: set) -> tuple[bool, str, str]:
        """
        KONTROLA INTEGRITY ODLINKOVANIA:
        Overí, či modul určený na odpojenie nie je vyžadovaný iným modulom,
        ktorý používateľ v UI nechal zakliknutý.
        """
        for item in selected_items:
            parent_name = item.get("name")
            meta_path = os.path.join(item.get("path", ""), "local_meta.json")
            if not os.path.exists(meta_path):
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                
                req_local = [str(m).strip() for m in meta.get("requires_local", []) if str(m).strip()]
                for child in req_local:
                    if child in modules_to_remove:
                        return False, child, parent_name
            except Exception:
                pass

        return True, "", ""

    @classmethod
    def apply_links(
        cls, 
        core, 
        venv_path: str, 
        selected_items: list[dict], 
        log_callback: Callable[[str], None] = print,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> tuple[LinkerOperationStatus, str]:
        rich_handler = cls._create_rich_status_handler(log_callback)

        def _emit_state(state: AptState, msg: str, progress: int = None, data: dict = None):
            event = AptStatusEvent(
                state=state,
                message=msg,
                progress_pct=progress,
                data=data or {}
            )
            rich_handler(event)
            if status_callback:
                try:
                    status_callback(event)
                except Exception:
                    pass

        # 0. KONTROLA INTEGRITY STAVU (100% ZHODA KĽÚČOV V JSON)
        try:
            AptLogic._load_state_data(venv_path)
        except RuntimeError as e:
            err_msg = str(e)
            log_callback(err_msg)
            _emit_state(AptState.FAILED, err_msg, data={"reason": "corrupt_state"})
            return LinkerOperationStatus.ERROR, err_msg

        # 0. ZISTÍME AKTUÁLNE LINKOVANÉ MODULY V SITE-PACKAGES
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_packages = os.path.join(venv_path, site_folder, "site-packages")
        json_hook_file = os.path.join(site_packages, "venvhub.json")

        currently_linked = set()
        if os.path.exists(json_hook_file):
            try:
                with open(json_hook_file, "r", encoding="utf-8") as f:
                    currently_linked = set(json.load(f).keys())
            except Exception:
                pass

        for item in selected_items:
            item['name'] = os.path.basename(os.path.normpath(item['path']))

        new_selected_names = {item['name'] for item in selected_items}
        is_pure_unlink = len(selected_items) == 0 and len(currently_linked) > 0
        modules_to_remove = currently_linked - new_selected_names

        # ---------------------------------------------------------------------
        # KONTROLA BEZPEČNOSTI ODLINKOVANIA (ZÁKAZ ROZBITIA STROMU)
        # ---------------------------------------------------------------------
        if modules_to_remove and not is_pure_unlink:
            is_safe, blocked_child, parent_pkg = cls._verify_unlink_safety(core, selected_items, modules_to_remove)
            if not is_safe:
                log_callback("\n" + "=" * 70)
                t_stop_head = LanguageBridge.translate("linker_stop_head", "🛑 [LINKER: STOPKA ZÁVISLOSTÍ]")
                log_callback(f"   ┌─ {t_stop_head}")
                log_callback(f"   ├─ " + LanguageBridge.translate("linker_stop_target", "Pokus o odpojenie modulu: {0}").format(blocked_child))
                log_callback(f"   ├─ " + LanguageBridge.translate("linker_stop_required_by", "Tvrdá závislosť pre aktívny modul: {0}").format(parent_pkg))
                log_callback(f"   └─ " + LanguageBridge.translate("linker_stop_solution", "Riešenie: Najprv odlinkujte nadradený modul '{0}'.").format(parent_pkg))
                log_callback("=" * 70 + "\n")

                err_msg = LanguageBridge.translate(
                    "linker_err_dep_blocked",
                    "Nemožno odpojiť '{0}', pretože je vyžadovaný aktívnym modulom '{1}'."
                ).format(blocked_child, parent_pkg)

                _emit_state(AptState.FAILED, err_msg, data={
                    "blocked_child": blocked_child,
                    "parent_module": parent_pkg,
                    "reason": "child_required_by_active_parent"
                })
                return LinkerOperationStatus.DEPENDENCY_ERROR, err_msg

        # =====================================================================
        # VETVA A: ČISTÉ ODPOJENIE VŠETKÝCH MODULOV (UNLINK ALL)
        # =====================================================================
        if is_pure_unlink:
            log_callback("\n" + "=" * 70)
            log_callback(LanguageBridge.translate("linker_unlink_start", "🔌 [LINKER] ŠTART ODPOJENIA VŠETKÝCH LOKÁLNYCH BALÍČKOV (UNLINK)"))
            log_callback(LanguageBridge.translate("linker_target_venv", "📁 Cieľový Venv: {0}").format(venv_path))
            
            t_un_head = LanguageBridge.translate("linker_tree_unlink_head", "🗑️ [PREHĽAD ODPOJENIA MODULOV]")
            log_callback(f"   ┌─ {t_un_head}")
            log_callback(f"   ├─ " + LanguageBridge.translate("linker_tree_currently_linked", "Aktuálne pripojené moduly: {0}").format(len(currently_linked)))
            log_callback(f"   ├─ " + LanguageBridge.translate("linker_tree_to_remove", "Moduly určené na odpojenie ({0}): {1}").format(len(modules_to_remove), ', '.join(sorted(modules_to_remove))))
            log_callback(f"   └─ " + LanguageBridge.translate("linker_tree_final_count", "Zostávajúce moduly po operácii: 0"))
            log_callback("=" * 70)

            with AptLogic._get_venv_lock(venv_path):
                log_callback("\n" + LanguageBridge.translate("linker_step_unlink_hooks", "[KROK 1/3] 🛠️ Odstraňujem import hooky a linky zo site-packages..."))
                cls._manage_hook_files(venv_path, {}, log_callback)

                log_callback("\n" + LanguageBridge.translate("linker_step_unlink_apt", "[KROK 2/3] 🧠 Aktualizujem 5. stav APT a uvoľňujem závislosti..."))
                cls._sync_apt_linker_state(core, venv_path, {}, log_callback, status_callback=status_callback)

            log_callback("\n" + LanguageBridge.translate("linker_step_unlink_ide", "[KROK 3/3] 💻 Čistím konfiguráciu IDE (VS Code & Cursor AI)..."))
            project_path = Paths.get_project_path(core.projects_root, core.active_project)
            try:
                VSCodeIntegration.sync_local_packages(project_path, [], core.local_packages_root)
                VSCodeIntegration.sync_vscode_tasks_and_keybindings(project_path, [], core.local_packages_root, log_callback=log_callback)
            except Exception as e:
                log_callback(f"  ⚠️ {e}")

            log_callback("\n" + "=" * 70)
            msg_un_done = LanguageBridge.translate(
                "linker_unlink_success", 
                "✅ [LINKER] Všetky lokálne balíčky boli úspešne odpojené! (Odpojené: {0})"
            ).format(len(modules_to_remove))
            log_callback(msg_un_done)
            log_callback("=" * 70 + "\n")
            _emit_state(AptState.COMPLETED_SUCCESS, msg_un_done, progress=100)
            return LinkerOperationStatus.SUCCESS, ""

        # =====================================================================
        # VETVA B: LINK / UPDATE REŽIM
        # =====================================================================
        log_callback("\n" + "=" * 70)
        log_callback(LanguageBridge.translate("linker_log_start", "🔗 [LINKER] ŠTART PREPOJENIA LOKÁLNYCH BALÍČKOV"))
        log_callback(LanguageBridge.translate("linker_target_venv", "📁 Cieľový Venv: {0}").format(venv_path))
        log_callback(LanguageBridge.translate("linker_selected_count", "📦 Počet vybraných modulov v UI: {0}").format(len(selected_items)))
        if modules_to_remove:
            log_callback(LanguageBridge.translate("linker_modules_unlinking_note", "🔻 Moduly, ktoré budú odpojené ({0}): {1}").format(len(modules_to_remove), ', '.join(modules_to_remove)))
        log_callback("=" * 70)

        # ---------------------------------------------------------------------
        # KROK 1: REKURZÍVNA ANALÝZA A DETEKCIA ZÁVISLOSTÍ
        # ---------------------------------------------------------------------
        step1_title = LanguageBridge.translate("linker_step1_title", "\n[KROK 1/5] 🔍 Rekurzívna analýza lokálnych metadát (local_meta.json)...")
        log_callback(step1_title)
        
        _emit_state(
            AptState.ANALYZING, 
            step1_title, 
            progress=10, 
            data={"stage": "resolve_dependencies", "selected": [i['name'] for i in selected_items]}
        )

        all_packages_to_link, pip_dependencies, err_missing = cls._resolve_dependencies(
            core, selected_items, log_callback
        )
        if err_missing:
            msg_abort = LanguageBridge.translate("linker_aborted", "\n❌ [LINKER] Prerušené: {0}").format(err_missing)
            log_callback(msg_abort)
            _emit_state(AptState.FAILED, msg_abort, data={"reason": "missing_local_dep", "error": err_missing})
            return LinkerOperationStatus.MISSING_LOCAL_DEP, err_missing

        t_mod_head = LanguageBridge.translate("linker_tree_modules_head", "🧩 [SUMÁR ZISTENÝCH MODULOV A EXTERNÝCH ZÁVISLOSTÍ]")
        log_callback(f"   ┌─ {t_mod_head}")
        log_callback(f"   ├─ " + LanguageBridge.translate("linker_tree_total_modules", "Celkový počet zapojených modulov: {0}").format(len(all_packages_to_link)))
        log_callback(f"   ├─ " + LanguageBridge.translate("linker_tree_modules_list", "Zoznam: {0}").format(', '.join(all_packages_to_link.keys())))
        log_callback(f"   └─ " + LanguageBridge.translate("linker_tree_ext_pip_count", "Agregované externé PIP balíčky ({0}): {1}").format(
            len(pip_dependencies), ', '.join(pip_dependencies) if pip_dependencies else LanguageBridge.translate("pack_tree_no_extra_children", "žiadne")
        ))

        # ---------------------------------------------------------------------
        # KROK 2: DIFF KONTROLA A INŠTALÁCIA LEN CHÝBAJÚCICH BALÍČKOV
        # ---------------------------------------------------------------------
        with AptLogic._get_venv_lock(venv_path):
            step2_title = LanguageBridge.translate("linker_step2_title", "\n[KROK 2/5] ⚖️ Diff kontrola prostredia a inštalácia externých závislostí...")
            log_callback(step2_title)

            _emit_state(
                AptState.DIFF_CALCULATING, 
                step2_title, 
                progress=30, 
                data={"total_deps": len(pip_dependencies), "pip_dependencies": pip_dependencies}
            )

            if pip_dependencies:
                success_pip, err_pip = cls._install_dependencies_safely(
                    core, venv_path, pip_dependencies, log_callback, status_callback=_emit_state
                )
                if not success_pip:
                    msg_fail = LanguageBridge.translate("linker_pip_failed", "\n❌ [LINKER] Inštalácia externých závislostí zlyhala: {0}").format(err_pip)
                    log_callback(msg_fail)
                    log_callback(LanguageBridge.translate("linker_rollback_info", "⚠️ Stav venvu a prelinkovanie ostávajú nezmenené (Rollback)."))
                    _emit_state(AptState.FAILED, msg_fail, data={"reason": "dependency_error", "error": err_pip})
                    return LinkerOperationStatus.DEPENDENCY_ERROR, err_pip
            else:
                _emit_state(AptState.COMPLETED_SKIPPED, "Preskakujem diff", data={})

            # -----------------------------------------------------------------
            # KROK 3: ZÁPIS IMPORT HOOKOV DO SITE-PACKAGES
            # -----------------------------------------------------------------
            step3_title = LanguageBridge.translate("linker_step3_title", "\n[KROK 3/5] 🛠️ Správa import hookov a sys.path v site-packages...")
            log_callback(step3_title)

            added_count, removed_count = cls._manage_hook_files(
                venv_path, all_packages_to_link, log_callback
            )

            _emit_state(
                AptState.STATE_UPDATING, 
                step3_title, 
                progress=60, 
                data={"mode": "hooks", "added": added_count, "removed": removed_count}
            )

            # -----------------------------------------------------------------
            # KROK 4: APT SYNCHRONIZÁCIA (5. STAV: linker_packages_bound)
            # -----------------------------------------------------------------
            step4_title = LanguageBridge.translate("linker_step4_title", "\n[KROK 4/5] 🧠 Synchronizácia 5. stavu APT (linker_packages_bound)...")
            log_callback(step4_title)

            _emit_state(
                AptState.STATE_UPDATING, 
                step4_title, 
                progress=75, 
                data={"mode": "apt_state", "modules": list(all_packages_to_link.keys())}
            )

            try:
                cls._sync_apt_linker_state(core, venv_path, all_packages_to_link, log_callback, status_callback=status_callback)
            except Exception as e:
                err_msg = LanguageBridge.translate("linker_err_apt_sync", "Chyba pri synchronizácii stavu APT: {0}").format(str(e))
                log_callback(f"  ❌ {err_msg}")
                _emit_state(AptState.FAILED, err_msg, data={"exception": str(e)})
                return LinkerOperationStatus.ERROR, err_msg

        # ---------------------------------------------------------------------
        # KROK 5: IDE SYNCHRONIZÁCIA (VS Code & Cursor AI)
        # ---------------------------------------------------------------------
        step5_title = LanguageBridge.translate("linker_step5_title", "\n[KROK 5/5] 💻 Konfigurácia vývojového prostredia (VS Code / Cursor)...")
        log_callback(step5_title)
        
        _emit_state(AptState.CHECKING_INTEGRITY, step5_title, progress=90)

        try:
            log_callback(LanguageBridge.translate("linker_ide_ext_check", "  🧩 Overujem rozšírenia editora pre aktívny profil..."))
            AptIDELogic.sync_ide_extensions(core, all_packages_to_link, log_callback=log_callback)
        except Exception as e:
            log_callback(LanguageBridge.translate("linker_warn_ide_ext", "  ⚠️ Varovanie pri synchronizácii IDE rozšírení: {0}").format(str(e)))

        project_path = Paths.get_project_path(core.projects_root, core.active_project)
        target_paths = [pkg_data['path'] for pkg_data in all_packages_to_link.values()]

        try:
            log_callback(LanguageBridge.translate("linker_ide_pylance", "  ⚙️ Aktualizujem Pylance cesty (python.analysis.extraPaths)..."))
            VSCodeIntegration.sync_local_packages(project_path, target_paths, core.local_packages_root)

            log_callback(LanguageBridge.translate("linker_ide_tasks", "  📜 Aktualizujem úlohy (tasks.json) a klávesové skratky (keybindings.json)..."))
            VSCodeIntegration.sync_vscode_tasks_and_keybindings(
                project_path, target_paths, core.local_packages_root, log_callback=log_callback
            )
        except Exception as e:
            log_callback(LanguageBridge.translate("linker_warn_ide_files", "  ⚠️ Varovanie pri úprave projektových súborov IDE: {0}").format(str(e)))

        log_callback("\n" + "=" * 70)
        if added_count == 0 and removed_count == 0:
            msg_no_change = LanguageBridge.translate(
                "linker_no_changes", 
                "ℹ️ [LINKER] Všetky moduly, cesty aj nastavenia boli už aktuálne. Nebolo potrebné nič meniť."
            )
            log_callback(msg_no_change)
            log_callback("=" * 70 + "\n")
            _emit_state(AptState.COMPLETED_SUCCESS, msg_no_change, progress=100)
            return LinkerOperationStatus.NO_CHANGES, ""
        else:
            msg_success = LanguageBridge.translate(
                "linker_success_summary",
                "✅ [LINKER] Operácia úspešne dokončená! Aktívne moduly: {0} (Pridané: {1}, Odstránené: {2})."
            ).format(len(all_packages_to_link), added_count, removed_count)
            log_callback(msg_success)
            log_callback("=" * 70 + "\n")
            _emit_state(AptState.COMPLETED_SUCCESS, msg_success, progress=100)
            return LinkerOperationStatus.SUCCESS, ""

    # =========================================================================
    # DETAILNÁ REKURZÍVNA ANALÝZA A ČÍTANIE ZÁVISLOSTÍ
    # =========================================================================

    @classmethod
    def _resolve_dependencies(cls, core, selected_items: list[dict], log) -> tuple[dict, list, str]:
        all_to_link = {item['name']: item for item in selected_items}
        pip_deps = []
        queue = deque([item['name'] for item in selected_items])
        visited = set()

        t_resolve_head = LanguageBridge.translate("linker_tree_resolve_meta", "📄 [ČÍTANIE METADÁT JEDNOTLIVÝCH MODULOV]")
        log(f"   ┌─ {t_resolve_head}")

        while queue:
            pkg_name = queue.popleft()
            if pkg_name in visited:
                continue
            visited.add(pkg_name)

            pkg_data = all_to_link.get(pkg_name)
            if not pkg_data:
                continue

            meta_path = os.path.join(pkg_data['path'], "local_meta.json")
            if not os.path.exists(meta_path):
                log(f"   ├─ " + LanguageBridge.translate("linker_no_meta", "ℹ️ [{0}] Bez súboru local_meta.json (preskakujem)").format(pkg_name))
                continue

            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                req_pip = meta.get("requires_pip", [])
                req_local = meta.get("requires_local", [])

                log(f"   ├─ " + LanguageBridge.translate("linker_tree_meta_read", "Modul '{0}': {1} externých PIP, {2} lokálnych").format(
                    pkg_name, len(req_pip), len(req_local)
                ))

                for pip_pkg in req_pip:
                    clean_entry = str(pip_pkg).strip()
                    if clean_entry and clean_entry not in pip_deps:
                        pip_deps.append(clean_entry)
                        log(f"   │  • PIP: + '{clean_entry}'")

                for local_dep_name in req_local:
                    dep_clean = str(local_dep_name).strip()
                    if not dep_clean:
                        continue

                    already_in = any(
                        existing_name == dep_clean or existing_data['name'] == dep_clean
                        for existing_name, existing_data in all_to_link.items()
                    )
                    if not already_in:
                        dep_path = os.path.join(core.local_packages_root, dep_clean)
                        if not os.path.isdir(dep_path):
                            msg_fmt = LanguageBridge.translate("msg_missing_local_dep", "Chýba lokálna závislosť: {0} pre {1}")
                            err_msg = msg_fmt.format(dep_clean, pkg_name) + f"\nCesta neexistuje: {dep_path}"
                            log(f"   └─ ❌ {err_msg}")
                            return {}, [], err_msg

                        real_name = os.path.basename(os.path.normpath(dep_path))
                        log(f"   │  • LOKÁLNA: + '{real_name}' (objavená nová závislosť)")
                        all_to_link[real_name] = {'name': real_name, 'path': dep_path}
                        queue.append(real_name)

            except (json.JSONDecodeError, OSError, IOError) as e:
                log(f"   │  ⚠️ " + LanguageBridge.translate("linker_err_reading_meta", "Chyba čítania metadát modulu '{0}': {1}").format(pkg_name, str(e)))

        log("   └─ " + LanguageBridge.translate("linker_tree_resolve_done", "Analýza stromu metadát úspešne dokončená."))
        return all_to_link, pip_deps, ""

    # =========================================================================
    # DETAILNÁ DIFF KONTROLA A BEZPEČNÁ INŠTALÁCIA
    # =========================================================================

    @classmethod
    def _install_dependencies_safely(cls, core, venv_path: str, dependencies: list[str], log, status_callback=None) -> tuple[bool, str]:
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_pkgs_dir = os.path.join(venv_path, site_folder, "site-packages")
        if not os.path.exists(site_pkgs_dir):
            site_pkgs_dir = AptLogic._get_site_packages_dir(venv_path)

        installed_versions = cls._collect_installed_versions(site_pkgs_dir)
        installed_on_disk = set(installed_versions.keys())

        missing_dependencies = []
        satisfied_count = 0

        t_pip_head = LanguageBridge.translate("linker_tree_pip_status", "📋 [DETAILNÁ DIFF KONTROLA BALÍČKOV V SITE-PACKAGES]")
        log(f"   ┌─ {t_pip_head}")

        for dep in dependencies:
            raw_dep = str(dep).strip()
            if not raw_dep:
                continue

            clean_name = RequirementsParser._extract_package_name(raw_dep)
            if not clean_name:
                missing_dependencies.append(raw_dep)
                continue

            norm_name = AptLogic._normalize(clean_name)
            prefix = "   │  •"

            # 1. Kontrola či je balíček vôbec na disku
            if norm_name not in installed_on_disk:
                t_msg = LanguageBridge.translate("linker_pip_missing", "{0} -> 🔻 CHÝBA NA DISKU (vyžaduje inštaláciu)").format(raw_dep)
                log(f"{prefix} {t_msg}")
                missing_dependencies.append(raw_dep)
                continue

            # 2. Kontrola požadovanej verzie
            installed_ver = installed_versions.get(norm_name, "")
            if not cls._version_satisfied(raw_dep, installed_ver):
                t_msg = LanguageBridge.translate(
                    "linker_pip_mismatch",
                    "{0} (na disku: {1}, požadované: {2}) -> ⚡ ZMENA VERZIE"
                ).format(norm_name, installed_ver, raw_dep)
                log(f"{prefix} {t_msg}")
                missing_dependencies.append(raw_dep)
                continue

            # 3. Kontrola extras príznakov
            extras_match = re.search(r"\[([^\]]+)\]", raw_dep)
            if extras_match:
                extras_list = [AptLogic._normalize(e) for e in extras_match.group(1).split(",") if e.strip()]
                extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm_name)
                missing_children = [
                    child for ext in extras_list
                    for child in extras_map.get(ext, [])
                    if child not in installed_on_disk
                ]
                if missing_children:
                    t_msg = LanguageBridge.translate(
                        "linker_pip_extras_missing",
                        "{0} (chýbajú extras pod-závislosti: {1}) -> ⚡ VYŽADUJE DOKONČENIE"
                    ).format(raw_dep, ', '.join(missing_children))
                    log(f"{prefix} {t_msg}")
                    missing_dependencies.append(raw_dep)
                    continue

            # 4. Balíček 100% sedí
            satisfied_count += 1
            t_msg = LanguageBridge.translate("linker_pip_satisfied", "{0}=={1} -> ✅ VYHOVUJE (preskakujem)").format(norm_name, installed_ver)
            log(f"{prefix} {t_msg}")

        # VÝSLEDOK DIFF ANALÝZY
        if not missing_dependencies:
            log("   └─ " + LanguageBridge.translate(
                "linker_all_pip_ok", 
                "Výsledok diffu: Všetkých {0} externých požiadaviek je na disku plne splnených. Inštalácia je preskočená."
            ).format(satisfied_count))
            
            if status_callback:
                status_callback(AptState.COMPLETED_SKIPPED, "Diff overený", data={})
            return True, ""

        log("   └─ " + LanguageBridge.translate(
            "linker_pip_needs_install", 
            "Výsledok diffu: Vyhovuje: {0}, Vyžaduje doinštalovať / aktualizovať: {1}"
        ).format(satisfied_count, len(missing_dependencies)))

        # SPUSTENIE INŠTALÁCIE LEN PRE CHÝBAJÚCE BALÍČKY
        manager_type = getattr(core, 'package_manager', 'pip')
        if status_callback:
            status_callback(
                AptState.INSTALLING,
                f"Inštalácia {len(missing_dependencies)} balíčkov",
                data={"packages_queue": missing_dependencies, "package_manager": manager_type}
            )

        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("install_multiple_exact", packages=missing_dependencies)

            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

            log(LanguageBridge.translate("linker_cmd_exec", "  🛠️ Spúšťam príkaz: {0}").format(' '.join(cmd)))
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                creationflags=CREATE_NO_WINDOW
            )

            for line in iter(process.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    log(f"    [{manager_type.upper()}] {clean_line}")

            process.wait()
            if process.returncode == 0:
                log(LanguageBridge.translate("linker_install_success", "  ✔ Inštalácia chýbajúcich závislostí úspešne dokončená."))
                return True, ""
            else:
                err_msg = LanguageBridge.translate("linker_err_installer_code", "Inštalátor vrátil chybový kód {0}").format(process.returncode)
                return False, err_msg

        except Exception as e:
            return False, str(e)

    # =========================================================================
    # SPRÁVA IMPORT HOOKOV V SITE-PACKAGES
    # =========================================================================

    @classmethod
    def _manage_hook_files(cls, venv_path: str, packages_dict: dict, log) -> tuple[int, int]:
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_packages = os.path.join(venv_path, site_folder, "site-packages")
        os.makedirs(site_packages, exist_ok=True)

        json_file = os.path.join(site_packages, "venvhub.json")
        pth_file = os.path.join(site_packages, "venvhub_links.pth")

        # Čistenie zastaraných súborov
        for old_f in ["venvhub_bootstrap.py", "venvhub_bootstrap.pth", ".venvhub_linked"]:
            old_path = os.path.join(site_packages, old_f)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    log(LanguageBridge.translate("linker_cleaned_old_hook", "  🧹 Odstránený starý hook: {0}").format(old_f))
                except Exception:
                    pass

        existing_keys = set()
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    existing_keys = set(json.load(f).keys())
            except Exception:
                pass

        wanted_keys = set(packages_dict.keys())
        added_count = len(wanted_keys - existing_keys)
        removed_count = len(existing_keys - wanted_keys)

        if not packages_dict:
            for filepath in [json_file, pth_file]:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        log(LanguageBridge.translate("linker_hook_removed_file", "  🗑️ Zmazaný súbor hooku: {0}").format(os.path.basename(filepath)))
                    except Exception:
                        pass
            return added_count, removed_count

        mapping = {name: os.path.normpath(data['path']) for name, data in packages_dict.items()}

        log(LanguageBridge.translate("linker_writing_hook", "  📄 Zapisujem '{0}' ({1} aktívnych modulov)...").format(os.path.basename(json_file), len(mapping)))
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=4, ensure_ascii=False)

        log(LanguageBridge.translate("linker_writing_pth", "  📄 Zapisujem '{0}' (sys.path cesty do site-packages)...").format(os.path.basename(pth_file)))
        with open(pth_file, "w", encoding="utf-8") as f:
            for path in mapping.values():
                f.write(f"{path}\n")

        for name in wanted_keys - existing_keys:
            log(LanguageBridge.translate("linker_new_linked", "    ➕ Prelinkovaný nový modul: {0} -> {1}").format(name, mapping[name]))
        for name in existing_keys - wanted_keys:
            log(LanguageBridge.translate("linker_unlinked", "    ➖ Odlinkovaný modul: {0}").format(name))

        return added_count, removed_count

    # =========================================================================
    # 5. STAV APT: EVIDENCIA A AUTOREMOVE SIRÔT
    # =========================================================================

    @classmethod
    def _build_module_state(cls, mod_name: str, mod_data: dict, venv_path: str, log) -> dict:
        meta_path = os.path.join(mod_data['path'], "local_meta.json")
        if not os.path.exists(meta_path):
            return {"packages": [], "extras_bound": {}}

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except Exception as e:
            log(LanguageBridge.translate("linker_err_reading_meta_keep", "  ⚠️ Metadáta modulu '{0}' nie je možné prečítať ({1}), ponechávam starý stav.").format(mod_name, str(e)))
            return None

        base_packages = []
        extras_bound = {}

        for req_str in meta.get("requires_pip", []):
            req_clean = str(req_str).strip()
            if not req_clean:
                continue

            clean_name = RequirementsParser._extract_package_name(req_clean)
            if not clean_name:
                continue

            norm_name = AptLogic._normalize(clean_name)
            base_packages.append(norm_name)

            extras_match = re.search(r"\[([^\]]+)\]", req_clean)
            if extras_match:
                extras_list = [AptLogic._normalize(e) for e in extras_match.group(1).split(",") if e.strip()]
                family = AptLogic.resolve_extras_family(venv_path, norm_name, extras_list)
                if family:
                    merged = set(extras_bound.get(norm_name, [])) | set(family)
                    extras_bound[norm_name] = sorted(merged)

        return {"packages": sorted(list(set(base_packages))), "extras_bound": extras_bound}

    @classmethod
    def _sync_apt_linker_state(cls, core, venv_path: str, all_packages_to_link: dict, log, status_callback=None):
        old_bounds = AptLogic.load_linker_bounds(venv_path)

        modules_state = {}
        for mod_name, mod_data in all_packages_to_link.items():
            entry = cls._build_module_state(mod_name, mod_data, venv_path, log)
            if entry is None:
                entry = old_bounds.get(mod_name, {"packages": [], "extras_bound": {}})
            modules_state[mod_name] = entry

        log(LanguageBridge.translate("linker_writing_apt_state", "  💾 Zapisujem záznamy modulov do 'venvhub_apt_state.json'..."))
        released_packages = AptLogic.sync_linker_state(venv_path, modules_state)

        if released_packages:
            log(LanguageBridge.translate(
                "linker_released_pkgs",
                "  🔻 Detekované uvoľnené balíčky po zmene prelinkovania ({0}): {1}"
            ).format(len(released_packages), ', '.join(released_packages)))
            log(LanguageBridge.translate("linker_running_autoremove", "  🧹 Spúšťam APT Autoremove na preverenie a vyčistenie nepoužívaných sirôt..."))
            AptLogic.autoremove(core, venv_path, log_callback=log, status_callback=status_callback, released_packages=released_packages)
        else:
            log(LanguageBridge.translate("linker_no_pkgs_released", "  ✔ Žiadne balíčky neboli uvoľnené (autoremove nie je potrebný)."))

    # =========================================================================
    # POMOCNÉ METÓDY (VERZIE A DISK)
    # =========================================================================

    @classmethod
    def _collect_installed_versions(cls, site_pkgs_dir: str) -> dict[str, str]:
        versions = {}
        if not os.path.exists(site_pkgs_dir):
            return versions
        try:
            for entry in os.listdir(site_pkgs_dir):
                if entry.lower().endswith(".dist-info"):
                    stem = entry[:-len(".dist-info")]
                    name, _, version = stem.partition("-")
                    versions[AptLogic._normalize(name)] = version
        except Exception:
            pass
        return versions

    @classmethod
    def _version_satisfied(cls, raw_dep: str, installed_version: str) -> bool:
        try:
            dep = raw_dep.split(";")[0].strip()
            if "@" in dep or "://" in dep or dep.startswith((".", "/", "\\", "git+")):
                return True
            dep = re.sub(r"\[[^\]]*\]", "", dep)
            match = re.match(r"^[A-Za-z0-9_.\-]+\s*(.*)$", dep)
            spec = match.group(1).strip().strip("()") if match else ""
            if not spec or not installed_version:
                return True
            from packaging.specifiers import SpecifierSet
            return SpecifierSet(spec).contains(installed_version, prereleases=True)
        except Exception:
            return True
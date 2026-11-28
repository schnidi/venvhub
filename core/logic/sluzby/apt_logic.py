# -*- coding: utf-8 -*-
#----------------------------------------
# Súbor: core/logic/sluzby/apt_logic.py
#----------------------------------------

import os
import json
import re
import subprocess
import threading
from typing import Callable, Optional
from core._path import Paths
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.sluzby.system.python_detector import PythonDetector
from core.logic.sluzby.apt_state import AptState, AptStatusEvent
from core.logic.sluzby.language_bridge import LanguageBridge
from contextlib import contextmanager


class AptLogic:
    """
    Centrálny systém správy závislostí aplikácie VenvHub Pro inšpirovaný Linuxovým balíčkovacím systémom APT.

    ARCHITEKTÚRA - JEDINÝ ZDROJ PRAVDY (Single Source of Truth):
    Jediným zdrojom pravdy pre skutočný stav nainštalovaných a požadovaných balíčkov 
    je súbor 'venvhub_apt_state.json' uložený priamo v 'site-packages' daného venvu.
    Deklaratívnou modlou projektu je súbor 'requirements.txt'.

    MODEL EVIDENCIE (4 zdroje vlastníctva + 3 vrstvy mäkkých väzieb = 6 kľúčov v JSON,
    navyše 'system_packages' = snímka základu venvu, ktorý sa nikdy nemaže):
      1. explicit:
         - Balíčky, ktoré si používateľ nainštaloval manuálne (napr. cez GUI alebo priamo 'pip install pkg').
         - Tieto balíčky 'autoremove' NIKDY nezmaže, pokiaľ ich používateľ sám neodstráni.
      2. explicit_extras_bound:
         - Skutočné závislosti nainštalované kvôli manuálnym hranatým zátvorkám (napr. 'pip install requests[socks]' -> 'pysocks').
         - Mapovanie: { "rodičovský_balíček": ["dieťa_extra1", "dieťa_extra2"] }.
      3. requirements_cache:
         - Čisté názvy balíčkov zadeklarované v 'requirements.txt' projektu.
      4. requirements_extras_bound:
         - Skutočné balíčky nainštalované na základe hranatých zátvorkiek v 'requirements.txt'.
      5. linker_packages_bound (LOKÁLNY VÝVOJ / LINKER):
         - Balíčky vyžadované lokálne prelinkovanými vývojovými modulmi (z ich 'local_meta.json').
         - Štruktúra: { "Názov_Modulu": { "packages": [...], "extras_bound": { "rodič": [...] } } }.
         - Tieto balíčky sú chránené pred zmazaním, kým je daný modul v Linkeri pripojený.
      6. editable_packages_bound (LOKÁLNE EDITOVATEĽNÉ PROJEKTY / pip -e):
         - Balíčky nainštalované v editovateľnom režime (-e / --editable) zo súboru požiadaviek.
         - Štruktúra: { "názov_balíčka": { "path": "cesta", "packages": [...], "extras_bound": { "rodič": [...] } } }.
         - Zabezpečuje presný diff a evidenciu závislostí a extras patriacich editovateľnému projektu.

    PRAVIDLO VLASTNÍCTVA:
    Balíček na disku existuje fyzicky iba raz, ale môže mať viacero vlastníkov (referencií).
    Zmazať sa môže až vtedy, keď ho neuvoľní ANI JEDEN zo štyroch zdrojov:
    používateľ (explicit), projekt (requirements), lokálny modul (linker) a editovateľný projekt (pip -e).
    Jediná funkcia, ktorá o vlastníctve rozhoduje pri čistení, je 'get_all_owned_packages()':
    'autoremove' z uvoľnených balíčkov vždy vyradí tie, ktoré majú ešte aspoň jedného vlastníka.
    """

    _REQUIRED_STATE_KEYS = {
        "system_packages",
        "explicit",
        "explicit_extras_bound",
        "requirements_cache",
        "requirements_extras_bound",
        "linker_packages_bound",
        "editable_packages_bound"
    }

    _locks_guard = threading.Lock()
    _venv_locks = {}

    @staticmethod
    def _emit(
        state: AptState,
        log_callback: Optional[Callable[[str], None]] = None,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None,
        progress_pct: Optional[int] = None,
        data: Optional[dict] = None,
        **msg_kwargs
    ) -> AptStatusEvent:
        """
        Centrálny interný dispečer stavov a hlásení.
        Vytvorí lokalizovanú správu podľa AptState šablóny a odošle
        AptStatusEvent objekt do status_callbacku a formátovaný text do log_callbacku.
        """
        ctx_data = data if data is not None else {}
        for k, v in msg_kwargs.items():
            if k not in ctx_data:
                ctx_data[k] = v

        msg = state.format_message(**msg_kwargs)
        event = AptStatusEvent(
            state=state,
            message=msg,
            progress_pct=progress_pct,
            data=ctx_data
        )

        if status_callback:
            try:
                status_callback(event)
            except Exception:
                pass

        if log_callback:
            try:
                log_callback(msg)
            except Exception:
                pass

        return event

    @staticmethod
    def _tr(key: str, default: str, *args, **kwargs) -> str:
        """
        Centrálny preklad volajúci výhradne LanguageBridge.translate.
        """
        val = LanguageBridge.translate(key, default) 
        if args or kwargs:                           
            try:
                return val.format(*args, **kwargs)
            except Exception:
                pass
        return val

    @staticmethod
    @contextmanager
    def _get_venv_lock(venv_path: str):
        with AptLogic._locks_guard:
            entry = AptLogic._venv_locks.get(venv_path)
            if entry is None:
                entry = {'lock': threading.RLock(), 'count': 0}
                AptLogic._venv_locks[venv_path] = entry
            entry['count'] += 1
            lock = entry['lock']

        acquired = False
        try:
            acquired = lock.acquire()
            yield lock
        finally:
            if acquired:
                lock.release()
            
            with AptLogic._locks_guard:
                entry = AptLogic._venv_locks.get(venv_path)
                if entry:
                    entry['count'] -= 1
                    if entry['count'] <= 0:
                        del AptLogic._venv_locks[venv_path]

    @staticmethod
    def _get_target_env(venv_path: str) -> Optional[dict]:
        """Pomocná metóda na bezpečné získanie PEP 508 prostredia cieľového venvu."""
        try:
            python_exe = Paths.get_venv_python_exe_path(venv_path)
            return PythonDetector.get_pep508_environment(python_exe)
        except Exception:
            return None

    @staticmethod
    def _extract_package_name(token: str) -> str:
        extracted = RequirementsParser._extract_package_name(token)
        if extracted:
            return extracted
        token = token.strip()
        match = re.match(r"^[A-Za-z0-9_.\-]+", token)
        return match.group(0) if match else token

    @staticmethod
    def _normalize(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name.strip().lower())

    @staticmethod
    def _get_site_packages_dir(venv_path: str) -> str:
        site_folder = "Lib" if os.name == 'nt' else "lib"
        path = os.path.join(venv_path, site_folder, "site-packages")
        if not os.path.exists(path) and os.name != 'nt':
            import glob
            matches = glob.glob(os.path.join(venv_path, "lib", "python*", "site-packages"))
            if matches:
                return matches[0]
        return path

    @staticmethod
    def _get_state_file(venv_path: str) -> str:
        return os.path.join(AptLogic._get_site_packages_dir(venv_path), "venvhub_apt_state.json")

    @staticmethod
    def _load_state_data(venv_path: str) -> dict:
        state_file = AptLogic._get_state_file(venv_path)
        venv_name = os.path.basename(os.path.normpath(venv_path))

        if not os.path.exists(state_file):
            raise RuntimeError(AptState.CORRUPT_STATE.format_message(venv=venv_name))

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError()
        except Exception:
            raise RuntimeError(AptState.CORRUPT_STATE.format_message(venv=venv_name))

        if not AptLogic._REQUIRED_STATE_KEYS.issubset(data.keys()) or data.get("system_packages") is None:
            raise RuntimeError(AptState.CORRUPT_STATE.format_message(venv=venv_name))

        return data

    @staticmethod
    def _save_state_data(venv_path: str, data: dict) -> bool:
        state_file = AptLogic._get_state_file(venv_path)
        try:
            ordered_data = {
                "system_packages": data.get("system_packages"),
                "explicit": data.get("explicit", []),
                "explicit_extras_bound": data.get("explicit_extras_bound", {}),
                "requirements_cache": data.get("requirements_cache", []),
                "requirements_extras_bound": data.get("requirements_extras_bound", {}),
                "linker_packages_bound": data.get("linker_packages_bound", {}),
                "editable_packages_bound": data.get("editable_packages_bound", {})
            }
            tmp_file = state_file + ".tmp"
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(ordered_data, f, indent=4)
            os.replace(tmp_file, state_file)
            return True
        except Exception:
            try:
                if os.path.exists(state_file + ".tmp"):
                    os.remove(state_file + ".tmp")
            except Exception:
                pass
            return False

    # =========================================================================
    # --- LINUX APT LOGIC: OCHRANA A VYHLADENIE PRED ODINŠTALÁCIOU ---
    # =========================================================================
    
    @staticmethod
    def verify_uninstall_safety(
        venv_path: str, 
        core, 
        pkg_name: str, 
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> tuple[bool, str]:
        try:
            AptLogic._load_state_data(venv_path)
        except RuntimeError as err:
            venv_name = os.path.basename(os.path.normpath(venv_path))
            AptLogic._emit(AptState.CORRUPT_STATE, status_callback=status_callback, venv=venv_name)
            return False, str(err)

        norm_pkg = AptLogic._normalize(pkg_name)
        target_env = AptLogic._get_target_env(venv_path)
        
        AptLogic._emit(
            AptState.VERIFYING_SAFETY,
            status_callback=status_callback,
            pkg=norm_pkg,
            data={"target_package": norm_pkg}
        )

        collected_messages = []
        collected_block_reasons = []

        # Ochrana č. 0: SYSTÉMOVÝ BALÍČEK venvu
        if AptLogic.is_system_package(venv_path, norm_pkg):
            msg = AptLogic._tr(
                "apt_err_cannot_uninstall_system",
                "🛑 OCHRANA: Balíček '{0}' je systémový balíček prostredia (vznikol pri vytvorení venvu) a nedá sa odinštalovať.",
                norm_pkg
            )
            collected_messages.append(msg)
            collected_block_reasons.append({
                "block_reason": "SYSTEM_PACKAGE"
            })

        # Ochrana č. 1: Reverzné závislosti
        deps = AptLogic.is_package_required_by_others(venv_path, core, norm_pkg, include_linker=False)
        hard_deps = []

        if deps:
            bounds = AptLogic.load_extras_bound(venv_path, context="all")
            for dep in deps:
                if norm_pkg in bounds.get(dep, []):
                    continue
                else:
                    hard_deps.append(dep)

        if hard_deps:
            msg = AptLogic._tr(
                "apt_err_cannot_uninstall_deps", 
                "❌ Nemožno odinštalovať '{0}', pretože je to TVRDÁ ZÁVISLOSŤ pre: {1}", 
                norm_pkg, ", ".join(hard_deps)
            )
            collected_messages.append(msg)
            collected_block_reasons.append({
                "block_reason": "HARD_DEPENDENCY",
                "broken_dependents": hard_deps
            })

        # Ochrana č. 2: SVÄTÉ PÍSMO (requirements.txt + jeho viazané extras s PEP-508 filtrom)
        try:
            project_path = Paths.get_project_path(core.projects_root, core.active_project)
            req_file = Paths.get_requirements_txt_path(project_path)
            
            if os.path.exists(req_file):
                raw_reqs_map = RequirementsParser.parse_requirements(req_file, pip_e_root=core.pip_e_packages_root)
                # Berieme do úvahy iba tie deklarácie, ktoré vyhovujú aktuálnemu PEP-508 prostrediu
                parsed_reqs = {
                    norm: spec for norm, spec in raw_reqs_map.items()
                    if RequirementsParser.is_marker_valid(spec, target_env=target_env)
                }
                
                # A) Ak je balík priamo v platných požiadavkách
                if norm_pkg in parsed_reqs:
                    msg = AptLogic._tr(
                        "apt_err_cannot_uninstall_reqs", 
                        "🛑 OCHRANA: Balíček '{0}' je definovaný v 'requirements.txt'!\n\nMusíte ho najprv vymazať (alebo zakomentovať) v tomto súbore, inak by ste rozbili definíciu prostredia.", 
                        norm_pkg
                    )
                    collected_messages.append(msg)
                    collected_block_reasons.append({
                        "block_reason": "IN_REQUIREMENTS",
                        "defined_in_file": req_file
                    })

                # B) Skontrolujeme, či nie je naviazaný ako "extra" k niektorému balíku z requirements.txt
                req_bounds = AptLogic.load_extras_bound(venv_path, context="requirements")
                for req_parent in parsed_reqs:
                    bound_children = req_bounds.get(req_parent, [])
                    if norm_pkg in [AptLogic._normalize(c) for c in bound_children]:
                        msg = AptLogic._tr(
                            "apt_err_cannot_uninstall_reqs_extra",
                            "🛑 OCHRANA: Balíček '{0}' je vyžiadaný cez extra väzbu z requirements.txt balíka '{1}'!\n\nNemôžete ho samostatne odinštalovať, pokiaľ je definovaný v požiadavkách.",
                            norm_pkg, req_parent
                        )
                        collected_messages.append(msg)
                        collected_block_reasons.append({
                            "block_reason": "REQUIREMENTS_EXTRA_BOUND",
                            "bound_parent": req_parent
                        })
        except Exception:
            pass

        # Ochrana č. 2.5: EXPLICIT EXTRAS (napr. manuálne nainštalovaný requests[socks] -> pysocks)        
        explicit_parents = AptLogic.load_explicit_list(venv_path)
        explicit_bounds = AptLogic.load_extras_bound(venv_path, context="explicit")
        for exp_parent in explicit_parents:
            bound_children = explicit_bounds.get(exp_parent, [])
            if norm_pkg in [AptLogic._normalize(c) for c in bound_children]:
                msg = AptLogic._tr(
                    "apt_err_cannot_uninstall_explicit_extra",
                    "🛑 OCHRANA: Balíček '{0}' je naviazaný cez [extras] na manuálne nainštalovaný balíček '{1}'!\n\nNemôžete ho samostatne odinštalovať, pokiaľ je vyžadovaný rodičom.",
                    norm_pkg, exp_parent
                )
                collected_messages.append(msg)
                collected_block_reasons.append({
                    "block_reason": "EXPLICIT_EXTRA_BOUND",
                    "bound_parent": exp_parent
                })

        # Ochrana č. 3: 5. STAV - LOKÁLNY LINKER
        linker_parents = AptLogic.get_linker_modules_for_package(venv_path, norm_pkg)
        if linker_parents:
            msg = AptLogic._tr(
                "apt_err_cannot_uninstall_linker",
                "🛑 OCHRANA: Balíček '{0}' je vyžadovaný pripojeným lokálnym modulom: {1}!\n\nAk ho chcete odstrániť, najprv odlinkujte daný modul v okne Lokálne balíčky.",
                norm_pkg, ", ".join(linker_parents)
            )
            collected_messages.append(msg)
            collected_block_reasons.append({
                "block_reason": "LINKER_MODULE_BOUND",
                "required_by_linker_modules": linker_parents
            })

        # Ochrana č. 3.5: 6. STAV - LOKÁLNE EDITOVATEĽNÉ PROJEKTY (pip -e)
        editable_parents = AptLogic.get_editable_parents_for_package(venv_path, norm_pkg)
        if editable_parents:
            msg = AptLogic._tr(
                "apt_err_cannot_uninstall_editable_dep",
                "🛑 OCHRANA: Balíček '{0}' je vyžadovaný editovateľným projektom (pip -e): {1}!\n\nAk ho chcete odstrániť, musíte najprv zmeniť závislosti alebo odstrániť príslušný -e riadok v requirements.txt.",
                norm_pkg, ", ".join(editable_parents)
            )
            collected_messages.append(msg)
            collected_block_reasons.append({
                "block_reason": "EDITABLE_PACKAGE_BOUND",
                "required_by_editable": editable_parents
            })

        # =====================================================================
        # HROMADNÉ VYHODNOTENIE: Ak sa našla aspoň jedna chyba, zablokujeme to
        # =====================================================================
        if collected_messages:
            full_error_msg = "\n\n".join(collected_messages)
            
            AptLogic._emit(
                AptState.FAILED,
                status_callback=status_callback,
                err=full_error_msg,
                data={
                    "target_package": norm_pkg,
                    "can_uninstall": False,
                    "block_reasons_list": collected_block_reasons
                }
            )
            return False, full_error_msg

        return True, ""

    @staticmethod
    def scrub_package_completely(venv_path: str, pkg_name: str) -> list[str]:
        norm_pkg = AptLogic._normalize(pkg_name)
        released_kids = set()
        
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            modified = False

            if norm_pkg in data.get("explicit", []):
                data["explicit"].remove(norm_pkg)
                modified = True

            if norm_pkg in data.get("requirements_cache", []):
                data["requirements_cache"].remove(norm_pkg)
                modified = True

            for context in ["explicit_extras_bound", "requirements_extras_bound"]:
                bounds = data.get(context, {})
                if norm_pkg in bounds:
                    kids = bounds.pop(norm_pkg)
                    released_kids.update(kids)
                    modified = True

                for parent, children in list(bounds.items()):
                    if norm_pkg in children:
                        children.remove(norm_pkg)
                        modified = True
                        if not children:
                            del bounds[parent]

            linker_bounds = data.get("linker_packages_bound", {})
            for mod_name, mod_info in list(linker_bounds.items()):
                pkgs = mod_info.get("packages", [])
                if norm_pkg in pkgs:
                    pkgs.remove(norm_pkg)
                    modified = True

                ex_bound = mod_info.get("extras_bound", {})
                if norm_pkg in ex_bound:
                    kids = ex_bound.pop(norm_pkg)
                    released_kids.update(kids)
                    modified = True

                for p_pkg, c_list in list(ex_bound.items()):
                    if norm_pkg in c_list:
                        c_list.remove(norm_pkg)
                        modified = True
                        if not c_list:
                            del ex_bound[p_pkg]

            editable_bounds = data.get("editable_packages_bound", {})
            if norm_pkg in editable_bounds:
                e_info = editable_bounds.pop(norm_pkg)
                released_kids.update(e_info.get("packages", []))
                for c_list in e_info.get("extras_bound", {}).values():
                    released_kids.update(c_list)
                modified = True

            for e_name, e_info in list(editable_bounds.items()):
                e_pkgs = e_info.get("packages", [])
                if norm_pkg in e_pkgs:
                    e_pkgs.remove(norm_pkg)
                    modified = True

                e_ex = e_info.get("extras_bound", {})
                if norm_pkg in e_ex:
                    kids = e_ex.pop(norm_pkg)
                    released_kids.update(kids)
                    modified = True

                for p_pkg, c_list in list(e_ex.items()):
                    if norm_pkg in c_list:
                        c_list.remove(norm_pkg)
                        modified = True
                        if not c_list:
                            del e_ex[p_pkg]

            if modified:
                AptLogic._save_state_data(venv_path, data)
                
        return list(released_kids)

    # =========================================================================
    # --- LINUX APT LOGIC: KONTROLA PRED INŠTALÁCIOU (STAV 1:1) ---
    # =========================================================================

    @staticmethod
    def check_install_necessity(
        venv_path: str, 
        core, 
        installed_items: list, 
        log_callback=None,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> tuple[bool, str]:
        target_env = AptLogic._get_target_env(venv_path)

        with AptLogic._get_venv_lock(venv_path):
            try:
                state_data = AptLogic._load_state_data(venv_path)
            except RuntimeError as err:
                venv_name = os.path.basename(os.path.normpath(venv_path))
                AptLogic._emit(AptState.CORRUPT_STATE, log_callback=log_callback, status_callback=status_callback, progress_pct=100, venv=venv_name)
                return False, str(err)

            req_cache = set(state_data.get("requirements_cache", []))
            req_bounds = state_data.get("requirements_extras_bound", {})
            
            installed_versions = AptLogic._collect_installed_versions(venv_path)

            all_skipped = True
            skip_messages = []

            for item in installed_items:
                if len(item) == 3:
                    norm_pkg, raw_spec, requested_extras = item
                else:
                    norm_pkg, requested_extras = item
                    raw_spec = norm_pkg

                norm_pkg = AptLogic._normalize(norm_pkg)

                # --- 1. PEP 508 MARKER EVALUATION PRE CIEĽOVÉ VENV ---
                if not RequirementsParser.is_marker_valid(raw_spec, target_env=target_env):
                    msg_marker_skip = AptLogic._tr(
                        "apt_check_marker_skipped",
                        "  ℹ️ Balíček '{0}' je preskočený (podmienka markeru '{1}' neplatí pre cieľové prostredie).",
                        norm_pkg, raw_spec
                    )
                    if log_callback:
                        log_callback(msg_marker_skip)
                    continue

                installed_ver = installed_versions.get(norm_pkg)
                is_installed = installed_ver is not None

                AptLogic._emit(
                    AptState.ANALYZING,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    pkg=norm_pkg,
                    data={
                        "target_package": norm_pkg,
                        "raw_spec": raw_spec,
                        "requested_extras": requested_extras,
                        "installed_version": installed_ver,
                        "is_installed": is_installed
                    }
                )

                if not is_installed:
                    all_skipped = False
                    continue

                if not RequirementsParser.is_satisfied(raw_spec, installed_ver, target_env=target_env):
                    msg_ver_change = AptLogic._tr(
                        "apt_check_version_mismatch",
                        "  ⚡ Zistená zmena verzie pre '{0}': na disku je {1}, požadovaná je {2}. Spúšťam inštaláciu.",
                        norm_pkg, installed_ver, raw_spec
                    )
                    if log_callback:
                        log_callback(msg_ver_change)
                    all_skipped = False
                    continue

                extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm_pkg)
                covered_kids = set(req_bounds.get(norm_pkg, [])) | set(state_data.get("explicit_extras_bound", {}).get(norm_pkg, []))
                installed_pkgs_set = set(installed_versions.keys())
                
                uncovered_kids = [
                    kid for extra in requested_extras
                    for kid in extras_map.get(AptLogic._normalize(extra), [])
                    if kid not in covered_kids or kid not in installed_pkgs_set
                ]

                if uncovered_kids:
                    all_skipped = False
                    continue

                if norm_pkg not in req_cache:
                    AptLogic.mark_as_explicit(venv_path, norm_pkg)

                msg_detail = AptLogic._tr(
                    "apt_pkg_already_satisfied",
                    "ℹ️ Balíček '{0}=={1}' je už v tomto prostredí nainštalovaný a spĺňa požiadavku ({2}). Inštalácia nie je potrebná.",
                    norm_pkg, installed_ver, raw_spec
                )

                AptLogic._emit(
                    AptState.COMPLETED_SKIPPED,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    pkg=f"{norm_pkg}=={installed_ver}",
                    data={
                        "target_package": norm_pkg,
                        "installed_version": installed_ver,
                        "requested_spec": raw_spec,
                        "satisfied_by_disk": True
                    }
                )
                skip_messages.append(msg_detail)

            if all_skipped and installed_items:
                return True, "\n".join(skip_messages)

            return False, ""

    # =========================================================================
    # --- STAV 1: EXPLICIT ---
    # =========================================================================

    @staticmethod
    def load_explicit_list(venv_path: str) -> set:
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return set(data.get("explicit", []))

    @staticmethod
    def save_explicit_list(venv_path: str, explicit_set: set):
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            data["explicit"] = sorted(list(explicit_set))
            AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def is_in_requirements(venv_path: str, pkg_name: str, state_data: dict = None) -> bool:
        norm_pkg = AptLogic._normalize(pkg_name)
        if state_data is None:
            state_data = AptLogic._load_state_data(venv_path)
        if norm_pkg in set(state_data.get("requirements_cache", [])):
            return True
        for kids in state_data.get("requirements_extras_bound", {}).values():
            if norm_pkg in kids:
                return True
        return False

    @staticmethod
    def mark_as_explicit(venv_path: str, package_name: str):
        with AptLogic._get_venv_lock(venv_path):
            norm_pkg = AptLogic._normalize(package_name)
            data = AptLogic._load_state_data(venv_path)

            if AptLogic.is_in_requirements(venv_path, norm_pkg, state_data=data):
                return

            if norm_pkg in set(data.get("system_packages") or []):
                return

            explicit = set(data.get("explicit", []))
            explicit.add(norm_pkg)
            data["explicit"] = sorted(list(explicit))
            AptLogic._save_state_data(venv_path, data)

    # =========================================================================
    # --- STAVY 3 & 4: EXTRAS BOUND (MANUÁLNE A CEZ REQUIREMENTS) ---
    # =========================================================================

    @staticmethod
    def load_extras_bound(venv_path: str, context: str = "all") -> dict[str, list[str]]:
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            if context == "explicit":
                return data.get("explicit_extras_bound", {})
            elif context == "requirements":
                return data.get("requirements_extras_bound", {})
            elif context == "linker":
                return {p: sorted(k) for p, k in AptLogic._merge_linker_extras(data).items()}
            elif context == "editable":
                return {p: sorted(k) for p, k in AptLogic._merge_editable_extras(data).items()}
            else:
                merged = {}
                for k in ["explicit_extras_bound", "requirements_extras_bound"]:
                    for parent, kids in data.get(k, {}).items():
                        merged.setdefault(parent, set()).update(kids)
                for parent, kids in AptLogic._merge_linker_extras(data).items():
                    merged.setdefault(parent, set()).update(kids)
                for parent, kids in AptLogic._merge_editable_extras(data).items():
                    merged.setdefault(parent, set()).update(kids)
                return {p: sorted(list(k)) for p, k in merged.items()}

    @staticmethod
    def _merge_linker_extras(data: dict) -> dict[str, set]:
        merged: dict[str, set] = {}
        for mod_info in data.get("linker_packages_bound", {}).values():
            for parent, kids in mod_info.get("extras_bound", {}).items():
                merged.setdefault(parent, set()).update(kids)
        return merged

    @staticmethod
    def _merge_editable_extras(data: dict) -> dict[str, set]:
        merged: dict[str, set] = {}
        for e_info in data.get("editable_packages_bound", {}).values():
            for parent, kids in e_info.get("extras_bound", {}).items():
                merged.setdefault(parent, set()).update(kids)
        return merged

    @staticmethod
    def bind_extras(venv_path: str, parent_pkg: str, child_pkgs: list[str], context: str = "explicit"):
        norm_parent = AptLogic._normalize(parent_pkg)
        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        if not child_pkgs or norm_parent in system_pkgs:
            return

        target_key = "explicit_extras_bound" if context == "explicit" else "requirements_extras_bound"

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.setdefault(target_key, {})

            current_children = set(bounds.get(norm_parent, []))
            for child in child_pkgs:
                norm_child = AptLogic._normalize(child)
                if norm_child in system_pkgs or norm_child == norm_parent:
                    continue
                current_children.add(norm_child)

            if current_children:
                bounds[norm_parent] = sorted(list(current_children))
            AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def unbind_extras_for_parent(venv_path: str, parent_pkg: str, context: str = "explicit") -> list[str]:
        target_key = "explicit_extras_bound" if context == "explicit" else "requirements_extras_bound"
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.get(target_key, {})
            norm_parent = AptLogic._normalize(parent_pkg)
            children = bounds.pop(norm_parent, [])
            AptLogic._save_state_data(venv_path, data)
            return children

    @staticmethod
    def promote_bound_to_explicit(venv_path: str, pkg_name: str):
        norm_pkg = AptLogic._normalize(pkg_name)
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            modified = False
            
            bounds = data.get("explicit_extras_bound", {})
            for parent, children in list(bounds.items()):
                if norm_pkg in children:
                    children.remove(norm_pkg)
                    modified = True
                    if not children:
                        del bounds[parent]
                            
            if modified:
                AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def get_bound_children(venv_path: str, parent_pkg: str) -> list[str]:
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            norm_parent = AptLogic._normalize(parent_pkg)
            
            kids = set(data.get("explicit_extras_bound", {}).get(norm_parent, []))
            kids.update(data.get("requirements_extras_bound", {}).get(norm_parent, []))
            kids.update(AptLogic._merge_linker_extras(data).get(norm_parent, set()))
            kids.update(AptLogic._merge_editable_extras(data).get(norm_parent, set()))
            
            return sorted(list(kids))

    @staticmethod
    def set_bound_extras_for_parent(venv_path: str, parent_pkg: str, child_pkgs: list[str], context: str = "requirements"):
        norm_parent = AptLogic._normalize(parent_pkg)
        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        target_key = "explicit_extras_bound" if context == "explicit" else "requirements_extras_bound"

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.setdefault(target_key, {})

            filtered = set()
            for child in child_pkgs:
                norm_child = AptLogic._normalize(child)
                if norm_child in system_pkgs or norm_child == norm_parent:
                    continue
                filtered.add(norm_child)

            if filtered:
                bounds[norm_parent] = sorted(list(filtered))
            else:
                bounds.pop(norm_parent, None)

            AptLogic._save_state_data(venv_path, data)

    # =========================================================================
    # --- 5. STAV: LOKÁLNY LINKER (linker_packages_bound) ---
    # =========================================================================

    @staticmethod
    def load_linker_bounds(venv_path: str) -> dict:
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return data.get("linker_packages_bound", {})

    @staticmethod
    def _clean_linker_entry(packages, extras_bound=None, system_pkgs: set = None) -> dict:
        system_pkgs = system_pkgs or set()
        clean_pkgs = sorted({
            n for n in (AptLogic._normalize(p) for p in (packages or []))
            if n and n not in system_pkgs
        })
        clean_extras = {}
        for p_pkg, c_list in (extras_bound or {}).items():
            p_norm = AptLogic._normalize(p_pkg)
            if not p_norm or p_norm in system_pkgs:
                continue
            valid_children = sorted({
                n for n in (AptLogic._normalize(c) for c in (c_list or []))
                if n and n not in system_pkgs and n != p_norm
            })
            if valid_children:
                clean_extras[p_norm] = valid_children
        return {"packages": clean_pkgs, "extras_bound": clean_extras}

    @staticmethod
    def _linker_entry_packages(entry: dict) -> set:
        result = set(entry.get("packages", []))
        for c_list in entry.get("extras_bound", {}).values():
            result.update(c_list)
        return result

    @staticmethod
    def _linker_union(bounds: dict) -> set:
        result = set()
        for entry in bounds.values():
            result.update(AptLogic._linker_entry_packages(entry))
        return result

    @staticmethod
    def bind_linker_module(venv_path: str, module_name: str, packages: list[str], extras_bound: dict[str, list[str]] = None) -> list[str]:
        norm_mod = module_name.strip()
        if not norm_mod:
            return []

        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        new_entry = AptLogic._clean_linker_entry(packages, extras_bound, system_pkgs=system_pkgs)

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.setdefault("linker_packages_bound", {})
            old_entry = bounds.get(norm_mod, {})
            dropped = AptLogic._linker_entry_packages(old_entry) - AptLogic._linker_entry_packages(new_entry)
            bounds[norm_mod] = new_entry
            AptLogic._save_state_data(venv_path, data)
        return sorted(dropped)

    @staticmethod
    def sync_linker_state(venv_path: str, modules: dict[str, dict]) -> list[str]:
        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        new_bounds = {}
        for mod_name, info in (modules or {}).items():
            norm_mod = str(mod_name).strip()
            if not norm_mod:
                continue
            info = info or {}
            new_bounds[norm_mod] = AptLogic._clean_linker_entry(info.get("packages", []), info.get("extras_bound", {}), system_pkgs=system_pkgs)

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            old_union = AptLogic._linker_union(data.get("linker_packages_bound", {}))
            new_union = AptLogic._linker_union(new_bounds)
            data["linker_packages_bound"] = new_bounds
            if not AptLogic._save_state_data(venv_path, data):
                raise RuntimeError(AptLogic._tr("apt_err_state_save_failed", "Zápis venvhub_apt_state.json zlyhal."))
        return sorted(old_union - new_union)

    @staticmethod
    def unbind_linker_module(venv_path: str, module_name: str) -> list[str]:
        norm_mod = module_name.strip()
        released = set()

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.get("linker_packages_bound", {})
            if norm_mod in bounds:
                mod_data = bounds.pop(norm_mod)
                released.update(mod_data.get("packages", []))
                for c_list in mod_data.get("extras_bound", {}).values():
                    released.update(c_list)
                AptLogic._save_state_data(venv_path, data)

        return sorted(list(released))

    @staticmethod
    def get_all_linker_required_packages(venv_path: str) -> set[str]:
        all_reqs = set()
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            for mod_info in data.get("linker_packages_bound", {}).values():
                all_reqs.update(mod_info.get("packages", []))
                for c_list in mod_info.get("extras_bound", {}).values():
                    all_reqs.update(c_list)
        return all_reqs

    @staticmethod
    def get_linker_modules_for_package(venv_path: str, pkg_name: str) -> list[str]:
        norm_pkg = AptLogic._normalize(pkg_name)
        matched = []
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            for mod_name, mod_info in data.get("linker_packages_bound", {}).items():
                if norm_pkg in mod_info.get("packages", []):
                    matched.append(mod_name)
                    continue
                for c_list in mod_info.get("extras_bound", {}).values():
                    if norm_pkg in c_list:
                        matched.append(mod_name)
                        break
        return matched

    # =========================================================================
    # --- 6. STAV: EDITABLE BALÍČKY (pip -e / editable_packages_bound) ---
    # =========================================================================

    @staticmethod
    def _editable_entry_packages(entry: dict) -> set:
        """Vráti zjednotenie všetkých priamych závislostí a extras jedného -e balíka."""
        result = set(entry.get("packages", []))
        for c_list in entry.get("extras_bound", {}).values():
            result.update(c_list)
        return result

    @staticmethod
    def _editable_union(bounds: dict) -> set:
        """Vráti množinu všetkých balíčkov a extras, ktoré si vyžiadali akékoľvek editovateľné projekty."""
        result = set()
        for entry in bounds.values():
            result.update(AptLogic._editable_entry_packages(entry))
        return result

    @staticmethod
    def load_editable_bounds(venv_path: str) -> dict:
        """Načíta záznamy všetkých viazaných editable balíčkov z JSON stavu."""
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return data.get("editable_packages_bound", {})

    @staticmethod
    def bind_editable_package(venv_path: str, pkg_name: str, path: str, packages: list[str], extras_bound: dict = None) -> list[str]:
        """
        Zaregistruje alebo aktualizuje editovateľný balíček (pip -e) v JSON stave venvu.
        Vypočíta diff oproti predošlému stavu a vráti zoznam uvoľnených závislostí.
        """
        norm_pkg = AptLogic._normalize(pkg_name)
        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        clean_pkgs = sorted({
            n for n in (AptLogic._normalize(p) for p in (packages or []))
            if n and n not in system_pkgs and n != norm_pkg
        })
        clean_extras = {}
        for p_pkg, c_list in (extras_bound or {}).items():
            p_norm = AptLogic._normalize(p_pkg)
            if not p_norm or p_norm in system_pkgs:
                continue
            valid_children = sorted({
                n for n in (AptLogic._normalize(c) for c in (c_list or []))
                if n and n not in system_pkgs and n != p_norm
            })
            if valid_children:
                clean_extras[p_norm] = valid_children

        new_entry = {
            "path": path,
            "packages": clean_pkgs,
            "extras_bound": clean_extras
        }

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.setdefault("editable_packages_bound", {})
            old_entry = bounds.get(norm_pkg, {})
            dropped = AptLogic._editable_entry_packages(old_entry) - AptLogic._editable_entry_packages(new_entry)
            bounds[norm_pkg] = new_entry
            AptLogic._save_state_data(venv_path, data)
        return sorted(list(dropped))

    @staticmethod
    def unbind_editable_package(venv_path: str, pkg_name: str) -> list[str]:
        """
        Odstráni editovateľný balíček z JSON stavu a vráti všetky závislosti, ktoré naň boli naviazané.
        """
        norm_pkg = AptLogic._normalize(pkg_name)
        released = set()
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.get("editable_packages_bound", {})
            if norm_pkg in bounds:
                entry = bounds.pop(norm_pkg)
                released.update(entry.get("packages", []))
                for c_list in entry.get("extras_bound", {}).values():
                    released.update(c_list)
                AptLogic._save_state_data(venv_path, data)
        return sorted(list(released))

    @staticmethod
    def get_editable_parents_for_package(venv_path: str, pkg_name: str) -> list[str]:
        """Zistí, ktoré editovateľné projekty (pip -e) vyžadujú daný balíček ako svoju priamu závislosť alebo extra."""
        norm_pkg = AptLogic._normalize(pkg_name)
        matched = []
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            for e_name, e_info in data.get("editable_packages_bound", {}).items():
                if norm_pkg in e_info.get("packages", []):
                    matched.append(e_name)
                    continue
                for c_list in e_info.get("extras_bound", {}).values():
                    if norm_pkg in c_list:
                        matched.append(e_name)
                        break
        return matched

    @staticmethod
    def get_all_editable_required_packages(venv_path: str) -> set[str]:
        """Vráti zjednotenie všetkých podzávislostí patriacich editovateľným projektom v danom venvu."""
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return AptLogic._editable_union(data.get("editable_packages_bound", {}))

    @staticmethod
    def get_editable_project_dependencies(project_path: str) -> list[str]:
        return RequirementsParser.get_project_dependencies(project_path)

    @staticmethod
    def get_all_owned_packages(venv_path: str) -> set[str]:
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            owned = set(data.get("explicit", [])) | set(data.get("requirements_cache", []))
            owned.update(data.get("system_packages") or [])
            for key in ("explicit_extras_bound", "requirements_extras_bound"):
                for kids in data.get(key, {}).values():
                    owned.update(kids)
            owned.update(AptLogic._linker_union(data.get("linker_packages_bound", {})))

            ed_bounds = data.get("editable_packages_bound", {})
            owned.update(ed_bounds.keys())
            owned.update(AptLogic._editable_union(ed_bounds))

        return owned

    # =========================================================================
    # --- SYSTÉMOVÉ BALÍČKY VENVU (snímka stavu po vytvorení prostredia) ---
    # =========================================================================

    @staticmethod
    def _scan_installed_dist_names(venv_path: str) -> set:
        names = set()
        site_pkgs = AptLogic._get_site_packages_dir(venv_path)
        if os.path.exists(site_pkgs):
            try:
                for entry in os.listdir(site_pkgs):
                    if entry.lower().endswith(".dist-info"):
                        names.add(AptLogic._normalize(entry.split("-")[0]))
            except Exception:
                pass
        return names

    @staticmethod
    def snapshot_system_packages(venv_path: str) -> list[str]:
        names = sorted(AptLogic._scan_installed_dist_names(venv_path))
        if not names:
            return []
        with AptLogic._get_venv_lock(venv_path):
            state_file = AptLogic._get_state_file(venv_path)
            data = {
                "system_packages": names,
                "explicit": [],
                "explicit_extras_bound": {},
                "requirements_cache": [],
                "requirements_extras_bound": {},
                "linker_packages_bound": {},
                "editable_packages_bound": {}
            }
            if os.path.exists(state_file):
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            data.update(loaded)
                            data["system_packages"] = names
                except Exception:
                    pass

            if not AptLogic._save_state_data(venv_path, data):
                raise RuntimeError(AptLogic._tr("apt_err_state_save_failed", "Zápis venvhub_apt_state.json zlyhal."))
        return names

    @staticmethod
    def ensure_system_packages(venv_path: str) -> set[str]:
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return set(data.get("system_packages") or [])

    @staticmethod
    def is_system_package(venv_path: str, pkg_name: str) -> bool:
        return AptLogic._normalize(pkg_name) in AptLogic.ensure_system_packages(venv_path)

    # =========================================================================
    # --- ČÍTANIE METADATA Z DISKU A RESOLVE EXTRAS ---
    # =========================================================================

    @staticmethod
    def resolve_extras_family(venv_path: str, parent_pkg: str, requested_extras: list[str]) -> list[str]:
        norm_parent = AptLogic._normalize(parent_pkg)
        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        if not requested_extras or norm_parent in system_pkgs:
            return []

        site_pkgs = AptLogic._get_site_packages_dir(venv_path)
        if not os.path.exists(site_pkgs):
            return []

        installed_in_site = set()
        try:
            for entry in os.listdir(site_pkgs):
                if entry.lower().endswith(".dist-info"):
                    installed_in_site.add(AptLogic._normalize(entry.split("-")[0]))
        except Exception:
            pass

        extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm_parent)
        queue = []
        for extra in requested_extras:
            norm_extra = AptLogic._normalize(extra)
            for direct_child in extras_map.get(norm_extra, []):
                if direct_child in installed_in_site and direct_child != norm_parent:
                    queue.append(direct_child)

        all_family = set()
        visited = set()

        while queue:
            current = queue.pop(0)
            if current in visited or current in system_pkgs:
                continue
            visited.add(current)
            all_family.add(current)

            child_deps = AptLogic._get_all_requires_from_metadata(venv_path, current)
            for dep in child_deps:
                norm_dep = AptLogic._normalize(dep)
                if norm_dep in installed_in_site and norm_dep != norm_parent and norm_dep not in visited:
                    queue.append(norm_dep)

        return sorted(list(all_family))

    @staticmethod
    def resolve_and_bind_extras(
        venv_path: str, 
        parent_pkg: str, 
        requested_extras: list[str], 
        context: str = "explicit",
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> list[str]:
        all_family = AptLogic.resolve_extras_family(venv_path, parent_pkg, requested_extras)
        if all_family:
            AptLogic.bind_extras(venv_path, parent_pkg, all_family, context=context)
            AptLogic._emit(
                AptState.EXTRAS_SYNCING,
                status_callback=status_callback,
                parent=parent_pkg,
                children=", ".join(all_family),
                data={
                    "parent": AptLogic._normalize(parent_pkg),
                    "requested_extras": requested_extras,
                    "resolved_children": all_family,
                    "context": context
                }
            )
        return all_family

    @staticmethod
    def get_extras_map_from_metadata(venv_path: str, pkg_name: str) -> dict[str, list[str]]:
        extras_map = {}
        norm_target = AptLogic._normalize(pkg_name)
        site_pkgs = AptLogic._get_site_packages_dir(venv_path)

        if not os.path.exists(site_pkgs):
            return extras_map

        try:
            for entry in os.listdir(site_pkgs):
                if entry.lower().endswith(".dist-info"):
                    folder_pkg = AptLogic._normalize(entry.split("-")[0])
                    if folder_pkg == norm_target:
                        meta_file = os.path.join(site_pkgs, entry, "METADATA")
                        if os.path.isfile(meta_file):
                            with open(meta_file, "r", encoding="utf-8", errors="replace") as f:
                                for line in f:
                                    if line.startswith("Requires-Dist:") and "extra ==" in line:
                                        val = line.split(":", 1)[1].strip()
                                        extra_match = re.search(r"""extra\s*==\s*['"]([^'"]+)['"]""", val)
                                        if extra_match:
                                            extra_name = AptLogic._normalize(extra_match.group(1))
                                            dep_raw = val.split(";")[0].strip()
                                            clean_dep = AptLogic._extract_package_name(dep_raw)
                                            if clean_dep:
                                                norm_dep = AptLogic._normalize(clean_dep)
                                                extras_map.setdefault(extra_name, []).append(norm_dep)
        except Exception:
            pass

        return extras_map

    @staticmethod
    def _get_all_requires_from_metadata(venv_path: str, pkg_name: str, target_env: dict = None) -> list[str]:
        reqs = set()
        norm_target = AptLogic._normalize(pkg_name)
        site_pkgs = AptLogic._get_site_packages_dir(venv_path)

        if not os.path.exists(site_pkgs):
            return []

        if target_env is None:
            target_env = AptLogic._get_target_env(venv_path)

        try:
            for entry in os.listdir(site_pkgs):
                if entry.lower().endswith(".dist-info"):
                    folder_pkg = AptLogic._normalize(entry.split("-")[0])
                    if folder_pkg == norm_target:
                        meta_file = os.path.join(site_pkgs, entry, "METADATA")
                        if os.path.isfile(meta_file):
                            with open(meta_file, "r", encoding="utf-8", errors="replace") as f:
                                for line in f:
                                    if line.startswith("Requires-Dist:"):
                                        val = line.split(":", 1)[1].strip()

                                        # --- PEP-508 Marker overenie pre cieľové prostredie ---
                                        if not RequirementsParser.is_marker_valid(val, target_env=target_env):
                                            continue
                                        
                                        # 1. Ignorujeme extra podmienené prostredia
                                        if "extra ==" not in val:
                                            dep_raw = val.split(";")[0].strip()
                                            clean_dep = AptLogic._extract_package_name(dep_raw)
                                            if clean_dep:
                                                norm_dep = AptLogic._normalize(clean_dep)
                                                reqs.add(norm_dep)

                                                # --- Detekcia vnorených extras cez bezpečný RequirementsParser ---
                                                extras_list = RequirementsParser.extract_extras(dep_raw)
                                                if extras_list:
                                                    extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm_dep)
                                                    for ext in extras_list:
                                                        for extra_child in extras_map.get(ext, []):
                                                            reqs.add(extra_child)
        except Exception:
            pass

        # Pridanie explicitne naviazaných balíčkov zo stavového JSONu
        bound_children = AptLogic.get_bound_children(venv_path, norm_target)
        for child in bound_children:
            reqs.add(child)

        return sorted(list(reqs))

    @staticmethod
    def is_subpackage_or_managed(venv_path: str, core, pkg_name: str) -> bool:
        norm_pkg = AptLogic._normalize(pkg_name)
        state_data = AptLogic._load_state_data(venv_path)
        
        if norm_pkg in set(state_data.get("requirements_cache", [])):
            return True

        for key in ["explicit_extras_bound", "requirements_extras_bound"]:
            bounds = state_data.get(key, {})
            for parent, children in bounds.items():
                if norm_pkg in children:
                    return True

        if norm_pkg in AptLogic.get_all_linker_required_packages(venv_path):
            return True

        if norm_pkg in AptLogic.get_all_editable_required_packages(venv_path):
            return True

        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for parent_pkg, deps in graph.items():
                if norm_pkg in deps:
                    return True

        return False

    @staticmethod
    def get_editable_packages(venv_path: str, manager_type: str = "pip"):
        python_exe = Paths.get_venv_python_exe_path(venv_path)
        if not os.path.exists(python_exe):
            return []

        if manager_type == "uv":
            try:
                from core.logic.sluzby.core_bridge import CoreBridge
                uv_exe = CoreBridge.get_uv_path() or "uv"
            except Exception:
                uv_exe = "uv"
            cmd = [uv_exe, "pip", "list", "--editable", "--format=json", "--python", python_exe]
        else:
            cmd = [python_exe, "-m", "pip", "list", "--editable", "--format=json"]

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout.strip())
        except Exception:
            pass
        return []

    @staticmethod
    def is_package_required_by_others(venv_path, core, package_name, include_linker=True):
        pkg_norm = AptLogic._normalize(package_name)
        dependents = []

        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for other_pkg, requirements in graph.items():
                if other_pkg == pkg_norm:
                    continue
                if pkg_norm in requirements:
                    dependents.append(other_pkg)

        if include_linker:
            linker_modules = AptLogic.get_linker_modules_for_package(venv_path, pkg_norm)
            for mod in linker_modules:
                display_name = AptLogic._tr("apt_linker_module_tag", "{mod} (Linker)", mod=mod)
                if display_name not in dependents:
                    dependents.append(display_name)

            editable_parents = AptLogic.get_editable_parents_for_package(venv_path, pkg_norm)
            for e_parent in editable_parents:
                display_name = AptLogic._tr("apt_editable_module_tag", "{parent} (pip -e)", parent=e_parent)
                if display_name not in dependents:
                    dependents.append(display_name)

        return dependents

    @staticmethod
    def get_requires_for_package(venv_path, pkg_name, manager_type="pip"):
        reqs = []
        norm_pkg = AptLogic._normalize(pkg_name)
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("show", package_name=norm_pkg)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)

            for line in res.stdout.splitlines():
                if line.startswith("Requires:"):
                    val = line.replace("Requires:", "").strip()
                    if val:
                        reqs = [AptLogic._normalize(r) for r in val.split(",") if r.strip()]

            metadata_reqs = AptLogic._get_all_requires_from_metadata(venv_path, norm_pkg)
            for m_req in metadata_reqs:
                if m_req not in reqs:
                    reqs.append(m_req)

            bound_kids = AptLogic.get_bound_children(venv_path, norm_pkg)
            for b_kid in bound_kids:
                if b_kid not in reqs:
                    reqs.append(b_kid)

        except Exception:
            pass
        return reqs

    SHOW_MULTIPLE_CHUNK_SIZE = 30

    @staticmethod
    def get_dependency_graph(
        venv_path: str, 
        core, 
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ):
        with AptLogic._get_venv_lock(venv_path):
            AptLogic._emit(AptState.GRAPH_BUILDING, status_callback=status_callback)
            dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            graph = {}
            target_env = AptLogic._get_target_env(venv_path)

            try:
                list_cmd = dispatcher.get("list_json")
                res_list = subprocess.run(list_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, timeout=30)
                if res_list.returncode != 0:
                    return None

                installed_pkgs = [item["name"] for item in json.loads(res_list.stdout)]
                if not installed_pkgs:
                    return {}

                chunk_size = AptLogic.SHOW_MULTIPLE_CHUNK_SIZE
                for i in range(0, len(installed_pkgs), chunk_size):
                    chunk = installed_pkgs[i:i + chunk_size]
                    
                    try:
                        show_cmd = dispatcher.get("show_multiple", packages=chunk)
                        res_show = subprocess.run(
                            show_cmd, 
                            capture_output=True, 
                            text=True, 
                            encoding="utf-8", 
                            errors="replace", 
                            creationflags=CREATE_NO_WINDOW, 
                            timeout=30
                        )
                        if res_show.returncode != 0:
                            return None
                        output_text = res_show.stdout
                    except Exception:
                        return None 
                        
                    current_pkg = None
                    for line in output_text.splitlines():
                        if line.startswith("Name:"):
                            current_pkg = AptLogic._normalize(line.split(":", 1)[1].strip())
                            graph[current_pkg] = []
                        elif line.startswith("Requires:") and current_pkg:
                            reqs = line.split(":", 1)[1].strip()
                            base_reqs = [
                                AptLogic._normalize(AptLogic._extract_package_name(r))
                                for r in reqs.split(",") if r.strip()
                            ] if reqs else []

                            meta_reqs = AptLogic._get_all_requires_from_metadata(venv_path, current_pkg, target_env=target_env)
                            all_deps = set(base_reqs + meta_reqs)
                            graph[current_pkg] = list(all_deps)
            except Exception:
                return None

            return graph

    # =========================================================================
    # --- ČÍTANIE EXTRAS ZO SÚBORU REQUIREMENTS.TXT PRI INŠTALÁCII ---
    # =========================================================================

    @staticmethod
    def _scan_requirements_for_extras(req_file_path: str, core=None) -> dict[str, list[str]]:
        pip_e_root = getattr(core, 'pip_e_packages_root', None) if core else None
        return RequirementsParser.parse_extras_map(req_file_path, pip_e_root=pip_e_root)

    # =========================================================================
    # --- ČÍTANIE A OVEROVANIE VERZIÍ BALÍČKOV NA DISKU ---
    # =========================================================================

    @staticmethod
    def _collect_installed_versions(venv_path: str) -> dict[str, str]:
        versions = {}
        site_pkgs = AptLogic._get_site_packages_dir(venv_path)
        if not os.path.exists(site_pkgs):
            return versions
        try:
            for entry in os.listdir(site_pkgs):
                if entry.lower().endswith(".dist-info"):
                    stem = entry[:-len(".dist-info")]
                    name, _, version = stem.partition("-")
                    if name:
                        versions[AptLogic._normalize(name)] = version
        except Exception:
            pass
        return versions

    # =========================================================================
    # --- SYNCHRONIZÁCIA: INSTALL_SYNC (PLNE STAVOVÝ S PEP 508 MARKERMI) ---
    # =========================================================================

    @staticmethod
    def install_sync(
        core, 
        venv_path: str, 
        log_callback=None, 
        req_file_path: str = None,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> bool:
        with AptLogic._get_venv_lock(venv_path):
            try:
                state_data = AptLogic._load_state_data(venv_path)
            except RuntimeError as e:
                venv_name = os.path.basename(os.path.normpath(venv_path))
                AptLogic._emit(
                    AptState.CORRUPT_STATE,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    progress_pct=100,
                    venv=venv_name
                )
                return False

            AptLogic._emit(
                AptState.DIFF_CALCULATING,
                log_callback=log_callback,
                status_callback=status_callback,
                progress_pct=5
            )

            try:
                if not req_file_path or not os.path.exists(req_file_path):
                    project_path = Paths.get_project_path(core.projects_root, core.active_project)
                    req_file_path = Paths.get_requirements_txt_path(project_path)

                # PEP 508 prostredie cieľového venvu
                target_env = AptLogic._get_target_env(venv_path)
                system_pkgs = set(state_data.get("system_packages") or [])

                pamat_extras = AptLogic._scan_requirements_for_extras(req_file_path, core=core)

                pip_e_root = getattr(core, 'pip_e_packages_root', '')
                raw_requirements_map = RequirementsParser.parse_requirements(req_file_path, pip_e_root=pip_e_root) if os.path.exists(req_file_path) else {}

                # =============================================================
                # KROK 0: FILTROVANIE POŽIADAVIEK CEZ PEP 508 ENVIRONMENT MARKERY
                # Do wanted_packages sa dostanú LEN tie, ktoré platia pre cieľový systém!
                # =============================================================
                requirements_map = {}
                for norm_pkg, req_line in raw_requirements_map.items():
                    if RequirementsParser.is_marker_valid(req_line, target_env=target_env):
                        requirements_map[norm_pkg] = req_line
                    else:
                        if log_callback:
                            log_callback(AptLogic._tr(
                                "apt_marker_skipped_env",
                                "  ℹ️ Preskakujem požiadavku '{0}': podmienka prostredia ({1}) neplatí pre toto prostredie.",
                                norm_pkg, req_line
                            ))

                wanted_packages = set(requirements_map.keys())

                cached_reqs = set(state_data.get("requirements_cache", []))
                released_from_reqs = list(cached_reqs - wanted_packages)

                installed_versions = AptLogic._collect_installed_versions(venv_path)

                missing_editable_args = []
                missing_standard_args = []
                missing_log_labels = []

                for norm_pkg, req_line in requirements_map.items():
                    inst_ver = installed_versions.get(norm_pkg)

                    if req_line.startswith("-e "):
                        raw_path = req_line[3:].strip()

                        # 1. PRED-KONTROLA: Načítame závislosti priamo zo zdrojov (pyproject.toml/setup.py)
                        raw_editable_deps = AptLogic.get_editable_project_dependencies(raw_path)
                        # Filtrujeme aj závislosti v projekte podľa markerov pre cieľové venv
                        editable_deps = [
                            d for d in raw_editable_deps
                            if RequirementsParser.is_marker_valid(d, target_env=target_env)
                        ]

                        stored_entry = state_data.get("editable_packages_bound", {}).get(norm_pkg, {})
                        stored_deps = set(stored_entry.get("packages", []))
                        current_source_deps = {
                            n for n in (
                                AptLogic._normalize(RequirementsParser._extract_package_name(d))
                                for d in editable_deps
                                if RequirementsParser._extract_package_name(d)
                            )
                            if n not in system_pkgs and n != norm_pkg
                        }

                        # Ak balíček chýba ALEBO sa zmenili jeho deklarované závislosti v TOML:
                        if not inst_ver or stored_deps != current_source_deps:
                            if f"{norm_pkg} (-e)" not in missing_log_labels:
                                missing_log_labels.append(f"{norm_pkg} (-e)")
                                missing_editable_args.extend(["-e", raw_path, "--no-deps"])

                        for ed_dep in editable_deps:
                            dep_norm = AptLogic._normalize(AptLogic._extract_package_name(ed_dep))
                            dep_inst_ver = installed_versions.get(dep_norm)

                            # Kontrola chýbania alebo nesúladu verzie
                            if not dep_inst_ver:
                                if ed_dep not in missing_standard_args:
                                    missing_log_labels.append(f"{ed_dep} (pre {norm_pkg})")
                                    missing_standard_args.append(ed_dep)
                            elif not RequirementsParser.is_satisfied(ed_dep, dep_inst_ver, target_env=target_env):
                                if ed_dep not in missing_standard_args:
                                    missing_log_labels.append(f"{ed_dep} (akt: {dep_inst_ver})")
                                    missing_standard_args.append(ed_dep)
                    else:
                        # Štandardný bežný balíček
                        req_extras = RequirementsParser.extract_extras(req_line)

                        if not inst_ver:
                            missing_log_labels.append(norm_pkg)
                            missing_standard_args.append(req_line)
                        elif not RequirementsParser.is_satisfied(req_line, inst_ver, target_env=target_env):
                            missing_log_labels.append(f"{norm_pkg} (akt: {inst_ver} -> žiad: {req_line})")
                            missing_standard_args.append(req_line)
                        elif req_extras:
                            # 3. KONTROLA EXTRAS: Verzia balíčka sedí, ale musíme overiť, či sú na disku a v stave aj jeho extras
                            req_bounds = set(state_data.get("requirements_extras_bound", {}).get(norm_pkg, []))
                            extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm_pkg)

                            uncovered = [
                                kid for extra in req_extras
                                for kid in extras_map.get(AptLogic._normalize(extra), [])
                                if kid not in req_bounds or kid not in installed_versions
                            ]

                            # Ak v požiadavkách pribudol extra, ktorý ešte nie je v JSON-e, alebo jeho pod-balíček chýba na disku:
                            if uncovered or (norm_pkg not in state_data.get("requirements_extras_bound", {})):
                                missing_log_labels.append(f"{norm_pkg}[{', '.join(req_extras)}]")
                                missing_standard_args.append(req_line)

                if released_from_reqs and log_callback:
                    log_callback(AptLogic._tr("apt_released_from_reqs", "  🔻 Uvoľnené zo súboru: {pkgs}", pkgs=', '.join(released_from_reqs)))
                if missing_log_labels and log_callback:
                    log_callback(AptLogic._tr("apt_missing_packages", "  🔺 Chýbajúce / nesúlad verzií: {pkgs}", pkgs=', '.join(missing_log_labels)))

                CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                
                # --- KROK 1: Inštalácia samotných editable (-e) balíčkov s --no-deps ---
                if missing_editable_args:
                    dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
                    install_e_cmd = dispatcher.get("install_multiple_exact", packages=missing_editable_args)

                    proc_e = subprocess.Popen(
                        install_e_cmd, 
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.STDOUT, 
                        text=True, 
                        encoding="utf-8", 
                        errors="replace", 
                        env=env,
                        creationflags=CREATE_NO_WINDOW
                    )
                    for line in proc_e.stdout:
                        if log_callback:
                            log_callback(f"  {line.strip()}")
                    proc_e.wait()
                    if proc_e.returncode != 0:
                        AptLogic._emit(
                            AptState.FAILED,
                            log_callback=log_callback,
                            status_callback=status_callback,
                            progress_pct=100,
                            err=AptLogic._tr("apt_install_failed", "Inštalácia editable balíčka zlyhala."),
                            data={"exit_code": proc_e.returncode}
                        )
                        return False

                # --- KROK 2: Inštalácia bežných závislostí NORMÁLNE BEZ --no-deps ---
                if missing_standard_args:
                    AptLogic._emit(
                        AptState.INSTALLING,
                        log_callback=log_callback,
                        status_callback=status_callback,
                        progress_pct=25,
                        count=len(missing_standard_args),
                        pkgs=', '.join([l for l in missing_log_labels if "(-e)" not in l]),
                        data={
                            "packages_queue": missing_standard_args,
                            "labels": missing_log_labels,
                            "package_manager": getattr(core, "package_manager", "pip")
                        }
                    )
                    dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
                    install_std_cmd = dispatcher.get("install_multiple_exact", packages=missing_standard_args)

                    process = subprocess.Popen(
                        install_std_cmd, 
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.STDOUT, 
                        text=True, 
                        encoding="utf-8", 
                        errors="replace", 
                        env=env,
                        creationflags=CREATE_NO_WINDOW
                    )
                    for line in process.stdout:
                        if log_callback:
                            log_callback(f"  {line.strip()}")
                    process.wait()
                    if process.returncode != 0:
                        AptLogic._emit(
                            AptState.FAILED,
                            log_callback=log_callback,
                            status_callback=status_callback,
                            progress_pct=100,
                            err=AptLogic._tr("apt_install_failed", "Inštalácia balíčkov zlyhala. Stav JSON ostáva nezmenený."),
                            data={"exit_code": process.returncode}
                        )
                        return False

                if not missing_editable_args and not missing_standard_args:
                    if log_callback:
                        log_callback(AptLogic._tr("apt_install_all_present", "✅ [APT: STAV 2 - INSTALL] Všetky požadované balíčky a ich verzie sú v poriadku."))

                for rel_pkg in list(released_from_reqs):
                    bound_kids = AptLogic.unbind_extras_for_parent(venv_path, rel_pkg, context="requirements")
                    released_from_reqs.extend(bound_kids)

                state_data = AptLogic._load_state_data(venv_path)
                current_req_bounds = state_data.get("requirements_extras_bound", {})
                all_parents_to_check = wanted_packages | set(current_req_bounds.keys())

                for parent_pkg in all_parents_to_check:
                    if parent_pkg in wanted_packages:
                        extras_list = pamat_extras.get(parent_pkg, [])
                        new_family = AptLogic.resolve_extras_family(venv_path, parent_pkg, extras_list) if extras_list else []
                        old_family = set(current_req_bounds.get(parent_pkg, []))
                        dropped_kids = old_family - set(new_family)
                        if dropped_kids:
                            released_from_reqs.extend(dropped_kids)
                        
                        AptLogic.set_bound_extras_for_parent(venv_path, parent_pkg, new_family, context="requirements")

                        if new_family:
                            AptLogic._emit(
                                AptState.EXTRAS_SYNCING,
                                log_callback=log_callback,
                                status_callback=status_callback,
                                progress_pct=50,
                                parent=parent_pkg,
                                children=', '.join(new_family),
                                data={
                                    "parent": parent_pkg,
                                    "requested_extras": extras_list,
                                    "resolved_children": new_family,
                                    "context": "requirements"
                                }
                            )
                    else:
                        bound_kids = AptLogic.unbind_extras_for_parent(venv_path, parent_pkg, context="requirements")
                        if bound_kids:
                            released_from_reqs.extend(bound_kids)

                # =============================================================
                # --- SPRÁVA A DIFF PRE EDITOVATEĽNÉ BALÍČKY (pip -e) ---
                # =============================================================
                current_editable_bounds = AptLogic.load_editable_bounds(venv_path)
                installed_editable_in_reqs = set()

                for norm_pkg, req_line in requirements_map.items():
                    if req_line.startswith("-e "):
                        installed_editable_in_reqs.add(norm_pkg)
                        raw_path = req_line[3:].strip()
                        
                        raw_project_deps = RequirementsParser.get_project_dependencies(raw_path)
                        
                        deps = []
                        extras_bound_map = {}

                        for raw_dep in raw_project_deps:
                            # Rešpektovanie markerov v deklaráciách editovateľného projektu
                            if not RequirementsParser.is_marker_valid(raw_dep, target_env=target_env):
                                continue

                            clean_name = RequirementsParser._extract_package_name(raw_dep)
                            if clean_name:
                                norm_dep = AptLogic._normalize(clean_name)
                                if norm_dep not in system_pkgs and norm_dep != norm_pkg:
                                    deps.append(norm_dep)

                                req_exts = RequirementsParser.extract_extras(raw_dep)
                                if req_exts:
                                    family = AptLogic.resolve_extras_family(venv_path, norm_dep, req_exts)
                                    if family:
                                        extras_bound_map[norm_dep] = family

                        deps = sorted(list(set(deps)))

                        dropped_editable_deps = AptLogic.bind_editable_package(
                            venv_path=venv_path,
                            pkg_name=norm_pkg,
                            path=raw_path,
                            packages=deps,
                            extras_bound=extras_bound_map
                        )
                        if dropped_editable_deps:
                            released_from_reqs.extend(dropped_editable_deps)

                        if deps or extras_bound_map:
                            AptLogic._emit(
                                AptState.EDITABLE_SYNCING,
                                log_callback=log_callback,
                                status_callback=status_callback,
                                progress_pct=55,
                                pkg=norm_pkg,
                                children=', '.join(deps),
                                data={
                                    "package": norm_pkg,
                                    "path": raw_path,
                                    "dependencies": deps,
                                    "extras": extras_bound_map
                                }
                            )

                for old_e_pkg in list(current_editable_bounds.keys()):
                    if old_e_pkg not in installed_editable_in_reqs:
                        released_kids = AptLogic.unbind_editable_package(venv_path, old_e_pkg)
                        released_from_reqs.extend(released_kids)

                AptLogic._emit(AptState.STATE_UPDATING, status_callback=status_callback, progress_pct=65)
                state_data = AptLogic._load_state_data(venv_path)
                state_data["requirements_cache"] = sorted(list(wanted_packages))
                AptLogic._save_state_data(venv_path, state_data)

                if released_from_reqs:
                    unique_released = list(dict.fromkeys(released_from_reqs))
                    if log_callback:
                        log_callback(AptLogic._tr("apt_autoremove_removing", "🧹 [APT: STAV 4 - AUTOREMOVE] Odstraňujem balíčky: {pkgs}", pkgs=', '.join(unique_released)))
                    AptLogic.autoremove(
                        core, 
                        venv_path, 
                        log_callback=log_callback, 
                        status_callback=status_callback, 
                        released_packages=unique_released
                    )

                state_data = AptLogic._load_state_data(venv_path)
                state_data["requirements_cache"] = sorted(list(wanted_packages))
                AptLogic._save_state_data(venv_path, state_data)

                manager_type = getattr(core, "package_manager", "pip")
                
                AptLogic._emit(
                    AptState.CHECKING_INTEGRITY,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    progress_pct=85,
                    mgr=manager_type.upper(),
                    data={"package_manager": manager_type}
                )

                dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
                cmd_check = dispatcher.get("check")
                CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
                
                check_proc = subprocess.run(
                    cmd_check, 
                    capture_output=True, 
                    text=True, 
                    encoding="utf-8", 
                    errors="replace", 
                    env=env,
                    creationflags=CREATE_NO_WINDOW
                )
                
                if check_proc.returncode == 0:
                    AptLogic._emit(
                        AptState.COMPLETED_SUCCESS,
                        log_callback=log_callback,
                        status_callback=status_callback,
                        progress_pct=100,
                        data={"package_manager": manager_type}
                    )
                else:
                    out_err = (check_proc.stdout + "\n" + check_proc.stderr).strip()
                    AptLogic._emit(
                        AptState.COMPLETED_WARNING,
                        log_callback=log_callback,
                        status_callback=status_callback,
                        progress_pct=100,
                        mgr=manager_type.upper(),
                        output=out_err,
                        data={"package_manager": manager_type, "conflicts": out_err}
                    )

                return True

            except Exception as e:
                AptLogic._emit(
                    AptState.FAILED,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    progress_pct=100,
                    err=str(e),
                    data={"exception": str(e)}
                )
                return False

    # =========================================================================
    # --- AUTOREMOVE: ČISTENIE SIRÔT VÝHRADNE PODĽA JSONU (PLNE STAVOVÝ) ---
    # =========================================================================

    @staticmethod
    def autoremove(
        core, 
        venv_path: str, 
        log_callback=None, 
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None,
        released_packages=None
    ) -> bool:
        with AptLogic._get_venv_lock(venv_path):
            try:
                state_data = AptLogic._load_state_data(venv_path)
            except RuntimeError as e:
                venv_name = os.path.basename(os.path.normpath(venv_path))
                AptLogic._emit(
                    AptState.CORRUPT_STATE,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    progress_pct=100,
                    venv=venv_name
                )
                return False

            mgr_label = "UV" if getattr(core, "package_manager", "pip") == "uv" else "PIP"

            graph = AptLogic.get_dependency_graph(venv_path, core, status_callback=status_callback)
            if graph is None:
                AptLogic._emit(
                    AptState.FAILED,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    err=AptLogic._tr("apt_err_list_failed_short", "❌ [APT] Zlyhalo načítanie zoznamu balíčkov.")
                )
                return False

            if not graph:
                AptLogic._emit(
                    AptState.COMPLETED_SUCCESS,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    progress_pct=100
                )
                return True

            all_installed = set(graph.keys())
            system_roots = set(state_data.get("system_packages") or []) & all_installed

            explicit_roots = set(state_data.get("explicit", []))
            explicit_roots.update(state_data.get("requirements_cache", []))
            explicit_roots.update(AptLogic.get_all_linker_required_packages(venv_path))

            ed_bounds = AptLogic.load_editable_bounds(venv_path)
            for e_name, e_info in ed_bounds.items():
                explicit_roots.add(e_name)
                explicit_roots.update(e_info.get("packages", []))
                for c_list in e_info.get("extras_bound", {}).values():
                    explicit_roots.update(c_list)

            norm_released_all = list(dict.fromkeys(AptLogic._normalize(p) for p in (released_packages or [])))
            still_owned = AptLogic.get_all_owned_packages(venv_path)
            kept_owned = [p for p in norm_released_all if p in still_owned]
            norm_released = [p for p in norm_released_all if p not in still_owned]
            if kept_owned and log_callback:
                log_callback(AptLogic._tr("apt_autoremove_kept_owned", "🛡️ [APT] Ponechávam (má ďalšieho vlastníka): {pkgs}", pkgs=', '.join(kept_owned)))
            explicit_roots.difference_update(norm_released)

            editable_pkgs = AptLogic.get_editable_packages(venv_path, core.package_manager)
            for e_pkg in editable_pkgs:
                e_name = AptLogic._normalize(e_pkg.get("name", ""))
                if e_name and e_name not in norm_released:
                    explicit_roots.add(e_name)

            AptLogic._emit(AptState.ORPHANS_CALCULATING, status_callback=status_callback, progress_pct=70)

            def get_all_required(roots):
                required = set()
                queue = list(roots)
                while queue:
                    current = queue.pop(0)
                    for dep in graph.get(current, []):
                        if dep not in required and dep in graph:
                            required.add(dep)
                            queue.append(dep)
                return required

            auto_needed = get_all_required(explicit_roots | system_roots)
            released_tree = get_all_required(norm_released)
            released_tree.update(norm_released)

            state_explicit = set(state_data.get("explicit", []))
            new_manual_found = False
            for pkg in all_installed:
                if pkg not in explicit_roots and pkg not in auto_needed and pkg not in system_roots:
                    if pkg in released_tree:
                        continue
                    explicit_roots.add(pkg)
                    state_explicit.add(pkg)
                    new_manual_found = True

            if new_manual_found:
                AptLogic.save_explicit_list(venv_path, state_explicit)
                auto_needed = get_all_required(explicit_roots | system_roots)

            orphans = all_installed - explicit_roots - auto_needed - system_roots

            if not orphans:
                if log_callback:
                    log_callback(AptLogic._tr("apt_clean_no_orphans", "✅ [APT] Systém je čistý. Žiadne osirelé balíčky."))
                return True

            AptLogic._emit(
                AptState.REMOVING_ORPHANS,
                log_callback=log_callback,
                status_callback=status_callback,
                progress_pct=75,
                mgr=mgr_label,
                pkgs=', '.join(orphans),
                data={"orphans": sorted(list(orphans)), "manager": mgr_label}
            )

            dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            uninstall_args = dispatcher.get("uninstall_multiple", packages=list(orphans))

            try:
                process = subprocess.Popen(
                    uninstall_args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=CREATE_NO_WINDOW
                )

                for line in process.stdout:
                    if log_callback:
                        log_callback(f"  {line.strip()}")

                process.wait()

                if process.returncode != 0:
                    AptLogic._emit(
                        AptState.FAILED,
                        log_callback=log_callback,
                        status_callback=status_callback,
                        err=AptLogic._tr("apt_uninstall_failed", "❌ [APT] Odinštalácia balíčkov zlyhala."),
                        data={"exit_code": process.returncode}
                    )
                    return False

                return True

            except Exception as e:
                AptLogic._emit(
                    AptState.FAILED,
                    log_callback=log_callback,
                    status_callback=status_callback,
                    err=str(e),
                    data={"exception": str(e)}
                )
                return False
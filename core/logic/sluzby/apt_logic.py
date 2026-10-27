#----------------------------------------
# Súbor: core/logic/sluzby/apt_logic.py
#----------------------------------------

import os
import json
import re
import subprocess
import threading
from core._path import Paths
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.language_manager import LanguageManager
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.uv_detector import UVDetector
from contextlib import contextmanager


class AptLogic:
    """
    Centrálny systém správy závislostí aplikácie VenvHub Pro inšpirovaný Linuxovým balíčkovacím systémom APT.

    ARCHITEKTÚRA – JEDINÝ ZDROJ PRAVDY (Single Source of Truth):
    Jediným zdrojom pravdy pre skutočný stav nainštalovaných a požadovaných balíčkov 
    je súbor 'venvhub_apt_state.json' uložený priamo v 'site-packages' daného venvu.
    Deklaratívnou modlou projektu je súbor 'requirements.txt'.

    MODEL EVIDENCIE (3 zdroje vlastníctva + 3 vrstvy mäkkých väzieb = 5 kľúčov v JSON,
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

    PRAVIDLO VLASTNÍCTVA:
    Balíček na disku existuje fyzicky iba raz, ale môže mať viacero vlastníkov (referencií).
    Zmazať sa môže až vtedy, keď ho neuvoľní ANI JEDEN z troch zdrojov:
    používateľ (explicit), projekt (requirements) a vývojový modul (linker).
    Jediná funkcia, ktorá o vlastníctve rozhoduje pri čistení, je 'get_all_owned_packages()':
    'autoremove' z uvoľnených balíčkov vždy vyradí tie, ktoré majú ešte aspoň jedného vlastníka.
    """

    # Základné nástroje Pythonu, ktoré systém nikdy nesmie označiť ako siroty na zmazanie
    CORE_TOOLS = {"pip", "setuptools", "wheel", "virtualenv", "uv"}

    # Medzivláknové zámky pre bezpečný paralelný prístup k súborom konkrétneho venvu
    _locks_guard = threading.Lock()
    _venv_locks = {}

    @staticmethod
    def _tr(key: str, default: str, *args, **kwargs) -> str:
        """
        Pomocná metóda na bezpečné získanie preloženého textu cez LanguageManager.
        
        Args:
            key (str): Kľúč textu v lokalizačnom JSON súbore.
            default (str): Predvolený text, ak kľúč neexistuje alebo preklad zlyhá.
            *args, **kwargs: Parametre pre formátovanie reťazca (napr. {0}, {pkg}).

        Returns:
            str: Výsledný sformátovaný text.
        """
        try:
            val = LanguageManager.get(key, default)
            if not val or val == key:
                val = default
        except TypeError:
            try:
                val = LanguageManager.get(key)
                if not val or val == key:
                    val = default
            except Exception:
                val = default
        except Exception:
            val = default

        if args or kwargs:
            try:
                return val.format(*args, **kwargs)
            except Exception:
                pass
        return val

    @staticmethod
    @contextmanager
    def _get_venv_lock(venv_path: str):
        """
        Kontextový manažér na zabezpečenie výhradného (Thread-Safe) prístupu 
        k súborom daného virtuálneho prostredia (venvhub_apt_state.json).
        
        Args:
            venv_path (str): Absolútna cesta k priečinku virtuálneho prostredia.
        """
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
    def _extract_package_name(token: str) -> str:
        """
        Vytiahne čistý identifikátor balíčka zo zadaného reťazca bez porovnávacích operátorov.
        
        Args:
            token (str): Vstupný text (napr. 'requests>=2.25.1').

        Returns:
            str: Čistý názov (napr. 'requests').
        """
        token = token.strip()
        match = re.match(r"^[A-Za-z0-9_.\-]+", token)
        return match.group(0) if match else token

    @staticmethod
    def _normalize(name: str) -> str:
        """
        Znormalizuje názov balíčka podľa špecifikácie PEP 503 (malé písmená, pomlčky namiesto podčiarkovníkov a bodiek).
        
        Args:
            name (str): Ľubovoľný zápis názvu balíčka (napr. 'PySide6_QtAds', 'flask.cors').

        Returns:
            str: Normalizovaný názov (napr. 'pyside6-qtads', 'flask-cors').
        """
        return re.sub(r"[-_.]+", "-", name.strip().lower())

    @staticmethod
    def _get_site_packages_dir(venv_path: str) -> str:
        """
        Zistí presnú cestu k priečinku 'site-packages' vo vnútri venvu (ošetruje Windows aj Linux).
        
        Args:
            venv_path (str): Absolútna cesta k virtuálnemu prostrediu.

        Returns:
            str: Absolútna cesta k priečinku site-packages.
        """
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
        """
        Vráti absolútnu cestu k stavovému súboru venvhub_apt_state.json.
        """
        return os.path.join(AptLogic._get_site_packages_dir(venv_path), "venvhub_apt_state.json")

    @staticmethod
    def _load_state_data(venv_path: str) -> dict:
        """
        Načíta stavový JSON z disku. Ak súbor neexistuje alebo je poškodený,
        vráti novú inicializovanú štruktúru s 5 definovanými stavmi.

        Returns:
            dict: Štruktúra so stavmi explicit, explicit_extras_bound, requirements_cache, 
                  requirements_extras_bound a linker_packages_bound.
        """
        state_file = AptLogic._get_state_file(venv_path)
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("explicit", [])
                        data.setdefault("explicit_extras_bound", {})
                        data.setdefault("requirements_cache", [])
                        data.setdefault("requirements_extras_bound", {})
                        data.setdefault("linker_packages_bound", {})
                        data.setdefault("system_packages", None)
                        return data
            except Exception:
                pass
        return {
            "explicit": [], 
            "explicit_extras_bound": {},
            "requirements_cache": [], 
            "requirements_extras_bound": {},
            "linker_packages_bound": {},
            "system_packages": None
        }

    @staticmethod
    def _save_state_data(venv_path: str, data: dict) -> bool:
        """
        Uloží 5 stavov v presnom poradí do súboru venvhub_apt_state.json.
        """
        state_file = AptLogic._get_state_file(venv_path)
        try:
            ordered_data = {
                "system_packages": data.get("system_packages"),
                "explicit": data.get("explicit", []),
                "explicit_extras_bound": data.get("explicit_extras_bound", {}),
                "requirements_cache": data.get("requirements_cache", []),
                "requirements_extras_bound": data.get("requirements_extras_bound", {}),
                "linker_packages_bound": data.get("linker_packages_bound", {})
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
    def verify_uninstall_safety(venv_path: str, core, pkg_name: str) -> tuple[bool, str]:
        """
        ŽIVÁ KONTROLA BEZPEČNOSTI pred povolením odinštalácie balíčka.
        
        Vykonáva 3 nezávislé ochranné kontroly:
        1. Reverzné závislosti: Či balíček nie je tvrdou závislosťou iného nainštalovaného balíčka.
        2. requirements.txt: Či balíček nepatrí do modly projektu (alebo k jeho viazaným extras).
        3. Linker (5. stav): Či balíček nie je vyžadovaný pripojeným lokálnym vývojovým modulom.

        Args:
            venv_path (str): Cesta k venvu.
            core: Inštancia ProjectCore.
            pkg_name (str): Názov balíčka, ktorý chce používateľ odinštalovať.

        Returns:
            tuple[bool, str]: (True, "") ak je odinštalovanie bezpečné, 
                              (False, "chybová správa") ak by odinštalovanie rozbilo systém.
        """
        norm_pkg = AptLogic._normalize(pkg_name)
        
        # Ochrana č. 0: SYSTÉMOVÝ BALÍČEK venvu (pip, setuptools, wheel, packaging, ...)
        if AptLogic.is_system_package(venv_path, norm_pkg):
            msg = AptLogic._tr(
                "apt_err_cannot_uninstall_system",
                "🛑 OCHRANA: Balíček '{0}' je systémový balíček prostredia (vznikol pri vytvorení venvu) a nedá sa odinštalovať.",
                norm_pkg
            )
            return False, msg

        # Ochrana č. 1: Reverzné závislosti (Rozlišujeme Hard a Soft)
        # Linker sa tu zámerne nezapočítava - rieši ho samostatne ochrana č. 3 s presným hlásením.
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
            return False, msg

        # Ochrana č. 2: SVÄTÉ PÍSMO (requirements.txt + jeho viazané extras)
        try:
            project_path = Paths.get_project_path(core.projects_root, core.active_project)
            req_file = Paths.get_requirements_txt_path(project_path)
            
            if os.path.exists(req_file):
                raw_parsed = RequirementsParser.parse(req_file, pip_e_root=core.pip_e_packages_root)
                parsed_reqs = {AptLogic._normalize(p) for p in raw_parsed}
                
                # A) Ak je balík priamo v requirements.txt
                if norm_pkg in parsed_reqs:
                    msg = AptLogic._tr(
                        "apt_err_cannot_uninstall_reqs", 
                        "🛑 OCHRANA: Balíček '{0}' je definovaný v 'requirements.txt'!\n\nMusíte ho najprv vymazať (alebo zakomentovať) v tomto súbore, inak by ste rozbili definíciu prostredia.", 
                        norm_pkg
                    )
                    return False, msg

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
                        return False, msg

        except Exception:
            pass

        # Ochrana č. 3: 5. STAV - LOKÁLNY LINKER
        linker_parents = AptLogic.get_linker_modules_for_package(venv_path, norm_pkg)
        if linker_parents:
            msg = AptLogic._tr(
                "apt_err_cannot_uninstall_linker",
                "🛑 OCHRANA: Balíček '{0}' je vyžadovaný pripojeným lokálnym modulom: {1}!\n\nAk ho chcete odstrániť, najprv odlinkujte daný modul v okne Lokálne balíčky.",
                norm_pkg, ", ".join(linker_parents)
            )
            return False, msg

        return True, ""

    @staticmethod
    def scrub_package_completely(venv_path: str, pkg_name: str) -> list[str]:
        """
        Vyhladí balíček zo všetkých evidovaných stavov v JSON súbore po jeho fyzickom odinštalovaní.
        Uvoľní všetky jeho viazané extras a vráti ich zoznam pre následný autoremove.

        Args:
            venv_path (str): Cesta k venvu.
            pkg_name (str): Názov odinštalovaného balíčka.

        Returns:
            list[str]: Zoznam názvov uvoľnených pod-balíčkov (detí).
        """
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

            # Vyčistenie aj z 5. stavu (Linker)
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

            if modified:
                AptLogic._save_state_data(venv_path, data)
                
        return list(released_kids)

    # =========================================================================
    # --- LINUX APT LOGIC: KONTROLA PRED INŠTALÁCIOU (STAV 1:1) ---
    # =========================================================================

    @staticmethod
    def check_install_necessity(venv_path: str, core, installed_items: list[tuple[str, list[str]]], log_callback=None) -> tuple[bool, str]:
        """
        KONTROLA PRED INŠTALÁCIOU (STAV 1:1 a OCHRANA PRED DUPLICITAMI).
        Overuje, či požadovaný balíček už nie je plne prítomný a zadeklarovaný v requirements.txt.
        Ak je stav 1:1 zhodný, inštalácia sa úplne preskočí, čím sa šetrí čas a disk.

        Args:
            venv_path (str): Cesta k venvu.
            core: Inštancia ProjectCore.
            installed_items: Zoznam n-tíc [(názov_balíčka, [požadované_extras])].
            log_callback: Voliteľná funkcia na logovanie správ.

        Returns:
            tuple[bool, str]: (True, správa) ak sa inštalácia môže preskočiť, 
                              (False, "") ak sa inštalácia musí vykonať.
        """
        from PyQt6.QtWidgets import QApplication

        def _log(text):
            if log_callback:
                log_callback(text)
                QApplication.processEvents()

        with AptLogic._get_venv_lock(venv_path):
            _log(AptLogic._tr("apt_check_reading_reqs", "  📄 Čítam evidenciu požiadaviek (requirements.txt)..."))
            state_data = AptLogic._load_state_data(venv_path)
            req_cache = set(state_data.get("requirements_cache", []))
            req_bounds = state_data.get("requirements_extras_bound", {})
            
            site_pkgs = AptLogic._get_site_packages_dir(venv_path)
            installed_on_disk = set()
            if os.path.exists(site_pkgs):
                try:
                    for entry in os.listdir(site_pkgs):
                        if entry.lower().endswith(".dist-info"):
                            installed_on_disk.add(AptLogic._normalize(entry.split("-")[0]))
                except Exception:
                    pass

            all_skipped = True
            skip_messages = []

            for pkg_name, requested_extras in installed_items:
                norm_pkg = AptLogic._normalize(pkg_name)
                is_in_reqs = norm_pkg in req_cache
                is_installed = norm_pkg in installed_on_disk

                # Zistíme, či balíček nie je naviazaný ako extra k niektorému balíku z requirements
                req_parent_extra = None
                if not is_in_reqs:
                    for parent, kids in req_bounds.items():
                        if norm_pkg in kids:
                            req_parent_extra = parent
                            break

                _log(AptLogic._tr("apt_check_analyzing_pkg", "  🔬 Analyzujem stav balíčka '{pkg}'...", pkg=norm_pkg))

                if is_in_reqs and is_installed:
                    covered_kids = set(req_bounds.get(norm_pkg, []))
                    extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm_pkg)
                    
                    uncovered_kids = []
                    for extra in requested_extras:
                        for kid in extras_map.get(AptLogic._normalize(extra), []):
                            if kid not in covered_kids or kid not in installed_on_disk:
                                uncovered_kids.append(kid)

                    if not uncovered_kids:
                        extras_str = f"[{','.join(requested_extras)}]" if requested_extras else ""
                        msg = AptLogic._tr(
                            "apt_install_already_1to1",
                            "ℹ️ Balíček '{0}{1}' je už definovaný v requirements.txt a nainštalovaný. Inštalácia nie je potrebná.",
                            norm_pkg, extras_str
                        )
                        skip_messages.append(msg)
                    else:
                        all_skipped = False
                elif req_parent_extra and is_installed and not requested_extras:
                    msg = AptLogic._tr(
                        "apt_install_already_in_req_extras",
                        "ℹ️ Balíček '{0}' je už zabezpečený cez requirements.txt (ako extra pre '{1}') a nainštalovaný. Inštalácia nie je potrebná.",
                        norm_pkg, req_parent_extra
                    )
                    skip_messages.append(msg)
                else:
                    all_skipped = False

            if all_skipped and installed_items:
                return True, "\n".join(skip_messages)

            return False, ""

    # =========================================================================
    # --- STAV 1: EXPLICIT ---
    # =========================================================================

    @staticmethod
    def load_explicit_list(venv_path: str) -> set:
        """
        Načíta zoznam manuálne nainštalovaných balíčkov (stav 'explicit').
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return set(data.get("explicit", []))

    @staticmethod
    def save_explicit_list(venv_path: str, explicit_set: set):
        """
        Uloží množinu manuálne nainštalovaných balíčkov do stavu 'explicit'.
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            data["explicit"] = sorted(list(explicit_set))
            AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def is_in_requirements(venv_path: str, pkg_name: str, state_data: dict = None) -> bool:
        """
        Zistí, či je balíček zadeklarovaný v requirements.txt (priamo v cache alebo ako dieťa v extras).
        """
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
        """
        Označí balíček ako explicitný (používateľský).
        ZÁKAZ DUPLICITY: Ak je balíček už v requirements.txt (priamo alebo cez extras), do explicit nejde!
        """
        with AptLogic._get_venv_lock(venv_path):
            norm_pkg = AptLogic._normalize(package_name)
            data = AptLogic._load_state_data(venv_path)

            # SVÄTÉ PÍSMO: Ak je v requirements.txt (priamo alebo ako extra väzba), do explicit nesmie ísť
            if AptLogic.is_in_requirements(venv_path, norm_pkg, state_data=data):
                return

            # Systémové balíčky (základ venvu) majú vlastnú ochranu - do explicit nepatria.
            if norm_pkg in set(data.get("system_packages") or []) or norm_pkg in AptLogic.CORE_TOOLS:
                return

            explicit = AptLogic.load_explicit_list(venv_path)
            explicit.add(norm_pkg)
            AptLogic.save_explicit_list(venv_path, explicit)

    # =========================================================================
    # --- STAVY 3 & 4: EXTRAS BOUND (MANUÁLNE A CEZ REQUIREMENTS) ---
    # =========================================================================

    @staticmethod
    def load_extras_bound(venv_path: str, context: str = "all") -> dict[str, list[str]]:
        """
        Načíta mapovanie viazaných extras závislostí.
        
        Args:
            context (str): 'explicit' pre manuálne, 'requirements' pre súbor požiadaviek,
                           alebo 'all' pre zlúčený pohľad.
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            if context == "explicit":
                return data.get("explicit_extras_bound", {})
            elif context == "requirements":
                return data.get("requirements_extras_bound", {})
            elif context == "linker":
                return {p: sorted(k) for p, k in AptLogic._merge_linker_extras(data).items()}
            else:
                merged = {}
                for k in ["explicit_extras_bound", "requirements_extras_bound"]:
                    for parent, kids in data.get(k, {}).items():
                        merged.setdefault(parent, set()).update(kids)
                for parent, kids in AptLogic._merge_linker_extras(data).items():
                    merged.setdefault(parent, set()).update(kids)
                return {p: sorted(list(k)) for p, k in merged.items()}

    @staticmethod
    def _merge_linker_extras(data: dict) -> dict[str, set]:
        """
        Zlúči 'extras_bound' všetkých linker modulov do jednej mapy rodič -> {deti}.
        (Čistá funkcia nad už načítaným stavom, zámok nie je potrebný.)
        """
        merged: dict[str, set] = {}
        for mod_info in data.get("linker_packages_bound", {}).values():
            for parent, kids in mod_info.get("extras_bound", {}).items():
                merged.setdefault(parent, set()).update(kids)
        return merged

    @staticmethod
    def bind_extras(venv_path: str, parent_pkg: str, child_pkgs: list[str], context: str = "explicit"):
        """
        Naviaže balíčky nainštalované cez extras k ich rodičovskému balíčku.
        """
        norm_parent = AptLogic._normalize(parent_pkg)
        if not child_pkgs or norm_parent in AptLogic.CORE_TOOLS:
            return

        target_key = "explicit_extras_bound" if context == "explicit" else "requirements_extras_bound"

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.setdefault(target_key, {})
            explicit_set = set(data.get("explicit", []))

            other_key = "requirements_extras_bound" if context == "explicit" else "explicit_extras_bound"
            other_bounds = set(data.get(other_key, {}).get(norm_parent, []))

            current_children = set(bounds.get(norm_parent, []))
            for child in child_pkgs:
                norm_child = AptLogic._normalize(child)
                if norm_child in AptLogic.CORE_TOOLS or norm_child == norm_parent:
                    continue
                current_children.add(norm_child)

            if current_children:
                bounds[norm_parent] = sorted(list(current_children))
            AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def unbind_extras_for_parent(venv_path: str, parent_pkg: str, context: str = "explicit") -> list[str]:
        """
        Odstráni väzbu extras pre daného rodiča a vráti zoznam uvoľnených detí.
        """
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
        """
        Povýši balíček, ktorý bol pôvodne len viazaným extra dieťaťom v explicitných väzbách.
        Na 'requirements_extras_bound' nikdy nesiaha (sväté písmo projektu).
        """
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
        """
        Vráti všetky deti viazané k danému rodičovskému balíčku naprieč všetkými kontextami.
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            norm_parent = AptLogic._normalize(parent_pkg)
            
            kids = set(data.get("explicit_extras_bound", {}).get(norm_parent, []))
            kids.update(data.get("requirements_extras_bound", {}).get(norm_parent, []))
            kids.update(AptLogic._merge_linker_extras(data).get(norm_parent, set()))
            
            return sorted(list(kids))

    @staticmethod
    def set_bound_extras_for_parent(venv_path: str, parent_pkg: str, child_pkgs: list[str], context: str = "requirements"):
        """
        Nastaví presný zoznam naviazaných extras pre daného rodiča v určenom kontexte.
        Ak je zoznam prázdny, väzba rodiča sa úplne odstráni zo stavu JSON.
        """
        norm_parent = AptLogic._normalize(parent_pkg)
        target_key = "explicit_extras_bound" if context == "explicit" else "requirements_extras_bound"

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            bounds = data.setdefault(target_key, {})
            explicit_set = set(data.get("explicit", []))

            other_key = "requirements_extras_bound" if context == "explicit" else "explicit_extras_bound"
            other_bounds = set(data.get(other_key, {}).get(norm_parent, []))

            filtered = set()
            for child in child_pkgs:
                norm_child = AptLogic._normalize(child)
                if norm_child in AptLogic.CORE_TOOLS or norm_child == norm_parent:
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
        """
        Načíta kompletný stav väzieb pre lokálny linker z 5. stavu venvhub_apt_state.json.

        Returns:
            dict: { "Názov_Modulu": { "packages": [...], "extras_bound": { "parent": [...] } } }
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return data.get("linker_packages_bound", {})

    @staticmethod
    def _clean_linker_entry(packages, extras_bound=None) -> dict:
        """
        Znormalizuje záznam jedného linker modulu do tvaru
        { "packages": [...], "extras_bound": { "rodič": [...] } } (bez CORE_TOOLS a bez prázdnych mien).
        """
        clean_pkgs = sorted({
            n for n in (AptLogic._normalize(p) for p in (packages or []))
            if n and n not in AptLogic.CORE_TOOLS
        })
        clean_extras = {}
        for p_pkg, c_list in (extras_bound or {}).items():
            p_norm = AptLogic._normalize(p_pkg)
            if not p_norm or p_norm in AptLogic.CORE_TOOLS:
                continue
            valid_children = sorted({
                n for n in (AptLogic._normalize(c) for c in (c_list or []))
                if n and n not in AptLogic.CORE_TOOLS and n != p_norm
            })
            if valid_children:
                clean_extras[p_norm] = valid_children
        return {"packages": clean_pkgs, "extras_bound": clean_extras}

    @staticmethod
    def _linker_entry_packages(entry: dict) -> set:
        """Plochá množina všetkých balíčkov (základné + extras deti), ktoré si nárokuje jeden modul."""
        result = set(entry.get("packages", []))
        for c_list in entry.get("extras_bound", {}).values():
            result.update(c_list)
        return result

    @staticmethod
    def _linker_union(bounds: dict) -> set:
        """Plochá množina všetkých balíčkov, ktoré si nárokujú všetky moduly v danej mape dokopy."""
        result = set()
        for entry in bounds.values():
            result.update(AptLogic._linker_entry_packages(entry))
        return result

    @staticmethod
    def bind_linker_module(venv_path: str, module_name: str, packages: list[str], extras_bound: dict[str, list[str]] = None) -> list[str]:
        """
        Deklaratívne zapíše pod konkrétny vývojový modul jeho balíčky a viazané extras.

        IZOLÁCIA STAVOV:
        Nešahá na 'explicit' ani na 'requirements_cache'. Každý stav si striktne drží svoje vlastné referencie.

        Returns:
            list[str]: Balíčky, ktoré tento modul predtým držal a po prepise už nedrží
                       (kandidáti na uvoľnenie; či sa naozaj zmažú, rozhodne 'autoremove' podľa vlastníctva).
        """
        norm_mod = module_name.strip()
        if not norm_mod:
            return []

        new_entry = AptLogic._clean_linker_entry(packages, extras_bound)

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
        """
        Atomicky nahradí CELÝ 5. stav ('linker_packages_bound') požadovanou množinou modulov.

        Args:
            modules: { "Názov_Modulu": {"packages": [...], "extras_bound": {"rodič": [...]}} }
                     Musí obsahovať VŠETKY aktuálne pripojené moduly (aj tranzitívne cez requires_local).

        Returns:
            list[str]: Balíčky, ktoré linker predtým držal a teraz už nedrží ani jeden modul
                       (rozdiel zjednotení starý − nový). Pokrýva odpojené moduly aj zmenu
                       'requires_pip' / extras pri moduloch, ktoré zostali pripojené.

        Raises:
            RuntimeError: Ak sa stav nepodarilo zapísať na disk.
        """
        new_bounds = {}
        for mod_name, info in (modules or {}).items():
            norm_mod = str(mod_name).strip()
            if not norm_mod:
                continue
            info = info or {}
            new_bounds[norm_mod] = AptLogic._clean_linker_entry(info.get("packages", []), info.get("extras_bound", {}))

        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            old_union = AptLogic._linker_union(data.get("linker_packages_bound", {}))
            new_union = AptLogic._linker_union(new_bounds)
            data["linker_packages_bound"] = new_bounds
            if not AptLogic._save_state_data(venv_path, data):
                raise RuntimeError(AptLogic._tr("apt_err_state_save_failed", "Zápis venvhub_apt_state.json zlyhal."))
        return sorted(old_union - new_union)

    @staticmethod
    def get_all_owned_packages(venv_path: str) -> set[str]:
        """
        JEDINÁ FUNKCIA VLASTNÍCTVA: množina všetkých balíčkov, ktoré má aktuálne aspoň jeden vlastník
        - explicit, requirements_cache, ich viazané extras deti a všetko z linker modulov.
        'autoremove' ňou filtruje uvoľnené balíčky, aby nezmazal nič, čo ešte niekto drží.
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            owned = set(data.get("explicit", [])) | set(data.get("requirements_cache", []))
            owned.update(data.get("system_packages") or [])
            for key in ("explicit_extras_bound", "requirements_extras_bound"):
                for kids in data.get(key, {}).values():
                    owned.update(kids)
            owned.update(AptLogic._linker_union(data.get("linker_packages_bound", {})))
        return owned

    @staticmethod
    def unbind_linker_module(venv_path: str, module_name: str) -> list[str]:
        """
        Odstráni lokálny vývojový modul z 5. stavu a vráti zoznam VŠETKÝCH uvoľnených balíčkov
        (základné balíčky + viazané extras deti) na následnú kontrolu v autoremove.

        Args:
            venv_path (str): Cesta k venvu.
            module_name (str): Názov odlinkovaného modulu.

        Returns:
            list[str]: Zoznam balíčkov, ktoré modul uvoľnil.
        """
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
        """
        Vráti plochú zjednotenú množinu VŠETKÝCH balíčkov (základné balíčky aj extras),
        ktoré si nárokujú všetky momentálne aktívne pripojené Linker moduly dohromady.
        Túto množinu využíva 'autoremove()' ako chránené korene (roots).
        """
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
        """
        Zistí, ktoré konkrétne lokálne moduly v Linkeri si nárokujú daný balíček.
        Využíva sa pri hlásení bezpečnostnej ochrany v 'verify_uninstall_safety()'.

        Args:
            venv_path (str): Cesta k venvu.
            pkg_name (str): Názov kontrolovaného balíčka.

        Returns:
            list[str]: Zoznam názvov modulov, ktoré balíček vyžadujú.
        """
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
    # --- SYSTÉMOVÉ BALÍČKY VENVU (snímka stavu po vytvorení prostredia) ---
    # =========================================================================

    @staticmethod
    def _scan_installed_dist_names(venv_path: str) -> set:
        """Normalizované názvy všetkých balíčkov, ktoré majú v site-packages priečinok *.dist-info."""
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
        """
        Zapíše do stavu ('system_packages') všetko, čo je v čerstvo vytvorenom venve nainštalované.
        Volá sa JEDNOU po dokončení vytvárania venvu (vrátane doinštalovania setuptools/wheel),
        takže zachytí skutočný stav na disku (pip, setuptools, wheel aj ich závislosť packaging),
        nie pevný zoznam. Platí rovnako pre štandardný venv aj pre predpripravený embed.

        Systémové balíčky sa nikdy nemažú (ani autoremove, ani GUI) a ich závislosti sú chránené.

        Returns:
            list[str]: Zapísaný zoznam (prázdny, ak v site-packages zatiaľ nič nie je a nič sa nezapísalo).

        Raises:
            RuntimeError: Ak sa stav nepodarilo zapísať.
        """
        names = sorted(AptLogic._scan_installed_dist_names(venv_path))
        if not names:
            return []
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            data["system_packages"] = names
            if not AptLogic._save_state_data(venv_path, data):
                raise RuntimeError("Zápis venvhub_apt_state.json zlyhal.")
        return names

    @staticmethod
    def _estimate_system_packages(venv_path: str) -> list[str]:
        """
        ODHAD pre staré venvy bez snímky: nainštalované CORE_TOOLS + ich tranzitívne nainštalované závislosti.
        """
        installed = AptLogic._scan_installed_dist_names(venv_path)
        queue = [p for p in AptLogic.CORE_TOOLS if p in installed]
        found = set()
        while queue:
            current = queue.pop(0)
            if current in found:
                continue
            found.add(current)
            for dep in AptLogic._get_all_requires_from_metadata(venv_path, current):
                if dep in installed and dep not in found:
                    queue.append(dep)
        return sorted(found)

    @staticmethod
    def ensure_system_packages(venv_path: str) -> set[str]:
        """
        Vráti množinu systémových balíčkov venvu. Ak stav ešte nemá snímku ('system_packages' = null),
        jednorazovo ju odhadne (pozri _estimate_system_packages) a uloží. Nikdy nevracia menej než CORE_TOOLS.
        """
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            pkgs = data.get("system_packages")
            if pkgs is None:
                pkgs = AptLogic._estimate_system_packages(venv_path)
                if pkgs:
                    data["system_packages"] = pkgs
                    AptLogic._save_state_data(venv_path, data)
            return set(pkgs or []) | set(AptLogic.CORE_TOOLS)

    @staticmethod
    def is_system_package(venv_path: str, pkg_name: str) -> bool:
        """True, ak je balíček systémový (zo snímky venvu alebo CORE_TOOLS)."""
        return AptLogic._normalize(pkg_name) in AptLogic.ensure_system_packages(venv_path)

    # =========================================================================
    # --- ČÍTANIE METADATA Z DISKU A RESOLVE EXTRAS ---
    # =========================================================================

    @staticmethod
    def resolve_extras_family(venv_path: str, parent_pkg: str, requested_extras: list[str]) -> list[str]:
        """
        Rekurzívne prejde METADATA nainštalovaného balíčka a vyhľadá celý strom závislostí,
        ktoré prinášajú zadané extras (napr. 'requests' + ['socks'] -> 'pysocks').

        Args:
            venv_path (str): Cesta k venvu.
            parent_pkg (str): Rodičovský balíček.
            requested_extras (list[str]): Zoznam požadovaných extras (napr. ['socks']).

        Returns:
            list[str]: Zoznam reálnych balíčkov prislúchajúcich k zadaným extras.
        """
        norm_parent = AptLogic._normalize(parent_pkg)
        if not requested_extras or norm_parent in AptLogic.CORE_TOOLS:
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
            if current in visited or current in AptLogic.CORE_TOOLS:
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
    def resolve_and_bind_extras(venv_path: str, parent_pkg: str, requested_extras: list[str], context: str = "explicit"):
        """
        Vyrieši strom závislostí pre zadané extras a rovno ho naviaže k rodičovskému balíčku.
        """
        all_family = AptLogic.resolve_extras_family(venv_path, parent_pkg, requested_extras)
        if all_family:
            AptLogic.bind_extras(venv_path, parent_pkg, all_family, context=context)

    @staticmethod
    def get_extras_map_from_metadata(venv_path: str, pkg_name: str) -> dict[str, list[str]]:
        """
        Prečíta súbor METADATA daného balíčka v 'site-packages' a vytiahne z neho mapovanie
        jednotlivých extras k ich priamym závislostiam.

        Returns:
            dict: { "socks": ["pysocks"], "security": ["cryptography", "pyopenssl"] }
        """
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
    def _get_all_requires_from_metadata(venv_path: str, pkg_name: str) -> list[str]:
        """
        Vráti všetky priame tvrdé závislosti balíčka zo súboru METADATA na disku
        zlúčené s jeho viazanými extras deťmi zo stavového JSONu.
        """
        reqs = set()
        norm_target = AptLogic._normalize(pkg_name)
        site_pkgs = AptLogic._get_site_packages_dir(venv_path)

        if not os.path.exists(site_pkgs):
            return []

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
                                        if "extra ==" not in val:
                                            dep_raw = val.split(";")[0].strip()
                                            clean_dep = AptLogic._extract_package_name(dep_raw)
                                            if clean_dep:
                                                reqs.add(AptLogic._normalize(clean_dep))
        except Exception:
            pass

        bound_children = AptLogic.get_bound_children(venv_path, norm_target)
        for child in bound_children:
            reqs.add(child)

        return list(reqs)

    @staticmethod
    def is_subpackage_or_managed(venv_path: str, core, pkg_name: str) -> bool:
        """
        Zistí, či je balíček pod-závislosťou iného balíčka, alebo je spravovaný 
        cez requirements.txt či Linker.
        """
        norm_pkg = AptLogic._normalize(pkg_name)
        state_data = AptLogic._load_state_data(venv_path)
        
        if norm_pkg in set(state_data.get("requirements_cache", [])):
            return True

        for key in ["explicit_extras_bound", "requirements_extras_bound"]:
            bounds = state_data.get(key, {})
            for parent, children in bounds.items():
                if norm_pkg in children:
                    return True

        # Kontrola cez 5. stav (Linker)
        if norm_pkg in AptLogic.get_all_linker_required_packages(venv_path):
            return True

        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for parent_pkg, deps in graph.items():
                if norm_pkg in deps:
                    return True

        return False

    @staticmethod
    def get_editable_packages(venv_path: str, manager_type: str = "pip"):
        """
        Získa zoznam editovateľných balíčkov (inštalovaných cez 'pip install -e').
        """
        python_exe = Paths.get_venv_python_exe_path(venv_path)
        if not os.path.exists(python_exe):
            return []

        if manager_type == "uv":
            uv_exe = UVDetector.get_uv_path() or "uv"
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
        """
        Zistí, či daný balíček vyžadujú iné balíčky v prostredí alebo pripojené Linker moduly.
        """
        pkg_norm = AptLogic._normalize(package_name)
        dependents = []

        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for other_pkg, requirements in graph.items():
                if other_pkg == pkg_norm:
                    continue
                if pkg_norm in requirements:
                    dependents.append(other_pkg)

        # Kontrola Linker modulov priamo z 5. stavu (voliteľná - verify_uninstall_safety ju rieši samostatne)
        if include_linker:
            linker_modules = AptLogic.get_linker_modules_for_package(venv_path, pkg_norm)
            for mod in linker_modules:
                display_name = LanguageManager.get("apt_linker_module_tag", "{mod} (Linker)", mod=mod)
                if display_name not in dependents:
                    dependents.append(display_name)

        return dependents

    @staticmethod
    def get_requires_for_package(venv_path, pkg_name, manager_type="pip"):
        """
        Zistí zoznam priamych závislostí balíčka cez príkaz 'show' aj priamo z METADATA.
        """
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
    def get_dependency_graph(venv_path: str, core):
        """
        Zostaví kompletný graf závislostí celého prostredia: { 'balíček': ['jeho_závislosť_1', ...] }.
        Dávkuje požiadavky po 30 balíčkoch pre bleskovú rýchlosť a nízku záťaž systému.
        """
        with AptLogic._get_venv_lock(venv_path):
            dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            graph = {}

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

                            meta_reqs = AptLogic._get_all_requires_from_metadata(venv_path, current_pkg)
                            all_deps = set(base_reqs + meta_reqs)
                            graph[current_pkg] = list(all_deps)
            except Exception:
                return None

            return graph

    # =========================================================================
    # --- ČÍTANIE EXTRAS ZO SÚBORU REQUIREMENTS.TXT PRI INŠTALÁCII ---
    # =========================================================================

    @staticmethod
    def _scan_requirements_for_extras(req_file_path: str, visited=None) -> dict[str, list[str]]:
        """
        Preskenuje súbor requirements.txt (vrátane vnorených -r súborov) a vyextrahuje
        požiadavky na extras: { 'rodičovský_balíček': ['extra1', 'extra2'] }.
        """
        extras_map = {}
        if not req_file_path or not os.path.exists(req_file_path):
            return extras_map

        if visited is None:
            visited = set()
        real_path = os.path.realpath(req_file_path)
        if real_path in visited:
            return extras_map
        visited.add(real_path)

        base_dir = os.path.dirname(real_path)

        try:
            with open(real_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    clean = line.strip().split("#")[0].strip()
                    if not clean:
                        continue

                    if clean.startswith(("-r ", "--requirement ")):
                        parts = clean.split(maxsplit=1)
                        if len(parts) > 1:
                            nested_file = os.path.normpath(os.path.join(base_dir, parts[1].strip().strip("'\"")))
                            nested_map = AptLogic._scan_requirements_for_extras(nested_file, visited)
                            for p, exts in nested_map.items():
                                extras_map.setdefault(p, []).extend(exts)
                        continue

                    if clean.startswith("-"):
                        continue

                    match = re.search(r"([A-Za-z0-9_.\-]+)\s*\[([^\]]+)\]", clean)
                    if match:
                        parent = AptLogic._normalize(match.group(1))
                        raw_extras = match.group(2)
                        extras = [AptLogic._normalize(e) for e in raw_extras.split(",") if e.strip()]
                        if extras and parent not in AptLogic.CORE_TOOLS:
                            extras_map.setdefault(parent, []).extend(extras)
        except Exception:
            pass

        return extras_map

    # =========================================================================
    # --- SYNCHRONIZÁCIA: INSTALL_SYNC ---
    # =========================================================================

    @staticmethod
    def install_sync(core, venv_path: str, log_callback, req_file_path: str = None) -> bool:
        """
        Vykoná kompletnú stavovú synchronizáciu medzi súborom requirements.txt a venvom.
        
        Kroky cyklu:
        1. DIFF: Zistí, čo v prostredí chýba a čo bolo zo súboru odstránené.
        2. INSTALL: Nainštaluje iba chýbajúce balíčky.
        3. EXTRAS SYNC: Prepočíta a zaktualizuje viazané extras.
        4. AUTOREMOVE: Odstráni siroty, ktoré uvoľnilo zmazanie riadkov z requirements.txt
           (avšak IBA ak ich nedrží 'explicit' alebo 'linker_packages_bound').
        5. ZÁPIS: Uloží nový zoznam do 'requirements_cache'.
        """
        with AptLogic._get_venv_lock(venv_path):
            log_callback(AptLogic._tr("apt_diff_comparing", "\n📦 [APT: STAV 1 - DIFF] Porovnávam požiadavky z requirements.txt voči JSON stavu..."))

            try:
                if not req_file_path or not os.path.exists(req_file_path):
                    project_path = Paths.get_project_path(core.projects_root, core.active_project)
                    req_file_path = Paths.get_requirements_txt_path(project_path)

                pamat_extras = AptLogic._scan_requirements_for_extras(req_file_path)

                raw_wanted = RequirementsParser.parse(req_file_path, pip_e_root=core.pip_e_packages_root) if os.path.exists(req_file_path) else set()
                wanted_packages = {AptLogic._normalize(p) for p in raw_wanted}

                state_data = AptLogic._load_state_data(venv_path)
                cached_reqs = set(state_data.get("requirements_cache", []))
                released_from_reqs = list(cached_reqs - wanted_packages)

                graph = AptLogic.get_dependency_graph(venv_path, core)
                if graph is None:
                    log_callback(AptLogic._tr("apt_err_list_failed", "❌ [APT: CHYBA] Zlyhalo načítanie zoznamu balíčkov."))
                    return False

                installed_packages = set(graph.keys())
                missing_packages = wanted_packages - installed_packages

                if released_from_reqs:
                    log_callback(AptLogic._tr("apt_released_from_reqs", "  🔻 Uvoľnené zo súboru: {pkgs}", pkgs=', '.join(released_from_reqs)))
                if missing_packages:
                    log_callback(AptLogic._tr("apt_missing_packages", "  🔺 Chýbajúce v prostredí: {pkgs}", pkgs=', '.join(missing_packages)))

                if missing_packages:
                    log_callback(AptLogic._tr("apt_installing_reqs", "🚀 [APT: STAV 2 - INSTALL] Inštalujem požiadavky: {pkgs}", pkgs=', '.join(missing_packages)))
                    dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
                    install_args = dispatcher.get("install_multiple_exact", packages=list(missing_packages))

                    CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
                    process = subprocess.Popen(install_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=CREATE_NO_WINDOW)
                    for line in process.stdout:
                        log_callback(f"  {line.strip()}")
                    process.wait()
                    if process.returncode != 0:
                        log_callback(AptLogic._tr("apt_install_failed", "❌ [APT: CHYBA] Inštalácia zlyhala. Stav JSON ostáva nezmenený."))
                        return False
                else:
                    log_callback(AptLogic._tr("apt_install_all_present", "✅ [APT: STAV 2 - INSTALL] Všetky požadované balíčky sú prítomné."))

                # ZÁPIS DO JSONU EXPLICITNE PRE REQUIREMENTS KONTEXT A SYNCHRONIZÁCIA EXTRAS
                # 1. Odviažeme extras pre balíčky, ktoré boli úplne odstránené zo súboru
                for rel_pkg in list(released_from_reqs):
                    bound_kids = AptLogic.unbind_extras_for_parent(venv_path, rel_pkg, context="requirements")
                    released_from_reqs.extend(bound_kids)

                # 2. Skontrolujeme zmenu extras pre balíčky, ktoré v súbore zostali (napr. requests[socks] -> requests)
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
                    else:
                        bound_kids = AptLogic.unbind_extras_for_parent(venv_path, parent_pkg, context="requirements")
                        if bound_kids:
                            released_from_reqs.extend(bound_kids)

                # 3. Cache sa aktualizuje PRED autoremove, aby stav odrážal nový súbor
                #    a vlastníctvo (get_all_owned_packages) nepovažovalo zmazané riadky za stále držané.
                state_data = AptLogic._load_state_data(venv_path)
                state_data["requirements_cache"] = sorted(list(wanted_packages))
                AptLogic._save_state_data(venv_path, state_data)

                # 4. Ak pribudli uvoľnené balíčky alebo odobrané extras, spustíme čistenie
                if released_from_reqs:
                    unique_released = list(dict.fromkeys(released_from_reqs))
                    log_callback(AptLogic._tr("apt_autoremove_removing", "🧹 [APT: STAV 4 - AUTOREMOVE] Odstraňujem balíčky: {pkgs}", pkgs=', '.join(unique_released)))
                    AptLogic.autoremove(core, venv_path, log_callback, released_packages=unique_released)

                state_data = AptLogic._load_state_data(venv_path)
                state_data["requirements_cache"] = sorted(list(wanted_packages))
                AptLogic._save_state_data(venv_path, state_data)

                log_callback(AptLogic._tr("apt_cycle_done", "✅ [APT: HOTOVO] Celý stavový cyklus úspešne dokončený."))
                return True

            except Exception as e:
                log_callback(AptLogic._tr("apt_err_critical", "❌ [APT: CHYBA] Kritické zlyhanie stavového cyklu: {err}", err=str(e)))
                return False

    # =========================================================================
    # --- AUTOREMOVE: ČISTENIE SIRÔT VÝHRADNE PODĽA JSONU ---
    # =========================================================================

    @staticmethod
    def autoremove(core, venv_path: str, log_callback, released_packages=None) -> bool:
        """
        Automaticky odinštaluje všetky osirelé balíčky (siroty).

        DEFINÍCIA CHRÁNENÝCH KOREŇOV (ROOTS), KTORÉ SA NIKDY NEMAŽÚ:
          Roots = explicit ∪ requirements_cache ∪ linker_packages_bound ∪ editable_pkgs
        Závislosti systémových nástrojov (CORE_TOOLS) sa považujú za potrebné (tranzitívne od CORE_TOOLS).
        
        Sirota je balíček, ktorý:
          - Nie je v Roots.
          - Nie je vyžadovaný žiadnym balíčkom z Roots (ani tranzitívne).
          - Nie je systémovým jadrovým nástrojom (CORE_TOOLS).
        """
        with AptLogic._get_venv_lock(venv_path):
            mgr_label = "UV" if getattr(core, "package_manager", "pip") == "uv" else "PIP"

            graph = AptLogic.get_dependency_graph(venv_path, core)
            if graph is None:
                log_callback(AptLogic._tr("apt_err_list_failed_short", "❌ [APT] Zlyhalo načítanie zoznamu balíčkov."))
                return False

            if not graph:
                log_callback(AptLogic._tr("apt_clean_no_pkgs", "✅ [APT] Systém je čistý. Žiadne balíčky."))
                return True

            all_installed = set(graph.keys())

            # Systémové nástroje (pip, wheel, setuptools, ...) sa nikdy nemažú, ale ich závislosti
            # (napr. 'packaging' pre wheel) musia byť chránené tiež - preto sú to korene pre výpočet
            # potrebných balíčkov. Bez toho sa závislosti systémových nástrojov zmažú (alebo sa
            # pri self-healingu omylom povýšia na 'explicit').
            core_roots = (AptLogic.CORE_TOOLS | AptLogic.ensure_system_packages(venv_path)) & all_installed

            # 1. Zostavenie chránených koreňov
            explicit_roots = AptLogic.load_explicit_list(venv_path)
            state_data = AptLogic._load_state_data(venv_path)
            explicit_roots.update(state_data.get("requirements_cache", []))

            # 5. STAV: Chránené korene z Linkera (priamo zo stavu JSON)
            explicit_roots.update(AptLogic.get_all_linker_required_packages(venv_path))

            # Uvoľnené balíčky, ktoré má ešte iný vlastník (explicit / requirements / iný linker modul),
            # sa NESMÚ odpočítať z koreňov - inak by sa zmazali napriek platnému nároku.
            norm_released_all = list(dict.fromkeys(AptLogic._normalize(p) for p in (released_packages or [])))
            still_owned = AptLogic.get_all_owned_packages(venv_path)
            kept_owned = [p for p in norm_released_all if p in still_owned]
            norm_released = [p for p in norm_released_all if p not in still_owned]
            if kept_owned:
                log_callback(AptLogic._tr("apt_autoremove_kept_owned", "🛡️ [APT] Ponechávam (má ďalšieho vlastníka): {pkgs}", pkgs=', '.join(kept_owned)))
            explicit_roots.difference_update(norm_released)

            editable_pkgs = AptLogic.get_editable_packages(venv_path, core.package_manager)
            for e_pkg in editable_pkgs:
                e_name = AptLogic._normalize(e_pkg.get("name", ""))
                if e_name and e_name not in norm_released:
                    explicit_roots.add(e_name)

            # 2. Rekurzívne vyhľadanie všetkých potrebných pod-závislostí
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

            auto_needed = get_all_required(explicit_roots | core_roots)

            released_tree = get_all_required(norm_released)
            released_tree.update(norm_released)

            # 3. Self-healing pre manuálne doinštalované balíčky mimo VenvHubu
            state_explicit = AptLogic.load_explicit_list(venv_path)
            new_manual_found = False
            for pkg in all_installed:
                if pkg not in explicit_roots and pkg not in auto_needed and pkg not in AptLogic.CORE_TOOLS and pkg not in core_roots:
                    if pkg in released_tree:
                        continue
                    explicit_roots.add(pkg)
                    state_explicit.add(pkg)
                    new_manual_found = True

            if new_manual_found:
                AptLogic.save_explicit_list(venv_path, state_explicit)
                auto_needed = get_all_required(explicit_roots | core_roots)

            # 4. Výpočet skutočných sirôt
            orphans = all_installed - explicit_roots - auto_needed - AptLogic.CORE_TOOLS - core_roots

            if not orphans:
                log_callback(AptLogic._tr("apt_clean_no_orphans", "✅ [APT] Systém je čistý. Žiadne osirelé balíčky."))
                return True

            log_callback(AptLogic._tr("apt_autoremove_orphans", "🗑️ [APT-{mgr}] Autoremove: Odstraňujem: {pkgs}", mgr=mgr_label, pkgs=', '.join(orphans)))

            dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            uninstall_args = dispatcher.get("uninstall_multiple", packages=list(orphans))

            try:
                process = subprocess.Popen(uninstall_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=CREATE_NO_WINDOW)

                def _read_output():
                    for line in process.stdout:
                        log_callback(f"  {line.strip()}")

                reader_thread = threading.Thread(target=_read_output, daemon=True)
                reader_thread.start()
                reader_thread.join(timeout=60)

                if reader_thread.is_alive():
                    process.kill()
                    reader_thread.join(timeout=5)
                    log_callback(AptLogic._tr("apt_uninstall_timeout", "❌ [APT] Odinštalácia prekročila časový limit."))
                    return False

                process.wait(timeout=5)
                return True

            except Exception as e:
                log_callback(AptLogic._tr("apt_err_uninstall", "❌ [APT] Chyba pri odinštalovaní: {err}", err=str(e)))
                return False
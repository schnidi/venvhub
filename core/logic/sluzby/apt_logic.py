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
    Systém správy závislostí inšpirovaný Linuxovým APT.
    Jediným zdrojom pravdy pre stav balíčkov je venvhub_apt_state.json,
    ale deklaratívnou modlou pre systémové balíčky je requirements.txt.

    Štvorstavový model evidencie:
      1. explicit
      2. explicit_extras_bound
      3. requirements_cache
      4. requirements_extras_bound
    """

    CORE_TOOLS = {"pip", "setuptools", "wheel", "virtualenv", "uv"}

    _locks_guard = threading.Lock()
    _venv_locks = {}

    @staticmethod
    def _tr(key: str, default: str, *args, **kwargs) -> str:
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
        token = token.strip()
        match = re.match(r"^[A-Za-z0-9_.\-]+", token)
        return match.group(0) if match else token

    @staticmethod
    def _normalize(name: str) -> str:
        import re
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
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("explicit", [])
                        data.setdefault("explicit_extras_bound", {})
                        data.setdefault("requirements_cache", [])
                        data.setdefault("requirements_extras_bound", {})
                        return data
            except Exception:
                pass
        return {
            "explicit": [], 
            "explicit_extras_bound": {},
            "requirements_cache": [], 
            "requirements_extras_bound": {}
        }

    @staticmethod
    def _save_state_data(venv_path: str, data: dict):
        state_file = AptLogic._get_state_file(venv_path)
        try:
            ordered_data = {
                "explicit": data.get("explicit", []),
                "explicit_extras_bound": data.get("explicit_extras_bound", {}),
                "requirements_cache": data.get("requirements_cache", []),
                "requirements_extras_bound": data.get("requirements_extras_bound", {})
            }
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(ordered_data, f, indent=4)
        except Exception:
            pass

    # =========================================================================
    # --- LINUX APT LOGIC: OCHRANA A VYHLADENIE PRED ODINŠTALÁCIOU ---
    # =========================================================================
    
    @staticmethod
    def verify_uninstall_safety(venv_path: str, core, pkg_name: str) -> tuple[bool, str]:
        """
        ŽIVÁ KONTROLA pred povolením odinštalácie.
        1. Skontroluje, či balíček nevyžadujú iné nainštalované balíčky (TVRDÉ závislosti).
        2. Skontroluje NAŽIVO requirements.txt a jeho viazané extras (stromové väzby). 
           Ak je balík viazaný na requirements balík, NESMIE sa zmazať ručne!
        """
        norm_pkg = AptLogic._normalize(pkg_name)
        
        # Ochrana č. 1: Reverzné závislosti (Rozlišujeme Hard a Soft)
        deps = AptLogic.is_package_required_by_others(venv_path, core, norm_pkg)
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
                "❌ Nemožno odinštalovať '{0}', pretože je to TVRDá ZÁVISLOSŤ pre: {1}", 
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

                # B) NOVINKA: Skontrolujeme, či nie je naviazaný ako "extra" k niektorému balíku z requirements.txt
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

        return True, ""

    @staticmethod
    def scrub_package_completely(venv_path: str, pkg_name: str) -> list[str]:
        """Keď kontrola bezpečnosti prejde, táto metóda ho vyhladí zo stavu a uvoľní jeho deti."""
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

            if modified:
                AptLogic._save_state_data(venv_path, data)
                
        return list(released_kids)

    # =========================================================================
    # --- LINUX APT LOGIC: KONTROLA PRED INŠTALÁCIOU (STAV 1:1) ---
    # =========================================================================

    @staticmethod
    def check_install_necessity(venv_path: str, core, installed_items: list[tuple[str, list[str]]], log_callback=None) -> tuple[bool, str]:
        """
        KONTROLA PRED INŠTALÁCIOU (STAV 1:1 a OCHRANA PRED DUPLICITAMI)
        s priebežným výpisom do GUI logu v reálnom čase.
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
    def mark_as_explicit(venv_path: str, package_name: str):
        """Označí balíček ako explicitný. ZÁKAZ DUPLICITY: Ak je v requirements, do explicit nejde!"""
        with AptLogic._get_venv_lock(venv_path):
            norm_pkg = AptLogic._normalize(package_name)
            data = AptLogic._load_state_data(venv_path)

            if norm_pkg in set(data.get("requirements_cache", [])):
                return

            AptLogic.promote_bound_to_explicit(venv_path, norm_pkg)
            explicit = AptLogic.load_explicit_list(venv_path)
            explicit.add(norm_pkg)
            AptLogic.save_explicit_list(venv_path, explicit)

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
            else:
                merged = {}
                for k in ["explicit_extras_bound", "requirements_extras_bound"]:
                    for parent, kids in data.get(k, {}).items():
                        merged.setdefault(parent, set()).update(kids)
                return {p: sorted(list(k)) for p, k in merged.items()}

    @staticmethod
    def bind_extras(venv_path: str, parent_pkg: str, child_pkgs: list[str], context: str = "explicit"):
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
                if norm_child in other_bounds:
                    continue
                if norm_child not in explicit_set:
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
            
            for key in ["explicit_extras_bound", "requirements_extras_bound"]:
                bounds = data.get(key, {})
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
                if norm_child in other_bounds:
                    continue
                if norm_child not in explicit_set:
                    filtered.add(norm_child)

            if filtered:
                bounds[norm_parent] = sorted(list(filtered))
            else:
                bounds.pop(norm_parent, None)

            AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def resolve_extras_family(venv_path: str, parent_pkg: str, requested_extras: list[str]) -> list[str]:
        """
        Vyhľadá a vráti zoznam nainštalovaných balíčkov (celý strom závislostí)
        prislúchajúcich k zadaným extras rodičovského balíčka z metadát.
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
        """Vyrieši a naviaže balíčky prislúchajúce k extras daného rodiča."""
        all_family = AptLogic.resolve_extras_family(venv_path, parent_pkg, requested_extras)
        if all_family:
            AptLogic.bind_extras(venv_path, parent_pkg, all_family, context=context)
    # =========================================================================
    # --- ČÍTANIE METADATA Z DISKU ---
    # =========================================================================

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
    def _get_all_requires_from_metadata(venv_path: str, pkg_name: str) -> list[str]:
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
        norm_pkg = AptLogic._normalize(pkg_name)
        state_data = AptLogic._load_state_data(venv_path)
        
        if norm_pkg in set(state_data.get("requirements_cache", [])):
            return True

        for key in ["explicit_extras_bound", "requirements_extras_bound"]:
            bounds = state_data.get(key, {})
            for parent, children in bounds.items():
                if norm_pkg in children:
                    return True

        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for parent_pkg, deps in graph.items():
                if norm_pkg in deps:
                    return True

        site_folder = "Lib" if os.name == 'nt' else "lib"
        venvhub_json = os.path.join(venv_path, site_folder, "site-packages", "venvhub.json")
        if os.path.exists(venvhub_json):
            try:
                with open(venvhub_json, 'r', encoding='utf-8') as f:
                    for pkg_path in json.load(f).values():
                        meta_file = os.path.join(pkg_path, "local_meta.json")
                        if os.path.exists(meta_file):
                            with open(meta_file, 'r', encoding='utf-8') as mf:
                                reqs = [AptLogic._normalize(r) for r in json.load(mf).get("requires_pip", [])]
                                if norm_pkg in reqs:
                                    return True
            except Exception:
                pass

        return False

    @staticmethod
    def get_editable_packages(venv_path: str, manager_type: str = "pip"):
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
    def is_package_required_by_others(venv_path, core, package_name):
        pkg_norm = AptLogic._normalize(package_name)
        dependents = []

        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for other_pkg, requirements in graph.items():
                if other_pkg == pkg_norm:
                    continue
                if pkg_norm in requirements:
                    dependents.append(other_pkg)

        site_folder = "Lib" if os.name == 'nt' else "lib"
        venvhub_json = os.path.join(venv_path, site_folder, "site-packages", "venvhub.json")
        if os.path.exists(venvhub_json):
            try:
                with open(venvhub_json, 'r', encoding='utf-8') as f:
                    linked_map = json.load(f)
                for pkg_key, pkg_path in linked_map.items():
                    meta_path = os.path.join(pkg_path, "local_meta.json")
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path, 'r', encoding='utf-8') as mf:
                                meta = json.load(mf)
                                name = meta.get("name", pkg_key)
                                reqs = [AptLogic._normalize(r) for r in meta.get("requires_pip", [])]
                                if pkg_norm in reqs:
                                    display_name = f"{name} (Linker)"
                                    if display_name not in dependents:
                                        dependents.append(display_name)
                        except Exception:
                            pass
            except Exception:
                pass

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
    def get_dependency_graph(venv_path: str, core):
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
        Vykoná kompletnú synchronizáciu medzi požiadavkami v requirements.txt
        a skutočným stavom virtuálneho prostredia vrátane viazaných extras závislostí.
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

                # 3. Ak pribudli uvoľnené balíčky alebo odobrané extras, spustíme čistenie
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

            explicit_roots = AptLogic.load_explicit_list(venv_path)
            state_data = AptLogic._load_state_data(venv_path)
            explicit_roots.update(state_data.get("requirements_cache", []))

            norm_released = [AptLogic._normalize(p) for p in (released_packages or [])]
            explicit_roots.difference_update(norm_released)

            editable_pkgs = AptLogic.get_editable_packages(venv_path, core.package_manager)
            for e_pkg in editable_pkgs:
                e_name = AptLogic._normalize(e_pkg.get("name", ""))
                if e_name and e_name not in norm_released:
                    explicit_roots.add(e_name)

            site_folder = "Lib" if os.name == 'nt' else "lib"
            venvhub_json = os.path.join(venv_path, site_folder, "site-packages", "venvhub.json")
            if os.path.exists(venvhub_json):
                try:
                    with open(venvhub_json, 'r', encoding='utf-8') as f:
                        for pkg_path in json.load(f).values():
                            meta_path = os.path.join(pkg_path, "local_meta.json")
                            if os.path.exists(meta_path):
                                with open(meta_path, 'r', encoding='utf-8') as mf:
                                    for req in json.load(mf).get("requires_pip", []):
                                        norm_req = AptLogic._normalize(req)
                                        if norm_req not in norm_released:
                                            explicit_roots.add(norm_req)
                except Exception:
                    pass

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

            auto_needed = get_all_required(explicit_roots)

            released_tree = get_all_required(norm_released)
            released_tree.update(norm_released)

            state_explicit = AptLogic.load_explicit_list(venv_path)
            new_manual_found = False
            for pkg in all_installed:
                if pkg not in explicit_roots and pkg not in auto_needed and pkg not in AptLogic.CORE_TOOLS:
                    if pkg in released_tree:
                        continue
                    explicit_roots.add(pkg)
                    state_explicit.add(pkg)
                    new_manual_found = True

            if new_manual_found:
                AptLogic.save_explicit_list(venv_path, state_explicit)
                auto_needed = get_all_required(explicit_roots)

            orphans = all_installed - explicit_roots - auto_needed - AptLogic.CORE_TOOLS

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
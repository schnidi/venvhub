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

class AptLogic:
    """
    Systém správy závislostí inšpirovaný Linuxovým APT (apt-get autoremove).
    Rozlišuje explicitne a automaticky nainštalované balíčky s funkciou Self-Healing.
    
    Zabezpečený proti súbehu vlákien (Race Conditions) pomocou Reentrant Lock (RLock),
    pričom zámok je udržiavaný samostatne PRE KAŽDÝ venv.
    """

    CORE_TOOLS = {"pip", "setuptools", "wheel", "virtualenv", "uv"}

    _locks_guard = threading.Lock()
    _venv_locks = {}

    @staticmethod
    def _get_venv_lock(venv_path: str) -> threading.RLock:
        """Vráti (alebo vytvorí) RLock prislúchajúci danému venv."""
        with AptLogic._locks_guard:
            lock = AptLogic._venv_locks.get(venv_path)
            if lock is None:
                lock = threading.RLock()
                AptLogic._venv_locks[venv_path] = lock
            return lock

    @staticmethod
    def cleanup_unused_venv_locks(active_venv_paths) -> None:
        """Voliteľné upratovanie nepoužívaných zámkov."""
        with AptLogic._locks_guard:
            stale = [path for path in AptLogic._venv_locks if path not in active_venv_paths]
            for path in stale:
                del AptLogic._venv_locks[path]

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalizácia názvu balíčka podľa PEP 503."""
        return re.sub(r"[-_.]+", "-", name.strip().lower())

    @staticmethod
    def _extract_package_name(token: str) -> str:
        """Vytiahne čistý názov balíčka z tokenu."""
        token = token.strip()
        match = re.match(r"^[A-Za-z0-9_.\-]+", token)
        return match.group(0) if match else token

    @staticmethod
    def _get_state_file(venv_path: str) -> str:
        site_folder = "Lib" if os.name == 'nt' else "lib"
        return os.path.join(venv_path, site_folder, "site-packages", "venvhub_apt_state.json")

    @staticmethod
    def _load_state_data(venv_path: str) -> dict:
        state_file = AptLogic._get_state_file(venv_path)
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def _save_state_data(venv_path: str, data: dict):
        state_file = AptLogic._get_state_file(venv_path)
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception:
            pass

    @staticmethod
    def load_explicit_list(venv_path: str) -> set:
        """Bezpečné načítanie explicitného zoznamu."""
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            return set(data.get("explicit", []))

    @staticmethod
    def save_explicit_list(venv_path: str, explicit_set: set):
        """Bezpečný zápis explicitného zoznamu."""
        with AptLogic._get_venv_lock(venv_path):
            data = AptLogic._load_state_data(venv_path)
            data["explicit"] = list(explicit_set)
            AptLogic._save_state_data(venv_path, data)

    @staticmethod
    def mark_as_explicit(venv_path: str, package_name: str):
        """Označí balíček ako explicitný pod ochranou zámku."""
        with AptLogic._get_venv_lock(venv_path):
            explicit = AptLogic.load_explicit_list(venv_path)
            explicit.add(AptLogic._normalize(package_name))
            AptLogic.save_explicit_list(venv_path, explicit)

    @staticmethod
    def unmark_explicit(venv_path: str, package_name: str):
        """Odoberie značku balíčka pod ochranou zámku."""
        with AptLogic._get_venv_lock(venv_path):
            explicit = AptLogic.load_explicit_list(venv_path)
            pkg_normalized = AptLogic._normalize(package_name)
            if pkg_normalized in explicit:
                explicit.remove(pkg_normalized)
                AptLogic.save_explicit_list(venv_path, explicit)

    # =========================================================================
    # --- METÓDY PRE ANALÝZU ZÁVISLOSTÍ ---
    # =========================================================================

    @staticmethod
    def get_editable_packages(venv_path):
        """
        Získa zoznam -e balíčkov vo forme JSON priamo z venvu.
        """
        python_exe = Paths.get_venv_python_exe_path(venv_path)
        if not os.path.exists(python_exe):
            return []

        cmd = [python_exe, "-m", "pip", "list", "--editable", "--format=json"]
        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW
            )
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout.strip())
        except Exception:
            pass

        return []

    @staticmethod
    def is_package_required_by_others(venv_path, core, package_name):
        """
        Skontroluje, či na danom balíčku závisia iné nainštalované balíčky (reverzné závislosti)
        A TAKTIEŽ či ho nevyžaduje niektorý z prepojených Linker balíčkov.
        """
        pkg_norm = AptLogic._normalize(package_name)
        dependents = []

        # 1. Kontrola štandardných PIP závislostí
        graph = AptLogic.get_dependency_graph(venv_path, core)
        if graph:
            for other_pkg, requirements in graph.items():
                if other_pkg == pkg_norm:
                    continue
                if pkg_norm in requirements:
                    dependents.append(other_pkg)

        # 2. Kontrola VenvHub Linker závislostí (venvhub.json -> local_meta.json)
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

    # >>> DOPLNENÉ: Pomocná metóda na extrakciu voliteľných [extras] závislostí z METADATA súborov
    @staticmethod
    def _get_all_requires_from_metadata(venv_path: str, pkg_name: str) -> list[str]:
        """
        Načíta všetky závislosti (vrátane [extras] ako requests[socks] -> pysocks)
        priamo z .dist-info/METADATA súboru balíčka.
        """
        reqs = set()
        norm_target = AptLogic._normalize(pkg_name)
        site_folder = "Lib" if os.name == 'nt' else "lib"
        
        site_pkgs = os.path.join(venv_path, site_folder, "site-packages")
        if not os.path.exists(site_pkgs) and os.name != 'nt':
            import glob
            matches = glob.glob(os.path.join(venv_path, "lib", "python*", "site-packages"))
            if matches:
                site_pkgs = matches[0]

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
                                        dep_raw = val.split(";")[0].strip()
                                        clean_dep = AptLogic._extract_package_name(dep_raw)
                                        if clean_dep:
                                            reqs.add(AptLogic._normalize(clean_dep))
        except Exception:
            pass

        return list(reqs)
    # <<< KONIEC DOPLNENIA

    @staticmethod
    def get_requires_for_package(venv_path, pkg_name, manager_type="pip"):
        reqs = []
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("show", package_name=pkg_name)
            
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            
            for line in res.stdout.splitlines():
                if line.startswith("Requires:"):
                    val = line.replace("Requires:", "").strip()
                    if val: 
                        reqs = [AptLogic._normalize(r) for r in val.split(",") if r.strip()]

            # Robustnejšie zistenie závislostí pre pip -e (fallback pri zámene pomlčiek a podčiarkovníkov)
            if not reqs and ("-" in pkg_name or "_" in pkg_name):
                alt_name = pkg_name.replace("-", "_") if "-" in pkg_name else pkg_name.replace("_", "-")
                try:
                    alt_cmd = dispatcher.get("show", package_name=alt_name)
                    alt_res = subprocess.run(alt_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                    for line in alt_res.stdout.splitlines():
                        if line.startswith("Requires:"):
                            val = line.replace("Requires:", "").strip()
                            if val:
                                reqs = [AptLogic._normalize(r) for r in val.split(",") if r.strip()]
                except Exception:
                    pass

            # >>> DOPLNENÉ: Zlúčenie štandardných Requires s voliteľnými extras závislosťami
            metadata_reqs = AptLogic._get_all_requires_from_metadata(venv_path, pkg_name)
            for m_req in metadata_reqs:
                if m_req not in reqs:
                    reqs.append(m_req)
            # <<< KONIEC DOPLNENIA

        except Exception: 
            pass
        return reqs

    # =========================================================================

    SHOW_MULTIPLE_CHUNK_SIZE = 30

    @staticmethod
    def get_dependency_graph(venv_path: str, core):
        """Načíta strom závislostí s ochranou proti kolízii procesov."""
        with AptLogic._get_venv_lock(venv_path):
            dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
            graph = {}
            
            try:
                list_cmd = dispatcher.get("list_json")
                res_list = subprocess.run(list_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=30)
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
                        res_show = subprocess.run(show_cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=30)
                        if res_show.returncode != 0:
                            return None
                    except Exception:
                        return None

                    current_pkg = None
                    for line in res_show.stdout.splitlines():
                        if line.startswith("Name:"):
                            current_pkg = AptLogic._normalize(line.split(":", 1)[1].strip())
                            graph[current_pkg] = []
                        elif line.startswith("Requires:") and current_pkg:
                            reqs = line.split(":", 1)[1].strip()
                            base_reqs = [
                                AptLogic._normalize(AptLogic._extract_package_name(r))
                                for r in reqs.split(",") if r.strip()
                            ] if reqs else []

                            # >>> DOPLNENÉ: Obohatenie grafu závislostí o extras závislosti z METADATA
                            meta_reqs = AptLogic._get_all_requires_from_metadata(venv_path, current_pkg)
                            all_deps = set(base_reqs + meta_reqs)
                            graph[current_pkg] = list(all_deps)
                            # <<< KONIEC DOPLNENIA
                                
            except Exception:
                return None

            return graph

    # =========================================================================
    # --- SYNCHRONIZÁCIA (INSTALL MISSING & PRUNE REMOVED) ---
    # =========================================================================
    @staticmethod
    def install_sync(core, venv_path: str, log_callback) -> bool:
        """
        1. Analyzuje všetky requirements (vrátane -r vnorených súborov).
        2. Zistí balíčky, ktoré boli zo súborov odstránené / zakomentované.
        3. Doinštaluje chýbajúce balíčky.
        4. Automaticky odstráni osirelé balíčky, ktoré vypadli zo súborov.
        """
        with AptLogic._get_venv_lock(venv_path):
            log_callback(LanguageManager.get("apt_checking_missing", "\n📦 [APT] Kontrolujem zmeny v requirements..."))

            try:
                project_path = Paths.get_project_path(core.projects_root, core.active_project)
                req_file = Paths.get_requirements_txt_path(project_path)
                
                # Získame kompletný aktuálny zoznam zo všetkých súborov (rekurzívne)
                raw_wanted = RequirementsParser.parse(req_file, pip_e_root=core.pip_e_packages_root) if os.path.exists(req_file) else set()
                wanted_packages = {AptLogic._normalize(p) for p in raw_wanted}

                # Načítame predchádzajúci stav requirements pre tento venv
                state_data = AptLogic._load_state_data(venv_path)
                prev_reqs = set(state_data.get("requirements_cache", []))

                # Čo bolo zakomentované alebo zmazané zo súborov
                released_from_reqs = list(prev_reqs - wanted_packages)

                # Aktualizujeme uložený stav requirements
                state_data["requirements_cache"] = list(wanted_packages)
                AptLogic._save_state_data(venv_path, state_data)

                # Zistíme, čo reálne vo venv je
                graph = AptLogic.get_dependency_graph(venv_path, core)
                if graph is None:
                    log_callback(LanguageManager.get("apt_err_graph_failed", "❌ [APT] Zlyhalo načítanie zoznamu balíčkov."))
                    return False

                installed_packages = set(graph.keys())

                # 1. Doinštalovanie chýbajúcich
                missing = wanted_packages - installed_packages
                if missing:
                    log_callback(LanguageManager.get("apt_installing_missing", "🚀 [APT] Doinštalovávam chýbajúce balíčky: {0}").format(", ".join(missing)))
                    dispatcher = PackageManagerFactory.get_dispatcher(core.package_manager, venv_path)
                    install_args = dispatcher.get("install_multiple_exact", packages=list(missing))
                    
                    CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
                    process = subprocess.Popen(install_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=CREATE_NO_WINDOW)
                    for line in process.stdout:
                        log_callback(f"  {line.strip()}")
                    process.wait()
                else:
                    log_callback(LanguageManager.get("apt_all_installed", "✅ [APT] Všetky požadované balíčky sú prítomné."))

                # 2. Automatické odstránenie balíčkov, ktoré zo súboru vypadli (vrátane ich sirôt)
                if released_from_reqs:
                    log_callback(LanguageManager.get("apt_reqs_released", "ℹ️ [APT] Zo súborov boli odstránené: {0}").format(", ".join(released_from_reqs)))
                
                AptLogic.autoremove(core, venv_path, log_callback, released_packages=released_from_reqs)
                return True

            except Exception as e:
                log_callback(f"❌ [APT] Chyba pri synchronizácii inštalácie: {e}")
                return False

    @staticmethod
    def autoremove(core, venv_path: str, log_callback, released_packages=None) -> bool:
        """Analyzuje a odstraňuje nepoužívané závislosti."""
        with AptLogic._get_venv_lock(venv_path):
            log_callback(LanguageManager.get("apt_analyzing", "\n🔍 [APT] Analyzujem strom závislostí pre autoremove..."))

            graph = AptLogic.get_dependency_graph(venv_path, core)
            if graph is None:
                log_callback(LanguageManager.get("apt_err_graph_failed", "❌ [APT] Zlyhalo načítanie zoznamu balíčkov."))
                return False

            if not graph:
                log_callback(LanguageManager.get("apt_clean", "✅ [APT] Systém je čistý. Žiadne osirelé balíčky."))
                return True

            all_installed = set(graph.keys())
            state_explicit = AptLogic.load_explicit_list(venv_path)
            explicit_roots = state_explicit.copy()

            if not released_packages:
                released_packages = []
            released_packages = [AptLogic._normalize(p) for p in released_packages]

            # 1. Poistka: Requirements (Rekurzívne cez Parser + pip-e prepojenie)
            parsed_reqs = set()
            try:
                project_path = Paths.get_project_path(core.projects_root, core.active_project)
                req_file = Paths.get_requirements_txt_path(project_path)
                if os.path.exists(req_file):
                    raw_parsed = RequirementsParser.parse(req_file, pip_e_root=core.pip_e_packages_root)
                    parsed_reqs = {AptLogic._normalize(p) for p in raw_parsed}
                    explicit_roots.update(parsed_reqs)

                # Podpora pre pip -e balíčky
                editable_pkgs = AptLogic.get_editable_packages(venv_path)
                for e_pkg in editable_pkgs:
                    e_name = AptLogic._normalize(e_pkg.get("name", ""))
                    if e_name and e_name not in released_packages:
                        explicit_roots.add(e_name)
            except Exception:
                pass

            # 2. Poistka: Ostatné Linkery
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
                                        explicit_roots.add(AptLogic._normalize(req))
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

            released_tree = get_all_required(released_packages)
            released_tree.update(released_packages)

            # 3. Samooprava (Self-healing)
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

            # 4. Výpočet sirôt
            orphans = all_installed - explicit_roots - auto_needed - AptLogic.CORE_TOOLS

            if not orphans:
                log_callback(LanguageManager.get("apt_clean", "✅ [APT] Systém je čistý. Žiadne osirelé balíčky."))
                return True

            # 5. Hromadné vymazanie
            log_callback(LanguageManager.get("apt_removing", "🗑️ [APT] Autoremove: Odstraňujem osirelé závislosti: {0}").format(", ".join(orphans)))
            
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
                    log_callback(LanguageManager.get("apt_timeout", "❌ [APT] Odinštalácia trvala príliš dlho a bola ukončená (Timeout 60s)."))
                    return False

                process.wait(timeout=5)
                return True
                
            except subprocess.TimeoutExpired:
                process.kill()
                log_callback(LanguageManager.get("apt_timeout", "❌ [APT] Odinštalácia trvala príliš dlho a bola ukončená (Timeout 60s)."))
                return False
            except Exception as e:
                if 'process' in locals() and process.poll() is None:
                    process.kill()
                log_callback(LanguageManager.get("apt_err", "❌ [APT] Chyba pri odinštalovaní: {0}").format(e))
                return False
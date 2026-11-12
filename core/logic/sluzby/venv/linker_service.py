#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/linker_service.py
# Nízkoúrovňová jadrová služba pre lokálny linker (LOCAL_LINKER)
# Zabezpečuje prelinkovanie modulov, inštaláciu závislostí,
# evidenciu v 5. stave APT a synchronizáciu s IDE.
# Všetky preklady idú výhradne cez CoreBridge.
#----------------------------------------------------

import os
import json
import subprocess
import re
from collections import deque

from core._path import Paths
from core.core_bridge import CoreBridge
from core.core_states import LinkerOperationStatus
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.apt_ide_logic import AptIDELogic
from core.logic.vs_code_json import VSCodeIntegration


class LocalLinkerService:
    """
    Služba jadra pre správu a prelinkovanie lokálnych vývojových balíčkov.
    Poskytuje detailné in-time logovanie priebehu každého kroku.
    """

    @classmethod
    def apply_links(cls, core, venv_path: str, selected_items: list[dict], log_callback=print) -> tuple[LinkerOperationStatus, str]:
        """
        Hlavný vstupný bod: vykoná kompletný cyklus prelinkovania balíčkov.
        
        Returns:
            tuple[LinkerOperationStatus, str]: Stav operácie (Enum) a prípadná chybová správa.
        """
        def _log(msg: str):
            if log_callback:
                log_callback(msg)

        _log("\n" + "=" * 70)
        _log(CoreBridge.translate("linker_log_start", "🔗 [LINKER] ŠTART PREPOJENIA LOKÁLNYCH BALÍČKOV"))
        _log(f"📁 Cieľový Venv: {venv_path}")
        _log(f"📦 Počet vybraných modulov v UI: {len(selected_items)}")
        _log("=" * 70)

        # ---------------------------------------------------------------------
        # FÁZA 1: REKURZÍVNA ANALÝZA LOKÁLNYCH A EXTERNÝCH ZÁVISLOSTÍ
        # ---------------------------------------------------------------------
        _log("\n[KROK 1/5] 🔍 Analyzujem závislosti vybraných balíčkov...")

        for item in selected_items:
            item['name'] = os.path.basename(os.path.normpath(item['path']))

        all_packages_to_link, pip_dependencies, err_missing = cls._resolve_dependencies(
            core, selected_items, _log
        )
        if err_missing:
            _log(f"\n❌ [LINKER] Prerušené: {err_missing}")
            return LinkerOperationStatus.MISSING_LOCAL_DEP, err_missing

        _log(f"  ✔ Zoznam modulov na prelinkovanie ({len(all_packages_to_link)}): {', '.join(all_packages_to_link.keys())}")
        if pip_dependencies:
            _log(f"  ✔ Nájdené externé PIP požiadavky ({len(pip_dependencies)}): {', '.join(pip_dependencies)}")
        else:
            _log("  ℹ️ Moduly nevyžadujú žiadne externé PIP závislosti.")

        # ---------------------------------------------------------------------
        # FÁZA 2: BEZPEČNÁ INŠTALÁCIA EXTERNÝCH ZÁVISLOSTÍ (POD ZÁMKOM VENVU)
        # ---------------------------------------------------------------------
        with AptLogic._get_venv_lock(venv_path):
            _log("\n[KROK 2/5] 📦 Kontrola a inštalácia externých PIP balíčkov...")

            if pip_dependencies:
                success_pip, err_pip = cls._install_dependencies_safely(
                    core, venv_path, pip_dependencies, _log
                )
                if not success_pip:
                    _log(f"\n❌ [LINKER] Inštalácia externých závislostí zlyhala: {err_pip}")
                    _log("⚠️ Stav venvu a prelinkovanie ostávajú nezmenené (Rollback).")
                    return LinkerOperationStatus.DEPENDENCY_ERROR, err_pip
            else:
                _log("  ✔ Preskakujem inštaláciu (žiadne externé PIP závislosti).")

            # -----------------------------------------------------------------
            # FÁZA 3: ZÁPIS HOOK SÚBOROV DO SITE-PACKAGES (venvhub.json & .pth)
            # -----------------------------------------------------------------
            _log("\n[KROK 3/5] 🛠️ Vytváram import hooky v site-packages...")
            added_count, removed_count = cls._manage_hook_files(
                venv_path, all_packages_to_link, _log
            )
            _log(f"  ✔ Prelinkovanie dokončené (Pridané cesty: {added_count}, Odstránené cesty: {removed_count}).")

            # -----------------------------------------------------------------
            # FÁZA 4: SYNCHRONIZÁCIA 5. STAVU APT & AUTOREMOVE SIRÔT
            # -----------------------------------------------------------------
            _log("\n[KROK 4/5] 🧠 Zosúlaďujem 5. stav APT (linker_packages_bound)...")
            try:
                cls._sync_apt_linker_state(core, venv_path, all_packages_to_link, _log)
            except Exception as e:
                err_msg = f"Chyba pri synchronizácii stavu APT: {e}"
                _log(f"  ❌ {err_msg}")
                return LinkerOperationStatus.ERROR, err_msg

        # ---------------------------------------------------------------------
        # FÁZA 5: SYNCHRONIZÁCIA S VÝVOJOVÝMI EDITROVMI (VS CODE / CURSOR AI)
        # ---------------------------------------------------------------------
        _log("\n[KROK 5/5] 💻 Synchronizujem konfiguráciu IDE (VS Code & Cursor AI)...")
        
        # A) IDE Rozšírenia pre profil
        try:
            _log("  🧩 Overujem rozšírenia editora pre aktívny profil...")
            AptIDELogic.sync_ide_extensions(core, all_packages_to_link, log_callback=_log)
        except Exception as e:
            _log(f"  ⚠️ Varovanie pri synchronizácii IDE rozšírení: {e}")

        # B) IntelliSense extraPaths, tasks.json a keybindings.json
        project_path = Paths.get_project_path(core.projects_root, core.active_project)
        target_paths = [pkg_data['path'] for pkg_data in all_packages_to_link.values()]

        try:
            _log("  ⚙️ Aktualizujem Pylance cesty (python.analysis.extraPaths)...")
            VSCodeIntegration.sync_local_packages(project_path, target_paths, core.local_packages_root)

            _log("  📜 Aktualizujem úlohy (tasks.json) a klávesové skratky (keybindings.json)...")
            VSCodeIntegration.sync_vscode_tasks_and_keybindings(
                project_path, target_paths, core.local_packages_root, log_callback=_log
            )
        except Exception as e:
            _log(f"  ⚠️ Varovanie pri úprave projektových súborov IDE: {e}")

        # ---------------------------------------------------------------------
        # VYHODNOTENIE A FINÁLNE ZHODNOTENIE
        # ---------------------------------------------------------------------
        _log("\n" + "=" * 70)
        if added_count == 0 and removed_count == 0:
            _log("ℹ️ [LINKER] Všetky moduly a nastavenia boli už aktuálne. Nebolo potrebné nič meniť.")
            _log("=" * 70 + "\n")
            return LinkerOperationStatus.NO_CHANGES, ""
        else:
            _log(f"✅ [LINKER] Operácia úspešná! Aktívne moduly: {len(all_packages_to_link)} (Pridané: {added_count}, Odstránené: {removed_count}).")
            _log("=" * 70 + "\n")
            return LinkerOperationStatus.SUCCESS, ""

    # =========================================================================
    # VNÚTORNÉ METÓDY PRE ANALÝZU A SPRACOVANIE
    # =========================================================================

    @classmethod
    def _resolve_dependencies(cls, core, selected_items: list[dict], log) -> tuple[dict, list, str]:
        """
        Rekurzívne prejde vybrané moduly a načíta ich `requires_local` a `requires_pip`.
        """
        all_to_link = {item['name']: item for item in selected_items}
        pip_deps = []
        queue = deque([item['name'] for item in selected_items])
        visited = set()

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
                log(f"  ℹ️ Modul '{pkg_name}' nemá súbor local_meta.json (preskakujem čítanie závislostí).")
                continue

            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)

                # 1. Externé PIP závislosti
                req_pip = meta.get("requires_pip", [])
                for pip_pkg in req_pip:
                    clean_entry = str(pip_pkg).strip()
                    if clean_entry and clean_entry not in pip_deps:
                        pip_deps.append(clean_entry)
                        log(f"  ➕ [{pkg_name}] Vyžaduje externý PIP balíček: '{clean_entry}'")

                # 2. Lokálne závislosti (requires_local)
                req_local = meta.get("requires_local", [])
                for local_dep_name in req_local:
                    dep_clean = str(local_dep_name).strip()
                    if not dep_clean:
                        continue

                    # Overíme, či už nie je v strome
                    already_in = any(
                        existing_name == dep_clean or existing_data['name'] == dep_clean
                        for existing_name, existing_data in all_to_link.items()
                    )
                    if not already_in:
                        dep_path = os.path.join(core.local_packages_root, dep_clean)
                        if not os.path.isdir(dep_path):
                            msg_fmt = CoreBridge.translate(
                                "msg_missing_local_dep", 
                                "Chýba lokálna závislosť: {0} pre {1}"
                            )
                            err_msg = msg_fmt.format(dep_clean, pkg_name) + f"\nCesta neexistuje: {dep_path}"
                            log(f"  ❌ {err_msg}")
                            return {}, [], err_msg

                        real_name = os.path.basename(os.path.normpath(dep_path))
                        log(f"  🔗 [{pkg_name}] Automaticky pridávam lokálnu závislosť: '{real_name}'")
                        all_to_link[real_name] = {'name': real_name, 'path': dep_path}
                        queue.append(real_name)

            except (json.JSONDecodeError, OSError, IOError) as e:
                log(f"  ⚠️ Chyba pri čítaní metadát modulu '{pkg_name}': {e}")

        return all_to_link, pip_deps, ""

    @classmethod
    def _install_dependencies_safely(cls, core, venv_path: str, dependencies: list[str], log) -> tuple[bool, str]:
        """
        Overí prítomnosť balíčkov a ich verzií na disku. Ak niečo chýba, nainštaluje to.
        """
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_pkgs_dir = os.path.join(venv_path, site_folder, "site-packages")
        if not os.path.exists(site_pkgs_dir):
            site_pkgs_dir = AptLogic._get_site_packages_dir(venv_path)

        installed_versions = cls._collect_installed_versions(site_pkgs_dir)
        installed_on_disk = set(installed_versions.keys())

        missing_dependencies = []

        for dep in dependencies:
            raw_dep = str(dep).strip()
            if not raw_dep:
                continue

            clean_name = RequirementsParser._extract_package_name(raw_dep)
            if not clean_name:
                missing_dependencies.append(raw_dep)
                continue

            norm_name = AptLogic._normalize(clean_name)

            if norm_name not in installed_on_disk:
                log(f"  🔻 Chýba v site-packages: '{raw_dep}' -> zaradené na inštaláciu.")
                missing_dependencies.append(raw_dep)
                continue

            installed_ver = installed_versions.get(norm_name, "")
            if not cls._version_satisfied(raw_dep, installed_ver):
                log(f"  ⚡ Nevyhovujúca verzia pre '{norm_name}' (nainštalované: {installed_ver}, požadované: {raw_dep}) -> zaradené na inštaláciu.")
                missing_dependencies.append(raw_dep)
                continue

            # Kontrola [extras] detí
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
                    log(f"  ⚡ Chýbajú viazané extras ({', '.join(missing_children)}) pre '{raw_dep}' -> zaradené na inštaláciu.")
                    missing_dependencies.append(raw_dep)
                    continue

            log(f"  ✔ Balíček '{norm_name}=={installed_ver}' je už nainštalovaný a vyhovuje.")

        if not missing_dependencies:
            log("  ✅ Všetky externé PIP závislosti sú už v prostredí prítomné.")
            return True, ""

        log(f"\n  ⚡ Spúšťam inštaláciu chýbajúcich balíčkov ({len(missing_dependencies)}): {', '.join(missing_dependencies)}")

        try:
            manager_type = getattr(core, 'package_manager', 'pip')
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("install_multiple_exact", packages=missing_dependencies)

            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

            log(f"  🛠️ Príkaz: {' '.join(cmd)}")
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
                    log(f"    [Install] {clean_line}")

            process.wait()
            if process.returncode == 0:
                log("  ✔ Inštalácia externých závislostí úspešne dokončená.")
                return True, ""
            else:
                err_msg = f"Inštalátor vrátil chybový kód {process.returncode}"
                return False, err_msg

        except Exception as e:
            return False, str(e)

    @classmethod
    def _manage_hook_files(cls, venv_path: str, packages_dict: dict, log) -> tuple[int, int]:
        """
        Vytvorí súbory venvhub.json a venvhub_links.pth v site-packages.
        """
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_packages = os.path.join(venv_path, site_folder, "site-packages")
        os.makedirs(site_packages, exist_ok=True)

        json_file = os.path.join(site_packages, "venvhub.json")
        pth_file = os.path.join(site_packages, "venvhub_links.pth")

        # Vyčistenie starých legacy bootstrap súborov
        for old_f in ["venvhub_bootstrap.py", "venvhub_bootstrap.pth", ".venvhub_linked"]:
            old_path = os.path.join(site_packages, old_f)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                    log(f"  🧹 Odstránený starý hook: {old_f}")
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
            log("  ℹ️ Žiadne moduly nie sú vybrané. Odstraňujem hook súbory...")
            for filepath in [json_file, pth_file]:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
            return added_count, removed_count

        mapping = {name: os.path.normpath(data['path']) for name, data in packages_dict.items()}

        log(f"  📄 Zapisujem '{os.path.basename(json_file)}' ({len(mapping)} záznamov)...")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=4, ensure_ascii=False)

        log(f"  📄 Zapisujem '{os.path.basename(pth_file)}' (sys.path cesty)...")
        with open(pth_file, "w", encoding="utf-8") as f:
            for path in mapping.values():
                f.write(f"{path}\n")

        for name in wanted_keys - existing_keys:
            log(f"    ➕ Prelinkovaný nový modul: {name} -> {mapping[name]}")
        for name in existing_keys - wanted_keys:
            log(f"    ➖ Odlinkovaný modul: {name}")

        return added_count, removed_count

    @classmethod
    def _build_module_state(cls, mod_name: str, mod_data: dict, venv_path: str, log) -> dict:
        """
        Zostaví štruktúru 5. stavu pre jeden modul z jeho local_meta.json.
        """
        meta_path = os.path.join(mod_data['path'], "local_meta.json")
        if not os.path.exists(meta_path):
            return {"packages": [], "extras_bound": {}}

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except Exception as e:
            log(f"  ⚠️ Metadáta modulu '{mod_name}' nie je možné prečítať ({e}), ponechávam starý stav.")
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
    def _sync_apt_linker_state(cls, core, venv_path: str, all_packages_to_link: dict, log):
        """
        Zosynchronizuje 5. stav v venvhub_apt_state.json a vyčistí uvoľnené siroty.
        """
        old_bounds = AptLogic.load_linker_bounds(venv_path)

        modules_state = {}
        for mod_name, mod_data in all_packages_to_link.items():
            entry = cls._build_module_state(mod_name, mod_data, venv_path, log)
            if entry is None:
                entry = old_bounds.get(mod_name, {"packages": [], "extras_bound": {}})
            modules_state[mod_name] = entry

        log("  💾 Zapisujem záznamy modulov do 'venvhub_apt_state.json'...")
        released_packages = AptLogic.sync_linker_state(venv_path, modules_state)

        if released_packages:
            log(f"  🔻 Detekované uvoľnené balíčky po odlinkovaní ({len(released_packages)}): {', '.join(released_packages)}")
            log("  🧹 Spúšťam APT Autoremove na preverenie a vyčistenie nepoužívaných sirôt...")
            AptLogic.autoremove(core, venv_path, log, released_packages=released_packages)
        else:
            log("  ✔ Žiadne balíčky neboli uvoľnené (autoremove nie je potrebný).")

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
#----------------------------------------------------
# Súbor: core/logic/button/manager/local_packages_linker.py
#----------------------------------------------------

import os
import json
import subprocess
import re
from collections import deque
from PyQt6.QtWidgets import QMessageBox, QApplication

from core.logic.language_manager import LanguageManager
from core._path import Paths
from core.logic.vs_code_json import VSCodeIntegration
from core.logic.commands.command_factory import PackageManagerFactory

# --- CENTRÁLNY PARSER A APT JADRO ---
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.apt_ide_logic import AptIDELogic

# --- BEZRÁMOVÉ OZNAMOVACIE OKNO ---
from windows.custom_message_box import CustomMessageBox


class LocalPackagesLinker:
    """
    Centrálny manažér pre prepájanie lokálnych vývojových balíčkov (Linker) do virtuálneho prostredia.
    Všetky závislosti prechádzajú striktne cez RequirementsParser (URL, Git, tar.gz, verzie, extras).
    """

    def __init__(self, parent_window):
        self.parent = parent_window
        self.core = parent_window.core
        self.venv_path = parent_window.venv_path
        self.log_callback = parent_window.log

    def apply_changes(self, selected_items_data):
        self.log_callback(LanguageManager.get("msg_saving_changes_deps", "\n--- Ukladám zmeny a analyzujem závislosti ---"))

        self._set_ui_enabled(False)

        try:
            for item in selected_items_data:
                item['name'] = os.path.basename(item['path'])

            # 1. Rekurzívne vyriešenie závislostí cez local_meta.json
            #    (all_packages_to_link obsahuje aj tranzitívne moduly cez requires_local)
            all_packages_to_link, pip_dependencies = self._resolve_dependencies(selected_items_data)
            if all_packages_to_link is None:
                return False

            # Celá operácia (inštalácia + zápis stavu + autoremove) beží pod zámkom venvu,
            # aby sa medzi krokmi nemohla vložiť iná APT operácia (listener, install_sync...).
            with AptLogic._get_venv_lock(self.venv_path):

                # 2. Bezpečná inštalácia externých závislostí (len chýbajúce / nevyhovujúce verzie).
                #    Pri zlyhaní sa NIČ nemení - ani hooky, ani stav JSON.
                if pip_dependencies:
                    self.log_callback(LanguageManager.get("msg_detected_ext_deps", "Detekované externé závislosti: {0}").format(', '.join(pip_dependencies)))
                    if not self._install_dependencies_safely(pip_dependencies):
                        self.log_callback(AptLogic._tr(
                            "linker_install_failed_abort",
                            "❌ [Linker-APT] Inštalácia závislostí zlyhala. Prelinkovanie a stav JSON ostávajú nezmenené."
                        ))
                        return False

                # 3. Vytvorenie .pth prelinkovania a venvhub.json
                added_count, removed_count = self._manage_hook_files(all_packages_to_link)

                # 4. Zosúladenie 5. stavu v venvhub_apt_state.json
                self._sync_apt_linker_state(all_packages_to_link)

            # 5. IDE rozšírenia
            AptIDELogic.sync_ide_extensions(self.core, all_packages_to_link, self.log_callback)

            # 6. Aktualizácia VS Code / Cursor konfigurácie
            project_path = Paths.get_project_path(self.core.projects_root, self.core.active_project)
            target_paths = [pkg_data['path'] for pkg_data in all_packages_to_link.values()]

            try:
                VSCodeIntegration.sync_local_packages(project_path, target_paths, self.core.local_packages_root)
                VSCodeIntegration.sync_vscode_tasks_and_keybindings(project_path, target_paths, self.core.local_packages_root, self.log_callback)
            except Exception as e:
                self.log_callback(LanguageManager.get("msg_vscode_err", "Chyba VS Code: {0}").format(e))

            if added_count == 0 and removed_count == 0:
                self.log_callback(LanguageManager.get("msg_no_changes_local_pkgs", "ℹ️ Neboli vykonané žiadne zmeny, stav je aktuálny."))
            else:
                self.log_callback(LanguageManager.get("msg_changes_saved_local_pkgs", "✅ Zmeny úspešne uložené (Pridané: {0}, Odstránené: {1}).").format(added_count, removed_count))

            self.log_callback(LanguageManager.get("msg_done_simple", "--- Hotovo ---"))
            return True

        finally:
            self._set_ui_enabled(True)

    def _build_module_state(self, mod_name: str, mod_data: dict):
        """
        Zostaví záznam 5. stavu pre jeden modul z jeho local_meta.json.

        Returns:
            dict | None: {"packages": [...], "extras_bound": {...}}
                         alebo None, ak sa metadáta nepodarilo prečítať (volajúci vtedy zachová starý záznam).
        """
        meta_path = os.path.join(mod_data['path'], "local_meta.json")
        if not os.path.exists(meta_path):
            return {"packages": [], "extras_bound": {}}

        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except (json.JSONDecodeError, OSError, IOError) as e:
            self.log_callback(AptLogic._tr(
                "linker_meta_unreadable_keep_state",
                "⚠️ [Linker-APT] Metadáta modulu {mod} sa nedajú prečítať, ponechávam starý stav: {err}",
                mod=mod_name, err=str(e)
            ))
            return None

        base_packages = []
        extras_bound = {}

        for req_str in meta.get("requires_pip", []):
            req_clean = str(req_str).strip()
            if not req_clean:
                continue

            # PARSER KROK 1: čistý názov (podporuje Git, URL, tar.gz, verzie)
            clean_name = RequirementsParser._extract_package_name(req_clean)
            if not clean_name:
                continue

            norm_name = AptLogic._normalize(clean_name)
            base_packages.append(norm_name)

            # PARSER KROK 2: [extras] -> reálne deti z METADATA nainštalovaného balíčka
            extras_match = re.search(r"\[([^\]]+)\]", req_clean)
            if extras_match:
                extras_list = [AptLogic._normalize(e) for e in extras_match.group(1).split(",") if e.strip()]
                family = AptLogic.resolve_extras_family(self.venv_path, norm_name, extras_list)
                if family:
                    # Ak modul uvádza ten istý balíček viackrát s rôznymi extras, väzby sa zlúčia.
                    merged = set(extras_bound.get(norm_name, [])) | set(family)
                    extras_bound[norm_name] = sorted(merged)

        return {"packages": base_packages, "extras_bound": extras_bound}

    def _sync_apt_linker_state(self, all_packages_to_link: dict):
        """
        Zosynchronizuje 5. stav ('linker_packages_bound') s množinou VŠETKÝCH aktuálne prelinkovaných modulov
        (vrátane tranzitívnych cez requires_local).

        Uvoľnené balíčky sa počítajú ako rozdiel zjednotení (starý stav − nový stav), takže pokrývajú:
          - odpojené moduly,
          - zmenu requires_pip / extras pri moduloch, ktoré zostali pripojené.
        Balíčky, ktoré drží ešte niekto iný (explicit / requirements / iný modul), 'autoremove' ponechá.
        """
        old_bounds = AptLogic.load_linker_bounds(self.venv_path)

        modules_state = {}
        for mod_name, mod_data in all_packages_to_link.items():
            entry = self._build_module_state(mod_name, mod_data)
            if entry is None:
                # Nečitateľné metadáta: zachovať predchádzajúci záznam (alebo prázdny), nič neuvoľňovať.
                entry = old_bounds.get(mod_name, {"packages": [], "extras_bound": {}})
            modules_state[mod_name] = entry

        try:
            released_packages = AptLogic.sync_linker_state(self.venv_path, modules_state)
        except Exception as e:
            self.log_callback(AptLogic._tr(
                "linker_state_write_error",
                "⚠️ [Linker-APT] Chyba pri zápise stavu: {err}",
                err=str(e)
            ))
            return

        if released_packages:
            self.log_callback(AptLogic._tr("apt_autoremove_removing", "🧹 [APT: STAV 4 - AUTOREMOVE] Odstraňujem balíčky: {pkgs}", pkgs=', '.join(released_packages)))
            AptLogic.autoremove(self.core, self.venv_path, self.log_callback, released_packages=released_packages)

    def _set_ui_enabled(self, enabled):
        if hasattr(self.parent, 'btn_apply'): self.parent.btn_apply.setEnabled(enabled)
        if hasattr(self.parent, 'btn_refresh'): self.parent.btn_refresh.setEnabled(enabled)
        if hasattr(self.parent, 'table_packages'): self.parent.table_packages.setEnabled(enabled)
        QApplication.processEvents()

    def _resolve_dependencies(self, selected_items_data):
        all_to_link = {item['name']: item for item in selected_items_data}
        pip_deps = []
        queue = deque([item['name'] for item in selected_items_data])

        while queue:
            pkg_name = queue.popleft()
            pkg_data = all_to_link.get(pkg_name)
            if not pkg_data:
                continue
            meta_path = os.path.join(pkg_data['path'], "local_meta.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                
                for pip_pkg in meta.get("requires_pip", []):
                    clean_entry = str(pip_pkg).strip()
                    if clean_entry and clean_entry not in pip_deps:
                        pip_deps.append(clean_entry)

                for local_dep_name in meta.get("requires_local", []):
                    found = False
                    for existing_name, existing_data in all_to_link.items():
                        if existing_name == local_dep_name or existing_data['name'] == local_dep_name:
                            found = True
                            break
                    if not found:
                        dep_path = os.path.join(self.core.local_packages_root, local_dep_name)
                        if not os.path.isdir(dep_path):
                            msg = LanguageManager.get("msg_missing_local_dep", "Chýba lokálna závislosť: {0} pre {1}").format(local_dep_name, pkg_name)
                            self.log_callback(msg)
                            CustomMessageBox.critical(self.parent, LanguageManager.get("title_error", "Chyba"), msg)
                            return None, None
                        new_name = os.path.basename(dep_path)
                        all_to_link[new_name] = {'name': new_name, 'path': dep_path}
                        queue.append(new_name)
            except (json.JSONDecodeError, OSError, IOError) as e:
                self.log_callback(LanguageManager.get("msg_metadata_err", "Chyba v metadátach {0}: {1}").format(pkg_name, e))
        return all_to_link, pip_deps

    def _manage_hook_files(self, packages_dict):
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_packages = os.path.join(self.venv_path, site_folder, "site-packages")
        os.makedirs(site_packages, exist_ok=True)

        json_file = os.path.join(site_packages, "venvhub.json")
        pth_file = os.path.join(site_packages, "venvhub_links.pth")
        
        for old_f in ["venvhub_bootstrap.py", "venvhub_bootstrap.pth", ".venvhub_linked"]:
            old_path = os.path.join(site_packages, old_f)
            if os.path.exists(old_path):
                try: os.remove(old_path)
                except Exception: pass

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
                    try: os.remove(filepath)
                    except Exception: pass
            return added_count, removed_count

        mapping = {name: os.path.normpath(data['path']) for name, data in packages_dict.items()}
        try:
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_callback(f"Chyba pri zápise venvhub.json: {e}")

        try:
            with open(pth_file, "w", encoding="utf-8") as f:
                for path in mapping.values():
                    f.write(f"{path}\n")
        except Exception as e:
            self.log_callback(f"Chyba pri zápise venvhub_links.pth: {e}")

        return added_count, removed_count

    @staticmethod
    def _collect_installed_versions(site_pkgs_dir: str) -> dict:
        """Vráti { normalizovaný_názov: verzia } podľa priečinkov *.dist-info v site-packages."""
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

    @staticmethod
    def _version_satisfied(raw_dep: str, installed_version: str) -> bool:
        """
        Overí, či nainštalovaná verzia spĺňa špecifikátor v položke requires_pip (napr. 'pkg[x]>=2.0,<3').
        Pri URL/Git/cestách, bez špecifikátora, alebo ak knižnica 'packaging' nie je dostupná,
        sa verzia nekontroluje (platí: balíček je prítomný = vyhovuje).
        """
        try:
            dep = raw_dep.split(";")[0].strip()
            if "@" in dep or "://" in dep or dep.startswith((".", "/", "git+")):
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

    def _install_dependencies_safely(self, dependencies: list):
        """
        Nainštaluje externé závislosti.
        Každú položku analyzuje cez RequirementsParser, aby overil, či už nie je na disku
        (vrátane tar.gz, git, URL, rôznych formátov názvov, extras a verzií).

        Returns:
            bool: True ak je všetko nainštalované (alebo nebolo čo inštalovať), False pri zlyhaní.
        """
        if not dependencies:
            return True

        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_pkgs_dir = os.path.join(self.venv_path, site_folder, "site-packages")
        if not os.path.exists(site_pkgs_dir):
            site_pkgs_dir = AptLogic._get_site_packages_dir(self.venv_path)

        installed_versions = self._collect_installed_versions(site_pkgs_dir)
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
                missing_dependencies.append(raw_dep)
                continue

            # Prítomný, ale nevyhovuje požadovaná verzia
            if not self._version_satisfied(raw_dep, installed_versions.get(norm_name, "")):
                missing_dependencies.append(raw_dep)
                continue

            # Prítomný, ale s [extras] - overíme, či nechýba niektoré viazané dieťa
            extras_match = re.search(r"\[([^\]]+)\]", raw_dep)
            if extras_match:
                extras_list = [AptLogic._normalize(e) for e in extras_match.group(1).split(",") if e.strip()]
                extras_map = AptLogic.get_extras_map_from_metadata(self.venv_path, norm_name)
                has_missing_child = any(
                    child_dep not in installed_on_disk
                    for ext in extras_list
                    for child_dep in extras_map.get(ext, [])
                )
                if has_missing_child:
                    missing_dependencies.append(raw_dep)

        if not missing_dependencies:
            self.log_callback("ℹ️ Všetky externé PIP závislosti sú už vo venv nainštalované.")
            return True

        try:
            manager_type = getattr(self.core, 'package_manager', 'pip')
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, self.venv_path)
            cmd = dispatcher.get("install_multiple_exact", packages=missing_dependencies)

            CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                creationflags=CREATE_NO_WINDOW
            )

            for line in iter(process.stdout.readline, ''):
                clean_line = line.strip()
                if clean_line:
                    self.log_callback(f"  {clean_line}")
                    QApplication.processEvents()

            process.wait()
            return process.returncode == 0

        except Exception as e:
            self.log_callback(LanguageManager.get("msg_dep_install_err", "Chyba inštalácie závislostí: {0}").format(e))
            return False

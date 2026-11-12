#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/editable_service.py
# Dedikovaná LAZY služba pre správu editovateľných balíčkov (pip -e)
# VŠETKY PRÍKAZY IDÚ VÝHRADNE CEZ PackageManagerFactory DISPEČER
#----------------------------------------------------

import os
import re
import json
import subprocess
from typing import Callable

from core._path import Paths
from core.core_states import EditableOperationStatus
from core.core_bridge import CoreBridge
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.birth_certificate import BirthCertificateGenerator

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0


class EditableOperationsService:
    """
    Špecializovaná služba pre prácu s editovateľnými balíčkami (pip install -e / uv pip install -e).
    Všetky systémové príkazy skladá centrálny PackageManagerFactory dispečer.
    """

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
        """Vyparsuje z priečinka názov balíčka a zoznam jeho vlastných deklarovaných závislostí."""
        pkg_name = RequirementsParser._get_package_name_from_dir(target_path)
        deps = []

        # 1. pyproject.toml
        pyproject_path = os.path.join(target_path, "pyproject.toml")
        if os.path.isfile(pyproject_path):
            try:
                with open(pyproject_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                match_deps = re.search(r'dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if match_deps:
                    found = re.findall(r'["\']([^"\']+)["\']', match_deps.group(1))
                    deps.extend(found)
            except Exception:
                pass

        # 2. setup.py
        setup_path = os.path.join(target_path, "setup.py")
        if os.path.isfile(setup_path) and not deps:
            try:
                with open(setup_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                match_reqs = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
                if match_reqs:
                    found = re.findall(r'["\']([^"\']+)["\']', match_reqs.group(1))
                    deps.extend(found)
            except Exception:
                pass

        return pkg_name, deps

    @classmethod
    def install_editable_package(cls, core, venv_path: str, target_path: str, log_callback: Callable[[str], None] = print) -> EditableOperationStatus:
        """Inštaluje balíček cez dispečer po overení STAVU 1:1 a integrácii do APT."""
        target_norm = os.path.normpath(target_path)
        has_setup = os.path.exists(os.path.join(target_norm, "setup.py"))
        has_toml = os.path.exists(os.path.join(target_norm, "pyproject.toml"))

        if not has_setup and not has_toml:
            log_callback(f"⚠️ [EditableService] Priečinok '{os.path.basename(target_norm)}' neobsahuje setup.py ani pyproject.toml.")
            return EditableOperationStatus.INVALID_PROJECT

        # 1. INŠPEKCIA BALÍČKA
        pkg_name, internal_deps = cls._inspect_editable_dir(target_norm)
        if not pkg_name:
            pkg_name = os.path.basename(target_norm)

        norm_name = AptLogic._normalize(pkg_name)
        log_callback(f"\n📦 [EditableService] Inšpekcia balíčka: '{norm_name}' (Závislostí v kóde: {len(internal_deps)})")

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
                    log_callback(f"ℹ️ [EditableService] Balíček '{norm_name}' je definovaný v requirements.txt projektu.")
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
                installed_versions = AptLogic._collect_installed_versions(venv_path)
                missing_or_outdated = []

                for dep_spec in internal_deps:
                    clean_dep = RequirementsParser._extract_package_name(dep_spec)
                    if not clean_dep:
                        continue
                    norm_dep = AptLogic._normalize(clean_dep)
                    inst_ver = installed_versions.get(norm_dep)

                    if not inst_ver:
                        missing_or_outdated.append(f"{clean_dep} (chýba)")
                    elif not RequirementsParser.is_satisfied(dep_spec, inst_ver):
                        missing_or_outdated.append(f"{clean_dep} (na disku: {inst_ver}, požadovaná: {dep_spec})")

                if not missing_or_outdated:
                    log_callback(f"ℹ️ [EditableService] Balíček '{norm_name}' je už na tejto ceste prelinkovaný.")
                    if internal_deps:
                        log_callback(f"ℹ️ [EditableService] Všetky jeho závislosti ({len(internal_deps)}) sú vo venv nainštalované a vyhovujú.")
                    log_callback(f"✅ [EditableService] Inštalácia nie je potrebná (STAV 1:1).")

                    if not is_in_project_reqs:
                        AptLogic.mark_as_explicit(venv_path, norm_name)

                    BirthCertificateGenerator.update_venv_certificate(venv_path)
                    return EditableOperationStatus.SKIPPED
                else:
                    log_callback(f"⚡ [EditableService] Balíček '{norm_name}' je prelinkovaný, ale vyžaduje aktualizáciu závislostí:\n   -> {', '.join(missing_or_outdated)}")
            else:
                log_callback(f"⚡ [EditableService] Zistená zmena cesty balíčka '{norm_name}':\n   Pôvodná: {raw_loc}\n   Nová:    {target_norm}")

        # 4. PRÍPRAVA PRÍKAZOV VÝHRADNE CEZ DISPEČER
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        except Exception as e:
            log_callback(f"❌ [EditableService] Chyba dispečera: {e}")
            return EditableOperationStatus.ERROR

        # Build tools cez dispečer
        if manager_type == "pip":
            log_callback("🛠 [EditableService] Zabezpečujem build nástroje (setuptools, wheel)...")
            try:
                cmd_tools = dispatcher.get("install_multiple_exact", packages=["setuptools", "wheel"])
                subprocess.run(cmd_tools, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

        # Inštalačný príkaz z dispečera
        try:
            cmd = dispatcher.get("install_editable", path=target_norm)
        except Exception as e:
            log_callback(f"❌ [EditableService] Chyba pri zostavení príkazu install_editable: {e}")
            return EditableOperationStatus.ERROR

        log_callback(f"⚡ [EditableService] Spúšťam {manager_type.upper()} inštaláciu: -e {os.path.basename(target_norm)}")

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
                log_callback(f"❌ [EditableService] Inštalácia zlyhala s kódom {proc.returncode}.")
                return EditableOperationStatus.ERROR

            # 5. INTEGRÁCIA DO APT MATRIKY
            if is_in_project_reqs:
                log_callback("🔄 [EditableService] Synchronizujem stav projektu cez APT...")
                AptLogic.install_sync(core, venv_path, log_callback)
            else:
                AptLogic.mark_as_explicit(venv_path, norm_name)

            # 6. KONTROLA INTEGRITY ZÁVISLOSTÍ (Check cez dispečer)
            cmd_check = dispatcher.get("check")
            check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            status = EditableOperationStatus.SUCCESS

            if check_proc.returncode != 0:
                out_err = (check_proc.stdout + "\n" + check_proc.stderr).strip()
                log_callback(f"⚠️ [{manager_type.upper()} Check] Zistené nezrovnalosti v závislostiach:\n{out_err}")
                status = EditableOperationStatus.SUCCESS_WITH_CONFLICTS
            else:
                log_callback("✅ [EditableService] Všetky závislosti sú kompatibilné.")

            BirthCertificateGenerator.update_venv_certificate(venv_path)
            log_callback(f"✅ [EditableService] Balíček '{norm_name}' úspešne nainštalovaný v editovateľnom režime.")
            return status

        except Exception as e:
            log_callback(f"❌ [EditableService] Kritická chyba: {e}")
            return EditableOperationStatus.ERROR

    @classmethod
    def uninstall_editable_package(cls, core, venv_path: str, package_name: str, log_callback: Callable[[str], None] = print) -> EditableOperationStatus:
        """Odinštaluje balíček cez dispečer s plnou APT previerkou, scrubom a autoremove."""
        if not package_name:
            return EditableOperationStatus.SKIPPED

        norm_name = AptLogic._normalize(package_name)
        log_callback(f"\n🗑️ [EditableService] Spúšťam previerku odinštalovania balíčka: '{norm_name}'...")

        # 1. APT BEZPEČNOSTNÁ PREVIERKA (GUARD)
        is_safe, err_msg = AptLogic.verify_uninstall_safety(venv_path, core, norm_name)
        if not is_safe:
            log_callback(f"🛑 [EditableService] STOP: {err_msg}")
            return EditableOperationStatus.BLOCKED

        # 2. ZBER ZÁVISLOSTÍ PRED ZMAZANÍM
        manager_type = getattr(core, "package_manager", "pip")
        released_reqs = AptLogic.get_requires_for_package(venv_path, norm_name, manager_type)

        # 3. ODINŠTALÁCIA CEZ DISPEČER
        try:
            dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
            cmd = dispatcher.get("uninstall", package_name=norm_name)
        except Exception as e:
            log_callback(f"❌ [EditableService] Chyba dispečera pri zostavení uninstall: {e}")
            return EditableOperationStatus.ERROR

        log_callback(f"🗑️ [EditableService] Fyzicky odstraňujem '{norm_name}' ({manager_type.upper()})...")

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
                log_callback(f"❌ [EditableService] Odinštalácia zlyhala s kódom {proc.returncode}.")
                return EditableOperationStatus.ERROR

            # 4. SCRUB ZO STAVU A AUTOREMOVE SIROT
            kids = AptLogic.scrub_package_completely(venv_path, norm_name)
            all_released = list(dict.fromkeys(released_reqs + kids))

            if all_released:
                log_callback(f"🧹 [EditableService] Preverujem uvoľnené závislosti: {', '.join(all_released)}")
                AptLogic.autoremove(core, venv_path, log_callback, released_packages=all_released)

            BirthCertificateGenerator.update_venv_certificate(venv_path)
            log_callback(f"✅ [EditableService] Balíček '{norm_name}' a jeho nepoužívané závislosti boli úspešne odstránené.")
            return EditableOperationStatus.SUCCESS

        except Exception as e:
            log_callback(f"❌ [EditableService] Kritická chyba: {e}")
            return EditableOperationStatus.ERROR
#----------------------------------------
# Súbor: core/logic/sluzby/pack_inst_unis.py
#----------------------------------------

import os
import re
import subprocess
from typing import Callable

from core._path import Paths
from core.core_states import PackageOperationStatus  # <--- IMPORT STAVU
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.language_manager import LanguageManager
from core.logic.birth_certificate import BirthCertificateGenerator

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

class PackageOperationsService:
    """
    Čistá služba na inštaláciu a odinštaláciu balíčkov.
    Vracia striktné stavové Enumy (PackageOperationStatus).
    """

    @staticmethod
    def install_packages(core, venv_path: str, packages: list[str], log_callback: Callable[[str], None] = print) -> PackageOperationStatus:
        """Nainštaluje balíčky a vráti presný stavový objekt."""
        if not packages:
            return PackageOperationStatus.SKIPPED

        manager_type = getattr(core, "package_manager", "pip")
        msg_start = LanguageManager.get("pack_inst_start", "\n📦 [PackService] Spúšťam inštaláciu {0} balíčkov cez {1}...")
        log_callback(msg_start.format(len(packages), manager_type.upper()))

        # 1. PARSOVANIE A KONTROLA NUTNOSTI
        parsed_items = []
        for pkg_str in packages:
            clean_name = RequirementsParser._extract_package_name(pkg_str)
            if not clean_name:
                continue
            norm_name = AptLogic._normalize(clean_name)
            extras = [AptLogic._normalize(e) for e in re.findall(r"\[([^\]]+)\]", pkg_str)] if "[" in pkg_str else []
            parsed_items.append((norm_name, pkg_str, extras))

        # Kontrola, či už nie sú nainštalované
        can_skip, skip_msg = AptLogic.check_install_necessity(venv_path, core, parsed_items, log_callback)
        if can_skip:
            log_callback(f"{skip_msg}")
            log_callback(LanguageManager.get("pack_inst_skip", "✅ [PackService] Nič nové nie je potrebné inštalovať."))
            return PackageOperationStatus.SKIPPED

        # 2. INŠTALÁCIA
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("install_multiple_exact", packages=packages)

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=CREATE_NO_WINDOW
            )
            for line in iter(process.stdout.readline, ''):
                clean_l = line.strip()
                if clean_l: log_callback(f"  {clean_l}")
            process.wait()

            if process.returncode != 0:
                log_callback(LanguageManager.get("pack_inst_failed", "❌ [PackService] Inštalácia zlyhala (kód {0}).").format(process.returncode))
                return PackageOperationStatus.ERROR

            # 3. ZÁPIS DO STAVU
            for norm_name, raw_spec, extras in parsed_items:
                if AptLogic.is_subpackage_or_managed(venv_path, core, norm_name):
                    log_callback(LanguageManager.get("pack_inst_managed", "ℹ️ [PackService] '{0}' je podbalíček/managed. Neoznačujem ho ako explicit.").format(norm_name))
                else:
                    AptLogic.mark_as_explicit(venv_path, norm_name)
                if extras:
                    AptLogic.resolve_and_bind_extras(venv_path, norm_name, extras, context="explicit")

            # 4. KONTROLA INTEGRITY (Pip/UV Check)
            check_success = PackageOperationsService._verify_and_autofix_dependencies(venv_path, manager_type, dispatcher, log_callback)

            BirthCertificateGenerator.update_venv_certificate(venv_path)

            if check_success:
                log_callback(LanguageManager.get("pack_inst_ok", "✅ [PackService] Inštalácia a aktualizácia stavov úspešne dokončená."))
                return PackageOperationStatus.SUCCESS
            else:
                log_callback(LanguageManager.get("pack_inst_ok_with_warn", "⚠️ [PackService] Inštalácia prebehla, ale závislosti vykazujú konflikty."))
                return PackageOperationStatus.SUCCESS_WITH_CONFLICTS

        except Exception as e:
            log_callback(f"❌ [PackService] Kritická chyba inštalácie: {e}")
            return PackageOperationStatus.ERROR

    @staticmethod
    def uninstall_packages(core, venv_path: str, packages: list[str], log_callback: Callable[[str], None] = print) -> PackageOperationStatus:
        """Odinštaluje balíčky a vráti presný stavový objekt."""
        if not packages:
            return PackageOperationStatus.SKIPPED

        manager_type = getattr(core, "package_manager", "pip")
        log_callback(LanguageManager.get("pack_uninst_start", "\n🗑️ [PackService] Spúšťam odinštaláciu {0} balíčkov...").format(len(packages)))

        # 1. BEZPEČNOSTNÁ PREVIERKA (GUARD)
        norm_packages = []
        for pkg_str in packages:
            clean_name = RequirementsParser._extract_package_name(pkg_str)
            if not clean_name: continue
            norm_name = AptLogic._normalize(clean_name)
            norm_packages.append(norm_name)

            is_safe, err_msg = AptLogic.verify_uninstall_safety(venv_path, core, norm_name)
            if not is_safe:
                log_callback(f"🛑 [PackService] STOP: {err_msg}")
                return PackageOperationStatus.BLOCKED

        # 2. ZBER DÁT A ODINŠTALÁCIA
        released_reqs = []
        for pkg in norm_packages:
            released_reqs.extend(AptLogic.get_requires_for_package(venv_path, pkg, manager_type))

        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("uninstall_multiple", packages=norm_packages)

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=CREATE_NO_WINDOW
            )
            for line in iter(process.stdout.readline, ''):
                clean_l = line.strip()
                if clean_l: log_callback(f"  {clean_l}")
            process.wait()

            if process.returncode != 0:
                log_callback(LanguageManager.get("pack_uninst_failed", "❌ [PackService] Odinštalácia zlyhala (kód {0}).").format(process.returncode))
                return PackageOperationStatus.ERROR

            # 3. SCRUB A AUTOREMOVE
            for pkg in norm_packages:
                released_reqs.extend(AptLogic.scrub_package_completely(venv_path, pkg))

            unique_released = list(dict.fromkeys(released_reqs))
            if unique_released:
                AptLogic.autoremove(core, venv_path, log_callback, released_packages=unique_released)

            BirthCertificateGenerator.update_venv_certificate(venv_path)

            log_callback(LanguageManager.get("pack_uninst_ok", "✅ [PackService] Odinštalácia a vyčistenie systému dokončené."))
            return PackageOperationStatus.SUCCESS

        except Exception as e:
            log_callback(f"❌ [PackService] Kritická chyba odinštalácie: {e}")
            return PackageOperationStatus.ERROR

    @staticmethod
    def _verify_and_autofix_dependencies(venv_path: str, manager_type: str, dispatcher, log_callback: Callable[[str], None]) -> bool:
        # Pôvodný kód overenia, ktorý vracia True (všetko OK) alebo False (Konflikt)
        # (Zostáva rovnaký ako v predchádzajúcej odpovedi)
        msg_check = LanguageManager.get("apt_checking_deps", "--- Vykonávam {0} kontrolu závislostí... ---").format(manager_type.upper())
        log_callback(msg_check)

        cmd_check = dispatcher.get("check")
        check_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        
        if check_proc.returncode == 0:
            log_callback(LanguageManager.get("apt_deps_compatible", "✅ Všetky závislosti sú kompatibilné."))
            return True

        out_err = (check_proc.stdout + "\n" + check_proc.stderr).strip()
        log_callback(LanguageManager.get("apt_deps_conflicts", "⚠️ [{0} Check] Zistené nezrovnalosti v závislostiach:\n{1}").format(manager_type.upper(), out_err))

        if manager_type == "uv":
            conflicts = list(set(re.findall(r"requires\s+`([^`]+)`", out_err)))
            if conflicts:
                log_callback(LanguageManager.get("uv_fixing_downgrade", "Pokúšam sa o automatickú opravu..."))
                cmd_fix = dispatcher.get("install_multiple_exact", packages=conflicts)
                fix_proc = subprocess.Popen(cmd_fix, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=CREATE_NO_WINDOW)
                for line in iter(fix_proc.stdout.readline, ''):
                    clean_l = line.strip()
                    if clean_l: log_callback(f"  {clean_l}")
                fix_proc.wait()
                
                if fix_proc.returncode == 0:
                    check2_proc = subprocess.run(cmd_check, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
                    if check2_proc.returncode == 0 or "All installed packages are compatible" in check2_proc.stdout:
                        log_callback(LanguageManager.get("uv_fix_ok", "✅ Všetky konflikty boli úspešne vyriešené."))
                        return True
            log_callback(LanguageManager.get("uv_fix_error_manual", "⚠️ Automatická oprava zlyhala. Opravte závislosti manuálne."))
            return False
            
        return False
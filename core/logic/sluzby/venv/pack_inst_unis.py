#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/pack_inst_unis.py
#----------------------------------------------------

import os
import subprocess
from core.core_states import PackageOperationStatus
from core.core_bridge import CoreBridge
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.commands.command_factory import PackageManagerFactory

class PackageOperationsService:
    """
    Služba pre manuálnu inštaláciu a odinštalovanie PyPI balíčkov.
    Implementuje APT logovanie napojené na CoreBridge prekladový systém.
    """

    @classmethod
    def install_packages(cls, core, venv_path: str, packages: list[str], log_callback) -> PackageOperationStatus:
        log_callback("\n" + "="*50)
        
        msg_start = CoreBridge.translate("pack_start_install", "📦 [PackService] ŠTART INŠTALÁCIE: {0}").format(', '.join(packages))
        log_callback(msg_start)
        
        # --- 1. APT STAV 1:1 DIFF KONTROLA ---
        msg_diff = CoreBridge.translate("pack_apt_diff", "🔍 [APT: STAV 1 - DIFF] Overujem požiadavku voči requirements.txt a prostrediu...")
        log_callback(msg_diff)
        
        # Pripravíme zoznam pre AptLogic (očakáva tuple: (názov, spec, extras))
        items_to_check = []
        for pkg in packages:
            clean_name = AptLogic._extract_package_name(pkg)
            if clean_name:
                items_to_check.append((clean_name, pkg, []))

        can_skip, skip_msg = AptLogic.check_install_necessity(venv_path, core, items_to_check, log_callback)
        if can_skip:
            if skip_msg:
                log_callback(skip_msg)
            
            msg_skipped = CoreBridge.translate("pack_apt_skipped", "✅ [APT: STAV 1] Všetky požiadavky sú už splnené. Inštalácia sa preskakuje.")
            log_callback(msg_skipped)
            return PackageOperationStatus.SKIPPED

        # --- 1.5 OCHRANA PRED PREPÍSANÍM REQUIREMENTS.TXT (UPOZORNENIE NA OVERRIDE) ---
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
                        # Overíme, či používateľ reálne mení verziu (zadal ==, <, > atď.)
                        is_version_request = any(c in raw_spec for c in ["==", "<", ">", "~="])
                        
                        if is_version_request and raw_spec != req_spec:
                            warn1 = CoreBridge.translate("pack_warn_req1", "⚠️ UPOZORNENIE: '{0}' je v requirements.txt definovaný ako '{1}'.").format(clean_name, req_spec)
                            warn2 = CoreBridge.translate("pack_warn_req2", "   Inštalujete '{0}' ako DOČASNÝ override pre testovanie.").format(raw_spec)
                            warn3 = CoreBridge.translate("pack_warn_req3", "   Pri synchronizácii 'requirements.txt' alebo Update sa vráti späť.")
                            
                            log_callback(warn1)
                            log_callback(warn2)
                            log_callback(warn3)
        except Exception:
            pass # Ak by zlyhalo parsovanie, nezhodíme kvôli tomu inštaláciu

        # --- 2. FYZICKÁ INŠTALÁCIA ---
        msg_install = CoreBridge.translate("pack_apt_install", "🚀 [APT: STAV 2 - INSTALL] Spúšťam fyzickú inštaláciu...")
        log_callback(msg_install)
        
        manager_type = getattr(core, "package_manager", "pip")
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("install_multiple_exact", packages=packages)

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW
            )
            for line in process.stdout:
                log_callback(f"  {line.strip()}")
            process.wait()

            if process.returncode != 0:
                err_code = CoreBridge.translate("pack_apt_err_code", "❌ [APT: CHYBA] Inštalátor zlyhal (kód {0}). Stav JSON ostáva nezmenený.").format(process.returncode)
                log_callback(err_code)
                return PackageOperationStatus.ERROR

        except Exception as e:
            err_crash = CoreBridge.translate("pack_apt_err_crash", "❌ [APT: KRITICKÁ CHYBA] Subproces havaroval: {0}").format(str(e))
            log_callback(err_crash)
            return PackageOperationStatus.ERROR

        # --- 3. APT OCHRANA A ZÁPIS DO JSONU ---
        msg_guard = CoreBridge.translate("pack_apt_guard", "📝 [APT: STAV 3 - GUARD] Zapisujem zmeny do venvhub_apt_state.json...")
        log_callback(msg_guard)
        
        for clean_name, raw_spec, extras in items_to_check:
            is_version_change = any(c in raw_spec for c in ["==", "<", ">"])
            
            if is_version_change and AptLogic.is_subpackage_or_managed(venv_path, core, clean_name):
                msg_sub = CoreBridge.translate("pack_apt_subpkg_updated", "ℹ️ [APT: GUARD] Verzia podbalíčka '{0}' upravená. Zostáva ako automatická závislosť (nie explicit).").format(clean_name)
                log_callback(msg_sub)
            else:
                AptLogic.mark_as_explicit(venv_path, clean_name)
                msg_explicit = CoreBridge.translate("pack_apt_explicit_registered", "✅ [APT] Balíček '{0}' zaregistrovaný ako manuálny (explicit).").format(clean_name)
                log_callback(msg_explicit)

        return PackageOperationStatus.SUCCESS

    @classmethod
    def uninstall_packages(cls, core, venv_path: str, packages: list[str], log_callback) -> PackageOperationStatus:
        log_callback("\n" + "="*50)
        
        msg_start_un = CoreBridge.translate("pack_start_uninstall", "🗑️ [PackService] ŠTART ODINŠTALÁCIE: {0}").format(', '.join(packages))
        log_callback(msg_start_un)

        released_reqs = []

        # --- 1. KONTROLA BEZPEČNOSTI PRED ZMAZANÍM ---
        msg_safety = CoreBridge.translate("pack_apt_safety_check", "🛡️ [APT: KONTROLA BEZPEČNOSTI] Overujem, či je bezpečné balíček zmazať...")
        log_callback(msg_safety)
        
        for pkg in packages:
            clean_name = AptLogic._extract_package_name(pkg)
            if not clean_name: continue

            is_safe, err_msg = AptLogic.verify_uninstall_safety(venv_path, core, clean_name)
            if not is_safe:
                msg_blocked = CoreBridge.translate("pack_apt_blocked", "🛑 [APT: BLOCKED] {0}").format(err_msg)
                log_callback(msg_blocked)
                return PackageOperationStatus.BLOCKED
            
            # Zistíme, čo tento balíček drží pri živote (aby sme to potom mohli hodiť do autoremove)
            released_reqs.extend(AptLogic.get_requires_for_package(venv_path, clean_name, core.package_manager))

        # --- 2. FYZICKÁ ODINŠTALÁCIA ---
        msg_run_un = CoreBridge.translate("pack_apt_uninstall", "🚀 Spúšťam fyzickú odinštaláciu...")
        log_callback(msg_run_un)
        
        manager_type = getattr(core, "package_manager", "pip")
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)
        cmd = dispatcher.get("uninstall_multiple", packages=packages)

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, encoding='utf-8', errors='replace', creationflags=CREATE_NO_WINDOW
            )
            for line in process.stdout:
                log_callback(f"  {line.strip()}")
            process.wait()

            if process.returncode != 0:
                err_un_code = CoreBridge.translate("pack_apt_uninst_err_code", "❌ [APT: CHYBA] Odinštalácia zlyhala (kód {0}). Stav JSON ostáva nezmenený.").format(process.returncode)
                log_callback(err_un_code)
                return PackageOperationStatus.ERROR

        except Exception as e:
            err_crash = CoreBridge.translate("pack_apt_err_crash", "❌ [APT: KRITICKÁ CHYBA] Subproces havaroval: {0}").format(str(e))
            log_callback(err_crash)
            return PackageOperationStatus.ERROR

        # --- 3. VYHLADENIE ZO STAVU (SCRUB) ---
        msg_scrub = CoreBridge.translate("pack_apt_scrubbing", "🧹 [APT] Vyhladzujem balíček z registrov venvhub_apt_state.json...")
        log_callback(msg_scrub)
        
        for pkg in packages:
            clean_name = AptLogic._extract_package_name(pkg)
            if clean_name:
                kids = AptLogic.scrub_package_completely(venv_path, clean_name)
                released_reqs.extend(kids)

        # --- 4. AUTOREMOVE SIRÔT ---
        msg_auto = CoreBridge.translate("pack_apt_autoremove", "⚙️ [APT: STAV 4 - AUTOREMOVE] Kontrolujem osirelé závislosti...")
        log_callback(msg_auto)
        
        AptLogic.autoremove(core, venv_path, log_callback, released_packages=released_reqs)

        msg_done = CoreBridge.translate("pack_apt_uninst_done", "✅ [APT] Odinštalácia a čistenie úspešne dokončené.")
        log_callback(msg_done)
        return PackageOperationStatus.SUCCESS
#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/package_update.py
# NENORMÁLNA LOGIKA PRE UPDATE: Plne integrovaná s APT jadrom.
#----------------------------------------------------

import os
import json
import subprocess
from typing import Callable, Optional
from core._path import Paths
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.sluzby.venv.pack_operation_state import AptState, AptStatusEvent


class PackageUpdateService:
    """
    Inteligentná služba pre hromadnú aktualizáciu balíčkov.
    Namiesto "slepého" pip upgrade aplikuje prísne pravidlá APT jadra:
    1. Parser: Zistí, čo je pripnuté v requirements.txt (==) a zakáže to aktualizovať.
    2. Linker & Pip-e: Chráni lokálne a vývojové balíčky pred prepísaním.
    3. Install Sync: Na záver odovzdá riadenie AptLogic.install_sync, ktorý dorieši
       nové prídavky, zmaže výpadky (autoremove) a skontroluje stromy závislostí.
    """

    @classmethod
    def update_all(
        cls, 
        venv_path: str, 
        core=None, 
        manager_type: str = "pip", 
        log_callback: Optional[Callable[[str], None]] = None,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> bool:
        if log_callback is None:
            log_callback = print

        # KĽÚČOVÁ POISTKA (proti strate parametra)
        if core is None:
            err_core = LanguageBridge.translate("err_core_missing", "❌ KRITICKÁ CHYBA: Chýba objekt 'core'. Aktualizácia prerušená.")
            log_callback(err_core)
            if status_callback:
                status_callback(AptStatusEvent(
                    state=AptState.FAILED, 
                    message=err_core, 
                    data={"reason": "core_missing"}
                ))
            return False

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        dispatcher = PackageManagerFactory.get_dispatcher(manager_type, venv_path)

        log_callback(LanguageBridge.translate("update_apt_start", "\n🔄 [APT UPDATE] Inicializujem inteligentnú aktualizáciu..."))

        # ==========================================================
        # KROK 1: Aktualizácia balíčkovacieho jadra (pip/uv)
        # ==========================================================
        msg_step1 = LanguageBridge.translate("update_step1", "📦 Krok 1: Aktualizácia balíčkovacieho jadra...")
        log_callback(msg_step1)
        if status_callback:
            status_callback(AptStatusEvent(
                state=AptState.INSTALLING,
                message=msg_step1,
                progress_pct=5,
                data={"target": manager_type}
            ))

        subprocess.run(dispatcher.get("upgrade_pip"), capture_output=True, creationflags=CREATE_NO_WINDOW)

        # ==========================================================
        # KROK 2: Získanie zoznamu zastaraných balíčkov
        # ==========================================================
        msg_step2 = LanguageBridge.translate("update_step2", "🔍 Krok 2: Hľadám zastarané balíčky na webe...")
        log_callback(msg_step2)
        if status_callback:
            status_callback(AptStatusEvent(
                state=AptState.ANALYZING,
                message=msg_step2,
                progress_pct=15
            ))

        res_outdated = subprocess.run(
            dispatcher.get("list_outdated_json"), 
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
        )
        
        if res_outdated.returncode != 0:
            err_outdated = LanguageBridge.translate("update_err_outdated", "❌ Chyba pri hľadaní aktualizácií:\n{0}").format(res_outdated.stderr.strip())
            log_callback(err_outdated)
            if status_callback:
                status_callback(AptStatusEvent(
                    state=AptState.FAILED,
                    message=err_outdated,
                    data={"stderr": res_outdated.stderr}
                ))
            return False

        try:
            outdated_data = json.loads(res_outdated.stdout)
        except json.JSONDecodeError:
            outdated_data = []

        if not outdated_data:
            log_callback(LanguageBridge.translate("update_all_latest", "✅ Všetky balíčky sú momentálne na najnovších verziách."))
            # APT SYNC: Zbehneme ho aj tak! Možno užívateľ niečo zmazal/pridal do requirements.txt
            log_callback(LanguageBridge.translate("update_step3_sync", "\n🧹 Krok 3: Spúšťam APT synchronizáciu (Diff, Autoremove, Check)..."))
            return AptLogic.install_sync(
                core=core, 
                venv_path=venv_path, 
                log_callback=log_callback,
                status_callback=status_callback
            )

        outdated_pkgs = [AptLogic._normalize(item['name']) for item in outdated_data]
        allowed_to_upgrade = set(outdated_pkgs)

        # Evidencia chránených balíčkov pre status payload
        protected_by_reqs = []
        protected_by_linker = []
        protected_by_pipe = []

        # ==========================================================
        # KROK 3: APT OCHRANNÉ FILTRE (Parser, Linker, Pip-e)
        # ==========================================================
        log_callback(LanguageBridge.translate("update_step3", "🧠 Krok 3: Aplikujem APT pravidlá a reštrikcie..."))
        
        project_path = Paths.get_project_path(core.projects_root, core.active_project)
        req_file = Paths.get_requirements_txt_path(project_path)

        # A) Ochrana striktne pripnutých balíčkov v requirements.txt (napr. pkg==1.0)
        pip_e_root = getattr(core, 'pip_e_packages_root', '')
        req_specs = RequirementsParser.parse_specs(req_file, pip_e_root=pip_e_root) if os.path.exists(req_file) else {}

        for req_norm, spec in req_specs.items():
            # Ak je v súbore explicitne '=' alebo '<', nesmieme to nasilu upgradnúť na 'latest'
            if ("==" in spec or "<" in spec) and not spec.startswith(("-e", "git+", "http")):
                if req_norm in allowed_to_upgrade:
                    allowed_to_upgrade.remove(req_norm)
                    protected_by_reqs.append((req_norm, spec))
                    msg_prot_req = LanguageBridge.translate("update_protect_req", "   🛡️ Ochrana: Preskakujem '{0}' (Verzia je pevne limitovaná v requirements.txt: {1})").format(req_norm, spec)
                    log_callback(msg_prot_req)

        # B) Ochrana Linker modulov (5. stav venvhub_apt_state.json)
        with AptLogic._get_venv_lock(venv_path):
            linker_pkgs = AptLogic.get_all_linker_required_packages(venv_path)
            for l_pkg in linker_pkgs:
                if l_pkg in allowed_to_upgrade:
                    allowed_to_upgrade.remove(l_pkg)
                    protected_by_linker.append(l_pkg)
                    msg_prot_link = LanguageBridge.translate("update_protect_linker", "   🔗 Ochrana: Preskakujem '{0}' (Spravované lokálnym Linker vývojovým modulom)").format(l_pkg)
                    log_callback(msg_prot_link)

        # C) Ochrana editovateľných balíčkov (pip -e)
        editable_pkgs = AptLogic.get_editable_packages(venv_path, manager_type)
        for e_pkg in editable_pkgs:
            e_name = AptLogic._normalize(e_pkg.get("name", ""))
            if e_name in allowed_to_upgrade:
                allowed_to_upgrade.remove(e_name)
                protected_by_pipe.append(e_name)
                msg_prot_pipe = LanguageBridge.translate("update_protect_pipe", "   ✏️ Ochrana: Preskakujem '{0}' (Lokálny editovateľný balíček pip -e)").format(e_name)
                log_callback(msg_prot_pipe)

        # ==========================================================
        # KROK 4: Bezpečná aktualizácia povolených balíčkov
        # ==========================================================
        if allowed_to_upgrade:
            msg_step4 = LanguageBridge.translate("update_step4", "🚀 Krok 4: Sťahujem a aktualizujem {0} povolených balíčkov: {1}").format(
                len(allowed_to_upgrade), ', '.join(sorted(allowed_to_upgrade))
            )
            log_callback(msg_step4)

            if status_callback:
                status_callback(AptStatusEvent(
                    state=AptState.INSTALLING,
                    message=msg_step4,
                    progress_pct=35,
                    data={
                        "upgrading_packages": sorted(list(allowed_to_upgrade)),
                        "protected_by_requirements": protected_by_reqs,
                        "protected_by_linker": protected_by_linker,
                        "protected_by_pipe": protected_by_pipe
                    }
                ))
            
            cmd_upgrade = dispatcher.get("upgrade_multiple", packages=list(allowed_to_upgrade))

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"

            proc = subprocess.Popen(
                cmd_upgrade, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True, 
                encoding='utf-8', 
                bufsize=1, 
                env=env, 
                creationflags=CREATE_NO_WINDOW
            )
            for line in proc.stdout:
                log_callback(f"  {line.strip()}")
            proc.wait()

            if proc.returncode != 0:
                err_download = LanguageBridge.translate("update_err_download", "❌ Chyba počas sťahovania aktualizácií.")
                log_callback(err_download)
                if status_callback:
                    status_callback(AptStatusEvent(
                        state=AptState.FAILED,
                        message=err_download,
                        data={"exit_code": proc.returncode}
                    ))
                return False
        else:
            log_callback(LanguageBridge.translate("update_all_protected", "ℹ️ Všetky zastarané balíčky sú chránené APT pravidlami. Sťahovanie preskočené."))

        # ==========================================================
        # KROK 5: FINÁLNA APT SYNCHRONIZÁCIA (Magic Krok)
        # ==========================================================
        log_callback(LanguageBridge.translate("update_step5", "\n🧹 Krok 5: Odovzdávam riadenie APT jadru (Diff, Autoremove a Integrálny Check)..."))
        
        return AptLogic.install_sync(
            core=core, 
            venv_path=venv_path, 
            log_callback=log_callback, 
            req_file_path=req_file,
            status_callback=status_callback
        )
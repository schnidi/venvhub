#----------------------------------------------------
# Súbor: core/logic/sluzby/venv/pack_requr.py
# Dedikovaná LAZY služba pre synchronizáciu requirements.txt
#----------------------------------------------------

import os
from typing import Callable, Optional

from core._path import Paths
from core.logic.sluzby.language_bridge import LanguageBridge
from core.core_states import RequirementsOperationStatus
from core.logic.sluzby.venv.pack_operation_state import AptState, AptStatusEvent
from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.requirements_parser import RequirementsParser
from core.logic.sluzby.path_normalizer import PathNormalizer
from core.logic.birth_certificate import BirthCertificateGenerator


class RequirementsService:
    """
    Služba pre správu a synchronizáciu súboru requirements.txt s virtuálnym prostredím.
    Vracia oficiálny stavový Enum RequirementsOperationStatus.
    """

    @classmethod
    def _create_rich_status_handler(cls, log_callback: Callable[[str], None]) -> Callable[[AptStatusEvent], None]:
        def _handler(event: AptStatusEvent):
            if event.state == AptState.EXTRAS_SYNCING:
                parent = event.get("parent", "?")
                req_extras = event.get("requested_extras", [])
                children = event.get("resolved_children", [])
                ctx = event.get("context", "requirements")

                t_title = LanguageBridge.translate("pack_tree_extras_detected", "🧬 [EXTRAS DETEKCIA ({0})]").format(ctx)
                t_parent = LanguageBridge.translate("pack_tree_parent_pkg", "Rodičovský balíček: {0}").format(parent)
                t_req_ext = LanguageBridge.translate("pack_tree_extras_requested", "Požadované prívlastky: [{0}]").format(", ".join(req_extras))
                kids_str = ", ".join(children) if children else LanguageBridge.translate("pack_tree_no_extra_children", "žiadne ďalšie")
                t_children = LanguageBridge.translate("pack_tree_children_bound", "Naviazané deti na disku: {0}").format(kids_str)

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_parent}")
                log_callback(f"   ├─ {t_req_ext}")
                log_callback(f"   └─ {t_children}")

            elif event.state == AptState.REMOVING_ORPHANS:
                orphans = event.get("orphans", [])
                mgr = event.get("manager", "PIP")

                t_title = LanguageBridge.translate("pack_tree_autoremove_detail", "🧹 [DETAIL AUTOREMOVE ({0})]").format(mgr)
                t_count = LanguageBridge.translate("pack_tree_orphans_count", "Počet nájdených sirôt na zmazanie: {0}").format(len(orphans))
                t_list = LanguageBridge.translate("pack_tree_orphans_list", "Zoznam: {0}").format(", ".join(orphans))

                log_callback(f"   ┌─ {t_title}")
                log_callback(f"   ├─ {t_count}")
                log_callback(f"   └─ {t_list}")

            elif event.state == AptState.INSTALLING:
                pkgs_queue = event.get("packages_queue", [])
                if len(pkgs_queue) > 1:
                    t_queue = LanguageBridge.translate("pack_tree_install_queue", "📋 Fronta balíčkov na inštaláciu ({0}):").format(len(pkgs_queue))
                    log_callback(f"   ┌─ {t_queue}")
                    for p in pkgs_queue:
                        log_callback(f"   │  • {p}")
                    log_callback("   └───────────────────────────────")

        return _handler

    @classmethod
    def sync_requirements(
        cls, 
        core, 
        venv_path: str, 
        project_root: str = "",
        req_file_path: str = None,
        log_callback: Callable[[str], None] = print,
        status_callback: Optional[Callable[[AptStatusEvent], None]] = None
    ) -> RequirementsOperationStatus:
        rich_handler = cls._create_rich_status_handler(log_callback)

        def _unified_status(ev: AptStatusEvent):
            rich_handler(ev)
            if status_callback:
                try:
                    status_callback(ev)
                except Exception:
                    pass

        # 1. ZISTENIE CESTY K SÚBORU
        if not req_file_path:
            if not project_root:
                project_root = Paths.get_project_path(
                    getattr(core, "projects_root", ""), 
                    getattr(core, "active_project", "")
                )
            req_file_path = Paths.get_requirements_txt_path(project_root)

        if not os.path.exists(req_file_path):
            err_msg = LanguageBridge.translate("err_req_not_found", "CHYBA: Súbor 'requirements.txt' nebol nájdený: {0}").format(req_file_path)
            log_callback(err_msg)
            _unified_status(AptStatusEvent(
                state=AptState.FAILED,
                message=err_msg,
                data={"reason": "file_not_found", "path": req_file_path}
            ))
            return RequirementsOperationStatus.FILE_NOT_FOUND

        log_callback("\n" + "=" * 55)
        log_callback(LanguageBridge.translate(
            "req_sync_start", 
            "📜 [RequirementsService] ŠTART SYNCHRONIZÁCIE: {0}"
        ).format(os.path.basename(req_file_path)))

        # 2. SANITIZÁCIA CIEST V SÚBORE
        PathNormalizer.sanitize_requirements_file(req_file_path)

        # 3. SPUSTENIE STAVOVÉHO CYKLU APT
        success = AptLogic.install_sync(
            core=core,
            venv_path=venv_path,
            log_callback=log_callback,
            req_file_path=req_file_path,
            status_callback=_unified_status
        )

        # 4. AKTUALIZÁCIA RODNÉHO LISTU PROSTREDIA
        if success:
            BirthCertificateGenerator.update_venv_certificate(venv_path)
            log_callback(LanguageBridge.translate("req_sync_success", "✅ [RequirementsService] Súbor requirements.txt a prostredie sú plne zosynchronizované."))
            _unified_status(AptStatusEvent(
                state=AptState.COMPLETED_SUCCESS,
                message="",
                progress_pct=100,
                data={"path": req_file_path}
            ))
            return RequirementsOperationStatus.SUCCESS
        else:
            log_callback(LanguageBridge.translate("req_sync_failed", "❌ [RequirementsService] Synchronizácia požiadaviek zlyhala."))
            return RequirementsOperationStatus.ERROR
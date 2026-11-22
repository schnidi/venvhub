#----------------------------------------------------
# Súbor: core/core_bridge.py
# Centrálny Most (Bridge / Service Locator)
# Prepája nízkoúrovňovú logiku s dátovými stavmi jadra.
#----------------------------------------------------

from typing import Any
from core.core_states import (
    CoreService, 
    IDEType, 
    IDEStatus, 
    IDEProfileMode, 
    LanguageStatus, 
    PythonOrigin, 
    PythonPipStatus, 
    PythonDetectorStatus, 
    UVStatus
)
from core.logic.vscode_user.sluzby.ide_paths import IDEPaths
from core.logic.sluzby.language_bridge import LanguageBridge


class CoreBridge:
    """Centrálny register a most jadra."""

    _services: dict[CoreService, Any] = {}

    @classmethod
    def register_service(cls, key: CoreService, service_instance: Any) -> None:
        """Zaregistruje inštanciu alebo triedu služby do jadra."""
        cls._services[key] = service_instance

    @classmethod
    def get_service(cls, key: CoreService) -> Any:
        """Vráti zaregistrovanú službu podľa kľúča."""
        return cls._services.get(key)

    # =========================================================================
    # AUDIT A DIAGNOSTIKA
    # =========================================================================
    
    @classmethod
    def audit_services(cls) -> list[str]:
        """Vráti zoznam všetkých aktívne zaregistrovaných služieb v jadre."""
        print("\n--- [CoreBridge AUDIT ŠTART] ---")
        registered = []

        # Zoznam služieb, ktoré sú zámerne typu LAZY (načítavajú sa na požiadanie)
        lazy_services = {
            CoreService.PACKAGE_UPDATE, 
            CoreService.PACKAGE_OPERATIONS, 
            CoreService.EDITABLE_OPERATIONS,
            CoreService.LOCAL_LINKER,
            CoreService.PORTABILITY_GUARD,
            CoreService.PYTHON_DETECTOR,
            CoreService.UV_DETECTOR,
            CoreService.REQUIREMENTS_SYNC,
        }
        
        for service_enum in CoreService:
            if service_enum in cls._services:
                registered.append(service_enum.value)
                print(f"[CoreBridge] ✅ Služba '{service_enum.value}' je pripravená.")
            elif service_enum in lazy_services:
                registered.append(service_enum.value)
                print(f"[CoreBridge] ⚡ Služba '{service_enum.value}' je pripravená (LAZY).")
            else:
                print(f"[CoreBridge] ❌ POZOR: Služba '{service_enum.value}' NIE JE registrovaná!")
                
        print("--- [CoreBridge AUDIT KONIEC] ---\n")
        return registered

    # =========================================================================
    # PREKLAD NÍZKEJ ÚROVNE NA DÁTOVÉ STAVY (Enumy pre IDE)
    # =========================================================================
    @classmethod
    def get_ide_state(cls, ide_type: str | IDEType, portable_path: str = "", users_root: str = "", active_user_id: str = "") -> dict:
        """Zavolá nízkoúrovňový IDEPaths a výsledok zabalí do oficiálnych Enumov."""
        ide_str = ide_type.value if isinstance(ide_type, IDEType) else str(ide_type)
        
        # 1. Holé fakty z nízkej úrovne:
        raw_status, executable = IDEPaths.get_raw_executable_info(ide_str, portable_path)
        raw_mode, user_data_dir, extensions_dir = IDEPaths.get_raw_profile_paths(users_root, active_user_id, ide_str)

        # 2. Priradenie Enumov:
        status_map = {
            "portable": IDEStatus.PORTABLE,
            "system": IDEStatus.SYSTEM,
            "not_found": IDEStatus.NOT_FOUND
        }
        mode_map = {
            "custom": IDEProfileMode.CUSTOM_PROFILE,
            "system_default": IDEProfileMode.SYSTEM_DEFAULT
        }

        final_status = status_map.get(raw_status, IDEStatus.NOT_FOUND)
        final_mode = mode_map.get(raw_mode, IDEProfileMode.SYSTEM_DEFAULT)
        final_ide_type = IDEType.CURSOR if ide_str == "cursor" else IDEType.VSCODE

        return {
            "ide_type": final_ide_type,
            "status": final_status,
            "is_ready": (final_status != IDEStatus.NOT_FOUND),
            "executable": executable,
            "profile_mode": final_mode,
            "user_data_dir": user_data_dir,
            "extensions_dir": extensions_dir
        }

    # =========================================================================
    # SPOJOVATEĽ PRE JAZYK (Delegácia na samostatný LanguageBridge)
    # =========================================================================
    @classmethod
    def translate(cls, key: str, default: str = None) -> str:
        """Preloží text podľa kľúča cez LanguageBridge."""
        return LanguageBridge.translate(key, default)

    @classmethod
    def load_language(cls, lang_code: str = "auto") -> LanguageStatus:
        """Načíta jazykový súbor cez LanguageBridge."""
        return LanguageBridge.load_language(lang_code)

    @classmethod
    def translate_window(cls, window: Any) -> None:
        """Preloží prvky okna cez LanguageBridge."""
        LanguageBridge.translate_window(window)

    @classmethod
    def get_current_language(cls) -> str:
        """Vráti aktuálny kód jazyka cez LanguageBridge."""
        return LanguageBridge.get_current_language()

    @classmethod
    def connect_language_changed(cls, slot) -> None:
        """Pripne widget na odber zmien jazyka cez LanguageBridge."""
        LanguageBridge.connect_language_changed(slot)

    @classmethod
    def disconnect_language_changed(cls, slot) -> None:
        """Odpojí widget z odberu zmien jazyka cez LanguageBridge."""
        LanguageBridge.disconnect_language_changed(slot)

    # =========================================================================
    # LAZY SLUŽBA PRE AKTUALIZÁCIU BALÍČKOV (PACKAGE_UPDATE)
    # =========================================================================
    @classmethod
    def _get_package_update_service(cls):
        service = cls.get_service(CoreService.PACKAGE_UPDATE)
        if service is None:
            from core.logic.sluzby.venv.package_update import PackageUpdateService
            cls.register_service(CoreService.PACKAGE_UPDATE, PackageUpdateService)
            service = PackageUpdateService
        return service

    @classmethod
    def update_all_packages(cls, venv_path: str, core=None, manager_type: str = "pip", log_callback=None) -> bool:
        """Oficiálny mostík jadra pre spustenie celého cyklu Update All."""
        service = cls._get_package_update_service()
        return service.update_all(venv_path, core, manager_type, log_callback)

    # =========================================================================
    # LAZY SLUŽBA PRE INŠTALÁCIU / ODINŠTALÁCIU (PACKAGE_OPERATIONS)
    # =========================================================================
    @classmethod
    def _get_package_operations_service(cls):
        service = cls.get_service(CoreService.PACKAGE_OPERATIONS)
        if service is None:
            from core.logic.sluzby.venv.pack_inst_unis import PackageOperationsService
            cls.register_service(CoreService.PACKAGE_OPERATIONS, PackageOperationsService)
            service = PackageOperationsService
        return service

    @classmethod
    def install_packages(cls, core, venv_path: str, packages: list[str], log_callback=print):
        """Oficiálny mostík jadra pre bezpečnú inštaláciu balíčkov s APT integráciou."""
        service = cls._get_package_operations_service()
        return service.install_packages(core, venv_path, packages, log_callback)

    @classmethod
    def uninstall_packages(cls, core, venv_path: str, packages: list[str], log_callback=print):
        """Oficiálny mostík jadra pre bezpečnú odinštaláciu balíčkov s vyčistením sirot."""
        service = cls._get_package_operations_service()
        return service.uninstall_packages(core, venv_path, packages, log_callback)

    # =========================================================================
    # LAZY SLUŽBA PRE EDITOVATEĽNÉ BALÍČKY PIP -E (EDITABLE_OPERATIONS)
    # =========================================================================
    @classmethod
    def _get_editable_operations_service(cls):
        service = cls.get_service(CoreService.EDITABLE_OPERATIONS)
        if service is None:
            from core.logic.sluzby.venv.editable_service import EditableOperationsService
            cls.register_service(CoreService.EDITABLE_OPERATIONS, EditableOperationsService)
            service = EditableOperationsService
        return service

    @classmethod
    def list_editable_packages(cls, venv_path: str, manager_type: str = "pip") -> list[dict]:
        """Vráti zoznam nainštalovaných editovateľných balíčkov vo venv."""
        service = cls._get_editable_operations_service()
        return service.list_editable_packages(venv_path, manager_type)

    @classmethod
    def install_editable_package(cls, core, venv_path: str, target_path: str, log_callback=print):
        """Inštaluje balíček v editovateľnom režime (pip -e) s APT analýzou."""
        service = cls._get_editable_operations_service()
        return service.install_editable_package(core, venv_path, target_path, log_callback)

    @classmethod
    def uninstall_editable_package(cls, core, venv_path: str, package_name: str, log_callback=print):
        """Bezpečne odinštaluje editovateľný balíček s APT autoremove sirot."""
        service = cls._get_editable_operations_service()
        return service.uninstall_editable_package(core, venv_path, package_name, log_callback)

    # =========================================================================
    # LAZY SLUŽBA PRE LOKÁLNY LINKER (LOCAL_LINKER)
    # =========================================================================
    @classmethod
    def _get_local_linker_service(cls):
        service = cls.get_service(CoreService.LOCAL_LINKER)
        if service is None:
            from core.logic.sluzby.venv.linker_service import LocalLinkerService
            cls.register_service(CoreService.LOCAL_LINKER, LocalLinkerService)
            service = LocalLinkerService
        return service

    @classmethod
    def apply_local_links(cls, core, venv_path: str, selected_items: list[dict], log_callback=print):
        """Oficiálny mostík jadra pre prepojenie lokálnych balíčkov VenvHub."""
        service = cls._get_local_linker_service()
        return service.apply_links(core, venv_path, selected_items, log_callback)

    # =========================================================================
    # LAZY SLUŽBA PRE OCHRANU PRENOSNOSTI (PORTABILITY_GUARD)
    # =========================================================================
    @classmethod
    def get_portability_guard_service(cls):
        service = cls.get_service(CoreService.PORTABILITY_GUARD)
        if service is None:
            from core.logic.sluzby.portability.portability_guard import PortabilityGuardService
            cls.register_service(CoreService.PORTABILITY_GUARD, PortabilityGuardService)
            service = PortabilityGuardService
        return service

    @classmethod
    def verify_venv_access(cls, venv_path: str) -> bool:
        """Oficiálny mostík jadra pre overenie prístupu k venvu na danom PC (True/False)."""
        guard = cls.get_portability_guard_service()
        return guard.verify_access(venv_path)

    @classmethod
    def register_venv_creation(cls, venv_path: str, source_python_path: str = None):
        """Oficiálny mostík jadra pre evidenciu PC pri vzniku venvu."""
        guard = cls.get_portability_guard_service()
        guard.register_venv_creation(venv_path, source_python_path)

    # =========================================================================
    # LAZY SLUŽBA PRE DETEKCIU PYTHONU (PYTHON_DETECTOR)
    # =========================================================================
    @classmethod
    def get_python_detector_service(cls):
        """Lazy-loader: Načíta novú službu z core/logic/sluzby/system/python_detector.py."""
        service = cls.get_service(CoreService.PYTHON_DETECTOR)
        if service is None:
            from core.logic.sluzby.system.python_detector import PythonDetector
            cls.register_service(CoreService.PYTHON_DETECTOR, PythonDetector)
            service = PythonDetector
        return service

    @classmethod
    def get_installed_pythons(cls, force_refresh: bool = False) -> list[dict]:
        """Vráti zoznam Pythonov s priradenými Enumami (PythonOrigin, PythonPipStatus)."""
        service = cls.get_python_detector_service()
        return service.get_installed_pythons(force_refresh)

    @classmethod
    def get_python_detector_status(cls) -> PythonDetectorStatus:
        """Vráti stav poslednej detekcie (SUCCESS, FALLBACK_ONLY, NO_PYTHONS_FOUND, ERROR)."""
        service = cls.get_python_detector_service()
        return service.get_detector_status()

    @classmethod
    def get_active_python(cls) -> str:
        """Vráti cestu k aktívnemu Pythonu."""
        service = cls.get_python_detector_service()
        return service.get_active_python_path()

    @classmethod
    def set_active_python(cls, python_path: str) -> None:
        """Nastaví aktívny Python."""
        service = cls.get_python_detector_service()
        service.set_active_python_path(python_path)

    @classmethod
    def resolve_parent_python(cls, venv_path: str) -> str:
        """Zistí materský Python z pyvenv.cfg (multiplatformovo)."""
        service = cls.get_python_detector_service()
        return service.resolve_parent_python(venv_path)

    @classmethod
    def add_local_python(cls, folder_name: str, python_path: str, pip_status: PythonPipStatus | str = PythonPipStatus.OK) -> None:
        """Zaregistruje nový lokálny Python do pamäte."""
        service = cls.get_python_detector_service()
        service.add_local_python(folder_name, python_path, pip_status)

    @classmethod
    def remove_local_python(cls, python_path: str) -> None:
        """Odstráni lokálny Python z pamäte."""
        service = cls.get_python_detector_service()
        service.remove_local_python(python_path)

    @classmethod
    def update_python_pip_status(cls, python_path: str, status: PythonPipStatus | str) -> None:
        """Aktualizuje stav pipu pre daný runtime na presný Enum."""
        service = cls.get_python_detector_service()
        service.update_pip_status(python_path, status)

    # =========================================================================
    # LAZY SLUŽBA PRE UV DETEKTOR (UV_DETECTOR)
    # =========================================================================
    @classmethod
    def get_uv_detector_service(cls):
        """Lazy-loader: Načíta novú službu z core/logic/sluzby/venv/uv_detector.py."""
        service = cls.get_service(CoreService.UV_DETECTOR)
        if service is None:
            from core.logic.sluzby.venv.uv_detector import UVDetector
            cls.register_service(CoreService.UV_DETECTOR, UVDetector)
            service = UVDetector
        return service

    @classmethod
    def get_uv_state(cls, force_refresh: bool = False) -> dict:
        """
        Oficiálny mostík jadra pre zistenie kompletného stavu UV.
        Mostík prepojí UVDetector s aktívnym Pythonom bez toho,
        aby tieto dve nízkoúrovňové služby museli o sebe vedieť.
        """
        service = cls.get_uv_detector_service()
        active_py = cls.get_active_python()
        return service.get_uv_state(active_python_path=active_py, force_refresh=force_refresh)

    @classmethod
    def get_uv_path(cls) -> str | None:
        """Mostík: vráti cestu k spustiteľnému súboru UV."""
        state = cls.get_uv_state()
        return state["executable"]

    @classmethod
    def is_uv_installed(cls) -> bool:
        """Mostík: overí pripravenosť UV (True/False)."""
        state = cls.get_uv_state()
        return state["is_ready"]

    @classmethod
    def get_uv_version(cls) -> str | None:
        """Mostík: vráti verziu UV."""
        state = cls.get_uv_state()
        return state["version"]

    # =========================================================================
    # LAZY SLUŽBA PRE REQUIREMENTS.TXT (REQUIREMENTS_SYNC)
    # =========================================================================
    @classmethod
    def _get_requirements_service(cls):
        """Lazy-loader pre synchronizáciu requirements.txt riadený cez CoreService Enum."""
        service = cls.get_service(CoreService.REQUIREMENTS_SYNC)
        if service is None:
            from core.logic.sluzby.venv.pack_requr import RequirementsService
            cls.register_service(CoreService.REQUIREMENTS_SYNC, RequirementsService)
            service = RequirementsService
        return service

    @classmethod
    def sync_requirements(cls, core, venv_path: str, project_root: str = "", req_file_path: str = None, log_callback=print, status_callback=None) -> bool:
        """Oficiálny mostík jadra pre spustenie synchronizácie requirements.txt."""
        service = cls._get_requirements_service()
        return service.sync_requirements(
            core=core,
            venv_path=venv_path,
            project_root=project_root,
            req_file_path=req_file_path,
            log_callback=log_callback,
            status_callback=status_callback
        )
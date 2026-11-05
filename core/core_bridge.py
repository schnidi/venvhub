#----------------------------------------------------
# Súbor: core/core_bridge.py
# Centrálny Most (Bridge / Service Locator)
# Prepája nízkoúrovňovú logiku s dátovými stavmi jadra.
#----------------------------------------------------

from typing import Any
from core.core_states import CoreService, IDEType, IDEStatus, IDEProfileMode, LanguageStatus
from core.logic.vscode_user.sluzby.ide_paths import IDEPaths


class CoreBridge:
    """Centrálny register a most jadra."""

    _services: dict[CoreService, Any] = {}

    @classmethod
    def register_service(cls, key: CoreService, service_instance: Any) -> None:
        cls._services[key] = service_instance

    @classmethod
    def get_service(cls, key: CoreService) -> Any:
        return cls._services.get(key)

    # =========================================================================
    # PREKLAD NÍZKEJ ÚROVNE NA DÁTOVÉ STAVY (Enumy)
    # =========================================================================
    @classmethod
    def get_ide_state(cls, ide_type: str | IDEType, portable_path: str = "", users_root: str = "", active_user_id: str = "") -> dict:
        """
        Zavolá nízkoúrovňový IDEPaths a výsledok zabalí do oficiálnych Enumov.
        """
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
    # AUDIT A DIAGNOSTIKA
    # =========================================================================
    
    @classmethod
    def audit_services(cls) -> list[str]:
        """Vráti zoznam všetkých aktívne zaregistrovaných služieb v jadre."""
        print("\n--- [CoreBridge AUDIT ŠTART] ---")
        registered = []

        # Zoznam služieb, ktoré sú zámerne typu LAZY (načítavajú sa na požiadanie)
        lazy_services = {CoreService.PACKAGE_UPDATE}
        
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
    # SPOJOVATEĽ PRE JAZYK (Delegácia na novú službu)
    # =========================================================================
    @classmethod
    def translate(cls, key: str, default: str = None) -> str:
        lang_service = cls.get_service(CoreService.LANGUAGE)
        if lang_service:
            return lang_service.get(key, default)
        return default if default else key

    @classmethod
    def load_language(cls, lang_code: str = "auto") -> LanguageStatus:
        lang_service = cls.get_service(CoreService.LANGUAGE)
        if lang_service:
            return lang_service.load_language(lang_code)
        return LanguageStatus.ERROR

    @classmethod
    def translate_window(cls, window: Any) -> None:
        lang_service = cls.get_service(CoreService.LANGUAGE)
        if lang_service:
            lang_service.translate_ui(window)

    @classmethod
    def get_current_language(cls) -> str:
        """Vráti aktuálny kód jazyka (napr. sk_SK alebo en_US)."""
        lang_service = cls.get_service(CoreService.LANGUAGE)
        if lang_service and hasattr(lang_service, "_current_lang_code"):
            return lang_service._current_lang_code
        return "en_US"

    @classmethod
    def connect_language_changed(cls, slot) -> None:
        """Pripne widget na odber real-time zmien jazyka."""
        lang_service = cls.get_service(CoreService.LANGUAGE)
        if lang_service:
            lang_service.language_changed.connect(slot)

    @classmethod
    def disconnect_language_changed(cls, slot) -> None:
        """Odpojí widget z odberu zmien jazyka."""
        lang_service = cls.get_service(CoreService.LANGUAGE)
        if lang_service:
            try:
                lang_service.language_changed.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    # =========================================================================
    # LAZY SLUŽBA PRE AKTUALIZÁCIU BALÍČKOV (PACKAGE_UPDATE)
    # =========================================================================
    @classmethod
    def get_package_update_service(cls):
        """
        Lazy-loader: Služba sa importuje a zaregistruje do centrálneho registra
        AŽ VTEDY, keď je prvýkrát vyžiadaná. Využíva register_service.
        """
        service = cls.get_service(CoreService.PACKAGE_UPDATE)
        if service is None:
            from core.logic.sluzby.venv.package_update import PackageUpdateService
            cls.register_service(CoreService.PACKAGE_UPDATE, PackageUpdateService)
            service = PackageUpdateService
        return service

    @classmethod
    def update_all_packages(cls, venv_path: str, core=None, manager_type: str = "pip", log_callback=None) -> bool:
        """
        Oficiálny mostík jadra pre spustenie celého cyklu Update All.
        """
        service = cls.get_package_update_service()
        return service.update_all(venv_path, core, manager_type, log_callback)
#----------------------------------------------------
# Súbor: core/logic/sluzby/dialog_bridge.py
# Most pre CustomMessageBox a ProgressDialog
#----------------------------------------------------

from typing import Any, Optional


class DialogBridge:
    """Striktný most pre CustomMessageBox a ProgressDialog."""

    _provider: Any = None
    _progress_provider: Any = None

    # =========================================================================
    # AUDIT A DIAGNOSTIKA
    # =========================================================================
    @classmethod
    def audit(cls) -> bool:
        """Vykoná formátovaný audit pripravenosti oboch okien."""
        print("\n--- [DialogBridge AUDIT ŠTART] ---")
        is_ok = True

        # 1. CustomMessageBox
        if cls._provider is not None:
            provider_name = getattr(cls._provider, "__name__", str(cls._provider))
            print(f"[DialogBridge] ✅ Poskytovateľ dialógov '{provider_name}' je pripravený.")
            
            required_methods = [
                "information", 
                "warning", 
                "critical", 
                "question", 
                "show_portability_blocked"
            ]
            for method_name in required_methods:
                if hasattr(cls._provider, method_name):
                    print(f"[DialogBridge] ✅ Metóda '{method_name}' je overená.")
                else:
                    print(f"[DialogBridge] ❌ POZOR: Metóda '{method_name}' na poskytovateľovi CHÝBA!")
                    is_ok = False
        else:
            print("[DialogBridge] ❌ POZOR: Poskytovateľ dialógov NIE JE registrovaný!")
            is_ok = False

        # 2. ProgressDialog
        if cls._progress_provider is not None:
            prog_name = getattr(cls._progress_provider, "__name__", str(cls._progress_provider))
            print(f"[DialogBridge] ✅ Poskytovateľ priebehu '{prog_name}' je pripravený.")
            
            prog_methods = [
                "set_message", 
                "add_log_message", 
                "enable_cancel_button", 
                "set_progress_mode", 
                "set_progress_value"
            ]
            for method_name in prog_methods:
                if hasattr(cls._progress_provider, method_name):
                    print(f"[DialogBridge] ✅ Metóda '{method_name}' je overená.")
                else:
                    print(f"[DialogBridge] ❌ POZOR: Metóda '{method_name}' na poskytovateľovi CHÝBA!")
                    is_ok = False
        else:
            print("[DialogBridge] ❌ POZOR: Poskytovateľ ProgressDialog NIE JE registrovaný!")
            is_ok = False

        print("--- [DialogBridge AUDIT KONIEC] ---\n")
        return is_ok

    # =========================================================================
    # REGISTRÁCIA
    # =========================================================================
    @classmethod
    def register_provider(cls, msg_box_class: Any, progress_dialog_class: Any = None) -> None:
        """Zaregistruje triedy dialógov pri štarte aplikácie."""
        cls._provider = msg_box_class
        cls._progress_provider = progress_dialog_class
        cls.audit()

    # =========================================================================
    # DELEGÁCIA CustomMessageBox
    # =========================================================================
    @classmethod
    def information(cls, parent: Optional[Any], title: str, text: str, *args, **kwargs) -> Any:
        return cls._provider.information(parent, title, text, *args, **kwargs)

    @classmethod
    def warning(cls, parent: Optional[Any], title: str, text: str, *args, **kwargs) -> Any:
        return cls._provider.warning(parent, title, text, *args, **kwargs)

    @classmethod
    def critical(cls, parent: Optional[Any], title: str, text: str, *args, **kwargs) -> Any:
        return cls._provider.critical(parent, title, text, *args, **kwargs)

    @classmethod
    def question(cls, parent: Optional[Any], title: str, text: str, *args, **kwargs) -> Any:
        return cls._provider.question(parent, title, text, *args, **kwargs)

    @classmethod
    def show_portability_blocked(cls, parent: Optional[Any], venv_name: str) -> None:
        cls._provider.show_portability_blocked(parent, venv_name)

    # =========================================================================
    # PROGRESS DIALOG (Čisté vrátenie inštancie, žiadne hlúpe podmienky)
    # =========================================================================
    @classmethod
    def progress_dialog(cls, parent=None):
        """Vráti inštanciu ProgressDialog."""
        return cls._progress_provider(parent)
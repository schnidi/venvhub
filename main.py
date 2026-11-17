"""
Súbor: main.py
Hlavný spúšťací modul aplikácie VenvHub Pro.
"""

import os
import sys
import threading

# =========================================================================
# NATVRDO PREPNÚŤ CELÝ WINDOWS A KONZOLU DO NATIVE UTF-8 (Code Page 65001)
# =========================================================================
if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    ctypes.windll.kernel32.SetConsoleCP(65001)

    handle = ctypes.windll.kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    mode = ctypes.c_ulong()
    if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
# =========================================================================

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# =========================================================================
# 1. REGISTRÁCIA STATICKÝCH SLUŽIEB (Bez závislosti na GUI)
# =========================================================================
from core.core_states import CoreService
from core.core_bridge import CoreBridge
from core.logic.vscode_user.sluzby.ide_paths import IDEPaths

CoreBridge.register_service(CoreService.IDE_PATHS, IDEPaths)

# =========================================================================
# 2. PROSTREDIE A LISTNERY
# =========================================================================
from core.logic.pyqt_to_pyside import setup_qt_environment
setup_qt_environment()

# --- ŠTART 2s SCANNERA PRE VS CODE & CURSOR ---
from core.logic.ide_detector import IDEDetector
IDEDetector.start_listening()

from PyQt6.QtWidgets import QApplication

from windows.widget import ProjectMiniBar
from windows.about_dialog import AboutDialog
from core.logic.project_manager import ProjectCore
from core.logic.skin_manager import SkinManager 
from core.single_instance import SingleInstance, SingleInstanceError
from core.logic.containers.logic.autostart_boot import AutostartBooter
from core.logic.sluzby.about_logic import AboutLogic
from core.logic.sluzby.github_update import GitHubUpdate


def _start_background_update_check():
    """Spustí asynchrónnu kontrolu novej verzie z GitHubu na pozadí."""
    def check_task():
        try:
            GitHubUpdate.check_for_updates()
        except Exception:
            pass

    thread = threading.Thread(target=check_task, daemon=True, name="StartupGitHubUpdateCheck")
    thread.start()


def main():
    app = QApplication(sys.argv)

    # =========================================================================
    # 3. REGISTRÁCIA GUI SLUŽIEB & PREKLADY JADRA
    # =========================================================================
    from core.logic.sluzby.language.language_manager import LanguageManager
    
    lang_manager = LanguageManager()
    CoreBridge.register_service(CoreService.LANGUAGE, lang_manager)
    
    # === TU JE SPRÁVNE MIESTO PRE AUDIT ===
    # Prebehne kontrola zoznamu služieb a vypíše sa do konzoly
    CoreBridge.audit_services()
    # ======================================
    
    # Načítame preklady úplne na začiatku, pred tvorbou okien
    CoreBridge.load_language("auto")
    # =========================================================================

    AboutLogic.register_about_dialog(AboutDialog)

    window_ref = [None]

    def bring_to_front():
        if window_ref[0]:
            win = window_ref[0]
            win.show()
            win.raise_()
            win.activateWindow()
            if hasattr(win, 'manager_window') and win.manager_window:
                win.manager_window.show()
                win.manager_window.raise_()
                win.manager_window.activateWindow()

    APP_ID = "VenvHubPro_Single_Instance_Lock"
    checker = SingleInstance(APP_ID, bring_to_front)
    
    try:
        if checker.is_running():
            sys.exit(0)
    except SingleInstanceError as e:
        print(f"CHYBA: {e}")
        sys.exit(1)

    app._single_instance = checker

    _start_background_update_check()

    core = ProjectCore()
    
    if core.active_theme and core.active_theme != "default":
        SkinManager.apply_skin(core.active_theme)
        
    widget = ProjectMiniBar(core)
    window_ref[0] = widget
    
    if core.last_pos:
        widget.move(core.last_pos[0], core.last_pos[1])
        
    widget.show()
    AutostartBooter.run_autostart_groups(core)
    
    exit_code = app.exec()
    
    core.last_pos = widget.get_position()
    core.save_config()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
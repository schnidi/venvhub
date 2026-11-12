#----------------------------------------
# Súbor: core/logic/path_logic/portable.py
#----------------------------------------

import os
import sys
import platform
import re
import json

from core.logic.path_logic.disk_uuid_win_lin import get_all_disks_info
from core.core_bridge import CoreBridge

class PortablePathLogic:
    """
    Logika pre Portable verziu.
    Rieši dynamické zmeny písmen diskov pri prenose USB kľúča pomocou UUID disku.
    """

    @staticmethod
    def is_linux() -> bool:
        """Zistí, či aplikácia beží na OS Linux."""
        return platform.system() == "Linux"

    @staticmethod
    def encode_path(abs_path: str) -> str:
        """
        Zoberie absolútnu cestu (napr. E:\\Projekty) a zakóduje do nej UUID disku.
        Výsledok: [UUID:1A2B3C4D]\\Projekty
        """
        if not abs_path or PortablePathLogic.is_linux():
            return abs_path

        drive, tail = os.path.splitdrive(abs_path)
        if not drive:
            return abs_path

        target_drive = drive.replace("\\", "").replace("/", "").upper()
        
        for disk in get_all_disks_info():
            if disk.get("mount", "").upper() == target_drive:
                uuid = disk.get("uuid", "")
                if uuid:
                    clean_tail = tail.lstrip("\\/")
                    return f"[UUID:{uuid}]\\{clean_tail}"
        
        return abs_path

    @staticmethod
    def resolve_path(stored_path: str) -> tuple[str, bool]:
        """
        Dekóduje uloženú cestu.
        Preloží [UUID:1A2B3C4D]\\Projekty späť na F:\\Projekty podľa aktuálneho stavu PC.
        Vráti: (Správna absolútna cesta, Bol_formát_zmenený?)
        """
        if not stored_path:
            return "", False

        if PortablePathLogic.is_linux():
            print("UPOZORNENIE: Tento softvér aktuálne nepodporuje Portable režim pre OS Linux.")
            return stored_path, False

        # 1. Je cesta už uložená v novom UUID formáte?
        match = re.match(r"^\[UUID:([a-zA-Z0-9\-]+)\][\\/](.*)", stored_path, re.IGNORECASE)
        if match:
            target_uuid = match.group(1).upper()
            tail = match.group(2)

            for disk in get_all_disks_info():
                if disk.get("uuid", "").upper() == target_uuid:
                    current_drive = disk.get("mount", "")
                    new_path = os.path.normpath(f"{current_drive}\\{tail}")
                    return new_path, True 

            print(f"[PORTABLE] Upozornenie: Disk (alebo partícia) s UUID '{target_uuid}' nie je pripojený!")
            return "", False

        # 2. LEGACY formát (napr. E:\Projekty) - Starý konfig
        if os.path.exists(stored_path):
            return stored_path, True

        if getattr(sys, 'frozen', False):
            app_path = sys.executable
        else:
            app_path = os.path.abspath(sys.argv[0])
            
        current_drive, _ = os.path.splitdrive(app_path)
        stored_drive, tail = os.path.splitdrive(stored_path)      

        new_path = os.path.join(current_drive, tail)
        if os.path.exists(new_path):
            return new_path, True
        
        return stored_path, False

    @staticmethod
    def check_and_repair_venv_if_needed(venv_path: str, local_packages_root: str = ""):
        """
        Dokonalá, exaktná kontrola venvu.
        Opravuje aktivátory, import hooky pre lokálne balíčky a tiež pip -e editovateľné odkazy.
        Systémové venvy na USB neprepisuje.
        """
        if not venv_path or not os.path.exists(venv_path):
            return

        if PortablePathLogic.is_linux():
            return

        # 👉 NATÍVNA OCHRANA PRENOSNOSTI: Zákaz prepisovania systémových venvov na USB
        guard = CoreBridge.get_portability_guard_service()
        if guard.is_portable_mode() and guard.is_system_venv(venv_path):
            return

        current_drive, _ = os.path.splitdrive(venv_path)
        if not current_drive: return
        current_drive = current_drive.upper()

        from core._path import Paths
        pyvenv_cfg = Paths.get_pyvenv_cfg_path(venv_path)
        activate_bat = Paths.get_venv_activate_bat_path(venv_path)
        activate_sh = os.path.join(venv_path, Paths.VENV_SCRIPTS_DIR_NAME, "activate")

        # Zistíme STARÉ písmeno priamo zo súborov vo Venve
        old_drive = None
        if os.path.exists(activate_bat):
            try:
                with open(activate_bat, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("set VIRTUAL_ENV="):
                            path_part = line.split("=")[1].strip()
                            if len(path_part) >= 2 and path_part[1] == ':':
                                old_drive = path_part[:2].upper()
                                break
            except Exception:
                pass
        
        if not old_drive and os.path.exists(pyvenv_cfg):
             try:
                with open(pyvenv_cfg, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith("home = "):
                            path_part = line.split("=")[1].strip()
                            if len(path_part) >= 2 and path_part[1] == ':':
                                old_drive = path_part[:2].upper()
                                break
             except Exception:
                 pass

        # Ak sa disk nezmenil, vyskakujeme
        if not old_drive or old_drive == current_drive:
            return

        # =========================================================================
        # 1. OPRAVA AKTIVÁTOROV (activate.bat a pyvenv.cfg)
        # =========================================================================
        old_d = old_drive
        old_d_lower = old_drive.lower()
        new_d = current_drive

        for act_file in [activate_bat, activate_sh]:
            if os.path.exists(act_file):
                try:
                    with open(act_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    new_content = content.replace(old_d, new_d).replace(old_d_lower, new_d)
                    if new_content != content:
                        with open(act_file, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                except Exception:
                    pass

        if os.path.exists(pyvenv_cfg):
            try:
                with open(pyvenv_cfg, 'r', encoding='utf-8') as f:
                    content = f.read()
                new_content = content.replace(old_d, new_d).replace(old_d_lower, new_d)
                if new_content != content:
                    with open(pyvenv_cfg, 'w', encoding='utf-8') as f:
                        f.write(new_content)
            except Exception:
                pass

        # =========================================================================
        # 2. LOGIKA PRE LOKÁLNE BALÍČKY - JSON IMPORT HOOK (BEZ UAC!)
        # =========================================================================
        site_folder = "Lib" if os.name == 'nt' else "lib"
        site_packages_dir = os.path.join(venv_path, site_folder, "site-packages")
        
        json_file = os.path.join(site_packages_dir, "venvhub.json")
        
        if os.path.exists(json_file):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    mapping = json.load(f)
                
                changed = False
                for pkg_name, pkg_path in mapping.items():
                    if old_d in pkg_path or old_d_lower in pkg_path:
                        new_path = pkg_path.replace(old_d, new_d).replace(old_d_lower, new_d)
                        mapping[pkg_name] = new_path
                        changed = True
                        
                if changed:
                    with open(json_file, 'w', encoding='utf-8') as f:
                        json.dump(mapping, f, indent=4, ensure_ascii=False)
                    print(f"[PORTABLE] Opravené cesty pre lokálne balíčky (venvhub.json)")
            except Exception as e:
                print(f"[PORTABLE] Chyba pri oprave venvhub.json: {e}")

        # =========================================================================
        # 3. OPRAVA PIP -e (.pth a .egg-link súbory v site-packages)
        # =========================================================================
        if os.path.exists(site_packages_dir):
            import glob
            
            pth_files = glob.glob(os.path.join(site_packages_dir, "*.pth"))
            egg_links = glob.glob(os.path.join(site_packages_dir, "*.egg-link"))
            editable_links = pth_files + egg_links
            
            for file_path in editable_links:
                filename = os.path.basename(file_path).lower()
                if filename == "venvhub_bootstrap.pth" or (filename.startswith("python") and filename.endswith("._pth")):
                    continue
                    
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if old_d in content or old_d_lower in content:
                        new_content = content.replace(old_d, new_d).replace(old_d_lower, new_d)
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)
                            
                        print(f"[PORTABLE] Opravený editovateľný pip odkaz: {filename}")
                except Exception as e:
                    print(f"[PORTABLE] Chyba pri oprave {file_path}: {e}")
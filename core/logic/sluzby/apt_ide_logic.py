#----------------------------------------------------
# Súbor: core/logic/sluzby/apt_ide_logic.py
#----------------------------------------------------

import os
import json
import re
import shutil
import subprocess

from core._path import Paths
from core.core_states import IDEType
from core.core_bridge import CoreBridge
from core.logic.language_manager import LanguageManager
from core.logic.commands.vscode_commands import VSCodeCommandDispatcher
from core.logic.commands.cursor_commands import CursorAICommandDispatcher


class AptIDELogic:
    """
    Centrálna služba správy IDE rozšírení (VS Code & Cursor AI).
    
    KUMULATÍVNA ARCHITEKTÚRA (Jeden profil pre viacero projektov):
    - Profil slúži ako stály sklad rozšírení: chýbajúce rozšírenie sa nainštaluje IBA RAZ.
    - Žiadne automatické odinštalovanie pri prepínaní projektov (ochrana disku a ostatných projektov).
    - Zapínanie a vypínanie funkcií pre konkrétny projekt riadi VSCodeIntegration cez settings.json.
    - Metóda na odinštalovanie sirôt (Autoremove) zostáva zachovaná ako samostatná servisná funkcia do budúcna.
    """

    TRACKER_FILE_NAME = "venvhub_extensions_tracker.json"

    # =========================================================================
    # 1. NORMALIZÁCIA A POMOCNÉ METÓDY
    # =========================================================================

    @staticmethod
    def _normalize(ext_id: str) -> str:
        """Zjednotí formát ID rozšírenia na malé písmená."""
        return ext_id.strip().lower()

    @staticmethod
    def _get_ide_context(core) -> dict:
        """
        Zistí aktívne IDE, profil, cesty a dispečer priamo cez stavovú službu CoreBridge.
        """
        active_ide = getattr(core, 'active_ide', 'vscode')
        portable_path = getattr(core, f"portable_{active_ide}_path", "")
        users_root = getattr(core, 'vscode_users_root', '')
        active_user = core.get_active_ide_user() if hasattr(core, 'get_active_ide_user') else ''

        # Získanie overeného stavu z mosta jadra
        ide_state = CoreBridge.get_ide_state(
            ide_type=active_ide,
            portable_path=portable_path,
            users_root=users_root,
            active_user_id=active_user
        )

        executable = ide_state["executable"]
        extensions_dir = ide_state["extensions_dir"]
        user_data_dir = ide_state["user_data_dir"]

        # Zaistenie priečinkov a cesty k účtenke
        if extensions_dir:
            os.makedirs(extensions_dir, exist_ok=True)
        if user_data_dir:
            os.makedirs(user_data_dir, exist_ok=True)
            tracker_file = os.path.join(user_data_dir, AptIDELogic.TRACKER_FILE_NAME)
        else:
            tracker_file = ""

        # Vytvorenie príkazového dispečera s overenou binárkou
        if ide_state["ide_type"] == IDEType.CURSOR:
            dispatcher = CursorAICommandDispatcher(custom_executable=executable)
            ide_name = "Cursor"
        else:
            dispatcher = VSCodeCommandDispatcher(custom_executable=executable)
            ide_name = "VS Code"

        return {
            "active_ide": active_ide,
            "ide_name": ide_name,
            "active_user": active_user,
            "extensions_dir": extensions_dir,
            "tracker_file": tracker_file,
            "dispatcher": dispatcher
        }

    @staticmethod
    def _get_installed_extensions_on_disk(extensions_dir: str) -> dict[str, str]:
        """
        Preskenuje fyzickú zložku extensions na disku.
        Vráti mapovanie { 'normalizovane_id': 'cely_nazov_zlozky' }.
        """
        installed = {}
        if not extensions_dir or not os.path.exists(extensions_dir):
            return installed

        for folder_name in os.listdir(extensions_dir):
            if folder_name.startswith('.'):
                continue

            full_path = os.path.join(extensions_dir, folder_name)
            if os.path.isdir(full_path):
                clean_id = re.sub(r'-\d+\.\d+.*$', '', folder_name).lower()
                installed[clean_id] = folder_name
                
        return installed

    # =========================================================================
    # 2. ÚČTENKOVÝ MANAŽÉR (TRACKER)
    # =========================================================================

    @staticmethod
    def _load_tracker(tracker_file: str) -> dict:
        """Načíta účtenku profilu, alebo vytvorí novú."""
        if tracker_file and os.path.exists(tracker_file):
            try:
                with open(tracker_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data.setdefault("explicit", [])
                    data.setdefault("linked_by_venvhub", {})
                    return data
            except Exception:
                pass
        return {"explicit": [], "linked_by_venvhub": {}}

    @staticmethod
    def _save_tracker(tracker_file: str, data: dict):
        """Uloží účtenku na disk."""
        if not tracker_file:
            return
        try:
            os.makedirs(os.path.dirname(tracker_file), exist_ok=True)
            with open(tracker_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    # =========================================================================
    # 3. HLAVNÁ SYNCHRONIZÁCIA LINKERA (KUMULATÍVNA BEZ ODINŠTALÁCIE)
    # =========================================================================

    @classmethod
    def sync_ide_extensions(cls, core, all_packages_to_link: dict, log_callback=print):
        """
        Kumulatívna synchronizácia rozšírení:
        1. Zistí požiadavky aktuálne pripájaných Linker balíčkov.
        2. Doinštaluje chýbajúce rozšírenia (ak už v profile sú, inštaláciu preskočí).
        3. Fyzický Autoremove je VYPNUTÝ: pluginy v profile zostávajú pre iné projekty.
        4. Vypínanie funkcií pre projekt riadi VSCodeIntegration cez settings.json.
        """
        ctx = cls._get_ide_context(core)
        extensions_dir = ctx["extensions_dir"]
        tracker_file = ctx["tracker_file"]
        dispatcher = ctx["dispatcher"]
        ide_name = ctx["ide_name"]

        if ctx['active_user']:
            target_desc = LanguageManager.get("apt_ide_target_profile", "profilu '{profile}'").format(profile=ctx['active_user'])
        else:
            target_desc = LanguageManager.get("apt_ide_target_system", "systémového {ide}").format(ide=ide_name)

        # 1. Načítame účtenku a aktuálny stav disku
        tracker = cls._load_tracker(tracker_file)
        installed_on_disk = cls._get_installed_extensions_on_disk(extensions_dir)

        # 2. Zozbierame požiadavky pripájaných balíčkov
        new_linked_state = {}
        all_incoming_extensions = set()
        raw_extensions_to_install = {}

        for pkg_name, pkg_data in all_packages_to_link.items():
            meta_path = os.path.join(pkg_data['path'], "local_meta.json")
            if not os.path.exists(meta_path):
                continue
                
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    req_exts = meta.get("vscode_integration", {}).get("extensions", [])
                    
                    pkg_clean_exts = []
                    for ext_id in req_exts:
                        norm_id = cls._normalize(ext_id)
                        pkg_clean_exts.append(norm_id)
                        all_incoming_extensions.add(norm_id)
                        raw_extensions_to_install[norm_id] = ext_id
                            
                    new_linked_state[pkg_name] = pkg_clean_exts
            except Exception:
                pass

        tracker["linked_by_venvhub"] = new_linked_state

        # 3. Self-Healing: Všetko čo je na disku mimo prichádzajúcich Linkerov patrí používateľovi (Explicit)
        current_explicit = set(cls._normalize(e) for e in tracker.get("explicit", []))
        current_explicit -= all_incoming_extensions

        for installed_id in installed_on_disk.keys():
            if installed_id not in all_incoming_extensions and installed_id not in current_explicit:
                current_explicit.add(installed_id)

        tracker["explicit"] = sorted(list(current_explicit))

        # 4. Inštalácia IBA TÝCH, ktoré na disku reálne chýbajú
        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
        extensions_to_install = [
            raw_extensions_to_install[norm_id] 
            for norm_id in all_incoming_extensions 
            if norm_id not in installed_on_disk
        ]

        if extensions_to_install:
            msg_analyzing = LanguageManager.get(
                "apt_ide_analyzing_for",
                "\n🧩 [APT IDE] Pripravujem potrebné rozšírenia pre {target_desc}..."
            ).format(target_desc=target_desc)
            log_callback(msg_analyzing)

            for ext_id in extensions_to_install:
                msg_installing = LanguageManager.get(
                    "apt_ide_installing_ext",
                    "📦 [APT IDE] Inštalujem do profilu chýbajúce rozšírenie: {ext_id}..."
                ).format(ext_id=ext_id)
                log_callback(msg_installing)

                cmd = dispatcher.get("install_extension", extension_id=ext_id)
                if ctx["active_user"] and extensions_dir:
                    cmd.extend(["--extensions-dir", extensions_dir])

                try:
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        bufsize=1,
                        creationflags=CREATE_NO_WINDOW,
                        shell=(os.name == 'nt')
                    )
                    for line in iter(proc.stdout.readline, ''):
                        clean_l = line.strip()
                        if clean_l:
                            log_callback(f"  {clean_l}")
                    proc.wait()
                    
                    if proc.returncode == 0:
                        msg_ok = LanguageManager.get(
                            "apt_ide_ext_installed_ok",
                            "✔ Rozšírenie '{ext_id}' úspešne nainštalované."
                        ).format(ext_id=ext_id)
                        log_callback(msg_ok)
                        installed_on_disk[cls._normalize(ext_id)] = ext_id
                    else:
                        msg_code = LanguageManager.get(
                            "apt_ide_installer_code",
                            "⚠️ Inštalátor vrátil kód {code}."
                        ).format(code=proc.returncode)
                        log_callback(msg_code)
                except Exception as e:
                    msg_err = LanguageManager.get(
                        "apt_ide_install_failed",
                        "❌ Zlyhala inštalácia {ext_id}: {error}"
                    ).format(ext_id=ext_id, error=e)
                    log_callback(msg_err)

        # 5. Uloženie aktualizovanej účtenky bez odinštalovania čohokoľvek
        cls._save_tracker(tracker_file, tracker)

    # =========================================================================
    # 4. SAMOSTATNÁ SERVISNÁ FUNKCIA: MANUÁLNE VYČISTENIE PROFILU (AUTOREMOVE)
    # =========================================================================

    @classmethod
    def clean_orphaned_extensions(cls, core, log_callback=print):
        """
        Servisná funkcia pre budúce manuálne čistenie (napr. tlačidlo 'Prečistiť profil').
        Zmaže iba pluginy, ktoré nie sú explicitné a nepatria žiadnemu balíčku.
        Táto funkcia sa NEVOLÁ automaticky pri linkovaní balíčkov.
        """
        ctx = cls._get_ide_context(core)
        extensions_dir = ctx["extensions_dir"]
        tracker_file = ctx["tracker_file"]
        dispatcher = ctx["dispatcher"]

        tracker = cls._load_tracker(tracker_file)
        installed_on_disk = cls._get_installed_extensions_on_disk(extensions_dir)

        protected_extensions = set(tracker.get("explicit", []))
        for active_ext_list in tracker.get("linked_by_venvhub", {}).values():
            for e in active_ext_list:
                protected_extensions.add(cls._normalize(e))

        orphans_to_remove = [
            (installed_id, folder_name)
            for installed_id, folder_name in installed_on_disk.items()
            if installed_id not in protected_extensions
        ]

        if not orphans_to_remove:
            msg_no_orphans = LanguageManager.get(
                "apt_ide_no_orphans",
                "✅ [APT IDE] Žiadne osirelé rozšírenia na vymazanie."
            )
            log_callback(msg_no_orphans)
            return

        msg_autoremove_start = LanguageManager.get(
            "apt_ide_autoremove_start",
            "\n🧹 [APT IDE Cleanup] Odstraňujem {count} nepoužívaných rozšírení..."
        ).format(count=len(orphans_to_remove))
        log_callback(msg_autoremove_start)

        CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

        for ext_id, folder_name in orphans_to_remove:
            msg_deleting = LanguageManager.get(
                "apt_ide_deleting_orphan",
                "🗑️ [APT IDE] Mažem rozšírenie: {ext_id}"
            ).format(ext_id=ext_id)
            log_callback(msg_deleting)

            # 1. Odinštalovanie cez dispečer editora
            try:
                cmd_un = dispatcher.get("uninstall_extension", extension_id=ext_id)
                if ctx["active_user"] and extensions_dir:
                    cmd_un.extend(["--extensions-dir", extensions_dir])
                subprocess.run(cmd_un, capture_output=True, shell=(os.name == 'nt'), creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

            # 2. Fyzické dočistenie zložky z disku
            target_folder_path = os.path.join(extensions_dir, folder_name)
            if os.path.exists(target_folder_path):
                try:
                    shutil.rmtree(target_folder_path, ignore_errors=True)
                except Exception:
                    pass

        msg_autoremove_done = LanguageManager.get(
            "apt_ide_autoremove_done",
            "✅ [APT IDE Cleanup] Vyčistenie profilu dokončené."
        )
        log_callback(msg_autoremove_done)
        cls._save_tracker(tracker_file, tracker)

    # =========================================================================
    # 5. BLESKOVÁ KONTROLA PRED ŠTARTOM EDITORA
    # =========================================================================

    @classmethod
    def verify_and_heal_profile_on_launch(cls, core, venv_path: str, dispatcher):
        """
        Zavolá sa z VSCodeLauncher pred spustením editora.
        Iba overí, či v profile nechýba rozšírenie pre aktívne prelinkované balíčky.
        Keďže autoremove je vypnutý, proces je bleskový a bezpečný.
        """
        if not venv_path:
            return

        site_folder = "Lib" if os.name == 'nt' else "lib"
        vh_json = os.path.join(venv_path, site_folder, "site-packages", "venvhub.json")
        if not os.path.exists(vh_json):
            return

        try:
            with open(vh_json, "r", encoding="utf-8") as f:
                linked_pkgs_map = json.load(f)

            all_packages_to_link = {
                name: {"name": name, "path": path}
                for name, path in linked_pkgs_map.items()
            }

            # Doinštaluje len tie, ktoré náhodou v profile ešte chýbajú
            cls.sync_ide_extensions(core, all_packages_to_link, log_callback=lambda msg: None)

        except Exception as e:
            print(f"[AptIDELogic] Chyba pri overení profilu pred štartom: {e}")
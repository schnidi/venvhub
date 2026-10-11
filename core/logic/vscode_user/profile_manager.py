#----------------------------------------
# Súbor: core/logic/vscode_user/profile_manager.py
#----------------------------------------

import os
import json
import shutil
import re
import stat
from PyQt6.QtCore import QObject, pyqtSignal
from core.logic.sluzby.copy_del import CopyDelService
from core.logic.language_manager import LanguageManager

class ProfileDeleteWorker(QObject):
    log_msg = pyqtSignal(str)
    progress_percent = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, target_dir: str):
        super().__init__()
        self.target_dir = target_dir

    def run(self):
        result = CopyDelService.safe_delete_with_progress(
            target_path=self.target_dir,
            log_func=self.log_msg.emit,
            progress_func=self.progress_percent.emit
        )
        self.finished.emit(result["success"], result.get("error", ""))


class VSCodeProfileManager:
    @staticmethod
    def get_profiles(root_path: str) -> list[dict]:
        profiles = []
        if not root_path or not os.path.exists(root_path):
            return profiles

        for item in os.listdir(root_path):
            profile_dir = os.path.join(root_path, item)
            if os.path.isdir(profile_dir):
                meta_path = os.path.join(profile_dir, "meta.json")
                display_name = item 
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            display_name = meta.get("display_name", item)
                    except Exception: pass
                
                profiles.append({"id": item, "display_name": display_name, "path": profile_dir})
        return sorted(profiles, key=lambda x: x["id"].lower())

    @staticmethod
    def create_profile(root_path: str, user_id: str, display_name: str) -> dict:
        if not root_path or not os.path.exists(root_path):
            return {"success": False, "error": LanguageManager.get("err_root_dir_not_exist", "Koreňový priečinok neexistuje.")}

        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '', user_id.strip())
        if not safe_id: return {"success": False, "error": LanguageManager.get("err_invalid_profile_id", "Neplatné ID profilu.")}

        profile_dir = os.path.join(root_path, safe_id)
        if os.path.exists(profile_dir):
            return {"success": False, "error": LanguageManager.get("err_profile_id_exists", "Profil s ID '{0}' už existuje.").format(safe_id)}

        try:
            os.makedirs(profile_dir)
            os.makedirs(os.path.join(profile_dir, "data", "User"))
            os.makedirs(os.path.join(profile_dir, "data", "extensions"))

            meta_path = os.path.join(profile_dir, "meta.json")
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({"display_name": display_name.strip() or safe_id}, f, ensure_ascii=False, indent=4)

            return {"success": True, "id": safe_id, "path": profile_dir}
        except Exception as e:
            return {"success": False, "error": LanguageManager.get("err_create_profile", "Chyba pri vytváraní: {0}").format(e)}

    @staticmethod
    def _remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception: pass

    @staticmethod
    def get_ide_profiles_dir(root_path: str, ide_type: str = "vscode") -> str:
        """
        Vráti cestu k priečinku profilov pre konkrétne IDE (napr. root/vscode alebo root/cursor).
        Ak priečinok ešte neexistuje, automaticky ho vytvorí.
        """
        if not root_path:
            return ""
        subfolder = "cursor" if ide_type == "cursor" else "vscode"
        target_dir = os.path.join(root_path, subfolder)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError:
            pass
        return target_dir

    @staticmethod
    def delete_profile(root_path: str, user_id: str) -> dict:
        profile_dir = os.path.join(root_path, user_id)
        return CopyDelService.safe_delete_with_progress(profile_dir)

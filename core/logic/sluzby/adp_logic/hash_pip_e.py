#----------------------------------------------------
# Súbor: core/logic/sluzby/apt_logic/hash_pip_e.py
# Čistá hashovacia služba pre všetky varianty vstupov.
#----------------------------------------------------

import os
import hashlib
from core.core_states import HashTargetType

class HashService:
    """
    Ostrá služba pre výpočet obsahu (SHA-256) pre:
    - 1 súbor
    - Viac súborov
    - 1 priečinok (s rekurziou a filtráciou šumu)
    - Viac priečinkov
    - Zmiešané vstupy (súbory aj priečinky naraz)
    """

    IGNORED_DIRS = {
        "__pycache__", ".git", ".idea", ".vscode", "build", "dist", 
        ".pytest_cache", ".venv", "venv", "env"
    }
    
    IGNORED_FILES = {
        ".DS_Store", "Thumbs.db"
    }

    @staticmethod
    def _should_ignore(name: str, is_dir: bool) -> bool:
        if is_dir:
            return name in HashService.IGNORED_DIRS
        else:
            if name in HashService.IGNORED_FILES:
                return True
            if name.endswith((".pyc", ".pyo", ".pyd")):
                return True
            return False

    @classmethod
    def _hash_single_file(cls, file_path: str, hasher: hashlib._Hash):
        if os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    hasher.update(chunk)

    @classmethod
    def _hash_folder_recursive(cls, folder_path: str, hasher: hashlib._Hash, base_prefix: str = ""):
        abs_folder = os.path.abspath(folder_path)
        if not os.path.exists(abs_folder) or not os.path.isdir(abs_folder):
            return

        file_records = []
        try:
            for root, dirs, files in os.walk(abs_folder):
                dirs[:] = [d for d in sorted(dirs) if not cls._should_ignore(d, is_dir=True)]
                for file in sorted(files):
                    if cls._should_ignore(file, is_dir=False):
                        continue
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, abs_folder)
                    file_records.append((rel_path, full_path))
        except Exception:
            return

        for rel_path, full_path in sorted(file_records, key=lambda x: x[0]):
            identifier = os.path.join(base_prefix, rel_path).replace("\\", "/")
            hasher.update(identifier.encode('utf-8', errors='ignore'))
            cls._hash_single_file(full_path, hasher)

    @classmethod
    def calculate_state_hash(cls, targets: str | list[str]) -> tuple[str, HashTargetType]:
        """
        Vypočíta SHA-256 hash pre ľubovoľný variant vstupu (str alebo list[str]).
        Vyhadzuje ValueError pri neplatných alebo neexistujúcich cestách.
        """
        if not targets:
            raise ValueError("HashService: Vstupné cesty (targets) nemôžu byť prázdne.")

        path_list = [targets] if isinstance(targets, str) else list(targets)
        if not path_list:
            raise ValueError("HashService: Zoznam ciest je prázdny.")

        # Overenie existencie všetkých vstupov
        for p in path_list:
            if not p or not os.path.exists(p):
                raise FileNotFoundError(f"HashService: Cesta neexistuje: {p}")

        hasher = hashlib.sha256()

        if len(path_list) == 1:
            single = path_list[0]
            if os.path.isfile(single):
                target_type = HashTargetType.SINGLE_FILE
                hasher.update(os.path.basename(single).encode('utf-8', errors='ignore'))
                cls._hash_single_file(single, hasher)
            else:
                target_type = HashTargetType.SINGLE_FOLDER
                cls._hash_folder_recursive(single, hasher)
        else:
            is_all_files = all(os.path.isfile(p) for p in path_list)
            is_all_folders = all(os.path.isdir(p) for p in path_list)

            if is_all_files:
                target_type = HashTargetType.MULTIPLE_FILES
            elif is_all_folders:
                target_type = HashTargetType.MULTIPLE_FOLDERS
            else:
                target_type = HashTargetType.MIXED

            valid_paths = [os.path.abspath(p) for p in path_list]
            valid_paths.sort()

            for p in valid_paths:
                if os.path.isfile(p):
                    hasher.update(os.path.basename(p).encode('utf-8', errors='ignore'))
                    cls._hash_single_file(p, hasher)
                else:
                    folder_name = os.path.basename(p.rstrip(os.sep))
                    cls._hash_folder_recursive(p, hasher, base_prefix=folder_name)

        return hasher.hexdigest(), target_type

    @classmethod
    def verify_state_changed(cls, targets: str | list[str], last_saved_hash: str) -> bool:
        """
        Porovná aktuálny vypočítaný hash s uloženým.
        Vrátí True, ak sa obsah zmenil alebo uložený hash neexistuje.
        """
        if not last_saved_hash:
            return True

        current_hash, _ = cls.calculate_state_hash(targets)
        return current_hash != last_saved_hash
#----------------------------------------
# Súbor: core/logic/sluzby/path_normalizer.py
#----------------------------------------

import os
from pathlib import Path

class PathNormalizer:
    r"""
    Služba pre bezpečnú úpravu ciest tak, aby nepadali v systémových 
    príkazoch, pip inštalátoroch ani v requirements.txt.
    """

    @staticmethod
    def to_safe_pip_path(path_str: str) -> str:
        r"""
        Zmení akúkoľvek cestu (napr. C:\Moja\Cesta) na bezpečný 
        multiplatformový formát s lomítkami dopredu (C:/Moja/Cesta).
        """
        if not path_str:
            return ""
            
        try:
            return Path(path_str).resolve().as_posix()
        except Exception:
            return str(path_str).replace("\\", "/")

    @staticmethod
    def to_os_path(path_str: str) -> str:
        r"""
        Vráti cestu do natívneho formátu pre daný operačný systém.
        """
        if not path_str:
            return ""
        return os.path.normpath(path_str)

    # =========================================================================
    # NOVÁ SAMOOPRAVNÁ METÓDA (AUTO-HEALING PRE REQUIREMENTS.TXT)
    # =========================================================================
    @staticmethod
    def sanitize_requirements_file(file_path: str) -> None:
        r"""
        Prečíta requirements.txt a ak nájde akékoľvek cesty so spätnými lomítkami (\),
        automaticky ich na disku opraví na dopredné lomítka (/) ešte predtým,
        než súbor prečíta PIP inštalátor.
        """
        if not file_path or not os.path.exists(file_path):
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            lines = content.splitlines()
            modified = False
            new_lines = []

            for line in lines:
                clean = line.strip()
                # Ak riadok obsahuje -e alebo --editable
                if clean.startswith("-e ") or clean.startswith("--editable "):
                    parts = clean.split(maxsplit=1)
                    prefix = parts[0]
                    path_part = parts[1] if len(parts) > 1 else ""
                    
                    safe_path = PathNormalizer.to_safe_pip_path(path_part.strip().strip('\'"'))
                    new_line = f"{prefix} {safe_path}"
                    
                    if new_line != line:
                        modified = True
                    new_lines.append(new_line)
                else:
                    new_lines.append(line)

            # Ak sme našli a opravili chybné lomítko, prepíšeme súbor na disku
            if modified:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(new_lines) + "\n")
        except Exception as e:
            print(f"[PathNormalizer] Chyba pri samooprave requirements.txt: {e}")
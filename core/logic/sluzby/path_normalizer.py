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
        """
        ZÁKAZ ZÁPISU:
        Originálny requirements.txt je deklarovaný stav a nesmie sa prepisovať.
        Všetka normalizácia prebieha výhradne cez dočasné súbory v PipManageri.
        """
        pass
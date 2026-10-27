#----------------------------------------------------
# Súbor: core/core_states.py
# Centrálny katalóg stavov a typov celého jadra (0 závislostí).
#----------------------------------------------------

from enum import Enum


class CoreService(str, Enum):
    """Katalóg registrovaných služieb jadra."""
    IDE_PATHS = "IDE_PATHS"
    LANGUAGE = "LANGUAGE"

class IDEType(str, Enum):
    """Typ editora."""
    VSCODE = "vscode"
    CURSOR = "cursor"


class IDEStatus(str, Enum):
    """Fyzický stav binárky na disku."""
    PORTABLE = "PORTABLE"      # Overený súbor na USB / v prenosnej zložke
    SYSTEM = "SYSTEM"          # Overený súbor v systéme (PATH / Program Files / AppData)
    NOT_FOUND = "NOT_FOUND"    # Súbor fyzicky neexistuje na disku


class IDEProfileMode(str, Enum):
    """Režim používateľského profilu."""
    CUSTOM_PROFILE = "CUSTOM_PROFILE"  # Vlastný VenvHub profil (data/ a extensions/)
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"  # Štandardný systémový profil (%APPDATA%)


#----------------------------------------------------
# core/logic/sluzby/language/language_manager.py
# Stavy pre jazyk
#----------------------------------------------------

# --- Pridáme stavy pre jazyk ---
class LanguageStatus(str, Enum):
    """Výsledok pokusu o načítanie jazykového súboru."""
    EXACT_MATCH = "EXACT_MATCH"        # Našiel sa presný kód (napr. sk_SK)
    FALLBACK_SHORT = "FALLBACK_SHORT"  # Našiel sa len skrátený kód (napr. sk)
    FALLBACK_EN = "FALLBACK_EN"        # Nenašlo sa nič, použil sa default en_US
    ERROR = "ERROR"                    # Súbor existuje, ale JSON je poškodený


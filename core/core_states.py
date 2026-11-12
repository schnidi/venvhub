#----------------------------------------------------
# Súbor: core/core_states.py
# Centrálny katalóg stavov a typov celého jadra (0 závislostí).
#----------------------------------------------------

from enum import Enum


class CoreService(str, Enum):
    """Katalóg registrovaných služieb jadra."""
    IDE_PATHS = "IDE_PATHS"
    LANGUAGE = "LANGUAGE"
    PACKAGE_UPDATE = "PACKAGE_UPDATE"
    PACKAGE_OPERATIONS = "PACKAGE_OPERATIONS"
    EDITABLE_OPERATIONS = "EDITABLE_OPERATIONS"
    LOCAL_LINKER = "LOCAL_LINKER"
    PORTABILITY_GUARD = "PORTABILITY_GUARD"

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

#----------------------------------------------------
# ccore/logic/sluzby/venv/pack_inst_unis.py
# Stavy pre jazyk
#----------------------------------------------------

class PackageOperationStatus(str, Enum):
    """Výsledok pokusu o inštaláciu alebo odinštaláciu balíčka."""
    SUCCESS = "SUCCESS"                             # Všetko prebehlo úspešne
    SKIPPED = "SKIPPED"                             # Nebolo čo robiť (balíčky už sú nainštalované)
    SUCCESS_WITH_CONFLICTS = "SUCCESS_WITH_CONFLICTS" # Nainštalované, ale pip/uv check vyhodil konflikty závislostí
    BLOCKED = "BLOCKED"                             # Operáciu zablokoval APT Guard (napr. balíček drží Linker)
    ERROR = "ERROR"                                 # Zlyhanie inštalátora (napr. výpadok siete)


# ====================================================
# STAVY PRE EDITOVATEĽNÉ BALÍČKY (pip -e)
# ====================================================

class EditableOperationStatus(str, Enum):
    """Výsledok operácie s editovateľným balíčkom (pip -e)."""
    SUCCESS = "SUCCESS"                                 # Úspešne nainštalované / odinštalované
    SKIPPED = "SKIPPED"                                 # Preskočené (nebolo čo robiť)
    SUCCESS_WITH_CONFLICTS = "SUCCESS_WITH_CONFLICTS"   # Nainštalované, ale pip/uv check hlási konflikty
    BLOCKED = "BLOCKED"                                 # Zablokované ochranou APT (napr. väzba v requirements.txt)
    INVALID_PROJECT = "INVALID_PROJECT"                 # Priečinok neobsahuje setup.py ani pyproject.toml
    ERROR = "ERROR"                                     # Kritické zlyhanie inštalátora (syntax error, pád kompilácie)


# ====================================================
# STAVY PRE LINKER BALÍČKY (linker)
# ====================================================

class LinkerOperationStatus(str, Enum):
    """Výsledok operácie prepájania lokálnych vývojových balíčkov."""
    SUCCESS = "SUCCESS"                     # Všetko prebehlo úspešne, zmeny sa uložili
    NO_CHANGES = "NO_CHANGES"               # Všetko bolo aktuálne, nebolo čo robiť
    MISSING_LOCAL_DEP = "MISSING_LOCAL_DEP" # Chýba nejaký lokálny modul v zložke
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"   # Chyba pri sťahovaní externých PIP závislostí
    ERROR = "ERROR"                         # Kritická chyba (napr. problém so zápisom na disk)


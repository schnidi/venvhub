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
    PYTHON_DETECTOR = "PYTHON_DETECTOR"
    UV_DETECTOR = "UV_DETECTOR"

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


# ====================================================
# STAVY PRE PYTHON DETEKTOR
# ====================================================

class PythonOrigin(str, Enum):
    """Pôvod a typ Python runtime prostredia."""
    SYSTEM = "SYSTEM"          # Systémový Python (Windows py, Linux /usr/bin, macOS Homebrew/Framework)
    LOCAL = "LOCAL"            # Lokálny prenosný Python v PyRuntimes (Embed / Standalone)
    VENV = "VENV"              # Virtuálne prostredie

class PythonPipStatus(str, Enum):
    """Fyzický stav nástroja PIP a site-packages v danom runtime."""
    OK = "OK"                  # PIP je overený, funkčný a pripravený
    CHECKING = "CHECKING"      # Prebieha asynchrónne overovanie na pozadí
    MISSING = "MISSING"        # PIP fyzicky chýba (typické pre čistý embed zip)
    ERROR = "ERROR"            # PIP havaroval (Access Violation, poškodený runtime)

class PythonDetectorStatus(str, Enum):
    """Výsledok procesu detekcie Python prostredí."""
    SUCCESS = "SUCCESS"                 # Našiel sa aspoň jeden platný interpreter
    FALLBACK_ONLY = "FALLBACK_ONLY"     # Nenašiel sa žiadny systémový, použil sa iba sys.executable
    NO_PYTHONS_FOUND = "NO_PYTHONS_FOUND" # Kritický stav - nenašiel sa vôbec žiadny interpreter
    ERROR = "ERROR"                     # Chyba pri skenovaní


# ====================================================
# STAVY PRE UV DETEKTOR (UV_DETECTOR)
# ====================================================

class UVStatus(str, Enum):
    """Fyzický stav a pôvod binárky UV na disku a v systéme."""
    BUNDLED = "BUNDLED"          # Vstavané priamo v distribúcii aplikácie (MEIPASS / root)
    ACTIVE_VENV = "ACTIVE_VENV"  # V aktívnom venv/Python prostredí (Scripts/ alebo bin/)
    STANDALONE = "STANDALONE"    # V lokálnych inštaláciách (Homebrew, Cargo, ~/.local/bin)
    SYSTEM_PATH = "SYSTEM_PATH"  # Globálne v systémovej premennej PATH
    NOT_FOUND = "NOT_FOUND"      # UV sa v systéme vôbec nenašlo
    ERROR = "ERROR"              # Súbor existuje, ale nefunguje (havária, zlá architektúra, chýbajúce práva)


# ====================================================
# STAVY PRE PYTHON DETEKTOR
# ====================================================

class PythonOrigin(str, Enum):
    """Pôvod a typ Python runtime prostredia."""
    SYSTEM = "SYSTEM"          # Systémový Python (Windows py, Linux /usr/bin, macOS Homebrew)
    LOCAL = "LOCAL"            # Lokálny prenosný Python v PyRuntimes (Embed)
    VENV = "VENV"              # Virtuálne prostredie


class PythonPipStatus(str, Enum):
    """Fyzický stav nástroja PIP v danom runtime."""
    OK = "OK"                  # PIP je overený a funkčný
    CHECKING = "CHECKING"      # Prebieha asynchrónne overovanie na pozadí
    MISSING = "MISSING"        # PIP fyzicky chýba (čistý embed zip)
    ERROR = "ERROR"            # PIP havaroval alebo je runtime poškodený


class PythonDetectorStatus(str, Enum):
    """Výsledok procesu detekcie Python prostredí."""
    SUCCESS = "SUCCESS"                 # Našiel sa aspoň jeden platný interpreter
    FALLBACK_ONLY = "FALLBACK_ONLY"     # Nenašiel sa žiadny systémový, použitý len sys.executable
    NO_PYTHONS_FOUND = "NO_PYTHONS_FOUND" # Kritický stav - nenašiel sa žiadny interpreter
    ERROR = "ERROR"                     # Chyba pri skenovaní OS


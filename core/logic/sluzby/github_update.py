#----------------------------------------
# Súbor: core/logic/sluzby/github_update.py
#----------------------------------------

import re
import threading
import requests
from core.logic.sluzby.about_logic import AboutLogic
from core.logic.language_manager import LanguageManager


class GitHubUpdate:
    """
    Centrálna služba pre kontrolu, porovnávanie a správu aktualizácií z GitHubu.
    Udržiava stav v pamäti (RAM) pre okamžitý prístup celej aplikácie.
    """

    REPO_OWNER = "schnidi"
    REPO_NAME = "venvhub"
    API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
    WEB_BASE_URL = "https://schnidi.github.io/venvhub/"
    FALLBACK_RELEASE_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/latest"

    SUPPORTED_WEB_LANGS = {"sk", "en"}
    DEFAULT_WEB_LANG = "en"

    # --- 4 STAVY V PAMÄTI ---
    _lock = threading.Lock()
    _is_update_available: bool = False
    _latest_version: str | None = None
    _release_url: str | None = None
    _was_checked: bool = False

    @staticmethod
    def _parse_version(version_str: str) -> tuple[int, ...]:
        """Prevedie 'v2.5.28' alebo '2.5.28' na čísla (2, 5, 28) pre sémantické porovnanie."""
        if not version_str:
            return (0,)
        clean = str(version_str).strip().lstrip("vV")
        numbers = re.findall(r"\d+", clean)
        return tuple(int(n) for n in numbers) if numbers else (0,)

    @classmethod
    def check_for_updates(cls, force_refresh: bool = False) -> bool:
        """
        Zavolá GitHub API, zistí najnovšiu verziu, porovná s lokálnou verziou
        a uloží výsledok do pamäte.
        """
        with cls._lock:
            if cls._was_checked and not force_refresh:
                return cls._is_update_available

        current_ver_str = AboutLogic.get_app_version()
        current_ver_tuple = cls._parse_version(current_ver_str)

        headers = {
            "User-Agent": f"VenvHubPro/{current_ver_str}",
            "Accept": "application/vnd.github+json"
        }

        try:
            response = requests.get(cls.API_URL, headers=headers, timeout=4)
            if response.status_code == 200:
                data = response.json()
                raw_tag = data.get("tag_name", "")
                latest_ver_str = raw_tag.lstrip("vV").strip() if raw_tag else current_ver_str
                release_url = data.get("html_url", cls.FALLBACK_RELEASE_URL)

                latest_ver_tuple = cls._parse_version(latest_ver_str)
                is_newer = latest_ver_tuple > current_ver_tuple

                with cls._lock:
                    cls._latest_version = latest_ver_str
                    cls._release_url = release_url
                    cls._is_update_available = is_newer
                    cls._was_checked = True

                return is_newer
            else:
                with cls._lock:
                    cls._latest_version = current_ver_str
                    cls._release_url = cls.FALLBACK_RELEASE_URL
                    cls._is_update_available = False
                    cls._was_checked = True
                return False

        except Exception:
            with cls._lock:
                cls._latest_version = current_ver_str
                cls._release_url = cls.FALLBACK_RELEASE_URL
                cls._is_update_available = False
                cls._was_checked = True
            return False

    @classmethod
    def get_status(cls) -> bool:
        """Vráti True, ak je dostupná nová verzia."""
        with cls._lock:
            return cls._is_update_available

    @classmethod
    def get_latest_version(cls) -> str:
        """Vráti reťazec najnovšej verzie z pamäte (napr. '2.5.29')."""
        with cls._lock:
            return cls._latest_version or AboutLogic.get_app_version()

    @classmethod
    def get_download_url(cls) -> str:
        """Vráti webový odkaz lokalizovaný podľa jazyka aplikácie."""
        raw_lang = getattr(LanguageManager, "_current_lang_code", "en_US")
        short_lang = str(raw_lang).split("_")[0].lower().strip()

        if short_lang in cls.SUPPORTED_WEB_LANGS:
            lang_param = short_lang
        else:
            lang_param = cls.DEFAULT_WEB_LANG

        return f"{cls.WEB_BASE_URL}?lang={lang_param}"
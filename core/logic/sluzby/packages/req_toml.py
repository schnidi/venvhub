# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Súbor: core/logic/sluzby/packages/req_toml.py
# Nízkoúrovňová služba pre export závislostí z venvu do štandardu pyproject.toml.
# Plne lokalizovaná cez LanguageBridge, s podporou extras [socks], pip -e aj direct URL.
#-------------------------------------------------------------------------------

import os
import json
from enum import Enum
from typing import Optional, Callable, Any

from core.logic.sluzby.apt_logic import AptLogic
from core.logic.sluzby.language_bridge import LanguageBridge


def _tr(key: str, default: str, **kwargs) -> str:
    """Pomocná funkcia pre lokalizáciu textov cez LanguageBridge."""
    text = LanguageBridge.translate(key, default)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            pass
    return text


class TomlExportStatus(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    NO_VENV = "NO_VENV"
    WRITE_ERROR = "WRITE_ERROR"


class ReqTomlService:

    @staticmethod
    def _get_direct_url_spec(dist_info_path: str, norm_pkg_name: str) -> Optional[str]:
        """Zistí Git alebo URL adresu z PEP 610 direct_url.json ak existuje."""
        direct_url_file = os.path.join(dist_info_path, "direct_url.json")
        if not os.path.exists(direct_url_file):
            return None

        try:
            with open(direct_url_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            url = data.get("url", "")
            vcs_info = data.get("vcs_info", {})

            if vcs_info:
                vcs_type = vcs_info.get("vcs", "git")
                rev = vcs_info.get("requested_revision") or vcs_info.get("commit_id")
                if rev:
                    return f"{norm_pkg_name} @ {vcs_type}+{url}@{rev}"
                return f"{norm_pkg_name} @ {vcs_type}+{url}"

            if url.startswith(("http://", "https://", "file://")):
                return f"{norm_pkg_name} @ {url}"
        except Exception:
            pass

        return None

    @classmethod
    def _find_dist_info_dir(cls, site_pkgs: str, norm_pkg_name: str) -> Optional[str]:
        """Nájde .dist-info priečinok pre daný balíček v site-packages."""
        if not site_pkgs or not os.path.exists(site_pkgs):
            return None
        try:
            for entry in os.listdir(site_pkgs):
                if entry.lower().endswith(".dist-info"):
                    stem = entry[:-len(".dist-info")]
                    raw_name, _, _ = stem.partition("-")
                    if AptLogic._normalize(raw_name) == norm_pkg_name:
                        return os.path.join(site_pkgs, entry)
        except Exception:
            pass
        return None

    @classmethod
    def build_dependencies_list(
        cls,
        venv_path: str,
        master_data: dict,
        selected_packages: Optional[list[str]] = None,
        pin_exact: bool = True
    ) -> list[str]:
        flat_index = master_data.get("flat_index", {})
        state_data = master_data.get("state_data", {})
        site_pkgs = AptLogic._get_site_packages_dir(venv_path)

        dependencies = []
        op = "==" if pin_exact else ">="

        req_cache = set(state_data.get("requirements_cache", []))
        explicit_pkgs = set(state_data.get("explicit", []))
        editable_bounds = state_data.get("editable_packages_bound", {})
        req_extras = state_data.get("requirements_extras_bound", {})
        exp_extras = state_data.get("explicit_extras_bound", {})

        # Systémové balíčky venvu (bezpečne, bez AttributeError)
        try:
            system_pkgs = AptLogic.ensure_system_packages(venv_path)
        except Exception:
            system_pkgs = set()

        # 1. Zozbierame mapu väzieb: rodič -> deti
        extras_by_parent: dict[str, set[str]] = {}
        for parent, kids in req_extras.items():
            extras_by_parent.setdefault(AptLogic._normalize(parent), set()).update(
                [AptLogic._normalize(k) for k in kids]
            )
        for parent, kids in exp_extras.items():
            extras_by_parent.setdefault(AptLogic._normalize(parent), set()).update(
                [AptLogic._normalize(k) for k in kids]
            )

        # Množina všetkých detí, ktoré sú naviazané ako extras
        all_bound_children = set()
        for kids in extras_by_parent.values():
            all_bound_children.update(kids)

        # 2. Určenie cieľových balíčkov na export
        if selected_packages is not None:
            raw_targets = [AptLogic._normalize(p) for p in selected_packages]
        else:
            raw_targets = [
                norm for norm, info in flat_index.items()
                if (
                    norm in req_cache 
                    or norm in explicit_pkgs 
                    or info.get("is_editable")
                    or (info.get("is_requirement") and norm not in all_bound_children)
                    or (info.get("is_explicit") and norm not in all_bound_children)
                )
                and norm not in system_pkgs
            ]

        # Vylúčime balíčky, ktoré sú len extras deťmi iného exportovaného rodiča
        targets = []
        raw_targets_set = set(raw_targets)

        for norm in sorted(raw_targets_set):
            info = flat_index.get(norm)
            if not info:
                continue

            # Ak je to čisté dieťa viazané na rodiča, ktorý je tiež v exporte, preskočíme ho (bude v [extras])
            if norm in all_bound_children and norm not in req_cache and norm not in explicit_pkgs:
                has_parent_in_targets = any(
                    parent in raw_targets_set 
                    for parent, kids in extras_by_parent.items() 
                    if norm in kids
                )
                if has_parent_in_targets:
                    continue

            targets.append(norm)

        # 3. Formátovanie závislostí vrátane EXTRAS (napr. requests[socks])
        for norm in targets:
            info = flat_index.get(norm)
            if not info:
                continue

            raw_pkg_name = info.get("name", norm)

            # Zistíme, či má tento rodičovský balíček naviazané extras
            bound_kids = extras_by_parent.get(norm, set())
            extras_suffix = ""
            if bound_kids:
                extras_map = AptLogic.get_extras_map_from_metadata(venv_path, norm)
                active_extras = set()
                for extra_name, extra_pkgs in extras_map.items():
                    norm_extra_pkgs = {AptLogic._normalize(p) for p in extra_pkgs}
                    if norm_extra_pkgs and (norm_extra_pkgs & bound_kids):
                        active_extras.add(extra_name)

                if active_extras:
                    extras_suffix = f"[{','.join(sorted(active_extras))}]"

            pkg_spec_base = f"{raw_pkg_name}{extras_suffix}"

            # Kontrola Git / URL zdroja
            dist_info = cls._find_dist_info_dir(site_pkgs, norm)
            if dist_info:
                direct_spec = cls._get_direct_url_spec(dist_info, pkg_spec_base)
                if direct_spec:
                    dependencies.append(direct_spec)
                    continue

            # Editovateľný balíček (pip -e)
            if info.get("is_editable"):
                e_info = editable_bounds.get(norm, {})
                e_path = e_info.get("path")
                if e_path:
                    safe_url_path = e_path.replace("\\", "/")
                    dependencies.append(f"{pkg_spec_base} @ file://{safe_url_path}")
                    continue

            # Štandardný PyPI balíček (napr. requests[socks]==2.31.0)
            version = info.get("version")
            if version and version != "unknown":
                dependencies.append(f"{pkg_spec_base}{op}{version}")
            else:
                dependencies.append(pkg_spec_base)

        return dependencies

    @classmethod
    def export_to_toml(
        cls,
        venv_path: str,
        target_file_path: str,
        master_data: dict,
        project_name: str = "my-project",
        selected_packages: Optional[list[str]] = None,
        pin_exact: bool = True,
        log_callback: Optional[Callable[[str], None]] = None
    ) -> tuple[TomlExportStatus, str, int]:
        def _log(msg):
            if log_callback:
                log_callback(msg)

        if not venv_path or not os.path.exists(venv_path):
            err_no_venv = _tr("toml_export_err_no_venv", "Venv neexistuje: {path}", path=venv_path)
            return TomlExportStatus.NO_VENV, err_no_venv, 0

        _log(_tr("toml_export_log_gathering", "🔍 [TOML Export] Zbieram informácie o balíčkoch z venvu..."))

        try:
            deps = cls.build_dependencies_list(
                venv_path=venv_path,
                master_data=master_data,
                selected_packages=selected_packages,
                pin_exact=pin_exact
            )
        except Exception as e:
            err_build = _tr("toml_export_err_build", "Chyba pri zostavovaní závislostí: {err}", err=str(e))
            _log(f"❌ [TOML Export] {err_build}")
            return TomlExportStatus.WRITE_ERROR, err_build, 0

        if not deps:
            _log(_tr("toml_export_log_empty", "⚠️ [TOML Export] Nenašli sa žiadne vhodné balíčky na export."))
            err_empty = _tr("toml_export_err_empty_desc", "Neboli vybrané ani nájdené žiadne balíčky.")
            return TomlExportStatus.EMPTY, err_empty, 0

        deps_formatted = "\n".join([f'    "{d}",' for d in deps])
        
        toml_content = f"""[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{project_name}"
version = "0.1.0"
description = "Exported from VenvHub Pro"
readme = "README.md"
requires-python = ">=3.8"
dependencies = [
{deps_formatted}
]
"""

        try:
            target_dir = os.path.dirname(os.path.abspath(target_file_path))
            os.makedirs(target_dir, exist_ok=True)

            with open(target_file_path, "w", encoding="utf-8") as f:
                f.write(toml_content)

            # Plne preložená úspešná hláška do logu / status baru
            success_msg = _tr(
                "toml_export_log_success", 
                "✅ [TOML Export] Súbor '{filename}' úspešne vytvorený ({count} balíčkov).",
                filename=os.path.basename(target_file_path),
                count=len(deps)
            )
            _log(success_msg)
            return TomlExportStatus.SUCCESS, target_file_path, len(deps)

        except Exception as e:
            err_msg = _tr("toml_export_err_write", "Chyba pri zápise do súboru: {err}", err=str(e))
            _log(f"❌ [TOML Export] {err_msg}")
            return TomlExportStatus.WRITE_ERROR, err_msg, 0
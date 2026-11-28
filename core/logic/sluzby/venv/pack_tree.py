# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Súbor: core/logic/sluzby/venv/pack_tree.py
# Služba pre zber stromu závislostí vybudovaná priamo na AptLogic.
# POHĽAD A: Štruktúrovaný strom podľa zdrojov (Vlastníctvo / "Kto čo drží").
#-------------------------------------------------------------------------------

import os
import json
from enum import IntEnum
from typing import Optional, Any
from PyQt6.QtCore import QThread, pyqtSignal

from core._path import Paths
from core.logic.sluzby.apt_logic import AptLogic


class PackageCategory(IntEnum):
    ALL = 0
    SYSTEM = 1
    PACKAGES = 2     # requirements.txt
    EDITABLE = 3     # pip -e
    LINKER = 4       # Linker moduly
    ORPHANS = 5      # Siroty
    EXPLICIT = 6     # Manuálne nainštalované


class PackageTreeService:

    @staticmethod
    def _read_package_metadata(site_pkgs: str) -> dict[str, dict]:
        """Načíta informácie o balíčkoch priamo z ich .dist-info/METADATA."""
        meta_index = {}
        if not site_pkgs or not os.path.exists(site_pkgs):
            return meta_index

        try:
            for entry in os.listdir(site_pkgs):
                if entry.lower().endswith(".dist-info"):
                    folder_path = os.path.join(site_pkgs, entry)
                    if not os.path.isdir(folder_path):
                        continue

                    stem = entry[:-len(".dist-info")]
                    raw_name, _, raw_version = stem.partition("-")
                    norm_name = AptLogic._normalize(raw_name)

                    summary = ""
                    license_str = ""
                    home_page = ""

                    meta_file = os.path.join(folder_path, "METADATA")
                    if os.path.isfile(meta_file):
                        try:
                            with open(meta_file, "r", encoding="utf-8", errors="replace") as f:
                                for line in f:
                                    if line.startswith("Summary:"):
                                        summary = line.split(":", 1)[1].strip()
                                    elif line.startswith("License:"):
                                        license_str = line.split(":", 1)[1].strip()
                                    elif line.startswith("Home-page:"):
                                        home_page = line.split(":", 1)[1].strip()
                                    elif line.strip() == "":
                                        break
                        except Exception:
                            pass

                    meta_index[norm_name] = {
                        "name": raw_name,
                        "version": raw_version,
                        "summary": summary,
                        "license": license_str,
                        "homepage": home_page
                    }
        except Exception:
            pass

        return meta_index

    @classmethod
    def build_tree_master(cls, venv_path: str, core=None) -> dict[str, Any]:
        """
        Zanalyzuje prostredie, načíta stavový JSON a graf závislostí.
        Vytvorí kompletný flat_index balíčkov s ich vlastníkmi a väzbami.
        """
        if not venv_path or not os.path.exists(venv_path):
            return {"error": "Venv path does not exist", "roots": [], "flat_index": {}}

        try:
            state_data = AptLogic._load_state_data(venv_path)
        except RuntimeError as e:
            return {"error": str(e), "roots": [], "flat_index": {}}

        site_pkgs = AptLogic._get_site_packages_dir(venv_path)
        meta_index = cls._read_package_metadata(site_pkgs)

        # 1. Získame graf priamych závislostí
        raw_graph = AptLogic.get_dependency_graph(venv_path, core) or {}
        graph: dict[str, list[str]] = {
            AptLogic._normalize(k): [AptLogic._normalize(d) for d in v] 
            for k, v in raw_graph.items()
        }

        all_pkgs = set(graph.keys()) | set(meta_index.keys())

        # 2. Reverzný index z grafu (tvrdé závislosti)
        parents_map: dict[str, set[str]] = {pkg: set() for pkg in all_pkgs}
        for parent, children in graph.items():
            for child in children:
                norm_child = AptLogic._normalize(child)
                parents_map.setdefault(norm_child, set()).add(parent)

        # 3. Zdroje z venvhub_apt_state.json
        system_pkgs = AptLogic.ensure_system_packages(venv_path)
        explicit_pkgs = set(state_data.get("explicit", []))
        req_cache = set(state_data.get("requirements_cache", []))
        owned_packages = AptLogic.get_all_owned_packages(venv_path)

        all_extras_bound = AptLogic.load_extras_bound(venv_path, context="all")
        exp_extras_bound = state_data.get("explicit_extras_bound", {})
        req_extras_bound = state_data.get("requirements_extras_bound", {})
        linker_bounds = state_data.get("linker_packages_bound", {})
        editable_bounds = state_data.get("editable_packages_bound", {})

        flat_index = {}
        category_counts = {cat.value: 0 for cat in PackageCategory}

        for pkg in sorted(all_pkgs):
            norm = AptLogic._normalize(pkg)
            meta = meta_index.get(norm, {})
            direct_deps = [AptLogic._normalize(d) for d in graph.get(norm, [])]
            parents = sorted(list(parents_map.get(norm, set())))

            owners = []
            extra_parents = []

            # --- A. SYSTÉM ---
            is_system = norm in system_pkgs
            if is_system:
                owners.append("Systémový balíček")

            # --- B. EXPLICIT (Priamy aj cez Extras) ---
            is_explicit = norm in explicit_pkgs
            if is_explicit:
                owners.append("Manuálne (explicit)")

            for exp_parent, kids in exp_extras_bound.items():
                if norm in [AptLogic._normalize(k) for k in kids]:
                    owners.append(f"Manuálne (explicit) cez {exp_parent} [extra]")
                    extra_parents.append(f"{exp_parent} [extra]")
                    is_explicit = True

            # --- C. REQUIREMENTS.TXT (Priamy aj cez Extras) ---
            is_req = norm in req_cache
            if is_req:
                owners.append("requirements.txt")

            for req_parent, kids in req_extras_bound.items():
                if norm in [AptLogic._normalize(k) for k in kids]:
                    owners.append(f"requirements.txt cez {req_parent} [extra]")
                    extra_parents.append(f"{req_parent} [extra]")
                    is_req = True

            # --- D. LINKER MODULY (Priame aj cez Extras) ---
            is_linker = False
            for mod_name, mod_info in linker_bounds.items():
                mod_pkgs = [AptLogic._normalize(p) for p in mod_info.get("packages", [])]
                if norm in mod_pkgs:
                    owners.append(f"Linker: {mod_name}")
                    is_linker = True
                    continue
                for p_pkg, c_list in mod_info.get("extras_bound", {}).items():
                    if norm in [AptLogic._normalize(c) for c in c_list]:
                        owners.append(f"Linker: {mod_name} cez {p_pkg} [extra]")
                        extra_parents.append(f"{p_pkg} [extra]")
                        is_linker = True
                        break

            # --- E. EDITOVATEĽNÉ PROJEKTY (pip -e) ---
            is_editable = norm in editable_bounds
            if is_editable:
                owners.append("pip -e (Projekt)")

            for e_name, e_info in editable_bounds.items():
                if norm == e_name:
                    continue
                e_pkgs = [AptLogic._normalize(p) for p in e_info.get("packages", [])]
                if norm in e_pkgs:
                    owners.append(f"Editable: {e_name}")
                    is_editable = True
                    continue
                for p_pkg, c_list in e_info.get("extras_bound", {}).items():
                    if norm in [AptLogic._normalize(c) for c in c_list]:
                        owners.append(f"Editable: {e_name} cez {p_pkg} [extra]")
                        extra_parents.append(f"{p_pkg} [extra]")
                        is_editable = True
                        break

            # Spojíme tvrdých rodičov aj extras rodičov
            all_parents_set = set(parents) | set(extra_parents)
            all_parents_list = sorted(list(all_parents_set))

            req_by_sources = set(owners) | set(all_parents_list)
            req_by_text = ", ".join(sorted(list(req_by_sources))) if req_by_sources else "-"

            # Očistené o neexistujúci CORE_TOOLS
            is_orphan = (not is_system) and (norm not in owned_packages) and (len(all_parents_list) == 0)

            # Počítadlá pre horné tlačidlá
            if is_orphan:
                category_counts[PackageCategory.ORPHANS.value] += 1
            if is_system:
                category_counts[PackageCategory.SYSTEM.value] += 1
            if is_req:
                category_counts[PackageCategory.PACKAGES.value] += 1
            if is_editable:
                category_counts[PackageCategory.EDITABLE.value] += 1
            if is_linker:
                category_counts[PackageCategory.LINKER.value] += 1
            if is_explicit:
                category_counts[PackageCategory.EXPLICIT.value] += 1

            category_counts[PackageCategory.ALL.value] += 1

            flat_index[norm] = {
                "id": norm,
                "name": meta.get("name", pkg),
                "normalized_name": norm,
                "version": meta.get("version", "unknown"),
                "summary": meta.get("summary", ""),
                "license": meta.get("license", ""),
                "homepage": meta.get("homepage", ""),
                "requires": direct_deps,
                "extras_bound": all_extras_bound.get(norm, []),
                "parents": all_parents_list,
                "owners": owners,
                "required_by_text": req_by_text,
                "is_orphan": is_orphan,
                "is_system": is_system,
                "is_explicit": is_explicit,
                "is_requirement": is_req,
                "is_editable": is_editable,
                "is_linker": is_linker
            }

        return {
            "venv_name": os.path.basename(venv_path),
            "venv_path": venv_path,
            "total_packages": len(all_pkgs),
            "counts": category_counts,
            "state_data": state_data,
            "flat_index": flat_index,
            "graph": graph
        }

    @classmethod
    def filter_tree(
        cls, 
        master_data: dict, 
        category: int | PackageCategory = PackageCategory.ALL, 
        single_package: Optional[str] = None
    ) -> list[dict]:
        flat_index = master_data.get("flat_index", {})
        state_data = master_data.get("state_data", {})
        cat_val = int(category)

        def build_pkg_node(
            pkg_norm: str, 
            branch_path: set[str], 
            depth: int = 0,
            is_extra_child: bool = False,
            extra_parent_name: str = "",
            context_extras: Optional[dict] = None
        ) -> dict:
            info = flat_index.get(pkg_norm, {})
            name = info.get("name", pkg_norm)

            node = {
                "id": pkg_norm,
                "name": name,
                "normalized_name": pkg_norm,
                "version": info.get("version", ""),
                "summary": info.get("summary", ""),
                "license": info.get("license", ""),
                "homepage": info.get("homepage", ""),
                "node_type": "package",
                "is_extra": is_extra_child,
                "extra_parent": extra_parent_name,
                "is_orphan": info.get("is_orphan", False),
                "owners": info.get("owners", []),
                "parents": info.get("parents", []),
                "required_by_text": info.get("required_by_text", "-"),
                "depth": depth,
                "circular": False,
                "dependencies": []
            }

            if pkg_norm in branch_path:
                node["circular"] = True
                return node

            new_branch = branch_path | {pkg_norm}
            children_nodes = []

            direct_deps = list(info.get("requires", []))

            bound_extras = []
            if context_extras and pkg_norm in context_extras:
                bound_extras = context_extras.get(pkg_norm, [])
            else:
                bound_extras = info.get("extras_bound", [])

            for ex in bound_extras:
                norm_ex = AptLogic._normalize(ex)
                if norm_ex not in direct_deps:
                    direct_deps.append(norm_ex)

            for dep_norm in direct_deps:
                is_ex = dep_norm in bound_extras
                children_nodes.append(build_pkg_node(
                    dep_norm, 
                    new_branch, 
                    depth + 1, 
                    is_extra_child=is_ex,
                    extra_parent_name=pkg_norm if is_ex else "",
                    context_extras=context_extras
                ))

            node["dependencies"] = children_nodes
            return node

        if single_package:
            norm_target = AptLogic._normalize(single_package)
            if norm_target in flat_index:
                return [build_pkg_node(norm_target, set())]
            return []

        linker_bounds = state_data.get("linker_packages_bound", {})
        editable_bounds = state_data.get("editable_packages_bound", {})
        req_cache = set(state_data.get("requirements_cache", []))
        req_extras = state_data.get("requirements_extras_bound", {})
        explicit_pkgs = set(state_data.get("explicit", []))
        explicit_extras = state_data.get("explicit_extras_bound", {})
        system_pkgs = AptLogic.ensure_system_packages(master_data.get("venv_path", ""))

        # 1. Linker moduly
        linker_nodes = []
        for mod_name, mod_info in sorted(linker_bounds.items(), key=lambda x: x[0].lower()):
            mod_pkgs = mod_info.get("packages", [])
            mod_ex = mod_info.get("extras_bound", {})
            mod_children = []
            for p in sorted(mod_pkgs):
                mod_children.append(build_pkg_node(p, set(), depth=1, context_extras=mod_ex))

            linker_nodes.append({
                "id": f"linker:{mod_name}",
                "name": mod_name,
                "normalized_name": AptLogic._normalize(mod_name),
                "version": "Modul",
                "summary": "Lokálne prelinkovaný vývojový modul (Linker)",
                "node_type": "linker_module",
                "is_extra": False,
                "owners": ["Linker"],
                "required_by_text": "Linker",
                "depth": 0,
                "circular": False,
                "dependencies": mod_children
            })

        # 2. Editovateľné projekty (pip -e)
        editable_nodes = []
        for e_name, e_info in sorted(editable_bounds.items(), key=lambda x: x[0].lower()):
            e_path = e_info.get("path", "")
            e_pkgs = e_info.get("packages", [])
            e_ex = e_info.get("extras_bound", {})
            e_children = []
            for p in sorted(e_pkgs):
                e_children.append(build_pkg_node(p, set(), depth=1, context_extras=e_ex))

            e_meta = flat_index.get(e_name, {})
            editable_nodes.append({
                "id": f"editable:{e_name}",
                "name": e_meta.get("name", e_name),
                "normalized_name": e_name,
                "version": e_meta.get("version", "pip -e"),
                "summary": f"Editovateľný projekt [{e_path}]",
                "node_type": "editable_project",
                "path": e_path,
                "is_extra": False,
                "owners": ["requirements.txt (pip -e)"],
                "required_by_text": "requirements.txt (pip -e)",
                "depth": 0,
                "circular": False,
                "dependencies": e_children
            })

        # 3. requirements.txt
        requirements_nodes = []
        for req_pkg in sorted(req_cache):
            requirements_nodes.append(build_pkg_node(req_pkg, set(), depth=1, context_extras=req_extras))

        # 4. Explicit (manuálne)
        explicit_nodes = []
        for exp_pkg in sorted(explicit_pkgs):
            explicit_nodes.append(build_pkg_node(exp_pkg, set(), depth=1, context_extras=explicit_extras))

        # 5. Systémové balíčky
        system_nodes = []
        for sys_pkg in sorted(system_pkgs):
            if sys_pkg in flat_index:
                system_nodes.append(build_pkg_node(sys_pkg, set(), depth=1))

        # 6. Siroty
        orphan_nodes = []
        for norm, info in sorted(flat_index.items(), key=lambda x: x[0]):
            if info.get("is_orphan"):
                orphan_nodes.append(build_pkg_node(norm, set(), depth=1))

        if cat_val == PackageCategory.LINKER.value:
            return linker_nodes
        elif cat_val == PackageCategory.EDITABLE.value:
            return editable_nodes
        elif cat_val == PackageCategory.PACKAGES.value:
            return requirements_nodes
        elif cat_val == PackageCategory.EXPLICIT.value:
            return explicit_nodes
        elif cat_val == PackageCategory.SYSTEM.value:
            return system_nodes
        elif cat_val == PackageCategory.ORPHANS.value:
            return orphan_nodes

        # ALL: Skupinové priečinky
        sections = []
        if linker_nodes:
            sections.append({
                "id": "group:linker",
                "name": f"Lokálne Linker moduly ({len(linker_nodes)})",
                "normalized_name": "group_linker",
                "node_type": "group",
                "summary": "Lokálne moduly pripojené cez Linker a ich vyžadované balíčky",
                "depth": 0,
                "dependencies": linker_nodes
            })

        if editable_nodes:
            sections.append({
                "id": "group:editable",
                "name": f"Editovateľné projekty - pip -e ({len(editable_nodes)})",
                "normalized_name": "group_editable",
                "node_type": "group",
                "summary": "Lokálne balíčky nainštalované v editovateľnom režime (-e)",
                "depth": 0,
                "dependencies": editable_nodes
            })

        if requirements_nodes:
            sections.append({
                "id": "group:requirements",
                "name": f"Projektové požiadavky - requirements.txt ({len(requirements_nodes)})",
                "normalized_name": "group_requirements",
                "node_type": "group",
                "summary": "Koreňové balíčky deklarované v requirements.txt",
                "depth": 0,
                "dependencies": requirements_nodes
            })

        if explicit_nodes:
            sections.append({
                "id": "group:explicit",
                "name": f"Manuálne nainštalované - Explicit ({len(explicit_nodes)})",
                "normalized_name": "group_explicit",
                "node_type": "group",
                "summary": "Balíčky nainštalované manuálne používateľom",
                "depth": 0,
                "dependencies": explicit_nodes
            })

        if system_nodes:
            sections.append({
                "id": "group:system",
                "name": f"Systémové balíčky venvu ({len(system_nodes)})",
                "normalized_name": "group_system",
                "node_type": "group",
                "summary": "Základné nástroje venvu chránené pred odinštalovaním",
                "depth": 0,
                "dependencies": system_nodes
            })

        if orphan_nodes:
            sections.append({
                "id": "group:orphans",
                "name": f"Siroty ({len(orphan_nodes)})",
                "normalized_name": "group_orphans",
                "node_type": "group",
                "summary": "Balíčky bez vlastníka pripravené na autoremove",
                "depth": 0,
                "dependencies": orphan_nodes
            })

        return sections

    @classmethod
    def get_combobox_items(
        cls, 
        master_data: dict, 
        category: int | PackageCategory = PackageCategory.ALL
    ) -> list[dict]:
        flat_index = master_data.get("flat_index", {})
        cat_val = int(category)
        items = []

        for norm, data in sorted(flat_index.items(), key=lambda x: x[1]["name"].lower()):
            if cat_val == PackageCategory.SYSTEM.value and not data.get("is_system"):
                continue
            elif cat_val == PackageCategory.PACKAGES.value and not data.get("is_requirement"):
                continue
            elif cat_val == PackageCategory.EDITABLE.value and not data.get("is_editable"):
                continue
            elif cat_val == PackageCategory.LINKER.value and not data.get("is_linker"):
                continue
            elif cat_val == PackageCategory.EXPLICIT.value and not data.get("is_explicit"):
                continue
            elif cat_val == PackageCategory.ORPHANS.value and not data.get("is_orphan"):
                continue

            items.append({
                "normalized_name": norm,
                "name": data["name"],
                "version": data["version"],
                "owners": data.get("owners", []),
                "display": f"{data['name']} (v{data['version']})"
            })

        return items


class PackageTreeWorker(QThread):
    tree_ready = pyqtSignal(dict)
    log_msg = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, venv_path: str, core=None):
        super().__init__()
        self.venv_path = venv_path
        self.core = core

    def run(self):
        try:
            self.log_msg.emit("⏳ [PackageTree] Zbieram informácie o balíčkoch a závislostiach...")
            master_data = PackageTreeService.build_tree_master(self.venv_path, self.core)

            if "error" in master_data:
                self.error_signal.emit(master_data["error"])
            else:
                self.log_msg.emit("✅ [PackageTree] Analýza úspešne dokončená.")
                self.tree_ready.emit(master_data)

        except Exception as e:
            self.error_signal.emit(f"Chyba pri generovaní stromu: {e}")
# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Súbor: windows/venv_tree_window.py
# Bezrámové grafické okno pre vizualizáciu a interaktívne filtrovanie
# stromu závislostí virtuálneho prostredia (Venv Tree).
# Plne lokalizované cez LanguageBridge (dynamický preklad UI, stromu aj detailu).
#-------------------------------------------------------------------------------

import os
from typing import Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem, 
    QSplitter, QTextEdit, QFrame, QButtonGroup, QHeaderView, QWidget, QSizePolicy,
    QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QFont

from core._path import Paths
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.venv.pack_tree import PackageCategory, PackageTreeService, PackageTreeWorker
from core.logic.sluzby.packages.req_toml import ReqTomlService, TomlExportStatus
from windows.custom_message_box import CustomMessageBox
from windows.custom_title_bar import CustomTitleBar


def _tr(key: str, default: str, **kwargs) -> str:
    text = LanguageBridge.translate(key, default)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            pass
    return text


def _get_group_info(node: dict) -> tuple[str, str]:
    """Vráti lokalizovaný názov a popis pre virtuálne koreňové skupiny."""
    gid = node.get("id", "")
    count = len(node.get("dependencies", []))
    
    if gid == "group:linker":
        return (
            _tr("tree_sec_linker", "Lokálne Linker moduly ({count})", count=count),
            _tr("tree_sec_linker_desc", "Lokálne moduly pripojené cez Linker a ich vyžadované balíčky")
        )
    elif gid == "group:editable":
        return (
            _tr("tree_sec_editable", "Editovateľné projekty - pip -e ({count})", count=count),
            _tr("tree_sec_editable_desc", "Lokálne balíčky nainštalované v editovateľnom režime (-e)")
        )
    elif gid == "group:requirements":
        return (
            _tr("tree_sec_requirements", "Projektové požiadavky - requirements.txt ({count})", count=count),
            _tr("tree_sec_requirements_desc", "Koreňové balíčky deklarované v requirements.txt")
        )
    elif gid == "group:explicit":
        return (
            _tr("tree_sec_explicit", "Manuálne nainštalované - Explicit ({count})", count=count),
            _tr("tree_sec_explicit_desc", "Balíčky nainštalované manuálne používateľom")
        )
    elif gid == "group:system":
        return (
            _tr("tree_sec_system", "Systémové balíčky venvu ({count})", count=count),
            _tr("tree_sec_system_desc", "Základné nástroje venvu chránené pred odinštalovaním")
        )
    elif gid == "group:orphans":
        return (
            _tr("tree_sec_orphans", "Siroty ({count})", count=count),
            _tr("tree_sec_orphans_desc", "Balíčky bez vlastníka pripravené na autoremove")
        )
    return (node.get("name", ""), node.get("summary", ""))


def _format_owner(owner: str) -> str:
    """Preloží text vlastníka do zvoleného jazyka."""
    if not owner or owner == "-":
        return "-"
    
    # Rozpoznanie typov vlastníkov
    if "Systémový balíček" in owner or "System package" in owner:
        return _tr("tree_owner_system", "Systémový balíček")
    if "Manuálne (explicit)" in owner or "Manual (explicit)" in owner:
        if "[extra]" in owner and "cez" in owner:
            parent = owner.split("cez")[-1].replace("[extra]", "").strip()
            return _tr("tree_owner_extra_explicit", "Manuálne (explicit) cez {parent} [extra]", parent=parent)
        return _tr("tree_owner_explicit", "Manuálne (explicit)")
    if "requirements.txt" in owner:
        if "[extra]" in owner and "cez" in owner:
            parent = owner.split("cez")[-1].replace("[extra]", "").strip()
            return _tr("tree_owner_extra_reqs", "requirements.txt cez {parent} [extra]", parent=parent)
        return "requirements.txt"
    if "pip -e" in owner:
        return owner
    if "Linker:" in owner:
        if "cez" in owner:
            return owner.replace("cez", "via") if LanguageBridge.get_current_language().startswith("en") else owner
        return owner
    if "Editable:" in owner:
        if "cez" in owner:
            return owner.replace("cez", "via") if LanguageBridge.get_current_language().startswith("en") else owner
        return owner
    return owner


class VenvTreeWindow(QDialog):

    CATEGORY_COLORS = {
        PackageCategory.ALL: "#d4d4d4",
        PackageCategory.SYSTEM: "#7f8c8d",       # Šedá
        PackageCategory.PACKAGES: "#2ecc71",     # Zelená (requirements.txt)
        PackageCategory.EDITABLE: "#e67e22",     # Oranžová (pip -e)
        PackageCategory.LINKER: "#3498db",       # Modrá (Linker)
        PackageCategory.ORPHANS: "#e74c3c",      # Červená (Siroty)
        PackageCategory.EXPLICIT: "#9b59b6",     # Fialová (Manuálne)
    }

    def __init__(self, parent, venv_path: str):
        super().__init__(parent)
        self.core = parent.core if hasattr(parent, 'core') else None
        self.venv_path = venv_path
        self.venv_name = os.path.basename(venv_path)

        if LanguageBridge._provider is None and self.core:
            lang_mgr = getattr(self.core, "language_manager", None) or getattr(self.core, "lang_manager", None)
            if lang_mgr:
                LanguageBridge.register_provider(lang_mgr)

        self.master_data = None
        self.current_category = PackageCategory.ALL
        self.worker = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("VenvTreeWindow")
        self.resize(1150, 720)
        self.setMinimumSize(900, 520)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)

        self.title_bar = CustomTitleBar(self)
        self.title_bar.setFixedHeight(35)
        self.title_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.title_bar.btn_minimize.hide()
        self.title_bar.btn_about.hide()
        self.main_layout.addWidget(self.title_bar, 0)

        self.content_widget = QWidget()
        self.content_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 12, 15, 15)
        self.content_layout.setSpacing(10)
        self.main_layout.addWidget(self.content_widget, 1)

        self._build_ui()
        self._connect_signals()
        self.retranslate_ui()

        LanguageBridge.connect_language_changed(self.retranslate_ui)
        self.load_tree_data()

    def closeEvent(self, event):
        LanguageBridge.disconnect_language_changed(self.retranslate_ui)
        super().closeEvent(event)

    def _build_ui(self):
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self.btn_group = QButtonGroup(self)
        self.btn_group.setExclusive(True)

        self.btn_cat_all = QPushButton()
        self.btn_cat_pkgs = QPushButton()
        self.btn_cat_explicit = QPushButton()
        self.btn_cat_pipe = QPushButton()
        self.btn_cat_linker = QPushButton()
        self.btn_cat_sys = QPushButton()
        self.btn_cat_orphans = QPushButton()

        buttons = [
            (self.btn_cat_all, PackageCategory.ALL),
            (self.btn_cat_pkgs, PackageCategory.PACKAGES),
            (self.btn_cat_explicit, PackageCategory.EXPLICIT),
            (self.btn_cat_pipe, PackageCategory.EDITABLE),
            (self.btn_cat_linker, PackageCategory.LINKER),
            (self.btn_cat_sys, PackageCategory.SYSTEM),
            (self.btn_cat_orphans, PackageCategory.ORPHANS),
        ]

        for btn, cat in buttons:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("category_code", int(cat))
            btn.setStyleSheet("""
                QPushButton {
                    padding: 5px 11px;
                    border: 1px solid #3c3c3c;
                    border-radius: 3px;
                    background-color: #252526;
                    color: #d4d4d4;
                    font-size: 12px;
                }
                QPushButton:checked {
                    background-color: #0e639c;
                    color: #ffffff;
                    border: 1px solid #1177bb;
                    font-weight: bold;
                }
                QPushButton:hover:!checked {
                    background-color: #333333;
                }
            """)
            self.btn_group.addButton(btn, int(cat))
            top_bar.addWidget(btn)

        self.btn_cat_all.setChecked(True)
        top_bar.addStretch()

        self.btn_refresh = QPushButton()
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        top_bar.addWidget(self.btn_refresh)

        # PRIDANÉ: Tlačidlo pre export do pyproject.toml
        self.btn_export_toml = QPushButton()
        self.btn_export_toml.setCursor(Qt.CursorShape.PointingHandCursor)
        top_bar.addWidget(self.btn_export_toml)

        self.content_layout.addLayout(top_bar)

        search_bar = QHBoxLayout()
        search_bar.setSpacing(8)

        self.lbl_quick = QLabel()
        self.lbl_quick.setStyleSheet("color: #888888; font-size: 12px;")
        search_bar.addWidget(self.lbl_quick)

        self.combo_packages = QComboBox()
        self.combo_packages.setMinimumWidth(280)
        self.combo_packages.setStyleSheet("padding: 4px; font-size: 12px;")
        search_bar.addWidget(self.combo_packages)

        self.lbl_filter = QLabel()
        self.lbl_filter.setStyleSheet("color: #888888; font-size: 12px; margin-left: 10px;")
        search_bar.addWidget(self.lbl_filter)

        self.edit_search = QLineEdit()
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet("padding: 4px; font-size: 12px;")
        search_bar.addWidget(self.edit_search)

        self.btn_expand_all = QPushButton()
        self.btn_collapse_all = QPushButton()
        for b in (self.btn_expand_all, self.btn_collapse_all):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            search_bar.addWidget(b)

        self.content_layout.addLayout(search_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setAlternatingRowColors(True)
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333333;
                font-size: 12px;
            }
            QTreeWidget::item {
                padding: 4px 0;
            }
            QTreeWidget::item:selected {
                background-color: #04395e;
                color: #ffffff;
            }
        """)
        splitter.addWidget(self.tree_widget)

        self.detail_panel = QWidget()
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(10, 0, 0, 0)
        detail_layout.setSpacing(6)

        self.lbl_detail_title = QLabel()
        self.lbl_detail_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #007acc;")
        detail_layout.addWidget(self.lbl_detail_title)

        self.txt_detail = QTextEdit()
        self.txt_detail.setReadOnly(True)
        self.txt_detail.setStyleSheet("""
            background-color: #1e1e1e;
            color: #cccccc;
            border: 1px solid #333333;
            font-size: 12px;
            line-height: 1.4;
            padding: 8px;
        """)
        detail_layout.addWidget(self.txt_detail)

        self.detail_panel.setMinimumWidth(300)
        self.detail_panel.setMaximumWidth(450)
        splitter.addWidget(self.detail_panel)

        splitter.setStretchFactor(0, 7)
        splitter.setStretchFactor(1, 3)
        self.content_layout.addWidget(splitter, 1)

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("color: #888888; font-size: 11px;")
        self.content_layout.addWidget(self.lbl_status, 0)

    def _connect_signals(self):
        self.btn_group.idClicked.connect(self.on_category_button_clicked)
        self.btn_refresh.clicked.connect(self.load_tree_data)
        self.btn_export_toml.clicked.connect(self.on_export_toml_clicked)
        self.combo_packages.currentIndexChanged.connect(self.on_combo_package_selected)
        self.edit_search.textChanged.connect(self.on_search_text_changed)
        self.btn_expand_all.clicked.connect(self.tree_widget.expandAll)
        self.btn_collapse_all.clicked.connect(self.tree_widget.collapseAll)
        self.tree_widget.itemSelectionChanged.connect(self.on_tree_item_selected)

    def retranslate_ui(self, *args, **kwargs):
        title = _tr("tree_window_title", "🌳 Strom závislostí: {name}", name=self.venv_name)
        self.setWindowTitle(title)
        if hasattr(self, 'title_bar'):
            self.title_bar.lbl_title.setText(title)

        self.btn_refresh.setText(_tr("tree_btn_refresh", "🔄 Obnoviť"))
        self.btn_export_toml.setText(_tr("tree_btn_export_toml", "📄 Export do TOML"))
        self.btn_expand_all.setText(_tr("tree_btn_expand", "➕ Rozbaliť"))
        self.btn_collapse_all.setText(_tr("tree_btn_collapse", "➖ Zbaliť"))
        self.lbl_quick.setText(_tr("tree_lbl_quick", "Výber balíčka:"))
        self.lbl_filter.setText(_tr("tree_lbl_filter", "Hľadať v strome:"))
        self.edit_search.setPlaceholderText(_tr("tree_search_placeholder", "Filtrovať názov..."))
        self.lbl_detail_title.setText(_tr("tree_detail_title", "Detail položky"))

        headers = [
            _tr("tree_col_package", "Položka / Balíček (Verzia)"),
            _tr("tree_col_type", "Typ / Kategória"),
            _tr("tree_col_deps", "Závislosti"),
            _tr("tree_col_required_by", "Vlastník / Kto vyžaduje")
        ]
        self.tree_widget.setHeaderLabels(headers)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        counts = self.master_data.get("counts", {}) if self.master_data else {}
        self.btn_cat_all.setText(f"{_tr('tree_cat_all', 'Všetko')} ({counts.get(PackageCategory.ALL.value, 0)})")
        self.btn_cat_pkgs.setText(f"requirements.txt ({counts.get(PackageCategory.PACKAGES.value, 0)})")
        self.btn_cat_explicit.setText(f"{_tr('tree_cat_explicit', 'Manuálne')} ({counts.get(PackageCategory.EXPLICIT.value, 0)})")
        self.btn_cat_pipe.setText(f"pip -e ({counts.get(PackageCategory.EDITABLE.value, 0)})")
        self.btn_cat_linker.setText(f"Linker ({counts.get(PackageCategory.LINKER.value, 0)})")
        self.btn_cat_sys.setText(f"{_tr('tree_cat_sys', 'Systém')} ({counts.get(PackageCategory.SYSTEM.value, 0)})")
        self.btn_cat_orphans.setText(f"{_tr('tree_cat_orphans', 'Siroty')} ({counts.get(PackageCategory.ORPHANS.value, 0)})")

        if not self.master_data:
            self.lbl_status.setText(_tr("tree_status_ready", "Pripravený."))
        else:
            total = self.master_data.get("total_packages", 0)
            orphans = counts.get(PackageCategory.ORPHANS.value, 0)
            self.lbl_status.setText(_tr("tree_status_done", "✅ Hotovo. Celkovo balíčkov: {total} | Nájdených sirôt: {orphans}", total=total, orphans=orphans))
            self.populate_combobox()
            self.render_tree()
            self.on_tree_item_selected()

    def load_tree_data(self):
        self.lbl_status.setText(_tr("tree_status_analyzing", "⏳ Analyzujem prostredie a zbieram strom závislostí..."))
        self.btn_refresh.setEnabled(False)
        self.tree_widget.clear()
        self.txt_detail.clear()

        self.worker = PackageTreeWorker(self.venv_path, self.core)
        self.worker.tree_ready.connect(self.on_data_ready)
        self.worker.error_signal.connect(self.on_data_error)
        self.worker.log_msg.connect(lambda msg: self.lbl_status.setText(msg))
        self.worker.finished.connect(lambda: self.btn_refresh.setEnabled(True))
        self.worker.start()

    @pyqtSlot(dict)
    def on_data_ready(self, master_data: dict):
        self.master_data = master_data
        self.retranslate_ui()

    @pyqtSlot(str)
    def on_data_error(self, err_msg: str):
        self.lbl_status.setText(_tr("tree_status_error", "❌ Chyba: {err}", err=err_msg))
        self.btn_refresh.setEnabled(True)

    def populate_combobox(self):
        if not self.master_data:
            return

        self.combo_packages.blockSignals(True)
        self.combo_packages.clear()
        self.combo_packages.addItem(_tr("tree_combo_all_category", "-- Zobraziť celý strom kategórie --"), "")

        items = PackageTreeService.get_combobox_items(self.master_data, category=self.current_category)
        for it in items:
            self.combo_packages.addItem(it["display"], it["normalized_name"])

        self.combo_packages.blockSignals(False)

    def on_category_button_clicked(self, cat_code: int):
        self.current_category = PackageCategory(cat_code)
        self.populate_combobox()
        self.render_tree()

    def on_combo_package_selected(self, index: int):
        if index <= 0:
            self.render_tree()
        else:
            selected_pkg = self.combo_packages.currentData()
            self.render_tree(single_package=selected_pkg)

    def on_search_text_changed(self, text: str):
        query = text.strip().lower()
        if not query:
            for i in range(self.tree_widget.topLevelItemCount()):
                self._set_item_visible_recursive(self.tree_widget.topLevelItem(i), True)
            return

        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            self._filter_tree_item(item, query)

    def _filter_tree_item(self, item: QTreeWidgetItem, query: str) -> bool:
        pkg_name = item.text(0).lower()
        matches = query in pkg_name

        child_matches = False
        for c in range(item.childCount()):
            if self._filter_tree_item(item.child(c), query):
                child_matches = True

        visible = matches or child_matches
        item.setHidden(not visible)
        if visible and child_matches:
            item.setExpanded(True)
        return visible

    def _set_item_visible_recursive(self, item: QTreeWidgetItem, visible: bool):
        item.setHidden(not visible)
        for c in range(item.childCount()):
            self._set_item_visible_recursive(item.child(c), visible)

    def render_tree(self, single_package=None):
        if not self.master_data:
            return

        self.tree_widget.clear()
        roots = PackageTreeService.filter_tree(
            self.master_data, 
            category=self.current_category, 
            single_package=single_package
        )

        for node_data in roots:
            tree_item = self._create_tree_item(node_data)
            self.tree_widget.addTopLevelItem(tree_item)

        for i in range(self.tree_widget.topLevelItemCount()):
            top_item = self.tree_widget.topLevelItem(i)
            top_item.setExpanded(True)
            for c in range(top_item.childCount()):
                top_item.child(c).setExpanded(True)

    def _create_tree_item(self, node: dict) -> QTreeWidgetItem:
        node_type = node.get("node_type", "package")
        name = node.get("name", "")
        version = node.get("version", "")
        circular = node.get("circular", False)
        is_extra = node.get("is_extra", False)
        extra_parent = node.get("extra_parent", "")
        deps_count = len(node.get("dependencies", []))

        # Dynamický preklad stĺpca vlastník
        raw_req = node.get("required_by_text", "-")
        req_by_text = ", ".join([_format_owner(p.strip()) for p in raw_req.split(",")]) if raw_req != "-" else "-"

        if node_type == "group":
            group_name, _ = _get_group_info(node)
            title_text = f"📁 {group_name}"
            type_label = _tr("tree_type_section", "Sekcia")
            color_hex = "#ffffff"
        elif node_type == "linker_module":
            title_text = f"🧩 {name}"
            type_label = _tr("tree_type_linker", "Linker Modul")
            color_hex = "#3498db"
        elif node_type == "editable_project":
            title_text = f"🛠️ {name} (v{version})" if version else f"🛠️ {name}"
            type_label = "pip -e"
            color_hex = "#e67e22"
        elif is_extra:
            title_text = f"➕ {name} (v{version}) [extra: {extra_parent}]"
            type_label = _tr("tree_type_extra", "Viazané Extra")
            color_hex = "#f39c12"
        else:
            title_text = f"📦 {name} (v{version})" if version else f"📦 {name}"
            type_label = _tr("tree_type_package", "Balíček")
            color_hex = "#2ecc71"

        if circular:
            title_text += f" 🔄 {_tr('tree_badge_cycle', '[cyklus]')}"

        item = QTreeWidgetItem([
            title_text,
            type_label,
            str(deps_count) if deps_count > 0 else "-",
            req_by_text
        ])

        # PRIDANÉ: Checkboxy pre jednotlivé balíčky (predvolene zaškrtnuté Explicit balíčky)
        if node_type == "package":
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            is_explicit = node.get("is_explicit", False)
            item.setCheckState(0, Qt.CheckState.Checked if is_explicit else Qt.CheckState.Unchecked)

        item.setData(0, Qt.ItemDataRole.UserRole, node)
        item.setForeground(1, QColor(color_hex))
        if circular:
            item.setForeground(0, QColor("#e67e22"))

        for child_data in node.get("dependencies", []):
            child_item = self._create_tree_item(child_data)
            item.addChild(child_item)

        return item

    def on_tree_item_selected(self):
        items = self.tree_widget.selectedItems()
        if not items or not self.master_data:
            self.txt_detail.clear()
            return

        node = items[0].data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(node, dict):
            self.txt_detail.clear()
            return

        node_type = node.get("node_type", "package")
        norm_name = node.get("normalized_name", "")
        flat_info = self.master_data.get("flat_index", {}).get(norm_name, {})

        # --- A. Kliknutie na skupinu (Dynamický preklad názvu aj popisu) ---
        if node_type == "group":
            group_name, group_summary = _get_group_info(node)
            html = f"""
            <h3 style="color: #ffffff; margin-bottom: 4px;">📁 {group_name}</h3>
            <p style="color: #aaaaaa;">{group_summary}</p>
            <hr style="border: 0; border-top: 1px solid #333333;">
            <p><b>{_tr('tree_detail_items_count', 'Počet položiek v tejto sekcii:')}</b> <span style="color: #3498db; font-weight: bold;">{len(node.get('dependencies', []))}</span></p>
            """
            self.txt_detail.setHtml(html)
            return

        # --- B. Linker modul ---
        if node_type == "linker_module":
            deps = [d.get("name", "") for d in node.get("dependencies", [])]
            deps_str = ", ".join(deps) if deps else _tr("tree_detail_none", "Žiadne")
            html = f"""
            <h3 style="color: #3498db; margin-bottom: 2px;">🧩 {node.get('name')}</h3>
            <p style="color: #888888; font-size: 11px; margin-top: 0;"><b>{_tr('tree_detail_linker_type', 'Lokálny vývojový modul (Linker)')}</b></p>
            <hr style="border: 0; border-top: 1px solid #333333;">
            <p><b>{_tr('tree_detail_linker_reqs', 'Vyžadované balíčky modulu:')}</b><br>
            <span style="color: #2ecc71;">{deps_str}</span></p>
            <p style="color: #aaaaaa; font-size: 11px;">{_tr('tree_detail_linker_desc', 'Tieto balíčky sú chránené pred odinštalovaním (autoremove), kým je modul v Linkeri pripojený.')}</p>
            """
            self.txt_detail.setHtml(html)
            return

        # --- C. Editovateľný projekt ---
        if node_type == "editable_project":
            deps = [d.get("name", "") for d in node.get("dependencies", [])]
            deps_str = ", ".join(deps) if deps else _tr("tree_detail_none", "Žiadne")
            html = f"""
            <h3 style="color: #e67e22; margin-bottom: 2px;">🛠️ {node.get('name')}</h3>
            <p style="color: #888888; font-size: 11px; margin-top: 0;">{_tr('tree_detail_installed_ver', 'Verzia:')} <b>{node.get('version', 'pip -e')}</b></p>
            <p><b>{_tr('tree_detail_path', 'Cesta na disku:')}</b><br>
            <span style="color: #dcdcdc; font-family: monospace; font-size: 11px;">{node.get('path', '-')}</span></p>
            <hr style="border: 0; border-top: 1px solid #333333;">
            <p><b>{_tr('tree_detail_direct_deps', 'Priame závislosti projektu:')}</b><br>
            <span style="color: #3498db;">{deps_str}</span></p>
            """
            self.txt_detail.setHtml(html)
            return

        # --- D. Balíček ---
        name = flat_info.get("name", node.get("name", norm_name))
        version = flat_info.get("version", node.get("version", _tr("tree_detail_unknown", "neznáma")))
        license_str = flat_info.get("license") or _tr("tree_detail_unknown", "Neznáma")
        summary = flat_info.get("summary") or _tr("tree_detail_no_desc", "Bez popisu.")
        homepage = flat_info.get("homepage", "")

        owners = flat_info.get("owners", node.get("owners", []))
        owners_html = ""
        if owners:
            owners_html = "<ul style='margin-top: 4px; padding-left: 20px;'>"
            for ow in owners:
                localized_owner = _format_owner(ow)
                color = "#2ecc71" if "requirements" in ow.lower() else "#3498db" if "linker" in ow.lower() else "#e67e22" if "editable" in ow.lower() else "#9b59b6"
                owners_html += f"<li><span style='color: {color}; font-weight: bold;'>{localized_owner}</span></li>"
            owners_html += "</ul>"
        else:
            owners_html = f"<span style='color: #e74c3c;'>{_tr('tree_detail_no_direct_owner', 'Žiadny priamy vlastník (tranzitívna podzávislosť)')}</span>"

        parents = flat_info.get("parents", node.get("parents", []))
        parents_str = ", ".join(parents) if parents else _tr("tree_detail_no_parents", "Žiadny balíček ho priamo nevyžaduje")

        requires = flat_info.get("requires", [])
        requires_str = ", ".join(requires) if requires else _tr("tree_detail_no_deps", "Žiadne (nemá podzávislosti)")

        extras = flat_info.get("extras_bound", [])
        extras_str = ", ".join(extras) if extras else _tr("tree_detail_none", "Žiadne")

        extra_badge = ""
        if node.get("is_extra"):
            extra_badge = f"<p style='color: #f39c12; font-weight: bold;'>{_tr('tree_detail_bound_extra_for', '➕ Viazané Extra pre balíček: {parent}', parent=node.get('extra_parent'))}</p>"

        html = f"""
        <h3 style="color: #ffffff; margin-bottom: 2px;">📦 {name}</h3>
        <p style="color: #888888; font-size: 11px; margin-top: 0;">{_tr('tree_detail_installed_ver', 'Nainštalovaná verzia:')} <b>v{version}</b></p>
        
        {extra_badge}

        <hr style="border: 0; border-top: 1px solid #333333;">
        
        <p><b>{_tr('tree_detail_who_keeps', '🛡️ Kto ho drží nažive (Vlastníci):')}</b>{owners_html}</p>
        
        <p><b>{_tr('tree_detail_who_requires', '📥 Kto ho vyžaduje v kóde (Rodičia):')}</b><br>
        <span style="color: #3498db;">{parents_str}</span></p>

        <hr style="border: 0; border-top: 1px solid #333333;">

        <p><b>{_tr('tree_detail_what_requires', '📤 Tento balíček vyžaduje ({count}):', count=len(requires))}</b><br>
        <span style="color: #2ecc71;">{requires_str}</span></p>

        <p><b>{_tr('tree_detail_bound_extras', '➕ Naviazané Extras ({count}):', count=len(extras))}</b><br>
        <span style="color: #f39c12;">{extras_str}</span></p>

        <hr style="border: 0; border-top: 1px solid #333333;">

        <p><b>{_tr('tree_detail_license', 'Licencia:')}</b> {license_str}</p>
        <p><b>{_tr('tree_detail_desc', 'Popis:')}</b><br>{summary}</p>
        """

        if homepage:
            html += f"""
            <hr style="border: 0; border-top: 1px solid #333333;">
            <p><b>{_tr('tree_detail_web', 'Web:')}</b> <a style="color: #007acc;" href="{homepage}">{homepage}</a></p>
            """

        self.txt_detail.setHtml(html)

    # =========================================================================
    # PRIDANÉ: OBSLUHA TLAČIDLA PRE EXPORT DO TOML
    # =========================================================================

    def on_export_toml_clicked(self):
        """
        Zozbiera označené balíčky z checkboxov v strome a vygeneruje pyproject.toml.
        Ak používateľ neoznačil žiadny balíček, vyexportujú sa všetky primárne závislosti.
        """
        if not self.master_data:
            return

        # 1. Zozbierame označené balíčky z checkboxov
        checked_pkgs = []
        it = QTreeWidgetItemIterator(self.tree_widget)
        while it.value():
            tree_item = it.value()
            if tree_item.checkState(0) == Qt.CheckState.Checked:
                nd = tree_item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(nd, dict) and nd.get("node_type") == "package":
                    p_norm = nd.get("normalized_name")
                    if p_norm and p_norm not in checked_pkgs:
                        checked_pkgs.append(p_norm)
            it += 1

        selected_to_export = checked_pkgs if checked_pkgs else None

        # 2. Určíme cestu k projektu pre pyproject.toml
        project_path = ""
        project_name = "my-project"
        if self.core and hasattr(self.core, 'projects_root') and getattr(self.core, 'active_project', ''):
            project_path = Paths.get_project_path(self.core.projects_root, self.core.active_project)
            project_name = self.core.active_project
        else:
            project_path = os.path.dirname(self.venv_path)

        target_toml = os.path.join(project_path, "pyproject.toml")

        # 3. Spustíme export cez ReqTomlService s UŽ EXISTUJÚCIM master_data
        status, result_path_or_err, count = ReqTomlService.export_to_toml(
            venv_path=self.venv_path,
            target_file_path=target_toml,
            master_data=self.master_data,
            project_name=project_name,
            selected_packages=selected_to_export,
            pin_exact=True,
            log_callback=lambda msg: self.lbl_status.setText(msg)
        )

        # 4. Hlásenie pre používateľa cez CustomMessageBox
        if status == TomlExportStatus.SUCCESS:
            t_title = _tr("toml_export_success_title", "TOML Export úspešný")
            t_msg = _tr(
                "toml_export_success_msg", 
                "Súbor 'pyproject.toml' bol úspešne vytvorený v projekte:\n{path}\n\nExportovaných balíčkov: {count}",
                path=result_path_or_err,
                count=count
            )
            CustomMessageBox.information(self, t_title, t_msg)
        elif status == TomlExportStatus.EMPTY:
            t_title = _tr("toml_export_empty_title", "Prázdny výber")
            t_msg = _tr("toml_export_empty_msg", "Nenašli sa žiadne balíčky na export.")
            CustomMessageBox.warning(self, t_title, t_msg)
        else:
            t_title = _tr("toml_export_err_title", "Chyba exportu")
            t_msg = _tr("toml_export_err_msg", "Nepodarilo sa vytvoriť pyproject.toml:\n{err}", err=result_path_or_err)
            CustomMessageBox.critical(self, t_title, t_msg)
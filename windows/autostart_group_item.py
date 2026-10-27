#----------------------------------------
# Súbor: windows/autostart_group_item.py
#----------------------------------------

from PyQt6.QtWidgets import (QGroupBox, QTableWidgetItem, QMessageBox, QHeaderView, 
                             QWidget, QHBoxLayout, QCheckBox, QLineEdit)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6 import uic
import os

from core._path import Paths
from core.logic.containers.box.json_projects import AutostartJsonManager
from core.logic.containers.button.autostart_actions import AutostartActionHandler
from core.logic.language_manager import LanguageManager
from core.logic.containers.logic.RAM_detect import RAMDetector
from core.logic.containers.logic.check_multi_venv import MultiVenvChecker

from core.logic.process_registry import process_registry
from core.logic.containers.logic.autostart_boot import AutostartBooter # PRIDANÉ PRE LOGY

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox

class AutostartGroupItem(QGroupBox):
    def __init__(self, parent_window, parent=None):
        super().__init__(parent)
        self.parent_window = parent_window
        self.group_name = None
        self._is_loading = True 
        
        self.row_states = {}

        try:
            uic.loadUi(Paths.get_ui_file_path("autostart_group_item.ui"), self)
        except FileNotFoundError:
            return

        # Zabezpečenie nemenných rozmerov okna
        self.setFixedHeight(320)

        self.btn_auto_delete_group.clicked.connect(self.handle_delete)
        self.btn_auto_start_group.clicked.connect(self.on_start_clicked)
        self.btn_auto_stop_group.clicked.connect(self.on_stop_clicked)

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle_led_blink)
        self.is_led_on = True
        self.current_led_color = "gray"

        self.ram_timer = QTimer(self)
        self.ram_timer.timeout.connect(self._update_ram_usage)
        self.ram_timer.start(2000)

        header = self.auto_table_projects.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.auto_table_projects.setColumnWidth(1, 60)
        
        for i in range(2, self.auto_table_projects.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.auto_chk_autostart.stateChanged.connect(self._save_in_time)
        self.auto_chk_master_respawn.stateChanged.connect(self._on_master_respawn_changed)
        self.auto_chk_terminal.stateChanged.connect(self._on_terminal_toggled)
        self.auto_chk_silent.stateChanged.connect(self._on_silent_toggled)

    def on_start_clicked(self):
        if not self.group_name: return
        
        conflicts = MultiVenvChecker.get_running_conflicts(self.parent_window.core, self.group_name)
        if conflicts:
            msg = LanguageManager.get("autostart_group_conflict_msg", "Nie je možné spustiť skupinu '{group}', pretože nasledujúce prostredia už bežia:\n\n{conflicts}\n\nNajprv ich zastavte.").format(
                group=self.group_name, 
                conflicts="\n".join(f"- {c}" for c in conflicts)
            )
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.warning(self, LanguageManager.get("autostart_group_conflict_title", "Konflikt prostredí"), msg)
            return
        
        # ZMENA: Smerujeme logy priamo do centrálnej pamäte!
        AutostartActionHandler.start_group(
            self.parent_window.core, 
            self.group_name, 
            lambda msg: AutostartBooter.log_to_group(self.group_name, msg)
        )

    def on_stop_clicked(self):
        if not self.group_name: return
        AutostartBooter.log_to_group(self.group_name, LanguageManager.get("autostart_group_log_stopping", "--- Zastavujem skupinu ---"))
        
        AutostartActionHandler.stop_group(self.parent_window.core, self.group_name)
        self._force_all_rows_stopped()
        
        venv_paths = []
        for row in range(self.auto_table_projects.rowCount()):
            proj_item = self.auto_table_projects.item(row, 0)
            if proj_item and proj_item.data(Qt.ItemDataRole.UserRole):
                venv_paths.append(proj_item.data(Qt.ItemDataRole.UserRole))
                
        try:
            from core.logic.containers.logic.respawn_multi import RespawnManager
            RespawnManager.reset_counts(venv_paths)
        except ImportError:
            pass

    def _on_terminal_toggled(self, state):
        if self._is_loading: return
        if state == Qt.CheckState.Checked.value:
            self.auto_chk_silent.setChecked(False)
        elif not self.auto_chk_silent.isChecked():
            self.auto_chk_terminal.setChecked(True)
        self._save_in_time()

    def _on_silent_toggled(self, state):
        if self._is_loading: return
        if state == Qt.CheckState.Checked.value:
            self.auto_chk_terminal.setChecked(False)
        elif not self.auto_chk_terminal.isChecked():
            self.auto_chk_terminal.setChecked(True)
        self._save_in_time()

    def populate_data(self, group_name, members):
        self._is_loading = True
        self.group_name = group_name
        self.setTitle(group_name)
        self.row_states.clear() 

        # --- ZMENA: Načítame HISTÓRIU logov, ktorá sa nazbierala kým bolo okno zavreté ---
        self.auto_log_output.clear()
        history = AutostartBooter.group_logs.get(group_name, [])
        for msg in history[-100:]: # posledných 100 správ
            self.auto_log_output.append(msg)

        saved_data = AutostartJsonManager.load_group(self.group_name)

        self.auto_chk_autostart.setChecked(saved_data.get("autostart", False))
        
        is_t = saved_data.get("terminal", True)
        is_s = saved_data.get("silent", False)
        if not is_t and not is_s: is_t = True 
        
        self.auto_chk_terminal.setChecked(is_t)
        self.auto_chk_silent.setChecked(is_s)

        self.auto_table_projects.setRowCount(0)
        proj_settings = saved_data.get("projects", {})

        for row_position, member in enumerate(members):
            project_name = member.get("project", "N/A")
            venv_path = member.get("venv_path", "")
            
            self.auto_table_projects.insertRow(row_position)
            
            self.row_states[row_position] = "STOPPED"
            p_data = proj_settings.get(project_name, {})

            project_item = QTableWidgetItem(project_name)
            project_item.setFlags(project_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            project_item.setData(Qt.ItemDataRole.UserRole, venv_path)
            self.auto_table_projects.setItem(row_position, 0, project_item)

            id_item = QTableWidgetItem("-")
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.auto_table_projects.setItem(row_position, 1, id_item)

            chk_kotva = self._add_centered_checkbox(row_position, 2, p_data.get("kotva", False))
            chk_kotva.stateChanged.connect(self._save_in_time)
            
            wait_edit = QLineEdit(p_data.get("wait", "0"))
            wait_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            wait_edit.setStyleSheet("background: transparent; border: 1px solid #444; padding: 2px;")
            wait_edit.setMaximumWidth(60)
            wait_edit.textChanged.connect(self._save_in_time)
            
            cell_widget = QWidget()
            layout = QHBoxLayout(cell_widget)
            layout.addWidget(wait_edit)
            layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            cell_widget.setLayout(layout)
            self.auto_table_projects.setCellWidget(row_position, 3, cell_widget)

            chk_respawn = self._add_centered_checkbox(row_position, 4, p_data.get("respawn", False))
            chk_respawn.stateChanged.connect(self._on_local_respawn_changed)

            monitoring_item = QTableWidgetItem(LanguageManager.get("state_stopped", "Zastavené"))
            monitoring_item.setForeground(QColor("gray"))
            monitoring_item.setFlags(monitoring_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.auto_table_projects.setItem(row_position, 5, monitoring_item)

            if venv_path and process_registry.is_running(venv_path):
                if MultiVenvChecker.is_owner(venv_path, self.group_name):
                    pids = process_registry.get_pids(venv_path)
                    
                    if pids:
                        first_pid = next(iter(pids)) 
                        id_item.setText(str(first_pid))
                        monitoring_item.setText(LanguageManager.get("state_running", "Beží"))
                        monitoring_item.setForeground(QColor("#2ecc71"))
                        self.row_states[row_position] = "RUNNING"

        self._sync_master_respawn_from_projects()
        self._is_loading = False
        self._update_global_led()
        self._update_ram_usage() 
        self._save_in_time()

    def retranslate_ui(self):
        self.auto_table_projects.horizontalHeaderItem(0).setText(LanguageManager.get("col_auto_project", "Projekt"))
        self.auto_table_projects.horizontalHeaderItem(1).setText(LanguageManager.get("col_auto_id", "ID"))
        self.auto_table_projects.horizontalHeaderItem(2).setText(LanguageManager.get("col_auto_kotva", "Kotva"))
        self.auto_table_projects.horizontalHeaderItem(3).setText(LanguageManager.get("col_auto_wait", "Čakať (s)"))
        self.auto_table_projects.horizontalHeaderItem(4).setText(LanguageManager.get("col_auto_respawn", "Respawn"))
        self.auto_table_projects.horizontalHeaderItem(5).setText(LanguageManager.get("col_auto_monitoring", "Monitoring"))


    def handle_registry_update(self, key_name, pid, status, message):
        """Prijíma signály výhradne pre aktualizáciu grafiky."""
        for row in range(self.auto_table_projects.rowCount()):
            proj_item = self.auto_table_projects.item(row, 0)
            venv_path = proj_item.data(Qt.ItemDataRole.UserRole)
            
            if not venv_path: continue
            
            if os.path.normpath(venv_path).lower() == key_name:
                
                if status != 'STOPPED' and not MultiVenvChecker.is_owner(venv_path, self.group_name):
                    continue
                
                id_item = self.auto_table_projects.item(row, 1)
                mon_item = self.auto_table_projects.item(row, 5)
                
                if status == 'RUNNING':
                    id_item.setText(str(pid))
                elif status in ('STOPPED', 'ERROR_CRASHED', 'ERROR_NOT_STARTED', 'ERROR_CRASHED_START'):
                    id_item.setText("-")

                if status == 'RUNNING':
                    mon_item.setText(LanguageManager.get("state_running", "Beží"))
                    mon_item.setForeground(QColor("#2ecc71"))
                    self.row_states[row] = "RUNNING"
                elif status == 'STOPPED':
                    mon_item.setText(LanguageManager.get("state_stopped", "Zastavené"))
                    mon_item.setForeground(QColor("gray"))
                    self.row_states[row] = "STOPPED"
                elif status.startswith('ERROR'):
                    mon_item.setText(LanguageManager.get("state_error", "Chyba!"))
                    mon_item.setForeground(QColor("#e74c3c"))
                    self.row_states[row] = "ERROR"
                    # ZMENA: Samotný Respawn sa už na tomto mieste nerieši, všetko zastrešuje jadro

                self._update_global_led()
                self._update_ram_usage() 
                break

    def _update_ram_usage(self):
        if self._is_loading: return
        total_ram_mb = 0.0
        for row in range(self.auto_table_projects.rowCount()):
            state = self.row_states.get(row, "STOPPED")
            if state == "RUNNING":
                pid_text = self.auto_table_projects.item(row, 1).text()
                if pid_text.isdigit():
                    ram_mb = RAMDetector.get_memory_mb(int(pid_text))
                    total_ram_mb += ram_mb
                    mon_item = self.auto_table_projects.item(row, 5)
                    if mon_item: mon_item.setText(LanguageManager.get("state_running_ram", "Beží / {ram:.1f} MB").format(ram=ram_mb))
        if hasattr(self, 'auto_lbl_resources'):
            self.auto_lbl_resources.setText(LanguageManager.get("state_total_ram", "[ RAM: {total:.1f} MB ]").format(total=total_ram_mb))

    def _update_global_led(self):
        total = len(self.row_states)
        if total == 0:
            self._set_led_color("gray")
            return

        counts = {"RUNNING": 0, "STOPPED": 0, "ERROR": 0}
        for state in self.row_states.values():
            counts[state] = counts.get(state, 0) + 1

        if counts["ERROR"] > 0:
            self.current_led_color = "#f39c12" 
            if not self.blink_timer.isActive():
                self.blink_timer.start(500) 
        else:
            if self.blink_timer.isActive():
                self.blink_timer.stop()
            
            if counts["RUNNING"] > 0:
                self._set_led_color("#2ecc71") 
            else:
                self._set_led_color("#e74c3c") 

    def _set_led_color(self, color_hex):
        self.auto_led_status.setStyleSheet(f"color: {color_hex}; font-size: 16pt;")

    def _toggle_led_blink(self):
        if self.is_led_on: self._set_led_color("transparent")
        else: self._set_led_color(self.current_led_color)
        self.is_led_on = not self.is_led_on

    def _add_centered_checkbox(self, row, column, is_checked=False):
        checkbox = QCheckBox()
        checkbox.setChecked(is_checked)

        cell_widget = QWidget()
        layout = QHBoxLayout(cell_widget)
        layout.addWidget(checkbox)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        cell_widget.setLayout(layout)

        self.auto_table_projects.setCellWidget(row, column, cell_widget)
        return checkbox

    def _force_all_rows_stopped(self):
        for row in range(self.auto_table_projects.rowCount()):
            mon_item = self.auto_table_projects.item(row, 5)
            id_item = self.auto_table_projects.item(row, 1)
            if mon_item:
                mon_item.setText(LanguageManager.get("state_stopped", "Zastavené"))
                mon_item.setForeground(QColor("gray"))
            if id_item:
                id_item.setText("-")
            self.row_states[row] = "STOPPED"

            proj_item = self.auto_table_projects.item(row, 0)
            if proj_item:
                venv_path = proj_item.data(Qt.ItemDataRole.UserRole)
                if venv_path:
                    MultiVenvChecker.remove_owner(venv_path)
        self._update_global_led()

    def _get_respawn_checkbox(self, row):
        widget = self.auto_table_projects.cellWidget(row, 4)
        return widget.findChild(QCheckBox) if widget else None

    def _all_projects_respawn_checked(self):
        row_count = self.auto_table_projects.rowCount()
        if row_count == 0: return False
        for row in range(row_count):
            chk = self._get_respawn_checkbox(row)
            if not chk or not chk.isChecked(): return False
        return True

    def _set_all_projects_respawn(self, checked):
        self._is_loading = True
        for row in range(self.auto_table_projects.rowCount()):
            chk = self._get_respawn_checkbox(row)
            if chk: chk.setChecked(checked)
        self._is_loading = False

    def _sync_master_respawn_from_projects(self):
        self._is_loading = True
        self.auto_chk_master_respawn.setChecked(self._all_projects_respawn_checked())
        self._is_loading = False

    def _on_master_respawn_changed(self, state):
        if self._is_loading: return
        self._set_all_projects_respawn(state == Qt.CheckState.Checked.value)
        self._save_in_time()

    def _on_local_respawn_changed(self, state):
        if self._is_loading: return
        self._sync_master_respawn_from_projects()
        self._save_in_time()

    def _save_in_time(self):
        if self._is_loading or not self.group_name: return

        data = {
            "autostart": self.auto_chk_autostart.isChecked(),
            "respawn_global": self._all_projects_respawn_checked(),
            "terminal": self.auto_chk_terminal.isChecked(),
            "silent": self.auto_chk_silent.isChecked(),
            "projects": {}
        }

        for row in range(self.auto_table_projects.rowCount()):
            proj_item = self.auto_table_projects.item(row, 0)
            if not proj_item: continue
            proj_name = proj_item.text()

            kotva_widget = self.auto_table_projects.cellWidget(row, 2)
            kotva_val = kotva_widget.findChild(QCheckBox).isChecked() if kotva_widget else False

            wait_widget = self.auto_table_projects.cellWidget(row, 3)
            wait_val = wait_widget.findChild(QLineEdit).text().strip() if wait_widget else "0"
            if not wait_val.isdigit(): wait_val = "0"

            respawn_widget = self.auto_table_projects.cellWidget(row, 4)
            respawn_val = respawn_widget.findChild(QCheckBox).isChecked() if respawn_widget else False

            data["projects"][proj_name] = {
                "kotva": kotva_val,
                "wait": wait_val,
                "respawn": respawn_val
            }

        AutostartJsonManager.save_group(self.group_name, data)

    def handle_delete(self):
        if not self.group_name: return
        
        # --- ZMENA NA NAŠU LIŠTU ---
        reply = CustomMessageBox.question(
            self,
            LanguageManager.get("autostart_group_del_title", "Odstrániť skupinu?"),
            LanguageManager.get("autostart_group_del_msg", "Naozaj chcete odstrániť skupinu '{group}' z tohto zoznamu?\n\n(Skupina nebude zmazaná z 'Hromadného spúšťania', len odtiaľto odobratá. Uložené JSON nastavenia pre túto skupinu budú zmazané.)").format(group=self.group_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            AutostartJsonManager.delete_group(self.group_name)
            MultiVenvChecker.clear_owners_for_group(self.parent_window.core, self.group_name)
            self.parent_window.remove_group(self.group_name, self)
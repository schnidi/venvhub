#----------------------------------------
# Súbor: core/logic/button/widget/widget_dispatcher.py
# Logika pre spracovanie hlavných tlačidiel na mini-bare.
# Plne prepojené na DialogBridge a LanguageBridge (0 priamych väzieb na windows/).
#----------------------------------------

import os
from core._path import Paths
from core.logic.button.manager.actions import ActionHandler
from core.logic.containers.logic.check_multi_venv import MultiVenvChecker

# --- ČISTÉ MOSTY (0 VÄZIEB NA WINDOWS) ---
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.dialog_bridge import DialogBridge

# --- IMPORT PRE VS CODE ---
from core.logic.vscode_user.start_vs_code_user import VSCodeLauncher

class WidgetDispatcher:
    """
    Spravuje logiku hlavných tlačidiel na mini-bare a volá
    správne, oddelené metódy.
    """
    
    @staticmethod
    def handle_vscode(parent_widget):
        """
        Spracuje kliknutie na tlačidlo VS Code v MiniBare.
        """
        core = parent_widget.core
        
        if core.app_mode == 'multi':
            # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
            DialogBridge.information(
                parent_widget, 
                LanguageBridge.translate("title_info", "Info"), 
                LanguageBridge.translate("msg_vscode_single_only", "Otváranie VS Code je dostupné len v režime Single.")
            )
            return
            
        # Zozbierame chyby (rovnako ako pri Play)
        error_messages = []
        
        if not core.active_project:
            msg = LanguageBridge.translate("err_no_project_selected_widget", "• Nebol vybraný žiadny projekt.")
            error_messages.append(msg)
            
        if not core.active_venv_path:
            msg = LanguageBridge.translate("err_no_default_venv_set", "• Pre projekt nie je nastavené predvolené prostredie (venv).")
            error_messages.append(msg)
        elif not os.path.exists(core.active_venv_path):
            msg = LanguageBridge.translate(
                "err_venv_not_found_widget",
                "• Prostredie (venv) sa na disku nenašlo: {0}"
            ).format(core.active_venv_path)
            error_messages.append(msg)

        if error_messages:
            title = LanguageBridge.translate("err_cannot_start_title", "Nie je možné spustiť")
            intro = LanguageBridge.translate("err_intro_problems_found", "Vyskytli sa nasledujúce problémy:")
            full_message = f"{intro}\n\n" + "\n".join(error_messages)
            
            # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
            DialogBridge.warning(parent_widget, title, full_message)
            return

        # Všetko je OK, spúšťame existujúcu logiku VS Code
        project_path = Paths.get_project_path(core.projects_root, core.active_project)
        success, err_msg = VSCodeLauncher.launch(core, project_path, core.active_venv_path)
        
        if not success:
            # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
            DialogBridge.warning(
                parent_widget, 
                LanguageBridge.translate("title_vscode_launch_error", "Chyba pri spúšťaní VS Code"), 
                err_msg
            )

    @staticmethod
    def handle_play(parent_widget):
        """
        Rozhodne, ktorú PRESNÚ metódu na spustenie má zavolať.
        """
        core = parent_widget.core
        
        if core.app_mode == 'multi':
            active_group = core.active_multi_group
            if not active_group:
                print("MULTI-RUN CHYBA: Nie je vybraná žiadna skupina.")
                return

            conflicts = MultiVenvChecker.get_running_conflicts(core, active_group)
            if conflicts:
                msg_template = LanguageBridge.translate(
                    "msg_cannot_start_group_conflicts",
                    "Nie je možné spustiť skupinu '{0}', pretože nasledujúce prostredia už bežia:\n\n{1}\n\nNajprv ich zastavte."
                )
                msg = msg_template.format(active_group, "\n".join(f"- {c}" for c in conflicts))
                
                # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
                DialogBridge.warning(
                    parent_widget, 
                    LanguageBridge.translate("title_venv_conflict", "Konflikt prostredí"), 
                    msg
                )
                return
            
            from core.logic.containers.button.autostart_actions import AutostartActionHandler
            AutostartActionHandler.start_group(core, active_group)
            
        else:
            # --- SINGLE REŽIM ---
            error_messages = []
            
            if not core.active_project:
                msg = LanguageBridge.translate("err_no_project_selected_widget", "• Nebol vybraný žiadny projekt.")
                error_messages.append(msg)
            
            if not core.active_venv_path:
                msg = LanguageBridge.translate("err_no_default_venv_set", "• Pre projekt nie je nastavené predvolené prostredie (venv).")
                error_messages.append(msg)
            elif not os.path.exists(core.active_venv_path):
                msg = LanguageBridge.translate(
                    "err_venv_not_found_widget",
                    "• Prostredie (venv) sa na disku nenašlo: {0}"
                ).format(core.active_venv_path)
                error_messages.append(msg)

            if not core.last_script:
                msg = LanguageBridge.translate("err_no_script_defined_widget", "• Nie je definovaný spúšťací skript.")
                error_messages.append(msg)
            elif core.active_project and core.last_script:
                project_path = Paths.get_project_path(core.projects_root, core.active_project)
                script_full_path = os.path.join(project_path, core.last_script)
                
                if not os.path.exists(script_full_path):
                    msg_format = LanguageBridge.translate("err_script_not_found_widget", "• Spúšťací skript '{0}' sa v projekte nenašiel.")
                    error_messages.append(msg_format.format(core.last_script))

            if error_messages:
                title = LanguageBridge.translate("err_cannot_start_title", "Nie je možné spustiť")
                intro = LanguageBridge.translate("err_intro_problems_found", "Vyskytli sa nasledujúce problémy:")
                full_message = f"{intro}\n\n" + "\n".join(error_messages)
                
                # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
                DialogBridge.warning(parent_widget, title, full_message)
                return

            if core.run_mode == "run_in_terminal":
                ActionHandler.run_single_terminal(core)
            elif core.run_mode == "run_silent":
                ActionHandler.run_single_silent(core)
            elif core.run_mode == "open_terminal":
                ActionHandler.open_terminal_only(
                    project_path=Paths.get_project_path(core.projects_root, core.active_project),
                    venv_path=core.active_venv_path
                )

    @staticmethod
    def handle_stop(parent_widget):
        core = parent_widget.core
        if core.app_mode == 'multi':
            active_group = core.active_multi_group
            if not active_group:
                return
            ActionHandler.stop_multiple(core, active_group)
        else:
            ActionHandler.stop_single(core.active_venv_path)
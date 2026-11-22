#----------------------------------------
# Súbor: core/logic/containers/button/add_new_group.py
# Logika pre tlačidlo 'Pridať novú skupinu' v záložke Container.
# Plne prepojené na DialogBridge a LanguageBridge (0 priamych väzieb na windows/).
#----------------------------------------

from PyQt6.QtWidgets import QInputDialog

# --- ČISTÉ MOSTY (0 VÄZIEB NA WINDOWS) ---
from core.logic.sluzby.language_bridge import LanguageBridge
from core.logic.sluzby.dialog_bridge import DialogBridge

class AddNewGroupHandler:
    """
    Logika pre tlačidlo 'Pridať novú skupinu' v záložke Container.
    """

    @staticmethod
    def run(autostart_window):
        """
        Spustí proces výberu a pridania skupiny do zoznamu.

        Args:
            autostart_window (AutostartWindow): Inštancia hlavného okna záložky.
        """
        # Získame prístup k hlavnému 'core' objektu
        core = autostart_window.core

        # 1. Získame zoznam všetkých existujúcich skupín z "Hromadného spúšťania"
        all_groups = list(core.multi_groups.keys())

        # 2. Získame zoznam skupín, ktoré sú už pridané v Containeri
        already_added = autostart_window.added_groups

        # 3. Vytvoríme zoznam len tých skupín, ktoré ešte neboli pridané
        selectable_groups = [g for g in all_groups if g not in already_added]

        # 4. Ak už nie je čo pridať, zobrazíme správu
        if not selectable_groups:
            # --- ZOBRAZENIE CEZ DIALOG BRIDGE ---
            DialogBridge.information(
                autostart_window,
                LanguageBridge.translate("add_group_msg_title", "Všetko pridané"),
                LanguageBridge.translate("add_group_msg_text", "Všetky dostupné skupiny z 'Hromadného spúšťania' sú už v zozname.")
            )
            return

        # 5. Zobrazíme dialóg s výberom dostupných skupín
        group_name, ok = QInputDialog.getItem(
            autostart_window,
            LanguageBridge.translate("add_group_dialog_title", "Vybrať skupinu"),
            LanguageBridge.translate("add_group_dialog_text", "Vyberte skupinu, ktorú chcete pridať do monitoringu:"),
            selectable_groups,
            0,
            False
        )

        # 6. Ak užívateľ potvrdil výber, spracujeme ho
        if ok and group_name:
            # Získame dáta (členov) vybranej skupiny
            members = core.multi_groups.get(group_name, [])
            
            # Zavoláme metódu na hlavnom okne, aby pridala nový widget
            autostart_window.add_group(group_name, members)
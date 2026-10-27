#----------------------------------------
# Súbor: core/logic/containers/button/add_new_group.py
#----------------------------------------

from PyQt6.QtWidgets import QInputDialog
from core.logic.language_manager import LanguageManager

# --- PRIDANÝ IMPORT NAŠHO BEZRÁMOVÉHO OKNA ---
from windows.custom_message_box import CustomMessageBox

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
            # --- ZMENA NA NAŠU LIŠTU ---
            CustomMessageBox.information(
                autostart_window,
                LanguageManager.get("add_group_msg_title", "Všetko pridané"),
                LanguageManager.get("add_group_msg_text", "Všetky dostupné skupiny z 'Hromadného spúšťania' sú už v zozname.")
            )
            return

        # 5. Zobrazíme dialóg s výberom dostupných skupín
        group_name, ok = QInputDialog.getItem(
            autostart_window,
            LanguageManager.get("add_group_dialog_title", "Vybrať skupinu"),
            LanguageManager.get("add_group_dialog_text", "Vyberte skupinu, ktorú chcete pridať do monitoringu:"),
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
# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.02  
*Táto verzia prináša autonómnu správu IDE rozšírení pre VS Code a Cursor AI s ochranou manuálnych inštalácií, natívne .pth linkovanie pre 100% Pylance IntelliSense a vnorené importy, selektívne čistenie projektových nastavení cez tracker, kritické opravy APT jadra pri správe závislostí a okamžité prepínanie jazyka rozhrania cez CoreBridge.*

---

## 🚀 Nové funkcie a vylepšenia

### 🧩 Autonómna správa IDE rozšírení (VS Code & Cursor AI)
- **Automatická inštalácia z metadát:** Ak pripájaný lokálny balíček vyžaduje konkrétne IDE rozšírenia (napr. linter, formátovač či ikony), VenvHub ich automaticky a bezpečne doinštaluje do aktívneho editora.
- **Dôsledná izolácia profilov a Portable podpora:** Rozšírenia sa inštalujú výhradne do dátového priečinka aktívneho profilu (`.../data/extensions`). Globálny systémový editor zostáva čistý. Plne podporované sú aj prenosné (Portable) verzie editorov.
- **Cross-Profile poistka pri štarte:** Ak v MiniBare prepneš na iný profil alebo vytvoríš nový a spustíš projekt, systém pred otvorením okna skontroluje prítomnosť potrebných rozšírení a na pozadí ich chýbajúce doplní.
- **Inteligentný Autoremove s ochranou ručných inštalácií:** Systém eviduje vlastníctvo pluginov. Rozšírenia, ktoré si v editore nainštaluješ sám ručne cez `Ctrl + Shift + X`, VenvHub nikdy nezmaže. Pri odlinkovaní balíčka sa bezpečne odinštalujú iba tie rozšírenia, ktoré už žiadny iný balíček nepotrebuje.

### ⚡ Natívny `.pth` Linker a 100% Pylance našepkávanie
- **Koniec chybám „Import could not be resolved“:** Pôvodné dynamické zachytávanie importov bolo nahradené oficiálnym Python štandardom pomocou `.pth` súborov v `site-packages`.
- **Plná podpora vnorených štruktúr (`src.logic.*`):** V linkovaných balíčkoch môžeš používať reálnu adresárovú štruktúru. Statické analyzátory (Pylance, Pyright) okamžite indexujú kód a poskytujú plnohodnotné našepkávanie (IntelliSense).
- **Prenos kódu bez prepisovania importov:** Hotový modul stačí skopírovať priamo do projektu a v Linkeri ho odškrtnúť – v kóde nie je potrebné upravovať jediný import.

### ⚙️ Selektívny zápis a čistenie nastavení projektu (`settings.json`)
- **Projektové nastavenia balíčkov:** Lokálne balíčky môžu cez `local_meta.json` definovať špecifické nastavenia editora (pravidlá formátovania, konfigurácie pre Cursor AI).
- **Účtenkový mechanizmus (Tracker):** VenvHub si presne eviduje, ktoré kľúče do `.vscode/settings.json` a `.cursor/settings.json` vložil. Pri odlinkovaní balíčka vymaže **výhradne tieto kľúče** – tvoje vlastné témy, klávesové skratky či fonty zostanú 100 % nedotknuté.

### 🌐 Prepracovaný jazykový subsystém cez CoreBridge
- **Okamžitá reaktivita okien:** Správa jazyka bola prevedená na servisnú architektúru `CoreBridge`. Zmena jazyka v Rýchlych nastaveniach sa bez reštartu okamžite prejaví vo všetkých otvorených oknách (vrátane dynamického HTML popisu v dialógu *O programe*).
- **Nová lokalizácia:** Do metadát a prekladov bola doplnená plná podpora ruskej lokalizácie (`ru_RU`).

---

## 🛠️ Opravy chýb a stabilita

### 📦 Opravy v správe balíčkov (APT jadro)
- **Ochrana požiadaviek projektu pred manuálnymi zásahmi:** Opravená kritická chyba, kedy manuálna inštalácia balíčka prítomného v extras (napr. `pip install pysocks` popri `requests[socks]`) vymazala záznam o väzbe z `venvhub_apt_state.json`.
- **Zamedzenie duplicitnému explicitnému stavu:** Balíčky patriace projektu cez `requirements.txt` sa už pri manuálnej inštalácii nezaradia chybne medzi používateľské (`explicit`).
- **Preskočenie zbytočných inštalácií:** Systém správne rozpozná balíčky existujúce cez extras a nespúšťa zbytočné preinštalovávanie.
- **Oprava preklepu v autoremove:** Odstránená syntaktická chyba v kóde, ktorá mohla spôsobiť pád aplikácie pri čistení závislostí.

### 🖥️ Integrácia editorov a rozhranie
- **Tiché spúšťanie CLI bez blikania okien:** Inštalácia a kontrola IDE rozšírení na Windows beží na pozadí s príznakom `CREATE_NO_WINDOW` bez preblikávania čiernych konzolových okien a zamŕzania grafického rozhrania.
- **Ignorovanie dočasných zložiek editorov:** Skener rozšírení automaticky ignoruje interné dočasné zložky začínajúce bodkou (`.uuid`).
- **Ochrana štartu pred inicializáciou prekladov:** Pridané bezpečnostné kontroly zamedzujúce pádu na `AttributeError`, ak si modul vyžiada text ešte pred dokončením štartu jadra.
- **Vyhodnocovanie DEV verzií pri aktualizáciách:** Opravené rozpoznávanie verzií tak, aby pri prechode z vývojovej verzie na stabilnú korektne vyskočila notifikácia o aktualizácii.

---

## 📁 Dotknuté súbory

- `assets/about.json`
- `core/core_bridge.py`
- `core/core_states.py`
- `core/logic/button/manager/local_packages_linker.py`
- `core/logic/language_manager.py`
- `core/logic/sluzby/about_logic.py`
- `core/logic/sluzby/apt_ide_logic.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/github_update.py`
- `core/logic/sluzby/language/language_manager.py`
- `core/logic/vs_code_json.py`
- `core/logic/vscode_user/start_vs_code_user.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
- `windows/about_dialog.py`
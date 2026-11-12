# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.04  
*Táto verzia prináša výrazné zrýchlenie a stabilitu vďaka presunu náročných úloh na pozadie, inteligentnú ochranu systémových venvov pri prenášaní na USB kľúčoch, plynulé prepájanie lokálnych balíčkov s podrobným živým záznamom a novú úroveň bezpečnosti pri správe vývojových balíčkov bez rizika poškodenia projektu.*

---

## 🚀 Nové funkcie a vylepšenia

### 1. Spoľahlivá ochrana prenosných prostredí na USB (Portability Guard)
- **Zrozumiteľné upozornenie namiesto pádov:** Ak sa pokúsiš otvoriť terminál, spustiť IDE (VS Code, Cursor), klonovať prostredie alebo otvoriť správu balíčkov na inom počítači, kde pôvodný systémový Python neexistuje, VenvHub akciu bezpečne zastaví a prehľadne ti vysvetlí dôvod.
- **Prevencia poškodenia ciest na USB:** Systémové venvy sú na prenosných diskoch chránené pred nechceným prepísaním interných konfiguračných ciest, vďaka čomu po návrate k pôvodnému počítaču fungujú bezchybne.

### 2. Plynulý Správca lokálnych balíčkov (Linker bez zamŕzania)
- **Spracovanie na pozadí:** Prepájanie modulov, ukladanie a doinštalovanie závislostí už neblokuje grafické rozhranie. Celý proces prebieha asynchrónne a okno zostáva plne responzívne.
- **Detailný živý záznam (In-time logovanie):** Počas prepájania balíčkov vidíš priamo v okne presný priebeh operácie krok za krokom:
  - Vyhľadávanie lokálnych a externých závislostí,
  - Živý výstup inštalátora balíčkov (`pip` / `uv`),
  - Zápis prepojovacích `.pth` súborov a konfigurácie pre editory,
  - Automatické vyčistenie knižníc, ktoré už po zmene prepojení nie sú potrebné.
- **Bezpečné uzamknutie ovládacích prvkov:** Počas zápisu zmien sa tlačidlá a voľby v okne dočasne uzamknú, aby sa predišlo nechceným kolíziám.

### 3. Nová úroveň správy vývojových balíčkov (`pip install -e`)
- **Inteligentná kontrola priečinka pred inštaláciou:** Pri pridávaní editovateľného balíčka z disku VenvHub okamžite overí prítomnosť konfiguračných súborov (`pyproject.toml` alebo `setup.py`). Ak priečinok neobsahuje platný Python projekt, včas ťa upozorní a nespustí zbytočnú inštaláciu.
- **Krížová ochrana voči požiadavkám projektu (`requirements.txt`):** Systém rozpozná, či je inštalovaný balíček súčasťou základných požiadaviek projektu, alebo ide o samostatný vývojový modul, a podľa toho nastaví jeho evidenciu.
- **Nepriestrelná ochrana pri odinštalovaní (APT Guard):** VenvHub nedovolí náhodne odinštalovať balíček, na ktorom je závislý tvoj projekt alebo lokálny Linker.
- **Automatické upratovanie sirotincov:** Po odinštalovaní nepotrebného vývojového balíčka systém automaticky deteguje a bezpečne odstráni knižnice, ktoré balíček do prostredia priviedol a ktoré už žiadny iný balíček nepotrebuje.
- **Moderné grafické dialógy:** Pôvodné systémové dialógy boli nahradené moderným dizajnom `CustomMessageBox` s okamžitou podporou jazykových prekladov.

### 4. Robustná inštalácia a aktualizácia balíčkov
- **Inteligentné preskočenie existujúceho (STAV 1:1):** Ak požadovaný balíček v danej verzii už v prostredí existuje, inštalátor ho neinštaluje znova, čo výrazne šetrí čas aj dáta.
- **Zachovanie väzieb pri aktualizáciách:** Ak manuálne aktualizuješ balíček, ktorý je naviazaný na lokálny vývojový modul alebo editovateľný projekt, systém ho udrží prepojený a neoznačí ho ako samostatný cudzí balíček.
- **Jednotné správanie naprieč celou aplikáciou:** Inštalácia cez pravý panel Pip Manažéra, spodný panel Správy Venvs aj Rýchle nastavenia využíva rovnaké bezpečné jadro chránené stavovým systémom.

---

## 🛠️ Opravy chýb a stabilita

- **Eliminácia zamŕzania a zrýchlenie reakcií:** Odstránené blokujúce operácie v hlavnom vlákne pri manipulácii s lokálnymi balíčkami a editovateľnými projektmi.
- **Oprava zlyhania inštalácie z hlavného okna:** Odstránená chyba, ktorá v určitých prípadoch bránila spusteniu inštalácie balíčka priamo zo záložky *Správa Venvs* alebo z okna *Rýchle nastavenia*.
- **Odstránenie interných cyklických závislostí:** Vyriešené vnútorné zacyklenie medzi jadrom aplikácie a grafickými dialógmi pri overovaní prenosnosti prostredí, čo zabezpečuje spoľahlivý a čistý štart systému.
- **Oprava zobrazenia varovaní na nepodporovanom hardvéri:** Dialógové okná upozorňujúce na zablokovanie prenosného venvu sa teraz zobrazujú spoľahlivo, s korektným jazykovým prekladom a centrovaním nad aktívnym oknom.
- **Stabilita pri odinštalovaní chránených knižníc:** Pokus o odinštalovanie knižnice chránenej projektom už nespôsobí pád ani chybový výpis v konzole, ale korektne vráti zrozumiteľné bezpečnostné hlásenie v dialógovom okne.

---

## 📁 Dotknuté súbory (Prehľad zmien)

- `core/core_states.py`
- `core/core_bridge.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/venv/pack_inst_unis.py`
- `core/logic/sluzby/venv/editable_service.py`
- `core/logic/sluzby/venv/linker_service.py`
- `core/logic/sluzby/portability/portability_guard.py`
- `core/logic/button/manager/actions.py`
- `core/logic/button/manager/clone.py`
- `core/logic/button/manager/create.py`
- `core/logic/button/pip/freeze.py`
- `core/logic/containers/button/autostart_actions.py`
- `core/logic/path_logic/portable.py`
- `core/logic/vscode_user/start_vs_code_user.py`
- `windows/manager.py`
- `windows/quick_settings.py`
- `windows/pip_package_widget.py`
- `windows/pip_e_window.py`
- `windows/local_packages_window.py`
- `windows/custom_message_box.py`
- `core/logic/system_listener.py` *(odstránený)*
- `core/logic/button/manager/local_packages_linker.py` *(nahradený novou službou)*
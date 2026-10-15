# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.01_dev  
**Vývojová vetva:** Advanced APT Logic, Thread Safety, Subprocess Streaming & Requirements Batching  
*Tento dokument sumarizuje rozsiahlu a hĺbkovú refaktorizáciu subsystému pre správu závislostí a exekúciu procesov naprieč 5 kľúčovými súbormi. Vývoj sa zameral na: 1. Úplnú elimináciu Memory Leaku vo vláknových zámkoch (`apt_logic.py`); 2. Prechod na striktný 4-stavový model JSON evidencie s čítaním `.dist-info/METADATA`; 3. Nahradenie Monkey Patchingu bezpečným Hook systémom a Live kontrolami (`apt_listener.py`, `pip_e.py`); 4. Plynulé, neblokujúce streamovanie subprocesov do GUI s ochranou proti zamrznutiu (`DEVNULL`); 5. Asynchrónne dávkovanie (Chunking) inštalácie requirements.txt. Okrem iného bola natrvalo odstránená chyba pádu Qt jadra pri zatváraní okna s bežiacim vláknom.*

---

## 🚀 Architektonické zmeny a vylepšenia

### 1. Striktný 4-stavový model a hĺbková analýza `[extras]` (`core/logic/sluzby/apt_logic.py`)
- **Nový JSON Single Source of Truth:** Stavový súbor `venvhub_apt_state.json` bol rozšírený o exaktné oddelenie pôvodu závislostí. Obsahuje 4 polia:
  1. `explicit` (Korene nainštalované priamo používateľom)
  2. `explicit_extras_bound` (Pod-balíčky zviazané s manuálnym `[extra]` tagom)
  3. `requirements_cache` (Korene definované v requirements.txt)
  4. `requirements_extras_bound` (Pod-balíčky zviazané cez requirements.txt)
- **Extrakcia z METADATA na disku:** Aplikácia už neháda závislosti. Nové metódy `get_extras_map_from_metadata` a `_get_all_requires_from_metadata` fyzicky čítajú súbory `METADATA` vo virtuálnom prostredí a rekurzívne rozpletajú komplexné stromy (napr. `requests[socks]` -> `pysocks`).
- **Nová metóda `install_sync`:** Synchronizácia teraz prebieha tak, že skript načíta `requirements.txt` do pamäte RAM, porovná ho voči JSON stavu, vypočíta "diff", nainštaluje chýbajúce balíčky, prepočíta zmeny v `[extras]` a na záver spustí čisté `autoremove` iba pre balíčky, ktoré zo súboru naozaj vypadli.

### 2. Live APT kontroly (Interceptor) a ústup od Monkey Patchingu (`core/logic/sluzby/apt_listener.py`)
- **Live Check pred Inštaláciou (`check_install_necessity`):** Poslucháč pomocou nového regex parsera (`_extract_package_and_extras_from_arg`) odchytí príkaz. Ak používateľ inštaluje balíček (aj s extras), ktorý už je 1:1 prítomný v systéme a zapísaný v JSON-e, inštalácia sa okamžite preskočí, čím sa šetrí čas.
- **Live Check pred Odinštalovaním (`verify_uninstall_safety`):** Ochrana konzistencie prostredia. Ak sa používateľ pokúsi odinštalovať balíček, ktorý je natvrdo zapísaný v `requirements.txt` alebo je tvrdou závislosťou (Hard Dependency) iného balíčka, operácia sa zablokuje s chybovou hláškou skôr, než sa odošle pip-u.
- **Bezpečné napojenie:** Všetky "Monkey Patche" prepisujúce priamo `run()` metódy workerov boli zmazané, pretože spôsobovali kolízie signálov. Namiesto toho sa poslucháč napája do nového Hook systému.

### 3. Hook systém a neblokujúce streamovanie subprocesov (`core/logic/pip_e.py`)
- **Trieda `_BaseWorker`:** Implementovaný spoločný predok pre všetky akcie (list, install, uninstall). 
- **Zamedzenie zamŕzaniu inštalátora:** Všetky subprocesy sú teraz spúšťané s `stdin=subprocess.DEVNULL`. Toto kritické vylepšenie bráni pip-u, aby sa zasekol pri neviditeľnej otázke v termináli (napr. *Proceed (Y/n)?*). Pridaný je aj automatický prepínač `-y`.
- **Real-time streamovanie:** Prostredie `_build_env` vynucuje `PYTHONUNBUFFERED=1` a vypína progress bary (`PIP_PROGRESS_BAR=off`, `UV_NO_PROGRESS=1`). Metóda `_run_streamed` zachytáva stdout/stderr priamo z rúry (pipe) a po riadkoch to plynule posiela do logu v GUI.
- **Systém `HOOKS`:** Poslucháč (Listener) vkladá logiku do bodov `install_success`, `uninstall_pre`, a `uninstall_success`. Hooky bežia v asynchrónnom vlákne bez blokovania GUI.

### 4. Dávkovanie Requirements (Chunking) (`core/logic/pip_manager.py`)
- **Kompletný prepis `RequirementsInstallWorker`:** Pôvodné odovzdanie celého `.txt` súboru pip-u bolo zrušené. Metóda `_collect_full_install_specs` rekurzívne načíta hlavný aj všetky vnorené `-r` súbory do RAM, zanechajúc syntax pre verzie, URL, aj `[extras]` a lokálne `-e`.
- **Dávky po 30 (Chunking):** Zozbierané požiadavky sa inštalujú v balíkoch maximálne po 30 kusov. Odstraňuje to riziko pádu na Windows limite pre dĺžku príkazu (MAX_PATH / Command Line String Limit) a umožňuje detailný priebežný výpis ("Inštalujem dávku 1/3").

### 5. Plynulé vlákna a Queue systém (`windows/pip_e_window.py`)
- **Odstránenie blokujúceho `wait()`:** Násilné čakacie metódy v GUI vlákne (`_cleanup_thread`) boli odstránené. Nová metóda `_start_worker` pripája `thread.finished` na bezpečný `deleteLater`.
- **Zavedenie Fronty (`_pending_refresh`):** Ak sa na pozadí niečo inštaluje a udalosť si vyžiada obnovu tabuľky (`refresh_list`), príznak `_pending_refresh` si to zapamätá a zoznam obnoví plynule a automaticky presne v momente, kedy vlákno skutočne "zomrie".

---

## 🐛 Opravy chýb a stabilita

### Oprava pamäťového úniku (Memory Leak) vo Venv zámkoch (`apt_logic.py`)
- **Príznak chyby:** Pri vytváraní zámkov pre vlákna sa ukladali inštancie `threading.RLock()` do globálneho slovníka `_venv_locks`. Tieto objekty v pamäti ostávali visieť až do reštartu aplikácie aj pre venvy, ktoré už boli zmazané.
- **Riešenie:** Implementovaný vlastný `@contextmanager` pre `_get_venv_lock` s počítaním referencií (`ref_count`). Akonáhle blok kódu skončí a `count` padne na nulu, zámok je okamžite a trvalo odstránený zo slovníka a uvoľnený z RAM.

### Oprava pádu (Crash) aplikácie pri zatvorení okna (`pip_e_window.py`)
- **Príznak chyby:** Ak používateľ spustil inštaláciu editovateľného balíčka a klikol na "X" (zavretie okna), po chvíli celá aplikácia spadla s fatálnou C++/Qt chybou alebo `TypeError`.
- **Riešenie:** Pridaný preťažený (override) event `done(self, result)`. Ak sa okno zatvára, kód zistí, či beží vlákno, pošle mu signál `quit()` a zablokuje GUI maximálne na 5 sekúnd cez `wait(5000)`. Zabezpečí sa tak bezpečné uvoľnenie pamäte pred deštrukciou okna.

### Plná podpora UV pre Pip -e balíčky (`pip_e.py`)
- **Príznak chyby:** Zlyhanie workerov alebo tichý fallback na klasický pip, aj keď bol nastavený inštalátor UV. Príprava build nástrojov (setuptools) brzdila UV inštalácie.
- **Riešenie:** `_BaseWorker` teraz plne čerpá z `manager_type`. Metódy siahajú na `UVDetector` a `PackageManagerFactory`. Príprava build nástrojov bola zaobalená pod podmienku `if self.manager_type == "pip":`.

---

## 🧪 Testovacie scenáre a overenie funkčnosti (QA)

### Scenár 1: Overenie čistenia pamäte pri Venv zámkoch (Memory Leak Fix)
1. Spusti aplikáciu a v režime ladenia umiestni breakpoint do `AptLogic.autoremove`.
2. Sleduj obsah slovníka `AptLogic._venv_locks`.
3. Spusti ľubovoľnú inštaláciu v pravom paneli.
4. **Očakávaný výsledok:** Počas behu sa v slovníku objaví cesta k venvu a `count` sa zvýši na 1. Akonáhle inštalácia a zápis do JSONu skončí, kód opustí kontext a slovník `_venv_locks` bude absolútne prázdny.

### Scenár 2: Zablokovanie odinštalácie cez Live Check
1. Otvor `requirements.txt` a zapíš doň `requests`.
2. V grafickom rozhraní klikni na balíček `requests` a zvoľ "Odinštalovať".
3. **Očakávaný výsledok:** `apt_listener` a `verify_uninstall_safety` okamžite zareagujú. Vypíše sa varovanie: *"🛑 OCHRANA: Balíček 'requests' je definovaný v 'requirements.txt'!"*. Vlákno sa preruší a systém neodošle žiaden príkaz inštalátoru.

### Scenár 3: Preskočenie 1:1 inštalácie (Duplicate Check)
1. Uisti sa, že máš v prostredí plne nainštalovaný balíček `fastapi[all]`.
2. Vlož príkaz do inštalačného okna (alebo spusti update zo súboru requirements, ktorý ho obsahuje).
3. **Očakávaný výsledok:** V logu sa objaví *"🔬 Analyzujem stav balíčka 'fastapi'..."* nasledované *"ℹ️ Balíček 'fastapi[all]' je už definovaný v requirements.txt a nainštalovaný. Inštalácia nie je potrebná."* Subproces sa vôbec nevytvorí.

### Scenár 4: Plynulý stream do logu a ochrana pred zamrznutím
1. Otvor okno lokálnych balíčkov (Pip -e).
2. Spusti inštaláciu priečinka. Počas inštalácie sa pokús hybať oknom a kliknúť na tlačidlo "Obnoviť".
3. **Očakávaný výsledok:** Riadky konzoly pribúdajú sekundu po sekunde plynule. Okno nezamŕza, dá sa ním hýbať. Kliknutie na "Obnoviť" nemá okamžitý efekt (UI je zamknuté), ale vďaka `_pending_refresh` sa zoznam tabuľky bleskovo obnoví hneď po zobrazení *"✅ Balíček úspešne prelinkovaný"*.

### Scenár 5: Zatvorenie bežiaceho vlákna (Crash Test)
1. Spusti inštaláciu zložitého projektu (napr. stoviek requirements) alebo Pip -e balíčka.
2. Uprostred logovania okamžite klikni na krížik pre zatvorenie okna.
3. **Očakávaný výsledok:** Aplikácia krátko "zmrzne" (do 5 sekúnd) kvôli ochrannému `wait(5000)`, vlákno na pozadí sa bezpečne "zabije" a okno sa zavrie. Hlavná aplikácia (Jadro) zostane plne stabilná a nespadne.

---

## 📁 Modifikované a novovytvorené súbory

- `core/logic/sluzby/apt_logic.py` *(Prepracovaný model na 4-stavový JSON, odstránenie Memory Leaku cez RLock Ref-counting, pridané Live checky `verify_uninstall_safety` a `check_install_necessity`, METADATA parsovanie).*
- `core/logic/sluzby/apt_listener.py` *(Opustenie Money Patchingu, integrácia regex extrakcie tagov `[extras]`, implementácia napojenia na `HOOKS`).*
- `core/logic/pip_e.py` *(Zavedenie triedy `_BaseWorker` so `_run_streamed`, podpora `UVDetector`, vnucovanie `PYTHONUNBUFFERED` a presmerovanie `stdin=subprocess.DEVNULL`, zavedenie `HOOKS` slovníka).*
- `windows/pip_e_window.py` *(Asynchrónna správa životného cyklu vlákien (`_start_worker`, `deleteLater`), fronta príkazov cez `_pending_refresh`, bezpečná uzávierka cez override `done()`).*
- `core/logic/pip_manager.py` *(Úplný prepis `RequirementsInstallWorker`, rekurzívne parsovanie `-r` priamo do pamäte, dávkovanie inštalácie do Chunkov po 30 položiek).*
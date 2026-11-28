# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.07  
*Táto verzia prináša úplne nové interaktívne okno Stromu závislostí s hĺbkovým rozborom balíčkov, export do moderného konfiguračného štandardu pyproject.toml so záchranou Git a webových odkazov, inteligentné trasovanie vnorených balíčkov (eliminácia falošných sirôt), bleskové čistenie prostredia bez zamŕzania a plnú podporu multiplatformových požiadaviek (PEP 508).*

---

## 🚀 Nové funkcie a vylepšenia

### 1. Nové interaktívne okno: Strom závislostí (`Venv Tree`)
- **Pohľad podľa pôvodu a vlastníctva:** Namiesto neprehľadného zoznamu balíčkov aplikácia ponúka moderný stromový pohľad, ktorý položky prehľadne zoskupuje podľa ich skutočného zdroja:
  - 📁 **Lokálne Linker moduly** (moduly vyvíjané priamo tebou v Linkeri),
  - 📁 **Editovateľné projekty (`pip -e`)** (s priamou cestou k repozitáru na disku),
  - 📁 **Projektové požiadavky (`requirements.txt`)**,
  - 📁 **Manuálne nainštalované balíčky**,
  - 📁 **Systémové nástroje venvu** (izolované jadro prostredia),
  - 📁 **Skutočné siroty** (balíčky, ktoré už nikto nevyžaduje a sú pripravené na vyčistenie).
- **Detailná karta položky (Bočný inšpektor):** Jediným kliknutím na balíček získaš kompletný prehľad:
  - Kto daný balíček drží v systéme nažive (vrátane viacnásobného vlastníctva),
  - Ktoré balíčky sú naň priamo naviazané ako požiadavky a ktoré ako voliteľné rozšírenia `[extras]`,
  - Popis, licenciu, domovskú webovú stránku balíčka a priame umiestnenie na disku.
- **Okamžité vyhľadávanie a filtre:** Písaním do vyhľadávacieho poľa sa strom v reálnom čase filtruje a automaticky rozbaľuje vetvy zodpovedajúce hľadanému balíčku. K dispozícii sú aj rýchle prepínače kategórií s počítadlami.
- **Plynulá zmena jazyka za behu:** Okno okamžite reaguje na zmenu jazyka v Nastaveniach aplikácie – všetky texty, hlavičky aj detailné karty sa ihneď preložia bez nutnosti zatvárať okno či reštartovať aplikáciu.

### 2. Export do štandardu `pyproject.toml` s podporou Git odkazov
- **Moderný exportér (PEP 621):** V hornej lište okna pribudlo tlačidlo **`📄 Export do TOML`**, ktoré vygeneruje čistý a štandardizovaný konfiguračný súbor projektu.
- **Interaktívny výber pomocou zaškrtávacích políčok:** Priamo v strome si môžeš zvoliť, ktoré balíčky chceš do exportu zahrnúť. Manuálne nainštalované balíčky sú predvolene označené, zatiaľ čo automatické podzávislosti zostávajú odškrtnuté, vďaka čomu tvoj `pyproject.toml` zostane čistý bez zbytočného balastu.
- **Záchrana Git a webových odkazov (PEP 610):** Ak máš v prostredí balíčky inštalované priamo z GitHubu alebo privátnych repozitárov, exportér ich neznehodnotí obyčajným názvom, ale zistí ich skutočný zdroj a zapíše plnohodnotnú adresu (napr. `"balicek @ git+https://github.com/..."`).

### 3. Inteligentné trasovanie vnorených rozšírení (Koniec falošným sirotám)
- **Hĺbková reťazová analýza balíčkov:** Doterajšia detekcia vedela spracovať rozšírenia `[extras]` iba z hlavného súboru požiadaviek. Nové jadro dokáže prečítať požiadavky na extras aj hlboko vo vnútri reťazca závislostí.
- **Bezchybné rozpoznanie moderných knižníc:** Knižnice ako `google-generativeai` a ich podzávislosti (napr. `grpcio-status`) už systém nepovažuje omylom za nepotrebné siroty. Každý balíček dostane správne priradeného rodiča.

### 4. Bleskové čistenie balíčkov (Autoremove) bez zamŕzania
- **Odstránenie zbytočných časových limitov:** Pri odinštalovaní nepotrebných balíčkov bol odstránený starý 60-sekundový limit, ktorý pri zložitejších balíčkoch zbytočne zdržoval.
- **Ochrana pred zablokovaním procesu:** Proces odinštalácie má striktne uzatvorený vstup, vďaka čomu nikdy nezamrzne pri čakaní na potvrdenie klávesnicou a grafické rozhranie beží úplne plynule.

### 5. Plná podpora multiplatformových podmienok v `requirements.txt` (PEP 508)
- **Automatické rozpoznanie operačného systému:** VenvHub sa teraz pozerá na podmienky za bodkočiarkou (napr. `colorama; sys_platform == 'win32'` alebo `uvloop; sys_platform == 'linux'`). Ak tvoj projekt obsahuje požiadavky pre iný operačný systém alebo verziu Pythonu, VenvHub to okamžite rozpozná a bezpečne ich preskočí.
- **Čistý stav bez zbytočných chýb:** Balíčky určené pre iné platformy už nespôsobujú zlyhanie inštalácie ani sa neukladajú do zoznamu chýbajúcich balíčkov. Vývoj toho istého projektu na Windows, Linuxe či macOS je teraz úplne plynulý.

---

## 🛠️ Opravy chýb a stabilita

### Opravy v správe závislostí a v používateľskom rozhraní
- **Oprava pádu pri inštalácii editovateľných balíčkov (`pip -e`):** Vyriešená kritická chyba `AttributeError: type object 'AptLogic' has no attribute 'CORE_TOOLS'`, ku ktorej dochádzalo pri registrácii závislostí editovateľného balíčka do stavového súboru venvu. Filtrovanie systémových nástrojov je teraz plne zosúladené s matrikou prostredia cez dynamickú metódu `AptLogic.ensure_system_packages()`.
- **Oprava pádu pri otváraní Správcu (`IndexError` v UI parseri):** Odstránený poškodený prázdny layout tag `<item row="5" column="2">` v súbore `manager.ui`, ktorý spôsoboval zlyhanie funkcie `uic.loadUi` s chybou `IndexError: child index out of range` pri pokuse o otvorenie hlavného okna Master Manager z widgetu.
- **Oprava falošných chýb pri multiplatformových požiadavkách:** Odstránený problém, kedy VenvHub na Windows opakovane hlásil nesúlad stavu a chýbajúce balíčky, ak `requirements.txt` obsahoval knižnice určené výhradne pre Linux alebo macOS.
- **Oprava falošných sirôt pri systémových balíčkoch:** Systémové nástroje venvu (`virtualenv`, `packaging`, `pip`) sa už nikdy nezobrazia duplicitne v zozname sirôt.
- **Oprava pádu pri exporte do TOML:** Odstránená chyba `AttributeError`, ktorá spôsobovala pád okna pri pokuse o generovanie súboru `pyproject.toml`.
- **Oprava pádu pri prepnutí jazyka:** Vyriešená chyba `TypeError`, ktorá mohla nastať pri zmene jazykového balíčka s otvoreným oknom stromu závislostí.
- **Konzistentné kódovanie na Windows:** Procesy odinštalovania balíčkov teraz využívajú bezpečné kódovanie UTF-8 s automatickým ošetrením neštandardných znakov.

---

## 📁 Dotknuté súbory (Prehľad zmien)

- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/venv/editable_service.py`
- `core/logic/sluzby/apt_state.py`
- `core/logic/sluzby/system/python_detector.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/packages/req_toml.py`
- `core/logic/sluzby/venv/pack_tree.py`
- `windows/manager.py`
- `windows/venv_tree_window.py`
- `resources/ui/manager.ui`
- `resources/translations/sk_SK.json`
- `resources/translations/en_US.json`
- `resources/translations/ru_RU.json`
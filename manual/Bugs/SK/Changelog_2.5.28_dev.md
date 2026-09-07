# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.5.28  
*Tento dokument sumarizuje architektonickú opravu spracovania ciest v QSS témach, zabezpečenie automatického kvótovania URL odkazov pre inštalačné priečinky s medzerami, posilnenie stability načítavania ikon, plnú integráciu podpory voliteľných závislostí balíčkov (extras syntax `[extras]`), inteligentnú heuristickú extrakciu balíčkov z priamych URL/Git odkazov, striktné zastavenie inštalácie (Fail-Fast princíp) pri chybách verzií v APT systéme a opravu kódovania výstupu konzoly (UTF-8 Mojibake fix) zavedené vo verzii 2.5.28.*

---

## 🚀 Nové funkcie a vylepšenia

### Univerzálny normalizátor a auto-kvótovanie ciest v QSS témach [v2.5.28]
- **Automatické obalenie URL odkazov v `SkinManager`:** Mechanizmus spracovania štýlov v `SkinManager.apply_skin()` teraz pri nahrádzaní zástupného znaku `{{CORE_THEMES_DIR}}` automaticky zabezpečuje správnu syntax `url("...")` s úvodzovkami.
- **Zachovanie spätnej kompatibility tém:** Všetky existujúce interné aj používateľské `.qss` témy zostávajú plne kompatibilné bez nutnosti akéhokoľvek manuálneho prepisovania zdrojových CSS súborov.

### Podpora voliteľných závislostí balíčkov (`[extras]`) v APT engine [v2.5.28]
- **Hĺbková analýza `dist-info/METADATA`:** Rozšírená logika triedy `AptLogic` o priame čítanie poľa `Requires-Dist` z `METADATA` súborov v `site-packages`. Systém teraz spoľahlivo mapuje vzťahy balíčkov inštalovaných cez extras syntax (napr. `requests[socks]` -> `pysocks`), ktoré štandardný `pip show` / `uv pip show` v riadku `Requires:` neuvádza.
- **Plná kompatibilita s UV a Pip inštalátormi:** Dynamické začlenenie voliteľných závislostí do globálneho grafu bez spomalenia bežného overovania balíčkov.

### Inteligentná extrakcia balíčkov z priamych URL a Git repozitárov [v2.5.28]
- **Fallback heuristika v `RequirementsParser`:** Doplnený robustný mechanizmus na parsovanie názvov balíčkov priamo z čistých URL odkazov, archívov (`.tar.gz`, `.whl`, `.zip`) a Git repozitárov bez nutnosti definovať explicitný fragment `#egg=...`.
- **Podpora verziovaných a vetvených odkazov:** Parser automaticky izoluje čistý názov balíčka s korektným orezaním git vetiev (`@main`, `@v1.0.0`), commit hashov a PEP 440 čísel verzií.

---

## 🐛 Opravy chýb a stabilita

### Oprava zlyhania načítavania ikon v inštalovanom prostredí (NSIS / Program Files) [v2.5.28]
- **Kritická oprava výpadku dynamických ikon:** Odstránená chyba, pri ktorej Qt CSS parser zahodil pravidlá `qproperty-icon: url(...)`, ak bola aplikácia nainštalovaná v ceste obsahujúcej medzery (typicky `C:\Program Files\VenvHub Pro\...`).
- **Ochrana pred zlyhaním CSS tokenizéra:** Doplnená regulárna normalizácia v `core/logic/skin_manager.py`, ktorá garantuje validný formát cesty pre Qt štýly vo všetkých režimoch behu (vývojové prostredie `python main.py`, prenosný portable režim aj štandardná NSIS inštalácia).

### Oprava falošnej detekcie sirôt a Self-Healingu pri extras balíčkoch [v2.5.28]
- **Zamedzenie falošného explicitného označenia:** Mechanizmus Self-Healing už neoznačuje balíčky privolané cez `[extras]` za neznáme manuálne inštalácie a nezapisuje ich chybne do `venvhub_apt_state.json`.
- **Automatické čistenie explicitného stavu pri odinštalovaní:** Doplnené čistenie uvoľneného stromu závislostí (`released_tree`) v metóde `AptLogic.autoremove()`, ktoré garantuje vymazanie pod-závislostí z `state_explicit`, ak boli v minulosti omylom zachytené.
- **Robustné parsovanie metadát:** Odstránená chyba pri delení názvov priečinkov `.dist-info` obsahujúcich pomlčky a čísla verzií priamym čítaním hlavičky `Name:` z `METADATA`.

### Oprava falošného označovania URL a Git balíčkov za ručné inštalácie [v2.5.28]
- **Odstránenie zlyhania parsera pri čistých URL:** Vyriešený stav, kedy balíčky inštalované z URL archívov alebo Git repozitárov bez `#egg=` parser vrátil ako `None`. V dôsledku toho ich Self-Healing mylne považoval za ručné inštalácie z terminálu a odmietal ich pri odstránení z `requirements.txt` odinštalovať.

### Oprava vyhodnocovania chybových stavov inštalátora a zamedzenie nechcených inštalácií (Fail-Fast) [v2.5.28]
- **Oprava zachytenia signálu v `AptListener`:** Odstránená chyba v callbacku `apt_callback`, kde predvolený parameter `result=0` spôsobil nesprávne vyhodnotenie `success = True` aj v prípade, keď proces inštalátora zlyhal (napr. pri neexistujúcej verzii balíčka `requests===3.0`).
- **Ochrana pred svojvoľným stiahnutím najnovších verzií:** Pri zlyhaní inštalátora (UV/Pip) sa APT synchronizácia okamžite preruší a systém sa nepokúša obchádzať dependency solver inštaláciou neobmedzených holých balíčkov.
- **Lokalizácia chybových výstupov:** Všetky systémové hlášky v `AptListener` boli plne integrované do `LanguageManager` a doplnené do jazykových balíčkov (`sk_SK.json`, `en_US.json`).

### Oprava kódovania výstupu procesov v logu (UTF-8 Mojibake Fix) [v2.5.28]
- **Správne dekódovanie Unicode symbolov v `PipManager`:** Doplnený parameter `encoding="utf-8"` a `errors="replace"` do volaní `subprocess.Popen` v triedach `PipWorker` a `UpdateAllWorker`.
- **Eliminácia poškodených znakov:** Odstránené chybné zobrazenie formátovacích znakov a stromov závislostí z nástroja UV (napr. zobrazenie `×`, `╰─`, `▶` namiesto poškodených reťazcov ako `Ă—`, `â•°â”€â–¶`).

---

## 🧪 Testovacie scenáre a overenie funkčnosti (QA)

### Scenár 1: Overenie voliteľných závislostí (`[extras]`)
1. **Inštalácia:**
   - Do `requirements.txt` zapíš: `requests[socks]`.
   - Spusti inštaláciu cez tlačidlo *Requirements / Inštalovať*.
   - **Očakávaný výsledok:** Nainštaluje sa `requests`, `pysocks` a základné závislosti. V stave `venvhub_apt_state.json` sa v poli `"requirements_cache"` nachádza `["requests"]` a v poli `"explicit"` sa `pysocks` **nenachádza** (je správne chápaný ako automatická závislosť).
2. **Odinštalovanie:**
   - Zakomentuj alebo zmaž riadok `requests[socks]` v `requirements.txt`.
   - Spusti synchronizáciu cez tlačidlo *Requirements*.
   - **Očakávaný výsledok:** Log vypíše `Zo súborov boli odstránené: requests` a v sekcii `Autoremove: Removing orphan dependencies:` odstráni **všetky balíčky vrátane `pysocks`**.

### Scenár 2: Overenie priamych URL a Git repozitárov (bez `#egg=`)
1. **Inštalácia z URL / Git:**
   - Do `requirements.txt` zapíš čistú URL alebo Git link, napr.:
     - `https://files.pythonhosted.org/packages/source/e/emoji/emoji-2.2.0.tar.gz`
     - alebo `git+https://github.com/carpedm20/emoji.git`
   - Spusti inštaláciu cez *Requirements*.
   - **Očakávaný výsledok:** Balíček sa úspešne nainštaluje. V `venvhub_apt_state.json` sa v `"requirements_cache"` objaví `["emoji"]` a Self-Healing nezapíše `emoji` do `"explicit"`.
2. **Odinštalovanie po zmazaní zo súboru:**
   - Zakomentuj alebo zmaž URL odkaz z `requirements.txt`.
   - Spusti synchronizáciu cez *Requirements*.
   - **Očakávaný výsledok:** Log vypíše `Zo súborov boli odstránené: emoji` a `Autoremove` balíček `emoji` automaticky a čisto odstráni.

### Scenár 3: Overenie reakcie na neexistujúcu / chybnú verziu (Fail-Fast)
1. **Zadanie chybnej verzie:**
   - Do `requirements.txt` zapíš neexistujúcu verziu, napr.: `requests===3.0`.
   - Spusti inštaláciu cez tlačidlo *Requirements / Inštalovať*.
   - **Očakávaný výsledok:**
     - UV/Pip vypíše chybu (`No solution found / No matching distribution`).
     - APT vypíše: `⚠️ [APT] Operácia zlyhala — APT stav ostáva nezmenený.`
     - **Systém sa okamžite zastaví.** Do prostredia sa **nenainštaluje žiadna náhradná (najnovšia) verzia** a venv ostane v pôvodnom, čistom stave.

### Scenár 4: Overenie čitateľnosti chybového výstupu v logu (UTF-8 kódovanie)
1. **Vyvolanie chybového výstupu z UV:**
   - Do `requirements.txt` vlož neplatnú požiadavku (napr. `requests==3.0`).
   - Spusti inštaláciu cez *Requirements*.
   - **Očakávaný výsledok:**
     - V konzole logu sa výstup zobrazí s korektnými Unicode znakmi:
       ```text
       × No solution found when resolving dependencies:
       ╰─▶ Because there is no version of requests==3.0 and you require
           requests==3.0, we can conclude that your requirements are unsatisfiable.
       ```
     - Vo výstupe sa **nenachádzajú žiadne poškodené znaky** (ako `Ă—` alebo `â•°â”€â–¶`).

---

## 📁 Modifikované a dotknuté súbory

- `core/logic/skin_manager.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/apt_listener.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
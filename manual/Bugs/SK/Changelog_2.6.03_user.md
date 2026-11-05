# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.03  
*Táto verzia prináša kompletnú rekonštrukciu správy projektových závislostí a ručnej inštalácie cez centrálne APT jadro, inteligentnú hromadnú aktualizáciu balíčkov s ochranou tvojich kódov a requirements, univerzálnu kontrolu integrity prostredia pre Pip aj UV a okamžité opravy stability celého systému.*

---

## 🚀 Nové funkcie a vylepšenia

### 1. Inteligentná inštalácia požiadaviek a ručných balíčkov (`requirements.txt`)
- **Koniec slepého sťahovania (Brute-Force Chunking):** Inštalácia súboru `requirements.txt` už nesťahuje všetkých 30 balíčkov v dávkach dokola. Systém pred každým krokom urobí chytrú DIFF analýzu voči disku.
- **Inštalujeme len to, čo chýba:** Inštalátor (`pip` / `uv`) po novom dostane na spracovanie **výhradne tie balíčky, ktoré v prostredí reálne chýbajú** alebo nespĺňajú požadovanú verziu.
- **Ochrana pred zbytočným preinštalovaním pri ručnom zadaní:** Ak napríklad zadáš balíček, ktorý už vo venv je, systém inštaláciu okamžite preskočí.

### 2. Pokročilá verifikačná logika verzií (Upgrade / Downgrade)
- **Stráženie verzií (PEP 440 / PEP 508):** APT jadro teraz bleskovo kontroluje verzie priamo z metadát na disku (`*.dist-info`).
- **Automatická oprava nesúladu:** Ak máš v projekte napríklad staršiu verziu balíčka (`0.4.0`) a v `requirements.txt` alebo pri ručnom zadaní si vyžiadaš inú (napr. `0.4.6` alebo nižšiu), systém nesúlad deteguje a automaticky spustí cielený **Upgrade** alebo **Downgrade**.

### 3. Inteligentná hromadná aktualizácia (`Update All`)
- **Bezpečná hromadná aktualizácia:** Tlačidlo pre aktualizáciu všetkých balíčkov bolo kompletne prerobené na modernú službu `PackageUpdateService`.
- **Ochranné filtre pred sťahovaním:** 
  - **Ochrana `requirements.txt`:** Ak máš v požiadavkách pevne limitovanú verziu (napr. `Django==3.2`), aktualizácia ju nezmení.
  - **Ochrana Linkera:** Balíčky viazané na lokálne vývojové moduly sú bezpečne chránené.
  - **Ochrana editovateľných balíčkov (`pip -e`):** Systém ich automaticky vyradí z hromadného upgradu.
- **Automatické čistenie (Autoremove):** Ak medzitým zmažeš balík z `requirements.txt`, po aktualizácii sa automaticky spustí čistenie a odstránia sa aj osirelé závislosti.

### 4. Univerzálna kontrola integrity prostredia (Pip & UV)
- **Zovšeobecnenie `pip check` / `uv pip check`:** Po každej inštalácii alebo aktualizácii (bez ohľadu na to, či používaš klasický `pip` alebo rýchly `uv`) systém v reálnom čase overí, či v prostredí nevznikli konflikty závislostí.
- **Prehľadné hlásenia:** V logu sa okamžite dozvieš, či sú všetky závislosti stopercentne kompatibilné.

---

## 🛠️ Opravy chýb a stabilita

### Opravy v správe balíčkov a jadre
- **Oprava kritického pádu pri hromadnej aktualizácii:** Odstránená chyba straty kontextu (`AttributeError`), ktorá spôsobovala pád aplikácie pri kliknutí na tlačidlo Update.
- **Oprava rozbaľovania inštalácií (`ValueError`):** Opravený defekt v listeneri, ktorý nesprávne spracovával dáta z nového parsera špecifikácií.
- **Stabilita CoreBridge a prekladov:** Opravený chýbajúci import stavov pri štarte aplikácie a doplnené chýbajúce preklady pre slovenské, anglické aj ruské rozhranie.
- **Čistá konzola:** Odstránené otravné a falošné varovania Qt frameworku zo systémového terminálu.

---

## 📁 Dotknuté súbory (Prehľad zmien)

- `core/core_bridge.py`
- `core/logic/pip_manager.py`
- `core/logic/system_listener.py`
- `core/logic/button/pip/pip_command_worker.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/venv/package_update.py`
- `windows/manager.py`
- `windows/pip_manager_window.py`
- `translations/en_US.json`
- `translations/ru_RU.json`
- `translations/sk_SK.json`
# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.05  
*Táto verzia prináša novú generáciu detekcie systémových Python interpretov a nástroja UV, ochranu pred zamŕzaním aplikácie pri štarte a inštaláciách, opravu kritického pádu pri klonovaní virtuálnych prostredí a celkové zrýchlenie správy lokálnych balíčkov.*

---

## 🚀 Nové funkcie a vylepšenia

### 1. Nová generácia detekcie Python interpretov
- **Hĺbkové a spoľahlivé skenovanie systému:** Detekčný mechanizmus bol od základu prepísaný. Okrem štandardného Windows launchera (`py`) aplikácia dôkladne prehľadáva priečinky `%LOCALAPPDATA%\Programs\Python` a `Program Files`.
- **Ochrana pred zamrznutím štartu (Timeout guard):** Ak systém narazí na pomalé, odpojené alebo sieťové disky, aplikácia nezamrzne. Detekcia má nastavený bezpečnostný 5-sekundový limit, vďaka čomu sa VenvHub Pro vždy spoľahlivo a rýchlo spustí.
- **Odstránenie duplicitných odkazov:** Kanonické overovanie ciest zaručuje, že sa v zozname nezobrazujú duplicitné interprety spôsobené odkazmi a symlinkami.

### 2. Inteligentná detekcia a bezpečné používanie nástroja UV
- **Viacúrovňové vyhľadávanie binárky UV:** Detektor overuje prítomnosť UV v prísnom a logickom poradí:
  1. *Pribalené priamo v aplikácii* (`uv.exe` v koreni VenvHubu).
  2. *V aktívnom virtuálnom prostredí* (v priečinku `Scripts` alebo priamo vedľa Pythonu).
  3. *V používateľských inštaláciách* (v `%LOCALAPPDATA%\bin` z oficiálneho inštalátora alebo v `%USERPROFILE%\.cargo\bin`).
  4. *V systémovej premennej PATH*.
- **Overenie reálnej funkčnosti:** Systém nekontroluje len prítomnosť súboru na disku, ale v tichosti na pozadí overí jeho spustiteľnosť (`--version`). Ak je binárka poškodená, nepoužije sa.
- **Ochrana v Nastaveniach pred zlyhaním:** Ak v nastaveniach prepneš správcu balíčkov z Pip na UV a nástroj UV v systéme nemáš dostupný, aplikácia ťa okamžite upozorní a bezpečne vráti voľbu späť na Pip, aby nedochádzalo k chybám pri inštalácii závislostí.

### 3. Plynulé rozhranie bez zamŕzania a jasné stavy
- **Koniec hláseniam „Aplikácia neodpovedá“:** Inštalácia nástroja PIP a spracovanie verzií Pythonu bežia v optimalizovaných vláknach na pozadí. Používateľské rozhranie zostáva počas celej doby plne responzívne.
- **Prehľadné overovanie nástroja PIP:** V záložke *Local Python* systém v reálnom čase overuje stav PIPu pre každý interpreter. Okamžite vidíš, či prebieha kontrola (⏳), či je PIP pripravený (✅), alebo v balíčku chýba.
- **Plynulejšie mazanie a pridávanie runtime balíčkov:** Práca s prenosnými (Embed) verziami Pythonu je sprevádzaná prehľadným ukazovateľom priebehu bez zasekávania okna.

---

## 🛠️ Opravy chýb a stabilita

### Opravy vo virtuálnych prostrediach a v jadre aplikácie
- **Oprava kritického pádu pri klonovaní prostredia:** Odstránená chyba v module klonovania (`clone.py`), ktorá pri pokuse o vytvorenie kópie existujúceho venvu spôsobovala pád celej aplikácie.
- **Oprava inicializácie pri štarte aplikácie:** Opravená chyba pri spúšťaní jadra a načítavaní jazykových prekladov, ktorá mohla za určitých okolností zabrániť otvoreniu hlavného okna.
- **Rýchlejšie načítanie vďaka Lazy-loadingu:** Detektory Pythonu a UV sa inicializujú až vo chvíli, kedy sú reálne potrebné, čo výrazne zrýchľuje samotný štart aplikácie a šetrí systémové prostriedky.

---

## 📁 Dotknuté súbory (Prehľad zmien)

- `main.py`
- `core/core_bridge.py`
- `core/core_states.py`
- `core/logic/sluzby/system/python_detector.py`
- `core/logic/sluzby/venv/uv_detector.py`
- `core/logic/button/manager/clone.py`
- `core/logic/button/manager/create.py`
- `core/logic/commands/uv_commands.py`
- `core/logic/project_manager.py`
- `core/logic/python_installer/button/pip_installer.py`
- `core/logic/python_installer/button/python_install.py`
- `windows/manager.py`
- `windows/python_ver.py`
# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.5.28  
*Táto aktualizácia prináša plnú podporu voliteľných balíčkových rozšírení ([extras]), inteligentné spracovanie priamych Git a URL odkazov v požiadavkách, striktné a bezpečné zastavenie inštalácie pri chybách verzií, opravu načítavania ikon v inštalačných priečinkoch s medzerami a čisté zobrazenie výstupov v zázname bez poškodených znakov.*

---

## 🚀 Nové vylepšenia

### 📦 Plná podpora voliteľných závislostí (`[extras]`)
- **Hĺbková analýza balíčkov:** Správca závislostí (APT engine) teraz detailne analyzuje metadáta balíčkov a plne rozumie syntaxi voliteľných rozšírení (napr. `requests[socks]`).
- **Presná evidencia stromu závislostí:** Balíčky a ich voliteľné pod-závislosti sa automaticky mapujú. Pri odstránení hlavného balíčka z `requirements.txt` funkcia *Autoremove* spoľahlivo a čisto odinštaluje aj všetky jeho nepoužívané vedľajšie knižnice.

### 🔗 Inteligentné spracovanie priamych Git a webových odkazov
- **Automatická detekcia názvov bez `#egg=`:** Aplikácia dokáže presne identifikovať a izolovať názov balíčka priamo z webových archívov (`.whl`, `.tar.gz`, `.zip`) aj Git repozitárov (`git+https://...`) bez nutnosti manuálneho dopisovania parametra `#egg=`.
- **Podpora vetiev a verzií:** Správne sú spracované aj odkazy s definovanými vetvami (`@main`, `@v1.0`) alebo špecifickými commitmi.

### 🛡️ Bezpečné zastavenie inštalácie pri chybách (Fail-Fast princíp)
- **Ochrana pred nechcenými inštaláciami:** Ak v `requirements.txt` zadáte neplatnú alebo neexistujúcu verziu balíčka (napr. `requests===3.0`), systém inštaláciu okamžite a bezpečne preruší.
- **Zamedzenie svojvoľného sťahovania:** Aplikácia sa pri chybe nepokúša obchádzať pravidlá sťahovaním náhradných najnovších verzií – vaše virtuálne prostredie tak zostáva v čistom, stabilnom a predvídateľnom stave.

---

## 🛠️ Opravy chýb a stabilita

### 🖼️ Oprava načítavania ikon pri inštalácii do `Program Files`
- **Automatické ošetrenie ciest s medzerami:** Vyriešený problém, pri ktorom sa v nainštalovanej verzii aplikácie (typicky v `C:\Program Files\VenvHub Pro\...`) nemuseli správne zobraziť dynamické ikony v témach vzhľadu.
- **Spätná kompatibilita motívov:** Všetky interné aj používateľské `.qss` témy fungujú bez nutnosti akejkoľvek manuálnej úpravy súborov.

### 🔤 Oprava kódovania výstupu v zázname (UTF-8 Mojibake Fix)
- **Čisté a ostré logy:** Opravené dekódovanie výstupu z konzoly – stromové diagramy a špeciálne znaky nástroja UV (ako `×`, `╰─`, `▶`) sa už nezobrazujú ako poškodené zhluky znakov (`Ă—`, `â•°â”€â–¶`).

### 🧹 Stabilizácia stavu balíčkov a Self-Healingu
- **Koniec falošných manuálnych označení:** Balíčky inštalované cez rozšírenia `[extras]` alebo priame URL odkazy už systém mylne nepovažuje za ručne doinštalované knižnice a pri čistení požiadaviek ich korektne odstráni.
- **Lokalizované systémové hlášky:** Všetky nové stavové a chybové hlásenia synchronizácie boli plne preložené do slovenčiny a angličtiny.

---

## 📁 Dotknuté súbory

- `core/logic/pip_manager.py`
- `core/logic/skin_manager.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
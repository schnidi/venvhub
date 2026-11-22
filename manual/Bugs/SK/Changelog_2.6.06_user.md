# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.06  
*Táto verzia prináša prehľadný vizuálny strom závislostí v logu, inteligentnú ochranu pred rozbitím lokálnych modulov v Linkeri, bezchybnú dvojfázovú inštaláciu editovateľných balíčkov (vrátane requiremenst.txt a voliteľných rozšírení [extras]), odstránenie pádov aplikácie pri práci s dialógmi a celkové zjednotenie prekladov.*

---

## 🚀 Nové funkcie a vylepšenia

### 1. Vizuálny strom závislostí a detailná inšpekcia balíčkov
- **Štruktúrovaný rentgen závislostí:** Pri inštalácii balíčkov s voliteľnými doplnkami (napr. `requests[socks]`) systém namiesto neprehľadných technických výpisov vykreslí priamo v logu prehľadný vetvený strom rodičovských a dcérskych balíčkov.
- **Vizitka presnej zhody (1:1 Skip):** Ak už požadovaný balíček na disku existuje a spĺňa špecifikáciu verzie, VenvHub zobrazí prehľadnú vizitku (názov balíčka, verzia na disku, požiadavka) a inštaláciu bezpečne a bleskovo preskočí bez zaťažovania siete.
- **Pred-inštalačná inšpekcia lokálnych balíčkov (`pip -e`):** Ešte pred spustením inštalácie systém analyzuje konfiguračné súbory projektu a vopred ťa informuje, ktoré závislosti už v prostredí sú, ktoré chýbajú a ktoré si vyžiadajú zmenu verzie.

### 2. Bezpečnejší Linker s inteligentnou STOPKOU závislostí
- **Ochrana pred nechceným rozbitím projektov:** Ak sa pokúsiš odpojiť lokálny modul, na ktorom je pevne závislý iný aktívny modul (napr. odpojenie loggera, ktorý vyžaduje tvoje jadro aplikácie), Linker operáciu včas zastaví.
- **Automatický návrat stavu (Rollback):** Pri zastavení operácie sa zaškrtávacie políčko automaticky vráti do pôvodného zaškrtnutého stavu, takže rozhranie vždy presne zodpovedá skutočnému stavu na disku.
- **Čisté odlinkovanie:** Pri odpojení modulov systém spustí cielený 3-krokový proces (zmazanie prepojení, bezpečné odinštalovanie osirelých závislostí a vyčistenie konfigurácie pre VS Code).

### 3. Spoľahlivá podpora editovateľných projektov (`requiremenst.txt` a `pip -e`)
- **Bezchybné spracovanie rozšírení [extras]:** Odstránené chyby pri čítaní hranatých zátvoriek v zoznamoch závislostí. Balíčky ako `requests[socks]` sa teraz prečítajú a nainštalujú korektne na prvý pokus.
- **Dvojfázová inštalácia:** Samotný lokálny vývojový projekt sa prelinkuje bez zbytočného sťahovania a v druhom kroku inštalátor bezpečne dotiahne všetky jeho skutočné podzávislosti (vrátane hlbokých závislostí). Záverečná kontrola integrity prostredia tak prebehne na 100 % bez konfliktov.
- **Inteligentné automatické čistenie (Autoremove):** Ak priamo v konfiguračnom súbore projektu (`requiremenst.txt`) zmažeš nepotrebnú závislosť, systém pri ďalšej synchronizácii zmenu deteguje a uvoľnené balíčky automaticky a bezpečne odinštaluje.

---

## 🛠️ Opravy chýb a stabilita

### Stabilita rozhrania, procesov a dialógov
- **Oprava kritického pádu pri varovných dialógoch:** Vyriešená chyba na úrovni vlákien, ktorá spôsobovala pád celej aplikácie pri zobrazení varovného dialógu v okne Lokálnych balíčkov.
- **Koniec nezrozumiteľným hláškam `{0}`:** Odstránená chyba formátovania v chybových dialógoch Linkera. Namiesto surovej šablóny sa teraz vždy zobrazí zrozumiteľné a konkrétne vysvetlenie problému.
- **Odstránenie zdvojených záznamov v logu:** Odstránené opakované výpisy stavov inštalácie, vďaka čomu je konzola prehľadnejšia a ľahšie čitateľná.
- **Nový jednotný most pre dialógy a indikátory priebehu:** Vytváranie venvov, mazanie, klonovanie aj ochrana prenosnosti (Portability Guard) využívajú zjednotený systém bezrámových okien a dialógov s vlastnou diagnostikou pri štarte.
- **Zjednotenie prekladov:** Prečistené interné preklady – odstránené miešanie anglických výrazov do slovenského jazyka a doplnené chýbajúce lokalizačné texty pre všetky dialógy a stavy.

---

## 📁 Dotknuté súbory (Prehľad zmien)

- `main.py`
- `core/core_bridge.py`
- `core/core_states.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/dialog_bridge.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/venv/pack_operation_state.py`
- `core/logic/sluzby/venv/pack_requr.py`
- `core/logic/sluzby/venv/pack_inst_unis.py`
- `core/logic/sluzby/venv/package_update.py`
- `core/logic/sluzby/venv/editable_service.py`
- `core/logic/sluzby/venv/linker_service.py`
- `core/logic/button/manager/create.py`
- `core/logic/button/manager/clone.py`
- `core/logic/button/manager/delete.py`
- `core/logic/button/manager/py_launcher.py`
- `core/logic/button/widget/widget_dispatcher.py`
- `core/logic/box/ide_settings.py`
- `core/logic/box/metadata_exe.py`
- `windows/local_packages_window.py`
- `windows/progress_dialog.py`
- `translations/sk_SK.json`
- `translations/en_US.json`
- `translations/ru_RU.json`
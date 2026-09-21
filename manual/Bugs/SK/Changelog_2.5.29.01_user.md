# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.5.29.01  
*Táto opravná aktualizácia (hotfix) prináša kritickú opravu stability pre používateľov operačného systému Windows. Rieši zlyhanie aplikácie na chybe kódovania (`UnicodeDecodeError` / CP1250) pri načítavaní zoznamu balíčkov, aktualizáciách a spracovaní závislostí cez inštalátor PIP, a zároveň odstraňuje interné systémové varovania Qt jadra v správcovi balíčkov.*

---

## 🛠️ Opravy chýb a stabilita

###  Oprava kritického pádu pri práci s inštalátorom PIP (`UnicodeDecodeError`)
- **Odstránenie kolízie kódovania CP1250:** Na lokalizovaných systémoch Windows (slovenské a české prostredie) dochádzalo pri spustení príkazov PIP k pádu interného čítacieho vlákna (`_readerthread`), pretože systémové kódovanie nedokázalo spracovať špecifické UTF-8 znaky vo výstupe konzoly.
- **Vynútená multiplatformová UTF-8 komunikácia:** Všetky komunikačné kanály procesov teraz striktne používajú kódovanie UTF-8 s automatickou náhradou poškodených znakov. Aplikácia tak bezpečne spracuje výstupy PIP aj v prípade, že balíček obsahuje špeciálne symboly, medzinárodné znaky či diakritiku v popise alebo mene autora.

###  Odstránenie interných varovaní Qt mechanizmu (`connectSlotsByName`)
- **Zamedzenie falošným chybovým hláseniam:** V okne správcu balíčkov (*Pip Manager*) dochádzalo pri jeho otvorení k vypisovaniu varovaní Qt Meta-Object systému (`No matching signal for on_freeze_finished / on_update_all_finished`).
- **Čisté prepojenie asynchrónnych slotov:** Interné callbacky asynchrónnych úloh (export balíčkov do `requirements.txt` a hromadná aktualizácia) boli premenované tak, aby nekolidovali s vyhradeným formátom automatického prepájania Qt Designeru. Tým sa prečistil systémový výstup konzoly a optimalizovala sa inicializácia dialógového okna.

---

## 📁 Dotknuté súbory

- `core/logic/button/pip/load_list.py`
- `core/logic/sluzby/apt_logic.py`
- `windows/pip_manager_window.py`
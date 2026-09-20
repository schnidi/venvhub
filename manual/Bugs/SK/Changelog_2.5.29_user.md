# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.5.29  
*Táto aktualizácia prináša flexibilné kaskádové rozpoznávanie editovateľných balíčkov (`-e`), plné zachovanie histórie a pravidiel závislostí APT pri klonovaní virtuálnych prostredí a inteligentnú ochranu pod-závislostí pri manuálnej úprave ich verzií alebo downgrade.*

---

## 🚀 Nové vylepšenia

### 📂 Flexibilné rozpoznávanie lokálnych balíčkov (`pip -e`)
- **Kaskádové overovanie ciest:** Správca požiadaviek (`RequirementsParser`) teraz využíva viacúrovňový mechanizmus na rozpoznávanie cieľov za direktívou `-e` / `--editable`.
- **Podpora ľubovoľných diskov a priečinkov:** Lokálne balíčky môžu byť umiestnené kdekoľvek na disku (napr. na inom disku `F:/...`) alebo zadané relatívnou cestou (`./...`, `../...`) voči súboru `requirements.txt` bez obmedzenia len na centrálny priečinok `pip_e_root`.
- **Inteligentný záchranný mechanizmus:** Ak sa adresár balíčka presunie, systém dokáže izolovať názov balíčka a predísť chybám pri spracovaní.

### 🐑 Plné zachovanie histórie závislostí pri klonovaní Venvu
- **Prenos stavu APT (`venvhub_apt_state.json`):** Pri klonovaní alebo zálohovaní prostredia sa automaticky prenáša kompletná hierarchia a evidencia balíčkov.
- **Bezchybná kontinuita pravidiel:** Klonované prostredie presne vie, ktoré balíčky boli nainštalované explicitne a ktoré sú len vedľajšími závislosťami. Funkcia *Autoremove* tak v klone funguje rovnako spoľahlivo ako v pôvodnom prostredí.
- **Lokalizovaná spätná väzba:** Dialóg klonovania prehľadne informuje o úspešnom prenose histórie a pravidiel závislostí v slovenčine aj angličtine.

### 🧩 Inteligentná ochrana pod-závislostí pri úprave verzií (Downgrade)
- **Kontextové overenie väzieb:** Pri inštalácii špecifickej verzie knižnice (alebo downgrade) systém prednostne overí, či balíček nie je súčasťou iného nadradeného balíčka v prostredí.
- **Zamedzenie osiroteným knižniciam:** Ak upravíte verziu pod-závislosti (napr. `pysocks` pod `requests[socks]` alebo `urllib3` pod `requests`), systém ju neoznačí ako ručne nainštalovanú. Zostáva evidovaná ako závislosť a pri odinštalovaní hlavného balíčka sa automaticky a čisto uprace.

---

## 🛠️ Opravy chýb a stabilita

### 🛡️ Ochrana `-e` balíčkov pred falošnou manuálnou konverziou (Self-Healing)
- **Zamedzenie prepisovania ciest:** Odstránená chyba, pri ktorej systém nesprávne prepájal cesty lokálnych balíčkov s priečinkom `pip_e_root`, čo viedlo k ich falošnému označeniu za ručné inštalácie.
- **Čistý životný cyklus v `requirements.txt`:** Lokálne vyvíjané balíčky inštalované cez `-e` sú korektne evidované v registri požiadaviek. Pri ich zakomentovaní alebo zmazaní zo súboru ich *Autoremove* okamžite a spoľahlivo odinštaluje.

### 🧬 Zamedzenie degradácie pravidiel závislostí pri klonovaní
- **Ochrana pred stratou hierarchie:** Vyriešený problém, pri ktorom sa v klonovanom prostredí označili všetky balíčky ako explicitné (manuálne), čo blokovalo ich následné automatické čistenie po odstránení hlavných knižníc.

### 🧹 Stabilizácia stavu balíčkov po manuálnom príkaze `pip install`
- **Presná evidencia v APT Listeneri:** Opravené správanie, kedy akýkoľvek manuálny zásah do verzie balíčka spôsobil jeho trvalé uzamknutie medzi manuálne balíčky, aj keď išlo o pod-závislosť.

---

## 📁 Dotknuté súbory

- `core/logic/button/manager/clone.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/requirements_parser.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
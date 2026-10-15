# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.01  
*Táto verzia predstavuje obrovský skok v stabilite, inteligencii a rýchlosti aplikácie. Zameriava sa na dokonalú ochranu vášho virtuálneho prostredia pred náhodným rozbitím, plynulé (nezamŕzajúce) grafické rozhranie a bezpečné inštalovanie obrovských projektov. Aplikácia teraz oveľa lepšie "chápe" vzťahy medzi balíčkami a už nikdy nespadne, ak omylom zatvoríte okno uprostred práce.*

---

## 🚀 Nové funkcie a vylepšenia

### ✨ Inteligentný štít prostredia (Ochrana pred rozbitím)
- **Čo sa zmenilo:** Aplikácia teraz naživo sleduje, čo sa snažíte urobiť. Ak sa pokúsite odinštalovať balíček, ktorý je pre váš projekt kritický (napríklad je pevne zapísaný v `requirements.txt` alebo ho nevyhnutne potrebuje iná knižnica), systém vás okamžite zastaví a vypíše varovanie.
- **Prínos:** Už si nikdy omylom nevymažete kľúčové súčasti projektu. Vaše prostredie zostane vždy funkčné a konzistentné.

### ✨ Bleskové preskakovanie zbytočností
- **Čo sa zmenilo:** Pred každou inštaláciou si systém bleskovo overí aktuálny stav. Ak zistí, že požadovaný balíček (aj so všetkými jeho voliteľnými súčasťami, napr. `fastapi[all]`) už v systéme reálne máte, inštaláciu okamžite preskočí.
- **Prínos:** Obrovská úspora času. Aplikácia nebude zbytočne nič sťahovať ani spúšťať inštalátor pre veci, ktoré už dávno fungujú.

### ✨ Stabilná inštalácia obrovských projektov
- **Čo sa zmenilo:** Inštalácia masívnych zoznamov z `requirements.txt` už neprebieha naraz (čo na systéme Windows občas spôsobovalo pády kvôli dlhým príkazom). Aplikácia si zoznam rozdelí na menšie dávky (po 30 balíčkov).
- **Prínos:** Inštalácia je absolútne stabilná, nech je váš projekt akokoľvek veľký. V logu navyše presne vidíte postup (napr. *Inštalujem dávku 1/3*).

### ✨ Dokonalá pamäť na zložité balíčky (Extras)
- **Čo sa zmenilo:** Systém sa naučil perfektne chápať zápisy so zátvorkami (tzv. extras, napr. `requests[socks]`). Presne vie, ktoré pod-balíčky si tento zápis do systému priniesol.
- **Prínos:** Pri odinštalovaní takýchto balíčkov systém korektne a dočista uprace úplne všetky súvisiace závislosti, takže vám vo virtuálnom prostredí neostane žiadny "stavebný odpad".

---

## 🛠️ Opravy chýb a stabilita

### ❌ Koniec zamŕzaniu okien a logov
- **Opravené:** Pri inštalácii alebo odinštalovaní balíčkov okno aplikácie už nikdy nezamrzne. Text v logu (konzole) nabieha plynule, riadok po riadku, v reálnom čase. Ak počas práce kliknete na tlačidlo "Obnoviť", aplikácia počká a zoznam plynule aktualizuje až keď to bude bezpečné.

### ❌ Oprava pádov aplikácie pri zatváraní okna
- **Opravené:** V minulosti mohla aplikácia spadnúť (Crash), ak ste zatvorili okno (napr. okno lokálnych balíčkov) presne vo chvíli, keď na pozadí ešte prebiehala inštalácia. Teraz aplikácia bezpečne proces ukončí, uprace po sebe pamäť a až potom sa okno ticho zavrie.

### ❌ Odstránenie zasekávania inštalátora (Pip)
- **Opravené:** V špecifických prípadoch inštalátor na pozadí čakal na neviditeľné potvrdenie od používateľa (napr. *Proceed (Y/n)?*), čo spôsobilo, že sa proces zasekol navždy. Aplikácia teraz automaticky vynucuje odpovede a zabraňuje akémukoľvek zablokovaniu.

### ❌ Zníženie spotreby pamäte (Oprava Memory Leaku)
- **Opravené:** Opravená skrytá chyba, pri ktorej si aplikácia natrvalo ukladala do pamäte RAM dáta o virtuálnych prostrediach, s ktorými ste už prestali pracovať (alebo ste ich zmazali). Aplikácia je teraz ľahšia a rýchlejšia pri dlhodobom používaní.

---

## 📁 Dotknuté súbory

- `core/logic/pip_e.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/apt_logic.py`
- `windows/pip_e_window.py`
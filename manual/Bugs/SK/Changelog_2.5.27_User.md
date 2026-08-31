# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.5.27  
*Táto aktualizácia prináša automatické upozornenia na novú verziu priamo v záhlaví okna, okamžité prepínanie jazykov v rozhraní, dôležité opravy čistenia a synchronizácie lokálnych balíčkov (pip -e) a celkové zvýšenie stability aplikácie.*

---

## 🚀 Nové vylepšenia

### 🔔 Upozornenie na novú verziu priamo v lište okna
- **Rýchla kontrola na pozadí:** Aplikácia hneď pri štarte bleskovo a nečujne overí na GitHube, či je dostupná novšia verzia. Kontrola beží na pozadí a nijako nespomaľuje štart ani prácu v aplikácii.
- **Nové tlačidlo v hornej lište:** Ak je vydaná nová verzia, v záhlaví okna (vedľa tlačidla *O programe*) sa automaticky zobrazí ikona aktualizácie prispôsobená aktívnej svetlej či tmavej téme.
- **Stiahnutie jedným kliknutím:** Kliknutím na ikonu sa v prehliadači otvorí oficiálna stránka projektu priamo vo vašom nastavenom jazyku (slovenčina alebo angličtina).

### 🌐 Okamžité prepínanie jazyka a reaktívne záhlavie okien
- **Blesková zmena jazyka:** Pri prepnutí jazyka cez *Rýchle nastavenia* sa texty v hornej lište a názvy okien preložia okamžite bez potreby reštartovania okna či celej aplikácie.
- **Centrálna správa verzie:** Informácie o verzii v dialógovom okne *O programe* sú teraz vždy presné a dynamicky zosúladené vo všetkých jazykových mutáciách.

---

## 🛠️ Opravy chýb a stabilita

### ✏️ Oprava čistenia a správy lokálnych balíčkov (`pip -e`)
- **Oprava čistenia po vymazaní z requirements.txt (Autoremove):** Vyriešená chyba, pri ktorej lokálny vývojový balíček vymazaný alebo zakomentovaný v `requirements.txt` nebol odinštalovaný, pretože ho systém mylne považoval za chránený. Požiadavky sa teraz čistia presne a spoľahlivo.
- **Obnovenie varovania pred nechceným odinštalovaním:** Opravená detekcia vo widgete balíčkov – aplikácia vás opäť riadne varuje dialógovým oknom, ak sa pokúsite odinštalovať lokálny balíček, ktorý je stále súčasťou definície projektu.
- **Bezchybná synchronizácia požiadaviek:** Funkcia zosúladenia balíčkov (`install_sync`) bola opravená tak, aby správne spracovávala relatívne cesty a nevytvárala falošné konflikty závislostí.

### 🎨 Vizuálne a systémové opravy
- **Oprava prepínania jazyka z Rýchlych nastavení:** Opravená chyba, ktorá v určitých prípadoch bránila korektnému preposlaniu zmeny jazyka do otvorených častí aplikácie.
- **Oprava motívu GitHub Light:** Opravený neuzavretý blok štýlov, ktorý spôsoboval nesprávne správanie a ignorovanie hover efektov na MiniBare.
- **Vyladenie ikon pre všetky motívy:** Do všetkých farebných tém boli pridané ostré vektorové SVG ikony pre notifikácie o aktualizácii.

---

## 📁 Dotknuté súbory

- `assets/about.json`
- `core/logic/language_manager.py`
- `core/logic/sluzby/about_logic.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/github_update.py`
- `core/themes/*.qss` *(všetky témy vzhľadu)*
- `core/themes/icon/update/github_update_white.svg`
- `core/themes/icon/update/github_update_black.svg`
- `main.pyw`
- `ui/custom_title_bar.ui`
- `windows/custom_title_bar.py`
- `windows/manager.py`
- `windows/pip_package_widget.py`
- `windows/quick_settings.py`
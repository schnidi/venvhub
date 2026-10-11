# VenvHub Pro - Poznámky k vydaniu (Changelog)

**Verzia:** v2.6.00  
*Táto aktualizácia prináša natívnu podporu pre Cursor AI, autonómnu detekciu editorov na pozadí, plnú fyzickú izoláciu používateľských profilov a 100 % ochranu vašich vlastných nastavení pri synchronizácii. Zároveň zavádza automatickú opravu ciest pri zmene písmena USB disku a reaktívnejšie používateľské rozhranie.*

---

## 🚀 Nové vylepšenia

###  Plná podpora Cursor AI a autonómny skener
- **Nezávislé prostredia:** Pridaná plnohodnotná podpora pre moderný editor Cursor AI, fungujúci bok po boku s Visual Studio Code vďaka novým nezávislým CLI dispečerom.
- **Detekcia editorov na pozadí:** Nový 2-sekundový asynchrónny skener neustále sleduje systém a pripojené USB kľúče. Detekcia nových editorov prebieha okamžite, a to bez zablokovania alebo sekania grafického rozhrania.

###  100 % ochrana nastavení a oddelenie profilov (Izolácia)
- **Fyzické oddelenie dát:** Používateľské profily sú teraz striktne izolované do nezávislých priečinkov (`📁 vscode/` a `📁 cursor/`), čím sa eliminuje akékoľvek nežiaduce miešanie nastavení medzi editormi.
- **Inteligentná synchronizácia (Merge):** Zápis do konfiguračných zložiek `.vscode/` a `.cursor/` upravuje výhradne cesty k Pythonu. Vaše vlastné fonty, pravidlá AI či používateľské úlohy systém už neprepisuje vďaka novému vnútornému trackeru.
- **Dynamický import zo systému:** Funkcia pre sťahovanie existujúceho profilu z OS teraz inteligentne rozpozná aktívne IDE a stiahne správne rozšírenia a dáta z príslušných priečinkov (`AppData/Cursor` alebo `AppData/Code`).

###  Adaptívna podpora prenosných editorov (USB Portable)
- **Automatická oprava písmena disku:** Cesty k prenosným verziám editorov sa ukladajú pomocou interného mapovania `[UUID...]`. Ak váš USB kľúč dostane na inom počítači iné písmeno jednotky (napríklad `F:` namiesto `E:`), VenvHub zmenu rozpozná a cesty automaticky opraví.

###  Plynulejší dizajn a reaktívna architektúra
- **Okamžité prepínanie ikon:** Vďaka novej Event-Driven architektúre a dynamickým témam (QSS) sa ikony editorov v tabuľkách a na MiniBare menia a prispôsobujú okamžite podľa svetlej/tmavej témy bez nutnosti klikania navyše.
- **Pevná mriežka Nastavení:** Záložka Nastavení dostala zjednotený Grid layout so zafixovanou šírkou textových popisov (185px) pre dokonale čistý a zarovnaný vzhľad.

---

## 🛠️ Opravy chýb a stabilita

###  Opravy používateľského rozhrania a zamŕzania
- **Odstránenie zasekávania ikon po spustení IDE:** Vyriešený kritický problém, pri ktorom sa ikona editora uzamkla vo vyrovnávacej pamäti Qt po prvom kliknutí. Zmena editora v nastaveniach teraz okamžite prekreslí ikony vo všetkých riadkoch.
- **Stabilizácia mriežky UI:** Odstránený vizuálny rozpad a posúvanie vstupných polí v Nastaveniach, ku ktorému dochádzalo pri preklade textov do iných jazykov.
- **Konzistentné zoznamy profilov:** Rozbaľovacie pole na výber profilu sa už nezasekáva na dátach z predchádzajúceho editora. Pri prepnutí IDE sa okamžite vyčistí a načíta správne profily.

###  Opravy systémovej logiky a profilov
- **Oprava ukladania profilov v Rýchlych nastaveniach:** Vyriešená chyba na MiniBare, kedy prepnutie aktívneho profilu pre Cursor nesprávne prepísalo predvolený profil pre VS Code.
- **Odstránenie duplicitného kopírovania:** Pri importe systémových dát sa prenos rozšírení spúšťal nežiaduco dvakrát za sebou. Problém bol odstránený a pribudla stabilizačná ochrana pre prípady, kedy používateľ nemá v systéme žiadne rozšírenia.

###  Komplexná lokalizácia a presnejšie hlásenia
- **Detailné chybové hlásenie pri štarte IDE:** Opravené nesprávne formátovanie dialógu. Ak zlyhá štart editora, okno už nezostane prázdne, ale presne vypíše technický dôvod chyby.
- **Vyčistenie hardcodovanej slovenčiny:** Z okna správy profilov boli odstránené natvrdo vpísané slovenské reťazce, ktoré nežiaduco prepisovali anglickú lokalizáciu pri prepnutí jazyka.
- **Doplnenie chýbajúcich prekladov (EN):** Do anglických slovníkov boli doplnené chýbajúce texty pre tooltipy multiskupín, placeholdery prenosných ciest, dialóg výberu `pip -e` balíčkov a popisky editorov. Zároveň bolo lokalizované chybové hlásenie pri páde čítania metadát balíčka.

---

## 📁 Dotknuté súbory

- `main.py`
- `core/_path.py`
- `core/logic/ide_detector.py`
- `core/logic/box/ide_settings.py`
- `core/logic/vs_code_json.py`
- `core/logic/vscode_user/start_vs_code_user.py`
- `core/logic/project_manager.py`
- `core/logic/commands/vscode_commands.py`
- `core/logic/commands/cursor_commands.py`
- `core/logic/vscode_user/profile_manager.py`
- `core/logic/vscode_user/system_sync.py`
- `windows/widget.py`
- `windows/manager.py`
- `windows/vscode_user.py`
- `windows/quick_settings.py`
- `translations/sk_SK.json`
- `translations/en_US.json`
- `ui/manager.ui`
- `ui/venv_actions.ui`

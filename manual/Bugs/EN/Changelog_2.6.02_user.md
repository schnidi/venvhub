# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.02  
*This release introduces autonomous IDE extension management for VS Code and Cursor AI with protection for manual installations, native .pth linking for 100% Pylance IntelliSense and nested imports, selective project settings cleanup via tracker, critical APT core fixes for dependency management, and instant interface language switching powered by CoreBridge.*

---

## 🚀 New Improvements

### 🧩 Autonomous IDE Extension Management (VS Code & Cursor AI)
- **Automatic installation from metadata:** When linking a local package that specifies IDE extensions (such as linters, formatters, or themes), VenvHub automatically and safely installs them into the active editor.
- **Strict profile isolation & Portable support:** Extensions are installed exclusively into the active profile's data folder (`.../data/extensions`), leaving your global system editor untouched. Portable installations of both VS Code and Cursor AI are fully supported.
- **Cross-Profile safeguard on launch:** Switching to a different profile in the MiniBar or creating a new profile and launching a project automatically triggers a background check that quietly installs any missing required extensions before the editor window opens.
- **Smart Autoremove with manual installation protection:** The system tracks extension ownership. Any extension installed manually inside the editor (`Ctrl + Shift + X`) is permanently protected and will never be deleted. When unlinking a package, only orphaned extensions no longer required by any other package are safely uninstalled.

### ⚡ Native `.pth` Linker & 100% Pylance IntelliSense
- **No more "Import could not be resolved" warnings:** Dynamic import hooks have been replaced with Python's standard `.pth` linking mechanism inside `site-packages`.
- **Full support for nested directory structures (`src.logic.*`):** Linked packages can now maintain real directory structures. Static language servers (Pylance, Pyright) immediately index the source tree and provide complete code completion (IntelliSense).
- **Zero-code migration:** When ready to finalize development, simply move the directory into the project root and uncheck the package in the Linker—no import statements need to be rewritten.

### ⚙️ Selective Settings Injection & Cleanup (`settings.json`)
- **Package-defined project settings:** Local packages can declaratively define editor settings in `local_meta.json` (such as linter rules, formatting preferences, or Cursor AI options).
- **Tracker-based cleanup:** VenvHub tracks every injected key via `venvhub_tracker.json`. Unlinking a package removes **only the keys added by that specific package**, leaving personal settings, fonts, color themes, and custom keybindings completely untouched.

### 🌐 Redesigned Language Subsystem via CoreBridge
- **Instant UI reactivity:** The language service now operates on a centralized `CoreBridge` architecture. Changing languages via Quick Settings updates all open dialogs instantly without requiring an application restart (including dynamic HTML version summaries in *About*).
- **New localization:** Added full Russian localization (`ru_RU`) alongside updated Slovak and English language packs.

---

## 🛠️ Bug Fixes & Stability

### 📦 APT Core & Dependency Management Fixes
- **Protected project dependencies against manual overwrites:** Fixed a critical bug where manually running a package installation for an existing extras dependency (e.g. `pip install pysocks` alongside `requests[socks]`) corrupted requirement tracking and wiped parent bindings from `venvhub_apt_state.json`.
- **Prevented duplicate explicit entries:** Packages defined in `requirements.txt` (directly or via extras) are no longer mistakenly tagged as manual user installations (`explicit`).
- **Skipped redundant installations:** Pre-install checks now properly detect packages already satisfied through extras, avoiding unnecessary pip subprocess executions.
- **Fixed typo in Autoremove:** Fixed a syntax typo in the exception handling block of the autoremove logic that could cause runtime crashes.

### 🖥️ IDE Integration & UI Stability
- **Silent CLI execution without flashing windows:** IDE extension installation and inspection commands on Windows now execute with `CREATE_NO_WINDOW`, eliminating flashing black console windows and GUI freezes.
- **Filtered temporary editor folders:** The extension scanner now ignores internal hidden editor directories starting with a period (`.uuid`).
- **Startup crash guard:** Added null-safety guards to prevent `AttributeError` crashes if localized strings are requested before the CoreBridge registry is fully initialized.
- **DEV version update evaluation:** Improved release version comparison logic so that transitioning from a development build to a stable release properly triggers update notifications.

---

## 📁 Affected Files

- `assets/about.json`
- `core/core_bridge.py`
- `core/core_states.py`
- `core/logic/button/manager/local_packages_linker.py`
- `core/logic/language_manager.py`
- `core/logic/sluzby/about_logic.py`
- `core/logic/sluzby/apt_ide_logic.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/github_update.py`
- `core/logic/sluzby/language/language_manager.py`
- `core/logic/vs_code_json.py`
- `core/logic/vscode_user/start_vs_code_user.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
- `windows/about_dialog.py`
# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.5.28  
*This document summarizes the architectural fix for path resolution in QSS themes, automatic URL quoting for installation directories containing spaces, improved icon loading stability, full integration of optional package dependency support (extras syntax `[extras]`), smart heuristic package extraction from direct URL/Git links, strict installation halting (Fail-Fast principle) on version errors within the APT system, and process console output encoding fixes (UTF-8 Mojibake fix) introduced in version 2.5.28.*

---

## 🚀 New Features & Improvements

### Universal Normalizer and Auto-Quoting of Paths in QSS Themes [v2.5.28]
- **Automatic Wrapping of URL References in `SkinManager`:** The stylesheet processing mechanism in `SkinManager.apply_skin()` now automatically enforces valid `url("...")` syntax with quotes when replacing the placeholder `{{CORE_THEMES_DIR}}`.
- **Theme Backward Compatibility:** All existing built-in and user-defined `.qss` themes remain fully compatible without requiring any manual editing of the source CSS/QSS files.

### Support for Optional Package Dependencies (`[extras]`) in APT Engine [v2.5.28]
- **Deep Inspection of `dist-info/METADATA`:** Extended `AptLogic` class capabilities to directly read the `Requires-Dist` field from `METADATA` files in `site-packages`. The system now reliably tracks relationships of packages installed via extras syntax (e.g., `requests[socks]` -> `pysocks`), which standard `pip show` / `uv pip show` commands omit from the `Requires:` field.
- **Full Compatibility with UV and Pip Installers:** Dynamic integration of optional dependencies into the global dependency graph without impacting regular package inspection performance.

### Smart Package Extraction from Direct URLs and Git Repositories [v2.5.28]
- **Fallback Heuristics in `RequirementsParser`:** Added a robust fallback mechanism to parse package names directly from clean URL endpoints, archives (`.tar.gz`, `.whl`, `.zip`), and Git repositories without requiring an explicit `#egg=...` fragment.
- **Support for Versioned and Branched URLs:** The parser automatically isolates the clean package name while correctly stripping Git branches (`@main`, `@v1.0.0`), commit hashes, and PEP 440 version strings.

---

## 🐛 Bug Fixes & Stability

### Fix for Icon Loading Failure in Installed Environments (NSIS / Program Files) [v2.5.28]
- **Critical Fix for Dynamic Icon Outages:** Resolved a bug where the Qt CSS parser discarded `qproperty-icon: url(...)` rules whenever the application was installed in a path containing spaces (typically `C:\Program Files\VenvHub Pro\...`).
- **CSS Tokenizer Crash Protection:** Implemented regular expression normalization in `core/logic/skin_manager.py`, ensuring a valid path format for Qt stylesheets across all runtime environments (development `python main.py`, portable mode, and standard NSIS installation).

### Fix for False Orphan Detection and Self-Healing with Extras Packages [v2.5.28]
- **Prevention of False Explicit Flags:** The Self-Healing mechanism no longer misidentifies packages pulled via `[extras]` as unknown manual installations and avoids writing them incorrectly into `venvhub_apt_state.json`.
- **Automatic Cleanup of Explicit State during Uninstallation:** Added released dependency tree cleanup (`released_tree`) in `AptLogic.autoremove()`, ensuring sub-dependencies are pruned from `state_explicit` if they were captured by mistake in earlier runs.
- **Robust Metadata Parsing:** Eliminated issues caused by splitting `.dist-info` directory names containing hyphens and version strings by directly reading the `Name:` header from `METADATA`.

### Fix for False Explicit Flagging of Direct URL and Git Packages [v2.5.28]
- **Resolved Parser Failures on Clean URLs:** Fixed an issue where packages installed from URL archives or Git repositories without `#egg=` returned `None` from the parser. Consequently, Self-Healing previously treated them as manual terminal installations and refused to uninstall them when removed from `requirements.txt`.

### Fix for Installer Error State Evaluation & Prevention of Unwanted Fallbacks (Fail-Fast) [v2.5.28]
- **Signal Capture Fix in `AptListener`:** Resolved a bug in the `apt_callback` where the default parameter `result=0` caused an evaluation of `success = True` even when the installer process failed (e.g., on a non-existent package version like `requests===3.0`).
- **Protection Against Arbitrary Downloads:** On installer failure (UV/Pip), APT synchronization is aborted immediately, and the system no longer attempts to bypass solver errors by installing unconstrained root packages.
- **Localization of Error Outputs:** All system messages in `AptListener` have been integrated into `LanguageManager` and added to language resource files (`sk_SK.json`, `en_US.json`).

### Process Output Encoding Fix in Log Console (UTF-8 Mojibake Fix) [v2.5.28]
- **Proper Unicode Symbol Decoding in `PipManager`:** Added parameters `encoding="utf-8"` and `errors="replace"` to `subprocess.Popen` invocations across `PipWorker` and `UpdateAllWorker` classes.
- **Elimination of Corrupted Characters:** Fixed broken rendering of dependency trees and formatting symbols output by UV (e.g., displaying `×`, `╰─`, `▶` instead of corrupted strings such as `Ă—`, `â•°â”€â–¶`).

---

## 🧪 Test Scenarios & Verification (QA)

### Scenario 1: Verification of Optional Dependencies (`[extras]`)
1. **Installation:**
   - Add `requests[socks]` to `requirements.txt`.
   - Run the installation via the *Requirements / Install* button.
   - **Expected Result:** `requests`, `pysocks`, and base dependencies are installed. In `venvhub_apt_state.json`, `"requirements_cache"` contains `["requests"]` and `"explicit"` **does not** contain `pysocks` (it is correctly identified as an automatic dependency).
2. **Uninstallation:**
   - Comment out or remove `requests[socks]` from `requirements.txt`.
   - Run synchronization via the *Requirements* button.
   - **Expected Result:** The log outputs `Removed from files: requests` and the `Autoremove: Removing orphan dependencies:` step cleanly uninstalls **all related packages including `pysocks`**.

### Scenario 2: Verification of Direct URL and Git Repositories (without `#egg=`)
1. **Installation from URL / Git:**
   - Add a clean URL or Git repository link to `requirements.txt`, for example:
     - `https://files.pythonhosted.org/packages/source/e/emoji/emoji-2.2.0.tar.gz`
     - or `git+https://github.com/carpedm20/emoji.git`
   - Run the installation via *Requirements*.
   - **Expected Result:** The package is installed successfully. In `venvhub_apt_state.json`, `"requirements_cache"` lists `["emoji"]`, and Self-Healing does not flag `emoji` in `"explicit"`.
2. **Uninstallation upon Removal from File:**
   - Comment out or delete the URL link from `requirements.txt`.
   - Run synchronization via *Requirements*.
   - **Expected Result:** The log outputs `Removed from files: emoji` and `Autoremove` automatically and cleanly removes the `emoji` package.

### Scenario 3: Verification of Response to Non-Existent / Invalid Version (Fail-Fast)
1. **Specifying an Invalid Version:**
   - Add a non-existent package version to `requirements.txt`, e.g.: `requests===3.0`.
   - Run the installation via the *Requirements / Install* button.
   - **Expected Result:**
     - UV/Pip outputs an error (`No solution found / No matching distribution`).
     - APT outputs: `⚠️ [APT] Operation failed — APT state remains unchanged.`
     - **The process terminates immediately.** No fallback/latest versions are installed, and the virtual environment remains in its original, clean state.

### Scenario 4: Verification of Error Output Readability in Log (UTF-8 Encoding)
1. **Triggering Error Output from UV:**
   - Insert an unsatisfiable requirement into `requirements.txt` (e.g., `requests==3.0`).
   - Run the installation via *Requirements*.
   - **Expected Result:**
     - The console log displays the output with proper Unicode tree characters:
       ```text
       × No solution found when resolving dependencies:
       ╰─▶ Because there is no version of requests==3.0 and you require
           requests==3.0, we can conclude that your requirements are unsatisfiable.
       ```
     - The output contains **no corrupted mojibake characters** (such as `Ă—` or `â•°â”€â–¶`).

---

## 📁 Modified & Affected Files

- `core/logic/skin_manager.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/apt_listener.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
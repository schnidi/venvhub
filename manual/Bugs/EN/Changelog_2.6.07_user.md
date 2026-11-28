# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.07  
*This release introduces the brand new interactive Dependency Tree window with in-depth package inspection, export to the modern pyproject.toml configuration standard preserving Git and URL sources, smart nested extras tracking (eliminating false orphans), blazing-fast non-blocking environment autoremove, and complete multiplatform requirement support (PEP 508).*

---

## 🚀 New Features & Enhancements

### 1. New Interactive Window: Dependency Tree (`Venv Tree`)
- **Origin and Ownership-Based View:** Instead of an unorganized package list, the application offers a modern tree view that clearly groups entries by their actual source:
  - 📁 **Local Linker Modules** (modules developed by you directly in the Linker),
  - 📁 **Editable Projects (`pip -e`)** (with a direct filesystem path to the repository),
  - 📁 **Project Requirements (`requirements.txt`)**,
  - 📁 **Manually Installed Packages**,
  - 📁 **Environment System Packages** (isolated environment core),
  - 📁 **True Orphans** (packages no longer required by any component, ready for cleanup).
- **Detailed Package Inspector (Side Panel):** A single click on any package reveals a comprehensive breakdown:
  - Which components keep the package alive in the environment (including shared multi-ownership),
  - Which packages depend on it directly and which are bound via optional `[extras]`,
  - Package description, license, homepage URL, and exact installation path on disk.
- **Instant Search & Category Filters:** As you type into the search box, the tree filters in real time and automatically expands relevant branches. Quick category toggles with item counters are also available.
- **On-the-Fly Language Switching:** The tree window reacts instantly to language changes in the application Settings – all labels, headers, and inspector cards retranslate immediately without reopening the window or restarting the application.

### 2. Export to `pyproject.toml` Standard with Git Reference Support
- **Modern Project Exporter (PEP 621):** The top toolbar features a new **`📄 Export to TOML`** button to generate a clean, standardized project configuration file.
- **Interactive Checkbox Selection:** Select which packages to include in the export directly inside the tree. Manually installed packages are checked by default, while automatic sub-dependencies remain unchecked, keeping your `pyproject.toml` lean and free of unnecessary clutter.
- **Direct Git & Web Source Preservation (PEP 610):** For packages installed directly from GitHub or private Git repositories, the exporter preserves full URLs rather than plain package names (e.g., `"package @ git+https://github.com/..."`).

### 3. Smart Nested Extras Resolution (No More False Orphans)
- **Deep Recursive Package Analysis:** Previously, extras flags `[extras]` were only resolved from the root requirements file. The updated core inspects extras requirements deep within the dependency graph.
- **Flawless Resolution for Modern Libraries:** Libraries such as `google-generativeai` and their sub-dependencies (e.g., `grpcio-status`) are no longer erroneously flagged as orphans. Each package is properly mapped to its declaring parent.

### 4. High-Speed Non-Blocking Autoremove
- **Timeout Elimination:** Removed the legacy 60-second timeout during uninstall routines, which previously caused unnecessary delays on larger packages.
- **Process Deadlock Prevention:** Uninstallation subprocesses now enforce a closed input stream (`stdin=DEVNULL`), preventing the process from hanging on interactive prompts and keeping the UI responsive.

### 5. Full PEP 508 Environment Marker Support in `requirements.txt`
- **Automatic Target Platform Evaluation:** VenvHub now evaluates semicolon markers (such as `colorama; sys_platform == 'win32'` or `uvloop; sys_platform == 'linux'`). If your requirements contain specifications for a different OS or Python version, VenvHub detects and safely skips them.
- **Clean State Without False Mismatches:** Packages meant for other platforms no longer cause install failures or false "missing package" flags. Developing the same project across Windows, Linux, or macOS is now completely seamless.

---

## 🛠️ Bug Fixes & Stability

### Dependency Management & UI Fixes
- **Fixed Crash During Editable Package Installation (`pip -e`):** Resolved a critical `AttributeError: type object 'AptLogic' has no attribute 'CORE_TOOLS'` exception occurring during editable package dependency binding. System package filtering is now fully aligned with environment state management via `AptLogic.ensure_system_packages()`.
- **Fixed Crash Opening Manager (`IndexError` in UI Loader):** Removed an orphaned empty layout `<item row="5" column="2">` in `manager.ui` that caused `uic.loadUi` to fail with `IndexError: child index out of range` when launching the Master Manager window from the mini widget.
- **Fixed False Mismatches on Multiplatform Requirements:** Resolved an issue where VenvHub on Windows repeatedly reported missing packages and state discrepancies when `requirements.txt` contained libraries intended exclusively for Linux or macOS.
- **Fixed False Orphans on System Packages:** Environment core tools (`virtualenv`, `packaging`, `pip`) will no longer appear duplicated inside the orphan packages list.
- **Fixed TOML Export Crash:** Fixed an `AttributeError` exception that triggered a window crash when generating the `pyproject.toml` file.
- **Fixed Crash on Language Change:** Resolved a `TypeError` that occurred when switching language locales while the Dependency Tree window was open.
- **Consistent Encoding on Windows:** Package removal subprocesses now consistently use UTF-8 encoding with fallback error replacement.

---

## 📁 Affected Files (Summary of Changes)

- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/venv/editable_service.py`
- `core/logic/sluzby/apt_state.py`
- `core/logic/sluzby/system/python_detector.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/packages/req_toml.py`
- `core/logic/sluzby/venv/pack_tree.py`
- `windows/manager.py`
- `windows/venv_tree_window.py`
- `resources/ui/manager.ui`
- `resources/translations/sk_SK.json`
- `resources/translations/en_US.json`
- `resources/translations/ru_RU.json`
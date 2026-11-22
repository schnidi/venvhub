# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.06  
*This version introduces a clear visual dependency tree in the log, smart protection against breaking local modules in the Linker, seamless two-phase installation of editable packages (including requirements.txt and optional [extras]), fixes for application crashes when working with dialogs, and overall translation unification.*

---

## 🚀 New Features and Improvements

### 1. Visual Dependency Tree and Detailed Package Inspection
- **Structured Dependency X-Ray:** When installing packages with optional extras (e.g., `requests[socks]`), instead of cluttered technical outputs, the system renders a clear branched tree of parent and child packages directly in the log.
- **Exact Match Card (1:1 Skip):** If the requested package already exists on disk and meets the version specification, VenvHub displays a clean summary card (package name, version on disk, requirement) and safely skips the installation instantly without straining the network.
- **Pre-installation Inspection of Local Packages (`pip -e`):** Before starting the installation, the system analyzes the project's configuration files and informs you in advance which dependencies are already in the environment, which are missing, and which will require a version change.

### 2. Safer Linker with Smart Dependency STOP
- **Protection Against Accidental Project Breakage:** If you attempt to unlink a local module on which another active module strictly depends (e.g., unlinking a logger required by your application core), the Linker will stop the operation in time.
- **Automatic State Rollback:** When the operation is stopped, the checkbox automatically reverts to its original checked state, ensuring the interface always accurately reflects the actual state on disk.
- **Clean Unlinking:** When unlinking modules, the system runs a targeted 3-step process (removing links, safely uninstalling orphaned dependencies, and cleaning up the VS Code configuration).

### 3. Reliable Support for Editable Projects (`requirements.txt` and `pip -e`)
- **Flawless Handling of [extras] Extensions:** Fixed errors when parsing square brackets in dependency lists. Packages like `requests[socks]` are now read and installed correctly on the first try.
- **Two-Phase Installation:** The local development project itself is linked without unnecessary downloading, and in the second step, the installer safely pulls all of its actual sub-dependencies (including deep dependencies). The final environment integrity check thus completes 100% conflict-free.
- **Smart Automatic Cleanup (Autoremove):** If you delete an unnecessary dependency directly in the project's configuration file (`requirements.txt`), the system will detect the change during the next synchronization and automatically and safely uninstall the released packages.

---

## 🛠️ Bug Fixes and Stability

### Interface, Process, and Dialog Stability
- **Fixed Critical Crash on Warning Dialogs:** Resolved a thread-level bug that caused the entire application to crash when displaying a warning dialog in the Local Packages window.
- **No More Cryptic `{0}` Messages:** Fixed a formatting error in Linker error dialogs. Instead of a raw template, a clear and specific explanation of the problem is now always displayed.
- **Removal of Duplicate Log Entries:** Removed repeated installation status outputs, making the console cleaner and easier to read.
- **New Unified Bridge for Dialogs and Progress Indicators:** Creating venvs, deleting, cloning, as well as Portability Guard now use a unified system of frameless windows and dialogs with built-in startup diagnostics.
- **Translation Unification:** Cleaned up internal translations – removed mixed English terms from Slovak texts and added missing localization strings for all dialogs and states.

---

## 📁 Affected Files (Overview of Changes)

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
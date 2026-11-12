# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.04  
*This version brings significant speed and stability improvements by moving heavy tasks to the background, intelligent protection of system venvs when moving to USB drives, smooth local package linking with detailed live logs, and a new level of security for managing development packages without the risk of project corruption.*

---

## 🚀 New Features and Improvements

### 1. Reliable Protection of Portable Environments on USB (Portability Guard)
- **Clear warnings instead of crashes:** If you attempt to open a terminal, launch an IDE (VS Code, Cursor), clone an environment, or open package management on another computer where the original system Python does not exist, VenvHub safely halts the action and clearly explains the reason.
- **Prevention of path corruption on USB:** System venvs on portable drives are protected against accidental overwriting of internal configuration paths, ensuring they work flawlessly upon returning to the original computer.

### 2. Smooth Local Package Manager (Non-freezing Linker)
- **Background processing:** Module linking, saving, and dependency installation no longer block the graphical interface. The entire process runs asynchronously and the window remains fully responsive.
- **Detailed live logging (In-time logging):** During package linking, you can see the exact step-by-step progress directly in the window:
  - Searching for local and external dependencies,
  - Live output of the package installer (`pip` / `uv`),
  - Writing `.pth` link files and editor configurations,
  - Automatic cleanup of libraries that are no longer needed after link changes.
- **Safe control locking:** During the writing of changes, buttons and options in the window are temporarily locked to prevent unwanted collisions.

### 3. New Level of Development Package Management (`pip install -e`)
- **Intelligent folder check before installation:** When adding an editable package from disk, VenvHub immediately verifies the presence of configuration files (`pyproject.toml` or `setup.py`). If the folder does not contain a valid Python project, it warns you in time and prevents unnecessary installation.
- **Cross-protection against project requirements (`requirements.txt`):** The system recognizes whether the installed package is part of the core project requirements or an independent development module, and sets its tracking accordingly.
- **Bulletproof uninstallation protection (APT Guard):** VenvHub prevents accidental uninstallation of packages upon which your project or local Linker depends.
- **Automatic orphan cleanup:** After uninstalling an unneeded development package, the system automatically detects and safely removes libraries brought in by that package which are no longer needed by any other package.
- **Modern graphical dialogs:** Old system dialogs have been replaced with a modern `CustomMessageBox` design with immediate support for language translations.

### 4. Robust Package Installation and Updates
- **Intelligent skipping of existing packages (STATUS 1:1):** If the requested package in a given version already exists in the environment, the installer does not reinstall it, significantly saving time and data.
- **Preservation of bindings during updates:** If you manually update a package tied to a local development module or editable project, the system keeps it linked and does not mark it as a standalone foreign package.
- **Unified behavior across the application:** Installation via the Pip Manager right panel, Venvs Management bottom panel, and Quick Settings all utilize the same secure core protected by a state system.

---

## 🛠️ Bug Fixes and Stability

- **Elimination of freezing and faster responses:** Removed blocking operations in the main thread when manipulating local packages and editable projects.
- **Fix for main window installation failure:** Fixed a bug that in certain cases prevented the execution of package installation directly from the *Venvs Management* tab or the *Quick Settings* window.
- **Removal of internal circular dependencies:** Resolved internal looping between the application core and graphical dialogs during environment portability checks, ensuring a reliable and clean system start.
- **Fix for warning displays on unsupported hardware:** Dialog boxes warning about portable venv blocking now display reliably, with correct language translation and centering over the active window.
- **Stability when uninstalling protected libraries:** Attempting to uninstall a library protected by the project no longer causes a crash or console traceback, but correctly returns a clear security message in a dialog box.

---

## 📁 Affected Files (Overview of Changes)

- `core/core_states.py`
- `core/core_bridge.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/venv/pack_inst_unis.py`
- `core/logic/sluzby/venv/editable_service.py`
- `core/logic/sluzby/venv/linker_service.py`
- `core/logic/sluzby/portability/portability_guard.py`
- `core/logic/button/manager/actions.py`
- `core/logic/button/manager/clone.py`
- `core/logic/button/manager/create.py`
- `core/logic/button/pip/freeze.py`
- `core/logic/containers/button/autostart_actions.py`
- `core/logic/path_logic/portable.py`
- `core/logic/vscode_user/start_vs_code_user.py`
- `windows/manager.py`
- `windows/quick_settings.py`
- `windows/pip_package_widget.py`
- `windows/pip_e_window.py`
- `windows/local_packages_window.py`
- `windows/custom_message_box.py`
- `core/logic/system_listener.py` *(removed)*
- `core/logic/button/manager/local_packages_linker.py` *(replaced by new service)*
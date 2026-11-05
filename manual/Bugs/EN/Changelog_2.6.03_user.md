# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.03  
*This version brings a complete overhaul of project dependency management and manual installations via the central APT core, intelligent bulk package updates with protection for your code and requirements, universal environment integrity checks for both Pip and UV, and immediate system stability fixes.*

---

## 🚀 New Features and Improvements

### 1. Intelligent Requirements & Manual Installation (`requirements.txt`)
- **End of Blind Downloading (Brute-Force Chunking):** Installing `requirements.txt` no longer downloads all 30 packages in endless loops. The system performs a smart DIFF analysis against the disk before every step.
- **Installing Only What is Missing:** The installer (`pip` / `uv`) will now exclusively process **packages that are genuinely missing** from the environment or do not match the required version.
- **Protection Against Redundant Reinstalls on Manual Input:** If you manually input a package that is already present in the venv, the system immediately skips the installation.

### 2. Advanced Version Verification Logic (Upgrade / Downgrade)
- **Version Tracking (PEP 440 / PEP 508):** The APT core now lightning-fast checks versions directly from disk metadata (`*.dist-info`).
- **Automatic Mismatch Correction:** If an older version of a package is present in your environment (e.g., `0.4.0`) and `requirements.txt` (or manual input) requests a different one (e.g., `0.4.6` or lower), the system detects the mismatch and automatically triggers a targeted **Upgrade** or **Downgrade**.

### 3. Intelligent Bulk Updates (`Update All`)
- **Safe Bulk Upgrades:** The button for updating all outdated packages has been completely redesigned into the modern `PackageUpdateService`.
- **Pre-download Protection Filters:** 
  - **`requirements.txt` Protection:** If a version is strictly limited in your requirements (e.g., `Django==3.2`), the update will not alter it.
  - **Linker Protection:** Packages bound to local development modules are securely protected.
  - **Editable Packages Protection (`pip -e`):** The system automatically excludes them from bulk upgrades.
- **Automatic Cleanup (Autoremove):** If you delete a package from `requirements.txt` in the meantime, the cleanup process automatically triggers after the update to remove any orphaned dependencies.

### 4. Universal Environment Integrity Check (Pip & UV)
- **Generalized `pip check` / `uv pip check`:** After every installation or update (regardless of whether you use classical `pip` or lightning-fast `uv`), the system checks in real-time whether any dependency conflicts have arisen in the environment.
- **Clear Notifications:** The log will immediately inform you whether all dependencies are 100% compatible.

---

## 🛠️ Bug Fixes & Stability

### Package Management & Core Fixes
- **Critical Crash Fix on Bulk Update:** Fixed a context-loss error (`AttributeError`) that caused the app to crash when clicking the Update button.
- **Installation Unpacking Fix (`ValueError`):** Fixed a defect in the listener that incorrectly handled data from the new requirements spec parser.
- **CoreBridge & Translation Stability:** Fixed a missing state import on application startup and added missing translations for Slovak, English, and Russian interfaces.
- **Clean Console:** Removed annoying and false Qt framework warnings from the system terminal.

---

## 📁 Affected Files (Overview of Changes)

- `core/core_bridge.py`
- `core/logic/pip_manager.py`
- `core/logic/system_listener.py`
- `core/logic/button/pip/pip_command_worker.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `core/logic/sluzby/venv/package_update.py`
- `windows/manager.py`
- `windows/pip_manager_window.py`
- `translations/en_US.json`
- `translations/ru_RU.json`
- `translations/sk_SK.json`
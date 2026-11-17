# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.05  
*This release introduces next-generation detection for system Python interpreters and the UV tool, freeze protection during application startup and installations, a critical crash fix during virtual environment cloning, and overall performance improvements for local package management.*

---

## 🚀 New Features and Improvements

### 1. Next-Generation Python Interpreter Detection
- **Deep and Reliable System Scanning:** The detection mechanism has been rewritten from the ground up. In addition to the standard Windows launcher (`py`), the application thoroughly scans the `%LOCALAPPDATA%\Programs\Python` and `Program Files` directories.
- **Startup Freeze Protection (Timeout Guard):** The application will no longer freeze if the system encounters slow, disconnected, or network drives. The detection includes a 5-second safety timeout, ensuring VenvHub Pro always launches reliably and quickly.
- **Duplicate Link Elimination:** Canonical path resolution ensures that duplicate interpreters caused by shortcuts and symlinks do not clutter the list.

### 2. Intelligent Detection and Safe Usage of the UV Tool
- **Multi-tier UV Binary Lookup:** The detector checks for the presence of UV in a strict, logical hierarchy:
  1. *Bundled directly within the app* (`uv.exe` in the VenvHub root).
  2. *In the active virtual environment* (in the `Scripts` directory or directly alongside Python).
  3. *In user installations* (in `%LOCALAPPDATA%\bin` from the official installer or in `%USERPROFILE%\.cargo\bin`).
  4. *In the system PATH environment variable*.
- **Functional Verification:** The system does not merely check for the file's presence on disk; it silently validates its execution in the background (`--version`). If the binary is corrupted, it will not be used.
- **Settings Fallback Protection:** If you switch the package manager from Pip to UV in the settings and the UV tool is not available on your system, the application alerts you immediately and safely reverts the selection to Pip to prevent dependency installation failures.

### 3. Smooth, Responsive UI and Clear Statuses
- **No More "Application Not Responding" Prompts:** PIP installation and Python version processing now run in optimized background threads. The user interface remains completely responsive throughout the process.
- **Clear PIP Verification:** In the *Local Python* tab, the system verifies the PIP status for each interpreter in real time. You can instantly see whether a check is in progress (⏳), ready (✅), or missing from the package.
- **Smoother Deletion and Addition of Runtime Packages:** Working with portable (Embed) Python versions now features a clear progress indicator without window lockups.

---

## 🛠️ Bug Fixes and Stability

### Virtual Environment and Core Application Fixes
- **Critical Environment Cloning Crash Fix:** Resolved an issue in the cloning module (`clone.py`) that caused the entire application to crash when attempting to clone an existing virtual environment.
- **App Startup Initialization Fix:** Fixed a bug during core startup and language translation loading that could prevent the main window from opening under certain circumstances.
- **Faster Startup with Lazy-Loading:** Python and UV detectors are now initialized only when actually needed, significantly speeding up application startup and conserving system resources.

---

## 📁 Affected Files (Changelog Overview)

- `main.py`
- `core/core_bridge.py`
- `core/core_states.py`
- `core/logic/sluzby/system/python_detector.py`
- `core/logic/sluzby/venv/uv_detector.py`
- `core/logic/button/manager/clone.py`
- `core/logic/button/manager/create.py`
- `core/logic/commands/uv_commands.py`
- `core/logic/project_manager.py`
- `core/logic/python_installer/button/pip_installer.py`
- `core/logic/python_installer/button/python_install.py`
- `windows/manager.py`
- `windows/python_ver.py`
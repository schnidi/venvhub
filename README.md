# 🚀 VenvHub Pro
## Ultimate Python Environment Manager & Orchestrator for Windows

### 📝 Overview
VenvHub Pro is a comprehensive, IDE-agnostic management tool for Python developers. It solves real-world problems like dependency hell, project portability, microservice orchestration, and .exe packaging—replacing multiple tools with one smooth, asynchronous, responsive application.

**Version:** v2.6.00  
**Developer:** Ing. Viliam Schneider  
**Partner / Deployed at:** Seal and Lube, spol. s r.o.

---

## Screenshot

![VenvHub widget](assets/pictures/widget.jpg)


![VenvHub quick setup](assets/pictures/quick_setup.jpg)


![VenvHub Manager](assets/pictures/manager.jpg)


---

### ✨ Key Features

#### 📦 APT-Style Package Manager & State-Aware Orchestration
Forget messy virtual environments. VenvHub introduces an action-triggered, state-aware reconciliation engine inspired by Linux's `apt-get autoremove`. It maintains a hidden state file (`venvhub_apt_state.json`) inside your Venv to track exactly what you installed explicitly versus what was pulled in as a dependency.

* **GUI Action Interceptor:** When you install or uninstall packages directly through the VenvHub GUI, a background `AptListener` intercepts the command, updates the explicit state, and immediately triggers an `autoremove` to clean up any orphaned dependencies left behind by uninstalled packages.
* **External CLI Self-Healing:** What if you open a terminal outside VenvHub and manually type `pip install requests`? VenvHub doesn't break. The next time you trigger an APT-aware action in the GUI (like an update or sync), VenvHub performs a differential scan. It detects the manually installed package, realizes it's not an orphan, safely registers it to the "explicit" list (Self-Healing), and continues working flawlessly.
* **Requirements.txt Differential Sync:** Synchronization is an on-demand action, not a real-time background task. If you delete or comment out a line in your `requirements.txt`, you simply click the "Sync/Install Requirements" button in VenvHub. The engine calculates a "diff" against its last known cached state, installs any new additions, and safely triggers an `autoremove` on the packages (and their sub-dependencies) that fell out of the file.
* **Path Auto-Correction:** Before executing any Pip installer logic from a requirements file, the parser detects and automatically fixes broken Windows backslashes (`\`) inside `-e` (editable) local paths to prevent terminal crashes.

#### 🤖 Dual-IDE Integration (VS Code & Cursor AI)
Native and simultaneous support for both Visual Studio Code and **Cursor AI**. VenvHub dynamically synchronizes Python interpreter paths, local package paths, tasks, and keybindings into both `.vscode` and `.cursor` workspaces without conflicts.

#### 📁 Environment Separation Architecture
Physically separates your source code from your virtual environments. Projects stay clean while all Venvs are centrally managed in a dedicated "Venv Hub" folder. You can safely delete a Venv anytime without touching your code.

#### 🚀 Mini-Bar & Quick Settings
A floating toolbar that provides maximum control in minimal screen space. Quickly switch projects, environments, launch scripts, and change languages or themes—without ever opening the main Manager window.

#### 🔄 Container & Autostart (Venv Orchestrator)
Group Venvs (e.g., Frontend, Backend, Database) into "Containers." VenvHub launches them in a precise order:
* **8-Way Sequence Engine:** Combine time delays, signal Anchors (Hooks), and auto-restarts.
* **Signal Anchors (Hooks):** *Note: To use the "Anchor" wait feature, you must insert a small snippet into your target Python script that sends a ready signal back to VenvHub once the program successfully loads.*
* **Live RAM Monitor:** Tracks and displays the memory usage of running containers in real-time.
* **Intelligent Watchdog:** Monitors PIDs in the background. If a process crashes, it can intelligently respawn it (up to 3 times before applying a fatal block).

#### 🛠 PyInstaller Builder with Auto-Injector
A visual tool for creating `.exe` files. Not only does it generate a "Birth Certificate" (JSON metadata about the Python version and packages) and bundle the lightning-fast `uv.exe` installer, but its **Auto-Injector** also detects which VenvHub Local Packages your project uses and dynamically injects their source code and assets into the build (via `--paths` and `--add-data`).

#### 🔗 Deep-Injection Local Packages (The VenvHub Linker)
Sharing custom code across projects is no longer just about editing Python paths. VenvHub’s Linker is a comprehensive Dependency and Configuration Injection system.

* **UAC-Free `sys.meta_path` Linking:** Instead of relying on fragile Windows NTFS Symlinks or Junctions (which often trigger UAC Admin prompts), VenvHub injects a custom `venvhub_bootstrap.py` directly into the Venv's `site-packages`. This hooks into Python's `sys.meta_path`, dynamically routing imports to your shared code folder.
* **Recursive Payload & PIP Injection:** The Linker reads a `local_meta.json` file inside your shared package. If your local package requires external PIP packages (e.g., `requests`), the Linker automatically downloads and installs them into the active Venv. It also recursively resolves and links any other local packages required.
* **IDE Workspace Injection:** The Linker doesn't just inject Python paths into `.vscode/settings.json` for IntelliSense (Pylance). It safely injects custom VS Code `tasks` and `keybindings` directly into your project's workspace using a receipt-tracking system (`venvhub_tracker.json`), ensuring your manual workspace settings are never overwritten.
* **APT-Logic Protection:** The APT-style package manager is fully aware of the Linker. If a linked local package brings in a PIP dependency, the APT logic acts as a shield and strictly **blocks** you from accidentally uninstalling that PIP package via the GUI.
* **Triggered Autoremove:** When you unlink a local package from your project, the background `AptListener` intercepts the action, realizes the associated PIP dependencies are no longer needed, and automatically triggers an `autoremove` to purge them from the Venv.
* **PyInstaller Auto-Readiness:** When compiling your project, the PyInstaller Builder automatically reads the Linker state and dynamically injects `--paths` (for code) and `--add-data` (for UI files/assets) for every linked package, ensuring your `.exe` compiles flawlessly without manual path configuration.

#### 🔗 Editable Installs (`pip -e`)
Share your custom code and libraries across multiple projects without constantly copying them:
* **Editable Packages Manager:** A dedicated UI for managing `pip install -e` projects, fully protected by the APT logic (preventing accidental uninstallation of shared core libraries).

#### 🧳 Portable Mode & Hardware Locking (Security)
Working from a USB drive? VenvHub tracks drives using exact **Volume UUIDs**, so it doesn't get confused if Windows assigns a different drive letter.
* **Machine ID Lock:** If you plug your USB drive into a different PC, VenvHub calculates a SHA-256 hardware hash. For security reasons, it *blocks* the execution of System Venvs (preventing critical C-library and absolute path crashes on the foreign PC), while allowing pure Embed Venvs to run anywhere.

#### 💻 Isolated IDE User Profiles
Each profile has its own extensions, settings, and keybindings. Ideal for teamwork or switching between different types of projects. Profiles are fully portable on your USB drive, and with just one click, you can import your current Windows system settings (`%APPDATA%`) directly into a portable profile.

#### 🐍 Local Embeddable Runtimes
Download "Local" Python versions from official ZIP archives directly via the UI. VenvHub automatically "hacks" and fixes them (installs Pip, unlocks `site-packages` in the `._pth` file) so they behave like full installations—without ever touching your Windows Registry.

#### 🎨 Frameless UI & Dual-Theme System
A beautiful, modern user interface without classic Windows borders (custom title bar), featuring a responsive 3-zone Drag & Drop table system. It runs on a robust Compatibility Bridge supporting both PyQt6 and PySide6. You can even let AI recolor your QSS skins and import them with a single click.

#### 🛡️ Secure Execution & Background Services
* **Smart WinAdmin (UAC):** The system only requests Administrator privileges exactly when needed (e.g., writing to protected system folders like `C:\Program Files`) and streams live progress back to the UI.
* **GitHub Auto-Updater:** A silent background thread checks the GitHub API for new releases and notifies you with a title bar icon if an update is available.

---

### 📚 Full Documentation
This README provides an overview. The complete user manual is included directly in the application as offline HTML help files (within the `manual/` directory) for immediate access, covering:
*   Installation & First Run
*   Mini-Bar & Quick Settings
*   Environment Manager
*   Pip Package Manager
*   Multi-Run (Batch Launching)
*   PyInstaller Builder
*   Settings & Themes
*   Local Python Runtimes
*   Container & Autostart
*   Local Packages (Linker)
*   Editable Packages (pip -e)
*   VS Code User Profiles
*   VS Code Integration
*   Architecture & Compilation


---

### 🔧 Installation

#### Classic Windows Installer
*   Standard installation (e.g., `C:\Program Files\VenvHubPro`)
*   Data stored in `%APPDATA%\VenvHubPro\`
*   Per-user settings and themes

#### Portable Version
*   Extract to any folder (including USB drives) 
*   All data stored alongside the executable
*   Recognized by presence of `_is_portable.ini` marker file
*   Auto-corrects drive letter changes

---

### 🏗️ Architecture

#### Dual-Framework Bridge
Written for PyQt6 but includes a Compatibility Bridge (`pyqt_to_pyside.py`) using `MetaPathFinder` . If the environment has PySide6, the bridge silently intercepts all PyQt6 imports and redirects them to PySide6 at runtime.

#### Self-Replication (Dogfooding)
VenvHub Pro can compile itself using its own PyInstaller Builder . This guarantees the builder is production-ready and capable of packaging even complex applications.

#### Build Process
*   UI files (`*.ui`) are loaded dynamically 
*   PyInstaller builds with either PyQt6 or PySide6 (hidden imports needed for PySide6) 
*   NSIS installer script wraps the built `dist/VenvHubPro` folder

---

### 📬 Contact / Kontakt
*   **Bug Reports & Feature Requests:** Please open an Issue right here on GitHub.
*   **Business Inquiries & Collaboration:** Please visit my [GitHub Profile](https://github.com/schnidi) where you can find my verified contact details.

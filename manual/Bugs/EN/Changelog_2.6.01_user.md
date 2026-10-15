# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.01  
*This release represents a massive leap in application stability, intelligence, and speed. It focuses on perfectly protecting your virtual environment from accidental breakage, smoothing out the user interface (no more freezing), and safely installing huge projects. The application now has a much better "understanding" of relationships between packages and will never crash if you accidentally close a window mid-task.*

---

## 🚀 New Features & Improvements

### ✨ Intelligent Environment Shield (Breakage Protection)
- **What changed:** The application now monitors what you're trying to do in real-time. If you try to manually uninstall a package that is critical to your project (e.g., it is hardcoded in `requirements.txt` or strictly required by another installed library), the system will immediately stop you and display a warning.
- **Benefit:** You will no longer accidentally delete core project components. Your environment will always remain functional and consistent.

### ✨ Lightning-Fast Skipping of Unnecessary Tasks
- **What changed:** Before every installation, the system instantly verifies the current state. If it detects that the requested package (including all its optional components, e.g., `fastapi[all]`) is already perfectly installed in the system, it immediately skips the installation process.
- **Benefit:** Massive time savings. The application will no longer download or run installers for things that are already working perfectly.

### ✨ Stable Installation for Massive Projects
- **What changed:** Installing massive lists from `requirements.txt` no longer happens all at once (which occasionally caused crashes on Windows due to overly long command lines). The application now splits the list into manageable batches (e.g., 30 packages at a time).
- **Benefit:** Installation is absolutely rock-solid, no matter how large your project is. Plus, you can see the exact progress in the log (e.g., *Installing batch 1/3*).

### ✨ Perfect Memory for Complex Packages (Extras)
- **What changed:** The system has learned to perfectly understand bracket notations (known as extras, e.g., `requests[socks]`). It knows exactly which sub-packages this notation brought into the system.
- **Benefit:** When uninstalling such packages, the system correctly and cleanly removes absolutely all related dependencies, leaving no "construction debris" in your virtual environment.

---

## 🛠️ Bug Fixes & Stability

### ❌ End of Window and Log Freezing
- **Fixed:** When installing or uninstalling packages, the application window will never freeze again. Log (console) text flows smoothly, line by line, in real-time. If you click the "Refresh" button while a task is running, the app will wait and seamlessly update the list only when it's safe to do so.

### ❌ App Crashes on Window Close
- **Fixed:** In the past, the application could crash if you closed a window (e.g., the local packages window) exactly while an installation was still running in the background. Now, the application safely terminates the process, cleans up the memory, and only then quietly closes the window.

### ❌ Installer (Pip) Getting Stuck
- **Fixed:** In specific cases, the background installer would wait for an invisible user confirmation (e.g., *Proceed (Y/n)?*), causing the process to get stuck forever. The application now automatically forces responses and prevents any deadlocks.

### ❌ Reduced Memory Consumption (Memory Leak Fix)
- **Fixed:** Fixed a hidden bug where the application permanently stored RAM data about virtual environments you had already stopped working with (or deleted). The application is now lighter and faster during long-term use.

---

## 📁 Affected Files

- `core/logic/pip_e.py`
- `core/logic/pip_manager.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/apt_logic.py`
- `windows/pip_e_window.py`
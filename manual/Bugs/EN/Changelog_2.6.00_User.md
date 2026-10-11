# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.6.00  
*This update brings native support for Cursor AI, autonomous background editor detection, full physical isolation of user profiles, and 100% protection of your custom settings during synchronization. It also introduces automatic path repair when a USB drive letter changes and a more reactive user interface.*

---

## 🚀 New Features & Enhancements

###  Full Support for Cursor AI and Autonomous Scanner
- **Independent Environments:** Added native and full-featured support for the modern Cursor AI editor, working side-by-side with Visual Studio Code thanks to new independent CLI dispatchers.
- **Background Editor Detection:** A new 2-second asynchronous scanner continuously monitors the system and connected USB drives. Detection of new editors happens instantly, without blocking or lagging the graphical interface.

###  100% Settings Protection and Profile Separation (Isolation)
- **Physical Data Separation:** User profiles are now strictly isolated into independent folders (`📁 vscode/` and `📁 cursor/`), eliminating any unwanted mixing of settings between editors.
- **Smart Synchronization (Merge):** Writing to the `.vscode/` and `.cursor/` configuration folders exclusively modifies Python paths. Your custom fonts, AI rules, or user tasks are no longer overwritten by the system, thanks to a new internal tracker.
- **Dynamic System Import:** The function for downloading an existing OS profile now intelligently recognizes the active IDE and fetches the correct extensions and data from the respective folders (`AppData/Cursor` or `AppData/Code`).

###  Adaptive Support for Portable Editors (USB Portable)
- **Automatic Drive Letter Repair:** Paths to portable editor versions are saved using internal `[UUID...]` mapping. If your USB drive is assigned a different letter on another computer (e.g., `F:` instead of `E:`), VenvHub detects the change and automatically repairs the paths.

###  Smoother Design and Reactive Architecture
- **Instant Icon Switching:** Thanks to the new Event-Driven architecture and dynamic themes (QSS), editor icons in tables and on the MiniBar change and adapt instantly to light/dark themes without requiring extra clicks.
- **Fixed Settings Grid:** The Settings tab received a unified Grid layout with fixed-width text labels (185px) for a perfectly clean and aligned look.

---

## 🛠️ Bug Fixes & Stability

###  UI Fixes and Freezing Prevention
- **Fixed Icon Freezing After Launching IDE:** Resolved a critical issue where the editor icon got locked in the Qt cache after the first click. Changing the editor in settings now instantly redraws icons in all rows.
- **UI Grid Stabilization:** Fixed the visual breakdown and shifting of input fields in the Settings tab, which occurred when translating texts into other languages.
- **Consistent Profile Lists:** The profile selection dropdown no longer gets stuck on data from the previous editor. Switching the IDE immediately clears and loads the correct profiles.

###  System Logic and Profile Fixes
- **Fixed Profile Saving in Quick Settings:** Resolved a MiniBar bug where switching the active profile for Cursor incorrectly overwrote the default profile for VS Code.
- **Removed Duplicate Copying:** When importing system data, the extension transfer unintentionally ran twice in a row. This issue was resolved, and stabilization safeguards were added for cases where the user has no extensions installed in the system.

###  Comprehensive Localization and More Accurate Messages
- **Detailed Error Messages on IDE Startup:** Fixed incorrect dialog formatting. If the editor fails to start, the error window no longer stays empty but accurately displays the technical reason for the failure.
- **Cleared Hardcoded Slovak Text:** Hardcoded Slovak strings were removed from the profile management window, which undesirably overwrote the English localization when switching languages.
- **Added Missing Translations (EN):** Missing texts for multi-group tooltips, portable path placeholders, the `pip -e` package selection dialog, and editor labels were added to the English dictionaries. An error message for package metadata reading failures was also localized.

---

## 📁 Affected Files

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
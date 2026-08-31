# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.5.27  
*This update brings automatic update notifications directly in the window title bar, instant interface language switching, essential fixes for cleaning and synchronizing local editable packages (pip -e), and overall stability improvements.*

---

## 🚀 New Improvements

### 🔔 Update Notification Directly in the Title Bar
- **Fast background check:** The application quickly and silently checks GitHub upon startup to see if a newer version is available. The check runs in the background without slowing down startup or workflow.
- **New button in the top bar:** When a new version is released, an update icon automatically appears in the window title bar (next to the *About* button), seamlessly styled for both light and dark themes.
- **One-click download:** Clicking the icon opens the official project page in your browser, localized directly into your currently selected language (Slovak or English).

### 🌐 Instant Language Switching & Reactive Window Titles
- **Lightning-fast language change:** Switching languages via *Quick Settings* instantly updates the title bar texts and window titles without needing to restart the window or the application.
- **Centralized version management:** Version details in the *About* dialog are now dynamically synchronized and always 100% accurate across all translations.

---

## 🛠️ Bug Fixes & Stability

### ✏️ Fixes for Local Package Management (`pip -e`)
- **Fixed cleanup after removal from requirements.txt (Autoremove):** Resolved an issue where a local editable package removed or commented out in `requirements.txt` was not uninstalled due to being falsely flagged as protected. Cleanup now purges orphaned packages accurately.
- **Restored warning before unintended uninstallation:** Fixed package widget detection—the app now properly displays a warning dialog if you attempt to uninstall an editable package that is still defined in the project configuration.
- **Accurate requirements synchronization:** The package synchronization feature (`install_sync`) was fixed to properly resolve relative paths and prevent false dependency conflicts.

### 🎨 Visual & System Fixes
- **Fixed language change propagation from Quick Settings:** Resolved an issue where language change signals were occasionally not forwarded to open application components.
- **Fixed GitHub Light theme styling:** Fixed an unclosed CSS style block that caused hover effects on the MiniBar to be ignored.
- **Icon visual polish for all themes:** Added crisp vector SVG notification icons for all light and dark themes.

---

## 📁 Affected Files

- `assets/about.json`
- `core/logic/language_manager.py`
- `core/logic/sluzby/about_logic.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/github_update.py`
- `core/themes/*.qss` *(all UI theme files)*
- `core/themes/icon/update/github_update_white.svg`
- `core/themes/icon/update/github_update_black.svg`
- `main.pyw`
- `ui/custom_title_bar.ui`
- `windows/custom_title_bar.py`
- `windows/manager.py`
- `windows/pip_package_widget.py`
- `windows/quick_settings.py`
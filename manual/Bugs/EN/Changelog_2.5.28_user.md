# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.5.28  
*This update brings full support for optional package extras ([extras]), smart handling of direct Git and URL links in requirements, strict and safe fail-fast installation on version errors, a fix for icon loading in installation paths with spaces, and clean console log output without corrupted characters.*

---

## 🚀 New Features & Improvements

### 📦 Full Support for Optional Dependencies (`[extras]`)
- **Deep Package Analysis:** The dependency manager (APT engine) now inspects package metadata in detail and fully supports optional extras syntax (e.g., `requests[socks]`).
- **Accurate Dependency Tree Tracking:** Packages and their optional sub-dependencies are automatically mapped. When removing a root package from `requirements.txt`, the *Autoremove* feature reliably and cleanly uninstalls all of its unused secondary libraries.

### 🔗 Smart Handling of Direct Git & Web URLs
- **Automatic Name Extraction without `#egg=`:** The application can accurately identify and extract package names directly from web archives (`.whl`, `.tar.gz`, `.zip`) and Git repositories (`git+https://...`) without requiring an explicit `#egg=` fragment.
- **Branch and Version Support:** URLs with specified branches (`@main`, `@v1.0`) or commit hashes are now correctly parsed and tracked.

### 🛡️ Safe Fail-Fast Installation on Errors
- **Protection Against Unintended Installations:** If an invalid or non-existent package version (e.g., `requests===3.0`) is specified in `requirements.txt`, the installation process halts immediately and safely.
- **No Arbitrary Fallback Downloads:** The system will not attempt to bypass solver errors by downloading unconstrained latest package versions—keeping your virtual environment clean, stable, and predictable.

---

## 🛠️ Bug Fixes & Stability

### 🖼️ Fixed Icon Loading in `Program Files` & Custom Themes
- **Automatic Path Quoting with Spaces:** Resolved an issue where dynamic icons in UI themes failed to load when the app was installed in paths containing spaces (typically `C:\Program Files\VenvHub Pro\...`).
- **Theme Backward Compatibility:** All built-in and user-defined `.qss` themes work seamlessly without requiring any manual stylesheet edits.

### 🔤 Process Output Encoding Fix (UTF-8 Mojibake Fix)
- **Clean and Crisp Log Output:** Fixed console stream decoding—dependency trees and special formatting symbols from UV (such as `×`, `╰─`, `▶`) no longer appear as corrupted character strings (`Ă—`, `â•°â”€â–¶`).

### 🧹 APT State Stabilization & Self-Healing Improvements
- **Elimination of False Explicit Flags:** Packages installed via `[extras]` or direct URLs are no longer incorrectly flagged as manual terminal installations, allowing them to be cleanly removed when deleted from requirements.
- **Localized System Messages:** All new synchronization status and error notifications have been fully localized in Slovak and English.

---

## 📁 Affected Files

- `core/logic/pip_manager.py`
- `core/logic/skin_manager.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/apt_logic.py`
- `core/logic/sluzby/requirements_parser.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
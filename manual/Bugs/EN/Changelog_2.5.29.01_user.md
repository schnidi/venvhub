# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.5.29.01  
*This hotfix release delivers a critical stability fix for Windows users, resolving application crashes caused by encoding issues (`UnicodeDecodeError` / CP1250) when fetching package lists, updating, and resolving dependencies via the PIP installer. It also eliminates internal Qt core warnings within the package manager.*

---

## 🛠️ Bug Fixes & Stability

###  Fixed Critical Crash During PIP Operations (`UnicodeDecodeError`)
- **Resolved CP1250 Encoding Collision:** On localized Windows systems (such as Slovak and Czech locales), executing PIP commands caused the internal reader thread (`_readerthread`) to crash when system codepages failed to process specific UTF-8 characters present in console output.
- **Enforced Cross-Platform UTF-8 Communication:** All process communication pipes now strictly enforce UTF-8 encoding with automatic replacement of malformed characters. The application can now safely handle PIP outputs containing special symbols, international characters, or diacritics in package descriptions and author names.

###  Eliminated Internal Qt Mechanism Warnings (`connectSlotsByName`)
- **Prevented False Warning Logs:** Opening the package manager (*Pip Manager*) previously triggered Qt Meta-Object system warnings (`No matching signal for on_freeze_finished / on_update_all_finished`).
- **Clean Asynchronous Slot Connection:** Internal callbacks for background asynchronous tasks (exporting packages to `requirements.txt` and batch updates) were renamed to prevent collisions with Qt Designer's reserved auto-connection pattern. This cleans up the system console output and streamlines dialog initialization.

---

## 📁 Affected Files

- `core/logic/button/pip/load_list.py`
- `core/logic/sluzby/apt_logic.py`
- `windows/pip_manager_window.py`
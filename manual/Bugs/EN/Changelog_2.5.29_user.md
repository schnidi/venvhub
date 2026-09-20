# VenvHub Pro - Release Notes (Changelog)

**Version:** v2.5.29  
*This release introduces flexible cascading resolution for editable packages (`-e`), seamless preservation of APT dependency history during virtual environment cloning, and intelligent sub-dependency protection during version pinning or downgrades.*

---

## 🚀 New Features & Enhancements

### 📂 Flexible Editable Package Resolution (`pip -e`)
- **Cascading Path Resolution:** The requirements parser (`RequirementsParser`) now utilizes a multi-tier resolution mechanism to identify targets following the `-e` / `--editable` directive.
- **Support for Arbitrary Drives and Paths:** Local packages can now reside anywhere on your storage drives (e.g., on separate drives like `F:/...`) or be defined using relative paths (`./...`, `../...`) relative to the `requirements.txt` file, without being restricted to the central `pip_e_root` folder.
- **Smart Fallback Mechanism:** If a package directory has moved or is temporarily unavailable, the system safely extracts the package identity to prevent parser interruptions.

### 🐑 Full Preservation of Dependency Rules During Venv Cloning
- **Seamless APT State Transfer (`venvhub_apt_state.json`):** Cloning or backing up a virtual environment now automatically transfers its full dependency tree and tracking metadata.
- **Complete Rule Continuity:** The cloned environment retains full knowledge of which packages were installed explicitly and which are transient sub-dependencies. As a result, the *Autoremove* engine works in the clone just as reliably as in the original environment.
- **Localized Visual Feedback:** The cloning progress dialog now explicitly confirms the successful transfer of APT history and rules in both Slovak and English.

### 🧩 Intelligent Sub-Dependency Protection During Version Pinning (Downgrade)
- **Context-Aware Dependency Validation:** When manually installing a specific version or downgrading a package, the system checks whether the package is already required by another existing parent package in the environment.
- **Preventing Orphaned Libraries:** Pinning a sub-dependency version (e.g., `pysocks` under `requests[socks]`, or `urllib3` under `requests`) no longer erroneously elevates it to a manually installed package. It remains tracked as a dependency and is cleanly purged when the parent package is uninstalled.

---

## 🛠️ Bug Fixes & Stability Improvements

### 🛡️ Protection of `-e` Packages from False Manual Flags (Self-Healing)
- **Path Overwrite Prevention:** Resolved an issue where the parser forced local editable paths into the configured `pip_e_root` folder, causing the Self-Healing engine to mistake them for external manual terminal installs.
- **Clean Lifecycle via `requirements.txt`:** Local editable packages installed via `-e` are properly retained in the requirements registry. Commenting out or deleting their entry from the file allows *Autoremove* to cleanly uninstall them as expected.

### 🧬 Fixed Dependency Degradation in Cloned Environments
- **Tree Hierarchy Preservation:** Eliminated a bug where newly cloned virtual environments flattened package hierarchies and marked all packages as explicitly installed, which previously blocked their automatic removal during cleanup.

### 🧹 Refined State Tracking in APT Listener
- **Accurate Explicit Tracking:** Fixed an issue where manual version adjustments on sub-dependencies permanently locked them into the explicit installations registry, preventing proper future tree purges.

---

## 📁 Affected Files

- `core/logic/button/manager/clone.py`
- `core/logic/sluzby/apt_listener.py`
- `core/logic/sluzby/requirements_parser.py`
- `translations/en_US.json`
- `translations/sk_SK.json`
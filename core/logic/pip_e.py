#----------------------------------------
# Súbor: core/logic/pip_e.py
#----------------------------------------

import os
import json
import subprocess
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from core._path import Paths
from core.logic.language_manager import LanguageManager
from core.logic.birth_certificate import BirthCertificateGenerator
from core.logic.commands.command_factory import PackageManagerFactory
from core.logic.uv_detector import UVDetector

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

# Prepni na True, ak chceš v logu vidieť, v ktorom vlákne worker beží
DEBUG_THREAD = False

# Hooky, cez ktoré sa pripája AptListener (namiesto prepisovania run()).
# Všetky bežia vo vlákne workera, PRED emitovaním finished.
#   install_success(worker)                 -> None
#   uninstall_pre(worker)                   -> (blocked_msg | None, context)
#   uninstall_success(worker, context)      -> None
HOOKS = {
    "install_success": None,
    "uninstall_pre": None,
    "uninstall_success": None,
}


def _call_hook(worker, name, *args):
    """Bezpečne zavolá hook; jeho chyba nesmie zhodiť worker."""
    hook = HOOKS.get(name)
    if not hook:
        return None
    try:
        return hook(worker, *args)
    except Exception as e:
        worker.log_msg.emit(f"⚠️ [{name}] chyba: {e}")
        return None


def _build_env() -> dict:
    """Prostredie pre subprocesy: bez bufferovania a bez progress barov."""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PIP_PROGRESS_BAR"] = "off"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["UV_NO_PROGRESS"] = "1"
    return env


class _BaseWorker(QObject):
    """Spoločný základ: streamovanie výstupu procesu do log_msg v reálnom čase."""
    log_msg = pyqtSignal(str)
    error = pyqtSignal(str)

    def _debug_thread(self):
        if DEBUG_THREAD:
            from PyQt6.QtWidgets import QApplication
            in_main = QThread.currentThread() == QApplication.instance().thread()
            self.log_msg.emit(f"[DEBUG] worker beží v {'HLAVNOM (ZLE!)' if in_main else 'pozadí (OK)'} vlákne")

    def _run_streamed(self, cmd) -> int:
        """Spustí príkaz a každý riadok výstupu okamžite pošle do logu."""
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,          # nikdy nečakať na vstup (napr. 'Proceed (Y/n)?')
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=_build_env(),
            creationflags=CREATE_NO_WINDOW
        )
        for line in process.stdout:
            clean_line = line.strip()
            if clean_line:
                self.log_msg.emit(f"  {clean_line}")
        process.wait()
        return process.returncode


class PipEListWorker(_BaseWorker):
    """Asynchrónny Worker pre načítanie zoznamu editovateľných balíčkov (pip / uv)."""
    finished = pyqtSignal(list)

    def __init__(self, venv_path: str, manager_type: str = "pip"):
        super().__init__()
        self.venv_path = venv_path
        self.manager_type = manager_type

    @pyqtSlot()
    def run(self):
        try:
            self._debug_thread()
            python_exe = Paths.get_venv_python_exe_path(self.venv_path)
            if not os.path.exists(python_exe):
                self.error.emit(LanguageManager.get(
                    "pipe_err_no_python", "❌ Python executable nebol nájdený: {0}"
                ).format(python_exe))
                self.finished.emit([])
                return

            mgr_label = "UV" if self.manager_type == "uv" else "PIP"
            self.log_msg.emit(LanguageManager.get(
                "pipe_log_loading", "🔄 [{0}] Načítavam zoznam editovateľných balíčkov..."
            ).format(mgr_label))

            # 1. Zostavenie príkazu podľa vybraného manažéra (uv / pip)
            if self.manager_type == "uv":
                uv_exe = UVDetector.get_uv_path() or "uv"
                cmd = [uv_exe, "pip", "list", "--editable", "--format=json", "--python", python_exe]
            else:
                cmd = [python_exe, "-m", "pip", "list", "--editable", "--format=json"]

            run_kwargs = dict(
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                stdin=subprocess.DEVNULL, env=_build_env(), creationflags=CREATE_NO_WINDOW
            )
            result = subprocess.run(cmd, **run_kwargs)

            # 2. Ak príkaz zlyhal, pošleme presnú chybu manažéra bez tichého prepínania
            if result.returncode != 0:
                self.error.emit(LanguageManager.get(
                    "pipe_err_list_failed", "❌ Zlyhalo načítanie zoznamu ({0}): {1}"
                ).format(mgr_label, result.stderr.strip() or result.stdout.strip()))
                self.finished.emit([])
                return

            output = result.stdout.strip()
            if output:
                try:
                    packages = json.loads(output)
                    self.log_msg.emit(LanguageManager.get(
                        "pipe_log_loaded_count", "✅ [{0}] Načítaných {1} editovateľných balíčkov."
                    ).format(mgr_label, len(packages)))
                    self.finished.emit(packages)
                except json.JSONDecodeError as e:
                    self.error.emit(LanguageManager.get(
                        "pipe_err_json_parse", "❌ Chyba pri spracovaní JSON výstupu: {0}"
                    ).format(e))
                    self.finished.emit([])
            else:
                self.log_msg.emit(LanguageManager.get(
                    "pipe_log_no_packages",
                    "ℹ️ V tomto prostredí nie sú nainštalované žiadne editovateľné balíčky."
                ))
                self.finished.emit([])

        except Exception as e:
            self.error.emit(LanguageManager.get("pipe_err_critical", "❌ Kritická chyba: {0}").format(e))
            self.finished.emit([])


class PipEInstallWorker(_BaseWorker):
    """Asynchrónny Worker pre pip install -e / uv pip install -e."""
    finished = pyqtSignal(bool)

    def __init__(self, venv_path: str, target_path: str, manager_type: str = "pip"):
        super().__init__()
        self.venv_path = venv_path
        self.target_path = target_path
        self.manager_type = manager_type

    @pyqtSlot()
    def run(self):
        try:
            self._debug_thread()
            python_exe = Paths.get_venv_python_exe_path(self.venv_path)
            if not os.path.exists(python_exe):
                self.error.emit(LanguageManager.get(
                    "pipe_err_no_python", "❌ Python executable nebol nájdený: {0}"
                ).format(python_exe))
                self.finished.emit(False)
                return

            has_setup = os.path.exists(os.path.join(self.target_path, "setup.py"))
            has_toml = os.path.exists(os.path.join(self.target_path, "pyproject.toml"))
            if not has_setup and not has_toml:
                self.error.emit(LanguageManager.get(
                    "pipe_err_invalid_folder",
                    "⚠️ Priečinok '{0}' neobsahuje súbor 'setup.py' ani 'pyproject.toml'. Inštalácia nie je možná."
                ).format(os.path.basename(self.target_path)))
                self.finished.emit(False)
                return

            dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.venv_path)

            # Zabezpečenie build nástrojov (setuptools, wheel) dynamicky podľa manažéra
            if self.manager_type == "pip":
                self.log_msg.emit("🛠 [PIP] Zabezpečujem build nástroje (setuptools, wheel)...")
                rc = self._run_streamed([
                    python_exe, "-m", "pip", "install", "setuptools", "wheel",
                    "--progress-bar", "off"
                ])
                if rc != 0:
                    self.log_msg.emit("⚠️ Príprava build nástrojov zlyhala, pokračujem ďalej...")

            cmd = list(dispatcher.get("install_editable", path=self.target_path))

            # Špecifické doplnenie parametrov pre pip
            if self.manager_type == "pip":
                if "--no-build-isolation" not in cmd:
                    cmd.append("--no-build-isolation")
                if "--progress-bar" not in cmd:
                    cmd += ["--progress-bar", "off"]

            installer_label = "uv pip install -e" if self.manager_type == "uv" else "pip install -e"
            self.log_msg.emit(LanguageManager.get(
                "pipe_log_installing",
                "\n⚡ Spúšťam inštaláciu vývojového balíčka: {0} {1}"
            ).format(installer_label, os.path.basename(self.target_path)))

            returncode = self._run_streamed(cmd)
            success = (returncode == 0)

            if success:
                self.log_msg.emit(LanguageManager.get(
                    "pipe_log_install_success", "✅ Balíček úspešne prelinkovaný ({0})."
                ).format(self.manager_type.upper()))
                try:
                    BirthCertificateGenerator.update_venv_certificate(self.venv_path)
                except Exception as e:
                    self.log_msg.emit(f"⚠️ Birth certificate sa nepodarilo aktualizovať: {e}")
                _call_hook(self, "install_success")
            else:
                self.error.emit(LanguageManager.get(
                    "pipe_err_install_failed", "❌ Inštalácia zlyhala s kódom {0}."
                ).format(returncode))

            self.finished.emit(success)

        except Exception as e:
            self.error.emit(LanguageManager.get("pipe_err_critical", "❌ Kritická chyba: {0}").format(e))
            self.finished.emit(False)


class PipEUninstallWorker(_BaseWorker):
    """Asynchrónny Worker pre odinštalovanie editovateľného balíčka (pip / uv)."""
    finished = pyqtSignal(bool)

    def __init__(self, venv_path: str, package_name: str, manager_type: str = "pip"):
        super().__init__()
        self.venv_path = venv_path
        self.package_name = package_name
        self.manager_type = manager_type

    @pyqtSlot()
    def run(self):
        try:
            self._debug_thread()
            python_exe = Paths.get_venv_python_exe_path(self.venv_path)
            if not os.path.exists(python_exe):
                self.error.emit(LanguageManager.get(
                    "pipe_err_no_python", "❌ Python executable nebol nájdený: {0}"
                ).format(python_exe))
                self.finished.emit(False)
                return

            context = None
            pre = _call_hook(self, "uninstall_pre")
            if pre:
                blocked_msg, context = pre
                if blocked_msg:
                    self.log_msg.emit(blocked_msg)
                    self.finished.emit(False)
                    return

            dispatcher = PackageManagerFactory.get_dispatcher(self.manager_type, self.venv_path)
            cmd = list(dispatcher.get("uninstall", package_name=self.package_name))

            # pip vyžaduje -y na potvrdenie bez interakcie
            if self.manager_type == "pip" and "-y" not in cmd and "--yes" not in cmd:
                cmd.append("-y")

            self.log_msg.emit(LanguageManager.get(
                "pipe_log_uninstalling", "\n🗑️ Odinštalujem balíček '{0}' ({1})..."
            ).format(self.package_name, self.manager_type.upper()))

            returncode = self._run_streamed(cmd)
            success = (returncode == 0)

            if success:
                self.log_msg.emit(LanguageManager.get(
                    "pipe_log_uninstall_success", "✅ Balíček '{0}' bol úspešne odstránený."
                ).format(self.package_name))
                try:
                    BirthCertificateGenerator.update_venv_certificate(self.venv_path)
                except Exception as e:
                    self.log_msg.emit(f"⚠️ Birth certificate sa nepodarilo aktualizovať: {e}")
                _call_hook(self, "uninstall_success", context)
            else:
                self.error.emit(LanguageManager.get(
                    "pipe_err_uninstall_failed", "❌ Odinštalácia zlyhala s kódom {0}."
                ).format(returncode))

            self.finished.emit(success)

        except Exception as e:
            self.error.emit(LanguageManager.get("pipe_err_critical", "❌ Kritická chyba: {0}").format(e))
            self.finished.emit(False)
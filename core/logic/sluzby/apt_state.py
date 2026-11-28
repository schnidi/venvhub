#------------------------------------------------
# Súbor: core/logic/sluzby/apt_state.py
#------------------------------------------------

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Optional
from core.logic.sluzby.language_bridge import LanguageBridge


class AptState(str, Enum):
    IDLE = "IDLE"
    ANALYZING = "ANALYZING"
    VERIFYING_SAFETY = "VERIFYING_SAFETY"
    DIFF_CALCULATING = "DIFF_CALCULATING"
    INSTALLING = "INSTALLING"
    EXTRAS_SYNCING = "EXTRAS_SYNCING"
    EDITABLE_SYNCING = "EDITABLE_SYNCING"
    STATE_UPDATING = "STATE_UPDATING"
    GRAPH_BUILDING = "GRAPH_BUILDING"
    ORPHANS_CALCULATING = "ORPHANS_CALCULATING"
    REMOVING_ORPHANS = "REMOVING_ORPHANS"
    CHECKING_INTEGRITY = "CHECKING_INTEGRITY"
    COMPLETED_SUCCESS = "COMPLETED_SUCCESS"
    COMPLETED_SKIPPED = "COMPLETED_SKIPPED"
    COMPLETED_WARNING = "COMPLETED_WARNING"
    CORRUPT_STATE = "CORRUPT_STATE"
    FAILED = "FAILED"

    @property
    def default_template(self) -> tuple[str, str]:
        templates = {
            AptState.IDLE: ("apt_state_idle", "Package management system is idle."),
            AptState.ANALYZING: ("apt_state_analyzing", "🔬 Analyzing package state: {pkg}"),
            AptState.VERIFYING_SAFETY: ("apt_state_verifying_safety", "🛡️ Verifying safety for package '{pkg}'..."),
            AptState.DIFF_CALCULATING: ("apt_state_diff_calculating", "📦 [APT: STATE 1 - DIFF] Comparing requirements.txt with JSON state..."),
            AptState.INSTALLING: ("apt_state_installing", "🚀 [APT: STATE 2 - INSTALL] Installing requirements ({count}): {pkgs}"),
            AptState.EXTRAS_SYNCING: ("apt_state_extras_syncing", "🔗 [APT: STATE 3 - EXTRAS] Bound extras for '{parent}': {children}"),
            AptState.EDITABLE_SYNCING: ("apt_state_editable_syncing", "📂 [APT: STATE - EDITABLE] Bound dependencies for '{pkg}': {children}"),
            AptState.STATE_UPDATING: ("apt_state_updating", "💾 Updating venvhub_apt_state.json..."),
            AptState.GRAPH_BUILDING: ("apt_state_graph_building", "📊 Building environment dependency graph..."),
            AptState.ORPHANS_CALCULATING: ("apt_state_orphans_calculating", "🔍 Analyzing dependency tree and finding orphan packages..."),
            AptState.REMOVING_ORPHANS: ("apt_state_removing_orphans", "🗑️ [APT-{mgr}] Autoremove: Removing orphan packages: {pkgs}"),
            AptState.CHECKING_INTEGRITY: ("apt_state_checking_integrity", "--- Running {mgr} dependency integrity check... ---"),
            AptState.COMPLETED_SUCCESS: ("apt_state_completed_success", "✅ [APT: DONE] Status cycle completed successfully."),
            AptState.COMPLETED_SKIPPED: ("apt_state_completed_skipped", "ℹ️ Package '{pkg}' already satisfies requirement. Skipping."),
            AptState.COMPLETED_WARNING: ("apt_state_completed_warning", "⚠️ [{mgr} Check] Dependency conflicts detected:\n{output}"),
            AptState.CORRUPT_STATE: ("apt_state_corrupt", "🛑 [APT: CORRUPT] Invalid state for venv '{venv}'. Recreate the environment."),
            AptState.FAILED: ("apt_state_failed", "❌ [APT: ERROR] {err}"),
        }
        return templates.get(self, ("apt_state_unknown", "Unknown state: {err}"))

    def format_message(self, **kwargs) -> str:
        loc_key, default_tpl = self.default_template
        val = LanguageBridge.translate(loc_key, default_tpl)
        try:
            return val.format(**kwargs)
        except Exception:
            return val


@dataclass
class AptStatusEvent:
    state: AptState
    message: str
    progress_pct: Optional[int] = None
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default=None) -> Any:
        return self.data.get(key, default)

    @property
    def is_error(self) -> bool:
        return self.state in (AptState.FAILED, AptState.CORRUPT_STATE)

    @property
    def is_finished(self) -> bool:
        return self.state in (
            AptState.COMPLETED_SUCCESS, 
            AptState.COMPLETED_SKIPPED, 
            AptState.COMPLETED_WARNING, 
            AptState.CORRUPT_STATE,
            AptState.FAILED
        )
"""MC Command Center presence probe + should_defer() (SPEC.md Sec 9.1/Sec 10).

`INSTANCE_ID` (`MTS_Deaderpool_McCommander_MainSettings_ShowMenu`, research/build_plan.md Sec 2a) is
verified two ways, this session, against this machine's own currently-installed copy - not carried
forward on trust:
  1. `sims4.resources.Types.INTERACTION` is a real, class-level member of this build's own
     `sims4/resources.pyc` (this package's manifest row) - the same instance-manager type BP1/BP3 already
     verified and use for the Novulon interaction itself.
  2. The id is actually present, as an Interaction-tuning resource (DBPF type `0xE882D22F`), inside this
     machine's real, installed `mc_cmd_center.package` - read directly, read-only, with this repo's own
     `wicked_animator/backend/dbpf.py:read_index` (never modified, never written to): one index entry
     with `inst == 0xD27DB58CF1DAF8FA` and `type == 0xE882D22F`. This is strictly more evidence than
     `research/build_plan.md` had (a citation, not a fresh read of the currently-installed file) - see
     this package's build report for the exact command run.

`should_defer(feature)` backs SPEC.md Sec 9.1's compatibility banner and every Gameplay row that
overlaps an MCCC module: `settings.py` (BP1) computes the four `compat.defer_to_mccc.*` flags once, at
first run, from `is_present()` (all-true when MCCC is detected, all-false when it is not - never the
other way around, Sec 7's own review note). This file only ever reads that stored setting back; it never
re-decides the default itself, and never re-probes on every call - `is_present()`'s own result is what
`settings.py` consulted at first run, and `should_defer()` here is a completely separate, later read of
the persisted choice, correct even if a player uninstalls/reinstalls MCCC mid-save (the setting stays
whatever it was set to until the player changes it in Settings, matching a real mod-conflict flag rather
than a live re-check on every single feature use).
"""
from .. import common
from . import probe

INSTANCE_ID = 0xD27DB58CF1DAF8FA


def is_present():
    """True if MC Command Center's own main-settings interaction tuning is currently loaded. Cached by
    compat.probe() after the first call this session."""
    try:
        import sims4.resources
    except Exception:
        common.log_exception('compat.mccc.is_present (import sims4.resources)')
        return False
    return probe(sims4.resources.Types.INTERACTION, INSTANCE_ID)


def should_defer(feature):
    """True when Novulon's own `feature` ('population'/'pregnancy'/'aging'/'story_progression') should
    defer to MC Command Center rather than run its own version:
    settings.get('compat.defer_to_mccc.<feature>', False). An unrecognised feature name (a typo in a
    caller, or a future feature this file doesn't know about yet) defaults to False - never silently
    disable a feature no player has ever seen a setting for."""
    from .. import settings
    return bool(settings.get('compat.defer_to_mccc.' + feature, False))

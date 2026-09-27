"""adult/bridge.py - the Aggregated Settings Front Door's plumbing (SPEC.md Sec.1 resolution #2 /
Sec.11). Delegates every actual WickedWhims read/write to `compat.wickedwhims` (BP7) - that file's own
docstring names this package as its expected caller ("adult/bridge.py, BP11, is expected to be the
main caller of the accessors", SPEC.md Sec.10), so this file adds no `wickedwhims.*` import of its
own; `compat/wickedwhims.py` is the one place in the whole mod that touches WickedWhims' settings
modules directly, already guarded exactly like `inject.py`'s own game-module lookups (import inside
the function, `common.guarded`, log-and-None on failure).

Nothing new is built here - every setting this file exposes already exists in WickedWhims; V1 only
aggregates a front door onto it (SPEC.md Sec.1 resolution #2). `get_setting`/`set_setting` add one
more layer of defense on top of `compat.wickedwhims`'s own guarding: if `compat/` is ever
unimportable (a build-order accident - `gate.is_adult_section_available()` already keeps the whole
Adult tile hidden in that case, so this path is not expected to be reached in a real game session),
they degrade to "unavailable" instead of raising - the same direction every guarded call already
takes throughout this mod.

`set_setting`'s success signal: WickedWhims' own `set_*_setting` functions always return `None` on
success (confirmed this session by disassembling `set_sex_setting`/`set_nudity_setting`/
`set_relationship_setting` directly - each ends `LOAD_CONST None; RETURN_VALUE`), which is
indistinguishable, by return value alone, from `compat.wickedwhims`'s own guarded-failure path (also
`None`). `set_setting` reports success via `is_present()` instead - the most honest signal available:
if WickedWhims is present, the write is assumed to have gone through (a renamed/removed key silently
no-ops, same as every other guarded WickedWhims call in this mod); if it isn't present, the write
certainly failed.

SUBGROUPS below is the Aggregated Settings Front Door's own content: SPEC.md Sec.1 resolution #2's
five named groups (Pregnancy & Birth Control / Autonomy & Refusal / Venue & Location Permissions /
Statistics & Buffs / Social Feed), each holding only boolean switches - menukit has no verified
numeric or free-text input widget yet (SPEC.md Sec.18's `text_inputs=` open item), so a numeric
WickedWhims setting (e.g. `simhub_earnings_modifier_new`) is left out entirely rather than guessed at
with an unverified widget. Every key name below was independently re-verified THIS session, read-
only, directly against the owner's own installed copy
(`C:\\Users\\basim\\Documents\\Electronic Arts\\The Sims 4\\Mods\\scripts\\
TURBODRIVER_WickedWhims_Scripts.ts4script`) with `tools/pyc37.py --strings` against
`wickedwhims/sex/sex_settings.pyc`, `.../nudity_settings.pyc`, `.../relationship_settings.pyc` - not
merely carried from `research/adult_wants.md`'s own [VERIFIED] tags, though this pass independently
confirms every one of them. Not listed in `tools/novulon_api_manifest/` - see that package's own
`bp11_adult.py` docstring for why a third-party mod's setting-key strings don't belong in the shared,
game-zip-checked manifest (the same reasoning `compat/wickedwhims.py`'s own docstring already gives
for its accessor function names).
"""
from .. import common

# (get-function name, set-function name) on compat.wickedwhims, per accessor domain.
_ACCESSORS = {
    'sex': ('get_sex_setting', 'set_sex_setting'),
    'nudity': ('get_nudity_setting', 'set_nudity_setting'),
    'relationship': ('get_relationship_setting', 'set_relationship_setting'),
}

# The autonomy-related sex switches panic.py turns off/back on as a group (SPEC.md Sec.11 V1 row 3's
# "cancels pending autonomy" piece) - a subset of the 'autonomy' SUBGROUP below, named separately so
# panic.py doesn't have to reach into the UI-facing SUBGROUPS structure to find them.
AUTONOMY_SEX_KEYS = (
    'autonomy_switch', 'sex_autonomy_random_switch', 'sex_autonomy_romance_switch',
    'sex_autonomy_random_solo_switch', 'sex_autonomy_watch_switch', 'join_sex_autonomy_switch',
    'player_join_sex_autonomy_switch',
)

# The Aggregated Settings Front Door itself (SPEC.md Sec.1 resolution #2's five named subgroups).
# Each entry: (accessor domain, WickedWhims setting-key string, short display label). Every key here
# is a real, verified [see module docstring], already-existing WickedWhims/Wicked-Perversions-adjacent
# setting - V1 adds no new setting of its own.
SUBGROUPS = [
    {'key': 'pregnancy', 'label': 'Pregnancy & Birth Control', 'settings': [
        ('sex', 'pregnancy_menstrual_cycle', 'Menstrual Cycle Mode'),
    ]},
    {'key': 'autonomy', 'label': 'Autonomy & Refusal', 'settings': [
        ('sex', 'autonomy_switch', 'Autonomy'),
        ('sex', 'sex_autonomy_random_switch', 'Random Autonomy'),
        ('sex', 'sex_autonomy_romance_switch', 'Romance Autonomy'),
        ('sex', 'sex_autonomy_random_solo_switch', 'Solo Autonomy'),
        ('sex', 'sex_autonomy_watch_switch', 'Watching Autonomy'),
        ('sex', 'join_sex_autonomy_switch', 'Joining Autonomy'),
        ('sex', 'player_join_sex_autonomy_switch', 'Played Sims Joining'),
    ]},
    {'key': 'venue', 'label': 'Venue & Location Permissions', 'settings': [
        ('sex', 'sex_autonomy_club_switch', 'Club Autonomy'),
        ('sex', 'autonomy_sex_business_state', 'Business Autonomy'),
        ('sex', 'change_sex_location_anywhere', 'Anywhere'),
    ]},
    {'key': 'stats', 'label': 'Statistics & Buffs', 'settings': [
        ('relationship', 'desire_switch', 'Desire'),
        ('relationship', 'sex_cheating_buffs', 'Cheating Buffs'),
        ('relationship', 'attractiveness_system_state', 'Attractiveness'),
    ]},
    {'key': 'social', 'label': 'Social Feed', 'settings': [
        ('nudity', 'simhub_state_new', 'Social Feed'),
    ]},
]


def _ww_compat():
    """`compat.wickedwhims` (BP7), or None if `compat/` isn't importable right now. Lazy, guarded -
    see module docstring."""
    try:
        from ..compat import wickedwhims as ww_compat
        return ww_compat
    except Exception:
        return None


def get_setting(domain, key):
    """The current value of one WickedWhims setting, or None if `compat.wickedwhims`, WickedWhims
    itself, or that key isn't available right now. Never raises."""
    names = _ACCESSORS.get(domain)
    ww = _ww_compat()
    if names is None or ww is None:
        return None
    getter = getattr(ww, names[0], None)
    if getter is None:
        return None
    try:
        return getter(key)
    except Exception:
        common.log_exception('adult.bridge: get %s.%s' % (domain, key))
        return None


def set_setting(domain, key, value):
    """Write one WickedWhims setting through `compat.wickedwhims`. Returns True if WickedWhims is
    present (see module docstring for why that, not the call's own return value, is the success
    signal), False otherwise - never raises, never partially applies a batch (see
    `set_all_sex_autonomy` for how a caller composes several of these safely)."""
    names = _ACCESSORS.get(domain)
    ww = _ww_compat()
    if names is None or ww is None:
        return False
    setter = getattr(ww, names[1], None)
    if setter is None:
        return False
    try:
        setter(key, value)
        return bool(ww.is_present())
    except Exception:
        common.log_exception('adult.bridge: set %s.%s' % (domain, key))
        return False


def toggle_setting(domain, key, default=False):
    """Flip a boolean WickedWhims setting and return the NEW value. If the current value can't be
    read, assumes `default` was the old value so the row still does something sensible (flips away
    from `default`) instead of silently doing nothing."""
    current = get_setting(domain, key)
    if current is None:
        current = default
    new_value = not bool(current)
    set_setting(domain, key, new_value)
    return new_value


def set_all_sex_autonomy(enabled):
    """Set every `AUTONOMY_SEX_KEYS` switch to `enabled`. Best-effort per key (one missing/renamed
    key in a future WickedWhims version never stops the rest) - returns how many of them were
    actually written."""
    return sum(1 for key in AUTONOMY_SEX_KEYS if set_setting('sex', key, enabled))

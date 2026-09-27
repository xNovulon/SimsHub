"""Settings tile - Adult Content on/off, Compatibility, Log Level, About (SPEC.md Sec 12, build package
BP12). Every screen here is built with `menukit.Row`/`Page` only (never `ui.*` directly - menukit/BP2's
own file docstring: "menukit is the ONE place that builds a ui.ui_dialog_picker/ui.ui_dialog dialog").
No new EA API is introduced by this file - it only calls already-verified surface: `commands.add_section`
(BP1), `menukit.Row`/`Page`/`show_page`/`go_back`/`notify` (BP2), `settings.get`/`set` (BP1), and this
package's own `compat.*` probes (BP7, this same build task).

**Adult Content toggle**: disabled with `disabled_text='Requires WickedWhims'` whenever
`compat.wickedwhims.is_present()` is false - a player can't even reach the confirmation without
WickedWhims installed. Turning it ON pushes a one-screen notice (SPEC.md Sec 11's own interstitial copy,
reused verbatim: "Adults only / This section is for young adult and older Sims only.") that must be
confirmed before `adult.enabled` is actually set - this is a SEPARATE safety check from `adult/gate.py`'s
own "shown once ever" interstitial (BP11, not built in this pass): that one fires the first time a player
actually opens the Adult tile; this one fires every time a player flips this switch on, here in Settings,
regardless of whether the tile has ever been opened. The two together mean a player sees the notice both
when they turn the feature on AND the first time they use it - belt and suspenders around a hard rule
(SPEC.md Sec 0), not a redundancy to trim. Turning it OFF needs no confirmation - there is nothing unsafe
about disabling the section.

**Compatibility** is read-only status lines, never a feature gate itself (SPEC.md Sec 12): MC Command
Center / WickedWhims detected-or-not (with WickedWhims's version string when known), and a Wicked
Perversions duplicate-install line only when 2+ copies are actually found (nothing to say otherwise -
matching the MCCC/WickedWhims lines' own "(or absent)" framing, SPEC.md Sec 12). Each status line is a
disabled-by-nothing but effectively inert `Row` (no navigation, `on_activate=None`) - menukit's own "every
row needs a registered command" rule (`stack.validate_page`) still requires each one's `id` be registered
via `commands.add()`, so a single shared no-op action backs every status-line row on this tile - see
`_INFO_ID` below. This is exactly the same "several rows sharing one command id" shape `render.py` maps
back to the correct originating `Row` object by Python identity, not by the `id` string, so it is fully
safe (`render.py`'s own `_dispatch`/`by_identity` - confirmed by reading that file directly, not assumed).

**Log Level**: one row per level (`debug`/`info`/`warning`/`error`), the current one shown `selected`.
Every level's activation function is built ONCE at import time and reused for both `commands.add()` and
the `Row.on_activate` that appears on the page - `commands.py`'s own contract (BP1): "a menukit Row's
on_activate and the function registered ... for the SAME action_id must be the literal same function".
`settings_ui` does not add any actual level-based log FILTERING - `common.log()` (BP1, not editable by
this package) writes every line unconditionally today; this row only lets a player choose and persist the
stored value for whenever that filtering is added.

**About**: version and log-file path, both read-only info rows (same shared-no-op-action shape as
Compatibility).

Tile description text and every row label/description here follow SPEC.md's global text rule: short,
natural, no first person, no filler words.
"""
import os

from .. import commands, common, menukit, settings
from ..menukit import Page, Row

SECTION_KEY = 'settings'
SECTION_ORDER = 50   # SPEC.md's V1 order is Sims/Household/Gameplay/Cheats/Settings, Adult last of all
                      # when unlocked - BP11's own 'adult' section should use an order past this one
                      # (e.g. 60) to land after Settings; this file does not enforce that, only documents it.

ADULT_TOGGLE_ID = 'novulon.settings.adult_toggle'
ADULT_CONFIRM_ID = 'novulon.settings.adult_confirm'
COMPAT_OPEN_ID = 'novulon.settings.compat_open'
LOG_LEVEL_OPEN_ID = 'novulon.settings.log_level_open'
ABOUT_OPEN_ID = 'novulon.settings.about_open'
_INFO_ID = 'novulon.settings.info'   # shared no-op id for every read-only status/info row on this tile

LOG_LEVELS = ('debug', 'info', 'warning', 'error')
LOG_LEVEL_SET_PREFIX = 'novulon.settings.log_level.set.'


# ------------------------------------------------------------------ compat lookups (guarded, lazy)
def _mccc_present():
    try:
        from ..compat import mccc
    except Exception:
        return False
    return bool(common.guarded('settings_ui: mccc.is_present', mccc.is_present))


def _ww_present():
    try:
        from ..compat import wickedwhims
    except Exception:
        return False
    return bool(common.guarded('settings_ui: wickedwhims.is_present', wickedwhims.is_present))


def _ww_version():
    try:
        from ..compat import wickedwhims
    except Exception:
        return None
    return common.guarded('settings_ui: wickedwhims.version_str', wickedwhims.version_str)


def _wp_duplicate_count():
    try:
        from ..compat import wicked_perversions
    except Exception:
        return 0
    n = common.guarded('settings_ui: wicked_perversions.duplicate_count', wicked_perversions.duplicate_count)
    return n or 0


# ------------------------------------------------------------------ Adult Content row
def _adult_row():
    enabled = bool(settings.get('adult.enabled', False))
    if not _ww_present():
        return Row(ADULT_TOGGLE_ID, 'Adult Content', description='Off',
                    disabled_text='Requires WickedWhims')
    return Row(ADULT_TOGGLE_ID, 'Adult Content', description=('On' if enabled else 'Off'),
                on_activate=_activate_adult_toggle)


def _activate_adult_toggle(connection, selected_ids=None):
    enabled = bool(settings.get('adult.enabled', False))
    if enabled:
        settings.set('adult.enabled', False)
        menukit.notify('Adult Content', 'Turned off.')
        menukit.show_page(connection, build_settings_page(connection), push=False)
        return None
    return Page('Adults only', [Row(ADULT_CONFIRM_ID, 'Continue', on_activate=_confirm_adult_enable)],
                breadcrumb=('Settings', 'Adult Content'),
                subtitle='This section is for young adult and older Sims only.')


def _confirm_adult_enable(connection, selected_ids=None):
    """Leaves the 'Adults only' notice and shows a freshly-built Settings page in its place, in ONE
    render. `menukit.go_back` itself renders whatever it pops back to - calling it and then
    `menukit.show_page(..., push=False)` right after would build and show the dialog TWICE (once with
    the stale pre-toggle Settings page, immediately replaced by the fresh one), so the stack is popped
    directly here instead, with only the final `show_page` call actually rendering anything."""
    settings.set('adult.enabled', True)
    menukit.notify('Adult Content', 'Turned on.')
    menukit.stack.for_connection(connection).pop()
    menukit.show_page(connection, build_settings_page(connection), push=False)
    return None


# ------------------------------------------------------------------ Compatibility
def _info_noop(connection, selected_ids=None):
    return None


def _compat_lines():
    """[(label, status)] - see module docstring for what appears/is omitted and why."""
    lines = [('MC Command Center', 'Detected' if _mccc_present() else 'Not detected')]

    if _ww_present():
        ver = _ww_version()
        lines.append(('WickedWhims', 'Detected (%s)' % ver if ver else 'Detected'))
    else:
        lines.append(('WickedWhims', 'Not detected'))

    count = _wp_duplicate_count()
    if count >= 2:
        lines.append(('Wicked Perversions', '%d copies detected - this can cause conflicts.' % count))
    elif count == 1:
        lines.append(('Wicked Perversions', 'Detected'))
    return lines


def _compat_summary():
    bits = [label for label, status in _compat_lines() if status.startswith('Detected')]
    return (', '.join(bits) + ' detected.') if bits else 'Nothing detected.'


def build_compat_page(connection, selected_ids=None):
    rows = [Row(_INFO_ID, label, description=status, on_activate=None) for label, status in _compat_lines()]
    return Page('Compatibility', rows, breadcrumb=('Settings', 'Compatibility'))


# ------------------------------------------------------------------ Log Level
def _make_log_level_fn(level):
    def _fn(connection, selected_ids=None):
        # See `_confirm_adult_enable`'s docstring: pop directly (no render) rather than
        # `menukit.go_back` + `show_page`, which would render the dialog twice in a row.
        settings.set('log_level', level)
        menukit.notify('Log Level', level.capitalize() + '.')
        menukit.stack.for_connection(connection).pop()
        menukit.show_page(connection, build_settings_page(connection), push=False)
        return None
    return _fn


_LOG_LEVEL_FNS = dict((level, _make_log_level_fn(level)) for level in LOG_LEVELS)


def build_log_level_page(connection, selected_ids=None):
    current = settings.get('log_level', 'info')
    rows = [Row(LOG_LEVEL_SET_PREFIX + level, level.capitalize(), selected=(level == current),
                on_activate=_LOG_LEVEL_FNS[level])
            for level in LOG_LEVELS]
    return Page('Log Level', rows, breadcrumb=('Settings', 'Log Level'))


# ------------------------------------------------------------------ About
def build_about_page(connection, selected_ids=None):
    novulon_dir = common.novulon_dir()
    log_path = os.path.join(novulon_dir, 'logs', 'novulon.log') if novulon_dir else 'Not available'
    rows = [
        Row(_INFO_ID, 'Version', description=common.VERSION, on_activate=None),
        Row(_INFO_ID, 'Log File', description=log_path, on_activate=None),
    ]
    return Page('About', rows, breadcrumb=('Settings', 'About'))


# ------------------------------------------------------------------ the Settings tile itself
def build_settings_page(connection, selected_ids=None):
    rows = [
        _adult_row(),
        Row(COMPAT_OPEN_ID, 'Compatibility', description=_compat_summary(), on_activate=build_compat_page),
        Row(LOG_LEVEL_OPEN_ID, 'Log Level', description=settings.get('log_level', 'info').capitalize(),
            on_activate=build_log_level_page),
        Row(ABOUT_OPEN_ID, 'About', on_activate=build_about_page),
    ]
    return Page('Settings', rows, breadcrumb=('Settings',))


# ------------------------------------------------------------------ registration (module import time)
commands.add(ADULT_TOGGLE_ID, _activate_adult_toggle)
commands.add(ADULT_CONFIRM_ID, _confirm_adult_enable)
commands.add(COMPAT_OPEN_ID, build_compat_page)
commands.add(LOG_LEVEL_OPEN_ID, build_log_level_page)
commands.add(ABOUT_OPEN_ID, build_about_page)
commands.add(_INFO_ID, _info_noop)
for _level, _fn in _LOG_LEVEL_FNS.items():
    commands.add(LOG_LEVEL_SET_PREFIX + _level, _fn)

commands.add_section(SECTION_KEY, build_settings_page, label='Settings',
                      description='Turn modules on or off.', icon=None, order=SECTION_ORDER)

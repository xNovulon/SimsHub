"""adult/menu.py - wires gate.py/settings.py/bridge.py/panic.py into the actual "Adult" Main Menu
tile (SPEC.md Sec.11's three V1 rows), built entirely on menukit (BP2) the same way every other
feature package is meant to: `Row`/`Page` objects and `menukit.show_page`, never a direct `ui.*`
import (this file has none).

Screen flow:
    Main Menu "Adult" tile (only present when gate.is_adult_section_available())
      -> not shown before: the one-time "Adults only" interstitial (settings.interstitial_shown())
      -> the front door: one row per bridge.SUBGROUPS entry, plus Stop Everything (MENU.md's own
         Adult row list - no separate "Resume Autonomy" row: turning autonomy back on after Stop
         Everything is the existing "Autonomy" toggle inside Autonomy & Refusal, not a new top-level
         row; `panic.resume_autonomy` stays reachable as `novulon.do novulon.adult.resume_autonomy`
         for the one-shot "put every switch back the way it was" case, without adding menu surface
         MENU.md never asked for)
           -> tapping a subgroup row opens its own page: one row per boolean WickedWhims setting,
              tapping a setting row flips it and re-renders the SAME page in place (menukit's own
              "mutate + rebuild, return None" pattern - see menukit/__init__.py's own docstring)

Every row's `on_activate` is registered under a stable `novulon.adult.*` action id via
`commands.add` at import time (SPEC.md Sec.3.7/Sec.4: "every row needs a command") - built once, in
the loops below, from `bridge.SUBGROUPS`, so this file never hand-writes one function per setting.
"""
from . import bridge, gate, panic
from . import settings as adult_settings
from .. import commands
from .. import menukit

TILE_LABEL = 'Adult'
TILE_DESCRIPTION = 'WickedWhims settings, one place.'


# ------------------------------------------------------------------ the interstitial (shown once)
def _interstitial_continue(connection, selected_ids=None):
    adult_settings.mark_interstitial_shown()
    return _front_door_page(connection)


def _interstitial_page():
    return menukit.Page(
        'Adults only',
        [menukit.Row('novulon.adult.interstitial.continue', 'Continue',
                      description='This section is for young adult and older Sims only.',
                      on_activate=_interstitial_continue)],
        breadcrumb=('Adult',))


commands.add('novulon.adult.interstitial.continue', _interstitial_continue)


# ------------------------------------------------------------------ Stop Everything / Resume Autonomy
def _stop_everything(connection, selected_ids=None):
    ok = panic.stop_everything(connection)
    if ok:
        menukit.notify('Stopped.', 'Sex autonomy is off. Resume it below when ready.')
    else:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
    menukit.show_page(connection, _front_door_page(connection), push=False)
    return None


def _resume_autonomy(connection, selected_ids=None):
    """Not on the front door page (MENU.md lists only "Stop Everything") - reachable as
    `novulon.do novulon.adult.resume_autonomy` for a one-shot "put every autonomy switch back",
    with the granular per-switch "Autonomy" row inside Autonomy & Refusal always available too."""
    ok = panic.resume_autonomy(connection)
    if ok:
        menukit.notify('Autonomy resumed.', 'Sex autonomy is back on.')
    else:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
    return None


commands.add('novulon.adult.stop_everything', _stop_everything)
commands.add('novulon.adult.resume_autonomy', _resume_autonomy)


# ------------------------------------------------------------------ one boolean setting row
def _setting_row(domain, key, label):
    action_id = 'novulon.adult.setting.%s.%s' % (domain, key)
    # The action id is registered unconditionally at import time (the loop below), regardless of
    # whether WickedWhims can actually answer right now - menukit requires every row's id to already
    # be a registered command (SPEC.md Sec.3.7/Sec.4), disabled or not, and `on_activate` is always
    # the literal same function that id is registered under (commands.py's own contract).
    handler = _TOGGLE_HANDLERS[action_id]
    value = bridge.get_setting(domain, key)
    if value is None:
        return menukit.Row(action_id, label, description='Not available',
                            disabled_text='WickedWhims setting not found', on_activate=handler)
    description = 'On' if value else 'Off'
    return menukit.Row(action_id, label, description=description, on_activate=handler)


def _make_toggle_handler(domain, key, group_key):
    def _handler(connection, selected_ids=None):
        bridge.toggle_setting(domain, key)
        menukit.show_page(connection, _subgroup_page(group_key)(connection), push=False)
        return None
    return _handler


def _subgroup_page(group_key):
    group = _SUBGROUPS_BY_KEY[group_key]

    def _build(connection, selected_ids=None):
        rows = [_setting_row(domain, key, label) for domain, key, label in group['settings']]
        return menukit.Page(group['label'], rows, breadcrumb=('Adult', group['label']))
    return _build


# ------------------------------------------------------------------ registration (import time)
_SUBGROUPS_BY_KEY = {group['key']: group for group in bridge.SUBGROUPS}
_TOGGLE_HANDLERS = {}
_GROUP_OPENERS = {}

for _group in bridge.SUBGROUPS:
    _opener = _subgroup_page(_group['key'])
    _GROUP_OPENERS[_group['key']] = _opener
    commands.add('novulon.adult.group.%s' % _group['key'], _opener)
    for _domain, _key, _label in _group['settings']:
        _action_id = 'novulon.adult.setting.%s.%s' % (_domain, _key)
        _handler = _make_toggle_handler(_domain, _key, _group['key'])
        _TOGGLE_HANDLERS[_action_id] = _handler
        commands.add(_action_id, _handler)
del _group, _opener, _domain, _key, _label, _action_id, _handler


# ------------------------------------------------------------------ the front door
def _front_door_page(connection, selected_ids=None):
    rows = []
    for group in bridge.SUBGROUPS:
        rows.append(menukit.Row(
            'novulon.adult.group.%s' % group['key'], group['label'],
            description='%d setting%s' % (len(group['settings']), '' if len(group['settings']) == 1 else 's'),
            on_activate=_GROUP_OPENERS[group['key']]))
    rows.append(menukit.Row('novulon.adult.stop_everything', 'Stop Everything',
                             description='Reset everyone here and turn off sex autonomy.',
                             on_activate=_stop_everything))
    return menukit.Page('Adult', rows, breadcrumb=('Adult',))


# ------------------------------------------------------------------ the Main Menu tile itself
def open_adult(connection, selected_ids=None):
    """The Adult tile's own `on_activate`/`novulon.menu.adult` body: the interstitial once, the
    front door every time after."""
    if not adult_settings.interstitial_shown():
        return _interstitial_page()
    return _front_door_page(connection)


# SPEC.md Sec.2's Main Menu order is Sims, Household, Gameplay, Cheats, Settings, Adult - Adult
# last. `commands.sections()` sorts by (order, key); every sibling package is expected to register
# at the default order=0, where alphabetical order would put 'adult' FIRST - a high, explicit order
# here is what actually keeps Adult last regardless of what order the other packages pick.
commands.add_section('adult', open_adult, label=TILE_LABEL, description=TILE_DESCRIPTION,
                      icon=None, order=90, is_visible=gate.is_adult_section_available)

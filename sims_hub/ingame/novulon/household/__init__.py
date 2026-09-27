"""Household & Money - registers the 'Household' Main Menu tile with core (SPEC.md §8, BP8).

Import-time only does two things, both guarded independently so a problem in one never costs the other:
register every row's action id with `commands.add()` (required before a `Page` containing that row can
ever be shown - `menukit/stack.py`'s own contract, see `commands.py`'s docstring) and register the tile
itself with `commands.add_section()`. No game import happens here - `menu.py`'s functions only touch the
game once a row is actually activated, same pattern as every other Novulon package.
"""
from .. import common
from . import menu

_ORDER = 20   # Sims (BP4) is expected at a lower order; Gameplay/Cheats (BP9) follow at 30/40.


def _register_actions():
    from .. import commands
    commands.add('novulon.household.funds', menu._household_funds_row)
    commands.add('novulon.household.personal_funds', menu._personal_funds_row)
    commands.add('novulon.household.purge_inventory', menu._purge_inventory_row)


def _register_section():
    from .. import commands
    commands.add_section('household', menu.household_root, label='Household',
                          description='Funds, needs, inventory.', icon=None, order=_ORDER)


common.guarded('novulon.household: register actions', _register_actions)
common.guarded('novulon.household: register section', _register_section)

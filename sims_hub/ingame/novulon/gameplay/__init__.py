"""Gameplay + Cheats - registers both Main Menu tiles with core (SPEC.md §9/§13, BP9).

Two tiles, one package, because SPEC.md §13 makes Cheats a thin reuse layer over `gameplay/menu.py`'s
(and `household/menu.py`'s) own functions - splitting it into a separate top-level package would either
duplicate those functions or force an import cycle the other way. `relationships` (BP10) is a third,
separate package (no tile of its own - SPEC.md §1.4/§9.4) imported lazily from `menu.py`'s Relationships
row so a circular import at module load time is never possible (relationships/__init__.py does not import
anything from gameplay/).
"""
from .. import common
from . import cheats, menu

_GAMEPLAY_ORDER = 30
_CHEATS_ORDER = 40


def _register_actions():
    from .. import commands
    for action_id, handler in menu.all_actions():
        commands.add(action_id, handler)
    for action_id, handler in cheats.all_actions():
        commands.add(action_id, handler)


def _register_sections():
    from .. import commands
    commands.add_section('gameplay', menu.gameplay_root, label='Gameplay',
                          description='Needs, skills, careers, and more.', icon=None,
                          order=_GAMEPLAY_ORDER)
    commands.add_section('cheats', cheats.cheats_root, label='Cheats',
                          description='Quick fixes, A to Z.', icon=None, order=_CHEATS_ORDER)


common.guarded('novulon.gameplay: register actions', _register_actions)
common.guarded('novulon.gameplay: register sections', _register_sections)

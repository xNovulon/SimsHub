"""Relationships (SPEC.md §9.4, BP10) - no Main Menu tile of its own; registers only its three row
actions with core so `gameplay/menu.py`'s "Relationships" row (and, eventually, a Sim Card quick action)
can push `relationships.menu.relationships_page` and have every row on it already satisfy `menukit`'s
"every row needs a registered command" rule.
"""
from .. import common
from . import menu


def _register_actions():
    from .. import commands
    for action_id, handler in menu.all_actions():
        commands.add(action_id, handler)


common.guarded('novulon.relationships: register actions', _register_actions)

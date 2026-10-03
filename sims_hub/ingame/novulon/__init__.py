"""Novulon - an in-game menu for The Sims 4, on every computer and tablet and on every Sim.

    Computer or tablet -> Novulon: the main menu (Sims, Household, Cheats, World, Settings, and Adult when it's on).
    A Sim -> Novulon: that Sim's own page.

When the game loads the mod this registers the two commands the pie-menu entries run and two hooks: after a lot
starts (add the entries to computers, tablets and Sims - one pass per game session) and on the game's main menu
(forget open menus). Nothing else runs until the menu is opened: no timers, no background work, no hooks on the
game's own simulation. Outside a Mods folder (tests, tools) it does nothing at all.
"""
from . import common


def _start():
    if not common.sims_dir():
        return
    from . import entry, settings
    settings.load()
    entry.register_commands()
    entry.install()
    common.log('Novulon %s started' % common.VERSION)


common.guarded('starting Novulon', _start)

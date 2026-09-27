"""Novulon - a Sims 4 script mod (Python 3.7, game build 109.0.465.1030): a browsable, filterable,
searchable Sim manager plus household/gameplay/cheats/settings tools, reached from a "Novulon" pie-menu
wedge on every computer and tablet.

  (a) common     - <Sims 4>\\Novulon\\ paths, logging, guarded(), a notification helper (common.py)
  (b) settings   - settings.json load/save/migration (settings.py)
  (c) commands   - the 'novulon.menu'/'novulon.do' cheats, the action registry, and the Main Menu
                   section registry every feature package registers its tile into (commands.py)
  (d) inject     - the computer/tablet pie-menu entry point (inject.py)

The game imports every .pyc in a .ts4script on its own (sims4.importer.utils.module_names_gen), so this
file runs first, the same way speedkit_monitor/__init__.py already does for that mod. Start-up does as
little as possible: load settings, install the computer-injection hooks, register the two cheats. Nothing
else runs until a player opens a computer/tablet or types a cheat. Every step is independent and guarded
(common.guarded) so one failing step never takes another down with it, and every failure goes to
Novulon\\logs\\novulon.log, never to the game. Outside a Mods folder (tests, tools, or another package's
own unit tests importing this module directly) sims_dir() is None and start-up does nothing at all.

Feature packages (sims/, household/, gameplay/, adult/, settings_ui/, ...) register their own Main Menu
tile with commands.add_section(...) at their own import time; this file does not know their names, only
that commands.build_main_menu_page() will find whatever is registered by the time a player opens the menu.
"""
from . import common

VERSION = common.VERSION


def _install_inject(inject):
    inject.install(inject.NOVULON_INTERACTION_ID)


def _start():
    if common.sims_dir() is None:                # not loaded from <Sims 4>\Mods: stay inert
        return
    try:
        from . import settings, hooks, commands, inject  # noqa: F401  (hooks: used by inject, imported
                                                           # here too so a broken hooks.py is caught and
                                                           # logged at start-up, not on first use)
    except Exception:
        common.log_exception('Novulon start-up (imports)')
        return
    # four independent steps: one failing must not also cost the others
    common.guarded('Novulon start-up (settings)', settings.load)
    common.guarded('Novulon start-up (commands)', commands.register)
    common.guarded('Novulon start-up (session reset hook)', commands.install_session_reset_hook)
    common.guarded('Novulon start-up (inject)', _install_inject, inject)
    common.log('Novulon %s started' % (VERSION,))


_start()

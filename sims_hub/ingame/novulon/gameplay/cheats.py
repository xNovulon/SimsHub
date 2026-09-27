"""Cheats tile - active-Sim/household shortcuts (SPEC.md §13, build package BP9).

"This tile duplicates no logic - every row calls the same function sims/actions.py, household/, or
gameplay/menu.py already expose, just defaulted to the active Sim/household" (SPEC.md §13, verbatim).
Every row below reuses a function `household.menu`/`gameplay.menu` already defines and registers under
its own action id - it is never re-implemented here, only called with the active Sim resolved by this
tile's own default-target policy (same `_active_sim_id` every other file in this build's `gameplay`/
`household` packages already uses).

**Cut, per the build override ("verify or cut")**: **Teleport to Me**. SPEC.md §5.5/§13 both list it, but
the only verified command that repositions a Sim, `sims.teleport <x> <y> <z> <level> [sim] [rotation]`
(`server_commands/sim_commands.pyc:911`, this session's own disassembly), takes raw world coordinates -
it does not take a target Sim to teleport *to*. Building "to me" would mean reading the active Sim's live
position/level/rotation from Python first, and no research pass (this one included) verified which
attributes expose that cleanly on a live `Sim` object. Shipping a guess at that shape is exactly what the
build override forbids; left out of the menu, flagged here for a v1.1 pass that can check it live.
"""
from .. import common
from ..household import menu as _household
from ..menukit import Row, Page, search as _search, notify as _notify
from . import menu as _gameplay

BREADCRUMB = ('Cheats',)


def _active_sim_id(connection):
    try:
        import services
        info = services.active_sim_info()
        return info.id if info is not None else None
    except Exception:
        return None


def _money_row(connection, selected_ids=None):
    sim_id = _active_sim_id(connection)
    if sim_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None

    def _got(text):
        if not text:
            return
        try:
            amount = int(str(text).strip())
        except ValueError:
            _notify('Nothing changed.', 'Type a whole number, e.g. 5000.', urgent=True)
            return
        _household.set_personal_funds(connection, sim_id, amount)
    _search.open_search_box(connection, None, _got, title='Money', text="Type the active Sim's new funds.")
    return None


def _fill_needs_row(connection, selected_ids=None):
    return _gameplay._needs_fill_active(connection, selected_ids)


def _max_skill_row(connection, selected_ids=None):
    return _gameplay._skills_max_all(connection, selected_ids)


def _reset_row(connection, selected_ids=None):
    sim_id = _active_sim_id(connection)
    if sim_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None
    _gameplay._exec(connection, 'sims.reset %s' % sim_id, 'Sim reset.')
    return None


def _age_up_row(connection, selected_ids=None):
    return _gameplay._life_age_up(connection, selected_ids)


def _age_down_row(connection, selected_ids=None):
    return _gameplay._life_age_down(connection, selected_ids)


def cheats_root(connection, selected_ids=None):
    return Page('Cheats', [
        Row('novulon.cheats.money', 'Money…', on_activate=_money_row),
        Row('novulon.cheats.fill_needs', 'Fill Needs', on_activate=_fill_needs_row),
        Row('novulon.cheats.max_skill', 'Max Skill', on_activate=_max_skill_row),
        Row('novulon.cheats.reset', 'Reset', on_activate=_reset_row),
        Row('novulon.cheats.age_up', 'Age Up', on_activate=_age_up_row),
        Row('novulon.cheats.age_down', 'Age Down', on_activate=_age_down_row),
    ], breadcrumb=BREADCRUMB)


def all_actions():
    return [
        ('novulon.cheats.money', _money_row),
        ('novulon.cheats.fill_needs', _fill_needs_row),
        ('novulon.cheats.max_skill', _max_skill_row),
        ('novulon.cheats.reset', _reset_row),
        ('novulon.cheats.age_up', _age_up_row),
        ('novulon.cheats.age_down', _age_down_row),
    ]

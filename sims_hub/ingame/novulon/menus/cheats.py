"""Cheats: the quick ones for the Sim being played - no typing, no testingcheats needed."""
from .. import actions, game, ui


def build(conn):
    me = game.active_sim_info()
    if me is None:
        return ui.Page('Cheats', [ui.info('No Sim is selected.', icon='warning')])
    from . import household, simcard
    rows = [
        ui.Row('Money', lambda c: household.money_page, icon='money'),
        ui.Row('Fill needs', _on_me(actions.fill_needs, 'Needs are full.'), icon='fill'),
        ui.Row('Fill everyone\'s needs', lambda c: household.fill_all(c), icon='fill', desc='The whole household'),
        ui.Row('Max all skills', _on_me(actions.max_skills, 'Every skill is maxed.'), icon='trophy'),
        ui.Row('Complete the aspiration milestone', _on_me(actions.complete_milestone, 'Milestone done.'), icon='aspiration'),
        ui.Row('Reset', _on_me(actions.reset, 'Reset.'), icon='reset', desc='Unstuck: stops what the Sim is doing'),
        ui.Row('Everything else for %s' % game.first_name(me), lambda c: simcard.builder(me.id), icon='card'),
    ]
    return ui.Page('Cheats', rows, subtitle='For %s' % game.name(me), icon='cheats')


def _on_me(fn, ok_text):
    def action(conn):
        me = game.active_sim_info()
        if me is None:
            return ui.STAY
        worked, msg = fn(me)
        ui.notify(game.name(me), msg or ok_text, icon='check' if worked else 'warning')
        return ui.STAY
    return action

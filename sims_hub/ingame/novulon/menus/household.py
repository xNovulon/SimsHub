"""Household: the active household's money, everyone's needs, the members, and clearing out the inventory."""
from .. import actions, game, ui


def build(conn):
    hh = game.active_household()
    if hh is None:
        return ui.Page('Household', [ui.info('No household is being played right now.', icon='warning')])
    members = game.sort_by_name(actions.members(hh))
    rows = [
        ui.Row('Money', lambda c: money_page, icon='money', desc='§%s' % format(actions.funds(hh), ',')),
        ui.Row('Fill everyone\'s needs', fill_all, icon='fill', desc='%d Sims' % len(members)),
    ]
    from . import simcard
    for si in members:
        rows.append(ui.Row(game.name(si), (lambda c, i=si.id: simcard.builder(i)), icon='user', desc=game.summary(si)))
    rows.append(ui.Row("Empty the Sims' inventories", _purge, icon='inventory', desc='Everything the Sims on this lot carry'))
    return ui.Page(getattr(hh, 'name', '') or 'Household', rows, icon='household')


def money_page(conn):
    hh = game.active_household()
    amount = actions.funds(hh) if hh is not None else 0
    rows = [ui.Row('Add §%s' % format(n, ','), _add(n), icon='plus') for n in (1000, 10000, 50000, 100000)]
    rows += [ui.Row('Set an amount', _set_amount, icon='edit', desc='Type exactly how much'),
             ui.Row('Take it all away', lambda c: _confirm_zero(c), icon='minus', desc='Down to §0')]
    return ui.Page('Money', rows, subtitle='The household has §%s.' % format(amount, ','), icon='money')


def _add(n):
    def action(conn):
        hh = game.active_household()
        worked, msg = actions.add_funds(hh, n) if hh is not None else (False, 'No household.')
        ui.notify('Money', msg, icon='money' if worked else 'warning')
        return ui.STAY
    return action


def _set_amount(conn):
    hh = game.active_household()
    if hh is None:
        return None

    def done(c, value):
        h = game.active_household()
        if h is not None:
            worked, msg = actions.set_funds(h, value)
            ui.notify('Money', msg, icon='money' if worked else 'warning')
        ui.show(c)
    ui.ask_number(conn, 'Set an amount', 'How many Simoleons should the household have?', done,
                  initial=actions.funds(hh), minimum=0, maximum=99999999, icon='money')
    return None


def _confirm_zero(conn):
    def yes(c):
        h = game.active_household()
        if h is not None:
            actions.set_funds(h, 0)
            ui.notify('Money', 'The household has §0.', icon='money')
        ui.show(c)
    ui.confirm(conn, 'Take it all away', 'The household\'s money goes down to §0.', yes)
    return None


def fill_all(conn):
    hh = game.active_household()
    n = sum(1 for si in actions.members(hh) if actions.fill_needs(si)[0]) if hh is not None else 0
    ui.notify('Household', 'Needs filled for %d Sims.' % n, icon='fill')
    return ui.STAY


def _purge(conn):
    def yes(c):
        h = game.active_household()
        worked, msg = actions.empty_inventories(h) if h is not None else (False, 'No household.')
        ui.notify('Household', msg, icon='inventory' if worked else 'warning')
        ui.show(c)
    ui.confirm(conn, "Empty the Sims' inventories", 'Everything in the Sims\' own inventories on this lot is deleted. '
                                                      'This can\'t be undone.', yes, ok='Empty it', icon='inventory')
    return None

"""The main menu (computers and tablets): big tiles, one per part of Novulon."""
from .. import compat, game, settings, ui


def adult_tile_shown():
    """The Adult tile: turned on in Settings, WickedWhims installed, the Sim at the computer is an adult, and no mods
    for sexual content with minors installed."""
    return (bool(settings.get('adult_enabled')) and compat.wickedwhims_present() and not compat.adult_blocked()
            and game.is_adult_human(game.active_sim_info()))


def build(conn):
    from . import simcard, sims, household, cheats, world, settings_page, adult
    me = game.active_sim_info()
    hh = game.active_household()
    rows = [
        ui.Row('My Sim', (lambda c: simcard.builder(me.id)) if me is not None else None, icon='user',
               desc=game.name(me) if me is not None else '', reason='No Sim is selected.'),
        ui.Row('Sims', lambda c: sims.build, icon='sims', desc='Everyone in your world'),
        ui.Row('Household', lambda c: household.build, icon='household',
               desc=(getattr(hh, 'name', '') or 'Your household') if hh is not None else 'Your household'),
        ui.Row('Cheats', lambda c: cheats.build, icon='cheats', desc='Money, needs and skills'),
        ui.Row('World', lambda c: world.build, icon='world', desc='Time and autonomy'),
        ui.Row('Settings', lambda c: settings_page.build, icon='settings', desc='Novulon options'),
    ]
    if adult_tile_shown():
        rows.append(ui.Row('Adult', adult.entry, icon='adult', desc='WickedWhims settings'))
    sub = 'Playing as %s' % game.name(me) if me is not None else ''
    return ui.Page('Novulon', rows, subtitle=sub, style='tiles')

"""Sims: everyone in the world, by group or by name, shown in the game's own Sim picker (portraits).

Picking one Sim opens that Sim's page (simcard.py). "Several Sims at once" picks a whole group with ticks, then shows
what can be done to all of them. A group bigger than PICKER_MAX is split by first-name letters first, so the picker
never has to draw hundreds of portraits at once.
"""
from .. import game, ui

PICKER_MAX = 100
STAGES = [('Teens', (8,)), ('Young adults', (16,)), ('Adults', (32,)), ('Elders', (64,)),
          ('Children', (4,)), ('Toddlers', (2,)), ('Infants and babies', (1, 128))]


def groups():
    """[(title, icon, sims)] - computed when the page is drawn, so the counts are always current."""
    everyone = game.all_sim_infos()
    humans = [s for s in everyone if game.is_human(s)]
    me = game.active_household()
    hh_id = getattr(me, 'id', None)
    return [
        ('Everyone', 'sims', humans),
        ('Women', 'female', [s for s in humans if game.is_female(s)]),
        ('Men', 'male', [s for s in humans if game.is_male(s)]),
        ('My household', 'household', [s for s in everyone if hh_id is not None and getattr(s, 'household_id', None) == hh_id]),
        ('On this lot', 'here', [s for s in everyone if game.instanced(s) is not None]),
        ('Played households', 'played', [s for s in humans if not getattr(s, 'is_npc', True)]),
        ('Pets', 'pets', [s for s in everyone if not game.is_human(s)]),
    ]


def build(conn):
    rows = [ui.Row(title, (lambda c, t=title, l=sims: browse(c, t, l)), icon=icon, desc=_count(sims))
            for title, icon, sims in groups()]
    rows.insert(1, ui.Row('Find by name', _search, icon='search', desc='Type part of a name'))
    rows.append(ui.Row('By life stage', lambda c: stages_page, icon='age'))
    rows.append(ui.Row('Several Sims at once', lambda c: several_page, icon='select',
                       desc='Tick a group of Sims and do something to all of them'))
    return ui.Page('Sims', rows, icon='sims')


def _count(sims):
    n = len(sims)
    return '%d Sim%s' % (n, '' if n == 1 else 's')


def stages_page(conn):
    humans = [s for s in game.all_sim_infos() if game.is_human(s)]
    rows = []
    for title, ages in STAGES:
        sims = [s for s in humans if game.age_value(s) in ages]
        rows.append(ui.Row(title, (lambda c, t=title, l=sims: browse(c, t, l)), icon='age', desc=_count(sims)))
    return ui.Page('By life stage', rows, icon='age')


def several_page(conn):
    rows = [ui.Row(title, (lambda c, t=title, l=sims: browse(c, t, l, several=True)), icon=icon, desc=_count(sims))
            for title, icon, sims in groups()]
    return ui.Page('Several Sims at once', rows, subtitle='Pick a group, then tick the Sims.', icon='select')


def _search(conn):
    def found(c, typed):
        if not typed:
            return
        q = typed.lower()
        sims = [s for s in game.all_sim_infos() if q in game.name(s).lower()]
        if not sims:
            ui.notify('Find by name', 'No Sim is called "%s".' % typed, icon='search')
            return
        open_picker(c, 'Sims called "%s"' % typed, sims)
    ui.ask_text(conn, 'Find by name', 'Type part of a first or last name.', found, icon='search')
    return None


def browse(conn, title, sims, several=False):
    """A group: straight into the picker (nothing new on the page stack), or - when it's big - a page of name ranges."""
    sims = game.sort_by_name(sims)
    if len(sims) <= PICKER_MAX:
        open_picker(conn, title, sims, several)
        return None
    return letter_ranges(title, sims, several)


def letter_ranges(title, sims, several):
    """Sims in name order cut into ranges of at most PICKER_MAX, labelled by the first letters they cover."""
    chunks = [sims[i:i + PICKER_MAX] for i in range(0, len(sims), PICKER_MAX)]

    def build_ranges(conn):
        rows = []
        for chunk in chunks:
            a = (game.first_name(chunk[0])[:1] or '?').upper()
            b = (game.first_name(chunk[-1])[:1] or '?').upper()
            label = a if a == b else '%s to %s' % (a, b)
            rows.append(ui.Row(label, (lambda c, l=chunk, lb=label: open_picker(c, '%s · %s' % (title, lb), l, several)),
                               icon='sims', desc=_count(chunk)))
        return ui.Page(title, rows, subtitle='%s - pick a range of names.' % _count(sims), icon='sims')
    return build_ranges


def open_picker(conn, title, sims, several=False):
    from . import simcard
    if several:
        def picked_many(c, chosen):
            if chosen:
                ui.push(c, simcard.several_builder([s.id for s in chosen]))
        ui.pick_sims(conn, title, sims, picked_many, subtitle='Tick the Sims, then press OK.', multi=True)
    else:
        def picked_one(c, chosen):
            if chosen:
                ui.push(c, simcard.builder(chosen[0].id))
        ui.pick_sims(conn, title, sims, picked_one)

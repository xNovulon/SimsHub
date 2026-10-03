"""A Sim's own page - what a Sim's "Novulon" pie entry opens, and where picking a Sim anywhere in Novulon leads.

The page is built for a Sim id, never a stored SimInfo, so it always shows the Sim as they are now (and says so when
the Sim is gone). Everything it does is in actions.py, shared with Cheats and Household. Romance and pregnancy rows
only show for young adult or older humans, with an adult partner (game.is_adult_human).
"""
from .. import actions, game, obsession, ui


def builder(sim_id):
    def build(conn):
        si = game.sim_info_by_id(sim_id)
        if si is None:
            return ui.Page('Sim', [ui.info('This Sim is no longer in the world.', icon='warning')])
        return _page(si)
    return build


def _done(title, text, icon='check'):
    """After an action: a short note in the corner, and the page drawn again."""
    ui.notify(title, text, icon=icon)
    return ui.STAY


def _act(sim_id, fn, ok_text, icon='check'):
    """A row action running fn(SimInfo) -> (worked, message)."""
    def action(conn):
        si = game.sim_info_by_id(sim_id)
        if si is None:
            return _done('Novulon', 'This Sim is no longer in the world.', 'warning')
        worked, message = fn(si)
        return _done(game.name(si), message or ok_text, icon if worked else 'warning')
    return action


def _page(si):
    sid = si.id
    human, adult = game.is_human(si), game.is_adult_human(si)
    me = game.active_sim_info()
    rows = [
        ui.Row('Edit in Create a Sim', lambda c: actions.open_cas(game.sim_info_by_id(sid), c), icon='cas'),
        ui.Row('Fill needs', _act(sid, actions.fill_needs, 'Needs are full.'), icon='fill'),
        ui.Row('Needs and moodlets', lambda c: needs_page(sid), icon='needs'),
    ]
    if human:
        rows += [
            ui.Row('Skills', lambda c: skills_page(sid), icon='skills'),
            ui.Row('Career', lambda c: career_page(sid), icon='career',
                   desc=actions.career_summary(si)),
            ui.Row('Traits', lambda c: traits_page(sid), icon='traits'),
            ui.Row('Aspiration', lambda c: aspiration_page(sid), icon='aspiration'),
            ui.Row('Age', lambda c: age_page(sid), icon='age', desc=game.age_name(si)),
            ui.Row('Occult', lambda c: occult_page(sid), icon='occult', desc=actions.occult_summary(si)),
        ]
        if me is not None and me.id != sid:
            rows.append(ui.Row('Relationship with %s' % game.first_name(me), lambda c: relationship_page(sid),
                               icon='heart'))
        if adult:
            rows.append(ui.Row('Pregnancy', lambda c: pregnancy_page(sid), icon='pregnancy',
                               desc='Pregnant' if actions.is_pregnant(si) else ''))
            rows.append(ui.Row('Obsession', lambda c: obsession_page(sid), icon='heart',
                               desc=obsession.LEVEL_NAMES[obsession.level(si)]))
    rows += [
        ui.Row('Household', lambda c: household_page(sid), icon='household', desc=game.household_name(si) or 'No household'),
        ui.Row('Bring here', _act(sid, actions.teleport_to_active, 'Here now.'), icon='teleport',
               enabled=game.instanced(si) is not None and me is not None and me.id != sid,
               reason='Only Sims on this lot can be brought next to your Sim.'),
        ui.Row('Reset', _act(sid, actions.reset, 'Reset.'), icon='reset', desc='Unstuck: stops what the Sim is doing'),
        ui.Row('Delete', lambda c: _delete(c, sid), icon='delete', enabled=actions.can_delete(si),
               reason=actions.why_not_deletable(si)),
    ]
    return ui.Page(game.name(si), rows, subtitle=game.summary(si), sim=si)


# ------------------------------------------------------------------ needs and moodlets
def needs_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        if si is None:
            return builder(sid)(conn)
        here = game.instanced(si) is not None
        rows = [ui.Row('Fill all needs', _act(sid, actions.fill_needs, 'Needs are full.'), icon='fill')]
        for need in actions.needs_of(si):
            rows.append(ui.Row(need['name'], (lambda c, n=need: _set_need(c, sid, n)), icon=need['icon'] or 'needs',
                               desc='%d%%' % need['percent']))
        rows += [ui.Row('Add a moodlet', lambda c: _add_moodlet(c, sid), icon='moodlet', enabled=here,
                        reason='Moodlets can only be changed for Sims on this lot.'),
                 ui.Row('Remove a moodlet', lambda c: moodlets_page(sid), icon='minus', enabled=here,
                        reason='Moodlets can only be changed for Sims on this lot.')]
        return ui.Page('Needs and moodlets', rows, subtitle=game.name(si), sim=si)
    return build


def _set_need(conn, sid, need):
    def done(c, value):
        si = game.sim_info_by_id(sid)
        if si is not None:
            worked, msg = actions.set_need(si, need['value'], value)
            ui.notify(game.name(si), msg, icon='check' if worked else 'warning')
        ui.show(c)
    ui.ask_number(conn, need['name'], 'How full, from 0 to 100?', done, initial=need['percent'], minimum=0, maximum=100)
    return None


def _add_moodlet(conn, sid):
    def found(c, typed):
        si = game.sim_info_by_id(sid)
        if not typed or si is None:
            ui.show(c)
            return
        matches = actions.find_buffs(typed, si)
        if not matches:
            ui.notify('Add a moodlet', 'No moodlet matches "%s".' % typed, icon='search')
            ui.show(c)
            return
        ui.push(c, ui.choose('Moodlets matching "%s"' % typed,
                             [(m['name'], m['value'], '', m['icon'] or 'moodlet') for m in matches],
                             lambda cc, b: _act(sid, lambda s: actions.add_buff(s, b), 'Moodlet added.')(cc),
                             subtitle='Pick one to add.'))
    ui.ask_text(conn, 'Add a moodlet', 'Type part of a moodlet\'s name, like "happy" or "energized".', found,
                icon='moodlet')
    return None


def moodlets_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row(m['name'], (lambda c, b=m['value']: _act(sid, lambda s: actions.remove_buff(s, b),
                                                                 'Moodlet removed.')(c)),
                       icon=m['icon'] or 'moodlet') for m in (actions.buffs_of(si) if si else [])]
        if not rows:
            rows = [ui.info('No moodlets to remove.')]
        return ui.Page('Remove a moodlet', rows, subtitle='Pick one to remove.', sim=si)
    return build


# ------------------------------------------------------------------ skills
def skills_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row('Max all skills', _act(sid, actions.max_skills, 'Every skill is maxed.'), icon='trophy'),
                ui.Row('Set any skill', lambda c: all_skills_page(sid), icon='skills', desc='Every skill this Sim can have')]
        for skill in (actions.skills_of(si) if si else []):
            rows.append(ui.Row(skill['name'], (lambda c, s=skill: _set_skill(c, sid, s)), icon=skill['icon'] or 'skills',
                               desc='Level %d of %d' % (skill['level'], skill['max'])))
        rows.append(ui.Row('Clear all skills', lambda c: _confirm_act(c, sid, 'Clear all skills', 'Every skill goes back '
                                                                     'to nothing. This can\'t be undone.',
                                                                     actions.clear_skills, 'Skills cleared.'),
                           icon='clear'))
        return ui.Page('Skills', rows, sim=si)
    return build


def all_skills_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row(s['name'], (lambda c, s=s: _set_skill(c, sid, s)), icon=s['icon'] or 'skills',
                       desc='Level %d of %d' % (s['level'], s['max'])) for s in actions.all_skills(si)]
        return ui.Page('Set any skill', rows or [ui.info('No skills found.')], subtitle='Pick a skill, then a level.',
                       sim=si)
    return build


def _set_skill(conn, sid, skill):
    def done(c, level):
        si = game.sim_info_by_id(sid)
        if si is not None:
            worked, msg = actions.set_skill(si, skill['value'], level)
            ui.notify(game.name(si), msg, icon='check' if worked else 'warning')
        ui.show(c)
    ui.ask_number(conn, skill['name'], 'Which level, from 0 to %d?' % skill['max'], done,
                  initial=skill.get('level', 0), minimum=0, maximum=skill['max'], icon='skills')
    return None


# ------------------------------------------------------------------ career
def career_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        jobs = actions.careers_of(si) if si else []
        rows = [ui.Row('Join a career', lambda c: join_career_page(sid), icon='career')]
        for job in jobs:
            rows.append(ui.Row(job['name'], (lambda c, j=job: job_page(sid, j['value'])), icon=job['icon'] or 'career',
                               desc=job['title'] or 'Level %d' % job['level']))
        return ui.Page('Career', rows, subtitle='No job yet.' if not jobs else 'Pick a job to change it.', sim=si)
    return build


def job_page(sid, uid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        job = next((j for j in (actions.careers_of(si) if si else []) if j['value'] == uid), None)
        if job is None:
            return career_page(sid)(conn)
        rows = [
            ui.Row('Promote', _act(sid, lambda s: actions.promote(s, uid), 'Promoted.'), icon='age_up'),
            ui.Row('Demote', _act(sid, lambda s: actions.demote(s, uid), 'Demoted.'), icon='age_down'),
            ui.Row('Add a day off', _act(sid, lambda s: actions.add_pto(s, uid, 1), 'A day off added.'), icon='time'),
            ui.Row('Leave this job', lambda c: _confirm_act(c, sid, 'Leave this job', 'The Sim quits this job.',
                                                            lambda s: actions.quit_career(s, uid), 'Left the job.',
                                                            after=ui.back), icon='clear'),
        ]
        return ui.Page(job['name'], rows, subtitle=job['title'] or 'Level %d' % job['level'], sim=si)
    return build


def join_career_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row(c['name'], (lambda cc, car=c['value']: _act(sid, lambda s: actions.add_career(s, car),
                                                                     'Joined.')(cc)), icon=c['icon'] or 'career')
                for c in actions.all_careers(si)]
        return ui.Page('Join a career', rows or [ui.info('No careers this Sim can join.')], sim=si)
    return build


# ------------------------------------------------------------------ traits
def traits_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        free = actions.trait_slots_free(si) if si else 0
        rows = [ui.Row('Add a trait', lambda c: add_trait_page(sid), icon='plus', enabled=free > 0,
                       reason=actions.TRAIT_SLOTS_FULL, desc='%d free slot%s' % (free, '' if free == 1 else 's'))]
        for t in (actions.personality_traits(si) if si else []):
            rows.append(ui.Row(t['name'], _act(sid, lambda s, tr=t['value']: actions.remove_trait(s, tr), 'Trait removed.'),
                               icon=t['icon'] or 'traits', desc='Pick to remove'))
        return ui.Page('Traits', rows, subtitle='Personality traits only - hidden game traits are left alone.', sim=si)
    return build


def add_trait_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row(t['name'], (lambda c, tr=t['value']: _act(sid, lambda s: actions.add_trait(s, tr),
                                                                  'Trait added.')(c)),
                       icon=t['icon'] or 'traits') for t in (actions.addable_traits(si) if si else [])]
        return ui.Page('Add a trait', rows or [ui.info('No traits to add.')], subtitle='Only traits that fit this Sim.',
                       sim=si)
    return build


# ------------------------------------------------------------------ aspiration, age, occult
def aspiration_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row('Complete the current milestone', _act(sid, actions.complete_milestone, 'Milestone done.'),
                       icon='check'),
                ui.Row('Start the aspiration over', lambda c: _confirm_act(c, sid, 'Start the aspiration over',
                       'All aspiration progress is cleared. This can\'t be undone.', actions.reset_aspiration,
                       'Aspiration starts over.'), icon='reset')]
        return ui.Page('Aspiration', rows, sim=si)
    return build


def age_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = [ui.Row('Age up', _act(sid, actions.age_up, 'Aged up.'), icon='age_up',
                       enabled=si is not None and game.age_value(si) != 64, reason='Elders are the last life stage.'),
                ui.Row('Age down', _act(sid, actions.age_down, 'Aged down.'), icon='age_down',
                       enabled=si is not None and game.age_value(si) not in (1, 128),
                       reason='Already the youngest life stage.')]
        return ui.Page('Age', rows, subtitle=game.age_name(si) if si else '', sim=si)
    return build


def occult_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        rows = []
        for o in actions.occult_types():
            if si is not None and actions.has_occult(si, o['value']):
                rows.append(ui.Row('Stop being a %s' % o['name'],
                                   _act(sid, lambda s, v=o['value']: actions.remove_occult(s, v), 'Done.'),
                                   icon='occult', desc='Is a %s now' % o['name']))
            else:
                rows.append(ui.Row('Turn into a %s' % o['name'],
                                   _act(sid, lambda s, v=o['value']: actions.add_occult(s, v), 'Done.'), icon='occult'))
        return ui.Page('Occult', rows or [ui.info('No occult types in this game.')], sim=si)
    return build


# ------------------------------------------------------------------ relationship with the active Sim
def relationship_page(sid):
    def build(conn):
        si, me = game.sim_info_by_id(sid), game.active_sim_info()
        if si is None or me is None:
            return ui.Page('Relationship', [ui.info('Both Sims need to be in the world.', icon='warning')])
        both_adults = game.is_adult_human(si) and game.is_adult_human(me) and not actions.related(si, me)
        rows = [
            ui.Row('Make friends', _rel(sid, 'friendship', 50, 'Friends now.'), icon='friends'),
            ui.Row('Make best friends', _rel(sid, 'friendship', 100, 'Best friends now.'), icon='friends'),
            ui.Row('Make enemies', _rel(sid, 'friendship', -100, 'Enemies now.'), icon='warning'),
        ]
        if both_adults:
            rows += [ui.Row('Fall in love', _rel(sid, 'romance', 100, 'In love now.'), icon='heart'),
                     ui.Row('Clear the romance', _rel(sid, 'romance', 0, 'No romance now.'), icon='clear')]
        rows.append(ui.Row('Back to neutral', _rel(sid, 'neutral', 0, 'Back to neutral.'), icon='reset'))
        sub = '%s and %s' % (game.first_name(me), game.first_name(si))
        if not both_adults:
            sub += ' · romance is only for adult Sims who aren\'t family'
        return ui.Page('Relationship', rows, subtitle=sub, sim=si)
    return build


def _rel(sid, kind, value, ok_text):
    def action(conn):
        si, me = game.sim_info_by_id(sid), game.active_sim_info()
        if si is None or me is None:
            return _done('Relationship', 'Both Sims need to be in the world.', 'warning')
        if kind == 'romance' and not (game.is_adult_human(si) and game.is_adult_human(me) and not actions.related(si, me)):
            return _done('Relationship', 'Romance is only for adult Sims who aren\'t family.', 'warning')
        worked, msg = actions.set_relationship(me, si, kind, value)
        return _done('%s and %s' % (game.first_name(me), game.first_name(si)), msg or ok_text,
                     'heart' if worked else 'warning')
    return action


# ------------------------------------------------------------------ obsession (adults only)
def obsession_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        if si is None or not game.is_adult_human(si):
            return ui.Page('Obsession', [ui.info('Only for young adult and older Sims.', icon='warning')])
        now = obsession.level(si)

        def pick(value):
            return _act(sid, lambda s: obsession.set_level(s, value), '', icon='heart')
        rows = [
            ui.Row('Off', pick(obsession.OFF), icon='off', selected=now == obsession.OFF),
            ui.Row('Obsessed', pick(obsession.OBSESSED), icon='heart', selected=now == obsession.OBSESSED,
                   desc='Whoever sees %s finds them perfect and comes over now and then.' % game.first_name(si)),
            ui.Row('Extremely obsessed', pick(obsession.EXTREME), icon='heart', selected=now == obsession.EXTREME,
                   desc='More often, and they go after anyone %s talks to.' % game.first_name(si)),
        ]
        n = len(obsession.fans_of(si))
        sub = '%d Sim%s obsessed so far' % (n, '' if n == 1 else 's') if n else 'No one has seen %s yet' % game.first_name(si)
        return ui.Page('Obsession', rows, subtitle=sub, sim=si)
    return build


# ------------------------------------------------------------------ pregnancy (adults only)
def pregnancy_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        if si is None or not game.is_adult_human(si):
            return ui.Page('Pregnancy', [ui.info('Only for young adult and older Sims.', icon='warning')])
        if actions.is_pregnant(si):
            rows = [ui.Row('End the pregnancy', lambda c: _confirm_act(c, sid, 'End the pregnancy', 'The pregnancy ends '
                                                                     'with no baby.', actions.clear_pregnancy,
                                                                     'No longer pregnant.'), icon='clear')]
        else:
            rows = [ui.Row('Get pregnant with...', lambda c: _pick_partner(c, sid), icon='pregnancy',
                           desc='Pick an adult partner who isn\'t family')]
        return ui.Page('Pregnancy', rows, sim=si)
    return build


def _pick_partner(conn, sid):
    si = game.sim_info_by_id(sid)
    if si is None:
        return None
    partners = [p for p in game.all_sim_infos()
                if p.id != sid and game.is_adult_human(p) and not actions.related(si, p)]

    def picked(c, chosen):
        s = game.sim_info_by_id(sid)
        if s is not None and chosen and game.is_adult_human(s) and game.is_adult_human(chosen[0]) \
                and not actions.related(s, chosen[0]):
            worked, msg = actions.start_pregnancy(s, chosen[0])
            ui.notify(game.name(s), msg, icon='pregnancy' if worked else 'warning')
        ui.show(c)
    ui.pick_sims(conn, 'Pick the other parent', game.sort_by_name(partners), picked)
    return None


# ------------------------------------------------------------------ household
def household_page(sid):
    def build(conn):
        si = game.sim_info_by_id(sid)
        if si is None:
            return builder(sid)(conn)
        mine = game.in_active_household(si)
        controlled = actions.is_controlled(si)
        rows = [
            ui.Row('Move into my household', lambda c: _confirm_act(c, sid, 'Move into my household',
                   '%s moves into your household.' % game.first_name(si), actions.add_to_active_household, 'Moved in.'),
                   icon='join', enabled=not mine, reason='Already in your household.'),
            ui.Row('Take out of my Sims bar' if controlled else 'Add to my Sims bar',
                   _act(sid, actions.release if controlled else actions.control,
                        'Out of your Sims bar.' if controlled else 'Now in your Sims bar.'),
                   icon='npc' if controlled else 'playable', enabled=not mine,
                   desc='Play this Sim without moving them in',
                   reason='Sims in your household are always in your Sims bar.'),
        ]
        return ui.Page('Household', rows, subtitle=game.household_name(si) or 'No household', sim=si)
    return build


# ------------------------------------------------------------------ delete
def _delete(conn, sid):
    si = game.sim_info_by_id(sid)
    if si is None:
        return None

    def yes(c):
        s = game.sim_info_by_id(sid)
        if s is not None:
            worked, msg = actions.delete(s)
            ui.notify('Delete', msg, icon='delete' if worked else 'warning')
        ui.back(c)
    ui.confirm(conn, 'Delete %s?' % game.name(si), '%s is removed from the world for good. This can\'t be undone.'
               % game.name(si), yes, ok='Delete', icon='delete')
    return None


def _confirm_act(conn, sid, title, text, fn, ok_text, after=None):
    def yes(c):
        si = game.sim_info_by_id(sid)
        if si is not None:
            worked, msg = fn(si)
            ui.notify(game.name(si), msg or ok_text, icon='check' if worked else 'warning')
        (after or ui.show)(c)
    ui.confirm(conn, title, text, yes, ok='OK')
    return None


# ------------------------------------------------------------------ several Sims at once
def several_builder(sim_ids):
    def build(conn):
        sims = [s for s in (game.sim_info_by_id(i) for i in sim_ids) if s is not None]
        rows = [
            ui.Row('Fill needs', lambda c: _many(c, sim_ids, actions.fill_needs, 'Needs filled'), icon='fill'),
            ui.Row('Reset', lambda c: _many(c, sim_ids, actions.reset, 'Reset'), icon='reset'),
            ui.Row('Delete', lambda c: _delete_many(c, sim_ids), icon='delete',
                   enabled=any(actions.can_delete(s) for s in sims), reason='None of these Sims can be deleted.'),
        ]
        names = ', '.join(game.first_name(s) for s in sims[:6]) + (' and %d more' % (len(sims) - 6) if len(sims) > 6 else '')
        return ui.Page('%d Sims' % len(sims), rows, subtitle=names, icon='select')
    return build


def _many(conn, sim_ids, fn, verb):
    done = 0
    for i in sim_ids:
        si = game.sim_info_by_id(i)
        if si is not None and fn(si)[0]:
            done += 1
    return _done('Novulon', '%s: %d of %d Sims.' % (verb, done, len(sim_ids)))


def _delete_many(conn, sim_ids):
    sims = [s for s in (game.sim_info_by_id(i) for i in sim_ids) if s is not None and actions.can_delete(s)]
    if not sims:
        return None
    shown = ', '.join(game.name(s) for s in sims[:10]) + (' and %d more' % (len(sims) - 10) if len(sims) > 10 else '')

    def yes(c):
        n = sum(1 for s in sims if actions.delete(s)[0])
        ui.notify('Delete', '%d Sims deleted.' % n, icon='delete')
        ui.back(c)
    ui.confirm(conn, 'Delete %d Sims?' % len(sims), '%s. They are removed from the world for good. This can\'t be undone.'
               % shown, yes, ok='Delete', icon='delete')
    return None

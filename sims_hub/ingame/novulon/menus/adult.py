"""Adult: a short list of WickedWhims' own on/off settings, changed through WickedWhims' own functions (compat.py).

Only reachable from the main menu's Adult tile (main.adult_tile_shown: turned on in Settings, WickedWhims installed,
and the Sim at the computer is a young adult or older). It never picks or targets a Sim, and it never shows any of
WickedWhims' teen settings. Only settings whose value is a real on/off (a bool) can be switched here; anything else
is shown as it is, read-only, so a number or choice setting is never overwritten with True/False.
"""
from .. import compat, game, settings, ui

GROUPS = [
    ('Autonomy', 'autonomy', [
        ('sex', 'autonomy_switch', 'Autonomy'),
        ('sex', 'sex_autonomy_random_switch', 'Random autonomy'),
        ('sex', 'sex_autonomy_romance_switch', 'Romantic autonomy'),
        ('sex', 'sex_autonomy_random_solo_switch', 'Solo autonomy'),
        ('sex', 'sex_autonomy_watch_switch', 'Watching'),
        ('sex', 'join_sex_autonomy_switch', 'Joining'),
        ('sex', 'player_join_sex_autonomy_switch', 'Played Sims joining'),
    ]),
    ('Where it can happen', 'teleport', [
        ('sex', 'sex_autonomy_club_switch', 'In clubs'),
        ('sex', 'autonomy_sex_business_state', 'In businesses'),
        ('sex', 'change_sex_location_anywhere', 'Anywhere'),
    ]),
    ('Relationships', 'heart', [
        ('relationship', 'desire_switch', 'Desire'),
        ('relationship', 'sex_cheating_buffs', 'Cheating moodlets'),
        ('relationship', 'attractiveness_system_state', 'Attractiveness'),
    ]),
    ('Pregnancy', 'pregnancy', [
        ('sex', 'pregnancy_menstrual_cycle', 'Menstrual cycle'),
    ]),
    ('Social feed', 'friends', [
        ('nudity', 'simhub_state_new', 'Social feed'),
    ]),
]


def allowed():
    return compat.wickedwhims_present() and not compat.adult_blocked() and game.is_adult_human(game.active_sim_info())


def entry(conn):
    """The Adult tile: a one-time note first, then the settings."""
    if not allowed():
        ui.notify('Adult', 'This is for young adult and older Sims, with WickedWhims installed.', icon='warning')
        return None
    if not settings.get('adult_notice_seen'):
        def seen(c):
            settings.set('adult_notice_seen', True)
            ui.push(c, build)
        ui.confirm(conn, 'Adult', 'These are WickedWhims\' own settings. They only ever apply to young adult and '
                                  'older Sims.', seen, ok='Continue', icon='adult')
        return None
    return build


def build(conn):
    rows = [ui.Row(title, (lambda c, g=g: group_page(g)), icon=icon) for title, icon, g in GROUPS]
    rows.append(ui.Row('Stop everything', _stop_all, icon='stop', desc='Turns all WickedWhims autonomy off'))
    return ui.Page('Adult', rows, icon='adult')


def group_page(group):
    def build_group(conn):
        title = next(t for t, _i, g in GROUPS if g is group)
        rows = []
        for domain, key, label in group:
            value = compat.ww_get(domain, key)
            if isinstance(value, bool):
                rows.append(ui.Row('%s: %s' % (label, 'On' if value else 'Off'),
                                   (lambda c, d=domain, k=key, v=value: _set(d, k, not v)),
                                   icon='on' if value else 'off'))
            else:
                rows.append(ui.info(label, ('Set to %s - change it in WickedWhims\' own settings' % value)
                                    if value is not None else 'Not available'))
        return ui.Page(title, rows, icon='adult')
    return build_group


def _set(domain, key, value):
    if not allowed():
        return ui.BACK
    compat.ww_set(domain, key, value)
    return ui.STAY


def _stop_all(conn):
    if not allowed():
        return ui.BACK
    changed = 0
    for domain, key, _label in GROUPS[0][2]:
        if isinstance(compat.ww_get(domain, key), bool) and compat.ww_set(domain, key, False):
            changed += 1
    ui.notify('Adult', 'WickedWhims autonomy is off (%d settings).' % changed, icon='stop')
    return ui.STAY

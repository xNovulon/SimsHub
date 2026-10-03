"""Obsession: a Sim everyone falls for. Switched on per Sim on their own page (Novulon -> Obsession).

Who falls for them: every young adult or older human who is romantically attracted to their gender (the game's own
SimInfo.get_attracted_genders(GenderPreferenceType.ROMANTIC)) and isn't family (actions.related). Never children or
teens, on either side.

  OBSESSED  They find the Sim perfect: their turn-ons and turn-offs stop counting (Lovestruck's attraction track,
            AttractionTuning.ATTRACTION_RELATIONSHIP_TRACK, goes to its top) and they fall for them - romance and
            friendship rise every check until both are full - and they feel Enamored (the game's long-term
            sentiment, added by its own loot).
  EXTREME   All of that at once and kept at the top, and they are jealous: whenever the Sim is in a conversation with
            anyone else, every one of them on the lot gets the game's jealous moodlet and likes that other Sim less.

How it runs: nothing at all until a Sim's switch is on. Then a check every CHECK_MINUTES Sim minutes looks at the Sims
on the current lot (an alarm started once each lot has loaded - Zone.on_loading_screen_animation_finished - and right
away when a switch is turned on), and one wrapper on the game's attraction update
(AttractionService._update_attraction_value): after the game works an attraction out, an obsessed Sim's attraction to
the Sim they're obsessed with is set back to the top, so turn-ons and turn-offs never pull it down.

The switches are kept in Novulon's settings (settings.json, 'obsession': {Sim id: level}).
"""
from . import actions, common, game, hooks, settings

OFF, OBSESSED, EXTREME = 0, 1, 2
LEVEL_NAMES = {OFF: 'Off', OBSESSED: 'Obsessed', EXTREME: 'Extremely obsessed'}
CHECK_MINUTES = 10
ROMANCE_STEP = 10           # OBSESSED: romance and friendship rise this much every check, up to full
FRIENDSHIP_STEP = 5
RIVAL_STEP = 5              # EXTREME: friendship lost with whoever the Sim is talking to, every check
JEALOUS_BUFF = 'Buff_Jealousy_LoveInterest'
ENAMORED_LOOT = 'loot_Sentiment_AddSentiment_Enamored_generic_LT'


class _AlarmOwner:
    """The alarm's owner (the game keeps a weak reference to it)."""


_owner = _AlarmOwner()
_alarm = None
_enamored = set()           # (fan id, Sim id): the sentiment was given this session
_tuning = {}                # tuning name -> class (or None), looked up once


# ------------------------------------------------------------------ the switches
def _all():
    v = settings.get('obsession')
    return v if isinstance(v, dict) else {}


def level(sim_info):
    if sim_info is None:
        return OFF
    try:
        return int(_all().get(str(sim_info.id), OFF))
    except Exception:
        return OFF


def set_level(sim_info, value):
    """Turn a Sim's obsession to OFF, OBSESSED or EXTREME. -> (worked, message)"""
    if value not in LEVEL_NAMES:
        return False, 'Unknown level.'
    if value != OFF and not game.is_adult_human(sim_info):
        return False, 'Only for young adult and older Sims.'
    data = dict(_all())
    if value == OFF:
        data.pop(str(sim_info.id), None)
    else:
        data[str(sim_info.id)] = value
    settings.set('obsession', data)
    if value == OFF:
        return True, 'No one is obsessed with %s now.' % game.first_name(sim_info)
    start()
    common.guarded('obsession check', check)
    return True, ('Everyone into %s\'s gender falls for them.' if value == OBSESSED
                  else 'Everyone into %s\'s gender is madly in love with them.') % game.first_name(sim_info)


def idols():
    """[(SimInfo, level)] of every Sim whose switch is on and who is still in the world."""
    out = []
    for sid, lvl in _all().items():
        si = game.sim_info_by_id(sid)
        if si is not None and lvl in (OBSESSED, EXTREME) and game.is_adult_human(si):
            out.append((si, lvl))
    return out


# ------------------------------------------------------------------ who falls for whom
def attracted_to(fan, idol):
    """Is fan romantically attracted to idol's gender (the game's own orientation)?"""
    try:
        from sims.global_gender_preference_tuning import GenderPreferenceType
        return idol.gender in fan.get_attracted_genders(GenderPreferenceType.ROMANTIC)
    except Exception:
        return False


def is_fan(fan, idol):
    return (fan is not None and idol is not None and fan.id != idol.id
            and game.is_adult_human(fan) and game.is_adult_human(idol)
            and attracted_to(fan, idol) and not actions.related(fan, idol))


# ------------------------------------------------------------------ the game's pieces
def _named(resource_type, name):
    key = (resource_type, name)
    if key not in _tuning:
        _tuning[key] = next((t for t in actions._types(resource_type) if getattr(t, '__name__', '') == name), None)
    return _tuning[key]


def _top(track):
    v = getattr(track, 'max_value', None)
    v = v() if callable(v) else v
    return v if isinstance(v, (int, float)) else 100


def _tracks():
    from relationships.relationship_track import RelationshipTrack
    return RelationshipTrack.ROMANCE_TRACK, RelationshipTrack.FRIENDSHIP_TRACK


def _attraction_track():
    try:
        from relationships.attraction_tuning import AttractionTuning
        return AttractionTuning.ATTRACTION_RELATIONSHIP_TRACK
    except Exception:
        return None


def _raise(rs, a, b, track, step):
    """Raise a and b's track by step (or to the top for step None), never above it, never lowering it."""
    top = _top(track)
    now = rs.get_relationship_score(a.id, b.id, track)
    now = now if isinstance(now, (int, float)) else 0
    want = top if step is None else min(top, now + step)
    if want > now:
        rs.set_relationship_score(a.id, b.id, want, track)


def _perfect(fan, idol):
    """Turn-ons and turn-offs stop counting: fan's attraction to idol goes to the top (Lovestruck; else nothing)."""
    import services
    track = _attraction_track()
    if track is None or services.get_attraction_service() is None:
        return
    services.relationship_service().set_relationship_score(fan.id, idol.id, _top(track), track)


def _enamor(fan, idol):
    if (fan.id, idol.id) in _enamored:
        return
    _enamored.add((fan.id, idol.id))
    import sims4.resources
    from event_testing.resolver import DoubleSimResolver
    loot = _named(sims4.resources.Types.ACTION, ENAMORED_LOOT)
    if loot is not None:
        loot.apply_to_resolver(DoubleSimResolver(fan, idol))


def fall_for(fan, idol, lvl):
    """One check of one fan for one idol."""
    import services
    rs = services.relationship_service()
    romance, friendship = _tracks()
    _perfect(fan, idol)
    if lvl == EXTREME:
        _raise(rs, fan, idol, romance, None)
        _raise(rs, fan, idol, friendship, None)
    else:
        _raise(rs, fan, idol, romance, ROMANCE_STEP)
        _raise(rs, fan, idol, friendship, FRIENDSHIP_STEP)
    _enamor(fan, idol)


def _jealous(fans_here, idol_sim):
    """EXTREME: the idol is talking with someone - every fan on the lot gets jealous and likes that someone less."""
    import services
    import sims4.resources
    group = idol_sim.get_main_group()
    if group is None:
        return
    talking = [s for s in group if s is not idol_sim]
    if not talking:
        return
    buff = _named(sims4.resources.Types.BUFF, JEALOUS_BUFF)
    rs = services.relationship_service()
    _, friendship = _tracks()
    for fan_sim in fans_here:
        others = [s for s in talking if s is not fan_sim]
        if not others:
            continue
        if buff is not None and not fan_sim.has_buff(buff):
            fan_sim.debug_add_buff_by_type(buff)
        for other in others:
            if other.sim_info is not None and other.sim_info.id != fan_sim.sim_info.id:
                rs.add_relationship_score(fan_sim.sim_info.id, other.sim_info.id, -RIVAL_STEP, friendship)


# ------------------------------------------------------------------ the check
def check(*_):
    """Every Sim on the lot who is attracted to an obsession's gender falls for them (and, at EXTREME, gets jealous)."""
    ids = idols()
    if not ids:
        return
    import services
    here = [s for s in services.sim_info_manager().instanced_sims_gen() if getattr(s, 'sim_info', None) is not None]
    for idol, lvl in ids:
        fans_here = []
        for sim in here:
            fan = sim.sim_info
            if is_fan(fan, idol):
                common.guarded('obsession %s' % game.first_name(fan), fall_for, fan, idol, lvl)
                fans_here.append(sim)
        idol_sim = game.instanced(idol)
        if lvl == EXTREME and idol_sim is not None and fans_here:
            common.guarded('obsession jealousy', _jealous, fans_here, idol_sim)


def _after_attraction(args, result):
    """After the game works out actor -> target attraction: an obsessed fan's goes back to the top."""
    if len(args) < 3:
        return
    actor_id, target_id = args[1], args[2]
    if str(target_id) not in _all():
        return
    idol, fan = game.sim_info_by_id(target_id), game.sim_info_by_id(actor_id)
    if level(idol) != OFF and is_fan(fan, idol):
        _perfect(fan, idol)


# ------------------------------------------------------------------ running
def start():
    """The check every CHECK_MINUTES Sim minutes on this lot, and the attraction wrapper - only while a switch is on."""
    global _alarm
    if not _all():
        return
    _wrap_attraction()
    if _alarm is not None:
        return
    import alarms
    from date_and_time import create_time_span
    _alarm = alarms.add_alarm(_owner, create_time_span(minutes=CHECK_MINUTES),
                              lambda handle: common.guarded('obsession check', check), repeating=True)


def _wrap_attraction():
    try:
        from relationships.attraction_tuning import AttractionService
    except Exception:
        return
    hooks.install(AttractionService, '_update_attraction_value',
                  lambda orig: hooks.around(orig, after=_after_attraction, label='novulon obsession attraction'),
                  'AttractionService._update_attraction_value (novulon obsession)')


def _lot_loaded():
    """A new lot: the old lot's alarm went with it - start a fresh one (and check right away)."""
    global _alarm
    _alarm = None
    _enamored.clear()
    if _all():
        start()
        check()


def install():
    """Once, when the mod starts: start the check whenever a lot has finished loading."""
    import zone
    hooks.install(zone.Zone, 'on_loading_screen_animation_finished',
                  lambda orig: hooks.around(orig, after=lambda a, r: common.guarded('obsession lot', _lot_loaded),
                                            label='novulon obsession lot'),
                  'Zone.on_loading_screen_animation_finished (novulon obsession)')

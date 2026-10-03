"""Obsession: a Sim everyone is obsessed with. Switched on per Sim on their own page (Novulon -> Obsession).

Who is obsessed with them: every young adult or older human who is romantically attracted to their gender (the game's
own SimInfo.get_attracted_genders(GenderPreferenceType.ROMANTIC)) and isn't family (actions.related). Never children
or teens, on either side.

Nothing about their relationship is touched: no friendship, no romance, no sentiments - they stay strangers until the
game's own socials make them anything else, and the Sim they're obsessed with answers them as they normally would (a
flirt from someone they aren't into is turned down the usual way). The one thing changed is the fans' own one-way
attraction to the Sim (Lovestruck's AttractionTuning.ATTRACTION_RELATIONSHIP_TRACK, fan -> Sim): it is kept at its top,
so their turn-ons and turn-offs stop counting - the Sim is perfect in their eyes. The Sim's attraction to them is left
alone.

  OBSESSED  They come after the Sim now and then to flirt, and whenever the Sim is in a conversation with anyone else
            they get the game's jealous moodlet.
  EXTREME   They chase the Sim every check, storm over to yell at or send away anyone the Sim talks to, and now and
            then two of them fight each other over the Sim.

What they do is pushed the way the game pushes a reaction mixer (interactions/utils/reactions.pyc ReactionMixer): the
game's own social mixers (flirt, compliment, kiss on the cheek; yell at, go away; fight) under the sim_Chat
conversation, through autonomy.content_sets.get_valid_aops_gen, which starts the conversation first when there is
none - the game's own tests still decide whether each one can happen, and its own outcomes decide how it goes. Sims in
the player's Sims bar are never pushed.

How it runs: nothing at all until a Sim's switch is on. Then a check every CHECK_MINUTES Sim minutes looks at the Sims
on the current lot (an alarm started once each lot has loaded - Zone.on_loading_screen_animation_finished - and right
away when a switch is turned on), and one wrapper on the game's attraction update
(AttractionService._update_attraction_value): after the game works an attraction out, a fan's attraction to the Sim
goes back to the top.

The switches are kept in Novulon's settings (settings.json, 'obsession': {Sim id: level}).
"""
import random

from . import actions, common, game, hooks, settings

OFF, OBSESSED, EXTREME = 0, 1, 2
LEVEL_NAMES = {OFF: 'Off', OBSESSED: 'Obsessed', EXTREME: 'Extremely obsessed'}
CHECK_MINUTES = 10
CHASE_CHANCE = {OBSESSED: 0.35, EXTREME: 1.0}   # each check, a fan who isn't with the Sim comes over to flirt
CONFRONT_CHANCE = 0.6       # EXTREME: a jealous fan storms over to the one the Sim is talking to
FIGHT_CHANCE = 0.12         # EXTREME: two fans on the lot fight each other over the Sim
JEALOUS_BUFF = 'Buff_Jealousy_LoveInterest'
CHAT = 'sim_Chat'
FLIRTS = ('mixer_social_Flirt_targeted_romance_alwaysOn', 'mixer_social_ComplimentAppearance_targeted_romance_alwaysOn',
          'mixer_social_KissCheek_targeted_romance_alwaysOn')
CONFRONTS = ('mixer_social_YellAT_targeted_mean', 'mixer_social_GoAway_targeted_mean_alwaysOn')
FIGHT = 'mixer_social_Fight_targeted_mean'


class _AlarmOwner:
    """The alarm's owner (the game keeps a weak reference to it)."""


_owner = _AlarmOwner()
_alarm = None
_tuning = {}                # (resource type, tuning name) -> class (or None), looked up once
_roll = random.random       # the dice (tests replace them)
_pick = random.choice


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
    name = game.first_name(sim_info)
    if value == OFF:
        return True, 'No one is obsessed with %s now.' % name
    start()
    common.guarded('obsession check', check)
    return True, ('Everyone into %s\'s gender is obsessed with them.' if value == OBSESSED
                  else 'Everyone into %s\'s gender is madly obsessed with them.') % name


def idols():
    """[(SimInfo, level)] of every Sim whose switch is on and who is still in the world."""
    out = []
    for sid, lvl in _all().items():
        si = game.sim_info_by_id(sid)
        if si is not None and lvl in (OBSESSED, EXTREME) and game.is_adult_human(si):
            out.append((si, lvl))
    return out


# ------------------------------------------------------------------ who is obsessed
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


def _attraction_track():
    try:
        from relationships.attraction_tuning import AttractionTuning
        return AttractionTuning.ATTRACTION_RELATIONSHIP_TRACK
    except Exception:
        return None


def perfect(fan, idol):
    """Turn-ons and turn-offs stop counting: fan's own one-way attraction to idol goes to its top (Lovestruck; without
    it there is no attraction to change). Nothing else between them changes."""
    import services
    track = _attraction_track()
    if track is None or services.get_attraction_service() is None:
        return
    services.relationship_service().set_relationship_score(fan.id, idol.id, _top(track), track)


def _jealous_mood(sim):
    import sims4.resources
    buff = _named(sims4.resources.Types.BUFF, JEALOUS_BUFF)
    if buff is not None and not sim.has_buff(buff):
        sim.debug_add_buff_by_type(buff)


def _push(sim, target, mixer_name, extreme):
    """Push one of the game's social mixers on sim toward target, as the game pushes a reaction mixer: under the
    sim_Chat conversation they are in, or one started for it first. -> True when the game took it."""
    import sims4.resources
    from autonomy.content_sets import get_valid_aops_gen
    from interactions.context import InteractionContext, InteractionSource
    from interactions.priority import Priority
    mixer = _named(sims4.resources.Types.INTERACTION, mixer_name)
    chat = _named(sims4.resources.Types.INTERACTION, CHAT)
    if mixer is None or chat is None:
        return False
    si = next(iter(sim.running_interactions_gen(chat)), None)
    context = InteractionContext(sim, InteractionSource.SCRIPT, Priority.High if extreme else Priority.Low)
    for aop, result in get_valid_aops_gen(target, mixer, chat, si, context, False, push_super_on_prepare=si is None):
        if result and aop.test_and_execute(context):
            return True
    return False


def _pushable(sim):
    """A fan the mod may send somewhere: not one the player plays."""
    return not actions.is_controlled(sim.sim_info) and not game.in_active_household(sim.sim_info)


# ------------------------------------------------------------------ what they do
def _jealous(fan_sim, rivals, lvl):
    """The Sim is talking with rivals: fan_sim is jealous - and at EXTREME may storm over. -> True when they went."""
    _jealous_mood(fan_sim)
    if lvl == EXTREME and _pushable(fan_sim) and _roll() < CONFRONT_CHANCE:
        return _push(fan_sim, _pick(rivals), _pick(CONFRONTS), True)
    return False


def _fight(fans_here):
    """EXTREME: two fans on the lot fight each other over the Sim (yelling, when the game won't let them fight)."""
    free = [s for s in fans_here if _pushable(s)]
    if len(free) < 2 or _roll() >= FIGHT_CHANCE:
        return False
    a = _pick(free)
    b = _pick([s for s in fans_here if s is not a])
    for s in (a, b):
        _jealous_mood(s)
    return _push(a, b, FIGHT, True) or _push(a, b, CONFRONTS[0], True)


def _act_out(idol_sim, fans_here, lvl):
    """What fans on the lot do about the Sim this check: jealousy at whoever the Sim talks to, chasing, fighting."""
    group = idol_sim.get_main_group()
    with_idol = [s for s in group if s is not idol_sim] if group is not None else []
    for fan_sim in fans_here:
        rivals = [s for s in with_idol if s is not fan_sim]
        if rivals and common.guarded('obsession jealousy', _jealous, fan_sim, rivals, lvl):
            continue
        if fan_sim in with_idol or not _pushable(fan_sim):
            continue
        if _roll() < CHASE_CHANCE[lvl]:
            common.guarded('obsession chase', _push, fan_sim, idol_sim, _pick(FLIRTS), lvl == EXTREME)
    if lvl == EXTREME:
        common.guarded('obsession fight', _fight, fans_here)


# ------------------------------------------------------------------ the check
def check(*_):
    """Every Sim on the lot who is attracted to an obsession's gender finds them perfect, chases them, gets jealous."""
    ids = idols()
    if not ids:
        return
    import services
    here = [s for s in services.sim_info_manager().instanced_sims_gen() if getattr(s, 'sim_info', None) is not None]
    for idol, lvl in ids:
        fans_here = []
        for sim in here:
            if is_fan(sim.sim_info, idol):
                common.guarded('obsession %s' % game.first_name(sim.sim_info), perfect, sim.sim_info, idol)
                fans_here.append(sim)
        idol_sim = game.instanced(idol)
        if idol_sim is not None and fans_here:
            common.guarded('obsession acting out', _act_out, idol_sim, fans_here, lvl)


def _after_attraction(args, result):
    """After the game works out actor -> target attraction: a fan's goes back to the top."""
    if len(args) < 3:
        return
    actor_id, target_id = args[1], args[2]
    if str(target_id) not in _all():
        return
    idol, fan = game.sim_info_by_id(target_id), game.sim_info_by_id(actor_id)
    if level(idol) != OFF and is_fan(fan, idol):
        perfect(fan, idol)


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

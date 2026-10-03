"""Everything Novulon changes in the game, in one place. Each change returns (worked, message) - the message is what
the corner notification says - and never raises: a failure is logged and reported as (False, message).

No console commands. Most of the game's cheats are DebugOnly, Automation or Cheat commands that refuse to run without
testingcheats, so every change here calls the game's own objects directly - the exact calls those cheats make,
read from this game build (server_commands/*.pyc, careers/career_tuning.pyc, objects/components/buff_component.pyc):

  needs        sim_info.commodity_tracker.set_all_commodities_to_best_value(visible_only=True)
  traits       sim_info.add_trait / remove_trait; the list is trait_tracker.can_add_trait(trait, True)
  skills       commodity_tracker.add_statistic + set_user_value; the list is STATISTIC all_skills_gen() + can_add
  careers      career_tracker.add_career(Career(sim_info)), get_career_by_uid(uid).promote() / demote() / add_pto();
               the join list is the career service's list filtered the way the phone's own join list does
  moodlets     sim.debug_add_buff_by_type / remove_buff_by_type, sim.get_active_buff_types() (Sim on the lot)
  age          sim_info.callback_auto_age() / reverse_age()
  occult       sim_info.occult_tracker.add_occult_type / remove_occult_type / has_occult_type
  pregnancy    sim_info.pregnancy_tracker.start_pregnancy(sim_info, partner) / clear_pregnancy()
  relationship relationship_tracker.set_relationship_score(id, value, RelationshipTrack.FRIENDSHIP_TRACK / ROMANCE_TRACK)
  family test  sim_info.incest_prevention_test(other) - the game's own "may these two be romantic" check
  household    household_manager().switch_sim_household(sim_info, None, reason=HouseholdChangeOrigin.CHEAT)
  control      client.add_selectable_sim_info / remove_selectable_sim_info
  money        household.funds.add / try_remove(amount, Consts_pb2.TELEMETRY_MONEY_CHEAT)
  time         game_clock_service().set_game_time(h, 0, 0), then sim_info_manager().auto_satisfy_sim_motives()
  autonomy     autonomy_service().global_autonomy_settings.set_setting(AutonomyState, AutonomySettingsGroup.DEFAULT)
  aspiration   aspiration_tracker: the same milestone loop as aspirations.complete_current_milestone; reset_data()
  Create a Sim client_cheat('sims.exit2caswithhouseholdid <sim> <household>') - what the game's own "Modify in CAS" sends

Lists (traits, skills, moodlets, careers) are dicts {'name', 'icon', 'value', 'search'}: name is the game's own
translated name (a game string) or a readable fallback, icon its own icon, search a lower-case text from the tuning
name for sorting and typing a search.

Age rule: nothing romantic or adult is ever offered to, or done to, anyone younger than a young adult. Moodlets and
traits that look adult are left out of the lists for younger Sims (_looks_adult), on top of the game's own tests.
"""
import re

from . import common, deleting, game

TRAIT_SLOTS_FULL = 'All personality trait slots are full. Remove a trait first.'
ADULT_WORDS = ('ww_', 'wicked', 'woohoo', 'horny', 'arous', 'sex', 'nsfw', 'nude', 'naked', 'romance', 'romantic',
               'flirt', 'lust', 'kink', 'turbodriver', 'pregnan', 'attraction', 'desire')
FIND_LIMIT = 60
OCCULT_NAMES = {'ALIEN': 'Alien', 'VAMPIRE': 'Vampire', 'MERMAID': 'Mermaid', 'WITCH': 'Spellcaster',
                'WEREWOLF': 'Werewolf', 'FAIRY': 'Fairy'}
_PREFIXES = {'trait', 'traits', 'buff', 'buffs', 'statistic', 'skill', 'skills', 'adultmajor', 'adultminor', 'major',
             'minor', 'career', 'careers', 'commodity', 'motive', 'motives', 'visible'}


def _safe(where, fn, failed='That didn\'t work. The details are in Novulon\'s log.'):
    """fn() -> (worked, message); any exception is logged and becomes (False, failed)."""
    try:
        return fn()
    except Exception:
        common.log_exception(where)
        return False, failed


# ------------------------------------------------------------------ names and lists
def pretty(tuning):
    """A readable name from a tuning class name: 'trait_HotHeaded' -> 'Hot Headed'."""
    n = getattr(tuning, '__name__', '') or str(tuning)
    parts = [p for p in re.split(r'[_\-\s]+', n) if p]
    keep = [p for p in parts if p.lower() not in _PREFIXES] or parts
    return ' '.join(re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', p) for p in keep).strip() or n


def text(value, *tokens):
    """A game string from a tuned name: a string factory is called with the tokens, a string is used as it is.
    None when there's no string."""
    if value is None:
        return None
    try:
        s = value(*tokens) if callable(value) else value
    except Exception:
        return None
    if s is None or not getattr(s, 'hash', 1):
        return None
    return s


def _item(tuning, name=None, icon=None, **extra):
    d = {'name': name if name is not None else pretty(tuning), 'icon': icon, 'value': tuning,
         'search': (pretty(tuning) + ' ' + (getattr(tuning, '__name__', '') or '')).lower()}
    d.update(extra)
    return d


def _sorted(items):
    return sorted(items, key=lambda d: d['search'])


def _types(resource_type):
    import services
    mgr = services.get_instance_manager(resource_type)
    return list(mgr.types.values()) if mgr is not None else []


def _looks_adult(tuning):
    n = (getattr(tuning, '__name__', '') or '').lower()
    mod = (getattr(tuning, '__module__', '') or '').lower()
    return any(w in n or w in mod for w in ADULT_WORDS)


def _allowed_for(sim_info, tuning):
    return game.is_adult_human(sim_info) or not _looks_adult(tuning)


# ------------------------------------------------------------------ needs
def fill_needs(sim_info):
    def go():
        sim_info.commodity_tracker.set_all_commodities_to_best_value(visible_only=True)
        return True, 'Needs are full.'
    return _safe('fill needs', go)


def _visible(stat):
    v = getattr(stat, 'is_visible', None)
    if v is None:
        v = getattr(stat, 'visible', False)
    if callable(v):
        v = v()
    return bool(v)


def _range(stat):
    lo = getattr(stat, 'min_value', None)
    hi = getattr(stat, 'max_value', None)
    if lo is None or hi is None:
        lo, hi = getattr(stat, 'min_value_tuning', -100), getattr(stat, 'max_value_tuning', 100)
    return float(lo), float(hi)


def needs_of(sim_info):
    """[{'name', 'icon', 'value' (the commodity type), 'percent'}] for the needs the game shows."""
    out = []
    try:
        for stat in list(sim_info.commodity_tracker):
            if getattr(stat, 'is_skill', False) or not _visible(stat):
                continue
            t = type(stat)
            lo, hi = _range(stat)
            pct = int(round((stat.get_value() - lo) * 100.0 / (hi - lo))) if hi > lo else 0
            out.append(_item(t, text(getattr(t, 'stat_name', None)), getattr(t, 'icon', None),
                             percent=max(0, min(100, pct))))
    except Exception:
        common.log_exception('needs list')
    return _sorted(out)


def set_need(sim_info, stat_type, percent):
    def go():
        tracker = sim_info.get_tracker(stat_type) or sim_info.commodity_tracker
        stat = tracker.get_statistic(stat_type)
        lo, hi = _range(stat if stat is not None else stat_type)
        tracker.set_value(stat_type, lo + (hi - lo) * max(0, min(100, percent)) / 100.0)
        return True, 'Set to %d%%.' % percent
    return _safe('set need', go)


# ------------------------------------------------------------------ moodlets (the Sim must be on the lot)
def _buff_item(buff, sim_info):
    return _item(buff, text(getattr(buff, 'buff_name', None), sim_info), getattr(buff, 'icon', None))


def buffs_of(sim_info):
    sim = game.instanced(sim_info)
    if sim is None:
        return []
    try:
        return _sorted(_buff_item(b, sim_info) for b in sim.get_active_buff_types() if getattr(b, 'visible', True))
    except Exception:
        common.log_exception('moodlet list')
        return []


def find_buffs(typed, sim_info):
    """Moodlets the game shows (visible, named) whose name contains what was typed - at most FIND_LIMIT."""
    import sims4.resources
    words = typed.lower().split()
    found = []
    for buff in _types(sims4.resources.Types.BUFF):
        try:
            if not getattr(buff, 'visible', False) or text(getattr(buff, 'buff_name', None), sim_info) is None:
                continue
            item = _buff_item(buff, sim_info)
            if all(w in item['search'] for w in words) and _allowed_for(sim_info, buff):
                found.append(item)
        except Exception:
            continue
    return _sorted(found)[:FIND_LIMIT]


def add_buff(sim_info, buff):
    sim = game.instanced(sim_info)
    if sim is None:
        return False, 'Moodlets can only be given to Sims on this lot.'
    if not _allowed_for(sim_info, buff):
        return False, 'That moodlet is only for adults.'

    def go():
        if hasattr(buff, 'can_add') and not buff.can_add(sim_info):
            return False, 'The game doesn\'t allow that moodlet for this Sim.'
        sim.debug_add_buff_by_type(buff)
        return True, 'Moodlet added.'
    return _safe('add moodlet', go)


def remove_buff(sim_info, buff):
    sim = game.instanced(sim_info)
    if sim is None:
        return False, 'Moodlets can only be changed for Sims on this lot.'

    def go():
        if not sim.has_buff(buff):
            return False, 'That moodlet is already gone.'
        sim.remove_buff_by_type(buff)
        return True, 'Moodlet removed.'
    return _safe('remove moodlet', go)


# ------------------------------------------------------------------ skills
def _skill_item(t, **extra):
    return _item(t, text(getattr(t, 'stat_name', None)), getattr(t, 'icon', None),
                 max=int(getattr(t, 'max_level', 10) or 10), **extra)


def _all_skill_types():
    import services
    import sims4.resources
    mgr = services.get_instance_manager(sims4.resources.Types.STATISTIC)
    return list(mgr.all_skills_gen()) if mgr is not None else []


def _can_have(skill_type, sim_info):
    if getattr(skill_type, 'hidden', False):
        return False
    try:
        return bool(skill_type.can_add(sim_info))
    except Exception:
        return False


def skills_of(sim_info):
    out = []
    try:
        for stat in list(sim_info.commodity_tracker):
            t = type(stat)
            if getattr(stat, 'is_skill', False) and not getattr(t, 'hidden', False):
                out.append(_skill_item(t, level=int(stat.get_user_value())))
    except Exception:
        common.log_exception('skill list')
    return _sorted(out)


def all_skills(sim_info):
    """Every skill this Sim can have (the game's own can_add: age, species, packs)."""
    if sim_info is None:
        return []
    have = {d['value']: d['level'] for d in skills_of(sim_info)}
    return _sorted(_skill_item(t, level=have.get(t, 0)) for t in _all_skill_types() if _can_have(t, sim_info))


def _set_level(sim_info, skill_type, level):
    tracker = sim_info.commodity_tracker
    stat = tracker.get_statistic(skill_type) or tracker.add_statistic(skill_type)
    if stat is None:
        return False
    tracker.set_user_value(skill_type, level)
    return True


def set_skill(sim_info, skill_type, level):
    def go():
        if not _set_level(sim_info, skill_type, level):
            return False, 'This Sim can\'t have that skill.'
        return True, 'Level %d.' % level
    return _safe('set skill', go)


def max_skills(sim_info):
    def go():
        n = sum(1 for t in _all_skill_types()
                if _can_have(t, sim_info) and _set_level(sim_info, t, int(getattr(t, 'max_level', 10) or 10)))
        return (n > 0), ('%d skills maxed.' % n if n else 'No skills this Sim can have.')
    return _safe('max skills', go)


def clear_skills(sim_info):
    def go():
        tracker = sim_info.commodity_tracker
        gone = [type(s) for s in list(tracker) if getattr(s, 'is_skill', False)]
        for t in gone:
            tracker.remove_statistic(t)
        return True, '%d skills cleared.' % len(gone)
    return _safe('clear skills', go)


# ------------------------------------------------------------------ careers
def careers_of(sim_info):
    """[{'name', 'title', 'icon', 'value' (the career's uid), 'level'}] for the Sim's jobs."""
    out = []
    try:
        for uid, career in dict(getattr(sim_info, 'careers', None) or {}).items():
            track = getattr(career, 'current_track_tuning', None)
            level = getattr(career, 'current_level_tuning', None)
            name = text(getattr(track, 'career_name', None), sim_info) if track is not None else None
            title = text(getattr(level, 'title', None), sim_info) if level is not None else None
            d = _item(type(career), name, getattr(track, 'icon', None), title=title,
                      level=int(getattr(career, 'user_level', 0) or 0))
            d['value'] = uid
            out.append(d)
    except Exception:
        common.log_exception('career list')
    return out


def career_summary(sim_info):
    jobs = careers_of(sim_info)
    if not jobs:
        return 'No job'
    if len(jobs) == 1:
        return jobs[0]['title'] or 'Level %d' % jobs[0]['level']
    return '%d jobs' % len(jobs)


def all_careers(sim_info):
    """The careers this Sim can join now - the same tests as the phone's own join list."""
    if sim_info is None:
        return []
    import services
    out = []
    try:
        careers = list(services.get_career_service().get_shuffled_career_list())
    except Exception:
        common.log_exception('career service')
        return []
    tracker = sim_info.career_tracker
    for c in careers:
        try:
            if not getattr(c, 'show_career_in_join_career_picker', True):
                continue
            if tracker.get_career_by_uid(c.guid64) is not None:
                continue
            if not c.is_career_available(sim_info=sim_info, from_join=True):
                continue
            track = getattr(c, 'start_track', None)
            out.append(_item(c, text(getattr(track, 'career_name', None), sim_info), getattr(track, 'icon', None)))
        except Exception:
            continue
    return _sorted(out)


def add_career(sim_info, career_type):
    def go():
        if sim_info.career_tracker.get_career_by_uid(career_type.guid64) is not None:
            return False, 'Already in that career.'
        sim_info.career_tracker.add_career(career_type(sim_info))
        if sim_info.career_tracker.get_career_by_uid(career_type.guid64) is None:
            return False, 'The game didn\'t allow that career.'
        return True, 'Joined.'
    return _safe('join career', go)


def _career(sim_info, uid):
    return sim_info.career_tracker.get_career_by_uid(uid)


def promote(sim_info, uid):
    def go():
        c = _career(sim_info, uid)
        if c is None:
            return False, 'Not in that career any more.'
        c.promote()
        return True, 'Promoted.'
    return _safe('promote', go)


def demote(sim_info, uid):
    def go():
        c = _career(sim_info, uid)
        if c is None:
            return False, 'Not in that career any more.'
        c.demote()
        return True, 'Demoted.'
    return _safe('demote', go)


def add_pto(sim_info, uid, days=1):
    def go():
        c = _career(sim_info, uid)
        if c is None:
            return False, 'Not in that career any more.'
        c.add_pto(days)
        c.resend_career_data()
        return True, 'A day off added.' if days == 1 else '%d days off added.' % days
    return _safe('days off', go)


def quit_career(sim_info, uid):
    def go():
        if _career(sim_info, uid) is None:
            return False, 'Not in that career any more.'
        sim_info.career_tracker.remove_career(uid, post_quit_msg=True)
        return True, 'Left the job.'
    return _safe('quit career', go)


# ------------------------------------------------------------------ traits (personality traits only)
def _trait_item(trait, sim_info):
    return _item(trait, text(getattr(trait, 'display_name', None), sim_info), getattr(trait, 'icon', None))


def personality_traits(sim_info):
    try:
        return _sorted(_trait_item(t, sim_info) for t in sim_info.trait_tracker.personality_traits)
    except Exception:
        common.log_exception('trait list')
        return []


def addable_traits(sim_info):
    """Personality traits this Sim could take: the game's own can_add_trait (age, species, conflicts), slots aside."""
    import sims4.resources
    tracker = sim_info.trait_tracker
    out = []
    for t in _types(sims4.resources.Types.TRAIT):
        try:
            if not getattr(t, 'is_personality_trait', False) or tracker.has_trait(t):
                continue
            if not tracker.can_add_trait(t, True) or not _allowed_for(sim_info, t):
                continue
            out.append(_trait_item(t, sim_info))
        except Exception:
            continue
    return _sorted(out)


def trait_slots_free(sim_info):
    try:
        return int(sim_info.trait_tracker.empty_slot_number)
    except Exception:
        return 1


def add_trait(sim_info, trait):
    def go():
        if not _allowed_for(sim_info, trait):
            return False, 'That trait is only for adults.'
        if trait_slots_free(sim_info) <= 0:
            return False, TRAIT_SLOTS_FULL
        sim_info.add_trait(trait)
        return (True, 'Trait added.') if sim_info.has_trait(trait) else (False, 'The game didn\'t allow that trait.')
    return _safe('add trait', go)


def remove_trait(sim_info, trait):
    def go():
        sim_info.remove_trait(trait)
        return True, 'Trait removed.'
    return _safe('remove trait', go)


# ------------------------------------------------------------------ aspiration
def complete_milestone(sim_info):
    def go():
        import services
        import sims4.resources
        primary = getattr(sim_info, 'primary_aspiration', None)
        if not primary:
            return False, 'No aspiration is picked.'
        mgr = services.get_instance_manager(sims4.resources.Types.ASPIRATION_TRACK)
        track = (mgr.get(primary.guid64) if mgr is not None else None) or primary
        tracker = sim_info.aspiration_tracker
        for _, milestone in track.get_aspirations():
            if tracker.milestone_completed(milestone):
                continue
            just_done = []
            for objective in milestone.objectives:
                if not tracker.objective_completed(objective):
                    tracker.complete_objective(objective, milestone)
                    just_done.append(objective)
            tracker.complete_milestone(milestone, sim_info)
            tracker.send_if_dirty()
            tracker.update_objectives_after_ui_change(just_done)
            return True, 'Milestone done.'
        return False, 'Every milestone is already done.'
    return _safe('complete milestone', go)


def reset_aspiration(sim_info):
    def go():
        sim_info.aspiration_tracker.reset_data()
        return True, 'Aspiration starts over.'
    return _safe('reset aspiration', go)


# ------------------------------------------------------------------ age
def age_up(sim_info):
    if game.age_value(sim_info) == 64:
        return False, 'Elders are the last life stage.'

    def go():
        before = game.age_value(sim_info)
        sim_info.callback_auto_age()
        after = game.age_value(sim_info)
        return (after != before), ('Now %s.' % game.age_name(sim_info).lower() if after != before
                                   else 'The game didn\'t age this Sim up.')
    return _safe('age up', go)


def age_down(sim_info):
    if game.age_value(sim_info) in (1, 128):
        return False, 'Already the youngest life stage.'

    def go():
        before = game.age_value(sim_info)
        sim_info.reverse_age()
        sim = game.instanced(sim_info)
        if sim is not None:
            _reset_sim(sim)
        after = game.age_value(sim_info)
        return (after != before), ('Now %s.' % game.age_name(sim_info).lower() if after != before
                                   else 'The game didn\'t age this Sim down.')
    return _safe('age down', go)


# ------------------------------------------------------------------ occult
def _occult_enum():
    from sims.occult.occult_enums import OccultType
    return OccultType


def occult_types():
    """[{'name', 'value'}] for the occult types this game has (its occult tracker's own data), human left out."""
    try:
        OccultType = _occult_enum()
    except Exception:
        return []
    try:
        from sims.occult.occult_tracker import OccultTracker
        known = set(getattr(OccultTracker, 'OCCULT_DATA', None) or ())
    except Exception:
        known = set()
    out = []
    for member in OccultType:
        if member.name not in OCCULT_NAMES or (known and member not in known):
            continue
        out.append({'name': OCCULT_NAMES[member.name], 'value': int(member)})
    return sorted(out, key=lambda d: d['name'])


def has_occult(sim_info, value):
    try:
        return bool(sim_info.occult_tracker.has_occult_type(_occult_enum()(value)))
    except Exception:
        return False


def occult_summary(sim_info):
    names = [o['name'] for o in occult_types() if has_occult(sim_info, o['value'])]
    return ', '.join(names) if names else 'Human'


def add_occult(sim_info, value):
    others = [o['name'] for o in occult_types() if o['value'] != value and has_occult(sim_info, o['value'])]
    if others:
        return False, 'Already a %s. Turn back first.' % others[0]

    def go():
        sim_info.occult_tracker.add_occult_type(_occult_enum()(value))
        return (True, 'Done.') if has_occult(sim_info, value) else (False, 'The game didn\'t allow that.')
    return _safe('add occult', go)


def remove_occult(sim_info, value):
    def go():
        sim_info.occult_tracker.remove_occult_type(_occult_enum()(value))
        return True, 'Done.'
    return _safe('remove occult', go)


# ------------------------------------------------------------------ relationships
def related(a, b):
    """True when these two are family by the game's own rule (or it can't tell - then romance stays off)."""
    if a is None or b is None or getattr(a, 'id', 0) == getattr(b, 'id', 1):
        return True
    try:
        return not a.incest_prevention_test(b)
    except Exception:
        common.log_exception('family test')
        return True


def _tracks():
    from relationships.relationship_track import RelationshipTrack
    return RelationshipTrack.FRIENDSHIP_TRACK, RelationshipTrack.ROMANCE_TRACK


def set_relationship(me, other, kind, value):
    """kind: 'friendship' or 'romance' (value -100..100), or 'neutral' (both back to 0). Romance only between two
    young adult or older humans who aren't family."""
    romantic = kind == 'romance' or (kind == 'neutral')
    allowed = game.is_adult_human(me) and game.is_adult_human(other) and not related(me, other)
    if kind == 'romance' and not allowed:
        return False, 'Romance is only for adult Sims who aren\'t family.'

    def go():
        friendship, romance = _tracks()
        rt = me.relationship_tracker
        if kind == 'friendship':
            rt.set_relationship_score(other.id, value, friendship)
        elif kind == 'romance':
            rt.set_relationship_score(other.id, value, romance)
        else:
            rt.set_relationship_score(other.id, 0, friendship)
            if romantic and romance is not None:
                rt.set_relationship_score(other.id, 0, romance)
        return True, ''
    return _safe('relationship', go)


# ------------------------------------------------------------------ pregnancy (adults only)
def is_pregnant(sim_info):
    try:
        v = sim_info.pregnancy_tracker.is_pregnant
        return bool(v() if callable(v) else v)
    except Exception:
        return False


def start_pregnancy(sim_info, partner):
    if not (game.is_adult_human(sim_info) and game.is_adult_human(partner)) or related(sim_info, partner):
        return False, 'Only for two adult Sims who aren\'t family.'
    if is_pregnant(sim_info):
        return False, 'Already pregnant.'

    def go():
        sim_info.pregnancy_tracker.start_pregnancy(sim_info, partner)
        return (True, 'Pregnant with %s\'s baby.' % game.first_name(partner)) if is_pregnant(sim_info) \
            else (False, 'The game didn\'t start the pregnancy.')
    return _safe('start pregnancy', go)


def clear_pregnancy(sim_info):
    def go():
        sim_info.pregnancy_tracker.clear_pregnancy()
        return True, 'No longer pregnant.'
    return _safe('clear pregnancy', go)


# ------------------------------------------------------------------ household and control
def members(household):
    try:
        return list(household.sim_info_gen())
    except Exception:
        return []


def add_to_active_household(sim_info):
    import services
    hh = services.active_household()
    if hh is None:
        return False, 'No household is being played.'
    if game.in_active_household(sim_info):
        return False, 'Already in your household.'

    def go():
        if hasattr(hh, 'can_add_sim_info') and not hh.can_add_sim_info(sim_info):
            return False, 'Your household is full.'
        from sims.household_enums import HouseholdChangeOrigin
        services.household_manager().switch_sim_household(sim_info, None, reason=HouseholdChangeOrigin.CHEAT)
        return (True, 'Moved in.') if game.in_active_household(sim_info) else (False, 'The game didn\'t allow the move.')
    return _safe('move in', go)


def _client():
    import services
    return services.client_manager().get_first_client()


def is_controlled(sim_info):
    try:
        return sim_info in _client().selectable_sims
    except Exception:
        return False


def control(sim_info):
    def go():
        _client().add_selectable_sim_info(sim_info, send_relationship_update=True)
        return True, 'Now in your Sims bar.'
    return _safe('control', go)


def release(sim_info):
    if game.in_active_household(sim_info):
        return False, 'Sims in your household always stay in your Sims bar.'
    me = game.active_sim_info()
    if me is not None and me.id == sim_info.id:
        return False, 'This is the Sim being played.'

    def go():
        _client().remove_selectable_sim_info(sim_info)
        return True, 'Out of your Sims bar.'
    return _safe('release', go)


# ------------------------------------------------------------------ on the lot
def _reset_sim(sim):
    from objects.object_enums import ResetReason
    sim.reset(ResetReason.RESET_EXPECTED, None, 'Novulon')


def reset(sim_info):
    sim = game.instanced(sim_info)
    if sim is None:
        return False, 'Only Sims on this lot can be reset.'

    def go():
        _reset_sim(sim)
        return True, 'Reset.'
    return _safe('reset', go)


def teleport_to_active(sim_info):
    import services
    sim, me = game.instanced(sim_info), services.get_active_sim()
    if sim is None or me is None:
        return False, 'Both Sims need to be on this lot.'
    if sim is me:
        return False, 'That\'s the Sim being played.'

    def go():
        import sims4.math
        p, f = me.position, me.forward
        pos = sims4.math.Vector3(p.x + f.x, p.y, p.z + f.z)
        sim.location = sims4.math.Location(sims4.math.Transform(pos, me.orientation), me.location.routing_surface)
        _reset_sim(sim)
        return True, 'Here now.'
    return _safe('bring here', go)


def open_cas(sim_info, conn):
    """Create a Sim for this Sim's household. Returns None - the menu closes as CAS opens."""
    from . import ui
    if sim_info is None:
        return None
    try:
        import sims4.commands
        c = conn if isinstance(conn, int) and conn else _client().id
        sims4.commands.client_cheat('sims.exit2caswithhouseholdid {} {}'.format(sim_info.sim_id, sim_info.household_id), c)
    except Exception:
        common.log_exception('open CAS')
        ui.notify('Create a Sim', 'Create a Sim couldn\'t open. The details are in Novulon\'s log.', icon='warning')
    return None


def empty_inventories(household):
    def go():
        n = 0
        for si in members(household):
            sim = game.instanced(si)
            comp = getattr(sim, 'inventory_component', None) if sim is not None else None
            if comp is not None:
                comp.purge_inventory()
                n += 1
        return (n > 0), ('Emptied for %d Sims.' % n if n else 'None of the household is on this lot.')
    return _safe('empty inventories', go)


# ------------------------------------------------------------------ delete
def can_delete(sim_info):
    return not deleting.protected(sim_info)


def why_not_deletable(sim_info):
    return deleting.protected(sim_info)


def delete(sim_info):
    """Starts the delete (a Sim on the lot first leaves it). A later failure says so in the corner."""
    why = deleting.protected(sim_info)
    if why:
        return False, why
    who = game.name(sim_info)

    def finished(worked):
        if not worked:
            from . import ui
            ui.notify('Delete', '%s couldn\'t be deleted. The details are in Novulon\'s log.' % who, icon='warning')
    try:
        deleting.delete(sim_info, finished)
    except Exception:
        common.log_exception('delete')
        return False, '%s couldn\'t be deleted.' % who
    return True, '%s is deleted.' % who


# ------------------------------------------------------------------ money
def funds(household):
    try:
        return int(household.funds.money)
    except Exception:
        return 0


def _money_reason():
    from protocolbuffers import Consts_pb2
    return Consts_pb2.TELEMETRY_MONEY_CHEAT


def add_funds(household, amount):
    def go():
        household.funds.add(amount, _money_reason())
        return True, 'Added §%s. The household has §%s.' % (format(amount, ','), format(funds(household), ','))
    return _safe('add money', go)


def set_funds(household, amount):
    def go():
        delta = amount - funds(household)
        if delta > 0:
            household.funds.add(delta, _money_reason())
        elif delta < 0:
            household.funds.try_remove(-delta, _money_reason())
        return True, 'The household has §%s.' % format(funds(household), ',')
    return _safe('set money', go)


# ------------------------------------------------------------------ the world
def time_text():
    try:
        import services
        now = services.time_service().sim_now
        return '%d:%02d' % (now.hour(), now.minute())
    except Exception:
        return '?'


def set_time(hour):
    def go():
        import services
        services.game_clock_service().set_game_time(hour, 0, 0)
        services.sim_info_manager().auto_satisfy_sim_motives()
        return True, 'The time is now %d:00.' % hour
    return _safe('set time', go)


def set_autonomy(on):
    def go():
        import services
        from autonomy.settings import AutonomyState, AutonomySettingsGroup
        services.autonomy_service().global_autonomy_settings.set_setting(
            AutonomyState.FULL if on else AutonomyState.LIMITED_ONLY, AutonomySettingsGroup.DEFAULT)
        return True, 'Autonomy is on.' if on else 'Autonomy is off.'
    return _safe('autonomy', go)

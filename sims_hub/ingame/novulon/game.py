"""Reading the game: Sims, households, ages - the small layer every menu uses, so no menu reaches into the game's
services itself. Everything here is read-only; changes to Sims live in actions/.

Ages (sims.sim_info_types.Age): BABY 1, TODDLER 2, CHILD 4, TEEN 8, YOUNGADULT 16, ADULT 32, ELDER 64, INFANT 128.
Species (sims.sim_info_types.Species): HUMAN 1, then the pets. Novulon's rule: romance, pregnancy and anything adult
is only ever between young adults or older humans (is_adult_human).
"""
from . import common

AGE_NAMES = {1: 'Baby', 128: 'Infant', 2: 'Toddler', 4: 'Child', 8: 'Teen', 16: 'Young adult', 32: 'Adult', 64: 'Elder'}
ADULT_AGES = (16, 32, 64)
SPECIES_HUMAN = 1


def _int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


# ------------------------------------------------------------------ finding Sims
def all_sim_infos():
    import services
    mgr = services.sim_info_manager()
    return list(mgr.get_all()) if mgr is not None else []


def sim_info_by_id(sim_id):
    """A SimInfo by its id (the Sim's own id, or the id of its Sim object on the lot); None when there is none."""
    import services
    sid = _int(sim_id)
    if not sid:
        return None
    mgr = services.sim_info_manager()
    si = mgr.get(sid) if mgr is not None else None
    if si is None:
        om = services.object_manager()
        obj = om.get(sid) if om is not None else None
        si = getattr(obj, 'sim_info', None)
    return si


def active_sim_info():
    import services
    return services.active_sim_info()


def active_household():
    import services
    return services.active_household()


def instanced(sim_info):
    """The Sim's object on the current lot, or None when it isn't here."""
    try:
        return sim_info.get_sim_instance()
    except Exception:
        return None


# ------------------------------------------------------------------ describing a Sim
def name(sim_info):
    first, last = getattr(sim_info, 'first_name', '') or '', getattr(sim_info, 'last_name', '') or ''
    full = ('%s %s' % (first, last)).strip()
    return full or 'Sim %s' % getattr(sim_info, 'id', '?')


def first_name(sim_info):
    return getattr(sim_info, 'first_name', '') or name(sim_info)


def age_value(sim_info):
    return _int(getattr(sim_info, 'age', 0))


def age_name(sim_info):
    return AGE_NAMES.get(age_value(sim_info), 'Sim')


def is_human(sim_info):
    return _int(getattr(sim_info, 'species', SPECIES_HUMAN), SPECIES_HUMAN) == SPECIES_HUMAN


def is_adult_human(sim_info):
    """Young adult, adult or elder, and human - who romance, pregnancy and adult options are for."""
    return sim_info is not None and is_human(sim_info) and age_value(sim_info) in ADULT_AGES


def is_male(sim_info):
    g = getattr(sim_info, 'gender', None)
    return getattr(g, 'name', '') == 'MALE' if g is not None else False


def is_female(sim_info):
    g = getattr(sim_info, 'gender', None)
    return getattr(g, 'name', '') == 'FEMALE' if g is not None else False


def household_name(sim_info):
    hh = getattr(sim_info, 'household', None)
    return (getattr(hh, 'name', '') or '') if hh is not None else ''


def in_active_household(sim_info):
    hh = active_household()
    return hh is not None and getattr(sim_info, 'household_id', None) == getattr(hh, 'id', 0)


def summary(sim_info):
    """'Young adult · Goth household · here' - a short line under a Sim's name."""
    parts = [age_name(sim_info)]
    if not is_human(sim_info):
        sp = getattr(getattr(sim_info, 'species', None), 'name', '') or 'Pet'
        parts[0] = sp.title()
    hh = household_name(sim_info)
    if hh:
        parts.append(hh + ' household')
    if instanced(sim_info) is not None:
        parts.append('here')
    return ' · '.join(parts)


def sort_by_name(sim_infos):
    return sorted(sim_infos, key=lambda si: ((getattr(si, 'first_name', '') or '').lower(),
                                             (getattr(si, 'last_name', '') or '').lower()))

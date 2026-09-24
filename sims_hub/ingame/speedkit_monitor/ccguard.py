"""CC guard: after a lot loads, warn if the active household wears CAS parts this profile does not load.

The game API used, and why it answers "is this CAS part loaded?" (build 1.126.73):
  * cas.cas.get_caspart_bodytype is the native _cas.get_caspart_bodytype of Simulation_x64.dll (cas/cas.pyc
    line 254 re-exports it; the name is in the DLL's string table next to the other _cas functions). It
    looks a part id up in the game's loaded CAS catalog and returns its body type.
  * WickedWhims (in Mods now) decides "CAS part loaded" with exactly get_caspart_bodytype(int(id)) > 0
    (turbolib2/services/cas_service.pyc, TurboCASService.is_cas_part_loaded). Its log of the 2026-09-24
    00:31 session (WickedWhimsInfoLog.log) says 'Loaded 3527 CAS Part Handlers' - including its tongue and
    condom handlers whose 14 CASPs sit in Mods\\scripts\\TURBODRIVER_WickedWhims_Tuning.package - and
    skipped exactly the 24 'Hiroki:Body_CAS_Parts' handlers 'caused by missing CAS part'; those 24 part
    ids are in neither Mods nor Mods_parked (library index). So in the running game the call returns a
    number > 0 for a loaded part and <= 0, without raising, for one the catalog does not have. EA code
    also compares its result with None, so None is treated as missing too.
  * Outfits: SimInfo derives from SimInfoWithOccultTracker -> SimInfoBaseWrapper, whose bases include
    OutfitTrackerMixin; SimInfoBaseWrapper.get_outfits() returns the sim info itself (line 593);
    OutfitTrackerMixin.get_all_outfits() yields (category, outfit list) straight from the native data
    and each outfit's part_ids are the CAS part ids (server_commands/outfit_commands.show_outfit_info
    walks them the same way). We never call get_outfit(), which can generate a missing outfit.
  * The household: services.active_household().sim_info_gen().
Not proven in the running game: that part_ids still hold ids the catalog does not know after a load (if
the game strips them while loading, this finds nothing). Everything is read-only; a check is a few
hundred native lookups at most.
"""
from . import common

MAX_IDS_LOGGED = 40


# ------------------------------------------------------------------ pure logic (tested under 3.12)
def find_missing_parts(sims, is_loaded):
    """Which sims wear parts that are not loaded.

    sims: iterable of (label, sim_id, iterable of part ids). is_loaded: part id -> bool (may raise).
    Returns {'sims': [(label, sim_id, [missing ids])], 'missing': set, 'checked': n, 'errors': n};
    an id whose lookup raised counts as an error, not as missing."""
    cache = {}
    errors = 0
    out = []
    for label, sim_id, part_ids in sims:
        missing = []
        for pid in sorted(set(p for p in part_ids if p)):
            if pid not in cache:
                try:
                    cache[pid] = bool(is_loaded(pid))
                except Exception:
                    cache[pid] = None
                    errors += 1
            if cache[pid] is False:
                missing.append(pid)
        if missing:
            out.append((label, sim_id, missing))
    return {'sims': out, 'missing': set(p for _l, _s, ids in out for p in ids),
            'checked': len(cache), 'errors': errors}


def bodytype_says_loaded(bodytype):
    """get_caspart_bodytype result -> loaded? (None or <= 0 means the catalog does not have the part)."""
    try:
        return bodytype is not None and int(bodytype) > 0
    except Exception:
        return False


def describe(result, household=''):
    """(log lines, notification text or None) for a find_missing_parts result."""
    if not result['sims']:
        return (['CC guard: household %s: all %d CAS parts worn are loaded%s' % (
            household, result['checked'], (' (%d lookups failed)' % result['errors']) if result['errors'] else '')],
            None)
    lines = ['CC guard: household %s: %d sim(s) wear %d CAS part(s) that are NOT loaded in this profile:' % (
        household, len(result['sims']), len(result['missing']))]
    for label, sim_id, ids in result['sims']:
        shown = ', '.join('0x%016X' % i for i in ids[:MAX_IDS_LOGGED])
        more = ' (+%d more)' % (len(ids) - MAX_IDS_LOGGED) if len(ids) > MAX_IDS_LOGGED else ''
        lines.append('  %s (sim id %s): %d missing: %s%s' % (label, sim_id, len(ids), shown, more))
    names = ', '.join(label for label, _s, _i in result['sims'][:6])
    text = ('%d sim(s) in this household wear %d custom content part(s) that this mod profile does not load '
            '(%s). Do not save in this profile: the game can drop the missing parts from their outfits '
            'for good. Load the profile with that CC first. Details: SpeedKit\\reports\\monitor.log' % (
                len(result['sims']), len(result['missing']), names))
    return lines, text


# ------------------------------------------------------------------ game glue (main thread only)
def household_outfits():
    """[(label, sim id, set of part ids)] for the active household, or [] (never raises)."""
    import services
    hh = services.active_household()
    if hh is None:
        return []
    out = []
    for si in list(hh.sim_info_gen()):
        try:
            ids = set()
            for _category, outfit_list in si.get_outfits().get_all_outfits():
                for outfit_data in outfit_list:
                    ids.update(int(p) for p in outfit_data.part_ids)
            label = ('%s %s' % (getattr(si, 'first_name', ''), getattr(si, 'last_name', ''))).strip() or '?'
            out.append((label, getattr(si, 'id', '?'), ids))
        except Exception:
            common.log_exception('CC guard reading outfits')
    return out


def part_is_loaded(part_id):
    """Is this CAS part in the game's loaded catalog? (see the module docstring)"""
    from cas.cas import get_caspart_bodytype
    return bodytype_says_loaded(get_caspart_bodytype(part_id))


def check(notify=True):
    """Run the guard for the active household; log, notify when parts are missing. Returns the result."""
    try:
        import services
        hh = services.active_household()
        name = getattr(hh, 'name', '') if hh is not None else ''
    except Exception:
        name = ''
    result = find_missing_parts(household_outfits(), part_is_loaded)
    lines, text = describe(result, name)
    for line in lines:
        common.log(line)
    if text and notify:
        common.notify('SpeedKit: missing CC on your sims', text, urgent=True)
    return result


# ------------------------------------------------------------------ the prepared save (fast / save profiles)
# Novulon's Sims Hub prepares the Mods folder for one mode before it starts the game: 'fast' (the fast pack
# of every save's CC) or 'save' (the pack of one save's CC). SpeedKit\profile_state.json says which, and for
# 'save' also which save: {"profile": "save", "save_slot": "Slot_00000014", "save_slot_id": 20,
# "save_name": "Neuworld Save File", "save_guid": 1560215555}. Playing another save in that mode, or a
# household that wears CC the mode does not load, and then saving would drop CC for good, so the player is
# told once per lot load. Which save is loaded (game build 1.126.73, read with tools/pyc37.py):
#   * services.get_persistence_service() -> PersistenceService; get_save_slot_proto_buff() returns
#     _save_game_data_proto.save_slot (SaveSlotData: slot_id 1, slot_name 9), get_save_slot_proto_guid()
#     returns _save_game_data_proto.guid (services/persistence_service.pyc lines 853 and 862). The same
#     SaveSlotData is what areaserver.c_api_zone_init hands to Zone.start_services.
#   * slot_id is what the game wrote into the file: normally the slot number of Slot_%08x.save, but a save
#     the game recovered keeps its original's id (Slot_00000018 holds 23) and copies share a guid, so a
#     save counts as the prepared one only when name, slot id (the recorded one or the file's number) and
#     guid all agree.
#   * The identity is taken at the first lot load after the main menu (before the player could 'Save As'
#     to another slot) and kept for the lots that follow.
PREPARED_TITLE = "Novulon's Sims Hub"
PREPARED_TEXT = "This save was not prepared for this mode - do not save. Restart the game from Novulon's Sims Hub."
PREPARED_PROFILES = ('fast', 'save')
_session = {'loaded': None, 'same': None}


def slot_number(slot):
    """0x14 for 'Slot_00000014' (the file name's hex number), else None."""
    try:
        s = str(slot)
        if s.lower().startswith('slot_') and len(s) == 13:
            return int(s[5:], 16)
    except (TypeError, ValueError):
        pass
    return None


def _as_int(v):
    try:
        return None if v is None or isinstance(v, bool) else int(v)
    except (TypeError, ValueError):
        return None


def expected_save(doc):
    """What profile_state.json says the prepared save is: {'slot', 'number', 'slot_id', 'name', 'guid'}, or
    None when the profile is not 'save' (or names no save)."""
    if not isinstance(doc, dict) or str(doc.get('profile') or '').strip().lower() != 'save':
        return None
    slot = doc.get('save_slot')
    if not isinstance(slot, str) or not slot.strip():
        return None
    return {'slot': slot.strip(), 'number': slot_number(slot.strip()), 'slot_id': _as_int(doc.get('save_slot_id')),
            'name': doc.get('save_name') if isinstance(doc.get('save_name'), str) else None,
            'guid': _as_int(doc.get('save_guid'))}


def same_save(expected, loaded):
    """True / False, or None when either side is unknown. The loaded save {'slot_id', 'name', 'guid'} is the
    prepared one when every fact both sides know agrees (slot id: the recorded one or the file's number)."""
    if not expected or not loaded:
        return None
    known = False
    if expected.get('name') and loaded.get('name'):
        known = True
        if expected['name'] != loaded['name']:
            return False
    if expected.get('guid') is not None and loaded.get('guid') is not None:
        known = True
        if expected['guid'] != loaded['guid']:
            return False
    lid = loaded.get('slot_id')
    ids = {x for x in (expected.get('slot_id'), expected.get('number')) if x is not None}
    if lid is not None and ids:
        known = True
        if lid not in ids:
            return False
    return True if known else None


def installed_nowhere(doc):
    """Set of CAS part ids profile_state.json lists as installed nowhere (hex strings written by the profile
    tool from the pack's manifest): missing in every mode, so never a sign of an unprepared mode."""
    out = set()
    for v in ((doc or {}).get('installed_nowhere') or []) if isinstance(doc, dict) else []:
        try:
            out.add(int(v, 16) if isinstance(v, str) else int(v))
        except (TypeError, ValueError):
            continue
    return out


def decide(doc, same, missing):
    """(warn with PREPARED_TEXT?, reasons) for the profile in profile_state.json `doc`, the same_save verdict
    and the number of worn CAS parts that are not loaded."""
    profile = str((doc or {}).get('profile') or '').strip().lower() if isinstance(doc, dict) else ''
    if profile not in PREPARED_PROFILES:
        return False, []
    reasons = []
    if profile == 'save' and same is False:
        reasons.append('another save is loaded than the one this game was prepared for (%s)'
                       % ((doc or {}).get('save_name') or (doc or {}).get('save_slot')))
    if missing:
        reasons.append('%d worn CAS part(s) are not loaded in this mode' % missing)
    return bool(reasons), reasons


def loaded_save():
    """{'slot_id', 'name', 'guid'} of the save the game has loaded, or None (main thread; never raises)."""
    try:
        import services
        ps = services.get_persistence_service()
        if ps is None:
            return None
        slot = ps.get_save_slot_proto_buff()
        guid = ps.get_save_slot_proto_guid() if hasattr(ps, 'get_save_slot_proto_guid') else None
    except Exception:
        return None
    if slot is None:
        return None
    try:
        name = str(slot.slot_name) if getattr(slot, 'slot_name', None) is not None else None
    except Exception:
        name = None
    return {'slot_id': _as_int(getattr(slot, 'slot_id', None)), 'name': name or None, 'guid': _as_int(guid)}


def reset_session():
    """At the main menu: the next lot may belong to another save."""
    _session['loaded'] = None
    _session['same'] = None


def after_load(doc, lot_index):
    """After a lot loads: run the CC guard; in the fast/save modes warn with PREPARED_TEXT when the wrong save
    is loaded or worn CC is missing, else keep the CC guard's own notification. Returns a summary dict."""
    exp = expected_save(doc)
    if exp is not None and (lot_index in (None, 0, 1) or _session['loaded'] is None):
        _session['loaded'] = loaded_save()
        _session['same'] = same_save(exp, _session['loaded'])
        common.log('save guard: prepared for %s (%s, slot id %s, guid %s); loaded %s -> %s' % (
            exp['slot'], exp['name'], exp['slot_id'], exp['guid'], _session['loaded'],
            {True: 'same save', False: 'ANOTHER SAVE', None: 'cannot tell'}[_session['same']]))
    same = _session['same'] if exp is not None else None
    profile = str((doc or {}).get('profile') or '') if isinstance(doc, dict) else ''
    prepared = profile.strip().lower() in PREPARED_PROFILES
    result = check(notify=not prepared)
    nowhere = installed_nowhere(doc) if prepared else set()
    counted = set(result['missing']) - nowhere
    if prepared and result['missing'] and len(counted) != len(result['missing']):
        common.log('save guard: %d of the missing parts are installed nowhere (missing in every mode); not counted'
                   % (len(result['missing']) - len(counted)))
    warn, reasons = decide(doc, same, len(counted))
    if warn:
        common.log('save guard: %s' % '; '.join(reasons))
        common.notify(PREPARED_TITLE, PREPARED_TEXT, urgent=True)
    return {'cc': result, 'same_save': same, 'warned': warn, 'reasons': reasons}


def run_after_load():
    """Called by the load timer when a lot finished loading. Never raises."""
    def go():
        from . import loadtimer
        st = loadtimer.state
        return after_load(st.get('profile_state'), st.get('lots'))
    return common.guarded('CC guard', go)

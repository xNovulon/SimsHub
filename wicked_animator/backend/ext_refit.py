"""Any furniture (R3-3): the places an animation can be moved to, read-only.

    GET /api/refit_places
        {'places': [{id, location, label, group, kind, object_id, surface_height, bounds, seats, lying, app_id}],
         'cc': [{id, label, group, kind, object_id, surface_height, bounds, seats, lying, package}],
         'cc_status': 'ok' | 'waiting' | 'none' | 'error', 'cc_note'}
        Every WickedWhims place (its reference object, objmesh.all_locations) and the placeable CC furniture with a
        top surface from the Mods folder (objmesh.mods_objects, when the game-object reader has it).
    GET /api/refit_places?place=ww:BATHTUB | cc:<object id>
        the object itself, like /api/furniture_mesh: meshes, bounds, surface_height, surface_grid, slots.

Only the objmesh read API is used (all_locations, furniture_for_location, object_mesh, mods_objects). Adults only:
nothing whose name reads as child, teen or pet (gamedata._BLOCK_WORDS) is listed, and places made for children
(the swing set) are left out.
"""
import re
import threading

import gamedata as G

# WickedWhims place -> (plain name, group). Groups order the picker.
GROUPS = ['Beds', 'Sofas and seats', 'Tables and counters', 'Bath and water', 'Fitness', 'Floor and walls', 'Other']
_NAMES = {
    'DOUBLE_BED': ('Double bed', 'Beds'), 'SINGLE_BED': ('Single bed', 'Beds'), 'BUNK_BED': ('Bunk bed (top)', 'Beds'),
    'MURPHY_DOUBLE_BED': ('Murphy bed', 'Beds'), 'BED_ROLL': ('Bed roll', 'Beds'), 'MASSAGE_TABLE': ('Massage table', 'Beds'),
    'COFFIN': ('Coffin', 'Beds'),
    'SOFA': ('Sofa', 'Sofas and seats'), 'LOVESEAT': ('Loveseat', 'Sofas and seats'),
    'CORNER_LOVESEAT': ('Corner loveseat', 'Sofas and seats'), 'MURPHY_LOVESEAT': ('Murphy loveseat', 'Sofas and seats'),
    'SECTIONAL_SOFA': ('Sectional sofa', 'Sofas and seats'), 'SECTIONAL_SOFA_LOVESEAT': ('Sectional loveseat', 'Sofas and seats'),
    'SECTIONAL_SOFA_CHAIR_LIVING': ('Sectional armchair', 'Sofas and seats'),
    'SECTIONAL_SOFA_LARGE_IN_CORNER': ('Sectional corner', 'Sofas and seats'),
    'BENCH_OUTDOOR': ('Outdoor bench', 'Sofas and seats'), 'CHAIR_LIVING': ('Armchair', 'Sofas and seats'),
    'CHAIR_DINING': ('Dining chair', 'Sofas and seats'), 'CHAIR_DESK': ('Desk chair', 'Sofas and seats'),
    'CHAIR_STOOL': ('Bar stool', 'Sofas and seats'), 'CHAIR_LOUNGE': ('Lounge chair', 'Sofas and seats'),
    'CHAIR_LOUNGE_SOFA': ('Lounge sofa', 'Sofas and seats'), 'CHAIR_LOUNGE_FLOAT': ('Pool float', 'Bath and water'),
    'OTTOMAN': ('Ottoman', 'Sofas and seats'),
    'TABLE_DINING_1X': ('Small dining table', 'Tables and counters'), 'TABLE_DINING_2X': ('Dining table', 'Tables and counters'),
    'TABLE_DINING_3X': ('Long dining table', 'Tables and counters'), 'TABLE_DINING_ROUND_BIG': ('Round dining table', 'Tables and counters'),
    'TABLE_DINING_TALL_1X': ('Small tall table', 'Tables and counters'), 'TABLE_DINING_TALL_2X': ('Tall table', 'Tables and counters'),
    'TABLE_DINING_TALL_3X': ('Long tall table', 'Tables and counters'), 'TABLE_TV_STAND': ('TV stand', 'Tables and counters'),
    'TABLE_COFFEE': ('Coffee table', 'Tables and counters'), 'TABLE_ACCENT': ('Side table', 'Tables and counters'),
    'TABLE_PICNIC': ('Picnic table', 'Tables and counters'), 'TABLE_OUTDOOR': ('Outdoor table', 'Tables and counters'),
    'TABLE_OUTDOOR_UMBRELLA': ('Patio table', 'Tables and counters'), 'DESK': ('Desk', 'Tables and counters'),
    'BAR_1X': ('Small bar', 'Tables and counters'), 'BAR_2X': ('Bar', 'Tables and counters'), 'BAR_3X': ('Long bar', 'Tables and counters'),
    'BAR_CURVED': ('Curved bar', 'Tables and counters'), 'COUNTER': ('Counter', 'Tables and counters'),
    'COUNTER_ISLAND': ('Kitchen island', 'Tables and counters'), 'COUNTER_CORNER': ('Corner counter', 'Tables and counters'),
    'STOVE': ('Stove', 'Tables and counters'), 'SINK': ('Sink', 'Tables and counters'),
    'BATHTUB': ('Bathtub', 'Bath and water'), 'CORNER_BATHTUB': ('Corner bathtub', 'Bath and water'),
    'SHOWER': ('Shower', 'Bath and water'), 'SHOWER_TUB': ('Shower tub', 'Bath and water'), 'OPEN_SHOWER': ('Open shower', 'Bath and water'),
    'HOTTUB': ('Hot tub', 'Bath and water'), 'HOTTUB_INGROUND': ('In-ground hot tub', 'Bath and water'), 'SAUNA': ('Sauna', 'Bath and water'),
    'TOILET': ('Toilet', 'Bath and water'), 'TOILET_STALL': ('Toilet stall', 'Bath and water'), 'SQUAT_TOILET': ('Squat toilet', 'Bath and water'),
    'PUBLIC_BATHROOM': ('Public bathroom', 'Bath and water'),
    'DIVING_BOARD_SHORT': ('Diving board', 'Bath and water'), 'DIVING_BOARD_TALL': ('Tall diving board', 'Bath and water'),
    'YOGA_MAT': ('Yoga mat', 'Fitness'), 'SPINNING_BIKE': ('Exercise bike', 'Fitness'), 'FREE_WEIGHTS': ('Weight bench', 'Fitness'),
    'TREADMILL': ('Treadmill', 'Fitness'), 'PUNCHING_BAG': ('Punching bag', 'Fitness'), 'WORKOUT_MACHINE': ('Workout machine', 'Fitness'),
    'DANCE_FLOOR': ('Dance floor', 'Floor and walls'), 'BLANKET': ('Picnic blanket', 'Floor and walls'),
    'BEACH_TOWEL': ('Beach towel', 'Floor and walls'), 'WINDOW': ('Window', 'Floor and walls'), 'DOOR': ('Door', 'Floor and walls'),
    'MIRROR': ('Mirror', 'Floor and walls'), 'MURPHY_CLOSED': ('Murphy bed (closed)', 'Floor and walls'),
}
# made for children (a playground swing set): never offered
_NOT_ADULT = {'SWING_SET'}
# places the app has its own furniture entry for (server.FURNITURE ids): those ids are used, so the Scene step, Magic
# and the ready poses know them
APP_IDS = {'DOUBLE_BED': 'double_bed', 'SINGLE_BED': 'single_bed', 'SOFA': 'sofa', 'LOVESEAT': 'loveseat',
           'CHAIR_LIVING': 'chair_living', 'CHAIR_DINING': 'chair_dining', 'COUNTER': 'counter', 'TABLE_DINING_2X': 'table_dining'}
_WALLISH = {'WINDOW', 'DOOR', 'MIRROR', 'MURPHY_CLOSED'}
_FLOORISH = {'DANCE_FLOOR', 'PUBLIC_BATHROOM', 'SHOWER', 'OPEN_SHOWER'}


def _nice(loc):
    return loc.replace('_', ' ').capitalize()


def _kind(loc, row):
    """What the place is for moving an animation: bed | seat | surface | floor | wall | water."""
    slots = row.get('slots') or []
    kinds = {s.get('kind') for s in slots}
    top = row.get('surface_height')
    if loc in _WALLISH:
        return 'wall'
    if loc in _FLOORISH or top is None:
        return 'floor'
    if 'in' in kinds or loc in ('DOUBLE_BED', 'SINGLE_BED', 'BUNK_BED', 'MURPHY_DOUBLE_BED', 'BED_ROLL', 'MASSAGE_TABLE', 'COFFIN'):
        return 'bed'
    if loc.startswith(('HOTTUB', 'BATHTUB', 'CORNER_BATHTUB', 'SHOWER_TUB', 'CHAIR_LOUNGE_FLOAT')):
        return 'water'
    if 'seat' in kinds or 'edge' in kinds:
        return 'seat'
    if top is not None and top < 0.06:
        return 'floor'
    return 'surface'


def _counts(slots):
    return (sum(1 for s in slots or [] if s.get('kind') in ('seat', 'edge', 'in')),
            sum(1 for s in slots or [] if s.get('kind') == 'lie'))


def _adult_name(text):
    return not G._BLOCK_WORDS.search(str(text or '').replace('_', ' ').replace('-', ' '))


_lock = threading.Lock()
_places = None


def ww_places():
    """Every WickedWhims place the app can show (its reference object loads), adults only, in picker order."""
    global _places
    with _lock:
        if _places is not None:
            return _places
        import objmesh
        rows = objmesh.all_locations()
        out = []
        for r in rows:
            loc = str(r.get('location') or '').upper()
            if not loc or loc in _NOT_ADULT or not _adult_name(loc) or not _adult_name(r.get('name')):
                continue
            label, group = _NAMES.get(loc, (_nice(loc), 'Other'))
            seats, lying = _counts(r.get('slots'))
            out.append({'id': APP_IDS.get(loc) or 'ww:' + loc, 'location': loc, 'label': label, 'group': group,
                        'kind': _kind(loc, r), 'object_id': r.get('object_id'), 'surface_height': r.get('surface_height'),
                        'bounds': r.get('bounds'), 'seats': seats, 'lying': lying, 'app_id': APP_IDS.get(loc)})
        out.sort(key=lambda x: (GROUPS.index(x['group']) if x['group'] in GROUPS else len(GROUPS), x['label']))
        _places = out
        return out


# ------------------------------------------------------------------ CC furniture (objmesh.mods_objects, R3-1)
# objmesh.mods_objects' kinds -> ours
_CC_KIND = {'bed': 'bed', 'lie': 'bed', 'sofa': 'seat', 'chair': 'seat', 'table': 'surface', 'counter': 'surface', 'surface': 'surface'}


def _cc_rows():
    """(rows, status, note). objmesh.mods_objects() lists the placeable CC furniture with a surface; until the object
    reader has it, there is simply no CC list ('waiting')."""
    try:
        import objmesh
    except Exception as ex:           # the game-object reader itself is missing
        return [], 'error', str(ex)
    fn = getattr(objmesh, 'mods_objects', None)
    if not callable(fn):
        return [], 'waiting', 'Your own CC furniture shows here once the app can read objects from the Mods folder.'
    try:
        raw = fn()
    except Exception as ex:
        return [], 'error', 'Could not read the CC furniture: %s' % ex
    if isinstance(raw, dict):
        raw = raw.get('objects') or raw.get('items') or list(raw.values())
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        oid = r.get('id', r.get('object_id', r.get('obj_def_id', r.get('guid'))))
        if oid in (None, ''):
            continue
        try:
            oid = int(oid)
        except (TypeError, ValueError):
            continue
        name = r.get('label') or r.get('title') or r.get('name') or r.get('objName') or ('Object %d' % oid)
        if not all(_adult_name(x) for x in (name, r.get('name'), r.get('objName'), r.get('package'))):
            continue
        top = r.get('surface_height')
        if top is None and r.get('surface') is not None:
            top = r.get('surface')
        slots = r.get('slots') or []
        seats, lying = _counts(slots)
        loc = str(r.get('location') or r.get('category') or '').upper()
        kind = _CC_KIND.get(str(r.get('kind') or '').lower()) or _kind(loc, {'slots': slots, 'surface_height': top})
        out.append({'id': 'cc:%d' % oid, 'label': str(name)[:60], 'group': 'My CC furniture', 'kind': kind, 'object_id': oid,
                    'surface_height': top, 'bounds': r.get('bounds'), 'seats': seats, 'lying': lying,
                    'package': r.get('package'), 'cc': True})
    out.sort(key=lambda x: x['label'].lower())
    return out, ('ok' if out else 'none'), ('' if out else 'No CC furniture with a top surface was found in the Mods folder.')


def cc_object(oid):
    """The CC object's mesh (the object reader's own answer), or None."""
    import objmesh
    for name in ('mods_object_mesh', 'mods_object'):
        fn = getattr(objmesh, name, None)
        if callable(fn):
            try:
                m = fn(oid)
            except (KeyError, ValueError, LookupError):
                m = None
            if m:
                return m
    try:
        return objmesh.object_mesh(oid)          # the reader may find Mods objects itself
    except (KeyError, ValueError, LookupError):
        return None


# ------------------------------------------------------------------ routes
_ID = re.compile(r'^(ww|cc):([A-Za-z0-9_]{1,40})$')


def _object(place):
    import objmesh
    app_loc = {v: k for k, v in APP_IDS.items()}
    if place in app_loc:
        place = 'ww:' + app_loc[place]
    m = _ID.match(place or '')
    if not m:
        raise ValueError('place must look like ww:DOUBLE_BED or cc:12345')
    if m.group(1) == 'ww':
        loc = m.group(2).upper()
        if loc in _NOT_ADULT or not any(p['location'] == loc for p in ww_places()):
            raise LookupError('no such place')
        obj = objmesh.furniture_for_location(loc)
        if not obj or not obj.get('meshes'):
            raise LookupError('the object for this place is not in the game files')
        return dict(obj, place='ww:' + loc)
    oid = int(m.group(2))
    rows, _, _ = _cc_rows()
    row = next((r for r in rows if r['object_id'] == oid), None)
    if not row:
        raise LookupError('no such CC object')
    obj = cc_object(oid)
    if not obj or not obj.get('meshes'):
        raise LookupError('the CC object could not be read')
    out = dict(obj, place='cc:%d' % oid, cc=True)
    out.setdefault('surface_height', row.get('surface_height'))
    return out


def refit_places(q):
    if q.get('place'):
        return _object(q['place'])
    cc, status, note = _cc_rows()
    return {'places': ww_places(), 'groups': GROUPS + ['My CC furniture'], 'cc': cc, 'cc_status': status, 'cc_note': note}


GET = {'refit_places': refit_places}


def _warm():
    try:
        ww_places()
    except Exception:
        pass
    try:
        _cc_rows()                   # reads the CC furniture in Mods once (cached by the object reader)
    except Exception:
        pass


WARM = [_warm]

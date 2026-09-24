"""Game Doctor: "Why don't my animations show up?" (needs.md section 1).

A read-only check of the Mods folder, Mods_parked and WickedWhims' own settings. It reads package indexes only (plus
WickedWhims' animation XML snippets and a few CAS part names), caches what it learns per file by path, size and
modification time, and runs on a background thread that reports its progress.

    start_scan(force=False) -> status()        begin a scan (or report the one that runs)
    status()                                    {running, phase, done, total, text, cards, seconds, ...}
    scan(progress=None)                         the same scan, synchronously (tests)
    fix(body)                                   the two safe fixes, only on a click in the app:
        {'action': 'park', 'file': '<path inside Mods>'}           -> moves it to Mods_parked (+ _manifest.json)
        {'action': 'enable', 'file': 'dynamic', 'list': ..., 'entry': [t, v]} / {'action': 'enable', 'file': 'individual'}
        {'action': 'favorite' | 'turn_off', 'id': <WickedWhims identifier>, 'on': bool}   -> wwlists.mark (Browse tab)

Cards: {id, level: red|yellow|green|info, group, title, text, items: [{label, detail, file, action}], action, more}.
An action is {kind: 'park'|'enable'|'reveal'|'details', label, ...}; each card has one kind of safe button.

Adults only: a pack whose animations fail the adult filter (gamedata.adult_animation, _BLOCK_WORDS) is only listed
by its file name as "has content this app doesn't show"; nothing inside it is read out, cached or shown.

The user's own files and tools are known and healthy: Mods\\FitStudio (this app's exports, add-on and sound kit),
Mods\\animation (their animation packs) and Novulon's Sims Hub's Mods\\SpeedKit_Monitor.ts4script and
Mods\\!!!!!SpeedKit_Fast_*.package (fast mode's merged CC). They are never reported as a problem and never parked;
they get one green "Your own files are left alone" card, and their motions and objects still count.

Nothing is ever deleted. Fixes refuse to run while TS4_x64.exe runs. Parking never touches those files or
WickedWhims' own files, and writes Mods_parked\\_manifest.json exactly like Tools\\sims4_fitstudio\\mods_switch.py
(and SpeedKit), so "Mods - everything back (full).bat" puts parked files back.

WICKED_SIMS_DIR (tests) replaces the 'The Sims 4' folder. The game install is only read.
"""
import glob
import hashlib
import json
import os
import pickle
import re
import shutil
import threading
import time
import traceback
import xml.etree.ElementTree as ET
import zlib

from dbpf import read_index, read_resource
from clipfmt import fnv64
import gamelog

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.normpath(os.path.join(HERE, '..', 'cache', 'doctor'))
CACHE_VERSION = 4

T_CLIP, T_RIG, T_CASP, T_SNIPPET, T_STBL = 0x6B20C4F3, 0x8EAF13DE, 0x034AEECB, 0x7DF2169C, 0x220557DA
T_OBJD, T_COBJ, T_SIMDATA, T_OBJTUNING = 0xC0DB5AE7, 0x319E4F1D, 0x545AC67A, 0xB61DE6B4
OBJECT_TYPES = (T_OBJD, T_COBJ, T_SIMDATA, T_OBJTUNING)
HIGH = 1 << 63
LOW = HIGH - 1
AURIG = fnv64('auRig') & LOW

# WickedWhims' place names (SexLocationType, read from its script) and the old ones it keeps but no object uses
LOCATION_TYPES = {
    'NONE': 0, 'FLOOR': 1, 'UNDERWATER': 2, 'WALL': 3, 'TABLE_DINING_SHORT': 50, 'TABLE_DINING_LONG': 51,
    'TABLE_TV_STAND': 52, 'TABLE_COFFEE': 53, 'TABLE_ACCENT': 54, 'TABLE_PICNIC': 55, 'TABLE_OUTDOOR': 56,
    'TABLE_OUTDOOR_UMBRELLA': 57, 'TABLE_DINING_1X': 58, 'TABLE_DINING_2X': 59, 'TABLE_DINING_3X': 60,
    'TABLE_DINING_TALL_1X': 61, 'TABLE_DINING_TALL_2X': 62, 'TABLE_DINING_TALL_3X': 63, 'TABLE_DINING_ROUND_BIG': 64,
    'DESK': 100, 'BAR': 101, 'COUNTER': 102, 'COUNTER_ISLAND': 103, 'COUNTER_CORNER': 104, 'BAR_1X': 105,
    'BAR_2X': 106, 'BAR_3X': 107, 'BAR_CURVED': 108, 'SOFA': 200, 'LOVESEAT': 201, 'BENCH_OUTDOOR': 202,
    'CORNER_LOVESEAT': 203, 'MURPHY_LOVESEAT': 204, 'SECTIONAL_SOFA': 205, 'SECTIONAL_SOFA_LARGE_IN_CORNER': 206,
    'SECTIONAL_SOFA_CHAIR_LIVING': 207, 'SECTIONAL_SOFA_DYNAMIC': 208, 'SECTIONAL_SOFA_LOVESEAT': 209,
    'WORKOUT_MACHINE': 250, 'STOVE': 251, 'SPINNING_BIKE': 252, 'FREE_WEIGHTS': 253, 'TREADMILL': 254,
    'PUNCHING_BAG': 255, 'CHAIR_LIVING': 300, 'CHAIR_DINING': 301, 'CHAIR_STOOL': 302, 'CHAIR_DESK': 303,
    'CHAIR_LOUNGE': 304, 'CHAIR_LOUNGE_FLOAT': 305, 'CHAIR_LOUNGE_SOFA': 307, 'TOILET': 400, 'TOILET_STALL': 401,
    'PUBLIC_BATHROOM': 402, 'SQUAT_TOILET': 403, 'HOTTUB': 450, 'SHOWER_TUB': 451, 'SHOWER': 452, 'BATHTUB': 453,
    'OPEN_SHOWER': 454, 'CORNER_BATHTUB': 456, 'HOTTUB_INGROUND': 457, 'DOUBLE_BED': 500, 'SINGLE_BED': 501,
    'OTTOMAN': 502, 'MURPHY_DOUBLE_BED': 503, 'COFFIN': 504, 'BUNK_BED': 505, 'BED_ROLL': 506, 'SAUNA': 600,
    'YOGA_MAT': 601, 'MASSAGE_TABLE': 602, 'BEACH_TOWEL': 603, 'DANCE_FLOOR': 604, 'MURPHY_CLOSED': 605,
    'SWING_SET': 606, 'BLANKET': 607, 'DIVING_BOARD_TALL': 608, 'DIVING_BOARD_SHORT': 609, 'WINDOW': 700,
    'DOOR': 701, 'MIRROR': 702, 'SINK': 703, 'TABLE_DNING_LONG': 51, 'TABLE_OUTDOOR_UNBRELLA': 57, 'POSE': 99999,
}
OLD_LOCATIONS = {'TABLE_DINING_SHORT', 'TABLE_DINING_LONG', 'BAR', 'TABLE_DNING_LONG', 'TABLE_OUTDOOR_UNBRELLA', 'POSE'}
LOCATION_NAMES = {v: k for k, v in LOCATION_TYPES.items() if k not in ('TABLE_DNING_LONG', 'TABLE_OUTDOOR_UNBRELLA')}
PLACEHOLDER_IDS = {123456789, 987654321}
CATEGORIES = ('TEASING', 'HANDJOB', 'FOOTJOB', 'ORALJOB', 'VAGINAL', 'ANAL', 'CLIMAX')
CATEGORY_WORDS = {'TEASING': 'Teasing', 'HANDJOB': 'Handjob', 'FOOTJOB': 'Footjob', 'ORALJOB': 'Oral',
                  'VAGINAL': 'Vaginal', 'ANAL': 'Anal', 'CLIMAX': 'Climax'}
# DynamicAnimationDisableType values in dynamic_disabled_animations.json (WickedWhims' script)
DYN_CATEGORY, DYN_TAG, DYN_ORIENTATION, DYN_COUNT, DYN_PLACE, DYN_AUTHOR, DYN_PROPS = 1, 2, 3, 4, 5, 9, 10
SEX_CATEGORY_VALUES = {0: 'TEASING', 1: 'HANDJOB', 2: 'FOOTJOB', 3: 'ORALJOB', 4: 'VAGINAL', 5: 'ANAL', 6: 'CLIMAX'}
ORIENTATION_WORDS = {2: 'straight', 3: 'gay (two men)', 4: 'lesbian (two women)', 5: 'bisexual'}
TAG_NAMES = {
    1: 'TEASING', 2: 'HANDJOB', 3: 'FOOTJOB', 4: 'ORALJOB', 5: 'VAGINAL', 6: 'ANAL', 10: 'HOMOSEXUAL', 15: 'DRESSED',
    100: 'STANDING', 101: 'SITTING', 102: 'SIDEWAYS', 103: 'UPSIDE_DOWN', 104: 'CARRY', 105: 'KNEELING',
    110: 'MASTURBATION', 115: 'BLOWJOB', 116: 'DEEP_THROAT', 117: 'CUNNILINGUS', 118: 'RIMJOB', 119: 'LICKING',
    120: 'FINGERING', 121: 'SIXTYNINE', 122: 'FACE_SITTING', 123: 'TITJOB', 124: 'THIGHJOB', 125: 'BUTTJOB',
    150: 'DOGGY', 151: 'MISSIONARY', 152: 'COWGIRL', 153: 'SPOONING', 154: 'PRONE_BONE', 155: 'PILE_DRIVER',
    156: 'SPIT_ROAST', 200: 'KISSING', 201: 'SPANKING', 202: 'CHOKING', 203: 'GROPING', 204: 'TITS_SUCKING',
    205: 'TOES_SUCKING', 206: 'FLEXIBLE', 210: 'DOUBLE_PENETRATION', 211: 'PEEING', 212: 'FISTING', 250: 'CLIMAX',
    251: 'SQUIRT', 252: 'CUMSHOT', 253: 'CREAMPIE', 254: 'CUM_IN_MOUTH', 256: 'CUM_INSIDE', 257: 'BUKKAKE',
    300: 'FOREPLAY', 301: 'SLOW', 302: 'PASSIONATE', 303: 'ROUGH', 304: 'FORCED', 310: 'BDSM', 311: 'FEMDOM',
    312: 'MALEDOM', 313: 'FREE_USE', 350: 'SHY', 351: 'AWKWARD', 360: 'FUTA', 370: 'THREESOME', 371: 'FOURSOME',
    372: 'ORGY', 373: 'GANGBANG', 374: 'HAREM', 400: 'TOY', 401: 'DILDO', 402: 'CAMERA', 500: 'STORY', 501: 'CUCK',
    502: 'ONLOOKER', 503: 'WEIRD', 504: 'SLEEPING', 505: 'GROSS', 506: 'UNDER_COVERS', 550: 'VAMPIRE',
    551: 'ALIEN', 552: 'GHOST', 553: 'SERVO', 554: 'MAGIC', 600: 'DANCE', 700: 'CUSTOM_VOICE_SFX',
    1000: 'INAPPROPRIATE_INDOORS', 1001: 'INAPPROPRIATE_OUTDOORS', 1100: 'LOW_REACTION', 1101: 'NO_REACTION'}
# The game's default nude parts (WickedWhims overrides them in its own tuning package)
EA_NUDE = {0x198C: 'yfTop_Nude', 0x19A2: 'ymTop_Nude', 0x1990: 'yfBottom_Nude', 0x19AE: 'ymBottom_Nude'}
BODY_SLOTS = [('female top', ('yftop_nude', 'turbodriver_nude_top_female')),
              ('male top', ('ymtop_nude', 'turbodriver_nude_top_male')),
              ('female bottom', ('yfbottom_nude', 'turbodriver_nudebottom_af',
                                 'turbodriver_wickedwhims_nudity_cas_body_female_bottom')),
              ('male bottom', ('ymbottom_nude', 'turbodriver_nude_bottom_male')),
              ('penis', ('turbodriver_penis_',))]

WW_SCRIPT = 'turbodriver_wickedwhims_scripts.ts4script'
WW_TUNING = 'turbodriver_wickedwhims_tuning.package'
OWN_FOLDERS = ('fitstudio', 'animation')           # Mods\FitStudio and Mods\animation (first folder, any case)


# ------------------------------------------------------------------ folders
def sims_dir():
    return gamelog.sims_dir()


def mods_dir():
    return os.path.join(sims_dir(), 'Mods')


def parked_dir():
    return os.path.join(sims_dir(), 'Mods_parked')


def manifest_path():
    return os.path.join(parked_dir(), '_manifest.json')


def ww_saves_dir():
    return os.path.join(sims_dir(), 'saves', 'WickedWhimsMod')


def _rel(path, root):
    return os.path.relpath(path, root).replace('\\', '/')


def _inside(path, root):
    p, r = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    try:
        return os.path.commonpath([p, r]) == r and p != r
    except ValueError:
        return False


def is_ww_file(rel):
    """WickedWhims' own files (and anything else TURBODRIVER, WickedWhims' author, ships): never parked."""
    base = rel.replace('\\', '/').rsplit('/', 1)[-1].lower()
    return base.startswith('turbodriver_')


def is_own_file(rel):
    """Mods\\FitStudio (this app's own exports, the Fit Studio add-on and its sound kit) and Mods\\animation (the
    user's own animation packs, which mods_switch's studio set keeps on purpose)."""
    return rel.replace('\\', '/').lower().split('/', 1)[0] in OWN_FOLDERS


# Novulon's Sims Hub (Tools\\sims4_speedkit): its in-game monitor and its packs, by the exact names it writes
# (speedkit.fastmode.is_speedkit_file). The fast packs are merged copies of parked CC on purpose.
_HUB_FILE = re.compile(r'^(?:!!!!!speedkit_fast_[^/]*\.package|!!!!!speedkit_save_[0-9a-f]{8}_\d{3}\.package'
                       r'|speedkit_usedcc_\d{3}\.package|speedkit_monitor[^/]*\.ts4script)$', re.I)


def is_hub_file(rel):
    """Mods\\SpeedKit_Monitor.ts4script and Mods\\!!!!!SpeedKit_Fast_*.package (the Sims Hub's fast mode)."""
    return bool(_HUB_FILE.match(rel.replace('\\', '/').rsplit('/', 1)[-1]))


def is_user_tool(rel):
    """The user's own files and tools: known and healthy. The Doctor never reports them as a problem and never
    offers to park them (their motions and objects still count, so nothing that uses them looks missing)."""
    return is_own_file(rel) or is_hub_file(rel)


def is_known(rel):
    """WickedWhims' own files or the user's own tools."""
    return is_ww_file(rel) or is_user_tool(rel)


def _adult_ok(anim):
    """The app's adults-only filter. A missing gender is a creator mistake (it gets its own card), not a reason to
    hide the pack, so an empty gender is tested as 'BOTH'."""
    import gamedata as G
    a = dict(anim)
    a['actors'] = [dict(x, genders=[g for g in x.get('genders') or [] if g] or ['BOTH'], gender=x.get('gender') or 'BOTH',
                        clip=x.get('clip') or '') for x in anim.get('actors') or []]
    if not a['actors']:
        return True
    return G.adult_animation(a)


def _blocked_rel(rel):
    import gamedata as G
    return bool(G._BLOCK_WORDS.search(rel.replace('_', ' ').replace('-', ' ')))


# ------------------------------------------------------------------ small readers
def _stbl(data):
    out = {}
    if data[:4] != b'STBL':
        return out
    count = int.from_bytes(data[7:15], 'little')
    p = 21
    for _ in range(count):
        if p + 7 > len(data):
            break
        key = int.from_bytes(data[p:p + 4], 'little'); p += 5
        n = int.from_bytes(data[p:p + 2], 'little'); p += 2
        out[key] = data[p:p + n].decode('utf-8', 'replace'); p += n
    return out


def _snippet_head(f, e, n=400):
    """The first bytes of a snippet resource, without unpacking all of it."""
    f.seek(e['pos'])
    data = f.read(e['size'])
    if e['comp'] == 0x5A42:
        return zlib.decompressobj().decompress(data, n)
    if e['comp'] == 0xFFFF:
        from dbpf import refpack
        return refpack(data)[:n]
    return data[:n]


def _field(el, name):
    for c in el:
        if c.get('n') == name:
            return (c.text or '').strip()
    return ''


def parse_animation_xml(xml):
    """WickedWhims animation snippet -> [{name, name_key, author, locations, custom, category, actors[]}] with the
    raw texts the creator typed (nothing corrected), so the doctor can say what is wrong."""
    try:
        root = ET.fromstring(xml if isinstance(xml, bytes) else xml.encode('utf-8'))
    except ET.ParseError:
        return None
    out = []
    for lst in root.iter():
        if lst.get('n') != 'animations_list':
            continue
        for an in lst:
            if not len(an):
                continue                          # an empty item: not an animation at all
            acts = next((c for c in an if c.get('n') == 'animation_actors_list'), None)
            actors = []
            for a in (acts if acts is not None else []):
                genders = [(c.text or '').strip() for c in a if c.get('n') == 'animation_genders']
                prefs = [p.strip() for c in a if c.get('n') == 'animation_pref_gender' for p in (c.text or '').split(',') if p.strip()]
                actors.append({'clip': _field(a, 'animation_clip_name') or _field(a, 'animation_name'),
                               'type': _field(a, 'animation_type'), 'genders': [g for g in genders if g], 'prefs': prefs})
            out.append({'name': _field(an, 'animation_raw_display_name'), 'name_key': _field(an, 'animation_display_name'),
                        'author': _field(an, 'animation_author'), 'locations': _field(an, 'animation_locations'),
                        'custom': _field(an, 'animation_custom_locations'), 'category': _field(an, 'animation_category'),
                        'actors': actors})
    return out


# ------------------------------------------------------------------ the game's own objects and clips (cached)
def _game_packages():
    import gamedata as G
    try:
        g = G.game_dir()
    except Exception:
        return []
    pats = [os.path.join(g, 'Data', 'Client', '*.package'), os.path.join(g, 'Data', 'Simulation', '*.package'),
            os.path.join(g, '*', 'Client*Build*.package'), os.path.join(g, '*', 'Simulation*Build*.package'),
            os.path.join(g, 'Delta', '*', '*Build*.package')]
    out = set()
    for p in pats:
        out.update(glob.glob(p))
    return sorted(out)


_game_mem = None


def game_sets():
    """{'objects': set, 'clips': set} of instance ids in the game's own packages (index only; cached in cache/doctor)."""
    global _game_mem
    pk = _game_packages()
    sig = [(p, os.path.getsize(p), int(os.path.getmtime(p))) for p in pk]
    if _game_mem and _game_mem['sig'] == sig:
        return _game_mem
    path = os.path.join(CACHE_DIR, 'game_v1.pkl')
    try:
        with open(path, 'rb') as f:
            cached = pickle.load(f)
        if cached.get('sig') == sig:
            _game_mem = cached
            return cached
    except Exception:
        pass
    objects, clips = set(), set()
    for p in pk:
        try:
            for e in read_index(p):
                t = e['type']
                if t == T_CLIP:
                    clips.add(e['inst'] & LOW)
                elif t in OBJECT_TYPES:
                    objects.add(e['inst'] & LOW)
        except Exception:
            continue
    res = {'sig': sig, 'objects': objects, 'clips': clips}
    _store_pickle(path, res)
    _game_mem = res
    return res


def _store_pickle(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = '%s.%d-%d.tmp' % (path, os.getpid(), threading.get_ident())
    try:
        with open(tmp, 'wb') as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


# ------------------------------------------------------------------ WickedWhims' nude parts
def nude_parts(ww_tuning):
    """{casp instance: (slot, name)} - the nude body parts a body override replaces."""
    parts = {i: n for i, n in EA_NUDE.items()}
    if ww_tuning:
        try:
            with open(ww_tuning, 'rb') as f:
                for e in read_index(ww_tuning):
                    if e['type'] != T_CASP:
                        continue
                    f.seek(e['pos'])
                    raw = f.read(e['size'])
                    d = zlib.decompress(raw) if e['comp'] == 0x5A42 else raw
                    if len(d) < 16:
                        continue
                    p, n, shift = 12, 0, 0
                    while True:
                        b = d[p]; p += 1; n |= (b & 0x7F) << shift; shift += 7
                        if not b & 0x80:
                            break
                    parts[e['inst']] = d[p:p + n].decode('utf-16-be', 'replace')
        except Exception:
            traceback.print_exc()
    out = {}
    for inst, name in parts.items():
        low = name.lower()
        for slot, prefixes in BODY_SLOTS:
            if any(low.startswith(x) for x in prefixes):
                out[inst] = (slot, name)
                break
    return out


# ------------------------------------------------------------------ one package
def package_facts(path, nude):
    """What the doctor needs from one package, from its index (plus WickedWhims' animation snippets)."""
    facts = {'clips': {}, 'objects': [], 'rig': False, 'nude': [], 'anims': [], 'ww': 0, 'blocked': False,
             'error': None, 'entries': 0}
    try:
        idx = read_index(path)
    except Exception as ex:
        facts['error'] = 'not a package the game can read (%s)' % (str(ex)[:80] or type(ex).__name__)
        return facts
    facts['entries'] = len(idx)
    snippets, stbls = [], []
    for e in idx:
        t = e['type']
        if t == T_CLIP:
            facts['clips'][e['inst'] & LOW] = (e['size'], e['mem'])
        elif t in OBJECT_TYPES:
            facts['objects'].append(e['inst'] & LOW)
        elif t == T_RIG and (e['inst'] & LOW) == AURIG:
            facts['rig'] = True
        elif t == T_CASP and e['inst'] in nude:
            facts['nude'].append(e['inst'])
        elif t == T_SNIPPET and 0 < e['mem'] <= 16_000_000:
            snippets.append(e)
        elif t == T_STBL and ((e['inst'] >> 56) & 0xFF) == 0:
            stbls.append(e)
    xmls = []
    if snippets:
        try:
            with open(path, 'rb') as f:
                for e in snippets:
                    try:
                        head = _snippet_head(f, e)
                    except Exception:
                        continue
                    if b'AnimationPackage' in head and (b'WickedWhims' in head or b'WickedWoohoo' in head):
                        xmls.append(e)
        except OSError as ex:
            facts['error'] = str(ex)[:120]
    anims = []
    for e in xmls:
        try:
            parsed = parse_animation_xml(read_resource(path, e))
        except Exception:
            parsed = None
        if parsed is None:
            facts.setdefault('bad_xml', 0)
            facts['bad_xml'] += 1
            continue
        facts['ww'] += 1
        anims.extend(parsed)
    if anims and any(a['name_key'] and not a['name'] for a in anims):
        strings = {}
        for e in stbls:
            try:
                strings.update(_stbl(read_resource(path, e)))
            except Exception:
                pass
        for a in anims:
            if not a['name'] and a['name_key']:
                try:
                    a['name'] = strings.get(int(a['name_key'], 0), '')
                except ValueError:
                    pass
    if anims and not all(_adult_ok(a) for a in anims):
        # adults only: nothing from this pack is kept, only that it has such content
        facts['blocked'] = True
        facts['blocked_count'] = len(anims)
        anims = []
    facts['anims'] = anims
    return facts


# ------------------------------------------------------------------ problems of one animation
def classify(anim, clips, objects):
    """-> (never: [reason], notes: [reason], examples: {reason: text}) for one parsed animation."""
    never, notes, ex = [], [], {}
    if not anim['name'] and not anim['name_key']:
        never.append('no_name')
    if not anim['author']:
        never.append('no_author')
    if not anim['actors'] or any(not x['clip'] for x in anim['actors']):
        never.append('no_actors')
    if any(not x['genders'] for x in anim['actors']):
        never.append('no_gender')
    cat = anim['category'].upper().strip()
    if cat not in CATEGORIES:
        never.append('bad_category')
        ex['bad_category'] = anim['category'] or '(empty)'
    tokens = [t.strip().upper() for t in anim['locations'].split(',') if t.strip()]
    places = [t for t in tokens if t != 'NONE']
    valid = [t for t in places if t in LOCATION_TYPES and t not in OLD_LOCATIONS]
    old = [t for t in places if t in OLD_LOCATIONS]
    unknown = [t for t in places if t not in LOCATION_TYPES]
    ids = []
    for x in anim['custom'].split(','):
        x = x.strip()
        if x:
            try:
                ids.append(int(x))
            except ValueError:
                pass
    real_ids = [i for i in ids if i not in PLACEHOLDER_IDS]
    if not valid:
        # no place WickedWhims can match: a custom object decides, else it never shows up
        if real_ids:
            if not any((i & LOW) in objects for i in real_ids):
                never.append('missing_object')
                ex['missing_object'] = ', '.join(str(i) for i in real_ids[:2])
        elif unknown:
            never.append('unknown_place')
            ex['unknown_place'] = ', '.join(unknown[:3])
        elif old:
            never.append('old_place')
            ex['old_place'] = ', '.join(old[:3])
        elif ids:
            never.append('placeholder')
        else:
            never.append('no_place')
    missing = [x['clip'] for x in anim['actors'] if x['clip'] and (fnv64(x['clip']) & LOW) not in clips]
    if missing:
        never.append('missing_clip')
        ex['missing_clip'] = missing[0]
    bad_types = [x['type'] for x in anim['actors'] if x['type'] and x['type'].upper().strip() not in CATEGORIES + ('NONE',)]
    if bad_types:
        notes.append('bad_act')
        ex['bad_act'] = bad_types[0]
    if unknown and valid:
        notes.append('some_unknown_place')
        ex['some_unknown_place'] = ', '.join(unknown[:3])
    return never, notes, ex


REASONS = {
    'no_name': ('have no name', 'WickedWhims needs a name for every animation.'),
    'no_author': ('have no creator name', 'WickedWhims needs a creator name for every animation.'),
    'no_actors': ('have no motion set for a sim', ''),
    'no_gender': ('have a sim with no gender set', ''),
    'bad_category': ("have the kind of act spelled wrong ({x})", "WickedWhims only knows Teasing, Handjob, Footjob, Oral, "
                                                                 "Vaginal, Anal and Climax."),
    'no_place': ('have no place at all', 'WickedWhims only offers an animation where it is set to play.'),
    'placeholder': ("still use the template's example place (123456789, 987654321)", 'That place is only an example '
                                                                                   "in WickedWhims' template - no object has it."),
    'unknown_place': ("are set to a place WickedWhims doesn't know ({x})", 'A place name that is cut off or spelled '
                                                                          'wrong never matches any furniture.'),
    'old_place': ("use an old place name WickedWhims no longer uses ({x})", ''),
    'missing_object': ("need a custom object that isn't installed", 'They only show up on that furniture, and it is '
                                                                   'not in your Mods.'),
    'missing_clip': ("use a motion that's in none of your files ({x})", 'The motion (clip) is missing, so WickedWhims '
                                                                       "can't play them."),
    'bad_act': ("have a sim's act spelled wrong ({x})", 'They still show up, but WickedWhims treats that sim as doing '
                                                       'nothing (no cum, no act stats).'),
    'some_unknown_place': ("list a place WickedWhims doesn't know ({x}) next to good ones", 'They still show up at '
                                                                                            'the good places.'),
}
NEVER_ORDER = ['no_place', 'placeholder', 'unknown_place', 'old_place', 'missing_object', 'missing_clip', 'bad_category',
               'no_name', 'no_author', 'no_actors', 'no_gender']


# ------------------------------------------------------------------ WickedWhims' settings
def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _nice(s):
    return str(s).replace('_', ' ').lower().capitalize()


def explain_dynamic(entry, autonomy=False):
    """[type, value] from dynamic_disabled_animations.json -> (plain words, level)."""
    try:
        t, v = int(entry[0]), entry[1]
    except (TypeError, ValueError, IndexError):
        return 'Some animations are switched off in WickedWhims\' settings.', 'yellow'
    who = ' when sims choose on their own' if autonomy else ''
    if t == DYN_PROPS and v == 2:
        return ("WickedWhims hides animations that need a prop (an object like a toy) that isn't installed. This is "
                "WickedWhims' normal setting%s." % ('' if not autonomy else ' for sims choosing on their own'), 'info')
    if t == DYN_PROPS and v == 1:
        return 'All animations that use props (objects the sims hold or use) are switched off%s.' % who, 'yellow'
    if t == DYN_CATEGORY:
        c = SEX_CATEGORY_VALUES.get(v if isinstance(v, int) else -99, str(v))
        return "All '%s' animations are switched off in WickedWhims' Dynamic Disabler%s." % (CATEGORY_WORDS.get(c, _nice(c)), who), 'yellow'
    if t == DYN_TAG:
        tag = TAG_NAMES.get(v, str(v)) if isinstance(v, int) else str(v)
        return "All animations tagged '%s' are switched off in WickedWhims' Dynamic Disabler%s." % (_nice(tag), who), 'yellow'
    if t == DYN_ORIENTATION:
        return 'All %s animations are switched off in WickedWhims\' Dynamic Disabler%s.' % (
            ORIENTATION_WORDS.get(v, 'of one kind of couple'), who), 'yellow'
    if t == DYN_COUNT:
        return 'All animations for %s sims are switched off in WickedWhims\' Dynamic Disabler%s.' % (v, who), 'yellow'
    if t == DYN_PLACE:
        loc = LOCATION_NAMES.get(v, str(v)) if isinstance(v, int) else str(v)
        return "All animations on '%s' are switched off in WickedWhims' Dynamic Disabler%s." % (_nice(loc), who), 'yellow'
    if t == DYN_AUTHOR:
        return "All animations by '%s' are switched off in WickedWhims' Dynamic Disabler%s." % (v, who), 'yellow'
    return "Some animations are switched off in WickedWhims' settings%s." % who, 'yellow'


def settings_cards():
    cards = []
    d = ww_saves_dir()
    dyn = _read_json(os.path.join(d, 'dynamic_disabled_animations.json'))
    if isinstance(dyn, dict):
        for key, autonomy in (('disabled_animation_types', False), ('autonomy_disabled_animation_types', True)):
            for entry in dyn.get(key) or []:
                text, level = explain_dynamic(entry, autonomy)
                if autonomy and level == 'yellow':
                    level = 'info'
                cards.append({'id': 'dyn:%s:%s' % (key, json.dumps(entry)), 'level': level, 'group': 'settings',
                              'title': 'Turned off in WickedWhims' + (' (for sims choosing on their own)' if autonomy else ''),
                              'text': text, 'entry': entry,
                              'action': {'kind': 'enable', 'label': 'Turn back on', 'file': 'dynamic', 'list': key, 'entry': entry}})
    one = _read_json(os.path.join(d, 'all_disabled_animations.json'))
    if isinstance(one, dict):
        n = len(one.get('disabled_animations') or [])
        if n:
            cards.append({'id': 'single:player', 'level': 'yellow', 'group': 'settings', 'title': 'Turned off one by one',
                          'text': '%d animation%s switched off one by one in WickedWhims\' settings, so %s never offered.'
                                  % (n, 's are' if n != 1 else ' is', 'they are' if n != 1 else 'it is'),
                          'action': {'kind': 'enable', 'label': 'Turn them all back on', 'file': 'individual'}})
        n = len(one.get('autonomy_disabled_animations') or [])
        if n:
            cards.append({'id': 'single:autonomy', 'level': 'info', 'group': 'settings',
                          'title': 'Turned off for sims choosing on their own',
                          'text': "%d animation%s never picked when sims start sex on their own (you can still pick %s)."
                                  % (n, 's are' if n != 1 else ' is', 'them' if n != 1 else 'it')})
    return cards


def _game_options():
    """(mods on, script mods on) from Options.ini, None when unknown."""
    path = os.path.join(sims_dir(), 'Options.ini')
    vals = {}
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            for line in f:
                if '=' in line:
                    k, v = line.split('=', 1)
                    vals[k.strip().lower()] = v.strip()
    except OSError:
        return None, None
    mods = None if 'modsdisabled' not in vals else vals['modsdisabled'] != '1'
    scripts = None if 'scriptmodsenabled' not in vals else vals['scriptmodsenabled'] == '1'
    return mods, scripts


def _game_version():
    try:
        with open(os.path.join(sims_dir(), 'GameVersion.txt'), 'rb') as f:
            m = re.search(rb'\d+(?:\.\d+){2,}', f.read(200))
            return m.group(0).decode() if m else None
    except OSError:
        return None


def _ww_version():
    try:
        with open(os.path.join(ww_saves_dir(), 'last_version_control.ww'), encoding='utf-8', errors='replace') as f:
            m = re.search(r'v\d+[0-9A-Za-z]*', f.read(200))
            return m.group(0) if m else None
    except OSError:
        return None


def _max_depth():
    """How many folders deep the game reads packages (Mods\\Resource.cfg; 5 when it can't be read)."""
    try:
        with open(os.path.join(mods_dir(), 'Resource.cfg'), encoding='utf-8', errors='replace') as f:
            depths = [line.count('*/') for line in f if line.strip().lower().startswith('packedfile')]
        return max(depths) if depths else 5
    except OSError:
        return 5


# ------------------------------------------------------------------ the scan
def _walk(root):
    """[(rel, size, mtime)] of every file under root."""
    out = []
    if not os.path.isdir(root):
        return out
    for dp, dn, fn in os.walk(root):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((_rel(p, root), st.st_size, st.st_mtime))
    return out


def _cache_file():
    key = hashlib.sha1(os.path.normcase(os.path.abspath(sims_dir())).encode('utf-8')).hexdigest()[:10]
    return os.path.join(CACHE_DIR, 'packages_%s.pkl' % key)


def _nude_key(nude):
    return hashlib.sha1(json.dumps(sorted(nude)).encode()).hexdigest()


def scan(progress=None, emit=None):
    """The whole check. progress(phase, done, total, text); emit(card) as cards become known. -> result dict."""
    t0 = time.time()
    progress = progress or (lambda *a: None)
    emit = emit or (lambda c: None)
    cards = []

    def add(card):
        cards.append(card)
        emit(card)

    mods, parked = mods_dir(), parked_dir()
    progress('files', 0, 0, 'Looking through your Mods folder...')
    mod_files = _walk(mods)
    parked_files = [f for f in _walk(parked) if not f[0].lower().startswith('_old_caches/')]
    mod_pk = [f for f in mod_files if f[0].lower().endswith('.package')]
    parked_pk = [f for f in parked_files if f[0].lower().endswith('.package')]

    # ---- install, options, versions (quick)
    session = {}
    try:
        lg = gamelog.read(check_running=False)
        session = lg.get('session') or {}
    except Exception:
        traceback.print_exc()
    for c in _install_cards(mod_files, parked_files, session):
        add(c)
    for c in _depth_cards(mod_files):
        add(c)
    for c in settings_cards():
        add(c)

    # ---- the game's own objects and clips
    progress('game', 0, 0, "Reading the game's own objects...")
    try:
        game = game_sets()
    except Exception:
        traceback.print_exc()
        game = {'objects': set(), 'clips': set()}

    # ---- every package (cached by path, size and time)
    ww_tuning = next((os.path.join(mods, r) for r, s, m in mod_files if r.lower().rsplit('/', 1)[-1] == WW_TUNING), None) \
        or next((os.path.join(parked, r) for r, s, m in parked_files if r.lower().rsplit('/', 1)[-1] == WW_TUNING), None)
    nude = nude_parts(ww_tuning)
    nkey = _nude_key(nude)
    cpath = _cache_file()
    cache = {}
    try:
        with open(cpath, 'rb') as f:
            c = pickle.load(f)
        if c.get('version') == CACHE_VERSION and c.get('nude') == nkey:
            cache = c.get('files', {})
    except Exception:
        pass
    new_cache, facts = {}, {}
    todo = [('mods', mods, f) for f in mod_pk] + [('parked', parked, f) for f in parked_pk]
    total, read_now = len(todo), 0
    for k, (where, root, (rel, size, mtime)) in enumerate(todo):
        path = os.path.join(root, rel)
        key = os.path.normcase(path)
        hit = cache.get(key)
        if hit and hit['size'] == size and hit['mtime'] == mtime:
            fa = hit['facts']
        else:
            progress('packages', k, total, 'Reading %s' % rel.rsplit('/', 1)[-1])
            fa = package_facts(path, nude)
            read_now += 1
        new_cache[key] = {'size': size, 'mtime': mtime, 'facts': fa}
        facts[(where, rel)] = fa
        if k % 8 == 0:
            progress('packages', k, total, 'Reading %s' % rel.rsplit('/', 1)[-1])
    _store_pickle(cpath, {'version': CACHE_VERSION, 'nude': nkey, 'files': new_cache})
    progress('checking', total, total, 'Putting it all together...')

    active = {rel: fa for (w, rel), fa in facts.items() if w == 'mods'}
    set_aside = {rel: fa for (w, rel), fa in facts.items() if w == 'parked'}
    for c in _package_cards(active, game, nude, where='mods'):
        add(c)
    for c in _parked_cards(active, set_aside, game, nude):
        add(c)
    for c in _session_cards(session, mod_files):
        add(c)
    for c in _own_cards(mod_files):
        add(c)

    order = {'red': 0, 'yellow': 1, 'info': 2, 'green': 3}
    cards.sort(key=lambda c: (order.get(c['level'], 9), c.get('sort', 50)))
    summary = {'mods_files': len(mod_files), 'mods_packages': len(mod_pk), 'parked_packages': len(parked_pk),
               'bytes': sum(s for r, s, m in mod_files) + sum(s for r, s, m in parked_files), 'read': read_now,
               'cached': total - read_now,
               'animations': sum(len(fa['anims']) for fa in active.values()),
               'packs': sum(1 for fa in active.values() if fa['ww']),
               'red': sum(1 for c in cards if c['level'] == 'red'),
               'yellow': sum(1 for c in cards if c['level'] == 'yellow'),
               'green': sum(1 for c in cards if c['level'] == 'green')}
    return {'cards': cards, 'summary': summary, 'seconds': round(time.time() - t0, 2), 'sims_dir': sims_dir(),
            'session': session, 'finished': time.time()}


def _install_cards(mod_files, parked_files, session):
    cards = []
    scripts = [r for r, s, m in mod_files if r.lower().rsplit('/', 1)[-1] == WW_SCRIPT]
    tunings = [r for r, s, m in mod_files if r.lower().rsplit('/', 1)[-1] == WW_TUNING]
    parked_scripts = [r for r, s, m in parked_files if r.lower().rsplit('/', 1)[-1] == WW_SCRIPT]
    game_v = _game_version() or session.get('game_version')
    ww_v = session.get('ww_version') or _ww_version()
    if not os.path.isdir(mods_dir()):
        cards.append({'id': 'install:nomods', 'level': 'red', 'group': 'install', 'sort': 0,
                      'title': 'There is no Mods folder',
                      'text': 'The game looks for mods in Documents\\Electronic Arts\\The Sims 4\\Mods, and it is not there.'})
        return cards
    if not scripts:
        if parked_scripts:
            cards.append({'id': 'install:wwparked', 'level': 'red', 'group': 'install', 'sort': 0,
                          'title': 'WickedWhims is set aside',
                          'text': "WickedWhims is in Mods_parked, so the game doesn't load it and no animation shows up. "
                                  "Put your mods back with 'Mods - everything back (full).bat'."})
        else:
            cards.append({'id': 'install:noww', 'level': 'red', 'group': 'install', 'sort': 0,
                          'title': "WickedWhims isn't installed",
                          'text': "The game can't show WickedWhims animations without WickedWhims. Put its two files "
                                  '(TURBODRIVER_WickedWhims_Scripts.ts4script and _Tuning.package) in Mods\\scripts.'})
    elif len(scripts) > 1:
        cards.append({'id': 'install:twice', 'level': 'red', 'group': 'install', 'sort': 0,
                      'title': 'WickedWhims is installed twice',
                      'text': 'Two copies fight each other. Keep only the newest one.',
                      'items': [{'label': r, 'file': r, 'action': {'kind': 'reveal', 'label': 'Show me', 'file': r}} for r in scripts]})
    elif scripts[0].count('/') > 1:
        cards.append({'id': 'install:wwdeep', 'level': 'red', 'group': 'install', 'sort': 0,
                      'title': 'WickedWhims is too deep in folders',
                      'text': 'The game only runs script mods that sit at most one folder inside Mods, so WickedWhims never '
                              'starts. Move its two files into Mods\\scripts.',
                      'items': [{'label': scripts[0].rsplit('/', 1)[-1], 'detail': 'Mods/' + scripts[0], 'file': scripts[0],
                                 'action': {'kind': 'reveal', 'label': 'Show me', 'file': scripts[0]}}]})
    elif not tunings:
        cards.append({'id': 'install:half', 'level': 'red', 'group': 'install', 'sort': 0,
                      'title': 'Half of WickedWhims is missing',
                      'text': "TURBODRIVER_WickedWhims_Tuning.package is not in your Mods. Put it next to the script file."})
    else:
        bits = []
        if session.get('available') is not None:
            bits.append('Last time you played, WickedWhims had %d animation%s ready.' % (
                session['available'], '' if session['available'] == 1 else 's'))
        cards.append({'id': 'install:ok', 'level': 'green', 'group': 'install', 'sort': 0,
                      'title': 'WickedWhims %sis installed' % (ww_v + ' ' if ww_v else ''),
                      'text': ('The Sims 4 %s. ' % game_v if game_v else '') + ' '.join(bits),
                      'facts': {'ww': ww_v, 'game': game_v}})
    mods_on, scripts_on = _game_options()
    if mods_on is False or scripts_on is False:
        cards.append({'id': 'install:options', 'level': 'red', 'group': 'install', 'sort': 1,
                      'title': 'Mods are turned off in the game',
                      'text': "In The Sims 4 open Game Options > Other, tick 'Enable Custom Content and Mods' and "
                              "'Script Mods Allowed', then restart the game."})
    return cards


def _depth_cards(mod_files):
    cards = []
    mod_files = [f for f in mod_files if not is_user_tool(f[0])]        # the user's own tools are never flagged
    deep = [r for r, s, m in mod_files if r.lower().endswith('.ts4script') and r.count('/') > 1]
    if deep:
        cards.append({'id': 'depth:scripts', 'level': 'red', 'group': 'files', 'sort': 2,
                      'title': 'Script mods are too deep in folders',
                      'text': "The game only runs script mods that sit at most one folder inside Mods. %s never run%s. "
                              "Move %s up so it sits in Mods or one folder inside it." % (
                                  'These' if len(deep) > 1 else 'This one', '' if len(deep) > 1 else 's',
                                  'them' if len(deep) > 1 else 'it'),
                      'items': [{'label': r.rsplit('/', 1)[-1], 'detail': '%d folders deep: Mods/%s' % (r.count('/'), r),
                                 'file': r, 'action': {'kind': 'reveal', 'label': 'Show me', 'file': r}} for r in deep]})
    limit = _max_depth()
    too_deep = [r for r, s, m in mod_files if r.lower().endswith('.package') and r.count('/') > limit]
    if too_deep:
        cards.append({'id': 'depth:packages', 'level': 'red', 'group': 'files', 'sort': 3,
                      'title': 'Some files are too deep in folders',
                      'text': 'The game only reads packages up to %d folders inside Mods, so %d file%s never load.' % (
                          limit, len(too_deep), '' if len(too_deep) == 1 else 's'),
                      'items': [{'label': r.rsplit('/', 1)[-1], 'detail': 'Mods/' + r, 'file': r,
                                 'action': {'kind': 'reveal', 'label': 'Show me', 'file': r}} for r in too_deep[:30]]})
    return cards


def _parkable(rel):
    return not is_known(rel)


def _park_action(rel):
    return {'kind': 'park', 'label': 'Park this file', 'file': rel} if _parkable(rel) else None


def _conflicts(pk, nude):
    """Rig clashes, body clashes and clip-name clashes between the packages in pk ({rel: facts}). WickedWhims' own
    files and the user's own tools never count as a rig or body clash; clip pairs keep them (see _package_cards)."""
    rigs = [rel for rel, fa in pk.items() if fa['rig'] and not is_known(rel.replace('(set aside) ', '', 1))]
    slots = {}
    for rel, fa in pk.items():
        if is_known(rel.replace('(set aside) ', '', 1)):
            continue
        for inst in fa['nude']:
            slot = nude.get(inst, ('body', ''))[0]
            slots.setdefault(slot, {}).setdefault(rel, set()).add(nude.get(inst, ('', '?'))[1])
    holders = {}
    for rel in sorted(pk):
        for inst, sz in pk[rel]['clips'].items():
            holders.setdefault(inst, []).append((rel, sz))
    pairs = {}
    for hs in holders.values():
        if len(hs) < 2:
            continue
        # every pair of files that share the motion name (a file that sorts first - like the Sims Hub's fast pack -
        # must not hide a clash between two others); a name in very many files pairs each with the first two only
        firsts = hs if len(hs) <= 8 else hs[:2]
        for i, (a, sa) in enumerate(firsts):
            for b, sb in hs[i + 1:]:
                p = pairs.setdefault((a, b), [0, 0])
                p[0] += 1
                if sa != sb:
                    p[1] += 1
    return rigs, {s: v for s, v in slots.items() if len(v) > 1}, pairs


def _package_cards(pk, game, nude, where='mods'):
    cards = []
    rigs, body, pairs = _conflicts(pk, nude)
    mtime = {}
    root = mods_dir()
    for rel in pk:
        try:
            mtime[rel] = os.path.getmtime(os.path.join(root, rel))
        except OSError:
            mtime[rel] = 0
    if rigs:
        cards.append({'id': 'rig', 'level': 'red', 'group': 'clash', 'sort': 5, 'need': len(rigs),
                      'title': "Another mod changes WickedWhims' skeleton",
                      'text': "These files carry their own copy of the sims' skeleton (the rig). It fights WickedWhims' "
                              'rig: penises, tongues and hips stretch or float. Park them.',
                      'items': [{'label': r.rsplit('/', 1)[-1], 'detail': 'Mods/' + r, 'file': r, 'action': _park_action(r)} for r in rigs]})
    for slot, files in sorted(body.items()):
        cards.append({'id': 'body:' + slot, 'level': 'red', 'group': 'clash', 'sort': 6, 'need': len(files) - 1,
                      'title': 'More than one body for the %s' % slot,
                      'text': 'These files all replace the same nude %s. Only one of them shows, so bodies look wrong or '
                              'change at random. Keep the one you like and park the others.' % slot,
                      'items': [{'label': r.rsplit('/', 1)[-1], 'detail': 'Mods/' + r, 'file': r, 'action': _park_action(r)}
                                for r in sorted(files)]})
    # clip names used by two packs (the biggest overlaps; the rest in one line). Two known files (WickedWhims' own,
    # the user's own tools) never make a card; with one known file, the other one is the one to park. The Sims Hub's
    # fast packs are merged copies on purpose and the Hub decides what sits next to them, so they make no card at all.
    pairs = {ab: v for ab, v in pairs.items()
             if not (is_known(ab[0]) and is_known(ab[1])) and not is_hub_file(ab[0]) and not is_hub_file(ab[1])}
    ranked = sorted(pairs.items(), key=lambda kv: (-kv[1][0], kv[0]))
    if len(ranked) > 12:
        rest = ranked[12:]
        cards.append({'id': 'clips:more', 'level': 'yellow', 'group': 'clash', 'sort': 8.5,
                      'title': '%d more pairs of packs share motion names' % len(rest),
                      'text': 'The biggest overlaps are listed above; these are smaller.',
                      'items': [{'label': '%s + %s' % (a.rsplit('/', 1)[-1], b.rsplit('/', 1)[-1]), 'detail': '%d motions' % n}
                                for (a, b), (n, d) in rest[:40]]})
    for (a, b), (n, differ) in ranked[:12]:
        if n < 1:
            continue
        older, newer = (a, b) if mtime.get(a, 0) <= mtime.get(b, 0) else (b, a)
        target = older if _parkable(older) else (newer if _parkable(newer) else None)
        na = {(x['name'].lower(), x['author'].lower()) for x in pk[a]['anims']}
        nb = {(x['name'].lower(), x['author'].lower()) for x in pk[b]['anims']}
        shared = len(na & nb)
        fa, fb = older.rsplit('/', 1)[-1], newer.rsplit('/', 1)[-1]
        kept = older if is_known(older) else (newer if is_known(newer) else None)
        if kept and target:
            fix = ' Park %s - %s is one of %s own files and stays.' % (
                target.rsplit('/', 1)[-1], kept.rsplit('/', 1)[-1], "WickedWhims'" if is_ww_file(kept) else 'your')
        else:
            fix = None
        if shared and shared * 2 >= min(len(na), len(nb)):
            title = 'Two versions of the same pack are installed'
            text = ('%s (older) and %s (newer) have %d of the same animations and %d motions with the same names. '
                    'WickedWhims keeps only one of each, and the motions get mixed up.' % (fa, fb, shared, n))
            text += fix or ' Park the older one.'
        elif differ == 0:
            title = 'The same motions are installed twice'
            text = '%s and %s share %d motion%s. It looks like the same pack twice' % (fa, fb, n, '' if n == 1 else 's')
            text += ('.' + fix) if fix else ' - keep one.'
        else:
            title = 'Two packs use the same motion names'
            text = ("%s and %s both have %d motion%s with the same name, so one of them plays the other one's motion."
                    % (fa, fb, n, '' if n == 1 else 's')) + (fix or '')
        cards.append({'id': 'clips:%s|%s' % (a, b), 'level': 'yellow', 'group': 'clash', 'sort': 8, 'need': 1, 'title': title,
                      'text': text,
                      'items': [{'label': r.rsplit('/', 1)[-1],
                                 'detail': ('older' if r == older else 'newer') + ((' - WickedWhims, stays' if is_ww_file(r) else ' - yours, stays') if r == kept else '') + ' - Mods/' + r,
                                 'file': r, 'action': _park_action(r) if r == target else None} for r in (older, newer)]})
    # every package's clips (for "a motion that's in none of your files")
    clips = set(game.get('clips') or ())
    objects = set(game.get('objects') or ())
    for fa in pk.values():
        clips.update(fa['clips'])
        objects.update(fa['objects'])
    good_packs, good_anims, blocked = 0, set(), []
    for rel in sorted(pk):
        fa = pk[rel]
        if is_user_tool(rel):
            continue                               # the user's own files: the "Your own files" card, never a problem
        if fa['blocked']:
            blocked.append(rel)
            continue
        if not fa['anims']:
            continue
        c = pack_card(rel, fa, clips, objects)
        if c:
            cards.append(c)
        else:
            good_packs += 1
            good_anims.update((x['name'].lower(), x['author'].lower()) for x in fa['anims'])   # the same one twice counts once
    if good_packs:
        cards.append({'id': 'packs:ok', 'level': 'green', 'group': 'packs', 'sort': 20,
                      'title': '%d animation pack%s look%s fine' % (good_packs, '' if good_packs == 1 else 's', 's' if good_packs == 1 else ''),
                      'text': '%d animation%s in %s can show up in the game.' % (
                          len(good_anims), '' if len(good_anims) == 1 else 's', 'it' if good_packs == 1 else 'them')})
    if blocked:
        cards.append({'id': 'packs:blocked', 'level': 'info', 'group': 'packs', 'sort': 30,
                      'title': "Has content this app doesn't show",
                      'text': 'This app is for adults only, so it never opens or shows what is inside these files.',
                      'items': [{'label': r.rsplit('/', 1)[-1], 'detail': 'Mods/' + r, 'file': r, 'action': _park_action(r)} for r in blocked]})
    bad_files = [rel for rel, fa in pk.items() if fa.get('error') and not is_user_tool(rel)]
    if bad_files:
        cards.append({'id': 'packs:broken', 'level': 'yellow', 'group': 'files', 'sort': 9,
                      'title': "Files the game can't read",
                      'text': "These .package files are damaged or empty. The game skips them (or may crash on them).",
                      'items': [{'label': r.rsplit('/', 1)[-1], 'detail': 'Mods/' + r, 'file': r, 'action': _park_action(r)} for r in bad_files]})
    return cards


def pack_card(rel, fa, clips, objects):
    """A yellow card for one pack with animations that can never show up (or that play oddly), else None."""
    counts, notes, examples, names, never_total = {}, {}, {}, {}, 0
    for a in fa['anims']:
        never, nts, ex = classify(a, clips, objects)
        if never:
            never_total += 1
        for r in never:
            counts[r] = counts.get(r, 0) + 1
            examples.setdefault(r, ex.get(r))
            names.setdefault(r, []).append(a['name'] or (a['actors'][0]['clip'] if a['actors'] else '?'))
        for r in nts:
            notes[r] = notes.get(r, 0) + 1
            examples.setdefault(r, ex.get(r))
            names.setdefault(r, []).append(a['name'] or (a['actors'][0]['clip'] if a['actors'] else '?'))
    if not counts and not notes:
        return None
    n = len(fa['anims'])
    lines = []
    for r in NEVER_ORDER + ['bad_act', 'some_unknown_place']:
        k = counts.get(r) or notes.get(r)
        if not k:
            continue
        short, why = REASONS[r]
        lines.append({'reason': r, 'count': k, 'never': r in counts,
                      'label': '%d %s' % (k, short.replace('{x}', examples.get(r) or '?')), 'detail': why,
                      'names': sorted(set(names.get(r, [])))[:40]})
    base = rel.rsplit('/', 1)[-1]
    title = ('%d of %d animations in %s can never show up' % (never_total, n, base)) if never_total else \
        ('%s: %d animation%s may play oddly' % (base, sum(notes.values()), '' if sum(notes.values()) == 1 else 's'))
    return {'id': 'pack:' + rel, 'level': 'yellow', 'group': 'packs', 'sort': 10, 'title': title,
            'text': 'Mods/' + rel, 'file': rel, 'counts': dict(counts, **notes), 'never': never_total, 'total': n,
            'lines': lines, 'action': {'kind': 'details', 'label': 'Show which ones'}}


def _parked_cards(active, set_aside, game, nude):
    """What waits in Mods_parked: how many animation packs, and what would clash if they came back."""
    packs = [rel for rel, fa in set_aside.items() if fa['ww'] or fa['anims'] or fa.get('blocked')]
    if not set_aside:
        return []
    anims = sum(len(fa['anims']) for fa in set_aside.values())
    both = dict(active)
    both.update({'(set aside) ' + r: fa for r, fa in set_aside.items()})
    rigs, body, pairs = _conflicts({r: fa for r, fa in both.items()}, nude)
    rigs = [r for r in rigs if r.startswith('(set aside) ')]
    clips = set(game.get('clips') or ())
    objects = set(game.get('objects') or ())
    for fa in both.values():
        clips.update(fa['clips'])
        objects.update(fa['objects'])
    never = 0
    for fa in set_aside.values():
        for a in fa['anims']:
            if classify(a, clips, objects)[0]:
                never += 1
    lines = []
    if packs:
        lines.append({'label': '%d animation pack%s with %d animation%s' % (len(packs), '' if len(packs) == 1 else 's', anims,
                                                                          '' if anims == 1 else 's')})
    if never:
        lines.append({'label': '%d of those animations could never show up anyway (no place, a missing motion or object...)' % never})
    for r in rigs:
        lines.append({'label': "%s would clash with WickedWhims' skeleton" % r.replace('(set aside) ', '').rsplit('/', 1)[-1]})
    for slot, files in sorted(body.items()):
        lines.append({'label': '%d files would replace the same nude %s' % (len(files), slot)})
    return [{'id': 'parked', 'level': 'info', 'group': 'parked', 'sort': 40,
             'title': '%d file%s set aside in Mods_parked' % (len(set_aside), '' if len(set_aside) == 1 else 's'),
             'text': "The game doesn't load these, so their animations don't show up. Novulon's Sims Hub or "
                     "'Mods - everything back (full).bat' puts them back." if packs else "The game doesn't load these.",
             'lines': lines}]


def _session_cards(session, mod_files=()):
    cards = []
    # WickedWhims names files without their folder: the user's own tools (by name) are left out
    own = {r.rsplit('/', 1)[-1].lower() for r, s, m in mod_files if is_known(r)}
    names = [x for x in (session.get('duplicate_files') or []) if x.lower() not in own and not is_known(x)]
    n = len(names) if session.get('duplicate_files') else (session.get('duplicates') or 0)
    if n:
        cards.append({'id': 'log:duplicates', 'level': 'yellow', 'group': 'files', 'sort': 9,
                      'title': 'WickedWhims found mods installed twice',
                      'text': 'The last time you played, WickedWhims saw %d file%s that may be the same mod twice.' % (
                          n, '' if n == 1 else 's'),
                      'items': [{'label': x} for x in names[:30]]})
    return cards


def _own_cards(mod_files):
    """One green card: the user's own files and tools the Doctor knows and leaves alone."""
    mods = [r for r, s, m in mod_files if r.lower().endswith(('.package', '.ts4script'))]
    groups = [
        ('fitstudio', "This app's animations and add-on", 'Mods/FitStudio',
         [r for r in mods if r.lower().split('/', 1)[0] == 'fitstudio']),
        ('animation', 'Your animation packs', 'Mods/animation', [r for r in mods if r.lower().split('/', 1)[0] == 'animation']),
        ('monitor', "Novulon's Sims Hub's game monitor", None,
         [r for r in mods if is_hub_file(r) and r.lower().endswith('.ts4script')]),
        ('packs', "Novulon's Sims Hub's fast packs (your CC, merged on purpose so the game loads faster)", None,
         [r for r in mods if is_hub_file(r) and r.lower().endswith('.package')]),
    ]
    items = []
    for gid, label, folder, files in groups:
        if not files:
            continue
        if folder:
            detail = '%s - %d file%s' % (folder, len(files), '' if len(files) == 1 else 's')
        else:
            detail = ', '.join('Mods/' + r for r in files[:3]) + (' and %d more' % (len(files) - 3) if len(files) > 3 else '')
        items.append({'label': label, 'detail': detail, 'id': gid})
    if not items:
        return []
    return [{'id': 'own', 'level': 'green', 'group': 'own', 'sort': 22, 'title': 'Your own files are left alone',
             'text': 'The Doctor knows these. It never flags them as a problem and never parks them.', 'items': items}]


# ------------------------------------------------------------------ background scan + status
_lock = threading.Lock()
_state = {'running': False, 'phase': 'idle', 'done': 0, 'total': 0, 'text': '', 'cards': [], 'result': None,
          'started': None, 'error': None, 'scan': 0}


def status():
    with _lock:
        s = {k: v for k, v in _state.items() if k != 'result'}
        s['cards'] = list(_state['cards'])
        r = _state['result']
        if r:
            s['summary'], s['seconds'], s['finished'] = r['summary'], r['seconds'], r['finished']
        s['sims_dir'] = sims_dir()
        return s


def start_scan(force=False):
    """Start a scan unless one runs. A finished scan is reused for 3 seconds unless force."""
    with _lock:
        if _state['running']:
            return None
        r = _state['result']
        if r and not force and time.time() - r['finished'] < 3:
            return None
        _state.update({'running': True, 'phase': 'start', 'done': 0, 'total': 0, 'text': 'Starting...', 'cards': [],
                       'started': time.time(), 'error': None, 'scan': _state['scan'] + 1})
        n = _state['scan']
    threading.Thread(target=_run, args=(n,), daemon=True, name='doctor-scan').start()


def _run(n):
    def progress(phase, done, total, text):
        with _lock:
            if _state['scan'] == n:
                _state.update({'phase': phase, 'done': done, 'total': total, 'text': text})

    def emit(card):
        with _lock:
            if _state['scan'] == n:
                _state['cards'].append(card)
    try:
        res = scan(progress, emit)
        with _lock:
            if _state['scan'] == n:
                _state.update({'running': False, 'phase': 'done', 'cards': res['cards'], 'result': res,
                               'text': 'Done', 'done': _state['total']})
    except Exception as ex:
        traceback.print_exc()
        with _lock:
            if _state['scan'] == n:
                _state.update({'running': False, 'phase': 'error', 'error': str(ex) or repr(ex)})


# ------------------------------------------------------------------ safe fixes
def load_manifest():
    """Mods_parked\\_manifest.json, the same format mods_switch.py and SpeedKit use: {"moved": ["rel/path", "dir/"]}."""
    p = manifest_path()
    if os.path.exists(p):
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    return {'moved': []}


def save_manifest(m):
    """Exactly mods_switch.save_manifest: json indent=1 through a .tmp file."""
    os.makedirs(parked_dir(), exist_ok=True)
    tmp = manifest_path() + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(m, f, indent=1)
    os.replace(tmp, manifest_path())


def _refuse(reason, text):
    return {'ok': False, 'reason': reason, 'error': text}


def _game_check():
    running = gamelog.game_running()
    if running is None:
        return _refuse('unknown', "Couldn't check whether The Sims 4 is running, so nothing was changed. Try again.")
    if running:
        return _refuse('game_running', 'Close The Sims 4 first, then press the button again.')
    return None


def park(rel):
    """Move one file from Mods to Mods_parked (same place inside it) and list it in _manifest.json."""
    rel = str(rel or '').replace('\\', '/').strip('/')
    if not rel or rel.startswith('/') or '..' in rel.split('/') or ':' in rel:
        raise ValueError('That is not a file inside your Mods folder.')
    if is_own_file(rel):
        if rel.lower().split('/', 1)[0] == 'animation':
            return _refuse('own', 'Files in Mods\\animation are your own animation packs - they are never parked.')
        return _refuse('own', "Files in Mods\\FitStudio are this app's own - they are never parked.")
    if is_hub_file(rel):
        return _refuse('hub', "That is one of Novulon's Sims Hub's own files - it is never parked.")
    if is_ww_file(rel):
        return _refuse('ww', "That is one of WickedWhims' own files - it is never parked.")
    src = os.path.join(mods_dir(), *rel.split('/'))
    if not _inside(src, mods_dir()) or not os.path.isfile(src):
        return _refuse('missing', 'That file is not in your Mods folder any more.')
    if not rel.lower().endswith(('.package', '.ts4script')):
        raise ValueError('Only .package and .ts4script files can be parked.')
    busy = _game_check()
    if busy:
        return busy
    dst = os.path.join(parked_dir(), *rel.split('/'))
    if os.path.exists(dst):
        return _refuse('exists', 'Mods_parked already has a file with this name in the same place, so nothing was moved.')
    m = load_manifest()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.move(src, dst)
    try:
        if rel not in m.setdefault('moved', []):
            m['moved'].append(rel)
        save_manifest(m)
    except Exception:
        shutil.move(dst, src)             # never leave a parked file the manifest doesn't know
        raise
    return {'ok': True, 'parked': rel, 'to': dst,
            'text': "Moved to Mods_parked. Novulon's Sims Hub or 'Mods - everything back (full).bat' puts it back."}


def _backup(path):
    """A copy of a WickedWhims settings file in the app's cache before it is changed."""
    d = os.path.join(CACHE_DIR, 'backups')
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, '%s_%s' % (time.strftime('%Y%m%d_%H%M%S'), os.path.basename(path)))
    shutil.copy2(path, dst)
    return dst


def _write_json(path, data):
    tmp = path + '.wa.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    os.replace(tmp, path)


def enable(body):
    """Turn switched-off animations back on in WickedWhims' own settings files."""
    which = body.get('file')
    busy = _game_check()
    if busy:
        return busy
    if which == 'dynamic':
        path = os.path.join(ww_saves_dir(), 'dynamic_disabled_animations.json')
        data = _read_json(path)
        key = body.get('list') or 'disabled_animation_types'
        if not isinstance(data, dict) or key not in ('disabled_animation_types', 'autonomy_disabled_animation_types'):
            raise ValueError("WickedWhims' switch-off list was not found.")
        entry = list(body.get('entry') or [])
        before = data.get(key) or []
        after = [e for e in before if list(e) != entry]
        if len(after) == len(before):
            return {'ok': True, 'changed': False, 'text': 'That was already on.'}
        backup = _backup(path)
        data[key] = after
        _write_json(path, data)
        return {'ok': True, 'changed': True, 'backup': backup, 'text': 'Turned back on. WickedWhims uses it the next time the game starts.'}
    if which == 'individual':
        path = os.path.join(ww_saves_dir(), 'all_disabled_animations.json')
        data = _read_json(path)
        if not isinstance(data, dict):
            raise ValueError("WickedWhims' switch-off list was not found.")
        if not data.get('disabled_animations'):
            return {'ok': True, 'changed': False, 'text': 'Nothing was switched off.'}
        backup = _backup(path)
        data['disabled_animations'] = []
        _write_json(path, data)
        return {'ok': True, 'changed': True, 'backup': backup, 'text': 'Turned back on. WickedWhims uses them the next time the game starts.'}
    raise ValueError('Unknown setting.')


def fix(body):
    action = (body or {}).get('action')
    if action == 'park':
        return park(body.get('file'))
    if action == 'enable':
        return enable(body)
    if action in ('favorite', 'turn_off'):
        import wwlists                    # WickedWhims' own lists, only with the proven identifier (R3-2)
        return wwlists.mark(body)
    raise ValueError('Unknown fix.')


if __name__ == '__main__':
    import sys
    t = time.time()
    res = scan(lambda ph, d, n, text: None)
    for c in res['cards']:
        print('%-6s %s | %s' % (c['level'], c['title'], (c.get('text') or '')[:120]))
    print(json.dumps(res['summary']), res['seconds'], 's')

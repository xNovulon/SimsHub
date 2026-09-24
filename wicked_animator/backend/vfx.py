"""The game's particle effect names (what a WickedWhims EFFECT moment can play), checked and adults only.

The names live in one resource of type 0xEA5118B0 in Data\\Client\\ClientDeltaBuild0 and ClientFullBuild0: a table of
(u32 big-endian id, zero-terminated name) records that ends at the last FF FF FF FF. The two tables together hold
34,081 distinct names. Read-only; cached in cache/vfx_names_v1.json with the two packages' size and mtime.

    names()                 -> set of every effect name (lower case)
    adult(name)             -> False for names with child/teen/toddler/infant words or EA's one-letter age tokens
    valid(name)             -> the game has it and it is adult
    adult_equivalent(name)  -> the adult version of a child variant ('sim_pee_c' -> 'sim_pee'), the name itself when it
                               is already valid, or None
    search(q, limit=60)     -> [{name, label, group, uses}] adult names containing every word of q, curated first
    popular(joint=None)     -> the curated effects, most used at that joint first
    CURATED, JOINTS, GROUPS -> frozen from 331 creator packages (cache/research ww_adult_*.pickle)

Effect names are EA's own (pet_small_drool_front is the drool creators use as a fluid), so they are never run through
gamedata._BLOCK_WORDS: only the age words and tokens below decide what is adult.
"""
import json, os, re, threading

import gamedata

T_VFX = 0xEA5118B0
CACHE = os.path.join(gamedata.CACHE, 'vfx_names_v1.json')
BLOCK = re.compile(r'(?<![a-z])(child|children|kid|kids|toddler|toddlers|infant|infants|baby|babies|teen|teens|'
                   r'c|p|i|t)(?![a-z])')
# the same words run together with others ('ageupsparkleschild', 'puddletoddlersplash', 'kiddie_pool')
EMBEDDED = re.compile(r'child|toddler|infant|bab(?:y|ies)|kiddie')

GROUPS = ['Cum & splashes', 'Drool & strands', 'Drips & sweat', 'Streams', 'Tears', 'Steam & breath', 'Sparkles & flash']

# (name, label, group, uses in creator animations, {rig joint: uses there}). Every name is in the game and adult.
# Joint counts come from the creators' event lists (effect + joint pairs); the not-rig-bone joints
# (b__Penis_Tip01..03, b__Tounge__4) and prop/helper joints are left out.
CURATED = [
    ('sim_bar_icecube_splash', 'Splash (white)', 'Cum & splashes', 3228,
     {'b__Penis_Mid': 262, 'b__Penis_Tip': 120, 'b__Penis_Base': 107, 'b__R_Skirt__': 63, 'b__Penis_Testicles': 58}),
    ('hottub_splash_idle_play_splash_death', 'Big splash', 'Cum & splashes', 828,
     {'b__Penis_Tip': 151, 'b__Penis_Testicles': 29, 'b__Penis_Base': 26, 'b__Low_Anus': 16, 'b__L_Stigmata': 11}),
    ('obj_shower_watersplash_effects06', 'Wet splash', 'Cum & splashes', 153,
     {'b__Penis_Base': 92, 'b__Penis_Mid': 16, 'b__Penis_Base01': 15, 'b__Low_Anus': 5, 'b__Penis_Testicles': 3}),
    ('clothing_hamper_damp_drip_splash', 'Drip & splash', 'Cum & splashes', 143,
     {'b__Penis_Tip': 3, 'b__L_Stigmata': 3, 'b__R_Stigmata': 3, 'b__LoLip__': 3}),
    ('sim_bar_pour_skill_med_stir_fail_splash_up', 'Splash up', 'Cum & splashes', 40,
     {'b__Penis_Tip': 2, 'b__L_Stigmata': 1, 'b__Low_Anus': 1}),
    ('sim_bar_stir_fail_splash', 'Spill splash', 'Cum & splashes', 36,
     {'b__Penis_Testicles': 8, 'b__Penis_Tip': 6, 'b__Penis_Base01': 2, 'b__Tounge__3': 2}),
    ('sim_bar_icecube_splash_high', 'Splash, high', 'Cum & splashes', 25,
     {'b__Penis_Testicles': 6, 'b__Penis_Mid01': 2, 'b__L_Stigmata': 2, 'b__R_Stigmata': 2, 'b__Penis_Tip': 1}),
    ('s40_dollhouse_splash', 'Small splash', 'Cum & splashes', 17,
     {'b__Penis_Tip': 14, 'b__Penis_Testicles': 2, 'b__Penis_Base': 1}),
    ('ep02_espresso_pour_trick_splashes', 'Squirts', 'Cum & splashes', 16,
     {'b__Penis_Testicles': 8, 'b__Penis_Tip': 3, 'b__Penis_Mid01': 2}),
    ('pet_small_drool_front', 'Drool strands', 'Drool & strands', 3186,
     {'b__Penis_Mid': 210, 'b__R_Stigmata': 172, 'b__L_Stigmata': 167, 'b__Penis_Base01': 144,
      'b__Penis_Testicles': 132, 'b__CAS_Chin__': 87, 'b__LoLip__': 60, 'b__Penis_Tip': 50}),
    ('ep04_dog_large_drool', 'Heavy drool', 'Drool & strands', 1015,
     {'b__Penis_Base': 179, 'b__L_Stigmata': 133, 'b__R_Stigmata': 129, 'b__Penis_Base01': 31}),
    ('pet_small_drool', 'Drool drops', 'Drool & strands', 714,
     {'b__Penis_Base01': 93, 'b__Penis_Base': 57, 'b__Penis_Testicles': 54, 'b__Penis_Tip': 45, 'b__Tounge__3': 39,
      'b__Penis_Mid': 37}),
    ('pet_sickness_med_drool_front', 'Drool from the mouth', 'Drool & strands', 475,
     {'b__L_Mouth__': 16, 'b__R_Mouth__': 15, 'b__R_LoLip__': 15, 'b__Penis_Base': 13, 'b__LoLip__': 8}),
    ('ep04_dog_large_drool_front', 'Heavy strands', 'Drool & strands', 223,
     {'b__Penis_Base01': 68, 'b__Penis_Base': 21, 'b__Penis_Testicles': 8, 'b__Penis_Tip': 2}),
    ('pet_sickness_large_drool_front', 'Thick drool', 'Drool & strands', 157,
     {'b__Low_Anus': 23, 'b__R_Stigmata': 18, 'b__L_Stigmata': 18, 'b__Penis_Tip': 9, 'b__Penis_Testicles': 6}),
    ('dog_large_drool_front', 'Long strands', 'Drool & strands', 95,
     {'b__Penis_Testicles': 26, 'b__Penis_Base': 25, 'b__Penis_Base01': 14, 'b__R_Stigmata': 5}),
    ('ep04_pet_small_drool', 'Small drool', 'Drool & strands', 38,
     {'b__R_LoLip__': 6, 'b__L_Mouth__': 4, 'b__R_Mouth__': 4, 'b__Penis_Tip': 4, 'b__Penis_Mid': 4, 'b__LoLip__': 4}),
    ('s40_obj_toilet_puke', 'Gush from the mouth', 'Drool & strands', 328, {'b__LoLip__': 8}),
    ('ep02_jump_stand_sim_drips_lthigh', 'Wet drips', 'Drips & sweat', 304,
     {'b__Penis_Testicles': 8, 'b__Penis_Tip': 3}),
    ('ep04_dog_large_foot_drip', 'Dripping', 'Drips & sweat', 137,
     {'b__Penis_Base': 90, 'b__Penis_Tip': 10, 'b__Low_Anus': 6, 'b__Penis_Base01': 6, 'b__Penis_Mid': 5}),
    ('s40_obj_workout_bench_waterdrips', 'Sweat drips', 'Drips & sweat', 248,
     {'b__L_MidBrow__': 53, 'b__R_MidBrow__': 53, 'b__R_InBrow__': 17, 'b__L_InBrow__': 17}),
    ('s40_obj_workout_bench_waterdrips_lite', 'Light sweat', 'Drips & sweat', 41,
     {'b__Penis_Testicles': 13, 'b__Low_Anus': 7}),
    ('s40_obj_bathtub_jets_high_fail_drips', 'Drips', 'Drips & sweat', 132, {}),
    ('ep02_jump_stand_sim_drips_head', 'Wet head', 'Drips & sweat', 52, {'b__CAS_Chin__': 6, 'b__Head__': 1}),
    ('pool_sim_drips_torso', 'Wet body', 'Drips & sweat', 20, {'b__Spine2__': 1}),
    ('s40_obj_treadmill_exercise_waterdrips', 'Sweat', 'Drips & sweat', 22, {'b__Penis_Testicles': 19}),
    ('gp02_steam_room_sweat', 'Sweat sheen', 'Drips & sweat', 2, {'b__Spine2__': 1}),
    ('sim_pee', 'Pee stream', 'Streams', 388,
     {'b__R_Skirt__': 71, 'b__Penis_Tip': 66, 'b__Penis_Testicles': 28, 'b__Penis_Mid': 10}),
    ('talking_toilet_fountain_up_holder', 'Fountain squirt', 'Streams', 556,
     {'b__R_Skirt__': 117, 'b__Penis_Tip': 68, 'b__Penis_Testicles': 55, 'b__Penis_Base': 41, 'b__Low_Anus': 8}),
    ('obj_shower_spray_science', 'Fine spray', 'Streams', 108, {'b__Penis_Testicles': 5}),
    ('s40_sim_react_cry', 'Tears', 'Tears', 216, {'b__Head__': 41}),
    ('s40_sim_react_cry_heavy_constant', 'Heavy tears', 'Tears', 118, {'b__Head__': 1}),
    ('s40_sim_react_cry_heavy', 'Crying', 'Tears', 40, {'b__Head__': 1}),
    ('s40_sim_react_weeping_flick_l', 'Tear flick', 'Tears', 146, {'b__Head__': 1}),
    ('gp02_steam_room_steam_clear', 'Steam cloud', 'Steam & breath', 51, {'b__Spine2__': 1}),
    ('ep1_fever_steam', 'Hot steam', 'Steam & breath', 17, {'b__LoLip__': 3}),
    ('ep03_chilling_breath', 'Cold breath', 'Steam & breath', 23, {'b__LoLip__': 1}),
    ('s40_obj_bathtub_steam', 'Rising steam', 'Steam & breath', 19, {'b__Pelvis__': 1}),
    ('candle_smoke', 'Smoke wisp', 'Steam & breath', 24, {'b__L_LoLip__': 4}),
    ('gp03_cellphone_flash', 'Camera flash', 'Sparkles & flash', 168, {'b__Head__': 1}),
    ('gp08_world_magic_sparkles', 'Sparkles', 'Sparkles & flash', 32, {}),
    ('ageupsparklesadult', 'Sparkle burst', 'Sparkles & flash', 21, {}),
]

# the friendly body parts an effect can sit on (all checked rig bones; b__Tounge__4 and b__Penis_Tip01-03 are not
# bones, so WickedWhims plays effects there at nothing - never offered). needs: the body the sim must have.
JOINTS = [
    {'id': 'penis_tip', 'label': 'Tip of the penis', 'bone': 'b__Penis_Tip', 'needs': 'penis'},
    {'id': 'penis_mid', 'label': 'Middle of the penis', 'bone': 'b__Penis_Mid', 'needs': 'penis'},
    {'id': 'penis_base', 'label': 'Base of the penis', 'bone': 'b__Penis_Base', 'needs': 'penis'},
    {'id': 'balls', 'label': 'Balls', 'bone': 'b__Penis_Testicles', 'needs': 'penis'},
    {'id': 'mouth', 'label': 'Mouth (lower lip)', 'bone': 'b__LoLip__', 'needs': None},
    {'id': 'tongue', 'label': 'Tongue', 'bone': 'b__Tounge__3', 'needs': None},
    {'id': 'chin', 'label': 'Chin', 'bone': 'b__CAS_Chin__', 'needs': None},
    {'id': 'l_palm', 'label': 'Left palm', 'bone': 'b__L_Stigmata', 'needs': None},
    {'id': 'r_palm', 'label': 'Right palm', 'bone': 'b__R_Stigmata', 'needs': None},
    {'id': 'anus', 'label': 'Anus', 'bone': 'b__Low_Anus', 'needs': None},
    {'id': 'vagina', 'label': 'Vagina', 'bone': 'b__Low_Vagina__', 'needs': 'vagina'},
    {'id': 'forehead', 'label': 'Forehead (sweat)', 'bone': 'b__L_MidBrow__', 'needs': None},
    {'id': 'eyes', 'label': 'Eyes (tears)', 'bone': 'b__Head__', 'needs': None},
    {'id': 'l_breast', 'label': 'Left breast', 'bone': 'b__CAS_L_Breast__', 'needs': None},
    {'id': 'r_breast', 'label': 'Right breast', 'bone': 'b__CAS_R_Breast__', 'needs': None},
    {'id': 'chest', 'label': 'Chest', 'bone': 'b__Spine2__', 'needs': None},
    {'id': 'hips', 'label': 'Hips', 'bone': 'b__Pelvis__', 'needs': None},
]
# joints that are never written (not rig bones: F8), mapped to the bone WickedWhims meant
BAD_JOINTS = {'b__penis_tip01': 'b__Penis_Tip', 'b__penis_tip02': 'b__Penis_Tip', 'b__penis_tip03': 'b__Penis_Tip',
              'b__tounge__4': 'b__Tounge__3'}

_KEYWORD_GROUPS = [('Streams', r'pee|spray|fountain|squirt|stream'), ('Tears', r'cry|tear|weep'),
                   ('Steam & breath', r'steam|breath|smoke'), ('Sparkles & flash', r'sparkle|flash|glow'),
                   ('Drool & strands', r'drool|strand|puke'), ('Cum & splashes', r'splash'),
                   ('Drips & sweat', r'drip|sweat|wet')]

_lock = threading.Lock()
_names = None


def _table(d, window=3_000_000):
    """(id, name) records of the effect name table: walked backwards from the last FF FF FF FF, the longest chain of
    'u32 big-endian id + printable zero-terminated name' records that ends exactly there."""
    end = d.rfind(b'\xff\xff\xff\xff')
    if end < 0:
        return []
    lo = max(0, end - window)
    chain = {end: 0}
    nxt = {}
    for s in range(end - 5, lo, -1):
        if int.from_bytes(d[s:s + 4], 'big') > 0x40000:
            continue
        c = d[s + 4]
        if not (48 <= c < 123):
            continue
        e = d.find(b'\x00', s + 4, s + 4 + 200)
        if e < 0:
            continue
        name = d[s + 4:e]
        if not all(32 < b < 127 for b in name):
            continue
        n = e + 1
        if n in chain:
            chain[s] = chain[n] + 1
            nxt[s] = n
    start = max(chain, key=lambda k: chain[k])
    out, s = [], start
    while s != end:
        e = d.find(b'\x00', s + 4)
        out.append((int.from_bytes(d[s:s + 4], 'big'), d[s + 4:e].decode('ascii')))
        s = nxt[s]
    return out


def _sources():
    d = os.path.join(gamedata.game_dir(), 'Data', 'Client')
    return [os.path.join(d, 'ClientDeltaBuild0.package'), os.path.join(d, 'ClientFullBuild0.package')]


def _signature(paths):
    return [[p, os.path.getsize(p), int(os.path.getmtime(p))] for p in paths if os.path.isfile(p)]


def names():
    """Every effect name in the game (lower case), as a set."""
    global _names
    with _lock:
        if _names is not None:
            return _names
        from dbpf import read_index, read_resource
        paths = _sources()
        sig = _signature(paths)
        cached = gamedata._load_cache(CACHE) if os.path.exists(CACHE) else None
        if isinstance(cached, dict) and cached.get('signature') == sig and isinstance(cached.get('names'), list):
            _names = frozenset(cached['names'])
            return _names
        out = set()
        for p in paths:
            if not os.path.isfile(p):
                continue
            try:
                idx = read_index(p)
            except Exception:
                continue
            for e in idx:
                if e['type'] == T_VFX:
                    try:
                        out |= {n.lower() for _, n in _table(read_resource(p, e))}
                    except Exception:
                        pass
        gamedata._store(CACHE, {'signature': sig, 'names': sorted(out)})
        _names = frozenset(out)
        return _names


def adult(name):
    n = (name or '').lower()
    return not BLOCK.search(n.replace('_', ' ')) and not EMBEDDED.search(n)


def valid(name):
    n = (name or '').strip().lower()
    return bool(n) and n in names() and adult(n)


_AGE_WORDS = [('children', 'adults'), ('child', 'adult'), ('toddler', 'adult'), ('infant', 'adult'), ('teen', 'adult'),
              ('kids', 'adults'), ('kid', 'adult'), ('baby', 'adult')]


def adult_equivalent(name):
    """The adult version of a child/teen/toddler effect: one-letter age tokens (_c_, _p_, _t_, _i_ and a trailing _c)
    dropped, or 'child' -> 'adult'; the name itself when it is already valid; None when there is no adult version."""
    n = (name or '').strip().lower()
    if not n:
        return None
    if valid(n):
        return n
    parts = n.split('_')
    cands = []
    ages = [k for k, w in enumerate(parts) if w in ('c', 'p', 't', 'i')]
    if ages:
        cands.append('_'.join(w for k, w in enumerate(parts) if k not in ages))
        for k in ages:
            cands.append('_'.join(parts[:k] + parts[k + 1:]))
    for a, b in _AGE_WORDS:
        if a in n:
            cands.append(n.replace(a, b))
            cands.append(re.sub(r'_?%s_?' % a, '_', n).strip('_'))
    for c in cands:
        c = re.sub(r'_+', '_', c).strip('_')
        if c and valid(c):
            return c
    return None


def group_of(name):
    n = (name or '').lower()
    for g, rx in _KEYWORD_GROUPS:
        if re.search(rx, n):
            return g
    return 'Other'


def _label(name):
    words = [w for w in re.split(r'[_\s]+', name) if w and not re.match(r'^(s\d+|ep\d+|gp\d+|sp\d+|fp\d+|obj|sim|fx)$', w)]
    return (' '.join(words) or name).capitalize()


_CUR = {c[0]: c for c in CURATED}


def _item(name):
    c = _CUR.get(name)
    if c:
        return {'name': c[0], 'label': c[1], 'group': c[2], 'uses': c[3]}
    return {'name': name, 'label': _label(name), 'group': group_of(name), 'uses': 0}


def search(q, limit=60):
    """Adult game effects whose name contains every word of q (curated ones first, then shorter names)."""
    words = [w for w in re.split(r'[\s_]+', (q or '').lower()) if w]
    limit = max(1, min(int(limit or 60), 500))
    if not words:
        return popular()[:limit]
    hits = [n for n in names() if all(w in n for w in words) and adult(n)]
    hits.sort(key=lambda n: (n not in _CUR, -(_CUR[n][3] if n in _CUR else 0), len(n), n))
    return [_item(n) for n in hits[:limit]]


def popular(joint=None):
    """The curated effects that the game has, most used at `joint` first (then most used overall)."""
    j = (joint or '').strip()
    out = []
    for name, label, group, uses, joints in CURATED:
        if not valid(name):
            continue
        at = joints.get(j, 0) if j else 0
        out.append(({'name': name, 'label': label, 'group': group, 'uses': uses, 'at_joint': at}, at, uses))
    out.sort(key=lambda x: (-x[1], -x[2]))
    return [x[0] for x in out]


def joint_ok(joint):
    """Is this a joint an effect may be written at (a rig bone that is not one of the broken names)?"""
    j = (joint or '').strip()
    if not j or j.lower() in BAD_JOINTS:
        return False
    try:
        return j in {b['name'] for b in gamedata.rig('au')['bones']}
    except Exception:
        return j.startswith('b__')

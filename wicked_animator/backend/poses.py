"""Ready-made poses for the Pose step, taken from real WickedWhims animations in the (adults-only) library:
for each position the best floor animation is found and its first frame becomes the pose."""
import gamedata as G

SIDES = ['Clavicle', 'UpperArm', 'Forearm', 'Hand', 'Thumb0', 'Thumb1', 'Thumb2', 'Index0', 'Index1', 'Index2',
         'Mid0', 'Mid1', 'Mid2', 'Ring0', 'Ring1', 'Ring2', 'Pinky0', 'Pinky1', 'Pinky2', 'Thigh', 'Calf', 'Foot', 'Toe']
POSABLE = (['b__Pelvis__', 'b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__', 'b__Jaw__']
           + ['b__%s_%s__' % (s, n) for n in SIDES for s in ('L', 'R')]
           + ['b__Penis_Base', 'b__Penis_Base01', 'b__Penis_Mid', 'b__Penis_Mid01', 'b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3'])
HIPS = ['b__Spine0__', 'b__Pelvis__']

# id, label, hint, match: tags (all), category, name words (any)
COUPLE = [
    ('kiss', 'Kissing', 'Standing close, lips together', {'tags': ['KISSING'], 'cat': 'TEASING'}),
    ('bj', 'Blowjob', 'Kneeling in front of him', {'tags': ['BLOWJOB', 'KNEELING']}),
    ('handjob', 'Handjob', 'Her hand on him', {'cat': 'HANDJOB', 'words': ['handjob', 'hand job']}),
    ('missionary', 'Missionary', 'She lies back, he is on top', {'tags': ['MISSIONARY']}),
    ('cowgirl', 'Cowgirl', 'She rides him, facing him', {'tags': ['COWGIRL']}),
    ('doggy', 'Doggy', 'On all fours, from behind', {'tags': ['DOGGY'], 'cat': 'VAGINAL'}),
    ('standing', 'Standing', 'Standing sex', {'tags': ['STANDING'], 'cat': 'VAGINAL'}),
    ('sitting', 'Sitting', 'She sits on his lap', {'tags': ['SITTING'], 'cat': 'VAGINAL'}),
    ('spooning', 'Spooning', 'Lying on their sides', {'tags': ['SPOONING'], 'words': ['spoon']}),
    ('pronebone', 'Prone bone', 'She lies flat on her front', {'tags': ['PRONEBONE']}),
    ('sixtynine', '69', 'Oral on each other', {'tags': ['SIXTYNINE'], 'words': ['69', 'sixty']}),
    ('cunni', 'Cunnilingus', 'He goes down on her', {'tags': ['CUNNILINGUS']}),
    ('titjob', 'Titjob', 'Between her breasts', {'tags': ['TITJOB']}),
    ('carry', 'Carry', 'He holds her up', {'tags': ['CARRY']}),
    ('anal', 'Anal', 'From behind, anal', {'cat': 'ANAL', 'tags': ['DOGGY']}),
    ('fingering', 'Fingering', 'His fingers on her', {'tags': ['FINGERING']}),
]
# solo poses: one part of a couple pose
SOLO = [
    ('solo_back', 'Lying on back', 'Legs open', 'missionary', 'FEMALE'),
    ('solo_fours', 'On all fours', 'Hands and knees', 'doggy', 'FEMALE'),
    ('solo_straddle', 'Straddling', 'Squatting, as if riding', 'cowgirl', 'FEMALE'),
    ('solo_kneel', 'Kneeling', 'Kneeling, leaning in', 'bj', 'FEMALE'),
    ('solo_front', 'Lying on front', 'Flat on the front', 'pronebone', 'FEMALE'),
    ('solo_side', 'Lying on side', 'On the side', 'spooning', 'FEMALE'),
    ('solo_stand', 'Standing close', 'Standing, arms around', 'kiss', 'FEMALE'),
    ('solo_kneel_up', 'Kneeling upright', 'Kneeling tall, hips forward', 'doggy', 'MALE'),
    ('solo_top', 'On top', 'Leaning over, knees down', 'missionary', 'MALE'),
    ('solo_lying_m', 'Lying back', 'Lying on the back (for riding)', 'cowgirl', 'MALE'),
]


def _pick(lib, spec):
    tags, cat, words = spec.get('tags', []), spec.get('cat'), spec.get('words', [])

    def ok(a, use_tags=True):
        if not a['available'] or len(a['actors']) != 2:
            return False
        g = sorted(x['gender'] for x in a['actors'])
        if g not in (['FEMALE', 'MALE'], ['BOTH', 'FEMALE'], ['BOTH', 'MALE']):
            return False
        if cat and a['category'] != cat:
            return False
        at = set(a.get('tags') or [])
        if use_tags and tags and not all(t in at for t in tags):
            return False
        if not use_tags and words and not any(w in a['name'].lower() for w in words):
            return False
        return True
    cands = [a for a in lib if ok(a)] or ([a for a in lib if ok(a, False)] if words else [])
    if not cands:
        return None
    # floor first (poses sit on the ground), then animations installed now, then fewer extra tags (plainer)
    cands.sort(key=lambda a: ('FLOOR' not in a['locations'], a['package'].startswith('Mods_parked'), len(a.get('tags') or []), a['name']))
    return cands[0]


def _qmul(a, b):
    x1, y1, z1, w1 = a; x2, y2, z2, w2 = b
    return [w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2]


def _qrot(q, v):
    x, y, z, w = q
    u = (x, y, z)
    c1 = (u[1] * v[2] - u[2] * v[1] + w * v[0], u[2] * v[0] - u[0] * v[2] + w * v[1], u[0] * v[1] - u[1] * v[0] + w * v[2])
    c2 = (u[1] * c1[2] - u[2] * c1[1], u[2] * c1[0] - u[0] * c1[2], u[0] * c1[1] - u[1] * c1[0])
    return [v[0] + 2 * c2[0], v[1] + 2 * c2[1], v[2] + 2 * c2[2]]


def _at(keys, f):
    """Value of a decoded channel at frame f (keys = [[tick, ...values]], held between keys)."""
    best = keys[0]
    for k in keys:
        if k[0] <= f:
            best = k
        else:
            break
    return best[1:]


def _world(tracks, rig, bone, f):
    """World position of `bone` at frame f (forward kinematics over the clip, rest pose where a bone has no track)."""
    chain = []
    b = rig[bone]
    while True:
        chain.append(b)
        if b['parent'] < 0:
            break
        b = rig['#' + str(b['parent'])]
    q, t = [0, 0, 0, 1], [0.0, 0.0, 0.0]
    for b in reversed(chain):
        tr = tracks.get(b['name'], {})
        lp = _at(tr['t'], f) if tr.get('t') else b['pos']
        lq = _at(tr['r'], f) if tr.get('r') else b['rot']
        p = _qrot(q, lp)
        t = [t[i] + p[i] for i in range(3)]
        q = _qmul(q, lq)
    return t


def deepest_frame(clips, genders, target):
    """The frame where the penis base is closest to the partner's hips (or head for oral) - the deepest moment,
    which is what the motion layers expect as "the pose". clips: {'MALE': tracks, 'FEMALE': tracks}."""
    rig = {}
    for k, b in enumerate(G.rig('au')['bones']):
        rig[b['name']] = b
        rig['#' + str(k)] = b
    m, f = clips.get('MALE'), clips.get('FEMALE')
    if not m or not f or 'b__Penis_Base' not in rig:
        return 0
    n = max(1, min(m['ticks'], f['ticks']))
    best, bd = 0, 1e9
    for fr in range(0, n, 2):
        a = _world(m['tracks'], rig, 'b__Penis_Base', fr)
        b = _world(f['tracks'], rig, target, fr)
        d = sum((a[i] - b[i]) ** 2 for i in range(3))
        if d < bd:
            best, bd = fr, d
    return best


def _pose(clip, frame=0, tracks=None):
    """A frame of a clip as an editor pose. Half of all creator clips place the body with b__ROOT_bind__;
    the editor places it with the lower back and hips, so the root bone's offset is folded into those two."""
    tr = tracks or G.clip_tracks(clip)
    if not tr:
        return None
    rig = {b['name']: b for b in G.rig('au')['bones']}
    rot, pos = {}, {}
    for n in POSABLE:
        r = tr['tracks'].get(n, {}).get('r')
        if r:
            rot[n] = _at(r, frame)
    for n in HIPS:
        t = tr['tracks'].get(n, {}).get('t')
        if t:
            pos[n] = _at(t, frame)
    rb = tr['tracks'].get('b__ROOT_bind__', {})
    if rb.get('t') or rb.get('r'):
        rest = rig['b__ROOT_bind__']
        qr, tr0 = rest['rot'], rest['pos']
        qa = _at(rb['r'], frame) if rb.get('r') else qr
        ta = _at(rb['t'], frame) if rb.get('t') else tr0
        inv = [-qr[0], -qr[1], -qr[2], qr[3]]
        dq = _qmul(inv, qa)
        dt = _qrot(inv, [ta[i] - tr0[i] for i in range(3)])
        for n in HIPS:
            r0 = rot.get(n) or rig[n]['rot']
            t0 = pos.get(n) or rig[n]['pos']
            rot[n] = _qmul(dq, r0)
            p = _qrot(dq, t0)
            pos[n] = [p[i] + dt[i] for i in range(3)]
    return {'rot': rot, 'pos': pos}


# which body part the penis goes to, per ready pose (others use the animation's first frame)
DEEP = {'missionary': 'b__Pelvis__', 'cowgirl': 'b__Pelvis__', 'doggy': 'b__Pelvis__', 'standing': 'b__Pelvis__',
        'sitting': 'b__Pelvis__', 'spooning': 'b__Pelvis__', 'pronebone': 'b__Pelvis__', 'carry': 'b__Pelvis__',
        'anal': 'b__Pelvis__', 'bj': 'b__Head__'}


def presets():
    def build():
        lib = G.library()['animations']
        out, couples = [], {}
        for pid, label, hint, spec in COUPLE:
            a = _pick(lib, spec)
            if not a:
                continue
            sims = []
            genders = [actor['gender'] if actor['gender'] != 'BOTH' else ('MALE' if any(x['gender'] == 'FEMALE' for x in a['actors']) else 'FEMALE') for actor in a['actors']]
            tracks = [G.clip_tracks(actor['clip']) for actor in a['actors']]
            if any(t is None for t in tracks):
                continue
            frame = deepest_frame(dict(zip(genders, tracks)), genders, DEEP[pid]) if pid in DEEP else 0
            for actor, g, tr in zip(a['actors'], genders, tracks):
                sims.append({'gender': g, 'pose': _pose(actor['clip'], frame, tr)})
            if len(sims) != 2:
                continue
            # the male part first, like WickedWhims orders actors
            sims.sort(key=lambda s: s['gender'] != 'MALE')
            item = {'id': pid, 'label': label, 'hint': hint, 'group': 'couple', 'sims': sims,
                    'source': {'name': a['name'], 'author': a['author'], 'frame': frame}, 'locations': ['FLOOR'] if 'FLOOR' in a['locations'] else a['locations'][:1]}
            couples[pid] = item
            out.append(item)
        for pid, label, hint, src, gender in SOLO:
            c = couples.get(src)
            if not c:
                continue
            s = next((x for x in c['sims'] if x['gender'] == gender), None)
            if s:
                out.append({'id': pid, 'label': label, 'hint': hint, 'group': 'solo', 'sims': [s], 'source': c['source']})
        return out
    return G._cached('poses_v6.json', build)    # 6: made from library5 (stricter adults-only word list)

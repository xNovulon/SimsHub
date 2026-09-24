"""The app's server with a stand-in game, for checks on a PC without The Sims 4 (nothing is read from or written to a
game or Mods folder, and nothing goes into the app's cache folder).

    ANIMATOR_PORT=8792 python tools/checks/lib/fake_game_server.py

It is backend/server.py with four things swapped in memory before it starts:
  - gamedata.rig('au'): a small made-up adult rig with the real bone names the app uses (root, hips, spine, arms,
    hands and fingers, legs, face, WickedWhims' penis / vagina / anus bones, palms and a few grab slots), game space
    (Y up, facing +Z, the sim's left is +X);
  - gamedata.body(frame): one box per bone for the woman, the man and the futa body (the man's and the futa's with
    penis meshes, the woman's with the "NudeBottom_AF" part), skinned to that rig;
  - poses.presets(): every couple ready pose of backend/poses.py COUPLE as the two sims standing face to face (so
    Magic, Say it and the ready poses have something to start from - the poses themselves mean nothing);
  - /api/status answers without a game folder.
Every other route is the real one: game-data routes still say "The Sims 4 install not found", which is what the
checks want to see the app handle.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, '..', '..', '..', 'backend'))
sys.path.insert(0, BACKEND)
# the saved animations, the recovery file and exports go to a throw-away home folder (WA_FAKE_HOME to pick one), never
# into the real Documents folder
_home = os.environ.get('WA_FAKE_HOME') or tempfile.mkdtemp(prefix='wa_fake_home_')
os.makedirs(_home, exist_ok=True)
os.environ['HOME'] = os.environ['USERPROFILE'] = _home

import gamedata as G          # noqa: E402
import poses                  # noqa: E402
from clipfmt import fnv32     # noqa: E402

ID = [0.0, 0.0, 0.0, 1.0]
SIDES = ('L', 'R')


def _rig_bones():
    """[(name, parent name, local position)] - rest turns are all identity (a T-pose)."""
    b = [('b__ROOT__', None, (0, 0, 0)), ('b__ROOT_bind__', 'b__ROOT__', (0, 0, 0)),
         ('b__Pelvis__', 'b__ROOT_bind__', (0, 1.0, 0)), ('b__Spine0__', 'b__ROOT_bind__', (0, 1.03, 0)),
         ('b__Spine1__', 'b__Spine0__', (0, 0.12, 0)), ('b__Spine2__', 'b__Spine1__', (0, 0.14, 0)),
         ('b__Neck__', 'b__Spine2__', (0, 0.2, 0)), ('b__Head__', 'b__Neck__', (0, 0.1, 0)),
         ('b__Jaw__', 'b__Head__', (0, 0.02, 0.05)), ('b__Carry__', 'b__ROOT__', (0, 1.0, 0.3))]
    for i, n in enumerate(('b__Tounge__1', 'b__Tounge__2', 'b__Tounge__3')):
        b.append((n, 'b__Jaw__' if i == 0 else b[-1][0], (0, 0, 0.02)))
    face = {'UpLid': (0.03, 0.1, 0.09), 'LoLid': (0.03, 0.09, 0.09), 'Mouth': (0.025, 0.03, 0.1), 'UpLip': (0.01, 0.035, 0.105),
            'LoLip': (0.01, 0.025, 0.105), 'InBrow': (0.015, 0.12, 0.1), 'MidBrow': (0.03, 0.125, 0.095),
            'OutBrow': (0.05, 0.12, 0.085), 'Cheek': (0.045, 0.06, 0.09), 'Squint': (0.035, 0.08, 0.09), 'Eye': (0.03, 0.095, 0.08)}
    for part, (x, y, z) in face.items():
        for s in SIDES:
            b.append(('b__%s_%s__' % (s, part), 'b__Head__', (x if s == 'L' else -x, y, z)))
    b += [('b__mouth_slot', 'b__Head__', (0, 0.03, 0.11)), ('b__Neck_slot', 'b__Neck__', (0, 0.05, 0.05)),
          ('b__backNeck_slot', 'b__Neck__', (0, 0.05, -0.05)),
          ('b__UpLip__', 'b__Head__', (0, 0.035, 0.11)), ('b__LoLip__', 'b__Jaw__', (0, 0.005, 0.06)),
          ('b__CAS_L_Nostril__', 'b__Head__', (0.01, 0.05, 0.11)), ('b__CAS_R_Nostril__', 'b__Head__', (-0.01, 0.05, 0.11))]
    for n in ('CAS_Glasses', 'CAS_NoseArea', 'CAS_NoseTip', 'CAS_NoseBridge', 'CAS_UpperMouthArea', 'CAS_LowerMouthArea',
              'CAS_JawComp', 'CAS_Chin'):
        b.append(('b__%s__' % n, 'b__Head__', (0, 0.06, 0.1)))
    for s in SIDES:
        k = 1 if s == 'L' else -1
        b += [('b__%s_Clavicle__' % s, 'b__Spine2__', (0.03 * k, 0.17, 0)),
              ('b__%s_UpperArm__' % s, 'b__%s_Clavicle__' % s, (0.15 * k, 0, 0)),
              ('b__%s_ShoulderTwist__' % s, 'b__%s_UpperArm__' % s, (0.05 * k, 0, 0)),
              ('b__%s_Forearm__' % s, 'b__%s_UpperArm__' % s, (0.28 * k, 0, 0)),
              ('b__%s_Elbow__' % s, 'b__%s_UpperArm__' % s, (0.28 * k, 0, -0.02)),
              ('b__%s_ForearmTwist__' % s, 'b__%s_Forearm__' % s, (0.12 * k, 0, 0)),
              ('b__%s_Hand__' % s, 'b__%s_Forearm__' % s, (0.25 * k, 0, 0)),
              ('b__%s_Stigmata' % s, 'b__%s_Hand__' % s, (0.05 * k, -0.02, 0)),
              ('b__%s_Prop__' % s, 'b__%s_Hand__' % s, (0.06 * k, 0, 0.02)),
              ('b__CAS_%s_EyeArea__' % s, 'b__Head__', (0.03 * k, 0.1, 0.08)),
              ('b__CAS_%s_EyeScale__' % s, 'b__Head__', (0.03 * k, 0.1, 0.08)),
              ('b__CAS_%s_Breast__' % s, 'b__Spine2__', (0.09 * k, 0.02, 0.1)),
              ('b__%s_Butt__' % s, 'b__Pelvis__', (0.08 * k, -0.05, -0.1)),
              ('b__%s_Skirt__' % s, 'b__Pelvis__', (0.1 * k, 0, 0)),
              ('b__%s_Thigh__' % s, 'b__Pelvis__', (0.1 * k, -0.05, 0)),
              ('b__%s_ThighTwist__' % s, 'b__%s_Thigh__' % s, (0, -0.1, 0)),
              ('b__%s_Calf__' % s, 'b__%s_Thigh__' % s, (0, -0.45, 0)),
              ('b__%s_Foot__' % s, 'b__%s_Calf__' % s, (0, -0.45, 0)),
              ('b__%s_Toe__' % s, 'b__%s_Foot__' % s, (0, -0.05, 0.12))]
        fingers = {'Thumb': (0.02, 0, 0.03), 'Index': (0.08, 0, 0.02), 'Mid': (0.085, 0, 0), 'Ring': (0.08, 0, -0.015), 'Pinky': (0.07, 0, -0.03)}
        for f, (x, y, z) in fingers.items():
            parent = 'b__%s_Hand__' % s
            for j in range(3):
                name = 'b__%s_%s%d__' % (s, f, j)
                b.append((name, parent, ((x if j == 0 else 0.025) * k, y, z if j == 0 else 0)))
                parent = name
        # EA's touch-target slots (bones.GRAB): every one the app asks for, near where the real ones are
        slots = {'ThighTarget_slot': ('b__Pelvis__', (0.14, -0.05, 0)), 'backBellyTarget_slot': ('b__Spine0__', (0.12, 0.05, -0.05)),
                 'lowBackTarget_slot': ('b__Spine0__', (0.06, 0.02, -0.1)), 'BellyTarget_slot': ('b__Spine0__', (0.05, 0.05, 0.1)),
                 'frontBellyTarget_slot': ('b__Spine1__', (0.05, 0, 0.11)), 'BackTarget_slot': ('b__Spine1__', (0.08, 0.05, -0.1)),
                 'sideBackTorsoTarget_slot': ('b__Spine1__', (0.12, 0.05, -0.06)), 'chestTarget_slot': ('b__Spine2__', (0.07, 0.05, 0.12)),
                 'frontTorsoTarget_slot': ('b__Spine2__', (0.1, 0, 0.1)), 'breastTarget_slot': ('b__Spine2__', (0.09, 0.02, 0.13)),
                 'shoulderbladeTarget_slot': ('b__Spine2__', (0.1, 0.1, -0.1)), 'ShoulderTarget_slot': ('b__Spine2__', (0.16, 0.17, 0)),
                 'outThighTarget_slot': ('b__%s_Thigh__' % s, (0.07, -0.2, 0)), 'ThighFrontTarget_slot': ('b__%s_Thigh__' % s, (0, -0.2, 0.07)),
                 'KneeTarget_slot': ('b__%s_Calf__' % s, (0, 0, 0.06)), 'frontCalfTarget_slot': ('b__%s_Calf__' % s, (0, -0.2, 0.05)),
                 'inCalfTarget_slot': ('b__%s_Calf__' % s, (-0.04, -0.2, 0)), 'ForearmTarget_slot': ('b__%s_Forearm__' % s, (0.12, 0, 0.03))}
        for n, (parent, (x, y, z)) in slots.items():
            b.append(('b__%s_%s' % (s, n), parent, (x * k, y, z)))
    b += [('b__Penis_Base', 'b__Pelvis__', (0, -0.08, 0.1)), ('b__Penis_Base01', 'b__Penis_Base', (0, 0, 0.03)),
          ('b__Penis_Mid', 'b__Penis_Base01', (0, 0, 0.04)), ('b__Penis_Mid01', 'b__Penis_Mid', (0, 0, 0.04)),
          ('b__Penis_Tip', 'b__Penis_Mid01', (0, 0, 0.04)), ('b__Penis_Testicles', 'b__Pelvis__', (0, -0.1, 0.08)),
          ('b__Penis_L_Testicle', 'b__Pelvis__', (0.01, -0.1, 0.08)), ('b__Penis_R_Testicle', 'b__Pelvis__', (-0.01, -0.1, 0.08)),
          ('b__Up_Vagina__', 'b__Pelvis__', (0, -0.09, 0.07)), ('b__Low_Vagina__', 'b__Pelvis__', (0, -0.11, 0.06)),
          ('b__Anus', 'b__Pelvis__', (0, -0.1, -0.06)), ('b__L_Anus__', 'b__Pelvis__', (0.01, -0.1, -0.06)),
          ('b__R_Anus__', 'b__Pelvis__', (-0.01, -0.1, -0.06)), ('b__Up_Anus', 'b__Pelvis__', (0, -0.09, -0.06)),
          ('b__Low_Anus', 'b__Pelvis__', (0, -0.11, -0.06))]
    return b


def fake_rig(key='au'):
    if key != 'au':
        raise FileNotFoundError('Only the adult rig is available.')
    bones = _rig_bones()
    index = {n: i for i, (n, _p, _t) in enumerate(bones)}
    out = []
    for n, p, t in bones:
        opp = n.replace('_L_', '_X_').replace('_R_', '_L_').replace('_X_', '_R_')
        out.append({'name': n, 'parent': index[p] if p else -1, 'pos': [float(c) for c in t], 'rot': list(ID),
                    'scale': [1.0, 1.0, 1.0], 'hash': fnv32(n), 'opposite': index.get(opp, index[n])})
    return {'name': 'auRig', 'bones': out}


def _world(rig):
    pos = []
    for b in rig['bones']:
        p = pos[b['parent']] if b['parent'] >= 0 else (0.0, 0.0, 0.0)
        pos.append(tuple(p[i] + b['pos'][i] for i in range(3)))
    return pos


# a box between a bone and a point (size s), skinned fully to that bone
def _box(center, half, bone, mesh):
    base = len(mesh['positions']) // 3
    cx, cy, cz = center
    hx, hy, hz = half
    for dx, dy, dz in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]:
        mesh['positions'] += [round(cx + dx * hx, 5), round(cy + dy * hy, 5), round(cz + dz * hz, 5)]
        n = (dx * dx + dy * dy + dz * dz) ** 0.5
        mesh['normals'] += [round(dx / n, 4), round(dy / n, 4), round(dz / n, 4)]
        mesh['uvs'] += [0.5 + 0.25 * dx, 0.5 + 0.25 * dy]
        mesh['bones'] += [bone, 0, 0, 0]
        mesh['weights'] += [1.0, 0.0, 0.0, 0.0]
    for a, b, c in [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2), (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3)]:
        mesh['faces'] += [base + a, base + b, base + c]


BODY_PARTS = {   # bone -> (to bone for the box's length, thickness)
    'b__Pelvis__': (None, (0.16, 0.08, 0.1)), 'b__Spine1__': (None, (0.14, 0.08, 0.09)), 'b__Spine2__': (None, (0.17, 0.1, 0.1)),
    'b__Neck__': ('b__Head__', 0.05), 'b__Head__': (None, (0.08, 0.11, 0.1)),
}


def fake_body(frame='yf'):
    if frame not in G.BODIES:
        raise FileNotFoundError('unknown body')
    rig = fake_rig('au')
    idx = {b['name']: i for i, b in enumerate(rig['bones'])}
    world = _world(rig)
    body = {'part': 'fake_body', 'role': 'top', 'positions': [], 'normals': [], 'uvs': [], 'bones': [], 'weights': [], 'faces': []}
    for name, (to, size) in BODY_PARTS.items():
        i = idx[name]
        if to:
            a, b2 = world[i], world[idx[to]]
            c = tuple((a[k] + b2[k]) / 2 for k in range(3))
            _box(c, (size, abs(b2[1] - a[1]) / 2 + 0.01, size), i, body)
        else:
            c = world[i]
            _box((c[0], c[1] + (0.1 if name == 'b__Head__' else 0.04), c[2]), size, i, body)
    for s in SIDES:
        for a, b2, t in (('UpperArm', 'Forearm', 0.04), ('Forearm', 'Hand', 0.035), ('Thigh', 'Calf', 0.07), ('Calf', 'Foot', 0.05)):
            i, j = idx['b__%s_%s__' % (s, a)], idx['b__%s_%s__' % (s, b2)]
            pa, pb = world[i], world[j]
            c = tuple((pa[k] + pb[k]) / 2 for k in range(3))
            half = tuple(max(t, abs(pb[k] - pa[k]) / 2) for k in range(3))
            _box(c, half, i, body)
        h, f = idx['b__%s_Hand__' % s], idx['b__%s_Foot__' % s]
        _box((world[h][0] + (0.05 if s == 'L' else -0.05), world[h][1], world[h][2]), (0.05, 0.015, 0.04), h, body)
        _box((world[f][0], world[f][1] - 0.03, world[f][2] + 0.05), (0.04, 0.03, 0.1), f, body)
    meshes = [body]
    if frame in ('ym', 'yf_futa'):
        for role in ('penis_soft', 'penis_hard'):
            m = {'part': 'fake_%s' % role, 'role': role, 'positions': [], 'normals': [], 'uvs': [], 'bones': [], 'weights': [], 'faces': []}
            for n in ('b__Penis_Base', 'b__Penis_Mid', 'b__Penis_Tip'):
                _box(world[idx[n]], (0.015, 0.015, 0.02), idx[n], m)
            meshes.append(m)
    if frame == 'yf':
        m = {'part': 'fake_NudeBottom_AF', 'role': 'bottom', 'positions': [], 'normals': [], 'uvs': [], 'bones': [], 'weights': [], 'faces': []}
        _box(world[idx['b__Up_Vagina__']], (0.02, 0.02, 0.02), idx['b__Up_Vagina__'], m)
        meshes.append(m)
    return {'frame': frame, 'rig': 'au', 'meshes': meshes, 'ww': False}


def fake_presets():
    """Every couple ready pose as the two sims standing face to face, 30 cm apart."""
    turn = [0.0, 1.0, 0.0, 0.0]                         # 180 degrees about Y: he faces her
    him = {'rot': {'b__Pelvis__': turn, 'b__Spine0__': turn}, 'pos': {'b__Pelvis__': [0, 1.0, 0.3], 'b__Spine0__': [0, 1.03, 0.3]}}
    her = {'rot': {}, 'pos': {'b__Pelvis__': [0, 1.0, 0], 'b__Spine0__': [0, 1.03, 0]}}
    out = []
    for pid, label, hint, _spec in poses.COUPLE:
        out.append({'id': pid, 'label': label, 'hint': hint, 'group': 'couple', 'locations': ['FLOOR'],
                    'source': {'name': 'stand-in', 'author': 'checks', 'frame': 0},
                    'sims': [{'gender': 'MALE', 'pose': him}, {'gender': 'FEMALE', 'pose': her}]})
    return out


G.rig = fake_rig
G.body = fake_body
poses.presets = fake_presets
G.ww_tuning_package = lambda: None

import server  # noqa: E402

_api_get = server.Handler._api_get


def _api_get_fake(self, route, q):
    if route == 'status':
        return self._send(200, server._json({'game_dir': None, 'mods': G.MODS_DIR, 'ww': False, 'ok': True, 'fake_game': True,
                                             'build': server.BUILD, 'pid': os.getpid()}))
    return _api_get(self, route, q)


server.Handler._api_get = _api_get_fake

if __name__ == '__main__':
    server.main()

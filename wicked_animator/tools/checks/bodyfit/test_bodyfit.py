""""Fit hands to each sim's body" (experimental IK targets, backend/exporter.py ik_parts + clipfmt slots).

    python tools/checks/bodyfit/test_bodyfit.py [git ref of the code before the feature, default 9c88a0d]

No game needed: a small stand-in rig (root > pelvis > both arms and legs) and baked tracks that move the arm.
  - switch off: every resource of the export is byte-for-byte what the code before the feature wrote (that code is
    taken from git and run in a separate process on the same project) - even when the baked actors carry 'ik';
  - switch on: the clips parse back with clipfmt - IK targets (chain, slot, namespace 'x', joint b__ROOT__) in the
    clip and its header, a constant weight of 1 (F1_Zero) and the held end bone's position/rotation channels whose
    decoded values match an independent forward kinematics (4x4 matrices) of the same tracks; the other clips, the
    prop-free snippet XML and every other channel are unchanged; a hold for part of the loop is reported and skipped;
  - bundle: the README gets the "How to test" lines.
"""
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np

TMP = tempfile.mkdtemp(prefix='wa_bodyfit_')
os.environ['ANIMATOR_SAVES'] = os.path.join(TMP, 'saves')
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
REPO = os.path.abspath(os.path.join(ROOT, '..'))
BEFORE = sys.argv.pop(1) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else '9c88a0d'


def fnv32(s):
    h = 0x811C9DC5
    for b in s.lower().encode('utf-8'):
        h = ((h * 0x01000193) & 0xFFFFFFFF) ^ b
    return h


BONES = [('b__ROOT__', -1, [0, 0, 0]), ('b__Pelvis__', 0, [0, 1.0, 0]),
         ('b__L_UpperArm__', 1, [0.2, 0.45, 0]), ('b__L_Forearm__', 2, [0.28, 0, 0]), ('b__L_Hand__', 3, [0.25, 0, 0]),
         ('b__R_UpperArm__', 1, [-0.2, 0.45, 0]), ('b__R_Forearm__', 5, [-0.28, 0, 0]), ('b__R_Hand__', 6, [-0.25, 0, 0]),
         ('b__L_Thigh__', 1, [0.1, -0.05, 0]), ('b__L_Calf__', 8, [0, -0.45, 0]), ('b__L_Foot__', 9, [0, -0.43, 0])]
RIG = {'bones': [{'name': n, 'parent': p, 'pos': pos, 'rot': [0, 0, 0, 1], 'scale': [1, 1, 1], 'hash': fnv32(n),
                  'opposite': -1} for n, p, pos in BONES]}
FRAMES = 24


def axis_quat(axis, ang):
    s = math.sin(ang / 2)
    return [axis[0] * s, axis[1] * s, axis[2] * s, math.cos(ang / 2)]


def project(fit, with_ik=True, uid='u-fit-1'):
    """A baked two-sim animation: sim 1 moves its pelvis and right arm and holds with the right hand (whole loop) and
    the left hand (part of the loop only); sim 2 stands still."""
    k = range(FRAMES)
    tracks = {
        'b__Pelvis__': {'t': [[0, 1.0 + 0.05 * math.sin(i / 4), 0.02 * i / FRAMES] for i in k],
                        'r': [axis_quat((0, 1, 0), 0.3 * math.sin(i / 5)) for i in k]},
        'b__R_UpperArm__': {'r': [axis_quat((0, 0, 1), -0.6 + 0.4 * math.sin(i / 3)) for i in k]},
        'b__R_Forearm__': {'r': [axis_quat((0, 1, 0), 0.8 + 0.3 * math.cos(i / 3)) for i in k]},
    }
    a1 = {'gender': 'MALE', 'tracks': tracks, 'sounds': []}
    if with_ik:
        a1['ik'] = [{'limb': 'R hand'}]
        a1['ikSkipped'] = ['L hand']
    p = {'uid': uid, 'name': 'Fit test', 'author': 'Tester', 'frames': FRAMES, 'fps': 30, 'category': 'TEASING',
         'locations': ['FLOOR'], 'actors': [a1, {'gender': 'FEMALE', 'tracks': {}, 'sounds': []}]}
    if fit:
        p['fitBodies'] = True
    return p


RUNNER = r'''
import json, sys, hashlib, os
sys.path.insert(0, sys.argv[1])
import gamedata as G
G.rig = lambda key='au': json.loads(os.environ['FIT_RIG'])
import exporter as X
res, info = X.animation_resources(json.loads(os.environ['FIT_PROJECT']), metas={}, present=set())
print(json.dumps([[t, g, '%016x' % i, hashlib.sha256(d).hexdigest()] for t, g, i, d in res]))
'''


def run_exporter(backend, proj):
    env = dict(os.environ, FIT_RIG=json.dumps(RIG), FIT_PROJECT=json.dumps(proj))
    out = subprocess.run([sys.executable, '-c', RUNNER, backend], env=env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def old_backend():
    """The backend folder as it was at BEFORE (from git), in the temp dir."""
    dst = os.path.join(TMP, 'before_backend')
    if not os.path.isdir(dst):
        os.makedirs(dst)
        names = subprocess.run(['git', '-C', REPO, 'ls-tree', '--name-only', BEFORE, 'wicked_animator/backend/'],
                               capture_output=True, text=True, check=True).stdout.split()
        for n in names:
            if n.endswith('.py'):
                data = subprocess.run(['git', '-C', REPO, 'show', '%s:%s' % (BEFORE, n)], capture_output=True, check=True).stdout
                with open(os.path.join(dst, os.path.basename(n)), 'wb') as f:
                    f.write(data)
    return dst


sys.path.insert(0, os.path.join(ROOT, 'backend'))
import clipfmt  # noqa: E402
import dbpf  # noqa: E402
import exporter as X  # noqa: E402
import gamedata as G  # noqa: E402
import wwpackage as W  # noqa: E402

G.rig = lambda key='au': RIG


# ------------------------------------------------------------------ an independent forward kinematics (matrices)
def mat(t, q):
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, 3] = t
    return m


def fk(tracks, name, k):
    by = {b['name']: b for b in RIG['bones']}
    chain = []
    b = by[name]
    while b['parent'] >= 0:
        chain.append(b)
        b = RIG['bones'][b['parent']]
    m = np.eye(4)
    for b in reversed(chain):          # below b__ROOT__, whose own transform the IK target is relative to
        tr = tracks.get(b['name'], {})
        t = tr['t'][k] if tr.get('t') else b['pos']
        r = tr['r'][k] if tr.get('r') else b['rot']
        m = m @ mat(t, r)
    return m


def track_values(ch, frames):
    vals = clipfmt.decode_track(ch)
    per = [None] * frames
    for tick, v in vals:
        if 0 <= tick < frames:
            per[tick] = v
    last = vals[0][1]
    for i in range(frames):
        per[i] = per[i] or last
        last = per[i]
    return per


def clips_of(resources):
    return [(i, d) for t, g, i, d in resources if t == X.T_CLIP], [(i, d) for t, g, i, d in resources if t == X.T_CLIP_HEADER]


class BodyFit(unittest.TestCase):
    def test_1_off_is_byte_identical_to_before(self):
        try:
            before = old_backend()
        except (subprocess.CalledProcessError, FileNotFoundError) as ex:
            self.skipTest('no git history here (%s)' % ex)
        for proj in (project(False, with_ik=True), project(False, with_ik=False)):
            old = run_exporter(before, proj)
            new = run_exporter(os.path.join(ROOT, 'backend'), proj)
            self.assertEqual(old, new)
        print('  switch off: %d resources, same bytes as %s' % (len(new), BEFORE))

    def test_2_on_round_trip(self):
        on, info = X.animation_resources(project(True), metas={}, present=set())
        off, _ = X.animation_resources(project(False), metas={}, present=set())
        self.assertEqual(info['fit_bodies'], ['0:R hand'])
        self.assertTrue(any('part of the loop only' in w and 'left hand' in w for w in info['warnings']), info['warnings'])
        (c_on, h_on), (c_off, h_off) = clips_of(on), clips_of(off)
        # sim 2 (no holds), the snippet XML: identical
        self.assertEqual(c_on[1], c_off[1])
        self.assertEqual(h_on[1], h_off[1])
        snip = lambda rs: [d for t, g, i, d in rs if t == W.SNIPPET]
        self.assertEqual(snip(on), snip(off))
        clip = clipfmt.parse_clip(c_on[0][1])
        head = clipfmt.parse_clip(h_on[0][1])
        self.assertEqual(clip['slots'], [(1, 0, 'x', 'b__ROOT__')])       # R hand = chain 1, slot 0, own root
        self.assertEqual(head['slots'], clip['slots'])
        self.assertEqual(clip['rig_ns'], 'x')
        base = clipfmt.parse_clip(c_off[0][1])
        self.assertEqual(base['slots'], [])
        # every channel of the clip without the switch is still there, unchanged
        key = lambda ch: (ch['target'], ch['sub'], ch['type'], ch['offset'], ch['scale'], tuple((t, f, tuple(i)) for t, f, i in ch['frames']))
        self.assertEqual([key(c) for c in clip['codec']['channels'][:len(base['codec']['channels'])]],
                         [key(c) for c in base['codec']['channels']])
        extra = clip['codec']['channels'][len(base['codec']['channels']):]
        hand = fnv32('b__R_Hand__')
        self.assertEqual([(c['target'], c['sub'], c['type']) for c in extra],
                         [(hand, 14, 9), (hand, 25, 18), (hand, 26, 20)])
        self.assertEqual(clipfmt.constant_value(extra[0]), [1.0])
        self.assertEqual(extra[0]['frames'], [])
        tracks = project(True)['actors'][0]['tracks']
        pos = track_values(extra[1], FRAMES)
        rot = track_values(extra[2], FRAMES)
        worst_t = worst_r = 0.0
        for k in range(FRAMES):
            m = fk(tracks, 'b__R_Hand__', k)
            worst_t = max(worst_t, float(np.max(np.abs(np.array(pos[k]) - m[:3, 3]))))
            q = np.array(rot[k]) / np.linalg.norm(rot[k])
            worst_r = max(worst_r, float(np.max(np.abs(mat([0, 0, 0], q)[:3, :3] - m[:3, :3]))))
        print('  switch on: IK position within %.2f mm, rotation matrix within %.4f of the forward kinematics' % (worst_t * 1000, worst_r))
        self.assertLess(worst_t, 0.002)
        self.assertLess(worst_r, 0.005)

    def test_3_constant_hold_and_loop_hold(self):
        p = project(True)
        p['category'], p['loops'] = 'CLIMAX', 1          # a climax that plays once gets extra hold ticks
        res, _ = X.animation_resources(p, metas={}, present=set())
        clip = clipfmt.parse_clip(clips_of(res)[0][0][1])
        pos = next(c for c in clip['codec']['channels'] if c['sub'] == 25)
        ticks = [t for t, _, _ in pos['frames']]
        self.assertEqual(ticks[-1], FRAMES - 1 + 30)
        self.assertEqual(clip['codec']['num_ticks'], FRAMES + 30)

    def test_4_bundle_readme(self):
        saved = X.EXPORTS
        X.EXPORTS = os.path.join(TMP, 'exports')
        try:
            r = X.bundle({'name': 'Fit Mod', 'author': 'Tester', 'animations': [project(True)], 'include_sounds': False})
            r_off = X.bundle({'name': 'Plain Mod', 'author': 'Tester', 'animations': [project(False, uid='u-fit-2')], 'include_sounds': False})
        finally:
            X.EXPORTS = saved
        self.assertEqual(r['fit_bodies'], 1)
        self.assertEqual(r_off['fit_bodies'], 0)
        with open(os.path.join(r['folder'], 'README.txt'), encoding='utf-8') as f:
            readme = f.read()
        with open(os.path.join(r_off['folder'], 'README.txt'), encoding='utf-8') as f:
            plain = f.read()
        self.assertIn('HOW TO TEST "Fit hands to each sim\'s body"', readme)
        self.assertIn('EXPERIMENTAL: HANDS AND FEET FITTED TO EACH BODY in Fit test.', readme)
        self.assertNotIn('HOW TO TEST', plain)
        idx = dbpf.read_index(r['package'])
        clip = next(clipfmt.parse_clip(dbpf.read_resource(r['package'], e)) for e in idx
                    if e['type'] == X.T_CLIP and clipfmt.parse_clip(dbpf.read_resource(r['package'], e))['slots'])
        self.assertEqual(clip['slots'], [(1, 0, 'x', 'b__ROOT__')])

    def test_5_write_clip_slots(self):
        chans = [clipfmt.encode_channel(7, 1, [(0, [0.0, 1.0, 2.0]), (3, [1.0, 1.0, 1.0])], False)]
        a, ah = clipfmt.write_clip('c', 'x', 4, chans)
        b, bh = clipfmt.write_clip('c', 'x', 4, chans, slots=())
        self.assertEqual((a, ah), (b, bh))
        slots = [(0, 0, 'x', 'b__ROOT__'), (3, 1, 'y', 'b__Pelvis__')]
        c, ch = clipfmt.write_clip('c', 'x', 4, chans + [clipfmt.constant_channel(9, 14, 0.5)], slots=slots)
        pc = clipfmt.parse_clip(c)
        self.assertEqual(pc['slots'], slots)
        self.assertEqual(clipfmt.parse_clip(ch)['slots'], slots)
        self.assertEqual(clipfmt.constant_value(pc['codec']['channels'][1]), [0.5])
        # the header bytes: u32 count, then u16 chain, u16 slot, str32 namespace, str32 joint
        at = c.index(b'b__ROOT__') - 4 - 4 - 1 - 4
        self.assertEqual(struct.unpack_from('<iHHi', c, at - 4), (2, 0, 0, 1))


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

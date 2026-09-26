"""TASK 1 (objmesh.py 'skin' data) and TASK 2 (exporter.py bedAnim -> the bed's own clip / wwpackage.py
object_animation_clip_name) for the two beds (SINGLE_BED = object 51719, DOUBLE_BED = 288627).

    python tools/checks/bedanim/test_bed_export.py

(a) SkinData: the furniture mesh builder's skin data for both beds - needs the game (E:\\The Sims 4); skipped when
    it isn't there.
(b) BedExport.test_bed_clip_written_and_readable: a synthetic animation with a bedAnim, exported for real (into a
    temp Mods folder, never the real one) and parsed back with dbpf - the extra clip, its channel targets and the
    XML tag. Also needs the game (the bed rig comes from the same reference objects as (a)).
(c) BedExport.test_no_bedanim_is_unchanged: without project['bedAnim'] the resources and XML are exactly what they
    were before this feature - no game needed.
"""
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
TMP = tempfile.mkdtemp(prefix='wa_bedanim_')
os.environ.setdefault('ANIMATOR_SAVES', os.path.join(TMP, 'saves'))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import dbpf                                                        # noqa: E402
import exporter as X                                               # noqa: E402
import wwpackage as W                                              # noqa: E402
from clipfmt import parse_clip, decode_track, fnv32, fnv64         # noqa: E402

SINGLE_BED, DOUBLE_BED = 51719, 288627


def _has_game():
    try:
        import gamefind
        gamefind.game_dir()
        return True
    except Exception:
        return False


HAS_GAME = _has_game()
NO_GAME = 'needs the real game (E:\\The Sims 4) - not found here'


def axis_quat(axis, ang):
    s = math.sin(ang / 2)
    return [axis[0] * s, axis[1] * s, axis[2] * s, math.cos(ang / 2)]


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def _qn(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def _qrot(q, v):
    x, y, z, w = q
    r = _qmul(_qmul(q, (v[0], v[1], v[2], 0.0)), (-x, -y, -z, w))
    return (r[0], r[1], r[2])


# two small-offset bones (a pillow's squish bone, relative to its own trans bone): a modest translation/rotation
# delta on them keeps the clip's shared quantisation scale small, so the round trip holds well inside 1e-4
BED_TEST_BONES = ['_bind_DB_Pillow_squish_L_', '_bind_DB_Pillow_squish_R_']


def bed_anim_frames(frames):
    rows = []
    for i in range(frames):
        row = []
        row += [0.0, 0.008 * i, 0.0] + axis_quat((1, 0, 0), 0.03 * i)
        row += [0.0, -0.006 * i, 0.0] + axis_quat((0, 0, 1), -0.02 * i)
        rows.append(row)
    return rows


def baked_project(with_bed=True, frames=6, uid='u-bed-1'):
    tracks = {'b__Pelvis__': {'t': [[0, 1.0, 0.0]] * frames, 'r': [[0, 0, 0, 1]] * frames}}
    actors = [{'gender': 'FEMALE', 'body': 'yf', 'tracks': tracks, 'sounds': [], 'role': 'receiver'},
              {'gender': 'MALE', 'body': 'ym', 'tracks': tracks, 'sounds': [], 'role': 'giver'}]
    p = {'uid': uid, 'name': 'Bed test', 'author': 'Checks', 'frames': frames, 'fps': 30, 'category': 'VAGINAL',
         'locations': ['DOUBLE_BED'], 'actors': actors}
    if with_bed:
        p['bedAnim'] = {'location': 'DOUBLE_BED', 'bones': BED_TEST_BONES, 'frames': bed_anim_frames(frames)}
    return p


class SkinData(unittest.TestCase):
    """TASK 1: objmesh.py's per-mesh 'skin' data for the two beds."""

    @unittest.skipUnless(HAS_GAME, NO_GAME)
    def test_both_beds_have_bone_skin_data(self):
        import objmesh
        for obj_id in (SINGLE_BED, DOUBLE_BED):
            m = objmesh.object_mesh(obj_id)
            skinned = [x for x in m['meshes'] if x.get('skinned')]
            self.assertEqual(len(skinned), 1, (m['name'], [x['mesh'] for x in m['meshes']]))
            mesh = skinned[0]
            skin = mesh.get('skin')
            self.assertIsNotNone(skin, mesh['mesh'])
            names = skin['bones']
            self.assertTrue(any('blanket' in n.lower() for n in names), (m['name'], names))
            trans_bones = [n for n in names if 'pillow' in n.lower() and 'trans' in n.lower()]
            self.assertTrue(trans_bones, (m['name'], names))
            self.assertEqual(len(skin['rest']), len(names))
            self.assertEqual(len(skin['rq']), len(names))
            n_verts = len(mesh['positions']) // 3
            self.assertEqual(len(skin['idx']), n_verts * 4)
            self.assertEqual(len(skin['w']), n_verts * 4)
            self.assertTrue(all(0 <= v < len(names) for v in skin['idx']), m['name'])
            for i in range(n_verts):
                s = sum(skin['w'][i * 4:i * 4 + 4])
                self.assertAlmostEqual(s, 1.0, places=3, msg=(m['name'], i))
            lo, hi = m['bounds']['min'], m['bounds']['max']
            for pos in skin['rest']:
                for c, mn, mx in zip(pos, lo, hi):
                    self.assertTrue(mn - 1e-3 <= c <= mx + 1e-3, (m['name'], pos, lo, hi))
            for q in skin['rq']:
                self.assertAlmostEqual(sum(c * c for c in q), 1.0, places=3, msg=(m['name'], q))
            # the pillows sit at the -Z end of the bed (the headboard - objmesh.py's module doc: +Z is the foot)
            mid_z = (lo[2] + hi[2]) / 2
            for n, pos in zip(names, skin['rest']):
                if n in trans_bones:
                    self.assertLess(pos[2], mid_z, 'pillow (%s) should be on the -Z (headboard) side' % n)


class BedExport(unittest.TestCase):
    """TASK 2: exporter.py's bedAnim -> the bed's own clip + object_animation_clip_name."""

    @unittest.skipUnless(HAS_GAME, NO_GAME)
    def test_bed_clip_written_and_readable(self):
        saved = X.MY_ANIMATIONS
        X.MY_ANIMATIONS = os.path.join(TMP, 'MyAnimations')
        proj = baked_project(with_bed=True)
        try:
            r = X.export(proj)
        finally:
            X.MY_ANIMATIONS = saved
        path = r['path']
        self.assertTrue(os.path.isfile(path), path)
        idx = dbpf.read_index(path)

        snippet = next(dbpf.read_resource(path, e) for e in idx if e['type'] == W.SNIPPET)
        xml = snippet.decode('utf-8')
        root = ET.fromstring(xml)
        obj_clip_el = next((t for t in root.iter('T') if t.get('n') == 'object_animation_clip_name'), None)
        self.assertIsNotNone(obj_clip_el, xml)
        clip_name = obj_clip_el.text
        self.assertTrue(clip_name.endswith('_bed'), clip_name)

        inst = fnv64(clip_name)
        clip_entry = next((e for e in idx if e['type'] == X.T_CLIP and e['inst'] == inst), None)
        header_entry = next((e for e in idx if e['type'] == X.T_CLIP_HEADER and e['inst'] == inst), None)
        self.assertIsNotNone(clip_entry, 'clip %s not found in the written package' % clip_name)
        self.assertIsNotNone(header_entry, 'clip header %s not found in the written package' % clip_name)

        clip_bytes = dbpf.read_resource(path, clip_entry)
        c = parse_clip(clip_bytes)
        h = parse_clip(dbpf.read_resource(path, header_entry))
        self.assertEqual(c['rig_ns'], X.BED_RIG_NS)
        self.assertEqual(c['explicit_ns'], list(X.BED_EXPLICIT_NS))
        self.assertEqual(h['rig_ns'], c['rig_ns'])
        self.assertEqual(h['explicit_ns'], c['explicit_ns'])

        bones = proj['bedAnim']['bones']
        chan_targets = {ch['target'] for ch in c['codec']['channels']}
        for bn in bones:
            self.assertIn(fnv32(bn), chan_targets, bn)

        rig = X._bed_rig('DOUBLE_BED')
        frame_rows = proj['bedAnim']['frames']
        frames = len(frame_rows)
        for bi, bn in enumerate(bones):
            info = rig[bn]
            parent = rig.get(info['parent']) if info['parent'] else None
            p_pos = parent['pos'] if parent else (0.0, 0.0, 0.0)
            p_rot = parent['rot'] if parent else (0.0, 0.0, 0.0, 1.0)
            p_inv = (-p_rot[0], -p_rot[1], -p_rot[2], p_rot[3])
            target = fnv32(bn)
            tch = next(ch for ch in c['codec']['channels'] if ch['target'] == target and ch['sub'] == 1)
            rch = next(ch for ch in c['codec']['channels'] if ch['target'] == target and ch['sub'] == 2)
            tvals, rvals = dict(decode_track(tch)), dict(decode_track(rch))
            for k in (0, frames // 2, frames - 1):
                dx, dy, dz, qx, qy, qz, qw = frame_rows[k][bi * 7:bi * 7 + 7]
                world_pos = (info['pos'][0] + dx, info['pos'][1] + dy, info['pos'][2] + dz)
                world_rot = _qn(_qmul((qx, qy, qz, qw), info['rot']))
                rel = tuple(world_pos[i] - p_pos[i] for i in range(3))
                exp_t = _qrot(p_inv, rel)
                exp_r = _qn(_qmul(p_inv, world_rot))
                got_t = tvals.get(k, tvals.get(0))
                got_r = list(rvals.get(k, rvals.get(0)))
                if sum(a * b for a, b in zip(got_r, exp_r)) < 0:      # q and -q are the same rotation
                    got_r = [-v for v in got_r]
                for a, b in zip(got_t, exp_t):
                    self.assertLess(abs(a - b), 1e-4, (bn, k, 't', got_t, exp_t))
                for a, b in zip(got_r, exp_r):
                    self.assertLess(abs(a - b), 1e-4, (bn, k, 'r', got_r, exp_r))

    @unittest.skipUnless(HAS_GAME, NO_GAME)
    def test_bed_parent_and_child_bone_compose_at_runtime(self):
        """A Pillow_trans_ bone and its child Pillow_squish_ bone are keyed together (as web/js/features/furnanim.js's
        boneDeltas() always sends them for a real bed): the exported LOCAL channels must combine correctly at
        runtime (parent's world pose that frame, then the child's local on top of it) back to each bone's own
        rest+delta target - not the parent's REST pose used for every frame, which double-applies the parent's own
        rotation to the child (caught by hand: a 20 degree pillow tip came back out as 40 degrees)."""
        trans, squish = '_bind_DB_Pillow_trans_L_', '_bind_DB_Pillow_squish_L_'
        rig = X._bed_rig('DOUBLE_BED')
        rest_p, rest_c = rig[trans]['pos'], rig[squish]['pos']
        rel0 = tuple(rest_c[i] - rest_p[i] for i in range(3))
        frames = 4
        rows = []
        for k in range(frames):
            qd = axis_quat((1, 0, 0), math.radians(8 * (k + 1)))
            dt = (0.0, -0.01 * (k + 1), 0.0)
            moved = tuple(_qrot(qd, rel0)[i] - rel0[i] for i in range(3))
            child_dt = (dt[0] + moved[0], dt[1] + moved[1], dt[2] + moved[2])
            rows.append(list(dt) + list(qd) + list(child_dt) + list(qd))          # child rotates exactly like its parent

        proj = baked_project(with_bed=False, frames=frames)
        proj['bedAnim'] = {'location': 'DOUBLE_BED', 'bones': [trans, squish], 'frames': rows}
        warnings = []
        res, clip_name = X.bed_resources(proj, 'basecheck', frames, frames, 0, 30, warnings)
        self.assertEqual(warnings, [])
        self.assertIsNotNone(clip_name)
        clip_bytes = next(d for t, g, i, d in res if t == X.T_CLIP)
        c = parse_clip(clip_bytes)
        chans = {(ch['target'], ch['sub']): ch for ch in c['codec']['channels']}
        t_t = dict(decode_track(chans[(fnv32(trans), 1)]))
        t_r = dict(decode_track(chans[(fnv32(trans), 2)]))
        s_t = dict(decode_track(chans[(fnv32(squish), 1)]))
        s_r = dict(decode_track(chans[(fnv32(squish), 2)]))

        grandp = rig.get(rig[trans]['parent'])
        gp_world = (grandp['pos'], grandp['rot']) if grandp else ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0))
        for k in range(frames):
            trans_world = (gp_world[0], gp_world[1])
            tp = _qrot(trans_world[1], t_t.get(k, t_t.get(0)))
            trans_world = (tuple(trans_world[0][i] + tp[i] for i in range(3)),
                           _qn(_qmul(trans_world[1], t_r.get(k, t_r.get(0)))))
            sp = _qrot(trans_world[1], s_t.get(k, s_t.get(0)))
            squish_world_pos = tuple(trans_world[0][i] + sp[i] for i in range(3))
            squish_world_rot = _qn(_qmul(trans_world[1], s_r.get(k, s_r.get(0))))

            dx, dy, dz, qx, qy, qz, qw = rows[k][7:14]
            target_pos = (rest_c[0] + dx, rest_c[1] + dy, rest_c[2] + dz)
            target_rot = _qn(_qmul((qx, qy, qz, qw), rig[squish]['rot']))
            if sum(a * b for a, b in zip(squish_world_rot, target_rot)) < 0:
                squish_world_rot = tuple(-v for v in squish_world_rot)
            for a, b in zip(squish_world_pos, target_pos):
                self.assertLess(abs(a - b), 1e-3, (k, 'pos', squish_world_pos, target_pos))
            for a, b in zip(squish_world_rot, target_rot):
                self.assertLess(abs(a - b), 1e-3, (k, 'rot', squish_world_rot, target_rot))

    def test_no_bedanim_is_unchanged(self):
        """No game needed: without project['bedAnim'] nothing about the export changes."""
        proj = baked_project(with_bed=False)
        res, info = X.animation_resources(proj, metas={}, present=set())
        self.assertIsNone(info.get('bed_clip'))
        xml = next(d for t, g, i, d in res if t == W.SNIPPET).decode('utf-8')
        self.assertNotIn('object_animation_clip_name', xml)
        clip_count = sum(1 for t, g, i, d in res if t == X.T_CLIP)
        header_count = sum(1 for t, g, i, d in res if t == X.T_CLIP_HEADER)
        self.assertEqual(clip_count, len(proj['actors']))          # just the two actors' clips, nothing extra
        self.assertEqual(header_count, len(proj['actors']))

        # the same project run twice (with vs. without a bedAnim block removed again) writes byte-identical clips
        proj2 = baked_project(with_bed=True)
        proj2.pop('bedAnim')
        res2, info2 = X.animation_resources(proj2, metas={}, present=set())
        key = lambda rs: sorted((t, g, i, d) for t, g, i, d in rs)
        self.assertEqual(key(res), key(res2))


if __name__ == '__main__':
    unittest.main(verbosity=2)

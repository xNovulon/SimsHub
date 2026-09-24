"""The clothes preview's backend (backend/clothes.py, backend/ext_clothes.py and the hair.py code it shares), without
the game: every CAS part, GEOM and texture here is SYNTHETIC, written with the repo's own package writer
(wwpackage.build_package) in the layouts the repo's readers parse (casptex.parse_casp, morph.read_geom, texfmt).

    python tools/checks/clothes/test_clothes.py

What it checks: which parts an outfit shows per category, the basic outfits' part choice, reading a part from a
"game" package and a "Mods" recolour, LOD 0 only, repeats and stand-in GEOMs left out, skin weights mapped to the rig
(unknown bones dropped), the fallback bone, cache keys and files, a body-shape slider (a BOND) moving the clothes
like the body, the refusals, and hair still picking its mesh after the shared code moved. Only a real game and real
Tray households can tell whether EA's actual parts look right (listed in the commit message).
Nothing is written outside a temp folder.
"""
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix='wa_clothes_')
os.environ['WA_FAKE_HOME'] = os.path.join(TMP, 'home')
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
sys.path.insert(0, HERE)
import fake_game_server as F      # noqa: E402  (the stand-in auRig; the server is not started)
import casptex                    # noqa: E402
import clothes as C               # noqa: E402
import ext_clothes as X           # noqa: E402
import hair                       # noqa: E402
import morph                      # noqa: E402
import wwpackage                  # noqa: E402
from clipfmt import fnv32         # noqa: E402
from synth import T_CASP, T_GEOM, T_DDS, make_casp, make_dds, make_geom, solid, point_parts_at  # noqa: E402

RIG = F.fake_rig()
RIDX = {b['name']: k for k, b in enumerate(RIG['bones'])}
H = {n: fnv32(n) for n in RIDX}
UNKNOWN = 0xDEADBEEF


def strip(y0, y1, bone_hashes, x=0.2, n=8):
    """A small vertical strip of n vertices from y0 to y1 (a stand-in mesh)."""
    return [(x if k % 2 else -x, y0 + (y1 - y0) * (k // 2) / max(1, n // 2 - 1), 0.1) for k in range(n)]


ADULT_F, ADULT_M, CHILD_F = 0x2000 | 0x10 | 0x20 | 0x40, 0x1000 | 0x10 | 0x20 | 0x40, 0x2000 | 0x4
I_TOP, I_TOP_GEOM, I_TOP_LOD1, I_TOP_TEX = 0x1000000000000001, 0x2000000000000001, 0x2000000000000002, 0x3000000000000001
I_TINY, I_RECOL, I_RECOL_TEX, I_TIGHTS, I_KID, I_HAIR, I_HAIR_GEOM, I_HAIR_TEX = (
    0x2000000000000003, 0x1000000000000002, 0x3000000000000002, 0x1000000000000003, 0x1000000000000004,
    0x1000000000000005, 0x2000000000000005, 0x3000000000000005)

# the top: 16 vertices; 0-3 on the chest, 4-5 split chest / upper arm, 6 partly on a bone the rig doesn't have,
# 7 only on that unknown bone (it goes to the part's main bone), 8-15 on the chest
TOP_POS = strip(1.1, 1.4, None, n=16)
TOP_BONES = [(0, 0, 0, 0)] * 4 + [(0, 2, 0, 0)] * 2 + [(0, 1, 0, 0), (1, 0, 0, 0)] + [(0, 0, 0, 0)] * 8
TOP_W = [(1, 0, 0, 0)] * 4 + [(0.5, 0.5, 0, 0)] * 2 + [(0.6, 0.4, 0, 0), (1, 0, 0, 0)] + [(1, 0, 0, 0)] * 8
TOP_HASHES = [H['b__Spine2__'], UNKNOWN, H['b__L_UpperArm__']]


def build_world():
    sims = os.path.join(TMP, 'sims')
    mods = os.path.join(sims, 'Mods')
    client = os.path.join(TMP, 'game', 'Data', 'Client')
    os.makedirs(mods, exist_ok=True)
    os.makedirs(client, exist_ok=True)
    geom_top = make_geom(TOP_POS, TOP_BONES, TOP_W, TOP_HASHES)
    lod1 = make_geom(strip(1.1, 1.4, None, n=20), [(0, 0, 0, 0)] * 20, [(1, 0, 0, 0)] * 20, [H['b__Spine2__']])
    tiny = make_geom([(0, 1.2, 0.1 + k * 0.0001) for k in range(16)], [(0, 0, 0, 0)] * 16, [(1, 0, 0, 0)] * 16, [H['b__Spine2__']])
    # the top's LOD 0 lists its mesh twice (groups 0 and 1), a 1 mm stand-in and, in LOD 1, a lower mesh
    top_tgis = [(T_GEOM, 0, I_TOP_GEOM), (T_GEOM, 1, I_TOP_GEOM), (T_GEOM, 0, I_TINY), (T_GEOM, 0, I_TOP_LOD1), (T_DDS, 0, I_TOP_TEX)]
    casp_top = make_casp('yfTop_TestTee_Red', 6, ADULT_F, [(0, [0, 1, 2]), (1, [3])], top_tgis, diffuse=4)
    casp_tights = make_casp('yfTights_Test', 42, ADULT_F, [], [(T_DDS, 0, I_TOP_TEX)], diffuse=0)
    casp_kid = make_casp('cuTop_Test', 6, CHILD_F, [(0, [0])], [(T_GEOM, 0, I_TOP_GEOM)])
    hair_tall = make_geom(strip(1.5, 1.8, None, n=20), [(0, 0, 0, 0)] * 20, [(1, 0, 0, 0)] * 20, [H['b__Head__']])
    hair_cut = make_geom(strip(1.5, 1.7, None, n=40), [(0, 0, 0, 0)] * 40, [(1, 0, 0, 0)] * 40, [H['b__Head__']])
    casp_hair = make_casp('yfHair_Test_Brown', 2, ADULT_F, [(0, [0, 1])], [(T_GEOM, 0, I_HAIR_GEOM), (T_GEOM, 1, I_HAIR_GEOM), (T_DDS, 0, I_HAIR_TEX)], diffuse=2)
    game = wwpackage.build_package([
        (T_CASP, 0, I_TOP, casp_top), (T_GEOM, 0, I_TOP_GEOM, geom_top), (T_GEOM, 1, I_TOP_GEOM, geom_top),
        (T_GEOM, 0, I_TINY, tiny), (T_GEOM, 0, I_TOP_LOD1, lod1), (T_DDS, 0, I_TOP_TEX, make_dds(solid(200, 20, 20))),
        (T_CASP, 0, I_TIGHTS, casp_tights), (T_CASP, 0, I_KID, casp_kid),
        (T_CASP, 0, I_HAIR, casp_hair), (T_GEOM, 0, I_HAIR_GEOM, hair_tall), (T_GEOM, 1, I_HAIR_GEOM, hair_cut),
        (T_DDS, 0, I_HAIR_TEX, make_dds(solid(90, 60, 30)))])
    # a CC recolour in Mods: its own CASP and texture, the game's mesh
    recol_tgis = [(T_GEOM, 0, I_TOP_GEOM), (T_DDS, 0, I_RECOL_TEX)]
    cc = wwpackage.build_package([
        (T_CASP, 0, I_RECOL, make_casp('yfTop_TestTee_CCBlue', 6, ADULT_F, [(0, [0])], recol_tgis, diffuse=1)),
        (T_DDS, 0, I_RECOL_TEX, make_dds(solid(20, 40, 220)))])
    paths = {'game': os.path.join(client, 'ClientFullBuild0.package'), 'cc': os.path.join(mods, 'TestRecolour.package')}
    for k, data in (('game', game), ('cc', cc)):
        with open(paths[k], 'wb') as f:
            f.write(data)
    point_parts_at(TMP, sims, paths['game'], paths['cc'])
    return paths


PATHS = build_world()


def spec_with(outfits, current=('EVERYDAY', 0)):
    return {'outfits': outfits, 'current_outfit': {'category': current[0], 'index': current[1]}}


def outfit(cat, idx, parts):
    return {'category': cat, 'category_id': 0, 'index': idx,
            'parts': [{'casp_instance': '0x%016x' % i, 'body_type': bt, 'body_type_name': str(bt)} for i, bt in parts]}


# ------------------------------------------------------------------ tests
class Outfits(unittest.TestCase):
    def test_parts_shown_per_outfit(self):
        parts = C.wearable([{'casp_instance': '0x10', 'body_type': 2}, {'casp_instance': '0x11', 'body_type': 8},
                            {'casp_instance': '0x12', 'body_type': 6}, {'casp_instance': '0x13', 'body_type': 29},
                            {'casp_instance': '0x14', 'body_type': 12}, {'casp_instance': '0x12', 'body_type': 6},
                            {'casp_instance': '0x15', 'body_type': 7}, {'casp_instance': '0x0', 'body_type': 7},
                            {'casp_instance': '0x16', 'body_type': 3}, {'casp_instance': '0x17', 'body_type': 42}])
        self.assertEqual([p['kind'] for p in parts], ['top', 'bottom', 'tights', 'shoes', 'accessory'])
        self.assertEqual([p['casp'] for p in parts], ['0x%016x' % i for i in (0x12, 0x15, 0x17, 0x11, 0x14)])

    def test_categories(self):
        spec = spec_with([
            outfit('EVERYDAY', 0, [(0x20, 2), (0x21, 6), (0x22, 7), (0x23, 8)]),
            outfit('BATHING', 0, [(0x198C, 6), (0x1990, 7)]),              # the nude body: never offered
            outfit('SLEEP', 0, [(0x20, 2)]),                                # hair only: nothing to wear
            outfit('FORMAL', 0, [(0x30, 5), (0x31, 8)]),
            outfit('EVERYDAY', 1, [(0x40, 6), (0x41, 7)]),
            outfit('SWIMWEAR', 0, [(0x50, 6), (0x51, 7)]),
            outfit('COLDWEATHER', 0, [(0x60, 5), (0x61, 1)]),
            outfit('CURRENT_OUTFIT', 0, [(0x70, 6)])])
        outs = C.outfits_of(spec)
        self.assertEqual([o['key'] for o in outs], ['EVERYDAY:0', 'EVERYDAY:1', 'FORMAL:0', 'SWIMWEAR:0', 'COLDWEATHER:0'])
        self.assertEqual([o['label'] for o in outs], ['Everyday', 'Everyday 2', 'Formal', 'Swimwear', 'Cold weather'])
        self.assertEqual([p['kind'] for p in outs[2]['parts']], ['full', 'shoes'])
        self.assertEqual([p['kind'] for p in outs[4]['parts']], ['full', 'hat'])
        self.assertEqual(C.pick_outfit(outs, 'EVERYDAY')['key'], 'EVERYDAY:0')
        self.assertEqual(C.pick_outfit(outs, 'EVERYDAY:1')['parts'][0]['casp'], '0x%016x' % 0x40)
        self.assertIsNone(C.pick_outfit(outs, 'FORMAL:1'))
        self.assertIsNone(C.pick_outfit(outs, 'PARTY'))
        self.assertIsNone(C.pick_outfit(outs, 'EVERYDAY:x'))
        self.assertEqual(C.current_key(spec), 'EVERYDAY:0')
        self.assertIsNone(C.current_key(spec_with([], ('BATHING', 0))))


class Basic(unittest.TestCase):
    CASPS = {
        1: {'body_type': 6, 'age_gender': ADULT_F, 'geoms': [1]},
        2: {'body_type': 7, 'age_gender': ADULT_F, 'geoms': [1]},
        3: {'body_type': 6, 'age_gender': CHILD_F, 'geoms': [1]},                  # not for adults
        4: {'body_type': 7, 'age_gender': ADULT_F, 'geoms': [1]},                  # a bottom named like a top
        5: {'body_type': 7, 'age_gender': ADULT_M, 'geoms': [1]},
        6: {'body_type': 7, 'age_gender': ADULT_F, 'geoms': []},                   # no mesh
        7: {'body_type': 6, 'age_gender': ADULT_F, 'geoms': [1]},
        8: {'body_type': 7, 'age_gender': ADULT_F, 'geoms': [1]},
    }
    NAMES = {'yfTop_Bra': 3, 'yfTop_BraX': 4, 'yfTop_SportsBra_White': 1, 'yfTop_BraLace_Black': 7,
             'yfBottom_Panties': 6, 'yfBottom_UnderwearBrief_Black': 2, 'ymBottom_BoxerBrief': 5,
             'yfBottom_Underwear_Teen': 8, 'yfTop_Bikini_Red': 99}

    def load(self, inst):
        return self.CASPS.get(inst)

    def test_female(self):
        out = C.resolve_basic('yf', self.NAMES, self.load)
        self.assertEqual([o['id'] for o in out], ['underwear'])        # casual: no tee; swim: the bikini doesn't load
        parts = out[0]['parts']
        # shortest valid name per slot: yfTop_Bra is a child's, yfTop_BraX a bottom -> yfTop_BraLace_Black
        self.assertEqual([p['name'] for p in parts], ['yfTop_BraLace_Black', 'yfBottom_UnderwearBrief_Black'])
        self.assertEqual([p['casp'] for p in parts], ['0x%016x' % 7, '0x%016x' % 2])
        self.assertEqual([p['kind'] for p in parts], ['top', 'bottom'])

    def test_male_and_futa(self):
        self.assertEqual(C.resolve_basic('ym', self.NAMES, self.load),
                         [{'id': 'underwear', 'label': 'Underwear', 'parts': [
                             {'casp': '0x%016x' % 5, 'name': 'ymBottom_BoxerBrief', 'body_type': 7, 'kind': 'bottom'}]}])
        self.assertEqual(C.resolve_basic('yf_futa', self.NAMES, self.load), C.resolve_basic('yf', self.NAMES, self.load))


class Parts(unittest.TestCase):
    def test_top_from_the_game(self):
        r = C.part_mesh('0x%016x' % I_TOP)
        self.assertEqual((r['origin'], r['name'], r['kind'], r['body_type']), ('game', 'yfTop_TestTee_Red', 'top', 6))
        self.assertEqual(len(r['meshes']), 1)                          # LOD 0, listed twice, stand-in left out
        m = r['meshes'][0]
        self.assertEqual(len(m['positions']), len(TOP_POS) * 3)        # not the 20-vertex LOD 1
        b = np.array(m['bones']).reshape(-1, 4)
        w = np.array(m['weights']).reshape(-1, 4)
        spine, arm = RIDX['b__Spine2__'], RIDX['b__L_UpperArm__']
        self.assertTrue(all(b[k, 0] == spine and w[k, 0] == 1 for k in range(4)))
        self.assertEqual((b[4, 0], b[4, 1]), (spine, arm))
        np.testing.assert_allclose(w[4, :2], [0.5, 0.5])
        self.assertEqual(b[6, 0], spine)                                # the unknown bone's 40% is dropped
        np.testing.assert_allclose(w[6], [1, 0, 0, 0])
        self.assertEqual((b[7, 0], w[7, 0]), (spine, 1))               # only an unknown bone: the part's main bone
        self.assertEqual(r['unknown_bones'], ['0x%08x' % UNKNOWN])
        self.assertTrue(np.array(m['bones']).max() < len(RIG['bones']))
        self.assertTrue(r['texture'] and os.path.isfile(C.texture_path(r['texture'])))
        from PIL import Image
        self.assertEqual(Image.open(C.texture_path(r['texture'])).convert('RGBA').getpixel((1, 1)), (200, 20, 20, 255))

    def test_cc_recolour(self):
        r = C.part_mesh('0x%016x' % I_RECOL)
        self.assertEqual((r['origin'], r['name']), ('cc', 'yfTop_TestTee_CCBlue'))
        self.assertEqual(len(r['meshes']), 1)                          # the game's mesh...
        from PIL import Image
        px = Image.open(C.texture_path(r['texture'])).convert('RGBA').getpixel((2, 2))
        self.assertEqual(px, (20, 40, 220, 255))                        # ...in the recolour's own colour
        self.assertNotEqual(r['cache'], C.part_mesh('0x%016x' % I_TOP)['cache'])

    def test_cache(self):
        inst = I_TOP
        k1 = C.cache_key(inst, PATHS['game'])
        self.assertEqual(k1, C.cache_key(inst, PATHS['game']))
        self.assertRegex(k1, r'^%016x_[0-9a-f]{8}_v%d$' % (inst, C.VERSION))
        self.assertNotEqual(k1, C.cache_key(inst + 1, PATHS['game']))
        self.assertNotEqual(k1, C.cache_key(inst, PATHS['cc']))
        r = C.part_mesh('0x%016x' % inst)
        self.assertEqual(r['cache'], k1)
        self.assertTrue(os.path.isfile(os.path.join(C.CACHE, k1 + '.json')))
        self.assertIs(C.part_mesh(inst), r)                            # memory
        C._mem.clear()
        again = C.part_mesh(inst)                                       # disk
        self.assertIsNot(again, r)
        self.assertEqual(again['meshes'], r['meshes'])
        st = os.stat(PATHS['game'])                                     # the package changed (a game update)
        os.utime(PATHS['game'], (st.st_atime, st.st_mtime + 60))
        try:
            self.assertNotEqual(C.cache_key(inst, PATHS['game']), k1)
        finally:
            os.utime(PATHS['game'], (st.st_atime, st.st_mtime))
        self.assertIsNone(C.texture_path('../clothes_%s.png' % k1.replace('_v', '_x')))
        self.assertIsNone(C.texture_path('hair_%016x_v2.png' % inst))
        self.assertIsNone(C.texture_path('clothes_%016x_zzzzzzzz_v1.png' % inst))

    def test_shaped_like_the_body(self):
        """A body slider that moves the chest bone (a BOND) moves the clothes on it, as it moves the body."""
        adj = np.array([(H['b__Spine2__'], (0, 0.1, 0), (0, 0, 0), (0, 0, 0, 1))],
                       dtype=[('hash', '<u4'), ('offset', '<f4', 3), ('scale', '<f4', 3), ('quat', '<f4', 4)])
        saved = morph.resolve_morphs, morph.bond
        morph.resolve_morphs = lambda spec, prefix='yf', include_face=True: ([{'kind': 'bond', 'inst': 7, 'weight': 1.0}], {})
        morph.bond = lambda inst: {'adjustments': adj}
        try:
            shape = {'tray_id': '0x01', 'sim_index': 0, 'prefix': 'yf', 'name': 'Test Sim'}
            r = C.part_mesh(I_TOP, shape)
            plain = C.part_mesh(I_TOP)
            p0 = np.array(plain['meshes'][0]['positions']).reshape(-1, 3)
            p1 = np.array(r['meshes'][0]['positions']).reshape(-1, 3)
            np.testing.assert_allclose(p1[:4] - p0[:4], [[0, 0.1, 0]] * 4, atol=1e-4)   # all on the chest
            self.assertTrue(0.03 < p1[4, 1] - p0[4, 1] < 0.1)                           # half on the arm
            self.assertEqual(r['shaped_for'], 'Test Sim')
            self.assertIs(C.part_mesh(I_TOP, shape), r)                 # kept per sim
            self.assertEqual(r['meshes'][0]['bones'], plain['meshes'][0]['bones'])
        finally:
            morph.resolve_morphs, morph.bond = saved

    def test_refusals_and_missing(self):
        with self.assertRaises(ValueError):
            C.part_mesh(I_KID)                                          # not for adults
        with self.assertRaises(ValueError):
            C.part_mesh(I_HAIR)                                         # hair is not clothing
        r = C.part_mesh(0x1234)
        self.assertEqual((r['origin'], r['meshes']), (None, []))       # not installed: nothing, no error
        t = C.part_mesh(I_TIGHTS)
        self.assertEqual((t['meshes'], t['painted'], t['kind']), ([], True, 'tights'))

    def test_hair_still_picks_the_uncut_mesh(self):
        r = hair.hair_mesh(I_HAIR)
        self.assertEqual(len(r['meshes']), 1)
        self.assertEqual(len(r['meshes'][0]['positions']), 20 * 3)     # the tallest, not the denser cut one
        self.assertTrue(r['texture'])


class Routes(unittest.TestCase):
    def test_answers(self):
        r = X.GET['clothes_part']({'casp': '0x%016x' % I_TOP})
        self.assertEqual(r['kind'], 'top')
        with self.assertRaises(ValueError):
            X.GET['clothes_part']({})
        with self.assertRaises(ValueError):
            X.GET['clothes_part']({'casp': 'nonsense'})
        with self.assertRaises(ValueError):
            X.GET['clothes_outfits']({})
        with self.assertRaises(LookupError):
            X.GET['clothes_basic']({'frame': 'cu'})
        with self.assertRaises(LookupError):
            X.GET['clothes_tex']({'file': '../../config.json'})
        data, ctype = X.GET['clothes_tex']({'file': r['texture']})
        self.assertEqual((ctype, data[:4]), ('image/png', b'\x89PNG'))

    def test_no_game_is_a_plain_404(self):
        saved = casptex.casp_by_name
        casptex.casp_by_name = lambda: (_ for _ in ()).throw(FileNotFoundError('The Sims 4 install not found'))
        C._basic.clear()
        try:
            with self.assertRaises(LookupError) as cm:
                X.GET['clothes_basic']({'frame': 'yf'})
            self.assertIn('install not found', str(cm.exception))
        finally:
            casptex.casp_by_name = saved


if __name__ == '__main__':
    unittest.main(verbosity=2)

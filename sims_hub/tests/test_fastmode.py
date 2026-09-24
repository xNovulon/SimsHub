"""Tests for speedkit.fastmode on a synthetic Sims 4 tree under E:\\speedkit_test\\fastmode (never the real one).

The fake world: Mods (a script mod with its tuning package that also carries a CAS part, FitStudio, user
CC named 'SpeedKit_Extra' and 'SpeedKit Merged/CAS_001' - CC like any other - and the SpeedKit Monitor
script) and Mods_parked (two S4S-merged CC catalogs in sim/, S4S-merged script companions with a
small and a large script share, a non-merged companion with CAS parts, a tiny CAS file, a big standalone
CAS file, sliders, the animation/ folder, a package too deep to load), a save and a Tray household, and a
fake game folder whose EA resources the library overrides. The fast profile is then simulated for real:
the kept packages and the built pack are copied into a separate Mods folder, indexed, and every key fast
mode needs must come out as the same bytes the full library uses.
"""
import collections, json, os, shutil, sqlite3, struct, sys, tempfile, time, unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit.dbpf import Package, PackageWriter, read_entries
from speedkit.library import Library, PARKED, MODS
from speedkit.journal import undo, JournalError
from speedkit.companions import Verdict
from speedkit.game_index import GameIndex
from speedkit import manifest as M
from speedkit import usedpack as U
from speedkit import fastmode as F
import speedkit.journal as journal_mod

BASE = r'E:\speedkit_test\fastmode'
REAL_CACHES = os.path.join(BASE, 'real')

SNIPPET, BUFF, ASM, CLIP = 0x7DF2169C, 0x6017E896, 0x02D5DF13, 0x6B20C4F3


# ------------------------------------------------------------------ protobuf for fake saves (as test_usedpack)
def varint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def fv(f, v):
    return varint(f << 3) + varint(v)


def f64(f, v):
    return varint(f << 3 | 1) + struct.pack('<Q', v)


def fb(f, b):
    return varint(f << 3 | 2) + varint(len(b)) + b


def packed64(f, vals):
    return fb(f, b''.join(struct.pack('<Q', v) for v in vals))


def sim_data(sim_id, hh_id, first, last, parts):
    outfits = fb(1, fv(1, 777) + fv(2, 0) + fb(5, packed64(1, parts)))
    return f64(1, sim_id) + f64(4, hh_id) + fb(5, first) + fb(6, last) + fb(21, outfits)


def savegame(households, sims):
    out = b''.join(fb(5, f64(2, hid) + fb(3, name)) for hid, name in households)
    return out + b''.join(fb(6, s) for s in sims)


def write_save(path, sg):
    with PackageWriter(path) as w:
        w.add((0x0D, 0, 1), sg)


def household_binary(path, fam_id, fam_name, sims):
    fam = fv(2, fam_id) + fb(3, fam_name) + b''.join(fb(6, s) for s in sims)
    msg = fb(1, fam)
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', 2, len(msg) + 12, 0, len(msg)) + msg + b'\x01\x00\x00\x00\x00')


# ------------------------------------------------------------------ fake resources
def casp(refs):
    body = struct.pack('<II', 46, 24) + b'\x00' * 24 + bytes([len(refs) + 1]) + struct.pack('<QII', 0, 0, 0)
    return body + b''.join(struct.pack('<QII', i, g, t) for t, g, i in refs)


def stbl(pairs):
    body = b''.join(struct.pack('<IBH', k, 0, len(s)) + s for k, s in pairs)
    return b'STBL' + struct.pack('<HBQHI', 5, 0, len(pairs), 0, sum(len(s) + 1 for k, s in pairs)) + body


def xml(n, body=''):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<I c="Buff" i="buff" m="buffs.buff" n="%s" s="1">%s</I>'
            % (n, body)).encode()


def filler_cas(base, n, tex_type=U.T_RLE2):
    """n CASPs, each with its own texture (CC ids base+k)."""
    out = []
    for k in range(n):
        c, tex = base + 2 * k, base + 2 * k + 1
        out.append(((U.T_CASP, 0, c), casp([(tex_type, 0, tex)])))
        out.append(((tex_type, 0, tex), (b'texture %x ' % tex) * 40))
    return out


def pkg(path, resources, merged=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        if merged is not None:
            w.add(M.MANIFEST_KEY, M.build_flat(merged))
        for k, data in resources:
            w.add(k, data)


# ids (CC ids are 64-bit, EA ids small)
CC_WORN, GEOM_WORN, RLE2_WORN = 0xA100000000000001, 0xA100000000000011, 0xA100000000000012
CC_NEW, GEOM_NEW = 0xA100000000000002, 0xA100000000000021
CC_TUNED, RLE2_TUNED = 0xA100000000000003, 0xA100000000000031
CC_SIMDATA, GEOM_SD = 0xA100000000000004, 0xA100000000000041
CC_CHAIN, RLE2_CHAIN = 0xA100000000000005, 0xA100000000000051
CC_ABSENT = 0xDEAD0000BEEF0001
OBJ_TUNED, MODL_TUNED, MLOD_TUNED = 0xD100000000000001, 0xD100000000000002, 0xD100000000000003
KEPT_CASP, GEOM_KEPTDEP = 0xA200000000000001, 0xA200000000000011
SHADOW_DMAP = 0xC200000000000002
TUNING_KEPT_WINS, TUNING_M1, SIMDATA_M1, SIMDATA_KEPT, STBL_M1 = (0xB000000000000001, 0xB000000000000002,
                                                                   0xB000000000000003, 0xB000000000000004,
                                                                   0x0011000000000005)
CLIP_M1, ASM_M1 = 0xB000000000000006, 0xB000000000000007
EA_PART, EA_OVR_PART = 0x1234, 0x1235
RLES_DR, GEOM_DR2, RLE2_OVR = 0x9A00000000000001, 0x9A00000000000002, 0x9B00000000000001
WALK_ID = 0xB69951B3FF9E1C9B          # hard-coded in the real LittleMsSam_QuickGoForWalkwithDog.ts4script
WALK = 'LittleMsSam_QuickGoForWalkwithDog'


def make_world(root):
    sims = os.path.join(root, 'sims')
    mods, parked = os.path.join(sims, 'Mods'), os.path.join(sims, 'Mods_parked')
    for d in (mods, parked, os.path.join(sims, 'saves'), os.path.join(sims, 'Tray')):
        os.makedirs(d, exist_ok=True)
    # --- Mods: a script mod whose tuning package names CC by id, carries a CAS part and a SimData
    scripts_dir = os.path.join(mods, 'scripts')
    os.makedirs(scripts_dir)
    src = [os.path.join(r, 'scripts', WALK + '.ts4script') for r in (PARKED, MODS)]
    real_script = next((p for p in src if os.path.exists(p)), None)
    if real_script:
        shutil.copy2(real_script, scripts_dir)        # a real, tiny script with a hard-coded 64-bit id
    else:
        with zipfile.ZipFile(os.path.join(scripts_dir, WALK + '.ts4script'), 'w') as z:
            z.writestr('readme.txt', 'no pyc')
    pkg(os.path.join(scripts_dir, 'Fake_Tuning.package'), [
        ((BUFF, 0, TUNING_KEPT_WINS), xml('kept_wins', '<T n="cas_part">%d</T><T n="obj">0x%016X</T>'
                                          % (CC_TUNED, OBJ_TUNED))),
        ((U.T_SIMDATA, 0, SIMDATA_KEPT), b'DATA' + b'\x00' * 3 + struct.pack('<Q', CC_SIMDATA) + b'\x00' * 9),
        ((U.T_CASP, 0, KEPT_CASP), casp([(U.T_GEOM, 0, GEOM_KEPTDEP)])),
    ])
    pkg(os.path.join(mods, 'FitStudio', 'FitStudio_anims.package'), filler_cas(0xF1F1000000000000, 25))
    # user CC whose names contain 'SpeedKit' (the merger's output) is CC like any other; only the exact
    # SpeedKit pack / monitor names are SpeedKit's own
    pkg(os.path.join(mods, 'SpeedKit_Extra.package'), filler_cas(0x5E5E000000000000, 25))
    pkg(os.path.join(mods, 'SpeedKit Merged', 'CAS_001.package'), filler_cas(0x5F5F000000000000, 25))
    with zipfile.ZipFile(os.path.join(mods, 'SpeedKit_Monitor.ts4script'), 'w') as z:
        z.writestr('readme.txt', 'monitor stand-in')
    # --- Mods_parked/sim: two S4S-merged CC catalogs (sim/ loads before Sliders/, after scripts/)
    m1 = filler_cas(0xE1E1000000000000, 25) + [
        ((BUFF, 0, TUNING_KEPT_WINS), xml('stale_copy')),                          # loses to scripts/ (kept)
        ((SNIPPET, 0, TUNING_M1), xml('m1_tuning', '<T n="part">%d</T>' % CC_CHAIN)),
        ((U.T_SIMDATA, 0, SIMDATA_M1), b'DATA' + b'\x01' * 20),
        ((U.T_STBL, 0, STBL_M1), stbl([(0x12345678, b'Some name')])),
        ((CLIP, 0, CLIP_M1), b'CLIP animation' * 30),
        ((ASM, 0, ASM_M1), b'ASM state machine' * 10),
        ((U.T_DMAP, 0, SHADOW_DMAP), b'winning slider map' * 20),                  # shadows Sliders/ copy
        ((U.T_GEOM, 0, GEOM_KEPTDEP), b'mesh a kept CAS part needs' * 20),
        ((U.T_GEOM, 0, GEOM_DR2), b'default replacement mesh' * 20),                # overrides EA's
        ((U.T_CASP, 0, EA_OVR_PART), casp([(U.T_RLE2, 0, RLE2_OVR)])),              # overrides EA part
        ((U.T_RLE2, 0, RLE2_OVR), b'recolor of an EA part' * 20),
        ((F.T_NAMEMAP, 0, 0x77), b'namemap'),
        ((F.T_S4S_HISTORY, 0, 0x78), b'batch fix history'),
    ]
    pkg(os.path.join(parked, 'sim', 'm1.package'), m1, merged=[('m1 sources', [k for k, _ in m1])])
    m2 = filler_cas(0xE2E2000000000000, 25) + [
        ((U.T_CASP, 0, CC_WORN), casp([(U.T_GEOM, 0, GEOM_WORN), (U.T_RLE2, 0, RLE2_WORN)])),
        ((U.T_GEOM, 0, GEOM_WORN), b'worn mesh' * 30),
        ((U.T_RLE2, 0, RLE2_WORN), b'worn texture' * 30),
        ((U.T_THUM, 2, CC_WORN), b'\x89PNG thumb' * 10),
        ((U.T_CASP, 0, CC_NEW), casp([(U.T_GEOM, 0, GEOM_NEW)])),
        ((U.T_GEOM, 0, GEOM_NEW), b'new outfit mesh' * 30),
        ((U.T_CASP, 0, CC_TUNED), casp([(U.T_RLE2, 0, RLE2_TUNED)])),
        ((U.T_RLE2, 0, RLE2_TUNED), b'tuned part texture' * 30),
        ((U.T_CASP, 0, CC_SIMDATA), casp([(U.T_GEOM, 0, GEOM_SD)])),
        ((U.T_GEOM, 0, GEOM_SD), b'simdata part mesh' * 30),
        ((U.T_CASP, 0, CC_CHAIN), casp([(U.T_RLE2, 0, RLE2_CHAIN)])),
        ((U.T_RLE2, 0, RLE2_CHAIN), b'chained part texture' * 30),
        ((U.T_CASP, 0, WALK_ID), casp([])),
        ((U.T_OBJD, 0, OBJ_TUNED), struct.pack('<I', 1) + struct.pack('<IIII', MODL_TUNED >> 32,
                                                                      MODL_TUNED & 0xFFFFFFFF, U.T_MODL, 0)),
        ((U.T_COBJ, 0, OBJ_TUNED), struct.pack('<III', 1, 0x1111, 0)),
        ((U.T_MODL, 0, MODL_TUNED), b'MODL' + struct.pack('<QII', MLOD_TUNED, U.T_MLOD, 0)),
        ((U.T_MLOD, 0, MLOD_TUNED), b'MLOD lod' * 10),
    ]
    pkg(os.path.join(parked, 'sim', 'm2.package'), m2, merged=[('m2 sources', [k for k, _ in m2])])
    # S4S merges the classifier ties to a script: small script share (parked) and a large one (kept)
    cm = filler_cas(0xC1C1000000000000, 210) + [((BUFF, 0, 0xC1C1FFFF00000001), xml('small script part'))]
    pkg(os.path.join(parked, 'sim', 'cm_small.package'), cm, merged=[('cm', [k for k, _ in cm])])
    cm2 = filler_cas(0xC2C2000000000000, 210) + [((BUFF, 0, 0xC2C2FFFF00000000 + n), xml('big script part %d' % n,
                                                                                         'x' * 4000))
                                                 for n in range(40)]
    pkg(os.path.join(parked, 'sim', 'cm_big.package'), cm2, merged=[('cm2', [k for k, _ in cm2])])
    pkg(os.path.join(parked, 'scripts', 'addon_cas.package'), filler_cas(0xADAD000000000000, 30))
    pkg(os.path.join(parked, 'scripts', 'tiny_cas.package'), filler_cas(0x7171000000000000, 2))
    pkg(os.path.join(parked, 'cc', 'bighair.package'), [((U.T_CASP, 0, 0xB1B1000000000001),
                                                         casp([(U.T_LRLE, 0, 0xB1B1000000000002)])),
                                                        ((U.T_LRLE, 0, 0xB1B1000000000002), os.urandom(6000))])
    pkg(os.path.join(parked, 'Sliders', 'slider.package'), [
        ((U.T_SMOD, 0, 0xC2000000000000AA), struct.pack('<I', 3) + struct.pack('<IIQ', U.T_DMAP, 0, SHADOW_DMAP)),
        ((U.T_DMAP, 0, SHADOW_DMAP), b'losing slider map' * 20)])
    pkg(os.path.join(parked, 'animation', 'anim1.package'), filler_cas(0xA0A0000000000000, 25)
        + [((CLIP, 0, 0xA0A0FFFF00000001), b'clip' * 50)])
    pkg(os.path.join(parked, 'a', 'b', 'c', 'd', 'e', 'f', 'deep.package'), filler_cas(0xDEDE000000000000, 25))
    # --- saves and Tray: a sim wearing CC, an EA part the library restyles, and CC installed nowhere
    sg = savegame([(0x7001, b'Lee Family')], [sim_data(0x5101, 0x7001, b'Ann', b'Lee', [CC_WORN, EA_PART, CC_ABSENT])])
    write_save(os.path.join(sims, 'saves', 'Slot_00000001.save'), sg)
    household_binary(os.path.join(sims, 'Tray', '0x00000000!0x0000000000000abc.householdbinary'), 0xABC,
                     b'Tray Family', [sim_data(0x5201, 0, b'Bo', b'Tray', [EA_PART])])
    # --- fake game: EA's parts and textures the library overrides
    gdir = os.path.join(root, 'game', 'Data', 'Simulation')
    os.makedirs(gdir)
    with open(os.path.join(gdir, 'Resource.cfg'), 'w') as f:
        f.write('Priority -30\nPackedFile *.package\n')
    with PackageWriter(os.path.join(gdir, 'SimulationPreload.package')) as w:
        w.add((U.T_CASP, 0, EA_PART), casp([(U.T_RLES, 0, RLES_DR)]))
        w.add((U.T_CASP, 0, EA_OVR_PART), casp([]))
        w.add((U.T_RLES, 0, RLES_DR), b'ea specular')
        w.add((U.T_GEOM, 0, GEOM_DR2), b'ea mesh')
    pkg(os.path.join(parked, 'dr', 'specular_dr.package'), [((U.T_RLES, 0, RLES_DR), b'no-shine specular' * 20)])
    return sims, real_script is not None


VERDICT_KINDS = {'scripts/Fake_Tuning.package': 'core', 'sim/cm_small.package': 'core', 'sim/cm_big.package': 'core',
                 'scripts/addon_cas.package': 'addon'}


def verdicts_for(lib):
    return {p.id: Verdict(VERDICT_KINDS.get(p.rel, 'cc'), 'scripts/x.ts4script' if p.rel in VERDICT_KINDS else None,
                          []) for p in lib.packages()}


def read_raw(path, key):
    with Package(path) as p:
        e = [x for x in p.entries if (x.t, x.g, x.i) == key][0]
        return p.raw(e)


def winner_raw(lib, key, roots=('Mods', 'Mods_parked')):
    """The bytes the game would use for key: the first copy in lib's load order (None if none)."""
    order = lib.load_order(roots)
    ids = {(r, rel): pid for pid, r, rel in lib.db.execute('select id, root, rel from pkg')}
    t, g, i = key
    have = {pid for (pid,) in lib.db.execute('select pkg from res where t=? and g=? and i=? and comp != 65504',
                                             (t, g, U.signed64(i)))}
    for r, rel in order:
        if ids.get((r, rel)) in have:
            return read_raw(lib.path(r, rel), key)
    return None


class FastModeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(BASE, exist_ok=True)
        cls.root = tempfile.mkdtemp(dir=BASE, prefix='t_')
        cls.sims, cls.has_script = make_world(cls.root)
        cls.roots = {'Mods': os.path.join(cls.sims, 'Mods'), 'Mods_parked': os.path.join(cls.sims, 'Mods_parked')}
        cls.lib = Library(db_path=os.path.join(cls.root, 'library.sqlite'), roots=cls.roots)
        cls.lib.scan()
        cls.game = U.load_game_ids(os.path.join(cls.root, 'game'), os.path.join(cls.root, 'game_ids.sqlite'))
        gi = GameIndex(os.path.join(cls.root, 'game.sqlite'), os.path.join(cls.root, 'game'))
        gi.scan()
        cls.overrides = gi.override_keys(cls.lib)
        gi.close()
        cls.cache = os.path.join(cls.root, 'companions.sqlite')
        cls.refs_db = os.path.join(cls.root, 'refs.sqlite')
        cls.old_big = F.BIG_CAS_BYTES
        F.BIG_CAS_BYTES = 3000                   # the fake 'big hair' is 6 KB

    @classmethod
    def tearDownClass(cls):
        F.BIG_CAS_BYTES = cls.old_big
        cls.lib.close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def refs(self):
        return U.scan_references(os.path.join(self.sims, 'saves'), os.path.join(self.sims, 'Tray'), self.refs_db,
                                 workers=1)

    def parked(self, lib=None):
        lib = lib or self.lib
        return F.park_set(lib, verdicts=verdicts_for(lib))

    def plan(self, refs=None, lib=None, parked=None):
        lib = lib or self.lib
        return F.plan_pack(lib, refs or self.refs(), parked if parked is not None else self.parked(lib),
                           game=self.game, overrides=self.overrides, cache_path=self.cache)

    # -------------------------------------------------------------- park_set
    def test_park_set_rules(self):
        ps = self.parked()
        rels = {rel for _, rel in ps}
        self.assertEqual(rels, {'sim/m1.package', 'sim/m2.package', 'sim/cm_small.package', 'cc/bighair.package',
                                'SpeedKit_Extra.package', 'SpeedKit Merged/CAS_001.package'})
        kept = {rel for _, rel in ps.kept}
        for rel in ('scripts/Fake_Tuning.package', 'FitStudio/FitStudio_anims.package', 'sim/cm_big.package', 'scripts/addon_cas.package', 'scripts/tiny_cas.package',
                    'Sliders/slider.package', 'animation/anim1.package', 'dr/specular_dr.package'):
            self.assertIn(rel, kept)
        self.assertNotIn('a/b/c/d/e/f/deep.package', rels | kept)      # never loads: neither list
        for root, rel in ps:                                           # a plain list of (root, rel)
            self.assertTrue(ps.reasons[(root, rel)])
        self.assertIn('script-mod content', ps.reasons[('Mods_parked', 'sim/cm_small.package')])
        self.assertIn('script-mod companion', ps.keep_reasons[('Mods_parked', 'sim/cm_big.package')])
        self.assertIn('animation', ps.keep_reasons[('Mods_parked', 'animation/anim1.package')])
        self.assertIn('FitStudio', ps.keep_reasons[('Mods', 'FitStudio/FitStudio_anims.package')])
        self.assertEqual(ps.stats['parked'], 6)
        self.assertTrue(F.is_speedkit_pack('!!!!!SpeedKit_Fast_001.package'))
        self.assertTrue(F.is_speedkit_pack('SpeedKit_UsedCC_002.package'))
        self.assertTrue(F.is_speedkit_file('SpeedKit_Monitor.ts4script'))
        for rel in ('SpeedKit Merged/CAS_001.package', 'SpeedKit Loose/x.package', 'SpeedKit_Extra.package',
                    '!!!!!SpeedKit_Fast_001.package.writing', 'sub/SpeedKit_Monitor.ts4script'):
            self.assertFalse(F.is_speedkit_file(rel), rel)
        self.assertEqual(ps.stats['full_casp'], ps.stats['parked_casp'] + ps.stats['kept_casp'])
        self.assertEqual(ps.rels(), rels)

    def test_park_set_with_the_real_classifier(self):
        """park_set without verdicts runs speedkit.companions (private cache; the game's own zips read-only)."""
        cache = os.path.join(self.root, 'companions_real.sqlite')
        if os.path.exists(os.path.join(REAL_CACHES, 'companions.sqlite')):
            shutil.copy2(os.path.join(REAL_CACHES, 'companions.sqlite'), cache)    # warm game-python facts
        ps = F.park_set(self.lib, cache_path=cache)
        rels = {rel for _, rel in ps}
        self.assertIn('sim/m1.package', rels)                          # CC catalog with plain tuning
        self.assertNotIn('scripts/Fake_Tuning.package', rels)
        self.assertNotIn('animation/anim1.package', rels)
        if self.has_script:
            # the real script hard-codes one of m2's CAS part ids: 'weak' companion, too small to park
            self.assertNotIn('sim/m2.package', rels)
            self.assertIn('weak', ps.keep_reasons[('Mods_parked', 'sim/m2.package')])

    # -------------------------------------------------------------- plan
    def test_plan_parts(self):
        p = self.plan()
        items = p.items
        k = lambda t, i, g=0: (t, g, i)
        part = lambda key: items[key].part if key in items else None
        # (a) worn CC with its closure and thumbnail
        for key in (k(U.T_CASP, CC_WORN), k(U.T_GEOM, GEOM_WORN), k(U.T_RLE2, RLE2_WORN), k(U.T_THUM, CC_WORN, 2)):
            self.assertEqual(part(key), 'a', key)
        # (b) script content of parked packages; the stale copy that loses to a kept package is left out
        for key in (k(SNIPPET, TUNING_M1), k(U.T_SIMDATA, SIMDATA_M1), k(U.T_STBL, STBL_M1), k(CLIP, CLIP_M1),
                    k(ASM, ASM_M1)):
            self.assertEqual(part(key), 'b', key)
        self.assertNotIn(k(BUFF, TUNING_KEPT_WINS), items)
        # (b) EA overrides: a mesh directly, an overriding CAS part with its closure
        self.assertEqual(part(k(U.T_GEOM, GEOM_DR2)), 'b')
        self.assertTrue(items[k(U.T_GEOM, GEOM_DR2)].why.startswith('EA override'))
        self.assertEqual(part(k(U.T_CASP, EA_OVR_PART)), 'b')
        self.assertEqual(part(k(U.T_RLE2, RLE2_OVR)), 'b')
        # (b) a key a kept package has but a parked copy wins: the parked (winning) copy is packed
        self.assertEqual(part(k(U.T_DMAP, SHADOW_DMAP)), 'b')
        self.assertTrue(items[k(U.T_DMAP, SHADOW_DMAP)].why.startswith('shadowed'))
        # never: S4S manifest, NameMap, batch-fix history
        self.assertFalse([x for x in items if x[0] in F.SKIP_TYPES])
        # (c) kept CC's own needs, and ids named by kept tuning, kept SimData, pack tuning and a script
        self.assertEqual(part(k(U.T_GEOM, GEOM_KEPTDEP)), 'c')
        for key in (k(U.T_CASP, CC_TUNED), k(U.T_RLE2, RLE2_TUNED), k(U.T_OBJD, OBJ_TUNED), k(U.T_COBJ, OBJ_TUNED),
                    k(U.T_MODL, MODL_TUNED), k(U.T_MLOD, MLOD_TUNED), k(U.T_CASP, CC_SIMDATA), k(U.T_GEOM, GEOM_SD),
                    k(U.T_CASP, CC_CHAIN), k(U.T_RLE2, RLE2_CHAIN)):
            self.assertEqual(part(key), 'c', key)
        if self.has_script:
            self.assertEqual(part(k(U.T_CASP, WALK_ID)), 'c')
            self.assertGreaterEqual(p.stats['c_scan']['script_ids'], 1)
        # not packed: CC nobody uses, the used CC of kept packages (they stay loaded), EA's own data
        self.assertNotIn(k(U.T_CASP, 0xE2E2000000000000), items)
        self.assertNotIn(k(U.T_CASP, CC_NEW), items)
        self.assertNotIn(k(U.T_CASP, KEPT_CASP), items)
        self.assertNotIn(k(U.T_RLES, RLES_DR), items)        # its winner (dr/specular_dr) is kept
        # every packed copy is the full library's winner and comes from a parked package
        parked_rels = {rel for _, rel in p.parked}
        for key, it in items.items():
            src = p.packages[it.pkg]
            self.assertIn(src['rel'], parked_rels)
            self.assertEqual(read_raw(os.path.join(self.roots[src['root']], src['rel']), key), winner_raw(self.lib, key))
        # numbers
        s = p.summary()
        self.assertEqual(sum(d['keys'] for d in s['parts'].values()), len(items))
        cas = p.stats['cas_parts']
        self.assertEqual(cas['full'], sum(1 for _ in self.lib.db.execute(
            'select 1 from res r join pkg p on p.id = r.pkg where r.t=? and p.rel != ?', (U.T_CASP, 'a/b/c/d/e/f/deep.package'))))
        self.assertEqual(cas['fast'], cas['kept'] + cas['pack'])
        self.assertEqual(cas['pack'], 6 if self.has_script else 5)   # worn, EA override, tuned, SimData, chain, script
        self.assertEqual(cas['kept'], 293)                           # 210 + 30 + 2 + 25 + 25 + 1 kept CAS parts
        self.assertLess(cas['fast'], cas['full'])
        self.assertEqual(p.absent['cas'], [CC_ABSENT])

    def test_plan_is_the_same_after_the_other_tool_moves_files(self):
        """mods_switch / the profile switcher move packages between Mods and Mods_parked (same rel): the
        plan, the park set and the library fingerprint do not change."""
        p1 = self.plan()
        a = os.path.join(self.roots['Mods_parked'], 'sim', 'm2.package')
        b = os.path.join(self.roots['Mods'], 'sim', 'm2.package')
        os.makedirs(os.path.dirname(b), exist_ok=True)
        os.rename(a, b)
        lib2 = Library(db_path=os.path.join(self.root, 'lib_moved.sqlite'), roots=self.roots)
        try:
            lib2.scan()
            p2 = self.plan(lib=lib2)
            self.assertEqual(set(p2.items), set(p1.items))
            self.assertEqual(p2.library_fp, p1.library_fp)
            self.assertEqual(F.park_set(lib2, verdicts=verdicts_for(lib2)).rels(), self.parked().rels())
            # a park list made before the move is resolved by rel
            p3 = F.plan_pack(lib2, self.refs(), list(self.parked()), game=self.game, overrides=self.overrides,
                             cache_path=self.cache)
            self.assertEqual(set(p3.items), set(p1.items))
        finally:
            lib2.close()
            os.rename(b, a)
            os.rmdir(os.path.dirname(b))

    def test_xml_and_binary_ids(self):
        data = (b'<T>12345678901234567890</T><T>0x00A1000000000001</T><U>034AEECB:00000000:A100000000000002</U>'
                b'<T>4294967295</T><T n="x">abc9223372036854775807</T><T>99</T>')
        self.assertEqual(F.xml_ids(data), {12345678901234567890, 0x00A1000000000001, 0xA100000000000002})
        tarr = F.np.array(sorted([0xA100000000000003, 0xA100000000000004, 5]), dtype=F.np.uint64)
        blob = b'x' * 3 + struct.pack('<Q', 0xA100000000000003) + b'y' * 6 + struct.pack('<Q', 5)
        self.assertEqual(F.binary_ids(blob, tarr), {0xA100000000000003})       # small values are ignored
        self.assertEqual(F.member({0xA100000000000004, 7, -1}, tarr), {0xA100000000000004})

    def test_layout_order_and_limits(self):
        p = self.plan()
        with self.assertRaises(ValueError):
            F.layout(p, 1 << 31)
        groups = F.layout(p, 700)
        self.assertGreater(len(groups), 1)
        ranks = [F._rank(it.t) for g in groups for it in g]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(groups[0][0].t, U.T_CASP)
        self.assertEqual(sum(len(g) for g in groups), len(p.items))

    # -------------------------------------------------------------- build / status / verify / update / undo
    def test_build_status_verify_update_undo(self):
        refs = self.refs()
        p = self.plan(refs)
        out = os.path.join(self.sims, 'SpeedKit', 'fastpack')
        home = os.path.join(self.sims, 'SpeedKit')
        dry = F.build_pack(p, max_package_bytes=900)
        self.assertGreater(len(dry), 1)
        self.assertFalse(os.path.exists(out))                       # a dry run writes nothing
        self.assertEqual(os.path.dirname(dry[0]['path']), out)       # default: <fake Sims>\SpeedKit\fastpack
        res = F.build_pack(p, max_package_bytes=900, dry_run=False)
        names = [os.path.basename(r['path']) for r in res]
        self.assertEqual(names, [F.PACK_NAME % (n + 1) for n in range(len(dry))])
        self.assertTrue(names[0].startswith('!!!!!SpeedKit_Fast_001'))
        # bit-exact copies of the chosen sources, catalog records first
        order = []
        for r in res:
            with Package(r['path']) as pk:
                for e in sorted(pk.entries, key=lambda e: e.off):
                    it = p.items[(e.t, e.g, e.i)]
                    src = p.packages[it.pkg]
                    self.assertEqual(pk.raw(e), read_raw(os.path.join(self.roots[src['root']], src['rel']),
                                                         (e.t, e.g, e.i)))
                    order.append(F._rank(e.t))
        self.assertEqual(order, sorted(order))
        self.assertEqual(len(order), len(p.items))
        man = F.read_manifest(out)
        self.assertEqual(man['keys'], len(p.items))
        self.assertEqual({s['name'] for s in man['saves_and_tray']},
                         {'Slot_00000001.save', '0x00000000!0x0000000000000abc.householdbinary'})
        self.assertEqual(man['library']['fingerprint'], p.library_fp)
        self.assertEqual(set(man['parts']), {'a', 'b', 'c'})
        self.assertTrue(os.path.exists(os.path.join(out, F.KEYS_FILE)))
        self.assertFalse(os.listdir(os.path.join(home, 'staging')))
        # fresh, and verify finds nothing missing (the CC installed nowhere is only reported)
        st = F.status(out)
        self.assertEqual(st['state'], 'fresh', st['why'])
        # installing a new SpeedKit Monitor does not make the pack stale; a changed merged-CC file does
        mon = os.path.join(self.roots['Mods'], 'SpeedKit_Monitor.ts4script')
        mst = os.stat(mon)
        os.utime(mon, ns=(mst.st_atime_ns, mst.st_mtime_ns + 7_000_000_000))
        self.assertEqual(F.status(out)['state'], 'fresh')
        merged = os.path.join(self.roots['Mods'], 'SpeedKit Merged', 'CAS_001.package')
        cst = os.stat(merged)
        os.utime(merged, ns=(cst.st_atime_ns, cst.st_mtime_ns + 7_000_000_000))
        try:
            self.assertTrue(F.status(out)['library_changed'])
        finally:
            os.utime(merged, ns=(cst.st_atime_ns, cst.st_mtime_ns))
            os.utime(mon, ns=(mst.st_atime_ns, mst.st_mtime_ns))
        v = F.verify(self.lib, refs, out, game=self.game, overrides=self.overrides, cache_path=self.cache)
        self.assertTrue(v['ok'], v)
        self.assertEqual(v['installed_nowhere'], {U.PART: 1})
        self.assertGreater(v['checked']['closure_casps'], 0)
        self.assertGreater(v['checked']['tuning_ids'], 0)
        # the fast profile for real: kept packages + the pack, indexed on their own
        self.simulate_fast_profile(p, out)
        # verify notices a pack that lacks what a sim wears
        self.assertNotIn(CC_NEW, {k[2] for k in F.pack_keys(out)})
        # a new save wearing more CC -> stale -> a small delta package
        extra = os.path.join(self.sims, 'saves', 'Slot_00000002.save')
        write_save(extra, savegame([], [sim_data(0x5301, 0, b'Cy', b'New', [CC_NEW])]))
        try:
            st = F.status(out)
            self.assertEqual(st['state'], 'stale')
            self.assertEqual(st['saves_changed'], ['Slot_00000002.save'])
            self.assertFalse(st['library_changed'])
            refs2 = self.refs()
            v = F.verify(self.lib, refs2, out, game=self.game, overrides=self.overrides, cache_path=self.cache)
            self.assertIn(('refs', '%s %016X' % (U.PART, CC_NEW), 'loaded by the full library, not in fast mode'),
                          v['missing'])
            kw = dict(game=self.game, overrides=self.overrides, cache_path=self.cache)
            parked = self.parked()
            d = F.update_pack(self.lib, refs2, parked=parked, **kw)
            self.assertEqual(d['action'], 'delta')
            self.assertEqual(d['missing_keys'], 2)                   # CC_NEW's CASP and its mesh
            self.assertFalse(os.path.exists(os.path.join(out, F.PACK_NAME % 900)))
            d = F.update_pack(self.lib, refs2, parked=parked, dry_run=False, **kw)
            self.assertTrue(os.path.exists(os.path.join(out, F.PACK_NAME % 900)))
            self.assertEqual(F.status(out)['state'], 'fresh')
            self.assertTrue(F.verify(self.lib, refs2, out, **kw)['ok'])
            self.assertEqual(F.update_pack(self.lib, refs2, parked=parked, **kw)['action'], 'none')
            # all deltas together over the limit -> a rebuild instead
            extra2 = os.path.join(self.sims, 'saves', 'Slot_00000003.save')
            write_save(extra2, savegame([], [sim_data(0x5401, 0, b'Di', b'More', [0xE2E2000000000000])]))
            try:
                refs3 = self.refs()
                self.assertEqual(F.update_pack(self.lib, refs3, parked=parked, **kw)['action'], 'delta')
                self.assertEqual(F.update_pack(self.lib, refs3, parked=parked, delta_limit=10, **kw)['action'], 'rebuild')
            finally:
                os.remove(extra2)
            # a pack source changes -> status says what; an unscanned index is refused; then a rebuild
            src = os.path.join(self.roots['Mods_parked'], 'sim', 'm2.package')
            stt = os.stat(src)
            os.utime(src, ns=(stt.st_atime_ns, stt.st_mtime_ns + 5_000_000_000))
            try:
                st = F.status(out)
                self.assertTrue(st['library_changed'])
                self.assertTrue(any('sim/m2.package' in w for w in st['why']), st['why'])
                with self.assertRaises(F.FastPackError):
                    F.update_pack(self.lib, refs2, parked=parked, **kw)
                self.lib.scan()
                u = F.update_pack(self.lib, refs2, parked=parked, **kw)
                self.assertEqual(u['action'], 'rebuild')
                self.assertIn('m2.package changed', ' '.join(u['why']))
            finally:
                os.utime(src, ns=(stt.st_atime_ns, stt.st_mtime_ns))
                self.lib.scan()
            # a kept package changes (the other chat's FitStudio exports an animation): no rebuild
            export = os.path.join(self.roots['Mods'], 'FitStudio', 'export_1.package')
            pkg(export, [((CLIP, 0, 0xF1F1FFFF00000001), b'new clip' * 20)])
            try:
                self.lib.scan()
                self.assertEqual(F.status(out)['state'], 'stale')
                self.assertEqual(F.update_pack(self.lib, refs2, parked=parked, **kw)['action'], 'refresh')
                pkg(export, [((CLIP, 0, 0xF1F1FFFF00000001), b'new clip' * 20),
                             ((BUFF, 0, 0xF1F1FFFF00000002), xml('export', '<T>%d</T>' % 0xE2E2000000000002))])
                self.lib.scan()
                u = F.update_pack(self.lib, refs2, parked=parked, **kw)
                self.assertEqual((u['action'], u['missing_keys']), ('delta', 2))    # the CAS part it names + texture
                # a kept package that now wins over a key the pack holds -> the pack must be rebuilt
                pkg(os.path.join(self.roots['Mods_parked'], 'animation', 'aaa.package'),
                    [((SNIPPET, 0, TUNING_M1), xml('newer copy that loads first'))])
                self.lib.scan()
                u = F.update_pack(self.lib, refs2, parked=parked, **kw)
                self.assertEqual(u['action'], 'rebuild')
                self.assertIn('animation/aaa.package', ' '.join(u['why']))
            finally:
                os.remove(export)
                aaa = os.path.join(self.roots['Mods_parked'], 'animation', 'aaa.package')
                if os.path.exists(aaa):
                    os.remove(aaa)
                self.lib.scan()
            self.assertEqual(F.status(out)['state'], 'fresh')
            # undo the delta: the 900 package leaves, the first manifest is back; undo the build: nothing left
            undo(d['journal'], home=home, check_game=False)
            self.assertFalse(os.path.exists(os.path.join(out, F.PACK_NAME % 900)))
            self.assertEqual(F.read_manifest(out)['keys'], len(p.items))
        finally:
            os.remove(extra)
            self.refs()
        undo(res[0]['journal'], home=home, check_game=False)
        self.assertFalse([n for n in os.listdir(out) if n.endswith(('.package', '.json'))])
        self.assertEqual(F.status(out)['state'], 'missing')

    def simulate_fast_profile(self, p, out):
        """Copy the kept packages (same rel) and the pack (Mods root) into a separate Mods folder, index it
        alone, and check every key fast mode needs is there with the full library's bytes."""
        fast = os.path.join(self.root, 'fastsim')
        mods = os.path.join(fast, 'Mods')
        for root, rel in p.parked.kept:
            dst = os.path.join(mods, rel.replace('/', os.sep))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(self.roots[root], rel.replace('/', os.sep)), dst)
        for n in os.listdir(out):
            if n.endswith('.package'):
                shutil.copy2(os.path.join(out, n), mods)
        flib = Library(db_path=os.path.join(fast, 'lib.sqlite'), roots={'Mods': mods})
        try:
            flib.scan()
            kept_keys = set()
            for root, rel in p.parked.kept:
                with Package(os.path.join(self.roots[root], rel)) as pk:
                    kept_keys |= {(e.t, e.g, e.i) for e in pk.entries if e.t not in F.SKIP_TYPES}
            need = set(p.items) | kept_keys
            for key in sorted(need):
                self.assertEqual(winner_raw(flib, key, ('Mods',)), winner_raw(self.lib, key), F.key_text(key))
            # CAS parts: the fast profile loads far fewer
            n_fast = flib.db.execute('select count(*) from res where t=?', (U.T_CASP,)).fetchone()[0]
            self.assertEqual(n_fast, p.stats['cas_parts']['fast'])
        finally:
            flib.close()
            shutil.rmtree(fast, ignore_errors=True)

    def test_pack_in_mods_root(self):
        """The profile switcher moves the pack files into the Mods root: status finds them, a rescan that
        indexes them does not change the plan, a build into the fastpack folder refuses, and an update
        writes its delta next to them - only while the game is not running."""
        refs = self.refs()
        p = self.plan(refs)
        sims = self.sims
        out = os.path.join(sims, 'SpeedKit', 'fp_mods')
        res = F.build_pack(p, out, dry_run=False)
        mods = self.roots['Mods']
        moved = []
        for r in res:
            dst = os.path.join(mods, os.path.basename(r['path']))
            os.rename(r['path'], dst)
            moved.append(dst)
        lib2 = Library(db_path=os.path.join(self.root, 'lib_pack_in_mods.sqlite'), roots=self.roots)
        extra = os.path.join(sims, 'saves', 'Slot_00000004.save')
        old_j, old_f = journal_mod.game_running, F.game_running
        try:
            st = F.status(out)
            self.assertEqual(st['state'], 'fresh', st['why'])
            self.assertEqual(st['pack']['where'], 'mods')
            lib2.scan()
            self.assertTrue(any(F.is_speedkit_pack(x.rel) for x in lib2.packages()))
            p2 = self.plan(refs, lib=lib2)
            self.assertEqual(set(p2.items), set(p.items))
            self.assertEqual(p2.library_fp, p.library_fp)
            with self.assertRaises(F.FastPackError):
                F.build_pack(p2, out, dry_run=False)
            write_save(extra, savegame([], [sim_data(0x5501, 0, b'Ed', b'Mods', [CC_NEW])]))
            refs2 = self.refs()
            kw = dict(game=self.game, overrides=self.overrides, cache_path=self.cache)
            journal_mod.game_running = F.game_running = lambda: True
            with self.assertRaises(JournalError):
                F.update_pack(lib2, refs2, out, parked=self.parked(lib2), dry_run=False, **kw)
            self.assertFalse(os.path.exists(os.path.join(mods, F.PACK_NAME % 900)))
            self.assertEqual(F.read_manifest(out)['keys'], len(p.items))           # untouched
            journal_mod.game_running = F.game_running = lambda: False
            d = F.update_pack(lib2, refs2, out, parked=self.parked(lib2), dry_run=False, **kw)
            self.assertEqual(d['action'], 'delta')
            self.assertTrue(os.path.exists(os.path.join(mods, F.PACK_NAME % 900)))
            self.assertEqual(F.status(out)['state'], 'fresh')
            moved.append(os.path.join(mods, F.PACK_NAME % 900))
            self.assertTrue(F.verify(lib2, refs2, out, **kw)['ok'])
        finally:
            journal_mod.game_running, F.game_running = old_j, old_f
            lib2.close()
            if os.path.exists(extra):
                os.remove(extra)
            self.refs()
            for m in moved:
                if os.path.exists(m):
                    os.remove(m)                      # test files of our own
            shutil.rmtree(out, ignore_errors=True)

    def test_build_refuses(self):
        p = self.plan()
        for bad in (os.path.join(self.sims, 'saves', 'fp'), os.path.join(self.root, 'outside'),
                    os.path.join(self.roots['Mods'], 'fp'), os.path.join(self.roots['Mods_parked'], 'fp')):
            with self.assertRaises(ValueError):
                F.build_pack(p, bad, dry_run=False)
            self.assertFalse(os.path.exists(bad))
        with self.assertRaises(ValueError):                        # pack files only in the Mods ROOT
            F.build_pack(p, os.path.join(self.sims, 'SpeedKit', 'fpx'), dry_run=False,
                         pack_dir=os.path.join(self.roots['Mods'], 'sub'))
        # a source that changed after the plan: nothing is written
        src = os.path.join(self.roots['Mods_parked'], 'sim', 'm1.package')
        st = os.stat(src)
        os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        out = os.path.join(self.sims, 'SpeedKit', 'fp_stale')
        try:
            with self.assertRaises(U.PlanStale):
                F.build_pack(p, out, dry_run=False)
            self.assertFalse(os.path.exists(out) and os.listdir(out))
        finally:
            os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))

    def test_status_of_damaged_or_missing_manifest(self):
        d = os.path.join(self.root, 'nopack')
        self.assertEqual(F.status(d)['state'], 'missing')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, F.MANIFEST), 'w') as f:
            f.write('{not json')
        self.assertEqual(F.status(d)['state'], 'stale')
        self.assertEqual(F.find_pack(os.path.join(self.root, 'nothing'))['where'], 'none')


class RealLibraryParkSet(unittest.TestCase):
    """park_set on a private copy of the real library index (read-only; skipped without it)."""
    DB = os.path.join(REAL_CACHES, 'library.sqlite')
    CACHE = os.path.join(REAL_CACHES, 'companions.sqlite')

    @unittest.skipUnless(os.path.exists(os.path.join(REAL_CACHES, 'library.sqlite'))
                         and os.path.exists(os.path.join(REAL_CACHES, 'companions.sqlite')), 'no private real index')
    def test_real_park_set(self):
        tmp = tempfile.mkdtemp(dir=BASE, prefix='real_')
        try:
            db, cache = os.path.join(tmp, 'library.sqlite'), os.path.join(tmp, 'companions.sqlite')
            for a, b in ((self.DB, db), (self.CACHE, cache)):
                s, d = sqlite3.connect(a), sqlite3.connect(b)
                s.backup(d)
                d.close()
                s.close()
            lib = Library(db)                         # never scanned: an index snapshot of the real library
            try:
                ps = F.park_set(lib, cache_path=cache)
                pk = {(p.root, p.rel): p for p in lib.packages()}
                for root, rel in ps:
                    self.assertFalse(rel.lower().startswith(('animation/', 'fitstudio/')), rel)
                for key in ps.kept:
                    self.assertFalse(key[1].lower().endswith('.ts4script'))
                kept_rels = {rel for _, rel in ps.kept}
                for rel in ('scripts/TURBODRIVER_WickedWhims_Tuning.package', 'animation/WW_LAMABOY_Animations.package'):
                    if any(k[1] == rel for k in pk):
                        self.assertIn(rel, kept_rels)
                parked_sim = sum(1 for _, rel in ps if rel.startswith('sim/'))
                self.assertGreater(parked_sim, 150)
                self.assertLess(ps.stats['kept_casp'], ps.stats['full_casp'] * 0.01)
            finally:
                lib.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=1)

"""Tests for speedkit.usedpack on a synthetic Sims 4 tree under E:\\speedkit_test\\usedpack (never the real one).

The fake world: a save (SaveGameData + lot objects + thrift store mannequin) and a Tray household
wearing CC and EA items, a library in Mods / Mods_parked built with PackageWriter (CASPs with key
lists, textures, thumbnails, a skin tone, a slider, a pet coat, a CC object with model/LOD/tuning/
strings, a wall, and default replacements of EA textures) and a fake game folder with EA ids (an EA
part with a base and a delta copy, an EA skin tone and slider). A last test runs the scanner on
copies of real saves (E:\\speedkit_test\\usedpack\\fake_sims) when present.
"""
import hashlib, json, os, shutil, sqlite3, struct, sys, tempfile, time, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit.dbpf import Package, PackageWriter, read_entries, ZLIB
from speedkit.library import Library
from speedkit.journal import undo
from speedkit import usedpack as U

BASE = r'E:\speedkit_test\usedpack'


# ------------------------------------------------------------------ protobuf encoding for fake saves
def varint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def fv(f, v):                    # varint field
    return varint(f << 3) + varint(v)


def f64(f, v):                   # fixed64 field
    return varint(f << 3 | 1) + struct.pack('<Q', v)


def fb(f, b):                    # length-delimited field
    return varint(f << 3 | 2) + varint(len(b)) + b


def packed64(f, vals):
    return fb(f, b''.join(struct.pack('<Q', v) for v in vals))


def packedv(f, vals):
    return fb(f, b''.join(varint(v) for v in vals))


def sim_data(sim_id, hh_id, first, last, parts, genetic=(), tone=0, sculpts=(), mods=(), hh_name=b'', pelts=()):
    outfits = fb(1, fv(1, 777) + fv(2, 0) + fb(5, packed64(1, parts)))          # OutfitList.outfits.parts.ids
    gen = fb(5, b''.join(fb(1, fv(1, p) + fv(2, 5)) for p in genetic))          # GeneticData.parts_list.parts.id
    facial = packedv(1, sculpts) + b''.join(fb(2, fv(1, m)) for m in mods)
    pelt = b''.join(fb(1, fv(1, p) + fv(2, 0xFF8040)) for p in pelts)          # PeltLayerDataList.layers.layer_id
    return (f64(1, sim_id) + f64(4, hh_id) + fb(5, first) + fb(6, last) + fv(10, tone) + fb(18, facial)
            + fb(21, outfits) + fb(22, hh_name) + fb(28, gen) + (fb(63, pelt) if pelts else b''))


def savegame(households, sims, mannequins=(), thrift=None):
    out = b''.join(fb(5, f64(2, hid) + fb(3, name) + fb(25, b''.join(fb(1, fv(1, r)) for r in rewards)))
                   for hid, name, rewards in households)
    out += b''.join(fb(6, s) for s in sims)
    out += b''.join(fb(15, f64(1, mid) + fv(13, tone) + fb(21, fb(1, fb(5, packed64(1, parts)))))
                    for mid, tone, parts in mannequins)
    if thrift:      # save_slot(2).gameplay_data(8).fashion_trend_service(43).thrift_store_mannequin(2)
        tone, sculpt = thrift
        out += fb(2, fb(8, fb(43, fb(2, f64(1, 1) + fb(12, packedv(1, [sculpt])) + fv(13, tone)))))
    return out


def zone(guids):
    objs = b''.join(fb(1, f64(1, 1000 + n) + fv(30, g)) for n, g in enumerate(guids))
    return f64(1, 55) + fb(2, os.urandom(4096)) + fb(3, objs)


def write_save(path, sg, zones):
    with PackageWriter(path) as w:
        w.add((0x0D, 0, 1), sg)
        for n, z in enumerate(zones):
            w.add((0x06, 0, 100 + n), z)
        w.add((0x0F, 0, 5), b'\xff\xd8\xff' + b'jpeg' * 50, compress=False)


def household_binary(path, fam_id, fam_name, sims, rewards=()):
    fam = fv(2, fam_id) + fb(3, fam_name) + b''.join(fb(6, s) for s in sims)
    fam += fb(21, b''.join(fb(1, fv(1, r)) for r in rewards))
    msg = fb(1, fam)
    with open(path, 'wb') as f:
        f.write(struct.pack('<IIII', 2, len(msg) + 12, 0, len(msg)) + msg + b'\x01\x00\x00\x00\x00')


def read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


# ------------------------------------------------------------------ fake resources
def casp(refs):
    """A CASP whose key list (u8 count + I-G-T entries) starts at 8 + 24."""
    body = struct.pack('<II', 46, 24) + b'\x00' * 24 + bytes([len(refs) + 1]) + struct.pack('<QII', 0, 0, 0)
    return body + b''.join(struct.pack('<QII', i, g, t) for t, g, i in refs)


def stbl(pairs):
    body = b''.join(struct.pack('<IBH', k, 0, len(s)) + s for k, s in pairs)
    return b'STBL' + struct.pack('<HBQHI', 5, 0, len(pairs), 0, sum(len(s) + 1 for k, s in pairs)) + body


# ids used by the fake world (CC ids are 64-bit, EA ids small)
CC_A, CC_B, CC_DEEP, CC_ABSENT, CC_ABSENT2 = 0xA1000000000000AA, 0xA2000000000000BB, 0xA3000000000000CC, 0xDEAD0000BEEF0001, 0xDEAD0000BEEF0002
EA_PART, EA_OVERRIDE = 0x1234, 0x1235
REWARD_CC = 0xA4000000000000DD
GEOM_A, GEOM_OTHER_GROUP, RLE2_AS_LRLE, RLES_EA, GEOM_MISSING = (0xB100000000000001, 0xB100000000000002,
                                                                  0xB100000000000003, 0xB100000000000004,
                                                                  0xB100000000000005)
TONE_CC, TONE_TEX = 0xC100000000000001, 0xC100000000000002
SMOD_CC, DMAP_CC = 0xC200000000000001, 0xC200000000000002
OBJ_CC, MODL_CC, MLOD_CC, IMG_CC, TUNING_CC = (0xD100000000000001, 0xD100000000000002, 0xD100000000000003,
                                               0xD100000000000004, 0xD100000000000005)
NAME_HASH = 0x5A5A1234
CWAL_CC, MATD_CC, WALL_TEX = 0xE100000000000001, 0xE100000000000002, 0xE100000000000003
BUFF_T = 0x6017E896
# EA looks the library restyles (default replacements), and a CC pet coat
RLES_DR, RLE2_DR_DELTA, EA_GEOM = 0x9A00000000000001, 0x9A00000000000002, 0x9A00000000000003
EA_TONE, EA_TONE_TEX, EA_SMOD, EA_DMAP = 0x2F5A, 0x9B00000000000001, 0x9C00000000000001, 0x9C00000000000002
PELT_CC, PELT_TEX = 0xF100000000000001, 0xF100000000000002
THRIFT_TONE, THRIFT_SCULPT = 0xF200000000000001, 0xF200000000000002


def make_world(root):
    sims_dir = os.path.join(root, 'sims')
    mods, parked = os.path.join(sims_dir, 'Mods'), os.path.join(sims_dir, 'Mods_parked')
    for d in (os.path.join(mods, 'cc'), os.path.join(parked, 'cc'), os.path.join(sims_dir, 'saves'),
              os.path.join(sims_dir, 'Tray'), os.path.join(root, 'game', 'Data')):
        os.makedirs(d, exist_ok=True)
    deep = os.path.join(parked, 'a', 'b', 'c', 'd', 'e', 'f')
    os.makedirs(deep)
    # --- library. Load order: Mods_parked/cc/A_first before Mods_parked/cc/B_second (NTFS name order)
    with PackageWriter(os.path.join(parked, 'cc', 'A_first.package')) as w:
        w.add((U.T_CASP, 0, CC_A), casp([(U.T_GEOM, 0, GEOM_A), (U.T_GEOM, 0, GEOM_OTHER_GROUP),
                                          (U.T_RLE2, 0, RLE2_AS_LRLE), (U.T_RLES, 0, RLES_EA),
                                          (U.T_GEOM, 0, GEOM_MISSING), (BUFF_T, 0, 0x99)]))
        w.add((U.T_GEOM, 0, GEOM_A), b'winner mesh' * 20)
        w.add((U.T_GEOM, 1, GEOM_OTHER_GROUP), b'other group mesh' * 20)
        w.add((U.T_LRLE, 0, RLE2_AS_LRLE), b'lrle texture' * 20)
        w.add((U.T_THUM, 2, CC_A), b'\x89PNG thumb' * 10)
        w.add((U.T_THUM, 0x102, CC_A), b'\x89PNG thumb big' * 10)
        w.add((U.T_CASP, 0, EA_OVERRIDE), casp([(U.T_GEOM, 0, GEOM_A)]))
        w.add((U.T_CASP, 0, 0xF00000000000000F), casp([(U.T_GEOM, 0, 0xF0)]))   # CC nobody wears
    with PackageWriter(os.path.join(parked, 'cc', 'B_second.package')) as w:
        w.add((U.T_GEOM, 0, GEOM_A), b'loser mesh copy' * 20)                   # same key, loads later
        w.add((U.T_CASP, 0, CC_B), casp([(U.T_GEOM, 0, GEOM_A)]))
        w.add((U.T_CASP, 0, REWARD_CC), casp([]))
        w.add((U.T_TONE, 0, TONE_CC), struct.pack('<IQ', 7, TONE_TEX) + b'\x00' * 30)
        w.add((U.T_RLE2, 0, TONE_TEX), b'skin texture' * 30)
        w.add((U.T_SMOD, 0, SMOD_CC), struct.pack('<I', 3) + struct.pack('<IIQ', U.T_DMAP, 0, DMAP_CC) + b'\x00' * 8)
        w.add((U.T_DMAP, 0, DMAP_CC), b'deformer map' * 30)
    with PackageWriter(os.path.join(mods, 'cc', 'object.package')) as w:
        w.add((U.T_OBJD, 0, OBJ_CC), struct.pack('<I', 1) + struct.pack('<IIII', MODL_CC >> 32, MODL_CC & 0xFFFFFFFF, U.T_MODL, 0)
              + struct.pack('<Q', TUNING_CC))
        w.add((U.T_COBJ, 0, OBJ_CC), struct.pack('<III', 1, NAME_HASH, 0))
        w.add((U.T_OTHM, 0, OBJ_CC), b'\x89PNG object thumb' * 5)
        w.add((U.T_MODL, 0, MODL_CC), b'MODL' + struct.pack('<QII', MLOD_CC, U.T_MLOD, 0))
        w.add((U.T_MLOD, 0, MLOD_CC), b'MLOD' + struct.pack('<QII', IMG_CC, U.T_IMG, 0))
        w.add((U.T_IMG, 0, IMG_CC), b'DDS object texture' * 20)
        w.add((U.T_OBJ_TUNING, 0, TUNING_CC), b'<I c="Object" i="object" n="cc_chair" s="1"/>')
        w.add((U.T_SIMDATA, 0, TUNING_CC), b'DATA' + b'\x00' * 20)
        w.add((U.T_STBL, 0, 0x0011111111111111), stbl([(NAME_HASH, b'CC Chair')]))
        w.add((U.T_STBL, 0, 0x0022222222222222), stbl([(0x1, b'other string')]))
        w.add((U.T_CWAL, 0, CWAL_CC), struct.pack('<QII', MATD_CC, U.T_MATD, 0))
        w.add((U.T_MATD, 0, MATD_CC), b'MATD' + struct.pack('<QII', WALL_TEX, U.T_IMG, 0))
        w.add((U.T_IMG, 0, WALL_TEX), b'wall texture' * 10)
    with PackageWriter(os.path.join(deep, 'too_deep.package')) as w:           # 6 folders down: never loads
        w.add((U.T_CASP, 0, CC_DEEP), casp([]))
    os.makedirs(os.path.join(parked, 'dr'))
    with PackageWriter(os.path.join(parked, 'dr', 'defaults.package')) as w:     # default replacements of EA keys
        w.add((U.T_RLES, 0, RLES_DR), b'no-shine specular' * 20)
        w.add((U.T_RLE2, 0, RLE2_DR_DELTA), b'eye texture DR' * 20)
        w.add((U.T_THUM, 2, EA_PART), b'\x89PNG DR thumb' * 10)
        w.add((U.T_RLE2, 0, EA_TONE_TEX), b'skin DR texture' * 20)
        w.add((U.T_DMAP, 0, EA_DMAP), b'slider DR dmap' * 20)
        w.add((U.T_PELT, 0, PELT_CC), struct.pack('<I', 1) + struct.pack('<QII', PELT_TEX, 0, U.T_RLE2) + b'\x00' * 8)
        w.add((U.T_RLE2, 0, PELT_TEX), b'coat texture' * 20)
    # --- fake game: EA ids. EA_PART has a base copy and a patched (delta) copy listing one more key
    with PackageWriter(os.path.join(root, 'game', 'Data', 'SimulationPreload.package')) as w:
        w.add((U.T_CASP, 0, EA_PART), casp([(U.T_RLES, 0, RLES_DR), (U.T_GEOM, 0, EA_GEOM)]))
        w.add((U.T_CASP, 0, EA_OVERRIDE), casp([]))
        w.add((U.T_RLES, 0, RLES_EA), b'ea specular')
        w.add((U.T_RLES, 0, RLES_DR), b'ea specular that the library replaces')
        w.add((U.T_GEOM, 0, EA_GEOM), b'ea mesh')
        w.add((U.T_TONE, 0, EA_TONE), struct.pack('<IQ', 7, EA_TONE_TEX) + b'\x00' * 30)
        w.add((U.T_RLE2, 0, EA_TONE_TEX), b'ea skin')
        w.add((U.T_SMOD, 0, EA_SMOD), struct.pack('<I', 3) + struct.pack('<IIQ', U.T_DMAP, 0, EA_DMAP) + b'\x00' * 8)
        w.add((U.T_DMAP, 0, EA_DMAP), b'ea dmap')
    os.makedirs(os.path.join(root, 'game', 'Delta'))
    with PackageWriter(os.path.join(root, 'game', 'Delta', 'SimulationDeltaBuild0.package')) as w:
        w.add((U.T_CASP, 0, EA_PART), casp([(U.T_RLES, 0, RLES_DR), (U.T_RLE2, 0, RLE2_DR_DELTA)]))
        w.add((U.T_RLE2, 0, RLE2_DR_DELTA), b'ea eyes')
    # --- saves and Tray
    sims = [sim_data(0x5101, 0x7001, b'Ann', b'Lee', [CC_A, EA_PART, EA_OVERRIDE, CC_ABSENT], genetic=[CC_B],
                     tone=TONE_CC, mods=[SMOD_CC], pelts=[PELT_CC])]
    sg = savegame([(0x7001, b'Lee Family', [REWARD_CC])], sims, mannequins=[(0x9001, 0, [CC_DEEP])],
                  thrift=(THRIFT_TONE, THRIFT_SCULPT))
    write_save(os.path.join(sims_dir, 'saves', 'Slot_00000001.save'), sg, [zone([OBJ_CC, 20627])])
    tray_sim = sim_data(0x5201, 0, b'Bo', b'Tray', [CC_ABSENT2, EA_PART], tone=EA_TONE, mods=[EA_SMOD])
    household_binary(os.path.join(sims_dir, 'Tray', '0x00000000!0x0000000000000abc.householdbinary'),
                     0xABC, b'Tray Family', [tray_sim])
    with open(os.path.join(sims_dir, 'Tray', '0x00000002!0x0000000000000abc.hhi'), 'wb') as f:
        f.write(b'\xff\xd8\xff image')
    return sims_dir


class UsedPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(BASE, exist_ok=True)
        cls.root = tempfile.mkdtemp(dir=BASE, prefix='t_')
        cls.sims = make_world(cls.root)
        cls.saves, cls.tray = os.path.join(cls.sims, 'saves'), os.path.join(cls.sims, 'Tray')
        cls.lib = Library(db_path=os.path.join(cls.root, 'library.sqlite'),
                          roots={'Mods': os.path.join(cls.sims, 'Mods'), 'Mods_parked': os.path.join(cls.sims, 'Mods_parked')})
        cls.lib.scan()
        cls.game = U.load_game_ids(os.path.join(cls.root, 'game'), os.path.join(cls.root, 'game_ids.sqlite'))
        cls.refs_db = os.path.join(cls.root, 'refs.sqlite')

    @classmethod
    def tearDownClass(cls):
        cls.lib.close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def refs(self, **kw):
        return U.scan_references(self.saves, self.tray, self.refs_db, workers=1, **kw)

    def plan(self, refs=None, **kw):
        return U.plan(self.lib, refs or self.refs(), game=self.game, **kw)

    # -------------------------------------------------------------- scanning
    def test_scan_categories_and_sims(self):
        r = self.refs()
        self.assertEqual(r.ids(U.PART), {CC_A, EA_PART, EA_OVERRIDE, CC_ABSENT, CC_B, CC_DEEP, CC_ABSENT2})
        self.assertEqual(r.ids(U.PART_OTHER), {REWARD_CC})
        self.assertEqual(r.ids(U.TONE), {TONE_CC, EA_TONE, THRIFT_TONE, 0})
        self.assertEqual(r.ids(U.MODIFIER), {SMOD_CC, EA_SMOD})
        self.assertEqual(r.ids(U.SCULPT), {THRIFT_SCULPT})
        self.assertEqual(r.ids(U.PELT), {PELT_CC})
        self.assertIn(OBJ_CC, r.ids(U.OBJECT))
        sims = {s.name: s for s in r.sim_list()}
        self.assertEqual(sims['Ann Lee'].household, 'Lee Family')
        self.assertEqual(sims['Ann Lee'].parts, {CC_A, EA_PART, EA_OVERRIDE, CC_ABSENT, CC_B})
        self.assertEqual(sims['Bo Tray'].household, 'Tray Family')
        self.assertEqual(sims['(mannequin)'].parts, {CC_DEEP})

    def test_scan_is_incremental_and_survives_backup_rotation(self):
        db = os.path.join(self.root, 'incr.sqlite')
        r1 = U.scan_references(self.saves, self.tray, db, workers=1)
        self.assertEqual(r1.stats['parsed'], 2)                  # the save + the household (images skipped)
        r2 = U.scan_references(self.saves, self.tray, db, workers=1)
        self.assertEqual(r2.stats['parsed'], 0)
        # the game rotates Slot.save -> Slot.save.ver0 and writes a new Slot.save
        src = os.path.join(self.saves, 'Slot_00000001.save')
        ver = os.path.join(self.saves, 'Slot_00000002.save.ver0')
        shutil.copy2(src, ver)
        r3 = U.scan_references(self.saves, self.tray, db, workers=1, include_backups=True)
        self.assertEqual(r3.stats['parsed'], 0)                  # same content fingerprint: reused
        self.assertEqual(len(r3.selected(True)), 3)
        self.assertEqual(len(r3.selected(False)), 2)
        os.remove(ver)

    def test_scan_with_worker_processes(self):
        db = os.path.join(self.root, 'mp.sqlite')
        r = U.scan_references(self.saves, self.tray, db, workers=2)
        self.assertEqual(r.stats['parsed'], 2)
        self.assertEqual(r.ids(U.PART), self.refs().ids(U.PART))

    def test_game_ids_cached(self):
        self.assertEqual(self.game.casp, {EA_PART, EA_OVERRIDE})
        self.assertTrue(self.game.has(U.T_RLES, RLES_EA))
        self.assertFalse(self.game.has(U.T_RLES, GEOM_A))
        # 'built' has one-second resolution and the fake game indexes in milliseconds, so comparing it
        # proves nothing: mark the cache instead (a rebuild wipes the meta table)
        db = sqlite3.connect(os.path.join(self.root, 'game_ids.sqlite'))
        db.execute("insert or replace into meta values('test_marker', 'still here')")
        db.commit()
        db.close()
        again = U.load_game_ids(os.path.join(self.root, 'game'), os.path.join(self.root, 'game_ids.sqlite'))
        self.assertEqual(again.info.get('test_marker'), 'still here')
        self.assertEqual(again.casp, self.game.casp)

    # -------------------------------------------------------------- plan
    def test_plan_contents(self):
        p = self.plan()
        keys = set(p.items)
        k = lambda t, i, g=0: (t, g, i)
        # worn CC parts, the EA override, the reward part; not the EA part, not the unworn CC, not the too-deep copy
        for i in (CC_A, CC_B, EA_OVERRIDE, REWARD_CC):
            self.assertIn(k(U.T_CASP, i), keys)
        for i in (EA_PART, 0xF00000000000000F, CC_DEEP):
            self.assertNotIn(k(U.T_CASP, i), keys)
        # key list: exact, other-group fallback, texture-type fallback; EA's RLES and the tuning ref left out
        self.assertIn(k(U.T_GEOM, GEOM_A), keys)
        self.assertIn(k(U.T_GEOM, GEOM_OTHER_GROUP, 1), keys)
        self.assertIn(k(U.T_LRLE, RLE2_AS_LRLE), keys)
        self.assertNotIn(k(U.T_RLES, RLES_EA), keys)
        self.assertFalse([x for x in keys if x[0] == BUFF_T])
        res = p.stats['cas']['ref_resolution']
        self.assertEqual((res['same_type_other_group'], res['other_texture_type'], res['ea_game'], res['missing']),
                         (1, 1, 1, 1))
        # thumbnails, skin tone + its texture, slider + its deformer map
        self.assertIn(k(U.T_THUM, CC_A, 2), keys)
        self.assertIn(k(U.T_THUM, CC_A, 0x102), keys)
        for key in (k(U.T_TONE, TONE_CC), k(U.T_RLE2, TONE_TEX), k(U.T_SMOD, SMOD_CC), k(U.T_DMAP, DMAP_CC)):
            self.assertIn(key, keys)
        # the CC object with its model chain, own tuning, the string table naming it (not the other one)
        for key in (k(U.T_OBJD, OBJ_CC), k(U.T_COBJ, OBJ_CC), k(U.T_OTHM, OBJ_CC), k(U.T_MODL, MODL_CC),
                    k(U.T_MLOD, MLOD_CC), k(U.T_IMG, IMG_CC), k(U.T_OBJ_TUNING, TUNING_CC),
                    k(U.T_SIMDATA, TUNING_CC), k(U.T_STBL, 0x0011111111111111)):
            self.assertIn(key, keys)
        self.assertNotIn(k(U.T_STBL, 0x0022222222222222), keys)
        # walls and floors safety net
        for key in (k(U.T_CWAL, CWAL_CC), k(U.T_MATD, MATD_CC), k(U.T_IMG, WALL_TEX)):
            self.assertIn(key, keys)
        self.assertNotIn(k(U.T_CWAL, CWAL_CC), set(self.plan(build_surfaces=False).items))
        # CC pet coat with its texture
        self.assertIn(k(U.T_PELT, PELT_CC), keys)
        self.assertIn(k(U.T_RLE2, PELT_TEX), keys)

    def test_plan_packs_default_replacements_of_worn_ea_looks(self):
        p = self.plan()
        keys = set(p.items)
        k = lambda t, i, g=0: (t, g, i)
        # EA_PART (worn, EA's own): the library's copies of keys either game copy lists, and its CAS thumbnail
        self.assertEqual(p.items[k(U.T_RLES, RLES_DR)].why, 'EA part DR RLES')
        self.assertIn(k(U.T_RLE2, RLE2_DR_DELTA), keys)                  # listed by the delta copy only
        self.assertIn(k(U.T_THUM, EA_PART, 2), keys)
        self.assertNotIn(k(U.T_GEOM, EA_GEOM), keys)                     # EA's, not replaced by the library
        self.assertNotIn(k(U.T_CASP, EA_PART), keys)                     # the EA part itself stays EA's
        self.assertEqual(p.stats['ea_restyled']['game_casps_read'], 2)
        # EA skin tone -> its texture by instance; EA slider -> its deformer map by key
        self.assertIn(k(U.T_RLE2, EA_TONE_TEX), keys)
        self.assertIn(k(U.T_DMAP, EA_DMAP), keys)
        self.assertNotIn(k(U.T_TONE, EA_TONE), keys)
        # switched off: none of it
        off = set(self.plan(ea_overrides=False).items)
        for key in (k(U.T_RLES, RLES_DR), k(U.T_RLE2, RLE2_DR_DELTA), k(U.T_THUM, EA_PART, 2),
                    k(U.T_RLE2, EA_TONE_TEX), k(U.T_DMAP, EA_DMAP)):
            self.assertNotIn(key, off)
        self.assertEqual(keys - off, {k(U.T_RLES, RLES_DR), k(U.T_RLE2, RLE2_DR_DELTA), k(U.T_THUM, EA_PART, 2),
                                      k(U.T_RLE2, EA_TONE_TEX), k(U.T_DMAP, EA_DMAP)})

    def test_plan_takes_first_loaded_copy(self):
        p = self.plan()
        it = p.items[(U.T_GEOM, 0, GEOM_A)]
        self.assertTrue(p.packages[it.pkg]['rel'].endswith('A_first.package'))

    def test_fingerprint_sees_a_change_in_the_middle_of_a_big_save(self):
        """A re-save that keeps the package layout (first and last MiB identical) is still re-parsed."""
        d = os.path.join(self.root, 'mid')
        saves = os.path.join(d, 'saves')
        os.makedirs(saves)
        path = os.path.join(saves, 'Slot_00000007.save')
        filler = [os.urandom(3 << 20), os.urandom(3 << 20)]

        def write(part):
            sg = savegame([], [sim_data(0x5401, 0, b'Di', b'Mid', [part])])
            with PackageWriter(path) as w:
                w.add((0x10, 0, 1), filler[0], compress=False)                   # image-type filler
                w.add((0x0D, 0, 1), sg, compress=False)                          # same size for any part id
                w.add((0x14, 0, 2), filler[1], compress=False)

        def ends():
            with open(path, 'rb') as f:
                head = f.read(1 << 20)
                f.seek(-(1 << 20), 2)
                return hashlib.sha1(head + f.read()).hexdigest()
        write(0xAB00000000000001)
        db = os.path.join(d, 'refs.sqlite')
        r1 = U.scan_references(saves, os.path.join(d, 'Tray'), db, workers=1)
        self.assertEqual(r1.ids(U.PART), {0xAB00000000000001})
        size, before = os.path.getsize(path), ends()
        write(0xAB00000000000002)
        self.assertEqual((os.path.getsize(path), ends()), (size, before))      # first and last MiB unchanged
        r2 = U.scan_references(saves, os.path.join(d, 'Tray'), db, workers=1)
        self.assertEqual(r2.stats['parsed'], 1)
        self.assertEqual(r2.ids(U.PART), {0xAB00000000000002})

    def test_missing_cc_by_household(self):
        p = self.plan()
        self.assertEqual(set(p.absent['cas']), {CC_ABSENT, CC_ABSENT2})
        by_name = {g['household']: g for g in p.households}
        self.assertEqual(by_name['Lee Family']['missing_parts'], ['%016X' % CC_ABSENT])
        self.assertEqual(by_name['Lee Family']['sims'], {'Ann Lee': 1})
        self.assertEqual(by_name['Tray Family']['missing_parts'], ['%016X' % CC_ABSENT2])
        # CC_DEEP is installed (just too deep to load): not "installed nowhere" but "unloadable"
        self.assertNotIn(CC_DEEP, p.absent['cas'])
        self.assertEqual(p.unloadable['cas'], [CC_DEEP])

    # -------------------------------------------------------------- build / verify / stale
    def test_build_verify_stale_and_undo(self):
        refs = self.refs()
        p = self.plan(refs)
        out = os.path.join(self.sims, 'SpeedKit', 'usedpack')
        limit = 600                                                # fake resources compress to a few dozen bytes
        dry = U.build(p, out, max_package_bytes=limit, sims=self.sims, check_game=False)
        self.assertGreater(len(dry), 1)
        self.assertFalse(os.path.exists(out))                      # a dry run writes nothing
        res = U.build(p, out, max_package_bytes=limit, dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual([os.path.basename(r['path']) for r in res], [U.PACK_NAME % (n + 1) for n in range(len(dry))])
        # every resource bit-exact from the chosen copy, catalog types first, each package within the limit
        order = []
        for r in res:
            with Package(r['path']) as pk:
                self.assertTrue(os.path.getsize(r['path']) <= limit or len(pk.entries) == 1)
                for e in pk.entries:
                    it = p.items[(e.t, e.g, e.i)]
                    src = os.path.join(self.sims, p.packages[it.pkg]['root'], p.packages[it.pkg]['rel'])
                    with Package(src) as sp:
                        se = [x for x in sp.entries if (x.t, x.g, x.i) == (e.t, e.g, e.i)][0]
                        self.assertEqual(pk.raw(e), sp.raw(se))
                        self.assertEqual((e.fsize, e.msize, e.comp), (se.fsize, se.msize, se.comp))
                    order.append(e.t)
        self.assertEqual(len(order), len(p.items))
        ranks = [U.TYPE_RANK.get(t, 7 if t in U.BULK_TYPES else 6) for t in order]
        self.assertEqual(ranks, sorted(ranks))
        self.assertEqual(order[0], U.T_CASP)
        man = U.read_manifest(out)
        self.assertEqual(man['bytes'], p.total_bytes())
        self.assertEqual({s['name'] for s in man['saves_and_tray']}, {'Slot_00000001.save',
                                                                     '0x00000000!0x0000000000000abc.householdbinary'})
        self.assertTrue(os.path.exists(os.path.join(out, U.KEYS_FILE)))
        # verify: complete (absent and too-deep ids are known), and those show when asked
        absent = {'%016X' % v for v in (CC_ABSENT, CC_ABSENT2, CC_DEEP, THRIFT_TONE, THRIFT_SCULPT)}
        self.assertEqual(U.verify(out, refs, game=self.game), [])
        self.assertEqual({v for c, v in U.verify(out, refs, game=self.game, include_absent=True)}, absent)
        self.assertEqual(U.verify(out, refs, game=self.game, lib=self.lib), [])
        self.assertEqual({v for c, v in U.verify(out, refs, game=self.game, lib=self.lib, include_absent=True)}, absent)
        self.assertFalse(U.is_stale(out, self.saves, self.tray))
        # a new save wearing CC that is not in the pack: stale, and verify names it
        extra = os.path.join(self.saves, 'Slot_00000009.save')
        write_save(extra, savegame([], [sim_data(0x5301, 0, b'Cy', b'New', [0xF00000000000000F])]), [])
        try:
            self.assertTrue(U.is_stale(out, self.saves, self.tray))
            self.assertEqual(U.verify(out, self.refs(), game=self.game), [(U.PART, '%016X' % 0xF00000000000000F)])
        finally:
            os.remove(extra)
            self.refs()
        # a rebuild replaces the files through the journal; undoing it restores the first build
        first = {r['path']: read_bytes(r['path']) for r in res}
        res2 = U.build(p, out, dry_run=False, sims=self.sims, check_game=False)      # one package this time
        self.assertEqual(len(res2), 1)
        self.assertEqual(sorted(n for n in os.listdir(out) if n.endswith('.package')), [U.PACK_NAME % 1])
        undo(res2[0]['journal'], home=os.path.join(self.sims, 'SpeedKit'), check_game=False)
        self.assertEqual({r: read_bytes(r) for r in first}, first)
        undo(res[0]['journal'], home=os.path.join(self.sims, 'SpeedKit'), check_game=False)
        self.assertFalse([n for n in os.listdir(out) if n.endswith('.package')])
        self.assertFalse(os.listdir(os.path.join(self.sims, 'SpeedKit', 'staging')))

    def test_verify_with_library_catches_a_missing_override_of_an_ea_id(self):
        refs = self.refs()
        p = self.plan(refs)
        del p.items[(U.T_CASP, 0, EA_OVERRIDE)]          # a pack without the library's copy of EA part 0x1235
        out = os.path.join(self.sims, 'SpeedKit', 'no_override')
        U.build(p, out, dry_run=False, sims=self.sims, check_game=False)
        self.assertEqual(U.verify(out, refs, game=self.game), [])        # small id: invisible without the library
        self.assertEqual(U.verify(out, refs, game=self.game, lib=self.lib), [(U.PART, '%016X' % EA_OVERRIDE)])

    def test_build_refuses_without_disk_space(self):
        p = self.plan()
        old = U.FREE_MARGIN
        U.FREE_MARGIN = 1 << 62
        try:
            with self.assertRaises(OSError):
                U.build(p, os.path.join(self.sims, 'SpeedKit', 'nospace'), dry_run=False, sims=self.sims,
                        check_game=False)
            self.assertFalse(os.path.exists(os.path.join(self.sims, 'SpeedKit', 'nospace')))
        finally:
            U.FREE_MARGIN = old

    def test_build_refuses_outside_sims_and_changed_sources(self):
        p = self.plan()
        with self.assertRaises(ValueError):
            U.build(p, os.path.join(self.root, 'elsewhere'), dry_run=False, sims=self.sims, check_game=False)
        # a source package that changed after the plan
        src = os.path.join(self.sims, 'Mods', 'cc', 'object.package')
        st = os.stat(src)
        os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        try:
            with self.assertRaises(U.PlanStale):
                U.build(p, os.path.join(self.sims, 'SpeedKit', 'u2'), dry_run=False, sims=self.sims, check_game=False)
            self.assertFalse(os.path.exists(os.path.join(self.sims, 'SpeedKit', 'u2')))
        finally:
            os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns))

    def test_plan_finds_package_moved_to_other_root(self):
        p = self.plan()
        a = os.path.join(self.sims, 'Mods_parked', 'cc', 'A_first.package')
        b = os.path.join(self.sims, 'Mods', 'cc', 'A_first.package')
        os.rename(a, b)                         # the other tool un-parks it after the library scan
        try:
            p2 = self.plan()
            self.assertEqual(set(p2.items), set(p.items))
            out = os.path.join(self.sims, 'SpeedKit', 'moved')
            U.build(p2, out, dry_run=False, sims=self.sims, check_game=False)
            self.assertEqual(U.verify(out, self.refs(), game=self.game), [])
        finally:
            os.rename(b, a)


class RealSaveCopies(unittest.TestCase):
    """Scanner on copies of real saves/Tray (E:\\speedkit_test\\usedpack\\fake_sims), checked against the
    research scan of the same save (research/usedcc/ids.sqlite)."""
    FAKE = os.path.join(BASE, 'fake_sims')
    IDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'research', 'usedcc', 'ids.sqlite')

    @unittest.skipUnless(os.path.exists(os.path.join(BASE, 'fake_sims', 'saves', 'Slot_00000018.save'))
                         and os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                                                         'research', 'usedcc', 'ids.sqlite')), 'no real save copies')
    def test_matches_research_scan(self):
        db = os.path.join(tempfile.mkdtemp(dir=BASE, prefix='real_'), 'refs.sqlite')
        try:
            r = U.scan_references(os.path.join(self.FAKE, 'saves'), os.path.join(self.FAKE, 'Tray'), db, workers=2)
            self.assertFalse(r.stats['errors'])
            fp = [s.fp for s in r.sources if s.name == 'Slot_00000018.save'][0]
            mine = r.by_fp[fp]
            ids = sqlite3.connect(self.IDS)
            sid = ids.execute("select id from src where file like '%Slot_00000018.save'").fetchone()[0]
            theirs = {}
            for cat, v in ids.execute('select cat, v from typed where src=?', (sid,)):
                theirs.setdefault(cat, set()).add(v & (2 ** 64 - 1))
            ids.close()
            self.assertFalse((theirs['outfit_part'] | theirs['genetic_part']) - mine[U.PART])
            self.assertEqual(theirs['object_guid'], mine[U.OBJECT])
            self.assertFalse(theirs['skin_tone'] - mine[U.TONE])
            names = {s.name for s in r.sim_list()}
            self.assertGreater(len(names), 100)
        finally:
            shutil.rmtree(os.path.dirname(db), ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=1)

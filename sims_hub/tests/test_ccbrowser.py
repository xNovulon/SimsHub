"""The CC browser (speedkit/ccbrowser.py and its speedkit/api.py functions) on a fake Sims 4 folder made of synthetic
packages (dbpf.PackageWriter): categories from CAS part body types and object catalog data, pictures (PNG, JPEG, EA's
alpha-in-JPEG) made once and cached, filters and pages, duplicates and damaged files, "used by my saves", the CC one
save uses per sim with the missing CC, and setting files aside + undo. Cross-platform: everything lives in a temporary
folder; the real Sims 4 folder and the real game are never touched."""
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from speedkit import api, ccbrowser as CB, gamepath as G, usedpack as U  # noqa: E402
from speedkit.dbpf import PackageWriter  # noqa: E402

try:
    from PIL import Image
except ImportError:          # pragma: no cover - the Hub's engine needs Pillow for pictures
    Image = None

INSIDE_WORDS = ('package', 'quarantine', 'journal', 'profile', 'CASP')


# ------------------------------------------------------------------ protobuf bits for fake saves (as test_usedpack)
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


def sim_data(sim_id, hh_id, first, last, parts):
    outfits = fb(1, fv(1, 777) + fv(2, 0) + fb(5, fb(1, b''.join(struct.pack('<Q', p) for p in parts))))
    return f64(1, sim_id) + f64(4, hh_id) + fb(5, first) + fb(6, last) + fb(21, outfits)


def savegame(name, active, households, sims):
    slot = f64(1, 1) + fb(9, name.encode()) + fv(11, active)
    out = fv(1, 99) + fb(2, slot)
    for hid, hname in households:
        out += fb(5, f64(2, hid) + fb(3, hname))
    return out + b''.join(fb(6, s) for s in sims)


def write_save(path, sg, object_guids=()):
    objs = b''.join(fb(1, f64(1, 1000 + n) + fv(30, g)) for n, g in enumerate(object_guids))
    with PackageWriter(path) as w:
        w.add((0x0D, 0, 1), sg)
        w.add((0x06, 0, 100), f64(1, 55) + fb(3, objs))


# ------------------------------------------------------------------ fake CC
def casp(name, body_type, version=46):
    """A CAS part with the header layout ccbrowser.casp_info reads (TS4SimRipper's CASP.cs)."""
    b = bytearray(struct.pack('<III', version, 0, 0))
    nm = name.encode('utf-16-be')
    b += bytes([len(nm)]) + nm
    b += struct.pack('<fHII', 1.0, 0, 0, 0) + b'\x00'
    if version >= 39:
        b += b'\x00'
    if version >= 50:
        b += b'\x00\x00'
    if version >= 51:
        b += struct.pack('<i', 1) + struct.pack('<Q', 0)
    else:
        b += b'\x00' * 8 + (b'\x00' * 8 if version >= 41 else b'')
    b += b'\x00' * (8 if version > 36 else 4)
    b += struct.pack('<i', 2) + (struct.pack('<HI', 0x41, 7) * 2 if version >= 37 else struct.pack('<HH', 0x41, 7) * 2)
    b += struct.pack('<III', 0, 0, 0) + (b'\x00' * 4 if version >= 0x2B else b'') + b'\x00'
    b += struct.pack('<III', body_type, 0, 0x2078)
    b += b'\x00' * 24
    struct.pack_into('<I', b, 4, len(b) - 8)
    return bytes(b + b'\x00')


def png(color=(220, 60, 140, 255), size=(104, 148)):
    img = Image.new('RGBA', size, color)
    for x in range(size[0] // 3):
        for y in range(size[1] // 3):
            img.putpixel((x, y), (255, 255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()


def jpeg(color=(40, 120, 220), size=(96, 96)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'JPEG', quality=90)
    return buf.getvalue()


def alpha_jpeg(color=(40, 200, 90), size=(96, 96)):
    """EA's alpha-in-JPEG thumbnail: a JFIF JPEG with an APP0 'ALFA' segment holding a grayscale PNG mask (left half
    see-through, right half solid) right after the JFIF segment, so 'ALFA' sits at byte 0x18."""
    base = jpeg(color, size)
    assert base[2:4] == b'\xff\xe0' and base[6:11] == b'JFIF\x00'
    end = 4 + int.from_bytes(base[4:6], 'big')
    mask = Image.new('L', size, 255)
    for x in range(size[0] // 2):
        for y in range(size[1]):
            mask.putpixel((x, y), 0)
    mb = io.BytesIO()
    mask.save(mb, 'PNG')
    m = mb.getvalue()
    seg = b'\xff\xe0' + (2 + 4 + 4 + len(m)).to_bytes(2, 'big') + b'ALFA' + len(m).to_bytes(4, 'big') + m
    return base[:end] + seg + base[end:]


HAIR, HAIR_2, DRESS, TOP, SOFA, ABSENT, SET_ASIDE_PART = (0xA1000000000000A1, 0xA1000000000000A2, 0xA2000000000000D1,
                                                         0xA3000000000000C1, 0xB1000000000000F1, 0xDEAD00000000BEEF,
                                                         0xC0FFEE00000000A1)
TUNING_T = 0x03B33DDF


def pkg(path, resources):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        for key, data in resources:
            w.add(key, data)


def make_world(root):
    """A fake Sims 4 folder: Mods with sorted CC, a save that uses some of it, the game's thumbnail cache."""
    sims = os.path.join(root, 'The Sims 4')
    mods = os.path.join(sims, 'Mods')
    pkg(os.path.join(mods, 'Hair', 'Simstrouble_Braids.package'),
        [((U.T_CASP, 0, HAIR), casp('yfHair_Braids', 2)), ((U.T_CASP, 0, HAIR_2), casp('yfHair_Braids_2', 2)),
         ((U.T_THUM, 2, HAIR), png())])
    pkg(os.path.join(mods, 'Clothes', '[Sentate] Venus Dress.package'),
        [((U.T_CASP, 0, DRESS), casp('yfBody_Venus', 5, version=51)), ((U.T_THUM, 0x102, DRESS), alpha_jpeg())])
    pkg(os.path.join(mods, 'Clothes', 'NoPicture_Top.package'), [((U.T_CASP, 0, TOP), casp('ymTop_Tee', 6, 42))])
    pkg(os.path.join(mods, 'BuildBuy', 'Peacemaker - Sofa.package'),
        [((U.T_OBJD, 0, SOFA), b'objd' * 20), ((U.T_COBJ, 0, SOFA), b'cobj' * 20),
         ((U.T_OTHM, 0, SOFA), png((90, 90, 200, 255), (128, 128)))])
    pkg(os.path.join(mods, 'Hair', 'Copy of braids.package'),
        [((U.T_CASP, 0, HAIR), casp('yfHair_Braids', 2)), ((U.T_CASP, 0, HAIR_2), casp('yfHair_Braids_2', 2))])
    pkg(os.path.join(mods, 'Gameplay', 'Better_Autonomy.package'), [((TUNING_T, 0, 0x1234), b'<I n="x"/>' * 10)])
    with open(os.path.join(mods, 'broken.package'), 'wb') as f:
        f.write(b'DBPF' + b'\x02\x00\x00\x00' + os.urandom(40))
    os.makedirs(os.path.join(mods, 'Scripts'))
    with open(os.path.join(mods, 'Scripts', 'mc_cmd_center.ts4script'), 'wb') as f:
        f.write(b'PK\x03\x04' + b'\x00' * 40)
    # the game's own picture cache knows the top (and the part that is missing everywhere)
    pkg(os.path.join(sims, 'localthumbcache.package'),
        [((U.T_THUM, 1, TOP), png((250, 200, 40, 255))), ((U.T_THUM, 1, ABSENT), png((30, 30, 30, 255)))])
    # a save: Ann wears the hair, the dress and a part that is installed nowhere; a lot has the sofa
    ann = sim_data(0x5101, 0x7001, b'Ann', b'Lee', [HAIR, DRESS, ABSENT, SET_ASIDE_PART, 0x1234])
    bo = sim_data(0x5102, 0x7002, b'Bo', b'Nu', [HAIR])
    os.makedirs(os.path.join(sims, 'saves'))
    write_save(os.path.join(sims, 'saves', 'Slot_00000001.save'),
               savegame('Lee Story', 0x7001, [(0x7001, b'Lee Family'), (0x7002, b'Nu Family')], [ann, bo]),
               object_guids=[SOFA, 0x42])
    # a CC file set aside earlier: its name can be told for the part the save misses
    pkg(os.path.join(sims, 'SpeedKit', 'quarantine', '20260901-101010-dedup', 'Mods', 'Old', 'Trillyke_Earrings.package'),
        [((U.T_CASP, 0, SET_ASIDE_PART), casp('yfAcc_Earrings', 10))])
    os.makedirs(os.path.join(sims, 'Tray'))
    return sims


NO_GAME = G.Clues(processes=lambda: [], shortcuts=lambda: [], resolve=lambda paths: [], registry=lambda: [],
                  steam=lambda: None, drives=lambda: [])


def assert_plain(test, text):
    for w in INSIDE_WORDS:
        test.assertNotRegex(text or '', r'(?i)(?<![\w.])%s(?!\w)' % w, text)


# ------------------------------------------------------------------ a merged file
class MergedFile(unittest.TestCase):
    """A merged file (Sims 4 Studio's merge list inside) that is mostly outfits but also holds floors and walls: it is
    marked Merged, counts what it holds, and is listed under each of its categories."""

    def test_merged_file_is_marked_and_counts_its_build_items(self):
        from speedkit import library as L
        d = tempfile.mkdtemp(prefix='sk_merged_')
        try:
            mods = os.path.join(d, 'Mods')
            parts = [((U.T_CASP, 0, 0xE1000000000000A0 + k), casp('yfBody_Set%d' % k, 5)) for k in range(8)]
            build = [((U.T_CFLR, 0, 0xF1000000000000B0 + k), b'cflr' * 8) for k in range(2)]
            build += [((U.T_CWAL, 0, 0xF2000000000000C0 + k), b'cwal' * 8) for k in range(3)]
            pkg(os.path.join(mods, 'Everyday merge.package'), parts + build + [((0x7FB6AD8A, 0, 1), b'merge list')])
            pkg(os.path.join(mods, 'Plain dress.package'), [((U.T_CASP, 0, DRESS), casp('yfBody_Venus', 5))])
            lib = L.Library(os.path.join(d, 'library.sqlite'), roots={'Mods': mods})
            try:
                lib.scan()
                by = {os.path.basename(p.rel): p for p in lib.packages()}
                m = CB.classify(lib, by['Everyday merge.package'])
                plain = CB.classify(lib, by['Plain dress.package'])
            finally:
                lib.close()
            self.assertTrue(m['merged'])
            self.assertEqual((m['walls'], m['floors'], m['fences']), (3, 2, 0))
            self.assertEqual(m['category'], 'fullbody')                 # mostly outfits
            self.assertIn('walls', m['cats'])                          # and listed under Walls & floors too
            self.assertFalse(plain['merged'])
            self.assertEqual((plain['walls'], plain['floors']), (0, 0))
            # what the Hub shows: the flag and counts reach the details and the cards
            view = api._cc_view({'id': 1, 'name': 'Everyday merge.package', 'rel': 'Everyday merge.package', 'folder': '',
                                 'creator': None, 'kind': 'package', 'category': 'fullbody', 'cats': 'fullbody,walls',
                                 'body': 'Full outfit', 'part_name': None, 'size': 1000, 'mtime': 0, 'n_cas': 4,
                                 'n_obj': 0, 'thumb': '', 'root': 'Mods', 'used': None, 'used_by': None,
                                 'broken': None, 'dup_of': None,
                                 'extra': json.dumps({'merged': True, 'walls': 3, 'floors': 2})})
            self.assertEqual((view['merged'], view['walls'], view['floors'], view['fences']), (True, 3, 2, 0))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_merged_animation_pack_is_listed_under_poses_and_animations(self):
        from speedkit import library as L
        d = tempfile.mkdtemp(prefix='sk_anims_')
        try:
            mods = os.path.join(d, 'Mods')
            clips = [((CB.T_CLIP, 0, 0xC1000000000000D0 + k), b'clip' * 16) for k in range(30)]
            extra = [((U.T_OBJD, 0, 0xB2000000000000E1), b'objd' * 20),                        # a prop
                     ((U.T_CASP, 0, 0xE3000000000000F1), casp('yfBody_Robe', 5)),               # an outfit for it
                     ((TUNING_T, 0, 0x5678), b'<I n="anim"/>' * 10), ((0x7FB6AD8A, 0, 1), b'merge list')]
            pkg(os.path.join(mods, 'WW_Animations_merged.package'), clips + extra)
            lib = L.Library(os.path.join(d, 'library.sqlite'), roots={'Mods': mods})
            try:
                lib.scan()
                info = CB.classify(lib, lib.packages()[0])
            finally:
                lib.close()
            self.assertEqual(info['category'], 'poses')
            self.assertTrue(info['merged'])
            self.assertIn('buildbuy', info['cats'])          # the prop still counts, second
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_an_old_index_gets_the_new_column(self):
        import sqlite3
        d = tempfile.mkdtemp(prefix='sk_oldidx_')
        try:
            path = os.path.join(d, 'ccbrowser.sqlite')
            old = sqlite3.connect(path)
            old.execute('create table item(id integer primary key, kind text, root text, rel text, relkey text unique, '
                        'name text, folder text, creator text, size integer, mtime real, category text, cats text, '
                        'body text, part_name text, n_res integer, n_cas integer, n_obj integer, thumb text, '
                        'broken text, dup_of text, used integer, used_by text, version integer)')
            old.commit()
            old.close()
            idx = CB.CCIndex(path)
            try:
                cols = {r[1] for r in idx.db.execute('pragma table_info(item)')}
            finally:
                idx.close()
            self.assertIn('extra', cols)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ unit parts
@unittest.skipIf(Image is None, 'Pillow is not installed')
class Pictures(unittest.TestCase):
    def test_png(self):
        img = CB.decode_image(png())
        self.assertEqual(img.size, (104, 148))
        self.assertEqual(img.mode, 'RGBA')

    def test_plain_jpeg(self):
        img = CB.decode_image(jpeg())
        self.assertEqual(img.getpixel((10, 10))[3], 255)

    def test_alpha_jpeg(self):
        data = alpha_jpeg()
        self.assertEqual(data[0x18:0x1C], b'ALFA')
        img = CB.decode_image(data)
        self.assertEqual(img.size, (96, 96))
        self.assertLess(img.getpixel((5, 50))[3], 10)          # left half see-through
        self.assertGreater(img.getpixel((90, 50))[3], 245)     # right half solid
        r, g, b, _ = img.getpixel((90, 50))
        self.assertGreater(g, 150)                             # the colour came from the JPEG

    def test_alpha_jpeg_with_a_bad_segment_length(self):
        data = bytearray(alpha_jpeg())
        data[0x16:0x18] = b'\x00\x08'                          # a writer that did not count the PNG
        img = CB.decode_image(bytes(data))
        self.assertLess(img.getpixel((5, 50))[3], 10)

    def test_not_a_picture(self):
        with self.assertRaises(ValueError):
            CB.decode_image(b'\x00\x01garbage' * 10)
        with self.assertRaises(ValueError):
            CB.decode_image(b'')

    def test_make_thumb_scales_down(self):
        blob, ctype = CB.make_thumb(png(size=(900, 600)))
        self.assertIn(ctype, ('image/webp', 'image/png'))
        img = Image.open(io.BytesIO(blob))
        self.assertLessEqual(max(img.size), CB.THUMB_SIZE)


class CasParts(unittest.TestCase):
    def test_versions(self):
        for v in (27, 37, 42, 43, 46, 49, 50, 51):
            info = CB.casp_info(casp('yfHair_Test', 2, v))
            self.assertEqual(info['body_type'], 2, v)
            self.assertEqual(info['name'], 'yfHair_Test')

    def test_body_types(self):
        self.assertEqual(CB.body_category(2), ('hair', 'Hair'))
        self.assertEqual(CB.body_category(8), ('shoes', 'Shoes'))
        self.assertEqual(CB.body_category(29), ('makeup', 'Lipstick'))
        self.assertEqual(CB.body_category(45)[0], 'skin')
        self.assertEqual(CB.body_category(300)[0], 'cas_other')
        self.assertEqual(CB.body_category(None)[0], 'cas_other')

    def test_old_and_broken(self):
        self.assertIsNone(CB.casp_info(casp('x', 6, 18))['body_type'])     # version 18: layout not known
        self.assertIsNone(CB.casp_info(b'\x2e\x00\x00\x00'))
        self.assertIsNone(CB.casp_info(casp('x', 6, 46)[:30]))


class Creators(unittest.TestCase):
    def test_guess(self):
        self.assertEqual(CB.guess_creator('[Sentate] Venus Dress.package'), 'Sentate')
        self.assertEqual(CB.guess_creator('Simstrouble_Braids.package'), 'Simstrouble')
        self.assertEqual(CB.guess_creator('Peacemaker - Sofa.package'), 'Peacemaker')
        self.assertEqual(CB.guess_creator('SimpliciatyHair_Long.package'), 'SimpliciatyHair')
        self.assertIsNone(CB.guess_creator('hair_01.package'))
        self.assertIsNone(CB.guess_creator('yf_top.package'))
        self.assertIsNone(CB.guess_creator('broken.package'))


# ------------------------------------------------------------------ duplicates among merged files
P = [0xE100000000000000 + n for n in range(1, 9)]


@unittest.skipIf(Image is None, 'Pillow is not installed')
class MergedDuplicates(unittest.TestCase):
    """Merges that share some of the same CC are not duplicates; a file is only marked when one other file holds all
    of it with the same content, and never both of two identical files."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='ccdup_')
        sims = os.path.join(self.root, 'The Sims 4')
        mods, parked = os.path.join(sims, 'Mods'), os.path.join(sims, 'Mods_parked')
        part = lambda n, v=46: ((U.T_CASP, 0, P[n]), casp('yfTop_Part%d' % n, 6, v))
        pkg(os.path.join(mods, 'merge_A.package'), [part(0), part(1), part(2)])
        pkg(os.path.join(mods, 'merge_B.package'), [part(2), part(3), part(4)])       # shares part 2 with A
        pkg(os.path.join(mods, 'X.package'), [part(2)])                                 # the shared mod on its own
        pkg(os.path.join(parked, 'old_merge.package'), [part(0), part(1)])             # all of it is in A
        pkg(os.path.join(mods, 'spread.package'), [part(0), part(3)])                  # half in A, half in B
        pkg(os.path.join(mods, 'other_version.package'), [part(3), part(4, 50)])       # part 4 is another version
        pkg(os.path.join(mods, 'twin_1.package'), [part(5), part(6)])
        pkg(os.path.join(mods, 'twin_2.package'), [part(5), part(6)])                  # the same file twice
        pkg(os.path.join(mods, 'with_tuning.package'), [part(0), ((TUNING_T, 0, 0x77), b'<I n="t"/>' * 8)])
        pkg(os.path.join(mods, 'ScriptMod', 'companion.package'), [part(1)])           # beside a script mod
        with open(os.path.join(mods, 'ScriptMod', 'mod.ts4script'), 'wb') as f:
            f.write(b'PK' + bytes([3, 4]) + bytes(40))
        self.data = os.path.join(self.root, 'data')
        api.configure(sims=sims, db_path=os.path.join(self.data, 'library.sqlite'),
                      refs_db=os.path.join(self.data, 'refs.sqlite'), game_ids_db=os.path.join(self.data, 'ids.sqlite'),
                      check_game=False, game_clues=NO_GAME, remember_game=False, opener=lambda *a: None,
                      companions_cache=os.path.join(self.data, 'comp.json'))
        api._CC_PICS.clear()
        r = api.cc_scan()
        self.assertTrue(r['ok'], r)

    def tearDown(self):
        api.reset()
        api._CC_PICS.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_merges(self):
        dup = {i['name']: i['duplicate_of'] for i in api.cc_list(flag='duplicate', limit=200)['items']}
        self.assertNotIn('merge_A.package', dup)
        self.assertNotIn('merge_B.package', dup)                 # merges that share a mod are both needed
        self.assertNotIn('spread.package', dup)                  # no single file holds all of it
        self.assertNotIn('other_version.package', dup)           # same part, different content
        self.assertNotIn('with_tuning.package', dup)             # its tuning is nowhere else
        self.assertNotIn('companion.package', dup)               # a script mod's own package stays
        self.assertIn(dup.get('X.package'), ('merge_A.package', 'merge_B.package'))
        self.assertEqual(dup.get('old_merge.package'), 'merge_A.package')
        self.assertEqual(len({'twin_1.package', 'twin_2.package'} & set(dup)), 1)
        # removing every marked file keeps every part somewhere
        names = {'merge_A.package': [0, 1, 2], 'merge_B.package': [2, 3, 4], 'X.package': [2], 'old_merge.package': [0, 1],
                 'spread.package': [0, 3], 'other_version.package': [3, 4], 'twin_1.package': [5, 6], 'twin_2.package': [5, 6]}
        kept = set().union(*(set(v) for k, v in names.items() if k not in dup))
        self.assertEqual(kept, set(range(7)))
        for name, of in dup.items():
            self.assertNotIn(of, dup)                            # it names a file that stays


# ------------------------------------------------------------------ the engine on a fake Sims 4 folder
@unittest.skipIf(Image is None, 'Pillow is not installed')
class Browser(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='ccbrowser_')
        self.sims = make_world(self.root)
        self.data = os.path.join(self.root, 'data')
        self.opened = []
        api.configure(sims=self.sims, db_path=os.path.join(self.data, 'library.sqlite'),
                      refs_db=os.path.join(self.data, 'refs.sqlite'), game_ids_db=os.path.join(self.data, 'ids.sqlite'),
                      check_game=False, game_clues=NO_GAME, remember_game=False, opener=self.opened.append,
                      companions_cache=os.path.join(self.data, 'comp.json'))
        api._CC_PICS.clear()
        r = api.cc_scan()
        self.assertTrue(r['ok'], r)

    def tearDown(self):
        api.reset()
        api._CC_PICS.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def items(self, **kw):
        kw.setdefault('limit', 200)
        r = api.cc_list(**kw)
        self.assertTrue(r['ok'], r)
        return {i['name']: i for i in r['items']}

    def item(self, name):
        return self.items()[name]

    # ---------------------------------------------------------------- sorting into categories
    def test_categories(self):
        it = self.items()
        self.assertEqual(it['Simstrouble_Braids.package']['category'], 'hair')
        self.assertEqual(it['Simstrouble_Braids.package']['part_name'], 'yfHair_Braids')
        self.assertEqual(it['Simstrouble_Braids.package']['body'], 'Hair')
        self.assertEqual(it['Simstrouble_Braids.package']['creator'], 'Simstrouble')
        self.assertEqual(it['Simstrouble_Braids.package']['folder'], 'Hair')
        self.assertEqual(it['[Sentate] Venus Dress.package']['category'], 'fullbody')
        self.assertEqual(it['[Sentate] Venus Dress.package']['category_label'], 'Full outfits')
        self.assertEqual(it['NoPicture_Top.package']['category'], 'top')
        self.assertEqual(it['Peacemaker - Sofa.package']['category'], 'buildbuy')
        self.assertEqual(it['Better_Autonomy.package']['category'], 'gameplay')
        self.assertEqual(it['mc_cmd_center.ts4script']['category'], 'script')
        self.assertEqual(it['mc_cmd_center.ts4script']['kind'], 'script')
        self.assertTrue(it['broken.package']['broken'])
        self.assertIsNone(it['Simstrouble_Braids.package']['broken'])
        assert_plain(self, it['broken.package']['broken'])

    def test_category_counts_and_filters(self):
        r = api.cc_list(limit=200, facets=True)
        cats = {c['key']: c['n'] for c in r['categories']}
        self.assertEqual(cats['hair'], 2)
        self.assertEqual(cats['buildbuy'], 1)
        self.assertEqual(cats['script'], 1)
        self.assertEqual(r['total'], 8)
        self.assertEqual(set(self.items(category='hair')), {'Simstrouble_Braids.package', 'Copy of braids.package'})
        self.assertEqual(set(self.items(q='venus')), {'[Sentate] Venus Dress.package'})
        self.assertEqual(set(self.items(q='sentate dress')), {'[Sentate] Venus Dress.package'})
        self.assertEqual(set(self.items(q='yfhair_braids')), {'Simstrouble_Braids.package', 'Copy of braids.package'})
        self.assertEqual(set(self.items(folder='Clothes')), {'[Sentate] Venus Dress.package', 'NoPicture_Top.package'})
        self.assertEqual(set(self.items(folder='(root)')), {'broken.package'})
        self.assertEqual(set(self.items(creator='Peacemaker')), {'Peacemaker - Sofa.package'})
        self.assertIn({'name': 'Hair', 'n': 2}, r['folders'])
        self.assertEqual(set(self.items(q='100%_nothing')), set())
        # a search that is also SQL wildcards finds nothing by accident
        self.assertEqual(set(self.items(q='_')), set(self.items(q='_')) & set(self.items()))

    def test_used_by_saves(self):
        self.assertTrue(api.cc_list()['index']['used_known'])
        used = self.items(used='used')
        self.assertIn('Simstrouble_Braids.package', used)
        self.assertIn('[Sentate] Venus Dress.package', used)
        self.assertIn('Peacemaker - Sofa.package', used)
        self.assertEqual(used['Simstrouble_Braids.package']['used_by'], ['Lee Story'])
        unused = self.items(used='unused')
        self.assertIn('NoPicture_Top.package', unused)
        self.assertNotIn('mc_cmd_center.ts4script', unused)        # script mods are never called unused
        self.assertNotIn('Better_Autonomy.package', unused)
        self.assertIsNone(self.item('mc_cmd_center.ts4script')['used'])

    def test_duplicates_and_broken(self):
        dup = self.items(flag='duplicate')
        # the copy is marked, the file it copies is not (removing every marked file never loses a part)
        self.assertEqual(set(dup), {'Copy of braids.package'})
        self.assertEqual(dup['Copy of braids.package']['duplicate_of'], 'Simstrouble_Braids.package')
        self.assertEqual(set(self.items(flag='broken')), {'broken.package'})
        r = api.cc_list()
        self.assertEqual(r['flags']['duplicate'], 1)
        self.assertEqual(r['flags']['broken'], 1)

    def test_pages(self):
        seen, offset = [], 0
        while True:
            r = api.cc_list(limit=3, offset=offset, sort='name')
            seen += [i['id'] for i in r['items']]
            offset += 3
            if offset >= r['total']:
                break
        self.assertEqual(len(seen), 8)
        self.assertEqual(len(set(seen)), 8)
        names = [i['name'].lower() for i in api.cc_list(limit=200, sort='name')['items']]
        self.assertEqual(names, sorted(names))
        sizes = [i['size_mb'] for i in api.cc_list(limit=200, sort='biggest')['items']]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(api.cc_list(limit=100000)['limit'], CB.MAX_LIMIT)

    def test_rescan_reads_only_changes(self):
        ids = {n: i['id'] for n, i in self.items().items()}
        r = api.cc_scan()
        self.assertEqual(r['read'], 0)
        # a file moved to the set-aside folder by a mode switch keeps its row (and its id)
        src = os.path.join(self.sims, 'Mods', 'Clothes', 'NoPicture_Top.package')
        dst = os.path.join(self.sims, 'Mods_parked', 'Clothes', 'NoPicture_Top.package')
        os.makedirs(os.path.dirname(dst))
        os.replace(src, dst)
        r = api.cc_scan()
        self.assertEqual(r['read'], 0)
        top = self.item('NoPicture_Top.package')
        self.assertEqual(top['id'], ids['NoPicture_Top.package'])
        self.assertFalse(top['in_mods'])
        # a changed file is read again
        pkg(os.path.join(self.sims, 'Mods', 'Hair', 'Simstrouble_Braids.package'),
            [((U.T_CASP, 0, HAIR), casp('yfShoes_Now', 8)), ((U.T_THUM, 2, HAIR), png())])
        r = api.cc_scan()
        self.assertEqual(r['read'], 1)
        self.assertEqual(self.item('Simstrouble_Braids.package')['category'], 'shoes')
        # a removed file leaves the list
        os.remove(os.path.join(self.sims, 'Mods', 'broken.package'))
        api.cc_scan()
        self.assertNotIn('broken.package', self.items())

    # ---------------------------------------------------------------- pictures
    def picture(self, name):
        it = self.item(name)
        return it, api.cc_picture(item_id=it['id'])

    def test_pictures_are_made_and_cached(self):
        it, r = self.picture('Simstrouble_Braids.package')
        self.assertTrue(it['pic'])
        self.assertTrue(r['ok'], r)
        img = Image.open(io.BytesIO(r['data']))
        self.assertLessEqual(max(img.size), CB.THUMB_SIZE)
        cached = [os.path.join(dp, n) for dp, dn, fn in os.walk(os.path.join(self.data, 'ccthumbs')) for n in fn]
        self.assertEqual(len(cached), 1)
        # the second time the package is not opened at all
        with mock.patch.object(CB, 'read_resource', side_effect=AssertionError('read again')):
            again = api.cc_picture(item_id=it['id'])
        self.assertEqual(again['data'], r['data'])
        # the cache is outside the game's folders
        self.assertFalse(cached[0].startswith(self.sims))

    def test_alpha_jpeg_thumbnail_keeps_transparency(self):
        _, r = self.picture('[Sentate] Venus Dress.package')
        self.assertTrue(r['ok'], r)
        img = Image.open(io.BytesIO(r['data'])).convert('RGBA')
        w, h = img.size
        self.assertLess(img.getpixel((2, h // 2))[3], 20)
        self.assertGreater(img.getpixel((w - 3, h // 2))[3], 235)

    def test_a_copy_without_a_picture_borrows_the_parts_thumbnail(self):
        it, r = self.picture('Copy of braids.package')
        self.assertTrue(r['ok'], r)

    def test_object_picture(self):
        _, r = self.picture('Peacemaker - Sofa.package')
        self.assertTrue(r['ok'], r)

    def test_picture_from_the_games_cache(self):
        it, r = self.picture('NoPicture_Top.package')
        self.assertTrue(it['pic'])
        self.assertTrue(r['ok'], r)
        img = Image.open(io.BytesIO(r['data'])).convert('RGBA')
        self.assertGreater(img.getpixel((img.width - 2, img.height - 2))[0], 200)     # the cache's yellow

    def test_no_picture(self):
        it = self.item('Better_Autonomy.package')
        self.assertIsNone(it['pic'])
        self.assertFalse(api.cc_picture(item_id=it['id'])['ok'])
        self.assertFalse(api.cc_picture(item_id=self.item('broken.package')['id'])['ok'])
        self.assertFalse(api.cc_picture(item_id=999999)['ok'])

    def test_changed_file_gets_a_new_picture(self):
        it, r = self.picture('Simstrouble_Braids.package')
        pkg(os.path.join(self.sims, 'Mods', 'Hair', 'Simstrouble_Braids.package'),
            [((U.T_CASP, 0, HAIR), casp('yfHair_Braids', 2)), ((U.T_THUM, 2, HAIR), png((10, 200, 10, 255)))])
        later = time.time() + 5
        os.utime(os.path.join(self.sims, 'Mods', 'Hair', 'Simstrouble_Braids.package'), (later, later))
        api.cc_scan()
        it2, r2 = self.picture('Simstrouble_Braids.package')
        self.assertNotEqual(it['pic'], it2['pic'])
        self.assertNotEqual(r['data'], r2['data'])

    def test_part_pictures(self):
        r = api.cc_picture(kind='cas', instance='%016X' % HAIR)
        self.assertTrue(r['ok'])
        r = api.cc_picture(kind='cas', instance='%016X' % ABSENT)          # only the game's cache has it
        self.assertTrue(r['ok'])
        self.assertFalse(api.cc_picture(kind='cas', instance='%016X' % 0x77)['ok'])
        self.assertFalse(api.cc_picture(kind='cas', instance='not hex')['ok'])

    # ---------------------------------------------------------------- one save's CC
    def test_save_cc(self):
        r = api.save_cc('Slot_00000001')
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['name'], 'Lee Story')
        files = {f['name']: f for f in r['files']}
        self.assertIn('Simstrouble_Braids.package', files)
        self.assertIn('[Sentate] Venus Dress.package', files)
        self.assertIn('Peacemaker - Sofa.package', files)
        # the hair is in two files: sims are credited to the copy the game loads first ('COPY OF...' < 'SIMS...')
        self.assertEqual(files['Copy of braids.package']['sims'], ['Ann Lee', 'Bo Nu'])
        self.assertEqual(files['Simstrouble_Braids.package']['sims'], [])
        self.assertEqual(files['Peacemaker - Sofa.package']['objects'], 1)
        self.assertEqual(files['Simstrouble_Braids.package']['pic'], {'kind': 'cas', 'id': '%016X' % HAIR})
        self.assertEqual(files['Simstrouble_Braids.package']['item']['category'], 'hair')
        # per household and sim; the played household first
        self.assertEqual(r['households'][0]['name'], 'Lee Family')
        self.assertTrue(r['households'][0]['played'])
        ann = r['households'][0]['sims'][0]
        self.assertEqual(ann['name'], 'Ann Lee')
        self.assertEqual(ann['missing'], 2)
        self.assertEqual({r['files'][n]['name'] for n in ann['files']},
                         {'Copy of braids.package', '[Sentate] Venus Dress.package'})
        # missing CC: only ids ... unless a copy is found in the safe copies
        miss = {m['id']: m for m in r['missing']}
        self.assertEqual(set(miss), {'%016X' % ABSENT, '%016X' % SET_ASIDE_PART})      # 0x1234 counts as EA's
        absent = miss['%016X' % ABSENT]
        self.assertEqual(absent['key'], '034AEECB:00000000:%016X' % ABSENT)
        self.assertEqual(absent['sims'], ['Ann Lee'])
        self.assertEqual(absent['found'], [])
        found = miss['%016X' % SET_ASIDE_PART]['found']
        self.assertEqual(found[0]['name'], 'Trillyke_Earrings.package')
        self.assertEqual(found[0]['place'], 'safe copies')
        self.assertEqual(found[0]['creator'], 'Trillyke')
        self.assertEqual(r['counts']['missing'], 2)
        self.assertEqual(r['counts']['objects'], 1)
        # the missing part's picture still exists in the game's cache
        self.assertTrue(api.cc_picture(kind='cas', instance=absent['id'])['ok'])
        json.dumps(r)

    def test_save_cc_unknown(self):
        self.assertFalse(api.save_cc('Slot_000000FF')['ok'])
        self.assertFalse(api.save_cc('../../etc')['ok'])
        r = api.save_cc('tray')
        self.assertFalse(r['ok'])
        assert_plain(self, r['message'])

    # ---------------------------------------------------------------- set aside + undo
    def test_set_aside_and_undo(self):
        top = self.item('NoPicture_Top.package')
        path = os.path.join(self.sims, 'Mods', 'Clothes', 'NoPicture_Top.package')
        r = api.cc_set_aside([top['id']])
        self.assertTrue(r['ok'], r)
        assert_plain(self, r['message'])
        self.assertEqual(r['done'], ['NoPicture_Top.package'])
        self.assertFalse(os.path.exists(path))
        kept = [os.path.join(dp, n) for dp, dn, fn in os.walk(os.path.join(self.sims, 'SpeedKit', 'quarantine', r['journal']))
                for n in fn]
        self.assertEqual([os.path.basename(k) for k in kept], ['NoPicture_Top.package'])
        self.assertNotIn('NoPicture_Top.package', self.items())
        st = api.status()
        j = next(j for j in st['journals'] if j['id'] == r['journal'])
        self.assertEqual(j['kind'], 'setaside')
        self.assertEqual(j['title'], 'Set CC files aside')
        self.assertTrue(j['next_undo'])
        u = api.undo_last()
        self.assertTrue(u['ok'], u)
        self.assertTrue(os.path.exists(path))
        api.cc_scan()
        self.assertIn('NoPicture_Top.package', self.items())

    def test_set_aside_refusals(self):
        it = self.items()
        r = api.cc_set_aside([it['mc_cmd_center.ts4script']['id']])
        self.assertFalse(r['ok'])
        self.assertIn('Script mods', r['message'])
        self.assertTrue(os.path.exists(os.path.join(self.sims, 'Mods', 'Scripts', 'mc_cmd_center.ts4script')))
        self.assertFalse(api.cc_set_aside([])['ok'])
        self.assertFalse(api.cc_set_aside(['x'])['ok'])
        self.assertFalse(api.cc_set_aside([424242])['ok'])
        # a file that changed since the last look stays
        p = os.path.join(self.sims, 'Mods', 'Gameplay', 'Better_Autonomy.package')
        later = time.time() + 7
        os.utime(p, (later, later))
        r = api.cc_set_aside([it['Better_Autonomy.package']['id']])
        self.assertFalse(r['ok'])
        self.assertTrue(os.path.exists(p))
        # nothing changes while the game runs
        with mock.patch.object(api, '_game_running', return_value=True):
            r = api.cc_set_aside([it['Peacemaker - Sofa.package']['id']])
        self.assertFalse(r['ok'])
        self.assertIn('running', r['message'])
        self.assertTrue(os.path.exists(os.path.join(self.sims, 'Mods', 'BuildBuy', 'Peacemaker - Sofa.package')))

    def test_open_folder(self):
        it = self.item('Peacemaker - Sofa.package')
        r = api.cc_open(it['id'])
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.opened, [os.path.join(self.sims, 'Mods', 'BuildBuy')])
        self.assertFalse(api.cc_open(987654)['ok'])

    def test_item_details(self):
        it = self.item('Simstrouble_Braids.package')
        d = api.cc_item(it['id'])
        self.assertTrue(d['ok'])
        self.assertEqual(d['path'], os.path.join(self.sims, 'Mods', 'Hair', 'Simstrouble_Braids.package'))
        self.assertEqual(d['cas_parts'], 2)


@unittest.skipIf(Image is None, 'Pillow is not installed')
class BigLibrary(unittest.TestCase):
    """Thousands of small files: the first look, an unchanged second look and filtered pages stay quick."""

    def test_many_files(self):
        root = tempfile.mkdtemp(prefix='ccbig_')
        try:
            sims = os.path.join(root, 'The Sims 4')
            mods = os.path.join(sims, 'Mods')
            n = 1500
            for k in range(n):
                bt = (2, 6, 7, 8, 29)[k % 5]
                pkg(os.path.join(mods, 'Creator%d' % (k % 30), 'Creator%d_item_%04d.package' % (k % 30, k)),
                    [((U.T_CASP, 0, 0xA000000000000000 + k), casp('part%d' % k, bt))])
            os.makedirs(os.path.join(sims, 'saves'))
            data = os.path.join(root, 'data')
            api.configure(sims=sims, db_path=os.path.join(data, 'library.sqlite'), refs_db=os.path.join(data, 'r.sqlite'),
                          check_game=False, game_clues=NO_GAME, remember_game=False)
            t0 = time.time()
            r = api.cc_scan()
            first = time.time() - t0
            self.assertTrue(r['ok'], r)
            self.assertEqual(r['items'], n)
            t0 = time.time()
            self.assertEqual(api.cc_scan()['read'], 0)
            second = time.time() - t0
            t0 = time.time()
            page = api.cc_list(category='hair', q='item', offset=120, limit=60, facets=True)
            query = time.time() - t0
            self.assertEqual(page['total'], n // 5)
            self.assertEqual(len(page['items']), 60)
            self.assertLess(query, 1.0)
            self.assertLess(second, first)
            print('\n  %d files: first look %.1fs, again %.1fs, one filtered page %.0f ms' % (n, first, second,
                                                                                            query * 1000))
        finally:
            api.reset()
            shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()

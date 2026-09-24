"""CC that may need a Sims 4 Studio batch fix (speedkit/batchfix.py, api_care.batch_fixes / batch_fix_scan / batch_fix_open):
every detector on synthetic packages written with dbpf.PackageWriter (a case that must be found and cases that must
not), the results store (incremental, moved and removed files, SpeedKit's own packs), and the API end to end on a
fake Sims 4 folder - including that no CC file is ever changed. Cross-platform (temp folders)."""
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api, batchfix as BF, library as L  # noqa: E402
from speedkit.dbpf import PackageWriter  # noqa: E402
from tests import care_fakes as CF  # noqa: E402
from tests.batchfix_fakes import casp, hotc, package, T_CASP, T_HOTC, T_OBJD, CC_ID, EA_ID  # noqa: E402

ALL_AGES = 0x307E          # toddler to elder, both genders: "all ages" before infants
WITH_INFANT = 0x30FE       # the same plus infants (S4S's own value for eyes)
TEEN_UP = 0x3078
CHILD_ONLY = 0x3004


def fixes_of(tmp, *resources, name='x.package', compress=True):
    """The fix ids check_package finds in one package made of these resources."""
    path = os.path.join(tmp, name)
    with PackageWriter(path) as w:
        for k, (t, i, data) in enumerate(resources):
            w.add((t, k, i), data, compress=compress)
    from speedkit.dbpf import Package
    with Package(path) as p:
        rows = [(e.t, e.i, e.off, e.fsize, e.msize, e.comp) for e in p.entries if e.t in (T_CASP, T_HOTC)]
    return BF.check_package(path, rows)


class Detectors(unittest.TestCase):
    def setUp(self):
        self.tmp = CF.make_sims('bf_det_')[0]
        self.addCleanup(CF.cleanup, self.tmp)

    def found(self, *res, **kw):
        return sorted(fixes_of(self.tmp, *res, **kw))

    # -------------------------------------------------------------------------------- sliders (werewolf patch)
    def test_sliders(self):
        self.assertEqual(self.found((T_HOTC, CC_ID, hotc(0x0E))), ['sliders_werewolf'])
        self.assertEqual(self.found((T_HOTC, CC_ID, hotc(0x0C))), ['sliders_werewolf'])
        self.assertEqual(self.found((T_HOTC, CC_ID, hotc(0x0F))), [])
        self.assertEqual(self.found((T_HOTC, CC_ID, hotc(0x10))), [])
        # counts: 1 of 2 sliders, with the old format number
        hit = fixes_of(self.tmp, (T_HOTC, 1 << 40, hotc(0x0E)), (T_HOTC, 2 << 40, hotc(0x0F)))['sliders_werewolf']
        self.assertEqual((hit['parts'], hit['total'], hit['versions']), (1, 2, [14]))
        self.assertIn('1 of 2 sliders use the format from before the June 2022 game update', BF.why('sliders_werewolf', hit))

    # -------------------------------------------------------------------------------- eye colors (infants patch)
    def test_eyes_for_infants(self):
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=35, age_gender=ALL_AGES))), ['eyes_infants'])
        self.assertEqual(self.found((T_CASP, EA_ID, casp(body_type=35, age_gender=ALL_AGES))), ['eyes_infants'])  # default replacement too
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=35, age_gender=WITH_INFANT))), [])
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=35, age_gender=TEEN_UP))), [])       # not for little ones
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=34, age_gender=ALL_AGES))), [])      # eyebrows

    # -------------------------------------------------------------------------------- shoes (werewolves)
    def test_shoes_for_werewolves(self):
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP, occult=0))), ['shoes_werewolves'])
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP, occult=0x02))),
                         ['shoes_werewolves'])                                          # off for aliens only
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP, occult=0x20))), [])
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP, occult=0xFFFFFFFE))), [])
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=8, age_gender=CHILD_ONLY))), [])     # no child werewolves
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP, species=2))), [])  # dog shoes
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=6, age_gender=TEEN_UP))), [])        # a top
        # a part from before the occult field existed can't be turned off for werewolves (and needs the pets fix)
        self.assertEqual(self.found((T_CASP, CC_ID, casp(version=0x1E, body_type=8, age_gender=TEEN_UP))),
                         ['pets_patch', 'shoes_werewolves'])

    # -------------------------------------------------------------------------------- default garment (nude outfit)
    def test_default_garment(self):
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=6, flags=0x01))), ['nude_default'])
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=7, flags2=0x04))), ['nude_default'])  # female
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=5, flags2=0x02))), ['nude_default'])  # male
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=6, flags=0x7E, flags2=0x01))), [])    # other flags
        self.assertEqual(self.found((T_CASP, EA_ID, casp(body_type=6, flags=0x01))), [])   # replaces EA's own default
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=2, flags=0x01))), [])   # hair is not clothing
        # before version 39 there is no second flags byte: the byte after the flags is not read as one
        self.assertEqual(self.found((T_CASP, CC_ID, casp(version=0x25, body_type=6, flags=0x00))), [])

    # -------------------------------------------------------------------------------- old CAS parts (pets patch)
    def test_pets_patch(self):
        for v in (0x12, 0x1B, 0x1C, 0x1F):
            self.assertIn('pets_patch', self.found((T_CASP, CC_ID, casp(version=v, body_type=6))), hex(v))
        for v in (0x20, 0x25, 0x2E, 0x33, 0x34):
            self.assertEqual(self.found((T_CASP, CC_ID, casp(version=v, body_type=6))), [], hex(v))
        hit = fixes_of(self.tmp, (T_CASP, 1 << 40, casp(version=0x1B)), (T_CASP, 2 << 40, casp(version=0x1B)))
        self.assertEqual(hit['pets_patch']['versions'], [27])
        self.assertIn('All 2 Create a Sim items were made before the Cats & Dogs update', BF.why('pets_patch', hit['pets_patch']))

    # -------------------------------------------------------------------------------- reading
    def test_every_layout_reads_the_same_fields(self):
        """The skipped fields change with the version; the fields read must still be the right ones."""
        for v in range(0x1B, 0x35):
            for materials in (True, False):
                info = BF.casp_fields(casp(version=v, body_type=8, age_gender=TEEN_UP, species=1, occult=0x21,
                                           flags=0x41, flags2=0x06, ntags=5, colors=3, materials=materials))
                self.assertEqual((info['flags'], info['body_type'], info['age_gender']), (0x41, 8, TEEN_UP), hex(v))
                self.assertEqual(info['flags2'], 0x06 if v >= 39 else 0, hex(v))
                self.assertEqual(info['occult'], 0x21 if v >= 31 else None, hex(v))

    def test_stored_uncompressed_and_other_resources(self):
        self.assertEqual(self.found((T_CASP, CC_ID, casp(body_type=35, age_gender=ALL_AGES)),
                                    (T_OBJD, CC_ID, b'\0' * 200), compress=False), ['eyes_infants'])
        self.assertEqual(self.found((T_OBJD, CC_ID, b'\0' * 200)), [])

    def test_damaged_parts_are_skipped(self):
        self.assertEqual(self.found((T_CASP, CC_ID, b'\x2e\x00\x00\x00' + b'\xff' * 40),
                                    (T_CASP, CC_ID + 1, b'short')), [])
        self.assertIsNone(BF.casp_fields(b'tiny'))

    def test_menu_paths(self):
        for fx in BF.FIXES:
            self.assertEqual(fx['menu'][:4], ['Tools', 'Content Management', 'Batch Fixes', 'CAS'])
            self.assertEqual(fx['menu'][-1], fx['name'])
            self.assertTrue(fx['sources'])


class StoreScan(unittest.TestCase):
    def setUp(self):
        self.root, self.sims = CF.make_sims('bf_store_')
        self.addCleanup(CF.cleanup, self.root)
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.lib = L.Library(os.path.join(self.root, 'lib.sqlite'), roots={'Mods': self.mods, 'Mods_parked': self.parked})
        self.store = BF.Store(os.path.join(self.root, 'bf.sqlite'))
        self.addCleanup(self.lib.close)
        self.addCleanup(self.store.close)

    def scan(self, **kw):
        self.lib.scan()
        return self.store.scan(self.lib, **kw)

    def test_incremental(self):
        package(os.path.join(self.mods, 'Sliders', 'nose.package'), [(T_HOTC, CC_ID, hotc(0x0E))])
        package(os.path.join(self.mods, 'Eyes', 'eyes.package'), [(T_CASP, CC_ID, casp(body_type=35, age_gender=ALL_AGES))])
        package(os.path.join(self.mods, 'fine.package'), [(T_CASP, CC_ID, casp(body_type=6))])
        package(os.path.join(self.parked, 'Old', 'old.package'), [(T_CASP, CC_ID, casp(version=0x1B))])
        r = self.scan()
        self.assertEqual((r['files'], r['read']), (4, 4))
        f = self.store.findings()
        self.assertEqual(sorted(f), ['eyes_infants', 'pets_patch', 'sliders_werewolf'])
        self.assertEqual(f['pets_patch'][0]['root'], 'Mods_parked')
        self.assertEqual(self.scan()['read'], 0)                      # nothing new: nothing read
        # a changed file is read again; a removed one is dropped
        package(os.path.join(self.mods, 'Sliders', 'nose.package'), [(T_HOTC, CC_ID, hotc(0x0F))])
        os.remove(os.path.join(self.mods, 'Eyes', 'eyes.package'))
        r = self.scan()
        self.assertEqual((r['read'], r['removed']), (1, 1))
        self.assertEqual(sorted(self.store.findings()), ['pets_patch'])
        self.assertTrue(self.store.state()['scanned'])

    def test_skip_and_both_roots(self):
        package(os.path.join(self.mods, 'SpeedKit_FastPack_001.package'), [(T_CASP, CC_ID, casp(version=0x1B))])
        package(os.path.join(self.mods, 'A', 'shoes.package'), [(T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP))])
        package(os.path.join(self.parked, 'A', 'shoes.package'), [(T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP))])
        self.scan(skip=lambda rel: rel.startswith('SpeedKit_'))
        f = self.store.findings()
        self.assertEqual(list(f), ['shoes_werewolves'])
        self.assertEqual([(x['root'], x['rel']) for x in f['shoes_werewolves']], [('Mods', 'A/shoes.package')])


class ThroughTheApi(unittest.TestCase):
    def setUp(self):
        self.root, self.sims = CF.make_sims('bf_api_')
        self.addCleanup(CF.cleanup, self.root)
        self.addCleanup(api.reset)
        self.opened = []
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'data', 'library.sqlite'), check_game=False,
                      opener=self.opened.append, game=None)
        m = os.path.join(self.sims, 'Mods')
        self.files = {
            'Sliders/nose.package': [(T_HOTC, CC_ID, hotc(0x0E))],
            'Shoes/boots.package': [(T_CASP, CC_ID, casp(body_type=8, age_gender=TEEN_UP)),
                                    (T_CASP, CC_ID + 1, casp(body_type=8, age_gender=TEEN_UP, occult=0x20))],
            'Tops/tank.package': [(T_CASP, CC_ID, casp(body_type=6, flags=0x01))],
            'fine.package': [(T_CASP, CC_ID, casp(body_type=6)), (T_HOTC, CC_ID, hotc(0x0F))],
        }
        for rel, res in self.files.items():
            package(os.path.join(m, rel.replace('/', os.sep)), res)

    def digest(self):
        out = {}
        for dp, _, fn in os.walk(self.sims):
            for n in fn:
                if n.endswith('.package'):
                    with open(os.path.join(dp, n), 'rb') as f:
                        out[os.path.relpath(os.path.join(dp, n), self.sims)] = hashlib.sha256(f.read()).hexdigest()
        return out

    def test_end_to_end(self):
        r = api.batch_fixes()
        self.assertTrue(r['ok'])
        self.assertIsNone(r['scanned'])
        self.assertIsNone(api.patch_day()['batch_fixes'])
        before = self.digest()
        progress = []
        s = api.batch_fix_scan(progress=lambda *a: progress.append(a))
        self.assertTrue(s['ok'], s)
        self.assertEqual((s['files'], s['found']), (4, 3))
        self.assertEqual(self.digest(), before)                       # no CC file was changed
        self.assertTrue(progress)
        r = api.batch_fixes()
        self.assertEqual([f['id'] for f in r['fixes']], ['sliders_werewolf', 'shoes_werewolves', 'nude_default'])
        shoes = r['fixes'][1]
        self.assertEqual(shoes['menu'], ['Tools', 'Content Management', 'Batch Fixes', 'CAS', 'Disable Shoes for Werewolves'])
        self.assertEqual(shoes['files'][0]['why'], '1 of 2 shoe items are not turned off for werewolves.')
        self.assertEqual((shoes['files'][0]['in_mods'], shoes['files'][0]['set_aside']), (True, False))
        self.assertIn('3 CC files may need a Sims 4 Studio batch fix', r['message'])
        for word in ('package', 'CASP', 'quarantine', 'journal'):
            self.assertNotIn(word, r['message'])
            self.assertNotIn(word, ' '.join(f['why'] for fx in r['fixes'] for f in fx['files']))
        pd = api.patch_day()['batch_fixes']
        self.assertEqual(pd['files'], 3)
        self.assertEqual([f['id'] for f in pd['fixes']], ['sliders_werewolf', 'shoes_werewolves', 'nude_default'])
        # open the folder of a listed file only
        o = api.batch_fix_open('Tops/tank.package')
        self.assertTrue(o['ok'], o)
        self.assertEqual(self.opened, [os.path.join(self.sims, 'Mods', 'Tops')])
        self.assertFalse(api.batch_fix_open('fine.package')['ok'])
        self.assertFalse(api.batch_fix_open('../x.package')['ok'])
        # set aside until fixed (the existing undoable change), then undo
        a = api.set_aside(['Tops/tank.package'], why='fix')
        self.assertTrue(a['ok'], a)
        self.assertTrue(os.path.isfile(os.path.join(self.sims, 'Mods_parked', 'Tops', 'tank.package')))
        nude = next(f for f in api.batch_fixes()['fixes'] if f['id'] == 'nude_default')
        self.assertEqual((nude['set_aside'], nude['files'][0]['root']), (1, 'Mods_parked'))
        self.assertEqual(api.patch_day()['batch_fixes']['files'], 2)
        st = api.status()
        self.assertEqual(st['journals'][0]['title'], 'Set CC aside until it gets a Sims 4 Studio fix')
        u = api.undo_last()
        self.assertTrue(u['ok'], u)
        self.assertTrue(os.path.isfile(os.path.join(self.sims, 'Mods', 'Tops', 'tank.package')))
        nude = next(f for f in api.batch_fixes()['fixes'] if f['id'] == 'nude_default')
        self.assertEqual((nude['set_aside'], nude['in_mods']), (0, 1))
        # a file that was fixed (by Sims 4 Studio) drops out after the next check
        package(os.path.join(self.sims, 'Mods', 'Sliders', 'nose.package'), [(T_HOTC, CC_ID, hotc(0x0F))])
        s = api.batch_fix_scan()
        self.assertEqual((s['read'], s['found']), (1, 2))
        # a file deleted by hand is not listed even before the next check
        os.remove(os.path.join(self.sims, 'Mods', 'Shoes', 'boots.package'))
        self.assertEqual([f['id'] for f in api.batch_fixes()['fixes']], ['nude_default'])


if __name__ == '__main__':
    unittest.main()

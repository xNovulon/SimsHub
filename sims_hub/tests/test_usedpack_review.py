"""Adversarial review tests for speedkit.usedpack, on fake Sims trees under E:\\speedkit_test\\usedpack_review.

Each test builds its own world with test_usedpack.make_world (a save, a Tray household, a Mods /
Mods_parked library and a fake game folder) and removes it afterwards. Covered here:
  * files SpeedKit reads can be renamed/moved by others meanwhile (the game's save rotation, the
    other tool's shutil.move of a package), and a save is not held open while it is parsed;
  * a save whose content changed after it was fingerprinted is not cached under the old fingerprint
    (and is fingerprinted afresh next time); a backup rotation (rename) is not read again, but a new
    file that only shares size and mtime with a file still in place is read;
  * HouseholdData.cas_inventory (packed in the game's schema); a half-written save makes plan() refuse;
  * load_game_ids on a missing game folder raises and keeps the cache; the cache really is reused;
  * build: the game starting during the copy, a failure while moving files (rolled back), a failed
    rollback (no manifest vouches for the half-replaced pack), a package moved to the other root
    before / while it is copied, out_dir in saves, packages over 2 GiB;
  * library oddities: a deleted entry and duplicate keys inside one package, a RefPack CASP in a
    folder with a non-ASCII name.
"""
import os, shutil, sqlite3, struct, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from speedkit.dbpf import Entry, Package, PackageWriter, REFPACK, DELETED
from speedkit.library import Library
from speedkit import journal as J
from speedkit import usedpack as U
import test_usedpack as T

BASE = r'E:\speedkit_test\usedpack_review'


def refpack_literal(data):
    """data as a RefPack stream made only of literal runs (valid for the game's decoder)."""
    out = bytearray([0x10, 0xFB]) + len(data).to_bytes(3, 'big')
    p, n = 0, len(data)
    while n - p >= 4:
        k = min(112, (n - p) // 4 * 4)
        out.append(0xE0 + (k - 4) // 4)
        out += data[p:p + k]
        p += k
    out.append(0xFC + (n - p))
    out += data[p:]
    return bytes(out)


def patch_entry(path, n, i=None, comp=None):
    """Overwrite the instance and/or compression of index entry n of a PackageWriter package."""
    with open(path, 'r+b') as f:
        head = f.read(96)
        pos = struct.unpack_from('<I', head, 64)[0] or struct.unpack_from('<I', head, 40)[0]
        base = pos + 4 + 32 * n
        if i is not None:
            f.seek(base + 8)
            f.write(struct.pack('<II', i >> 32, i & 0xFFFFFFFF))
        if comp is not None:
            f.seek(base + 28)
            f.write(struct.pack('<H', comp))


def snapshot(d):
    """{name: bytes} of every file in folder d."""
    return {n: T.read_bytes(os.path.join(d, n)) for n in sorted(os.listdir(d))} if os.path.isdir(d) else {}


RUN = r'''
import os, shutil, sys
op, a, b = sys.argv[1:4]
try:
    (os.rename if op == 'rename' else shutil.move)(a, b)
    print('OK')
except OSError as e:
    print('FAILED', e)
'''


def other_process(op, a, b):
    """Rename/move a to b from another process (like the game or the other tool would)."""
    return subprocess.run([sys.executable, '-c', RUN, op, a, b], capture_output=True, text=True).stdout.strip()


class ReviewTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(BASE, exist_ok=True)
        self.root = tempfile.mkdtemp(dir=BASE, prefix='t_')
        self.sims = T.make_world(self.root)
        self.saves, self.tray = os.path.join(self.sims, 'saves'), os.path.join(self.sims, 'Tray')
        self.mods, self.parked = os.path.join(self.sims, 'Mods'), os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.out = os.path.join(self.home, 'usedpack')
        self.lib = None
        self.game_db = os.path.join(self.root, 'game_ids.sqlite')
        self.game = U.load_game_ids(os.path.join(self.root, 'game'), self.game_db)
        self._restore = []

    def tearDown(self):
        for obj, name, value in reversed(self._restore):
            setattr(obj, name, value)
        if self.lib:
            self.lib.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def patch(self, obj, name, value):
        self._restore.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def library(self):
        if self.lib:
            self.lib.close()
        self.lib = Library(db_path=os.path.join(self.root, 'library.sqlite'),
                           roots={'Mods': self.mods, 'Mods_parked': self.parked})
        self.lib.scan()
        return self.lib

    def refs(self, **kw):
        return U.scan_references(self.saves, self.tray, os.path.join(self.root, 'refs.sqlite'), workers=1, **kw)

    def plan(self, refs=None, **kw):
        return U.plan(self.library(), refs or self.refs(), game=self.game, **kw)

    def build(self, p, **kw):
        kw.setdefault('check_game', False)
        return U.build(p, self.out, dry_run=False, sims=self.sims, **kw)

    def assert_bit_exact(self, p, results):
        n = 0
        for r in results:
            with Package(r['path']) as pk:
                for e in pk.entries:
                    it = p.items[(e.t, e.g, e.i)]
                    src = U._find_source(p.root_dirs, p.packages[it.pkg])
                    with Package(src) as sp:
                        se = [x for x in sp.entries if (x.t, x.g, x.i, x.off) == (e.t, e.g, e.i, it.off)][0]
                        self.assertEqual(pk.raw(e), sp.raw(se))
                        self.assertEqual((e.fsize, e.msize, e.comp, e.committed), (se.fsize, se.msize, se.comp, se.committed))
                    n += 1
        self.assertEqual(n, len(p.items))

    # ------------------------------------------------------------------ reading while others move files
    def test_open_read_lets_other_programs_rename_the_file(self):
        a = os.path.join(self.parked, 'cc', 'A_first.package')
        b = os.path.join(self.mods, 'cc', 'A_first.package')
        with U._open_read(a) as f:
            head = f.read(96)
            self.assertEqual(other_process('move', a, b), 'OK')         # the other tool's shutil.move
            self.assertFalse(os.path.exists(a))                         # moved, not copied to both roots
            f.seek(0)
            self.assertEqual(f.read(96), head)                          # the handle still reads the file
        with self.assertRaises(FileNotFoundError):
            U._open_read(a)

    def test_game_can_rotate_a_save_while_it_is_parsed(self):
        save = os.path.join(self.saves, 'Slot_00000001.save')
        seen = {}
        orig = U._scan_savegame

        def spy(b, prefix, ids, sims):
            if 'rotation' not in seen:           # mid-parse: the game renames Slot.save -> .ver0
                seen['rotation'] = other_process('rename', save, save + '.ver0')
            return orig(b, prefix, ids, sims)
        self.patch(U, '_scan_savegame', spy)
        res = U.scan_file(save, 'save')
        self.assertEqual(seen['rotation'], 'OK')
        self.assertIn(T.CC_A, res['ids'][U.PART])

    def test_save_changed_after_fingerprint_is_not_cached_under_it(self):
        save = os.path.join(self.saves, 'Slot_00000001.save')
        fp = U.fingerprint(save)
        st = os.stat(save)
        data = bytearray(T.read_bytes(save))
        data[-40] ^= 0xFF                                # same size, same mtime, other bytes
        with open(save, 'wb') as f:
            f.write(data)
        os.utime(save, ns=(st.st_atime_ns, st.st_mtime_ns))
        path, res, err = U._scan_job((save, 'save', fp))
        self.assertIsNone(res)
        self.assertIn('changed', err)

    def test_rotation_by_rename_takes_the_fingerprint_over_without_reading(self):
        save = os.path.join(self.saves, 'Slot_00000001.save')
        self.refs()
        reads = []
        orig = U.fingerprint
        self.patch(U, 'fingerprint', lambda path, *a, **k: reads.append(os.path.basename(path)) or orig(path, *a, **k))
        os.rename(save, save + '.ver0')                                   # the game's rotation...
        T.write_save(save, T.savegame([], [T.sim_data(0x5701, 0, b'New', b'Save', [T.CC_B])]), [])   # ...and new save
        r = self.refs(include_backups=True)
        self.assertEqual(reads, ['Slot_00000001.save'])                  # .ver0 was not read
        self.assertEqual(r.stats['parsed'], 1)
        self.assertIn(T.CC_A, r.ids(U.PART, True))                        # the backup still counts

    def test_new_file_sharing_size_and_mtime_with_one_still_there_is_read(self):
        a = os.path.join(self.tray, '0x00000000!0x0000000000000aaa.householdbinary')
        b = os.path.join(self.tray, '0x00000000!0x0000000000000bbb.householdbinary')
        T.household_binary(a, 0xAAA, b'Family A', [T.sim_data(0x5801, 0, b'A', b'A', [T.CC_A])])
        self.refs()
        T.household_binary(b, 0xBBB, b'Family B', [T.sim_data(0x5802, 0, b'B', b'B', [0xA7000000000000FF])])
        st = os.stat(a)
        self.assertEqual(os.path.getsize(b), st.st_size)
        os.utime(b, ns=(st.st_atime_ns, st.st_mtime_ns))                  # whole-second mtimes make this possible
        r = self.refs()
        self.assertIn(0xA7000000000000FF, r.ids(U.PART))
        self.assertEqual({s.household for s in r.sim_list()} >= {'Family A', 'Family B'}, True)

    def test_a_scan_error_forgets_the_fingerprint(self):
        save = os.path.join(self.saves, 'Slot_00000001.save')
        orig = U._fingerprint_bytes
        U._fingerprint_bytes = lambda content: 'no match'               # the bytes read are not the ones fingerprinted
        try:
            r = self.refs()
        finally:
            U._fingerprint_bytes = orig
        self.assertIn('Slot_00000001.save', r.stats['errors'])
        db = sqlite3.connect(os.path.join(self.root, 'refs.sqlite'))
        self.assertIsNone(db.execute('select fp from seen where path=?', (save,)).fetchone())
        db.close()
        r = self.refs()
        self.assertFalse(r.stats['errors'])
        self.assertIn(T.CC_A, r.ids(U.PART))

    # ------------------------------------------------------------------ scanning
    def test_packed_cas_inventory_is_read(self):
        unworn = 0xF00000000000000F                      # a library CASP nobody wears
        hh = T.fb(5, T.f64(2, 0x7009) + T.fb(3, b'Inventory Family') + T.packedv(17, [unworn, 0x1234]))
        T.write_save(os.path.join(self.saves, 'Slot_00000002.save'), hh, [])
        r = self.refs()
        self.assertTrue({unworn, 0x1234} <= r.ids(U.PART_OTHER))
        p = self.plan(r)
        self.assertEqual(p.items[(U.T_CASP, 0, unworn)].why, 'CASP')

    def test_half_written_save_makes_plan_refuse(self):
        save = os.path.join(self.saves, 'Slot_00000003.save')
        T.write_save(save, T.savegame([], [T.sim_data(0x5501, 0, b'Half', b'Written', [T.CC_B])]), [])
        with open(save, 'r+b') as f:
            f.truncate(os.path.getsize(save) - 60)       # the game is still writing it
        r = self.refs()
        self.assertIn('Slot_00000003.save', r.stats['errors'])
        with self.assertRaises(ValueError):
            self.plan(r)
        self.assertIn((U.T_CASP, 0, T.CC_A), self.plan(r, allow_unparsed=True).items)

    # ------------------------------------------------------------------ game ids
    def test_missing_game_folder_raises_and_keeps_the_cache(self):
        with self.assertRaises(FileNotFoundError):
            U.load_game_ids(os.path.join(self.root, 'no_such_game'), self.game_db)
        again = U.load_game_ids(os.path.join(self.root, 'game'), self.game_db)
        self.assertEqual(again.casp, {T.EA_PART, T.EA_OVERRIDE})
        self.assertEqual(again.info['built'], self.game.info['built'])

    def test_game_id_cache_is_reused_and_rebuilt_after_a_patch(self):
        db = sqlite3.connect(self.game_db)
        db.execute("insert into meta values('sentinel', 'kept')")      # a rebuild wipes meta
        db.commit()
        db.close()
        self.assertEqual(U.load_game_ids(os.path.join(self.root, 'game'), self.game_db).info.get('sentinel'), 'kept')
        delta = os.path.join(self.root, 'game', 'Delta', 'SimulationDeltaBuild0.package')
        st = os.stat(delta)
        os.utime(delta, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))  # a patch
        self.assertNotIn('sentinel', U.load_game_ids(os.path.join(self.root, 'game'), self.game_db).info)

    # ------------------------------------------------------------------ build failures
    def first_build(self):
        p = self.plan()
        res = self.build(p, max_package_bytes=600)
        self.assertGreater(len(res), 1)
        return p, snapshot(self.out)

    def test_game_started_during_build_moves_nothing(self):
        p, before = self.first_build()
        self.patch(J, 'game_running', lambda: False)     # closed when the build starts...
        self.patch(U, 'game_running', lambda: True)      # ...running once the copy is done
        with self.assertRaises(J.JournalError):
            self.build(p, check_game=True)
        self.assertEqual(snapshot(self.out), before)
        self.assertFalse(os.listdir(os.path.join(self.home, 'staging')))
        last = J.list_journals(self.home)[-1]
        self.assertTrue(last[2].startswith('failed'))

    def test_failure_while_moving_rolls_back_to_the_previous_pack(self):
        p, before = self.first_build()
        orig = J.Journal.put_new
        calls = []

        def flaky(j, tmp, final):
            calls.append(final)
            if len(calls) == 2:
                raise OSError('simulated: disk error while moving %s' % os.path.basename(final))
            return orig(j, tmp, final)
        self.patch(J.Journal, 'put_new', flaky)
        with self.assertRaises(OSError) as cm:
            self.build(p)                                 # one package now: replaces 001, drops the rest
        self.assertTrue(any('was undone' in n for n in getattr(cm.exception, '__notes__', [])))
        self.assertEqual(snapshot(self.out), before)      # byte for byte the first build
        self.assertEqual(J.list_journals(self.home)[-1][2], 'undone')
        self.assertFalse(os.listdir(os.path.join(self.home, 'staging')))

    def test_failed_rollback_leaves_no_manifest_and_names_the_journal(self):
        p, before = self.first_build()
        refs = self.refs()
        orig = J.Journal.put_new
        calls = []

        def flaky(j, tmp, final):
            calls.append(final)
            if len(calls) == 2:
                raise OSError('simulated move failure')
            return orig(j, tmp, final)

        def broken_undo(*a, **k):
            raise J.JournalError('simulated: undo impossible right now')
        self.patch(J.Journal, 'put_new', flaky)
        self.patch(U, 'undo', broken_undo)
        with self.assertRaises(J.JournalError) as cm:
            self.build(p)
        jid = J.list_journals(self.home)[-1][0]
        self.assertIn(jid, str(cm.exception))
        # half-replaced: no manifest vouches for it
        self.assertIsNone(U.read_manifest(self.out))
        self.assertTrue(U.is_stale(self.out, self.saves, self.tray))
        with self.assertRaises(FileNotFoundError):
            U.verify(self.out, refs, game=self.game)
        J.undo(jid, home=self.home, check_game=False)    # what the error tells the user to do
        self.assertEqual(snapshot(self.out), before)

    def test_package_moved_to_the_other_root_before_it_is_copied(self):
        p = self.plan()
        b_parked = os.path.join(self.parked, 'cc', 'B_second.package')
        b_mods = os.path.join(self.mods, 'cc', 'B_second.package')
        orig = U._source_entries

        def then_move(plan_, paths):
            out = orig(plan_, paths)
            os.rename(b_parked, b_mods)                   # the other tool un-parks it mid-build
            return out
        self.patch(U, '_source_entries', then_move)
        res = self.build(p)
        self.assertTrue(os.path.exists(b_mods))
        self.assert_bit_exact(p, res)

    def test_other_tool_can_move_a_package_the_build_is_reading(self):
        p = self.plan()
        a_parked = os.path.join(self.parked, 'cc', 'A_first.package')
        a_mods = os.path.join(self.mods, 'cc', 'A_first.package')
        seen = {}

        class SpyWriter(PackageWriter):
            def add_raw(self, e, raw):
                if 'move' not in seen:                    # the first CASP comes from A_first, now held open
                    seen['move'] = other_process('move', a_parked, a_mods)
                return super().add_raw(e, raw)
        self.patch(U, 'PackageWriter', SpyWriter)
        res = self.build(p)
        self.assertEqual(seen['move'], 'OK')
        self.assertEqual((os.path.exists(a_parked), os.path.exists(a_mods)), (False, True))   # in one root only
        self.assert_bit_exact(p, res)
        self.assertEqual(U.verify(self.out, self.refs(), game=self.game, lib=self.lib), [])

    def test_verify_of_a_backup_pack_needs_backup_refs(self):
        shutil.copy2(os.path.join(self.saves, 'Slot_00000001.save'), os.path.join(self.saves, 'Slot_00000001.save.ver0'))
        refs_b = self.refs(include_backups=True)
        self.build(self.plan(refs_b, include_backups=True))
        self.assertEqual(U.verify(self.out, refs_b, game=self.game, lib=self.lib), [])
        with self.assertRaises(ValueError):                          # would silently skip the backups
            U.verify(self.out, self.refs(), game=self.game)

    def test_out_dir_in_saves_is_refused_before_any_work(self):
        p = self.plan()
        with self.assertRaises(ValueError):
            U.build(p, os.path.join(self.saves, 'pack'), dry_run=False, sims=self.sims, check_game=False)
        self.assertFalse(os.path.exists(os.path.join(self.home, 'journal')))

    def test_packages_over_2_gib_are_refused(self):
        p = self.plan()
        with self.assertRaises(ValueError):
            U.layout(p, 3_000_000_000)
        with self.assertRaises(ValueError):
            U.build(p, self.out, max_package_bytes=1 << 31)
        self.assertEqual(len(U.layout(p, U.MAX_PACKAGE_LIMIT)), 1)

    # ------------------------------------------------------------------ library oddities
    def test_deleted_entry_and_duplicate_keys_in_one_package(self):
        # loads before A_first: [0] a DELETED copy, [1] and [2] two copies of GEOM_A in the same package
        dups = os.path.join(self.parked, 'cc', '0_dups.package')
        with PackageWriter(dups) as w:
            w.add((U.T_GEOM, 0, 0x77), b'deleted copy' * 10, compress=False)
            w.add((U.T_GEOM, 0, 0x78), b'first live copy' * 10, compress=False)
            w.add((U.T_GEOM, 0, 0x79), b'second live copy' * 10, compress=False)
        for n in range(3):
            patch_entry(dups, n, i=T.GEOM_A)
        patch_entry(dups, 0, comp=DELETED)
        p = self.plan()
        it = p.items[(U.T_GEOM, 0, T.GEOM_A)]
        self.assertTrue(p.packages[it.pkg]['rel'].endswith('0_dups.package'))
        res = self.build(p)
        with Package(res[0]['path']) as pk:
            e = pk.find(U.T_GEOM, 0, T.GEOM_A)[0]
            self.assertEqual(pk.read(e), b'first live copy' * 10)
        self.assert_bit_exact(p, res)

    def test_refpack_casp_in_a_non_ascii_folder(self):
        rp_casp, rp_geom = 0xA5000000000000EE, 0xB5000000000000EE
        folder = os.path.join(self.parked, 'Ünïcødé 名前')
        os.makedirs(folder)
        data = T.casp([(U.T_GEOM, 0, rp_geom)])
        raw = refpack_literal(data)
        with PackageWriter(os.path.join(folder, 'refpack ☃.package')) as w:
            w.add_raw(Entry(U.T_CASP, 0, rp_casp, 0, len(raw), len(data), REFPACK, 1), raw)
            w.add((U.T_GEOM, 0, rp_geom), b'refpack part mesh' * 10)
        T.write_save(os.path.join(self.saves, 'Slot_00000004.save'),
                     T.savegame([], [T.sim_data(0x5601, 0, b'Ren', b'Pak', [rp_casp])]), [])
        refs = self.refs()
        p = self.plan(refs)
        self.assertIn((U.T_GEOM, 0, rp_geom), p.items)                # the RefPack CASP was read
        res = self.build(p)
        self.assert_bit_exact(p, res)
        with Package(res[0]['path']) as pk:
            self.assertEqual(pk.find(U.T_CASP, 0, rp_casp)[0].comp, REFPACK)
        self.assertEqual(U.verify(self.out, refs, game=self.game, lib=self.lib), [])
        with open(os.path.join(self.out, U.KEYS_FILE), encoding='utf-8') as f:
            self.assertIn('Ünïcødé 名前/refpack ☃.package', f.read())


if __name__ == '__main__':
    unittest.main(verbosity=1)

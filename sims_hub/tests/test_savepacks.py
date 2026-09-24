"""speedkit.savepacks ('Play this save'), the b/c plan cache and disk hygiene of speedkit.fastmode, and the 'save'
profile of speedkit.profiles - on a fake Sims 4 tree under E:\\speedkit_test\\savepacks (test_fastmode's world
plus two saves with their own slot data). Nothing under the real Sims 4 folder is touched."""
import collections
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import test_fastmode as TF  # noqa: E402
from test_fastmode import fv, f64, fb, sim_data, write_save  # noqa: E402
from speedkit.library import Library  # noqa: E402
from speedkit.game_index import GameIndex  # noqa: E402
from speedkit import usedpack as U, fastmode as F, savepacks as S, profiles as PR, journal as J  # noqa: E402

BASE = r'E:\speedkit_test\savepacks'
HOOD_WC, HOOD_OS = 0x7000000000000001, 0x7000000000000002
ZONE_HOME1, ZONE_HOME2, ZONE_OTHER = 0x5100000000000001, 0x5100000000000002, 0x5100000000000003
HH1, HH2, HH3 = 0x7001, 0x7002, 0x7003


def rich_savegame(slot_id, name, guid, active, households, sims):
    """SaveGameData with the fields savepacks reads (field numbers of the game's FileSerialization.proto)."""
    slot = f64(1, slot_id) + fb(9, name.encode()) + (fv(11, active) if active else b'')
    out = fv(1, guid) + fb(2, slot)
    out += fb(4, f64(1, HOOD_WC) + fb(3, b'Willow Creek')) + fb(4, f64(1, HOOD_OS) + fb(3, b'Oasis Springs'))
    for hid, hname, home in households:
        out += fb(5, f64(2, hid) + fb(3, hname) + f64(4, home))
    out += b''.join(fb(6, s) for s in sims)
    for zid, zname, hood in ((ZONE_HOME1, b'Pique Hearth', HOOD_WC), (ZONE_HOME2, b'Oasis Home', HOOD_OS),
                             (ZONE_OTHER, b'Park', HOOD_WC)):
        out += fb(7, f64(1, zid) + fb(2, zname) + f64(10, hood))
    return out


def make_saves(sims):
    saves = os.path.join(sims, 'saves')
    ann = sim_data(0x5101, HH1, b'Ann', b'Lee', [TF.CC_WORN, TF.EA_PART, TF.CC_ABSENT])
    write_save(os.path.join(saves, 'Slot_00000001.save'),
               rich_savegame(1, 'Lee Story', 111, HH1, [(HH1, b'Lee Family', ZONE_HOME1), (HH3, b'Townies', ZONE_OTHER)],
                             [ann]))
    bo = sim_data(0x5201, HH2, b'Bo', b'Nu', [TF.CC_NEW, TF.EA_PART])
    write_save(os.path.join(saves, 'Slot_00000002.save'),
               rich_savegame(2, 'Nu Legacy', 222, HH2, [(HH2, b'Nu Family', ZONE_HOME2)], [bo]))
    # a backup, a non-save file and the Wicked Animator's folder in saves\ - never read as saves, never touched
    shutil.copy2(os.path.join(saves, 'Slot_00000002.save'), os.path.join(saves, 'Slot_00000002.save.ver0'))
    with open(os.path.join(saves, 'notes.txt'), 'w') as f:
        f.write('not a save')
    fit = os.path.join(saves, 'FitStudio')
    os.makedirs(fit)
    for n in ('animator_projects.json', 'animator_progress.json', 'recovery.save.json'):
        with open(os.path.join(fit, n), 'w') as f:
            json.dump({'file': n}, f)


def digest_tree(d):
    out = {}
    for dp, dn, fn in os.walk(d):
        for n in fn:
            p = os.path.join(dp, n)
            st = os.stat(p)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, d)] = (st.st_size, st.st_mtime_ns, hash(f.read()))
    return out


class World(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.makedirs(BASE, exist_ok=True)
        cls.root = tempfile.mkdtemp(dir=BASE, prefix='t_')
        cls.sims, cls.has_script = TF.make_world(cls.root)
        make_saves(cls.sims)
        cls.roots = {'Mods': os.path.join(cls.sims, 'Mods'), 'Mods_parked': os.path.join(cls.sims, 'Mods_parked')}
        cls.home = os.path.join(cls.sims, 'SpeedKit')
        cls.lib = Library(db_path=os.path.join(cls.root, 'library.sqlite'), roots=cls.roots)
        cls.lib.scan()
        cls.game = U.load_game_ids(os.path.join(cls.root, 'game'), os.path.join(cls.root, 'game_ids.sqlite'))
        gi = GameIndex(os.path.join(cls.root, 'game.sqlite'), os.path.join(cls.root, 'game'))
        gi.scan()
        cls.overrides = gi.override_keys(cls.lib)
        gi.close()
        cls.cache = os.path.join(cls.root, 'companions.sqlite')
        cls.refs_db = os.path.join(cls.root, 'refs.sqlite')
        cls.bc = os.path.join(cls.root, 'bc.json.gz')
        cls.old_big = F.BIG_CAS_BYTES
        F.BIG_CAS_BYTES = 3000
        cls.saves_before = digest_tree(os.path.join(cls.sims, 'saves'))

    @classmethod
    def tearDownClass(cls):
        F.BIG_CAS_BYTES = cls.old_big
        cls.lib.close()
        shutil.rmtree(cls.root, ignore_errors=True)

    def refs(self):
        return U.scan_references(os.path.join(self.sims, 'saves'), os.path.join(self.sims, 'Tray'), self.refs_db,
                                 workers=1)

    def parked(self):
        return F.park_set(self.lib, verdicts=TF.verdicts_for(self.lib))

    def kw(self, **extra):
        kw = dict(game=self.game, overrides=self.overrides, cache_path=self.cache)
        kw.update(extra)
        return kw


class Headers(World):
    def test_read_header_and_list(self):
        h = S.read_header(os.path.join(self.sims, 'saves', 'Slot_00000001.save'))
        self.assertEqual((h['slot'], h['name'], h['household'], h['world'], h['sims'], h['lots'], h['slot_id'],
                          h['guid'], h['households']), ('Slot_00000001', 'Lee Story', 'Lee Family', 'Willow Creek',
                                                        1, 3, 1, 111, 2))
        h2 = S.read_header(os.path.join(self.sims, 'saves', 'Slot_00000002.save'))
        self.assertEqual((h2['name'], h2['household'], h2['world']), ('Nu Legacy', 'Nu Family', 'Oasis Springs'))
        slots = [x['slot'] for x in S.list_saves(os.path.join(self.sims, 'saves'))]
        self.assertEqual(sorted(slots), ['Slot_00000001', 'Slot_00000002'])     # no .ver, no txt, no FitStudio
        self.assertEqual(S.slot_name('save:Slot_0000000A.save'), 'Slot_0000000a')
        with self.assertRaises(S.SaveError):
            S.slot_name('Slot_12')
        with self.assertRaises(S.SaveError):
            S.read_header(os.path.join(self.sims, 'saves', 'notes.txt'))

    def test_unreadable_save_is_listed_with_a_problem(self):
        d = tempfile.mkdtemp(dir=self.root)
        with open(os.path.join(d, 'Slot_00000009.save'), 'wb') as f:
            f.write(b'DBPF broken')
        out = S.list_saves(d)
        self.assertEqual(out[0]['slot'], 'Slot_00000009')
        self.assertIn('error', out[0])


class Refs(World):
    def test_one_save_only_and_other_files_untouched(self):
        refs = self.refs()
        self.assertFalse(refs.stats['errors'])
        names = sorted(s.name for s in refs.sources)
        self.assertNotIn('notes.txt', names)
        self.assertFalse([n for n in names if 'animator' in n or n.endswith('.json')])
        r1 = S.save_refs(refs, 'Slot_00000001')
        self.assertEqual([s.name for s in r1.sources], ['Slot_00000001.save'])
        self.assertIn(TF.CC_WORN, r1.ids(U.PART))
        self.assertNotIn(TF.CC_NEW, r1.ids(U.PART))
        r2 = S.scan_one(os.path.join(self.sims, 'saves'), 'Slot_00000002', os.path.join(self.root, 'one.sqlite'))
        self.assertEqual([s.name for s in r2.sources], ['Slot_00000002.save'])
        self.assertIn(TF.CC_NEW, r2.ids(U.PART))
        self.assertNotIn(TF.CC_WORN, r2.ids(U.PART))
        with self.assertRaises(S.SaveError):
            S.save_refs(refs, 'Slot_00000007')
        with self.assertRaises(S.SaveError):
            S.scan_one(os.path.join(self.sims, 'saves'), 'Slot_00000007', os.path.join(self.root, 'one.sqlite'))
        self.assertEqual(digest_tree(os.path.join(self.sims, 'saves')), self.saves_before)

    def test_usage_per_save(self):
        refs = self.refs()
        use = S.save_usage(self.lib, refs, self.game, self.parked())
        self.assertEqual(set(use), {'Slot_00000001', 'Slot_00000002'})
        self.assertEqual(use['Slot_00000001']['cc_parts'], 1)            # CC_WORN (EA_PART is EA's)
        self.assertEqual(use['Slot_00000001']['cc_missing'], 1)          # CC_ABSENT is installed nowhere
        self.assertEqual({k[2] for k in use['Slot_00000001']['pack_casp']}, {TF.CC_WORN})
        self.assertEqual({k[2] for k in use['Slot_00000002']['pack_casp']}, {TF.CC_NEW})


class Plans(World):
    def test_save_pack_covers_only_its_save_and_shares_b_c(self):
        refs, parked = self.refs(), self.parked()
        fast = F.plan_pack(self.lib, refs, parked, **self.kw())
        p1 = S.plan_save_pack(self.lib, refs, 'Slot_00000001', parked, **self.kw())
        p2 = S.plan_save_pack(self.lib, refs, 'Slot_00000002', parked, **self.kw())
        casp = lambda p: {k[2] for k, it in p.items.items() if k[0] == U.T_CASP and it.part == 'a'}
        self.assertIn(TF.CC_WORN, casp(fast))
        self.assertIn(TF.CC_NEW, casp(fast))
        self.assertEqual(casp(p1), {TF.CC_WORN})
        self.assertEqual(casp(p2), {TF.CC_NEW})
        self.assertIn((U.T_GEOM, 0, TF.GEOM_WORN), p1.items)
        self.assertNotIn((U.T_GEOM, 0, TF.GEOM_NEW), p1.items)
        bc = lambda p: {k for k, it in p.items.items() if it.part in 'bc'}
        # (b)/(c) do not depend on the saves: every b/c key of the fast plan is in each save plan
        self.assertTrue(bc(fast))
        for p in (p1, p2):
            self.assertEqual({k for k in bc(fast)} - set(p.items), set())
        self.assertEqual([s['name'] for s in p1.sources], ['Slot_00000001.save'])

    def test_bc_cache_gives_the_same_plan(self):
        refs, parked = self.refs(), self.parked()
        cache = os.path.join(self.root, 'bc_same.json.gz')
        plain = F.plan_pack(self.lib, refs, parked, **self.kw())
        miss = F.plan_pack(self.lib, refs, parked, **self.kw(bc_cache=cache))
        hit = F.plan_pack(self.lib, refs, parked, game=self.game, cache_path=self.cache, bc_cache=cache,
                          overrides=set())          # a hit never needs the overrides
        self.assertEqual((miss.stats['bc_cache'], hit.stats['bc_cache'], plain.stats['bc_cache']), ('miss', 'hit', 'off'))
        for p in (miss, hit):
            self.assertEqual({k: (it.pkg, it.off, it.fsize, it.part) for k, it in p.items.items()},
                             {k: (it.pkg, it.off, it.fsize, it.part) for k, it in plain.items.items()})
        self.assertEqual(hit.stats['cas_parts'], plain.stats['cas_parts'])
        self.assertIsNotNone(F.cached_bc(self.lib, parked, self.game, cache))
        # the saves do not matter; a changed parked set or library does
        s1 = S.plan_save_pack(self.lib, refs, 'Slot_00000001', parked, **self.kw(bc_cache=cache))
        self.assertEqual(s1.stats['bc_cache'], 'hit')
        self.assertIsNone(F.cached_bc(self.lib, list(parked)[:-1], self.game, cache))
        # after a profile switch moves files between roots and the library is rescanned: still a hit
        a = os.path.join(self.roots['Mods_parked'], 'sim', 'm1.package')
        b = os.path.join(self.roots['Mods'], 'sim', 'm1.package')
        os.makedirs(os.path.dirname(b), exist_ok=True)
        os.rename(a, b)
        lib2 = Library(db_path=os.path.join(self.root, 'lib_moved.sqlite'), roots=self.roots)
        try:
            lib2.scan()
            p = F.plan_pack(lib2, refs, F.park_set(lib2, verdicts=TF.verdicts_for(lib2)), game=self.game,
                            cache_path=self.cache, bc_cache=cache, overrides=set())
            self.assertEqual(p.stats['bc_cache'], 'hit')
            self.assertEqual(set(p.items), set(plain.items))
        finally:
            lib2.close()
            os.rename(b, a)


class Hygiene(World):
    def test_prune_keeps_only_the_newest_previous_copy(self):
        refs, parked = self.refs(), self.parked()
        home = os.path.join(self.root, 'hyg_home')
        out = os.path.join(self.sims, 'SpeedKit', 'hyg_pack')
        plan = F.plan_pack(self.lib, refs, parked, **self.kw())
        jids = []
        for n in range(3):
            res = F.build_pack(plan, out, max_package_bytes=2000, dry_run=False, sims=self.sims, home=home,
                               prune=True)
            jids.append(res[0]['journal'])
            time.sleep(1.05)
        qfiles = lambda jid: [n for dp, dn, fn in os.walk(os.path.join(home, 'quarantine', jid)) for n in fn
                              if F.is_speedkit_pack(n)]
        self.assertEqual(qfiles(jids[0]), [])                      # the first build replaced nothing
        self.assertEqual(qfiles(jids[1]), [])                      # its copies (of build 1) were pruned
        self.assertTrue(qfiles(jids[2]))                           # the newest previous copy stays
        with open(os.path.join(home, 'journal', jids[1] + '.json'), encoding='utf-8') as f:
            doc = json.load(f)
        self.assertEqual(doc['state'], 'pruned')
        self.assertTrue(doc['pruned'])
        self.assertTrue(all(s.get('pruned') for s in doc['steps'] if s['op'] == 'quarantine'
                            and F.is_speedkit_pack(s['q'])))
        with self.assertRaises(J.JournalError):
            J.undo(jids[1], home=home, check_game=False)
        J.undo(jids[2], home=home, check_game=False)              # the newest one still undoes
        undone_new = os.path.join(home, 'quarantine', jids[2], '_undone_new')
        self.assertTrue([n for dp, dn, fn in os.walk(undone_new) for n in fn if F.is_speedkit_pack(n)])
        # an undo keeps the new files in _undone_new: the next build's prune treats them like any older copy
        time.sleep(1.05)
        res = F.build_pack(plan, out, max_package_bytes=2000, dry_run=False, sims=self.sims, home=home, prune=True)
        self.assertFalse([n for dp, dn, fn in os.walk(undone_new) for n in fn if F.is_speedkit_pack(n)])
        self.assertTrue(qfiles(res[0]['journal']))
        rep = F.prune_quarantine(home, dry_run=True)
        self.assertEqual(rep['pruned'], [])
        # nothing but exact SpeedKit pack names is ever deleted
        odd = os.path.join(home, 'quarantine', jids[0], 'ConfigOverride', 'GraphicsRules.sgr')
        os.makedirs(os.path.dirname(odd), exist_ok=True)
        with open(odd, 'w') as f:
            f.write('user file')
        F.prune_quarantine(home)
        self.assertTrue(os.path.exists(odd))

    def test_crashed_build_leaves_staging_that_the_next_run_removes(self):
        home = os.path.join(self.root, 'stage_home')
        # a dead build (its owner pid is gone) with an open journal
        j = J.Journal('fastpack', 'fast pack: crashed', home=home, sims=self.sims, check_game=False)
        st = os.path.join(home, 'staging', j.id)
        os.makedirs(st)
        for n in ('!!!!!SpeedKit_Fast_001.package', '!!!!!SpeedKit_Fast_002.package.writing', 'fastpack.json'):
            with open(os.path.join(st, n), 'wb') as f:
                f.write(b'x' * 1000)
        with open(os.path.join(st, F.STAGING_OWNER), 'w') as f:
            json.dump({'pid': 999999, 'started': time.time() - 100}, f)
        # a build running now (our own pid) and one with a stranger's file in it
        time.sleep(1.05)
        j2 = J.Journal('savepack', 'save pack: running', home=home, sims=self.sims, check_game=False)
        st2 = os.path.join(home, 'staging', j2.id)
        os.makedirs(st2)
        with open(os.path.join(st2, F.STAGING_OWNER), 'w') as f:
            json.dump({'pid': os.getpid(), 'started': time.time()}, f)
        with open(os.path.join(st2, '!!!!!SpeedKit_Save_00000001_001.package'), 'wb') as f:
            f.write(b'y')
        time.sleep(1.05)
        j3 = J.Journal('fastpack', 'fast pack: done', home=home, sims=self.sims, check_game=False)
        j3.close('committed')
        st3 = os.path.join(home, 'staging', j3.id)
        os.makedirs(st3)
        with open(os.path.join(st3, 'keep me.txt'), 'w') as f:
            f.write('not ours')
        with open(os.path.join(st3, 'fastpack_keys.tsv'), 'w') as f:
            f.write('k')
        rep = F.cleanup_staging(home)
        self.assertEqual(sorted(os.path.basename(r['folder']) for r in rep), sorted([j.id, j3.id]))
        self.assertFalse(os.path.exists(st))
        self.assertTrue(os.path.exists(os.path.join(st2, '!!!!!SpeedKit_Save_00000001_001.package')))
        self.assertTrue(os.path.exists(os.path.join(st3, 'keep me.txt')))
        self.assertFalse(os.path.exists(os.path.join(st3, 'fastpack_keys.tsv')))
        with open(os.path.join(home, 'journal', j.id + '.json'), encoding='utf-8') as f:
            self.assertTrue(json.load(f)['state'].startswith('failed: interrupted'))


class SaveProfile(World):
    """Switching to 'save' with the real pack tool (savepacks.PackProvider) on the fake tree."""

    def provider(self, slot):
        return S.PackProvider(slot, refs=self.refs, plan_kw=self.kw(bc_cache=self.bc, verdicts=TF.verdicts_for(self.lib)),
                              companions_cache=self.cache)

    def sw(self, profile, slot=None, fm=None):
        if fm is None and profile in ('fast', 'save'):
            fm = self.provider(slot)
        return PR.switch(profile, dry_run=False, lib=self.lib, sims=self.sims, check_game=False, fastmode=fm,
                         verdicts=TF.verdicts_for, save_slot=slot, keep=['FitStudio/', 'SpeedKit_Monitor.ts4script'])

    def mods_root_packs(self):
        return sorted(n for n in os.listdir(self.roots['Mods']) if F.is_speedkit_pack(n))

    def files(self):
        out = collections.Counter()
        for root in list(self.roots.values()) + [self.home]:
            for dp, dn, fn in os.walk(root):
                if os.path.normcase(dp).startswith(os.path.normcase(os.path.join(self.home, 'quarantine'))):
                    continue
                for n in fn:
                    if n.lower().endswith('.package') or n.lower().endswith('.ts4script'):
                        out[os.path.relpath(os.path.join(dp, n), self.sims).split(os.sep, 1)[-1].lower()
                            if not F.is_speedkit_pack(n) else n.lower()] += 1
        return out

    def test_fast_save_save_full_cycle(self):
        mods_files = lambda: {os.path.relpath(os.path.join(dp, n), self.roots['Mods']).replace(os.sep, '/')
                              for dp, dn, fn in os.walk(self.roots['Mods']) for n in fn}
        p = self.sw('fast')
        self.assertTrue(p['verified'])
        self.assertEqual(self.mods_root_packs(), ['!!!!!SpeedKit_Fast_001.package'])
        fast_mods = mods_files()
        # the first save: the fast pack goes home, this save's pack comes in; the same packages are parked
        p = self.sw('save', 'Slot_00000001')
        self.assertTrue(p['verified'])
        self.assertEqual(p['save_slot'], 'Slot_00000001')
        self.assertEqual(self.mods_root_packs(), ['!!!!!SpeedKit_Save_00000001_001.package'])
        self.assertEqual({f for f in mods_files() if not F.is_speedkit_pack(f)},
                         {f for f in fast_mods if not F.is_speedkit_pack(f)})
        self.assertTrue(os.path.exists(os.path.join(self.home, 'fastpack', '!!!!!SpeedKit_Fast_001.package')))
        st = PR.read_state(self.sims)
        self.assertEqual((st['profile'], st['save_slot'], st['save_name'], st['save_slot_id'], st['save_guid']),
                         ('save', 'Slot_00000001', 'Lee Story', 1, 111))
        self.assertEqual(os.path.normcase(st['pack_dir']),
                         os.path.normcase(os.path.join(self.home, 'savepacks', 'Slot_00000001')))
        self.assertEqual(st['save_pack'], ['!!!!!SpeedKit_Save_00000001_001.package'])
        self.assertEqual(st['installed_nowhere'], ['%016X' % TF.CC_ABSENT])      # missing in every mode
        cur = PR.current(sims=self.sims)
        self.assertEqual((cur['profile'], cur['save_slot']), ('save', 'Slot_00000001'))
        self.assertEqual(S.status('Slot_00000001', self.home)['state'], 'fresh')
        # the pack holds the first save's CC and not the second's
        keys = F.pack_keys(S.pack_dir(self.home, 'Slot_00000001'), kind=S.kind('Slot_00000001'))
        self.assertIn((U.T_CASP, 0, TF.CC_WORN), keys)
        self.assertNotIn((U.T_CASP, 0, TF.CC_NEW), keys)
        # the second save: the first save's pack goes back to its own folder
        p = self.sw('save', 'Slot_00000002')
        self.assertEqual(self.mods_root_packs(), ['!!!!!SpeedKit_Save_00000002_001.package'])
        self.assertTrue(os.path.exists(os.path.join(self.home, 'savepacks', 'Slot_00000001',
                                                    '!!!!!SpeedKit_Save_00000001_001.package')))
        self.assertEqual(PR.current(sims=self.sims)['save_slot'], 'Slot_00000002')
        self.assertEqual(p['pack']['action'], 'updated')
        # the same save again: nothing to do
        self.assertTrue(self.sw('save', 'Slot_00000002')['nothing_to_do'])
        # the save changes (the player saved): its pack is stale and gets a refresh/delta before the switch
        path = os.path.join(self.sims, 'saves', 'Slot_00000002.save')
        bo = sim_data(0x5201, HH2, b'Bo', b'Nu', [TF.CC_NEW, TF.CC_TUNED])
        write_save(path, rich_savegame(2, 'Nu Legacy', 222, HH2, [(HH2, b'Nu Family', ZONE_HOME2)], [bo]))
        self.assertEqual(S.status('Slot_00000002', self.home)['state'], 'stale')
        self.assertEqual(S.status('Slot_00000001', self.home)['state'], 'fresh')       # another save's change: no
        p = self.sw('save', 'Slot_00000002')
        self.assertEqual(S.status('Slot_00000002', self.home)['state'], 'fresh')
        self.assertIn((U.T_CASP, 0, TF.CC_TUNED), F.pack_keys(S.pack_dir(self.home, 'Slot_00000002'),
                                                              kind=S.kind('Slot_00000002')))
        # back to fast and full: every pack in its own folder, nothing lost or doubled
        self.sw('fast')
        self.assertEqual(self.mods_root_packs(), ['!!!!!SpeedKit_Fast_001.package'])
        self.sw('full')
        self.assertEqual(self.mods_root_packs(), [])
        self.assertEqual(PR.check_manifest(self.sims)['ok'], True)
        files = self.files()
        self.assertFalse([k for k, n in files.items() if n > 1], 'a file exists twice')
        for slot in ('Slot_00000001', 'Slot_00000002'):
            self.assertTrue(S.pack_names(self.home, slot))
        # FitStudio stays in Mods in every mode
        self.assertTrue(os.path.exists(os.path.join(self.roots['Mods'], 'FitStudio', 'FitStudio_anims.package')))
        self.assertEqual(digest_tree(os.path.join(self.sims, 'saves', 'FitStudio')),
                         {k[len('FitStudio') + 1:]: v for k, v in self.saves_before.items() if k.startswith('FitStudio')})

    def test_save_profile_needs_a_slot_and_a_pack_tool(self):
        with self.assertRaises(PR.ProfileError):
            PR.switch('save', dry_run=True, lib=self.lib, sims=self.sims, check_game=False)
        with self.assertRaises(PR.ProfileError):
            PR.switch('save', dry_run=True, lib=self.lib, sims=self.sims, check_game=False, save_slot='Slot_1')
        with self.assertRaises(PR.ProfileError):
            PR.switch('save', dry_run=True, lib=self.lib, sims=self.sims, check_game=False, save_slot='Slot_00000001')
        with mock.patch.object(PR, 'game_running', return_value=True):
            with self.assertRaises(PR.ProfileError) as cm:
                PR.switch('save', dry_run=False, lib=self.lib, sims=self.sims, save_slot='Slot_00000001',
                          fastmode=self.provider('Slot_00000001'))
            self.assertIn('running', str(cm.exception))

    def test_names_are_exact(self):
        self.assertEqual(PR._pack_family('!!!!!SpeedKit_Save_0000abcd_001.package'), 'save:0000abcd')
        self.assertIsNone(PR._pack_family('!!!!!SpeedKit_Save_0000abcd_001 - Copy.package'))
        self.assertIsNone(PR._pack_family('!!!!!SpeedKit_Save_00000001.package'))
        self.assertEqual(PR._pack_family('!!!!!SpeedKit_Fast_900.package'), 'fast')
        self.assertTrue(F.is_speedkit_pack('!!!!!SpeedKit_Save_FFFFFFFF_999.package'))
        self.assertFalse(F.is_speedkit_pack('!!!!!SpeedKit_Save_1_001.package'))
        self.assertEqual(S.kind('Slot_ffffffff').name(1), '!!!!!SpeedKit_Save_ffffffff_001.package')
        # the save pack sorts after the fast pack and before every ordinary name
        self.assertFalse(F.loads_before('!!!Mods/x.package', S.kind('Slot_00000001').name(1)))
        self.assertTrue(F.loads_before('!!!!!!early.package', S.kind('Slot_00000001').name(1)))


if __name__ == '__main__':
    unittest.main()

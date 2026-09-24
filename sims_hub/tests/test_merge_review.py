"""Adversarial review tests of speedkit.merge on FAKE Sims 4 trees under E:\\speedkit_test\\merge_review.

Covers what the builder's tests did not: a failure at EVERY journal step (before and after its move, with the
automatic rollback and with a simulated crash + manual undo), coexistence with the other chat's mods_switch.py
(its KEEP list, whole-folder parking, full -> lean -> Inbox -> full), stale plans caught by the after-check,
identical copies with different compression, the size cap, undo after a profile switch and after a broken
parking manifest, and Inbox edge cases (Deflate64 / encrypted / bad-CRC / bad-name zip members, nested zips,
deep zips, unicode names, a zip named .package, load-order names, a re-downloaded script's companions, disk
space, a library with no common Sims folder). Nothing under the real Sims 4 folder is written.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import test_merge as TM                                                                          # noqa: E402
from test_merge import (write, blob, rmtree, tree_digest, load_mods_switch, CASP, THUM, RLE2,    # noqa: E402
                        GEOM, TUN, SMOD)
from test_merge_inbox import tuning_xml, pkg_bytes, state, BUFF                                  # noqa: E402
from speedkit.dbpf import Package, key_of                                                        # noqa: E402
from speedkit.library import Library, SIMS as REAL_SIMS                                          # noqa: E402
from speedkit import journal as J                                                                # noqa: E402
from speedkit import merge as M                                                                  # noqa: E402
from speedkit import manifest as S4S                                                             # noqa: E402

BASE = r'E:\speedkit_test\merge_review'
TODAY = '2026-09-24'


class Tree(TM.Tree):
    """test_merge.Tree, built under E:\\speedkit_test\\merge_review."""

    def __init__(self):
        os.makedirs(BASE, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=BASE)
        self.sims = os.path.join(self.dir, 'The Sims 4')
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.cache = os.path.join(self.dir, 'hash.sqlite')
        self.kinds = {}
        self.build()
        self.lib = Library(os.path.join(self.dir, 'library.sqlite'), {'Mods': self.mods, 'Mods_parked': self.parked})
        self.lib.scan()

    def write_manifest(self, m):
        with open(os.path.join(self.parked, '_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(m, f, indent=1)


def journal_ids(home):
    d = os.path.join(home, 'journal')
    if not os.path.isdir(d):
        return set()
    return {n[:-5] for n in os.listdir(d) if n.endswith('.json') and not n.endswith(('.merge.json', '.tmp'))}


def temp_leftovers(sims):
    return [os.path.join(dp, n) for dp, dn, fn in os.walk(sims) for n in fn
            if M.TMP_SUFFIX in n or n.endswith(('.writing', '.copying'))]


def failing_journal(n, where):
    """A Journal that raises on the n-th step: before its move ('step') or after it ('done', not marked done)."""
    calls = [0]

    class FJ(J.Journal):
        def _step(self, op, **kw):
            if where == 'step':
                calls[0] += 1
                if calls[0] == n:
                    raise OSError('injected failure before step %d (%s)' % (n, op))
            return super()._step(op, **kw)

        def _done(self, step):
            if where == 'done':
                calls[0] += 1
                if calls[0] == n:
                    raise OSError('injected failure after step %d moved (%s)' % (n, step['op']))
            return super()._done(step)
    return FJ, calls


def zip_patch(path, method=None, flags=None, corrupt=None):
    """Rewrite a zip's headers in place: compression method, general-purpose flags, or flip a data byte."""
    with open(path, 'rb') as f:
        data = bytearray(f.read())
    for sig, moff, foff in ((b'PK\x03\x04', 8, 6), (b'PK\x01\x02', 10, 8)):
        i = 0
        while True:
            i = data.find(sig, i)
            if i < 0:
                break
            if method is not None:
                data[i + moff:i + moff + 2] = method.to_bytes(2, 'little')
            if flags is not None:
                data[i + foff:i + foff + 2] = flags.to_bytes(2, 'little')
            i += 4
    if corrupt is not None:
        i = data.find(corrupt)
        data[i] ^= 0xFF
    with open(path, 'wb') as f:
        f.write(data)


# ================================================================================================ plan / apply
class PlanReviewTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def test_studio_keep_comes_from_mods_switch_and_is_never_merged(self):
        ms = load_mods_switch(self.t.sims)
        self.assertEqual(M.studio_keep(), list(ms.KEEP))                  # parsed, not executed
        self.assertEqual(M.studio_keep(os.path.join(self.t.dir, 'missing.py')), list(M.STUDIO_KEEP))
        self.assertTrue(M.studio_kept('Animation/ww_lamaboy_animation.package', ms.KEEP))
        self.assertTrue(M.studio_kept('FitStudio/a/b.package', ms.KEEP))
        self.assertFalse(M.studio_kept('animation/anim1.package', ms.KEEP))
        # plain CAS CC in the studio set's animation folder: only the file mods_switch keeps is excluded
        for n, name in enumerate(('WW_LAMABOY_Animation.package', 'other1.package', 'other2.package')):
            self.t.cc(self.t.m('animation', name), 60 + n)
        self.t.lib.scan()
        p = self.t.plan()
        self.assertTrue(p.excluded[self.t.pid('Mods', 'animation/WW_LAMABOY_Animation.package')].startswith('studio set'))
        g = next(g for g in p.groups if g.folder == 'animation')
        self.assertEqual(sorted(s.rel for s in g.sources), ['animation/other1.package', 'animation/other2.package'])
        # merging it would have taken it out of mods_switch's lean set
        self.assertIsNone(M.plan_merge(self.t.lib, cache_path=self.t.cache, verdicts=self.t.verdicts(), keep=[])
                          .excluded.get(self.t.pid('Mods', 'animation/WW_LAMABOY_Animation.package')))

    def test_parked_merged_folder_blocks_merges_into_mods(self):
        p_old = self.t.plan()                         # made before the folder was parked whole
        write(self.t.p('SpeedKit Merged', 'CAS_050.package'), [((CASP, 0, 0x5050), blob(5050), 'z')],
              manifest=[('x', [(CASP, 0, 0x5050)])])
        man = self.t.park_manifest()
        man['moved'].append('SpeedKit Merged/')
        self.t.write_manifest(man)
        self.t.lib.scan()
        p = self.t.plan()
        self.assertFalse([g for g in p.groups if g.root == 'Mods'])
        self.assertTrue(p.excluded[self.t.pid('Mods', 'CC/hairA.package')].startswith('parked folder'))
        self.assertTrue(any('SpeedKit Merged/' in w for w in p.warnings))
        self.assertTrue([g for g in p.groups if g.root == 'Mods_parked'])  # parked groups still merge
        before = tree_digest(self.t.sims, skip=())
        with self.assertRaises(M.MergeError) as cm:
            self.t.apply(p_old, dry_run=False)
        self.assertIn('parked folder', str(cm.exception))
        self.assertEqual(tree_digest(self.t.sims, skip=()), before)
        self.assertFalse(os.path.exists(self.t.m('SpeedKit Merged')))

    def test_unlisted_parked_sources_never_go_into_a_listed_folder(self):
        # parked files the manifest does not list are never restored by 'full'; their merged file must not land
        # in a folder a 'dir/' entry lists, or 'full' would start loading that CC
        self.t.cc(self.t.p('Unlisted', 'u1.package'), 40)
        self.t.cc(self.t.p('Unlisted', 'u2.package'), 41)
        self.t.lib.scan()
        p_old = self.t.plan(roots=('Mods_parked',))
        self.assertTrue(any(g.folder == 'Unlisted' for g in p_old.groups))
        write(self.t.p('SpeedKit Merged', 'CAS_050.package'), [((CASP, 0, 0x5050), blob(5050), 'z')],
              manifest=[('x', [(CASP, 0, 0x5050)])])
        man = self.t.park_manifest()
        man['moved'].append('SpeedKit Merged/')
        self.t.write_manifest(man)
        self.t.lib.scan()
        p = self.t.plan(roots=('Mods_parked',))
        self.assertFalse(any(g.folder == 'Unlisted' for g in p.groups))
        self.assertTrue(p.excluded[self.t.pid('Mods_parked', 'Unlisted/u1.package')].startswith('parked folder'))
        self.assertTrue(any(g.folder == 'Sliders' for g in p.groups))           # listed sources still merge
        before = tree_digest(self.t.sims, skip=())
        with self.assertRaises(M.MergeError) as cm:
            self.t.apply(p_old, dry_run=False)
        self.assertIn('plan again', str(cm.exception))
        self.assertEqual(tree_digest(self.t.sims, skip=()), before)

    def test_stale_plan_with_a_new_conflicting_copy_is_undone_by_the_after_check(self):
        p = self.t.plan()
        k = (CASP, 0, 0x100000000)                     # hairA's CAS part
        write(self.t.m('D', 'd.package'), [(k, blob(4711, 600), 'z')])   # loads after CC/, before SpeedKit Merged/
        self.t.lib.scan()
        before = tree_digest(self.t.sims)
        man_before = self.t.park_manifest()
        with self.assertRaises(M.InvariantError) as cm:
            self.t.apply(p, dry_run=False)
        self.assertIn('034AEECB:00000000:0000000100000000', str(cm.exception))
        self.assertIn('undone', str(cm.exception))
        self.assertEqual(tree_digest(self.t.sims), before)
        self.assertEqual(self.t.park_manifest(), man_before)

    def test_identical_copies_with_different_compression(self):
        k = (CASP, 0, 0xC0FFEE)
        data = blob(777, 900)
        write(self.t.m('Pack', 'a.package'), [(k, data, 'z'), ((RLE2, 0, 0xA1), blob(771, 900), 'z')])
        write(self.t.m('Pack', 'b.package'), [(k, data, 'u'), ((RLE2, 0, 0xB1), blob(772, 900), 'z')])
        write(self.t.m('Pack', '!c.package'), [(k, data, 'z')])                    # excluded, same content
        self.t.lib.scan()
        p = self.t.plan()
        g = next(g for g in p.groups if g.folder == 'Pack')
        self.assertEqual([s.rel for s in g.sources], ['Pack/a.package', 'Pack/b.package'])
        with Package(self.t.m('Pack', 'a.package')) as pk:
            a_raw = pk.raw(next(e for e in pk.entries if key_of(e) == k))
        r = self.t.apply(p, dry_run=False)
        self.assertEqual(r['invariant']['changed'], [])
        with Package(self.t.m(*g.out_rel.split('/'))) as pk:
            es = [e for e in pk.entries if key_of(e) == k]
            self.assertEqual(len(es), 1)
            self.assertEqual(pk.raw(es[0]), a_raw)                                  # the first-loaded copy
            srcs = S4S.sources_of(S4S.read_payload(pk))
        self.assertEqual(srcs['a'], {k, (RLE2, 0, 0xA1)})
        self.assertEqual(srcs['b'], {k, (RLE2, 0, 0xB1)})

    def test_size_cap_is_enforced_before_writing(self):
        p = self.t.plan()
        p.max_bytes = 3000                            # every group is bigger
        before = tree_digest(self.t.sims)
        with self.assertRaises(M.MergeError) as cm:
            self.t.apply(p, dry_run=False)
        self.assertIn('limit', str(cm.exception))
        self.assertEqual(tree_digest(self.t.sims), before)
        self.assertEqual(temp_leftovers(self.t.sims), [])
        with self.assertRaises(ValueError):
            self.t.plan(target_bytes=M.HARD_LIMIT, max_bytes=M.HARD_LIMIT + 1)


class FailureAtEveryStepTests(unittest.TestCase):
    """A failure before or after any journal step leaves the tree exactly as it was (automatic rollback), and a
    crash at any step (no rollback) is fully undone by merge.undo."""

    def check_every_step(self, t, run, snapshot, manifest=True):
        base, man = snapshot(), (t.park_manifest() if manifest else None)
        ids0 = journal_ids(t.home)
        run()                                          # a clean run counts the steps ...
        jid = (journal_ids(t.home) - ids0).pop()
        with open(os.path.join(t.home, 'journal', jid + '.json'), encoding='utf-8') as f:
            total = len(json.load(f)['steps'])
        M.undo(jid, home=t.home, check_game=False)     # ... and is undone
        t.lib.scan()
        self.assertEqual(snapshot(), base)
        self.assertGreater(total, 5)
        for where in ('step', 'done', 'crash'):
            for n in range(1, total + 1):
                with self.subTest(where=where, step=n):
                    FJ, calls = failing_journal(n, 'done' if where == 'crash' else where)
                    ids0 = journal_ids(t.home)
                    with mock.patch.object(M, 'Journal', FJ):
                        if where == 'crash':           # the process dies: no rollback, undo by hand later
                            with mock.patch.object(M, '_roll_back', lambda *a, **k: 'not undone (simulated crash)'):
                                with self.assertRaises(M.MergeError):
                                    run()
                            M.undo((journal_ids(t.home) - ids0).pop(), home=t.home, check_game=False)
                        else:
                            with self.assertRaises(M.MergeError) as cm:
                                run()
                            self.assertIn('was undone', str(cm.exception))
                    t.lib.scan()
                    self.assertEqual(snapshot(), base)
                    if manifest:
                        self.assertEqual(t.park_manifest(), man)
                    self.assertEqual(temp_leftovers(t.sims), [])

    def test_apply_merge(self):
        t = Tree()
        try:
            def run():
                t.lib.scan()
                return t.apply(t.plan(), dry_run=False)
            self.check_every_step(t, run, lambda: tree_digest(t.sims))
        finally:
            t.close()

    def test_process_inbox(self):
        t = Tree()
        try:
            inbox = os.path.join(t.sims, 'SpeedKit', 'Inbox')
            os.makedirs(inbox)
            with zipfile.ZipFile(os.path.join(inbox, 'CoolMod.zip'), 'w') as z:
                z.writestr('CoolMod/CoolMod.ts4script', b'PK\x05\x06' + bytes(18))
                z.writestr('CoolMod/CoolMod_Tuning.package', pkg_bytes([((BUFF, 0, 0x7001), tuning_xml('c'), 'z')]))
            write(os.path.join(inbox, 'NewHair.package'), [((CASP, 0, 0x6100000001), blob(601, 900), 'z')])
            write(os.path.join(inbox, 'ConflictHair.package'), [((CASP, 0, 0x100000000), blob(4242, 600), 'z')])
            write(os.path.join(inbox, 'Fake_Tuning.package'), [((TUN, 0, 0x900000000), tuning_xml('v2'), 'z')])
            write(os.path.join(inbox, 's1.package'), [((SMOD, 0, 0x1400000000), blob(7301, 300), 'z')])

            def run():
                t.lib.scan()
                return M.process_inbox(t.lib, dry_run=False, cache_path=t.cache, today=TODAY, check_game=False)
            self.check_every_step(t, run, lambda: state(t.sims))
        finally:
            t.close()


class UndoReviewTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def test_undo_refuses_to_recreate_a_folder_a_profile_switch_parked_whole(self):
        before = tree_digest(self.t.sims)
        man_before = self.t.park_manifest()
        r = self.t.apply(self.t.plan(), dry_run=False)
        # a profile switch parks CC/ as a whole folder but leaves SpeedKit Merged/ in Mods
        os.rename(self.t.m('CC'), self.t.p('CC'))
        man = self.t.park_manifest()
        man['moved'].append('CC/')
        self.t.write_manifest(man)
        mid = tree_digest(self.t.sims)
        with self.assertRaises(M.MergeError) as cm:
            M.undo(r['journal'], home=self.t.home, check_game=False)
        self.assertIn('switch back first', str(cm.exception))
        self.assertEqual(tree_digest(self.t.sims), mid)                  # refused before changing anything
        self.assertFalse(os.path.exists(self.t.m('CC')))
        # switched back: the undo goes through
        os.rename(self.t.p('CC'), self.t.m('CC'))
        man['moved'].remove('CC/')
        self.t.write_manifest(man)
        M.undo(r['journal'], home=self.t.home, check_game=False)
        self.assertEqual(tree_digest(self.t.sims), before)
        self.assertEqual(self.t.park_manifest(), man_before)

    def test_undo_again_repairs_the_manifest_after_it_was_broken(self):
        before = tree_digest(self.t.sims)
        man_before = self.t.park_manifest()
        r = self.t.apply(self.t.plan(), dry_run=False)
        man_after = self.t.park_manifest()
        self.assertGreater(len(man_after['moved']), len(man_before['moved']))
        mp = os.path.join(self.t.parked, '_manifest.json')
        with open(mp, 'w') as f:
            f.write('not json')                       # the other tool broke it meanwhile
        with self.assertRaises(M.MergeError):
            M.undo(r['journal'], home=self.t.home, check_game=False)
        after = tree_digest(self.t.sims)
        key = os.path.join('Mods_parked', '_manifest.json')
        self.assertEqual({k: v for k, v in after.items() if k != key}, {k: v for k, v in before.items() if k != key})
        self.t.write_manifest(man_after)             # fixed again
        self.assertEqual(M.undo(r['journal'], home=self.t.home, check_game=False, dry_run=True),
                         [('parking manifest: repair', r['journal'])])
        M.undo(r['journal'], home=self.t.home, check_game=False)
        self.assertEqual(self.t.park_manifest(), man_before)
        with self.assertRaises(J.JournalError):
            M.undo(r['journal'], home=self.t.home, check_game=False)   # really done now


# ================================================================================================ Inbox
class InboxReviewTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()
        self.inbox = os.path.join(self.t.sims, 'SpeedKit', 'Inbox')
        os.makedirs(self.inbox)
        self.i = lambda *p: os.path.join(self.inbox, *p)
        self.hair = pkg_bytes([((CASP, 0, 0x6100000001), blob(601, 900), 'z'), ((RLE2, 0, 0x6100000002), blob(602, 900), 'z')])

    def tearDown(self):
        self.t.close()

    def run_inbox(self, **kw):
        kw.setdefault('check_game', False)
        return M.process_inbox(self.t.lib, cache_path=self.t.cache, today=TODAY, **kw)

    def acts(self, rep):
        return {f['file']: f for it in rep['items'] for f in it['files']}

    def items(self, rep):
        return {it['item']: it for it in rep['items']}

    def test_bad_zips_refuse_only_themselves(self):
        with open(self.i('NewHair.package'), 'wb') as f:
            f.write(self.hair)
        for name in ('Deflate64', 'Encrypted', 'BadCrc'):
            with zipfile.ZipFile(self.i(name + '.zip'), 'w', zipfile.ZIP_STORED) as z:
                z.writestr('x/%s.package' % name, pkg_bytes([((CASP, 0, 0x7B00000001), blob(9, 700), 'u')]))
        zip_patch(self.i('Deflate64.zip'), method=9)
        zip_patch(self.i('Encrypted.zip'), flags=1)
        zip_patch(self.i('BadCrc.zip'), corrupt=b'<T n=')
        with zipfile.ZipFile(self.i('BadName.zip'), 'w') as z:
            z.writestr('Mac/Hair?.package', self.hair)
        with zipfile.ZipFile(self.i('Nested.zip'), 'w') as z:
            z.writestr('inner/more.zip', b'PK\x05\x06' + bytes(18))
        os.makedirs(self.i('Folder', 'deep'))
        with open(self.i('Folder', 'deep', 'pack.7z'), 'wb') as f:
            f.write(b"7z\xbc\xaf'\x1c")
        before = state(self.t.sims)
        rep = self.run_inbox()
        items = self.items(rep)
        for name in ('Deflate64.zip', 'Encrypted.zip', 'BadCrc.zip', 'BadName.zip', 'Nested.zip', 'Folder'):
            self.assertEqual(items[name]['status'], 'refused', name)
        self.assertIn('NotImplementedError', items['Deflate64.zip']['why'])
        self.assertIn('extract it first', items['Nested.zip']['why'])
        self.assertEqual(self.acts(rep)['NewHair.package']['action'], 'merge')
        self.assertEqual(state(self.t.sims), before)
        rep = self.run_inbox(dry_run=False)                       # the good item is installed, the rest stay
        self.assertEqual(self.items(rep)['NewHair.package']['status'], 'done')
        self.assertEqual(sorted(os.listdir(self.inbox)), sorted(['BadCrc.zip', 'BadName.zip', 'Deflate64.zip',
                                                                 'Encrypted.zip', 'Folder', 'Nested.zip', '_done']))

    def test_deep_unicode_zip_with_script_in_a_subfolder(self):
        script = b'PK\x05\x06' + bytes(18) + b'deja'
        tun = pkg_bytes([((BUFF, 0, 0x7C01), tuning_xml('deja_buff'), 'z')])
        with zipfile.ZipFile(self.i('Déjà Vu Mod ✓.zip'), 'w') as z:
            z.writestr('Déjà Vu/Mods/a/b/c/DejaVu.ts4script', script)
            z.writestr('Déjà Vu/Mods/x/y/DejaVu_Tuning.package', tun)
            z.writestr('Déjà Vu/readme.txt', 'hi')
        with zipfile.ZipFile(self.i('Hairs.zip'), 'w') as z:
            z.writestr('ヘアー/深い/フォルダ/ヘアー.package', self.hair)
        before = state(self.t.sims)
        rep = self.run_inbox(dry_run=False)
        acts = self.acts(rep)
        self.assertEqual(self.items(rep)['Déjà Vu Mod ✓.zip']['not_installed'], ['Déjà Vu/readme.txt'])  # reported
        self.assertEqual(acts['DejaVu.ts4script']['to'], 'Mods/Déjà Vu Mod ✓/DejaVu.ts4script')     # one folder deep
        self.assertEqual(acts['DejaVu_Tuning.package']['to'], 'Mods/Déjà Vu Mod ✓/DejaVu_Tuning.package')
        with open(self.t.m('Déjà Vu Mod ✓', 'DejaVu.ts4script'), 'rb') as f:
            self.assertEqual(f.read(), script)                                             # untouched
        self.assertEqual(acts['ヘアー.package']['action'], 'merge')
        with Package(self.t.m('SpeedKit Merged', 'New_001.package')) as pk:
            srcs = S4S.sources_of(S4S.read_payload(pk))
        self.assertEqual(srcs, {'ヘアー': {(CASP, 0, 0x6100000001), (RLE2, 0, 0x6100000002)}})
        self.t.lib.scan()
        self.assertIn(('Mods', 'Déjà Vu Mod ✓/DejaVu.ts4script'), {(s.root, s.rel) for s in self.t.lib.scripts()})
        M.undo(rep['journal'], home=self.t.home, check_game=False)
        self.assertEqual(state(self.t.sims), before)

    def test_package_that_is_really_a_zip(self):
        with zipfile.ZipFile(self.i('Hair.package'), 'w') as z:
            z.writestr('Hair/Hair.package', self.hair)
        it = self.items(self.run_inbox())['Hair.package']
        self.assertEqual(it['status'], 'refused')
        self.assertIn('rename it to .zip', it['why'])

    def test_redownloaded_script_keeps_its_new_companion_beside_it(self):
        with open(self.t.m('scripts', 'Fake.ts4script'), 'rb') as f:
            script = f.read()
        with zipfile.ZipFile(self.i('Fake v2.zip'), 'w') as z:
            z.writestr('Fake_renamed.ts4script', script)                            # the same script again
            z.writestr('Fake_NewPart.package', pkg_bytes([((BUFF, 0, 0x7D01), tuning_xml('newpart'), 'z')]))
        acts = self.acts(self.run_inbox())
        self.assertEqual(acts['Fake_renamed.ts4script']['action'], 'duplicate')
        self.assertEqual(acts['Fake_NewPart.package']['to'], 'Mods/scripts/Fake_NewPart.package')

    def test_load_order_names_are_installed_untouched_at_the_root(self):
        write(self.i('!!!_Override.package'), [((CASP, 0, 0x100000000), blob(4242, 600), 'z')])   # changes hairA
        write(self.i('zz_New.package'), [((CASP, 0, 0x6E00000001), blob(6601, 600), 'z')])         # all new
        rep = self.run_inbox(dry_run=False)
        acts = self.acts(rep)
        self.assertEqual(acts['!!!_Override.package']['to'], 'Mods/!!!_Override.package')
        self.assertEqual(acts['zz_New.package']['to'], 'Mods/zz_New.package')
        self.assertEqual({a['action'] for a in acts.values()}, {'install'})
        self.assertEqual(rep['merged_into'], [])
        self.assertFalse(os.path.exists(self.t.m('SpeedKit Loose')))

    def test_parked_speedkit_merged_folder_with_mods_switch_full_lean_full(self):
        # the user's cycle: merge -> mods_switch full -> lean (SpeedKit Merged/ parked as a whole folder) -> Inbox
        # -> full. The Inbox must not recreate Mods/SpeedKit Merged, or 'full' leaves the parked one behind.
        self.t.apply(self.t.plan(), dry_run=False)
        ms = load_mods_switch(self.t.sims)
        with redirect_stdout(io.StringIO()):
            ms.full()
            ms.lean()
        self.assertIn('SpeedKit Merged/', self.t.park_manifest()['moved'])
        self.assertFalse(os.path.exists(self.t.m('SpeedKit Merged')))
        self.t.lib.scan()
        with open(self.i('NewHair.package'), 'wb') as f:
            f.write(self.hair)
        rep = self.run_inbox(dry_run=False)
        self.assertEqual(rep['invariant']['wrong'], [])
        self.assertEqual(rep['merged_into'][0]['file'], 'Mods_parked/SpeedKit Merged/New_001.package')
        self.assertFalse(os.path.exists(self.t.m('SpeedKit Merged')))
        out = io.StringIO()
        with redirect_stdout(out):
            ms.full()
        self.assertNotIn('NOT restored', out.getvalue())
        self.assertEqual(sorted(os.listdir(self.t.m('SpeedKit Merged'))),
                         ['CAS_001.package', 'New_001.package', 'Sliders_001.package', 'Tuning_001.package'])
        self.assertEqual(self.t.park_manifest()['moved'], [])
        with self.assertRaises(M.MergeError):                  # moved by the switch: undo asks to switch back
            M.undo(rep['journal'], home=self.t.home, check_game=False)

    def test_not_enough_space_refuses_before_changing_anything(self):
        with open(self.i('NewHair.package'), 'wb') as f:
            f.write(self.hair)
        before = state(self.t.sims)
        with self.assertRaises(M.MergeError) as cm:
            self.run_inbox(dry_run=False, min_free=1 << 60)
        self.assertIn('free space', str(cm.exception))
        self.assertEqual(state(self.t.sims), before)
        self.assertEqual(journal_ids(self.t.home), set())

    def test_no_common_sims_folder_never_falls_back_to_the_real_one(self):
        a, b = tempfile.mkdtemp(dir=BASE), tempfile.mkdtemp(dir=BASE)
        try:
            os.makedirs(os.path.join(a, 'Mods'))
            os.makedirs(os.path.join(b, 'Mods_parked'))
            lib = Library(os.path.join(a, 'lib.sqlite'), {'Mods': os.path.join(a, 'Mods'),
                                                         'Mods_parked': os.path.join(b, 'Mods_parked')})
            real = os.path.exists(os.path.join(REAL_SIMS, 'SpeedKit'))
            for dry in (True, False):
                with self.assertRaises(M.MergeError):
                    M.process_inbox(lib, dry_run=dry, check_game=False)
            self.assertEqual(os.path.exists(os.path.join(REAL_SIMS, 'SpeedKit')), real)
            lib.close()
        finally:
            rmtree(a)
            rmtree(b)
        with self.assertRaises(ValueError):
            self.run_inbox(target_bytes=10, max_bytes=5)


if __name__ == '__main__':
    unittest.main()

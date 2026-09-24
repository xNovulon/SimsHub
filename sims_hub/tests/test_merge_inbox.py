"""speedkit.merge.process_inbox on a FAKE Sims 4 tree under E:\\speedkit_test\\merge (see test_merge.Tree).

Dropped into <fake Sims 4>/SpeedKit/Inbox:
  CoolMod.zip            CoolMod/CoolMod.ts4script + CoolMod/CoolMod_Tuning.package + readme.txt -> Mods/CoolMod/ untouched
  NewHair.package        new CAS CC -> merged into Mods/SpeedKit Merged/New_001.package
  DupHair.package        a renamed copy of an installed package -> nothing to install
  ConflictHair.package   changes an installed CAS part -> Mods/SpeedKit Loose/ unmerged
  Pack/PackA.package     a folder: one resource already installed (left out) + new ones -> merged
  MyTuning.package       XML tuning -> Mods/MyTuning/ untouched (gameplay mods are never merged)
  Fake_Tuning.package    same name as Mods/scripts/Fake_Tuning.package -> replaces it in place
  s1.package             same name as the PARKED Sliders/s1.package -> replaced in Mods_parked (stays parked)
  thing.rar              refused: extract it first (stays in the Inbox)
  Alt.zip                two packages that change the same resource differently -> refused
  evil.zip               a member named ../evil.package -> refused
  big.package.crdownload still downloading -> skipped
Nothing under the real Sims 4 folder is written.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from test_merge import Tree, write, blob, rmtree, CASP, THUM, RLE2, GEOM, BASE                  # noqa: E402
from speedkit.dbpf import Package, key_of                                                        # noqa: E402
from speedkit import merge as M                                                                  # noqa: E402
from speedkit import manifest as S4S                                                             # noqa: E402

BUFF = 0x6017E896
TODAY = '2026-09-24'


def tuning_xml(name):
    return ('<?xml version="1.0" encoding="utf-8"?>\n<I c="Buff" i="buff" m="buffs.buff" n="%s" s="1"><T n="x">1</T></I>'
            % name).encode()


def digest_file(p):
    with open(p, 'rb') as f:
        return hashlib.blake2b(f.read(), digest_size=16).hexdigest()


def state(sims):
    """Every file under the fake Sims 4 folder except SpeedKit's journal and quarantine (the Inbox counts)."""
    out = {}
    for dp, dn, fn in os.walk(sims):
        rel = os.path.relpath(dp, sims)
        if rel.startswith(os.path.join('SpeedKit', 'journal')) or rel.startswith(os.path.join('SpeedKit', 'quarantine')):
            continue
        for n in fn:
            out[os.path.relpath(os.path.join(dp, n), sims)] = digest_file(os.path.join(dp, n))
    return out


def pkg_bytes(items):
    fd, p = tempfile.mkstemp(suffix='.package', dir=BASE)
    os.close(fd)
    os.remove(p)
    write(p, items)
    with open(p, 'rb') as f:
        data = f.read()
    os.remove(p)
    return data


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()
        self.inbox = os.path.join(self.t.sims, 'SpeedKit', 'Inbox')
        os.makedirs(self.inbox)
        self.i = lambda *p: os.path.join(self.inbox, *p)
        self.script = b'PK\x05\x06' + b'\x00' * 18 + b'CoolMod'
        self.cool_tuning = pkg_bytes([((BUFF, 0, 0x7001), tuning_xml('coolmod_buff'), 'z')])
        with zipfile.ZipFile(self.i('CoolMod.zip'), 'w') as z:
            z.writestr('CoolMod/CoolMod.ts4script', self.script)
            z.writestr('CoolMod/CoolMod_Tuning.package', self.cool_tuning)
            z.writestr('CoolMod/readme.txt', 'hello')
        self.new_keys = [(CASP, 0, 0x6100000001), (THUM, 1, 0x6100000001), (RLE2, 0, 0x6100000002)]
        write(self.i('NewHair.package'), [(k, blob(600 + n, 900), 'z') for n, k in enumerate(self.new_keys)])
        shutil.copy2(self.t.m('CC', 'hairA.package'), self.i('DupHair.package'))
        write(self.i('ConflictHair.package'), [((CASP, 0, 0x100000000), blob(4242, 600), 'z'),
                                              ((CASP, 0, 0x6200000001), blob(4243, 600), 'z')])
        self.pack_new = [(CASP, 0, 0x6300000001), (GEOM, 0, 0x6300000002)]
        write(self.i('Pack', 'sub', 'PackA.package'), [((THUM, 1, 0x200000001), blob(21, 600), 'u')] +
              [(k, blob(700 + n, 700), 'z') for n, k in enumerate(self.pack_new)])
        write(self.i('MyTuning.package'), [((BUFF, 0, 0x7101), tuning_xml('my_buff'), 'z')])
        # new versions of installed files: same name AND at least one shared resource
        write(self.i('Fake_Tuning.package'), [((0x0C772E27, 0, 0x900000000), tuning_xml('fake_v2'), 'z')])
        write(self.i('s1.package'), [((0xC5F6763E, 0, 0x1400000000), blob(7301, 300), 'z')])
        # same name as Mods/CC/tweak.package but unrelated CC: not an update
        write(self.i('tweak.package'), [((CASP, 0, 0x6600000001), blob(6601, 500), 'z')])
        # a loose script and its companion dropped separately belong together
        with open(self.i('Loose_Scripts.ts4script'), 'wb') as f:
            f.write(b'PK' + bytes([5, 6]) + bytes(18) + b'Loose')
        write(self.i('Loose_Tuning.package'), [((BUFF, 0, 0x7501), tuning_xml('loose_buff'), 'z')])
        with open(self.i('thing.rar'), 'wb') as f:
            f.write(b'Rar!\x1a\x07\x00')
        a = pkg_bytes([((CASP, 0, 0x6400000001), blob(1, 500), 'z')])
        b = pkg_bytes([((CASP, 0, 0x6400000001), blob(2, 500), 'z')])
        with zipfile.ZipFile(self.i('Alt.zip'), 'w') as z:
            z.writestr('Light/Alt.package', a)
            z.writestr('Dark/AltDark.package', b)
        with zipfile.ZipFile(self.i('evil.zip'), 'w') as z:
            z.writestr('../evil.package', a)
        with open(self.i('big.package.crdownload'), 'wb') as f:
            f.write(b'partial')

    def tearDown(self):
        self.t.close()

    def run_inbox(self, **kw):
        kw.setdefault('check_game', False)
        return M.process_inbox(self.t.lib, cache_path=self.t.cache, today=TODAY, **kw)

    def by_item(self, rep):
        return {it['item']: it for it in rep['items']}

    def test_dry_run_reports_and_changes_nothing(self):
        before = state(self.t.sims)
        rep = self.run_inbox()
        self.assertEqual(state(self.t.sims), before)
        items = self.by_item(rep)
        self.assertEqual(items['thing.rar']['status'], 'refused')
        self.assertIn('extract it first', items['thing.rar']['why'])
        self.assertEqual(items['Alt.zip']['status'], 'refused')
        self.assertIn('alternative versions', items['Alt.zip']['why'])
        self.assertEqual(items['evil.zip']['status'], 'refused')
        self.assertEqual(items['big.package.crdownload']['status'], 'skipped')
        act = {f['file']: f for it in rep['items'] for f in it['files']}
        self.assertEqual(act['CoolMod.ts4script']['action'], 'install')
        self.assertEqual(act['CoolMod.ts4script']['to'], 'Mods/CoolMod/CoolMod.ts4script')
        self.assertEqual(act['CoolMod_Tuning.package']['to'], 'Mods/CoolMod/CoolMod_Tuning.package')
        self.assertEqual(act['NewHair.package']['action'], 'merge')
        self.assertEqual(act['NewHair.package']['to'], 'Mods/SpeedKit Merged/New_001.package')
        self.assertEqual(act['DupHair.package']['action'], 'duplicate')
        self.assertIn('Mods/CC/hairA.package', act['DupHair.package']['why'])
        self.assertEqual(act['ConflictHair.package']['action'], 'loose')
        self.assertEqual(act['ConflictHair.package']['to'], 'Mods/SpeedKit Loose/ConflictHair.package')
        self.assertEqual(act['PackA.package']['action'], 'merge')
        self.assertEqual(act['PackA.package']['already_installed_resources'], 1)
        self.assertEqual(act['MyTuning.package']['to'], 'Mods/MyTuning/MyTuning.package')
        self.assertEqual(act['Fake_Tuning.package']['action'], 'update')
        self.assertEqual(act['Fake_Tuning.package']['to'], 'Mods/scripts/Fake_Tuning.package')
        self.assertEqual(act['s1.package']['to'], 'Mods_parked/Sliders/s1.package')
        self.assertEqual(act['s1.package']['action'], 'update')
        self.assertEqual(act['tweak.package']['action'], 'merge')          # a name clash is not an update
        self.assertEqual(act['Loose_Scripts.ts4script']['to'], 'Mods/Loose_Scripts/Loose_Scripts.ts4script')
        self.assertEqual(act['Loose_Tuning.package']['to'], 'Mods/Loose_Scripts/Loose_Tuning.package')
        self.assertEqual(items['Loose_Scripts.ts4script']['with'], ['Loose_Tuning.package'])
        self.assertNotIn('Loose_Tuning.package', items)
        self.assertEqual(rep['merged_into'][0]['file'], 'Mods/SpeedKit Merged/New_001.package')
        self.assertEqual(sorted(rep['merged_into'][0]['downloads']), ['NewHair.package', 'PackA.package', 'tweak.package'])

    def test_real_run_then_undo(self):
        before = state(self.t.sims)
        man_before = self.t.park_manifest()
        rep = self.run_inbox(dry_run=False)
        self.assertEqual(rep['invariant']['wrong'], [])
        self.assertTrue(rep['journal'].endswith('-inbox'))
        m = self.t.m
        with zipfile.ZipFile(os.path.join(self.inbox, '_done', TODAY, 'CoolMod.zip')) as z:
            self.assertEqual(z.read('CoolMod/CoolMod.ts4script'), self.script)
        with open(m('CoolMod', 'CoolMod.ts4script'), 'rb') as f:
            self.assertEqual(f.read(), self.script)                        # untouched
        with open(m('CoolMod', 'CoolMod_Tuning.package'), 'rb') as f:
            self.assertEqual(f.read(), self.cool_tuning)
        self.assertFalse(os.path.exists(m('CoolMod', 'readme.txt')))
        new = m('SpeedKit Merged', 'New_001.package')
        with Package(new) as k:
            keys = [key_of(e) for e in k.entries]
            srcs = S4S.sources_of(S4S.read_payload(k))
        self.assertEqual(set(keys[1:]), set(self.new_keys) | set(self.pack_new) | {(CASP, 0, 0x6600000001)})
        self.assertEqual(set(srcs), {'NewHair', 'PackA', 'tweak'})             # the installed THUM was left out
        self.assertEqual(srcs['PackA'], set(self.pack_new))
        self.assertEqual(digest_file(m('SpeedKit Loose', 'ConflictHair.package')),
                         digest_file(os.path.join(self.inbox, '_done', TODAY, 'ConflictHair.package')))
        self.assertEqual(digest_file(m('scripts', 'Fake_Tuning.package')),
                         digest_file(os.path.join(self.inbox, '_done', TODAY, 'Fake_Tuning.package')))
        self.assertEqual(digest_file(self.t.p('Sliders', 's1.package')),
                         digest_file(os.path.join(self.inbox, '_done', TODAY, 's1.package')))
        self.assertTrue(os.path.exists(m('MyTuning', 'MyTuning.package')))
        self.assertEqual(self.t.park_manifest(), man_before)              # s1 is covered by 'Sliders/'
        left = sorted(os.listdir(self.inbox))
        self.assertEqual(left, ['Alt.zip', '_done', 'big.package.crdownload', 'evil.zip', 'thing.rar'])
        self.assertEqual(sorted(os.listdir(os.path.join(self.inbox, '_done', TODAY))),
                         sorted(['CoolMod.zip', 'NewHair.package', 'DupHair.package', 'ConflictHair.package', 'Pack',
                                 'MyTuning.package', 'Fake_Tuning.package', 's1.package', 'tweak.package',
                                 'Loose_Scripts.ts4script', 'Loose_Tuning.package']))
        self.assertTrue(os.path.exists(m('Loose_Scripts', 'Loose_Tuning.package')))
        self.assertFalse(os.path.exists(os.path.join(self.inbox, '_staging')))
        # the game would load the new CC
        self.t.lib.scan()
        self.assertIn(('Mods', 'SpeedKit Merged/New_001.package'), {(p.root, p.rel) for p in self.t.lib.packages()})
        # undo puts everything back, the Inbox included
        M.undo(rep['journal'], home=os.path.join(self.t.sims, 'SpeedKit'), check_game=False)
        self.assertEqual(state(self.t.sims), before)

    def test_second_run_appends_to_the_newest_merged_file(self):
        rep1 = self.run_inbox(dry_run=False)
        self.t.lib.scan()
        new = self.t.m('SpeedKit Merged', 'New_001.package')
        v1 = digest_file(new)
        for n in os.listdir(self.inbox):                   # keep only the second download in the Inbox
            p = self.i(n)
            if n != '_done':
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        more = [(CASP, 0, 0x6500000001), (RLE2, 0, 0x6500000002)]
        write(self.i('Another.package'), [(k, blob(900 + n, 800), 'z') for n, k in enumerate(more)])
        rep2 = self.run_inbox(dry_run=False)
        self.assertEqual(rep2['merged_into'], [{'file': 'Mods/SpeedKit Merged/New_001.package', 'appends_to_existing': True,
                                                'downloads': ['Another.package']}])
        self.assertEqual(rep2['invariant']['wrong'], [])
        self.assertGreater(rep2['invariant']['kept_resources'], 0)
        with Package(new) as k:
            keys = {key_of(e) for e in k.entries}
            srcs = S4S.sources_of(S4S.read_payload(k))
        self.assertTrue(set(self.new_keys) | set(self.pack_new) | set(more) <= keys)
        self.assertEqual(set(srcs), {'NewHair', 'PackA', 'tweak', 'Another'})
        self.assertFalse(os.path.exists(self.t.m('SpeedKit Merged', 'New_002.package')))
        home = os.path.join(self.t.sims, 'SpeedKit')
        M.undo(rep2['journal'], home=home, check_game=False)
        self.assertEqual(digest_file(new), v1)                               # the previous version is back
        self.assertTrue(os.path.exists(self.i('Another.package')))
        M.undo(rep1['journal'], home=home, check_game=False)
        self.assertFalse(os.path.exists(new))

    def test_parked_home_listing_follows_the_script(self):
        # an update of a parked script mod: the new companion goes next to the parked script, and is listed in
        # Mods_parked/_manifest.json exactly when the script is (so 'full' restores both or neither)
        os.makedirs(self.t.p('Parked Mod'))
        with open(self.t.p('Parked Mod', 'PMod.ts4script'), 'wb') as f:
            f.write(b'PK' + bytes([5, 6]) + bytes(18) + b'old')
        self.t.lib.scan()
        self.clear_inbox()
        with zipfile.ZipFile(self.i('PMod v2.zip'), 'w') as z:
            z.writestr('PMod.ts4script', b'PK' + bytes([5, 6]) + bytes(18) + b'new')
            z.writestr('PMod_Extra.package', pkg_bytes([((BUFF, 0, 0x7401), tuning_xml('pmod'), 'z')]))
        act = {f['file']: f for it in self.run_inbox()['items'] for f in it['files']}
        self.assertEqual(act['PMod.ts4script']['to'], 'Mods_parked/Parked Mod/PMod.ts4script')
        self.assertEqual(act['PMod_Extra.package']['to'], 'Mods_parked/Parked Mod/PMod_Extra.package')
        self.assertNotIn('added_to_parking_manifest', act['PMod_Extra.package'])    # the script is not listed
        man = self.t.park_manifest()
        man['moved'].append('Parked Mod/PMod.ts4script')
        with open(os.path.join(self.t.parked, '_manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(man, f)
        rep = self.run_inbox(dry_run=False)
        act = {f['file']: f for it in rep['items'] for f in it['files']}
        self.assertTrue(act['PMod_Extra.package']['added_to_parking_manifest'])
        moved = self.t.park_manifest()['moved']
        self.assertEqual(moved[-2:], ['Parked Mod/PMod.ts4script', 'Parked Mod/PMod_Extra.package'])
        M.undo(rep['journal'], home=os.path.join(self.t.sims, 'SpeedKit'), check_game=False)
        self.assertEqual(self.t.park_manifest()['moved'][-1], 'Parked Mod/PMod.ts4script')
        with open(self.t.p('Parked Mod', 'PMod.ts4script'), 'rb') as f:
            self.assertTrue(f.read().endswith(b'old'))

    def test_new_folder_names_avoid_parked_names(self):
        os.makedirs(self.t.p('CoolMod'))
        rep = self.run_inbox()
        act = {f['file']: f for it in rep['items'] for f in it['files']}
        self.assertEqual(act['CoolMod.ts4script']['to'], 'Mods/CoolMod (2)/CoolMod.ts4script')

    def test_refusals(self):
        before = state(self.t.sims)
        with mock.patch.object(M, 'game_running', lambda: True):
            with self.assertRaises(M.MergeError):
                M.process_inbox(self.t.lib, dry_run=False, cache_path=self.t.cache)
        with open(self.t.m('CC', 'hairA.package'), 'ab') as f:            # library changed since the scan
            f.write(b'\0')
        with self.assertRaises(M.MergeError):
            self.run_inbox(dry_run=False)
        after = state(self.t.sims)
        del before[os.path.join('Mods', 'CC', 'hairA.package')], after[os.path.join('Mods', 'CC', 'hairA.package')]
        self.assertEqual(after, before)

    def test_failure_mid_run_is_rolled_back(self):
        before = state(self.t.sims)
        real = M.write_merged

        def boom(*a, **k):
            raise OSError('disk full (simulated)')
        with mock.patch.object(M, 'write_merged', boom):
            with self.assertRaises(M.MergeError) as cm:
                self.run_inbox(dry_run=False)
        self.assertIn('undone', str(cm.exception))
        self.assertEqual(state(self.t.sims), before)

    def clear_inbox(self):
        for n in os.listdir(self.inbox):
            p = self.i(n)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    def test_compares_with_the_copy_the_game_uses_and_namemaps(self):
        from test_merge import CONFLICT
        self.clear_inbox()
        # CONFLICT has two versions installed; conflictX's loads first, so a download holding that one adds nothing
        write(self.i('SameAsWinner.package'), [(CONFLICT, blob(501, 700), 'z'), ((CASP, 0, 0x6700000001), blob(6701, 400), 'z')])
        write(self.i('SameAsLoser.package'), [(CONFLICT, blob(502, 700), 'z'), ((CASP, 0, 0x6800000001), blob(6801, 400), 'z')])
        # two S4S-made packages in one zip: their NameMaps (same key, new to the library) differ - that is not
        # 'alternative versions'; by default both go loose, with ignore_namemap both merge and the first one's is kept
        nm = (0x0166038C, 0, 0x55)
        with zipfile.ZipFile(self.i('Set.zip'), 'w') as z:
            z.writestr('Set/SetA.package', pkg_bytes([(nm, b'names A' * 20, 'z'), ((CASP, 0, 0x6900000001), blob(6901, 400), 'z')]))
            z.writestr('Set/SetB.package', pkg_bytes([(nm, b'names B' * 20, 'z'), ((CASP, 0, 0x6900000002), blob(6902, 400), 'z')]))
        # a script downloaded again under another name
        shutil.copy2(self.t.m('scripts', 'Fake.ts4script'), self.i('Fake (1).ts4script'))
        act = {f['file']: f for it in self.run_inbox()['items'] for f in it['files']}
        self.assertEqual(act['SameAsWinner.package']['action'], 'merge')
        self.assertEqual(act['SameAsWinner.package']['already_installed_resources'], 1)
        self.assertEqual(act['SameAsLoser.package']['action'], 'loose')
        self.assertEqual(act['SetA.package']['action'], 'loose')          # NameMap counts as content by default
        self.assertEqual(act['SetB.package']['action'], 'loose')
        self.assertEqual(act['Fake (1).ts4script']['action'], 'duplicate')
        self.assertIn('scripts/Fake.ts4script', act['Fake (1).ts4script']['why'])
        rep = self.run_inbox(dry_run=False, ignore_namemap=True)
        act = {f['file']: f for it in rep['items'] for f in it['files']}
        self.assertEqual(act['SetA.package']['action'], 'merge')
        self.assertEqual(act['SetB.package']['action'], 'merge')
        self.assertEqual(rep['invariant']['wrong'], [])
        with Package(self.t.m('SpeedKit Merged', 'New_001.package')) as k:
            keys = [key_of(e) for e in k.entries]
            srcs = S4S.sources_of(S4S.read_payload(k))
        self.assertEqual(keys.count(nm), 1)
        self.assertIn(nm, srcs['SetA'])
        self.assertIn(nm, srcs['SetB'])
        self.assertNotIn(CONFLICT, keys)
        self.assertFalse(os.path.exists(self.t.m('Fake (1)')))

    def test_missing_inbox(self):
        rmtree(self.inbox)
        rep = self.run_inbox()
        self.assertTrue(rep['warnings'])
        self.assertFalse(os.path.exists(self.inbox))
        self.run_inbox(dry_run=False)
        self.assertTrue(os.path.isdir(os.path.join(self.inbox, '_done')))


if __name__ == '__main__':
    unittest.main()

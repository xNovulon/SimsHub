"""Unmerge (speedkit/unmerge.py): a merged package split back into its sources from the Sims 4 Studio merge list,
byte for byte, nothing left out, undoable; a file without a merge list is refused and left alone."""
import hashlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import manifest, unmerge                                  # noqa: E402
from speedkit.dbpf import Package, PackageWriter                        # noqa: E402
from speedkit.journal import undo                                       # noqa: E402

CASP, GEOM, IMG = 0x034AEECB, 0x015A1849, 0x3453CF95


def sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


class Unmerge(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='unmerge_')
        self.sims = os.path.join(self.root, 'The Sims 4')
        self.mods = os.path.join(self.sims, 'Mods', 'CC')
        os.makedirs(self.mods)
        self.home = os.path.join(self.sims, 'SpeedKit')
        hair = [((CASP, 0, 0xA1), b'hair-casp' * 30), ((GEOM, 0, 0xA1), b'hair-mesh' * 400), ((IMG, 0, 0xA1), b'hair-tex' * 900)]
        top = [((CASP, 0, 0xB1), b'top-casp' * 30), ((IMG, 0, 0xB1), b'top-tex' * 700)]
        shared = ((IMG, 0, 0xC1), b'shared-texture' * 50)        # one texture both mods use
        self.merged = os.path.join(self.mods, 'My Merge.package')
        data = manifest.build_flat([('Creator_Hair.package', [k for k, _ in hair] + [shared[0]]),
                                    ('Creator: Top/Set?.package', [k for k, _ in top] + [shared[0]])])
        with PackageWriter(self.merged) as w:
            w.add((manifest.MANIFEST_TYPE, 0, 0), data)
            for k, d in hair + top + [shared, ((0x220557DA, 0, 0xD1), b'strings-nobody-listed' * 20)]:
                w.add(k, d)
        self.before = sha(self.merged)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_info(self):
        i = unmerge.info(self.merged)
        self.assertTrue(i['merged'])
        self.assertEqual([s['resources'] for s in i['sources']], [4, 3])
        self.assertEqual(i['unlisted'], 1)
        self.assertEqual(i['missing'], 0)

    def test_split_exact_and_undo(self):
        with Package(self.merged) as p:
            orig = {(e.t, e.g, e.i): p.raw(e) for e in p.entries if e.t != manifest.MANIFEST_TYPE}
        r = unmerge.unmerge(self.merged, sims=self.sims, journal_home=self.home, check_game=False)
        self.assertTrue(r['ok'])
        self.assertFalse(os.path.exists(self.merged))                   # set aside (in the quarantine)
        names = sorted(os.path.basename(x) for x in r['written'])
        self.assertEqual(names, sorted(['Creator_Hair.package', 'Creator_ Top_Set_.package', 'Not in the merge list.package']))
        got = {}
        for f in r['written']:
            with Package(f) as q:
                for e in q.entries:
                    got.setdefault((e.t, e.g, e.i), set()).add(q.raw(e))
        self.assertEqual(set(got), set(orig))                            # nothing left out
        for k, raws in got.items():
            self.assertEqual(raws, {orig[k]})                            # byte for byte
        with Package(os.path.join(r['folder'], 'Creator_Hair.package')) as q:
            self.assertEqual(len(q.entries), 4)                          # its own 3 + the shared texture
        undo(r['journal'], home=self.home, check_game=False)
        self.assertEqual(sha(self.merged), self.before)                  # back as it was
        self.assertFalse(any(os.path.exists(x) for x in r['written']))

    def test_no_merge_list_is_refused(self):
        plain = os.path.join(self.mods, 'plain.package')
        with PackageWriter(plain) as w:
            w.add((CASP, 0, 0xE1), b'x' * 100)
        self.assertFalse(unmerge.info(plain)['merged'])
        with self.assertRaises(unmerge.UnmergeError):
            unmerge.unmerge(plain, sims=self.sims, journal_home=self.home, check_game=False)
        self.assertTrue(os.path.exists(plain))


if __name__ == '__main__':
    unittest.main()

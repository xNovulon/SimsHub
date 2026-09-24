"""Adversarial tests of speedkit.hashing / speedkit.dedup on a FAKE Sims 4 tree under E:\\speedkit_test\\dedup_review.

Covers what tests/test_dedup.py does not: 64-bit instances with the high bit set, source packages whose index
uses constant type/group/instance-high fields, deleted-flag (0xFFE0) entries, zero-byte resources sharing an
offset with the next one, a key held three times inside one package, an unreadable package, non-ASCII file
names, the streamed hashing path (resources bigger than the read window), RefPack / truncated zlib streams,
and the guards of apply(): a library whose roots have no common Sims folder, a journal home inside Mods, a
failure or Ctrl+C during the check after the run, two runs in the same second, a keeper that changed after
a rescan, and a leftover temporary file. Also the S4S-merge protection rules (include_merged=False).

The real Sims 4 folder is never touched: every tree lives in a temp folder under BASE, and the tests that
exercise the "which Sims folder" logic replace Journal with a mock that fails if it is ever created.
"""
import hashlib
import json
import os
import random
import shutil
import stat
import struct
import sys
import tempfile
import types
import unittest
import zlib
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from speedkit.dbpf import Package, PackageWriter, Entry, HEADER, ZLIB, NONE, REFPACK, DELETED, key_of, read_entries  # noqa: E402
from speedkit.library import Library                                                             # noqa: E402
from speedkit import dedup, hashing                                                               # noqa: E402
from speedkit.hashing import hash_copies, key_status, effective_map                               # noqa: E402
from speedkit.dedup import plan, apply, DedupError, default_protected                             # noqa: E402
from speedkit.journal import undo, list_journals                                                  # noqa: E402
from speedkit import manifest as s4s                                                              # noqa: E402
from speedkit.companions import Verdict, NEVER_MERGE                                              # noqa: E402

BASE = r'E:\speedkit_test\dedup_review'
CASP, TUN, CLIP = 0x034AEECB, 0x0C772E27, 0x6B20C4F3

H1 = (CASP, 0x80000000, 0x8000000000000000)     # high-bit instances (stored signed in SQLite)
H2 = (CASP, 0x00000000, 0xFFFFFFFFFFFFFFFF)
H3 = (TUN, 0x00000000, 0xF123456789ABCDEF)
KA = (CASP, 0, 0x9999999999999999)              # also in Mods: the active copy is kept
Z0 = (CLIP, 0, 0x10)                            # zero-byte, unique, shares its offset with KA in Early
Z2 = (CLIP, 0, 0x20)                            # zero-byte, duplicated
F1 = (CASP, 0, 0x0000111100000001)              # in the flags=7 package (constant t, g and instance-high)
F2 = (CASP, 0, 0x0000111100000002)
G1 = (CASP, 0, 0xC000000000000001)              # in the flags=3 package (constant t and g)
G2 = (CASP, 0, 0xC000000000000002)
KD = (CASP, 0, 0xD0)                            # live copy dropped, a deleted-flag entry of the same key stays
DX = (CASP, 0, 0xD1)                            # deleted-flag entry only
D2 = (CASP, 0, 0xD2)
UK, UU = (CASP, 0, 0xE0), (CASP, 0, 0xE1)       # in the non-ASCII named package
T3 = (CASP, 0, 0xF3)                            # three identical copies inside one package, nowhere else
TU = (CASP, 0, 0xF4)
MU = (CASP, 0, 0xAB)                            # unique to the merge
UNI_NAME = '[dreamlike] preset sets\u65e0\u75c5\u6bd2\u7248\uff01\uff01 \U0001D4AE.package'


def blob(seed, n=2500):
    r = random.Random(seed)
    words = [b'<T n="%d">%d</T>' % (r.randrange(40), r.randrange(10 ** 6)) for _ in range(30)]
    return b''.join(r.choice(words) for _ in range(n // 14))[:n]


def refpack(data):
    """A valid RefPack stream holding `data` as literals only (what the game's decoder accepts)."""
    out = bytearray([0x10, 0xFB]) + len(data).to_bytes(3, 'big')
    p = 0
    while len(data) - p >= 4:
        n = min(112, (len(data) - p) // 4 * 4)
        out.append(0xE0 | ((n - 4) >> 2))
        out += data[p:p + n]
        p += n
    out.append(0xFC | (len(data) - p))
    out += data[p:]
    return bytes(out)


def zlib_unfinished(data):
    """zlib stream without its final block and checksum (inflates fully, eof never reached)."""
    c = zlib.compressobj(9)
    return c.compress(data) + c.flush(zlib.Z_SYNC_FLUSH)


class DupWriter(PackageWriter):
    """Allows one key several times (S4S merges sometimes hold that)."""

    def _put(self, t, g, i, raw, msize, comp, committed=1):
        self.keys.discard((t, g, i))
        super()._put(t, g, i, raw, msize, comp, committed)


def write(path, items, writer=PackageWriter):
    """items: (key, data, how): 'z' zlib, 'u' stored, or ('raw', comp, msize) to store `data` as given."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with writer(path) as w:
        for key, data, how in items:
            if how == 'z':
                w.add(key, data, compress=True)
            elif how == 'u':
                w.add(key, data, compress=False)
            else:
                _, comp, msize = how
                w.add_raw(Entry(key[0], key[1], key[2], 0, len(data), msize, comp, 1), data)


def write_flagged(path, flags, items):
    """A package whose index uses constant fields (flags bit 1 type, 2 group, 4 instance-high), like 98 real
    packages do. items: (key, data) stored uncompressed; the constant fields come from the first key."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    body = bytearray()
    pos = 96
    offs = []
    for key, data in items:
        offs.append(pos)
        body += data
        pos += len(data)
    t0, g0, i0 = items[0][0]
    index = bytearray(struct.pack('<I', flags))
    if flags & 1:
        index += struct.pack('<I', t0)
    if flags & 2:
        index += struct.pack('<I', g0)
    if flags & 4:
        index += struct.pack('<I', i0 >> 32)
    for (key, data), off in zip(items, offs):
        t, g, i = key
        assert (not flags & 1 or t == t0) and (not flags & 2 or g == g0) and (not flags & 4 or i >> 32 == i0 >> 32)
        if not flags & 1:
            index += struct.pack('<I', t)
        if not flags & 2:
            index += struct.pack('<I', g)
        if not flags & 4:
            index += struct.pack('<I', i >> 32)
        index += struct.pack('<IIIIHH', i & 0xFFFFFFFF, off, len(data) | 0x80000000, len(data), NONE, 1)
    head = HEADER.pack(b'DBPF', 2, 1, 0, 0, 0, 0, 0, 0, len(items), 0, len(index), 0, 0, 0, 3, pos)
    with open(path, 'wb') as f:
        f.write(head + bytes(body) + bytes(index))


def rmtree(path):
    def retry(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if os.path.exists(path):
        shutil.rmtree(path, onerror=retry)


def tree_digest(sims):
    out = {}
    for dp, dn, fn in os.walk(sims):
        if os.path.relpath(dp, sims).split(os.sep)[0] == 'SpeedKit':
            continue
        for n in fn:
            p = os.path.join(dp, n)
            with open(p, 'rb') as f:
                out[os.path.relpath(p, sims)] = hashlib.blake2b(f.read(), digest_size=16).hexdigest()
    return out


class Tree:
    """A fake Sims folder with the odd cases listed in the module docstring."""

    def __init__(self, build=True):
        os.makedirs(BASE, exist_ok=True)
        self.dir = tempfile.mkdtemp(dir=BASE)
        self.sims = os.path.join(self.dir, 'The Sims 4')
        self.mods = os.path.join(self.sims, 'Mods')
        self.parked = os.path.join(self.sims, 'Mods_parked')
        self.home = os.path.join(self.sims, 'SpeedKit')
        self.cache = os.path.join(self.dir, 'hash.sqlite')
        os.makedirs(self.mods)
        os.makedirs(self.parked)
        self.data = {k: blob(n) for n, k in enumerate((H1, H2, H3, KA, F1, F2, G1, G2, KD, D2, UK, UU, T3, TU, MU))}
        if build:
            self.build()
        self.lib = Library(os.path.join(self.dir, 'library.sqlite'), {'Mods': self.mods, 'Mods_parked': self.parked})
        self.lib.scan()

    def P(self, *parts):
        return os.path.join(self.parked, *parts)

    def build(self):
        d = self.data
        write(os.path.join(self.mods, 'cc', 'Keep.package'), [(KA, d[KA], 'z')])
        # Early loads first in Mods_parked: it keeps every key except KA (Mods keeps that one)
        write(self.P('a', 'Early.package'),
              [(k, d[k], 'z') for k in (H1, H2, H3)] + [(Z0, b'', 'u'), (KA, d[KA], 'z'), (Z2, b'', 'u')]
              + [(k, d[k], 'u') for k in (F1, G1)] + [(KD, d[KD], 'z'), (UK, d[UK], 'z')])
        with open(self.P('a', 'Early.package'), 'rb') as f:
            ents = {key_of(e): e for e in read_entries(f)}
        assert ents[Z0].off == ents[KA].off              # a zero-byte resource shares its offset with KA
        os.makedirs(self.P('bad'))
        with open(self.P('bad', 'Corrupt.package'), 'wb') as f:
            f.write(b'DBPF' + b'\xff' * 200)             # unreadable index: must never be touched
        with open(self.P('bad', 'NotDBPF.package'), 'wb') as f:
            f.write(b'hello')
        write(self.P('del', 'Deleted.package'),
              [(KD, d[KD], 'z'), (D2, d[D2], 'z'), (KD, b'', ('raw', DELETED, 0)), (DX, b'', ('raw', DELETED, 0))],
              DupWriter)
        write_flagged(self.P('flags', 'Flagged7.package'), 7, [(F1, d[F1]), (F2, d[F2])])
        write_flagged(self.P('flags', 'Flagged3.package'), 3, [(G1, d[G1]), (G2, d[G2])])
        man = s4s.build_flat([('HighBits', [H1, H2, H3, Z2]), ('Active', [KA]), ('Own', [MU])])
        write(self.P('sim', 'Merge.package'), [(s4s.MANIFEST_KEY, man, 'z')] + [(k, d[k], 'z') for k in (H1, H2, H3, KA)]
              + [(Z2, b'', 'u'), (MU, d[MU], 'z')])
        write(self.P('trip', 'Triple.package'), [(T3, d[T3], 'z'), (TU, d[TU], 'z'), (T3, d[T3], 'z'), (T3, d[T3], 'z')],
              DupWriter)
        write(self.P('uni', UNI_NAME), [(UK, d[UK], 'z'), (UU, d[UU], 'z')])

    def pkg(self, rel, root='Mods_parked'):
        return next(p for p in self.lib.packages(root) if p.rel == rel)

    def keys(self, *parts):
        with Package(self.P(*parts)) as p:
            return [(key_of(e), e.comp) for e in p.entries]

    def plan(self, **kw):
        kw.setdefault('protected', set())
        return plan(self.lib, cache_path=self.cache, **kw)

    def apply(self, p, **kw):
        kw.setdefault('journal_home', self.home)
        kw.setdefault('sims', self.sims)
        return apply(p, self.lib, dry_run=False, check_game=False, cache_path=self.cache, min_free=0, **kw)

    def close(self):
        self.lib.close()
        rmtree(self.dir)


class OddPackageTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def test_plan_of_odd_packages(self):
        t = self.t
        p = t.plan()
        act = {pp.rel: pp.action for pp in p.packages.values()}
        self.assertEqual(act, {'a/Early.package': 'rewrite', 'del/Deleted.package': 'rewrite',
                               'flags/Flagged7.package': 'rewrite', 'flags/Flagged3.package': 'rewrite',
                               'sim/Merge.package': 'rewrite', 'trip/Triple.package': 'rewrite',
                               'uni/' + UNI_NAME: 'rewrite'})
        drops = {pp.rel: {d[:3] for d in pp.drop} for pp in p.packages.values()}
        self.assertEqual(drops['a/Early.package'], {KA})
        self.assertEqual(drops['sim/Merge.package'], {H1, H2, H3, KA, Z2})
        self.assertEqual(drops['trip/Triple.package'], {T3})
        self.assertEqual(len(next(pp for pp in p.packages.values() if pp.rel == 'trip/Triple.package').drop), 2)
        self.assertEqual(drops['del/Deleted.package'], {KD})
        # the unreadable packages are in the index with an error and never in a plan
        bad = [x for x in t.lib.packages() if x.rel.startswith('bad/')]
        self.assertEqual(len(bad), 2)
        self.assertTrue(all(x.err for x in bad))
        # high-bit instances survive the signed SQLite round trip in every structure
        self.assertIn(H2, p.check_keys)
        self.assertIn(H1, p.touched)
        json.dumps(dedup.report(p, t.lib), default=str)          # report of non-ASCII names serialises

    def test_apply_and_undo_odd_packages(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()
        r = t.apply(p)
        self.assertEqual((r['invariant']['changed'], r['invariant']['missing']), ([], []))
        self.assertEqual(r['skipped'], [])
        self.assertEqual(len(r['rewritten']), 7)
        d = t.data
        # constant-field indexes are rewritten as ordinary ones; the kept resource is bit-exact
        self.assertEqual(t.keys('flags', 'Flagged7.package'), [(F2, NONE)])
        self.assertEqual(t.keys('flags', 'Flagged3.package'), [(G2, NONE)])
        with Package(t.P('flags', 'Flagged3.package')) as pk:
            self.assertEqual(pk.read(pk.entries[0]), d[G2])
        # the deleted-flag entries stay as they were, the live dropped copy is gone
        self.assertEqual(t.keys('del', 'Deleted.package'), [(D2, ZLIB), (KD, DELETED), (DX, DELETED)])
        # one copy of the key held three times remains, in its place
        self.assertEqual(t.keys('trip', 'Triple.package'), [(T3, ZLIB), (TU, ZLIB)])
        # zero-byte resource that shared KA's offset is kept
        self.assertIn((Z0, NONE), t.keys('a', 'Early.package'))
        self.assertNotIn(KA, [k for k, _ in t.keys('a', 'Early.package')])
        # the merge lost the high-bit keys and its manifest no longer lists them
        self.assertEqual([k for k, _ in t.keys('sim', 'Merge.package')], [s4s.MANIFEST_KEY, MU])
        with Package(t.P('sim', 'Merge.package')) as pk:
            self.assertEqual(s4s.sources_of(s4s.read_payload(pk)), {'Own': {MU}})
        self.assertEqual([k for k, _ in t.keys('uni', UNI_NAME)], [UU])
        # the unreadable packages are untouched (bit-exact)
        now = tree_digest(t.sims)
        for rel in (os.path.join('Mods_parked', 'bad', 'Corrupt.package'), os.path.join('Mods_parked', 'bad', 'NotDBPF.package'),
                    os.path.join('Mods', 'cc', 'Keep.package')):
            self.assertEqual(now[rel], original[rel])
        # the game sees the same content for every key it could load, high-bit ones included
        em = effective_map(t.lib, ('Mods', 'Mods_parked'), [H1, H2, H3, KA, T3, UK, KD, Z2], cache_path=t.cache)
        self.assertEqual(em[H2], hashlib.blake2b(d[H2], digest_size=16).hexdigest())
        self.assertEqual(em[Z2], hashlib.blake2b(b'', digest_size=16).hexdigest())
        undo(r['journal'], home=t.home, check_game=False)
        self.assertEqual(tree_digest(t.sims), original)


class StreamedHashTests(unittest.TestCase):
    """The streamed path (resources bigger than the read window) must give the same hashes as the buffered one."""

    def setUp(self):
        self.t = Tree(build=False)
        t = self.t
        big = blob(77, 60000)
        self.items = {
            'zlib_vs_plain': (CASP, 0, 0xA0),
            'refpack_vs_plain': (CASP, 0, 0xA1),
            'unfinished_zlib': (CASP, 0, 0xA2),
            'corrupt_zlib': (CASP, 0, 0xA3),
            'conflict': (CASP, 0, 0xA4),
            'same_bytes': (CASP, 0, 0xA5),
        }
        k = self.items
        write(t.P('a', 'A.package'), [
            (k['zlib_vs_plain'], big, 'z'),
            (k['refpack_vs_plain'], refpack(big), ('raw', REFPACK, len(big))),
            (k['unfinished_zlib'], zlib_unfinished(big), ('raw', ZLIB, len(big))),
            (k['corrupt_zlib'], b'\x57' + bytes(random.Random(3).randbytes(5000)), ('raw', ZLIB, 9000)),
            (k['conflict'], big, 'z'),
            (k['same_bytes'], big, 'z')])
        write(t.P('b', 'B.package'), [
            (k['zlib_vs_plain'], big, 'u'), (k['refpack_vs_plain'], big, 'u'), (k['unfinished_zlib'], big, 'u'),
            (k['corrupt_zlib'], blob(5, 9000), 'u'), (k['conflict'], big[:-1] + b'!', 'z'), (k['same_bytes'], big, 'z')])
        t.lib.scan()

    def tearDown(self):
        self.t.close()

    def hashes(self, cache, **patch):
        with mock.patch.multiple(hashing, **(patch or {'THREADS': hashing.THREADS})):
            groups = hash_copies(self.t.lib, cache_path=cache)
        return ({k: [(c.pkg, c.raw, c.data, bool(c.err)) for c in cs] for k, cs in groups.items()},
                {k: key_status(cs) for k, cs in groups.items()})

    def test_streamed_equals_buffered(self):
        buffered, st1 = self.hashes(os.path.join(self.t.dir, 'h1.sqlite'))
        streamed, st2 = self.hashes(os.path.join(self.t.dir, 'h2.sqlite'), WINDOW=1000, CHUNK=333, GAP=10)
        self.assertEqual(buffered, streamed)
        self.assertEqual(st1, st2)
        k = self.items
        self.assertEqual(st1[k['zlib_vs_plain']], 'identical')
        self.assertEqual(st1[k['refpack_vs_plain']], 'identical')
        self.assertEqual(st1[k['unfinished_zlib']], 'identical')
        self.assertEqual(st1[k['corrupt_zlib']], 'undecidable')
        self.assertEqual(st1[k['conflict']], 'conflict')
        self.assertEqual(st1[k['same_bytes']], 'identical')


class ProtectionTests(unittest.TestCase):
    """include_merged=False may only unprotect S4S merges whose script link is a copy of a standalone companion."""

    def setUp(self):
        self.t = Tree(build=False)
        t = self.t
        man = lambda name: s4s.build_flat([(name, [(CASP, 0, 1)])])
        write(t.P('lib', 'Tool_Tuning.package'), [((TUN, 0, 1), blob(1), 'z')])
        for rel in ('sim/MA.package', 'sim/MB.package', 'sim/MW.package', 'sim/MC.package'):
            write(t.P(*rel.split('/')), [(s4s.MANIFEST_KEY, man(rel), 'z'), ((CASP, 0, 1), blob(2), 'z')])
        write(os.path.join(t.mods, 'anim', 'WW_Anims.package'), [(s4s.MANIFEST_KEY, man('x'), 'z'), ((CLIP, 0, 1), blob(3), 'z')])
        t.lib.scan()
        self.ids = {p.rel: p.id for p in t.lib.packages()}

    def tearDown(self):
        self.t.close()

    def companions_stub(self, fail=False):
        ids = self.ids
        kinds = {'lib/Tool_Tuning.package': 'core', 'sim/MA.package': 'addon', 'sim/MB.package': 'addon',
                 'sim/MW.package': 'weak', 'sim/MC.package': 'cc', 'anim/WW_Anims.package': 'addon'}
        sources = {ids['sim/MA.package']: ['Tool_Tuning'], ids['sim/MB.package']: ['Tool_Tuning', 'Other_Addon']}

        def classify(*a, **k):
            if fail:
                raise RuntimeError('no game folder')
            return {ids[rel]: Verdict(kind, None, []) for rel, kind in kinds.items()}
        return types.SimpleNamespace(classify=classify, script_bearing_sources=lambda *a, **k: dict(sources),
                                     never_merge=lambda v: v.kind in NEVER_MERGE)

    def protected(self, include_merged, fail=False, companions_json=None):
        with mock.patch.dict(sys.modules, {'speedkit.companions': self.companions_stub(fail)}), \
                mock.patch('speedkit.companions', self.companions_stub(fail), create=True):
            return default_protected(self.t.lib, include_merged=include_merged,
                                     companions_json=companions_json or os.path.join(self.t.dir, 'none.json'))

    def test_default_protects_all_companions(self):
        ids = self.ids
        got = self.protected(True)
        self.assertEqual(got, {ids[r] for r in ('lib/Tool_Tuning.package', 'sim/MA.package', 'sim/MB.package',
                                                'sim/MW.package', 'anim/WW_Anims.package')})

    def test_unprotect_merges_only_frees_stale_copies(self):
        ids = self.ids
        got = self.protected(False)
        self.assertIn(ids['lib/Tool_Tuning.package'], got)
        self.assertIn(ids['anim/WW_Anims.package'], got)     # a script add-on in its own right (no standalone twin)
        self.assertIn(ids['sim/MB.package'], got)            # carries Other_Addon, which exists nowhere else
        self.assertNotIn(ids['sim/MA.package'], got)         # its only script source is Tool_Tuning, kept standalone
        self.assertNotIn(ids['sim/MW.package'], got)         # weak link, no script-bearing source

    def test_unprotect_merges_without_classifier_frees_nothing(self):
        ids = self.ids
        js = os.path.join(self.t.dir, 'companions.json')
        with open(js, 'w', encoding='utf-8') as f:
            json.dump({'packages': [{'package': 'Mods_parked/sim/MA.package', 'verdict': 'companion'},
                                    {'package': 'Mods/anim/WW_Anims.package', 'verdict': 'companion'}]}, f)
        got = self.protected(False, fail=True, companions_json=js)
        self.assertTrue({ids['sim/MA.package'], ids['anim/WW_Anims.package']} <= got)


class ApplyGuardTests(unittest.TestCase):
    def setUp(self):
        self.t = Tree()

    def tearDown(self):
        self.t.close()

    def test_roots_without_common_sims_folder_refuse(self):
        t = self.t
        other = os.path.join(t.dir, 'elsewhere', 'Mods_parked')
        os.makedirs(os.path.dirname(other))
        shutil.move(t.parked, other)
        lib = Library(os.path.join(t.dir, 'lib2.sqlite'), {'Mods': t.mods, 'Mods_parked': other})
        try:
            lib.scan()
            p = plan(lib, protected=set(), cache_path=t.cache)
            self.assertTrue(p.packages)
            self.assertIsNone(dedup.sims_folder(lib))
            dry = apply(p, lib, cache_path=t.cache)           # a dry run still works
            self.assertTrue(dry['dry_run'])
            journal = mock.MagicMock(side_effect=AssertionError('a journal was created'))
            with mock.patch('speedkit.dedup.Journal', journal):
                with self.assertRaises(DedupError):
                    apply(p, lib, dry_run=False, check_game=False, cache_path=t.cache, min_free=0)
            journal.assert_not_called()
        finally:
            lib.close()

    def test_journal_home_inside_mods_is_refused(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()
        for home in (os.path.join(t.mods, 'SpeedKit'), os.path.join(t.parked, 'x', 'SpeedKit')):
            with self.assertRaises(DedupError):
                t.apply(p, journal_home=home)
            self.assertFalse(os.path.exists(home))
        self.assertEqual(tree_digest(t.sims), original)

    def test_failure_in_the_check_after_the_run_is_rolled_back(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()
        real = dedup._effective
        calls = [0]

        def flaky(*a, **k):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError('disk hiccup while checking')
            return real(*a, **k)
        with mock.patch('speedkit.dedup._effective', flaky):
            with self.assertRaises(DedupError) as cm:
                t.apply(p)
        self.assertIn('undone', str(cm.exception))
        self.assertEqual(tree_digest(t.sims), original)
        (jid, kind, state, n, note), = list_journals(t.home)
        self.assertEqual(state, 'undone')

    def test_ctrl_c_in_the_check_after_the_run_is_rolled_back(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()
        real = dedup._effective
        calls = [0]

        def interrupted(*a, **k):
            calls[0] += 1
            if calls[0] == 2:
                raise KeyboardInterrupt
            return real(*a, **k)
        with mock.patch('speedkit.dedup._effective', interrupted):
            with self.assertRaises(KeyboardInterrupt):
                t.apply(p)
        self.assertEqual(tree_digest(t.sims), original)

    def test_two_runs_in_the_same_second_keep_both_journals(self):
        t = self.t
        original = tree_digest(t.sims)
        frozen = types.SimpleNamespace(strftime=lambda fmt, *a: '20260101-000000')
        with mock.patch('speedkit.journal.time', frozen):
            p1 = t.plan()
            p1.packages = {k: v for k, v in p1.packages.items() if v.rel == 'sim/Merge.package'}
            r1 = t.apply(p1)
            t.lib.scan()
            p2 = t.plan()
            with self.assertRaises(DedupError):
                t.apply(p2)
        (jid, kind, state, n, note), = list_journals(t.home)
        self.assertEqual((jid, state, n), (r1['journal'], 'committed', 2))
        undo(r1['journal'], home=t.home, check_game=False)
        self.assertEqual(tree_digest(t.sims), original)

    def test_keeper_changed_after_a_rescan_is_refused(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()
        early = t.P('a', 'Early.package')                   # keeps H1-H3 for the merge
        os.utime(early, (1_000_000, 1_000_000))
        t.lib.scan()                                          # the index is current again, the plan is not
        with self.assertRaises(DedupError) as cm:
            t.apply(p)
        self.assertIn('changed since the plan', str(cm.exception))
        self.assertEqual(tree_digest(t.sims), original)
        self.assertFalse(os.path.exists(os.path.join(t.home, 'quarantine')))

    def test_failure_inside_journal_replace_is_rolled_back(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()
        real_put_new = dedup.Journal.put_new
        calls = [0]

        def put_new(self_, tmp, final):
            calls[0] += 1
            if calls[0] == 3:                # the third rewrite: its original is already quarantined
                raise OSError('disk full')
            return real_put_new(self_, tmp, final)
        with mock.patch.object(dedup.Journal, 'put_new', put_new):
            with self.assertRaises(DedupError) as cm:
                t.apply(p)
        self.assertIn('undone', str(cm.exception))
        self.assertEqual(tree_digest(t.sims), original)
        self.assertFalse([n for dp, dn, fn in os.walk(t.sims) for n in fn if dedup.TMP_SUFFIX in n])

    def test_read_only_package_is_skipped_when_the_quarantine_is_on_another_drive(self):
        t = self.t
        merge = t.P('sim', 'Merge.package')
        os.chmod(merge, stat.S_IREAD)              # 210 of the 627 real packages are read-only
        t.lib.scan()
        original = tree_digest(t.sims)
        p = t.plan()
        real_drive = dedup._drive

        def drive(path):                           # pretend the journal home is on another drive (X:)
            return 'X:' if dedup._inside(path, t.home) else real_drive(path)
        with mock.patch('speedkit.dedup._drive', drive):
            fs = dedup.free_space(p, t.lib, min_free=0, journal_home=t.home)
            self.assertEqual(fs['one_run_with_current_free_space']['skipped_read_only_across_drives'], 1)
            r = t.apply(p)
        why = dict(r['skipped'])
        self.assertIn('read-only', why['Mods_parked/sim/Merge.package'])
        self.assertEqual(len(r['rewritten']), 6)
        self.assertEqual(r['invariant']['changed'], [])
        self.assertEqual(tree_digest(t.sims)[os.path.join('Mods_parked', 'sim', 'Merge.package')],
                         original[os.path.join('Mods_parked', 'sim', 'Merge.package')])
        undo(r['journal'], home=t.home, check_game=False)
        self.assertEqual(tree_digest(t.sims), original)
        # on the same drive a read-only original is simply renamed into the quarantine
        t.lib.scan()
        r2 = t.apply(t.plan())
        self.assertIn('Mods_parked/sim/Merge.package', r2['rewritten'])
        undo(r2['journal'], home=t.home, check_game=False)
        self.assertEqual(tree_digest(t.sims), original)

    def test_disk_full_while_closing_the_new_file_leaves_no_temp_file(self):
        t = self.t
        original = tree_digest(t.sims)
        p = t.plan()

        def close(self_):                         # the index write fails after the resources were written
            self_.f.close()
            raise OSError(28, 'No space left on device')
        with mock.patch.object(dedup.PackageWriter, 'close', close):
            with self.assertRaises(DedupError):
                t.apply(p)
        self.assertEqual(tree_digest(t.sims), original)
        self.assertFalse([n for dp, dn, fn in os.walk(t.sims) for n in fn if dedup.TMP_SUFFIX in n])

    def test_unreadable_manifest_is_kept_as_it_is(self):
        t = self.t
        bad_manifest = b'\x57' + bytes(random.Random(9).randbytes(300))
        write(t.P('sim', 'BadMan.package'), [(s4s.MANIFEST_KEY, bad_manifest, ('raw', ZLIB, 900)),
                                            (H1, t.data[H1], 'z'), (MU, blob(4242), 'z')])
        t.lib.scan()
        original = tree_digest(t.sims)
        p = t.plan()
        r = t.apply(p)
        self.assertIn('Mods_parked/sim/BadMan.package', r['rewritten'])
        with Package(t.P('sim', 'BadMan.package')) as pk:
            self.assertEqual([key_of(e) for e in pk.entries], [s4s.MANIFEST_KEY, MU])
            self.assertEqual(pk.raw(pk.entries[0]), bad_manifest)
        undo(r['journal'], home=t.home, check_game=False)
        self.assertEqual(tree_digest(t.sims), original)

    def test_script_added_after_planning_is_refused(self):
        t = self.t
        p = t.plan()
        with open(t.P('sim', 'NewMod.ts4script'), 'wb') as f:     # Merge.package is now next to a script
            f.write(b'PK\x05\x06' + b'\0' * 18)
        original = tree_digest(t.sims)
        with self.assertRaises(DedupError) as cm:
            t.apply(p)
        self.assertIn('NewMod.ts4script', str(cm.exception))
        self.assertEqual(tree_digest(t.sims), original)
        t.lib.scan()
        self.assertIn(t.pkg('sim/Merge.package').id, default_protected(t.lib, source=None))

    def test_same_package_in_both_roots_is_refused(self):
        t = self.t
        os.makedirs(os.path.join(t.mods, 'a'))
        shutil.copy2(t.P('a', 'Early.package'), os.path.join(t.mods, 'a', 'EARLY.package'))
        t.lib.scan()
        p = t.plan()
        self.assertEqual(dedup.report(p, t.lib)['in_more_than_one_root'], ['a/early.package'])
        original = tree_digest(t.sims)
        with self.assertRaises(DedupError) as cm:
            t.apply(p)
        self.assertIn('more than one', str(cm.exception))
        self.assertEqual(tree_digest(t.sims), original)

    def test_leftover_temp_file_stops_the_run_and_is_left_alone(self):
        t = self.t
        p = t.plan()
        merge = t.P('sim', 'Merge.package')
        with open(merge + dedup.TMP_SUFFIX, 'wb') as f:
            f.write(b'someone else')
        original = tree_digest(t.sims)
        with self.assertRaises(DedupError) as cm:
            t.apply(p)
        self.assertIn('in the way', str(cm.exception))
        self.assertEqual(tree_digest(t.sims), original)      # rolled back; the foreign file is untouched


if __name__ == '__main__':
    unittest.main(verbosity=2)

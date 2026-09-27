"""speedkit.api's merge_plan / merge_apply (docs\\hub_contract.md): the Hub's own engine functions driven on
the same fake tree test_merge.py builds (a COPY under a temp folder; nothing under the real Sims 4 folder is
touched). Checks the plain-word plan, that apply really merges and can be undone, and the game-running guard."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from speedkit import api                                    # noqa: E402
from speedkit.companions import Verdict                      # noqa: E402
from speedkit.library import DEFAULT_RESOURCE_CFG            # noqa: E402
import test_merge as TM                                      # noqa: E402

INSIDE_WORDS = ('package', 'quarantine', 'journal', 'CASP', 'packages', 'merged files', 'dedup', 'policy', 'park ')


def assert_plain(test, text):
    low = text.lower()
    for w in INSIDE_WORDS:
        test.assertNotIn(w.lower(), low, '%r found in %r' % (w, text))


def _verdicts_for(kinds):
    """Recomputed against whatever lib api.py's own connection scans (like test_fastmode.verdicts_for): package
    ids are not shared with the Tree's own Library object, only relative paths are."""
    def fn(lib):
        return {p.id: Verdict(kinds.get(p.rel, 'cc'), 'scripts/Fake.ts4script' if kinds.get(p.rel) == 'core' else None, [])
                for p in lib.packages()}
    return fn


class MergeApiTests(unittest.TestCase):
    def setUp(self):
        self.t = TM.Tree()
        api.reset()
        api.configure(sims=self.t.sims, db_path=os.path.join(self.t.dir, 'api_library.sqlite'),
                     hash_cache=self.t.cache, companions_cache=os.path.join(self.t.dir, 'api_companions.sqlite'),
                     check_game=False, verdicts=_verdicts_for(self.t.kinds))

    def tearDown(self):
        api.reset()
        self.t.close()

    def test_plan_reports_plain_numbers_and_reasons(self):
        r = api.merge_plan()
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['groups'], 3)                   # CAS, Sliders (parked), Tuning (parked) - see test_merge.Tree
        self.assertGreater(r['files'], r['groups'])
        self.assertGreaterEqual(r['seconds_low'], 0)
        self.assertGreaterEqual(r['seconds_high'], r['seconds_low'])
        self.assertTrue(r['left_alone'])
        assert_plain(self, r['message'])
        for row in r['left_alone']:
            self.assertIn('files', row)
            self.assertIn('label', row)
            assert_plain(self, row['label'])

    def test_plan_is_read_only(self):
        before = TM.tree_digest(self.t.sims)
        api.merge_plan()
        self.assertEqual(before, TM.tree_digest(self.t.sims))

    def test_apply_merges_and_undo_restores_everything(self):
        before = TM.tree_digest(self.t.sims, skip=('SpeedKit',))
        r = api.merge_apply()
        self.assertTrue(r['ok'], r)
        self.assertTrue(r.get('journal'))
        assert_plain(self, r['message'])
        self.assertTrue(os.path.isfile(os.path.join(self.t.mods, 'SpeedKit Merged', 'CAS_001.package')))
        self.assertFalse(os.path.isfile(self.t.m('CC', 'hairA.package')))         # merged away
        self.assertFalse(os.path.isfile(self.t.m('CC', 'hairB.package')))
        u = api.undo_last()
        self.assertTrue(u['ok'], u)
        after = TM.tree_digest(self.t.sims, skip=('SpeedKit',))
        self.assertEqual(before, after)                    # every file is back exactly as it was

    def test_apply_refuses_while_the_game_runs(self):
        orig = api._game_running
        api._game_running = lambda: True
        try:
            r = api.merge_apply()
        finally:
            api._game_running = orig
        self.assertFalse(r['ok'])
        self.assertIn('Sims 4 is running', r['message'])
        self.assertIsNone(r['journal'])
        # nothing was touched
        self.assertTrue(os.path.isfile(self.t.m('CC', 'hairA.package')))

    def test_nothing_to_merge_is_a_plain_ok_message(self):
        # a Mods folder with nothing loose in it: the plan has zero groups, and both tasks still answer cleanly
        d = tempfile.mkdtemp(dir=TM.BASE)
        sims = os.path.join(d, 'The Sims 4')
        os.makedirs(os.path.join(sims, 'Mods'))
        with open(os.path.join(sims, 'Mods', 'Resource.cfg'), 'w') as f:
            f.write('\n'.join(DEFAULT_RESOURCE_CFG) + '\n')
        try:
            api.configure(sims=sims, db_path=os.path.join(d, 'api_library2.sqlite'),
                         hash_cache=os.path.join(d, 'hash2.sqlite'), companions_cache=os.path.join(d, 'companions2.sqlite'))
            r = api.merge_plan()
            self.assertTrue(r['ok'], r)
            self.assertEqual(r['groups'], 0)
            self.assertIn('Nothing can be merged', r['message'])
            r2 = api.merge_apply()
            self.assertTrue(r2['ok'], r2)
            self.assertIsNone(r2['journal'])
        finally:
            TM.rmtree(d)


if __name__ == '__main__':
    unittest.main()

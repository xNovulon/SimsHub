"""Load-time savings (speedkit/loadstats.py through speedkit/api.py): SpeedKit Monitor's loadtimes.csv summed up
per start and per mode, with honest wording when there is too little data. Cross-platform, temp folders."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api, loadstats as LS  # noqa: E402
from tests import care_fakes as F  # noqa: E402


class LoadTimes(unittest.TestCase):
    def setUp(self):
        self.root, self.sims = F.make_sims()
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'library.sqlite'), check_game=False)

    def tearDown(self):
        api.reset()
        F.cleanup(self.root)

    def test_one_entry_per_start(self):
        p = F.write_loadtimes(self.sims, [('2026-09-20 18:00:00', 'full', 2400.0, 180.0),
                                          ('2026-09-21 18:00:00', 'fast', 170.0, 30.0)])
        starts = LS.read_starts(p)
        self.assertEqual(len(starts), 2)                     # 4 rows each: one start
        self.assertEqual(starts[0]['menu_s'], 2400.0)
        self.assertEqual(starts[0]['lot_s'], 180.0)          # the first lot, not the second one
        self.assertEqual(starts[0]['total_s'], 2580.0)

    def test_nothing_yet(self):
        r = api.load_savings()
        self.assertTrue(r['ok'])
        self.assertEqual(r['confidence'], 'none')
        self.assertIn('No start times recorded yet', r['message'])

    def test_only_one_mode(self):
        F.write_loadtimes(self.sims, [('2026-09-20 18:00:00', 'full', 2400.0, 180.0)])
        r = api.load_savings()
        self.assertEqual(r['confidence'], 'one_mode')
        self.assertIsNone(r['saved_s'])
        self.assertIn('Full Start: 43 min', r['message'])
        self.assertIn('Start once with Quick Start to compare', r['message'])
        F.write_loadtimes(self.sims, [('2026-09-20 18:00:00', 'fast', 170.0, 10.0)])
        r = api.load_savings()
        self.assertIn('Start once with Full Start to compare', r['message'])

    def test_few_starts_are_said_to_be_few(self):
        F.write_loadtimes(self.sims, [('2026-09-20 18:00:00', 'full', 2400.0, 180.0),
                                      ('2026-09-21 18:00:00', 'fast', 170.0, 10.0)])
        r = api.load_savings()
        self.assertEqual(r['confidence'], 'low')
        self.assertEqual(r['saved_s'], 2400.0)
        self.assertIn('Quick Start: 3 min - Full Start: 43 min (about 40 min less per start)', r['message'])
        self.assertIn('only a few starts', r['message'])

    def test_medians_and_total_saved(self):
        starts = [('2026-09-%02d 18:00:00' % (i + 1), 'full', 2400.0 + i * 10, 200.0) for i in range(3)]
        starts += [('2026-09-%02d 20:00:00' % (i + 1), 'fast', 160.0 + i * 10, 20.0) for i in range(3)]
        starts += [('2026-09-10 20:00:00', 'fast', 9000.0, 20.0)]           # one very slow start (a patch)
        starts += [('2026-09-11 20:00:00', 'save', 150.0, 18.0), ('2026-09-12 20:00:00', 'lean', 60.0, None)]
        F.write_loadtimes(self.sims, starts)
        r = api.load_savings()
        self.assertEqual(r['confidence'], 'ok')
        self.assertEqual(r['modes']['full']['starts'], 3)
        self.assertEqual(r['modes']['full']['total_s'], 2610.0)
        self.assertEqual(r['modes']['fast']['total_s'], 195.0)              # the median: not skewed by 9000 s
        self.assertEqual(r['modes']['studio']['starts'], 1)
        self.assertEqual(r['compare'], 'fast')
        self.assertEqual(r['saved_s'], 2415.0)
        self.assertGreater(r['saved_total_s'], 3 * 2400)
        self.assertNotIn('few starts', r['message'])

    def test_fast_is_not_quicker(self):
        F.write_loadtimes(self.sims, [('2026-09-20 18:00:00', 'full', 100.0, 10.0),
                                      ('2026-09-21 18:00:00', 'fast', 200.0, 10.0)])
        self.assertIn('has not been quicker', api.load_savings()['message'])


if __name__ == '__main__':
    unittest.main()

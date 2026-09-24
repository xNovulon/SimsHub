"""The Hub server's routes for "CC that may need a Sims 4 Studio fix" (care_routes.py): GET /api/batchfix, POST
/api/batchfix/open, the task batch_fix_scan and set_aside with why "fix" - against the example-data stub and end to
end against the real engine on a fake Sims 4 folder (cross-platform)."""
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api  # noqa: E402
from speedkit.hub import stub_api  # noqa: E402
from tests import care_fakes as F  # noqa: E402
from tests.batchfix_fakes import casp, hotc, package, T_CASP, T_HOTC, CC_ID  # noqa: E402
from tests.test_care_server import Base  # noqa: E402


class WithStub(Base):
    def setUp(self):
        stub_api.reset()
        stub_api.DELAY = 0.002
        stub_api.HOLD, stub_api.HOLD_AT = None, 0
        self.start(stub_api)
        self.addCleanup(stub_api.reset)

    def test_read_open_scan_and_set_aside(self):
        code, r = self.req('GET', '/api/batchfix')
        self.assertEqual(code, 200)
        self.assertTrue(r['ok'])
        self.assertEqual(len(r['fixes']), 5)
        tank = 'Clothes/Tops/Basic_Tank_Top.package'
        code, o = self.req('POST', '/api/batchfix/open', {'rel': tank})
        self.assertEqual((code, o['ok']), (200, True))
        for bad in ({'rel': '../x'}, {'rel': 'C:\\x.package'}, {}, {'rel': 5}):
            code, o = self.req('POST', '/api/batchfix/open', bad)
            self.assertEqual((code, o['ok']), (200, False), bad)
        v = self.run_task('batch_fix_scan')
        self.assertEqual(v['state'], 'done', v)
        self.assertTrue(v['progress'])
        v = self.run_task('set_aside', {'rels': [tank], 'why': 'fix'})
        self.assertEqual(v['state'], 'done', v)
        _, r = self.req('GET', '/api/batchfix')                  # the task dropped the cached answer
        nude = next(f for f in r['fixes'] if f['id'] == 'nude_default')
        self.assertEqual(nude['set_aside'], 1)
        _, p = self.req('GET', '/api/patchday')
        self.assertIn(tank, [h['rel'] for h in p['set_aside']])
        self.assertEqual(p['batch_fixes']['files'], 9)
        for action, args in (('batch_fix_scan', {'x': 1}), ('set_aside', {'rels': [tank], 'why': 'later'})):
            code, r = self.req('POST', '/api/task', {'action': action, 'args': args})
            self.assertEqual(code, 400, (action, args, r))

    def test_read_waits_for_a_running_change(self):
        stub_api.HOLD = threading.Event()
        code, _ = self.req('POST', '/api/task', {'action': 'batch_fix_scan', 'args': {}})
        self.assertEqual(code, 200)
        try:
            _, r = self.req('GET', '/api/batchfix')
            self.assertTrue(r.get('busy'))
            self.assertIn('checking your CC for Sims 4 Studio fixes', r['message'])
            self.assertEqual(r['fixes'], [])
        finally:
            stub_api.HOLD.set()


class WithEngine(Base):
    def setUp(self):
        self.root, self.sims = F.make_sims('bf_srv_')
        self.addCleanup(F.cleanup, self.root)
        self.addCleanup(api.reset)
        self.opened = []
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'data', 'library.sqlite'), check_game=False,
                      opener=self.opened.append)
        package(os.path.join(self.sims, 'Mods', 'Sliders', 'nose.package'), [(T_HOTC, CC_ID, hotc(0x0E))])
        package(os.path.join(self.sims, 'Mods', 'Eyes', 'eyes.package'),
                [(T_CASP, CC_ID, casp(body_type=35, age_gender=0x307E))])
        self.start(api)

    def test_end_to_end(self):
        _, r = self.req('GET', '/api/batchfix')
        self.assertIsNone(r['scanned'])
        v = self.run_task('batch_fix_scan')
        self.assertEqual(v['state'], 'done', v)
        self.assertEqual(v['result']['found'], 2)
        _, r = self.req('GET', '/api/batchfix')
        self.assertEqual([f['id'] for f in r['fixes']], ['sliders_werewolf', 'eyes_infants'])
        code, o = self.req('POST', '/api/batchfix/open', {'rel': 'Eyes/eyes.package'})
        self.assertTrue(o['ok'], o)
        self.assertEqual(self.opened, [os.path.join(self.sims, 'Mods', 'Eyes')])
        v = self.run_task('set_aside', {'rels': ['Eyes/eyes.package'], 'why': 'fix'})
        self.assertEqual(v['state'], 'done', v)
        self.assertTrue(os.path.isfile(os.path.join(self.sims, 'Mods_parked', 'Eyes', 'eyes.package')))
        _, r = self.req('GET', '/api/batchfix')
        eyes = next(f for f in r['fixes'] if f['id'] == 'eyes_infants')
        self.assertEqual(eyes['set_aside'], 1)
        _, st = self.req('GET', '/api/status')
        self.assertEqual(st['journals'][0]['title'], 'Set CC aside until it gets a Sims 4 Studio fix')
        self.assertEqual(self.run_task('undo_last')['state'], 'done')
        self.assertTrue(os.path.isfile(os.path.join(self.sims, 'Mods', 'Eyes', 'eyes.package')))


if __name__ == '__main__':
    unittest.main()

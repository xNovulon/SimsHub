"""The Hub server's patch-day / game-error / save-backup / load-time routes (speedkit/hub/care_routes.py): against
the example-data stub, and end to end against the real engine on a fake Sims 4 folder (cross-platform)."""
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from speedkit import api  # noqa: E402
from speedkit.hub import server, stub_api  # noqa: E402
from tests import care_fakes as F  # noqa: E402


class Base(unittest.TestCase):
    engine = None

    def start(self, engine):
        self.httpd = server.make_server(0, api=engine, log_path=os.path.join(tempfile.mkdtemp(prefix='hubcare_'), 'hub.log'),
                                        opener=lambda p: {'ok': True, 'message': 'opened'})
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.host = '127.0.0.1:%d' % self.httpd.port

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection('127.0.0.1', self.httpd.port, timeout=20)
        try:
            h = {'Host': self.host}
            data = None
            if body is not None:
                data = json.dumps(body).encode()
                h['Content-Type'] = 'application/json'
            c.request(method, path, body=data, headers=h)
            r = c.getresponse()
            return r.status, json.loads(r.read() or b'{}')
        finally:
            c.close()

    def run_task(self, action, args=None):
        code, r = self.req('POST', '/api/task', {'action': action, 'args': args or {}})
        self.assertEqual(code, 200, r)
        for _ in range(400):
            code, v = self.req('GET', '/api/task/' + r['task'])
            if v.get('state') != 'running':
                return v
            time.sleep(0.02)
        self.fail('the task did not finish')


class WithStub(Base):
    def setUp(self):
        stub_api.reset()
        stub_api.DELAY = 0.002
        stub_api.HOLD, stub_api.HOLD_AT = None, 0
        self.start(stub_api)
        self.addCleanup(stub_api.reset)

    def test_reads(self):
        for route, key in (('patchday', 'older'), ('errors', 'errors'), ('save_health', 'backups'),
                           ('load_savings', 'modes')):
            code, r = self.req('GET', '/api/' + route)
            self.assertEqual(code, 200, route)
            self.assertTrue(r['ok'], route)
            self.assertIn(key, r)

    def test_seen(self):
        self.assertTrue(self.req('GET', '/api/patchday')[1]['game']['updated'])
        code, r = self.req('POST', '/api/patchday/seen', {})
        self.assertEqual((code, r['ok']), (200, True))
        self.assertFalse(self.req('GET', '/api/patchday')[1]['game']['updated'])      # the cached answer is dropped
        code, r = self.req('POST', '/api/errors/seen', {})
        self.assertEqual(code, 200)
        self.assertFalse(any(g['new'] for g in self.req('GET', '/api/errors')[1]['errors']))

    def test_tasks_and_their_details(self):
        v = self.run_task('set_aside', {'rels': ['MCCC/mc_cmd_center.ts4script'], 'why': 'patch'})
        self.assertEqual(v['state'], 'done', v)
        self.assertEqual(v['result']['moved'], ['MCCC/mc_cmd_center.ts4script', 'MCCC/mc_cmd_center.package'])
        held = [h['rel'] for h in self.req('GET', '/api/patchday')[1]['set_aside']]
        self.assertIn('MCCC/mc_cmd_center.ts4script', held)
        self.assertEqual(self.run_task('put_back', {'rels': ['MCCC/mc_cmd_center.ts4script']})['state'], 'done')
        b = self.run_task('backup_saves')
        self.assertEqual(b['state'], 'done')
        self.assertEqual(self.run_task('restore_saves', {'backup': b['result']['backup']})['state'], 'done')
        _, st = self.req('GET', '/api/status')
        self.assertEqual(st['journals'][0]['kind'], 'saves')
        for action, args in (('set_aside', {}), ('set_aside', {'rels': []}), ('set_aside', {'rels': ['../x']}),
                             ('set_aside', {'rels': ['C:\\x.ts4script']}), ('set_aside', {'rels': ['a'], 'why': 'x'}),
                             ('put_back', {'rels': 'a'}), ('restore_saves', {'backup': '../../x'}),
                             ('restore_saves', {}), ('backup_saves', {'x': 1})):
            code, r = self.req('POST', '/api/task', {'action': action, 'args': args})
            self.assertEqual(code, 400, (action, args, r))

    def test_reads_wait_for_a_running_change(self):
        self.req('GET', '/api/save_health')                   # something to show while busy
        stub_api.HOLD = threading.Event()
        code, r = self.req('POST', '/api/task', {'action': 'backup_saves', 'args': {}})
        self.assertEqual(code, 200)
        try:
            code, busy = self.req('POST', '/api/task', {'action': 'set_aside', 'args': {'rels': ['a.ts4script']}})
            self.assertEqual(code, 409)
            self.assertIn('backing up your saves', busy['message'])
            _, h = self.req('GET', '/api/save_health')
            self.assertTrue(h['ok'])                          # the last answer
            _, e = self.req('GET', '/api/errors')
            self.assertTrue(e.get('busy'))                    # never read before: 'busy'
        finally:
            stub_api.HOLD.set()


class WithEngine(Base):
    """The real speedkit.api on a fake Sims 4 folder."""

    def setUp(self):
        self.root, self.sims = F.make_sims()
        self.addCleanup(F.cleanup, self.root)
        self.addCleanup(api.reset)
        t = F.now() - 2 * F.DAY
        game = F.make_game(self.root, t)
        api.configure(sims=self.sims, db_path=os.path.join(self.root, 'library.sqlite'), check_game=False,
                      game={'exe': os.path.join(game, 'Game', 'Bin', 'TS4_x64.exe'), 'game_dir': game, 'store': 'ea',
                            'source': 'test'})
        F.make_script(os.path.join(self.sims, 'Mods', 'MCCC', 'mc_cmd_center.ts4script'),
                      ['mc_cmd_center/mc_utils/mc_zone.pyc'], t - 30 * F.DAY)
        F.write_last_exception(self.sims)
        F.make_save(self.sims, 0x14, 5000)
        F.write_loadtimes(self.sims, [('2026-09-20 18:00:00', 'full', 2400.0, 180.0)])
        self.start(api)

    def test_end_to_end(self):
        _, p = self.req('GET', '/api/patchday')
        self.assertEqual([o['rel'] for o in p['older']], ['MCCC/mc_cmd_center.ts4script'])
        _, e = self.req('GET', '/api/errors')
        self.assertTrue(any(g['mod'] and g['mod']['name'] == 'MCCC' for g in e['errors']))
        _, s = self.req('GET', '/api/load_savings')
        self.assertEqual(s['confidence'], 'one_mode')
        v = self.run_task('set_aside', {'rels': ['MCCC/mc_cmd_center.ts4script'], 'why': 'patch'})
        self.assertEqual(v['state'], 'done', v)
        self.assertTrue(os.path.isfile(os.path.join(self.sims, 'Mods_parked', 'MCCC', 'mc_cmd_center.ts4script')))
        _, p = self.req('GET', '/api/patchday')                # the task dropped the cached answer
        self.assertEqual(p['older'], [])
        self.assertEqual(p['set_aside'][0]['rel'], 'MCCC/mc_cmd_center.ts4script')
        _, h = self.req('GET', '/api/save_health')
        self.assertEqual(h['backups'][0]['reason'], 'before setting mods aside')
        v = self.run_task('undo_last')
        self.assertEqual(v['state'], 'done', v)
        self.assertTrue(os.path.isfile(os.path.join(self.sims, 'Mods', 'MCCC', 'mc_cmd_center.ts4script')))


if __name__ == '__main__':
    unittest.main()

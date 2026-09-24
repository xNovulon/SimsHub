"""The CC browser through the Hub's server: the /api/cc routes, pictures as image bytes, a save's CC, the 'cc_scan' and
'cc_set_aside' tasks - against the example-data stub and against the real engine on a fake Sims 4 folder
(test_ccbrowser.make_world). Each test starts its own server on a free port (never 8765/8766); cross-platform."""
import io
import os
import shutil
import sys
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from test_hub_server import Base  # noqa: E402
import test_ccbrowser as TC  # noqa: E402
from speedkit import api  # noqa: E402
from speedkit.hub import server, stub_api  # noqa: E402

PNG = b'\x89PNG\r\n\x1a\n'


class StubRoutes(Base):
    def test_list_filters_and_pages(self):
        code, h, r = self.get('/api/cc?facets=1')
        self.assertEqual(code, 200)
        self.assertEqual(h['cache-control'], 'no-store')
        self.assertTrue(r['ok'])
        self.assertEqual(r['index']['state'], 'ready')
        self.assertEqual(len(r['items']), 60)
        self.assertGreater(r['total'], 200)
        self.assertIn({'key': 'hair', 'label': 'Hair', 'n': 46}, r['categories'])
        self.assertTrue(r['folders'] and r['creators'])
        hair = self.get('/api/cc?category=hair&limit=200')[2]
        self.assertEqual(hair['total'], 46)
        self.assertTrue(all(i['category'] == 'hair' for i in hair['items']))
        q = self.get('/api/cc?q=braids&category=hair')[2]
        self.assertTrue(q['total'] and all('braids' in i['name'].lower() for i in q['items']))
        p2 = self.get('/api/cc?offset=60&limit=60')[2]
        self.assertEqual(p2['offset'], 60)
        self.assertFalse({i['id'] for i in p2['items']} & {i['id'] for i in r['items']})
        self.assertEqual(self.get('/api/cc?flag=duplicate')[2]['total'], 6)
        self.assertEqual(self.get('/api/cc?flag=broken')[2]['total'], 2)
        unused = self.get('/api/cc?used=unused&limit=200')[2]
        self.assertTrue(all(i['used'] is False for i in unused['items']))

    def test_bad_filters(self):
        for q in ('used=maybe', 'flag=x', 'sort=weird', 'category=Hair!', 'offset=x', 'q=' + 'a' * 300):
            code, _, r = self.get('/api/cc?' + q)
            self.assertEqual(code, 400, q)
            self.assertFalse(r['ok'])
        self.assertEqual(self.get('/api/cc/item/abc')[0], 404)
        self.assertEqual(self.get('/api/cc/pic/cas/XYZ')[0], 404)
        self.assertEqual(self.get('/api/cc/pic/shoes/0123')[0], 404)

    def test_pictures(self):
        r = self.get('/api/cc?category=hair')[2]
        it = next(i for i in r['items'] if i['pic'])
        code, h, data = self.get('/api/cc/thumb/%d?v=%s' % (it['id'], it['pic']))
        self.assertEqual(code, 200)
        self.assertEqual(h['content-type'], 'image/png')
        self.assertIn('max-age', h['cache-control'])
        self.assertTrue(data.startswith(PNG))
        none = next(i for i in self.get('/api/cc?category=gameplay')[2]['items'] if not i['pic'])
        code, _, r = self.get('/api/cc/thumb/%d' % none['id'])
        self.assertEqual(code, 404)
        self.assertEqual(self.get('/api/cc/thumb/999999')[0], 404)

    def test_item_and_open(self):
        it = self.get('/api/cc')[2]['items'][0]
        code, _, d = self.get('/api/cc/item/%d' % it['id'])
        self.assertEqual(code, 200)
        self.assertTrue(d['ok'])
        self.assertIn('Mods', d['path'])
        code, _, o = self.post('/api/cc/open', {'id': it['id']})
        self.assertEqual(code, 200)
        self.assertTrue(o['ok'])
        self.assertEqual(self.post('/api/cc/open', {'id': 'x'})[0], 400)
        self.assertEqual(self.post('/api/cc/open', {'id': True})[0], 400)
        self.assertEqual(self.post('/api/cc/nothing', {})[0], 404)

    def test_save_cc(self):
        code, _, r = self.get('/api/saves/Slot_00000003/cc')
        self.assertEqual(code, 200)
        self.assertTrue(r['ok'])
        self.assertEqual(r['counts']['missing'], 37)
        self.assertTrue(r['files'] and r['households'])
        miss = r['missing'][0]
        self.assertRegex(miss['key'], r'^[0-9A-F]{8}:00000000:[0-9A-F]{16}$')
        f = next(f for f in r['files'] if f['pic'])
        code, h, data = self.get('/api/cc/pic/%s/%s' % (f['pic']['kind'], f['pic']['id']))
        self.assertEqual(code, 200)
        self.assertTrue(data.startswith(PNG))
        self.assertTrue(self.get('/api/saves/tray/cc')[2]['ok'])
        self.assertFalse(self.get('/api/saves/Slot_DEADBEEF/cc')[2]['ok'])
        self.assertEqual(self.get('/api/saves/..%2F..%2Fx/cc')[0], 400)

    def test_save_cc_waits_for_other_tasks_but_not_the_cc_scan(self):
        stub_api.HOLD = threading.Event()
        self.post('/api/task', {'action': 'report', 'args': {}})
        r = self.get('/api/saves/Slot_00000014/cc')[2]
        self.assertTrue(r['busy'])
        self.assertIn('busy', r['message'])
        stub_api.HOLD.set()
        self.wait(self.get('/api/task/current')[2]['id'])
        stub_api.HOLD = threading.Event()
        code, _, t = self.post('/api/task', {'action': 'cc_scan', 'args': {}})
        self.assertEqual(code, 200)
        self.assertTrue(self.get('/api/saves/Slot_00000014/cc')[2]['ok'])
        self.assertTrue(self.get('/api/cc')[2]['ok'])              # the list answers during any task
        stub_api.HOLD.set()
        done = self.wait(t['task'])
        self.assertEqual(done['state'], 'done')
        self.assertIn('Sorted', done['result']['message'])

    def test_cc_scan_keeps_the_saves_cache(self):
        self.get('/api/saves')
        self.assertIn('saves', self.httpd.hub._cache)
        t = self.post('/api/task', {'action': 'cc_scan', 'args': {}})[2]['task']
        self.wait(t)
        self.assertIn('saves', self.httpd.hub._cache)

    def test_set_aside_task_and_undo(self):
        items = [i for i in self.get('/api/cc?category=top')[2]['items'] if i['in_mods']]
        ids = [items[0]['id'], items[1]['id']]
        total = self.get('/api/cc')[2]['total']
        for bad in ({}, {'ids': []}, {'ids': ['1']}, {'ids': [True]}, {'ids': list(range(1, 600))}, {'ids': [1], 'x': 1}):
            code, _, r = self.post('/api/task', {'action': 'cc_set_aside', 'args': bad})
            self.assertEqual(code, 400, bad)
        code, _, t = self.post('/api/task', {'action': 'cc_set_aside', 'args': {'ids': ids}})
        self.assertEqual(code, 200)
        v = self.wait(t['task'])
        self.assertEqual(v['state'], 'done', v)
        self.assertEqual(len(v['result']['done']), 2)
        self.assertEqual(self.get('/api/cc')[2]['total'], total - 2)
        st = self.get('/api/status?refresh=1')[2]
        self.assertEqual(st['journals'][0]['kind'], 'setaside')
        v = self.wait(self.post('/api/task', {'action': 'undo_last', 'args': {}})[2]['task'])
        self.assertEqual(v['state'], 'done')
        self.assertEqual(self.get('/api/cc')[2]['total'], total)

    def test_set_aside_refused_while_the_game_runs(self):
        stub_api.STATE['game_running'] = True
        it = [i for i in self.get('/api/cc?category=top')[2]['items'] if i['in_mods']][0]
        v = self.wait(self.post('/api/task', {'action': 'cc_set_aside', 'args': {'ids': [it['id']]}})[2]['task'])
        self.assertEqual(v['state'], 'failed')
        self.assertIn('running', v['result']['message'])

    def test_old_engine_without_the_cc_browser(self):
        class Old:
            PREVIEW = False

            @staticmethod
            def status():
                return {'ok': True}
        httpd = server.make_server(0, api=Old, log_path=self.log)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            old_port, self.port = self.port, httpd.port
            old_host, self.host = self.host, '127.0.0.1:%d' % httpd.port
            code, _, r = self.get('/api/cc')
            self.assertEqual(code, 200)
            self.assertFalse(r['ok'])
            self.assertEqual(r['message'], server.NOT_READY)
            self.assertEqual(self.get('/api/cc/thumb/1')[0], 404)
        finally:
            self.port, self.host = old_port, old_host
            httpd.shutdown()
            httpd.server_close()


@unittest.skipIf(TC.Image is None, 'Pillow is not installed')
class EngineRoutes(Base):
    """The same routes with the real engine (speedkit/api.py) on a fake Sims 4 folder."""
    api = api

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='cchub_')
        self.sims = TC.make_world(self.root)
        data = os.path.join(self.root, 'data')
        api.configure(sims=self.sims, db_path=os.path.join(data, 'library.sqlite'), refs_db=os.path.join(data, 'refs.sqlite'),
                      game_ids_db=os.path.join(data, 'ids.sqlite'), check_game=False, game_clues=TC.NO_GAME,
                      remember_game=False, opener=lambda p: None, companions_cache=os.path.join(data, 'comp.json'))
        api._CC_PICS.clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        api.reset()
        api._CC_PICS.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_scan_list_picture_save(self):
        r = self.get('/api/cc')[2]
        self.assertEqual(r['index']['state'], 'missing')
        self.assertIn('Sort CC files', r['message'])
        v = self.wait(self.post('/api/task', {'action': 'cc_scan', 'args': {}})[2]['task'], timeout=60)
        self.assertEqual(v['state'], 'done', v)
        self.assertTrue(any(p['fraction'] and p['fraction'] > 0.3 for p in v['progress']))
        r = self.get('/api/cc?category=hair')[2]
        self.assertEqual(r['total'], 2)
        it = r['items'][0]
        code, h, data = self.get('/api/cc/thumb/%d?v=%s' % (it['id'], it['pic']))
        self.assertEqual(code, 200)
        self.assertIn(h['content-type'], ('image/webp', 'image/png'))
        TC.Image.open(io.BytesIO(data)).load()
        s = self.get('/api/saves/Slot_00000001/cc')[2]
        self.assertTrue(s['ok'], s)
        self.assertEqual(s['counts']['missing'], 2)
        code, _, data = self.get('/api/cc/pic/cas/%016X' % TC.ABSENT)
        self.assertEqual(code, 200)


if __name__ == '__main__':
    unittest.main()

"""Novulon's Sims Hub server (speedkit/hub/server.py) against the example-data stub: every endpoint, the one-task
lock, task progress and results, Host/Origin checks and the static files. Each test starts its own server on a
free port; nothing here touches the game folders."""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
import speedkit  # noqa: E402
from speedkit.hub import server, stub_api  # noqa: E402

CONTRACT_KEYS = {'ok', 'game_running', 'profile', 'graphics', 'memory', 'library', 'fastpack', 'monitor', 'load_times',
                 'journals', 'animator', 'disk'}


class Base(unittest.TestCase):
    api = stub_api

    def setUp(self):
        stub_api.reset()
        stub_api.DELAY = 0.005
        stub_api.HOLD, stub_api.HOLD_AT = None, 0
        self.log = os.path.join(tempfile.mkdtemp(prefix='hubtest_'), 'hub.log')
        self.opened = []
        self.httpd = server.make_server(0, api=self.api, log_path=self.log, opener=self._opener)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.port = self.httpd.port
        self.host = '127.0.0.1:%d' % self.port

    def tearDown(self):
        if stub_api.HOLD is not None:
            stub_api.HOLD.set()
        self.httpd.shutdown()
        self.httpd.server_close()
        stub_api.HOLD = None
        stub_api.reset()

    def _opener(self, path):
        self.opened.append(path)
        return {'ok': True, 'message': 'opened'}

    def req(self, method, path, body=None, headers=None, raw=None, host=True):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            h = {'Host': self.host} if host is True else ({'Host': host} if host else {})
            data = raw
            if body is not None:
                data = json.dumps(body).encode()
                h['Content-Type'] = 'application/json'
            h.update(headers or {})
            if data is not None:
                h['Content-Length'] = str(len(data))
            for k, v in h.items():
                c.putheader(k, v)
            c.endheaders(data)
            r = c.getresponse()
            payload = r.read()
            try:
                out = json.loads(payload)
            except ValueError:
                out = payload
            return r.status, dict((k.lower(), v) for k, v in r.getheaders()), out
        finally:
            c.close()

    def get(self, path, **kw):
        return self.req('GET', path, **kw)

    def post(self, path, body, **kw):
        return self.req('POST', path, body=body, **kw)

    def wait(self, task_id, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            code, _, v = self.get('/api/task/' + task_id)
            self.assertEqual(code, 200)
            if v['state'] != 'running':
                return v
            time.sleep(0.02)
        self.fail('task %s did not finish' % task_id)


class Endpoints(Base):
    def test_ping(self):
        code, _, r = self.get('/api/ping')
        self.assertEqual(code, 200)
        self.assertEqual(r, {'ok': True, 'app': "Novulon's Sims Hub", 'engine': 'stub', 'pid': os.getpid(), 'busy': False})

    def test_status_has_contract_keys_and_hub_block(self):
        code, h, r = self.get('/api/status')
        self.assertEqual(code, 200)
        self.assertTrue(CONTRACT_KEYS <= set(r), CONTRACT_KEYS - set(r))
        self.assertEqual(r['hub']['engine'], 'stub')
        self.assertTrue(r['hub']['preview'])
        self.assertIsNone(r['hub']['task'])
        self.assertEqual(h['cache-control'], 'no-store')

    def test_status_is_cached_and_refresh_forces(self):
        self.get('/api/status')
        stub_api.STATE['disk']['c_free_gb'] = 1.5
        self.assertEqual(self.get('/api/status')[2]['disk']['c_free_gb'], 112.4)            # cached
        self.assertEqual(self.get('/api/status?refresh=1')[2]['disk']['c_free_gb'], 1.5)

    def test_previews_during_a_task_give_the_last_answer(self):
        first = self.get('/api/saves')[2]
        stub_api.HOLD = threading.Event()
        self.post('/api/task', {'action': 'report', 'args': {}})
        stub_api.STATE['saves'].pop()
        self.assertEqual(self.get('/api/saves?refresh=1')[2], first)
        stub_api.HOLD.set()

    def test_saves_cached_for_60s_and_refresh(self):
        code, _, r = self.get('/api/saves')
        self.assertEqual(code, 200)
        self.assertTrue(r['ok'])
        self.assertEqual(len(r['saves']), 4)
        s = r['saves'][0]
        for k in ('slot', 'name', 'household', 'world', 'last_played', 'size_mb', 'sims', 'lots', 'cc_parts', 'cas_loaded', 'pack'):
            self.assertIn(k, s)
        stub_api.STATE['saves'].pop()
        self.assertEqual(len(self.get('/api/saves')[2]['saves']), 4)
        self.assertEqual(server.SAVES_TTL, 60.0)
        self.assertEqual(len(self.get('/api/saves?refresh=1')[2]['saves']), 3)

    def test_graphics_and_inbox_previews_change_nothing(self):
        code, _, g = self.get('/api/graphics')
        self.assertEqual(code, 200)
        self.assertEqual(len(g['table']), 11)
        self.assertTrue({'setting', 'stock', 'before', 'after'} <= set(g['table'][0]))
        code, _, i = self.get('/api/inbox')
        self.assertEqual(code, 200)
        self.assertTrue(i['inbox_path'].endswith('Inbox'))
        self.assertEqual([x['status'] for x in i['items']], ['would be done'] * 3 + ['refused'])
        st = self.get('/api/status?refresh=1')[2]
        self.assertEqual(st['graphics']['state'], 'sgr_full')
        self.assertEqual(len(stub_api.STATE['inbox']), 4)

    def test_unknown_api_is_404(self):
        code, _, r = self.get('/api/nope')
        self.assertEqual(code, 404)
        self.assertFalse(r['ok'])
        self.assertEqual(self.post('/api/nope', {})[0], 404)


class Tasks(Base):
    def test_progress_and_result(self):
        code, _, r = self.post('/api/task', {'action': 'play', 'args': {'target': 'fast'}})
        self.assertEqual(code, 200)
        self.assertTrue(r['ok'])
        v = self.wait(r['task'])
        self.assertEqual(v['state'], 'done')
        self.assertEqual(v['action'], 'play')
        self.assertTrue(v['result']['ok'])
        self.assertIn('launched', v['result'])
        self.assertTrue(v['result']['steps'])
        ev = v['progress']
        self.assertGreaterEqual(len(ev), 8)
        for e in ev:
            self.assertEqual(set(e) - {'message_en'}, {'step', 'fraction', 'message', 't'})   # message_en: see i18n.py
            self.assertTrue(e['message'])
            self.assertTrue(e['fraction'] is None or 0 <= e['fraction'] <= 1)
        self.assertEqual(ev[-1]['fraction'], 1.0)
        # the status cache was dropped when the task finished
        st = self.get('/api/status')[2]
        self.assertEqual(st['profile']['name'], 'fast')
        self.assertEqual(st['graphics']['state'], 'tuned')

    def test_play_a_save_and_every_action(self):
        for action, args in [('play', {'target': 'save:Slot_00000014'}), ('prepare', {'target': 'studio'}),
                             ('inbox', {'apply': True}), ('cleanup_plan', {}), ('cleanup_apply', {}), ('report', {}),
                             ('graphics_restore', {'apply': True}), ('graphics_tune', {'apply': True}), ('undo_last', {})]:
            with self.subTest(action):
                code, _, r = self.post('/api/task', {'action': action, 'args': args})
                self.assertEqual(code, 200, r)
                v = self.wait(r['task'])
                self.assertEqual(v['state'], 'done', v['result'])
                self.assertTrue(v['result']['message'])
        self.assertEqual(self.get('/api/status')[2]['profile']['save_slot'], None)     # undo_last put 'full' back

    def test_failed_state_when_the_engine_says_no(self):
        stub_api.STATE['game_running'] = True
        r = self.post('/api/task', {'action': 'play', 'args': {'target': 'full'}})[2]
        v = self.wait(r['task'])
        self.assertEqual(v['state'], 'failed')
        self.assertFalse(v['result']['ok'])
        self.assertIn('running', v['result']['message'])

    def test_one_task_at_a_time(self):
        stub_api.HOLD = threading.Event()
        code, _, first = self.post('/api/task', {'action': 'play', 'args': {'target': 'fast'}})
        self.assertEqual(code, 200)
        code, _, second = self.post('/api/task', {'action': 'report', 'args': {}})
        self.assertEqual(code, 409)
        self.assertFalse(second['ok'])
        self.assertTrue(second['busy'])
        self.assertEqual(second['task'], first['task'])
        self.assertIn('Please wait', second['message'])
        self.assertIn('starting the game', second['message'])
        cur = self.get('/api/task/current')[2]
        self.assertEqual((cur['id'], cur['state']), (first['task'], 'running'))
        self.assertEqual(self.get('/api/status')[2]['hub']['task']['id'], first['task'])
        # the game path can't change under a running task either
        self.assertEqual(self.post('/api/game_path', {'path': 'E:\\The Sims 4'})[0], 409)
        # the read-only previews scan the library too: never beside a task (asked for the first time: 'busy')
        for path in ('/api/saves', '/api/graphics', '/api/inbox'):
            code, _, r = self.get(path)
            self.assertEqual((code, r['ok'], r['busy']), (200, False, True), path)
        stub_api.HOLD.set()
        self.assertEqual(self.wait(first['task'])['state'], 'done')
        code, _, third = self.post('/api/task', {'action': 'report', 'args': {}})
        self.assertEqual(code, 200)
        self.wait(third['task'])
        self.assertEqual(self.get('/api/task/current')[2]['id'], third['task'])       # newest when none runs

    def test_only_one_of_many_simultaneous_starts_wins(self):
        stub_api.HOLD = threading.Event()
        with ThreadPoolExecutor(8) as ex:
            codes = list(ex.map(lambda _: self.post('/api/task', {'action': 'cleanup_plan', 'args': {}})[0], range(8)))
        self.assertEqual(sorted(codes), [200] + [409] * 7)
        stub_api.HOLD.set()

    def test_bad_requests(self):
        cases = [({'action': 'format_c', 'args': {}}, 400), ({'action': 'play', 'args': {'target': 'everything'}}, 400),
                 ({'action': 'play', 'args': {'target': 'save:../../x'}}, 400), ({'action': 'play', 'args': {}}, 400),
                 ({'action': 'report', 'args': {'x': 1}}, 400), ({'action': 'inbox', 'args': {'apply': 'yes'}}, 400),
                 ({'action': 'report', 'args': [1]}, 400), ({'args': {}}, 400)]
        for body, want in cases:
            with self.subTest(body=body):
                code, _, r = self.post('/api/task', body)
                self.assertEqual(code, want)
                self.assertFalse(r['ok'])
                self.assertTrue(r['message'])
        self.assertIsNone(self.httpd.hub.current)
        code, _, r = self.get('/api/task/99-nope')
        self.assertEqual(code, 404)
        self.assertEqual(self.get('/api/task/current')[2], {'task': None})


class FakeEngine(Base):
    """The server with a hand-made engine: crashes, missing functions, noisy progress."""

    def setUp(self):
        def noisy(progress=None):
            for i in range(120):
                progress('step%d' % i, i / 119, 'message %d' % i)
            progress('odd', 'not a number', None)
            progress('extra', 0.5, 'x', 'unexpected', more=1)
            return {'ok': True, 'message': 'noisy done', 'copies': 1, 'gb': 0.1, 'rewritten': 0, 'removed': 0}

        def boom(progress=None):
            raise RuntimeError('disk on fire')

        def safe(fn):                                  # like speedkit/api.py's @_safe: the signature is hidden
            def wrapper(*a, **kw):
                try:
                    return fn(*a, **kw)
                except Exception as e:
                    return {'ok': False, 'message': 'Something went wrong: %s' % e}
            return wrapper

        @safe
        def plain(apply=False):                        # no progress parameter, like graphics_tune in the contract
            return {'ok': True, 'message': 'apply=%r' % apply, 'table': []}

        self.api = types.SimpleNamespace(status=lambda: {'ok': True, 'profile': {'name': 'full'}},
                                         cleanup_plan=noisy, cleanup_apply=boom, graphics_tune=plain,
                                         undo_last=lambda progress=None: 'not a dict')
        super().setUp()

    def test_mode_is_engine(self):
        self.assertEqual(self.get('/api/ping')[2]['engine'], 'engine')
        self.assertFalse(self.get('/api/status')[2]['hub']['preview'])

    def test_progress_keeps_the_last_50_and_tolerates_odd_calls(self):
        r = self.post('/api/task', {'action': 'cleanup_plan', 'args': {}})[2]
        v = self.wait(r['task'])
        self.assertEqual(v['state'], 'done')
        self.assertEqual(len(v['progress']), 50)
        self.assertEqual(v['progress'][-3]['message'], 'message 119')
        self.assertIsNone(v['progress'][-2]['fraction'])
        self.assertEqual(v['progress'][-2]['message'], '')

    def test_engine_crash_is_a_plain_failure_and_logged(self):
        v = self.wait(self.post('/api/task', {'action': 'cleanup_apply', 'args': {}})[2]['task'])
        self.assertEqual(v['state'], 'failed')
        self.assertIn('Something unexpected went wrong', v['result']['message'])
        self.assertNotIn('disk on fire', v['result']['message'])
        with open(self.log, encoding='utf-8') as f:
            self.assertIn('disk on fire', f.read())
        self.assertEqual(self.get('/api/ping')[0], 200)

    def test_no_progress_argument_when_the_engine_takes_none(self):
        v = self.wait(self.post('/api/task', {'action': 'graphics_tune', 'args': {'apply': True}})[2]['task'])
        self.assertEqual(v['state'], 'done')
        self.assertEqual(v['result']['message'], 'apply=True')

    def test_missing_function_and_odd_results(self):
        v = self.wait(self.post('/api/task', {'action': 'report', 'args': {}})[2]['task'])
        self.assertEqual(v['state'], 'failed')
        self.assertEqual(v['result']['message'], server.NOT_READY)
        v = self.wait(self.post('/api/task', {'action': 'undo_last', 'args': {}})[2]['task'])
        self.assertEqual(v['result'], {'ok': True, 'message': 'not a dict'})
        code, _, r = self.get('/api/browse')
        self.assertEqual((code, r['ok']), (200, False))
        self.assertEqual(self.post('/api/open', {'what': 'mods'})[2]['message'], server.NOT_READY)


class Security(Base):
    def test_host_must_be_local(self):
        for host in ('evil.example:%d' % self.port, '127.0.0.1:1', '127.0.0.1', '192.168.1.5:%d' % self.port, None):
            with self.subTest(host=host):
                for path in ('/api/status', '/', '/css/hub.css'):
                    code, _, r = self.get(path, host=host)
                    self.assertEqual(code, 403, path)
                self.assertEqual(self.post('/api/task', {'action': 'report', 'args': {}}, host=host)[0], 403)
        self.assertEqual(self.get('/api/ping', host='localhost:%d' % self.port)[0], 200)
        self.assertEqual(self.get('/api/ping', host='LOCALHOST:%d' % self.port)[0], 200)
        self.assertIsNone(self.httpd.hub.current)

    def test_origin_must_be_local(self):
        for origin in ('http://evil.example', 'null', 'http://127.0.0.1:1', 'https://127.0.0.1:%d' % self.port):
            with self.subTest(origin=origin):
                self.assertEqual(self.get('/api/status', headers={'Origin': origin})[0], 403)
                code, _, r = self.post('/api/task', {'action': 'report', 'args': {}}, headers={'Origin': origin})
                self.assertEqual(code, 403)
                self.assertIn('Hub', r['message'])
        self.assertIsNone(self.httpd.hub.current)
        ok = self.post('/api/open', {'what': 'mods'}, headers={'Origin': 'http://127.0.0.1:%d' % self.port})
        self.assertEqual(ok[0], 200)
        self.assertEqual(self.get('/api/ping', headers={'Origin': 'http://localhost:%d' % self.port})[0], 200)

    def test_post_needs_a_json_object(self):
        body = json.dumps({'action': 'report', 'args': {}}).encode()
        self.assertEqual(self.req('POST', '/api/task', raw=body, headers={'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.req('POST', '/api/task', raw=body)[0], 415)
        self.assertEqual(self.req('POST', '/api/task', raw=b'{nope', headers={'Content-Type': 'application/json'})[0], 400)
        self.assertEqual(self.req('POST', '/api/task', raw=b'[1,2]', headers={'Content-Type': 'application/json'})[0], 400)
        big = b'{"a":"' + b'x' * (70 * 1024) + b'"}'
        self.assertEqual(self.req('POST', '/api/task', raw=big, headers={'Content-Type': 'application/json'})[0], 400)
        self.assertIsNone(self.httpd.hub.current)

    def test_binds_to_loopback_only(self):
        self.assertEqual(self.httpd.server_address[0], '127.0.0.1')


class Static(Base):
    def test_page_and_files(self):
        code, h, body = self.get('/')
        self.assertEqual(code, 200)
        self.assertTrue(h['content-type'].startswith('text/html'))
        self.assertIn(b"Novulon's Sims Hub", body)
        self.assertIn("default-src 'self'", h['content-security-policy'])
        self.assertIn("frame-ancestors 'none'", h['content-security-policy'])
        self.assertEqual(h['x-content-type-options'], 'nosniff')
        for path, ctype in [('/css/hub.css', 'text/css'), ('/js/hub.js', 'text/javascript'), ('/img/logo.svg', 'image/svg+xml'),
                            ('/img/animator.svg', 'image/svg+xml'), ('/index.html', 'text/html')]:
            with self.subTest(path):
                code, h, body = self.get(path)
                self.assertEqual(code, 200)
                self.assertTrue(h['content-type'].startswith(ctype), h['content-type'])
                self.assertGreater(len(body), 100)
        if os.path.isfile(os.path.join(server.WEB, 'img', 'hub.ico')):
            code, h, body = self.get('/img/hub.ico')
            self.assertEqual((code, h['content-type'], body[:4]), (200, 'image/x-icon', b'\0\0\1\0'))

    def test_etag_gives_304(self):
        code, h, _ = self.get('/css/hub.css')
        code, h2, body = self.get('/css/hub.css', headers={'If-None-Match': h['etag']})
        self.assertEqual(code, 304)
        self.assertEqual(body, b'')

    def test_nothing_outside_the_web_folder(self):
        for path in ('/../server.py', '/%2e%2e/server.py', '/..%5cserver.py', '/css/../../server.py', '/nope.html', '/img/'):
            with self.subTest(path):
                code, _, body = self.get(path)
                self.assertEqual(code, 404)
                self.assertNotIn(b'import', body if isinstance(body, bytes) else b'')

    def test_head(self):
        code, h, body = self.req('HEAD', '/')
        self.assertEqual(code, 200)
        self.assertGreater(int(h['content-length']), 100)


class OpenAndGame(Base):
    def test_open_folders_and_animator(self):
        for what in ('mods', 'reports', 'inbox', 'saves', 'quarantine', 'animator'):
            with self.subTest(what):
                code, _, r = self.post('/api/open', {'what': what})
                self.assertEqual(code, 200)
                self.assertTrue(r['ok'])
        self.assertEqual(self.post('/api/open', {'what': 'C:\\Windows'})[0], 400)

    def test_report_html_opens_the_report_the_task_made(self):
        r = self.post('/api/open', {'what': 'report_html'})[2]
        self.assertEqual(r, {'ok': False, 'message': 'Make the library report first.'})
        v = self.wait(self.post('/api/task', {'action': 'report', 'args': {}})[2]['task'])
        self.assertEqual(v['state'], 'done')
        r = self.post('/api/open', {'what': 'report_html'})[2]
        self.assertTrue(r['ok'])
        self.assertEqual(self.opened, [v['result']['path']])

    def test_browse(self):
        code, _, r = self.get('/api/browse')
        self.assertEqual(code, 200)
        self.assertIsNone(r['path'])                                      # This PC, as speedkit/api.py says it
        self.assertEqual([d['name'] for d in r['drives']], ['C:', 'D:', 'E:'])
        self.assertTrue(r['suggestions'])
        r = self.get('/api/browse?path=E%3A%5C')[2]
        game = [e for e in r['entries'] if e['is_game']]
        self.assertEqual([e['path'] for e in game], ['E:\\The Sims 4'])
        self.assertIsNone(r['parent'])                                    # a drive's parent is This PC
        self.assertEqual(self.get('/api/browse?path=' + 'x' * 2000)[0], 400)

    def test_set_game_path(self):
        stub_api.STATE['game'] = {'found': False, 'exe': None, 'source': 'none'}
        self.assertFalse(self.get('/api/status?refresh=1')[2]['game']['found'])
        r = self.post('/api/game_path', {'path': 'D:\\Music'})[2]
        self.assertFalse(r['ok'])
        self.assertIn("isn't The Sims 4", r['message'])
        r = self.post('/api/game_path', {'path': 'E:\\The Sims 4'})[2]
        self.assertTrue(r['ok'])
        self.assertIn('remember', r['message'])
        self.assertTrue(self.get('/api/status')[2]['game']['found'])          # the cache was dropped
        for bad in ({}, {'path': ''}, {'path': 5}, {'path': 'x' * 2000}):
            self.assertEqual(self.post('/api/game_path', bad)[0], 400)


class Startup(unittest.TestCase):
    def test_load_api_picks_the_engine_or_the_stub(self):
        saved_mod, saved_attr = sys.modules.get('speedkit.api'), getattr(speedkit, 'api', None)
        try:
            self.assertIs(server.load_api('stub')[0], stub_api)
            broken = types.ModuleType('speedkit.api')                       # imports, but has no status()
            sys.modules['speedkit.api'] = broken
            speedkit.api = broken
            api, mode, why = server.load_api()
            self.assertEqual((api, mode), (stub_api, 'stub'))
            self.assertIn('status', why)
            good = types.ModuleType('speedkit.api')
            good.status = lambda: {'ok': True}
            sys.modules['speedkit.api'] = good
            speedkit.api = good
            self.assertEqual(server.load_api()[:2], (good, 'engine'))
            self.assertEqual(server.load_api('stub')[:2], (stub_api, 'stub'))
        finally:
            if saved_mod is None:
                sys.modules.pop('speedkit.api', None)
            else:
                sys.modules['speedkit.api'] = saved_mod
            if saved_attr is None:
                if hasattr(speedkit, 'api'):
                    del speedkit.api
            else:
                speedkit.api = saved_attr

    def test_python_dash_m_starts_the_hub(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        env = dict(os.environ, SIMS_HUB_PORT=str(port), SIMS_HUB_API='stub', PYTHONUNBUFFERED='1')
        p = subprocess.Popen([sys.executable, '-m', 'speedkit.hub'], cwd=ROOT, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            end, answer = time.time() + 20, None
            while time.time() < end and answer is None:
                try:
                    c = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    c.request('GET', '/api/ping')
                    answer = json.loads(c.getresponse().read())
                    c.close()
                except OSError:
                    time.sleep(0.2)
            self.assertEqual(answer, {'ok': True, 'app': "Novulon's Sims Hub", 'engine': 'stub', 'pid': p.pid, 'busy': False})
            # a second copy notices the first and stops at once
            p2 = subprocess.run([sys.executable, '-m', 'speedkit.hub'], cwd=ROOT, env=env, capture_output=True, timeout=30)
            self.assertEqual(p2.returncode, 0)
            self.assertIn(b'already running', p2.stdout)
        finally:
            p.terminate()
            out = p.communicate(timeout=10)[0]
        self.assertIn(b'EXAMPLE data', out)


if __name__ == '__main__':
    unittest.main()

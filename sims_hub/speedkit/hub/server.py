"""Novulon's Sims Hub - local server (the app side of docs/hub_contract.md).

    python -m speedkit.hub          then open http://127.0.0.1:8766/

It serves speedkit/hub/web/ and a small JSON API on 127.0.0.1 only. It never opens a window by itself.
The engine is speedkit/api.py; while that module is missing or does not import, the example-data stand-in
speedkit/hub/stub_api.py is used instead (SIMS_HUB_API=stub forces the stand-in, =engine forbids it).

API
  GET  /api/ping                     cheap "is it up" check for the launcher
  GET  /api/status[?refresh=1]       api.status(), cached a few seconds, plus a 'hub' block
  GET  /api/saves[?refresh=1]        api.list_saves(), cached for 60 s
  GET  /api/graphics[?refresh=1]     api.graphics_tune(apply=False): the before/after table (read-only)
  GET  /api/inbox[?refresh=1]        api.inbox(apply=False): the Inbox folder and what waits in it (read-only)
                                     (these three never run beside a task: the last answer, or 'busy', instead)
  GET  /api/browse?path=...          api.browse(path): folders for the in-app "Find The Sims 4" window
  POST /api/game_path {"path"}       api.set_game_path(path)
  POST /api/task {"action", "args"}  -> {"task": id}; one task at a time (409 while one runs)
  GET  /api/task/<id>                {"state": "running"|"done"|"failed", "progress": [...], "result": {...}}
  GET  /api/task/current             the running task, else the newest one (or {"task": null})
  POST /api/open {"what"}            animator | mods | reports | inbox | saves | quarantine | report_html

A finished task is 'done' when its result says ok, and 'failed' when it says not ok or raised.
"""
import email.utils
import inspect
import itertools
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, 'web')
ROOT = os.path.dirname(os.path.dirname(HERE))
LOG = os.path.join(ROOT, 'data', 'hub.log')
PORT = int(os.environ.get('SIMS_HUB_PORT', '8766'))
APP = "Novulon's Sims Hub"

TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
         '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf'}
# the page may use its own files and, when the internet is there, the Plus Jakarta Sans web font
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

STATUS_TTL = 4.0
SAVES_TTL = 60.0
PREVIEW_TTL = 60.0
KEEP_TASKS = 20

# action -> the plain words used when something else has to wait for it
ACTIONS = {
    'play': 'starting the game', 'prepare': 'getting the game ready', 'undo_last': 'undoing the last change',
    'inbox': 'adding your new downloads', 'cleanup_plan': 'checking for extra copies',
    'cleanup_apply': 'freeing up space', 'graphics_tune': 'fixing the graphics',
    'graphics_restore': 'putting your old graphics back', 'report': 'making the library report',
}
# the engine functions the contract gives a progress callback (its @_safe wrappers hide their signatures, so the
# contract decides; graphics_tune/graphics_restore take none)
TAKES_PROGRESS = {'list_saves', 'play', 'prepare', 'undo_last', 'inbox', 'cleanup_plan', 'cleanup_apply', 'report'}
OPEN_FOLDERS = ('mods', 'reports', 'inbox', 'saves', 'quarantine')
SLOT_RE = re.compile(r'^[A-Za-z0-9_.\- ]{1,80}$')
NOT_READY = "This part of the Hub isn't ready yet. Please update SpeedKit."


class BadRequest(Exception):
    pass


# ---------------------------------------------------------------------------------------------- the engine
def load_api(mode=None):
    """(module, 'engine'|'stub', why). The real speedkit.api when it imports and has status(), else the stub."""
    mode = (mode or os.environ.get('SIMS_HUB_API', '')).strip().lower()
    why = 'forced by SIMS_HUB_API=stub'
    if mode != 'stub':
        try:
            from speedkit import api as engine
            if callable(getattr(engine, 'status', None)):
                return engine, 'engine', ''
            why = 'speedkit/api.py has no status()'
        except Exception as ex:                      # missing, half-written, or broken: the Hub still opens
            if mode == 'engine':
                raise
            why = 'speedkit/api.py did not import (%s: %s)' % (type(ex).__name__, ex)
    from speedkit.hub import stub_api
    return stub_api, 'stub', why


def _accepts(fn, name):
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == name or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


def _plain(result, default_ok=True):
    """Every answer is a JSON-safe dict with 'ok' and 'message'."""
    if not isinstance(result, dict):
        result = {'ok': bool(result) if result is not None else default_ok, 'message': '' if result is None else str(result)}
    result = json.loads(json.dumps(result, default=str))
    result.setdefault('ok', default_ok)
    result.setdefault('message', '')
    return result


def _log(hub, text):
    try:
        os.makedirs(os.path.dirname(hub.log_path), exist_ok=True)
        with open(hub.log_path, 'a', encoding='utf-8') as f:
            f.write('%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), text.rstrip()))
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------- tasks
class Task:
    _ids = itertools.count(1)

    def __init__(self, action, args):
        self.id = '%d-%s' % (next(Task._ids), action)
        self.action, self.args = action, args
        self.state = 'running'
        self.progress = deque(maxlen=50)
        self.result = None
        self.started, self.finished = time.time(), None
        self.lock = threading.Lock()

    def event(self, step=None, fraction=None, message=None, *_, **__):
        """The progress callback handed to the engine. It never raises into the engine."""
        try:
            try:
                fraction = None if fraction is None else max(0.0, min(1.0, float(fraction)))
            except (TypeError, ValueError):
                fraction = None
            ev = {'step': '' if step is None else str(step)[:200], 'fraction': fraction,
                  'message': '' if message is None else str(message)[:500], 't': round(time.time() - self.started, 2)}
            with self.lock:
                self.progress.append(ev)
        except Exception:
            pass

    def view(self):
        with self.lock:
            progress = list(self.progress)
        return {'id': self.id, 'action': self.action, 'args': self.args, 'state': self.state, 'progress': progress,
                'result': self.result, 'started': self.started, 'finished': self.finished,
                'elapsed': round((self.finished or time.time()) - self.started, 2)}


class Hub:
    """Everything the handlers share: the engine, the caches and the one-task runner."""

    def __init__(self, api, mode='engine', why='', opener=None, log_path=LOG):
        self.api, self.mode, self.why = api, mode, why
        self.log_path = log_path
        self.opener = opener or (self._no_open if mode == 'stub' else self._startfile)
        self.lock = threading.Lock()
        self.tasks = {}
        self.current = None                     # the running Task, if any
        self.last_report = None
        self._cache = {}                        # name -> (time, value)
        self._cache_locks = {k: threading.Lock() for k in ('status', 'saves', 'graphics', 'inbox')}

    # ---------------------------------------------------------------- calling the engine
    def call(self, name, *args, **kwargs):
        fn = getattr(self.api, name, None)
        if not callable(fn):
            return {'ok': False, 'message': NOT_READY}
        if 'progress' in kwargs and (name not in TAKES_PROGRESS or not _accepts(fn, 'progress')):
            kwargs.pop('progress')
        try:
            return _plain(fn(*args, **kwargs))
        except Exception:
            _log(self, 'api.%s failed:\n%s' % (name, traceback.format_exc()))
            return {'ok': False, 'message': 'Something unexpected went wrong. Nothing else was changed after it. '
                                            'Details are in the Hub log (data\\hub.log).'}

    def cached(self, name, ttl, compute, refresh=False):
        with self._cache_locks[name]:           # one computation at a time; the others wait and share it
            hit = self._cache.get(name)
            if hit and not refresh and time.time() - hit[0] < ttl:
                return hit[1]
            value = compute()
            if value.get('ok', True) or not hit:
                self._cache[name] = (time.time(), value)
            return value

    def forget(self, *names):
        for n in names or tuple(self._cache):
            self._cache.pop(n, None)

    def status(self, refresh=False):
        st = dict(self.cached('status', STATUS_TTL, lambda: self.call('status'), refresh))
        with self.lock:
            cur = self.current.view() if self.current else None
        st['hub'] = {'engine': self.mode, 'preview': self.mode == 'stub', 'app': APP,
                     'task': {'id': cur['id'], 'action': cur['action']} if cur else None}
        return st

    def _quiet(self, name, ttl, compute, refresh):
        """The read-only previews scan the library too, so they never run beside a task: while one runs, the
        last answer (however old) or a plain 'busy' is given, and the page asks again when the task is done."""
        with self.lock:
            running = self.current
        if running is not None:
            hit = self._cache.get(name)
            return hit[1] if hit else dict(self.busy_message(running), items=[], saves=[], table=[])
        return self.cached(name, ttl, compute, refresh)

    def saves(self, refresh=False):
        return self._quiet('saves', SAVES_TTL, lambda: self.call('list_saves'), refresh)

    def graphics(self, refresh=False):
        return self._quiet('graphics', PREVIEW_TTL, lambda: self.call('graphics_tune', apply=False), refresh)

    def inbox_preview(self, refresh=False):
        return self._quiet('inbox', PREVIEW_TTL, lambda: self.call('inbox', apply=False), refresh)

    # ---------------------------------------------------------------- tasks
    @staticmethod
    def check_args(action, args):
        if action not in ACTIONS:
            raise BadRequest("I don't know how to do that.")
        if not isinstance(args, dict):
            raise BadRequest('The task needs its details as an object.')
        allowed = {'play': {'target'}, 'prepare': {'target'}, 'inbox': {'apply'}, 'graphics_tune': {'apply'},
                   'graphics_restore': {'apply'}}.get(action, set())
        extra = set(args) - allowed
        if extra:
            raise BadRequest('Unknown detail for this task: %s.' % ', '.join(sorted(extra)))
        if action in ('play', 'prepare'):
            target = args.get('target')
            ok = target in ('fast', 'full', 'studio') or (
                isinstance(target, str) and target.startswith('save:') and SLOT_RE.match(target[5:] or ''))
            if not ok:
                raise BadRequest('Pick how to play: fast, full, studio or a save.')
        if 'apply' in args and not isinstance(args['apply'], bool):
            raise BadRequest('"apply" must be true or false.')

    def start(self, action, args):
        """-> (Task, None) or (None, the running Task)."""
        self.check_args(action, args)
        with self.lock:
            if self.current is not None:
                return None, self.current
            task = self.current = Task(action, dict(args))
            self.tasks[task.id] = task
            for old in list(self.tasks)[:-KEEP_TASKS]:
                self.tasks.pop(old, None)
        threading.Thread(target=self._run, args=(task,), name='hub-task-' + task.id, daemon=True).start()
        return task, None

    def _run(self, task):
        try:
            kwargs = dict(task.args)
            target = kwargs.pop('target', None)
            pos = (target,) if task.action in ('play', 'prepare') else ()
            result = self.call(task.action, *pos, progress=task.event, **kwargs)
        except Exception:                        # call() already catches the engine; this is the Hub's own bug
            _log(self, 'task %s failed:\n%s' % (task.id, traceback.format_exc()))
            result = {'ok': False, 'message': 'Something unexpected went wrong in the Hub.'}
        if task.action == 'report' and result.get('ok') and result.get('path'):
            self.last_report = result['path']
        changes = task.action not in ('cleanup_plan', 'report') and (
            task.args.get('apply', True) if task.action in ('inbox', 'graphics_tune', 'graphics_restore') else True)
        with self.lock:
            task.result = result
            task.state = 'done' if result.get('ok') else 'failed'
            task.finished = time.time()
            self.current = None
            self.forget('status', 'saves', 'graphics', 'inbox') if changes else self.forget('status')

    def task_view(self, task_id):
        with self.lock:
            if task_id == 'current':
                task = self.current or (self.tasks[next(reversed(self.tasks))] if self.tasks else None)
            else:
                task = self.tasks.get(task_id)
        return task.view() if task else None

    def busy_message(self, running):
        return {'ok': False, 'busy': True, 'task': running.id,
                'message': 'Please wait - the Hub is still busy %s.' % ACTIONS.get(running.action, 'with something')}

    # ---------------------------------------------------------------- opening things
    def open(self, what):
        if what == 'animator':
            return self.call('open_animator')
        if what in OPEN_FOLDERS:
            return self.call('open_folder', what)
        if what == 'report_html':
            path = self.last_report
            if not path or not str(path).lower().endswith(('.html', '.htm')):
                return {'ok': False, 'message': 'Make the library report first.'}
            if self.mode != 'stub' and not os.path.isfile(path):
                return {'ok': False, 'message': "The library report isn't there any more. Make it again."}
            return self.opener(path)
        raise BadRequest("I can't open that.")

    def _no_open(self, path):
        return self.call('open_path', path) if callable(getattr(self.api, 'open_path', None)) else \
            {'ok': True, 'message': 'Preview: nothing was opened.'}

    @staticmethod
    def _startfile(path):
        try:
            os.startfile(path)                   # the user's default browser shows the report
            return {'ok': True, 'message': 'The library report is open.'}
        except OSError:
            return {'ok': False, 'message': "The library report couldn't be opened."}


# ---------------------------------------------------------------------------------------------- HTTP
def _json(obj):
    return json.dumps(obj, separators=(',', ':'), default=str).encode('utf-8')


def _inside(path, root):
    p, r = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = 'SimsHub/1'
    protocol_version = 'HTTP/1.1'
    timeout = 120

    def log_message(self, fmt, *args):
        pass

    @property
    def hub(self):
        return self.server.hub

    def _send(self, code, body, ctype='application/json', headers=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _ok(self, obj, code=200):
        self._send(code, _json(obj))

    def _error(self, code, message, **extra):
        self._send(code, _json(dict({'ok': False, 'message': message}, **extra)))

    def _local(self):
        """Only pages this server serves may talk to it: the right Host (stops DNS rebinding) and, when the
        browser names one, the right Origin (stops other web sites)."""
        host = (self.headers.get('Host') or '').strip().lower()
        if host not in self.server.hosts:
            return False
        origin = self.headers.get('Origin')
        return origin is None or origin.strip().lower() in self.server.origins

    def _refuse(self):
        self.close_connection = True
        self._error(403, 'Open the Hub from its own window (http://127.0.0.1:%d/).' % self.server.port)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if not self._local():
                return self._refuse()
            if url.path.startswith('/api/'):
                q = {k: v[-1] for k, v in parse_qs(url.query).items()}
                return self._get(url.path[5:], q)
            return self._static(url.path)
        except BadRequest as ex:
            self._error(400, str(ex))
        except Exception:
            _log(self.hub, 'GET %s failed:\n%s' % (url.path, traceback.format_exc()))
            self._error(500, 'Something unexpected went wrong in the Hub.')

    def do_POST(self):
        url = urlparse(self.path)
        try:
            try:
                n = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                n = -1
            if n < 0 or n > 64 * 1024:
                self.close_connection = True
                return self._error(400, 'Bad request.')
            raw = self.rfile.read(n) if n else b''
            if not self._local():
                return self._refuse()
            # other sites can't send a JSON body type without asking first (never allowed here)
            if (self.headers.get('Content-Type') or '').split(';')[0].strip().lower() != 'application/json':
                return self._error(415, 'Send JSON (Content-Type: application/json).')
            try:
                body = json.loads(raw or b'{}')
            except ValueError:
                return self._error(400, 'That was not valid JSON.')
            if not isinstance(body, dict):
                return self._error(400, 'Send a JSON object.')
            return self._post(url.path[5:] if url.path.startswith('/api/') else None, body)
        except BadRequest as ex:
            self._error(400, str(ex))
        except Exception:
            _log(self.hub, 'POST %s failed:\n%s' % (url.path, traceback.format_exc()))
            self._error(500, 'Something unexpected went wrong in the Hub.')

    # ---------------------------------------------------------------- API
    def _get(self, route, q):
        refresh = q.get('refresh') in ('1', 'true', 'yes')
        hub = self.hub
        if route == 'ping':
            return self._ok({'ok': True, 'app': APP, 'engine': hub.mode})
        if route == 'status':
            return self._ok(hub.status(refresh))
        if route == 'saves':
            return self._ok(hub.saves(refresh))
        if route == 'graphics':
            return self._ok(hub.graphics(refresh))
        if route == 'inbox':
            return self._ok(hub.inbox_preview(refresh))
        if route == 'browse':
            path = q.get('path') or None
            if path is not None and (len(path) > 1024 or '\x00' in path):
                raise BadRequest('That folder name is too long.')
            return self._ok(hub.call('browse', path))
        if route == 'task' or route == 'task/':
            route = 'task/current'
        if route.startswith('task/'):
            view = hub.task_view(route[5:])
            if view is None:
                if route == 'task/current':
                    return self._ok({'task': None})
                return self._error(404, "That task isn't known (the Hub may have restarted).")
            return self._ok(view)
        return self._error(404, 'Unknown request.')

    def _post(self, route, body):
        hub = self.hub
        if route == 'task':
            task, running = hub.start(body.get('action'), body.get('args') or {})
            if running is not None:
                return self._ok(hub.busy_message(running), 409)
            return self._ok({'ok': True, 'task': task.id})
        if route == 'open':
            return self._ok(hub.open(body.get('what')))
        if route == 'game_path':
            path = body.get('path')
            if not isinstance(path, str) or not path.strip() or len(path) > 1024 or '\x00' in path:
                raise BadRequest('Pick a folder first.')
            with hub.lock:
                running = hub.current
            if running is not None:
                return self._ok(hub.busy_message(running), 409)
            result = hub.call('set_game_path', path)
            hub.forget()
            return self._ok(result)
        return self._error(404, 'Unknown request.')

    # ---------------------------------------------------------------- files
    def _static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        full = os.path.normpath(os.path.join(WEB, path.lstrip('/')))
        if not _inside(full, WEB) or not os.path.isfile(full):
            return self._error(404, 'Not found.')
        st = os.stat(full)
        etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
        ext = os.path.splitext(full)[1].lower()
        headers = {'ETag': etag, 'Last-Modified': email.utils.formatdate(st.st_mtime, usegmt=True),
                   'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff'}
        if ext == '.html':
            headers.update({'Content-Security-Policy': CSP, 'Referrer-Policy': 'no-referrer'})
        if self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        with open(full, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', TYPES.get(ext, 'application/octet-stream'))
        self.send_header('Content-Length', str(len(data)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)


_EXCLUSIVE = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)


class Server(ThreadingHTTPServer):
    request_queue_size = 64
    daemon_threads = True
    block_on_close = False
    # Windows lets a second copy share a port opened the usual way; opening it exclusively makes it fail at once
    allow_reuse_address = _EXCLUSIVE is None

    def handle_error(self, request, client_address):
        # a browser or PowerShell hanging up early is normal; anything else goes to the Hub log, not the console
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return
        hub = getattr(self, 'hub', None)
        if hub is not None:
            _log(hub, 'request from %s failed:\n%s' % (client_address, traceback.format_exc()))

    def server_bind(self):
        if _EXCLUSIVE is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, _EXCLUSIVE, 1)
        super().server_bind()


def make_server(port=PORT, api=None, mode=None, why='', **hub_kwargs):
    """A ready (not yet serving) server on 127.0.0.1:port; port 0 picks a free one (tests)."""
    if api is None:
        api, mode, why = load_api(mode)
    elif mode is None:
        mode = 'stub' if getattr(api, 'PREVIEW', False) else 'engine'
    httpd = Server(('127.0.0.1', port), Handler)
    httpd.port = httpd.server_address[1]
    httpd.hosts = {'127.0.0.1:%d' % httpd.port, 'localhost:%d' % httpd.port}
    httpd.origins = {'http://' + h for h in httpd.hosts}
    httpd.hub = Hub(api, mode, why, **hub_kwargs)
    return httpd


def main(argv=None):
    url = 'http://127.0.0.1:%d/' % PORT
    try:
        httpd = make_server(PORT)
    except OSError as ex:
        print(APP, 'is already running at', url, '(port %d is in use: %s)' % (PORT, ex))
        return 0
    hub = httpd.hub
    print(APP, 'running at', url)
    if hub.mode == 'stub':
        print('Showing EXAMPLE data: ' + (hub.why or 'the engine is not installed yet'))
    threading.Thread(target=hub.status, daemon=True).start()        # warm the first page
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

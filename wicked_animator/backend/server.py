"""Novulon's Wicked Animator - local server. Serves the app and the game data, and exports to the game.

    python server.py            then open http://127.0.0.1:8765
"""
import base64, email.utils, importlib, json, os, re, socket, subprocess, sys, threading, traceback, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gamedata as G   # noqa: E402
import exporter        # noqa: E402
import projects as P   # noqa: E402

WEB = os.path.join(HERE, '..', 'web')
PORT = int(os.environ.get('ANIMATOR_PORT', '8765'))
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.jpg': 'image/jpeg',
         # motion capture (MediaPipe): Chrome refuses an ES module sent as octet-stream, and WebAssembly streams
         # only with its own type
         '.mjs': 'text/javascript; charset=utf-8', '.wasm': 'application/wasm', '.task': 'application/octet-stream',
         '.txt': 'text/plain; charset=utf-8', '.webp': 'image/webp', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
         '.woff2': 'font/woff2', '.mp4': 'video/mp4', '.webm': 'video/webm'}
# Pages and scripts may only talk to this server (and to blob:/data: URLs they made themselves). This stops anything
# inside the page - e.g. MediaPipe's built-in usage logger - from sending data off the PC. Scripts, styles and fonts
# still load as before (the policy only covers fetch / XHR / beacons / WebSockets).
CSP = "connect-src 'self' blob: data:"
ADULT_AGES = ('youngadult', 'adult', 'elder')
# who may talk to the server: only pages the server itself serves (stops other web sites and DNS rebinding)
HOSTS = {'127.0.0.1:%d' % PORT, 'localhost:%d' % PORT, '[::1]:%d' % PORT}
ORIGINS = {'http://' + h for h in HOSTS}
# POST routes that browsers send as text/plain (navigator.sendBeacon when the window closes)
BEACON_ROUTES = ('/api/recovery', '/api/recovery_clear')

FURNITURE = [
    # id, label, WickedWhims locations it stands for, size (width x, height y, depth z in metres), top height
    {'id': 'floor', 'label': 'Floor', 'locations': ['FLOOR'], 'kind': 'floor'},
    {'id': 'double_bed', 'label': 'Double bed', 'locations': ['DOUBLE_BED'], 'kind': 'bed', 'size': [1.9, 0.55, 2.35]},
    {'id': 'single_bed', 'label': 'Single bed', 'locations': ['SINGLE_BED'], 'kind': 'bed', 'size': [1.0, 0.55, 2.2]},
    {'id': 'sofa', 'label': 'Sofa', 'locations': ['SOFA'], 'kind': 'sofa', 'size': [2.6, 0.45, 0.95]},
    {'id': 'loveseat', 'label': 'Loveseat', 'locations': ['LOVESEAT'], 'kind': 'sofa', 'size': [1.7, 0.45, 0.95]},
    {'id': 'chair_living', 'label': 'Armchair', 'locations': ['CHAIR_LIVING'], 'kind': 'armchair', 'size': [0.95, 0.45, 0.9]},
    {'id': 'chair_dining', 'label': 'Dining chair', 'locations': ['CHAIR_DINING'], 'kind': 'chair', 'size': [0.5, 0.47, 0.5]},
    {'id': 'counter', 'label': 'Counter', 'locations': ['COUNTER'], 'kind': 'counter', 'size': [1.0, 0.92, 0.62]},
    {'id': 'table_dining', 'label': 'Dining table', 'locations': ['TABLE_DINING_2X', 'DESK'], 'kind': 'table', 'size': [1.9, 0.76, 0.95]},
    {'id': 'wall', 'label': 'Wall', 'locations': ['WALL'], 'kind': 'wall', 'size': [3.0, 2.8, 0.15]},
]


def _json(obj):
    return json.dumps(obj, separators=(',', ':')).encode('utf-8')


_adult_sims = set()          # sim ids (int) of the adult human sims /api/tray last listed


def _is_adult(s):
    return s.get('species', 'human') == 'human' and s.get('age') in ADULT_AGES


def _tray_households():
    """Households with at least one adult human sim, listing ONLY those sims (index = position in the household,
    which /api/tray_sim takes). Children, teens and pets never leave the server."""
    import trayfmt
    out, ids = [], set()
    for hh in trayfmt.list_households():
        sims = [dict(s, index=i, allowed=True) for i, s in enumerate(hh['sims']) if _is_adult(s)]
        if sims:
            out.append({'id': hh['id'], 'name': hh['name'], 'sims': sims})
            ids |= {trayfmt.to_int(s['sim_id']) for s in sims}
    _adult_sims.clear()
    _adult_sims.update(ids)
    return out


def _inside(path, root):
    """Is path (resolved) the folder root or inside it?"""
    p, r = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root))
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:        # another drive
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = 'WickedAnimator/2'
    protocol_version = 'HTTP/1.1'      # keep-alive: a page load reuses a few connections instead of opening ~40
    timeout = 120                      # an idle kept-alive connection is closed after this many seconds

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype='application/json', cache=False, headers=None):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'max-age=86400' if cache else 'no-store')
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, message):
        self._send(code, _json({'error': message}))

    def _host_ok(self):
        host = (self.headers.get('Host') or '').lower()
        return not host or host in HOSTS

    def _fail(self, ex):
        if isinstance(ex, FileNotFoundError):
            return self._error(404, str(ex) or 'not found')
        traceback.print_exc()
        self._error(500, str(ex) or repr(ex))

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if not self._host_ok():
                self.close_connection = True
                return self._error(403, 'Open the app at http://127.0.0.1:%d/' % PORT)
            if url.path.startswith('/api/'):
                return self._api_get(url.path[5:], q)
            return self._static(url.path)
        except Exception as ex:
            self._fail(ex)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            try:
                n = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                self.close_connection = True
                return self._error(400, 'bad request')
            raw = self.rfile.read(n) if n > 0 else b''
            # only the app's own pages may change things: the right Host, and no other site's Origin. JSON routes
            # also need a JSON body type, which other sites can't send without asking first (never allowed here)
            origin = self.headers.get('Origin')
            if not self._host_ok() or (origin is not None and origin.lower() not in ORIGINS):
                return self._error(403, 'Only the app itself can do that.')
            ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
            route = url.path[5:] if url.path.startswith('/api/') else None
            if url.path == '/api/save_video':
                if not ctype.startswith('video/'):
                    return self._error(415, 'Send the video as video/webm.')
            elif route in EXT_POST_RAW and route not in BUILTIN_POST:
                # an add-on route that takes a file as it is (a picture, a video): only the types it names
                fn, kinds = EXT_POST_RAW[route]
                if not any(ctype.startswith(k) for k in kinds):
                    return self._error(415, 'This kind of file can\'t be sent here.')
                q = {k: v[-1] for k, v in parse_qs(url.query).items()}
                return self._ext_reply(lambda: fn(raw, ctype, q))
            elif url.path not in BEACON_ROUTES and ctype != 'application/json':
                return self._error(415, 'Send JSON (Content-Type: application/json).')
            if url.path == '/api/save_video':
                # a recorded preview video (webm) - saved next to the exported mods
                q = {k: v[-1] for k, v in parse_qs(url.query).items()}
                name = re.sub(r'[^A-Za-z0-9 _-]+', '', q.get('name', 'video')).strip()[:80] or 'video'
                folder = os.path.join(exporter.EXPORTS, 'Videos')
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, name + '.webm')
                k = 2
                while os.path.exists(path):
                    path = os.path.join(folder, '%s (%d).webm' % (name, k)); k += 1
                with open(path, 'wb') as f:
                    f.write(raw)
                return self._send(200, _json({'path': path, 'folder': folder, 'bytes': len(raw)}))
            body = json.loads(raw or b'{}')
            return self._api_post(url.path[5:], body, {k: v[-1] for k, v in parse_qs(url.query).items()})
        except Exception as ex:
            self._fail(ex)

    # ------------------------------------------------------------------ static
    def _static(self, path):
        if path in ('', '/'):
            path = '/index.html'
        full = os.path.normpath(os.path.join(WEB, path.lstrip('/')))
        if not _inside(full, WEB) or not os.path.isfile(full):
            return self._error(404, 'not found')
        st = os.stat(full)
        etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
        # scripts, styles and pictures may be reused for a few seconds; after that (and for the page itself) the
        # browser asks again and gets a tiny "not modified" answer unless the file changed
        short = path.startswith(('/js/', '/css/', '/img/'))
        # add-on files (web/vendor/<name>/, e.g. MediaPipe 1.0.1 and its models) never change once installed: the
        # browser keeps them for a year instead of asking about a 30 MB model on every visit. Their list
        # (manifest.json) is asked for every time.
        vendor = path.startswith('/vendor/') and not path.endswith('.json')
        headers = {'ETag': etag, 'Last-Modified': email.utils.formatdate(st.st_mtime, usegmt=True),
                   'Cache-Control': 'max-age=31536000, immutable' if vendor else 'max-age=10' if short else 'no-cache',
                   'Content-Security-Policy': CSP}
        if self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            for k, v in headers.items():
                self.send_header(k, v)
            self.end_headers()
            return
        with open(full, 'rb') as f:
            data = f.read()
        self.send_response(200)
        self.send_header('Content-Type', TYPES.get(os.path.splitext(full)[1], 'application/octet-stream'))
        self.send_header('Content-Length', str(len(data)))
        for k, v in headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path, ctype):
        with open(path, 'rb') as f:
            self._send(200, f.read(), ctype, cache=True)

    # ------------------------------------------------------------------ API
    def _api_get(self, route, q):
        if route == 'status':
            return self._send(200, _json({'game_dir': G.game_dir(), 'mods': G.MODS_DIR, 'ww': bool(G.ww_tuning_package()), 'ok': True,
                                          'build': BUILD, 'pid': os.getpid()}))
        if route == 'rig':
            if q.get('key', 'au') != 'au':
                return self._error(404, 'Only the adult rig is available.')
            return self._send(200, _json(G.rig('au')))
        if route == 'body':
            frame = q.get('frame', 'yf')
            if frame not in G.BODIES:
                return self._error(404, 'unknown body')
            return self._send(200, _json(G.body(frame)))
        if route == 'skin':
            # never an error: a skin tone that isn't installed (custom content that is gone) or can't be read gets a
            # stand-in - X-Skin-Tone says 'real' or 'standin', X-Skin-Tone-Used which tone is shown
            import skintex
            path, info = skintex.skin_for(q.get('frame', 'yf'), q.get('tone') or None)
            ti = skintex.tone_info(info)
            with open(path, 'rb') as f:
                data = f.read()
            return self._send(200, data, 'image/png', cache=ti['status'] == 'real',
                              headers={'X-Skin-Tone': ti['status'], 'X-Skin-Tone-Used': ti['used'],
                                       'X-Skin-Tone-Source': ti['source']})
        if route == 'tones':
            import skintex
            tones = sorted(skintex.skin_tones(), key=lambda t: t.get('sort_order', 0))
            return self._send(200, _json([{'hex': t['hex'], 'swatch': t['swatch'], 'type': t.get('skin_type')} for t in tones]))
        if route == 'sounds':
            return self._send(200, _json(_sound_list()))
        if route == 'furniture':
            return self._send(200, _json(FURNITURE))
        if route == 'furniture_mesh':
            # the real game object WickedWhims uses for this place (exact size and origin)
            try:
                import objmesh
            except ImportError:
                return self._error(404, 'no game furniture reader')
            f = next((x for x in FURNITURE if x['id'] == q.get('id')), None)
            if not f or f.get('kind') == 'floor':
                return self._error(404, 'no object for this place')
            for loc in f['locations']:
                obj = objmesh.furniture_for_location(loc)
                if obj and obj.get('meshes'):
                    return self._send(200, _json(obj), cache=True)
            return self._error(404, 'object not found in the game files')
        if route == 'furniture_tex':
            name = os.path.basename(q.get('file', ''))
            path = os.path.join(G.CACHE, 'furniture', name)
            if not name.lower().endswith('.png') or not os.path.isfile(path):
                return self._error(404, 'no texture')
            return self._file(path, 'image/png')
        if route == 'library':
            return self._send(200, _json(self._library(q)))
        if route == 'animation':
            lib = G.library()['animations']
            a = lib[int(q['id'])]
            step = int(q.get('step', '1'))
            clips = [G.clip_tracks(x['clip'], step=step) for x in a['actors']]
            # the creator's moments (sounds, effects, undress...) come along, ready for the app (spec_game 3)
            try:
                ext_game = sys.modules.get('ext_game') or importlib.import_module('ext_game')
                events = ext_game._animation_events({'id': q['id']})['events']
            except Exception:
                traceback.print_exc()
                events = []
            return self._send(200, _json(dict(a, clips=clips, events=events)))
        if route == 'poses':
            import poses
            return self._send(200, _json(poses.presets()))
        if route == 'projects':
            return self._send(200, _json(P.list_projects()))
        if route == 'project':
            if q.get('uid'):
                d = P.load_uid(q['uid'])
                if d is None:
                    return self._error(404, 'That animation is not saved any more.')
                return self._send(200, _json(d))
            return self._send(200, _json(P.load(q['name'])))
        if route == 'project_name':
            # the file a name saves under, and the other animation already saved there (the same rule as saving)
            return self._send(200, _json(P.name_check(q.get('name', ''), q.get('uid') or None)))
        if route == 'project_thumb':
            t = P.thumb(q['name'])
            if not t.startswith('data:image/'):
                return self._error(404, 'no picture')
            head, b64 = t.split(',', 1)
            return self._send(200, base64.b64decode(b64), head[5:].split(';')[0])
        if route == 'progressions':
            return self._send(200, _json(P.progressions()))
        if route == 'recovery':
            return self._send(200, _json(P.read_recovery(q.get('slot'))))
        if route == 'my_poses':
            return self._send(200, _json(P.my_poses()))
        if route == 'sound':
            import mysounds
            if mysounds.is_mine(q.get('name')):             # one of your own sounds: what the game will play
                data = mysounds.preview(q['name'])
                return self._send(200, data, 'audio/wav', cache=True) if data else self._error(404, 'sound not found')
            try:
                import eaaudio
            except ImportError:
                return self._error(404, 'sound playback is not installed yet')
            data, mime = eaaudio.sound_file(q['name'], int(q.get('v', '0') or 0), q.get('voice') or None)
            if not data:
                return self._error(404, 'sound not found')
            return self._send(200, data, mime, cache=True)
        if route == 'exports':
            folder = os.path.join(G.MODS_DIR, 'FitStudio', 'MyAnimations')
            items = []
            if os.path.isdir(folder):
                for fn in sorted(os.listdir(folder)):
                    if fn.endswith('.package'):
                        p = os.path.join(folder, fn)
                        items.append({'file': fn, 'modified': os.path.getmtime(p), 'bytes': os.path.getsize(p)})
            return self._send(200, _json(items))
        if route == 'tray':
            return self._send(200, _json(_tray_households()))
        if route == 'tray_thumb':
            import trayfmt
            sim = trayfmt.to_int(q['sim'])
            if sim not in _adult_sims:
                _tray_households()          # the Tray may have new households since it was last listed
            if sim not in _adult_sims:
                return self._error(404, 'no picture')
            data = trayfmt.sim_thumbnail(q['sim'])
            if not data:
                return self._error(404, 'no picture')
            return self._send(200, data, 'image/jpeg', cache=True)
        if route == 'tray_sim':
            return self._send(200, _json(self._tray_sim(q['tray'], int(q.get('index', 0)))))
        if route == 'features':
            return self._send(200, _json(_features()))
        if route in EXT_GET:
            fn = EXT_GET[route]
            return self._ext_reply(lambda: fn(q))
        return self._error(404, 'unknown api ' + route)

    def _ext_reply(self, call):
        """Answer for an add-on route (backend/ext_*.py): a dict or list goes out as JSON, (bytes, type) as it is.
        ValueError -> 400 with its message, LookupError -> 404, anything else -> 500."""
        try:
            out = call()
        except ValueError as ex:
            return self._error(400, str(ex) or 'bad request')
        except LookupError as ex:
            msg = ex.args[0] if ex.args and isinstance(ex.args[0], str) else 'not found'
            return self._error(404, msg)
        except Exception as ex:
            traceback.print_exc()
            return self._error(500, str(ex) or repr(ex))
        if isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], (bytes, bytearray)):
            return self._send(200, bytes(out[0]), str(out[1] or 'application/octet-stream'))
        return self._send(200, _json(out))

    def _tray_sim(self, tray_id, index):
        import trayfmt, morph
        spec = trayfmt.sim_body_spec(tray_id, index)
        if spec.get('age') not in ADULT_AGES or spec.get('species', 'human') != 'human':
            raise ValueError('Only adult sims can be used.')
        frame = spec.get('frame') if spec.get('frame') in ('yf', 'ym') else ('ym' if spec.get('gender') == 'male' else 'yf')
        body = G.body(frame)
        morphed = morph.morph_body(body, spec)
        meshes = []
        for m, mm in zip(body['meshes'], morphed['meshes'] if isinstance(morphed, dict) and 'meshes' in morphed else morphed):
            pos = mm.get('positions') if isinstance(mm, dict) else None
            nrm = mm.get('normals') if isinstance(mm, dict) else None
            meshes.append(dict(m, positions=[round(float(c), 5) for c in (pos if pos is not None else m['positions'])],
                               normals=[round(float(c), 4) for c in (nrm if nrm is not None else m['normals'])]))
        tone = spec.get('tone_inst')
        out = {'frame': frame, 'name': spec.get('name') or '', 'gender': spec.get('gender'), 'age': spec.get('age'),
               'tone': ('%016x' % int(tone, 16) if isinstance(tone, str) else '%016x' % tone) if tone else '',
               'body': {'frame': frame, 'rig': body['rig'], 'meshes': meshes, 'ww': body.get('ww')}}
        # is the sim's own skin tone installed (game, pack or custom content in Mods / Mods_parked)? When it isn't,
        # /api/skin shows a stand-in and toneStandIn says so (toneInfo: status, source, used, reason, package)
        try:
            import skintex
            ti = skintex.tone_info(skintex.resolve_tone(out['tone'] or None))
            if not out['tone']:
                ti.update(status='standin', source='default', reason='missing')
        except Exception:
            traceback.print_exc()
            ti = {'status': 'standin', 'source': 'default', 'used': '', 'reason': 'missing', 'package': None}
        out['toneStandIn'] = ti['status'] != 'real'
        out['toneInfo'] = ti
        # the sim's own voice from the game (voice actor + pitch), when the sound reader knows how to tell it
        try:
            import eaaudio
            voice_for = getattr(eaaudio, 'voice_for_actor', None)
            voice = voice_for(spec.get('voice_actor'), spec.get('gender')) if voice_for else None
        except Exception:
            traceback.print_exc()
            voice = None
        if voice:
            out['voice'] = voice
            out['voicePitch'] = spec.get('voice_pitch') or 0
        return out

    def _library(self, q):
        lib = G.library()['animations']
        text = q.get('q', '').lower().strip()
        loc, cat, tag = q.get('loc', ''), q.get('cat', ''), q.get('tag', '')
        actors = int(q.get('actors', '0') or 0)
        out = []
        for a in lib:
            if not a['available']:
                continue
            if actors and len(a['actors']) != actors:
                continue
            if loc and loc not in a['locations']:
                continue
            if cat and a['category'] != cat:
                continue
            if tag and tag not in a.get('tags', []):
                continue
            if text and text not in a['name'].lower() and text not in a['author'].lower():
                continue
            out.append({'id': a['id'], 'name': a['name'], 'author': a['author'], 'locations': a['locations'],
                        'category': a['category'], 'tags': a.get('tags', []), 'actors': [x['gender'] for x in a['actors']]})
        page = int(q.get('page', '0'))
        return {'total': len(out), 'items': out[page * 100:(page + 1) * 100]}

    def _api_post(self, route, body, q=None):
        q = q or {}
        if route == 'export':
            return self._send(200, _json(exporter.export(body)))
        if route == 'bundle':
            return self._send(200, _json(exporter.bundle(body)))
        if route == 'project':
            # overwrite=1: the user chose "Replace it" - a different animation saved under this name is moved to
            # animator_replaced and this one takes its place. ask=1: answer 409 on such a clash (the app asks the
            # user). Neither: this one is saved under a free name ('Name (2)') and the answer says so.
            yes = ('1', 'true', 'yes')
            try:
                saved = P.save(body, overwrite=q.get('overwrite', '').lower() in yes, ask=q.get('ask', '').lower() in yes)
            except P.NameTaken as ex:
                return self._send(409, _json({'error': str(ex), 'existing': ex.existing}))
            return self._send(200, _json(saved))
        if route == 'project_remove':
            return self._send(200, _json(P.remove(body['file'])))
        if route == 'progressions':
            return self._send(200, _json(P.save_progressions(body if isinstance(body, list) else body.get('progressions', []))))
        if route == 'recovery':
            return self._send(200, _json(P.write_recovery(body, q.get('slot'))))
        if route == 'recovery_clear':
            return self._send(200, _json(P.clear_recovery(q.get('slot'))))
        if route == 'my_poses':
            return self._send(200, _json(P.save_my_poses(body if isinstance(body, list) else body.get('poses', []))))
        if route == 'reveal':
            # opens a folder in Explorer (a file is only shown selected in its folder, never opened)
            path = os.path.normpath(str(body.get('path') or ''))
            if not path or not os.path.exists(path) or not any(_inside(path, r) for r in (exporter.EXPORTS, G.MODS_DIR)):
                return self._error(400, 'Can only open the export and Mods folders.')
            if os.path.isdir(path):
                subprocess.Popen(['explorer', path])
            else:
                subprocess.Popen('explorer /select,"%s"' % path)
            return self._send(200, _json({'ok': True}))
        if route in EXT_POST:
            fn = EXT_POST[route]
            return self._ext_reply(lambda: fn(body, q))
        return self._error(404, 'unknown api ' + route)


# When this engine's code was last changed (newest backend .py, Unix seconds). The desktop app compares it with the
# files on disk and restarts an engine that is still running older code.
BUILD = int(max(os.path.getmtime(os.path.join(HERE, f)) for f in os.listdir(HERE) if f.endswith('.py')))

_EXCLUSIVE = getattr(socket, 'SO_EXCLUSIVEADDRUSE', None)


class Server(ThreadingHTTPServer):
    # a page load asks for ~40 files at once; the default queue of 5 made Windows refuse the rest (spinner forever)
    request_queue_size = 128
    daemon_threads = True
    block_on_close = False
    # Windows lets a second copy share a port opened the usual way (SO_REUSEADDR), and then the OLDER copy keeps
    # getting the connections. Opening it exclusively makes a second copy stop at once instead.
    allow_reuse_address = _EXCLUSIVE is None

    def server_bind(self):
        if _EXCLUSIVE is not None:
            self.socket.setsockopt(socket.SOL_SOCKET, _EXCLUSIVE, 1)
        super().server_bind()


_catalogue = (None, None)


def _sound_list():
    """Every sound the animations use that can be played: the game's voice lines ('vo_...', which the game picks
    per sim) are looked up too, so they show up and play. Made once per sound list."""
    global _catalogue
    base = G.sounds()
    if _catalogue[0] is not base:
        try:
            import eaaudio
            full = eaaudio.catalogue()
        except Exception:
            traceback.print_exc()
            full = base
        _catalogue = (base, [x for x in full if x['source'] != 'unknown'])
    return _catalogue[1]


def _warm():
    """Read the animation library and the sound list in the background, so the first visit is quick."""
    try:
        G.library()
        _sound_list()
    except Exception:
        traceback.print_exc()
    for fn in list(EXT_WARM):          # add-ons warm their own caches here too (an error is logged, never fatal)
        try:
            fn()
        except Exception:
            traceback.print_exc()


# ---------------------------------------------------------------------------------------------------- add-ons
# Features add their own routes in backend/ext_<name>.py (loaded at start, sorted by name). A module may define
#   GET = {'route': fn(q) -> obj}      POST = {'route': fn(body, q) -> obj}
#   POST_RAW = {'route': (fn(data: bytes, content_type, q) -> obj, ('image/', 'video/'))}
#   WARM = [fn]                         run once in the background warm-up
# and they answer at /api/<route>. The app's own routes always win a name clash.
BUILTIN_GET = {'status', 'rig', 'body', 'skin', 'tones', 'sounds', 'furniture', 'furniture_mesh', 'furniture_tex',
               'library', 'animation', 'poses', 'projects', 'project', 'project_name', 'project_thumb', 'progressions',
               'recovery', 'my_poses', 'sound', 'exports', 'tray', 'tray_thumb', 'tray_sim', 'features'}
BUILTIN_POST = {'export', 'bundle', 'project', 'project_remove', 'progressions', 'recovery', 'recovery_clear',
                'my_poses', 'reveal', 'save_video'}
EXT_GET, EXT_POST, EXT_POST_RAW, EXT_WARM = {}, {}, {}, []
EXT_LOADED = []
_ROUTE = re.compile(r'^[a-z0-9_]+$')


def _load_ext():
    """Import every backend/ext_*.py once and register its routes (a broken add-on is logged and skipped)."""
    if EXT_LOADED:
        return EXT_LOADED
    for fn in sorted(os.listdir(HERE)):
        m = re.match(r'^(ext_[A-Za-z0-9_]+)\.py$', fn)
        if not m:
            continue
        try:
            mod = importlib.import_module(m.group(1))
        except Exception:
            print('Add-on %s could not be loaded:' % fn)
            traceback.print_exc()
            continue
        EXT_LOADED.append(m.group(1))
        for kind, table, builtin, target in (('GET', getattr(mod, 'GET', None), BUILTIN_GET, EXT_GET),
                                             ('POST', getattr(mod, 'POST', None), BUILTIN_POST, EXT_POST),
                                             ('POST_RAW', getattr(mod, 'POST_RAW', None), BUILTIN_POST, EXT_POST_RAW)):
            for route, handler in (table or {}).items():
                if not isinstance(route, str) or not _ROUTE.match(route):
                    print('Add-on %s: route name %r is not allowed (a-z, 0-9, _) - skipped' % (fn, route))
                    continue
                if route in builtin:
                    print('Add-on %s: %s /api/%s is one of the app\'s own routes - the app\'s own one is kept' % (fn, kind, route))
                    continue
                if route in target or (kind != 'GET' and (route in EXT_POST or route in EXT_POST_RAW)):
                    print('Add-on %s: %s /api/%s is already taken by another add-on - skipped' % (fn, kind, route))
                    continue
                if kind == 'POST_RAW':
                    if not (isinstance(handler, (tuple, list)) and len(handler) == 2 and callable(handler[0])):
                        print('Add-on %s: POST_RAW /api/%s needs (fn, (types...)) - skipped' % (fn, route))
                        continue
                    kinds = handler[1]
                    kinds = (kinds,) if isinstance(kinds, str) else tuple(str(k).lower() for k in (kinds or ()))
                    target[route] = (handler[0], kinds)
                elif callable(handler):
                    target[route] = handler
        for w in getattr(mod, 'WARM', None) or []:
            if callable(w):
                EXT_WARM.append(w)
    return EXT_LOADED


_FEATURE_NAME = re.compile(r'^[a-z0-9_-]+\.(js|css)$')


def _features():
    """The app's add-on scripts and styles (web/js/features/*.js, web/css/features/*.css), file names only."""
    out = {}
    for kind, folder in (('js', os.path.join(WEB, 'js', 'features')), ('css', os.path.join(WEB, 'css', 'features'))):
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            names = []
        out[kind] = [n for n in names if _FEATURE_NAME.match(n) and n.endswith('.' + kind)
                     and os.path.isfile(os.path.join(folder, n))]
    return out


def main():
    url = 'http://127.0.0.1:%d/' % PORT
    try:
        httpd = Server(('127.0.0.1', PORT), Handler)
    except OSError as ex:
        print("Novulon's Wicked Animator is already running at", url, '(port %d is in use: %s)' % (PORT, ex))
        if '--open' in sys.argv:
            webbrowser.open(url)
        return
    _load_ext()                                             # add-on routes (backend/ext_*.py)
    threading.Thread(target=_warm, daemon=True).start()   # warm the animation index and the sound list
    print("Novulon's Wicked Animator running at", url)
    if '--open' in sys.argv:
        webbrowser.open(url)
    httpd.serve_forever()


if __name__ == '__main__':
    main()

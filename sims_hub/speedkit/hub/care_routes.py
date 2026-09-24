"""The Hub server's routes for patch day, game errors, save backups and load-time savings (docs/care.md).

server.py hands these requests over (its docstring lists them):
  GET  /api/patchday[?refresh=1]      api.patch_day(): the game's last update, older script mods, mods set aside
  GET  /api/errors[?refresh=1]        api.game_errors(): the game's error reports, grouped, with the mod named
  GET  /api/save_health[?refresh=1]   api.save_health(): each save's size and growth, and the save backups
  GET  /api/load_savings[?refresh=1]  api.load_savings(): load time per mode and the time Play FAST saves
      (these read files only; while a task runs they give their last answer, or 'busy')
  POST /api/patchday/seen             api.patch_seen(): the patch-day notice was seen
  POST /api/errors/seen               api.errors_seen(): hide the errors seen so far
Tasks (POST /api/task, one at a time like every change):
  set_aside     {"rels": [paths in Mods], "why": "patch"|"error"}
  put_back      {"rels": [paths in Mods]}
  backup_saves  {}
  restore_saves {"backup": "<backup id>"}
"""
import re
import threading
import time

ACTIONS = {'set_aside': 'setting mods aside', 'put_back': 'putting mods back', 'backup_saves': 'backing up your saves',
           'restore_saves': 'putting back your saves'}
TAKES_PROGRESS = set(ACTIONS)
ALLOWED = {'set_aside': {'rels', 'why'}, 'put_back': {'rels'}, 'backup_saves': set(), 'restore_saves': {'backup'}}
READS = {'patchday': ('patch_day', 30.0), 'errors': ('game_errors', 30.0), 'save_health': ('save_health', 30.0),
         'load_savings': ('load_savings', 30.0)}
POSTS = {'patchday/seen': 'patch_seen', 'errors/seen': 'errors_seen'}
BACKUP_RX = re.compile(r'^\d{8}-\d{6}(-\d{1,3})?$')
MAX_RELS = 500

_lock = threading.Lock()


class BadArgs(ValueError):
    pass


def check_args(action, args):
    """Raise BadArgs (a plain sentence) when a task's details are not what it takes."""
    extra = set(args) - ALLOWED[action]
    if extra:
        raise BadArgs('Unknown detail for this task: %s.' % ', '.join(sorted(extra)))
    if action in ('set_aside', 'put_back'):
        rels = args.get('rels')
        if not isinstance(rels, list) or not rels or len(rels) > MAX_RELS:
            raise BadArgs('Pick the mods first.')
        for r in rels:
            if not isinstance(r, str) or not r.strip() or len(r) > 400 or '\x00' in r:
                raise BadArgs('That is not a mod file in your Mods folder.')
            parts = r.replace('\\', '/').split('/')
            if '..' in parts or r.startswith(('/', '\\')) or ':' in r:
                raise BadArgs('That is not a mod file in your Mods folder.')
        if action == 'set_aside' and args.get('why', 'patch') not in ('patch', 'error'):
            raise BadArgs('"why" must be "patch" or "error".')
    if action == 'restore_saves':
        b = args.get('backup')
        if not isinstance(b, str) or not BACKUP_RX.match(b):
            raise BadArgs('Pick a backup first.')


def _cache(hub):
    c = getattr(hub, 'care_cache', None)
    if c is None:
        with _lock:
            c = getattr(hub, 'care_cache', None)
            if c is None:
                c = hub.care_cache = {}
    return c


def forget(hub):
    """A task finished: everything these pages show may have changed."""
    _cache(hub).clear()


def get(hub, route, refresh):
    """The answer for a GET route of this module, or None when the route is not one of them."""
    if route not in READS:
        return None
    name, ttl = READS[route]
    cache = _cache(hub)
    with hub.lock:
        running = hub.current
    hit = cache.get(route)
    if running is not None:                       # never read the folders while a change runs
        return hit[1] if hit else dict(hub.busy_message(running), errors=[], saves=[], backups=[], older=[],
                                       set_aside=[], modes={})
    if hit and not refresh and time.time() - hit[0] < ttl:
        return hit[1]
    value = hub.call(name)
    if value.get('ok', True) or not hit:
        cache[route] = (time.time(), value)
    return value


def post(hub, route, body):
    """The answer for a POST route of this module (not /api/task), or None."""
    if route not in POSTS:
        return None
    result = hub.call(POSTS[route])
    _cache(hub).pop(route.split('/')[0], None)
    return result

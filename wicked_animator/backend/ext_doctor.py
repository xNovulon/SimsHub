"""Extra server routes for the Game Doctor and "Did it play in the game?" (plan 2.7; names reserved for R1-E).

    GET  /api/doctor_scan[?force=1]      starts a scan on a background thread (read-only) -> status
    GET  /api/doctor_status              progress and the cards found so far
    POST /api/doctor_fix                 {action: 'park', file} | {action: 'enable', file: 'dynamic'|'individual', ...}
    GET  /api/game_log?author=&name=&since=[&running=0]   played / problem lines of WickedWhims' log
    GET  /api/game_running               {running: true|false|null}
    GET  /api/doctor_browse?q=&where=mods|parked|all&place=&act=&sims=&only=fav|off&page=&refresh=1
                                         the Browse tab: every installed adult animation with its WickedWhims
                                         identifier, favorite / turned-off state and the identifier proof (R3-2)

doctor_fix also takes {action: 'favorite'|'turn_off', id: <identifier>, on: true|false} (wwlists.mark): it writes
WickedWhims' own sex_animations_favorites.ww / all_disabled_animations.json only when the identifier proof holds.

doctor_fix is the only route that changes anything, and only on a click in the app: it refuses while The Sims 4
runs, never deletes, and never touches WickedWhims' own files or the user's own tools (Mods\\FitStudio,
Mods\\animation, the Sims Hub's SpeedKit_Monitor.ts4script and !!!!!SpeedKit_Fast_*.package).
"""
import doctor
import gamelog
import wwlists

_YES = ('1', 'true', 'yes')


def _scan(q):
    doctor.start_scan(force=str(q.get('force', '')).lower() in _YES)
    return doctor.status()


def _status(q):
    return doctor.status()


def _game_log(q):
    return gamelog.read(q.get('author') or None, q.get('name') or None, q.get('since') or None,
                        check_running=str(q.get('running', '1')).lower() not in ('0', 'false', 'no'))


def _browse(q):
    return wwlists.browse(q)


def _game_running(q):
    return {'running': gamelog.game_running()}


def _fix(body, q):
    if not isinstance(body, dict):
        raise ValueError('Send the fix as a JSON object.')
    return doctor.fix(body)


def _scan_post(body, q):
    return _scan(dict(q or {}, **(body if isinstance(body, dict) else {})))


GET = {'doctor_scan': _scan, 'doctor_status': _status, 'game_log': _game_log, 'game_running': _game_running,
       'doctor_browse': _browse}
POST = {'doctor_scan': _scan_post, 'doctor_fix': _fix}


def _warm():
    """The Browse list is read in the background at start (cached per package: under a second after the first time)."""
    wwlists.ensure()


WARM = [_warm]

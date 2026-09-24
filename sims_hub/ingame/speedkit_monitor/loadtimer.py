"""Load timer: how long from launching The Sims 4 to the main menu and to a playable lot.

Milestones and where they come from (game build 1.126.73, read with tools/pyc37.py + tools/xref.py):
  * launch      - SpeedKit\\launch_time.json when SpeedKit started the game, else the mtime of
                  <Sims 4>\\Config.log. The game rewrites Config.log once per start (its 'NumBoots' went
                  43 -> 44 between two launches; it holds that start's 'Free memory' reading) and it is the
                  first file the game writes. Measured live on 2026-09-24: TS4_x64.exe process start
                  01:39:47.8, Config.log written 01:40:06.8 and not touched again during the session. So a
                  Config.log-based launch time is about 19 s LATE and every 'since launch' figure from it
                  is about 19 s short; launch_source in the CSV says which one was used.
  * scripts     - the import of this module: the game imports script mods (sims4.importer.utils.
                  import_modules, called from Simulation_x64.dll) after the package index is read.
  * main menu   - areaserver.c_api_notify_client_in_main_menu (name present in Simulation_x64.dll)
                  calls services.on_enter_main_menu(), a no-op we wrap.
  * lot start   - areaserver.c_api_zone_init -> zone.start_services(gameplay_zone_data, save_slot_data).
  * lot loaded  - the client sends the Live command 'zone.loading_screen_animation_finished', which
                  calls services.current_zone().on_loading_screen_animation_finished() (zone.pyc line
                  1085): the loading screen is gone and the lot is playable. The game's own
                  areaserver.server_init_load_time then holds zone_init -> zone_loaded in seconds.
One CSV row per main-menu and lot-loaded event goes to SpeedKit\\reports\\loadtimes.csv; everything is also
logged to monitor.log. After a lot loads the CC guard runs (ccguard.py).

Robustness rules (review 2026-09-24):
  * the CC guard runs after a lot load even when the CSV cannot be written (e.g. loadtimes.csv open in
    Excel) or when the game's own loading-screen handler raised (hooks.around(always=True));
  * one lot_loaded row per zone start: the Live command 'clock.restore_saved_clock_speed' also calls
    Zone.on_loading_screen_animation_finished (server_commands/clock_commands.pyc line 187), so a second
    call for the same zone start is ignored;
  * the profile is read once, at our import (what the game loaded), not at each event: a profile tool
    may switch Mods while the game runs. Fallback: the 'profile' in launch_time.json of this launch;
  * launch_to_menu_s is only filled when the first main-menu event came before any lot; if the game
    reached the menu before script mods loaded, the first event we see is a return to the menu.
"""
import csv
import os
import time

from . import common, hooks

HEADER = ['time', 'event', 'since_launch_s', 'launch_to_scripts_s', 'launch_to_menu_s', 'lot_load_s',
          'game_zone_load_s', 'lot_index', 'zone_id', 'profile', 'script_mods', 'script_modules',
          'launch_source', 'launch_time', 'free_ram_mb_at_start', 'monitor_version']
MAX_LAUNCH_AGE = 3600.0             # a launch time older than this before our import is not this launch
SAME_LAUNCH = 600.0                 # launch_time.json and Config.log this close belong to one launch

state = {'import_time': None, 'launch': None, 'launch_source': 'unknown', 'free_ram_mb': None,
         'profile': None, 'profile_state': None, 'menu_time': None, 'menus': 0, 'zone_start': {}, 'lots': 0,
         'played': False}


# ------------------------------------------------------------------ pure helpers (tested under 3.12)
def parse_time_value(v):
    """Unix time from a number or an ISO-8601 string (local time when naive), else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        try:
            return float(s)
        except ValueError:
            pass
        import datetime
        try:
            # timestamp() of a naive date before 1970 or after 3000 raises OSError on Windows (checked in
            # the game's 3.7), so a bad value from another tool must not escape
            return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
        except (ValueError, OverflowError, OSError):
            return None
    return None


def launch_time_from_json(obj):
    """The launch time in SpeedKit\\launch_time.json. Accepted: {"launch_time": <unix time or ISO>}
    (also "time", "launched_at", "epoch"), or a bare number/string."""
    if isinstance(obj, dict):
        for k in ('launch_time', 'time', 'launched_at', 'epoch'):
            if k in obj:
                t = parse_time_value(obj[k])
                if t is not None:
                    return t
        return None
    return parse_time_value(obj)


def profile_from_json(obj):
    """The active profile name in SpeedKit\\profile_state.json ({"profile": "lean"} and similar), or None."""
    if isinstance(obj, str):
        return obj.strip() or None
    if not isinstance(obj, dict):
        return None
    for k in ('profile', 'active_profile', 'active', 'current', 'name'):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            inner = profile_from_json(v)
            if inner:
                return inner
    return None


def pick_launch_time(import_time, json_time=None, config_mtime=None, max_age=MAX_LAUNCH_AGE):
    """(launch unix time, source) from the candidates, or (None, 'unknown').

    A candidate is valid when it is not after our import (1 s slack) and at most max_age before it.
    launch_time.json wins when it belongs to the same launch as Config.log (written before it, and
    within SAME_LAUNCH seconds); a stale launch_time.json from an earlier SpeedKit launch loses."""
    def ok(t):
        return t is not None and t <= import_time + 1.0 and import_time - t <= max_age
    j = json_time if ok(json_time) else None
    c = config_mtime if ok(config_mtime) else None
    if j is not None and c is not None:
        if j <= c + 5.0 and c - j <= SAME_LAUNCH:
            return j, 'speedkit'
        return c, 'config.log'
    if j is not None:
        return j, 'speedkit'
    if c is not None:
        return c, 'config.log'
    return None, 'unknown'


def parse_free_ram(text):
    """The 'Free memory:     559MB' figure the game writes to Config.log at start, in MB, or None."""
    for line in text.splitlines()[:120]:
        if line.startswith('Free memory:'):
            digits = ''.join(ch for ch in line.split(':', 1)[1] if ch.isdigit())
            return int(digits) if digits else None
    return None


def seconds(a, b):
    """b - a rounded to 0.1 s, or '' when either is unknown."""
    if a is None or b is None:
        return ''
    return round(b - a, 1)


def append_row(path, row, header=HEADER):
    """Append a row to a CSV file, writing the header first; a file with another header is renamed
    to <name>_old_<time>.csv so rows never end up under the wrong columns."""
    exists = os.path.exists(path)
    if exists:
        try:
            with open(path, encoding='utf-8', newline='') as f:
                first = next(csv.reader(f), None)
        except Exception:
            first = None
        if first != header:
            base, ext = os.path.splitext(path)
            os.replace(path, '%s_old_%s%s' % (base, time.strftime('%Y%m%d_%H%M%S'), ext))
            exists = False
    with open(path, 'a', encoding='utf-8', errors='replace', newline='') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(header)
        w.writerow(row)


# ------------------------------------------------------------------ reading the Sims folder
def read_profile_state():
    """SpeedKit\\profile_state.json as written by the profile tool (dict), or None."""
    k = common.speedkit_dir()
    doc = common.read_json(os.path.join(k, 'profile_state.json')) if k else None
    return doc if isinstance(doc, dict) else None


def read_profile():
    """Profile name from SpeedKit\\profile_state.json, or None."""
    k = common.speedkit_dir()
    return profile_from_json(common.read_json(os.path.join(k, 'profile_state.json'))) if k else None


def _config_log():
    s = common.sims_dir()
    if not s:
        return None, None
    path = os.path.join(s, 'Config.log')
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, None
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read(16384)
    except OSError:
        text = ''
    return mtime, text


def on_import(import_time):
    """Record the script-loading milestone, work out the launch time and note the loaded profile."""
    state['import_time'] = import_time
    k = common.speedkit_dir()
    launch_obj = common.read_json(os.path.join(k, 'launch_time.json')) if k else None
    json_time = launch_time_from_json(launch_obj)
    config_mtime, config_text = _config_log()
    state['launch'], state['launch_source'] = pick_launch_time(import_time, json_time, config_mtime)
    state['free_ram_mb'] = parse_free_ram(config_text) if config_text else None
    state['profile_state'] = read_profile_state()
    profile = read_profile()
    if not profile and state['launch_source'] == 'speedkit' and isinstance(launch_obj, dict):
        profile = profile_from_json({'profile': launch_obj.get('profile')})
    state['profile'] = profile
    common.log('SpeedKit Monitor %s imported (script mods loading); launch %s (%s), %s s since launch, '
               'free RAM at start %s MB, profile %s' % (
                   common.VERSION, _fmt(state['launch']), state['launch_source'],
                   seconds(state['launch'], import_time), state['free_ram_mb'], profile or '-'))


def _fmt(t):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)) if t else ''


def make_row(event, now, zone_id='', lot_load_s='', game_zone_load_s='', lot_index=''):
    """One CSV row (list) for an event at unix time `now`, from the recorded state."""
    loaded = common.loaded_script_mods()
    launch = state['launch']
    return [_fmt(now), event, seconds(launch, now), seconds(launch, state['import_time']),
            seconds(launch, state['menu_time']) if state['menu_time'] is not None else '',
            lot_load_s, game_zone_load_s, lot_index, zone_id, state.get('profile') or '', len(loaded),
            sum(loaded.values()), state['launch_source'], _fmt(launch), state['free_ram_mb'] or '',
            common.VERSION]


def _write(row):
    """Log the row, then append it to loadtimes.csv. A CSV that cannot be written (open in Excel, disk
    full...) is logged and skipped - it must never stop what comes after (the CC guard)."""
    common.log('load timer: ' + ', '.join('%s=%s' % (h, v) for h, v in zip(HEADER, row) if v != ''))
    d = common.reports_dir()
    if d:
        common.guarded('writing loadtimes.csv', append_row, os.path.join(d, 'loadtimes.csv'), row)


# ------------------------------------------------------------------ events
def on_main_menu():
    """services.on_enter_main_menu was called: the main menu is up."""
    now = time.time()
    state['menus'] += 1
    if state['menus'] == 1:
        if state['played']:
            common.log('load timer: first main-menu event came after a lot was played (the menu was reached '
                       'before script mods loaded); launch_to_menu_s stays empty')
        else:
            state['menu_time'] = now
    state['lots'] = 0                     # in the menu: the next lot load starts a new series
    try:
        from . import ccguard
        ccguard.reset_session()           # the next lot may belong to another save
    except Exception:
        common.log_exception('resetting the save guard at main menu')
    try:
        from . import lagmeter
        lagmeter.stop_if_running('main menu')
    except Exception:
        common.log_exception('stopping lag meter at main menu')
    _write(make_row('main_menu', now))


def on_zone_start(zone):
    """Zone.start_services is about to run: the lot's simulation starts loading."""
    state['played'] = True
    state['zone_start'] = {'id': getattr(zone, 'id', None), 't': time.time(), 'loaded': False}


def on_lot_loaded(zone):
    """Zone.on_loading_screen_animation_finished ran: the lot is playable. One row and one CC check per
    zone start; the CC guard runs even if the row cannot be written."""
    now = time.time()
    zid = getattr(zone, 'id', None)
    start = state['zone_start'] if state['zone_start'].get('id') == zid else {}
    if start.get('loaded'):
        common.log('load timer: loading screen finished again for zone %s without a new zone start; ignored' % (
            '0x%x' % zid if isinstance(zid, int) else zid))
        return
    if start:
        start['loaded'] = True
    state['played'] = True
    state['lots'] += 1
    try:
        game_s = ''
        try:
            import areaserver
            v = float(areaserver.server_init_load_time)   # c_api_zone_loaded turns it into a duration
            if 0.0 <= v < 100000.0:
                game_s = round(v, 1)
        except Exception:
            pass
        _write(make_row('lot_loaded', now, '0x%x' % zid if isinstance(zid, int) else '',
                        seconds(start.get('t'), now), game_s, state['lots']))
    finally:
        try:
            from . import ccguard
            ccguard.run_after_load()
        except Exception:
            common.log_exception('CC guard after lot load')
        try:
            from . import lagmeter
            lagmeter.show_pending()          # a lag run that ended when the previous lot was unloaded
        except Exception:
            common.log_exception('lag meter notification after lot load')


# ------------------------------------------------------------------ hooks
def install():
    """Wrap services.on_enter_main_menu, zone.Zone.start_services and
    zone.Zone.on_loading_screen_animation_finished. Returns {hook label: installed?}."""
    done = {}
    try:
        import services
        done['services.on_enter_main_menu'] = hooks.install(
            services, 'on_enter_main_menu',
            lambda orig: hooks.around(orig, after=lambda a, r: on_main_menu(), label='main menu', always=True),
            'services.on_enter_main_menu')
    except Exception:
        common.log_exception('hook services.on_enter_main_menu')
        done['services.on_enter_main_menu'] = False
    try:
        import zone
        done['Zone.start_services'] = hooks.install(
            zone.Zone, 'start_services',
            lambda orig: hooks.around(orig, before=lambda a: on_zone_start(a[0]), label='zone start'),
            'Zone.start_services')
        done['Zone.on_loading_screen_animation_finished'] = hooks.install(
            zone.Zone, 'on_loading_screen_animation_finished',
            lambda orig: hooks.around(orig, after=lambda a, r: on_lot_loaded(a[0]), label='lot loaded',
                                      always=True),
            'Zone.on_loading_screen_animation_finished')
    except Exception:
        common.log_exception('hook zone.Zone')
        done.setdefault('Zone.start_services', False)
        done.setdefault('Zone.on_loading_screen_animation_finished', False)
    common.log('load timer hooks: ' + ', '.join('%s %s' % (k, 'ok' if v else 'FAILED') for k, v in done.items()))
    return done

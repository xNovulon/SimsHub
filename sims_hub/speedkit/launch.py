"""Start The Sims 4 after a memory check, and note the start time for the in-game load timer.

launch(dry_run=False) runs preflight() (speedkit.settings), refuses if TS4_x64.exe already runs, starts
the exe detached (it keeps running when this script or its terminal closes), and writes
<Sims 4>\\SpeedKit\\launch_time.json:

    {"epoch": 1790200000.123, "iso": "2026-09-24T12:00:00", "profile": "lean", "profile_source": "...",
     "exe": "E:\\The Sims 4\\Game\\Bin\\TS4_x64.exe", "args": [], "pid": 1234}

The in-game timer subtracts epoch from the time the game reaches the main menu / a lot. The file is
SpeedKit's own bookkeeping in its own folder (like the journal files), so it is written directly with
an atomic replace rather than through a Journal; the game never reads it.

Facts relied on: the game is E:\\The Sims 4\\Game\\Bin\\TS4_x64.exe (1.126.73.1030) and has been started
directly before (research 'settings': launched by another process at 23:52:52). No command-line flags
are passed by default: the research found strings like -nopreload and nointro in the exe but their
effects are untested, so they are not offered as speed tips. The profile is read from
SpeedKit\\profile_state.json when a profile tool wrote one (the in-game monitor reads the same file),
else from the Mods switch tool's Mods_parked\\_manifest.json (parked items = lean set, none = full set).
"""
import json, os, subprocess, sys, time

from .library import SIMS, game_running
from .settings import GAME_EXE, preflight

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
_LAUNCHED = []      # keep the Popen objects: the game outlives them on purpose (no "still running" warning)


def detect_profile(sims=SIMS, home=None):
    """(profile, source). A SpeedKit profile tool's SpeedKit\\profile_state.json ({"profile": name}) wins;
    otherwise 'lean' when the Mods switch tool has parked mods, 'full' when nothing is parked, None when
    neither file exists."""
    state = os.path.join(home or os.path.join(sims, 'SpeedKit'), 'profile_state.json')
    if os.path.exists(state):
        try:
            with open(state, encoding='utf-8') as f:
                d = json.load(f)
            name = next((d[k] for k in ('profile', 'active_profile', 'active', 'name')
                         if isinstance(d, dict) and isinstance(d.get(k), str)), None)
            if name:
                return name, state
        except (OSError, ValueError):
            pass
    man = os.path.join(sims, 'Mods_parked', '_manifest.json')
    if not os.path.exists(man):
        return None, None
    try:
        with open(man, encoding='utf-8') as f:
            moved = json.load(f).get('moved', [])
    except (OSError, ValueError, AttributeError):         # AttributeError: not a {"moved": [...]} object
        return None, man
    if not isinstance(moved, list):
        return None, man
    return ('lean' if moved else 'full'), man


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def _start_detached(cmd, cwd):
    """Start cmd with no console, in its own process group, outside our job object when allowed."""
    kw = dict(cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    try:
        return subprocess.Popen(cmd, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB, **kw)
    except OSError:
        return subprocess.Popen(cmd, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP, **kw)


def _open_url(url):
    """Hand a URL (steam://rungameid/...) to Windows, which starts the program registered for it."""
    if hasattr(os, 'startfile'):
        os.startfile(url)
    else:                                   # not Windows (tests elsewhere): nothing to hand it to
        raise OSError('cannot open %s on this system' % url)


def launch(exe=GAME_EXE, dry_run=True, args=(), sims=SIMS, home=None, profile=None, check_game=True, processes=True,
           url=None, preflight_report=None, extra=None):
    """Preflight, then start the game detached and write SpeedKit\\launch_time.json.

    Returns {'started', 'dry_run', 'exe', 'args', 'profile', 'launch_file', 'pid', 'preflight', 'warnings',
    'refused', 'via'}. dry_run=True (default) only reports what would happen. Refuses (started False,
    'refused' set) when the game already runs or the exe is missing. Never closes other programs.
    url: start the game through this URL instead of the exe (Steam installs: steam://rungameid/1222670 -
    a direct start may relaunch through Steam); the exe must still exist. preflight_report: a preflight()
    result to reuse. extra: more keys for launch_time.json (e.g. the save a 'save' profile was made for)."""
    home = home or os.path.join(sims, 'SpeedKit')
    exe = os.path.abspath(exe)              # the game starts in its own folder (cwd = the exe's folder)
    if profile is None:
        profile, source = detect_profile(sims, home)
    else:
        source = 'given'
    rep = preflight_report if preflight_report is not None else preflight(sims, processes=processes)
    running = check_game and (game_running() or rep['game_running'])
    plan = {'started': False, 'dry_run': dry_run, 'exe': exe, 'args': list(args), 'profile': profile,
            'profile_source': source, 'launch_file': os.path.join(home, 'launch_time.json'), 'pid': None,
            'preflight': rep, 'warnings': [w for w in rep['warnings'] if 'already running' not in w], 'refused': None,
            'via': url or exe}
    if running:
        plan['refused'] = 'The Sims 4 is already running.'
    elif not os.path.isfile(exe):
        plan['refused'] = 'Game exe not found: %s' % exe
    if dry_run or plan['refused']:
        return plan
    epoch = time.time()
    pid = None
    if url:
        _open_url(url)
    else:
        proc = _start_detached([exe] + list(args), os.path.dirname(exe))
        _LAUNCHED.append(proc)
        pid = proc.pid
    doc = {'epoch': epoch, 'iso': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(epoch)), 'profile': profile,
           'profile_source': source, 'exe': exe, 'args': list(args), 'pid': pid, 'via': url or exe}
    doc.update(extra or {})
    _write_json(plan['launch_file'], doc)
    plan['started'], plan['pid'] = True, pid
    return plan


def main(argv=None):
    """python -m speedkit.launch [--apply]   (without --apply: preflight and plan only)"""
    args = list(sys.argv[1:] if argv is None else argv)
    p = launch(dry_run='--apply' not in args)
    rep = p['preflight']
    m = rep['memory']
    print('Memory: %.1f GB free of %.1f GB; profile: %s' % (m['ram_available_mb'] / 1024, m['ram_total_mb'] / 1024,
                                                           p['profile'] or 'unknown'))
    for n in rep['notes']:
        print('  * ' + n)
    for w in p['warnings']:
        print('  ! ' + w)
    if p['refused']:
        print('Not started: ' + p['refused'])
        return 1
    if p['dry_run']:
        print('DRY RUN - would start %s and write %s' % (p['exe'], p['launch_file']))
    else:
        print('Started %s (pid %d); start time written to %s' % (p['exe'], p['pid'], p['launch_file']))
    return 0


if __name__ == '__main__':
    sys.exit(main())

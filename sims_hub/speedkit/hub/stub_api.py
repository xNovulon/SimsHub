"""A stand-in for speedkit/api.py with realistic example data (see docs/hub_contract.md).

The Hub uses it while the real engine module is missing or broken, and the tests use it on purpose
(SIMS_HUB_API=stub). It never touches a file, never opens a window and never starts the game: every
action only changes the in-memory STATE below, after a short, fake progress run.

Test knobs: DELAY (seconds per progress step), HOLD (a threading.Event the steps from HOLD_AT on wait
for), and STATE, which tests may edit directly (e.g. STATE['game_running'] = True).
"""
import copy
import os
import threading
import time
from datetime import datetime, timedelta

PREVIEW = True                  # the server shows "example data" while this module is in use
DELAY = float(os.environ.get('SIMS_HUB_STUB_DELAY', '0.45'))
HOLD = None                     # threading.Event: when set to an Event, steps from HOLD_AT on wait until it is set
HOLD_AT = 0

_lock = threading.RLock()


# like speedkit/api.py: the Wicked Animator's windowed exe, else its .bat
_ANIMATOR = [os.path.join(os.path.expanduser('~'), 'Tools', 'sims4_animator', n) for n in ('Wicked Animator.exe',
                                                                                         'Start Wicked Animator.bat')]


def _ago(**kw):
    return (datetime.now() - timedelta(**kw)).replace(microsecond=0).isoformat()


def _load_times(starts):
    """Rows as speedkit/api.py gives them: newest first, one 'main_menu' row per start and a separate 'lot_loaded'
    row when a lot was loaded afterwards."""
    rows = []
    for (hours,), profile, menu, lot in starts:
        if lot is not None:
            rows.append({'time': _ago(hours=hours, minutes=-5), 'event': 'lot_loaded', 'profile': profile,
                         'launch_to_menu_s': None, 'lot_load_s': lot})
        rows.append({'time': _ago(hours=hours), 'event': 'main_menu', 'profile': profile, 'launch_to_menu_s': menu,
                     'lot_load_s': None})
    return rows[:20]


def _initial_state():
    return {
        'game_running': False,
        'game': {'found': True, 'exe': r'E:\The Sims 4\Game\Bin\TS4_x64.exe', 'game_dir': r'E:\The Sims 4',
                 'source': 'EA app', 'store': 'ea', 'saved': False, 'message': r'The Sims 4 is at E:\The Sims 4.'},
        'profile': {'name': 'full', 'save_slot': None, 'label': 'All CC - every mod is loaded'},
        'graphics': {'state': 'sgr_full', 'label': "Simp4Sims 'SGR Full' - looks great but causes lag", 'can_tune': True,
                     'details': ['Sims far away are drawn in full detail, which slows the game down.',
                                 'Shadows and reflections are set higher than the game can use.']},
        'memory': {'free_gb': 7.8, 'total_gb': 31.3,
                   'warnings': ['Chrome is using 20 GB of memory - close it for a faster start'],
                   'top': [{'name': 'Chrome', 'gb': 20.1}, {'name': 'Discord', 'gb': 1.4}, {'name': 'Steam', 'gb': 0.6}]},
        'library': {'packages': 41236, 'gb': 259.3, 'cas_full': 755662, 'cas_fast': 15905},
        'fastpack': {'state': 'fresh', 'why': 'Up to date with your saves', 'gb': 7.6},
        'monitor': {'installed': True, 'where': 'Mods'},
        'load_times': _load_times([((3,), 'fast', 104.2, 21.5), ((26,), 'fast', 112.8, 24.1), ((53,), 'full', 402.6, 61.0),
                                   ((73,), 'fast', 98.4, 19.8), ((102,), 'full', 431.9, 66.3), ((123,), 'save', 121.0, 23.4),
                                   ((146,), 'full', 455.1, None), ((196,), 'full', 468.7, 70.2)]),
        'journals': [
            {'id': '20260924-101502-profile', 'kind': 'profile', 'state': 'committed', 'when': _ago(hours=3, minutes=4),
             'note': 'switch to full: park 0 files (0.0 GB), restore 189 files (251.6 GB)'},
            {'id': '20260924-101501-profile', 'kind': 'profile', 'state': 'committed', 'when': _ago(hours=3, minutes=4),
             'note': 'thumbnail cache moved aside before the switch to full (the game rebuilds it)'},
            {'id': '20260923-201133-inbox', 'kind': 'inbox', 'state': 'committed', 'when': _ago(days=1, hours=4),
             'note': '3 downloads'},
            {'id': '20260923-190210-profile', 'kind': 'profile', 'state': 'committed', 'when': _ago(days=1, hours=5),
             'note': 'switch to fast: park 189 files (251.6 GB), restore 0 files (0.0 GB)'},
            {'id': '20260923-185932-install', 'kind': 'install', 'state': 'committed', 'when': _ago(days=1, hours=5, minutes=3),
             'note': 'install SpeedKit Monitor'},
            {'id': '20260922-163045-dedup', 'kind': 'dedup', 'state': 'undone', 'when': _ago(days=2, hours=8),
             'note': 'identical policy: 12 packages'},
            {'id': '20260921-120001-merge', 'kind': 'merge', 'state': 'committed', 'when': _ago(days=3, hours=12),
             'note': '6 merged files from 812 packages'},
        ],
        'animator': {'installed': True, 'path': _ANIMATOR[0]},
        'disk': {'c_free_gb': 112.4},
        'saves': [
            {'slot': 'Slot_00000014', 'name': 'Wicked Nights', 'household': 'Novulon', 'world': 'Del Sol Valley',
             'last_played': _ago(hours=3), 'size_mb': 48.2, 'sims': 312, 'lots': 41, 'cc_parts': 12480,
             'cas_loaded': 14102, 'pack': {'state': 'fresh', 'gb': 2.9}},
            {'slot': 'Slot_00000009', 'name': 'Legacy Challenge', 'household': 'Goth', 'world': 'Willow Creek',
             'last_played': _ago(days=2, hours=1), 'size_mb': 36.7, 'sims': 245, 'lots': 33, 'cc_parts': 8315,
             'cas_loaded': 9870, 'pack': {'state': 'fresh', 'gb': 2.1}},
            {'slot': 'Slot_00000011', 'name': 'San Myshuno Apartment Life with a Very Long Save Name',
             'household': 'Landgraab-Bheeb Family', 'world': 'San Myshuno',
             'last_played': _ago(days=9), 'size_mb': 29.4, 'sims': 198, 'lots': 27, 'cc_parts': 5022,
             'cas_loaded': 6410, 'pack': {'state': 'stale', 'gb': 1.4}},
            {'slot': 'Slot_00000003', 'name': 'Build Test', 'household': None, 'world': 'Newcrest',
             'last_played': _ago(days=41), 'size_mb': 12.1, 'sims': 80, 'lots': 12, 'cc_parts': 640,
             'cas_loaded': None, 'cc_missing': 37, 'pack': {'state': 'missing', 'gb': None}},
        ],
        'inbox': [
            {'name': 'Sentate_Venus_Dress.package', 'status': 'would be done', 'where': None, 'reason': 'New CC'},
            {'name': 'Simstrouble_Hair_Pack.zip', 'status': 'would be done', 'where': None, 'reason': 'New CC (inside a zip)'},
            {'name': 'MCCC_2025.3.ts4script', 'status': 'would be done', 'where': None, 'reason': 'Script mod - added as it is'},
            {'name': 'OldHairs_2016.zip', 'status': 'refused', 'where': None, 'reason': "The zip file is damaged and can't be opened"},
        ],
    }


STATE = _initial_state()


def reset():
    """Back to the example data (tests call this between cases)."""
    global STATE
    with _lock:
        STATE = _initial_state()


def _run(progress, steps):
    """Report each (step, message) with a fake delay; the fraction climbs to 1."""
    n = len(steps)
    for i, (step, message) in enumerate(steps):
        if HOLD is not None and i >= HOLD_AT:
            HOLD.wait(60)
        if progress:
            progress(step, round(i / n, 3), message)
        if DELAY:
            time.sleep(DELAY)
    if progress and steps:
        progress(steps[-1][0], 1.0, steps[-1][1])


def _journal(kind, note):
    with _lock:
        now = datetime.now().replace(microsecond=0)
        STATE['journals'].insert(0, {'id': now.strftime('%Y%m%d-%H%M%S-') + kind, 'kind': kind, 'state': 'committed',
                                     'when': now.isoformat(), 'note': note})
        del STATE['journals'][15:]
        return STATE['journals'][0]['id']


def _busy():
    if STATE['game_running']:
        return {'ok': False, 'message': 'The Sims 4 is running. Close the game first, then try again.'}
    return None


# ------------------------------------------------------------------ reads
def status():
    with _lock:
        s = copy.deepcopy({k: v for k, v in STATE.items() if k not in ('saves', 'inbox')})
    s['ok'] = True
    return s


def list_saves(progress=None):
    _run(progress, [('saves', 'Looking at your saves...')] if progress else [])
    with _lock:
        return {'ok': True, 'saves': copy.deepcopy(STATE['saves'])}


# ------------------------------------------------------------------ play
_LABELS = {'fast': ('fast', 'Fast mode - only the CC your sims use'), 'full': ('full', 'All CC - every mod is loaded'),
           'studio': ('studio', 'Studio - the animation work set')}


def _target(target):
    if target in _LABELS:
        name, label = _LABELS[target]
        return {'name': name, 'save_slot': None, 'label': label}, None
    if isinstance(target, str) and target.startswith('save:'):
        slot = target[5:]
        save = next((s for s in STATE['saves'] if s['slot'] == slot), None)
        if not save:
            return None, "That save wasn't found. It may have been deleted or renamed."
        return {'name': 'save', 'save_slot': slot, 'label': "Play this save - only the CC of '%s'" % save['name']}, None
    return None, "I don't know that way to play."


def _prepare(target, progress, launch):
    bad = _busy()
    if bad:
        return dict(bad, launched=False, steps=[{'step': 'check', 'ok': False, 'message': bad['message']}])
    profile, err = _target(target)
    if err:
        return {'ok': False, 'message': err, 'launched': False, 'steps': []}
    if not STATE['game']['found']:
        return {'ok': False, 'message': "The Sims 4 wasn't found on this PC. Use \"Locate The Sims 4\" first.",
                'launched': False, 'steps': []}
    steps = [('check', 'Making sure the game is closed'),
             ('scan', 'Looking for new or changed CC'),
             ('monitor', 'Updating the SpeedKit Monitor'),
             ('graphics', 'Checking your graphics settings'),
             ('pack', 'Getting the CC your saves use ready'),
             ('switch', 'Setting up your Mods folder'),
             ('memory', 'Checking free memory')]
    if launch:
        steps.append(('launch', 'Starting The Sims 4'))
    _run(progress, steps)
    out = [{'step': s, 'ok': True, 'message': m} for s, m in steps if s != 'memory']
    with _lock:
        if STATE['graphics']['state'] == 'sgr_full':
            _tune_state()
        mem = STATE['memory']
        notes = mem['warnings'] or ['Memory: %.1f GB free - fine.' % mem['free_gb']]
        for w in notes:
            out.insert(len(out) - 1 if launch else len(out), {'step': 'memory', 'ok': True, 'message': w})
        changed = STATE['profile'] != profile
        STATE['profile'] = profile
    if changed:
        _journal('profile', 'switch to %s: park 189 files (251.6 GB), restore 0 files (0.0 GB)' % profile['name'])
    if launch:
        msg = 'Preview only: everything is ready, but the game was not started.'
    else:
        msg = 'Ready. Everything is prepared - start the game whenever you like.'
    return {'ok': True, 'message': msg, 'launched': False, 'steps': out}


def play(target, progress=None):
    return _prepare(target, progress, launch=True)


def prepare(target, progress=None):
    return _prepare(target, progress, launch=False)


# ------------------------------------------------------------------ changes
def undo_last(progress=None):
    bad = _busy()
    if bad:
        return dict(bad, journal=None)
    with _lock:
        last = next((j for j in STATE['journals'] if j['state'] == 'committed'
                     and not j['note'].startswith(('thumbnail cache moved aside', 'bring the fast pack home'))), None)
    if not last:
        return {'ok': False, 'message': 'There is nothing to undo.', 'journal': None}
    _run(progress, [('check', 'Making sure the game is closed'), ('undo', 'Putting your files back'),
                    ('verify', 'Checking everything is back')])
    with _lock:
        last['state'] = 'undone'
        if last['kind'] == 'settings':
            STATE['graphics'].update(state='sgr_full', label="Simp4Sims 'SGR Full' - looks great but causes lag", can_tune=True)
        if last['kind'] == 'profile':
            STATE['profile'] = {'name': 'full', 'save_slot': None, 'label': 'All CC - every mod is loaded'}
    on_undo(last)                    # patch day / save backups (stub_care.py)
    return {'ok': True, 'message': 'Undid the change from %s.' % last['when'].replace('T', ' '), 'journal': last['id']}


def inbox(apply=False, progress=None):
    path = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\SpeedKit\Inbox'
    with _lock:
        items = copy.deepcopy(STATE['inbox'])
    if not apply:
        _run(progress, [('look', 'Looking in your Inbox folder')] if progress else [])
        n = len(items)
        msg = ("%d downloads are waiting. Press 'Add to game' to add them." % n) if n else \
            'Your Inbox is empty. Drop downloads into it, then press this again.'
        return {'ok': True, 'message': msg, 'items': items, 'inbox_path': path}
    bad = _busy()
    if bad:
        return dict(bad, items=items, inbox_path=path)
    if not [it for it in items if it['status'] != 'refused']:
        return {'ok': True, 'message': 'Your Inbox is empty. Drop downloads into it, then press this again.', 'items': items,
                'inbox_path': path}
    _run(progress, [('check', 'Making sure the game is closed'), ('unpack', 'Unpacking zip files'),
                    ('sort', 'Sorting CC and script mods'), ('merge', 'Adding the new CC to your library'),
                    ('verify', 'Checking the game will load it')])
    items = [it for it in items if it['status'] != 'refused']
    for it in items:
        it['status'] = 'done'
        it['where'] = 'Mods\\SpeedKit Merged' if it['name'].endswith(('.package', '.zip')) else 'Mods'
    with _lock:
        STATE['inbox'] = [it for it in STATE['inbox'] if it['status'] == 'refused']
        STATE['library']['packages'] += len(items)
    _journal('inbox', '%d downloads' % len(items))
    return {'ok': True, 'message': 'Installed %d of %d downloads.' % (len(items), len(items) + 1), 'items': items,
            'inbox_path': path}


def cleanup_plan(progress=None):
    _run(progress, [('scan', 'Looking at your CC library'), ('compare', 'Finding CC stored more than once'),
                    ('plan', 'Working out what can go safely')])
    return {'ok': True, 'message': 'You can free up 18.2 GB by removing 4,210 extra copies.',
            'copies': 4210, 'gb': 18.2, 'rewritten': 57, 'removed': 12}


def cleanup_apply(progress=None):
    bad = _busy()
    if bad:
        return dict(bad, journal=None)
    _run(progress, [('check', 'Making sure the game is closed'), ('copy', 'Removing extra copies'),
                    ('verify', 'Checking the game loads exactly the same CC')])
    jid = _journal('dedup', 'identical policy: 69 packages')
    with _lock:
        STATE['library']['gb'] = round(STATE['library']['gb'] - 18.2, 1)
        STATE['disk']['c_free_gb'] = round(STATE['disk']['c_free_gb'] + 18.2, 1)
    return {'ok': True, 'message': 'Freed up 18.2 GB. Your game will look exactly the same.', 'journal': jid}


_TABLE = [
    {'setting': 'RenderSimLODDistances', 'stock': '25, 50, 100, 1000', 'before': '3000, 3000, 3000, 3000', 'after': '50, 100, 200, 2000'},
    {'setting': 'RenderSimTextureSizes', 'stock': '2048, 1024, 512, 128', 'before': '2048, 2048, 2048, 2048', 'after': '2048, 2048, 1024, 512'},
    {'setting': 'ObjectSizeCullFactor', 'stock': '200', 'before': '9999', 'after': '200'},
    {'setting': 'ObjectLODBias', 'stock': '0.6666', 'before': '0.00', 'after': '0.6666'},
    {'setting': 'ClipPlaneDistances', 'stock': '0.1, 5, 1000, 1500', 'before': '0.1, 0.42, 9999, 9999', 'after': '0.1, 0.42, 1000, 1500'},
    {'setting': 'FSAALevel', 'stock': '8', 'before': '512', 'after': '8'},
    {'setting': 'ShadowMapSize', 'stock': '2048', 'before': '5120', 'after': '4096'},
    {'setting': 'MirrorFadeRadiusThreshold', 'stock': '1.3', 'before': '120', 'after': '2.6'},
    {'setting': 'InteriorMirrorFarPlane', 'stock': '75', 'before': '900', 'after': '150'},
    {'setting': 'ExteriorMirrorFarPlane', 'stock': '150', 'before': '1200', 'after': '300'},
    {'setting': 'TerrainLODBoost', 'stock': '1', 'before': '6', 'after': '2'},
]


_WHAT = {'RenderSimLODDistances': 'Distances (m) where Sims switch to simpler models (2x stock)',
         'ClipPlaneDistances': 'Clip planes near..far in metres (far = stock, near stays)'}
_TABLE = [dict(r, prop=r['setting'], setting=_WHAT.get(r['setting'], r['setting'])) for r in _TABLE]


def _tune_state():
    STATE['graphics'].update(state='tuned', label='SpeedKit Max Quality - sharp graphics without the lag', can_tune=False,
                             details=['Everything still looks like SGR Full up close.',
                                      'Only the settings that caused lag were brought back to sane values.'])


def graphics_tune(apply=False):
    with _lock:
        tuned = STATE['graphics']['state'] == 'tuned'
    if not apply:
        return {'ok': True, 'message': 'Your graphics already have the lag fix.' if tuned else
                'These settings would change. Everything else stays at max quality.', 'table': copy.deepcopy(_TABLE)}
    bad = _busy()
    if bad:
        return dict(bad, table=[])
    if tuned:
        return {'ok': True, 'message': 'Your graphics already have the lag fix.', 'table': copy.deepcopy(_TABLE)}
    if DELAY:
        time.sleep(DELAY * 2)
    with _lock:
        _tune_state()
    _journal('settings', r'graphics: SpeedKit Max Quality (from ConfigOverride\GraphicsRules.sgr)')
    return {'ok': True, 'message': 'Done! Max quality graphics, without the lag.', 'table': copy.deepcopy(_TABLE)}


def graphics_restore(apply=False):
    with _lock:
        tuned = STATE['graphics']['state'] == 'tuned'
    if not tuned:
        return {'ok': False, 'message': 'There is no graphics change to put back.'}
    if not apply:
        return {'ok': True, 'message': 'Your old graphics file (SGR Full) would come back.'}
    bad = _busy()
    if bad:
        return bad
    with _lock:
        STATE['graphics'].update(state='sgr_full', label="Simp4Sims 'SGR Full' - looks great but causes lag", can_tune=True)
    _journal('settings', 'graphics: restore the file SpeedKit Max Quality replaced')
    return {'ok': True, 'message': 'Your old graphics file is back.'}


def report(progress=None):
    _run(progress, [('scan', 'Looking at your CC library'), ('write', 'Writing the report')])
    return {'ok': True, 'message': 'Your library report is ready.',
            'path': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\SpeedKit\reports\library_report.html'}


# ------------------------------------------------------------------ finding the game (a fake PC)
_DRIVES = [{'name': 'C:', 'label': 'Windows', 'free_gb': 112.4}, {'name': 'D:', 'label': 'Data', 'free_gb': 640.9},
           {'name': 'E:', 'label': 'Games', 'free_gb': 402.0}]
_TREE = {
    'C:\\': ['Program Files', 'Program Files (x86)', 'Users', 'Windows'],
    'C:\\Program Files': ['EA Games', 'Google', 'Microsoft Office', 'WindowsApps'],
    'C:\\Program Files\\EA Games': ['Apex Legends'],
    'C:\\Program Files (x86)': ['Origin Games', 'Steam'],
    'C:\\Program Files (x86)\\Origin Games': [],
    'C:\\Program Files (x86)\\Steam': ['steamapps'],
    'C:\\Program Files (x86)\\Steam\\steamapps': ['common'],
    'C:\\Program Files (x86)\\Steam\\steamapps\\common': [],
    'C:\\Users': ['basim', 'Public'],
    'D:\\': ['Backups', 'Music', 'Photos'],
    'E:\\': ['SteamLibrary', 'The Sims 4', 'Videos'],
    'E:\\SteamLibrary': ['steamapps'],
    'E:\\SteamLibrary\\steamapps': ['common'],
    'E:\\SteamLibrary\\steamapps\\common': ['Cities Skylines'],
}
_GAME_DIRS = {'E:\\The Sims 4'}
_HINTS = {'C:\\Program Files\\EA Games': 'EA games folder', 'C:\\Program Files (x86)\\Origin Games': 'EA games folder',
          'E:\\SteamLibrary': 'Steam', 'C:\\Program Files (x86)\\Steam': 'Steam', 'E:\\The Sims 4': 'Looks like The Sims 4',
          'E:\\SteamLibrary\\steamapps': 'Steam library'}


def _norm(path):
    p = (path or '').strip().replace('/', '\\')
    if len(p) == 2 and p[1] == ':':
        p += '\\'
    if len(p) > 3:
        p = p.rstrip('\\')
    return p[:1].upper() + p[1:] if p else ''


def browse(path=None):
    """This PC (path None/''), or one folder of the fake PC."""
    suggestions = [{'name': 'E:\\The Sims 4', 'path': 'E:\\The Sims 4', 'exe': 'E:\\The Sims 4\\Game\\Bin\\TS4_x64.exe',
                    'source': 'EA app', 'is_game': True, 'hint': 'Found automatically (EA app)'}]
    p = _norm(path)
    if not p:
        entries = [{'name': '%s (%s)' % (d['name'], d['label']), 'path': d['name'] + '\\', 'is_game': False,
                    'hint': '%.0f GB free' % d['free_gb']} for d in _DRIVES]
        return {'ok': True, 'message': 'This PC', 'path': None, 'parent': None, 'drives': copy.deepcopy(_DRIVES),
                'entries': entries, 'is_game': False, 'suggestions': suggestions}
    if p in _GAME_DIRS:
        kids = ['Data', 'Delta', 'Game', '__Installer']
    elif p in _TREE:
        kids = _TREE[p]
    elif p.upper()[:3] in _TREE and p.count('\\') >= 1:
        kids = []                        # any other folder of the fake PC is empty
    else:
        return {'ok': False, 'message': "That folder can't be opened.", 'path': p, 'parent': None,
                'drives': copy.deepcopy(_DRIVES), 'entries': [], 'suggestions': suggestions}
    base = p if p.endswith('\\') else p + '\\'
    entries = []
    for name in kids:
        full = base + name
        entries.append({'name': name, 'path': full, 'is_game': full in _GAME_DIRS, 'hint': _HINTS.get(full)})
    parent = None if p.endswith(':\\') else (p.rsplit('\\', 1)[0] + ('\\' if p.count('\\') == 1 else ''))
    here = p in _GAME_DIRS
    return {'ok': True, 'message': 'This is The Sims 4.' if here else '%d folders' % len(entries), 'path': p,
            'parent': parent, 'drives': copy.deepcopy(_DRIVES), 'entries': entries, 'is_game': here,
            'suggestions': suggestions}


def set_game_path(path):
    p = _norm(path)
    if p not in _GAME_DIRS:
        return {'ok': False, 'message': "That folder isn't The Sims 4. Pick the folder that has the Game and Data "
                                        "folders inside it."}
    exe = p + '\\Game\\Bin\\TS4_x64.exe'
    with _lock:
        STATE['game'] = {'found': True, 'exe': exe, 'game_dir': p, 'source': 'your choice', 'store': 'ea', 'saved': True,
                         'message': 'The Sims 4 is at %s.' % p}
    return {'ok': True, 'message': 'Saved - the Hub will remember this.', 'exe': exe, 'game_dir': p}


# ------------------------------------------------------------------ open (never opens anything here)
_FOLDERS = {'mods': 'Mods', 'reports': 'reports', 'inbox': 'Inbox', 'saves': 'saves', 'quarantine': 'safe copies'}


def open_animator():
    """The engine starts 'Wicked Animator.exe' (or, without it, 'Start Wicked Animator.bat'); the preview only says so."""
    with _lock:
        if not STATE['animator']['installed']:
            return {'ok': False, 'message': "Novulon's Wicked Animator isn't installed on this PC."}
    which = next((os.path.basename(p) for p in _ANIMATOR if os.path.isfile(p)), os.path.basename(_ANIMATOR[0]))
    return {'ok': True, 'message': "Preview: Novulon's Wicked Animator would open now (%s)." % which}


def open_folder(which):
    if which not in _FOLDERS:
        return {'ok': False, 'message': "I don't know that folder."}
    return {'ok': True, 'message': 'Preview: your %s folder would open now.' % _FOLDERS[which]}


def open_path(path):
    """Used by the server for the report page; the preview has no real report to show."""
    return {'ok': True, 'message': 'Preview: the library report would open now.'}


# ------------------------------------------------------------------ patch day, game errors, save backups, load times
from speedkit.hub.stub_care import (patch_day, patch_seen, game_errors, errors_seen, save_health,  # noqa: E402,F401
                                   load_savings, set_aside, put_back, backup_saves, restore_saves, on_undo)

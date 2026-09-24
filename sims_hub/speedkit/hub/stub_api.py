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
        'profile': {'name': 'full', 'save_slot': None, 'label': 'Full Start - all CC is loaded'},
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
        _cc_reset()


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
_LABELS = {'fast': ('fast', 'Quick Start - only the CC your sims use'), 'full': ('full', 'Full Start - all CC is loaded'),
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
            STATE['profile'] = {'name': 'full', 'save_slot': None, 'label': 'Full Start - all CC is loaded'}
        if last['kind'] == 'setaside':
            _cc_restore(last['id'])
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
# ------------------------------------------------------------------ the CC browser (docs/ccbrowser.md)
# Example CC with little generated pictures (a tiny PNG writer: no Pillow needed for the preview). CC holds the
# browser's state; reset() puts it back. Test knob: CC['ready'] = False shows the "not sorted yet" page.
import hashlib as _hashlib
import random as _random
import struct as _struct
import zlib as _zlib

_CC_CATEGORIES = [
    ('hair', 'Hair'), ('hat', 'Hats'), ('top', 'Tops'), ('bottom', 'Bottoms'), ('fullbody', 'Full outfits'),
    ('shoes', 'Shoes'), ('accessory', 'Accessories'), ('makeup', 'Makeup'), ('eyes', 'Eyes & brows'),
    ('skin', 'Skin & tattoos'), ('cas_other', 'Other CAS'), ('pets', 'Pets'), ('sliders', 'Sliders & presets'),
    ('buildbuy', 'Build/Buy objects'), ('walls', 'Walls & floors'), ('poses', 'Poses & animations'),
    ('gameplay', 'Gameplay mods'), ('script', 'Script mods'), ('other', 'Other'),
]
_CC_LABELS = dict(_CC_CATEGORIES)
# category -> (how many, folder, creators, things, body name, hue)
_CC_PLAN = {
    'hair': (46, 'Hair', ['Simstrouble', 'Simpliciaty', 'Wingssims', 'Anto', 'Sonyasims'],
             ['Braids', 'Nala', 'Bun', 'Curls', 'Bob', 'Waves', 'Afro Puff', 'Pixie', 'Ponytail', 'Locs'], 'Hair', 0.93),
    'hat': (8, 'Accessories', ['Sentate', 'Trillyke'], ['Beret', 'Cap', 'Sun Hat'], 'Hat', 0.08),
    'top': (34, 'Clothes', ['Sentate', 'Trillyke', 'Madlen', 'Serenity'],
            ['Crop Top', 'Hoodie', 'Blouse', 'Sweater', 'Tank', 'Shirt'], 'Top', 0.60),
    'bottom': (22, 'Clothes', ['Trillyke', 'Madlen', 'Christopher067'], ['Jeans', 'Skirt', 'Cargo Pants', 'Shorts'],
               'Bottom', 0.55),
    'fullbody': (24, 'Clothes', ['Sentate', 'Serenity', 'Arethabee'], ['Venus Dress', 'Gown', 'Jumpsuit', 'Sundress'],
                 'Full outfit', 0.83),
    'shoes': (16, 'Clothes', ['Madlen', 'Sentate'], ['Boots', 'Heels', 'Sneakers', 'Sandals'], 'Shoes', 0.03),
    'accessory': (22, 'Accessories', ['Trillyke', 'Arethabee'], ['Earrings', 'Necklace', 'Rings', 'Glasses'],
                  'Earrings', 0.14),
    'makeup': (20, 'Makeup', ['Pralinesims', 'Sammi'], ['Lipstick', 'Blush', 'Eyeliner', 'Eyeshadow'], 'Lipstick', 0.97),
    'eyes': (10, 'Makeup', ['Pralinesims', 'Northern Siberia Winds'], ['Eyes', 'Brows'], 'Eye color', 0.50),
    'skin': (12, 'Skin', ['Sammi', 'Pyxis'], ['Skin Overlay', 'Freckles', 'Tattoo'], 'Freckles', 0.07),
    'sliders': (6, 'Sliders', ['Luumia', 'Ellie'], ['Height Slider', 'Nose Preset'], None, 0.72),
    'buildbuy': (40, 'BuildBuy', ['Peacemaker', 'Felixandre', 'Harrie', 'Syboulette', 'Mxims'],
                 ['Sofa', 'Armchair', 'Plant', 'Bookcase', 'Lamp', 'Rug', 'Kitchen', 'Bed'], None, 0.10),
    'walls': (8, 'BuildBuy', ['Peacemaker', 'Harrie'], ['Brick Walls', 'Wood Floors', 'Tiles'], None, 0.04),
    'poses': (8, 'Poses', ['Katverse', 'Flowerchamber'], ['Couple Poses', 'Selfie Poses', 'Family Poses'], None, 0.78),
    'gameplay': (10, 'Gameplay', ['LittleMsSam', 'Kawaiistacie', 'Zerbu'],
                 ['Better Autonomy', 'Slice of Life', 'No Autosave', 'More Traits'], None, None),
    'script': (8, 'Scripts', ['mc', 'TwistedMexi', 'Lumpinou'],
               ['cmd_center', 'BetterExceptions', 'RPO', 'TOOL'], None, None),
}
_CC_MISSING_KINDS = {'cas': 'Clothing, hair, makeup or another Create a Sim item',
                     'object': 'A Build/Buy object on a lot', 'look': 'A skin tone, slider or preset'}
CC = {}
_CC_PNG = {}


def _png(w, h, pixels):
    """A PNG (RGBA, 8 bit) from rows of bytes."""
    def chunk(kind, data):
        return _struct.pack('>I', len(data)) + kind + data + _struct.pack('>I', _zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b''.join(b'\x00' + bytes(row) for row in pixels)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', _struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', _zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def _hsv(h, s, v):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def _seg(u, v, a, b, width):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    k = max(0.0, min(1.0, ((u - ax) * dx + (v - ay) * dy) / (dx * dx + dy * dy or 1)))
    return (u - ax - k * dx) ** 2 + (v - ay - k * dy) ** 2 < width * width


def _shape(cat, u, v):
    """0 background, 1 the thing, 2 its second colour."""
    if cat == 'hair':
        if (u - .5) ** 2 / .04 + (v - .56) ** 2 / .05 < 1:
            return 2
        return 1 if (u - .5) ** 2 + (v - .45) ** 2 < .1 or (abs(u - .5) < .31 and .45 < v < .86) else 0
    if cat == 'hat':
        return 1 if ((u - .5) ** 2 / .16 + (v - .62) ** 2 / .006 < 1) or (abs(u - .5) < .2 and .32 < v < .62) else 0
    if cat == 'top':
        return 1 if (abs(u - .5) < .2 and .28 < v < .86) or (.28 < v < .48 and abs(u - .5) < .2 + (.48 - v) * 1.2) else 0
    if cat == 'bottom':
        return 1 if (.24 < v < .34 and abs(u - .5) < .2) or (.24 < v < .9 and .03 < abs(u - .5) < .2) else 0
    if cat == 'fullbody':
        return 1 if .18 < v < .9 and abs(u - .5) < .1 + (v - .18) * .42 else 0
    if cat == 'shoes':
        return 1 if (u - .5) ** 2 / .12 + (v - .66) ** 2 / .012 < 1 or (abs(u - .66) < .08 and .45 < v < .66) else 0
    if cat == 'accessory':
        d = (u - .5) ** 2 + (v - .56) ** 2
        return 2 if (u - .5) ** 2 + (v - .3) ** 2 < .006 else 1 if .03 < d < .06 else 0
    if cat == 'makeup':
        return 2 if abs(u - .5) < .09 and .22 < v < .45 and v > .22 + abs(u - .5) else \
            1 if abs(u - .5) < .12 and .45 < v < .86 else 0
    if cat == 'eyes':
        return 2 if (u - .5) ** 2 + (v - .5) ** 2 < .012 else 1 if (u - .5) ** 2 / .1 + (v - .5) ** 2 / .02 < 1 else 0
    if cat == 'skin':
        return 2 if (int(u * 11) + int(v * 13)) % 7 == 0 and (u - .5) ** 2 + (v - .5) ** 2 < .1 else \
            1 if (u - .5) ** 2 + (v - .5) ** 2 < .12 else 0
    if cat == 'sliders':
        for y in (.3, .5, .7):
            if abs(v - y) < .015 and .18 < u < .82:
                return 1
            if (u - (.3 + y * .5)) ** 2 + (v - y) ** 2 < .003:
                return 2
        return 0
    if cat == 'buildbuy':                       # a sofa: back, cushions, arms, little legs
        if .52 < v < .64 and .24 < u < .76:
            return 2
        return 1 if ((.3 < v < .52 and .2 < u < .8) or (.42 < v < .72 and (.12 < u < .26 or .74 < u < .88)) or
                     (.52 < v < .72 and .12 < u < .88) or (.72 <= v < .78 and (.16 < u < .2 or .8 < u < .84))) else 0
    if cat == 'walls':
        row = int(v * 8)
        return 1 if ((u * 4 + (row % 2) * .5) % 1) > .08 and (v * 8) % 1 > .12 else 2
    if cat == 'poses':
        return 1 if (_seg(u, v, (.5, .38), (.5, .66), .03) or _seg(u, v, (.5, .66), (.38, .88), .03) or
                     _seg(u, v, (.5, .66), (.62, .88), .03) or _seg(u, v, (.5, .45), (.3, .3), .03) or
                     _seg(u, v, (.5, .45), (.7, .56), .03) or (u - .5) ** 2 + (v - .28) ** 2 < .006) else 0
    return 1 if (u - .5) ** 2 + (v - .5) ** 2 < .08 else 0


def _cc_draw(cat, seed, size=128):
    """A little picture for one example item: a soft gradient in the category's colour and the thing's shape."""
    key = (cat, seed % 7, size)
    if key in _CC_PNG:
        return _CC_PNG[key]
    hue = (_CC_PLAN.get(cat, (0, 0, 0, 0, 0, .7))[5] or .7) + (seed % 7 - 3) * .012
    top, bottom = _hsv(hue % 1, .35, .98), _hsv(hue % 1, .55, .78)
    thing, second = _hsv((hue + .02) % 1, .75, .55), _hsv((hue + .5) % 1, .25, .98)
    if cat in ('hair', 'hat'):
        second = (242, 200, 170)                # a face under the hair
    rows = []
    for y in range(size):
        v = y / size
        bg = tuple(int(top[k] + (bottom[k] - top[k]) * v) for k in range(3))
        row = bytearray()
        for x in range(size):
            s = _shape(cat, x / size, v)
            c = thing if s == 1 else second if s == 2 else bg
            row += bytes((c[0], c[1], c[2], 255))
        rows.append(row)
    _CC_PNG[key] = _png(size, size, rows)
    return _CC_PNG[key]


def _cc_items():
    rnd = _random.Random(20260924)
    items = []
    n = 0
    base = datetime.now().replace(microsecond=0)
    for cat, (count, folder, creators, things, body, hue) in _CC_PLAN.items():
        for k in range(count):
            n += 1
            creator = creators[k % len(creators)]
            thing = things[(k // len(creators)) % len(things)]
            script = cat == 'script'
            name = ('%s_%s.ts4script' % (creator, thing.replace(' ', '')) if script else
                    '%s_%s_%02d.package' % (creator, thing.replace(' ', ''), k + 1) if k % 5 else
                    '[%s] %s.package' % (creator, thing))
            cas = cat in ('hair', 'hat', 'top', 'bottom', 'fullbody', 'shoes', 'accessory', 'makeup', 'eyes', 'skin')
            body = {'Rings': 'Ring', 'Brows': 'Eyebrows', 'Eyes': 'Eye color', 'Skin Overlay': 'Skin overlay'}.get(
                thing, thing if cat in ('accessory', 'makeup', 'skin') else _CC_PLAN[cat][4])
            items.append({
                'id': n, 'name': name, 'rel': '%s/%s' % (folder, name), 'folder': folder, 'creator': creator,
                'kind': 'script' if script else 'package', 'category': cat, 'category_label': _CC_LABELS[cat],
                'cats': [cat], 'body': body, 'part_name': ('y%s%s_%s' % ('f' if k % 2 else 'm', body.replace(' ', ''),
                                                                           thing.replace(' ', ''))) if body else None,
                'size_mb': round(rnd.uniform(0.2, 38.0 if cat == 'buildbuy' else 12.0), 2),
                'modified': (base - timedelta(days=rnd.randint(0, 900), minutes=rnd.randint(0, 1400))).isoformat(),
                'cas_parts': rnd.randint(1, 40) if cas else 0, 'objects': rnd.randint(1, 6) if cat == 'buildbuy' else 0,
                'pic': None if (hue is None or (cas and k % 9 == 8)) else 'p%d' % n, 'in_mods': k % 11 != 10,
                'used': None if cat in ('script', 'gameplay', 'poses') else k % 3 != 2,
                'used_by': [], 'broken': None, 'duplicate_of': None,
            })
    saves = ['Wicked Nights', 'Legacy Challenge', 'San Myshuno Apartment Life with a Very Long Save Name', 'Build Test']
    for it in items:
        if it['used']:
            it['used_by'] = sorted({saves[(it['id'] * 7 + j) % 4] for j in range(1 + it['id'] % 3)})
    # a few files that hold the same CC as another file, and two damaged ones
    groups = {}
    for it in items:
        groups.setdefault((it['category'], it['creator']), []).append(it)
    for cat in ('hair', 'fullbody', 'buildbuy'):
        a, b = next(g for (c, _), g in groups.items() if c == cat and len(g) > 1)[:2]
        a['duplicate_of'], b['duplicate_of'] = b['name'], a['name']
    for cat, k, why in (('shoes', 3, "This file is damaged: the game can't read it."), ('gameplay', 1, 'This file is empty.')):
        it = [x for x in items if x['category'] == cat][k]
        it.update(broken=why, pic=None, used=None if cat == 'gameplay' else False)
    return items


def _cc_reset():
    CC.clear()
    CC.update({'ready': True, 'when': (datetime.now() - timedelta(hours=2)).replace(microsecond=0).isoformat(),
               'items': _cc_items(), 'aside': {}})


_cc_reset()


def _cc_match(it, category=None, folder=None, creator=None, q=None, used=None, flag=None):
    if category and category not in it['cats']:
        return False
    if folder and it['folder'] != ('' if folder == '(root)' else folder):
        return False
    if creator and it['creator'] != creator:
        return False
    if q:
        hay = ' '.join(str(x or '') for x in (it['rel'], it['part_name'], it['creator'])).lower()
        if not all(w in hay for w in q.lower().split()):
            return False
    if used == 'used' and it['used'] is not True:
        return False
    if used == 'unused' and it['used'] is not False:
        return False
    if flag == 'duplicate' and not it['duplicate_of']:
        return False
    if flag == 'broken' and not it['broken']:
        return False
    return True


_CC_SORTS = {'name': lambda it: (it['name'].lower(), it['id']), 'newest': lambda it: (it['modified'], it['id']),
             'biggest': lambda it: (it['size_mb'], it['id']), 'folder': lambda it: (it['folder'].lower(), it['name'].lower()),
             'category': lambda it: (it['category'], it['name'].lower())}


def _cc_state():
    return {'state': 'ready' if CC['ready'] else 'missing', 'items': len(CC['items']) if CC['ready'] else 0,
            'when': CC['when'] if CC['ready'] else None, 'used_known': CC['ready'], 'complete': True, 'generation': 1}


def cc_list(category=None, folder=None, creator=None, q=None, used=None, flag=None, sort='name', offset=0, limit=60,
            facets=False):
    with _lock:
        items = list(CC['items']) if CC['ready'] else []
        state = _cc_state()
    offset, limit = max(0, int(offset or 0)), max(1, min(200, int(limit or 60)))
    f = dict(folder=folder, creator=creator, q=q, used=used, flag=flag)
    hits = [it for it in items if _cc_match(it, category=category, **f)]
    hits.sort(key=_CC_SORTS.get(sort, _CC_SORTS['name']), reverse=sort in ('newest', 'biggest'))
    counts = {}
    for it in items:
        if _cc_match(it, **f):
            for c in it['cats']:
                counts[c] = counts.get(c, 0) + 1
    base = [it for it in items if _cc_match(it, category=category, folder=folder, creator=creator, q=q)]
    out = {'ok': True, 'index': state, 'total': len(hits), 'offset': offset, 'limit': limit,
           'items': copy.deepcopy(hits[offset:offset + limit]),
           'categories': [{'key': k, 'label': lbl, 'n': counts.get(k, 0)} for k, lbl in _CC_CATEGORIES],
           'flags': {'used': sum(1 for it in base if it['used'] is True),
                     'unused': sum(1 for it in base if it['used'] is False),
                     'duplicate': sum(1 for it in base if it['duplicate_of']),
                     'broken': sum(1 for it in base if it['broken'])}}
    if facets:
        folders, creators = {}, {}
        for it in items:
            folders[it['folder'] or '(root)'] = folders.get(it['folder'] or '(root)', 0) + 1
            creators[it['creator']] = creators.get(it['creator'], 0) + 1
        out['folders'] = [{'name': k, 'n': v} for k, v in sorted(folders.items(), key=lambda kv: kv[0].lower())]
        out['creators'] = [{'name': k, 'n': v} for k, v in sorted(creators.items(), key=lambda kv: kv[0].lower())
                           if v > 1]
    if not CC['ready']:
        out['message'] = "CC files have not been sorted yet. Use 'Sort CC files'; the first run takes a few minutes."
    return out


def _cc_find(item_id):
    with _lock:
        return next((it for it in CC['items'] if it['id'] == item_id), None)


def cc_item(item_id):
    it = _cc_find(item_id)
    if not it:
        return {'ok': False, 'message': 'That file is no longer in the CC list. Use "Look again".'}
    root = 'Mods' if it['in_mods'] else 'Mods_parked'
    return dict(copy.deepcopy(it), ok=True,
                path='C:\\Users\\basim\\Documents\\Electronic Arts\\The Sims 4\\%s\\%s' % (root, it['rel'].replace('/', '\\')))


def cc_picture(item_id=None, kind=None, instance=None):
    """Image bytes, like the engine's (the server sends them as they are)."""
    if item_id is not None:
        it = _cc_find(item_id)
        if not it or not it['pic']:
            return {'ok': False, 'message': 'No picture.'}
        return {'ok': True, 'data': _cc_draw(it['category'], it['id']), 'type': 'image/png'}
    try:
        n = int(str(instance), 16)
    except ValueError:
        return {'ok': False, 'message': 'No picture.'}
    cat = _CC_PART_CATS.get(n)
    if cat is None or n % 3 == 0 and n >= 0xDEAD000000000000:       # some missing CC has no picture anywhere
        return {'ok': False, 'message': 'No picture.'}
    return {'ok': True, 'data': _cc_draw(cat, n), 'type': 'image/png'}


_CC_PART_CATS = {}


def cc_scan(progress=None):
    with _lock:
        n = len(CC['items'])
    _run(progress, [('library', 'Looking for new or changed CC files'),
                    ('saves', 'Reading which CC the saves use'),
                    ('cc', 'Sorting CC files: %s of %s' % (format(n // 2, ','), format(n, ','))),
                    ('cc', 'Finding duplicate and damaged files'),
                    ('done', 'Sorted %s CC files' % format(n, ','))])
    with _lock:
        CC['ready'] = True
        CC['when'] = datetime.now().replace(microsecond=0).isoformat()
    return {'ok': True, 'message': 'Sorted %s CC files into categories.' % format(n, ','), 'items': n,
            'read': 12, 'seconds': 4.2}


def cc_set_aside(ids, progress=None):
    nothing = {'ok': False, 'message': 'Pick the files to set aside first.', 'journal': None, 'done': [], 'refused': []}
    if not ids:
        return nothing
    bad = _busy()
    if bad:
        return dict(nothing, message=bad['message'])
    done, refused = [], []
    with _lock:
        for i in ids:
            it = next((x for x in CC['items'] if x['id'] == i), None)
            if it is None:
                refused.append({'name': '#%s' % i, 'why': 'It is no longer in the CC list. Use "Look again".'})
            elif it['kind'] == 'script':
                refused.append({'name': it['name'], 'why': 'Script mods are not changed by the Hub.'})
            elif not it['in_mods']:
                refused.append({'name': it['name'], 'why': "It is not in the Mods folder right now (moved out by Quick Start or "
                                                           "one-save mode). Switch to Full Start first."})
            else:
                done.append(it)
    if not done:
        return dict(nothing, message=('Nothing was set aside. %s' % (refused[0]['why'] if refused else '')).strip(),
                    refused=refused)
    _run(progress, [('check', 'Making sure the game is closed')] +
         [('setaside', 'Setting aside %s' % it['name']) for it in done[:6]])
    names = [it['name'] for it in done]
    jid = _journal('setaside', 'set aside %d CC file%s: %s' % (len(done), '' if len(done) == 1 else 's',
                                                              ', '.join(names[:5])))
    with _lock:
        CC['aside'][jid] = done
        CC['items'] = [x for x in CC['items'] if x not in done]
        STATE['library']['packages'] -= len(done)
    msg = ('Set aside %d file%s. They are kept safe - "Undo last change" on the Tools page puts them back.'
           % (len(done), '' if len(done) == 1 else 's'))
    if refused:
        msg += ' %d file%s stayed where %s.' % (len(refused), '' if len(refused) == 1 else 's',
                                                'it was' if len(refused) == 1 else 'they were')
    return {'ok': True, 'message': msg, 'journal': jid, 'done': names, 'refused': refused}


def _cc_restore(jid):
    """undo_last of a 'setaside' change: the files come back."""
    back = CC['aside'].pop(jid, [])
    CC['items'] = sorted(CC['items'] + back, key=lambda it: it['id'])
    STATE['library']['packages'] += len(back)


def cc_open(item_id):
    it = _cc_find(item_id)
    if not it:
        return {'ok': False, 'message': 'That file is no longer in the CC list. Use "Look again".'}
    return {'ok': True, 'message': 'Preview: the folder of %s would open now.' % it['name']}


_CC_SIMS = {
    'Slot_00000014': [('Novulon', True, ['Ava Novulon', 'Luna Novulon', 'Kai Novulon', 'Mira Novulon']),
                      ('Bheeb', False, ['Bella Bheeb', 'Tom Bheeb']), ('Townies', False, ['Jade Rosa', 'Ira Cole'])],
    'Slot_00000009': [('Goth', True, ['Bella Goth', 'Mortimer Goth', 'Cassandra Goth', 'Alexander Goth']),
                      ('Landgraab', False, ['Nancy Landgraab', 'Geoffrey Landgraab'])],
    'Slot_00000011': [('Landgraab-Bheeb Family', True, ['Malcolm Landgraab-Bheeb', 'Katrina Bheeb'])],
    'Slot_00000003': [('Builders', True, ['Test Sim'])],
    'tray': [('Pancakes', False, ['Eliza Pancakes', 'Bob Pancakes']), ('Caliente', False, ['Nina Caliente'])],
}


def save_cc(slot, progress=None):
    """The CC one example save uses, per sim, and the CC it misses ('tray': the in-game library)."""
    with _lock:
        save = next((s for s in STATE['saves'] if s['slot'] == slot), None)
        items = [it for it in CC['items'] if it['kind'] == 'package' and it['category'] not in ('gameplay', 'poses')
                 and not it['broken']]
    if slot != 'tray' and save is None:
        return {'ok': False, 'message': "That save wasn't found. It may have been deleted or renamed."}
    if progress:
        _run(progress, [('read', 'Reading what this save uses')])
    rnd = _random.Random(slot)
    picked = rnd.sample(items, min(len(items), 18 if slot == 'Slot_00000003' else 64))
    files = []
    for n, it in enumerate(picked):
        obj = it['category'] in ('buildbuy', 'walls')
        part = 0xA000000000000000 + it['id'] * 16 + n % 3
        _CC_PART_CATS[part] = it['category']
        files.append({'name': it['name'], 'folder': it['folder'], 'in_mods': it['in_mods'], 'item': copy.deepcopy(it),
                      'category_label': it['category_label'], 'parts': 0 if obj else rnd.randint(1, 9),
                      'objects': rnd.randint(1, 5) if obj else 0, 'looks': 0,
                      'pic': {'kind': 'object' if obj else 'cas', 'id': '%016X' % part} if it['pic'] else None,
                      'sims': [], 'sims_count': 0})
    files.sort(key=lambda f: -(f['parts'] + f['objects']))
    wearable = [n for n, f in enumerate(files) if f['parts']]
    households = []
    for hname, played, sims in _CC_SIMS.get(slot, [('Household', True, ['A Sim'])]):
        h = {'name': hname, 'id': '%016X' % (0x7000 + len(households)), 'played': played, 'sims': []}
        for sname in sims:
            worn = sorted(rnd.sample(wearable, min(len(wearable), rnd.randint(3, 8))))
            for w in worn:
                if sname not in files[w]['sims']:
                    files[w]['sims'].append(sname)
                    files[w]['sims_count'] += 1
            h['sims'].append({'name': sname, 'role': 'sim', 'files': worn, 'parts': len(worn) + rnd.randint(0, 6),
                              'missing': 0})
        households.append(h)
    n_missing = (save.get('cc_missing') or 0) if save else 4
    everyone = [(h['name'], s) for h in households for s in h['sims']]
    missing = []
    finds = [[{'place': 'safe copies', 'name': 'Trillyke_Earrings_Hoops.package', 'creator': 'Trillyke'}],
             [{'place': 'Inbox', 'name': '[Sentate] Aurora Top.package', 'creator': 'Sentate'}]]
    for k in range(n_missing):
        kind = 'object' if k % 6 == 5 else 'look' if k % 9 == 7 else 'cas'
        inst = 0xDEAD000000000000 + rnd.randint(1, 1 << 40)
        if kind != 'look':
            _CC_PART_CATS[inst] = 'buildbuy' if kind == 'object' else rnd.choice(['hair', 'top', 'shoes', 'accessory'])
        wearers = rnd.sample(everyone, min(len(everyone), 1 + k % 3)) if kind != 'object' else []
        for hn, s in wearers:
            s['missing'] += 1
        t = {'cas': 0x034AEECB, 'object': 0xC0DB5AE7, 'look': 0x0354796A}[kind]
        missing.append({'id': '%016X' % inst, 'key': '%08X:00000000:%016X' % (t, inst), 'kind': kind,
                        'what': _CC_MISSING_KINDS[kind], 'sims': sorted(s['name'] for _, s in wearers),
                        'sims_count': len(wearers), 'households': sorted({hn for hn, _ in wearers}),
                        'found': finds[k] if k < len(finds) else []})
    for h in households:
        h['sims'].sort(key=lambda s: (-s['missing'], -s['parts'], s['name']))
    counts = {'files': len(files), 'parts': sum(f['parts'] for f in files), 'objects': sum(f['objects'] for f in files),
              'looks': 0, 'missing': len(missing), 'sims': sum(len(h['sims']) for h in households)}
    name = 'In-game library' if slot == 'tray' else save['name']
    return {'ok': True, 'slot': slot, 'name': name, 'household': save.get('household') if save else None,
            'counts': counts, 'files': files, 'households': households, 'missing': missing, 'index': _cc_state(),
            'message': ''}

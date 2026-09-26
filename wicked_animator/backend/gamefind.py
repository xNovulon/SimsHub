"""Where The Sims 4 is on this PC.

Two folders matter, and they are found separately:
- the install (the game's own files: the bodies, clothes and furniture the animator shows). Found without asking, in
  this order: a folder picked in the app (config.json), the one Sims Hub found (SpeedKit\\settings.json in the user
  folder), the EA app / Origin registry entries, Steam's libraries, then the usual install folders on every fixed
  drive. It is there right after installing - the game never has to be started for it.
- the user folder, Documents\\Electronic Arts\\The Sims 4 (Mods, Tray, saves). The game makes it the first time it
  starts, in the Documents folder Windows really uses (a moved one or OneDrive's) and named in the game's language
  ('Die Sims 4'...). Until then there are no Tray sims and no Mods folder.

Tests: WICKED_GAME_DIR replaces the whole install search (an empty folder = no game), WICKED_DOCUMENTS the Documents
folder, WICKED_CONFIG the file a picked folder is kept in. Nothing here writes anywhere but config.json (a folder the user picked).
"""
import json, os, re, string, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get('WICKED_CONFIG') or os.path.join(HERE, '..', 'config.json')     # WICKED_CONFIG: tests
HOME = os.path.expanduser('~')
MISSING = 'The Sims 4 install not found'
NOT_GAME = "That folder isn't The Sims 4. Pick the folder with the Data and Game folders in it."

# the usual install folders, below each fixed drive
COMMON = [r'Program Files\EA Games\The Sims 4', r'Program Files (x86)\EA Games\The Sims 4',
          r'Program Files (x86)\Origin Games\The Sims 4', r'Program Files\Origin Games\The Sims 4',
          r'EA Games\The Sims 4', r'Origin Games\The Sims 4', r'Games\The Sims 4', r'Games\EA Games\The Sims 4',
          r'The Sims 4', r'SteamLibrary\steamapps\common\The Sims 4', r'Steam\steamapps\common\The Sims 4',
          r'Program Files (x86)\Steam\steamapps\common\The Sims 4', r'Program Files\Steam\steamapps\common\The Sims 4']


# ---------------------------------------------------------------- the user folder (Documents)
def documents():
    """The Documents folder Windows uses for this user (it can be moved, or kept in OneDrive)."""
    d = os.environ.get('WICKED_DOCUMENTS')
    if d:
        return os.path.abspath(d)
    if os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as k:
                v, _ = winreg.QueryValueEx(k, 'Personal')
            p = os.path.expandvars(v)
            if p and os.path.isdir(p):
                return p
        except OSError:
            pass
    return os.path.join(HOME, 'Documents')


def find_sims_dir():
    """Documents\\Electronic Arts\\The Sims 4 - the one the game made, or where it will make it."""
    docs = documents()
    places = [os.path.join(docs, 'Electronic Arts')]
    legacy = os.path.join(HOME, 'Documents', 'Electronic Arts')
    if os.path.normcase(legacy) != os.path.normcase(places[0]):
        places.append(legacy)
    for ea in places:
        own = os.path.join(ea, 'The Sims 4')
        if os.path.isdir(own):
            return own
        try:                                      # the game in another language: 'Die Sims 4', 'Les Sims 4'...
            for n in sorted(os.listdir(ea)):
                p = os.path.join(ea, n)
                if re.search(r'sims\s*4', n, re.I) and os.path.isdir(p):
                    return p
        except OSError:
            pass
    return os.path.join(places[0], 'The Sims 4')


SIMS_DIR = find_sims_dir()


# ---------------------------------------------------------------- the install
def is_install(d):
    """A folder with the game's own files in it (Data\\Client\\ClientFullBuild*.package)."""
    try:
        return bool(d) and any(n.lower().startswith('clientfullbuild') and n.lower().endswith('.package')
                               for n in os.listdir(os.path.join(d, 'Data', 'Client')))
    except OSError:
        return False


def install_of(path):
    """The install for any path in it: the folder itself, Game, Game\\Bin, Data, Data\\Client or TS4_x64.exe."""
    if not path:
        return None
    p = os.path.abspath(os.path.expandvars(str(path).strip().strip('"')))
    if os.path.isfile(p):
        p = os.path.dirname(p)
    for _ in range(4):
        if is_install(p):
            return p
        up = os.path.dirname(p)
        if up == p:
            break
        p = up
    return None


def _config():
    try:
        with open(CONFIG, encoding='utf-8') as f:
            c = json.load(f)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def _hub_pick():
    """The game Sims Hub found or was shown (its settings file lives in the user folder)."""
    try:
        with open(os.path.join(find_sims_dir(), 'SpeedKit', 'settings.json'), encoding='utf-8') as f:
            s = json.load(f)
        return s.get('game_exe') or s.get('auto_exe')
    except (OSError, ValueError, AttributeError):
        return None


def _registry():
    if os.name != 'nt':
        return []
    import winreg
    out = []
    for view in (r'SOFTWARE\Maxis\The Sims 4', r'SOFTWARE\WOW6432Node\Maxis\The Sims 4'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, view) as k:
                out.append(winreg.QueryValueEx(k, 'Install Dir')[0])
        except OSError:
            pass
    for root in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as k:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sub:
                            name = winreg.QueryValueEx(sub, 'DisplayName')[0]
                            if isinstance(name, str) and name.strip().lower() == 'the sims 4':
                                out.append(winreg.QueryValueEx(sub, 'InstallLocation')[0])
                    except OSError:
                        continue
        except OSError:
            pass
    return [p for p in out if isinstance(p, str) and p]


def _steam():
    if os.name != 'nt':
        return []
    import winreg
    roots = []
    for hive, key, val in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                           (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
        try:
            with winreg.OpenKey(hive, key) as k:
                roots.append(os.path.normpath(winreg.QueryValueEx(k, val)[0]))
        except OSError:
            pass
    libs = []
    for r in roots:
        libs.append(r)
        try:
            with open(os.path.join(r, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8', errors='replace') as f:
                libs += [p.replace('\\\\', '\\') for p in re.findall(r'"path"\s*"([^"]+)"', f.read())]
        except OSError:
            pass
    return [os.path.join(l, 'steamapps', 'common', 'The Sims 4') for l in libs]


def drives(kinds=(3,)):
    """[(root, label)] of the drives of these kinds (3 fixed, 2 removable); network and CD drives are left out, they
    can keep a search waiting."""
    if os.name != 'nt':
        return [('/', '')]
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.SetErrorMode(0x0001 | 0x8000)            # no "There is no disk in the drive" box for an empty card reader
    out = []
    mask = k32.GetLogicalDrives()
    for i, letter in enumerate(string.ascii_uppercase):
        if not mask & (1 << i):
            continue
        root = letter + ':\\'
        kind = k32.GetDriveTypeW(root)
        if kind not in kinds:
            continue
        if kind == 2:                                  # removable: may have no card or stick in it
            out.append((root, 'Removable'))
            continue
        buf = ctypes.create_unicode_buffer(261)
        label = buf.value if k32.GetVolumeInformationW(root, buf, 261, None, None, None, None, 0) else ''
        out.append((root, label))
    return out


def candidates():
    """(path, how it was found) for every place the install may be, in order."""
    env = os.environ.get('WICKED_GAME_DIR')
    if env is not None:
        yield env, 'test'
        return
    c = _config().get('game_dir')
    if c:
        yield c, 'picked'
    h = _hub_pick()
    if h:
        yield h, 'Sims Hub'
    for p in _registry():
        yield p, 'EA app'
    for p in _steam():
        yield p, 'Steam'
    for root, _ in drives():
        for rel in COMMON:
            yield os.path.join(root, rel), 'found'


_lock = threading.Lock()
_state = {'dir': None, 'source': None, 'miss': 0.0}


def game_dir():
    """The install folder. Raises FileNotFoundError(MISSING) when it can't be found (asked again at most every 10 s)."""
    if os.environ.get('WICKED_GAME_DIR') is not None:
        d = install_of(os.environ['WICKED_GAME_DIR'])
        if d:
            return d
        raise FileNotFoundError(MISSING)
    with _lock:
        d = _state['dir']
        if d and os.path.isdir(os.path.join(d, 'Data', 'Client')):
            return d
        if time.time() - _state['miss'] < 10:
            raise FileNotFoundError(MISSING)
        for p, how in candidates():
            d = install_of(p)
            if d:
                _state.update(dir=d, source=how, miss=0.0)
                return d
        _state.update(dir=None, source=None, miss=time.time())
    raise FileNotFoundError(MISSING)


def forget():
    """Search again next time (after a folder was picked)."""
    with _lock:
        _state.update(dir=None, source=None, miss=0.0)


def info():
    """What the app tells the user: {found, dir, source, sims_dir, sims_ready, mods, tray, played}."""
    try:
        d, err = game_dir(), None
    except FileNotFoundError as ex:
        d, err = None, str(ex)
    sims = find_sims_dir()
    return {'found': bool(d), 'dir': d, 'source': ('test' if os.environ.get('WICKED_GAME_DIR') is not None else _state['source']) if d else None,
            'error': err, 'sims_dir': sims, 'sims_ready': os.path.isdir(sims),
            'mods': os.path.isdir(os.path.join(sims, 'Mods')), 'tray': os.path.isdir(os.path.join(sims, 'Tray')),
            'played': os.path.isfile(os.path.join(sims, 'Options.ini'))}


def set_game_dir(path):
    """Remember the folder the user picked (any folder in the install, or TS4_x64.exe). -> {ok, dir} or {ok, message}."""
    d = install_of(path)
    if not d:
        return {'ok': False, 'message': NOT_GAME}
    cfg = _config()
    cfg['game_dir'] = d
    tmp = CONFIG + '.%d.tmp' % os.getpid()
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=1)
        os.replace(tmp, CONFIG)
    except OSError as ex:
        try:
            os.remove(tmp)
        except OSError:
            pass
        with _lock:
            _state.update(dir=d, source='picked', miss=0.0)
        return {'ok': True, 'dir': d, 'kept': False,
                'message': "It's used now, but couldn't be saved for next time (%s)." % ex.strerror}
    forget()
    return {'ok': True, 'dir': d, 'kept': True}


# ---------------------------------------------------------------- the in-app folder browser
_sug = {'t': 0.0, 'list': None}


def suggestions():
    """Installs found on this PC (at most 4, found at most once a minute)."""
    if _sug['list'] is not None and time.time() - _sug['t'] < 60:
        return _sug['list']
    seen, out = set(), []
    for p, how in candidates():
        d = install_of(p)
        if d and os.path.normcase(d) not in seen:
            seen.add(os.path.normcase(d))
            out.append({'path': d, 'source': how})
            if len(out) >= 4:
                break
    _sug.update(t=time.time(), list=out)
    return out


def _hidden(entry):
    if entry.name.startswith(('$', '.')) or entry.name.lower() in ('system volume information', 'recovery', 'windows'):
        return True
    try:
        return bool(getattr(entry.stat(follow_symlinks=False), 'st_file_attributes', 0) & 0x6)   # hidden, system
    except OSError:
        return True


def _parent(p):
    par = os.path.dirname(p.rstrip('\\/'))
    if not par or par == p or os.path.splitdrive(p)[1] in ('\\', '/', ''):
        return None
    return par if os.path.splitdrive(par)[1] else par + '\\'


def browse(path=None):
    """One folder of the in-app browser. No path: This PC (the drives). -> {ok, message, path, parent, is_game,
    entries: [{name, path, is_game}], drives: [{path, label}], suggestions}. Folders only; hidden and system ones and
    ones that can't be opened are left out."""
    drv = [{'path': r, 'label': l} for r, l in drives((2, 3))]
    sug = suggestions()
    if not path:
        return {'ok': True, 'message': 'This PC', 'path': None, 'parent': None, 'is_game': False, 'entries': [],
                'drives': drv, 'suggestions': sug}
    p = os.path.abspath(path)
    if not os.path.isdir(p):
        return {'ok': False, 'message': "That folder doesn't exist.", 'path': p, 'parent': None, 'is_game': False,
                'entries': [], 'drives': drv, 'suggestions': sug}
    try:
        it = os.scandir(p)
    except OSError:
        return {'ok': False, 'message': "That folder can't be opened.", 'path': p, 'parent': _parent(p), 'is_game': False,
                'entries': [], 'drives': drv, 'suggestions': sug}
    entries = []
    with it:
        for e in it:
            try:
                if not e.is_dir(follow_symlinks=False) or _hidden(e):
                    continue
            except OSError:
                continue
            entries.append({'name': e.name, 'path': e.path, 'is_game': is_install(e.path)})
            if len(entries) >= 800:
                break
    entries.sort(key=lambda x: x['name'].lower())
    here = is_install(p)
    return {'ok': True, 'message': 'This is The Sims 4.' if here else '%d folders' % len(entries), 'path': p,
            'parent': _parent(p), 'is_game': here, 'entries': entries, 'drives': drv, 'suggestions': sug}

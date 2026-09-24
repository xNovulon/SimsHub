r"""Where is The Sims 4 installed? No path is hard-coded: the Hub is meant for other players too.

    g = find_game()          # {'exe', 'game_dir', 'store': 'steam'|'ea'|'unknown', 'source'} or None
    locate_game()            # the same plus 'found', 'saved', 'message' (what status() reports)
    set_game_path(path)      # the user's choice (any of the shapes below), saved for good
    normalise(path)          # a game folder / Game / Bin / the exe / TS4.exe -> the TS4_x64.exe path, or None

Clues, in this order; each candidate counts only when its TS4_x64.exe exists:
  1. a path remembered in <Sims 4>\SpeedKit\settings.json: the user's own choice ("game_exe", saved by
     set_game_path) or one found earlier ("auto_exe"). A chosen path that is gone (a drive letter changed)
     is reported as not found - "The game is no longer at <path>" - so the Hub asks again instead of
     silently using something else;
  2. a running TS4_x64.exe (PowerShell Get-Process TS4_x64 | select Path) - remembered when found;
  3. shortcuts named "*Sims 4*" (.lnk) on the user's and the Public Desktop and in the user's and the
     all-users Start Menu, resolved with WScript.Shell: a target ending in TS4_x64.exe, or TS4.exe with
     Game\Bin\TS4_x64.exe next to it ("Sims 4 Studio" shortcuts are ignored);
  4. the registry: "Install Dir" under HKLM\SOFTWARE\Maxis\The Sims 4 (and WOW6432Node), and Uninstall
     entries whose DisplayName contains "The Sims 4" (InstallLocation);
  5. Steam: HKCU\Software\Valve\Steam SteamPath, its steamapps\libraryfolders.vdf libraries, then
     steamapps\common\The Sims 4 in each;
  6. common folders on every fixed drive: \Program Files\EA Games\The Sims 4, \Program Files (x86)\Origin
     Games\The Sims 4, \The Sims 4, \Games\The Sims 4, \SteamLibrary\steamapps\common\The Sims 4.
Store: 'steam' when the exe is under a steamapps\common folder (the game is then started through
steam://rungameid/1222670, since a direct start may relaunch through Steam), 'ea' when an EA/Origin clue
found it or its folder has EA's __Installer, else 'unknown'.

Every probe can be replaced (tests use fakes): Clues(processes=..., shortcuts=..., resolve=..., registry=...,
steam=..., drives=...). Reads only; the only write is settings.json in SpeedKit's own folder.
"""
import datetime
import json
import os
import re
import string
import subprocess

from .library import SIMS

EXE = 'TS4_x64.exe'
STEAM_APP_ID = 1222670
STEAM_URL = 'steam://rungameid/%d' % STEAM_APP_ID
SETTINGS = 'settings.json'
COMMON_DIRS = (r'Program Files\EA Games\The Sims 4', r'Program Files (x86)\Origin Games\The Sims 4',
               r'The Sims 4', r'Games\The Sims 4', r'SteamLibrary\steamapps\common\The Sims 4',
               r'Program Files (x86)\Steam\steamapps\common\The Sims 4', r'Program Files\Steam\steamapps\common\The Sims 4')
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


# ------------------------------------------------------------------------------------------ shapes
def normalise(path):
    """The TS4_x64.exe for any accepted shape of a Sims 4 location, or None:
    the game folder (Game\\Bin\\TS4_x64.exe below it), its Game folder, the Bin folder, a folder holding
    TS4_x64.exe directly, the exe itself, or the TS4.exe launcher (Game\\Bin\\TS4_x64.exe next to it)."""
    if not path:
        return None
    p = os.path.abspath(os.path.expandvars(os.path.expanduser(str(path).strip().strip('"'))))
    low = os.path.basename(p).lower()
    if low == EXE.lower():
        return p if os.path.isfile(p) else None
    if low in ('ts4.exe', 'ts4_launcher_x64.exe', 'ts4_dx9_x64.exe'):
        d = os.path.dirname(p)
        for cand in (os.path.join(d, 'Game', 'Bin', EXE), os.path.join(d, EXE)):
            if os.path.isfile(cand):
                return cand
        return None
    for cand in (os.path.join(p, EXE), os.path.join(p, 'Bin', EXE), os.path.join(p, 'Game', 'Bin', EXE)):
        if os.path.isfile(cand):
            return cand
    return None


def game_dir_of(exe):
    """The game's install folder for its TS4_x64.exe (<game>\\Game\\Bin\\TS4_x64.exe), else the exe's folder."""
    b = os.path.dirname(exe)
    if os.path.basename(b).lower() == 'bin' and os.path.basename(os.path.dirname(b)).lower() == 'game':
        return os.path.dirname(os.path.dirname(b))
    return b


def store_of(exe, source=''):
    """'steam', 'ea' or 'unknown' for a found exe."""
    low = os.path.normcase(exe).replace('/', '\\')
    if '\\steamapps\\common\\' in low:
        return 'steam'
    gd = game_dir_of(exe)
    if source.startswith(('registry', 'ea')) or os.path.isdir(os.path.join(gd, '__Installer')) \
            or '\\ea games\\' in low or '\\origin games\\' in low:
        return 'ea'
    return 'unknown'


def _result(exe, source):
    return {'exe': exe, 'game_dir': game_dir_of(exe), 'store': store_of(exe, source), 'source': source}


# ------------------------------------------------------------------------------------------ probes
def _ps(command, timeout=20):
    try:
        r = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                           capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ''


def running_exe_paths():
    """Paths of running TS4_x64.exe processes (PowerShell Get-Process TS4_x64 | select Path)."""
    try:
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq TS4_x64.exe', '/NH', '/FO', 'CSV'], capture_output=True,
                           text=True, timeout=20, creationflags=_NO_WINDOW)
        if 'ts4_x64.exe' not in (r.stdout or '').lower():
            return []
    except (OSError, subprocess.SubprocessError):
        pass
    out = _ps('Get-Process TS4_x64 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Path')
    return [l.strip() for l in out.splitlines() if l.strip()]


def shortcut_dirs():
    """The Desktop and Start Menu folders shortcuts are looked for in (user and all users)."""
    home = os.path.expanduser('~')
    public = os.environ.get('PUBLIC', r'C:\Users\Public')
    appdata = os.environ.get('APPDATA', os.path.join(home, 'AppData', 'Roaming'))
    progdata = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    return [os.path.join(home, 'Desktop'), os.path.join(home, 'OneDrive', 'Desktop'), os.path.join(public, 'Desktop'),
            os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
            os.path.join(progdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs')]


def find_shortcuts(dirs):
    """.lnk files named '*Sims 4*' (not Sims 4 Studio) in the folders (Start Menu: two levels deep)."""
    out = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for dp, dn, fn in os.walk(d):
            if dp.count(os.sep) - d.count(os.sep) >= 2:
                dn[:] = []
            for n in fn:
                low = n.lower()
                if low.endswith('.lnk') and 'sims 4' in low and 'studio' not in low:
                    out.append(os.path.join(dp, n))
    return out


def resolve_shortcuts(paths):
    """{lnk path: target path} through WScript.Shell (one PowerShell call); links it cannot read fall back
    to reading the .lnk file's own local path."""
    out = {}
    if paths:
        items = ','.join("'%s'" % p.replace("'", "''") for p in paths)
        cmd = ('$s = New-Object -ComObject WScript.Shell; foreach ($p in @(%s)) { try { $t = $s.CreateShortcut($p).'
               'TargetPath } catch { $t = "" }; Write-Output ($p + "|" + $t) }' % items)
        for line in _ps(cmd, timeout=30).splitlines():
            if '|' in line:
                p, t = line.rsplit('|', 1)
                if t.strip():
                    out[p.strip()] = t.strip()
    for p in paths:
        if p not in out:
            t = lnk_target(p)
            if t:
                out[p] = t
    return out


def lnk_target(path):
    """The local target path stored in a .lnk file (MS-SHLLINK LinkInfo), or None. Pure Python fallback."""
    import struct
    try:
        with open(path, 'rb') as f:
            d = f.read(1 << 16)
        if len(d) < 76 or struct.unpack_from('<I', d, 0)[0] != 0x4C:
            return None
        flags = struct.unpack_from('<I', d, 20)[0]
        p = 76
        if flags & 0x01:                                  # HasLinkTargetIDList
            p += 2 + struct.unpack_from('<H', d, p)[0]
        if not flags & 0x02:                              # HasLinkInfo
            return None
        li = p
        hdr = struct.unpack_from('<I', d, li + 4)[0]
        base_off = struct.unpack_from('<I', d, li + 16)[0]
        if hdr >= 0x24:
            uoff = struct.unpack_from('<I', d, li + 28)[0]
            end = d.find(b'\x00\x00', li + uoff)
            while end >= 0 and (end - li - uoff) % 2:
                end = d.find(b'\x00\x00', end + 1)
            if end > 0:
                return d[li + uoff:end].decode('utf-16-le', 'replace') or None
        end = d.find(b'\x00', li + base_off)
        return d[li + base_off:end].decode('mbcs' if os.name == 'nt' else 'latin-1', 'replace') or None
    except (OSError, struct.error, ValueError):
        return None


def registry_dirs():
    """[(source, folder)] from the registry: Maxis 'Install Dir' and Uninstall entries named The Sims 4."""
    out = []
    try:
        import winreg
    except ImportError:
        return out
    for key in (r'SOFTWARE\Maxis\The Sims 4', r'SOFTWARE\WOW6432Node\Maxis\The Sims 4'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                out.append(('registry (Maxis)', winreg.QueryValueEx(k, 'Install Dir')[0]))
        except OSError:
            pass
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                    r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
            try:
                with winreg.OpenKey(hive, key) as k:
                    n = winreg.QueryInfoKey(k)[0]
                    for i in range(n):
                        try:
                            with winreg.OpenKey(k, winreg.EnumKey(k, i)) as sk:
                                name = winreg.QueryValueEx(sk, 'DisplayName')[0]
                                if 'the sims 4' in str(name).lower() and 'studio' not in str(name).lower():
                                    out.append(('registry (uninstall entry)', winreg.QueryValueEx(sk, 'InstallLocation')[0]))
                        except OSError:
                            continue
            except OSError:
                continue
    return out


def steam_path():
    """HKCU\\Software\\Valve\\Steam SteamPath, or None."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
            return winreg.QueryValueEx(k, 'SteamPath')[0]
    except (ImportError, OSError):
        return None


def steam_libraries(steam_root):
    """Library folders of a Steam install (the install itself + steamapps\\libraryfolders.vdf 'path' entries)."""
    if not steam_root:
        return []
    libs = [os.path.normpath(steam_root)]
    vdf = os.path.join(steam_root, 'steamapps', 'libraryfolders.vdf')
    try:
        with open(vdf, encoding='utf-8', errors='replace') as f:
            text = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = os.path.normpath(m.group(1).replace('\\\\', '\\'))
            if p.lower() not in (x.lower() for x in libs):
                libs.append(p)
    except OSError:
        pass
    return libs


def fixed_drives():
    """Fixed drive roots ('C:\\\\', 'E:\\\\', ...)."""
    out = []
    if os.name != 'nt':
        return ['/']
    import ctypes
    for letter in string.ascii_uppercase:
        root = letter + ':\\'
        try:
            if ctypes.windll.kernel32.GetDriveTypeW(root) == 3:     # DRIVE_FIXED
                out.append(root)
        except Exception:
            continue
    return out


class Clues:
    """The probes find_game uses; tests pass fakes. Each is a callable."""

    def __init__(self, processes=running_exe_paths, shortcuts=None, resolve=resolve_shortcuts, registry=registry_dirs,
                 steam=steam_path, drives=fixed_drives):
        self.processes = processes
        self.shortcuts = shortcuts or (lambda: find_shortcuts(shortcut_dirs()))
        self.resolve = resolve
        self.registry = registry
        self.steam = steam
        self.drives = drives


# ------------------------------------------------------------------------------------------ settings.json
def settings_path(sims=SIMS, home=None):
    return os.path.join(home or os.path.join(sims, 'SpeedKit'), SETTINGS)


def read_settings(sims=SIMS, home=None):
    try:
        with open(settings_path(sims, home), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_settings(doc, sims=SIMS, home=None):
    p = settings_path(sims, home)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1)
    os.replace(p + '.tmp', p)


def _now():
    return datetime.datetime.now().isoformat(timespec='seconds')


def set_game_path(path, sims=SIMS, home=None):
    """Remember the user's choice for good: any accepted shape (see normalise) -> SpeedKit\\settings.json
    {"game_exe": <TS4_x64.exe>, "saved": iso}. Returns {'ok', 'message', 'exe', 'game_dir'}."""
    exe = normalise(path)
    if not exe:
        return {'ok': False, 'exe': None, 'game_dir': None,
                'message': "That folder does not hold The Sims 4 (no Game\\Bin\\%s in it). Pick the game's own "
                           "folder, for example 'The Sims 4'." % EXE}
    doc = read_settings(sims, home)
    doc.update({'game_exe': exe, 'saved': _now()})
    try:
        _write_settings(doc, sims, home)
    except OSError as e:
        return {'ok': False, 'exe': exe, 'game_dir': game_dir_of(exe), 'message': 'Could not save the choice (%s).' % e}
    _CACHE.clear()
    return {'ok': True, 'exe': exe, 'game_dir': game_dir_of(exe), 'message': 'Found The Sims 4 at %s.' % game_dir_of(exe)}


def forget_game_path(sims=SIMS, home=None):
    """Drop the remembered paths (tests / 'Locate The Sims 4' again)."""
    doc = read_settings(sims, home)
    if doc.pop('game_exe', None) or doc.pop('auto_exe', None):
        _write_settings(doc, sims, home)
    _CACHE.clear()


# ------------------------------------------------------------------------------------------ search
_CACHE = {}
CACHE_SECONDS = 60


def search(clues=None, skip_remembered=True, sims=SIMS, home=None, first_only=True):
    """Candidates found by clues 2-6 (and 1 unless skip_remembered), each a find_game() result, best first."""
    import time as _t
    c = clues or Clues()
    out, seen = [], set()

    def add(path, source):
        exe = normalise(path)
        if exe and os.path.normcase(exe) not in seen:
            seen.add(os.path.normcase(exe))
            out.append(_result(exe, source))
        return bool(exe)

    if not skip_remembered:
        doc = read_settings(sims, home)
        for k, src in (('game_exe', 'your choice'), ('auto_exe', 'remembered')):
            if doc.get(k) and add(doc[k], src) and first_only:
                return out
    steps = [
        ('running game', lambda: [(p, 'running game') for p in (c.processes() or [])]),
        ('shortcut', lambda: [(t, 'shortcut %s' % os.path.basename(l)) for l, t in
                              (c.resolve(c.shortcuts() or []) or {}).items()]),
        ('registry', lambda: [(d, src) for src, d in (c.registry() or [])]),
        ('steam', lambda: [(os.path.join(lib, 'steamapps', 'common', 'The Sims 4'), 'Steam library')
                           for lib in steam_libraries(c.steam())]),
        ('folders', lambda: [(os.path.join(dr, sub), 'common folder') for dr in (c.drives() or []) for sub in COMMON_DIRS]),
    ]
    for name, fn in steps:
        try:
            cands = fn()
        except Exception:
            cands = []
        for path, source in cands:
            if add(path, source) and first_only:
                return out
    return out


def locate_game(sims=SIMS, home=None, clues=None, remember=True, use_cache=True):
    """{'found', 'exe', 'game_dir', 'store', 'source', 'saved' (the path is the user's own choice),
    'lost_path' (a chosen game folder that is gone, else None), 'message'}. A chosen path that is gone makes found False with "The game is no longer at <path>" (no
    other clue is tried, so the Hub asks again). A game found through a running TS4_x64.exe is remembered
    (settings.json "auto_exe") when remember is True. Results are cached for a minute."""
    import time as _t
    ck = (os.path.normcase(settings_path(sims, home)), id(clues) if clues else None)
    hit = _CACHE.get(ck)
    if use_cache and hit and _t.time() - hit[0] < CACHE_SECONDS:
        return dict(hit[1])
    doc = read_settings(sims, home)
    out = {'found': False, 'exe': None, 'game_dir': None, 'store': None, 'source': None, 'saved': False,
           'lost_path': None,
           'message': "The Sims 4 wasn't found on this PC. Click 'Locate The Sims 4' and select its folder."}
    chosen = doc.get('game_exe')
    if chosen:
        exe = normalise(chosen)
        if exe:
            out.update(_result(exe, 'your choice'), found=True, saved=True, message='The Sims 4 is at %s.' % game_dir_of(exe))
        else:
            out.update(message='The game is no longer at %s. Click \'Locate The Sims 4\' and select its folder.'
                       % game_dir_of(chosen), saved=True, exe=None, source='your choice',
                       lost_path=game_dir_of(chosen))
        _CACHE[ck] = (_t.time(), dict(out))
        return out
    auto = doc.get('auto_exe')
    if auto and normalise(auto):
        exe = normalise(auto)
        out.update(_result(exe, doc.get('auto_source') or 'remembered'), found=True,
                   message='The Sims 4 is at %s.' % game_dir_of(exe))
        _CACHE[ck] = (_t.time(), dict(out))
        return out
    found = search(clues, True, sims, home)
    if found:
        g = found[0]
        out.update(g, found=True, message='The Sims 4 is at %s.' % g['game_dir'])
        if remember and g['source'] == 'running game':
            try:
                doc = read_settings(sims, home)
                doc.update({'auto_exe': g['exe'], 'auto_source': g['source'], 'auto_found': _now()})
                _write_settings(doc, sims, home)
            except OSError:
                pass
    _CACHE[ck] = (_t.time(), dict(out))
    return out


def find_game(sims=SIMS, home=None, clues=None, remember=True, use_cache=True):
    """{'exe', 'game_dir', 'store': 'steam'|'ea'|'unknown', 'source'} of The Sims 4, or None (see locate_game)."""
    g = locate_game(sims, home, clues, remember, use_cache)
    if not g['found']:
        return None
    return {k: g[k] for k in ('exe', 'game_dir', 'store', 'source')}


def is_game_folder(path):
    """Is this folder a Sims 4 install (game root, Game, Bin, or a folder holding TS4_x64.exe)?"""
    return normalise(path) is not None

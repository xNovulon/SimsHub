r"""A shortcut for one save: "Play <save name>" on the Desktop (or any folder the user picks).

Opening it runs  pythonw -m speedkit.hub --play save:Slot_XXXXXXXX  (launcher.play_save): the Hub opens, sets the
Mods folder up for that save (quick - its pack is kept, so only what changed since is redone) and starts the game.

The Hub asks once after a save was played (Saves page); "Not now" is remembered for that save, and its card keeps a
link to make or move the shortcut. What was made is remembered in %LOCALAPPDATA%\NovulonSimsHub\save_shortcuts.json
({slot: {"path", "name"}} or {slot: {"declined": true}}); a shortcut the user deleted or moved by hand counts as
gone. The icon is the save's letter as on its card (drawn by Chrome or Edge, like desktop.py's), else the Hub's.
Only .lnk files this module made are ever moved or replaced.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading

from speedkit.hub import desktop

SLOT_RX = re.compile(r'^Slot_[0-9A-Fa-f]{8}$')
ARGS = '-m speedkit.hub --play save:%s'
ICON_SIZES = (32, 48, 256)
_lock = threading.Lock()
_places = {}


class ShortcutError(Exception):
    """A plain sentence for the user."""


def data_dir():
    return os.environ.get('SIMS_HUB_DATA') or os.path.join(
        os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'NovulonSimsHub')


def _store_path():
    return os.path.join(data_dir(), 'save_shortcuts.json')


def _load():
    try:
        with open(_store_path(), encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d):
    p = _store_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, p)


def check_slot(slot):
    if not isinstance(slot, str) or not SLOT_RX.match(slot):
        raise ShortcutError('Pick a save first.')
    return slot


def file_name(save_name, slot):
    """'Play <save name>' as a file name Windows accepts."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', ' ', str(save_name or '')).strip()
    s = ' '.join(s.split()).rstrip(' .')[:70].rstrip(' .')
    return 'Play ' + (s or slot)


def places():
    """Where a shortcut can go with one click: the Desktop and Documents (the real folders, even when moved into
    OneDrive)."""
    if not _places:
        docs = None
        try:
            r = subprocess.run(['powershell', '-NoProfile', '-Command', '[Environment]::GetFolderPath("MyDocuments")'],
                               capture_output=True, text=True, timeout=30)
            docs = r.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
        _places['desktop'] = desktop.desktop_dir()
        _places['documents'] = docs if docs and os.path.isdir(docs) else os.path.join(os.path.expanduser('~'), 'Documents')
    return [{'key': 'desktop', 'label': 'Desktop', 'path': _places['desktop']},
            {'key': 'documents', 'label': 'Documents', 'path': _places['documents']}]


def place_label(folder):
    for p in places():
        if os.path.normcase(os.path.normpath(p['path'])) == os.path.normcase(os.path.normpath(folder)):
            return p['label']
    return folder


def info(slot):
    """{'slot', 'exists', 'path', 'folder', 'place', 'declined'} for one save."""
    rec = _load().get(slot) or {}
    path = rec.get('path')
    exists = bool(path) and os.path.isfile(path)
    folder = os.path.dirname(path) if exists else None
    return {'slot': slot, 'exists': exists, 'path': path if exists else None, 'folder': folder,
            'place': place_label(folder) if folder else None, 'declined': bool(rec.get('declined')) and not exists}


def all_info():
    return {'ok': True, 'shortcuts': {slot: info(slot) for slot in _load() if SLOT_RX.match(slot)},
            'places': places()}


def decline(slot):
    check_slot(slot)
    with _lock:
        d = _load()
        rec = d.get(slot) or {}
        if not (rec.get('path') and os.path.isfile(rec['path'])):
            d[slot] = {'declined': True}
            _save(d)
    return {'ok': True, 'message': "OK - you can still make one from the save's card."}


def _free_path(folder, base, own):
    """<folder>\\<base>.lnk, or '<base> (2).lnk'... when a file of that name is there and isn't this save's."""
    for n in range(1, 50):
        p = os.path.join(folder, base + ('' if n == 1 else ' (%d)' % n) + '.lnk')
        if not os.path.exists(p) or (own and os.path.normcase(p) == os.path.normcase(own)):
            return p
    raise ShortcutError('That folder already has too many shortcuts with this name.')


def _check_folder(folder):
    if not isinstance(folder, str) or not folder.strip() or len(folder) > 1024 or '\x00' in folder:
        raise ShortcutError('Pick a folder first.')
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        raise ShortcutError("That folder doesn't exist.")
    return folder


def icon_for(slot, save_name, browser=None):
    """The save's letter on the Hub's pink-violet tile, as an .ico (kept next to save_shortcuts.json), or the Hub's
    own icon when no Chrome or Edge can draw it."""
    letter = (str(save_name or '?').strip()[:1] or '?').upper()
    folder = os.path.join(data_dir(), 'shortcut_icons')
    path = os.path.join(folder, '%s_%04x.ico' % (slot, ord(letter)))
    if os.path.isfile(path):
        return path
    browser = browser or desktop.find_browser()
    if not browser:
        return desktop.ICO
    tmp = tempfile.mkdtemp(prefix='saveicon_')
    try:
        pngs = {}
        for s in ICON_SIZES:
            page = os.path.join(tmp, 'i%d.html' % s)
            with open(page, 'w', encoding='utf-8') as f:
                f.write('<!doctype html><meta charset="utf-8"><body style="margin:0;background:transparent">'
                        '<div style="width:%dpx;height:%dpx;border-radius:%dpx;display:grid;place-items:center;'
                        'background:linear-gradient(135deg,#ff4f9a 0%%,#c04fe0 55%%,#8b5cf6 100%%);color:#fff;'
                        'font:800 %dpx/1 \'Segoe UI\',Arial,sans-serif;text-shadow:0 %dpx %dpx rgba(80,0,50,.3)">'
                        '%s</div></body>' % (s, s, round(s * .3), round(s * .6), max(1, s // 48), max(1, s // 24),
                                              '&#%d;' % ord(letter)))
            png = os.path.join(tmp, 'i%d.png' % s)
            subprocess.run([browser, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                            '--no-default-browser-check', '--user-data-dir=' + os.path.join(tmp, 'profile'),
                            '--force-device-scale-factor=1', '--default-background-color=00000000',
                            '--window-size=%d,%d' % (s, s), '--screenshot=' + png, 'file:///' + page.replace('\\', '/')],
                           capture_output=True, timeout=60)
            with open(png, 'rb') as f:
                data = f.read()
            if desktop.png_size(data) != (s, s):
                return desktop.ICO
            pngs[s] = data
        os.makedirs(folder, exist_ok=True)
        with open(path + '.tmp', 'wb') as f:
            f.write(desktop.ico_bytes(pngs))
        os.replace(path + '.tmp', path)
        return path
    except (OSError, ValueError, subprocess.SubprocessError):
        return desktop.ICO
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_lnk(lnk, slot, save_name, icon):
    script = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); $s.TargetPath = %s; $s.Arguments = %s; '
              '$s.WorkingDirectory = %s; $s.IconLocation = %s; $s.Description = %s; $s.WindowStyle = 1; $s.Save()'
              % (desktop._ps(lnk), desktop._ps(desktop.pythonw()), desktop._ps(ARGS % slot), desktop._ps(desktop.ROOT),
                 desktop._ps(icon + ',0'), desktop._ps("Play '%s' with only the CC it uses" % (save_name or slot))))
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', enc],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not os.path.isfile(lnk):
        raise ShortcutError("The shortcut couldn't be made there. Try another folder.")


def make(slot, save_name, folder=None):
    """Make the save's shortcut in folder (default: the Desktop), or move it there when it exists already.
    -> {'ok', 'message', ...info(slot)}."""
    check_slot(slot)
    folder = _check_folder(folder) if folder else places()[0]['path']
    with _lock:
        d = _load()
        rec = d.get(slot) or {}
        old = rec.get('path') if rec.get('path') and os.path.isfile(rec['path']) else None
        lnk = _free_path(folder, file_name(save_name, slot), old)
        if old and os.path.normcase(os.path.dirname(old)) == os.path.normcase(folder):
            lnk = old                                      # already there: keep it (and its name)
        if old and lnk != old:
            try:
                shutil.move(old, lnk)
            except OSError:
                raise ShortcutError("The shortcut couldn't be moved there. Try another folder.")
            moved = True
        else:
            moved = False
            if not old:
                _write_lnk(lnk, slot, save_name, icon_for(slot, save_name))
        d[slot] = {'path': lnk, 'name': str(save_name or '')[:120]}
        _save(d)
    where = where_words(folder)
    msg = ('Your shortcut is %s now.' if moved else 'Your shortcut is %s.' if not old else
           'Your shortcut is already %s.') % where
    return dict(info(slot), ok=True, message=msg)


def where_words(folder):
    """'on your Desktop', 'in your Documents' or 'in <folder name>'."""
    label = place_label(folder)
    if label == 'Desktop':
        return 'on your Desktop'
    if label == 'Documents':
        return 'in your Documents'
    return 'in ' + (os.path.basename(os.path.normpath(folder)) or folder)

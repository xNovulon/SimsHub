"""Shared helpers for Novulon (runs inside The Sims 4's Python 3.7).

Where things live:
  * The game loads a .ts4script from the Mods folder or one folder below it, and our modules get a __file__ like
    '<Sims 4>\\Mods\\Novulon.ts4script\\novulon\\common.pyc'. The Sims 4 user folder is found from that path. Outside a
    Mods folder (tests, tools) sims_dir() is None and the mod does nothing at all.
  * Everything Novulon writes goes to <Sims 4>\\Novulon\\ (settings.json, logs\\novulon.log) - never into Mods.

Rules every part of the mod follows:
  * nothing Novulon does may raise into the game: every entry point runs through guarded(), which logs the error
    and carries on;
  * no threads, no timers, nothing running in the background - Novulon only works while its menu is open.
"""
import os
import time
import traceback

VERSION = '2.0'
LOG_MAX_BYTES = 1024 * 1024          # novulon.log rolls over to novulon.log.1 above this size

_sims_dir = None
_resolved = False


# ------------------------------------------------------------------ paths
def find_sims_dir(module_file):
    """The Sims 4 user folder for a module loaded from <Sims 4>\\Mods[\\<one folder>]\\X.ts4script\\..., else None.
    For Mods\\Mods\\X.ts4script (a download unzipped with its own Mods folder) the folder holding Options.ini or
    Config.log wins, so our own files never land inside Mods."""
    if not module_file:
        return None
    p = str(module_file).replace('/', '\\')
    i = p.lower().find('.ts4script')
    if i < 0:
        return None
    parent = os.path.dirname(p[:i + len('.ts4script')])
    grand = os.path.dirname(parent)
    candidates = []
    if os.path.basename(grand).lower() == 'mods':
        candidates.append(os.path.dirname(grand))
    if os.path.basename(parent).lower() == 'mods':
        candidates.append(os.path.dirname(parent))
    for c in candidates:
        if any(os.path.isfile(os.path.join(c, n)) for n in ('Options.ini', 'Config.log')):
            return c
    return candidates[0] if candidates else None


def configure(sims_dir):
    """Point the mod at a Sims 4 folder explicitly (tests and tools only)."""
    global _sims_dir, _resolved
    _sims_dir, _resolved = sims_dir, True


def sims_dir():
    """The Sims 4 user folder Novulon belongs to, or None when it is not running from a Mods folder."""
    global _sims_dir, _resolved
    if not _resolved:
        _sims_dir = find_sims_dir(globals().get('__file__'))
        _resolved = True
    return _sims_dir


def data_dir(*parts):
    """<Sims 4>\\Novulon[\\parts], created on first use; None without a Sims folder."""
    s = sims_dir()
    if not s:
        return None
    d = os.path.join(s, 'Novulon', *parts)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


def log_path():
    d = data_dir('logs')
    return os.path.join(d, 'novulon.log') if d else None


# ------------------------------------------------------------------ logging
def log(msg):
    """One time-stamped line in logs\\novulon.log. Never raises."""
    try:
        path = log_path()
        if not path:
            return
        try:
            if os.path.getsize(path) > LOG_MAX_BYTES:
                os.replace(path, path + '.1')
        except OSError:
            pass
        with open(path, 'a', encoding='utf-8', errors='replace') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


def log_exception(where):
    """The exception being handled, with its traceback, in novulon.log. Never raises."""
    try:
        log('ERROR in %s:\n%s' % (where, traceback.format_exc().rstrip()))
    except Exception:
        pass


def guarded(where, fn, *args, **kwargs):
    """fn(*args, **kwargs); any exception is logged and None returned instead."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        log_exception(where)
        return None


# ------------------------------------------------------------------ files
def read_json(path):
    import json
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, value):
    """Written whole or not at all (a temp file, then replaced). Returns True when written."""
    import json
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(value, f, indent=1, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception:
        log_exception('writing ' + str(path))
        return False


# ------------------------------------------------------------------ text
def is_game_string(value):
    """True for a string the game already made (a translated name), which is shown as it is."""
    return value is not None and not isinstance(value, (str, int, float))


def raw(text):
    """A game string showing exactly `text` (no translation table). A game string is passed through unchanged."""
    if is_game_string(text):
        return text
    from sims4.localization import LocalizationHelperTuning
    return LocalizationHelperTuning.get_raw_text(str(text))


def raw_fn(text):
    """A callable game string (dialog titles and texts are called with the dialog's tokens)."""
    s = text if is_game_string(text) else str(text)
    return lambda *_a, **_k: raw(s)

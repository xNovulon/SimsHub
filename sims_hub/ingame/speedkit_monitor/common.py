"""Shared helpers for the SpeedKit Monitor script mod (runs inside The Sims 4's Python 3.7).

Where things live:
  * The game only loads a .ts4script from the Mods root or one folder below it, and zipimport gives
    our modules a __file__ like '<Sims 4>\\Mods\\SpeedKit_Monitor.ts4script\\speedkit_monitor\\common.pyc'.
    So the Sims 4 user folder is found from our own __file__: the parent of the 'Mods' folder that holds
    the archive. When the code is not running from an archive inside a Mods folder (unit tests, tools),
    sims_dir() is None and the mod does nothing at all - it never falls back to the real Documents folder.
  * Everything we write goes to <Sims 4>\\SpeedKit\\reports (monitor.log, loadtimes.csv, lag reports),
    never into Mods, so the game has nothing new to scan.

Rules every part of the mod follows:
  * nothing we add may raise into the game: hooks call our code through guarded(), which logs the
    exception to monitor.log and carries on;
  * no threads and no background work: everything runs on the simulation thread when the game calls us.
"""
import os
import sys
import time
import traceback

VERSION = '1.0'
ARCHIVE_NAME = 'SpeedKit_Monitor.ts4script'
PACKAGE = 'speedkit_monitor'
LOG_MAX_BYTES = 2 * 1024 * 1024          # monitor.log is rotated to monitor.log.1 above this size

_sims_dir = None
_resolved = False


# ------------------------------------------------------------------ paths
def archive_of(path):
    """Return the file name of the .ts4script archive in a path ('X.ts4script'), or None."""
    if not path:
        return None
    p = str(path).replace('/', '\\')
    i = p.lower().find('.ts4script')
    if i < 0:
        return None
    return p[:i + len('.ts4script')].rsplit('\\', 1)[-1]


def find_sims_dir(module_file):
    """The Sims 4 user folder for a module loaded from <Sims 4>\\Mods[\\<one folder>]\\X.ts4script\\..., else None.

    The game loads archives from the Mods root or one folder down. For Mods\\Mods\\X.ts4script (a download
    unzipped with its own 'Mods' folder) the Sims folder is the parent of the OUTER Mods, so reports never
    land inside Mods; the folder holding Options.ini/Config.log wins when both readings are possible."""
    if not module_file:
        return None
    p = str(module_file).replace('/', '\\')
    i = p.lower().find('.ts4script')
    if i < 0:
        return None
    parent = os.path.dirname(p[:i + len('.ts4script')])
    grand = os.path.dirname(parent)
    candidates = []
    if os.path.basename(grand).lower() == 'mods':         # one folder down (or Mods\Mods)
        candidates.append(os.path.dirname(grand))
    if os.path.basename(parent).lower() == 'mods':        # the Mods root
        candidates.append(os.path.dirname(parent))
    for c in candidates:
        if any(os.path.isfile(os.path.join(c, n)) for n in ('Options.ini', 'Config.log')):
            return c
    return candidates[0] if candidates else None


def configure(sims_dir):
    """Point the mod at a Sims 4 folder explicitly (tools/tests only; the game never calls this)."""
    global _sims_dir, _resolved
    _sims_dir, _resolved = sims_dir, True


def sims_dir():
    """The Sims 4 user folder we belong to, or None when not running from a Mods folder."""
    global _sims_dir, _resolved
    if not _resolved:
        _sims_dir = find_sims_dir(globals().get('__file__'))
        _resolved = True
    return _sims_dir


def speedkit_dir():
    """<Sims 4>\\SpeedKit (shared with the desktop tools: launch_time.json, profile_state.json)."""
    s = sims_dir()
    return os.path.join(s, 'SpeedKit') if s else None


def reports_dir():
    """<Sims 4>\\SpeedKit\\reports, created on first use; None when we have no Sims folder."""
    k = speedkit_dir()
    if not k:
        return None
    d = os.path.join(k, 'reports')
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    return d


# ------------------------------------------------------------------ logging
def log(msg):
    """Append one time-stamped line to reports\\monitor.log. Never raises."""
    try:
        d = reports_dir()
        if not d:
            return
        path = os.path.join(d, 'monitor.log')
        try:
            if os.path.getsize(path) > LOG_MAX_BYTES:
                os.replace(path, path + '.1')
        except OSError:
            pass
        # errors='replace': a Windows file name can hold a lone surrogate, which strict UTF-8 refuses
        with open(path, 'a', encoding='utf-8', errors='replace') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except Exception:
        pass


def log_exception(where):
    """Log the exception being handled, with its traceback, to monitor.log. Never raises."""
    try:
        log('ERROR in %s:\n%s' % (where, traceback.format_exc().rstrip()))
    except Exception:
        pass


def guarded(where, fn, *args, **kwargs):
    """Call fn(*args, **kwargs); on any exception log it and return None instead of raising."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        log_exception(where)
        return None


# ------------------------------------------------------------------ small readers
def read_json(path):
    """Parsed JSON from path, or None when it is missing or unreadable."""
    import json
    try:
        with open(path, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return None


def loaded_script_mods(modules=None):
    """{archive file name: number of modules imported from it} for every .ts4script with loaded modules,
    our own archive excluded. Reads sys.modules only (cheap, no file access)."""
    out = {}
    items = list((modules if modules is not None else sys.modules).items())
    for name, m in items:
        try:
            if name == PACKAGE or name.startswith(PACKAGE + '.'):
                continue
            a = archive_of(getattr(m, '__file__', None))
            if a and a.lower() != ARCHIVE_NAME.lower():
                out[a] = out.get(a, 0) + 1
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ game UI (main thread only)
def notify(title, text, urgent=False):
    """Show a notification (the game's UiDialogNotification with raw text). Returns True if shown."""
    try:
        from ui.ui_dialog_notification import UiDialogNotification
        from sims4.localization import LocalizationHelperTuning
        kw = {}
        if urgent:
            try:
                kw['urgency'] = UiDialogNotification.UiDialogNotificationUrgency.URGENT
            except Exception:
                pass
        dlg = UiDialogNotification.TunableFactory().default(
            None,
            title=lambda *_a, **_k: LocalizationHelperTuning.get_raw_text(title),
            text=lambda *_a, **_k: LocalizationHelperTuning.get_raw_text(text),
            **kw)
        dlg.show_dialog()
        return True
    except Exception:
        log_exception('notify')
        return False


def cheat_output(connection):
    """A function that prints to the cheat console of `connection`; a no-op if that is not possible."""
    try:
        import sims4.commands
        out = sims4.commands.CheatOutput(connection)
    except Exception:
        return lambda _text: None

    def write(text):
        try:
            out(text)
        except Exception:
            pass
    return write

"""'Did it play in the game?' - reads WickedWhims' own log, read-only.

WickedWhims writes `Documents\\Electronic Arts\\The Sims 4\\WickedWhimsInfoLog.log` every time the game starts. Two kinds
of line matter here (spec_game.md section 7; the texts were checked against WickedWhims' own code):

    09/24/26 02:06:15 [SEX/INFO] Sims 'Male Sim 1'+'Female Sim 2' played 'FS Proof' sex animation by 'FitStudio test'.
    ... [ANIMATIONS/WARN] [INVALID EVENT] Sex Animation 'X' by 'Y' has invalid effect event.
    ... [INVALID CLIP] Invalid Sex Animation 'X' by 'Y' from not being able to load clip data. ...

    read(author, name=None, since=None) -> {exists, played: [...], problems: [...], session: {...}, running}
    game_running()                      -> True / False / None (could not tell)

Only the last 2 MB of the log are read for the lines above (plus the first 512 KB for the session summary: the game's
and WickedWhims' versions and how many animations WickedWhims had ready), so even a huge log is read at once.

WICKED_SIMS_DIR (tests) points at a fake 'The Sims 4' folder; WICKED_TASKLIST at a text file that stands in for
tasklist's answer. Nothing here ever writes anything.
"""
import datetime
import os
import re
import subprocess
import time

TAIL = 2 * 1024 * 1024
HEAD = 512 * 1024
GAME_EXE = 'TS4_x64.exe'

TASKLIST = None        # tests may set a function that returns tasklist's text


def sims_dir():
    d = os.environ.get('WICKED_SIMS_DIR')
    if d:
        return os.path.abspath(d)
    import gamefind
    return gamefind.SIMS_DIR


def log_path():
    return os.path.join(sims_dir(), 'WickedWhimsInfoLog.log')


# ------------------------------------------------------------------ is the game running?
def _tasklist_text():
    if TASKLIST is not None:
        return TASKLIST()
    fake = os.environ.get('WICKED_TASKLIST')
    if fake:
        try:
            with open(fake, encoding='utf-8', errors='replace') as f:
                return f.read()
        except OSError:
            return ''                    # no file: nothing is running
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq %s' % GAME_EXE, '/NH'], capture_output=True, timeout=15,
                         creationflags=flags)
    return (out.stdout or b'').decode('mbcs' if os.name == 'nt' else 'utf-8', 'replace')


def game_running():
    """True when The Sims 4 (TS4_x64.exe) runs, False when it doesn't, None when that could not be checked."""
    try:
        return GAME_EXE.lower() in _tasklist_text().lower()
    except Exception:
        return None


# ------------------------------------------------------------------ reading the log
_LINE = re.compile(r'^(\d\d/\d\d/\d\d) (\d\d:\d\d:\d\d) \[([A-Z0-9_]+)/([A-Z]+)\] (.*?)\s*$')
_PLAYED = re.compile(r"^Sims (?P<sims>.*?) ?played '(?P<name>.*)' sex animation by '(?P<author>.*)'\.?$")
_BRACKET = re.compile(r'^\[(?P<kind>INVALID[^\]/]*)(?P<extra>/[^\]]*)?\] (?P<msg>.*)$')
_ANIM = re.compile(r"^(?:Invalid )?Sex Animation '(?P<name>.*)' by '(?P<author>.*?)' "
                   r"(?P<rest>(?:from|has invalid|collides with) .*)$")
_NO_NAME = re.compile(r"^Invalid Sex Animation by '(?P<author>.*?)'? from missing display name\.?$")
_NO_AUTHOR = re.compile(r"^Invalid Sex Animation '(?P<name>.*)' from missing author name\.?$")

# What WickedWhims says -> plain words. 'moment' problems only skip one event; the others stop the animation.
PLAIN = [
    ('invalid effect event', 'moment', 'WickedWhims skipped a moment: the effect needs a name'),
    ('invalid cum type event', 'moment', "WickedWhims skipped a moment: the cum spot isn't one WickedWhims knows"),
    ('invalid undress type event', 'moment', "WickedWhims skipped a moment: it doesn't say what to take off"),
    ('invalid event target', 'moment', "WickedWhims skipped a moment: it points at a sim that isn't in the animation"),
    ('invalid event start', 'moment', "WickedWhims skipped a moment: its start or end time isn't right"),
    ('invalid geometry state event', 'moment', "WickedWhims skipped a moment: the change to the object isn't valid"),
    ('invalid material state event', 'moment', "WickedWhims skipped a moment: the change to the object isn't valid"),
    ('load clip data', 'animation', "WickedWhims couldn't find this animation's motion, so it never plays. "
                                    'Send it to the game again, then restart the game.'),
    ('negative duration offset on a non-single', 'animation', "WickedWhims says the animation's length is wrong, so it never plays."),
    ('duration', 'animation', "WickedWhims says the animation's length is wrong, so it never plays."),
    ('missing display name', 'animation', 'WickedWhims needs a name for this animation, so it never shows up.'),
    ('missing author name', 'animation', 'WickedWhims needs a creator name, so it never shows up.'),
    ('incorrect sex category', 'animation', "The kind of act isn't one WickedWhims knows, so it never shows up."),
    ('missing locations', 'animation', 'No place is set, so it never shows up.'),
    ('incorrect actor ids', 'animation', 'The list of sims is wrong, so it never shows up.'),
    ('incorrect actors list', 'animation', 'The list of sims is wrong, so it never shows up.'),
    ('actor missing gender', 'animation', 'A sim has no gender set, so it never shows up.'),
    ('unspecific preferenced gender', 'animation', "A sim's preferred gender is too vague, so it never shows up."),
    ('incorrect prop ids', 'animation', 'The list of props is wrong, so it never shows up.'),
    ('collides with', 'animation', 'Another animation has the same name, so WickedWhims keeps only one of them.'),
]


def plain_words(message):
    """-> (kind, plain text) for one WickedWhims problem message."""
    low = message.lower()
    for key, kind, text in PLAIN:
        if key in low:
            return kind, text
    return 'animation', 'WickedWhims had a problem with this animation: ' + message


def _when(date, clock):
    """'09/24/26', '21:04:05' -> (unix seconds, 'HH:MM', ISO) in local time, or (None, clock[:5], None)."""
    try:
        dt = datetime.datetime.strptime(date + ' ' + clock, '%m/%d/%y %H:%M:%S')
        return time.mktime(dt.timetuple()), clock[:5], dt.isoformat()
    except ValueError:
        return None, clock[:5], None


def _read_tail(path, size, n):
    with open(path, 'rb') as f:
        start = max(0, size - n)
        f.seek(start)
        data = f.read(n)
    text = data.decode('utf-8', 'replace')
    if start > 0:                                  # the first line is cut: drop it
        cut = text.find('\n')
        text = text[cut + 1:] if cut >= 0 else ''
    return text


def _read_head(path, n):
    with open(path, 'rb') as f:
        return f.read(n).decode('utf-8', 'replace')


def parse_lines(text):
    """Every played / problem line in the text: ([played], [problems]) with the author and name as written."""
    played, problems = [], []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if not m:
            continue
        date, clock, tag, level, msg = m.groups()
        if 'played' in msg and 'sex animation by' in msg:
            p = _PLAYED.match(msg)
            if p:
                ts, hm, iso = _when(date, clock)
                sims = [s.strip("'") for s in re.findall(r"'([^']*)'", p.group('sims'))]
                played.append({'name': p.group('name'), 'author': p.group('author'), 'sims': [s for s in sims if s],
                               'time': ts, 'clock': hm, 'iso': iso})
            continue
        if 'Sex Animation' not in msg:
            continue
        kind_tag, extra = '', ''
        b = _BRACKET.match(msg)
        if b:
            kind_tag, extra, msg = b.group('kind'), (b.group('extra') or '').lstrip('/'), b.group('msg')
        name = author = None
        a = _ANIM.match(msg)
        if a:
            name, author = a.group('name'), a.group('author')
        else:
            n = _NO_NAME.match(msg)
            if n:
                name, author = '', n.group('author')
            else:
                n = _NO_AUTHOR.match(msg)
                if n:
                    name, author = n.group('name'), ''
        if name is None:
            continue
        kind, text = plain_words(msg)
        ts, hm, iso = _when(date, clock)
        problems.append({'name': name, 'author': author, 'kind': kind, 'text': text, 'raw': msg, 'tag': kind_tag,
                         'override': 'OVERRIDE' in extra.upper(), 'level': level, 'time': ts, 'clock': hm, 'iso': iso})
    return played, problems


_SESSION = [
    ('game_version', re.compile(r'Running The Sims 4 version (\d+(?:\.\d+)+)')),
    ('ww_version', re.compile(r'Running WickedWhims (v?\d+[0-9A-Za-z]*(?:\.\d+[0-9A-Za-z]*)*)')),
    ('loaded', re.compile(r'Loaded (\d+) sex animation tunings with valid (\d+) animation instances')),
    ('available', re.compile(r'to load (\d+) available sex animations')),
    ('disabled', re.compile(r'Disabled Animations: (\d+) individually, (\d+) dynamically')),
    ('mod_files', re.compile(r'Mod Files \((\d+)\)')),
    ('duplicates', re.compile(r'Possible Duplicated Mod Files \((\d+)\):\s*(.*)')),
]


def session_summary(text):
    """What the last game start said: versions, animations ready, switched off, duplicated mod files."""
    out = {}
    for raw in text.splitlines():
        for key, rx in _SESSION:
            if key in out:
                continue
            m = rx.search(raw)
            if not m:
                continue
            if key == 'loaded':
                out['tunings'], out['valid'] = int(m.group(1)), int(m.group(2))
                out[key] = True
            elif key == 'disabled':
                out['disabled_single'], out['disabled_dynamic'] = int(m.group(1)), int(m.group(2))
                out[key] = True
            elif key == 'duplicates':
                out[key] = int(m.group(1))
                out['duplicate_files'] = [x.strip() for x in m.group(2).split(',') if x.strip()]
            elif key in ('available', 'mod_files'):
                out[key] = int(m.group(1))
            else:
                out[key] = m.group(1)
        m = _LINE.match(raw)
        if m and 'started' not in out:
            out['started'] = _when(m.group(1), m.group(2))[0]
    return out


def _same(a, b):
    return (a or '').strip().lower() == (b or '').strip().lower()


def read(author=None, name=None, since=None, check_running=True):
    """The user's animations in WickedWhims' log: {exists, path, size, modified, played, problems, session, running}.

    author / name: only lines for that creator (and animation), compared without case. since (unix seconds): only
    lines written after it (a minute of slack for clock rounding)."""
    path = log_path()
    out = {'exists': os.path.isfile(path), 'path': path, 'played': [], 'problems': [], 'session': {},
           'running': game_running() if check_running else None}
    if not out['exists']:
        return out
    st = os.stat(path)
    out['size'], out['modified'] = st.st_size, st.st_mtime
    t0 = time.perf_counter()
    played, problems = parse_lines(_read_tail(path, st.st_size, TAIL))
    out['session'] = session_summary(_read_head(path, HEAD))
    try:
        since = float(since) if since not in (None, '') else None
    except ValueError:
        since = None

    def keep(x):
        if author is not None and author != '' and not _same(x['author'], author):
            return False
        if name and not _same(x['name'], name):
            return False
        if since is not None and x['time'] is not None and x['time'] < since - 60:
            return False
        return True
    # WickedWhims logs a played animation twice (once without the sims' names): one entry each
    best = {}
    for x in played:
        if keep(x):
            k = (x['name'].lower(), x['author'].lower(), x['time'])
            if k not in best or (x['sims'] and not best[k]['sims']):
                best[k] = x
    out['played'] = sorted(best.values(), key=lambda x: x['time'] or 0)
    # one line per problem (the game logs some twice: the animation and its override)
    seen, probs = set(), []
    for x in problems:
        if keep(x):
            k = (x['name'], x['author'], x['text'])
            if k not in seen:
                seen.add(k)
                probs.append(x)
    out['problems'] = probs
    out['counts'] = {'played_all': len(played), 'problems_all': len(problems)}
    out['ms'] = round((time.perf_counter() - t0) * 1000, 1)
    return out


if __name__ == '__main__':
    import json, sys
    a = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(read(a), indent=1)[:4000])

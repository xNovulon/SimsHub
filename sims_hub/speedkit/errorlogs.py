r"""Which mod caused this error? Read the game's error reports, find the mod files they point at, group repeats.

    rep = scan(sims)          # {'errors': [group, ...], 'files': [...], 'unreadable': [...]} - read-only

Where the reports come from (all read-only; nothing is ever deleted or changed):
  * <Sims 4>\lastException*.txt       the game's Python errors. XML: <root><report>... with <createtime>,
                                      <categoryid> ('path\file.py:line') and the traceback in <desyncdata>
                                      (older builds: <desc>), line breaks written as &#13;&#10;. One file can hold
                                      many <report> blocks; the game adds numbered files (lastException_1.txt...).
  * <Sims 4>\lastUIException*.txt     errors of the game's menus (ActionScript), same XML, no Python traceback.
  * mc_lastexception*.html            MC Command Center's copy of an error (in the Sims 4 folder or its Mods folder).
  * Better Exceptions reports         any .html/.txt/.log whose name has 'BetterException' (or starts with
                                      'BE_' and has 'report'/'exception'), in the Sims 4 folder, a BetterExceptions
                                      folder there, or a folder of Mods named like the mod (up to 3 folders deep).
Anything that cannot be read or has no known shape is still listed (as 'other', with its raw text).

Naming the mod (strongest first):
  1. a traceback line whose file path runs through a '.ts4script' (…\Mods\X\foo.ts4script\pkg\mod.py): that
     script file, matched by name;
  2. a traceback path whose tail is a module a script mod ships (d:\dev\mymod\core\thing.py -> 'mymod.core.thing'
     inside mymod.ts4script): the script whose zip holds that module (the longest match wins);
  3. no traceback match: a mod file name (6+ characters, script or package) written in the report text.
The game's own code (T:\InGame\Gameplay\Scripts\..., the Python library) never counts. The innermost mod line of
a traceback names the mod ('named'); the other mods on the same traceback are listed as 'also'. A match by (3)
is only 'mentioned' - the Hub says "probably" then.

Repeats: one group per (kind, mod, error line with numbers and addresses blanked, innermost place), with how
many times it happened and when first/last.
"""
import datetime
import hashlib
import html
import os
import re
import zipfile

from .library import SIMS

MAX_READ = 8 << 20                    # bytes read per report file (the newest end of a bigger file)
MAX_DETAILS = 6000
GAME_PATH_RX = re.compile(r'(?i)(\\|/)InGame(\\|/)Gameplay(\\|/)Scripts(\\|/)|^[a-z]:[\\/]dev[\\/]ts4[\\/]|'
                          r'(\\|/)_deploy(\\|/)|^t:[\\/]|(\\|/)python\d*(\\|/)lib(\\|/)|(\\|/)lib(\\|/)(encodings|collections)')
FRAME_RX = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\S+))?')
EXC_LINE_RX = re.compile(r'^\s*([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Interrupt|Failure|Fault)[\w.]*)(?::\s*(.*))?$')
REPORT_RX = re.compile(r'<report>(.*?)</report>', re.S | re.I)
TAG_RX = {t: re.compile(r'<%s>(.*?)</%s>' % (t, t), re.S | re.I) for t in ('createtime', 'categoryid', 'desyncdata', 'desc',
                                                                         'buildsignature')}
MIN_MENTION = 6


def _iso(t):
    return datetime.datetime.fromtimestamp(t).isoformat(timespec='seconds') if t else None


# ------------------------------------------------------------------------------------------ what is installed
class ModIndex:
    """The script and package files of Mods (and Mods_parked) with the Python modules each script ships."""

    def __init__(self, roots):
        self.files = []                               # {'rel', 'root', 'name', 'stem', 'script'}
        self.by_name = {}                             # lower-case file name -> file
        self.modules = {}                             # dotted module name (lower) -> script file
        self.tops = {}                                # top-level module (lower) -> [script files]
        for root_name, root in roots.items():
            if not root or not os.path.isdir(root):
                continue
            for dp, dn, fn in os.walk(root):
                depth = os.path.relpath(dp, root).count(os.sep)
                if depth >= 6:
                    dn[:] = []
                for n in fn:
                    low = n.lower()
                    if not low.endswith(('.ts4script', '.package')):
                        continue
                    full = os.path.join(dp, n)
                    rel = os.path.relpath(full, root).replace(os.sep, '/')
                    f = {'rel': rel, 'root': root_name, 'name': n, 'stem': os.path.splitext(n)[0],
                         'script': low.endswith('.ts4script'), 'path': full}
                    self.files.append(f)
                    # Mods wins over Mods_parked for the same name (it is the copy the game loads)
                    if low not in self.by_name or (self.by_name[low]['root'] != 'Mods' and root_name == 'Mods'):
                        self.by_name[low] = f
                    if f['script']:
                        self._read_modules(f)

    def _read_modules(self, f):
        try:
            with zipfile.ZipFile(f['path']) as z:
                names = z.namelist()
        except (OSError, zipfile.BadZipFile, ValueError, RuntimeError):
            return
        for n in names:
            p = n.replace('\\', '/')
            stem, ext = os.path.splitext(p)
            if ext.lower() not in ('.py', '.pyc', '.pyo'):
                continue
            parts = [x for x in stem.split('/') if x]
            if parts and parts[-1] == '__init__':
                parts = parts[:-1]
            if not parts:
                continue
            dotted = '.'.join(parts).lower()
            cur = self.modules.get(dotted)
            if cur is None or (cur['root'] != 'Mods' and f['root'] == 'Mods'):
                self.modules[dotted] = f
            self.tops.setdefault(parts[0].lower(), [])
            if f not in self.tops[parts[0].lower()]:
                self.tops[parts[0].lower()].append(f)


def _frame_file(path, index):
    """(mod file, how) for one traceback path, or (None, None) for the game's own code / nothing known."""
    p = path.strip()
    if GAME_PATH_RX.search(p):
        return None, None
    parts = [x for x in re.split(r'[\\/]+', p) if x]
    for x in parts:
        if x.lower().endswith('.ts4script'):
            f = index.by_name.get(x.lower())
            if f:
                return f, 'script path'
    if parts:
        last = parts[-1]
        stem, ext = os.path.splitext(last)
        if ext.lower() in ('.py', '.pyc', '.pyo'):
            parts = parts[:-1] + ([stem] if stem != '__init__' else [])
    low = [x.lower() for x in parts]
    for i in range(len(low)):                          # leftmost start = the longest module path
        dotted = '.'.join(low[i:])
        f = index.modules.get(dotted)
        if f is not None:
            return f, 'module'
    return None, None


def _word_in(low, cand):
    i = low.find(cand)
    while i >= 0:
        before = low[i - 1] if i > 0 else ' '
        after = low[i + len(cand)] if i + len(cand) < len(low) else ' '
        if not (before.isalnum() or before == '_') and not (after.isalnum() or after == '_'):
            return True
        i = low.find(cand, i + 1)
    return False


def _mentions(text, index):
    """Mod files whose name (6+ characters, with or without its extension) is written in the text as a whole
    word. Names without spaces are looked up among the text's words (fast for big libraries); names with
    spaces only for script mods."""
    out = []
    low = text.lower()[:200000]
    words = set(re.findall(r"[\w\-.!'\[\]()&+]+", low))
    words |= {w.strip(".'()[]") for w in words}
    for f in index.files:
        for cand in (f['name'].lower(), f['stem'].lower()):
            if len(cand) < MIN_MENTION:
                continue
            if (' ' not in cand and cand in words) or (' ' in cand and f['script'] and _word_in(low, cand)):
                out.append(f)
                break
    # the Mods copy of a name first, one per name
    seen, uniq = set(), []
    for f in sorted(out, key=lambda f: (f['root'] != 'Mods', f['rel'].lower())):
        if f['name'].lower() not in seen:
            seen.add(f['name'].lower())
            uniq.append(f)
    return uniq


# ------------------------------------------------------------------------------------------ reading reports
def _text(raw):
    t = raw.strip()
    if t.startswith('<![CDATA[') and t.endswith(']]>'):
        t = t[9:-3]
    t = html.unescape(t)
    return t.replace('\r\n', '\n').replace('\r', '\n')


def _strip_html(s):
    s = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', s)
    s = re.sub(r'(?i)<br\s*/?>|</(p|div|li|tr|h\d|pre)>', '\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    return html.unescape(s).replace('\r\n', '\n').replace('\r', '\n')


def _time(s):
    s = (s or '').strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%m/%d/%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M'):
        try:
            return datetime.datetime.strptime(s[:19], fmt).isoformat(timespec='seconds')
        except ValueError:
            continue
    return None


def _read(path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        if size > MAX_READ:
            f.seek(size - MAX_READ)
        data = f.read(MAX_READ)
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return data.decode('utf-16', 'replace')
    return data.decode('utf-8-sig', 'replace')


def report_files(sims=SIMS):
    """[(path, kind)] of the error reports on this PC: kind 'script' | 'ui' | 'mccc' | 'be'."""
    out = []
    try:
        names = sorted(os.listdir(sims))
    except OSError:
        names = []
    for n in names:
        low = n.lower()
        full = os.path.join(sims, n)
        if os.path.isfile(full):
            if re.match(r'^lastuiexception.*\.txt$', low):
                out.append((full, 'ui'))
            elif re.match(r'^lastexception.*\.txt$', low):
                out.append((full, 'script'))
            elif re.match(r'^mc_lastexception.*\.html?$', low):
                out.append((full, 'mccc'))
            elif _is_be(low):
                out.append((full, 'be'))
        elif os.path.isdir(full) and 'betterexception' in low.replace(' ', ''):
            out += [(p, 'be') for p in _walk_reports(full, 2, any_name=True)]
    mods = os.path.join(sims, 'Mods')
    for p in _walk_reports(mods, 3):
        low = os.path.basename(p).lower()
        if re.match(r'^mc_lastexception.*\.html?$', low):
            out.append((p, 'mccc'))
        elif _is_be(low):
            out.append((p, 'be'))
    seen, uniq = set(), []
    for p, k in out:
        if os.path.normcase(p) not in seen:
            seen.add(os.path.normcase(p))
            uniq.append((p, k))
    return uniq


def _is_be(low):
    if not low.endswith(('.html', '.htm', '.txt', '.log')):
        return False
    squashed = low.replace(' ', '').replace('_', '').replace('-', '')
    return 'betterexception' in squashed or (low.startswith('be_') and ('report' in low or 'exception' in low))


def _walk_reports(root, depth, any_name=False):
    out = []
    if not os.path.isdir(root):
        return out
    for dp, dn, fn in os.walk(root):
        d = os.path.relpath(dp, root).count(os.sep) + (0 if os.path.relpath(dp, root) == '.' else 1)
        if d >= depth:
            dn[:] = []
        for n in fn:
            low = n.lower()
            if any_name and low.endswith(('.html', '.htm', '.txt', '.log')):
                out.append(os.path.join(dp, n))
            elif low.startswith('mc_lastexception') or _is_be(low):
                out.append(os.path.join(dp, n))
    return out


def parse_file(path, kind):
    """[{'when', 'category', 'text', 'kind', 'build'}] - one per report in the file. Never raises for a strange
    file: it becomes one 'other' report with its raw text."""
    text = _read(path)
    mtime = _iso(os.path.getmtime(path))
    out = []
    if kind in ('script', 'ui'):
        blocks = REPORT_RX.findall(text)
        for b in blocks:
            body = ''
            for tag in ('desyncdata', 'desc'):
                m = TAG_RX[tag].search(b)
                if m and m.group(1).strip():
                    body = _text(m.group(1))
                    break
            cm = TAG_RX['createtime'].search(b)
            cat = TAG_RX['categoryid'].search(b)
            bs = TAG_RX['buildsignature'].search(b)
            out.append({'when': _time(cm.group(1)) if cm else None, 'category': _text(cat.group(1)) if cat else '',
                        'text': body, 'kind': kind, 'build': _text(bs.group(1)) if bs else ''})
        if not blocks:
            out.append({'when': None, 'category': '', 'text': text, 'kind': kind if 'Traceback' in text else 'other',
                        'build': ''})
    else:
        body = _strip_html(text) if path.lower().endswith(('.html', '.htm')) else text
        tbs = _split_tracebacks(body)
        m = re.search(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})', body)
        when = _time(m.group(1)) if m else None
        if tbs:
            for tb in tbs:
                out.append({'when': when, 'category': '', 'text': tb, 'kind': 'script', 'build': '', 'full': body})
        else:
            out.append({'when': when, 'category': '', 'text': body, 'kind': 'other', 'build': ''})
    for r in out:
        r['when'] = r['when'] or mtime
        r['file'] = os.path.basename(path)
        r['source'] = kind
    return out


def _split_tracebacks(text):
    """Each 'Traceback (most recent call last):' block with the lines after it up to its error line."""
    out = []
    starts = [m.start() for m in re.finditer(r'Traceback \(most recent call last\):', text)]
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        chunk = text[s:end]
        lines = chunk.split('\n')
        keep = []
        for ln in lines:
            keep.append(ln)
            if len(keep) > 1 and EXC_LINE_RX.match(ln) and not ln.startswith((' ', '\t')):
                break
        out.append('\n'.join(keep).strip())
    return out


def _error_line(text, kind):
    """The line that says what went wrong: the last 'SomethingError: ...' line, else the first meaningful one."""
    lines = [ln.rstrip() for ln in text.split('\n') if ln.strip()]
    for ln in reversed(lines):
        if EXC_LINE_RX.match(ln) and not ln.lstrip().startswith('File "'):
            return ln.strip()[:300]
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith(('<', 'Traceback')):
            return s[:300]
    return 'An error without a description' if kind != 'ui' else 'A menu error without a description'


def _norm_line(s):
    s = re.sub(r'0x[0-9a-fA-F]+', '0x_', s)
    s = re.sub(r'\b\d{3,}\b', '#', s)
    s = re.sub(r"'[^']{40,}'", "'…'", s)
    return s.strip().lower()


def analyse(report, index):
    """{'mod': file|None, 'how', 'also': [files], 'where': 'file.py:func'|''} for one report."""
    frames = FRAME_RX.findall(report['text'])
    hits = []
    for path, line, func in frames:
        f, how = _frame_file(path, index)
        if f is not None:
            hits.append((f, how, '%s:%s' % (re.split(r'[\\/]', path)[-1], func or line)))
    where = ''
    if frames:
        path, line, func = frames[-1]
        where = '%s:%s' % (re.split(r'[\\/]', path)[-1], func or line)
    if hits:
        f, how, w = hits[-1]
        also = []
        for g, _, _ in reversed(hits):
            if g is not f and g not in also:
                also.append(g)
        return {'mod': f, 'how': 'named', 'also': also, 'where': w or where}
    ment = _mentions(report['text'] + '\n' + (report.get('full') or '')[:200000], index)
    if ment:
        return {'mod': ment[0], 'how': 'mentioned', 'also': ment[1:4], 'where': where}
    return {'mod': None, 'how': None, 'also': [], 'where': where}


def _mod_view(f):
    if f is None:
        return None
    rel = f['rel']
    return {'name': rel.split('/')[0] if '/' in rel else f['stem'], 'file': f['name'], 'rel': rel, 'root': f['root'],
            'script': f['script'], 'can_set_aside': f['root'] == 'Mods'}


def scan(sims=SIMS, index=None, seen_until=None):
    """Every error report, grouped. Returns {'errors': [{'id', 'kind', 'error', 'mod', 'how', 'also', 'count',
    'first', 'last', 'files', 'details', 'new'}], 'files': [{'name', 'kind', 'reports', 'when'}],
    'unreadable': [names]}; newest group first. seen_until: iso - groups whose last time is not after it are
    marked new=False."""
    if index is None:
        index = ModIndex({'Mods': os.path.join(sims, 'Mods'), 'Mods_parked': os.path.join(sims, 'Mods_parked')})
    groups = {}
    files, unreadable = [], []
    for path, kind in report_files(sims):
        try:
            reps = parse_file(path, kind)
        except (OSError, ValueError) as e:
            unreadable.append(os.path.basename(path))
            continue
        files.append({'name': os.path.basename(path), 'kind': kind, 'reports': len(reps),
                      'when': _iso(os.path.getmtime(path))})
        for r in reps:
            a = analyse(r, index)
            gkind = 'ui' if r['kind'] == 'ui' else 'script' if r['kind'] == 'script' or FRAME_RX.search(r['text']) \
                else 'other'
            err = _error_line(r['text'], gkind)
            key = '|'.join([gkind, (a['mod'] or {}).get('rel', '').lower() if a['mod'] else '-', _norm_line(err),
                            a['where'].lower()])
            gid = hashlib.blake2b(key.encode('utf-8', 'replace'), digest_size=6).hexdigest()
            g = groups.get(gid)
            if g is None:
                details = r['text'].strip() or '(empty)'
                if r.get('category'):
                    details = 'Where: %s\n\n%s' % (r['category'], details)
                g = groups[gid] = {'id': gid, 'kind': gkind, 'error': err, 'mod': _mod_view(a['mod']), 'how': a['how'],
                                   'also': [_mod_view(x) for x in a['also']], 'count': 0, 'first': r['when'],
                                   'last': r['when'], 'files': [], 'details': details[:MAX_DETAILS],
                                   'where': a['where'], 'source': r['source']}
            g['count'] += 1
            if r['when'] and (not g['first'] or r['when'] < g['first']):
                g['first'] = r['when']
            if r['when'] and (not g['last'] or r['when'] > g['last']):
                g['last'] = r['when']
                g['details'] = ((('Where: %s\n\n' % r['category']) if r.get('category') else '')
                                + (r['text'].strip() or '(empty)'))[:MAX_DETAILS]
            if r['file'] not in g['files']:
                g['files'].append(r['file'])
    out = sorted(groups.values(), key=lambda g: g['last'] or '', reverse=True)
    for g in out:
        g['new'] = not seen_until or (g['last'] or '') > seen_until
    return {'errors': out, 'files': files, 'unreadable': unreadable}

"""Read faulthandler stack samples and charge them to script mods. Pure Python 3.7/3.12, no game imports.

How the lag meter samples (research/profiler, measured on the game's own python37_x64.dll):
  * faulthandler.dump_traceback_later(interval, repeat=True, file=f) is armed ONCE per measurement.
    Its C watchdog thread writes every thread's stack to f without taking the GIL, so samples are
    spread evenly in wall time; a Python sampler thread is biased by 5-16 points because the game's
    simulation thread holds the GIL. Measured 49.4/13.6/37.0 against a true 50/12.5/37.5.
  * Dump format of CPython 3.7 (Python/traceback.c), one block per dump:
        Timeout (0:00:00.040000)!
        Thread 0x000148a0 (most recent call first):
          File "<co_filename>", line <n> in <co_name>
    Thread ids are 8 hex digits on Windows (= threading.get_ident()). A thread with no Python frame
    prints only its header in 3.7 (newer versions add '  <no Python frame>'; both are handled).
    Strings are written by _Py_DumpASCII: printable ASCII as is, other characters as \\xNN / \\uNNNN /
    \\UNNNNNNNN (lower-case hex), cut at 500 characters + '...'. At most 100 frames per thread, then
    '  ...'.
  * co_filename in a mod's .pyc is the author's build path ('E:\\Builds\\MCCC_...\\mc_bills.py',
    '.\\WickedWhims_v185k\\...', 'lot51_core/tags.pyc', bare '__init__.py'...), not the archive. So the
    owner map is built at run time from sys.modules: every module whose __file__ is inside a .ts4script
    maps the co_filename of its functions to that archive. EA's own code ('T:\\InGame\\...',
    'D:\\dev\\TS4\\_deploy\\...') is never in the map and counts as 'game'.

Attribution of one sample (the main thread's stack, innermost frame first):
  * no Python frame                    -> '<outside Python>' (C++ work: rendering, routing, loading...)
  * the innermost frame that belongs to a script mod gets the sample, including time in EA code that
    the mod called (so a mod that wraps a busy game function is charged for it; the report also shows
    'self' = the owner of the innermost frame, which separates the two cases);
  * no mod frame on the stack          -> 'game';
  * SpeedKit's own frames (the Zone.update timing wrapper) are transparent.
"""
import collections

OUTSIDE = '<outside Python>'
GAME = 'game'
SELF = '<speedkit>'
OWN_LABEL = 'SpeedKit_Monitor.ts4script'
MAX_STRING = 500          # CPython traceback.c MAX_STRING_LENGTH
MAX_DEPTH = 100           # CPython traceback.c MAX_FRAME_DEPTH


# ------------------------------------------------------------------ names as faulthandler prints them
def fh_escape(text, limit=MAX_STRING):
    """A string exactly as faulthandler (_Py_DumpASCII) writes it."""
    out = []
    for ch in text[:limit]:
        c = ord(ch)
        if 32 <= c <= 126:
            out.append(ch)
        elif c <= 0xff:
            out.append('\\x%02x' % c)
        elif c <= 0xffff:
            out.append('\\u%04x' % c)
        else:
            out.append('\\U%08x' % c)
    if len(text) > limit:
        out.append('...')
    return ''.join(out)


def archive_owner(path, mods_dir=None):
    """Owner label for a file path: 'X.ts4script' if inside an archive, 'Mods\\<folder>' for a loose script
    under mods_dir (when given), else None."""
    if not path:
        return None
    p = str(path).replace('/', '\\')
    low = p.lower()
    i = low.find('.ts4script')
    if i >= 0:
        return p[:i + len('.ts4script')].rsplit('\\', 1)[-1]
    if mods_dir:
        m = str(mods_dir).replace('/', '\\').rstrip('\\').lower() + '\\'
        if low.startswith(m):
            first = p[len(m):].split('\\', 1)[0]
            return 'Mods\\' + first
    return None


# ------------------------------------------------------------------ owner map from loaded modules
# co_filename roots of EA's own code (research/profiler/ea_cofilename.py over base/core/simulation.zip and
# generated.zip): never a script mod, whatever a mod's namespace holds.
EA_CODE_PREFIXES = ('T:\\InGame\\Gameplay\\Scripts\\', 'D:\\dev\\TS4\\_deploy\\')
_MAX_UNWRAP = 20


def _own_function(f, modnames):
    """f, or the function it stands for, if that function was defined in one of `modnames`; else None.

    A decorator built with functools.wraps (EA's caches.cached_test / cached, sims4.utils.exception_protected,
    another mod's injector...) returns a wrapper whose __module__ is COPIED from the decorated function but
    whose code - and co_filename - belongs to the module that defines the decorator. WickedWhims (in Mods now)
    has ten test classes with '@turbo_cached_test def __call__' = EA's caches.cached_test, so using the
    wrapper's code would map EA's caches.py to WickedWhims and charge every EA cached test to it. So the
    __wrapped__ chain is followed to the real function, and a wrapper of something that is not a plain
    function is skipped."""
    ftype = type(_own_function)
    for _ in range(_MAX_UNWRAP):
        inner = getattr(f, '__wrapped__', None)
        if inner is None:
            break
        if not isinstance(inner, ftype):
            return None
        f = inner
    return f if getattr(f, '__module__', None) in modnames else None


def _functions_of(value, modnames):
    """Plain functions defined in one of `modnames` reachable from one module-level value: the value
    itself, or the methods (plain, static, class, property parts) of a class defined there. Functions a
    class merely holds (an alias of an EA function, a decorator's wrapper) are not its own."""
    ftype = type(_functions_of)
    if isinstance(value, ftype):
        f = _own_function(value, modnames)
        if f is not None:
            yield f
    elif isinstance(value, type) and getattr(value, '__module__', None) in modnames:
        for x in list(vars(value).values()):
            if isinstance(x, (staticmethod, classmethod)):
                x = x.__func__
            parts = (x.fget, x.fset, x.fdel) if isinstance(x, property) else (x,)
            for p in parts:
                if isinstance(p, ftype):
                    f = _own_function(p, modnames)
                    if f is not None:
                        yield f


def module_code_filenames(module, name):
    """The co_filename values of the functions a module defines (usually exactly one). EA's own code
    (EA_CODE_PREFIXES) is never returned."""
    modnames = {name}
    real = getattr(module, '__name__', None)
    if isinstance(real, str):
        modnames.add(real)
    names = set()
    for v in list(vars(module).values()):
        for f in _functions_of(v, modnames):
            code = getattr(f, '__code__', None)
            fn = getattr(code, 'co_filename', None)
            if isinstance(fn, str) and not fn.startswith(EA_CODE_PREFIXES):
                names.add(fn)
    return names


def build_owner_map(modules, self_package='speedkit_monitor', mods_dir=None):
    """{co_filename as faulthandler prints it: owner} for every loaded script-mod module.

    modules: iterable of (module name, module), e.g. list(sys.modules.items()).
    Our own package maps to SELF. A co_filename claimed by two archives (LittleMsSam's bare
    '__init__.py') maps to 'A.ts4script | B.ts4script'."""
    fmap = {}
    for name, m in modules:
        try:
            if name == self_package or name.startswith(self_package + '.'):
                owner = SELF
            else:
                owner = archive_owner(getattr(m, '__file__', None), mods_dir)
                if owner is None:
                    continue
            for fn in module_code_filenames(m, name):
                key = fh_escape(fn)
                prev = fmap.get(key)
                if prev is None or prev == owner:
                    fmap[key] = owner
                elif SELF not in (prev, owner) and owner not in prev.split(' | '):
                    fmap[key] = ' | '.join(sorted(prev.split(' | ') + [owner]))
        except Exception:
            continue
    return fmap


class OwnerLookup:
    """Callable filename -> owner using the map, with the path-based fallback cached.

    Filenames come from the dump, i.e. escaped by faulthandler, so mods_dir is escaped the same way
    before the loose-script fallback compares it (a Documents path with 'Jos\\xe9' would never match)."""

    def __init__(self, fmap, mods_dir=None):
        self.fmap = dict(fmap)
        self.mods_dir = fh_escape(str(mods_dir)) if mods_dir else None

    def __call__(self, filename):
        o = self.fmap.get(filename)
        if o is None:
            o = archive_owner(filename, self.mods_dir) or GAME
            self.fmap[filename] = o
        return o


# ------------------------------------------------------------------ dump parsing
def parse_frame(line):
    """('file', 'line', 'function') from a '  File "...", line N in f' line, or None for other lines."""
    if not line.startswith('  File '):
        return None
    line = line.rstrip('\r\n')
    if line.startswith('  File "'):
        j = line.rfind('", line ')
        if j < 0:
            return None
        filename, rest = line[8:j], line[j + 8:]
    else:                                         # '  File ???, line N in f'
        j = line.find(', line ')
        if j < 0:
            return None
        filename, rest = line[7:j], line[j + 7:]
    k = rest.find(' in ')
    if k < 0:
        return filename, rest, '???'
    return filename, rest[:k], rest[k + 4:]


def _thread_id(line):
    try:
        return int(line.split('hread 0x', 1)[1].split()[0], 16)
    except (IndexError, ValueError):
        return -1


def iter_samples(lines, main_tid=None):
    """Yield the main thread's frames (innermost first) for every dump in a faulthandler file.

    An empty list means the main thread had no Python frame (it was in C++). The main thread is the
    block whose id is main_tid; without a match the last block is used (CPython lists threads newest
    first, so the oldest - the main thread - comes last)."""
    blocks = None                                # list of (tid, frames) for the current dump
    frames = None
    for line in lines:
        if line.startswith('Timeout ('):
            if blocks is not None:
                yield _pick(blocks, main_tid)
            blocks, frames = [], None
            continue
        if blocks is None:
            continue
        if 'hread 0x' in line and line.rstrip().endswith('(most recent call first):'):
            frames = []
            blocks.append((_thread_id(line), frames))
        elif frames is not None:
            f = parse_frame(line)
            if f is not None:
                frames.append(f)
    if blocks is not None:
        yield _pick(blocks, main_tid)


def _pick(blocks, main_tid):
    if not blocks:
        return None
    for tid, frames in blocks:
        if tid == main_tid:
            return frames
    return blocks[-1][1]


# ------------------------------------------------------------------ attribution + aggregation
def attribute(frames, owner_of):
    """(owner charged, (owner, function, file, line) of the charged frame, owner of the innermost frame)."""
    if not frames:
        return OUTSIDE, None, OUTSIDE
    inner = None
    inner_key = None
    for filename, lineno, func in frames:
        o = owner_of(filename)
        if o == SELF:
            continue
        if inner is None:
            inner, inner_key = o, (o, func, filename, lineno)
        if o != GAME:
            return o, (o, func, filename, lineno), inner
    if inner is None:                             # only our own wrapper was running
        return OWN_LABEL, None, OWN_LABEL
    return GAME, inner_key, GAME


class Profile:
    """Sample counts per owner, per innermost owner ('self') and per charged function.

    Functions are counted per (owner, function, file) - a busy loop spreads its samples over many lines,
    so counting per line would rank it below one hot line elsewhere; the hottest line is kept per function."""

    def __init__(self):
        self.samples = 0
        self.dumps = 0
        self.charged = collections.Counter()
        self.self_owner = collections.Counter()
        self.functions = collections.Counter()      # (owner, func, file) -> samples
        self.lines = {}                              # (owner, func, file) -> Counter(line -> samples)

    def add(self, frames, owner_of):
        """Count one sample (frames innermost first; [] = outside Python)."""
        owner, key, inner = attribute(frames, owner_of)
        self.samples += 1
        self.charged[owner] += 1
        self.self_owner[inner] += 1
        if key is not None:
            fkey = key[:3]
            self.functions[fkey] += 1
            c = self.lines.get(fkey)
            if c is None:
                c = self.lines[fkey] = collections.Counter()
            c[key[3]] += 1

    def share(self, owner):
        """Percent of all samples charged to owner."""
        return 100.0 * self.charged[owner] / self.samples if self.samples else 0.0

    def python_samples(self):
        """Samples where the main thread was running Python."""
        return self.samples - self.charged[OUTSIDE]

    def mods(self):
        """[(owner, samples)] for script mods only, most expensive first."""
        return [(o, n) for o, n in self.charged.most_common() if o not in (OUTSIDE, GAME, OWN_LABEL)]

    def top_functions(self, owner, n=5):
        """[((owner, func, file, hottest line), samples of the whole function)] for one owner, hottest first."""
        rows = [(k, c) for k, c in self.functions.items() if k[0] == owner]
        rows.sort(key=lambda kc: (-kc[1], kc[0][1], kc[0][2]))
        return [(k + (self.lines[k].most_common(1)[0][0],), c) for k, c in rows[:n]]


def analyse_lines(lines, main_tid, owner_of):
    """Profile of an iterable of dump lines."""
    prof = Profile()
    for frames in iter_samples(lines, main_tid):
        prof.dumps += 1
        if frames is not None:
            prof.add(frames, owner_of)
    return prof


def analyse_file(path, main_tid, owner_of, max_bytes=64 * 1024 * 1024):
    """Profile of a faulthandler dump file, read line by line (a long run's dump is tens of MB and the
    game is short of RAM, so it is never loaded whole). Dumps that start after max_bytes are skipped.
    Returns (profile, truncated)."""
    cut = []

    def lines(f):
        n = 0
        for line in f:
            n += len(line)
            if n > max_bytes and line.startswith('Timeout ('):
                cut.append(True)
                return
            yield line
    with open(path, encoding='ascii', errors='replace') as f:
        prof = analyse_lines(lines(f), main_tid, owner_of)
    return prof, bool(cut)


# ------------------------------------------------------------------ tick timing
def tick_stats(durations, wall_s=None):
    """min/avg/p95/max in ms of Zone.update durations (seconds); p95 is nearest-rank."""
    d = sorted(durations)
    n = len(d)
    if not n:
        return {'n': 0, 'min_ms': 0.0, 'avg_ms': 0.0, 'p95_ms': 0.0, 'max_ms': 0.0, 'over_50ms': 0,
                'total_s': 0.0, 'busy_pct': None, 'per_s': None}
    total = sum(d)
    p95 = d[max(0, -(-95 * n // 100) - 1)]
    return {'n': n, 'min_ms': d[0] * 1000.0, 'avg_ms': total / n * 1000.0, 'p95_ms': p95 * 1000.0,
            'max_ms': d[-1] * 1000.0, 'over_50ms': sum(1 for x in d if x > 0.050), 'total_s': total,
            'busy_pct': (100.0 * total / wall_s) if wall_s else None,
            'per_s': (n / wall_s) if wall_s else None}


# ------------------------------------------------------------------ report
def short_name(owner):
    """'WickedWhims' style label for notifications (archive extension dropped)."""
    return owner[:-len('.ts4script')] if owner.lower().endswith('.ts4script') else owner


def top_mods(prof, n=5):
    """[(owner, percent of all samples)] for the n most expensive script mods."""
    return [(o, 100.0 * c / prof.samples) for o, c in prof.mods()[:n]] if prof.samples else []


def render_report(prof, ticks, meta, n_mods=15, n_funcs=5):
    """The text of a lag report. meta: dict with optional keys when, seconds, hz, zone_id, profile,
    script_mods, debt_start, debt_end, truncated, analysis_ms, stopped_by."""
    L = []
    L.append('SpeedKit lag report  %s' % meta.get('when', ''))
    L.append('Measured %.1f s (stopped by %s), lot %s, profile %s, %s script mods loaded' % (
        meta.get('seconds', 0.0), meta.get('stopped_by', '?'), meta.get('zone_id', '?'),
        meta.get('profile') or '-', meta.get('script_mods', '?')))
    L.append('')
    L.append('Zone.update (one simulation tick, exact timing):')
    if ticks['n']:
        L.append('  %d ticks (%.1f/s)  min %.2f ms  avg %.2f ms  p95 %.2f ms  max %.2f ms  over 50 ms: %d' % (
            ticks['n'], ticks['per_s'] or 0.0, ticks['min_ms'], ticks['avg_ms'], ticks['p95_ms'],
            ticks['max_ms'], ticks['over_50ms']))
        if ticks.get('busy_pct') is not None:
            L.append('  time inside Zone.update: %.1f%% of the measurement' % ticks['busy_pct'])
    else:
        L.append('  no ticks recorded (no lot running?)')
    if meta.get('debt_start') is not None or meta.get('debt_end') is not None:
        L.append('  simulator debt (sim minutes behind): start %s, end %s' % (meta.get('debt_start'),
                                                                             meta.get('debt_end')))
    L.append('')
    py = prof.python_samples()
    L.append('Stack samples of the simulation thread: %d of %d dumps (%.1f/s requested %s Hz)%s' % (
        prof.samples, prof.dumps, prof.samples / meta['seconds'] if meta.get('seconds') else 0.0,
        meta.get('hz', '?'), '  [dump file truncated]' if meta.get('truncated') else ''))
    L.append('  outside Python (C++: rendering, routing, animation, loading): %.1f%%' % prof.share(OUTSIDE))
    L.append('  running Python: %.1f%% - game code %.1f%%, script mods %.1f%%' % (
        100.0 * py / prof.samples if prof.samples else 0.0, prof.share(GAME),
        sum(100.0 * c / prof.samples for _o, c in prof.mods()) if prof.samples else 0.0))
    L.append('')
    L.append('Script mods by share of the simulation thread (charged = innermost mod frame on the stack,')
    L.append('including game code it called; self = the mod\'s own code was the innermost frame):')
    L.append('  %-48s %8s %8s %8s %9s' % ('script mod', 'charged%', 'of-Py%', 'self%', 'samples'))
    mods = prof.mods()
    for o, c in mods[:n_mods]:
        L.append('  %-48s %8.1f %8.1f %8.1f %9d' % (o[:48], 100.0 * c / prof.samples,
                                                   100.0 * c / py if py else 0.0,
                                                   100.0 * prof.self_owner[o] / prof.samples, c))
    if not mods:
        L.append('  (no script-mod code was sampled)')
    elif len(mods) > n_mods:
        L.append('  ... %d more' % (len(mods) - n_mods))
    L.append('')
    L.append('Hottest functions per mod (samples  function  (file:hottest line)):')
    for o, _c in mods[:n_mods]:
        L.append('  %s' % o)
        for (owner, func, filename, lineno), c in prof.top_functions(o, n_funcs):
            L.append('    %6d  %s  (%s:%s)' % (c, func, filename, lineno))
    L.append('  game (EA code with no mod on the stack)')
    for (owner, func, filename, lineno), c in prof.top_functions(GAME, n_funcs):
        L.append('    %6d  %s  (%s:%s)' % (c, func, filename, lineno))
    L.append('')
    if meta.get('analysis_ms') is not None:
        L.append('Analysis took %.0f ms.' % meta['analysis_ms'])
    L.append('Sampler: faulthandler.dump_traceback_later (GIL-free, armed once); ticks: wrapper on zone.Zone.update.')
    return '\n'.join(L) + '\n'

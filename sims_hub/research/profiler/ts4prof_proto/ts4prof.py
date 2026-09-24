# ts4prof - PROTOTYPE in-game lag profiler for The Sims 4 1.126.x (embedded CPython 3.7.0).
# Research prototype, NOT installed anywhere. To use: compile with Python 3.7 (the game's own python37_x64.dll works,
# see ../host37.py) into ts4prof.pyc and zip it at the root of "ts4prof.ts4script" in Mods\ (max one folder deep).
#
# What it measures (all opt-in, nothing runs until "ts4prof.start"):
#   1. sampler   - default 'watchdog': faulthandler's C watchdog dumps the stacks without the GIL (unbiased);
#                  'thread': Python thread + sys._current_frames() (needs the GIL -> biased toward late-in-burst code).
#                  Each sample is charged to the .ts4script owning the innermost frame (self) and to every
#                  .ts4script on the stack (inclusive). Neither sampler ever calls game APIs off the main thread.
#   2. probes    - exact timers around every alarm callback (alarms.AlarmElement._run / RepeatingAlarmElement._run)
#                  charged to the callback's owner, and around zone.Zone.update (per-tick python time, hitches).
# Report: <Documents>\Electronic Arts\The Sims 4\ts4prof_reports\ts4prof_<time>.txt/.json + an in-game notification.
# Cheats (CommandType.Live, no testingcheats needed):  ts4prof.start [seconds=60] [hz=100] [watchdog|thread]
#                                                      ts4prof.stop | ts4prof.status
import sys, os, time, threading, random, collections, json, functools

MAIN_TID = threading.get_ident()      # script mods are imported on the simulation thread (C++ -> import_modules)
_perf = time.perf_counter
_THIS_FILE = globals().get('__file__') or ''

# ------------------------------------------------------------------ ownership
_owner_by_module = {}


def _classify(path):
    p = path.replace('/', '\\')
    low = p.lower()
    i = low.find('.ts4script')
    if i >= 0:
        return os.path.basename(p[:i + 10])
    i = low.find('\\mods\\')                     # loose dev folders: Mods\<Folder>\Scripts\*.py
    if i >= 0:
        return 'Mods\\' + p[i + 6:].split('\\')[0]
    return 'game'


SELF_OWNER = None                               # set below: our own archive, never charged


def owner_of_globals(g):
    name = g.get('__name__')
    o = _owner_by_module.get(name)
    if o is None:
        o = _classify(g.get('__file__') or '')
        _owner_by_module[name] = o
    return o


def owner_of_callable(cb):
    f = getattr(cb, '__func__', cb)              # bound method -> function
    for _ in range(8):
        if isinstance(f, functools.partial):
            f = f.func
        elif hasattr(f, '__wrapped__') and not hasattr(f, '__globals__'):
            f = f.__wrapped__
        else:
            break
    g = getattr(f, '__globals__', None)
    if g is None:                                # callable object
        g = getattr(getattr(type(f), '__call__', None), '__globals__', None)
    return owner_of_globals(g) if g is not None else 'unknown'


SELF_OWNER = _classify(_THIS_FILE)

# ------------------------------------------------------------------ sampler
class Sampler:
    def __init__(self, hz):
        self.rate = float(hz)
        self.self_c = collections.Counter(); self.incl_c = collections.Counter(); self.func_c = collections.Counter()
        self.kept = self.entry = self.errors = 0
        self.running = False; self.thread = None; self.old_switch = None

    def start(self):
        self.old_switch = sys.getswitchinterval()
        sys.setswitchinterval(0.001)             # 1 ms: finer sampling inside long python bursts. Never < 1 ms on
        self.running = True                      # Windows (0 ms timed wait -> GIL ping-pong, measured).
        self.thread = threading.Thread(target=self._loop, name='ts4prof-sampler', daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread is not None:
            self.thread.join(1.0)
        if self.old_switch is not None:
            sys.setswitchinterval(self.old_switch)

    def _loop(self):
        cf = sys._current_frames; expo = random.expovariate; sleep = time.sleep
        while self.running:
            sleep(min(expo(self.rate), 0.25))    # Poisson: no phase-locking with the tick rhythm
            try:
                f = cf().get(MAIN_TID)
                if f is None:
                    continue
                inner = None; key = None; seen = set(); depth = 0; fr = f
                while fr is not None:
                    o = owner_of_globals(fr.f_globals)
                    if o != SELF_OWNER:          # our own probe wrappers are transparent
                        if inner is None:
                            inner = o; co = fr.f_code; key = (o, co.co_name, co.co_filename, co.co_firstlineno)
                        seen.add(o); depth += 1
                    fr = fr.f_back
                if inner is None:
                    continue
                if depth == 1 and f.f_lasti <= 10:
                    self.entry += 1              # first bytecodes of a C++->Python call: GIL-handoff artifact
                    continue
                self.kept += 1; self.self_c[inner] += 1; self.func_c[key] += 1
                for o in seen:
                    self.incl_c[o] += 1
            except Exception:
                self.errors += 1


class WatchdogSampler:
    """GIL-free sampler: faulthandler's C watchdog thread dumps every thread's stack every 1/hz s into a file
    without taking the GIL (so samples are uniform in wall time, no GIL-handoff bias). Parsed after stop().
    Measured on python37_x64.dll: ~62 dumps/s max on Windows, unbiased shares. Caveat: the dump reads frames
    while the game runs (tiny crash risk if a frame is freed mid-read); only one dump_traceback_later per process."""
    import re as _re
    _FRAME = _re.compile(r'^\s+File "(.*)", line (\d+) in (.*)$')

    def __init__(self, hz):
        self.interval = 1.0 / max(1.0, float(hz)); self.path = None; self.f = None
        self.self_c = collections.Counter(); self.incl_c = collections.Counter(); self.func_c = collections.Counter()
        self.kept = self.entry = self.errors = 0; self.dumps = 0; self.in_python = 0; self.fmap = {}

    def _build_map(self):                        # co_filename -> owner, from every loaded mod module
        for name, m in list(sys.modules.items()):
            f = getattr(m, '__file__', None) or ''
            o = _classify(f)
            if o == 'game':
                continue
            for v in list(vars(m).values()):
                objs = [v] + (list(vars(v).values()) if isinstance(v, type) else [])
                for x in objs:
                    x = getattr(x, '__func__', x)
                    c = getattr(x, '__code__', None)
                    if c is not None and getattr(x, '__module__', None) == name:
                        self.fmap.setdefault(c.co_filename, o)

    def start(self):
        import faulthandler
        self._build_map()
        self.path = os.path.join(reports_dir(), 'ts4prof_raw_%s.txt' % time.strftime('%Y%m%d_%H%M%S'))
        self.f = open(self.path, 'w')
        faulthandler.dump_traceback_later(self.interval, repeat=True, file=self.f, exit=False)

    def stop(self):
        import faulthandler
        faulthandler.cancel_dump_traceback_later()
        self.f.close()
        self._parse()

    def _owner(self, fn):
        o = self.fmap.get(fn)
        if o is None:
            o = _classify(fn)                    # a .py compiled from inside a .ts4script has the archive path
            self.fmap[fn] = o
        return o

    def _parse(self):
        block = None
        def flush(frames):
            frames = [fr for fr in frames if self._owner(fr[0]) != SELF_OWNER]
            if not frames:
                return
            self.in_python += 1; self.kept += 1
            owners = [self._owner(fr[0]) for fr in frames]
            self.self_c[owners[0]] += 1; self.func_c[(owners[0], frames[0][2], frames[0][0], int(frames[0][1]))] += 1
            for o in set(owners):
                self.incl_c[o] += 1
        with open(self.path, encoding='ascii', errors='replace') as f:
            for line in f:
                if line.startswith('Timeout ('):
                    self.dumps += 1
                    if block is not None: flush(block)
                    block = None
                elif 'hread 0x' in line:          # "Thread 0x0001a2b3 (...)" or "Current thread 0x..." (8 hex digits on Windows)
                    if block is not None: flush(block)
                    try:
                        tid = int(line.split('hread 0x')[1].split()[0], 16)
                    except ValueError:
                        tid = -1
                    block = [] if tid == MAIN_TID else None
                elif block is not None:
                    m = self._FRAME.match(line)
                    if m:
                        block.append(m.groups())
            if block is not None:
                flush(block)


# ------------------------------------------------------------------ deterministic probes
class Probes:
    def __init__(self):
        self.alarm_ms = collections.Counter(); self.alarm_n = collections.Counter(); self.alarm_max = collections.Counter()
        self.tick_ms = []; self.enabled = False; self._patched = []

    def _patch(self, cls, name, make):
        orig = cls.__dict__[name]
        wrapper = make(orig)
        wrapper.__ts4prof_orig__ = orig
        setattr(cls, name, wrapper)
        self._patched.append((cls, name, orig, wrapper))

    def install(self):
        import alarms, zone
        probes = self

        def make_alarm_run(orig):
            def _run(self, t):
                if not probes.enabled:
                    return orig(self, t)
                t0 = _perf()
                try:
                    return orig(self, t)
                finally:
                    dt = (_perf() - t0) * 1000.0
                    try:
                        o = owner_of_callable(self.callback)
                        probes.alarm_ms[o] += dt; probes.alarm_n[o] += 1
                        if dt > probes.alarm_max[o]:
                            probes.alarm_max[o] = dt
                    except Exception:
                        pass
            return _run

        def make_zone_update(orig):
            def update(self, absolute_ticks):
                if not probes.enabled:
                    return orig(self, absolute_ticks)
                t0 = _perf()
                try:
                    return orig(self, absolute_ticks)
                finally:
                    probes.tick_ms.append((_perf() - t0) * 1000.0)
            return update

        self._patch(alarms.AlarmElement, '_run', make_alarm_run)
        self._patch(alarms.RepeatingAlarmElement, '_run', make_alarm_run)   # overrides _run, so wrap it too
        self._patch(zone.Zone, 'update', make_zone_update)

    def uninstall(self):
        for cls, name, orig, wrapper in reversed(self._patched):
            if cls.__dict__.get(name) is wrapper:   # someone wrapped on top of us: leave it, we are disabled anyway
                setattr(cls, name, orig)
        self._patched = []


# ------------------------------------------------------------------ session + report
class Session:
    def __init__(self, seconds, hz, mode='watchdog'):
        self.seconds = seconds; self.probes = Probes()
        self.sampler = WatchdogSampler(hz) if mode == 'watchdog' else Sampler(hz)
        self.t0 = self.t1 = None; self.debt0 = self.debt1 = None; self.alarm_handle = None

    @staticmethod
    def sim_debt():
        try:
            import services
            return services.time_service().get_simulator_debt()   # sim minutes the sim timeline is behind
        except Exception:
            return None

    def start(self):
        self.probes.install(); self.probes.enabled = True
        self.debt0 = self.sim_debt(); self.t0 = _perf()
        self.sampler.start()

    def stop(self):
        self.sampler.stop(); self.probes.enabled = False; self.probes.uninstall()
        self.t1 = _perf(); self.debt1 = self.sim_debt()

    def report(self):
        s = self.sampler; p = self.probes; wall = (self.t1 or _perf()) - self.t0
        ticks = sorted(p.tick_ms)
        def pct(q):
            return ticks[min(len(ticks) - 1, int(q * len(ticks)))] if ticks else 0.0
        mods = []
        for o in set(s.incl_c) | set(p.alarm_ms):
            if o in ('game',):
                continue
            mods.append({'owner': o, 'self_pct': 100.0 * s.self_c[o] / max(s.kept, 1),
                         'incl_pct': 100.0 * s.incl_c[o] / max(s.kept, 1),
                         'alarm_ms_per_s': p.alarm_ms[o] / max(wall, 1e-9), 'alarm_calls': p.alarm_n[o],
                         'alarm_max_ms': p.alarm_max[o]})
        mods.sort(key=lambda m: (m['self_pct'], m['alarm_ms_per_s']), reverse=True)
        return {'wall_s': wall, 'sampler': type(s).__name__, 'samples': s.kept, 'entry_artifacts': s.entry,
                'sampler_errors': s.errors, 'main_thread_in_python_pct': (100.0 * s.in_python / s.dumps) if getattr(s, 'dumps', 0) else None,
                'game_self_pct': 100.0 * s.self_c['game'] / max(s.kept, 1),
                'ticks': len(ticks), 'tick_ms_p50': pct(.5), 'tick_ms_p95': pct(.95), 'tick_ms_max': ticks[-1] if ticks else 0.0,
                'ticks_over_50ms': sum(1 for t in ticks if t > 50), 'sim_debt_min_start': self.debt0, 'sim_debt_min_end': self.debt1,
                'mods': mods,
                'hot_functions': [{'owner': k[0], 'func': k[1], 'file': k[2], 'line': k[3], 'samples': c}
                                  for k, c in s.func_c.most_common(40) if k[0] != 'game']}


def reports_dir():
    p = _THIS_FILE
    while p and os.path.basename(p).lower() != 'mods':
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    base = os.path.dirname(p) if os.path.basename(p).lower() == 'mods' else os.path.expanduser('~')
    d = os.path.join(base, 'ts4prof_reports')              # NOT inside Mods: nothing new for the game to scan
    os.makedirs(d, exist_ok=True)
    return d


def write_report(rep):
    stamp = time.strftime('%Y%m%d_%H%M%S')
    d = reports_dir()
    with open(os.path.join(d, 'ts4prof_%s.json' % stamp), 'w', encoding='utf-8') as f:
        json.dump(rep, f, indent=1)
    lines = ['ts4prof  %.0f s, %d samples, python tick p50 %.1f ms / p95 %.1f ms / max %.1f ms, %d ticks > 50 ms, sim debt %s -> %s min' % (
        rep['wall_s'], rep['samples'], rep['tick_ms_p50'], rep['tick_ms_p95'], rep['tick_ms_max'], rep['ticks_over_50ms'],
        rep['sim_debt_min_start'], rep['sim_debt_min_end']),
        'game (EA code) self: %.1f%% of sampled python time' % rep['game_self_pct'],
        '%-44s %7s %7s %10s %8s %9s' % ('script mod', 'self%', 'incl%', 'alarm ms/s', 'alarms', 'alarm max')]
    for m in rep['mods']:
        lines.append('%-44s %7.1f %7.1f %10.2f %8d %9.1f' % (m['owner'][:44], m['self_pct'], m['incl_pct'], m['alarm_ms_per_s'],
                                                          m['alarm_calls'], m['alarm_max_ms']))
    lines.append('hot mod functions:')
    for h in rep['hot_functions'][:20]:
        lines.append('  %5d  %-30s %s  (%s:%d)' % (h['samples'], h['owner'][:30], h['func'], h['file'], h['line']))
    path = os.path.join(d, 'ts4prof_%s.txt' % stamp)
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path, lines


def notify(title, text):
    try:
        from ui.ui_dialog_notification import UiDialogNotification
        from sims4.localization import LocalizationHelperTuning
        dlg = UiDialogNotification.TunableFactory().default(
            None, title=lambda *_, **__: LocalizationHelperTuning.get_raw_text(title),
            text=lambda *_, **__: LocalizationHelperTuning.get_raw_text(text))
        dlg.show_dialog()
    except Exception:
        pass


# ------------------------------------------------------------------ cheat commands (main thread only)
_session = None


class _AlarmOwner:                      # alarms need a weak-referenceable owner
    pass


_ALARM_OWNER = _AlarmOwner()


def _finish(output=None):
    global _session
    s = _session
    if s is None:
        return
    _session = None
    s.stop()
    rep = s.report()
    path, lines = write_report(rep)
    top = ', '.join('%s %.0f%%' % (m['owner'].replace('.ts4script', ''), m['self_pct']) for m in rep['mods'][:3]) or 'none'
    notify('ts4prof', 'Top script-mod cost: %s. Report: %s' % (top, path))
    if output is not None:
        for line in lines[:12]:
            output(line)


try:
    import sims4.commands

    @sims4.commands.Command('ts4prof.start', command_type=sims4.commands.CommandType.Live)
    def ts4prof_start(seconds: int = 60, hz: int = 100, mode: str = 'watchdog', _connection=None):
        global _session
        out = sims4.commands.CheatOutput(_connection)
        if _session is not None:
            out('ts4prof: already running'); return
        _session = Session(seconds, max(10, min(hz, 400)), mode)
        _session.start()
        try:
            import alarms, clock
            _session.alarm_handle = alarms.add_alarm_real_time(_ALARM_OWNER, clock.interval_in_real_seconds(seconds),
                                                               lambda _h: _finish(None))
        except Exception as e:
            out('ts4prof: no auto-stop alarm (%s); use ts4prof.stop' % e)
        out('ts4prof: profiling for %d s at ~%d Hz' % (seconds, hz))

    @sims4.commands.Command('ts4prof.stop', command_type=sims4.commands.CommandType.Live)
    def ts4prof_stop(_connection=None):
        out = sims4.commands.CheatOutput(_connection)
        if _session is None:
            out('ts4prof: not running'); return
        if _session.alarm_handle is not None:
            try:
                _session.alarm_handle.cancel()
            except Exception:
                pass
        _finish(out)

    @sims4.commands.Command('ts4prof.status', command_type=sims4.commands.CommandType.Live)
    def ts4prof_status(_connection=None):
        out = sims4.commands.CheatOutput(_connection)
        s = _session
        out('ts4prof: %s' % ('idle' if s is None else 'running, %d samples, %d ticks' % (s.sampler.kept, len(s.probes.tick_ms))))
except ImportError:                     # outside the game (tests)
    pass

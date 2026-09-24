"""Lag meter: 'speedkit.lag <seconds>' measures which script mods use the simulation thread.

What one measurement does (all on the simulation thread; no threads of our own):
  1. start(): arms faulthandler.dump_traceback_later(1/hz, repeat=True, file=reports\\lag_raw_last.txt)
     ONCE. Re-arming per tick is too expensive (arm+cancel p90 4 ms, research/profiler hitch_test).
     The first start also wraps zone.Zone.update (installed once, never removed). While no measurement
     runs the wrapper only checks one global; while one runs it adds two perf_counter calls and an append.
  2. The wrapper times every Zone.update call (the whole per-tick simulation step: areaserver.
     c_api_server_tick -> zone.update(absolute_ticks)) and, when the time is up, finishes the
     measurement right there (still on the simulation thread). The wrapper is also the only thing that
     ends a run on time, so start() refuses when it cannot be installed (faulthandler would otherwise
     keep writing until the main menu). If our wrapper ends up in the chain twice (another mod wrapped
     it without functools.wraps, hiding our marker, and a later start() wrapped again), only the
     outermost one times the tick.
  3. finish(): cancels the watchdog, builds the co_filename -> archive map from sys.modules, parses the
     dump (sampling.py), writes reports\\lag_<time>.txt, shows a notification with the top 5 mods and
     echoes the summary to the cheat console that started it.
  4. A run also ends when the lot is unloaded: travel, quit to the menu and quit to the desktop all go
     through areaserver.c_api_request_client_disconnect -> zone.on_teardown(client) (LOAD_METHOD on the
     instance, so a class-level wrapper, installed together with the Zone.update one, sees it). Without
     this the watchdog kept dumping through a travel loading screen (no Zone.update there, and loading
     screens are minutes long with this library) or through the game's shutdown. The lot's UI is gone
     by then, so that run's notification is shown after the next lot has loaded.
Caveats (research open questions): faulthandler reads stacks while the game runs (a very rare crash is
possible if a frame is freed mid-read, so this only runs on request), and only one
dump_traceback_later can be armed per process, so a mod that uses it at the same time loses its own.
"""
import os
import sys
import time

from . import common, hooks, sampling

DEFAULT_SECONDS = 60
DEFAULT_HZ = 25                     # 1,500 samples a minute: +-1.3 points at a 50% share
MIN_SECONDS, MAX_SECONDS = 5, 1800
MIN_HZ, MAX_HZ = 5, 100
SAMPLE_BUDGET = 12000               # the rate is lowered for long runs: the dump stays < ~60 MB and the
                                    # parse at the end < ~4 s (1,500 samples of 100 frames = 7.2 MB, parsed
                                    # in 0.4-1.0 s by the game's Python in tests/test_ingame.py)
MAX_TICKS = 500000

_perf = time.perf_counter
_session = None                     # the running Session, read by the Zone.update wrapper every tick
last_result = None                  # summary of the last finished measurement (for status / tests)
_pending = None                     # a result whose notification waits for the next lot (ended by unload)


def _thread_ident():
    try:
        import _thread
        return _thread.get_ident()
    except Exception:
        return None


class Session:
    """One measurement: the armed faulthandler file plus the Zone.update durations."""

    def __init__(self, seconds, hz, connection=None):
        self.seconds = float(seconds)
        self.hz = int(hz)
        self.connection = connection
        self.main_tid = _thread_ident()   # commands run on the simulation thread
        self.ticks = []
        self.raw_path = None
        self.file = None
        self.t0 = self.deadline = None
        self.wall_start = None
        self.debt_start = None
        self.finishing = False
        self.in_tick = False              # a Zone.update wrapper of ours is timing the current tick

    def start(self):
        """Arm the sampler (once) and start the clock."""
        import faulthandler
        d = common.reports_dir()
        if not d:
            raise RuntimeError('no reports folder (not running from a Mods folder)')
        self.raw_path = os.path.join(d, 'lag_raw_last.txt')
        self.file = open(self.raw_path, 'w')
        self.debt_start = simulator_debt()
        self.wall_start = time.time()
        self.t0 = _perf()
        self.deadline = self.t0 + self.seconds
        faulthandler.dump_traceback_later(1.0 / self.hz, repeat=True, file=self.file, exit=False)

    def stop_sampler(self):
        """Disarm faulthandler and close the dump file (safe to call twice)."""
        try:
            import faulthandler
            faulthandler.cancel_dump_traceback_later()
        except Exception:
            common.log_exception('cancel_dump_traceback_later')
        if self.file is not None:
            try:
                self.file.close()
            except Exception:
                pass
            self.file = None


def simulator_debt():
    """Sim minutes the simulation is behind (TimeService.get_simulator_debt), or None."""
    try:
        import services
        return round(float(services.time_service().get_simulator_debt()), 2)
    except Exception:
        return None


def _zone_id():
    try:
        import services
        z = services.current_zone_id()
        return '0x%x' % z if isinstance(z, int) else str(z)
    except Exception:
        return '?'


# ------------------------------------------------------------------ the Zone.update wrapper
def _make_update_wrapper(orig):
    def update(*args, **kwargs):
        s = _session
        if s is None or s.in_tick:        # idle, or an outer wrapper of ours already times this tick
            return orig(*args, **kwargs)
        s.in_tick = True
        t0 = _perf()
        try:
            return orig(*args, **kwargs)
        finally:
            t1 = _perf()
            s.in_tick = False
            try:
                if not s.finishing:
                    if len(s.ticks) < MAX_TICKS:
                        s.ticks.append(t1 - t0)
                    if t1 >= s.deadline:
                        finish('time up')
            except Exception:
                common.log_exception('lag meter tick')
    return update


def ensure_tick_wrapper():
    """Wrap zone.Zone.update (and Zone.on_teardown, best effort) once. Returns True when the Zone.update
    wrapper is in place."""
    try:
        import zone
    except Exception:
        common.log_exception('import zone')
        return False
    if getattr(zone.Zone, 'on_teardown', None) is not None:
        hooks.install(zone.Zone, 'on_teardown',
                      lambda orig: hooks.around(orig, before=lambda a: on_lot_unloaded(), label='lot unloaded'),
                      'Zone.on_teardown')
    else:
        common.log('lag meter: zone.Zone has no on_teardown; a run then ends at its time or the main menu')
    return hooks.install(zone.Zone, 'update', _make_update_wrapper, 'Zone.update')


def on_lot_unloaded():
    """Zone.on_teardown is about to run (travel, quit to menu or desktop): end a running measurement now
    and keep its notification for the next lot."""
    global _pending
    if _session is None:
        return
    r = finish('lot unloaded', show=False)
    if r is not None:
        _pending = r


def show_pending():
    """Show the notification of a run that ended when its lot was unloaded (called after a lot loaded)."""
    global _pending
    r, _pending = _pending, None
    if r is not None:
        common.notify(r['title'] + ' (previous lot)', r['text'])


# ------------------------------------------------------------------ start / finish
def start(seconds=DEFAULT_SECONDS, hz=DEFAULT_HZ, connection=None):
    """Start a measurement. Returns a message for the cheat console."""
    global _session
    if _session is not None:
        left = max(0.0, _session.deadline - _perf())
        return 'SpeedKit lag meter is already running (%.0f s left). Use: speedkit.lag stop' % left
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, int(seconds)))
    hz = max(MIN_HZ, min(MAX_HZ, int(hz), SAMPLE_BUDGET // seconds))
    if not ensure_tick_wrapper():
        common.log('lag meter: Zone.update could not be wrapped; not starting (nothing could stop the run on time)')
        return ('SpeedKit lag meter could not start: zone.Zone.update could not be wrapped '
                '(see SpeedKit\\reports\\monitor.log)')
    s = Session(seconds, hz, connection)
    try:
        s.start()
    except Exception:
        common.log_exception('lag meter start')
        s.stop_sampler()
        return 'SpeedKit lag meter could not start (see SpeedKit\\reports\\monitor.log)'
    _session = s
    common.log('lag meter: started for %d s at %d Hz (main thread %s)' % (seconds, hz, s.main_tid))
    return 'SpeedKit lag meter: measuring for %d s. Keep playing normally; a notification shows the result.' % seconds


def running():
    """True while a measurement is active."""
    return _session is not None


def status():
    """One line about the current or last measurement."""
    s = _session
    if s is not None:
        return 'SpeedKit lag meter: running, %.0f s left, %d ticks so far' % (
            max(0.0, s.deadline - _perf()), len(s.ticks))
    if last_result:
        return 'SpeedKit lag meter: idle. Last report: %s' % last_result.get('report')
    return 'SpeedKit lag meter: idle'


def finish(stopped_by='stop command', show=True):
    """End the running measurement, write the report and (if show) notify. Returns the summary dict
    (or None). show=False is for the main menu and a lot unload, where there is no lot UI to show a
    notification in."""
    global _session, last_result
    s = _session
    if s is None or s.finishing:
        return None
    s.finishing = True
    _session = None                   # the wrapper goes back to a plain pass-through from here on
    s.stop_sampler()
    elapsed = _perf() - s.t0
    try:
        result = _analyse(s, elapsed, stopped_by)
    except Exception:
        common.log_exception('lag meter analysis')
        result = None
    last_result = result
    if result is None:
        common.cheat_output(s.connection)('SpeedKit lag meter failed - see SpeedKit\\reports\\monitor.log')
        return None
    if show:
        common.notify(result['title'], result['text'])
    out = common.cheat_output(s.connection)
    for line in result['console']:
        out(line)
    return result


def _analyse(s, elapsed, stopped_by):
    t_a = _perf()
    sims = common.sims_dir()
    mods_dir = os.path.join(sims, 'Mods') if sims else None
    owner_of = sampling.OwnerLookup(sampling.build_owner_map(list(sys.modules.items()),
                                                             common.PACKAGE, mods_dir), mods_dir)
    prof, truncated = sampling.analyse_file(s.raw_path, s.main_tid, owner_of)
    ticks = sampling.tick_stats(s.ticks, elapsed)
    loaded = common.loaded_script_mods()
    profile = None
    try:
        from . import loadtimer
        profile = loadtimer.state.get('profile')      # what the game loaded (read at our import)
    except Exception:
        pass
    analysis_ms = (_perf() - t_a) * 1000.0
    meta = {'when': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.wall_start)),
            'seconds': elapsed, 'hz': s.hz, 'zone_id': _zone_id(), 'profile': profile,
            'script_mods': len(loaded), 'debt_start': s.debt_start, 'debt_end': simulator_debt(),
            'truncated': truncated, 'analysis_ms': analysis_ms, 'stopped_by': stopped_by}
    text = sampling.render_report(prof, ticks, meta)
    stamp = time.strftime('%Y%m%d_%H%M%S', time.localtime(s.wall_start))
    path = os.path.join(common.reports_dir(), 'lag_%s.txt' % stamp)
    n = 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(common.reports_dir(), 'lag_%s_%d.txt' % (stamp, n))
    with open(path, 'w', encoding='utf-8', errors='replace') as f:     # mod names come from file names,
        f.write(text)                                                  # which may hold a lone surrogate
    top = sampling.top_mods(prof, 5)
    lines = ['%d. %s %.1f%%' % (i + 1, sampling.short_name(o), pct) for i, (o, pct) in enumerate(top)]
    if not lines:
        lines = ['No script-mod code was sampled.']
    summary = 'Game code %.0f%%, outside Python %.0f%%. Tick avg %.1f ms, p95 %.1f ms, max %.0f ms.' % (
        prof.share(sampling.GAME), prof.share(sampling.OUTSIDE), ticks['avg_ms'], ticks['p95_ms'], ticks['max_ms'])
    rel = os.path.relpath(path, sims) if sims else path
    body = 'Top script mods (share of the simulation thread, %.0f s):\n%s\n%s\nReport: %s' % (
        elapsed, '\n'.join(lines), summary, rel)
    common.log('lag meter: %d samples, %d ticks, report %s; top: %s' % (
        prof.samples, ticks['n'], path, '; '.join(lines)))
    return {'report': path, 'title': 'SpeedKit lag meter', 'text': body,
            'console': ['SpeedKit lag meter: %d samples in %.0f s' % (prof.samples, elapsed)] + lines +
                       [summary, 'Report: ' + path],
            'samples': prof.samples, 'dumps': prof.dumps, 'ticks': ticks, 'top': top,
            'shares': {o: prof.share(o) for o in prof.charged}, 'analysis_ms': analysis_ms}


def stop_if_running(reason):
    """Finish a running measurement early (e.g. when the game goes back to the main menu)."""
    if _session is not None:
        common.guarded('lag meter stop (%s)' % reason, finish, reason, False)

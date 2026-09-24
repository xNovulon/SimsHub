# Runs inside the game's python37_x64.dll (host37.py): loads ts4prof_proto/ts4prof.py compiled to a .pyc inside a
# synthetic ts4prof.ts4script, with minimal stand-ins for the game modules it touches (alarms, zone, services,
# sims4.commands, clock), and two fake script mods whose alarm callbacks / injected code burn known time.
import sys, os, types, time, zipfile, marshal, importlib.util, collections
R = r'C:\Users\basim\Tools\sims4_speedkit\research\profiler'
perf = time.perf_counter
print('TARGET_PID', os.getpid()); sys.stdout.flush()

# ---- stand-ins for game modules (same class/method names + signatures as simulation.zip) ----
def mod(name, **kw):
    m = types.ModuleType(name); m.__dict__.update(kw); sys.modules[name] = m; return m
class FunctionElement:
    __slots__ = ('callback',)
    def __init__(self, callback): self.callback = callback
class AlarmElement(FunctionElement):
    __slots__ = ()
    def _run(self, t): return self.callback(None)
class RepeatingAlarmElement(AlarmElement):
    __slots__ = ('interval',)
    def __init__(self, interval, callback): super().__init__(callback); self.interval = interval
    def _run(self, t): return self.callback(None)
mod('alarms', AlarmElement=AlarmElement, RepeatingAlarmElement=RepeatingAlarmElement,
    add_alarm_real_time=lambda owner, span, cb, **k: None)
ELEMENTS = []
class Zone:
    def update(self, absolute_ticks):
        for e in ELEMENTS:               # stands in for time_service.update -> sim_timeline.simulate -> element._run
            e._run(None)
        g_end = perf() + 0.003           # EA work
        while perf() < g_end: pass
mod('zone', Zone=Zone)
class _TS:
    def get_simulator_debt(self): return 0.0
mod('services', time_service=lambda: _TS())
mod('clock', interval_in_real_seconds=lambda s: s)
s4 = sys.modules.get('sims4') or mod('sims4'); s4.__path__ = []
class CommandType: DebugOnly = 1; Automation = 3; Cheat = 4; Live = 5
REG = {}
def Command(*aliases, command_type=CommandType.DebugOnly, **kw):
    def deco(fn): REG[aliases[0]] = (fn, command_type); return fn
    return deco
class CheatOutput:
    def __init__(self, ctx): pass
    def __call__(self, s): print('[cheat console]', s)
s4.commands = mod('sims4.commands', Command=Command, CommandType=CommandType, CheatOutput=CheatOutput)

# ---- build ts4script archives (pyc compiled by THIS game python) ----
def build(zipname, entries):
    p = os.path.join(R, 'py37', zipname)
    with zipfile.ZipFile(p, 'w') as z:
        for arcname, src, fake_path in entries:
            code = compile(src, fake_path, 'exec')
            z.writestr(arcname, importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(code))
    sys.path.append(p)
build('ts4prof.ts4script', [('ts4prof.pyc', open(os.path.join(R, 'ts4prof_proto', 'ts4prof.py'), encoding='utf-8').read(), r'C:\dev\ts4prof\ts4prof.py')])
BURN = 'import time\nperf = time.perf_counter\ndef burn(ms):\n    end = perf() + ms / 1000.0\n    while perf() < end: pass\n'
build('fake_heavy.ts4script', [('heavy/__init__.pyc', BURN + 'def on_alarm(handle):\n    burn(4)\n', r'E:\Builds\Heavy\heavy\__init__.py')])
build('fake_light.ts4script', [('light.pyc', BURN + 'class Thing:\n    def cb(self, handle):\n        burn(1)\n', r'/Users/x/light.py')])
import ts4prof, heavy, light
ts4prof.reports_dir = lambda: os.path.join(R, 'py37')          # test only: keep output in the research folder
print('ts4prof loaded from', ts4prof.__file__, '| commands:', {k: v[1] for k, v in REG.items()})
ELEMENTS[:] = [AlarmElement(heavy.on_alarm), RepeatingAlarmElement(5, light.Thing().cb)]
ZONE = Zone()
MODE = HOST_ARGS or 'watchdog'
REG['ts4prof.start'][0](30, 150, MODE, _connection=None)

def tick():
    ZONE.update(0)

def finish(host_s):
    REG['ts4prof.status'][0](_connection=None)
    REG['ts4prof.stop'][0](_connection=None)
    print('restored originals:', AlarmElement.__dict__['_run'].__name__, Zone.__dict__['update'].__qualname__)
    sys.stdout.flush()

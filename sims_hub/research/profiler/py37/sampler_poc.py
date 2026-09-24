# Runs INSIDE the game's python37_x64.dll via host37.py. Emulates the TS4 situation:
#  - the "C++" host thread owns the GIL for good and calls tick() (like areaserver.c_api_server_tick),
#  - between ticks it stays in C (host busy-wait) without releasing the GIL,
#  - two fake script mods (loaded from .ts4script zips via zipimport, with author-path co_filename) burn known time.
# A background sampling thread uses sys._current_frames() and attributes samples to the owning .ts4script.
import sys, os, time, threading, zipfile, marshal, importlib.util, collections

HERE = r'C:\Users\basim\Tools\sims4_speedkit\research\profiler\py37'
cfg = dict(kv.split('=') for kv in HOST_ARGS.split(',') if kv) if HOST_ARGS else {}
SAMPLER = cfg.get('sampler', '1') == '1'
INTERVAL = float(cfg.get('interval_ms', '5')) / 1000
A_MS, B_MS, G_MS, C_MS = (float(cfg.get(k, d)) for k, d in (('a', '4'), ('b', '2'), ('g', '4'), ('c', '0')))
SWITCH = cfg.get('switch')
if SWITCH:
    sys.setswitchinterval(float(SWITCH) / 1000)
perf = time.perf_counter
print('TARGET_PID', os.getpid()); sys.stdout.flush()

def build_mod(zipname, modname, author_path, src):
    p = os.path.join(HERE, zipname)
    code = compile(src, author_path, 'exec')
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr(modname + '/__init__.pyc', importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(code))
    sys.path.append(p)

BURN = '''
import time
perf = time.perf_counter
def burn(ms):
    end = perf() + ms / 1000.0
    x = 0
    while perf() < end:
        x += 1
    ITERS[0] += x
    return x
'''
build_mod('fake_modA.ts4script', 'modA', r'E:\Builds\AuthorA\modA\__init__.py', BURN + '''
def alarm_callback(handle):      # like a repeating alarm callback
    return burn(A_MS)
''')
build_mod('fake_modB.ts4script', 'modB', r'.\modB_v2\modB\__init__.py', BURN + '''
def install(game_obj):           # classic "inject": wrap a game method
    original = game_obj.update
    def _wrapped(*a, **k):
        burn(B_MS)
        big = sum(range(int(C_US * 12)))   # C-level work (holds GIL, no bytecode) inside the mod
        return original(*a, **k)
    game_obj.update = _wrapped
''')
import modA, modB
ITERS = [0]
modA.A_MS = A_MS; modB.B_MS = B_MS; modB.C_US = C_MS * 1000; modA.ITERS = modB.ITERS = ITERS

class GameThing:                 # stands in for EA code (module __main__ here = 'game')
    def update(self):
        end = perf() + G_MS / 1000.0
        x = 0
        while perf() < end:
            x += 1
        ITERS[0] += x

thing = GameThing()
modB.install(thing)
truth = collections.Counter(); tick_py = []

DEPTH = int(cfg.get('depth', '0'))
PROF = None
if cfg.get('mode') == 'cprofile':
    import cProfile
    PROF = cProfile.Profile()
def nest(n, fn):                 # emulate TS4's deep stacks (timeline -> element -> interaction -> ...)
    if n <= 0:
        return fn()
    return nest(n - 1, fn)
def work():
    ta = perf(); modA.alarm_callback(None); truth['fake_modA.ts4script'] += perf() - ta
    tb = perf(); thing.update(); truth['_tick_update_total'] += perf() - tb
def tick():                      # stands in for areaserver.c_api_server_tick
    t0 = perf()
    if PROF: PROF.enable()
    nest(DEPTH, work)
    if PROF: PROF.disable()
    tick_py.append(perf() - t0)

# ---------------- the sampler (this is the part that would ship in the profiler mod) ----------------
MAIN = threading.get_ident()
owner_cache = {}
def owner_of(g):
    name = g.get('__name__')
    o = owner_cache.get(name)
    if o is None:
        f = g.get('__file__') or ''
        i = f.lower().find('.ts4script')
        o = os.path.basename(f[:i + 10]) if i >= 0 else 'game'
        owner_cache[name] = o
    return o

self_counts = collections.Counter(); incl_counts = collections.Counter(); funcs = collections.Counter()
entry_like = collections.Counter(); overshoots = []; stop = False; sample_cost = []

import random
rnd = random.random
JITTER = {'0': None, '1': 'uni', 'exp': 'exp'}[cfg.get('jitter', '0')]
expo = random.expovariate
def sampler():
    cf = sys._current_frames
    while not stop:
        t0 = perf()
        time.sleep(expo(1.0 / INTERVAL) if JITTER == 'exp' else INTERVAL * (0.2 + 1.6 * rnd()) if JITTER else INTERVAL)   # releases the GIL; returning needs it back
        t1 = perf()
        f = cf().get(MAIN)
        if f is None:
            continue
        depth = 0; innermost = None; seen = set(); fr = f
        while fr is not None:
            if fr.f_code.co_filename != '<string>':   # harness-only: PyRun_SimpleString module frame = the C++ caller
                o = owner_of(fr.f_globals)
                if innermost is None:
                    innermost = o; key = (o, fr.f_code.co_name, fr.f_code.co_firstlineno)
                seen.add(o); depth += 1
            fr = fr.f_back
        over = t1 - t0 - INTERVAL
        overshoots.append(over)
        if depth <= 1 and f.f_lasti <= 10:
            entry_like[innermost] += 1   # sample landed on the very first bytecodes of a C->Python entry
            continue
        self_counts[innermost] += 1; funcs[key] += 1
        for o in seen:
            incl_counts[o] += 1
        sample_cost.append(perf() - t1)

if SAMPLER:
    th = threading.Thread(target=sampler, name='ts4prof-sampler', daemon=True); th.start()
FH = cfg.get('mode') == 'fh'
if FH:
    import faulthandler
    FH_PATH = os.path.join(HERE, 'fh_samples.txt')
    fh_file = open(FH_PATH, 'w')
    faulthandler.dump_traceback_later(INTERVAL, repeat=True, file=fh_file)

def parse_fh():
    import re
    faulthandler.cancel_dump_traceback_later(); fh_file.close()
    fmap = {r'E:\Builds\AuthorA\modA\__init__.py': 'fake_modA.ts4script', r'.\modB_v2\modB\__init__.py': 'fake_modB.ts4script'}
    main_hdr = 'Thread 0x%016x' % MAIN
    cnt = collections.Counter(); n = 0; py = 0
    txt = open(FH_PATH).read()
    for dump in txt.split('Timeout (')[1:]:
        n += 1
        for block in dump.split('Thread 0x')[1:]:
            if not ('Thread 0x' + block).startswith(main_hdr) and not ('Current thread 0x' in block):
                pass
            lines = block.splitlines()
            if int(lines[0].split()[0], 16) != MAIN:
                continue
            frames = [l for l in lines[1:] if l.strip().startswith('File ')]
            if not frames:
                continue
            fn = frames[0].split('"')[1]
            if fn == '<string>' and len(frames) == 1:
                continue
            py += 1; cnt[fmap.get(fn, 'game')] += 1
    print('faulthandler dumps=%d, main thread in python=%d (%.1f%%), file=%.1f MB' % (n, py, 100.0 * py / max(n, 1), os.path.getsize(FH_PATH) / 1e6))
    for o, c in cnt.most_common():
        print('   fh self %-24s %5d  %5.1f%%' % (o, c, 100.0 * c / max(py, 1)))

def finish(host_s):
    global stop
    stop = True
    time.sleep(0.05)
    n = len(tick_py); py_s = sum(tick_py)
    print('ticks=%d host_wall=%.3fs python_in_ticks=%.3fs (%.2f ms/tick) switchinterval=%.4f' % (n, host_s, py_s, 1000 * py_s / n, sys.getswitchinterval()))
    ta = truth['fake_modA.ts4script']; tb = truth['_tick_update_total']
    print('throughput: %.1f loop iterations per microsecond of python time (higher = less overhead)' % (ITERS[0] / (py_s * 1e6)))
    print('ground truth: modA=%.1f%%  update(modB wrapper + game) = %.1f%% of python time' % (100 * ta / py_s, 100 * tb / py_s))
    if FH:
        parse_fh()
    if not SAMPLER:
        sys.stdout.flush()
        return
    tot = sum(self_counts.values())
    print('samples kept=%d, dropped as C->Python entry artifacts=%s' % (tot, dict(entry_like)))
    for o, c in self_counts.most_common():
        print('   self  %-24s %5d  %5.1f%%   incl %5.1f%%' % (o, c, 100 * c / tot, 100 * incl_counts[o] / tot))
    for k, c in funcs.most_common(6):
        print('   func  %-60s %5d' % (k, c))
    ov = sorted(overshoots)
    print('sleep overshoot ms: p50=%.2f p90=%.2f max=%.2f ; per-sample python cost us: p50=%.1f p90=%.1f' % (
        1000 * ov[len(ov) // 2], 1000 * ov[int(len(ov) * .9)], 1000 * ov[-1],
        1e6 * sorted(sample_cost)[len(sample_cost) // 2], 1e6 * sorted(sample_cost)[int(len(sample_cost) * .9)]))
    sys.stdout.flush()

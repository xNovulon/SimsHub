# Runs inside the game's python37_x64.dll (host37.py). Tests faulthandler.dump_traceback_later as a
# "hitch catcher": armed at the start of every tick, cancelled at the end; if a tick overruns the budget the
# C watchdog thread (no GIL needed) writes the Python stacks of all threads to a file.
import sys, os, time, faulthandler, importlib
out = []
for m in ('threading', 'queue', 'cProfile', 'pstats', 'tracemalloc', 'faulthandler', 'ctypes', 'asyncio', 'sqlite3', 'json', 'socket'):
    try:
        importlib.import_module(m); out.append(m + ':ok')
    except Exception as e:
        out.append('%s:%s' % (m, type(e).__name__))
print('imports ->', ' '.join(out))
LOG = r'C:\Users\basim\Tools\sims4_speedkit\research\profiler\py37\hitch_dump.txt'
f = open(LOG, 'w')
perf = time.perf_counter
BUDGET = 0.050
n = [0]; arm_cost = []

def slow_mod_function(ms):          # stands in for a mod doing something expensive on one tick
    end = perf() + ms / 1000.0
    while perf() < end:
        pass

def tick():
    t0 = perf()
    faulthandler.dump_traceback_later(BUDGET, repeat=False, file=f, exit=False)
    arm_cost.append(perf() - t0)
    n[0] += 1
    slow_mod_function(120 if n[0] % 50 == 0 else 5)    # every 50th tick hitches for 120 ms
    t1 = perf()
    faulthandler.cancel_dump_traceback_later()
    arm_cost.append(perf() - t1)

def finish(host_s):
    f.flush()
    txt = open(LOG).read()
    arm_cost.sort()
    print('ticks', n[0], 'dumps written:', txt.count('most recent call first') // 1, 'arm/cancel cost us p50=%.0f p90=%.0f' % (
        1e6 * arm_cost[len(arm_cost) // 2], 1e6 * arm_cost[int(.9 * len(arm_cost))]))
    print(txt[:600])
    sys.stdout.flush()

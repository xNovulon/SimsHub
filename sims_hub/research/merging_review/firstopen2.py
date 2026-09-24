"""Re-test of 'first open of new package files is slow': fresh files under this folder only.
Pass 1 unbuffered (bypasses OS cache, so any extra cost is not disk cache), pass 2 unbuffered,
then a set of files renamed (same content, new name) and a set touched (content changed)."""
import os, sys, time, random, ctypes
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
from bench_pkgcount import write_package, read_unbuffered, k32
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
d = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fresh_%d' % int(time.time()))
os.makedirs(d)
rnd = random.Random(3)
for k in range(N):
    write_package(os.path.join(d, 'f%05d.package' % k),
                  [(0x034AEECB, 0x80000000, rnd.getrandbits(64), os.urandom(rnd.randint(500, 3000))) for _ in range(20)])
time.sleep(10)
buf = k32.VirtualAlloc(None, 64 << 20, 0x3000, 0x04)
files = sorted(os.path.join(d, x) for x in os.listdir(d))
for label in ('pass1 unbuffered', 'pass2 unbuffered', 'pass3 unbuffered'):
    t0 = time.perf_counter()
    for p in files:
        read_unbuffered(p, buf)
    dt = time.perf_counter() - t0
    print('%-18s %.3fs (%.2f ms/file)' % (label, dt, dt / N * 1000))
# rename half (content unchanged) -> is the cost tied to content or to path?
half = files[: N // 2]
ren = []
for p in half:
    q = p.replace('.package', '_r.package'); os.replace(p, q); ren.append(q)
time.sleep(3)
t0 = time.perf_counter()
for p in ren:
    read_unbuffered(p, buf)
dt = time.perf_counter() - t0
print('%-18s %.3fs (%.2f ms/file)' % ('renamed', dt, dt / len(ren) * 1000))

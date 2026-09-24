"""Synthetic files only, under research/merging_review2/fresh_*: first-open cost of new files
vs a second pass, plus the same files copied (new file, identical bytes) and one big file."""
import os, random, sys, time, shutil
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\merging')
from bench_pkgcount import write_package, read_buffered
HERE = os.path.dirname(os.path.abspath(__file__))
def passes(files, label):
    for p in ('1st', '2nd'):
        t0 = time.perf_counter()
        for f in files: read_buffered(f)
        dt = time.perf_counter() - t0
        print('%-28s %s pass %.3fs (%.2f ms/file)' % (label, p, dt, dt / len(files) * 1000))
n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
d = os.path.join(HERE, 'fresh_%d' % int(time.time())); os.makedirs(d)
rnd = random.Random(3)
for k in range(n):
    write_package(os.path.join(d, 'f%05d.package' % k), [(0x034AEECB, 0x80000000, rnd.getrandbits(64), os.urandom(rnd.randint(500, 3000))) for _ in range(20)])
big = os.path.join(d, 'big.package')
write_package(big, [(0x00B2D882, 0, rnd.getrandbits(64), os.urandom(1 << 20)) for _ in range(200)])
time.sleep(15)
files = sorted(os.path.join(d, x) for x in os.listdir(d) if x.startswith('f'))
passes(files, '%d new small files' % n)
passes([big], 'one new 200 MB file')
# rename test: same bytes, new name
d2 = d + '_renamed'; os.rename(d, d2)
files2 = [f.replace(d, d2) for f in files]
passes(files2, 'same files after dir rename')
d3 = d + '_copy'; shutil.copytree(d2, d3); time.sleep(10)
files3 = [f.replace(d, d3) for f in files]
passes(files3, 'byte-identical copies')

"""Is the first open of freshly written packages slow (antivirus on-access scan / cache flush)?

Writes N new small packages, waits for the lazy writer, then times a *buffered* first pass
(open + header + index, like a game launch right after a merge/install) and a second pass.
Synthetic files only, under research/merging/bench/fresh_<stamp>/.

    python bench_firstopen.py [n_files] [wait_seconds]
"""
import os
import random
import sys
import time

from bench_pkgcount import write_package, read_buffered, BENCH


def main(n=1000, wait=30):
    d = os.path.join(BENCH, 'fresh_%d' % int(time.time()))
    os.makedirs(d)
    rnd = random.Random(2)
    t0 = time.perf_counter()
    for k in range(n):
        res = [(0x034AEECB, 0x80000000, rnd.getrandbits(64), os.urandom(rnd.randint(500, 3000))) for _ in range(20)]
        write_package(os.path.join(d, 'f%05d.package' % k), res)
    print('wrote %d files in %.2fs; waiting %ds for the lazy writer' % (n, time.perf_counter() - t0, wait))
    time.sleep(wait)
    files = sorted(os.path.join(d, x) for x in os.listdir(d))
    for label in ('first pass', 'second pass', 'third pass'):
        t0 = time.perf_counter()
        for p in files:
            read_buffered(p)
        dt = time.perf_counter() - t0
        print('%-12s %.3fs  (%.2f ms/file)' % (label, dt, dt / n * 1000))


if __name__ == '__main__':
    main(*[int(x) for x in sys.argv[1:]])

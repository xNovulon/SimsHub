import time
p = time.perf_counter
for req in (0.001, 0.002, 0.005):
    d = []
    for i in range(40):
        t = p(); time.sleep(req); d.append(p() - t)
    d.sort()
    print('sleep(%.3f): p10=%.2fms p50=%.2fms p90=%.2fms' % (req, 1000*d[4], 1000*d[20], 1000*d[36]))
import sys; sys.stdout.flush()

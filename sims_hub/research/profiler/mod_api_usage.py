"""mod_api_usage.py: which functions in the user's script mods reference threading/profiling APIs (read-only)."""
import sys, os, zipfile, re
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from pyc37 import load, Code
R = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
PAT = re.compile(sys.argv[1] if len(sys.argv) > 1 else r'threading|_thread|start_new_thread|cProfile|Profile|Thread|Timer|setprofile|settrace|_current_frames|getswitchinterval|setswitchinterval')
paths = [os.path.join(R, 'Mods_parked', 'scripts', f) for f in os.listdir(os.path.join(R, 'Mods_parked', 'scripts')) if f.endswith('.ts4script')]
paths += [os.path.join(R, 'Mods', 'scripts', 'TURBODRIVER_WickedWhims_Scripts.ts4script')]
for p in paths:
    z = zipfile.ZipFile(p); b = os.path.basename(p)[:28]
    for n in z.namelist():
        if not n.endswith('.pyc'): continue
        c = load(z.read(n))
        def rec(c, q):
            h = sorted({s for s in c.co_names if PAT.fullmatch(s)})
            if h: print('%-28s %-60s %-50s %s' % (b, n, q or '<module>', h))
            for k in c.co_consts:
                if isinstance(k, Code): rec(k, (q + '.' if q else '') + k.co_name)
        rec(c, '')

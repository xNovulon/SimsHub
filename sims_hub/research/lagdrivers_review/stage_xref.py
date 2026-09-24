"""Read-only: find code that references the startup-stage name strings; print referencing instruction RVAs in string order."""
import sys
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\research\loadorder')
sys.argv = ['x', 'none']
import importlib.util
spec = importlib.util.spec_from_file_location('rx', r'C:\Users\basim\Tools\sims4_speedkit\research\loadorder\re_xref.py')
src = open(spec.origin).read().split("if __name__")[0]
g = {}; exec(compile(src, 're_xref', 'exec'), g)
names = {0x1def240:'ResourceSystem',0x1def3f8:'BeginBundlePreloads',0x1def4d0:'InitCacheBudget',0x1def568:'ModManagerService',0x1def5d8:'CompleteStage1',0x1def880:'PrefetchStart',0x1def8a0:'PreloadStart',0x1def8b0:'PreloadAllResources',0x1def8f8:'CompleteStage2',0x1def968:'Catalog',0x1def970:'InitLoad',0x1def980:'IncrementalLoad',0x1def990:'CompleteStage3',0x1defac8:'TuningPublishing',0x1defae0:'TuningLoaded',0x1defb60:'SimInfoSystem',0x1defbf8:'CompleteStage4'}
for off, nm in names.items():
    rva = g['off2rva'](off)
    hits = g['rip_refs'](rva)
    locs = sorted(set(g['T_RVA'] + i for i, k in hits))
    print(f'{nm:22s} rva={rva:#x} refs=' + ' '.join(f'{x:#x}' for x in locs[:6]))

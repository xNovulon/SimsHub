import sys, types, zipimport, os
# Run the GAME's own sims4.importer.utils.module_names_gen (from core.zip) against the user's ts4script files.
try:
    import sims4.log
    print('real sims4.log imported')
except Exception as e:
    print('sims4.log import failed:', type(e).__name__, e)
    s4 = types.ModuleType('sims4'); s4.__path__ = []
    log = types.ModuleType('sims4.log')
    class Logger:
        def __init__(self, *a, **k): pass
        def __getattr__(self, n): return lambda *a, **k: print('LOG', n, a)
    log.Logger = Logger; s4.log = log
    sys.modules['sims4'] = s4; sys.modules['sims4.log'] = log
    sys.modules['paths'] = types.ModuleType('paths')
zi = zipimport.zipimporter(r'E:\The Sims 4\Data\Simulation\Gameplay\core.zip\sims4\importer')
code = zi.get_code('utils')
g = {'__name__': 'sims4.importer.utils_under_test'}
exec(code, g)
S = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
for p in [S + r'\Mods_parked\scripts\Cumshine.ts4script', S + r'\Mods_parked\scripts\mc_career.ts4script',
          S + r'\Mods_parked\scripts\LittleMsSam_LiveInServices.ts4script', r'C:\Users\basim\Tools\sims4_speedkit\research\profiler\py37\synthetic_test.ts4script']:
    print(os.path.basename(p), '->', list(g['module_names_gen'](p)))
sys.stdout.flush()

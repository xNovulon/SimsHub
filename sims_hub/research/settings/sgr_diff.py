"""Diff the active ConfigOverride GraphicsRules.sgr against the stock rules (GraphicsRules.sgr + Ts4CommonRules.sgr).
Read-only. Usage: python sgr_diff.py"""
import re, sys
STOCK = [r'E:\The Sims 4\Game\Bin\Ts4CommonRules.sgr', r'E:\The Sims 4\Game\Bin\GraphicsRules.sgr']
OVR = [r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\ConfigOverride\GraphicsRules.sgr']
def parse(paths):
    props = {}; setopts = {}; options = set()
    for p in paths:
        opt = None; setting = None
        for raw in open(p, encoding='utf-8', errors='replace'):
            line = raw.split('#')[0].strip() if not raw.lstrip().startswith('#<') else ''
            if not line: continue
            t = line.split()
            if t[0] == 'option': opt = t[1]; setting = None; options.add(opt); continue
            if t[0] == 'end': opt = None; setting = None; continue
            if t[0] in ('setting', 'integer') and opt: setting = ' '.join(t[1:]); continue
            if t[0] == 'prop' and opt:
                props[(opt, setting, t[2])] = ' '.join(t[3:]); continue
            if t[0] == 'setProp':
                props[('<global>', None, t[2])] = ' '.join(t[3:]); continue
            if t[0] == 'setOption':
                setopts.setdefault(t[1], []).append(' '.join(t[2:]))
    return props, setopts, options
sp, ss, so = parse(STOCK); op, os_, oo = parse(OVR)
print('# options only in stock (not defined by override):', sorted(so - oo))
print('# options only in override:', sorted(oo - so))
print('# prop differences (option, setting, prop): stock -> override')
for k in sorted(set(sp) | set(op), key=lambda k: (k[0], str(k[1]), k[2])):
    a, b = sp.get(k), op.get(k)
    if a != b and k[0] in (oo | {'<global>'}):
        print(f'{k[0]:22} {str(k[1]):16} {k[2]:34} {str(a):40} -> {b}')

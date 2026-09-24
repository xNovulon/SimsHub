import sys, zipimport, zipfile, marshal, importlib.util, time, os
R = r'C:\Users\basim\Tools\sims4_speedkit\research\profiler\py37'
out = []
# 1) build a synthetic .ts4script with: a .py source module, a .pyc compiled with a fake author path, a package
z = os.path.join(R, 'synthetic_test.ts4script')
src_py = "X = 'from source'\n"
code = compile("def f():\n    return 1\nY = 'from pyc'\n", r'E:\Builds\SomeAuthor\mymod\pycmod.py', 'exec')
pyc = importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(code)
with zipfile.ZipFile(z, 'w') as zz:
    zz.writestr('srcmod.py', src_py)
    zz.writestr('pycmod.pyc', pyc)
    zz.writestr('pkg_a/__init__.pyc', importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(compile('', 'C:\dev\pkg_a\__init__.py', 'exec')))
    zz.writestr('pkg_a/sub.pyc', importlib.util.MAGIC_NUMBER + b'\0' * 12 + marshal.dumps(compile('def g(): pass', '.\v1\pkg_a\sub.py', 'exec')))
print('MAGIC', importlib.util.MAGIC_NUMBER.hex())
sys.path.append(z)
import srcmod, pycmod, pkg_a.sub
for m in (srcmod, pycmod, pkg_a, pkg_a.sub):
    print(m.__name__, '| __file__ =', m.__file__, '| loader =', type(m.__loader__).__name__, '| __spec__.origin =', m.__spec__.origin if m.__spec__ else None)
print('srcmod.X =', srcmod.X)
print('pycmod.f.__code__.co_filename =', pycmod.f.__code__.co_filename)
print('pkg_a.sub.g.__code__.co_filename =', pkg_a.sub.g.__code__.co_filename)
# 2) the real Cumshine.ts4script: can zipimport find & compile its .py source (without executing it)?
cz = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\Mods_parked\scripts\Cumshine.ts4script'
zi = zipimport.zipimporter(cz)
c = zi.get_code('Spent_Cumshine')
print('Cumshine get_code ->', type(c).__name__, 'co_filename =', c.co_filename, '| get_filename =', zi.get_filename('Spent_Cumshine'))
sys.stdout.flush()

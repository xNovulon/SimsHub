"""ea_cofilename.py: co_filename patterns of EA's own code (to tell game frames from mod frames in external samples)."""
import sys, os, zipfile, collections
sys.path.insert(0, r'C:\Users\basim\Tools\sims4_speedkit\tools')
from pyc37 import load
GP = r'E:\The Sims 4\Data\Simulation\Gameplay'
zips = [os.path.join(GP, z) for z in ('base.zip', 'core.zip', 'simulation.zip')] + [r'E:\The Sims 4\Game\Bin\Python\generated.zip']
for zp in zips:
    z = zipfile.ZipFile(zp)
    pref = collections.Counter(); ex = []
    for n in z.namelist():
        if n.endswith('.pyc'):
            f = load(z.read(n)).co_filename
            d = f.replace('/', '\\').rsplit('\\', 1)[0]
            pref[d.split('\\')[0] + '\\' + '\\'.join(d.split('\\')[1:4])] += 1
            if len(ex) < 2:
                ex.append((n, f))
    print(os.path.basename(zp), ex)
    print('    ', pref.most_common(5))

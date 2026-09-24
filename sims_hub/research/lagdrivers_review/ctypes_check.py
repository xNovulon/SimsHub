import zipfile, os
d = r'E:\The Sims 4\Data\Simulation\Gameplay'
for z in ('base.zip', 'core.zip', 'simulation.zip'):
    n = zipfile.ZipFile(os.path.join(d, z)).namelist()
    print(z, [x for x in n if 'ctypes' in x.lower()][:6])

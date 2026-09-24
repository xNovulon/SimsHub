import os, sqlite3
SIMS = r'C:\Users\basim\Documents\Electronic Arts\The Sims 4'
DB = r'file:C:\Users\basim\Tools\sims4_speedkit\data\library.sqlite?mode=ro'
def db():
    return sqlite3.connect(DB, uri=True)
def path(root, rel, size=None):
    for r in (root, 'Mods', 'Mods_parked'):
        p = os.path.join(SIMS, r, rel.replace('/', os.sep))
        if os.path.exists(p) and (size is None or os.path.getsize(p) == size):
            return p
    return None

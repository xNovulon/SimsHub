import re, sys
path = sys.argv[1] if len(sys.argv) > 1 else r'E:\The Sims 4\Game\Bin\TS4_x64.exe'
d = open(path, 'rb').read()
BS = chr(92)
words = sys.argv[2:] or ['Priority', 'Select', 'End', 'StopScan', 'Include', 'DirectoryFiles', 'autoupdate',
                         '...', '.../', 'Resource.cfg', 'ModsDisabled', 'Mods' + BS, 'Group', 'FileType']
for w in words:
    for enc in ['A', 'W']:
        pat = w.encode() + b'\x00' if enc == 'A' else w.encode('utf-16le') + b'\x00\x00'
        hits = [m.start() for m in re.finditer(re.escape(pat), d)]
        exact = [h for h in hits if h == 0 or d[h - 1] == 0]
        print(repr(w), enc, 'exact:', [hex(h) for h in exact[:12]])

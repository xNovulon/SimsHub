"""Read-only: count EA .package files and their index entries by category."""
import os, struct, collections, re
root = r'E:\The Sims 4'
cats = collections.Counter(); ents = collections.Counter(); biggest = []
for dp, dn, fn in os.walk(root):
    for f in fn:
        if not f.lower().endswith('.package'):
            continue
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, root).lower()
        if re.match(r'strings_(?!eng_us)', f.lower()):
            c = 'strings_other_lang'
        elif f.lower().startswith('strings_'):
            c = 'strings_eng_us'
        elif 'delta' in rel.split(os.sep):
            c = 'delta'
        elif '__installer' in rel:
            c = 'installer'
        else:
            c = 'other'
        try:
            with open(p, 'rb') as fh:
                h = fh.read(96)
            n = struct.unpack_from('<I', h, 36)[0] if h[:4] == b'DBPF' else 0
        except OSError:
            n = 0
        cats[c] += 1; ents[c] += n
        biggest.append((os.path.getsize(p), rel))
print('files', sum(cats.values()), dict(cats))
print('entries', sum(ents.values()), dict(ents))
biggest.sort(reverse=True)
print(biggest[:3]); print('over 2^31-1:', sum(1 for s, _ in biggest if s > 0x7FFFFFFF))

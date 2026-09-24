"""Cross-check the schema-less walk against a real schema parse (game's own .proto descriptors) for one save:
outfit/genetic CAS part ids, skin tones, sculpts, modifiers and zone object definition ids."""
import collections, os, sqlite3, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usedcc as U, protos

name = sys.argv[1] if len(sys.argv) > 1 else 'Slot_00000018.save'
path = os.path.join(U.SAVES, name)
SGD = protos.msg('EA.Sims4.Persistence.SaveGameData')
ZOD = protos.msg('EA.Sims4.Persistence.ZoneObjectData')
FAC = protos.msg('EA.Sims4.Persistence.BlobSimFacialCustomizationData')
sch = collections.defaultdict(set)
with open(path, 'rb') as f:
    for t, g, i, off, fs, ms, comp in U.read_index(path):
        if t not in (0x0D, 0x06):
            continue
        f.seek(off)
        d = U.decode(f.read(fs), comp)
        if t == 0x0D:
            s = SGD(); s.ParseFromString(d)
            for sim in list(s.sims) + list(s.mannequins):
                for o in sim.outfits.outfits:
                    sch['outfit_part'].update(o.parts.ids)
                sch['skin_tone'].add(sim.skin_tone)
                fa = FAC()
                fa.ParseFromString(sim.facial_attr if hasattr(sim, 'facial_attr') else sim.facial_attributes)
                sch['sculpt'].update(fa.sculpts)
                for m in list(fa.face_modifiers) + list(fa.aged_face_modifiers):
                    sch['face_modifier'].add(m.key)
                for m in list(fa.body_modifiers) + list(fa.aged_body_modifiers):
                    sch['body_modifier'].add(m.key)
            for sim in s.sims:
                for p in list(sim.genetic_data.parts_list.parts) + list(sim.genetic_data.growth_parts_list.parts):
                    sch['genetic_part'].add(p.id)
        else:
            z = ZOD(); z.ParseFromString(d)
            for ol in z.objects:
                for o in ol.objects:
                    sch['zone_object_guid'].add(o.guid)
ids = sqlite3.connect(os.path.join(U.HERE, 'ids.sqlite'))
sid = ids.execute('select id from src where file=?', (path,)).fetchone()[0]
gen = collections.defaultdict(set)
for cat, v in ids.execute('select cat, v from typed where src=?', (sid,)):
    gen[cat].add(U.u64(v))
zone = set(U.u64(v) for (v,) in ids.execute("select v from hit where src=? and path like 'R6.3.1.30'", (sid,)))
for cat in ('outfit_part', 'genetic_part', 'skin_tone', 'sculpt', 'face_modifier', 'body_modifier'):
    a, b = sch[cat], gen[cat]
    print('%-14s schema=%5d generic=%5d  schema-not-generic=%d  generic-not-schema=%d' % (cat, len(a), len(b), len(a - b), len(b - a)))
zg = sch['zone_object_guid']
print('zone objects: schema distinct guids=%d; of these in generic object_guid set: %d; library hits on R6.3.1.30: %d (schema has %d of them)'
      % (len(zg), len(zg & gen['object_guid']), len(zone), len(zone & zg)))

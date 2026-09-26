"""The Sims 4 Tray (saved households / gallery library) reader.

Files in Documents/Electronic Arts/The Sims 4/Tray are named  0x<group>!0x<instance>.<ext>:

  .trayitem        u32 0, u32 length, protobuf EA.Sims4.Network.TrayMetadata (name, creator, per-sim summary)
  .householdbinary u32 version; v2+: u32 bytes-after-this, u32 0, u32 length, protobuf EA.Sims4.Network.FamilyData,
                   then u8 1 + u32 count + custom-texture blobs (PNG); v0/v1: u32 length, FamilyData
  .hhi / .sgi      u32 length, u32 0, 16 bytes (8efc24489b780e3c 02000000 00000000), then a JPEG XOR-ed with a
                   repeating 8-byte key (41 25 e6 cd 47 ba b2 1a; recovered from the JFIF header, so any key works)
                   .hhi = household picture (group ....02 small, ....03 large), .sgi = one sim, instance = sim id
  .blueprint/.bpi/.room/.rmi  lots and rooms (not used here)

The protobuf schemas are the game's own: every protocolbuffers/*_pb2.pyc in <game>/Game/Bin/Python/generated.zip
holds its serialized FileDescriptorProto as a constant. They are extracted once (a tiny Python 3.7 marshal reader
lives below), stored as a FileDescriptorSet in cache/tray/protos.bin and loaded into a private descriptor pool.
"""
import glob, io, os, re, struct, threading, time, zipfile

from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from gamefind import HOME, SIMS_DIR
TRAY_DIR = os.path.join(SIMS_DIR, 'Tray')
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, '..', 'cache', 'tray')

AGES = {1: 'baby', 128: 'infant', 2: 'toddler', 4: 'child', 8: 'teen', 16: 'youngadult', 32: 'adult', 64: 'elder'}
GENDERS = {4096: 'male', 8192: 'female'}
SPECIES = {0: 'human', 1: 'human', 2: 'dog', 3: 'cat', 4: 'smalldog', 5: 'fox', 6: 'horse'}
# sims/outfits/outfit_enums.pyc
OUTFIT_CATEGORIES = {-1: 'CURRENT_OUTFIT', 0: 'EVERYDAY', 1: 'FORMAL', 2: 'ATHLETIC', 3: 'SLEEP', 4: 'PARTY', 5: 'BATHING',
                     6: 'CAREER', 7: 'SITUATION', 8: 'SPECIAL', 9: 'SWIMWEAR', 10: 'HOTWEATHER', 11: 'COLDWEATHER',
                     12: 'BATUU', 13: 'SMALL_BUSINESS'}
BODY_TYPES = dict(enumerate(
    'NONE HAT HAIR HEAD TEETH FULL_BODY UPPER_BODY LOWER_BODY SHOES CUMMERBUND EARRINGS GLASSES NECKLACE GLOVES '
    'WRIST_LEFT WRIST_RIGHT LIP_RING_LEFT LIP_RING_RIGHT NOSE_RING_LEFT NOSE_RING_RIGHT BROW_RING_LEFT BROW_RING_RIGHT '
    'INDEX_FINGER_LEFT INDEX_FINGER_RIGHT RING_FINGER_LEFT RING_FINGER_RIGHT MIDDLE_FINGER_LEFT MIDDLE_FINGER_RIGHT '
    'FACIAL_HAIR LIPS_TICK EYE_SHADOW EYE_LINER BLUSH FACEPAINT EYEBROWS EYECOLOR SOCKS EYELASHES '
    'SKINDETAIL_CREASE_FOREHEAD SKINDETAIL_FRECKLES SKINDETAIL_DIMPLE_LEFT SKINDETAIL_DIMPLE_RIGHT TIGHTS '
    'SKINDETAIL_MOLE_LIP_LEFT SKINDETAIL_MOLE_LIP_RIGHT TATTOO_ARM_LOWER_LEFT TATTOO_ARM_UPPER_LEFT '
    'TATTOO_ARM_LOWER_RIGHT TATTOO_ARM_UPPER_RIGHT TATTOO_LEG_LEFT TATTOO_LEG_RIGHT TATTOO_TORSO_BACK_LOWER '
    'TATTOO_TORSO_BACK_UPPER TATTOO_TORSO_FRONT_LOWER TATTOO_TORSO_FRONT_UPPER SKINDETAIL_MOLE_CHEEK_LEFT '
    'SKINDETAIL_MOLE_CHEEK_RIGHT SKINDETAIL_CREASE_MOUTH SKIN_OVERLAY FUR_BODY EARS TAIL SKINDETAIL_NOSE_COLOR '
    'EYECOLOR_SECONDARY OCCULT_BROW OCCULT_EYE_SOCKET OCCULT_EYE_LID OCCULT_MOUTH OCCULT_LEFT_CHEEK OCCULT_RIGHT_CHEEK '
    'OCCULT_NECK_SCAR FOREARM_SCAR ACNE FINGERNAIL TOENAIL HAIRCOLOR_OVERRIDE BITE BODYFRECKLES BODYHAIR_ARM '
    'BODYHAIR_LEG BODYHAIR_TORSOFRONT BODYHAIR_TORSOBACK BODYSCAR_ARMLEFT BODYSCAR_ARMRIGHT BODYSCAR_TORSOFRONT '
    'BODYSCAR_TORSOBACK BODYSCAR_LEGLEFT BODYSCAR_LEGRIGHT ATTACHMENT_BACK SKINDETAIL_ACNE_PUBERTY SCARFACE '
    'BIRTHMARKFACE BIRTHMARKTORSOBACK BIRTHMARKTORSOFRONT BIRTHMARKARMS MOLEFACE MOLECHESTUPPER MOLEBACKUPPER '
    'BIRTHMARKLEGS STRETCHMARKS_FRONT STRETCHMARKS_BACK SADDLE BRIDLE REINS BLANKET SKINDETAIL_HOOF_COLOR HAIR_MANE '
    'HAIR_TAIL HAIR_FORELOCK HAIR_FEATHERS HORN TAIL_BASE BIRTHMARKOCCULT TATTOO_HEAD WINGS HEADDECO SKINSPECULARITY '
    'BASE_LAYER UNUSED'.split()))
# SimData.physique is "heavy,fit,lean,bony,pregnant,hips_wide,hips_narrow,waist_wide,waist_narrow," (BODYBLENDTYPE order)
PHYSIQUE_KEYS = ['heavy', 'fit', 'lean', 'bony', 'pregnant', 'hips_wide', 'hips_narrow', 'waist_wide', 'waist_narrow']
TRAIT_FRAME_MASCULINE, TRAIT_FRAME_FEMININE = 136877, 136878
TRAIT_BREASTS_FORCE_OFF, TRAIT_BREASTS_FORCE_ON = 136862, 136863
TRAIT_PREGNANT = 16854
TRAY_EPOCH = 62135596800          # item_timestamp counts seconds from 0001-01-01


def hexid(v):
    return '0x%016x' % (v & 0xFFFFFFFFFFFFFFFF)


def to_int(v):
    """'0x..' / decimal string / int -> int (64-bit ids travel as hex strings so JavaScript keeps them exact)."""
    if isinstance(v, int):
        return v
    s = str(v).strip()
    return int(s, 16) if s.lower().startswith('0x') else int(s)


# ------------------------------------------------------------------ protobuf schemas from the game
class _Marshal37:
    """Just enough of the Python 3.7 marshal format to reach a module's constants."""

    def __init__(self, data):
        self.d, self.p, self.refs = data, 0, []

    def _i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def _raw(self, n):
        v = self.d[self.p:self.p + n]; self.p += n; return v

    def obj(self):
        code = self.d[self.p]; self.p += 1
        flag, t = code & 0x80, chr(code & 0x7F)
        idx = None
        if flag:
            idx = len(self.refs); self.refs.append(None)
        if t in '0NFTS.':
            v = {'0': None, 'N': None, 'F': False, 'T': True, 'S': None, '.': Ellipsis}[t]
        elif t == 'i':
            v = self._i32()
        elif t == 'l':
            n = self._i32(); v = 0
            for k in range(abs(n)):
                v |= struct.unpack_from('<H', self.d, self.p + 2 * k)[0] << (15 * k)
            self.p += 2 * abs(n); v = -v if n < 0 else v
        elif t == 'g':
            v = struct.unpack_from('<d', self.d, self.p)[0]; self.p += 8
        elif t == 'y':
            self.p += 16; v = 0j
        elif t == 's':
            v = self._raw(self._i32())
        elif t in 'tuaA':
            v = self._raw(self._i32()).decode('utf-8', 'surrogatepass')
        elif t in 'zZ':
            n = self.d[self.p]; self.p += 1; v = self._raw(n).decode('latin-1')
        elif t in '([<>':
            v = tuple(self.obj() for _ in range(self._i32()))
        elif t == ')':
            n = self.d[self.p]; self.p += 1; v = tuple(self.obj() for _ in range(n))
        elif t == '{':
            v = {}
            while self.d[self.p] != ord('0'):
                k = self.obj(); v[repr(k)] = self.obj()
            self.p += 1
        elif t == 'c':
            v = {}
            if idx is not None:
                self.refs[idx] = v
            self.p += 20
            for name in ('code', 'consts', 'names', 'varnames', 'freevars', 'cellvars', 'filename', 'name'):
                v[name] = self.obj()
            self.p += 4
            v['lnotab'] = self.obj()
        elif t == 'r':
            v = self.refs[self._i32()]
        else:
            raise ValueError('marshal type %r at %d' % (t, self.p))
        if idx is not None and t != 'c':
            self.refs[idx] = v
        return v


def _descriptor_from_pyc(pyc):
    """serialized_pb of a generated *_pb2 module (a str constant starting with field 1 = file name)."""
    code = _Marshal37(pyc[16:]).obj()
    for k in code['consts']:
        if isinstance(k, (str, bytes)) and len(k) > 4 and k[:1] in ('\n', b'\n') and '.proto' in str(k[:120]):
            raw = k.encode('latin-1') if isinstance(k, str) else k
            fd = descriptor_pb2.FileDescriptorProto()
            fd.ParseFromString(raw)
            return fd
    return None


def _generated_zip():
    import gamedata
    return os.path.join(gamedata.game_dir(), 'Game', 'Bin', 'Python', 'generated.zip')


def _load_descriptor_set():
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, 'protos.bin')
    src = None
    try:
        src = _generated_zip()
    except Exception:
        pass
    if os.path.exists(path) and (src is None or not os.path.exists(src) or os.path.getmtime(path) >= os.path.getmtime(src)):
        fds = descriptor_pb2.FileDescriptorSet()
        with open(path, 'rb') as f:
            fds.ParseFromString(f.read())
        return fds
    if not src or not os.path.exists(src):
        raise FileNotFoundError('generated.zip (game protobuf schemas) not found: %s' % src)
    fds = descriptor_pb2.FileDescriptorSet()
    with zipfile.ZipFile(src) as z:
        for n in sorted(z.namelist()):
            if n.endswith('_pb2.pyc'):
                fd = _descriptor_from_pyc(z.read(n))
                if fd is not None:
                    fds.file.append(fd)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(fds.SerializeToString())
    os.replace(tmp, path)
    return fds


class _Protos:
    _lock = threading.Lock()
    _pool = None
    _classes = {}

    @classmethod
    def cls(cls, full_name):
        with cls._lock:
            if cls._pool is None:
                fds = _load_descriptor_set()
                pool = descriptor_pool.DescriptorPool()
                pool.Add(descriptor_pb2.FileDescriptorProto.FromString(descriptor_pb2.DESCRIPTOR.serialized_pb))
                by_name = {f.name: f for f in fds.file}
                done = {'google/protobuf/descriptor.proto'}

                def add(name):
                    if name in done or name not in by_name:
                        return
                    done.add(name)
                    for dep in by_name[name].dependency:
                        add(dep)
                    pool.Add(by_name[name])
                for name in by_name:
                    add(name)
                cls._pool = pool
            if full_name not in cls._classes:
                cls._classes[full_name] = message_factory.GetMessageClass(cls._pool.FindMessageTypeByName(full_name))
            return cls._classes[full_name]


def message(full_name, data=None):
    """A game protobuf message, e.g. message('EA.Sims4.Persistence.SimData', raw_bytes)."""
    m = _Protos.cls(full_name)()
    if data is not None:
        m.ParseFromString(data)
    return m


# ------------------------------------------------------------------ files
_NAME = re.compile(r'^0x([0-9a-fA-F]{1,8})!0x([0-9a-fA-F]{1,16})\.([A-Za-z]+)$')


def _tray_files():
    """{(ext, instance): [(group, path)]} for every tray file."""
    out = {}
    try:
        names = os.listdir(TRAY_DIR)
    except FileNotFoundError:
        return out
    for n in names:
        m = _NAME.match(n)
        if m:
            out.setdefault((m.group(3).lower(), int(m.group(2), 16)), []).append((int(m.group(1), 16), os.path.join(TRAY_DIR, n)))
    return out


def _read_trayitem(path):
    with open(path, 'rb') as f:
        d = f.read()
    n = struct.unpack_from('<I', d, 4)[0]
    return message('EA.Sims4.Network.TrayMetadata', d[8:8 + n] if 8 + n <= len(d) else d[8:])


def _read_family(path):
    with open(path, 'rb') as f:
        d = f.read()
    version = struct.unpack_from('<I', d, 0)[0]
    if version >= 2:
        n = struct.unpack_from('<I', d, 12)[0]; body = d[16:16 + n]
    else:
        n = struct.unpack_from('<I', d, 4)[0]; body = d[8:8 + n]
    return message('EA.Sims4.Network.FamilyData', body), version


def decode_tray_image(data):
    """.hhi/.sgi/.bpi/.rmi -> JPEG bytes (the XOR key is recovered from the fixed JFIF header)."""
    body = data[24:]
    if body[:3] == b'\xff\xd8\xff':
        jpg = body
    else:
        key = bytes(a ^ b for a, b in zip(body[:8], b'\xff\xd8\xff\xe0\x00\x10JF'))
        k8 = (key * (len(body) // 8 + 1))[:len(body)]
        jpg = (int.from_bytes(body, 'little') ^ int.from_bytes(k8, 'little')).to_bytes(len(body), 'little')
    return _trim_jpeg(jpg)


def _trim_jpeg(j):
    """Cut anything after the JPEG end-of-image marker (the game appends extra data)."""
    p = 2
    try:
        while p + 4 <= len(j):
            if j[p] != 0xFF:
                return j
            marker = j[p + 1]
            if marker == 0xD9:
                return j[:p + 2]
            if marker == 0xDA:                                  # entropy-coded data: scan for the next real marker
                p += 2 + struct.unpack_from('>H', j, p + 2)[0]
                while p + 1 < len(j):
                    if j[p] == 0xFF and j[p + 1] not in (0x00, 0xFF) and not 0xD0 <= j[p + 1] <= 0xD7:
                        break
                    p += 1
                continue
            p += 2 + struct.unpack_from('>H', j, p + 2)[0]
    except struct.error:
        pass
    return j


# ------------------------------------------------------------------ public API
def list_households():
    """Every saved household: [{id, name, description, creator, family_size, sims: [...], modified, thumbs}] newest first."""
    files = _tray_files()
    out = []
    for (ext, inst), entries in files.items():
        if ext != 'trayitem':
            continue
        path = entries[0][1]
        try:
            tm = _read_trayitem(path)
        except Exception:
            continue
        if tm.type != 1:                                        # EXCHANGE_HOUSEHOLD (2 = lot, 3 = room)
            continue
        hh = tm.metadata.hh_metadata
        sims = []
        for s in hh.sim_data:
            sims.append({'sim_id': hexid(s.id), 'first': s.first_name, 'last': s.last_name,
                         'age': AGES.get(s.age, s.age), 'gender': GENDERS.get(s.gender, s.gender),
                         'species': SPECIES.get(s.species, s.species),
                         'thumb_key': hexid(s.id) if ('sgi', s.id) in files else None})
        ts = tm.item_timestamp - TRAY_EPOCH if tm.item_timestamp > TRAY_EPOCH else os.path.getmtime(path)
        out.append({'id': hexid(inst), 'name': tm.name, 'description': tm.description, 'creator': tm.creator_name,
                    'family_size': hh.family_size or len(sims), 'sims': sims, 'modified': int(ts),
                    'modded': bool(tm.metadata.is_modded_content),
                    'has_binary': ('householdbinary', inst) in files,
                    'thumbs': sorted('0x%08x' % g for g, _ in files.get(('hhi', inst), []))})
    out.sort(key=lambda h: -h['modified'])
    return out


def _physique(s):
    vals = []
    for x in s.split(','):
        x = x.strip()
        if x:
            try:
                vals.append(float(x))
            except ValueError:
                vals.append(0.0)
    vals += [0.0] * (len(PHYSIQUE_KEYS) - len(vals))
    return dict(zip(PHYSIQUE_KEYS, vals)), vals


def _modifiers(lst):
    return [{'modifier_instance': hexid(m.key), 'value': round(m.amount, 6)} for m in lst]


def _outfits(outfit_list):
    out, seen = [], {}
    for o in outfit_list.outfits:
        idx = seen.get(o.category, 0); seen[o.category] = idx + 1
        ids, bts = list(o.parts.ids), list(o.body_types_list.body_types)
        shifts = list(o.part_shifts.color_shift) if o.HasField('part_shifts') else []
        parts = []
        for k, inst in enumerate(ids):
            bt = bts[k] if k < len(bts) else 0
            p = {'casp_instance': hexid(inst), 'body_type': bt, 'body_type_name': BODY_TYPES.get(bt, str(bt))}
            if k < len(shifts) and shifts[k] != 0x4000000000000000:
                p['color_shift'] = hexid(shifts[k])
            parts.append(p)
        out.append({'category': OUTFIT_CATEGORIES.get(o.category, str(o.category)), 'category_id': o.category,
                    'index': idx, 'outfit_id': hexid(o.outfit_id), 'parts': parts})
    return out


def _sim_dict(s, files):
    blob = message('EA.Sims4.Persistence.BlobSimFacialCustomizationData', s.facial_attr)
    phys, raw = _physique(s.physique)
    traits = [int(t) for t in s.attributes.trait_tracker.trait_ids] if s.HasField('attributes') else []
    species = s.extended_species or 1
    return {
        'sim_id': hexid(s.sim_id), 'first': s.first_name, 'last': s.last_name,
        'age': AGES.get(s.age, s.age), 'age_id': s.age, 'gender': GENDERS.get(s.gender, s.gender), 'gender_id': s.gender,
        'species': SPECIES.get(species, species), 'species_id': species,
        'skin_tone': hexid(s.skin_tone), 'skin_tone_shift': round(s.skin_tone_val_shift, 6),
        'physique': phys, 'physique_raw': raw,
        'face_modifiers': _modifiers(blob.face_modifiers), 'body_modifiers': _modifiers(blob.body_modifiers),
        'aged_face_modifiers': _modifiers(blob.aged_face_modifiers), 'aged_body_modifiers': _modifiers(blob.aged_body_modifiers),
        'sculpts': [hexid(x) for x in blob.sculpts],
        'traits': traits,
        'frame': ('masculine' if TRAIT_FRAME_MASCULINE in traits else 'feminine' if TRAIT_FRAME_FEMININE in traits
                  else ('masculine' if s.gender == 4096 else 'feminine')),
        'breasts': (False if TRAIT_BREASTS_FORCE_OFF in traits else True if TRAIT_BREASTS_FORCE_ON in traits else None),
        'pregnant': TRAIT_PREGNANT in traits or s.pregnancy_progress > 0,
        'pregnancy_progress': round(s.pregnancy_progress, 4),
        'voice_pitch': round(s.voice_pitch, 4), 'voice_actor': s.voice_actor,
        'outfits': _outfits(s.outfits),
        'current_outfit': {'category': OUTFIT_CATEGORIES.get(s.current_outfit_type, str(s.current_outfit_type)),
                           'category_id': s.current_outfit_type, 'index': s.current_outfit_index},
        'has_thumb': ('sgi', s.sim_id) in files,
    }


_fam_cache = {}


def _family(tray_id):
    inst = to_int(tray_id)
    files = _tray_files()
    entries = files.get(('householdbinary', inst))
    if not entries:
        raise KeyError('no householdbinary for tray id %s' % hexid(inst))
    path = entries[0][1]
    key = (path, os.path.getmtime(path), os.path.getsize(path))
    hit = _fam_cache.get(inst)
    if hit and hit[0] == key:
        return hit[1], hit[2], files
    fam, version = _read_family(path)
    _fam_cache[inst] = (key, fam, version)
    return fam, version, files


def household_sims(tray_id, thumbnails=False):
    """Full sim data of one saved household (see module doc for the file format).

    Returns {id, name, description, money, sims: [...]} (+ 'thumbnails': {sim_id: jpeg bytes} when asked).
    Each sim: names, age/gender/species, skin_tone (TONE instance), physique {heavy, fit, lean, bony, ...},
    face_modifiers/body_modifiers [{modifier_instance, value}] (SimModifier 0xC5F6763E instances), sculpts
    (Sculpt 0x9D1AB874 instances), traits, frame, outfits [{category, index, parts: [{casp_instance, body_type}]}].
    64-bit ids are '0x%016x' strings.
    """
    fam, version, files = _family(tray_id)
    fa = fam.family_account
    out = {'id': hexid(to_int(tray_id)), 'name': fa.familyname, 'description': fa.description, 'money': fa.money,
           'creator': fa.original_creator_string, 'format_version': version,
           'sims': [_sim_dict(s, files) for s in fa.sim]}
    if thumbnails:
        out['thumbnails'] = {s['sim_id']: sim_thumbnail(s['sim_id']) for s in out['sims'] if s['has_thumb']}
    return out


def sim_data_message(tray_id, sim_index):
    """The raw EA.Sims4.Persistence.SimData protobuf message (for anything not flattened above)."""
    fam, _, _ = _family(tray_id)
    return fam.family_account.sim[sim_index]


def with_alpha(jpg):
    """A Tray picture with its own transparency: the game keeps a grey PNG mask in the JPEG's 'ALFA' segment (without
    it the blurred, zoomed render behind the sim shows). -> PNG bytes (RGBA), or the JPEG as it is when there is no
    mask or it can't be read."""
    i = jpg.find(b'ALFA', 0, 64)
    if i < 0:
        return jpg
    try:
        from PIL import Image
        n = struct.unpack_from('>I', jpg, i + 4)[0]
        mask = Image.open(io.BytesIO(jpg[i + 8:i + 8 + n])).convert('L')
        im = Image.open(io.BytesIO(jpg)).convert('RGB')
        if mask.size != im.size:
            mask = mask.resize(im.size, Image.BILINEAR)
        im.putalpha(mask)
        out = io.BytesIO()
        im.save(out, 'PNG', optimize=False)
        return out.getvalue()
    except Exception:
        return jpg


def sim_thumbnail(sim_id):
    """Picture bytes of a sim's gallery picture (.sgi): PNG with its transparency (with_alpha), or JPEG; None if none."""
    entries = _tray_files().get(('sgi', to_int(sim_id)))
    if not entries:
        return None
    with open(sorted(entries)[0][1], 'rb') as f:
        return with_alpha(decode_tray_image(f.read()))


def household_thumbnail(tray_id, large=True):
    """JPEG bytes of the household picture (.hhi; group ....03 is the large one), or None."""
    entries = sorted(_tray_files().get(('hhi', to_int(tray_id)), []))
    if not entries:
        return None
    pick = [p for g, p in entries if (g & 0xFF) == (3 if large else 2)] or [p for g, p in entries]
    with open(pick[0], 'rb') as f:
        return decode_tray_image(f.read())


# body types a nude (BATHING) outfit keeps from the sim's everyday look; everything else is clothing/accessory/makeup
_NUDE_KEEP = {2, 3, 4, 28, 34, 35, 37, 38, 39, 40, 41, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57,
              58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 76, 77, 78, 79, 80, 81, 82, 83, 84,
              85, 86, 87, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 112, 113, 116, 117}
# the game's nude body parts (a stored BATHING outfit uses exactly these instances)
NUDE_PARTS = {'yf': [(6, 0x198C, 'yfTop_Nude'), (7, 0x1990, 'yfBottom_Nude'), (8, 0x198F, 'yfShoes_Nude')],
              'ym': [(6, 0x19A2, 'ymTop_Nude'), (7, 0x19AE, 'ymBottom_Nude'), (8, 0x19A3, 'ymShoes_Nude')]}


def _part_info(inst, resolve):
    """{casp_instance, origin, name} (origin 'game' / 'cc' / None = not installed) when resolve, else just the id."""
    out = {'casp_instance': hexid(inst)}
    if resolve:
        import morph
        row = morph.PART_INDEX.find(morph.T_CASP, inst)
        out['origin'] = None if row is None else ('cc' if int(row['pkg']) < morph.PART_INDEX.n_cc else 'game')
        if row is not None:
            try:
                out['name'] = morph.casp_name(morph.PART_INDEX.read(morph.T_CASP, inst))
            except Exception:
                pass
    return out


# The parts of a sim's look the game paints on the skin: makeup, brows, eye colour, facial hair, skin details, tattoos,
# scars, nails, body hair. Occult parts, the teeth and the head are left out.
_LOOK = re.compile(r'^(FACIAL_HAIR|LIPS_TICK|EYE_SHADOW|EYE_LINER|BLUSH|FACEPAINT|EYEBROWS|EYECOLOR|EYECOLOR_SECONDARY|'
                   r'EYELASHES|SKINDETAIL_.*|TATTOO_.*|SKIN_OVERLAY|FOREARM_SCAR|ACNE|FINGERNAIL|TOENAIL|BODYFRECKLES|'
                   r'BODYHAIR_.*|BODYSCAR_.*|SCARFACE|BIRTHMARK.*|MOLE.*|STRETCHMARKS_.*)$')
LOOK_EYECOLOR = 35


def look_parts(tray_id, sim_index):
    """The CAS parts of a Tray sim's look that are painted on the skin, from the outfit it was saved in (the one its
    Tray picture shows; the everyday outfit when that one is not stored). -> [{casp_instance, body_type,
    body_type_name}] in the outfit's order, each part once."""
    s = household_sims(tray_id)['sims'][sim_index]
    outfits = s['outfits']
    cur = s['current_outfit']
    outfit = next((o for o in outfits if o['category'] == cur['category'] and o['index'] == cur['index']), None)         or next((o for o in outfits if o['category'] == 'EVERYDAY'), None) or (outfits[0] if outfits else None)
    out, seen = [], set()
    for p in (outfit or {}).get('parts', []):
        name = BODY_TYPES.get(p['body_type'], '')
        if not _LOOK.match(name) or p['casp_instance'] in seen or to_int(p['casp_instance']) == 0:
            continue
        seen.add(p['casp_instance'])
        out.append({'casp_instance': p['casp_instance'], 'body_type': p['body_type'], 'body_type_name': name})
    return out


def sim_body_spec(tray_id, sim_index, resolve=True):
    """Everything the animator needs to build one tray sim (body shape now, hair/clothes later).

    -> {sim_id, name, age, gender, species, frame ('yf'/'ym' = gamedata.body() frame; 'cu'/'pu' for kids),
        prefix (physique DMap prefix, e.g. 'yf', 'ef'), rig, tone_inst, tone_shift, physique, modifiers
        (face + body [{modifier_instance, value, kind}]), face_modifiers, body_modifiers, sculpts, nude_parts,
        head_part, hair_part, outfits, current_outfit, morph_report}
    Pass it straight to morph.morph_body(gamedata.body(spec['frame']), spec).
    With resolve=True parts get 'origin' ('game' / 'cc' / None when not installed) and CAS part 'name'.
    """
    data = household_sims(tray_id)
    s = data['sims'][sim_index]
    age_id, gender_id = s['age_id'], s['gender_id']
    adult = age_id in (8, 16, 32, 64)
    frame_gender = 'm' if s['frame'] == 'masculine' else 'f'
    if adult:
        frame = 'y' + frame_gender
        prefix = ('e' if age_id == 64 else 'y') + frame_gender
        rig = 'au'
    else:
        letter = {4: 'c', 2: 'p', 128: 'i', 1: 'i'}.get(age_id, 'c')
        frame = prefix = letter + 'u'
        rig = letter + 'u'
    outfits = s['outfits']
    by_cat = {}
    for o in outfits:
        by_cat.setdefault(o['category'], []).append(o)
    cur = s['current_outfit']
    current = next((o for o in by_cat.get(cur['category'], []) if o['index'] == cur['index']), None)
    base = (by_cat.get('EVERYDAY') or [current] or outfits[:1])[0] if outfits else None
    base = base or current

    def pick(bt, outfit):
        for p in (outfit or {}).get('parts', []):
            if p['body_type'] == bt:
                return int(p['casp_instance'], 16)
        return None

    # nude outfit: the stored BATHING outfit if there is one, else the everyday look minus clothing + nude body parts
    bathing = (by_cat.get('BATHING') or [None])[0]
    nude = []
    if bathing:
        for p in bathing['parts']:
            nude.append(dict(_part_info(int(p['casp_instance'], 16), resolve), body_type=p['body_type'],
                             body_type_name=p['body_type_name']))
    elif base:
        for p in base['parts']:
            if p['body_type'] in _NUDE_KEEP:
                nude.append(dict(_part_info(int(p['casp_instance'], 16), resolve), body_type=p['body_type'],
                                 body_type_name=p['body_type_name']))
        for bt, inst, name in NUDE_PARTS.get(frame, []):
            nude.append(dict(_part_info(inst, resolve), body_type=bt, body_type_name=BODY_TYPES[bt], default_name=name))
    hair = pick(2, current) or pick(2, base)
    head = pick(3, current) or pick(3, base)
    spec = {
        'tray_id': data['id'], 'sim_index': sim_index, 'sim_id': s['sim_id'],
        'name': ('%s %s' % (s['first'], s['last'])).strip(), 'first': s['first'], 'last': s['last'],
        'age': s['age'], 'age_id': age_id, 'gender': s['gender'], 'gender_id': gender_id, 'species': s['species'],
        'frame': frame, 'body_frame': s['frame'], 'prefix': prefix, 'rig': rig, 'breasts': s['breasts'],
        'tone_inst': s['skin_tone'], 'tone_shift': s['skin_tone_shift'],
        'physique': s['physique'],
        'modifiers': [dict(m, kind='face') for m in s['face_modifiers']] + [dict(m, kind='body') for m in s['body_modifiers']],
        'face_modifiers': s['face_modifiers'], 'body_modifiers': s['body_modifiers'],
        'sculpts': s['sculpts'],
        'nude_parts': nude,
        'head_part': _part_info(head, resolve) if head else None,
        'hair_part': _part_info(hair, resolve) if hair else None,
        'outfits': outfits, 'current_outfit': cur,
        'has_thumb': s['has_thumb'],
        # the sim's game voice: voice_actor = fnv32 of the actor code (eaaudio.voice_for_actor), pitch -1..1
        'voice_actor': s.get('voice_actor'), 'voice_pitch': s.get('voice_pitch'),
    }
    if resolve:
        import morph
        ops, report = morph.resolve_morphs({'physique': s['physique'], 'modifiers': spec['modifiers'],
                                            'sculpts': s['sculpts']}, prefix)
        spec['morph_report'] = {'ops': len(ops), 'bgeo': sum(o['kind'] == 'bgeo' for o in ops),
                                'dmap': sum(o['kind'] == 'dmap' for o in ops), 'bond': sum(o['kind'] == 'bond' for o in ops),
                                'smods': report['smods'], 'sculpts': report['sculpts'],
                                'physique': report['physique'], 'missing': report['missing']}
    return spec


def find_sims(text):
    """[(tray_id, sim_index, 'First Last')] whose name contains text (case-insensitive)."""
    text = text.lower()
    out = []
    for h in list_households():
        for k, s in enumerate(h['sims']):
            name = ('%s %s' % (s['first'], s['last'])).strip()
            if text in name.lower() or text in h['name'].lower():
                out.append((h['id'], k, name))
    return out


if __name__ == '__main__':
    import sys, json
    t = time.time()
    hs = list_households()
    print('%d households in %.2fs' % (len(hs), time.time() - t))
    for h in hs[:int(sys.argv[1]) if len(sys.argv) > 1 else 5]:
        print(h['id'], h['name'], [(s['first'], s['age'], s['gender']) for s in h['sims']])

"""Sims 4 CLIP resource (type 0x6B20C4F3): container + S3CLIP ('_pilC3S_') codec data. Raw structure only."""
import struct, io

CT_NAMES = ['Unknown', 'F1', 'F2', 'F3', 'F4', 'F1_Normalized', 'F2_Normalized', 'F3_Normalized', 'F4_Normalized',
            'F1_Zero', 'F2_Zero', 'F3_Zero', 'F4_Zero', 'F1_One', 'F2_One', 'F3_One', 'F4_One', 'F4_QuaternionIdentity',
            'F3_HighPrecisionNormalized', 'F4_HighPrecisionNormalized_Quaternion', 'F4_SuperHighPrecision_Quaternion',
            'F3_HighPrecisionNormalized_Quaternion']
ST_NAMES = ['Unknown', 'Translation', 'Orientation', 'Scale']
WIDTH = {5: 1, 6: 1, 7: 1, 8: 1, 18: 10, 19: 10, 21: 10, 1: 2, 2: 2, 3: 2, 4: 2, 20: 2}
COUNT = {1: 1, 5: 1, 2: 2, 6: 2, 3: 3, 7: 3, 4: 4, 8: 4, 20: 4, 19: 4, 21: 4, 18: 3}


class R:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos
    def u8(self): v = self.d[self.p]; self.p += 1; return v
    def u16(self): v = struct.unpack_from('<H', self.d, self.p)[0]; self.p += 2; return v
    def u32(self): v = struct.unpack_from('<I', self.d, self.p)[0]; self.p += 4; return v
    def i32(self): v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v
    def f32(self): v = struct.unpack_from('<f', self.d, self.p)[0]; self.p += 4; return v
    def raw(self, n): v = self.d[self.p:self.p + n]; self.p += n; return v
    def s32(self): n = self.i32(); return self.raw(n).decode('ascii', 'replace')
    def zstr(self, pos):
        end = self.d.index(b'\0', pos); return self.d[pos:end].decode('utf-8', 'replace')


CODEC_MARKER = b'_pilC3S_'


def parse_clip(data):
    """Version 14 (creator clips, this app) and the game's newer clips (version 15-18): the newer ones carry a few
    more bytes between the event list and the codec, so the codec is found at its '_pilC3S_' marker, whose length
    (u32) sits right before it."""
    r = R(data)
    c = {}
    c['version'] = r.u32(); c['flags'] = r.u32(); c['duration'] = r.f32()
    c['initial_q'] = [r.f32() for _ in range(4)]; c['initial_t'] = [r.f32() for _ in range(3)]
    v = c['version']
    if v >= 5: c['reference_ns_hash'] = r.u32()
    if v >= 10: c['surface_ns_hash'] = r.u32(); c['surface_joint_hash'] = r.u32()
    if v >= 11: c['surface_child_ns_hash'] = r.u32()
    if v >= 7: c['clip_name'] = r.s32()
    c['rig_ns'] = r.s32()
    if v >= 4: c['explicit_ns'] = [r.s32() for _ in range(r.i32())]
    marker = data.find(CODEC_MARKER, r.p)
    c['slots'], c['events'] = [], []
    try:
        for _ in range(r.i32()):
            c['slots'].append((r.u16(), r.u16(), r.s32(), r.s32()))
        for _ in range(r.u32()):
            et = r.u32(); size = r.u32(); c['events'].append((et, r.raw(size)))
        if marker >= 0 and r.p > marker - 4:
            raise ValueError('slot/event list runs into the codec')
    except (struct.error, IndexError, ValueError):
        if marker < 4:
            raise
        # a layout this reader doesn't know: keep what the codec says, drop the half-read lists
        c['slots'], c['events'], r.p = [], [], marker - 4
    if marker >= 4 and r.p != marker - 4 and data[r.p + 4:r.p + 12] != CODEC_MARKER:
        c['extra'] = data[r.p:marker - 4]      # version 15+: unknown bytes before the codec length
        r.p = marker - 4
    codec_len = r.u32()
    c['codec_offset'] = r.p
    c['codec'] = parse_codec(data, r.p) if codec_len else None
    c['tail'] = len(data) - (r.p + codec_len)
    return c


def parse_codec(data, start):
    r = R(data, start)
    k = {}
    k['token'] = r.raw(8); k['version'] = r.u32(); k['flags'] = r.u32(); k['tick_length'] = r.f32()
    k['num_ticks'] = r.u16(); k['padding'] = r.u16()
    n_channels = r.u32(); pal_size = r.u32(); ch_off = r.u32(); pal_off = r.u32(); name_off = r.u32(); src_off = r.u32()
    k['name'] = r.zstr(start + name_off); k['source'] = r.zstr(start + src_off)
    k['palette'] = list(struct.unpack_from('<%df' % pal_size, data, start + pal_off))
    k['offsets'] = dict(channels=ch_off, palette=pal_off, name=name_off, source=src_off)
    chans = []
    p = start + ch_off
    for i in range(n_channels):
        data_off, target, offset, scale, nframes, ctype, sub = struct.unpack_from('<IIffHBB', data, p); p += 20
        w, cnt = WIDTH.get(ctype, 0), COUNT.get(ctype, 0)
        frames = []
        q = start + data_off
        for _ in range(nframes):
            tick, flags = struct.unpack_from('<HH', data, q); q += 4
            if w == 1:
                idx = list(data[q:q + cnt]); q += 4 if cnt <= 4 else cnt
            elif w == 2:
                idx = list(struct.unpack_from('<%dH' % cnt, data, q)); q += 2 * cnt + (2 if cnt % 2 else 0)
            elif w == 10:
                d = struct.unpack_from('<I', data, q)[0]; q += 4
                idx = [d & 1023, (d >> 10) & 1023, (d >> 20) & 1023]
            else:
                idx = []
            frames.append((tick, flags, idx))
        chans.append(dict(data_off=data_off, target=target, offset=offset, scale=scale, type=ctype, sub=sub, frames=frames))
    k['channels'] = chans
    return k


# ------------------------------------------------------------------ values <-> stored indices
# Every stored component is  value = sign * (index / MAX) * scale + offset,  sign = frame flag bit k.
MAXV = {1: 255.0, 2: 4095.0, 10: 1023.0}


# Constant channels (the game's own clips): no frames at all; the value is the channel's offset in every component
# (checked on 3,000 EA clips: F1_Zero 0/1 weights, F3_Zero translation 0 and scale 1, F4_Zero b__ROOT_bind__
# rotation offset .5 = its rest (0.5, 0.5, 0.5, 0.5)). F4_QuaternionIdentity is (0, 0, 0, 1).
CONSTANT_COMPONENTS = {9: 1, 10: 2, 11: 3, 12: 4, 13: 1, 14: 2, 15: 3, 16: 4, 17: 4}


def constant_value(ch):
    """[floats] of a constant channel (no frames), or None for a keyed channel."""
    if ch['frames']:
        return None
    t = ch['type']
    if t == 17:
        return [0.0, 0.0, 0.0, 1.0]
    n = CONSTANT_COMPONENTS.get(t) or COUNT.get(t)
    if not n:
        return None
    if 13 <= t <= 16:                  # the '_One' types: the index at its top, i.e. offset + scale
        return [ch['offset'] + ch['scale']] * n
    return [ch['offset']] * n


def decode_track(ch):
    """[(tick, [floats])] for any channel: keyed channels as decode_frames, constant ones as one key at tick 0."""
    frames = decode_frames(ch)
    if frames:
        return frames
    v = constant_value(ch)
    return [(0, v)] if v is not None else []


def decode_frames(ch):
    """[(tick, [floats])] for a raw channel; constant channel types give no frames (see decode_track)."""
    w = WIDTH.get(ch['type'], 0)
    n = MAXV.get(w)
    out = []
    for tick, flags, ix in ch['frames']:
        vals = [(-1.0 if flags & (1 << k) else 1.0) * (ix[k] / n) * ch['scale'] + ch['offset'] for k in range(len(ix))]
        if ch['type'] in (19, 21) and len(vals) == 3:
            # 10-bit quaternion with the fourth component implied (not seen in WickedWhims clips)
            vals.append((max(0.0, 1.0 - sum(v * v for v in vals))) ** 0.5)
        out.append((tick, vals))
    return out


def encode_channel(target, sub, keys, quaternion):
    """keys: [(tick, [floats])] -> raw channel dict (F4_SuperHighPrecision_Quaternion or F3_HighPrecisionNormalized)."""
    ctype, n = (20, 4095.0) if quaternion else (18, 1023.0)
    flat = [v for _, vals in keys for v in vals]
    lo, hi = min(flat), max(flat)
    offset = (lo + hi) / 2.0
    scale = max(abs(v - offset) for v in flat)
    frames = []
    for tick, vals in keys:
        flags, ix = 0, []
        for k, v in enumerate(vals):
            d = v - offset
            if d < 0:
                flags |= 1 << k
            ix.append(int(round(abs(d) / scale * n)) if scale > 0 else 0)
        frames.append((tick, flags, ix))
    return dict(target=target, offset=float(offset), scale=float(scale), type=ctype, sub=sub, frames=frames)


def fnv32(s):
    h = 0x811C9DC5
    for b in s.lower().encode('utf-8'):
        h = ((h * 0x01000193) & 0xFFFFFFFF) ^ b
    return h


def fnv64(s):
    h = 0xCBF29CE484222325
    for b in s.lower().encode('utf-8'):
        h = ((h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ b
    return h


# ------------------------------------------------------------------ IK targets (slot assignments)
# The layout as thepancake1's s4animtools writes it (github.com/thepancake1/_s4animtools, HEAD 05a378c:
# slot_assignments.py, clip_processing/clip_header.py, __init__.py, animation_exporter/animation.py):
#  - in the header, after the explicit namespaces: u32 count, then per IK target
#      u16 chain, u16 slot, str32 target namespace (the actor it points at), str32 target joint
#    (parse_clip reads the same layout into c['slots']);
#  - chains: b__L_Hand__ 0, b__R_Hand__ 1, b__L_Foot__ 2, b__R_Foot__ 3, b__ROOT_bind__ 4; slot = the target's number
#    on its chain (0, 1, ...);
#  - in the codec, on the chain's end bone (target = fnv32 of its name): the weight of slot i (sub 14 + i, a one-value
#    channel), and the bone's position and rotation in the target joint's space (sub 25 + 2i and 26 + 2i).
IK_CHAINS = {'b__L_Hand__': 0, 'b__R_Hand__': 1, 'b__L_Foot__': 2, 'b__R_Foot__': 3, 'b__ROOT_bind__': 4}


def ik_weight_sub(slot):
    return 14 + slot


def ik_translation_sub(slot):
    return 25 + 2 * slot


def ik_rotation_sub(slot):
    return 26 + 2 * slot


def constant_channel(target, sub, value, ctype=9):
    """A channel with no frames whose value is its offset (F1_Zero, type 9: how EA's clips store a weight that never
    changes - see CONSTANT_COMPONENTS)."""
    return dict(target=target, offset=float(value), scale=0.0, type=ctype, sub=sub, frames=[])


# ------------------------------------------------------------------ writing
def _s32(b):
    return struct.pack('<i', len(b)) + b


def _slot_bytes(slots):
    """[(chain, slot, namespace, joint)] -> the header's IK target list (u32 count first)."""
    out = struct.pack('<i', len(slots))
    for chain, slot, ns, joint in slots:
        out += struct.pack('<HH', chain, slot) + _s32(ns.encode('ascii')) + _s32(joint.encode('ascii'))
    return out


def write_codec(name, source, num_ticks, channels, tick_length=1.0 / 30.0, version=2):
    """S3CLIP ('_pilC3S_') bytes; channels=[] gives the clip-header stub."""
    head_len = 48
    ch_table = 20 * len(channels)
    name_b = name.encode('utf-8') + b'\0'
    src_b = source.encode('utf-8') + b'\0'
    palette = struct.pack('<2f', 0.0, 1.0)
    ch_off = head_len
    name_off = ch_off + ch_table
    src_off = name_off + len(name_b)
    pal_off = src_off + len(src_b)
    data_start = pal_off + len(palette)
    blobs, table, pos = [], [], data_start
    for ch in channels:
        w = WIDTH.get(ch['type'], 0)            # constant channels (no frames) have no width
        buf = bytearray()
        for tick, flags, ix in ch['frames']:
            buf += struct.pack('<HH', tick, flags)
            if w == 10:
                buf += struct.pack('<I', (ix[0] & 1023) | ((ix[1] & 1023) << 10) | ((ix[2] & 1023) << 20))
            elif w == 2:
                buf += struct.pack('<%dH' % len(ix), *ix) + (b'\0\0' if len(ix) % 2 else b'')
            elif w == 1:
                buf += bytes(ix) + bytes(max(0, 4 - len(ix)))
        table.append(struct.pack('<IIffHBB', pos, ch['target'], ch['offset'], ch['scale'], len(ch['frames']), ch['type'], ch['sub']))
        blobs.append(bytes(buf))
        pos += len(buf)
    head = (b'_pilC3S_' + struct.pack('<IIfHH', version, 0, tick_length, num_ticks, 0)
            + struct.pack('<6I', len(channels), 2, ch_off, pal_off, name_off, src_off))
    return head + b''.join(table) + name_b + src_b + palette + b''.join(blobs)


def write_clip(name, rig_ns, num_ticks, channels, source='FitStudio', events=(), tick_length=1.0 / 30.0, slots=()):
    """(clip bytes, clip header bytes) for a version-14 CLIP resource. slots: IK targets [(chain, slot, namespace,
    joint)] (see IK_CHAINS); none gives exactly the bytes of a clip without them.

    The duration covers every tick (num_ticks * tick_length), like most creator clips: in a loop the step from the
    last tick back to tick 0 then takes one tick too, instead of no time at all (a visible hitch every loop)."""
    empty = 0x811C9DC5
    duration = max(1, num_ticks) * tick_length
    head = struct.pack('<IIf', 14, 0, duration) + struct.pack('<4f', 0, 0, 0, 1) + struct.pack('<3f', 0, 0, 0)
    head += struct.pack('<IIII', 0, empty, empty, empty)
    head += _s32(name.encode('ascii')) + _s32(rig_ns.encode('ascii'))
    head += struct.pack('<i', 0) + _slot_bytes(slots)             # explicit namespaces, slot assignments
    head += struct.pack('<I', len(events)) + b''.join(struct.pack('<II', t, len(d)) + d for t, d in events)
    codec = write_codec(name, source, num_ticks, channels, tick_length)
    stub = write_codec(name, source, num_ticks, [], tick_length)
    return head + struct.pack('<I', len(codec)) + codec, head + struct.pack('<I', len(stub)) + stub

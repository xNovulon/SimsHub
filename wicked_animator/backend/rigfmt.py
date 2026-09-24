"""Sims 4 RIG resource (type 0x8EAF13DE), version 3/4."""
import struct
from clipfmt import R


def parse_rig(data):
    r = R(data)
    rig = {'major': r.u32(), 'minor': r.u32()}
    bones = []
    for _ in range(r.i32()):
        pos = [r.f32() for _ in range(3)]
        rot = [r.f32() for _ in range(4)]      # x, y, z, w
        scale = [r.f32() for _ in range(3)]
        name = r.s32()
        opposite = r.i32(); parent = r.i32(); h = r.u32(); flags = r.u32()
        bones.append(dict(name=name, pos=pos, rot=rot, scale=scale, opposite=opposite, parent=parent, hash=h, flags=flags))
    rig['bones'] = bones
    if rig['major'] >= 4:
        rig['name'] = r.s32()
    rig['ik_chain_count'] = r.i32() if r.p < len(data) else 0
    rig['rest_bytes'] = len(data) - r.p
    return rig

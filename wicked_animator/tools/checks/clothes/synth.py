"""Synthetic CAS parts for the clothes checks (no game needed): CASP, GEOM and DDS bytes in the layouts the repo's
readers parse (casptex.parse_casp, morph.read_geom, texfmt.decode_dds), packed with wwpackage.build_package, and
point_parts_at() to make morph.PART_INDEX read only those packages (a "game" one and a "Mods" one in a temp folder).
Used by test_clothes.py and clothes_server.py.
"""
import os
import struct

import numpy as np

T_CASP, T_GEOM, T_DDS = 0x034AEECB, 0x015A1849, 0x00B2D882


def make_geom(positions, bones, weights, hashes, faces=None, version=14, normals=None):
    """An RCOL GEOM as morph.read_geom reads it: position, normal, uv0, uv1, bone indices, float weights, tags."""
    pos = np.asarray(positions, np.float32).reshape(-1, 3)
    n = len(pos)
    faces = list(faces if faces is not None else [k for t in range(n - 2) for k in (0, t + 1, t + 2)])
    fmts = [(1, 1, 12), (2, 1, 12), (3, 1, 8), (3, 1, 8), (4, 2, 4), (5, 1, 16), (7, 4, 4)]
    body = bytearray()
    body += struct.pack('<4I', 0, 0, n, len(fmts))
    for f in fmts:
        body += struct.pack('<IIB', *f)
    for v in range(n):
        body += struct.pack('<3f', *pos[v]) + struct.pack('<3f', *(normals[v] if normals is not None else (0, 0, 1)))
        body += struct.pack('<2f', (pos[v][0] + 1) / 2, 1 - pos[v][1] / 2) + struct.pack('<2f', 0.5, 0.5)
        body += bytes(int(b) for b in bones[v]) + struct.pack('<4f', *weights[v]) + struct.pack('<I', 0x4000)
    body += struct.pack('<I', 1) + bytes([2]) + struct.pack('<I', len(faces)) + struct.pack('<%dH' % len(faces), *faces)
    body += struct.pack('<I', 0)                               # uv stitches
    if version >= 13:
        body += struct.pack('<I', 0)                           # seam stitches
    body += struct.pack('<I', 0)                               # slot ray intersections
    body += struct.pack('<I', len(hashes)) + struct.pack('<%dI' % len(hashes), *hashes)
    tgi_block = struct.pack('<I', 0)
    chunk = b'GEOM' + struct.pack('<4I', version, 4 + len(body), len(tgi_block), 0) + bytes(body) + tgi_block
    head = struct.pack('<5I', 3, 0, 0, 0, 1) + struct.pack('<QII', 1, T_GEOM, 0)
    off = len(head) + 8
    return head + struct.pack('<II', off, len(chunk)) + chunk


def make_casp(name, body_type, age_gender, lods, tgis, diffuse=0xFF, version=42):
    """A CASP (version 42) as casptex.parse_casp reads it. lods: [(lod, [tgi indices])]; tgis: [(type, group, inst)]."""
    d = bytearray(struct.pack('<III', version, 0, 0))
    nm = name.encode('utf-16-be')
    n = len(nm)
    while True:                                                # 7-bit length
        b = n & 0x7F; n >>= 7
        d.append(b | (0x80 if n else 0))
        if not n:
            break
    d += nm
    d += struct.pack('<fHIIB', 1.0, 0, 0, 0, 0) + bytes([0])   # sort priority .. param flags, param flags 2
    d += struct.pack('<QQQ', 0, 0, 0)                          # exclude part flags (2), exclude modifier regions
    d += struct.pack('<I', 0)                                  # tags
    d += struct.pack('<III', 0, 0, 0) + bytes([0])             # price, title, desc, texture space
    d += struct.pack('<IIII', body_type, 0, age_gender, 1)     # body type, subtype, age/gender, species
    d += struct.pack('<HB', 0, 0) + bytes(9)                   # pack id, flags, reserved
    d += bytes([0, 0, 0]) + struct.pack('<Q', 0) + bytes([0])  # swatches, buff, thumb, voice, material sets
    d += struct.pack('<IQQ', 0, 0, 0)                          # hide for occult, opposite gender, fallback
    d += bytes([0, 0]) + struct.pack('<i', 0)                  # naked key, parent key, sort layer
    d.append(len(lods))
    for lod, keys in lods:
        d += bytes([lod]) + struct.pack('<I', 0) + bytes([0, len(keys)]) + bytes(keys)
    d += bytes([0, diffuse, 0xFF, 0, 0xFF, 0, 0xFF, 0xFF]) + struct.pack('<I', 0) + bytes([0xFF])
    struct.pack_into('<I', d, 4, len(d) - 8)
    d.append(len(tgis))
    for t, g, i in tgis:
        d += struct.pack('<QII', i, g, t)
    return bytes(d)


def make_dds(rgba):
    """An uncompressed 32-bit DDS (texfmt.decode_dds 'RAW')."""
    h, w, _ = rgba.shape
    head = bytearray(128)
    head[0:4] = b'DDS '
    struct.pack_into('<7I', head, 4, 124, 0x100F, h, w, w * 4, 0, 1)
    struct.pack_into('<II4s5I', head, 76, 32, 0x41, b'\0\0\0\0', 32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000)
    return bytes(head) + np.ascontiguousarray(rgba, np.uint8).tobytes()


def solid(r, g, b, a=255, size=8):
    img = np.zeros((size, size, 4), np.uint8)
    img[:] = (r, g, b, a)
    return img


def point_parts_at(tmp, sims_dir, game_pkg, cc_pkg=None):
    """morph.PART_INDEX (and the caches of clothes.py and hair.py) on these packages and a temp folder only."""
    import morph, clothes, hair
    morph.SIMS_DIR = sims_dir
    morph.CACHE_DIR = os.path.join(tmp, 'cache', 'tray')
    morph._package_sources = lambda include_cc=True: (([cc_pkg] if cc_pkg else []) + [game_pkg], 1 if cc_pkg else 0)
    morph.PART_INDEX._loaded = False
    clothes.CACHE = os.path.join(tmp, 'cache', 'clothes')
    hair.CACHE = os.path.join(tmp, 'cache', 'hair')


def ring_mesh(y0, y1, radius, segments=12, x=0.0, z=0.0):
    """An open tube from y0 to y1 (2 rings of `segments` vertices): positions, faces and normals."""
    pos, faces, nrm = [], [], []
    for y in (y0, y1):
        for k in range(segments):
            a = 2 * np.pi * k / segments
            pos.append((x + radius * np.sin(a), y, z + radius * np.cos(a)))
            nrm.append((np.sin(a), 0.0, np.cos(a)))
    for k in range(segments):
        a, b = k, (k + 1) % segments
        faces += [a, b, segments + a, b, segments + b, segments + a]
    return pos, faces, nrm

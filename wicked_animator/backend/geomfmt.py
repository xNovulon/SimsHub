"""Sims 4 GEOM mesh (type 0x015A1849, RCOL-wrapped, versions 12-15): vertices, faces, bone hashes."""
import struct


def parse_geom(data, known_bone_hashes=None):
    # RCOL header
    ver, public, unused, n_ext, n_int = struct.unpack_from('<5I', data, 0)
    p = 20 + 16 * (n_int + n_ext)
    chunk_off, chunk_size = struct.unpack_from('<II', data, p)
    c = chunk_off
    assert data[c:c + 4] == b'GEOM', data[c:c + 4]
    version, tgi_off, tgi_size, shader = struct.unpack_from('<4I', data, c + 4)
    q = c + 20
    if shader:
        mtnf_size = struct.unpack_from('<I', data, q)[0]
        q += 4 + mtnf_size
    merge_group, sort_order, n_verts, n_fmt = struct.unpack_from('<4I', data, q); q += 16
    fmts = []
    for _ in range(n_fmt):
        usage, dtype, size = struct.unpack_from('<IIB', data, q); q += 9
        fmts.append((usage, dtype, size))
    stride = sum(f[2] for f in fmts)
    pos, nrm, uv, bones, weights = [], [], [], [], []
    for v in range(n_verts):
        o = q + v * stride
        for usage, dtype, size in fmts:
            if usage == 1:
                pos.append(struct.unpack_from('<3f', data, o))
            elif usage == 2:
                nrm.append(struct.unpack_from('<3f', data, o))
            elif usage == 3 and len(uv) == v:
                uv.append(struct.unpack_from('<2f', data, o))
            elif usage == 4:
                bones.append(tuple(data[o:o + 4]))
            elif usage == 5:
                if size == 4:
                    weights.append(tuple(b / 255.0 for b in data[o:o + 4]))
                else:
                    weights.append(struct.unpack_from('<4f', data, o))
            o += size
    q += n_verts * stride
    n_sub = struct.unpack_from('<I', data, q)[0]; q += 4
    bpi = data[q]; q += 1
    n_idx = struct.unpack_from('<I', data, q)[0]; q += 4
    faces = list(struct.unpack_from('<%d%s' % (n_idx, 'H' if bpi == 2 else 'I'), data, q))
    q += n_idx * bpi
    # bone hash list sits right before the TGI block (at chunk + 12 + tgi_off)
    tgi_start = c + 12 + tgi_off
    # The bone hash list ends just before the TGI block (v15: one more empty uint32 list in between).
    # Its count is not at a fixed place, so every "count k followed by k hashes" candidate that covers
    # the bone indices the vertices use is scored by how many hashes are real rig bones.
    need = 1 + max((max(b) for b in bones), default=-1)
    best, best_score = [], -1
    for gap in ((8, 4) if version >= 15 else (4,)):
        for k in range(max(1, need), 1024):
            at = tgi_start - gap - 4 * k
            if at < q:
                break
            if struct.unpack_from('<I', data, at)[0] == k:
                cand = list(struct.unpack_from('<%dI' % k, data, at + 4))
                score = sum(1 for h in cand if h in known_bone_hashes) / k if known_bone_hashes else 1.0 / k
                if score > best_score:
                    best, best_score = cand, score
    bone_hashes = best
    return dict(version=version, shader=shader, formats=fmts, positions=pos, normals=nrm, uvs=uv,
                bones=bones, weights=weights, faces=faces, bone_hashes=bone_hashes or [])

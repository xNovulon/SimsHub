"""Decode The Sims 4 image resources to RGBA (numpy uint8 array, shape (H, W, 4)) or PIL images.

Formats (worked out from s4pi's DSTResource/RLEResource/LRLEResource and checked against game data):

- 0x00B2D882 "DDS/DST": a normal DDS file ('DDS ' + 124-byte header, data at 128, +20 for DX10). FourCC DXT1/DXT3/
  DXT5, ATI1/BC4U, ATI2/BC5U, uncompressed RGB(A)/luminance by bit masks, or EA's shuffled DST1/DST3/DST5: the same
  DXT blocks, but stored field by field over the whole (all-mips) data blob:
      DST1: [colour endpoints 4B x n][colour indices 4B x n]
      DST3: [explicit alpha 8B x n][colour endpoints 4B x n][colour indices 4B x n]
      DST5: [alpha endpoints 2B x n][colour endpoints 4B x n][alpha indices 6B x n][colour indices 4B x n]
- 0x3453CF95 "RLE2" and 0xBA856C78 "RLES": 16-byte header ('DXT5' or 'L8  ', 'RLE2'/'RLES', u16 w, h, mips, 0),
  then per mip 5 (RLES: 6) int32 offsets: commands, colour endpoints, colour indices, alpha endpoints, alpha
  indices[, specular mask]. The u16 commands (op = c & 3, count = c >> 2) emit DXT5 blocks: 0 = fully transparent,
  1 = next block from the streams (RLES: plus a 16-byte 4x4 specular mask), 2 = opaque block (RLE2: colour only,
  alpha forced 255; RLES: full block, mask = 255). Streams are segment-major over all mips.
  The 'L8' flavour stores 16 raw luminance bytes per op-1 block (op 0 = black, op 2 = white).
- 0x2BC04EDF "LRLE": 'LRLE', version (0 or 'V002'), u16 w, h, u32 mips, u32 mip offsets, [V002: u32 n + n*4-byte
  palette], then per mip a byte-coded run-length stream of 4-byte BGRA pixels in 4x4-block order.
"""
import io, struct
import numpy as np

T_DST, T_RLE2, T_RLES, T_LRLE = 0x00B2D882, 0x3453CF95, 0xBA856C78, 0x2BC04EDF
T_DDS_RAW = 0xB6C8B6A0
TEXTURE_TYPES = (T_LRLE, T_RLE2, T_DST, T_RLES, T_DDS_RAW)

_BIT16 = np.arange(16, dtype=np.uint32)


# ------------------------------------------------------------------ block (BCn) decoding, vectorised
def _unblock(px, bw, bh, ch):
    """(nb, 16, ch) block pixels (row-major blocks, row-major texels) -> (bh*4, bw*4, ch)."""
    return px.reshape(bh, bw, 4, 4, ch).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, ch)


def _rgb565(c):
    c = c.astype(np.int32)
    r = (c >> 11) & 31; g = (c >> 5) & 63; b = c & 31
    return np.stack([(r * 527 + 23) >> 6, (g * 259 + 33) >> 6, (b * 527 + 23) >> 6], -1)


def _colour_blocks(blk, dxt1):
    """blk: (nb, 8) uint8 colour blocks -> (nb, 16, 4) uint8 RGBA."""
    nb = blk.shape[0]
    c = np.ascontiguousarray(blk[:, 0:4]).view('<u2').reshape(nb, 2)
    c0, c1 = c[:, 0], c[:, 1]
    bits = np.ascontiguousarray(blk[:, 4:8]).view('<u4').reshape(nb)
    p0, p1 = _rgb565(c0), _rgb565(c1)                       # (nb, 3) int32
    four = (c0 > c1) if dxt1 else None
    if four is None:
        p2, p3 = (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3
    else:
        f = four[:, None]
        p2 = np.where(f, (2 * p0 + p1) // 3, (p0 + p1) // 2)
        p3 = np.where(f, (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1).astype(np.uint32)   # (nb, 4, 3)
    packed = pal[:, :, 0] | (pal[:, :, 1] << 8) | (pal[:, :, 2] << 16) | np.uint32(0xFF000000)
    if four is not None:
        packed[:, 3] = np.where(four, packed[:, 3], 0)
    idx = (bits[:, None] >> (2 * _BIT16)) & 3                  # (nb, 16)
    idx += (np.arange(nb, dtype=np.uint32) * 4)[:, None]
    return packed.reshape(-1)[idx].view(np.uint8).reshape(nb, 16, 4)


def _alpha_blocks(blk):
    """blk: (nb, 8) uint8 BC4/DXT5-alpha blocks -> (nb, 16) uint8."""
    nb = blk.shape[0]
    a0 = blk[:, 0].astype(np.int32); a1 = blk[:, 1].astype(np.int32)
    b = np.zeros((nb, 8), np.uint8)
    b[:, :6] = blk[:, 2:8]
    bits = b.view('<u8').reshape(nb)
    eight = a0 > a1
    k = np.arange(1, 7, dtype=np.int32)
    v8 = ((7 - k) * a0[:, None] + k * a1[:, None]) // 7                     # (nb, 6)
    k4 = np.arange(1, 5, dtype=np.int32)
    v6 = ((5 - k4) * a0[:, None] + k4 * a1[:, None]) // 5                   # (nb, 4)
    v6 = np.concatenate([v6, np.zeros((nb, 1), np.int32), np.full((nb, 1), 255, np.int32)], 1)
    pal = np.empty((nb, 8), np.uint8)
    pal[:, 0], pal[:, 1] = a0, a1
    pal[:, 2:] = np.where(eight[:, None], v8, v6)
    idx = ((bits[:, None] >> (3 * _BIT16.astype(np.uint64))) & np.uint64(7)).astype(np.intp)
    idx += (np.arange(nb, dtype=np.intp) * 8)[:, None]
    return pal.reshape(-1)[idx]


def _explicit_alpha(blk):
    """DXT3 alpha: (nb, 8) -> (nb, 16)."""
    lo = blk & 0x0F; hi = blk >> 4
    a = np.stack([lo, hi], -1).reshape(blk.shape[0], 16)
    return (a * 17).astype(np.uint8)


def decode_bc(data, w, h, fmt):
    """Top-level mip of a BCn image. fmt: DXT1, DXT3, DXT5, BC4, BC5. data: bytes/array of the blocks."""
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    nb = bw * bh
    bs = 8 if fmt in ('DXT1', 'BC4') else 16
    blk = np.frombuffer(data, np.uint8, nb * bs).reshape(nb, bs)
    if fmt == 'DXT1':
        px = _colour_blocks(blk, True)
    elif fmt == 'DXT3':
        px = _colour_blocks(blk[:, 8:], False)
        px[:, :, 3] = _explicit_alpha(blk[:, :8])
    elif fmt == 'DXT5':
        px = _colour_blocks(blk[:, 8:], False)
        px[:, :, 3] = _alpha_blocks(blk[:, :8])
    elif fmt == 'BC4':
        a = _alpha_blocks(blk)
        px = np.stack([a, a, a, np.full_like(a, 255)], -1)
    elif fmt == 'BC5':
        x = _alpha_blocks(blk[:, :8]).astype(np.float32) / 127.5 - 1
        y = _alpha_blocks(blk[:, 8:]).astype(np.float32) / 127.5 - 1
        z = np.sqrt(np.clip(1 - x * x - y * y, 0, 1))
        px = np.stack([(x + 1) * 127.5, (y + 1) * 127.5, (z + 1) * 127.5, np.full_like(x, 255)], -1)
        px = np.clip(px + 0.5, 0, 255).astype(np.uint8)
    else:
        raise ValueError(fmt)
    img = _unblock(px, bw, bh, 4)
    return img[:h, :w]


# ------------------------------------------------------------------ DDS / DST
_FOURCC = {b'DXT1': 'DXT1', b'DXT2': 'DXT3', b'DXT3': 'DXT3', b'DXT4': 'DXT5', b'DXT5': 'DXT5',
           b'ATI1': 'BC4', b'BC4U': 'BC4', b'BC4S': 'BC4', b'ATI2': 'BC5', b'BC5U': 'BC5', b'BC5S': 'BC5',
           b'DST1': 'DST1', b'DST3': 'DST3', b'DST5': 'DST5'}
_DXGI = {71: 'DXT1', 72: 'DXT1', 74: 'DXT3', 75: 'DXT3', 77: 'DXT5', 78: 'DXT5', 80: 'BC4', 81: 'BC4',
         83: 'BC5', 84: 'BC5'}


def dds_info(data):
    if data[:4] != b'DDS ':
        raise ValueError('not a DDS')
    (size, flags, h, w, pitch, depth, mips) = struct.unpack_from('<7I', data, 4)
    pf_size, pf_flags, fourcc, bits, rm, gm, bm, am = struct.unpack_from('<II4s5I', data, 76)
    off = 128
    fmt = None
    if pf_flags & 4:
        if fourcc == b'DX10':
            dxgi = struct.unpack_from('<I', data, 128)[0]
            off += 20
            fmt = _DXGI.get(dxgi, 'DXGI%d' % dxgi)
            if dxgi in (28, 29):
                fmt, bits, rm, gm, bm, am = 'RAW', 32, 0xFF, 0xFF00, 0xFF0000, 0xFF000000
            elif dxgi in (87, 91):
                fmt, bits, rm, gm, bm, am = 'RAW', 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000
        else:
            fmt = _FOURCC.get(fourcc)
            if fmt is None:
                raise ValueError('unsupported DDS fourcc %r' % fourcc)
    else:
        fmt = 'RAW'
        if not (pf_flags & 1):      # no alpha
            am = 0
    return dict(width=w, height=h, mips=max(1, mips), format=fmt, offset=off, bits=bits,
                masks=(rm, gm, bm, am), pf_flags=pf_flags)


def _unshuffle_dst(fmt, body):
    """DST blocks (all mips, field-major) -> interleaved DXT blocks (all mips)."""
    body = np.frombuffer(body, np.uint8)
    if fmt == 'DST1':
        n = len(body) // 8
        ep, ix = body[:4 * n].reshape(n, 4), body[4 * n:8 * n].reshape(n, 4)
        return np.concatenate([ep, ix], 1).tobytes(), 'DXT1'
    n = len(body) // 16
    if fmt == 'DST3':
        a, ep, ix = body[:8 * n].reshape(n, 8), body[8 * n:12 * n].reshape(n, 4), body[12 * n:16 * n].reshape(n, 4)
        return np.concatenate([a, ep, ix], 1).tobytes(), 'DXT3'
    a0 = body[:2 * n].reshape(n, 2)
    ep = body[2 * n:6 * n].reshape(n, 4)
    a1 = body[6 * n:12 * n].reshape(n, 6)
    ix = body[12 * n:16 * n].reshape(n, 4)
    return np.concatenate([a0, a1, ep, ix], 1).tobytes(), 'DXT5'


def _mask_channel(px, mask):
    if not mask:
        return None
    shift = (mask & -mask).bit_length() - 1
    maxv = mask >> shift
    v = (px >> np.uint32(shift)) & np.uint32(maxv)
    return (v.astype(np.uint32) * 255 // maxv).astype(np.uint8)


def decode_dds(data):
    info = dds_info(data)
    w, h, fmt, off = info['width'], info['height'], info['format'], info['offset']
    body = data[off:]
    if fmt in ('DST1', 'DST3', 'DST5'):
        body, fmt = _unshuffle_dst(fmt, body)
    if fmt in ('DXT1', 'DXT3', 'DXT5', 'BC4', 'BC5'):
        return decode_bc(body, w, h, fmt)
    if fmt != 'RAW':
        raise ValueError('unsupported DDS format ' + fmt)
    bpp = max(8, info['bits']) // 8
    raw = np.frombuffer(body, np.uint8, w * h * bpp).reshape(h * w, bpp)
    px = np.zeros(h * w, np.uint32)
    for k in range(bpp):
        px |= raw[:, k].astype(np.uint32) << (8 * k)
    rm, gm, bm, am = info['masks']
    if info['pf_flags'] & 0x20000 or (rm and not gm and not bm):     # luminance (L8 / A8L8)
        l = _mask_channel(px, rm)
        a = _mask_channel(px, am) if am else np.full(h * w, 255, np.uint8)
        out = np.stack([l, l, l, a], -1)
    elif info['pf_flags'] & 2 and not (rm or gm or bm):               # A8 only
        a = _mask_channel(px, am)
        out = np.stack([np.full_like(a, 255)] * 3 + [a], -1)
    else:
        ch = [(_mask_channel(px, m) if m else np.zeros(h * w, np.uint8)) for m in (rm, gm, bm)]
        a = _mask_channel(px, am) if am else np.full(h * w, 255, np.uint8)
        out = np.stack(ch + [a], -1)
    return out.reshape(h, w, 4)


# ------------------------------------------------------------------ RLE2 / RLES
def rle_info(data):
    fourcc, ver, w, h, mips, unk = struct.unpack_from('<4s4sHHHH', data, 0)
    return dict(fourcc=fourcc, version=ver, width=w, height=h, mips=mips)


def decode_rle(data, want_mask=False):
    """RLE2/RLES (DXT5 or L8) -> RGBA array of the top mip; with want_mask=True returns (rgba, mask or None)."""
    fourcc, ver, w, h, mips, _ = struct.unpack_from('<4s4sHHHH', data, 0)
    rles = ver == b'RLES'
    l8 = fourcc == b'L8  '
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    nb = bw * bh
    if l8:
        cmd0, off0 = struct.unpack_from('<2i', data, 16)
        cmd_end = struct.unpack_from('<i', data, 16 + 8)[0] if mips > 1 else off0
        cmds = np.frombuffer(data, '<u2', (cmd_end - cmd0) // 2, cmd0)
        ops = np.repeat((cmds & 3).astype(np.uint8), (cmds >> 2).astype(np.int64))[:nb]
        blocks = np.zeros((nb, 16), np.uint8)
        blocks[ops == 2] = 255
        n1 = int((ops == 1).sum())
        blocks[ops == 1] = np.frombuffer(data, np.uint8, 16 * n1, off0).reshape(n1, 16)
        l = _unblock(blocks[:, :, None], bw, bh, 1)[:h, :w, 0]
        out = np.stack([l, l, l, np.full_like(l, 255)], -1)
        return (out, None) if want_mask else out
    nh = 6 if rles else 5
    heads = [struct.unpack_from('<%di' % nh, data, 16 + 4 * nh * i) for i in range(mips)]
    cmd_off, o2, o3, o0, o1 = heads[0][:5]
    o4 = heads[0][5] if rles else None
    cmd_end = heads[1][0] if mips > 1 else o2
    cmds = np.frombuffer(data, '<u2', (cmd_end - cmd_off) // 2, cmd_off)
    ops = np.repeat((cmds & 3).astype(np.uint8), (cmds >> 2).astype(np.int64))
    if len(ops) < nb:
        ops = np.concatenate([ops, np.zeros(nb - len(ops), np.uint8)])
    ops = ops[:nb]
    has_col = ops != 0
    has_alpha = (ops != 0) if rles else (ops == 1)
    nc, na = int(has_col.sum()), int(has_alpha.sum())
    blk = np.zeros((nb, 16), np.uint8)
    # op 0: transparent (alpha palette 0/5, all index 0); RLE2 colour white, RLES black
    blk[:, 1] = 5
    if not rles:
        blk[:, 8:10] = 0xFF
    # op 2 in RLE2: opaque alpha (indices all 7 with a0=0,a1=5 -> 255)
    if not rles:
        op2 = ops == 2
        blk[op2, 2:8] = 0xFF
    blk[has_col, 8:10] = 0
    blk[has_col, 8:12] = np.frombuffer(data, np.uint8, 4 * nc, o2).reshape(nc, 4)
    blk[has_col, 12:16] = np.frombuffer(data, np.uint8, 4 * nc, o3).reshape(nc, 4)
    blk[has_alpha, 0:2] = np.frombuffer(data, np.uint8, 2 * na, o0).reshape(na, 2)
    blk[has_alpha, 2:8] = np.frombuffer(data, np.uint8, 6 * na, o1).reshape(na, 6)
    px = _colour_blocks(blk[:, 8:], False)
    px[:, :, 3] = _alpha_blocks(blk[:, :8])
    out = _unblock(px, bw, bh, 4)[:h, :w]
    if not want_mask:
        return out
    mask = None
    if rles:
        m = np.zeros((nb, 16), np.uint8)
        m[ops == 2] = 255
        n1 = int((ops == 1).sum())
        m[ops == 1] = np.frombuffer(data, np.uint8, 16 * n1, o4).reshape(n1, 16)
        mask = _unblock(m[:, :, None], bw, bh, 1)[:h, :w, 0]
    return out, mask


# ------------------------------------------------------------------ LRLE
def lrle_info(data):
    magic, ver, w, h, mips = struct.unpack_from('<4sIHHI', data, 0)
    return dict(version=ver, width=w, height=h, mips=mips)


def _assemble(counts, bases, rels, steps, sources, npx):
    """Runs -> (npx, 4) pixels. Run k covers counts[k] pixels read from sources[bases[k]] (a flat uint8 array) at
    byte offset rels[k] + steps[k] * i."""
    counts = np.asarray(counts, np.int64)
    total = int(counts.sum())
    first = np.cumsum(counts) - counts
    base_off = np.cumsum([0] + [len(s) for s in sources])[:-1]
    start = np.asarray(rels, np.int64) + base_off[np.asarray(bases, np.intp)]
    local = np.arange(total, dtype=np.int64) - np.repeat(first, counts)
    off = np.repeat(start, counts) + np.repeat(np.asarray(steps, np.int64), counts) * local
    flat = np.concatenate(sources)
    px = flat[off[:, None] + np.arange(4)]
    out = np.zeros((npx, 4), np.uint8)
    out[:min(npx, total)] = px[:npx]
    return out


def _varints(mv, ranges):
    """Decode the 7-bit little-endian varints stored in the byte ranges [(s, e), ...] of mv, in order."""
    s = np.array([r[0] for r in ranges], np.int64)
    e = np.array([r[1] for r in ranges], np.int64)
    lens = e - s
    first = np.cumsum(lens) - lens
    bidx = np.repeat(s - first, lens) + np.arange(int(lens.sum()), dtype=np.int64)
    b = mv[bidx].astype(np.int64)
    term = b < 0x80
    vstart = np.concatenate([[0], np.flatnonzero(term)[:-1] + 1])
    vid = np.cumsum(np.concatenate([[0], term[:-1]]))
    pos = np.arange(len(b)) - vstart[vid]
    return np.add.reduceat((b & 0x7F) << (7 * pos), vstart)


def _lrle_v2(mip, palette, npx):
    mv = np.frombuffer(mip, np.uint8)
    term = mv < 0x80
    tpos = np.flatnonzero(term).tolist()
    cum = np.cumsum(term).tolist()
    counts, bases, rels, steps, ranges = [], [], [], [], []
    ca, ba, ra, sa = counts.append, bases.append, rels.append, steps.append
    q, n, o = 0, len(mip), 0
    while q < n and o < npx:
        b = mip[q]
        if b & 1:
            c = (b & 0x7F) >> 2
            if b & 0x80:
                sh = 5
                while True:
                    q += 1; b2 = mip[q]; c += (b2 & 0x7F) << sh; sh += 7
                    if not b2 & 0x80:
                        break
            q += 1
            if b & 2:                        # op 3: raw BGRA pixels
                ca(c); ba(1); ra(q); sa(4); q += 4 * c
            else:                            # op 1: run of varint palette indices
                e = tpos[cum[q - 1] + c - 1]
                ca(c); ba(2); ra(0); sa(4)   # placeholder, filled from the decoded indices below
                ranges.append((q, e + 1)); q = e + 1
        else:
            c = (b & 0x7F) >> 3
            if b & 0x80:
                sh = 4
                while True:
                    q += 1; b2 = mip[q]; c += (b2 & 0x7F) << sh; sh += 7
                    if not b2 & 0x80:
                        break
            q += 1
            op = b & 7
            if op == 6:                      # repeat one raw pixel
                ca(c); ba(1); ra(q); sa(0); q += 4
            elif op == 2:                    # repeat palette colour, 1-byte index
                ca(c); ba(0); ra(4 * mip[q]); sa(0); q += 1
            elif op == 4:                    # repeat palette colour, 2-byte index
                ca(c); ba(0); ra(4 * (mip[q] | (mip[q + 1] << 8))); sa(0); q += 2
            else:
                raise ValueError('LRLE: unknown op 0x%02X at %d' % (b, q))
        o += c
    idx = _varints(mv, ranges) if ranges else np.zeros(0, np.int64)
    # index runs read from a third source: the palette colours of all decoded indices, in order
    pal_sel = palette[np.minimum(idx, len(palette) - 1)].ravel() if len(idx) else np.zeros(4, np.uint8)
    counts_a = np.asarray(counts, np.int64)
    is_idx = np.asarray(bases) == 2
    rels_a = np.asarray(rels, np.int64)
    rels_a[is_idx] = 4 * (np.cumsum(np.where(is_idx, counts_a, 0)) - counts_a)[is_idx]
    return _assemble(counts_a, bases, rels_a, steps, [palette.ravel(), mv, pal_sel], npx)


def _lrle_v0(mip, npx):
    mv = np.frombuffer(mip, np.uint8)
    counts, bases, rels, steps = [], [], [], []
    extra = bytearray()
    q, n, o = 0, len(mip), 0
    while q < n and o < npx:
        b = mip[q]
        op = b & 3
        if op == 1:                          # raw pixels, count in 6 bits
            c = b >> 2; q += 1
            counts.append(c); bases.append(1); rels.append(q); steps.append(4); q += 4 * c
        elif op == 0 or op == 2:             # zeros / repeat one pixel
            c = (b & 0x7F) >> 2
            if b & 0x80:
                sh = 5
                while True:
                    q += 1; b2 = mip[q]; c += (b2 & 0x7F) << sh; sh += 7
                    if not b2 & 0x80:
                        break
            q += 1
            if op == 2:
                counts.append(c); bases.append(1); rels.append(q); steps.append(0); q += 4
            else:
                counts.append(c); bases.append(0); rels.append(0); steps.append(0)
        else:                                # planar per-channel RLE
            c = b >> 2; q += 1
            res = bytearray(4 * c); r = 0
            while r < 4 * c:
                b2 = mip[q]
                if b2 & 1:
                    k = (b2 & 0x7F) >> 1
                    if b2 & 0x80:
                        q += 1; k += mip[q] << 6
                    q += 1
                    res[r:r + k] = mip[q:q + k]; r += k; q += k
                elif b2 & 2:
                    k = (b2 & 0x7F) >> 2
                    if b2 & 0x80:
                        q += 1; k += mip[q] << 5
                    q += 1
                    res[r:r + k] = bytes([mip[q]]) * k; r += k; q += 1
                else:
                    k = (b2 & 0x7F) >> 2
                    if b2 & 0x80:
                        q += 1; k += mip[q] << 5
                    r += k; q += 1
            px = np.frombuffer(bytes(res[:4 * c]), np.uint8).reshape(4, c).T
            counts.append(c); bases.append(2); rels.append(len(extra)); steps.append(4)
            extra += px.tobytes()
        o += c
    extra_src = np.frombuffer(bytes(extra), np.uint8) if extra else np.zeros(4, np.uint8)
    return _assemble(counts, bases, rels, steps, [np.zeros(4, np.uint8), mv, extra_src], npx)


def decode_lrle(data, mip_level=0):
    magic, ver, w, h, mips = struct.unpack_from('<4sIHHI', data, 0)
    if magic != b'LRLE':
        raise ValueError('not LRLE')
    offs = struct.unpack_from('<%dI' % mips, data, 16)
    p = 16 + 4 * mips
    palette = None
    if ver == 0x32303056:            # 'V002'
        npal = struct.unpack_from('<I', data, p)[0]
        palette = np.frombuffer(data, np.uint8, 4 * npal, p + 4).reshape(npal, 4)
        p += 4 + 4 * npal
    start = p + offs[mip_level]
    end = p + offs[mip_level + 1] if mip_level + 1 < mips else len(data)
    mip = data[start:end]
    mw, mh = max(1, w >> mip_level), max(1, h >> mip_level)
    npx = mw * mh
    out = _lrle_v2(mip, palette, npx) if palette is not None else _lrle_v0(mip, npx)
    bw, bh = max(1, mw // 4), max(1, mh // 4)
    img = _unblock(out[:bw * bh * 16].reshape(bw * bh, 16, 4), bw, bh, 4)
    return img[:, :, [2, 1, 0, 3]]           # BGRA -> RGBA


# ------------------------------------------------------------------ front door
def kind(data):
    if data[:4] == b'DDS ':
        return 'DDS'
    if data[:4] == b'LRLE':
        return 'LRLE'
    if data[4:8] in (b'RLE2', b'RLES'):
        return data[4:8].decode()
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'PNG'
    if data[:3] == b'\xff\xd8\xff':
        return 'JPG'
    return None


def decode(data):
    """Any supported Sims 4 image resource -> (H, W, 4) uint8 RGBA."""
    k = kind(data)
    if k == 'DDS':
        return decode_dds(data)
    if k == 'LRLE':
        return decode_lrle(data)
    if k in ('RLE2', 'RLES'):
        return decode_rle(data)
    if k in ('PNG', 'JPG'):
        from PIL import Image
        return np.asarray(Image.open(io.BytesIO(data)).convert('RGBA'))
    raise ValueError('unknown image format: %r' % data[:8])


def to_image(data):
    from PIL import Image
    return Image.fromarray(decode(data), 'RGBA')


def describe(data):
    k = kind(data)
    if k == 'DDS':
        i = dds_info(data)
        return 'DDS %s %dx%d mips=%d' % (i['format'], i['width'], i['height'], i['mips'])
    if k == 'LRLE':
        i = lrle_info(data)
        return 'LRLE v%s %dx%d mips=%d' % ('2' if i['version'] else '0', i['width'], i['height'], i['mips'])
    if k in ('RLE2', 'RLES'):
        i = rle_info(data)
        return '%s %s %dx%d mips=%d' % (k, i['fourcc'].decode().strip(), i['width'], i['height'], i['mips'])
    return str(k)

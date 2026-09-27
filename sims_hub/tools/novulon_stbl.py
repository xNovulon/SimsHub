"""Write a Sims 4 string table (STBL) resource, DBPF type 0x220557DA.

Byte layout verified against `mc_cmd_center.package`'s own STBL resource (`build_plan.md` §2b, dumped
header hex `53 54 42 4c 05 00 00 50 03 00 00 00 00 00 00 00 00 34 4e 00 00`):

    'STBL' + version(u16, =5) + compressed(u8, =0) + numEntries(u64) + reserved(u16) + stringLen(u32)
    then per entry: key(u32 LE) + flags(u8, =0) + len(u16 LE) + utf8 bytes

No STBL writer exists anywhere in this repo (only readers: `wicked_animator/backend/doctor.py:_stbl()`,
`gamedata.py:_stbl()`, `wwlists.py:_stbl()`, `posepack.py:read_stbl()`) - this is new code, matching that
already-trusted byte layout, not a copy of any of those readers. English-only for V1 (`gaps.md` §B.3: no
automatic locale fallback, so a non-English client would render blank strings, not English ones - a
documented limitation, not an oversight).
"""
import struct

VERSION = 5
LOCALE_ENGLISH = 0x00


def build_stbl(strings):
    """{key(u32): text} -> STBL bytes. Keys are masked to 32 bits; text is encoded as UTF-8."""
    body = bytearray()
    total = 0
    for key, text in strings.items():
        b = str(text).encode('utf-8')
        if len(b) > 0xFFFF:
            raise ValueError('string for key 0x%08X is too long for a u16 length (%d bytes)' % (key & 0xFFFFFFFF, len(b)))
        body += struct.pack('<IBH', key & 0xFFFFFFFF, 0, len(b)) + b
        total += len(b) + 1          # +1: the game's own writer counts a trailing NUL per string
    header = b'STBL' + struct.pack('<HBQHI', VERSION, 0, len(strings), 0, total)
    return header + bytes(body)


def read_stbl(data):
    """STBL bytes -> {key: text}. For round-trip tests only; never shipped as part of the mod itself."""
    if data[:4] != b'STBL':
        raise ValueError('not a string table (missing STBL magic)')
    version, compressed = struct.unpack_from('<HB', data, 4)
    if version != VERSION or compressed:
        raise ValueError('unsupported STBL version %d / compressed %d' % (version, compressed))
    n = struct.unpack_from('<Q', data, 7)[0]
    off, out = 21, {}
    for _ in range(n):
        key, flags, length = struct.unpack_from('<IBH', data, off)
        off += 7
        out[key] = data[off:off + length].decode('utf-8', 'replace')
        off += length
    return out

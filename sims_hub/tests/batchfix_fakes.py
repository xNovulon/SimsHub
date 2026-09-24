"""Synthetic CAS parts and sliders for the batch-fix tests, written byte by byte in the game's own layout
(speedkit/batchfix.py's docstring; TS4SimRipper CASP.cs and CmarNYC's HOTC.cs), plus packages holding them."""
import os
import struct

from speedkit.dbpf import PackageWriter

T_CASP = 0x034AEECB
T_HOTC = 0x8B18FF6E
T_OBJD = 0xC0DB5AE7
CC_ID = 0x9A3B5C7D11223344           # a CC-sized CAS part id (above 2^32)
EA_ID = 0x0000000000012345           # an EA-sized id: a default replacement


def casp(version=0x2E, flags=0, flags2=0, body_type=6, age_gender=0x3078, species=1, occult=0, name='cc_part',
         ntags=2, colors=2, materials=True, tail=64):
    """One CAS part resource. Every field the detectors skip over gets a real value, so a wrong skip shows."""
    nm = name.encode('utf-16-be')
    b = bytearray()
    b += bytes([len(nm)]) + nm
    b += struct.pack('<fHII', 1.0, 3, 7, 0xDEADBEEF) + bytes([flags])
    if version >= 39:
        b += bytes([flags2])
    if version >= 50:
        b += struct.pack('<H', 5)
    if version >= 51:
        b += struct.pack('<i', 2) + struct.pack('<QQ', 1, 2)
    else:
        b += struct.pack('<Q', 1) + (struct.pack('<Q', 2) if version >= 41 else b'')
    b += struct.pack('<Q', 3) if version >= 37 else struct.pack('<I', 3)
    b += struct.pack('<i', ntags)
    for k in range(ntags):
        b += struct.pack('<HI', 1, 100 + k) if version >= 37 else struct.pack('<HH', 1, 100 + k)
    b += struct.pack('<III', 0, 0x1111, 0x2222) + (struct.pack('<I', 0x3333) if version >= 43 else b'') + b'\x00'
    b += struct.pack('<III', body_type, 8, age_gender)
    if version >= 32:
        b += struct.pack('<I', species)
    if version >= 34:
        b += struct.pack('<HB', 0, 0) + b'\0' * 9
    else:
        b += b'\x01\x00'
    b += bytes([colors]) + b''.join(struct.pack('<I', 0xFF336699) for _ in range(colors))
    b += b'\x00\x01'
    if version >= 28:
        b += struct.pack('<Q', 0xABCDEF)
    if version >= 30:
        b += (b'\x03' + struct.pack('<III', 1, 2, 3)) if materials else b'\x00'
    if version >= 31:
        b += struct.pack('<I', occult)
    b += b'\0' * tail
    return struct.pack('<III', version, len(b) + 3, 0) + bytes(b)      # key list: the last byte (count 0)


def hotc(version=0x0F):
    """A HotSpotControl (slider) resource: u32 version, age/frame, species, [v15+] u32, then the rest."""
    body = struct.pack('<III', version, 0x3078, 1)
    if version >= 0x0F:
        body += struct.pack('<I', 0)
    return body + bytes([1, 2, 3]) + struct.pack('<IIB', 4, 0, 0) + struct.pack('<QI', 0, 0) + b'\x00'


def package(path, resources):
    """resources: [(type, instance, bytes)] -> a .package at path (zlib-compressed like S4S writes them)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        for t, i, data in resources:
            w.add((t, 0, i), data)
    return path

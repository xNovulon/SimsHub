"""usedpack - a lean pack holding only the CC the user's sims and lots actually use.

A light profile can then load a few GB instead of the whole 259 GB library while every sim keeps
its look. Four steps, each usable on its own:

    refs = scan_references()             # what the saves and Tray reference (cached, incremental)
    game = load_game_ids()               # which ids are EA's own (cached in data/game_ids.sqlite)
    p = plan(Library(), refs)            # which library resources the pack needs, and from where
    build(p, out_dir, dry_run=False)     # copy them bit-exact into SpeedKit_UsedCC_###.package
    verify(out_dir, refs); is_stale(out_dir)

Facts this module relies on (research/research_results.json 'usedcc' and research/usedcc/*):
  * Saves are DBPF packages. Resource 0x0D is SaveGameData, 0x06 is ZoneObjectData (lot objects);
    0x0F/0x10/0x14/0xE88DB35F are images. Tray .householdbinary holds a protobuf whose field 1 is
    AccountFamilyData (header: u32 version, then v0/v1 u32 length + message at 8, v2 u32 length at 12
    + message at 16). .trayitem is TrayMetadata at offset 8. .blueprint/.room are an undecoded
    framed format; only the ObjectData.guid tag (bytes F0 01 + varint) is scanned there.
  * The protobuf schemas come from the game (Game/Bin/Python/generated.zip). The walker reads the
    wire format with no schema and recurses into every blob that parses cleanly, so ids are found
    wherever they sit (occult forms, mannequins, matchmaking NPCs...). A value is given a meaning by
    the field-number path that leads to it (PATTERNS below). OutfitData.parts is an IdList whose ids
    are PACKED FIXED64. The research cross-checked this walk against a real schema parse: 0 misses.
  * CASP (0x034AEECB): u32 at offset 4 plus 8 is where its resource-key list starts: a u8 count, then
    count x 16 bytes (u64 instance, u32 group, u32 type) running to the end of the resource.
    Verified 2,025/2,025. Entry 0 is usually a null key.
  * THUM (0x3C1AF1F2) CAS thumbnails use the CASP instance (groups 1, 2, 0x101, 0x102).
  * TONE refers to its textures by instance only (RLE2/LRLE/DST 0xB6C8B6A0). SMOD/sculpts refer to
    BGEO/DMAP/BOND by full key; OBJD stores keys as (u32 instance-high, u32 instance-low, type, group),
    MODL/MLOD as (instance, type, group).
  * A CASP key that is missing often exists under another group, or as LRLE where the CASP says RLE2;
    the research used those fallbacks and so does plan().
  * Within one Resource.cfg priority the FIRST loaded copy of a key wins, so for a key with several
    copies the pack takes the copy that comes first in Library.load_order().
  * A mod resource with the exact key of an EA resource replaces it for the whole game (a "default
    replacement"). 21,009 library resources override EA keys (research verdicts), 3,448 of them RLES
    speculars; the worn EA parts list 1,054 of them (65 MB, e.g. Mods_parked/scripts/00s.package).
    plan() reads the worn EA parts and looks from the game (LOC_TYPES locations in the game cache)
    and packs those library copies, so a sim in EA clothes looks the same as with the whole library.
  * EA's CASP/OBJD ids are all below 2^32; CC ids are 64-bit. An id >= 2^32 that is neither in the
    library nor in the game is CC that is not installed anywhere.
  * Pet coats: SimData.pelt_layers(63).layers(1).layer_id(1) are type 0x26AF8338 resources (all 139
    pelt ids in the research's saves are game 0x26AF8338). This library holds none, but CC pelts
    are packed like skin tones when present.
  * Not decoded (known limits): lot architecture blobs (walls/floors/terrain paint) and Tray
    blueprints. plan() therefore adds every CC wall and floor (CWAL/CFLR, tiny) as a safety net.
  * Save/Tray files are fingerprinted by their whole content (a re-save can keep a package's layout
    while ids inside change); the game's backup rotation is a rename that keeps size and mtime, so a
    renamed file takes its fingerprint over without being read again.
  * Python's open() on Windows does not share delete access: while it holds a file, nobody can rename
    it. The game's save rotation (Slot.save -> .ver0) then fails, and the other tool's shutil.move of
    a package copies it, cannot delete the original and stops - leaving it in BOTH Mods and
    Mods_parked. So every save, Tray and library file is opened with _open_read (FILE_SHARE_DELETE),
    and a save is read into memory in one go and closed before it is parsed.

Nothing here writes to the saves, Tray, Mods or the game. build() is the only writer: it writes into
out_dir (default SIMS/SpeedKit/usedpack) through a Journal, so a build can be undone; a build that
fails half-way is rolled back.
"""
import array
import collections
import hashlib
import io
import json
import multiprocessing
import os
import shutil
import sqlite3
import struct
import time

import numpy as np

from .dbpf import PackageWriter, DBPFError, read_entries, decompress, DELETED
from .library import SIMS, Library, game_running, signed64, unsigned64
from .journal import Journal, JournalError, undo

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVES = os.path.join(SIMS, 'saves')
TRAY = os.path.join(SIMS, 'Tray')
GAME_DIR = r'E:\The Sims 4'
DEFAULT_REFS_DB = os.path.join(PROJECT, 'data', 'used_refs.sqlite')
DEFAULT_GAME_DB = os.path.join(PROJECT, 'data', 'game_ids.sqlite')
DEFAULT_OUT = os.path.join(SIMS, 'SpeedKit', 'usedpack')
PACK_NAME = 'SpeedKit_UsedCC_%03d.package'
MANIFEST = 'usedpack.json'
KEYS_FILE = 'usedpack_keys.tsv'
FREE_MARGIN = 1 << 30            # build() keeps at least 1 GiB free on the Sims 4 drive
MAX_PACKAGE_LIMIT = (1 << 31) - 1  # packages past 2 GiB were never loaded in-game (research verdicts, loadorder 13)

BIG = 1 << 32
M64 = (1 << 64) - 1

# ------------------------------------------------------------------------------------------ types
T_CASP, T_THUM, T_TONE = 0x034AEECB, 0x3C1AF1F2, 0x0354796A
T_OBJD, T_COBJ, T_STBL, T_OTHM = 0xC0DB5AE7, 0x319E4F1D, 0x220557DA, 0x3C2A8647
T_GEOM, T_RLE2, T_LRLE, T_RLES = 0x015A1849, 0x3453CF95, 0x2BC04EDF, 0xBA856C78
T_IMG, T_DST, T_RMAP, T_BOND = 0x00B2D882, 0xB6C8B6A0, 0xAC16FBEC, 0x0355E0A6
T_SCUL, T_SMOD, T_BGEO, T_DMAP, T_HSC = 0x9D1AB874, 0xC5F6763E, 0x067CAA11, 0xDB43E069, 0x8B18FF6E
T_MODL, T_MLOD, T_FTPT, T_RSLT, T_LITE, T_RIG, T_MATD = (0x01661233, 0x01D10F34, 0xD382BF57, 0xD3044521,
                                                          0x03B4C61D, 0x8EAF13DE, 0x01D0E75D)
T_OBJ_TUNING, T_SIMDATA = 0xB61DE6B4, 0x545AC67A
T_CWAL, T_CFLR = 0xD5F0F921, 0xB4F762C9
T_PELT = 0x26AF8338          # pet coat layer (all 139 pelt ids in the research's saves are game 0x26AF8338)

TYPE_NAMES = {T_CASP: 'CASP', T_THUM: 'THUM', T_TONE: 'TONE', T_OBJD: 'OBJD', T_COBJ: 'COBJ', T_STBL: 'STBL',
              T_OTHM: 'OTHM', T_GEOM: 'GEOM', T_RLE2: 'RLE2', T_LRLE: 'LRLE', T_RLES: 'RLES', T_IMG: '_IMG',
              T_DST: 'DST', T_RMAP: 'RMAP', T_BOND: 'BOND', T_SCUL: 'SCUL', T_SMOD: 'SMOD', T_BGEO: 'BGEO',
              T_DMAP: 'DMAP', T_HSC: 'HSC', T_MODL: 'MODL', T_MLOD: 'MLOD', T_FTPT: 'FTPT', T_RSLT: 'RSLT',
              T_LITE: 'LITE', T_RIG: 'RIG', T_MATD: 'MATD', T_OBJ_TUNING: 'OBJ_TUNING', T_SIMDATA: 'SIMDATA',
              T_CWAL: 'CWAL', T_CFLR: 'CFLR', T_PELT: 'PELT'}

TEXTURES = (T_RLE2, T_LRLE, T_RLES, T_IMG, T_DST)
CASP_REF_TYPES = {T_GEOM, T_RLE2, T_LRLE, T_RLES, T_IMG, T_DST, T_RMAP, T_BOND, T_BGEO, T_DMAP}
LOOK_REF_TYPES = {T_BGEO, T_DMAP, T_BOND, T_HSC, T_RMAP, T_GEOM, T_SMOD} | set(TEXTURES)
OBJECT_REF_TYPES = {T_MODL, T_MLOD, T_FTPT, T_RSLT, T_LITE, T_RIG, T_MATD, T_OTHM, T_GEOM} | set(TEXTURES)
OBJECT_CONTAINERS = {T_OBJD, T_COBJ, T_MODL, T_MLOD, T_RSLT, T_FTPT, T_LITE, T_RIG, T_MATD}
SURFACE_REF_TYPES = {T_MATD, T_THUM, T_OTHM} | set(TEXTURES)
# catalog first, then small data, then meshes and textures (EA keeps catalog data together the same way)
TYPE_RANK = {T_CASP: 0, T_THUM: 1, T_TONE: 2, T_OBJD: 3, T_COBJ: 4, T_STBL: 5}
BULK_TYPES = {T_GEOM, T_RLE2, T_LRLE, T_RLES, T_IMG, T_DST, T_MLOD, T_MODL, T_BGEO, T_DMAP}


def tname(t):
    """Short name of a resource type (hex when unknown)."""
    return TYPE_NAMES.get(t, '%08X' % t)


# ------------------------------------------------------------------------------------------ file access
if os.name == 'nt':
    import ctypes
    import msvcrt
    from ctypes import wintypes
    _K32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _K32.CreateFileW.restype = wintypes.HANDLE
    _K32.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    _K32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _INVALID_HANDLE = wintypes.HANDLE(-1).value
    _GENERIC_READ, _SHARE_ALL, _OPEN_EXISTING, _NORMAL = 0x80000000, 0x7, 3, 0x80


def _open_read(path):
    """open(path, 'rb'), except that other programs may rename, move or delete the file meanwhile.

    On Windows the file is opened with FILE_SHARE_DELETE (Python's open() leaves it out), so the game
    can rotate a save SpeedKit is reading and the other tool can move a package SpeedKit is copying;
    the handle keeps reading the same file after a rename."""
    if os.name != 'nt':
        return open(path, 'rb')
    h = _K32.CreateFileW(os.path.abspath(path), _GENERIC_READ, _SHARE_ALL, None, _OPEN_EXISTING, _NORMAL, None)
    if h is None or h == _INVALID_HANDLE:
        err = ctypes.get_last_error()
        raise OSError(None, ctypes.FormatError(err), path, err)     # FileNotFoundError etc. by winerror
    try:
        fd = msvcrt.open_osfhandle(h, os.O_RDONLY | os.O_BINARY)
    except Exception:
        _K32.CloseHandle(h)
        raise
    try:
        return os.fdopen(fd, 'rb')
    except Exception:
        os.close(fd)
        raise


def _read_file(path):
    """The whole file as bytes; the handle is open only while it is read."""
    with _open_read(path) as f:
        return f.read()


# ------------------------------------------------------------------------------------------ categories
PART, PART_OTHER, TONE, SCULPT, MODIFIER, PELT, OBJECT, OBJECT_TAG30 = (
    'cas_part', 'cas_other', 'tone', 'sculpt', 'modifier', 'pelt', 'object', 'object_tag30')
CATEGORIES = (PART, PART_OTHER, TONE, SCULPT, MODIFIER, PELT, OBJECT, OBJECT_TAG30)
LOOK_CATS = ((TONE, T_TONE), (SCULPT, T_SCUL), (MODIFIER, T_SMOD), (PELT, T_PELT))   # sim looks besides parts

# Field-number paths (protobuf field numbers from the game's own .proto files) whose values have a
# known meaning. A pattern matches the END of a value's path; a trailing 8 / 0 marks an element of a
# packed fixed64 / packed varint list. A pattern that starts with a root marker ('RD' = SaveGameData
# resource 0x0D, 'hh' = Tray household) only matches from the root: shorter suffixes of those paths
# also occur elsewhere and picked up tens of thousands of unrelated values in a test save.
PATTERNS = [
    # worn CAS parts: OutfitList(21).outfits(1).parts(5)=IdList .ids(1), packed fixed64 (or unpacked).
    # OutfitList is field 21 of SimData, MannequinSimData, OccultSimData and MatchmakingCandidateData.
    ((21, 1, 5, 1, 8), PART), ((21, 1, 5, 1), PART),
    # GeneticData.parts_list(5) / growth_parts_list(6) .parts(1).id(1), in SimData.genetic_data(28)
    # and OccultSimData.genetic_data(17) (occult_sim_infos is field 3 of the occult tracker)
    ((28, 5, 1, 1), PART), ((28, 6, 1, 1), PART), ((3, 17, 5, 1, 1), PART), ((3, 17, 6, 1, 1), PART),
    # CAS part ids outside outfits (the research's 223 "inventory / custom colour" ids)
    (('RD', 5, 25, 1, 1), PART_OTHER),   # SaveGameData.households(5).reward_inventory(25).reward_parts(1).part_id(1)
    (('hh', 1, 21, 1, 1), PART_OTHER),   # Tray: AccountFamilyData(1).reward_inventory(21).reward_parts(1).part_id(1)
    # HouseholdData.cas_inventory(17) is 'repeated uint64 [packed=true]' in the game's schema, so it is
    # written as a packed list (marker 0); the unpacked form is kept for old writers
    (('RD', 5, 17, 0), PART_OTHER), (('RD', 5, 17), PART_OTHER),
    (('RD', 2, 8, 43, 1, 0), PART_OTHER), (('RD', 2, 8, 43, 1), PART_OTHER),  # fashion_trend_service.thrift_store_inventory
    (('RD', 19, 1, 1, 3), PART_OTHER),   # custom_colors(19).color_mapping(1).part_id(1)=ResourceKey .instance(3)
    # skin tones: SimData.skin_tone(10) (sims are field 6 in saves and in Tray households),
    # SimList.sims(1), MannequinSimData(15).skin_tone(13), OccultSimData.skin_tone(16), matchmaking NPCs,
    # the thrift store mannequin (fashion_trend_service(43).thrift_store_mannequin(2).skin_tone(13))
    ((6, 10), TONE), ((1, 1, 10), TONE), ((15, 13), TONE), ((17, 3, 16), TONE), ((53, 2, 14), TONE),
    ((43, 2, 13), TONE),
    # pet coats: SimData.pelt_layers(63).layers(1).layer_id(1)
    ((6, 63, 1, 1), PELT),
    # ObjectList.objects(1).guid(30) = object definition id (lots, streets, sim/household/object
    # inventories). Not SaveGameData.object_fallbacks: its guid is an object INSTANCE id (sequential
    # 64-bit numbers; 50 of them collide with a creator's sequential CC ids in a test save).
    ((1, 30), OBJECT),
]
# BlobSimFacialCustomizationData: sculpts(1) repeated uint64, face/body/aged modifiers(2..5).key(1).
# It sits in SimData.facial_attr(18), MannequinSimData(15) / OccultSimData(3) .facial_attributes(12),
# matchmaking_service(53).existing_npc_data(2).facial_attributes(13), the thrift store mannequin
# (43, 2, 12) and GeneticData(28 / occult 17).sculpts_and_mods_attr(1).
for _blob in ((18,), (15, 12), (3, 12), (53, 2, 13), (43, 2, 12), (28, 1), (3, 17, 1)):
    PATTERNS += [(_blob + (1, 0), SCULPT), (_blob + (1,), SCULPT)]
    PATTERNS += [(_blob + (k, 1), MODIFIER) for k in (2, 3, 4, 5)]

# Reversed-path trie: _TRIE[last][previous]...['$'] = [categories]. Matching a value costs a dict
# lookup or two instead of a suffix comparison per pattern.
_TRIE = {}
for _pat, _cat in PATTERNS:
    _node = _TRIE
    for _step in reversed(_pat):
        _node = _node.setdefault(_step, {})
    _node.setdefault('$', []).append(_cat)
SCANNER_VERSION = '2:' + hashlib.blake2b(repr(PATTERNS).encode(), digest_size=6).hexdigest()

PACKED_MAX = 1 << 16
MAX_DEPTH = 40
SAVE_IMAGE_TYPES = {0x0F, 0x10, 0x14, 0xE88DB35F}
TRAY_KINDS = {'.householdbinary': 'household', '.trayitem': 'trayitem', '.blueprint': 'lot', '.room': 'lot'}

_Q = struct.Struct('<Q').unpack_from
_I = struct.Struct('<I').unpack_from


# ------------------------------------------------------------------------------------------ protobuf walk
def parse_message(b, start=0, end=None):
    """Fields of b[start:end] as [(field, wiretype, value)] if it is a clean protobuf message, else None.

    value is an int for varint / fixed64 / fixed32 fields and (start, end) for length-delimited ones."""
    n = len(b) if end is None else end
    p = start
    out = []
    add = out.append
    while p < n:
        key = shift = 0
        while True:
            if p >= n or shift > 63:
                return None
            c = b[p]
            p += 1
            key |= (c & 0x7F) << shift
            if c < 0x80:
                break
            shift += 7
        f, wt = key >> 3, key & 7
        if f == 0 or f > 536870911:
            return None
        if wt == 0 or wt == 2:
            v = shift = 0
            while True:
                if p >= n or shift > 63:
                    return None
                c = b[p]
                p += 1
                v |= (c & 0x7F) << shift
                if c < 0x80:
                    break
                shift += 7
            if wt == 0:
                add((f, 0, v & M64))
            else:
                if p + v > n:
                    return None
                add((f, 2, (p, p + v)))
                p += v
        elif wt == 1:
            if p + 8 > n:
                return None
            add((f, 1, _Q(b, p)[0]))
            p += 8
        elif wt == 5:
            if p + 4 > n:
                return None
            add((f, 5, _I(b, p)[0]))
            p += 4
        else:
            return None
    return out


def parse_packed(b, start, end):
    """A packed varint list b[start:end] as a list of ints, or None if it is not one."""
    out = []
    p = start
    while p < end:
        v = shift = 0
        while True:
            if p >= end or shift > 63:
                return None
            c = b[p]
            p += 1
            v |= (c & 0x7F) << shift
            if c < 0x80:
                break
            shift += 7
        out.append(v & M64)
    return out


def match(path, last):
    """Categories of the PATTERNS that path + (last,) ends with (None if none)."""
    node = _TRIE.get(last)
    out = None
    k = len(path) - 1
    while node is not None:
        cats = node.get('$')
        if cats:
            out = cats if out is None else out + cats
        if k < 0:
            break
        node = node.get(path[k])
        k -= 1
    return out


def _scalar(path, f, v, ids):
    if f in _TRIE:
        cats = match(path, f)
        if cats:
            for cat in cats:
                ids[cat].add(v)


def _blob(b, s, e, pth, ids, depth):
    """Handle one length-delimited field at path pth (which ends with its field number): recurse into
    it if it is a message, and read it as a packed list where a pattern expects one."""
    ln = e - s
    if not ln:
        return
    is_msg = depth < MAX_DEPTH and walk(b, s, e, pth, ids, depth + 1)
    if ln <= PACKED_MAX:
        if ln % 8 == 0:              # packed fixed64 (read even if it also parses as a message by accident)
            cats = match(pth, 8)
            if cats:
                vals = struct.unpack_from('<%dQ' % (ln // 8), b, s)
                for cat in cats:
                    ids[cat].update(vals)
        if not is_msg:
            cats = match(pth, 0)
            if cats:
                vals = parse_packed(b, s, e)
                if vals is not None:
                    for cat in cats:
                        ids[cat].update(vals)


def walk(b, start, end, path, ids, depth=0):
    """Schema-less walk of the message b[start:end]; adds every value whose path matches PATTERNS to
    ids[category]. Returns False (and adds nothing) when the bytes are not a clean message."""
    fields = parse_message(b, start, end)
    if fields is None:
        return False
    trie = _TRIE
    for f, wt, v in fields:
        if wt == 2:
            _blob(b, v[0], v[1], path + (f,), ids, depth)
        elif f in trie:
            cats = match(path, f)
            if cats:
                for cat in cats:
                    ids[cat].add(v)
    return True


def _new_ids():
    return collections.defaultdict(set)


def _first(fields, num, default=None):
    for f, wt, v in fields:
        if f == num:
            return v
    return default


def _text(b, span):
    return bytes(b[span[0]:span[1]]).decode('utf-8', 'replace') if isinstance(span, tuple) else ''


def _walk_sim(b, s, e, path, ids, role, households):
    """Walk one SimData / MannequinSimData blob with its own id sets; returns the sim record."""
    top = parse_message(b, s, e) or []
    mine = _new_ids()
    walk(b, s, e, path, mine, 1)
    for cat, vals in mine.items():
        ids[cat].update(vals)
    if role == 'mannequin':
        sim_id, name, hh_id, hh_name = _first(top, 1, 0), '(mannequin)', 0, '(mannequins)'
    else:
        sim_id = _first(top, 1, 0)
        name = (_text(b, _first(top, 5)) + ' ' + _text(b, _first(top, 6))).strip()
        hh_id = _first(top, 4, 0)
        hh_name = households.get(hh_id) or _text(b, _first(top, 22))
    looks = mine[TONE] | mine[SCULPT] | mine[MODIFIER] | mine[PELT]
    return (role, sim_id, name, hh_id, hh_name, sorted(mine[PART]), sorted(looks))


def _scan_savegame(b, prefix, ids, sims):
    """SaveGameData: households(5) give names, sims(6) and mannequins(15) are walked one by one."""
    top = parse_message(b)
    if top is None:
        return False
    households = {}
    for f, wt, v in top:
        if f == 5 and wt == 2:
            hh = parse_message(b, v[0], v[1]) or []
            households[_first(hh, 2, 0)] = _text(b, _first(hh, 3))
    for f, wt, v in top:
        if wt != 2:
            _scalar(prefix, f, v, ids)
        elif f in (6, 15):
            sims.append(_walk_sim(b, v[0], v[1], prefix + (f,), ids, 'sim' if f == 6 else 'mannequin', households))
        else:
            _blob(b, v[0], v[1], prefix + (f,), ids, 1)
    return True


def _scan_household(b, start, end, ids, sims):
    """Tray household: root field 1 is AccountFamilyData (familyid 2, familyname 3, sims 6)."""
    root = parse_message(b, start, end)
    if root is None:
        return False
    prefix = ('hh',)
    for f, wt, v in root:
        if f == 1 and wt == 2:
            fam = parse_message(b, v[0], v[1])
            if fam is None:
                _blob(b, v[0], v[1], prefix + (1,), ids, 1)
                continue
            households = {0: _text(b, _first(fam, 3))}
            fam_id = _first(fam, 2, 0)
            for f2, wt2, v2 in fam:
                if wt2 != 2:
                    _scalar(prefix + (1,), f2, v2, ids)
                elif f2 == 6:
                    rec = _walk_sim(b, v2[0], v2[1], prefix + (1, 6), ids, 'sim', households)
                    sims.append(rec[:3] + (fam_id, households[0]) + rec[5:])
                else:
                    _blob(b, v2[0], v2[1], prefix + (1, f2), ids, 2)
        elif wt == 2:
            _blob(b, v[0], v[1], prefix + (f,), ids, 1)
        else:
            _scalar(prefix, f, v, ids)
    return True


def _looks_image(data):
    return data[:3] == b'\xff\xd8\xff' or data[:4] == b'\x89PNG'


def scan_file(path, kind, content=None):
    """Parse one save or Tray file. Returns {'ids': {category: sorted ids}, 'sims': [...], 'info': {...}}.

    kind is 'save' / 'backup' (DBPF save), 'household', 'trayitem' or 'lot' (Tray). content is the
    file's bytes when the caller already read them. The file is read into memory in one go and closed
    before parsing (a big save takes ~40 s to parse; the game must be able to rotate it meanwhile).
    Library-independent: the result only depends on the file, so it can be cached by its fingerprint."""
    t0 = time.time()
    ids = _new_ids()
    sims = []
    info = {'resources': 0, 'unparsed': 0, 'bytes': 0}
    blob = _read_file(path) if content is None else content
    if kind in ('save', 'backup'):
        for e in read_entries(io.BytesIO(blob)):
            if e.comp == DELETED or e.t in SAVE_IMAGE_TYPES:
                continue
            raw = blob[e.off:e.off + e.fsize]
            if len(raw) != e.fsize:
                raise DBPFError('resource %08X:%08X:%016X runs past the end of %s' % (e.t, e.g, e.i, path))
            data = decompress(raw, e.comp, e.msize)
            info['resources'] += 1
            info['bytes'] += len(data)
            if _looks_image(data):
                continue
            prefix = ('R%X' % e.t,)
            ok = _scan_savegame(data, prefix, ids, sims) if e.t == 0x0D else walk(data, 0, len(data), prefix, ids)
            if not ok:
                info['unparsed'] += 1
    else:
        data = blob
        info['bytes'] = len(data)
        ok = False
        if kind == 'household' and len(data) >= 16:
            ver = _I(data, 0)[0]
            frames = [(16, 16 + _I(data, 12)[0]), (8, 8 + _I(data, 4)[0])]
            if ver < 2:
                frames.reverse()
            for s, e in frames:
                if e <= len(data) and _scan_household(data, s, e, ids, sims):
                    ok = True
                    break
        elif kind == 'trayitem' and len(data) >= 8:
            ok = walk(data, 8, len(data), ('trayitem',), ids)
        elif kind == 'lot':
            # undecoded C++ framing; ObjectData.guid(30) is tag bytes F0 01 followed by a varint
            p = data.find(b'\xf0\x01')
            while p >= 0:
                v = _varint_at(data, p + 2)
                if v is not None:
                    ids[OBJECT_TAG30].add(v)
                p = data.find(b'\xf0\x01', p + 2)
            ok = True
        if not ok:
            info['unparsed'] += 1
    info['secs'] = round(time.time() - t0, 2)
    return {'ids': {cat: sorted(v) for cat, v in ids.items() if v}, 'sims': sims, 'info': info}


def _varint_at(b, p):
    v = shift = 0
    while p < len(b) and shift <= 63:
        c = b[p]
        p += 1
        v |= (c & 0x7F) << shift
        if c < 0x80:
            return v & M64
        shift += 7
    return None


def _scan_job(job):
    """Worker: parse one file. The result is stored under the fingerprint taken before, so it is refused
    unless the bytes parsed are exactly the fingerprinted ones (the game may have saved in between)."""
    path, kind, fp = job
    try:
        content = _read_file(path)
        if _fingerprint_bytes(content) != fp:
            return path, None, 'changed while it was scanned'
        return path, scan_file(path, kind, content), None
    except Exception as e:           # a half-written save, a damaged Tray file...
        return path, None, '%s: %s' % (type(e).__name__, e)


# ------------------------------------------------------------------------------------------ sources + cache
Source = collections.namedtuple('Source', 'path name kind current size mtime_ns fp')
SimRef = collections.namedtuple('SimRef', 'source role sim_id name household_id household parts looks')


def list_sources(saves_dir=SAVES, tray_dir=TRAY):
    """Save files (current slots and .ver backups) and parseable Tray files, as [(path, kind)].

    kind: 'save' (Slot_*.save), 'backup' (*.save.ver0, .day.ver0, ...), or a Tray kind. Thumbnail
    images (.hhi .sgi .bpi .rmi) hold no ids and are left out."""
    out = []
    if os.path.isdir(saves_dir):
        for n in sorted(os.listdir(saves_dir)):
            p = os.path.join(saves_dir, n)
            if '.save' in n.lower() and os.path.isfile(p):
                out.append((p, 'save' if n.lower().endswith('.save') else 'backup'))
    if os.path.isdir(tray_dir):
        for n in sorted(os.listdir(tray_dir)):
            kind = TRAY_KINDS.get(os.path.splitext(n)[1].lower())
            p = os.path.join(tray_dir, n)
            if kind and os.path.isfile(p):
                out.append((p, kind))
    return out


FP_VERSION = 'blake2b-128-full'


def fingerprint(path, size=None, chunk=1 << 22):
    """Content fingerprint: blake2b-128 of the size and the whole file.

    The whole file, not a sample: a re-save can keep the package layout (and so the first and last
    MiB) while ids in the middle change. Saves are 10-80 MB on disk, so this costs well under a second
    a file, and only for new or changed files (see _fingerprint_sources)."""
    size = os.path.getsize(path) if size is None else size
    h = hashlib.blake2b(digest_size=16)
    h.update(struct.pack('<Q', size))
    with _open_read(path) as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _fingerprint_bytes(content):
    """fingerprint() of a file whose whole content is in memory."""
    h = hashlib.blake2b(digest_size=16)
    h.update(struct.pack('<Q', len(content)))
    h.update(content)
    return h.hexdigest()


REFS_SCHEMA = """
create table if not exists meta(k text primary key, v text);
create table if not exists seen(path text primary key, size integer, mtime_ns integer, fp text);
create table if not exists src(fp text primary key, kind text, size integer, secs real, info text, scanned real);
create table if not exists ids(fp text, cat text, n integer, data blob, primary key(fp, cat));
create table if not exists sim(fp text, idx integer, role text, sim_id integer, name text, household_id integer,
                               household text, parts blob, looks blob, primary key(fp, idx));
"""


def _pack_ids(vals):
    return array.array('Q', sorted(vals)).tobytes()


def _unpack_ids(blob):
    a = array.array('Q')
    a.frombytes(blob)
    return a


def _open_refs_db(cache_db):
    os.makedirs(os.path.dirname(os.path.abspath(cache_db)), exist_ok=True)
    db = sqlite3.connect(cache_db)
    db.executescript(REFS_SCHEMA)
    row = db.execute("select v from meta where k='scanner'").fetchone()
    if not row or row[0] != SCANNER_VERSION:        # the patterns changed: every cached parse is outdated
        db.executescript('delete from src; delete from ids; delete from sim;')
        db.execute("insert or replace into meta values('scanner', ?)", (SCANNER_VERSION,))
        db.commit()
    row = db.execute("select v from meta where k='fingerprint'").fetchone()
    if not row or row[0] != FP_VERSION:             # fingerprints made another way: recompute them all
        db.execute('delete from seen')
        db.execute("insert or replace into meta values('fingerprint', ?)", (FP_VERSION,))
        db.commit()
    return db


def _store(db, fp, kind, size, res):
    db.execute('delete from ids where fp=?', (fp,))
    db.execute('delete from sim where fp=?', (fp,))
    db.executemany('insert into ids values(?,?,?,?)',
                   [(fp, cat, len(v), _pack_ids(v)) for cat, v in res['ids'].items()])
    db.executemany('insert into sim values(?,?,?,?,?,?,?,?,?)',
                   [(fp, n, role, signed64(sid), name, signed64(hid), hh, _pack_ids(parts), _pack_ids(looks))
                    for n, (role, sid, name, hid, hh, parts, looks) in enumerate(res['sims'])])
    db.execute('insert or replace into src values(?,?,?,?,?,?)',
               (fp, kind, size, res['info'].get('secs', 0), json.dumps(res['info']), time.time()))
    db.commit()


class Refs:
    """What the saves and Tray reference, per source file (see scan_references).

    sources: [Source]; by_fp: {fp: {category: set of ids}}; sims: {fp: [SimRef]}; stats: scan numbers.
    Current slots (Slot_*.save) and Tray files are 'current'; .ver backups only count when asked."""

    def __init__(self, sources, by_fp, sims, stats, backups_scanned):
        self.sources = sources
        self.by_fp = by_fp
        self.sims = sims
        self.stats = stats
        self.backups_scanned = backups_scanned

    def selected(self, include_backups=False):
        """The sources that count: current slots + Tray, plus backups when include_backups."""
        return [s for s in self.sources if s.fp in self.by_fp and (s.current or include_backups)]

    def ids(self, cat, include_backups=False):
        """Union of one category's ids over the selected sources."""
        out = set()
        for s in self.selected(include_backups):
            out.update(self.by_fp[s.fp].get(cat, ()))
        return out

    def sim_list(self, include_backups=False):
        """Every sim / mannequin record of the selected sources."""
        out = []
        for s in self.selected(include_backups):
            out.extend(self.sims.get(s.fp, ()))
        return out

    def unparsed(self, include_backups=False):
        """Names of sources that count but have no scan result (a parse error, or the file changed while
        it was read - the game saving). A pack planned without them could miss their CC."""
        return sorted({s.name for s in self.sources if (s.current or include_backups) and s.fp not in self.by_fp})

    def fingerprints(self, include_backups=False):
        """[{'name', 'kind', 'size', 'mtime_ns', 'fp'}] of the selected sources (recorded in a build)."""
        return [{'name': s.name, 'kind': s.kind, 'size': s.size, 'mtime_ns': s.mtime_ns, 'fp': s.fp}
                for s in self.selected(include_backups)]


def _fingerprint_sources(db, found):
    """[(path, kind)] -> [Source]; reuses the stored fingerprint while size and mtime are unchanged.

    A file renamed by the game's backup rotation (Slot.save -> .ver0 -> .ver1 ...) keeps its size and
    its mtime, so its fingerprint is taken over from its old name without reading it - but only when
    the old name no longer holds a file with that size and mtime (it really moved away). The game
    writes whole-second mtimes, so a different file can share both with one that is still there."""
    seen = {p: (sz, mt, fp) for p, sz, mt, fp in db.execute('select path, size, mtime_ns, fp from seen')}
    by_stat = collections.defaultdict(list)
    for p, (sz, mt, fp) in seen.items():
        by_stat[(sz, mt)].append((p, fp))
    out = []
    for path, kind in found:
        try:
            st = os.stat(path)
            old = seen.get(path)
            if old and old[0] == st.st_size and old[1] == st.st_mtime_ns:
                fp = old[2]
            else:
                fp = None
                for old_path, old_fp in by_stat.get((st.st_size, st.st_mtime_ns), ()):
                    if not _has_stat(old_path, st):
                        fp = old_fp
                        break
                fp = fp or fingerprint(path, st.st_size)
                db.execute('insert or replace into seen values(?,?,?,?)', (path, st.st_size, st.st_mtime_ns, fp))
        except OSError:               # vanished between listdir and stat (the game rotating backups)
            continue
        out.append(Source(path, os.path.basename(path), kind, kind != 'backup', st.st_size, st.st_mtime_ns, fp))
    present = {s.path for s in out}
    db.executemany('delete from seen where path=?', [(p,) for p in seen if p not in present])
    db.commit()
    return out


def _has_stat(path, st):
    """Does path (still) hold a file with st's size and mtime?"""
    try:
        now = os.stat(path)
    except OSError:
        return False
    return now.st_size == st.st_size and now.st_mtime_ns == st.st_mtime_ns


def scan_references(saves_dir=SAVES, tray_dir=TRAY, cache_db=DEFAULT_REFS_DB, workers=3, include_backups=False,
                    verbose=False):
    """Collect the CAS part, object, skin tone, sculpt and slider ids every save and Tray file references.

    Incremental: results are cached in cache_db by content fingerprint, so unchanged files - including
    backups the game merely renamed (.save -> .ver0) - are never parsed twice. .ver backups are only
    parsed when include_backups is True. Read-only on saves_dir and tray_dir. Returns a Refs."""
    t0 = time.time()
    db = _open_refs_db(cache_db)
    sources = _fingerprint_sources(db, list_sources(saves_dir, tray_dir))
    cached = {fp for (fp,) in db.execute('select fp from src')}
    todo, queued = [], set()
    for s in sorted(sources, key=lambda s: -s.size):             # big saves first
        if (s.current or include_backups) and s.fp not in cached and s.fp not in queued:
            todo.append((s.path, s.kind, s.fp))
            queued.add(s.fp)
    fp_of = {s.path: s for s in sources}
    errors = {}
    parsed = 0

    def take(path, res, err):
        nonlocal parsed
        s = fp_of[path]
        if err:
            errors[s.name] = err
            db.execute('delete from seen where path=?', (path,))     # fingerprint it afresh next time
            return
        _store(db, s.fp, s.kind, s.size, res)
        parsed += 1
        if verbose and (s.kind in ('save', 'backup') or parsed % 200 == 0):
            print('  parsed %-40s %6.1f MB in %5.1fs' % (s.name, res['info']['bytes'] / 1e6, res['info']['secs']),
                  flush=True)

    if workers > 1 and len(todo) > 1:
        with multiprocessing.Pool(min(workers, len(todo))) as pool:
            for path, res, err in pool.imap_unordered(_scan_job, todo, chunksize=1):
                take(path, res, err)
    else:
        for job in todo:
            take(*_scan_job(job))
    # forget parses of files that no longer exist anywhere (fingerprints of all present files are kept)
    keep = {s.fp for s in sources}
    gone = [fp for fp in cached if fp not in keep]
    for fp in gone:
        for table in ('src', 'ids', 'sim'):
            db.execute('delete from %s where fp=?' % table, (fp,))
    db.commit()
    refs = _load_refs(db, sources, include_backups)
    refs.stats.update({'sources': len(sources), 'selected': len(refs.selected(include_backups)), 'parsed': parsed,
                       'errors': errors, 'forgotten': len(gone), 'seconds': round(time.time() - t0, 1)})
    db.close()
    return refs


def _load_refs(db, sources, include_backups):
    want = {s.fp for s in sources if s.current or include_backups}
    by_fp, sims = {}, {}
    for fp, cat, blob in db.execute('select fp, cat, data from ids'):
        if fp in want:
            by_fp.setdefault(fp, {})[cat] = set(_unpack_ids(blob))
    for (fp,) in db.execute('select fp from src'):
        if fp in want:
            by_fp.setdefault(fp, {})
    name_of = {}
    for s in sources:
        name_of.setdefault(s.fp, s.name)
    for fp, role, sid, name, hid, hh, parts, looks in db.execute(
            'select fp, role, sim_id, name, household_id, household, parts, looks from sim order by fp, idx'):
        if fp in want:
            sims.setdefault(fp, []).append(SimRef(name_of.get(fp, fp), role, unsigned64(sid), name, unsigned64(hid),
                                                  hh, set(_unpack_ids(parts)), set(_unpack_ids(looks))))
    return Refs(sources, by_fp, sims, {}, include_backups)


def load_refs(saves_dir=SAVES, tray_dir=TRAY, cache_db=DEFAULT_REFS_DB, include_backups=False):
    """Refs from the cache only (no parsing); files not parsed yet are simply missing from it."""
    db = _open_refs_db(cache_db)
    sources = _fingerprint_sources(db, list_sources(saves_dir, tray_dir))
    refs = _load_refs(db, sources, include_backups)
    db.close()
    return refs


# ------------------------------------------------------------------------------------------ game ids
GAME_CACHE_VERSION = 2
# where the game keeps its CAS parts and looks, so plan() can read the EA ones sims wear (default replacements)
LOC_TYPES = (T_CASP, T_TONE, T_SCUL, T_SMOD, T_PELT)
LOC_DTYPE = np.dtype([('i', '<u8'), ('pkg', '<u4'), ('off', '<u4'), ('fsize', '<u4'), ('msize', '<u4'),
                      ('comp', '<u4')])


class GameIds:
    """Instances of every resource type the game ships, per type (sorted uint64 arrays), and where the
    game's CAS parts, skin tones, sculpts, sliders and pelts are (to read the EA ones with read())."""

    def __init__(self, arrays, info=None, locs=None, packages=None, game_dir=None):
        self.arrays = arrays
        self.info = info or {}
        self.locs = locs or {}
        self.packages = packages or []
        self.game_dir = game_dir or self.info.get('game_dir')
        self.read_errors = 0
        self._sets = {}

    def ids(self, t):
        """All game instances of type t as a set."""
        if t not in self._sets:
            self._sets[t] = set(int(x) for x in self.arrays.get(t, ()))
        return self._sets[t]

    casp = property(lambda self: self.ids(T_CASP))
    objd = property(lambda self: self.ids(T_OBJD))
    cobj = property(lambda self: self.ids(T_COBJ))
    tone = property(lambda self: self.ids(T_TONE))

    def has(self, t, i):
        """Does the game ship a resource of type t with instance i (any group)?"""
        a = self.arrays.get(t)
        if a is None or not len(a):
            return False
        k = int(np.searchsorted(a, np.uint64(i)))
        return k < len(a) and int(a[k]) == i

    def read(self, t, instances):
        """Yield (instance, data) for EVERY game copy of type t (one of LOC_TYPES) whose instance is in
        instances - base game, packs and delta patches alike - decompressed. Reads package by package in
        file order; a copy that cannot be read is skipped and counted in read_errors. Read-only."""
        loc = self.locs.get(t)
        if loc is None or not len(loc) or not instances:
            return
        want = np.array(sorted(instances), dtype=np.uint64)
        sel = loc[np.isin(loc['i'], want)]
        sel = sel[np.lexsort((sel['off'], sel['pkg']))]
        f, cur = None, None
        try:
            for r in sel:
                pkg = int(r['pkg'])
                try:
                    if pkg != cur:
                        if f:
                            f.close()
                        f, cur = None, pkg
                        f = _open_read(os.path.join(self.game_dir, self.packages[pkg]))
                    if f is None:
                        raise OSError('package not readable')
                    f.seek(int(r['off']))
                    data = decompress(f.read(int(r['fsize'])), int(r['comp']), int(r['msize']))
                except Exception:
                    self.read_errors += 1
                    continue
                yield int(r['i']), data
        finally:
            if f:
                f.close()


def _game_listing(game_dir):
    out = []
    for dp, dn, fn in os.walk(game_dir):
        dn.sort()
        for n in sorted(fn):
            if n.lower().endswith('.package'):
                p = os.path.join(dp, n)
                st = os.stat(p)
                out.append((os.path.relpath(p, game_dir), st.st_size, st.st_mtime_ns))
    return out


GAME_SCHEMA = """
create table if not exists meta(k text primary key, v text);
create table if not exists ids(t integer primary key, n integer, data blob);
create table if not exists loc(t integer primary key, n integer, data blob);
create table if not exists gpkg(idx integer primary key, rel text);
"""


def load_game_ids(game_dir=GAME_DIR, cache_db=DEFAULT_GAME_DB, refresh=False):
    """EA's own ids: the instances of every type in every .package under game_dir (read-only there),
    plus where each CAS part, skin tone, sculpt, slider and pelt layer copy sits (LOC_TYPES).

    Cached in cache_db; rebuilt only when the list of game packages or their sizes/mtimes change
    (a patch). Raises FileNotFoundError, leaving the cache alone, when game_dir holds no packages (a
    wrong path, or the drive is not mounted): an empty id set would make plan() drop every default
    replacement and mistake EA ids for CC. Returns GameIds with .casp .objd .cobj .tone sets,
    .has(t, i) and .read(t, ids)."""
    listing = _game_listing(game_dir)
    if not listing:
        raise FileNotFoundError('no .package files under %s - is the game folder right and its drive there?'
                                % game_dir)
    fp = hashlib.blake2b(repr((GAME_CACHE_VERSION, listing)).encode(), digest_size=16).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(cache_db)), exist_ok=True)
    db = sqlite3.connect(cache_db)
    db.executescript(GAME_SCHEMA)
    row = db.execute("select v from meta where k='fingerprint'").fetchone()
    if row and row[0] == fp and not refresh:
        arrays = {t: np.frombuffer(blob, dtype='<u8') for t, blob in db.execute('select t, data from ids')}
        locs = {t: np.frombuffer(blob, dtype=LOC_DTYPE) for t, blob in db.execute('select t, data from loc')}
        packages = [rel for _, rel in db.execute('select idx, rel from gpkg order by idx')]
        info = dict(db.execute('select k, v from meta'))
        db.close()
        return GameIds(arrays, info, locs, packages, game_dir)
    t0 = time.time()
    ts, iss, bad = [], [], []
    locs = {t: [] for t in LOC_TYPES}
    for n, (rel, size, mtime) in enumerate(listing):
        try:
            with _open_read(os.path.join(game_dir, rel)) as f:
                entries = [e for e in read_entries(f) if e.comp != DELETED]
        except Exception as e:
            bad.append('%s: %s' % (rel, e))
            continue
        ts.append(np.array([e.t for e in entries], dtype=np.uint32))
        iss.append(np.array([e.i for e in entries], dtype=np.uint64))
        for e in entries:
            if e.t in locs:
                locs[e.t].append((e.i, n, e.off, e.fsize, e.msize, e.comp))
    t_all = np.concatenate(ts) if ts else np.zeros(0, np.uint32)
    i_all = np.concatenate(iss) if iss else np.zeros(0, np.uint64)
    order = np.lexsort((i_all, t_all))
    t_all, i_all = t_all[order], i_all[order]
    arrays = {}
    cuts = np.flatnonzero(np.diff(t_all)) + 1
    for lo, hi in zip(np.concatenate(([0], cuts)), np.concatenate((cuts, [len(t_all)]))):
        if hi > lo:
            arrays[int(t_all[lo])] = np.unique(i_all[lo:hi])
    locs = {t: np.array(rows, dtype=LOC_DTYPE) for t, rows in locs.items()}
    packages = [rel for rel, size, mtime in listing]
    db.executescript('delete from ids; delete from loc; delete from gpkg; delete from meta;')
    db.executemany('insert into ids values(?,?,?)', [(t, len(a), a.astype('<u8').tobytes()) for t, a in arrays.items()])
    db.executemany('insert into loc values(?,?,?)', [(t, len(a), a.tobytes()) for t, a in locs.items()])
    db.executemany('insert into gpkg values(?,?)', enumerate(packages))
    info = {'fingerprint': fp, 'game_dir': game_dir, 'packages': str(len(listing)), 'entries': str(len(i_all)),
            'unreadable': str(len(bad)), 'built': time.strftime('%Y-%m-%d %H:%M:%S'),
            'seconds': str(round(time.time() - t0, 1))}
    db.executemany('insert or replace into meta values(?,?)', info.items())
    db.commit()
    db.close()
    return GameIds(arrays, info, locs, packages, game_dir)


# ------------------------------------------------------------------------------------------ resource parsing
def casp_refs(data):
    """Resource keys listed in a CASP, [(t, g, i)] in list order (entry 0 is usually a null key).

    Layout verified on 2,025 library CASPs: the list starts at 8 + u32@4; u8 count, then count x
    (u64 instance, u32 group, u32 type), ending at the end of the resource."""
    p = 8 + _I(data, 4)[0]
    n = data[p]
    if p + 1 + 16 * n > len(data):
        raise ValueError('CASP key list runs past the end of the resource')
    return [(t, g, i) for i, g, t in (struct.unpack_from('<QII', data, p + 1 + 16 * k) for k in range(n))]


def embedded_refs(data, types, instance_only=True):
    """Resource keys embedded in data: full keys of the given types in any of four layouts
    (T-G-I, I-G-T, I-T-G, Ihi-Ilo-T-G) and, if instance_only, every 64-bit value >= 2^32
    (instance-only references such as TONE -> texture). Returns (keys, instances)."""
    keys, insts = set(), set()
    n = len(data)
    if n < 8:
        return keys, insts
    if instance_only:
        for k in range(8):
            m = (n - k) // 8
            if m > 0:
                a = np.frombuffer(data, dtype='<u8', count=m, offset=k)
                insts.update(int(x) for x in a[a >= BIG])
    tarr = np.array(sorted(types), dtype=np.uint32)
    for k in range(4):
        m = (n - k) // 4
        if m <= 0:
            continue
        a = np.frombuffer(data, dtype='<u4', count=m, offset=k)
        for idx in np.flatnonzero(np.isin(a, tarr)):
            p = k + 4 * int(idx)
            t = int(a[idx])
            if p + 16 <= n:                                           # T G I
                keys.add((t, _I(data, p + 4)[0], _Q(data, p + 8)[0]))
            if p >= 12:                                               # I G T
                keys.add((t, _I(data, p - 4)[0], _Q(data, p - 12)[0]))
            if p >= 8 and p + 8 <= n:                                 # I T G  and  Ihi Ilo T G
                g = _I(data, p + 4)[0]
                keys.add((t, g, _Q(data, p - 8)[0]))
                keys.add((t, g, (_I(data, p - 8)[0] << 32) | _I(data, p - 4)[0]))
    keys = {k for k in keys if k[2]}
    return keys, insts


def stbl_keys(data):
    """String keys (u32 hashes) of an STBL resource."""
    if data[:4] != b'STBL':
        return set()
    count = _Q(data, 7)[0]
    p = 21
    out = set()
    for _ in range(count):
        if p + 7 > len(data):
            break
        out.add(_I(data, p)[0])
        ln = struct.unpack_from('<H', data, p + 5)[0]
        p += 7 + ln
    return out


# ------------------------------------------------------------------------------------------ plan
Item = collections.namedtuple('Item', 't g i pkg off fsize msize comp why')


class PackPlan:
    """What a used-CC pack holds.

    items: {(t, g, i): Item} - one chosen copy per key (the copy the game would use).
    packages: {pkg_id: {'root', 'rel', 'size', 'mtime'}} - the source packages the copies come from.
    absent: {category: sorted ids} - referenced CC ids (>= 2^32) installed neither in the library nor
            in the game. unloadable: {category: sorted ids} - referenced ids the library has only in
            packages the game never loads (deeper than Resource.cfg reaches), so the pack cannot have
            them either. households: per-household list of worn CC that is installed nowhere.
    stats: counts and sizes. sources: fingerprints of the saves/Tray files the plan was made from.
    root_dirs: {root name: folder} of the library the plan read, where build() finds the sources."""

    def __init__(self):
        self.items = {}
        self.packages = {}
        self.absent = {}
        self.unloadable = {}
        self.households = []
        self.stats = {}
        self.sources = []
        self.roots = ()
        self.root_dirs = {}
        self.include_backups = False

    def total_bytes(self):
        """Bytes the pack's resources take on disk (as stored)."""
        return sum(it.fsize for it in self.items.values())

    def summary(self):
        """Counts and sizes by type, as a dict."""
        by_t = collections.Counter()
        by_n = collections.Counter()
        for it in self.items.values():
            by_t[tname(it.t)] += it.fsize
            by_n[tname(it.t)] += 1
        return {'keys': len(self.items), 'bytes': self.total_bytes(),
                'bytes_uncompressed': sum(it.msize for it in self.items.values()),
                'source_packages': len({it.pkg for it in self.items.values()}),
                'by_type_bytes': dict(by_t.most_common()), 'by_type_count': dict(by_n.most_common())}


class _Planner:
    def __init__(self, lib, roots, game):
        self.lib, self.db, self.game = lib, lib.db, game
        self.roots = tuple(roots)
        self.pos = lib.order_positions(self.roots)
        self.pkgs = {p.id: p for p in lib.packages()}
        self.items = {}
        self.why = collections.Counter()
        self.exact_cache = {}
        self.files = collections.OrderedDict()

    # --- library lookups (res.i is stored signed) ---
    def best_exact(self, key):
        """The loaded copy of key the game would use, as a row tuple, or None."""
        if key in self.exact_cache:
            return self.exact_cache[key]
        t, g, i = key
        best = None
        for pkg, off, fs, ms, comp in self.db.execute(
                'select pkg, off, fsize, msize, comp from res where t=? and g=? and i=? and comp != ?',
                (t, g, signed64(i), DELETED)):
            p = self.pos.get(pkg)
            if p is not None and (best is None or p < best[0]):
                best = (p, pkg, off, fs, ms, comp)
        self.exact_cache[key] = best
        return best

    def by_instance(self, types, instances):
        """({(t,g,i): best loaded row} for every key of the given types whose instance is in instances,
        set of instances present in the library at all - loaded or not)."""
        out, present = {}, set()
        if not instances:
            return out, present
        self.db.execute('drop table if exists temp.up_want')
        self.db.execute('create temp table up_want(i integer primary key)')
        self.db.executemany('insert or ignore into temp.up_want values(?)', ((signed64(i),) for i in instances))
        for t in sorted(types):
            for pkg, g, i, off, fs, ms, comp in self.db.execute(
                    'select pkg, g, i, off, fsize, msize, comp from res where t=? and comp != ? '
                    'and i in (select i from temp.up_want)', (t, DELETED)):
                i = unsigned64(i)
                present.add(i)
                p = self.pos.get(pkg)
                if p is None:
                    continue
                key = (t, g, i)
                cur = out.get(key)
                if cur is None or p < cur[0]:
                    out[key] = (p, pkg, off, fs, ms, comp)
        self.db.execute('drop table temp.up_want')
        return out, present

    def by_keys(self, keys):
        """{key: best loaded row} for the exact keys (t, g, i) that have a loaded library copy (batched)."""
        by_t = collections.defaultdict(set)
        for t, g, i in keys:
            by_t[t].add(i)
        out = {}
        for t, insts in by_t.items():
            rows, _ = self.by_instance([t], insts)
            out.update((k, r) for k, r in rows.items() if k in keys)
        return out

    def add(self, key, row, why):
        """Plan key from the chosen copy row; False if it was planned already."""
        if key in self.items:
            return False
        p, pkg, off, fs, ms, comp = row
        self.items[key] = Item(key[0], key[1], key[2], pkg, off, fs, ms, comp, why)
        self.why[why] += 1
        return True

    # --- reading source resources ---
    def path_of(self, pkg_id):
        """Where a library package is now (see _locate)."""
        return _locate(self.lib, self.pkgs[pkg_id])

    def read(self, item):
        """A planned resource, decompressed (source files kept open, at most 32)."""
        f = self.files.get(item.pkg)
        if f is None:
            if len(self.files) >= 32:
                self.files.popitem(last=False)[1].close()
            f = self.files[item.pkg] = _open_read(self.path_of(item.pkg))
        f.seek(item.off)
        return decompress(f.read(item.fsize), item.comp, item.msize)

    def close(self):
        """Close the source files."""
        for f in self.files.values():
            f.close()
        self.files.clear()

    # --- closures ---
    def resolve_embedded(self, sources, types, why, instance_only_max=1 << 14):
        """Add every library resource of the given types that the source items refer to; returns the new keys."""
        keys, insts = set(), set()
        for it in sources:
            try:
                data = self.read(it)
            except Exception:
                self.why['unreadable ' + tname(it.t)] += 1
                continue
            k, ins = embedded_refs(data, types, instance_only=len(data) <= instance_only_max)
            keys |= k
            insts |= ins - {it.i}
        new = []
        for key in keys:
            row = self.best_exact(key)
            if row and self.add(key, row, why + ' ' + tname(key[0])):
                new.append(key)
        rows, _ = self.by_instance(types, insts)
        for key, row in rows.items():
            if self.add(key, row, why + ' ' + tname(key[0])):
                new.append(key)
        return new


def _locate(lib, pkg):
    """Path of a library package; if the other tool moved it to another root since the library scan,
    find it at the same relative path there (same size)."""
    p = lib.path(pkg.root, pkg.rel)
    if os.path.exists(p):
        return p
    for root in lib.roots:
        q = lib.path(root, pkg.rel)
        if root != pkg.root and os.path.exists(q) and os.path.getsize(q) == pkg.size:
            return q
    raise FileNotFoundError('%s/%s is gone - re-scan the library' % (pkg.root, pkg.rel))


def plan(lib, refs, roots=('Mods', 'Mods_parked'), include_backups=False, game=None, build_surfaces=True,
         ea_overrides=True, allow_unparsed=False, verbose=False):
    """Work out which library resources a used-CC pack needs. Read-only. Returns a PackPlan.

    For the worn CAS parts (and the reward/thrift/custom-colour part ids) it takes every CASP copy,
    then every key in each CASP's resource-key list (exact key; if missing and not EA's: the same
    type under another group, then another texture type with the same instance), and the CAS
    thumbnails. Then the used CC skin tones, sculpts, sliders and pet coats with what they refer to,
    the used CC objects (OBJD/COBJ/thumbnail, their models, LODs, footprints, slots, textures, their
    own tuning and the string tables naming them), and - since lot architecture is not decoded -
    every CC wall and floor (build_surfaces). With ea_overrides it also reads the worn EA parts and
    looks from the game and adds the library's copies of the meshes/textures they list (default
    replacements), so sims wearing EA items keep the full library's look too. For each key it picks
    the copy first in lib.load_order(roots). include_backups=True also counts .ver backup saves (they
    must have been scanned). Refuses when a save/Tray file that counts has no scan result, unless
    allow_unparsed."""
    t0 = time.time()
    if include_backups and not refs.backups_scanned:
        raise ValueError('refs were scanned without backups; call scan_references(include_backups=True)')
    unparsed = refs.unparsed(include_backups)
    if unparsed and not allow_unparsed:
        raise ValueError('%d save/Tray files have no scan result (%s): scan again when the game is not saving, '
                         'or pass allow_unparsed=True' % (len(unparsed), ', '.join(unparsed[:5])))
    game = game if game is not None else load_game_ids()
    pl = _Planner(lib, roots, game)
    P = PackPlan()
    P.roots, P.include_backups = tuple(roots), include_backups
    P.root_dirs = dict(lib.roots)
    P.sources = refs.fingerprints(include_backups)
    st = collections.Counter()
    b = include_backups

    def classify(ids, present, game_types):
        c = collections.Counter()
        for v in ids:
            inl, ing = v in present, any(game.has(t, v) for t in game_types)
            c['cc' if inl and not ing else 'override_of_ea' if inl else 'ea' if ing else
              'absent' if v >= BIG else 'unknown_small'] += 1
        return dict(c)

    try:
        # ---- CAS parts
        worn = refs.ids(PART, b)
        other = refs.ids(PART_OTHER, b)
        casp_rows, casp_present = pl.by_instance([T_CASP], worn | other)
        st_parts = {'worn': classify(worn, casp_present, [T_CASP]),
                    'other_paths_in_library_only': len((other - worn) & casp_present)}
        for key, row in casp_rows.items():
            pl.add(key, row, 'CASP')
        res = collections.Counter()
        missing_by_type = collections.Counter()
        unresolved = []
        for key in sorted(k for k in pl.items if k[0] == T_CASP):
            try:
                refs_list = casp_refs(pl.read(pl.items[key]))
            except Exception:
                res['casp_unreadable'] += 1
                continue
            for rk in refs_list:
                t, g, i = rk
                if t == 0 or i == 0:
                    continue
                if t not in CASP_REF_TYPES:
                    res['skipped_type ' + tname(t)] += 1       # tuning (BUFF) or Sims 3 types
                    continue
                row = pl.best_exact(rk)
                if row:
                    pl.add(rk, row, 'CASP ref ' + tname(t))
                    res['exact'] += 1
                elif game.has(t, i):
                    res['ea_game'] += 1
                else:
                    unresolved.append(rk)
        # fallbacks, batched: same type other group, then another texture type with the same instance
        by_type = collections.defaultdict(set)
        for t, g, i in unresolved:
            by_type[t].add(i)
        other_group = {}
        for t, insts in by_type.items():
            rows, _ = pl.by_instance([t], insts)
            for key, row in rows.items():
                other_group.setdefault((key[0], key[2]), []).append((key, row))
        swap_insts = {i for t, g, i in unresolved if t in TEXTURES and (t, i) not in other_group}
        swap_rows, _ = pl.by_instance(TEXTURES, swap_insts)
        swapped = collections.defaultdict(list)
        for key, row in swap_rows.items():
            swapped[key[2]].append((key, row))
        for t, g, i in unresolved:
            if (t, i) in other_group:
                for key, row in other_group[(t, i)]:
                    pl.add(key, row, 'CASP ref other group ' + tname(key[0]))
                res['same_type_other_group'] += 1
            elif t in TEXTURES and [kr for kr in swapped.get(i, ()) if kr[0][0] != t]:
                for key, row in swapped[i]:
                    if key[0] != t:
                        pl.add(key, row, 'CASP ref other texture type ' + tname(key[0]))
                res['other_texture_type'] += 1
            else:
                res['missing'] += 1
                missing_by_type[tname(t)] += 1
        # CAS thumbnails share the CASP instance
        thum_rows, _ = pl.by_instance([T_THUM], {k[2] for k in pl.items if k[0] == T_CASP})
        for key, row in thum_rows.items():
            pl.add(key, row, 'THUM')
        st['cas'] = dict(st_parts, casp_keys=sum(1 for k in pl.items if k[0] == T_CASP),
                         ref_resolution=dict(res), missing_by_type=dict(missing_by_type))
        loaded_casp = {k[2] for k in casp_rows}

        # ---- default replacements of worn EA parts: a library copy of a mesh/texture key an EA CASP
        # lists is what the game draws for every sim wearing that part (specular/skin-detail DRs...)
        if ea_overrides:
            ea_parts = {v for v in worn | other if v not in loaded_casp and game.has(T_CASP, v)}
            keys, n_read = set(), 0
            for v, data in game.read(T_CASP, ea_parts):
                n_read += 1
                try:
                    keys.update(k for k in casp_refs(data) if k[0] in CASP_REF_TYPES and k[2])
                except Exception:
                    game.read_errors += 1
            for key, row in pl.by_keys(keys).items():
                pl.add(key, row, 'EA part DR ' + tname(key[0]))
            thumbs, _ = pl.by_instance([T_THUM], ea_parts)          # CAS thumbnails redone by a DR
            for key, row in thumbs.items():
                pl.add(key, row, 'EA part DR THUM')
            st['ea_restyled'] = {'ea_parts': len(ea_parts), 'game_casps_read': n_read}

        # ---- skin tones, sculpts, sliders, pet coats (CC ones, and the library's DRs of EA ones)
        look = {}
        look_items = []
        for cat, t in LOOK_CATS:
            ids = refs.ids(cat, b)
            rows, present = pl.by_instance([t], ids)
            look[cat] = dict(classify(ids, present, [t]), keys=len(rows))
            look[cat + '_present'] = present
            for key, row in rows.items():
                if pl.add(key, row, tname(t)):
                    look_items.append(pl.items[key])
            if ea_overrides:
                loaded = {k[2] for k in rows}
                keys, insts = set(), set()
                for v, data in game.read(t, {v for v in ids if v not in loaded and game.has(t, v)}):
                    k, ins = embedded_refs(data, LOOK_REF_TYPES, instance_only=len(data) <= 1 << 14)
                    keys |= k
                    insts |= ins - {v}
                found = pl.by_keys(keys)
                found.update(pl.by_instance(LOOK_REF_TYPES, insts)[0])
                for key, row in found.items():
                    if pl.add(key, row, 'EA look DR ' + tname(key[0])) and key[0] in (T_SMOD, T_HSC):
                        look_items.append(pl.items[key])
        frontier = look_items
        while frontier:
            new = pl.resolve_embedded(frontier, LOOK_REF_TYPES, 'look ref')
            frontier = [pl.items[k] for k in new if k[0] in (T_SMOD, T_HSC)]
        st['looks'] = {k: v for k, v in look.items() if not k.endswith('_present')}

        # ---- build/buy objects
        objs = refs.ids(OBJECT, b)
        tag30 = {v for v in refs.ids(OBJECT_TAG30, b) if v >= BIG}     # undecoded lot files: CC ids only
        obj_rows, obj_present = pl.by_instance([T_OBJD, T_COBJ], objs | tag30)
        used_obj = {k[2] for k in obj_rows}
        st['objects'] = {'object_ids': classify(objs, obj_present, [T_OBJD, T_COBJ]),
                         'blueprint_tag30_matches': len(tag30 & obj_present), 'cc_objects_used': len(used_obj)}
        thumbs, _ = pl.by_instance([T_OTHM], used_obj)
        for key, row in list(obj_rows.items()) + list(thumbs.items()):
            pl.add(key, row, tname(key[0]))
        frontier = [pl.items[k] for k in obj_rows]
        while frontier:
            new = pl.resolve_embedded(frontier, OBJECT_REF_TYPES, 'object ref')
            frontier = [pl.items[k] for k in new if k[0] in OBJECT_CONTAINERS]
        _add_object_tuning(pl, [pl.items[k] for k in obj_rows if k[0] == T_OBJD])
        _add_object_strings(pl, [pl.items[k] for k in obj_rows if k[0] == T_COBJ])

        # ---- walls and floors (architecture blobs are not decoded): all of them, they are tiny
        if build_surfaces:
            surf = _all_of_types(pl, [T_CWAL, T_CFLR])
            for key, row in surf.items():
                pl.add(key, row, tname(key[0]))
            frontier = [pl.items[k] for k in surf]
            thumbs, _ = pl.by_instance([T_THUM, T_OTHM], {k[2] for k in surf})
            for key, row in thumbs.items():
                pl.add(key, row, 'surface ' + tname(key[0]))
            while frontier:
                new = pl.resolve_embedded(frontier, SURFACE_REF_TYPES, 'surface ref')
                frontier = [pl.items[k] for k in new if k[0] == T_MATD]
            st['surfaces'] = {'cwal_cflr': len(surf)}

        # ---- CC worn / used but installed nowhere, or only in packages the game never loads (too deep)
        absent = {'cas': sorted(v for v in worn | other if v >= BIG and v not in casp_present
                                and not game.has(T_CASP, v))}
        unloadable = {'cas': sorted((worn | other) & casp_present - loaded_casp)}
        for cat, t in LOOK_CATS:
            present = look[cat + '_present']
            absent[cat] = sorted(v for v in refs.ids(cat, b) if v >= BIG and v not in present and not game.has(t, v))
            unloadable[cat] = sorted(present - {k[2] for k in pl.items if k[0] == t})
        absent['object'] = sorted(v for v in objs if v >= BIG and v not in obj_present
                                  and not game.has(T_OBJD, v) and not game.has(T_COBJ, v))
        unloadable['object'] = sorted(obj_present - used_obj)
        P.absent, P.unloadable = absent, unloadable
        absent_sets = {k: set(v) for k, v in absent.items()}
        P.households = _missing_by_household(refs.sim_list(b), absent_sets)
    finally:
        pl.close()

    P.items = pl.items
    for pid in {it.pkg for it in pl.items.values()}:
        p = pl.pkgs[pid]
        P.packages[pid] = {'root': p.root, 'rel': p.rel, 'size': p.size, 'mtime': p.mtime}
    if ea_overrides:
        for kind in ('EA part DR', 'EA look DR'):
            its = [it for it in pl.items.values() if it.why.startswith(kind)]
            st['ea_restyled'][kind.split()[1] + '_keys'] = len(its)
            st['ea_restyled'][kind.split()[1] + '_bytes'] = sum(it.fsize for it in its)
        st['ea_restyled']['game_read_errors'] = game.read_errors
    st['why'] = dict(pl.why.most_common())
    st['absent_counts'] = {k: len(v) for k, v in P.absent.items()}
    st['unloadable_counts'] = {k: len(v) for k, v in P.unloadable.items()}
    st['households_with_missing_cc'] = len(P.households)
    st['sources'] = collections.Counter(s['kind'] for s in P.sources)
    st['seconds'] = round(time.time() - t0, 1)
    P.stats = dict(st)
    P.stats.update(P.summary())
    if verbose:
        print('plan: %d keys, %.2f GB in %.0fs' % (len(P.items), P.total_bytes() / 1e9, st['seconds']))
    return P


def _all_of_types(pl, types):
    """Best loaded copy of every library key of the given types."""
    out = {}
    for t in types:
        for pkg, g, i, off, fs, ms, comp in pl.db.execute(
                'select pkg, g, i, off, fsize, msize, comp from res where t=? and comp != ?', (t, DELETED)):
            p = pl.pos.get(pkg)
            if p is None:
                continue
            key = (t, g, unsigned64(i))
            if key not in out or p < out[key][0]:
                out[key] = (p, pkg, off, fs, ms, comp)
    return out


def _add_object_tuning(pl, objds):
    """A CC object's own tuning (+ its SimData): only when it comes from the same package as the OBJD,
    so an unrelated mod's override of EA tuning is never pulled into the pack."""
    for it in objds:
        try:
            data = pl.read(it)
        except Exception:
            continue
        keys, insts = embedded_refs(data, {T_OBJ_TUNING}, instance_only=True)
        cands = {k[2] for k in keys} | insts
        rows, _ = pl.by_instance([T_OBJ_TUNING, T_SIMDATA], cands)
        tuned = {k[2] for k, row in rows.items() if k[0] == T_OBJ_TUNING and row[1] == it.pkg}
        for key, row in rows.items():
            if key[2] in tuned and row[1] == it.pkg:
                pl.add(key, row, 'object tuning ' + tname(key[0]))


def _add_object_strings(pl, cobjs):
    """String tables (from the COBJ's own package) holding any u32 found in the COBJ (its name and
    description hashes). Whole STBLs are copied - they cannot be split without rewriting them."""
    for it in cobjs:
        try:
            data = pl.read(it)
        except Exception:
            continue
        # string keys are FNV-32 hashes; small numbers (versions, counts, flags) would match by accident
        hashes = {h for h in (_I(data, k)[0] for k in range(len(data) - 3)) if h >= 0x10000}
        for g, i, off, fs, ms, comp in pl.db.execute(
                'select g, i, off, fsize, msize, comp from res where pkg=? and t=? and comp != ?',
                (it.pkg, T_STBL, DELETED)).fetchall():
            key = (T_STBL, g, unsigned64(i))
            if key in pl.items:
                continue
            row = pl.best_exact(key)
            if not row:
                continue
            probe = Item(T_STBL, g, key[2], it.pkg, off, fs, ms, comp, '')
            try:
                if stbl_keys(pl.read(probe)) & hashes:
                    pl.add(key, row, 'object STBL')
            except Exception:
                continue


def _missing_by_household(sims, absent):
    """Group the worn-but-installed-nowhere ids by household (and sim)."""
    cas = absent.get('cas', set())
    looks = set().union(*(absent.get(cat, set()) for cat, t in LOOK_CATS))
    groups = {}
    for s in sims:
        miss = s.parts & cas
        miss_look = s.looks & looks
        if not miss and not miss_look:
            continue
        key = (s.household or '(no household)', s.household_id)
        g = groups.setdefault(key, {'household': key[0], 'household_id': '%016X' % key[1], 'sources': set(),
                                    'sims': {}, 'missing_parts': set(), 'missing_looks': set()})
        g['sources'].add(s.source)
        sim_name = s.name or '%016X' % s.sim_id
        g['sims'][sim_name] = g['sims'].get(sim_name, 0) + len(miss) + len(miss_look)
        g['missing_parts'] |= miss
        g['missing_looks'] |= miss_look
    out = []
    for g in groups.values():
        out.append({'household': g['household'], 'household_id': g['household_id'], 'sources': sorted(g['sources']),
                    'sims': dict(sorted(g['sims'].items(), key=lambda x: -x[1])),
                    'missing_parts': ['%016X' % v for v in sorted(g['missing_parts'])],
                    'missing_looks': ['%016X' % v for v in sorted(g['missing_looks'])]})
    out.sort(key=lambda g: (-len(g['missing_parts']) - len(g['missing_looks']), g['household']))
    return out


# ------------------------------------------------------------------------------------------ build
def _order(plan_):
    """Items in pack order: catalog types first (CASP, THUM, TONE, OBJD, COBJ, STBL), then other small
    resources, then meshes and textures; within a type in source order, so sources are read sequentially."""
    paths = {pid: (p['root'], p['rel']) for pid, p in plan_.packages.items()}

    def rank(it):
        return TYPE_RANK.get(it.t, 7 if it.t in BULK_TYPES else 6)
    return sorted(plan_.items.values(), key=lambda it: (rank(it), it.t if rank(it) < 7 else 0, paths[it.pkg], it.off))


def layout(plan_, max_package_bytes=1_900_000_000):
    """Split the ordered items into packages no bigger than max_package_bytes: [[Item, ...], ...].

    max_package_bytes may not pass 2 GiB: no package that big has been seen loading in-game."""
    if not 0 < max_package_bytes <= MAX_PACKAGE_LIMIT:
        raise ValueError('max_package_bytes must be between 1 and %d (2 GiB)' % MAX_PACKAGE_LIMIT)
    groups, cur, size = [], [], 96 + 4
    for it in _order(plan_):
        need = it.fsize + 32
        if cur and size + need > max_package_bytes:
            groups.append(cur)
            cur, size = [], 96 + 4
        cur.append(it)
        size += need
    if cur:
        groups.append(cur)
    return groups


def build(plan_, out_dir=DEFAULT_OUT, max_package_bytes=1_900_000_000, dry_run=True, sims=SIMS, home=None,
          check_game=True, verbose=False):
    """Write the pack: SpeedKit_UsedCC_001.package, 002, ... plus usedpack.json and usedpack_keys.tsv.

    Every resource is copied bit-exact (PackageWriter.add_raw) from the copy the plan chose. Returns
    [{'path', 'keys', 'bytes', 'journal'}]. dry_run (default) only returns the layout. A real run:
      * needs out_dir inside the Sims 4 folder (sims) but not in saves or Tray;
      * refuses while the game runs - when it starts, and again after the (long) copy, just before
        anything is moved;
      * checks every source package is unchanged since the plan (PlanStale otherwise); a package the
        other tool moves to the other root, even during the build, is found there;
      * stages the files under SpeedKit/staging and moves them into place through a Journal. The old
        manifest is moved out first, so a half-replaced pack never has a manifest vouching for it;
        older pack files are quarantined, never deleted;
      * if anything fails once files have started moving, the journal is undone at once so out_dir
        holds the previous pack again (the error names the journal). A finished build is undone with
        journal.undo(result[0]['journal'])."""
    groups = layout(plan_, max_package_bytes)
    result = [{'path': os.path.join(out_dir, PACK_NAME % (n + 1)), 'keys': len(g),
               'bytes': 96 + 4 + sum(it.fsize + 32 for it in g)} for n, g in enumerate(groups)]
    if dry_run:
        return result
    home = home or os.path.join(sims, 'SpeedKit')
    if not _inside(out_dir, sims):
        raise ValueError('out_dir must be inside the Sims 4 folder %s' % sims)
    for protected in ('saves', 'Tray'):
        if _inside(out_dir, os.path.join(sims, protected)):
            raise ValueError('out_dir may not be inside the %s folder' % protected)
    lib_paths = _check_sources(plan_)
    need = sum(r['bytes'] for r in result) + FREE_MARGIN
    free = shutil.disk_usage(sims).free
    if free < need:
        raise OSError('the pack needs %.1f GB free on the Sims 4 drive, only %.1f GB is' % (need / 1e9, free / 1e9))
    # Journal ids have one-second resolution; a second journal in the same second would overwrite the first
    while os.path.exists(os.path.join(home, 'journal', time.strftime('%Y%m%d-%H%M%S') + '-usedpack.json')):
        time.sleep(0.25)
    j = Journal('usedpack', 'used-CC pack: %d keys, %.2f GB -> %s' % (len(plan_.items), plan_.total_bytes() / 1e9,
                                                                        out_dir), home=home, sims=sims,
                check_game=check_game)
    staging = os.path.join(home, 'staging', j.id)
    staged = []
    files = collections.OrderedDict()             # open source packages (FILE_SHARE_DELETE, see _open_read)
    try:
        os.makedirs(staging, exist_ok=True)
        entries = _source_entries(plan_, lib_paths)
        for n, g in enumerate(groups):
            path = os.path.join(staging, PACK_NAME % (n + 1))
            with PackageWriter(path) as w:
                for it in g:
                    e = entries[(it.pkg, it.t, it.g, it.i)]
                    f = files.get(it.pkg)
                    if f is None:
                        if len(files) >= 32:
                            files.popitem(last=False)[1].close()
                        f = files[it.pkg] = _open_source(plan_, it.pkg, lib_paths)
                    f.seek(e.off)
                    raw = f.read(e.fsize)
                    w.add_raw(e, raw)
            staged.append(path)
            result[n]['bytes'] = os.path.getsize(path)
            if verbose:
                print('  wrote %s: %d keys, %.2f GB' % (PACK_NAME % (n + 1), len(g), result[n]['bytes'] / 1e9), flush=True)
        _close_all(files)
        man_path = os.path.join(staging, MANIFEST)
        with open(man_path, 'w', encoding='utf-8') as f:
            json.dump(_manifest(plan_, groups, result), f, indent=1)
        keys_path = os.path.join(staging, KEYS_FILE)
        with open(keys_path, 'w', encoding='utf-8') as f:
            f.write('package\ttype\tgroup\tinstance\tfsize\twhy\tsource\n')
            for n, g in enumerate(groups):
                for it in g:
                    src = plan_.packages[it.pkg]
                    f.write('%s\t%08X\t%08X\t%016X\t%d\t%s\t%s/%s\n' % (PACK_NAME % (n + 1), it.t, it.g, it.i, it.fsize,
                                                                    it.why, src['root'], src['rel']))
        staged += [man_path, keys_path]
        # the copy can take many minutes: the game may have been started meanwhile
        if check_game and game_running():
            raise JournalError('The Sims 4 was started during the build; nothing was moved. '
                               'Build again once it is closed.')
        # move into place. The old manifest goes first: until the new one arrives (last), out_dir has
        # no manifest, so is_stale() and verify() never take a half-replaced pack for a complete one.
        old_manifest = os.path.join(out_dir, MANIFEST)
        if os.path.exists(old_manifest):
            j.quarantine(old_manifest)
        new_names = {os.path.basename(p) for p in staged}
        if os.path.isdir(out_dir):
            for n in sorted(os.listdir(out_dir)):
                old = os.path.join(out_dir, n)
                if n not in new_names and (n.startswith('SpeedKit_UsedCC_') or n in (MANIFEST, KEYS_FILE)):
                    j.quarantine(old)
        for p in staged:
            final = os.path.join(out_dir, os.path.basename(p))
            if os.path.exists(final):
                j.replace(p, final)
            else:
                j.put_new(p, final)
        j.close('committed')
    except BaseException as ex:
        _close_all(files)
        j.close('failed: %s' % (ex,))
        for p in staged:
            if os.path.exists(p):
                os.remove(p)                 # our own staging copies, never user files
        _roll_back(j, home, out_dir, ex)
        raise
    finally:
        try:
            os.rmdir(staging)
        except OSError:
            pass
    for r in result:
        r['journal'] = j.id
    return result


def _close_all(files):
    for f in files.values():
        f.close()
    files.clear()


def _roll_back(j, home, out_dir, ex):
    """After a failed build: undo the journal's finished steps so out_dir holds the previous pack again."""
    if not any(s['done'] for s in j.steps):
        return
    try:
        undo(j.id, home=home, check_game=False)      # only moves SpeedKit's own pack files back
    except Exception as ux:
        raise JournalError('the build failed (%s) and undoing its journal %s failed too (%s); fix the cause and '
                           'run speedkit.journal.undo(%r)' % (ex, j.id, ux, j.id)) from ex
    ex.add_note('journal %s was undone: %s holds the previous pack again' % (j.id, out_dir))


def _inside(path, base):
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path == base or path.startswith(base.rstrip('\\/') + os.sep)


class PlanStale(Exception):
    """A source package changed after plan(): re-scan the library and plan again."""


def _find_source(dirs, p):
    """Path of a plan source package p ({'root', 'rel', 'size', 'mtime'}) with the size and mtime the
    plan saw: at its own root, or at the same relative path in another root (the other tool moves
    packages between Mods and Mods_parked; a move keeps size and mtime). PlanStale if there is none."""
    rel = p['rel'].replace('/', os.sep)
    cands = [os.path.join(dirs[p['root']], rel)]
    cands += [os.path.join(d, rel) for r, d in dirs.items() if r != p['root']]
    for c in cands:
        try:
            st = os.stat(c)
        except OSError:
            continue
        if st.st_size == p['size'] and abs(st.st_mtime - p['mtime']) < 1e-3:
            return c
    raise PlanStale('%s/%s changed since the plan (or is gone): re-scan the library and plan again'
                    % (p['root'], p['rel']))


def _check_sources(plan_):
    """{pkg_id: path} after checking each source package still has the size and mtime the plan saw."""
    return {pid: _find_source(plan_.root_dirs, p) for pid, p in plan_.packages.items()}


def _open_source(plan_, pid, paths):
    """Open source package pid for reading; if it was moved to the other root since it was last
    found, find it there (and remember the new path)."""
    try:
        return _open_read(paths[pid])
    except FileNotFoundError:
        paths[pid] = _find_source(plan_.root_dirs, plan_.packages[pid])
        return _open_read(paths[pid])


def _source_entries(plan_, paths):
    """{(pkg, t, g, i): Entry} for the planned copies, checked against the planned offsets and sizes."""
    want = collections.defaultdict(set)
    for it in plan_.items.values():
        want[it.pkg].add((it.t, it.g, it.i))
    out = {}
    for pid, keys in want.items():
        with _open_source(plan_, pid, paths) as f:
            for e in read_entries(f):
                k = (e.t, e.g, e.i)
                if k in keys and (pid,) + k not in out and e.comp != DELETED:
                    out[(pid,) + k] = e
    for it in plan_.items.values():
        e = out.get((it.pkg, it.t, it.g, it.i))
        if e is None or (e.off, e.fsize, e.msize, e.comp) != (it.off, it.fsize, it.msize, it.comp):
            raise PlanStale('%s %08X:%08X:%016X is not where the plan expects it' % (
                plan_.packages[it.pkg]['rel'], it.t, it.g, it.i))
    return out


def _manifest(plan_, groups, result):
    per_src = collections.defaultdict(lambda: [0, 0])
    for it in plan_.items.values():
        per_src[it.pkg][0] += 1
        per_src[it.pkg][1] += it.fsize
    return {
        'built': time.strftime('%Y-%m-%d %H:%M:%S'),
        'include_backups': plan_.include_backups,
        'roots': list(plan_.roots),
        'packages': [{'name': os.path.basename(r['path']), 'keys': r['keys'], 'bytes': r['bytes']} for r in result],
        'counts': {k: v for k, v in plan_.stats.items() if k != 'why'},
        'why': plan_.stats.get('why', {}),
        'bytes': plan_.total_bytes(),
        'saves_and_tray': plan_.sources,
        'sources': sorted(({'root': plan_.packages[pid]['root'], 'rel': plan_.packages[pid]['rel'],
                            'keys': n, 'bytes': by} for pid, (n, by) in per_src.items()), key=lambda s: -s['bytes']),
        'absent': {k: ['%016X' % v for v in vs] for k, vs in plan_.absent.items()},
        'unloadable': {k: ['%016X' % v for v in vs] for k, vs in plan_.unloadable.items()},
        'households_with_missing_cc': plan_.households,
    }


# ------------------------------------------------------------------------------------------ verify / stale
def read_manifest(out_dir):
    """The usedpack.json of a built pack, or None."""
    p = os.path.join(out_dir, MANIFEST)
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


VERIFY_CHECKS = ((PART, (T_CASP,)), (PART_OTHER, (T_CASP,)), (TONE, (T_TONE,)), (SCULPT, (T_SCUL,)),
                 (MODIFIER, (T_SMOD,)), (PELT, (T_PELT,)), (OBJECT, (T_OBJD, T_COBJ)))


def verify(out_dir, refs, game=None, include_absent=False, lib=None):
    """Referenced CC ids the pack in out_dir does not contain, as sorted [(category, 'hex id')].

    Checks the worn/other CAS parts (CASP), skin tones (TONE), sculpts (SCUL), sliders (SMOD), pet
    coats (PELT) and objects (OBJD, COBJ) of the same saves/Tray selection the pack was built from
    (ValueError if the pack counted .ver backups and refs were scanned without them).
    An empty list means every sim and lot finds its CC in the pack.

    With lib (a Library) the check is exact: every referenced id that has a copy the game would load
    from the library - CC or a library override of an EA id, whatever its size - must be in the pack;
    ids installed nowhere are listed only with include_absent. Without lib, 64-bit ids that are neither
    in the pack nor EA's are reported unless the build recorded them as installed nowhere / too deep to
    load (usedpack.json 'absent' / 'unloadable'; include_absent lists those too); small ids are skipped
    there, since without the library they cannot be told apart from EA ids."""
    man = read_manifest(out_dir)
    if man is None:
        raise FileNotFoundError('no %s in %s' % (MANIFEST, out_dir))
    if man.get('include_backups') and not refs.backups_scanned:
        raise ValueError('the pack was built with .ver backups; verify it with scan_references(include_backups=True)')
    game = game if game is not None else load_game_ids()
    have = set()
    for p in man['packages']:
        with _open_read(os.path.join(out_dir, p['name'])) as f:
            have.update((e.t, e.i) for e in read_entries(f))
    known_absent = set()
    for part in ('absent', 'unloadable'):
        for vs in man.get(part, {}).values():
            known_absent.update(int(v, 16) for v in vs)
    b = man.get('include_backups', False)
    loaded = None
    if lib is not None:
        pl = _Planner(lib, tuple(man.get('roots') or ('Mods', 'Mods_parked')), game)
        want = set().union(*(refs.ids(cat, b) for cat, types in VERIFY_CHECKS))
        rows, _ = pl.by_instance({t for cat, types in VERIFY_CHECKS for t in types}, want)
        loaded = {(k[0], k[2]) for k in rows}
    out = set()
    for cat, types in VERIFY_CHECKS:
        for v in refs.ids(cat, b):
            if loaded is not None:
                if any((t, v) in loaded and (t, v) not in have for t in types):
                    out.add((cat, '%016X' % v))
                elif (include_absent and cat != PART_OTHER and v >= BIG and not any((t, v) in loaded for t in types)
                      and not any(game.has(t, v) for t in types)):
                    out.add((cat, '%016X' % v))
                continue
            if any((t, v) in have for t in types) or any(game.has(t, v) for t in types):
                continue
            if v < BIG or (v in known_absent and not include_absent):
                continue
            if cat == PART_OTHER:
                continue       # other-path part ids are only packed when installed; unknown ones are not CC evidence
            out.add((cat, '%016X' % v))
    return sorted(out)


def is_stale(out_dir, saves_dir=SAVES, tray_dir=TRAY):
    """True when the saves/Tray changed after the pack in out_dir was built (a new or changed file),
    or when there is no pack. Cheap: size+mtime first, content fingerprint only for files that differ."""
    man = read_manifest(out_dir)
    if man is None:
        return True
    rec = man.get('saves_and_tray', [])
    quick = {(r['name'], r['size'], r['mtime_ns']) for r in rec}
    fps = {r['fp'] for r in rec}
    b = man.get('include_backups', False)
    for path, kind in list_sources(saves_dir, tray_dir):
        if kind == 'backup' and not b:
            continue
        try:
            st = os.stat(path)
            if (os.path.basename(path), st.st_size, st.st_mtime_ns) in quick:
                continue
            if fingerprint(path, st.st_size) not in fps:
                return True
        except OSError:
            continue
    return False


# ------------------------------------------------------------------------------------------ CLI
def main(argv=None):
    """CLI: python -m speedkit.usedpack scan|plan|missing|build [--really]|verify|stale [--backups]."""
    import argparse
    ap = argparse.ArgumentParser(description='Lean pack of the CC your sims and lots use.')
    ap.add_argument('cmd', choices=['scan', 'plan', 'build', 'verify', 'stale', 'missing'])
    ap.add_argument('--backups', action='store_true', help='also count .ver backup saves')
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--library', default=None, help='library.sqlite to read (default data/library.sqlite)')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--really', action='store_true', help='build: write the pack (default is a dry run)')
    a = ap.parse_args(argv)
    refs = scan_references(workers=a.workers, include_backups=a.backups, verbose=True)
    print('refs: %d sources, %d parsed, %.0fs; errors: %s' % (refs.stats['sources'], refs.stats['parsed'],
                                                              refs.stats['seconds'], refs.stats['errors'] or 'none'))
    if a.cmd == 'scan':
        for cat in CATEGORIES:
            print('  %-13s %7d distinct ids' % (cat, len(refs.ids(cat, a.backups))))
        return
    lib = Library(a.library) if a.library else Library()       # read only: never scanned here
    if a.cmd == 'verify':
        miss = verify(a.out, refs, lib=lib)
        print('pack is complete' if not miss else '%d referenced CC ids are not in the pack' % len(miss))
        for cat, v in miss[:50]:
            print('  ', cat, v)
        return
    if a.cmd == 'stale':
        print('stale' if is_stale(a.out) else 'up to date')
        return
    p = plan(lib, refs, include_backups=a.backups, verbose=True)
    if a.cmd == 'missing':
        for g in p.households:
            print('%-40s %4d parts %3d looks  %s' % (g['household'][:40], len(g['missing_parts']),
                                                    len(g['missing_looks']), ', '.join(g['sources'])[:60]))
        return
    s = p.summary()
    print('plan: %d keys, %.2f GB (%.2f GB uncompressed) from %d packages; %d households wear CC installed nowhere'
          % (s['keys'], s['bytes'] / 1e9, s['bytes_uncompressed'] / 1e9, s['source_packages'], len(p.households)))
    for t, n in s['by_type_bytes'].items():
        print('  %-10s %7d keys %8.1f MB' % (t, s['by_type_count'][t], n / 1e6))
    if a.cmd == 'build':
        for r in build(p, a.out, dry_run=not a.really, verbose=True):
            print('%s %-60s %6d keys %6.2f GB' % ('wrote' if a.really else 'would write', r['path'], r['keys'],
                                                  r['bytes'] / 1e9))


if __name__ == '__main__':
    main()

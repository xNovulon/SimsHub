"""Pose packs for Andrew's Pose Player, laid out exactly like the ones Sims 4 Studio makes.

The layout was copied from real S4S pose packs in the user's parked Mods (read only, 2026-09-24): 150+ packs merged
into Mods_parked\\animation\\anim1.package and Mods_parked\\sim\\*.package. The reference used by the checks is
"Kd89_3dstudios:PosePack_202501180016151289" ("[Kd89] She knows how to play - Animation", an adult couple - "F (Sim)"
and "M (Sim)" - on a couch, S4S 2025). Every S4S pose pack has the same resources:

  - 1 snippet tuning (0x7DF2169C, group 0, instance = FNV64(name) | high bit), class PosePackInstance, module
    poseplayer, one line of XML: s4s_mod_type POSE_PACK, display_name / description / creator_name (string keys),
    sort_name (plain text), icon, and pose_list of <U> entries {pose_name, pose_display_name, pose_description,
    sort_order, icon}. The name is "<creator>:PosePack_<digits>" and each pose_name is "<name>_set_<n>".
  - per pose: 1 CLIP (0x6B20C4F3) + 1 clip header (0xBC4A5044), instance = FNV64(pose_name) (no high bit), rig
    namespace 'x', version 14; most S4S pose clips are 2 ticks long (306 of 773 measured) and carry clip event 19
    (1, 256, 0.0, 1000.0) (the face stays as posed - no lip-sync over it).
  - 1 picture per pose + 1 for the pack: type 0x00B2D882 (a DDS 'DST5', EA's shuffled DXT5), 64 x 64 with all 7
    mipmaps - the size S4S writes (the most common size by far: 301 pose icons and 102 pack icons measured). The
    tuning names it as '2f7d0004:00000000:<instance>', exactly like S4S does.
  - 18 string tables (0x220557DA, group 0x80000000), one per game language (the language code is the instance's
    top byte: 00 01 02 03 04 05 06 07 08 0B 0C 0D 0E 0F 11 12 13 15), each with the same strings (STBL version 5).

Adults only: Pose Player plays any clip on any sim, teens included, so a pose pack is NON-EXPLICIT ONLY. lock()
refuses nude outfit settings, genital or opening bone keys (or an opening that is open in a chosen pose), a
WickedWhims act (an act kind, act tags, moments, a strap-on) - and says so in one line. Genital bones are also never
written into a pose clip (they stay at rest). Anything explicit goes to the game through WickedWhims, which checks
ages.

Nothing here touches the game or the Mods folder by itself: build() makes the resources, write() puts them in the
folders it is given (ext_share decides which).
"""
import datetime, math, os, re, struct
from xml.sax.saxutils import escape

import exporter as X
import wwpackage as W
from clipfmt import fnv32, fnv64, write_clip

T_SNIPPET = 0x7DF2169C
T_CLIP, T_CLIP_HEADER = 0x6B20C4F3, 0xBC4A5044
T_IMG = 0x00B2D882            # the picture itself (DDS 'DST5')
ICON_KEY_TYPE = 0x2F7D0004    # the type the tuning names in its icon keys (as S4S writes it)
T_STBL = 0x220557DA
STBL_GROUP = 0x80000000
LOCALES = (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12, 0x13, 0x15)
ICON = 64                     # S4S pose-pack pictures: 64 x 64, DST5, 7 mipmaps
POSE_TICKS = 2                # S4S pose clips: 2 ticks holding one pose
LIPSYNC_OFF = (19, struct.pack('<IIff', 1, 256, 0.0, 1000.0))
SOURCE = "Novulon's Wicked Animator"
MAX_POSES = 200

# ------------------------------------------------------------------ the adults-only lock
# WickedWhims act kinds that are sex acts (Teasing is the only kind a clothed, non-explicit pose can have).
EXPLICIT_KINDS = {'HANDJOB': 'Handjob', 'FOOTJOB': 'Footjob', 'ORALJOB': 'Oral', 'VAGINAL': 'Vaginal', 'ANAL': 'Anal',
                  'CLIMAX': 'Climax'}
# Tags that say "sex": positions, acts (kissing is fine), finishes, kinks, group sex, toys. The app's own tag list
# (web/js/tags.js); neutral ones (standing, sitting, moods, supernatural, dance, story...) are allowed.
EXPLICIT_TAGS = set('''COWGIRL DOGGY MISSIONARY SPOONING PRONEBONE PILEDRIVER SIXTYNINE FACE_SITTING SPITROAST
BLOWJOB DEEP_THROAT CUNNILINGUS RIMJOB LICKING FINGERING MASTURBATION TITJOB THIGHJOB BUTTJOB GROPING TITS_SUCKING
TOES_SUCKING SPANKING CHOKING DOUBLE_PENETRATION FISTING PEEING FOREPLAY
CLIMAX CUMSHOT CREAMPIE CUM_INSIDE CUM_IN_MOUTH BUKKAKE SQUIRT
FEMDOM MALEDOM BDSM FORCED FREEUSE CUCK ONLOOKER SLEEPING WEIRD GROSS
FUTA THREESOME FOURSOME ORGY GANGBANG HAREM TOY DILDO UNDER_COVERS VAGINAL ANAL ORALJOB HANDJOB FOOTJOB'''.split())
PENIS = ('b__Penis_Base', 'b__Penis_Base01', 'b__Penis_Mid', 'b__Penis_Mid01', 'b__Penis_Tip', 'b__Penis_Testicles',
         'b__Penis_L_Testicle', 'b__Penis_R_Testicle')
OPENINGS = ('b__Up_Vagina__', 'b__Low_Vagina__', 'b__Anus', 'b__L_Anus__', 'b__R_Anus__', 'b__Up_Anus', 'b__Low_Anus')
GENITAL = frozenset(PENIS + OPENINGS)
OPEN_DEG = 4.0                         # an opening turned this far from rest in a chosen pose = it is open


def _nice(s):
    return str(s or '').replace('_', ' ').lower().capitalize()


def lock(meta, poses=(), rig=None):
    """Reasons this can't be a pose pack ([] = fine). meta = {category, tags, events, actors: [{naked, strapon,
    invisibleTeeth, keyed: [bone names keyed by hand], open: an opening moved away from this sim's own rest}]};
    poses = [{sim, tracks}] (the chosen poses); rig = the adult rig ({'bones': [{name, pos, rot}]}) to tell an open
    opening from one at rest."""
    reasons = []
    kind = str(meta.get('category') or '').upper()
    tags = [str(t).upper() for t in meta.get('tags') or []]
    acts = [EXPLICIT_KINDS[kind]] if kind in EXPLICIT_KINDS else []
    acts += [_nice(t) for t in tags if t in EXPLICIT_TAGS and _nice(t) not in acts]
    if acts:
        reasons.append('a WickedWhims act (%s)' % ', '.join(acts[:3]) + (' ...' if len(acts) > 3 else ''))
    if meta.get('events'):
        reasons.append('WickedWhims moments (cum, undress, effects)')
    actors = meta.get('actors') or []
    if any(str(a.get('naked') or 'NONE').upper() != 'NONE' for a in actors):
        reasons.append('undressed sims')
    if any(a.get('strapon') for a in actors):
        reasons.append('a strap-on')
    if any(a.get('invisibleTeeth') for a in actors):
        reasons.append('a mouth opened by a penis')
    keyed = sorted({b for a in actors for b in (a.get('keyed') or []) if b in GENITAL})
    if keyed:
        reasons.append('genital or opening keys')
    opened = any(a.get('open') for a in actors)
    if not opened and rig and poses:
        rest = {b['name']: b for b in rig.get('bones', [])}
        opened = any(_opening_open(p.get('tracks') or {}, rest) for p in poses)
    if opened:
        reasons.append('an opening that is open')
    return reasons


def _opening_open(tracks, rest):
    """Is an opening turned away from the rig's rest in this one-frame pose? (Turns only: a Tray sim's body moves
    the bones' rest places a little, so places are checked in the app against each sim's own rest - actor 'open'.)"""
    for n in OPENINGS:
        tr, b = tracks.get(n), rest.get(n)
        if not tr or not b:
            continue
        r = (tr.get('r') or [None])[0]
        if r:
            d = abs(sum(x * y for x, y in zip(_unit(r), _unit(b['rot']))))
            if 2 * math.degrees(math.acos(min(1.0, d))) > OPEN_DEG:
                return True
    return False


def _unit(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return [c / n for c in q]


def lock_message(reasons):
    """The one line the app shows when a pose pack is refused."""
    said = reasons[0] if len(reasons) == 1 else ', '.join(reasons[:-1]) + ' and ' + reasons[-1]
    return ('Pose packs are for non-explicit poses only - Pose Player can put a pose on any sim, teens too. This one has '
            + said + '. Explicit animations go to the game through WickedWhims (Send to game), which checks ages.')


class Refused(ValueError):
    """A pose pack the adults-only lock refuses (-> HTTP 400 with the one-line message)."""

    def __init__(self, reasons):
        super().__init__(lock_message(reasons))
        self.reasons = reasons


# ------------------------------------------------------------------ pictures: DDS 'DST5', 64 x 64, 7 mipmaps
def _resize(rgba, w, h, nw, nh):
    """Box-filtered resize of RGBA bytes (any size -> nw x nh)."""
    if (w, h) == (nw, nh):
        return bytes(rgba)
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        y0, y1 = y * h // nh, max(y * h // nh + 1, (y + 1) * h // nh)
        for x in range(nw):
            x0, x1 = x * w // nw, max(x * w // nw + 1, (x + 1) * w // nw)
            acc = [0, 0, 0, 0]
            n = 0
            for yy in range(y0, y1):
                row = (yy * w) * 4
                for xx in range(x0, x1):
                    i = row + xx * 4
                    acc[0] += rgba[i]; acc[1] += rgba[i + 1]; acc[2] += rgba[i + 2]; acc[3] += rgba[i + 3]
                    n += 1
            o = (y * nw + x) * 4
            out[o:o + 4] = bytes((a + n // 2) // n for a in acc)
    return bytes(out)


def _half(rgba, w, h):
    nw, nh = max(1, w // 2), max(1, h // 2)
    return _resize(rgba, w, h, nw, nh), nw, nh


def _565(c):
    return ((c[0] * 31 + 127) // 255) << 11 | ((c[1] * 63 + 127) // 255) << 5 | ((c[2] * 31 + 127) // 255)


def _from565(v):
    r, g, b = (v >> 11) & 31, (v >> 5) & 63, v & 31
    return ((r * 527 + 23) >> 6, (g * 259 + 33) >> 6, (b * 527 + 23) >> 6)


def _colour_block(px):
    """16 RGB pixels -> (c0, c1, 32-bit indices) of a BC1/BC3 colour block (4-colour mode, c0 > c1)."""
    n = len(px)
    mean = [sum(p[k] for p in px) / n for k in range(3)]
    # the main direction the colours spread in (a few power steps on their covariance)
    cov = [[sum((p[i] - mean[i]) * (p[j] - mean[j]) for p in px) for j in range(3)] for i in range(3)]
    axis = [1.0, 1.0, 1.0]
    for _ in range(6):
        v = [sum(cov[i][j] * axis[j] for j in range(3)) for i in range(3)]
        m = max(abs(x) for x in v)
        if m < 1e-9:
            break
        axis = [x / m for x in v]
    proj = [sum((p[k] - mean[k]) * axis[k] for k in range(3)) for p in px]
    lo, hi = px[proj.index(min(proj))], px[proj.index(max(proj))]
    # a little inset keeps the end colours from being too extreme
    inset = lambda a, b: [min(255, max(0, round(a[k] + (b[k] - a[k]) / 32))) for k in range(3)]
    c0, c1 = _565(inset(hi, lo)), _565(inset(lo, hi))
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return c0, c1, 0
    p0, p1 = _from565(c0), _from565(c1)
    pal = [p0, p1, tuple((2 * a + b) // 3 for a, b in zip(p0, p1)), tuple((a + 2 * b) // 3 for a, b in zip(p0, p1))]
    bits = 0
    for i, p in enumerate(px):
        best = min(range(4), key=lambda k: (p[0] - pal[k][0]) ** 2 + (p[1] - pal[k][1]) ** 2 + (p[2] - pal[k][2]) ** 2)
        bits |= best << (2 * i)
    return c0, c1, bits


def _alpha_block(al):
    """16 alpha values -> (a0, a1, 48-bit indices) of a BC3 alpha block."""
    a0, a1 = max(al), min(al)
    if a0 == a1:
        return a0, a1, 0
    pal = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    bits = 0
    for i, a in enumerate(al):
        best = min(range(8), key=lambda k: abs(a - pal[k]))
        bits |= best << (3 * i)
    return a0, a1, bits


def dst5(rgba, w, h):
    """RGBA bytes (w x h, multiples of 4 down to the 4x4 mips) -> a DDS 'DST5' with every mipmap, exactly the header
    S4S writes. DST5 = DXT5 blocks stored field by field over all mips: [alpha ends 2B][colour ends 4B][alpha
    indices 6B][colour indices 4B] for every block."""
    levels, cw, ch, cur = [], w, h, bytes(rgba)
    while True:
        levels.append((cur, cw, ch))
        if cw == 1 and ch == 1:
            break
        cur, cw, ch = _half(cur, cw, ch)
    a_end, c_end, a_idx, c_idx = bytearray(), bytearray(), bytearray(), bytearray()
    for data, lw, lh in levels:
        for by in range(0, max(1, lh), 4):
            for bx in range(0, max(1, lw), 4):
                px, al = [], []
                for y in range(4):
                    for x in range(4):
                        xx, yy = min(lw - 1, bx + x), min(lh - 1, by + y)
                        i = (yy * lw + xx) * 4
                        px.append((data[i], data[i + 1], data[i + 2]))
                        al.append(data[i + 3])
                a0, a1, abits = _alpha_block(al)
                c0, c1, cbits = _colour_block(px)
                a_end += bytes((a0, a1))
                a_idx += abits.to_bytes(6, 'little')
                c_end += struct.pack('<HH', c0, c1)
                c_idx += struct.pack('<I', cbits)
    head = bytearray(128)
    head[0:4] = b'DDS '
    struct.pack_into('<7I', head, 4, 124, 0x21007, h, w, 0, 1, len(levels))
    struct.pack_into('<II4s', head, 76, 32, 4, b'DST5')
    struct.pack_into('<I', head, 108, 0x401008)
    return bytes(head) + bytes(a_end) + bytes(c_end) + bytes(a_idx) + bytes(c_idx)


def icon_dds(pic):
    """{w, h, rgba: bytes} (any size) -> the 64 x 64 DST5 picture S4S writes."""
    w, h, rgba = int(pic['w']), int(pic['h']), pic['rgba']
    if w <= 0 or h <= 0 or len(rgba) != w * h * 4:
        raise ValueError('A pose picture came through broken - try again.')
    return dst5(_resize(rgba, w, h, ICON, ICON), ICON, ICON)


def blank_icon():
    """A plain picture (the app's plum colour) for a pose sent without one."""
    return dst5(bytes((58, 40, 70, 255)) * (ICON * ICON), ICON, ICON)


# ------------------------------------------------------------------ string table (STBL version 5)
def stbl(strings):
    """{key: text} -> STBL bytes: 'STBL', version 5, not compressed, count, 2 zero bytes, total text size (each
    text + 1), then key, flags 0, length, UTF-8 text."""
    body, total = bytearray(), 0
    for k, s in strings.items():
        b = str(s).encode('utf-8')
        body += struct.pack('<IBH', k, 0, len(b)) + b
        total += len(b) + 1
    return b'STBL' + struct.pack('<HBQHI', 5, 0, len(strings), 0, total) + bytes(body)


def read_stbl(data):
    """STBL bytes -> {key: text} (for the checks)."""
    if data[:4] != b'STBL':
        raise ValueError('not a string table')
    n = struct.unpack_from('<Q', data, 7)[0]
    off, out = 21, {}
    for _ in range(n):
        k, _fl, ln = struct.unpack_from('<IBH', data, off)
        off += 7
        out[k] = data[off:off + ln].decode('utf-8', 'replace')
        off += ln
    return out


# ------------------------------------------------------------------ names
def _ascii(s, limit=48):
    s = re.sub(r"[^A-Za-z0-9 _.()\[\]{}'&+-]+", '', str(s or '')).strip()
    return ' '.join(s.split())[:limit].strip()


def pack_name(author, title, uid=''):
    """'<creator>:PosePack_<18 digits>' like S4S - the digits come from the animation and the pack title, so the same
    pack exported again replaces itself in the game instead of showing up twice."""
    creator = _ascii(author, 32) or 'WickedAnimator'
    digits = fnv64('%s|%s|%s' % (uid or '', creator, title or '')) % 10 ** 18
    return '%s:PosePack_%018d' % (creator, digits)


def snippet_xml(name, display, sort_name, description, creator, icon, poses):
    """The pack's tuning, one line, field for field as S4S writes it. poses: [(pose_name, display, description, icon)]."""
    inst = W.instance_id(name)
    items = ''.join('<U><T n="pose_name">%s</T><T n="pose_display_name">0x%08X</T><T n="pose_description">0x%08X</T>'
                    '<T n="sort_order">%d</T><T n="icon">%08x:00000000:%016x</T></U>'
                    % (escape(pn), pd, pdesc, i + 1, ICON_KEY_TYPE, pic) for i, (pn, pd, pdesc, pic) in enumerate(poses))
    return ('<?xml version="1.0" encoding="utf-8"?><I s="%d" n="%s" c="PosePackInstance" i="snippet" m="poseplayer">'
            '<T n="s4s_mod_type">POSE_PACK</T><T n="display_name">0x%08X</T><T n="sort_name">%s</T>'
            '<T n="description">0x%08X</T><T n="creator_name">0x%08X</T><T n="icon">%08x:00000000:%016x</T>'
            '<L n="pose_list">%s</L></I>') % (inst, escape(name, {'"': '&quot;'}), display, escape(sort_name), description,
                                                creator, ICON_KEY_TYPE, icon, items)


# ------------------------------------------------------------------ the pack
def pose_tracks(tracks, index=0):
    """One frame of baked tracks ({bone: {t: [...], r: [...]}}) as a one-frame actor; genital bones are left out
    (they stay at rest in a pose clip)."""
    out = {}
    for bone, tr in (tracks or {}).items():
        if bone in GENITAL or not isinstance(tr, dict):
            continue
        one = {}
        for k in ('t', 'r'):
            seq = tr.get(k)
            if seq:
                one[k] = [list(seq[min(index, len(seq) - 1)])]
        if one:
            out[bone] = one
    return out


def build(req, rig=None):
    """req = {name, author, description, uid, meta: {category, tags, events, actors: [...]},
              poses: [{label, description, sim, tracks: {bone: {t: [xyz], r: [xyzw]}} (one frame), icon: {w, h, rgba}}],
              icon: {w, h, rgba} (the pack's picture)}
    -> (resources, info). Raises Refused when the adults-only lock says no, ValueError for a bad request."""
    poses = req.get('poses') or []
    if not poses:
        raise ValueError('Pick at least one pose.')
    if len(poses) > MAX_POSES:
        raise ValueError('A pose pack holds at most %d poses.' % MAX_POSES)
    reasons = lock(req.get('meta') or {}, poses, rig)
    if reasons:
        raise Refused(reasons)
    title = ' '.join(str(req.get('name') or '').split())[:80] or 'My poses'
    author = ' '.join(str(req.get('author') or '').split())[:40]
    name = pack_name(author, title, req.get('uid'))
    strings, used = {}, set()

    def key(label, text):
        if not text:
            return 0
        k = fnv32('%s:%s' % (name, label)) or 1
        while k in used:
            k = (k * 16777619 + 1) & 0xFFFFFFFF or 1
        used.add(k)
        strings[k] = text
        return k

    creator_k = key('creator', author or 'Wicked Animator')
    display_k = key('display', title)
    desc_k = key('description', ' '.join(str(req.get('description') or '').split())[:200]
                 or "Made with Novulon's Wicked Animator")
    resources, entries, clips = [], [], []
    pack_icon = fnv64(name + ':icon:pack')
    resources.append((T_IMG, 0, pack_icon, icon_dds(req['icon']) if req.get('icon') else blank_icon()))
    for i, p in enumerate(poses):
        pose_name = '%s_set_%d' % (name, i + 1)
        actor = {'tracks': pose_tracks(p.get('tracks') or {}, 0)}
        clip, header = write_clip(pose_name, 'x', POSE_TICKS, X.actor_channels(actor, 1), source=SOURCE,
                                  events=(LIPSYNC_OFF,), tick_length=1.0 / 30.0)
        inst = fnv64(pose_name)
        resources.append((T_CLIP, 0, inst, clip))
        resources.append((T_CLIP_HEADER, 0, inst, header))
        pic = fnv64('%s:icon:%d' % (name, i + 1))
        resources.append((T_IMG, 0, pic, icon_dds(p['icon']) if p.get('icon') else blank_icon()))
        label = ' '.join(str(p.get('label') or 'Pose %d' % (i + 1)).split())[:80]
        entries.append((pose_name, key('pose:%d' % i, label), key('pose_desc:%d' % i, ' '.join(str(p.get('description') or '').split())[:200]), pic))
        clips.append(pose_name)
    xml = snippet_xml(name, display_k, title, desc_k, creator_k, pack_icon, entries).encode('utf-8')
    resources.insert(0, (T_SNIPPET, 0, W.instance_id(name), xml))
    table = stbl(strings)
    low = fnv64(name + ':strings') & 0x00FFFFFFFFFFFFFF
    for loc in LOCALES:
        resources.append((T_STBL, STBL_GROUP, (loc << 56) | low, table))
    return resources, {'name': name, 'title': title, 'author': author, 'poses': len(poses), 'clips': clips,
                       'strings': len(strings)}


def structure(resources):
    """What a pack is made of (for the checks): resource counts by type, icon format, languages."""
    counts = {}
    for t, g, i, d in resources:
        counts['%08X' % t] = counts.get('%08X' % t, 0) + 1
    icons = {(struct.unpack_from('<I', d, 16)[0], struct.unpack_from('<I', d, 12)[0], d[84:88].decode('latin1'),
              struct.unpack_from('<I', d, 28)[0]) for t, g, i, d in resources if t == T_IMG and d[:4] == b'DDS '}
    langs = sorted('%02X' % (i >> 56) for t, g, i, d in resources if t == T_STBL)
    return {'types': counts, 'icons': sorted(icons), 'languages': langs}


# ------------------------------------------------------------------ files
def readme(info, poses, when=None):
    lines = ['%s%s' % (info['title'], ' by ' + info['author'] if info['author'] else ''), '=' * 60, '',
             "A pose pack for Andrew's Pose Player, made with Novulon's Wicked Animator.",
             'Non-explicit poses only.', '',
             'NEEDS: Pose Player by Andrew (and Teleport Any Sim to put sims on one spot).', '',
             'INSTALL', '  Put "%s" in Documents\\Electronic Arts\\The Sims 4\\Mods (a sub-folder is fine).' % info['file'],
             '', 'POSES (%d)' % len(poses)]
    for i, p in enumerate(poses):
        lines.append('  %d. %s' % (i + 1, ' '.join(str(p.get('label') or 'Pose %d' % (i + 1)).split())))
    lines += ['', 'COUPLES: every sim in a pose shares one spot. Put the sims on the same spot (Teleport Any Sim, or',
              "Pose Player's own move), then give each one its pose - they line up by themselves.",
              '', 'Made on %s.' % (when or datetime.date.today().isoformat())]
    return '\n'.join(lines) + '\n'


def write(req, exports_dir, mods_dir=None, rig=None):
    """Build the pack and write it: <exports_dir>/<title> - Pose pack/<file>.package + README.txt, and (install)
    also <mods_dir>/FitStudio/PosePacks/<file>.package. -> the result the app shows."""
    resources, info = build(req, rig)
    base = X._safe_file(info['title'] + (' by ' + info['author'] if info['author'] else ''))
    fname = base + ' - Pose pack'
    folder = os.path.join(exports_dir, fname)
    root = os.path.realpath(exports_dir)
    if os.path.commonpath([os.path.realpath(folder), root]) != root or os.path.realpath(folder) == root:
        raise ValueError('Pick another name for the pose pack.')
    info['file'] = base + '.package'
    pkg = os.path.join(folder, info['file'])
    size = X._write(pkg, resources)
    with open(os.path.join(folder, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write(readme(info, req.get('poses') or []))
    installed = None
    if req.get('install') and mods_dir:
        installed = os.path.join(mods_dir, 'FitStudio', 'PosePacks', info['file'])
        X._write(installed, resources)
    return {'folder': folder, 'package': pkg, 'file': info['file'], 'bytes': size, 'poses': info['poses'],
            'name': info['name'], 'title': info['title'], 'installed': installed, 'structure': structure(resources)}

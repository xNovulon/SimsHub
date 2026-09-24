"""Which packages belong to a script mod, and which are safe to merge.

A "companion" is a .package that only works together with a script mod (.ts4script): its tuning
names a Python module or class the script defines, the script looks its resources up by id or name,
or it declares the script as a requirement. Merging such a package into a CC pack breaks the
pairing (the script gets updated or removed, the stale tuning stays), so a merger must leave it
alone. Ported from research/merging/companions.py, with the skeptic's corrections applied.

Evidence per package (strongest first):
  module    XML tuning root m="..." (or module tuning <M n="...">) names a module whose top-level
            package is not one of the game's own (base/core/simulation.zip); resolved to the
            .ts4script that ships it, or "missing" if none does.
  class     c="..." is neither a game class nor in the game's strings; resolved to the script whose
            bytecode has that name (e.g. snippet types a mod registers), or "missing".
  insttype  i="..." (instance-tuning type) is not a game type; resolved the same way.
  restype   an XML tuning resource whose type is not in sims4.resources.Types, named by a script.
  nameref   an instance tuning's name (n="...", 8+ chars, not a game string) is a string constant
            in a script (the script fetches it by name).
  idref     a tuning/SimData/string resource whose 64-bit instance id (> 2^32) is an int constant
            in a script. The same match on any other type (CAS parts, sliders) is only "idref_asset".
  requires  a PlumbBuddy / Llama Logic "Mod File Manifest" snippet lists required_mods; each name
            is matched to an installed script, or to another package's manifest name (then the
            link is inherited from that package), or it is "missing".
  samename  the package and the script have the same name once "_Scripts"/"_Tuning" style
            suffixes are removed (UI_Cheats_Extension.package + UI_Cheats_Extension_Scripts).
  name      weak: the package name starts with the script's creator tag + next word, or with the
            whole script name (e.g. "LittleMsSam_FirstLove_Addon_...").

Verdict kinds: core (ships with its script), addon (third-party content that needs a script, e.g.
WickedWhims animation packs), orphan (needs at least one script / required mod that is not in the
library, or a class EA removed), weak (name or asset-id link only), tuning (XML tuning, no script
link), cc (no tuning at all), empty (no live resources), broken (index unreadable or file missing).
never_merge() is True for core, addon, orphan, weak and broken: the research verdict is that the
classification is heuristic, so 'weak' and 'orphan' are kept out of merges too.

Facts it relies on: the game imports only .pyc/.pyo from a .ts4script (never .py); Mods_parked
mirrors Mods paths, so scripts in both roots count as the library's scripts; Client_* classes are
C++-side tuning (not Python). XML sniffing reads tolerant zlib (two LittleMsSam packages carry
truncated streams the game accepts).

Cache: data/companions.sqlite keeps per-package XML facts and per-script bytecode facts keyed by
(root, rel, size, mtime), and the last verdicts with the signature of the script set they were
computed against, so a re-run only reads what changed. idref uses the library index (library.sqlite)
- scan the library first if files moved.
"""
import collections
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import time
import zipfile
import zlib
from collections import namedtuple

from .dbpf import Package, ZLIB, DELETED, decompress
from .library import PROJECT, signed64, unsigned64
from . import manifest

sys.path.insert(0, os.path.join(PROJECT, 'tools'))
from pyc37 import load as load_pyc, Code  # noqa: E402

GAME_DIR = r'E:\The Sims 4'
GAME_ZIPS = ('base.zip', 'core.zip', 'simulation.zip')
DEFAULT_CACHE = os.path.join(PROJECT, 'data', 'companions.sqlite')
FACTS_VERSION = 4          # bump when the extracted facts change shape (4: single-quoted / spaced XML attributes)
RULES_VERSION = 4          # bump when the verdict rules change (invalidates cached verdicts only)
MAX_XML = 8 << 20

Verdict = namedtuple('Verdict', 'kind script reasons')
KINDS = ('core', 'addon', 'orphan', 'weak', 'tuning', 'cc', 'empty', 'broken')
NEVER_MERGE = {'core', 'addon', 'orphan', 'weak', 'broken'}

ROOT_RX = re.compile(rb'<([IM])\s([^>]*)>')
# XML allows 'single' quotes and spaces around '=': missing m=/i= would turn a companion into mergeable CC.
ATTR_RX = re.compile(rb'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
MFM_MODULE = 'llamalogic.snippets.modfilemanifest'
MFM_NAME_RX = re.compile(rb'<T n="name">([^<]*)</T>')
REQ_START = b'<L n="required_mods">'
REQ_END_RX = re.compile(rb'<L n="(?!creators"|hashes")|</I>')
REQ_NAME_RX = re.compile(rb'<U>\s*<T n="name">([^<]*)</T>')
NAME_TOKEN = re.compile(r'[A-Za-z0-9]+')
NAME_SUFFIXES = {'script', 'scripts', 'tuning', 'tunings'}

# Big binary types that never hold tuning XML (CAS parts, images, meshes, clips, thumbnails, string
# tables, SimData, the S4S manifest ...): not sniffed.
BINARY_TYPES = {0x034AEECB, 0x3453CF95, 0x3C1AF1F2, 0x015A1849, 0x6B20C4F3, 0xBC4A5044, 0x2BC04EDF,
                0x00B2D882, 0xAC16FBEC, 0xBA856C78, 0x220557DA, 0x545AC67A, 0x3C2A8647, 0x01A527DB,
                0xFD04E3BE, 0x319E4F1D, 0xC0DB5AE7, 0x01D10F34, 0xDB43E069, 0xB6C8B6A0, 0x7FB6AD8A,
                0x01661233, 0x0166038C, 0x62ECC59A, 0x376840D7, 0xC5F6763E, 0xEAA32ADD, 0x0354796A,
                0x9D1AB874, 0xD382BF57, 0x81CA1A10, 0x03B4C61D, 0x8B18FF6E, 0x01D0E75D, 0x062C8204,
                0x16CA6BC4, 0xB4F762C9, 0xD5F0F921, 0x736884F1, 0x01357924, 0xB0118C15, 0xBDD82221}
# Besides tuning types, a script looks these up by id: SimData, string tables, combined tuning.
LOOKUP_TYPES_EXTRA = {0x545AC67A, 0x220557DA, 0x62E94D38}

# Big int constants in scripts that are masks or hash parameters, not resource ids.
NOT_IDS = {0xFFFFFFFFFFFFFFFF, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000, 0xFFFFFFFF00000000, 0x100000000,
           0xCBF29CE484222325, 0x100000001B3}

# Load order: names built to sort first or last (NTFS upper-cased order: '!' < digits < letters <
# '[' < '_' < '~'), plus mods whose instructions say they must win by position.
ORDER_PREFIX_RX = re.compile(r'^(!|~|_|\[|zz|0\d|0[ _\-.]|\d+[ _\-]+\D)', re.I)
ORDER_RELIANT_RX = [re.compile(r'northern siberia winds.*lighting', re.I)]

SCHEMA = """
create table if not exists meta(key text primary key, value text);
create table if not exists facts(root text, rel text, size integer, mtime real, data text, primary key(root, rel));
create table if not exists scriptfacts(root text, rel text, size integer, mtime real, data text, primary key(root, rel));
create table if not exists verdict(root text, rel text, size integer, mtime real, sig text, kind text, script text,
                                   reasons text, primary key(root, rel));
"""


# ---------------------------------------------------------------- small helpers
def load_order_sensitive(rel):
    """True if the package's position in the load order is part of how it works: a file or folder
    name starting with '!', '~', '_', '[', 'zz', a zero-padded or numbered prefix ('000', '01_',
    '1 - '), or a mod known to rely on loading first (NORTHERN SIBERIA WINDS lighting). Plain
    numbers such as S4S batch merges ('sim/111.package') are not flagged. Such files should keep
    their name and place: never merge or rename them."""
    parts = rel.replace('\\', '/').split('/')
    stem = parts[-1][:-len('.package')] if parts[-1].lower().endswith('.package') else parts[-1]
    for name in parts[:-1] + [stem]:
        if ORDER_PREFIX_RX.match(name.strip()):
            return True
    return any(rx.search(rel) for rx in ORDER_RELIANT_RX)


def never_merge(verdict):
    """True if a package with this verdict must stay a separate file (see module docstring)."""
    return verdict.kind in NEVER_MERGE


def _root_names(roots):
    """roots as a tuple; a single name is accepted ('Mods_parked' must not mean "any root inside it")."""
    return (roots,) if isinstance(roots, str) else tuple(roots)


def _tokens(stem):
    return [t.lower() for t in NAME_TOKEN.findall(stem)]


def _base_tokens(stem):
    toks = _tokens(stem)
    while len(toks) > 1 and toks[-1] in NAME_SUFFIXES:
        toks.pop()
    return toks


def _stem(rel):
    return os.path.splitext(rel.replace('\\', '/').rsplit('/', 1)[-1])[0]


def _norm_class(s):
    s = s.lower().replace('_', '')
    return s[:-4] if s.endswith('list') and len(s) > 4 else s


def _norm_req(s):
    return re.sub(r'[^a-z0-9]', '', html.unescape(s).lower())


def _read(pkg, e):
    """Decompressed resource; zlib read tolerantly (short streams are accepted like the game does)."""
    raw = pkg.raw(e)
    if e.comp == ZLIB:
        d = zlib.decompressobj()
        out = d.decompress(raw)
        if not d.eof and len(out) < e.msize:
            raise zlib.error('truncated zlib stream')
        return out
    return decompress(raw, e.comp, e.msize)


def _consts(code):
    """All str and int constants and names in a code object tree."""
    strs, ints = set(), set()
    stack = [code]
    while stack:
        c = stack.pop()
        strs.add(c.co_name)
        strs.update(n for n in c.co_names if isinstance(n, str))
        todo = list(c.co_consts)
        while todo:
            k = todo.pop()
            if isinstance(k, Code):
                stack.append(k)
            elif isinstance(k, str):
                strs.add(k)
            elif isinstance(k, bool):
                pass
            elif isinstance(k, int):
                ints.add(k)
            elif isinstance(k, (tuple, list, frozenset, set)):
                todo.extend(k)
    return strs, ints


def _module_name(path):
    """Dotted module name of a .pyc/.pyo inside a zip, or None (the game never imports .py)."""
    p = path.replace('\\', '/')
    if p.startswith('lib/'):
        p = p[4:]
    if not p.endswith(('.pyc', '.pyo')):
        return None
    parts = [x for x in p[:-4].split('/') if x]
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts) if parts else None


def _instance_ids(ints):
    """Int constants that can be 64-bit instance ids: above 2^32 once taken as unsigned 64-bit, and
    not a bit mask / hash constant (2**64 would otherwise become instance 0)."""
    out = set()
    for x in ints:
        if -(1 << 63) <= x < (1 << 64):
            u = x & 0xFFFFFFFFFFFFFFFF
            if u > 0xFFFFFFFF and u not in NOT_IDS:
                out.add(u)
    return out


def _zip_facts(path, want_ints=True):
    """(modules, strings, ints) of every .pyc/.pyo in a zip."""
    mods, strs, ints = set(), set(), set()
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            m = _module_name(n)
            if not m:
                continue
            mods.add(m)
            try:
                s, i = _consts(load_pyc(z.read(n)))
            except Exception:
                continue
            strs |= s
            if want_ints:
                ints |= i
    return mods, strs, ints


# ---------------------------------------------------------------- the game's own Python
def game_python(game_dir=GAME_DIR, db=None):
    """What the game's own Python defines: {'tops', 'strings', 'restypes', 'insttypes'} (sets).
    With a cache connection `db` the result is kept until a patch changes the Gameplay zips."""
    gameplay = os.path.join(game_dir, 'Data', 'Simulation', 'Gameplay')
    sig = json.dumps([[z, os.path.getsize(os.path.join(gameplay, z)), round(os.path.getmtime(os.path.join(gameplay, z)), 3)]
                      for z in GAME_ZIPS])
    if db is not None:
        row = db.execute("select value from meta where key='gamepy'").fetchone()
        if row:
            d = json.loads(row[0])
            if d['sig'] == sig:
                return {k: set(v) for k, v in d['data'].items()}
    out = _game_python(gameplay)
    if db is not None:
        db.execute("insert or replace into meta values('gamepy', ?)",
                   (json.dumps({'sig': sig, 'data': {k: sorted(v) for k, v in out.items()}}),))
        db.commit()
    return out


def _game_python(gameplay):
    mods, strs = set(), set()
    for z in GAME_ZIPS:
        m, s, _ = _zip_facts(os.path.join(gameplay, z), want_ints=False)
        mods |= m
        strs |= s
    with zipfile.ZipFile(os.path.join(gameplay, 'core.zip')) as z:
        top = load_pyc(z.read('sims4/resources.pyc'))
    types_code = next(k for k in top.co_consts if isinstance(k, Code) and k.co_name == 'Types')
    ts, ti = _consts(types_code)
    return {'tops': {m.split('.')[0] for m in mods}, 'strings': strs,
            'restypes': {x for x in ti if 0 <= x < 1 << 32}, 'insttypes': {x for x in ts if x.islower()}}


# ---------------------------------------------------------------- cache
def _open_cache(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    db = sqlite3.connect(path, timeout=60)        # other tools (dedup) may classify at the same time
    db.executescript(SCHEMA)
    row = db.execute("select value from meta where key='facts_version'").fetchone()
    if row is None or int(row[0]) != FACTS_VERSION:
        db.execute('delete from facts')
        db.execute('delete from scriptfacts')
        db.execute('delete from verdict')
        db.execute("insert or replace into meta values('facts_version', ?)", (str(FACTS_VERSION),))
        db.commit()
    return db


def _cached(db, table, root, rel, size, mtime):
    row = db.execute('select size, mtime, data from %s where root=? and rel=?' % table, (root, rel)).fetchone()
    if row and row[0] == size and abs(row[1] - mtime) < 1e-3:
        return json.loads(row[2])
    return None


# ---------------------------------------------------------------- scripts
def _script_index(lib, db):
    """[{root, rel, modules, tops, strings, ids, provides, error}] for every .ts4script in lib."""
    order = list(lib.roots)
    out = []
    for s in sorted(lib.scripts(), key=lambda s: (s.rel.lower(), order.index(s.root) if s.root in order else 99)):
        try:
            st = os.stat(s.path)
        except OSError:
            continue
        d = _cached(db, 'scriptfacts', s.root, s.rel, st.st_size, st.st_mtime)
        if d is None:
            try:
                mods, strs, ints = _zip_facts(s.path)
                d = {'modules': sorted(mods), 'strings': sorted(strs),
                     'ids': sorted(_instance_ids(ints)), 'error': None}
            except (OSError, zipfile.BadZipFile) as e:
                d = {'modules': [], 'strings': [], 'ids': [], 'error': '%s: %s' % (type(e).__name__, e)}
            db.execute('insert or replace into scriptfacts values(?,?,?,?,?)',
                       (s.root, s.rel, st.st_size, st.st_mtime, json.dumps(d)))
        mods = set(d['modules'])
        tops = {m.split('.')[0] for m in mods}
        stem = _stem(s.rel)
        toks = _tokens(stem)
        cut = [t for t in toks if not re.fullmatch(r'v?\d+', t)]
        provides = {_norm_req(t) for t in tops} | {''.join(toks), ''.join(_base_tokens(stem)),
                                                   ''.join(t for t in cut if t not in NAME_SUFFIXES)}
        out.append({'root': s.root, 'rel': s.rel, 'modules': mods, 'tops': tops, 'strings': set(d['strings']),
                    'ids': set(d['ids']), 'provides': {p for p in provides if len(p) >= 4},
                    'tokens': toks, 'base': _base_tokens(stem), 'error': d['error'], 'size': st.st_size,
                    'mtime': st.st_mtime})
    db.commit()
    return out


def script_modules(lib, cache_path=DEFAULT_CACHE):
    """{top-level module: script rel} for every module a .ts4script in the library ships (Mods and
    Mods_parked). When two scripts ship the same top-level module, the first by name wins."""
    db = _open_cache(cache_path)
    try:
        out = {}
        for s in _script_index(lib, db):
            for t in sorted(s['tops']):
                out.setdefault(t, s['rel'])
        return out
    finally:
        db.close()


def _signature(scripts, pkg_stats, game_dir):
    """Identity of everything a verdict depends on besides its own file: the rules, every script, every
    package in the classified roots (requirements can point at other packages) and the game version."""
    parts = [RULES_VERSION] + [[s['root'], s['rel'], s['size'], round(s['mtime'], 3)] for s in scripts]
    parts += sorted(pkg_stats)
    parts += [os.path.getsize(os.path.join(game_dir, 'Data', 'Simulation', 'Gameplay', z)) for z in GAME_ZIPS]
    return hashlib.blake2b(json.dumps(parts).encode(), digest_size=12).hexdigest()


def _stats(pkgs):
    """[[root, rel, size, mtime]] of the packages that exist on disk now."""
    out = []
    for p in pkgs:
        try:
            st = os.stat(p.path)
        except OSError:
            continue
        out.append([p.root, p.rel, st.st_size, round(st.st_mtime, 3)])
    return out


def _resolve_module(mod, scripts):
    parts = mod.split('.')
    for k in range(len(parts), 0, -1):
        pref = '.'.join(parts[:k])
        hits = [s['rel'] for s in scripts if pref in s['modules']]
        if hits:
            return hits
    return []


# ---------------------------------------------------------------- package facts
def package_facts(path):
    """Script-relevant facts of one package, independent of which scripts are installed:
    {'live', 'manifest', 'xml': [[t, g, i, tag, m, c, itype, n], ...], 'mfm': [[name, [required]]],
    'unreadable'}. Raises OSError / DBPFError if the package cannot be opened."""
    with Package(path) as p:
        live = [e for e in p.entries if e.comp != DELETED]
        out = {'live': sum(1 for e in live if e.t != manifest.MANIFEST_TYPE),
               'manifest': any(e.t == manifest.MANIFEST_TYPE for e in live), 'xml': [], 'mfm': [], 'unreadable': 0}
        cand = sorted((e for e in live if e.msize <= MAX_XML and e.t not in BINARY_TYPES), key=lambda e: e.off)
        for e in cand:
            try:
                data = _read(p, e)
            except Exception:
                out['unreadable'] += 1
                continue
            if not data[:512].lstrip(b'\xef\xbb\xbf \r\n\t').startswith(b'<'):
                continue
            m = ROOT_RX.search(data, 0, 4096)
            if not m:
                continue
            attrs = {a.decode(): html.unescape((v1 or v2).decode('utf-8', 'replace'))
                     for a, v1, v2 in ATTR_RX.findall(m.group(2))}
            tag = m.group(1).decode()
            if tag == 'I' and attrs.get('m') == MFM_MODULE:
                name = MFM_NAME_RX.search(data)
                req = []
                k0 = data.find(REQ_START)
                if k0 >= 0:
                    k0 += len(REQ_START)
                    end = REQ_END_RX.search(data, k0)
                    req = [html.unescape(x.decode('utf-8', 'replace'))
                           for x in REQ_NAME_RX.findall(data[k0:end.start() if end else len(data)])]
                out['mfm'].append([html.unescape(name.group(1).decode('utf-8', 'replace')) if name else '', req])
                continue
            out['xml'].append([e.t, e.g, e.i, tag, attrs.get('m'), attrs.get('c'), attrs.get('i'), attrs.get('n')])
    return out


def _facts_for(db, pkg):
    """Cached package_facts for a library Pkg; None if the file is missing; {'error'} if unreadable."""
    try:
        st = os.stat(pkg.path)
    except OSError:
        return None
    d = _cached(db, 'facts', pkg.root, pkg.rel, st.st_size, st.st_mtime)
    if d is not None:
        return d
    # moved between Mods and Mods_parked (same rel, size and mtime): reuse the other root's facts
    row = db.execute('select data from facts where rel=? and size=? and abs(mtime - ?) < 1e-3',
                     (pkg.rel, st.st_size, st.st_mtime)).fetchone()
    if row:
        db.execute('insert or replace into facts values(?,?,?,?,?)', (pkg.root, pkg.rel, st.st_size, st.st_mtime, row[0]))
        return json.loads(row[0])
    try:
        d = package_facts(pkg.path)
    except OSError:
        return None                       # vanished or locked while we looked: do not cache
    except Exception as e:
        d = {'error': '%s: %s' % (type(e).__name__, e)}
    d['size'], d['mtime'] = st.st_size, st.st_mtime
    db.execute('insert or replace into facts values(?,?,?,?,?)', (pkg.root, pkg.rel, st.st_size, st.st_mtime,
                                                                   json.dumps(d)))
    return d


def _idrefs(lib, script_ids):
    """{pkg_id: [(t, g, i)]} of library resources whose instance id a script hard-codes."""
    if not script_ids:
        return {}
    lib.db.execute('drop table if exists temp.sids')
    lib.db.execute('create temp table sids(i integer primary key)')
    lib.db.executemany('insert or ignore into temp.sids values(?)', ((signed64(i),) for i in script_ids))
    out = collections.defaultdict(list)
    for pid, t, g, i in lib.db.execute('select r.pkg, r.t, r.g, r.i from res r join temp.sids s on s.i = r.i '
                                       'where r.comp != ?', (DELETED,)):
        out[pid].append((t, g, unsigned64(i)))
    lib.db.execute('drop table temp.sids')
    lib.db.commit()                       # end the read transaction so other writers are not blocked
    return out


# ---------------------------------------------------------------- analysis
def _analyse(lib, roots, cache_path, game_dir):
    """Evidence for every package of lib in roots. Returns ({pkg_id: (Verdict, dep_keys)}, script-set
    signature, the Pkg rows, {pkg_id: facts}); dep_keys are the resources that carry script evidence."""
    roots = _root_names(roots)
    db = _open_cache(cache_path)
    try:
        game = game_python(game_dir, db)
        scripts = _script_index(lib, db)
        pkgs = [p for p in lib.packages() if p.root in roots]
        facts = {}
        for n, p in enumerate(pkgs, 1):
            facts[p.id] = _facts_for(db, p)
            if n % 20 == 0:
                db.commit()               # a cold run takes a minute: do not hold the cache's write lock all along
        db.commit()
    finally:
        db.close()
    game_strings, game_tops = game['strings'], game['tops']
    game_norm = {_norm_class(x) for x in game_strings}
    lookup_types = (game['restypes'] - BINARY_TYPES) | LOOKUP_TYPES_EXTRA
    script_ids = collections.defaultdict(set)
    for s in scripts:
        for x in s['ids']:
            script_ids[x].add(s['rel'])
    idrefs = _idrefs(lib, set(script_ids))
    mfm_names = collections.defaultdict(set)          # normalized manifest name -> pkg ids declaring it
    for pid, f in facts.items():
        for name, _ in (f or {}).get('mfm', []):
            if name:
                mfm_names[_norm_req(name)].add(pid)

    def hit(st, kind, rel, detail, key=None, strong=True):
        (st['strong'] if strong else st['weak'])[rel] += 1
        text = '%s %s -> %s' % (kind, detail, rel) if detail else '%s -> %s' % (kind, rel)
        (st['sreasons'] if strong else st['wreasons'])[text] += 1
        if key is not None and strong:
            st['dep'].add(tuple(key))

    state = {}
    for p in pkgs:
        f = facts[p.id]
        st = {'strong': collections.Counter(), 'weak': collections.Counter(), 'missing': collections.Counter(),
              'sreasons': collections.Counter(), 'wreasons': collections.Counter(), 'dep': set(), 'tuning': 0,
              'names': set(), 'same': set(), 'requires': [], 'merged': bool(f and f.get('manifest')), 'kind': None}
        state[p.id] = st
        if f is None:
            st['kind'] = Verdict('broken', None, ['file missing on disk - rescan the library'])
            continue
        if 'error' in f:
            st['kind'] = Verdict('broken', None, ['unreadable: ' + f['error']])
            continue
        if not f['live']:
            st['kind'] = Verdict('empty', None, ['no live resources'])
            continue
        for t, g, i, tag, mod, cls, ity, tname in f['xml']:
            key = (t, g, i)
            module = mod if tag == 'I' else tname
            if module or ity:
                st['tuning'] += 1
            if tag == 'I' and tname and len(tname) >= 8 and tname not in game_strings:
                for s in scripts:
                    if tname in s['strings']:
                        hit(st, 'nameref', s['rel'], tname, key)
            if cls and cls.startswith('Client_'):
                continue                  # C++-side tuning (e.g. casmodifiertuning), not Python
            if module and module.split('.')[0] not in game_tops:
                found = _resolve_module(module, scripts)
                for rel in found:
                    hit(st, 'module', rel, module, key)
                if not found:
                    st['missing']['script module ' + module] += 1
                    st['dep'].add(key)
                continue
            if cls and tag == 'I' and cls not in game_strings and _norm_class(cls) not in game_norm:
                found = [s['rel'] for s in scripts if cls in s['strings']]
                for rel in found:
                    hit(st, 'class', rel, cls, key)
                if not found:
                    st['missing']['class %s.%s' % (mod or '', cls)] += 1
                    st['dep'].add(key)
            if ity and ity not in game['insttypes'] and ity not in game_strings:
                found = [s['rel'] for s in scripts if ity in s['strings']]
                for rel in found:
                    hit(st, 'insttype', rel, ity, key)
                if not found:
                    st['missing']['instance type ' + ity] += 1
                    st['dep'].add(key)        # tuning of a missing script, like a missing module or class
            if t not in game['restypes']:
                for s in scripts:
                    if ('0x%08x' % t) in s['strings'] or ('0x%08X' % t) in s['strings']:
                        hit(st, 'restype', s['rel'], '%08X' % t, key)
        for t, g, i in idrefs.get(p.id, ()):
            strong = t in lookup_types
            for rel in script_ids[i]:
                hit(st, 'idref' if strong else 'idref_asset', rel, None, (t, g, i), strong)
        for _, req in f['mfm']:
            st['requires'].extend(req)
        pt, pb = _tokens(_stem(p.rel)), _base_tokens(_stem(p.rel))
        for s in scripts:
            if pb and pb == s['base']:
                st['same'].add(s['rel'])
                hit(st, 'samename', s['rel'], None)
            elif (len(s['tokens']) >= 2 and pt[:2] == s['tokens'][:2]) or (s['tokens'] and pt[:len(s['tokens'])] == s['tokens']):
                st['names'].add(s['rel'])
                hit(st, 'name', s['rel'], None, strong=False)

    def main_script(st, strong):
        for prefer in (st['same'], st['names'], set(strong)):
            pool = {k: v for k, v in strong.items() if k in prefer}
            if pool:
                return max(sorted(pool), key=lambda k: pool[k])
        return None

    # Declared requirements: an installed script; else another package whose Mod File Manifest has that
    # name (inherit its script link, or its missing script); else missing. Uses the evidence gathered
    # above for the other package, so the result does not depend on the order packages are visited.
    base = {pid: (collections.Counter(st['strong']), bool(st['missing'])) for pid, st in state.items()}
    for p in pkgs:
        st = state[p.id]
        for req in st['requires']:
            n = _norm_req(req)
            provider = [s['rel'] for s in scripts if n and (n in s['provides'] or
                        any(len(x) >= 6 and n.startswith(x) for x in s['provides']))]
            if provider:
                for rel in provider:
                    st['strong'][rel] += 1
                    st['sreasons']['requires %r -> %s' % (req, rel)] += 1
                continue
            others = [q for q in mfm_names.get(n, ()) if q != p.id]
            single = [q for q in others if not state[q]['merged']]
            linked = sorted({main_script(state[q], base[q][0]) for q in single if base[q][0]})
            if linked:
                for rel in linked:
                    st['strong'][rel] += 1
                    st['sreasons']['requires %r (its package belongs to %s)' % (req, rel)] += 1
            elif single and all(base[q][1] for q in single):
                st['missing']['required mod %r (its package needs a missing script)' % req] += 1
            elif others:
                st['weak']['required package'] += 1
                st['wreasons']['requires %r (another package%s)' % (req, '' if single else ', inside a merged pack')] += 1
            else:
                st['missing']['required mod %r' % req] += 1

    out = {}
    for p in pkgs:
        st = state[p.id]
        if st['kind'] is not None:
            out[p.id] = (st['kind'], set())
            continue
        reasons = ['%s (%d)' % (r, n) if n > 1 else r
                   for r, n in st['sreasons'].most_common(6) + st['wreasons'].most_common(4)]
        missing = ['missing %s (%d)' % (m, n) if n > 1 else 'missing ' + m for m, n in st['missing'].most_common(6)]
        if st['strong']:
            script = main_script(st, st['strong'])
            kind = 'core' if (st['same'] | st['names']) & set(st['strong']) else 'addon'
            v = Verdict(kind, script, reasons + missing)
        elif st['missing']:
            v = Verdict('orphan', None, missing + reasons)
        elif st['weak']:
            script = max(sorted(st['weak']), key=lambda k: st['weak'][k])
            v = Verdict('weak', script if script.lower().endswith('.ts4script') else None, reasons)
        elif st['tuning']:
            v = Verdict('tuning', None, ['%d XML tuning resources, no script link' % st['tuning']])
        else:
            v = Verdict('cc', None, [])
        out[p.id] = (v, st['dep'])
    return out, _signature(scripts, _stats(pkgs), game_dir), pkgs, facts


def classify(lib, roots=('Mods', 'Mods_parked'), cache_path=DEFAULT_CACHE, game_dir=GAME_DIR):
    """{pkg_id: Verdict(kind, script, reasons)} for every package of `lib` in `roots`.

    kind is one of core | addon | orphan | weak | tuning | cc | empty | broken; script is the rel of
    the .ts4script it belongs to (core/addon, and weak when the link is a script) or None; reasons
    are short evidence strings. Read-only on the Sims 4 folder; writes only the cache file."""
    roots = _root_names(roots)
    db = _open_cache(cache_path)
    try:
        scripts = _script_index(lib, db)
        pkgs = [p for p in lib.packages() if p.root in roots]
        stats = _stats(pkgs)
        sig = _signature(scripts, stats, game_dir)
        out = {}
        if len(stats) == len(pkgs):
            for p, (_, _, size, mtime) in zip(pkgs, stats):
                row = db.execute('select size, mtime, sig, kind, script, reasons from verdict where root=? and rel=?',
                                 (p.root, p.rel)).fetchone()
                if not row or row[0] != size or abs(row[1] - mtime) >= 1e-3 or row[2] != sig:
                    break
                out[p.id] = Verdict(row[3], row[4], json.loads(row[5]))
            if len(out) == len(pkgs):
                return out
    finally:
        db.close()
    res, sig, pkgs, facts = _analyse(lib, roots, cache_path, game_dir)
    db = _open_cache(cache_path)
    try:
        for p in pkgs:
            f = facts.get(p.id)
            if not f or 'size' not in f:
                continue
            v = res[p.id][0]
            db.execute('insert or replace into verdict values(?,?,?,?,?,?,?,?)',
                       (p.root, p.rel, f['size'], f['mtime'], sig, v.kind, v.script, json.dumps(v.reasons)))
        current = {(p.root, p.rel) for p in pkgs}
        stale = [(r, rel) for r, rel in db.execute('select root, rel from verdict')
                 if r in roots and (r, rel) not in current]
        db.executemany('delete from verdict where root=? and rel=?', stale)
        db.commit()
    finally:
        db.close()
    return {pid: v for pid, (v, _) in res.items()}


def script_bearing_sources(lib, roots=('Mods', 'Mods_parked'), cache_path=DEFAULT_CACHE, game_dir=GAME_DIR):
    """{pkg_id: [source names]} for S4S-merged packages: the sources in each package's manifest
    that carry script-linked resources (tuning of a script module/class, ids or names a script
    hard-codes, or tuning of a missing script), most such resources first. These sources are what
    a splitter must pull out of a merged CC pack."""
    res, sig, pkgs, facts = _analyse(lib, _root_names(roots), cache_path, game_dir)
    out = {}
    for p in pkgs:
        f = facts.get(p.id)
        dep = res[p.id][1]
        if not f or not f.get('manifest') or not dep:
            continue
        try:
            with Package(p.path) as pk:
                root = manifest.read(pk)
        except Exception:
            continue
        if root is None:
            continue
        counts = collections.Counter()
        for path, s in root.walk():
            n = len(dep.intersection(s.keys))
            if n:
                counts[(path + '/' + s.name) if path else s.name] += n
        if counts:
            out[p.id] = [name for name, _ in counts.most_common()]
    return out


def main():
    import argparse
    from .library import Library
    if hasattr(sys.stdout, 'reconfigure'):          # package names may hold any Unicode (CJK)
        sys.stdout.reconfigure(errors='backslashreplace')
    ap = argparse.ArgumentParser(description='Classify packages as script companions / tuning / CC (read-only).')
    ap.add_argument('--db', help='library.sqlite to use (default: the shared one, read as is)')
    ap.add_argument('--cache', default=DEFAULT_CACHE)
    ap.add_argument('--list', choices=KINDS, help='print the packages of one kind')
    ap.add_argument('--sources', action='store_true', help='also list script-bearing sources of merged packs')
    a = ap.parse_args()
    lib = Library(a.db) if a.db else Library()
    t0 = time.time()
    v = classify(lib, cache_path=a.cache)
    pk = {p.id: p for p in lib.packages()}
    counts = collections.Counter(x.kind for x in v.values())
    print('%d packages in %.1fs: %s' % (len(v), time.time() - t0, dict(counts.most_common())))
    print('never merge: %d; load-order sensitive names: %d' % (
        sum(never_merge(x) for x in v.values()), sum(load_order_sensitive(pk[i].rel) for i in v)))
    if a.list:
        for pid, x in sorted(v.items(), key=lambda kv: pk[kv[0]].rel.lower()):
            if x.kind == a.list:
                print('  %s/%s  [%s]  %s' % (pk[pid].root, pk[pid].rel, x.script or '-', '; '.join(x.reasons[:3])))
    if a.sources:
        for pid, names in script_bearing_sources(lib, cache_path=a.cache).items():
            print('  %s: %d sources, e.g. %s' % (pk[pid].rel, len(names), ', '.join(names[:5])))


if __name__ == '__main__':
    main()

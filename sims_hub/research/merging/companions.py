"""Find "script-companion" packages: .package files that only work together with a script mod
(.ts4script), so an auto-merger must leave them alone (and keep them next to their script).

Read-only on the game and the mod library. Uses the library index (data/library.sqlite).

Evidence collected per package (strongest first):
  module   - a tuning XML root element names a Python module (m="...") whose top-level package
             is not one of the game's own (top-level names in Gameplay/{base,core,simulation}.zip).
             Resolved to the .ts4script that ships that module; unresolved = script not installed.
  class    - m= is a game module but the class c="..." does not exist anywhere in the game's
             bytecode (e.g. snippet types a mod registers with snippets.define_snippet, or classes a
             mod injects into a game module); resolved to the script whose bytecode defines it.
  insttype - i="..." (instance-tuning type) is not a game type -> registered by a script.
  restype  - an XML tuning resource whose resource *type* is not in sims4.resources.Types.
  nameref  - a tuning's name (n="...") appears as a string constant in a script's bytecode
             (the script fetches that tuning by name), and it is not a game string.
  idref    - the package holds a resource whose 64-bit instance id (> 2^32) is a literal int
             constant inside a script's bytecode (the script looks that tuning/resource up).
  name     - weak: package file name starts with the same creator/mod token as a script.

    python companions.py [--out companions.json] [--no-cache]
"""
import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'tools'))
sys.path.insert(0, HERE)
from pyc37 import load, Code  # noqa: E402
from dbpf_read import DB, ROOTS, PackageReader, pkg_path, u64, COMP_DELETED  # noqa: E402
import s4s_manifest  # noqa: E402

GAMEPLAY = r'E:\The Sims 4\Data\Simulation\Gameplay'
GAME_ZIPS = ('base.zip', 'core.zip', 'simulation.zip')
CACHE = os.path.join(HERE, 'cache_game_index.json')
MAX_XML = 8 << 20
ROOT_RX = re.compile(rb'<([IM])\s([^>]*)>')
# PlumbBuddy / Llama Logic "Mod File Manifest" snippet: metadata the game ignores (its Python module
# does not exist in the game), but it declares dependencies in <L n="required_mods">.
MFM_MODULE = 'llamalogic.snippets.modfilemanifest'
REQ_START = b'<L n="required_mods">'
REQ_END_RX = re.compile(rb'<L n="(?!creators"|hashes")|</I>')
REQ_NAME_RX = re.compile(rb'<U>\s*<T n="name">([^<]*)</T>')
ATTR_RX = re.compile(rb'(\w+)="([^"]*)"')


# ---------------------------------------------------------------- bytecode helpers
def consts_of(code):
    """All str / int constants and names in a code object tree."""
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


def module_name(path):
    p = path.replace('\\', '/')
    if p.startswith('lib/'):
        p = p[4:]
    for ext in ('.pyc', '.py'):
        if p.endswith(ext):
            p = p[:-len(ext)]
            break
    else:
        return None
    parts = [x for x in p.split('/') if x]
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts) if parts else None


def zip_index(path, want_consts=True):
    """modules, string consts, int consts of every .pyc/.py in a zip."""
    mods, strs, ints = set(), set(), set()
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            m = module_name(n)
            if not m:
                continue
            mods.add(m)
            if not want_consts:
                continue
            data = z.read(n)
            if n.endswith('.pyc'):
                try:
                    s, i = consts_of(load(data))
                except Exception:
                    s, i = set(), set()
            else:  # plain source
                txt = data.decode('utf-8', 'replace')
                s = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', txt))
                i = {int(x, 0) for x in re.findall(r'\b(0x[0-9A-Fa-f]+|\d{6,})\b', txt)}
            strs |= s
            ints |= i
    return mods, strs, ints


def game_index(use_cache=True):
    if use_cache and os.path.exists(CACHE):
        with open(CACHE, encoding='utf-8') as f:
            d = json.load(f)
        return {k: set(v) for k, v in d.items()}
    mods, strs, ints = set(), set(), set()
    for z in GAME_ZIPS:
        m, s, i = zip_index(os.path.join(GAMEPLAY, z))
        mods |= m; strs |= s; ints |= i
    # sims4.resources.Types: every resource type value + instance-tuning type names
    with zipfile.ZipFile(os.path.join(GAMEPLAY, 'core.zip')) as z:
        top = load(z.read('sims4/resources.pyc'))
    types_code = next(k for k in top.co_consts if isinstance(k, Code) and k.co_name == 'Types')
    ts, ti = consts_of(types_code)
    d = {'modules': sorted(mods), 'tops': sorted({m.split('.')[0] for m in mods}),
         'strings': sorted(strs), 'restypes': sorted(x for x in ti if 0 <= x < 1 << 32),
         'insttypes': sorted(x for x in ts if x.islower())}
    with open(CACHE, 'w', encoding='utf-8') as f:
        json.dump(d, f)
    return {k: set(v) for k, v in d.items()}


# ---------------------------------------------------------------- scripts
def scripts_index(db):
    out = []
    for root, rel, size in db.execute('select root, rel, size from script order by rel'):
        path = pkg_path(root, rel)
        try:
            mods, strs, ints = zip_index(path)
        except Exception as e:
            out.append({'root': root, 'rel': rel, 'error': str(e), 'modules': set(), 'tops': set(),
                        'strings': set(), 'ids': set()})
            continue
        out.append({'root': root, 'rel': rel, 'modules': mods, 'tops': {m.split('.')[0] for m in mods},
                    'strings': strs, 'ids': {x & 0xFFFFFFFFFFFFFFFF for x in ints if abs(x) > 0xFFFFFFFF}})
    return out


def resolve_module(mod, scripts):
    """.ts4script(s) that ship module `mod` (longest dotted-prefix match)."""
    parts = mod.split('.')
    for k in range(len(parts), 0, -1):
        pref = '.'.join(parts[:k])
        hits = [s['rel'] for s in scripts if pref in s['modules']]
        if hits:
            return hits
    return []


# ---------------------------------------------------------------- packages
def norm(s):
    s = s.lower().replace('_', '')
    return s[:-4] if s.endswith('list') and len(s) > 4 else s


# Types whose instance ids a script looks up (tuning, SimData, string tables). An id match on any
# other type (CAS parts, sliders, thumbnails) only means "the script knows this asset" - weak.
LOOKUP_TYPES_EXTRA = {0x545AC67A, 0x220557DA, 0x62E94D38}


NAME_TOKEN = re.compile(r'[A-Za-z0-9]+')


def name_tokens(stem):
    toks = [t.lower() for t in NAME_TOKEN.findall(stem)]
    return toks


def name_match(pkg_rel, scripts):
    ps = name_tokens(os.path.splitext(os.path.basename(pkg_rel))[0])
    hits = []
    for s in scripts:
        ss = name_tokens(os.path.splitext(os.path.basename(s['rel']))[0])
        # first token = creator tag; need creator + next token equal, or whole script stem is a prefix
        if len(ss) >= 2 and ps[:2] == ss[:2]:
            hits.append(s['rel'])
        elif ss and ps[:len(ss)] == ss:
            hits.append(s['rel'])
    return hits


def scan(db, game, scripts, verbose=True):
    game_tops, game_strings = game['tops'], game['strings']
    game_restypes, game_insttypes = game['restypes'], game['insttypes']
    game_norm = {norm(x) for x in game_strings}
    lookup_types = (game_restypes - BINARY_TYPES) | LOOKUP_TYPES_EXTRA
    script_ids = collections.defaultdict(set)
    for s in scripts:
        for x in s['ids']:
            script_ids[x].add(s['rel'])
    results = []
    pkgs = db.execute('select id, root, rel, size, n from pkg where err is null order by root, rel').fetchall()
    t0 = time.time()
    n_xml = 0
    for k, (pid, root, rel, size, n) in enumerate(pkgs):
        ev = collections.defaultdict(lambda: collections.defaultdict(int))
        unresolved = collections.Counter()
        scripts_hit = collections.Counter()
        weak_hit = collections.Counter()
        n_tuning = 0
        meta = collections.Counter()
        meta_names, required = set(), set()
        dep_keys = set()   # (t, g, i) of resources that carry script evidence
        rows = db.execute('select t, g, i, off, fsize, msize, comp from res where pkg=? and comp!=? order by off',
                          (pid, COMP_DELETED)).fetchall()
        # idref: any resource instance that a script hard-codes
        for t, g, i, off, fs, ms, comp in rows:
            iu = u64(i)
            if iu > 0xFFFFFFFF and iu in script_ids:
                strong = t in lookup_types
                if strong:
                    dep_keys.add((t, g, iu))
                for s in script_ids[iu]:
                    ev['idref' if strong else 'idref_asset'][s] += 1
                    if strong:
                        scripts_hit[s] += 1
                    else:
                        weak_hit[s] += 1
        # XML tuning: sniff small resources whose type is not a known big binary type
        cand = [r for r in rows if r[5] <= MAX_XML and r[0] not in BINARY_TYPES]
        if cand:
            with PackageReader(pkg_path(root, rel)) as pr:
                for t, g, i, off, fs, ms, comp in cand:
                    try:
                        data = pr.read(off, fs, comp, ms)
                    except Exception:
                        continue
                    head = data[:512].lstrip(b'\xef\xbb\xbf \r\n\t')
                    if not head.startswith(b'<'):
                        continue
                    m = ROOT_RX.search(data, 0, 4096)
                    if not m:
                        continue
                    n_xml += 1
                    attrs = {a.decode(): v.decode('utf-8', 'replace') for a, v in ATTR_RX.findall(m.group(2))}
                    mod, cls, ity = attrs.get('m'), attrs.get('c'), attrs.get('i')
                    if mod == MFM_MODULE:
                        meta['mod_file_manifest'] += 1
                        mfm_name = re.search(rb'<T n="name">([^<]*)</T>', data)
                        if mfm_name:
                            meta_names.add(mfm_name.group(1).decode('utf-8', 'replace'))
                        k0 = data.find(REQ_START)
                        if k0 >= 0:
                            k0 += len(REQ_START)
                            e = REQ_END_RX.search(data, k0)
                            for nm in REQ_NAME_RX.findall(data[k0:e.start() if e else len(data)]):
                                required.add(nm.decode('utf-8', 'replace'))
                        continue
                    if mod or ity:
                        n_tuning += 1
                    tname = attrs.get('n')
                    if tname and len(tname) >= 8 and tname not in game_strings:
                        hits = [s['rel'] for s in scripts if tname in s['strings']]
                        if hits:
                            dep_keys.add((t, g, u64(i)))
                        for s in hits:
                            ev['nameref'][s] += 1
                            scripts_hit[s] += 1
                    if cls and cls.startswith('Client_'):
                        continue  # client-side (C++) tuning, e.g. casmodifiertuning - not Python
                    if mod and mod.split('.')[0] not in game_tops:
                        hits = resolve_module(mod, scripts)
                        dep_keys.add((t, g, u64(i)))
                        if hits:
                            for s in hits:
                                ev['module'][s + ' :: ' + mod] += 1
                                scripts_hit[s] += 1
                        else:
                            unresolved[mod] += 1
                        continue
                    if cls and m.group(1) == b'I' and cls not in game_strings and norm(cls) not in game_norm:
                        hits = [s['rel'] for s in scripts if cls in s['strings']]
                        dep_keys.add((t, g, u64(i)))
                        for s in hits:
                            ev['class'][s + ' :: ' + (mod or '') + '.' + cls] += 1
                            scripts_hit[s] += 1
                        if not hits:
                            # class exists neither in the game nor in any installed script:
                            # a missing script, or a class EA removed (outdated mod)
                            unresolved['class:' + (mod or '') + '.' + cls] += 1
                    if ity and ity not in game_insttypes and ity not in game_strings:
                        hits = [s['rel'] for s in scripts if ity in s['strings']]
                        for s in hits:
                            ev['insttype'][s + ' :: ' + ity] += 1
                            scripts_hit[s] += 1
                        if not hits:
                            unresolved['insttype:' + ity] += 1
                    if t not in game_restypes:
                        hits = [s['rel'] for s in scripts if t in s['ids'] or ('0x%08x' % t) in s['strings']]
                        ev['restype']['%08X' % t] += 1
                        for s in hits:
                            scripts_hit[s] += 1
        names = name_match(rel, scripts)
        strong = set(scripts_hit)
        if strong:
            verdict = 'companion'            # needs an installed script mod
        elif unresolved or required:
            verdict = 'orphan'               # needs a script that is NOT installed (or is outdated)
        elif weak_hit or names:
            verdict = 'weak'                 # script-aware asset / same creator prefix only
        elif n_tuning:
            verdict = 'tuning'               # plain XML tuning mod (no script link)
        else:
            verdict = 'none'
        # "core" = ships with the script (same creator/name); "addon" = third-party content that
        # merely needs the script (e.g. WickedWhims animation packs)
        relation = None
        if strong:
            relation = 'core' if set(names) & strong else 'addon'
        merged_sources = None
        man = [r for r in rows if r[0] == s4s_manifest.MANIFEST_TYPE]
        if man and dep_keys:
            t_, g_, i_, off_, fs_, ms_, comp_ = man[0]
            with PackageReader(pkg_path(root, rel)) as pr:
                mf = s4s_manifest.parse(pr.read(off_, fs_, comp_, ms_))
            merged_sources = collections.Counter()
            for path, pk in mf.packages():
                hit = len(dep_keys.intersection(pk.keys))
                if hit:
                    merged_sources[(path + '/' + pk.name).strip('/')] = hit
            merged_sources = dict(merged_sources.most_common())
        if verdict != 'none':
            results.append({
                'merged_sources_with_script_content': merged_sources,
                'relation': relation,
                'declared_requirements': sorted(required),
                'mod_file_manifest': sorted(meta_names),
                'package': root + '/' + rel, 'size': size, 'resources': n, 'verdict': verdict,
                'scripts': sorted(strong), 'weak_scripts': sorted(set(weak_hit)), 'name_match': names,
                'xml_tuning': n_tuning,
                'xml_scripted': sum(sum(ev[k].values()) for k in ('module', 'class', 'insttype', 'nameref') if k in ev),
                'evidence': {k2: dict(v2) for k2, v2 in ev.items() if v2},
                'missing_script_modules': dict(unresolved),
            })
        if verbose and k % 50 == 0:
            print('  %d/%d packages, %d xml, %.0fs' % (k, len(pkgs), n_xml, time.time() - t0), file=sys.stderr)
    return results, n_xml


# big binary types never holding tuning XML (CAS parts, images, geometry, clips, thumbnails...)
BINARY_TYPES = {0x034AEECB, 0x3453CF95, 0x3C1AF1F2, 0x015A1849, 0x6B20C4F3, 0xBC4A5044, 0x2BC04EDF,
                0x00B2D882, 0xAC16FBEC, 0xBA856C78, 0x220557DA, 0x545AC67A, 0x3C2A8647, 0x01A527DB,
                0xFD04E3BE, 0x319E4F1D, 0xC0DB5AE7, 0x01D10F34, 0xDB43E069, 0xB6C8B6A0, 0x7FB6AD8A,
                0x01661233, 0x0166038C, 0x62ECC59A, 0x376840D7, 0xC5F6763E, 0xEAA32ADD, 0x0354796A,
                0x9D1AB874, 0xD382BF57, 0x81CA1A10, 0x03B4C61D, 0x8B18FF6E, 0x01D0E75D, 0x062C8204,
                0x16CA6BC4, 0xB4F762C9, 0xD5F0F921, 0x736884F1, 0x01357924, 0xB0118C15, 0xBDD82221}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'companions.json'))
    ap.add_argument('--no-cache', action='store_true')
    a = ap.parse_args()
    db = sqlite3.connect(DB)
    t0 = time.time()
    game = game_index(not a.no_cache)
    print('game: %d modules, %d top-level, %d strings, %d resource types, %.0fs' % (
        len(game['modules']), len(game['tops']), len(game['strings']), len(game['restypes']), time.time() - t0),
        file=sys.stderr)
    scripts = scripts_index(db)
    print('scripts: %d, top-level packages: %s' % (len(scripts), sorted({t for s in scripts for t in s['tops']})),
          file=sys.stderr)
    res, n_xml = scan(db, game, scripts)
    summary = collections.Counter(r['verdict'] for r in res)
    by_script = collections.defaultdict(list)
    for r in res:
        for s in r['scripts']:
            by_script[s].append(r['package'])
    order_rx = re.compile(r'^(!|~|_|z{2,}|0{2,})', re.I)
    order_sensitive = [r + '/' + p for r, p in db.execute('select root, rel from pkg order by rel')
                       if order_rx.match(os.path.basename(p))]
    merged_with_script = [
        {'package': r['package'], 'size': r['size'], 'verdict': r['verdict'], 'scripts': r['scripts'],
         'missing': sorted(r['missing_script_modules']), 'sources': r['merged_sources_with_script_content']}
        for r in res if r.get('merged_sources_with_script_content')]
    out = {
        'generated': time.strftime('%Y-%m-%d %H:%M:%S'),
        'merge_policy': {
            'companion': 'needs an installed script mod: never merge into CC packs; relation=core (ships '
                         'with the script, updates with it) must stay a separate file next to the script; '
                         'relation=addon (e.g. WW animation packs) may only be merged with other addons of '
                         'the same script, into a pack that is enabled/disabled together with that script',
            'orphan': 'references a script module/class that is not installed (or a removed EA class) or '
                      'declares required_mods in a ModFileManifest: do not merge; fix or drop',
            'weak': 'same creator prefix as a script, or holds assets a script hard-codes: do not merge '
                    'without review (conservative default: treat as companion)',
            'tuning': 'plain XML tuning mod: keep out of CC merges (updates/conflicts); own bucket at most',
        },
        'order_sensitive_names': order_sensitive,
        'merged_packages_containing_script_content': merged_with_script,
        'xml_resources_scanned': n_xml,
        'summary': dict(summary),
        'scripts': [{'script': s['root'] + '/' + s['rel'], 'top_level_modules': sorted(s['tops']),
                     'n_modules': len(s['modules']), 'n_int_ids': len(s['ids']),
                     'companions': sorted(by_script.get(s['rel'], []))} for s in scripts],
        'packages': res,
    }
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, indent=1)
    print('done in %.0fs: %s -> %s' % (time.time() - t0, dict(summary), a.out), file=sys.stderr)


if __name__ == '__main__':
    main()

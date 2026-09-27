"""Novulon's settings.json - schema, migration, dotted-path get/set (SPEC.md Sec.7).

Where: <Sims 4>\\Novulon\\settings.json - our own folder, never Mods, never shared with
<Sims 4>\\SpeedKit\\ (common.novulon_dir()).

Schema 1 (the only version this build ships):
    {"schema": 1,
     "sim_browser": {"page_size": 80},
     "compat": {"defer_to_mccc": {"population": bool, "pregnancy": bool, "aging": bool,
                                   "story_progression": bool}},
     "adult": {"enabled": false, "interstitial_shown": false},
     "log_level": "info",
     "modules_hidden": []}

`compat.defer_to_mccc` is computed once, on a FIRST run only (no existing settings.json - or one that
does not parse at all, treated the same way since there is nothing to migrate either way), from
compat.mccc.is_present(): all four flags true when MC Command Center is detected, all four false when it
is not. SPEC.md Sec.7 is explicit that shipping `true` unconditionally would silently turn off Novulon's own
Gameplay rows for the many players who never installed MCCC - this is a Tier-1 test requirement below
(both branches asserted, not just the MCCC-present one). `compat/` (BP7) may not exist yet in every build
of this tree; its absence is treated exactly like "MCCC not present" - the safer of the two, since it
leaves Novulon's own features on rather than silently disabling them - never a crash either way.

Migration: load() walks _MIGRATIONS[schema] while the file's schema is below SCHEMA, so a settings.json
from an older build never crashes a newer one, and any key migration does not touch is preserved as-is,
never stripped. There is only one schema so far (1); _MIGRATIONS[0] is "a file with no recognisable
schema at all" - fill in only the top-level keys DEFAULTS has that the file is missing.

get(path, default)/set(path, value) (dotted path, e.g. 'compat.defer_to_mccc.population') are the only
way any other module is meant to touch settings; set() writes atomically (tmp file + os.replace, the
same pattern speedkit/journal.py already uses for its own settings-like files) - it loads, mutates the
in-memory document, then writes the whole thing in one pass.
"""
import copy
import json
import os

from . import common

SCHEMA = 1

DEFAULTS = {
    'schema': SCHEMA,
    'sim_browser': {'page_size': 80},
    'compat': {'defer_to_mccc': {'population': False, 'pregnancy': False, 'aging': False,
                                  'story_progression': False}},
    'adult': {'enabled': False, 'interstitial_shown': False},
    'log_level': 'info',
    'modules_hidden': [],
}

_cache = None      # the loaded/migrated document, kept in memory between get()/set() calls this session


def _mccc_present():
    """compat.mccc.is_present(), or False if compat/ is not built/importable yet or the probe itself
    raises - the safer default (Novulon's own features stay on rather than silently turning off)."""
    try:
        from .compat import mccc
    except Exception:
        return False
    try:
        return bool(mccc.is_present())
    except Exception:
        common.log_exception('settings: compat.mccc.is_present()')
        return False


def _merge_missing(doc, defaults):
    """Add any top-level key `defaults` has that `doc` doesn't; never touches a key already present,
    never removes a key `doc` has that `defaults` doesn't (an unknown key is preserved, not stripped)."""
    if not isinstance(doc, dict):
        doc = {}
    for k, v in defaults.items():
        if k not in doc:
            doc[k] = copy.deepcopy(v)
    return doc


def _fresh():
    """The first-run document: DEFAULTS with compat.defer_to_mccc filled from the live MCCC probe."""
    doc = copy.deepcopy(DEFAULTS)
    present = _mccc_present()
    doc['compat']['defer_to_mccc'] = dict.fromkeys(doc['compat']['defer_to_mccc'], present)
    return doc


_MIGRATIONS = {
    0: lambda doc: _merge_missing(doc, DEFAULTS),   # no schema key, or an unrecognised one
}


def _migrate(doc):
    """doc (already read from disk, not None) brought up to SCHEMA. A schema this build has never heard
    of (from a future build, or corrupt) is treated as 0 rather than crashing or guessing forward."""
    schema = doc.get('schema') if isinstance(doc, dict) else None
    if not isinstance(schema, int) or not (0 <= schema <= SCHEMA):
        schema = 0
    guard = 0
    while schema < SCHEMA and guard < 100:          # guard: a broken _MIGRATIONS chain must not hang
        fn = _MIGRATIONS.get(schema)
        if fn is None:
            common.log('settings: no migration from schema %r, keeping the document as-is' % (schema,))
            break
        doc = fn(doc)
        doc['schema'] = schema + 1
        schema += 1
        guard += 1
    return doc


def path():
    """<Sims 4>\\Novulon\\settings.json, or None when we have no Sims folder."""
    d = common.novulon_dir()
    return os.path.join(d, 'settings.json') if d else None


def _write(doc):
    p = path()
    if not p:
        return False
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
    except OSError:
        pass
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=2, sort_keys=True)
    os.replace(tmp, p)
    return True


def load(force=False):
    """The settings document, migrated if needed. Cached after the first call this session; pass
    force=True to re-read the file from disk (tests only - the game never needs to)."""
    global _cache
    if _cache is not None and not force:
        return _cache
    p = path()
    raw = common.read_json(p) if p else None
    if raw is None:
        doc = _fresh()
        if p:
            common.guarded('settings: writing fresh settings.json', _write, doc)
    else:
        # _migrate (via _merge_missing) mutates and returns the SAME dict it is given, so `raw` itself
        # changes too - a before/after identity comparison would always see "no change". Snapshot first.
        before = copy.deepcopy(raw)
        doc = _migrate(raw)
        if doc != before and p:
            common.guarded('settings: writing migrated settings.json', _write, doc)
    _cache = doc
    return doc


def save():
    """Write the current in-memory document to disk now (get()/set() already do this on every set())."""
    global _cache
    if _cache is None:
        _cache = load()
    return bool(common.guarded('settings: save', _write, _cache))


def _split(dotted_path):
    return [p for p in dotted_path.split('.') if p]


def get(dotted_path, default=None):
    """The value at a dotted path (e.g. 'compat.defer_to_mccc.population'), or default if any part of
    the path is missing."""
    node = load()
    for part in _split(dotted_path):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set(dotted_path, value):
    """Set a dotted path to value and write settings.json atomically. Creates intermediate dicts as
    needed; never partially writes (the whole document is written in one pass)."""
    global _cache
    doc = load()
    parts = _split(dotted_path)
    if not parts:
        return False
    node = doc
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value
    _cache = doc
    return bool(common.guarded('settings: set ' + dotted_path, _write, doc))


def reset_cache():
    """Forget the in-memory document (tests only) - the next get()/set()/load() re-reads the file."""
    global _cache
    _cache = None

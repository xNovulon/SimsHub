"""Novulon's shared, append-only registry of every EA API name its code cites (SPEC.md Sec 16 Tier 3:
"a flat, append-only list every module owner adds one row to whenever their code cites a new EA
name"), overridden per the build note so parallel builders never touch the same line: instead of one
shared file, each build package owns its own module in this package. Mirrors `tools/novulon_ids`'s own
aggregator right next to it ("same aggregator pattern") - if you've read that file's __init__.py, this
one does the equivalent job for API names instead of resource ids.

Each feature package adds `sims_hub/tools/novulon_api_manifest/<package>.py` - a plain module that
defines a list of rows, named either ROWS or MANIFEST (both spellings have been used while this
contract settled during the build; the aggregator takes whichever one a file defines, so it never
matters which you pick - ROWS is the name in this docstring from here on):

    ROWS = [
        ('sims.sim_info', 'SimInfo.remove_permanently', 'method'),
        ('sims.sim_info_types', 'Age.YOUNGADULT', 'const', 16),
        ('traits.trait_commands', 'traits.equip_trait', 'command'),
    ]

A row is (module, path, kind[, expected]):
  * module   - the dotted module path as it appears inside the game's zip. 'sims.sim_info' is checked
               against 'sims/sim_info.pyc'. A package works too either way: 'services' is tried as
               both 'services.pyc' and 'services/__init__.pyc' - no need to spell out '.__init__'
               yourself.
  * path     - the dotted name to verify inside that module: a class ('SimInfo'), a class member
               ('SimInfo.remove_permanently', 'Age.YOUNGADULT'), or a bare module-level name. Not
               used for kind 'module' (pass None).
  * kind     - 'class' / 'method' / 'function' / 'const' or 'member' (interchangeable: a plain name
               binding - an enum value, a property, a module-level attribute assigned at import time,
               not a nested def/class) / 'command' / 'module'. 'command' is special: `path` is a
               console-command literal (e.g. 'sims.reset', the string a
               @sims4.commands.Command(...) decorator registers) - a decorator argument is not a name
               binding, so novulon_api_check.py searches the whole module's constants/names for the
               literal instead of descending a dotted path. 'module' means only confirm the module
               itself exists - `path` is ignored. Every other kind runs through the same name-descent;
               `kind` documents what the row's author expects to find there and is never type-checked
               against a fixed vocabulary, so a locally-meaningful label works fine.
  * expected - optional. Noted in novulon_api_check.py's report, never enforced byte-for-byte (see
               that file's own docstring for why matching an exact bytecode constant isn't reliable
               enough to hard-fail a build on).

A file may also record which installed game build its own rows were checked against, in whichever of
these three ways is most convenient (all three have been used; the aggregator accepts any of them):
  * a row inside ROWS/MANIFEST itself, ('game_version', None, '<packversion>') - pulled out of the
    row list before duplicate-checking, never treated as a real API row;
  * a plain module-level string, CHECKED_AGAINST = '<packversion>';
  * or just prose in the module's own docstring, not machine-read at all - novulon_api_check.py always
    prints the build it actually checked against, so a prose citation can still be eyeballed against
    it even with no structured version note in the file.
None of the three is required; a file with no version note at all just never shows up in
novulon_api_check.py's per-file version-mismatch warnings.

This file discovers every sibling module in this package (skipping names starting with '_', reserved
for private helpers such as a shared fixture) with pkgutil, imports each one, and concatenates its
rows into ALL_ROWS (plus CHECKED_AGAINST, {source file: version} for files that give one, by either
structured means above). It raises ValueError at import time - so a mistake is caught the moment
anything imports this package, never silently dropped - when:
  * a sibling file defines neither ROWS nor MANIFEST;
  * a row isn't a 3- or 4-item tuple/list, or its module/path aren't strings;
  * a ('game_version', ...) row's version isn't a non-empty string, or a file gives two conflicting
    version notes (a ROWS-embedded one and a CHECKED_AGAINST that disagree);
  * two rows (from the same file or two different ones) cite the same (module, path) but disagree
    about what's there - a different `kind`, or two different non-None `expected` values. Citing the
    same (module, path) with the SAME kind from two different files is not an error: two packages
    legitimately reading the same EA name is normal (e.g. two feature modules both showing a failure
    notification at UiDialogNotificationUrgency.URGENT) and is kept once, silently, in ALL_ROWS - it's
    only ever a mistake when the two citations disagree with each other about the fact itself, which
    is the case the override note's "fails on a duplicate id or name" is actually guarding against.

Nothing here touches the installed game; it only reads Python source (its own siblings).
novulon_api_check.py is the tool that actually opens the game's own .pyc files and checks these rows
against them.
"""
import collections
import importlib
import os
import pkgutil

Row = collections.namedtuple('Row', 'module path kind expected source')
GAME_VERSION_MARKER = 'game_version'


def _normalize(row, source):
    """One raw tuple/list from a package's row list -> a Row, or raise ValueError naming the file."""
    if not isinstance(row, (tuple, list)) or len(row) not in (3, 4):
        raise ValueError('%s.py: a manifest row must be (module, path, kind) or (module, path, kind, '
                          'expected), got %r' % (source, row))
    if len(row) == 3:
        module, path, kind = row
        expected = None
    else:
        module, path, kind, expected = row
    if not module or not isinstance(module, str):
        raise ValueError('%s.py: row %r has a bad module (must be a non-empty dotted string)' % (source, row))
    if not isinstance(kind, str) or not kind:
        raise ValueError('%s.py: row %r has a bad kind' % (source, row))
    if kind != 'module' and (not path or not isinstance(path, str)):
        raise ValueError('%s.py: row %r has a bad path (required unless kind is \'module\')' % (source, row))
    return Row(module=module, path=path or None, kind=kind, expected=expected, source=source)


def _merge(existing, new):
    """Two rows citing the same (module, path). Fine (returns the more informative one) when they
    agree; raises ValueError when they genuinely contradict each other."""
    if existing.kind != new.kind:
        raise ValueError('conflicting manifest rows for %s: %s.py says kind %r, %s.py says kind %r'
                          % ((existing.module, existing.path), existing.source, existing.kind,
                             new.source, new.kind))
    if existing.expected is not None and new.expected is not None and existing.expected != new.expected:
        raise ValueError('conflicting manifest rows for %s: %s.py expects %r, %s.py expects %r'
                          % ((existing.module, existing.path), existing.source, existing.expected,
                             new.source, new.expected))
    # first writer wins, except a later file's `expected` fills in one the first writer left unset
    return new if (existing.expected is None and new.expected is not None) else existing


def _aggregate(sources):
    """sources: [(file_name, raw_rows, checked_against_attr)]. Pure - no filesystem or import work
    here - so this is the part test_novulon_api_surface.py exercises directly, with made-up sources,
    no real sibling files needed. Returns (rows, checked_against_by_source)."""
    by_key = {}
    checked_against = {}
    for name, raw_rows, attr_version in sources:
        if not isinstance(raw_rows, (list, tuple)):
            raise ValueError('%s.py: ROWS/MANIFEST must be a list, got %s' % (name, type(raw_rows).__name__))
        if attr_version is not None:
            if not isinstance(attr_version, str) or not attr_version:
                raise ValueError('%s.py: CHECKED_AGAINST must be a non-empty string, got %r' % (name, attr_version))
            checked_against[name] = attr_version
        for raw in raw_rows:
            if isinstance(raw, (tuple, list)) and len(raw) == 3 and raw[0] == GAME_VERSION_MARKER:
                _, _, version = raw
                if not version or not isinstance(version, str):
                    raise ValueError("%s.py: a %r row must be ('%s', None, '<packversion>'), got %r"
                                     % (name, GAME_VERSION_MARKER, GAME_VERSION_MARKER, raw))
                if name in checked_against and checked_against[name] != version:
                    raise ValueError('%s.py: conflicting version notes (%r vs %r)'
                                     % (name, checked_against[name], version))
                checked_against[name] = version
                continue
            row = _normalize(raw, name)
            key = (row.module, row.path)
            by_key[key] = _merge(by_key[key], row) if key in by_key else row
    return list(by_key.values()), checked_against


def _discover():
    """[(module_name, rows, CHECKED_AGAINST or None)] for every sibling *.py in this package except
    __init__ and any file starting with '_' (reserved for shared helpers, never a source of rows)."""
    pkg_dir = os.path.dirname(__file__)
    sources = []
    for info in sorted(pkgutil.iter_modules([pkg_dir]), key=lambda i: i.name):
        if info.name.startswith('_'):
            continue
        mod = importlib.import_module('.' + info.name, __name__)
        rows = getattr(mod, 'ROWS', None)
        if rows is None:
            rows = getattr(mod, 'MANIFEST', None)
        if rows is None:
            raise ValueError("%s.py must define ROWS (or MANIFEST) - a list of manifest rows, see "
                              "this package's __init__.py docstring for the shape" % info.name)
        sources.append((info.name, rows, getattr(mod, 'CHECKED_AGAINST', None)))
    return sources


ALL_ROWS, CHECKED_AGAINST = _aggregate(_discover())

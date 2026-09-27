r"""Checks every row novulon_api_manifest/*.py has registered against the names actually present in
THIS installed game build's own compiled Python (SPEC.md Sec 16 Tier 3 - "the most important safety
net"). Every EA name Novulon's code cites has to be one someone actually saw in this game's own
.pyc, never a name that merely sounds right or that existed in some older build - the hard rule
behind this whole file is "never ship a guess."

    python tools/novulon_api_check.py                  # check + report, exit != 0 on any miss
    python tools/novulon_api_check.py --quiet           # only the summary line and the failures
    python tools/novulon_api_check.py --no-update       # don't rewrite the checked-against marker

How a row is checked (see novulon_api_manifest/__init__.py for the row shape):
  * The row's module (e.g. 'sims.sim_info') is looked up as '<path>.pyc' inside core.zip, then
    simulation.zip. base.zip is never searched - it only ever holds the Python standard library
    ('lib/...'), never an EA name (verified directly: base.zip's only top-level entry is 'lib').
  * A module not found in either zip is a miss for every row that cites it.
  * kind 'module': finding the module is the whole check.
  * kind 'command': the literal in `path` (a console-command string, e.g. 'sims.reset') is searched
    across every nested code object's names/constants in the module, since a command literal is a
    decorator argument, not a name binding - there's nothing to "descend" into.
  * every other kind: `path` is walked dot by dot from the module's top-level code object. A class or
    function compiles to its own nested code object, findable by co_name among its parent's co_consts
    - the exact structural fact tools/pyc37.py's own --outline already prints, one function at a time.
    A plain member (an enum's YOUNGADULT, a module-level constant) is a name bound with STORE_NAME
    inside its owner's code object, findable in that code object's co_names. This automates the
    by-hand technique the whole research phase used with pyc37.py --outline, walking a list of names
    instead of reading one function at a time. (Verified directly against this build's own zips before
    writing this docstring: SimInfo.remove_permanently/assign_to_household/is_instanced,
    Age.YOUNGADULT/INFANT, Gender.MALE, OccultType.WITCH/VAMPIRE, and the traits.equip_trait/
    remove_trait command literals all resolve exactly this way.)
  * `expected` (present on some rows) is reported, never enforced: matching an exact literal value
    back out of bytecode - was this LOAD_CONST truly paired with this STORE_NAME, and not shadowed by
    a later reassignment or a conditional branch - isn't reliable enough to hard-fail a build on. The
    row's `path` existing at all is the check that matters; `expected` is a breadcrumb for whoever
    reads a failure, not a second assertion.

Nothing here starts the game or writes anywhere under Sims 4/Documents - it only reads the two/three
.zip files this repo's other tools already read (pyc37.py, game_python.py). The "loud warning when
the game version changed" the override note asks for is done per manifest file, not with one shared
state file: each novulon_api_manifest/<package>.py may carry its own ('game_version', None,
'<packversion>') row recording the build its author checked against (see that package's __init__.py
docstring) - a shared state file here would just be one more write race in a working tree several
builders touch at once, exactly what the override note's per-package-file split is already avoiding
everywhere else.
"""
import argparse
import configparser
import glob
import os
import sys
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from tools import pyc37                       # noqa: E402
from tools import novulon_api_manifest         # noqa: E402

GAMEPLAY = r'E:\The Sims 4\Data\Simulation\Gameplay'
GAME_DIR = r'E:\The Sims 4'
ZIP_ORDER = ('core.zip', 'simulation.zip')     # base.zip is just 'lib' (the stdlib) - never an EA name


# ------------------------------------------------------------------------------------------ game version
def game_build_version(game_dir=GAME_DIR):
    """packversion out of a Delta\\<pack>\\Version.ini. Verified directly against this machine's own
    install that every installed pack's copy agrees (EP01..EP21, GP01, SP01 all read
    '1.126.73.1030') - it's the overall client build, not a per-pack number - so any one file is
    enough. Tries Delta\\EP21 first (this spec's own citation for "the current highest pack"); if that
    one's missing (a future rebuild against an older/newer install), falls back to whichever pack
    folder sorts last. None if no Delta pack has a Version.ini at all."""
    delta = os.path.join(game_dir, 'Delta')
    preferred = os.path.join(delta, 'EP21', 'Version.ini')
    candidates = [preferred] if os.path.isfile(preferred) else []
    if os.path.isdir(delta):
        candidates += sorted(glob.glob(os.path.join(delta, '*', 'Version.ini')), reverse=True)
    for path in candidates:
        cp = configparser.ConfigParser()
        try:
            cp.read(path, encoding='utf-8-sig')
            v = cp.get('Version', 'packversion', fallback=None)
        except (OSError, configparser.Error):
            v = None
        if v:
            return v.strip()
    return None


# ------------------------------------------------------------------------------------------ pyc lookup
class GameZips:
    """Opens core.zip/simulation.zip lazily and caches their name lists. `gameplay` lets a test point
    this at a small fake pair of zips instead of the real install."""

    def __init__(self, gameplay=GAMEPLAY, zip_order=ZIP_ORDER):
        self.gameplay = gameplay
        self.zip_order = zip_order
        self._zips = {}
        self._names = {}

    def _zip(self, name):
        if name not in self._zips:
            z = zipfile.ZipFile(os.path.join(self.gameplay, name))
            self._zips[name] = z
            self._names[name] = set(z.namelist())
        return self._zips[name]

    def available(self):
        return all(os.path.isfile(os.path.join(self.gameplay, n)) for n in self.zip_order)

    def find_module(self, module):
        """(zip_name, Code) for the first zip (in zip_order) holding <module>.pyc, else (None, None).
        Tries the module as a flat file first ('sims.sim_info' -> 'sims/sim_info.pyc'), then as a
        package ('services' -> 'services/__init__.pyc') - a manifest row never has to spell out
        '.__init__' itself to cite a package like `services` or `sims4.localization`."""
        base = module.replace('.', '/')
        candidates = (base + '.pyc', base + '/__init__.pyc')
        for name in self.zip_order:
            z = self._zip(name)
            for arc in candidates:
                if arc in self._names[name]:
                    return name, pyc37.load(z.read(arc))
        return None, None

    def close(self):
        for z in self._zips.values():
            z.close()
        self._zips.clear()
        self._names.clear()


# ------------------------------------------------------------------------------------------ name descent
def _child_code(code, name):
    for k in code.co_consts:
        if isinstance(k, pyc37.Code) and k.co_name == name:
            return k
    return None


def _has_literal(module_code, literal):
    for c in pyc37.walk(module_code):
        if literal in c.co_names:
            return True
        if any(x == literal for x in c.co_consts if isinstance(x, str)):
            return True
    return False


def resolve(module_code, path, kind):
    """(ok, detail) for one row already matched to a module's Code. Never raises - a name genuinely
    not being there is the expected, reportable outcome this whole tool exists to catch."""
    if kind == 'module':
        return True, 'module present'
    if kind == 'command':
        if _has_literal(module_code, path):
            return True, 'command literal present'
        return False, 'command literal %r not found anywhere in the module' % (path,)
    parts = path.split('.')
    code = module_code
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        owner_name = '<module>' if code is module_code else code.co_name
        child = _child_code(code, part)
        if child is not None:
            code = child
            continue
        if part in code.co_names:
            if last:
                return True, 'name binding in %s' % owner_name
            return False, ('%r in %s is a plain name, not a class/function - can\'t descend into %r'
                            % (part, owner_name, '.'.join(parts[i + 1:])))
        return False, '%r not found in %s' % (part, owner_name)
    return True, 'found'


# ------------------------------------------------------------------------------------------ the check
def check(rows=None, zips=None):
    """[dict] one per manifest row: module, path, kind, source, expected, ok, where, detail. Only a
    real I/O problem (no game install at all) raises; a missing name is a normal, reported result."""
    rows = novulon_api_manifest.ALL_ROWS if rows is None else rows
    zips = zips or GameZips()
    out = []
    for row in rows:
        zip_name, code = zips.find_module(row.module)
        if code is None:
            out.append({'module': row.module, 'path': row.path, 'kind': row.kind, 'source': row.source,
                        'expected': row.expected, 'ok': False, 'where': None,
                        'detail': 'module not found in %s' % ' or '.join(zips.zip_order)})
            continue
        ok, detail = resolve(code, row.path, row.kind)
        out.append({'module': row.module, 'path': row.path, 'kind': row.kind, 'source': row.source,
                    'expected': row.expected, 'ok': ok, 'where': zip_name, 'detail': detail})
    return out


def version_warnings(installed_version, checked_against=None):
    """One line per manifest file whose optional CHECKED_AGAINST disagrees with the currently
    installed build (files that only note their checked build in prose, not in CHECKED_AGAINST,
    aren't flagged here - main() always prints the installed build so a prose citation can still be
    eyeballed against it). Pure - takes the dict directly, so this is unit-tested without any real
    manifest file or game install (test_novulon_api_surface.py)."""
    checked_against = novulon_api_manifest.CHECKED_AGAINST if checked_against is None else checked_against
    lines = []
    if not installed_version:
        return lines
    for source, recorded in sorted(checked_against.items()):
        if recorded != installed_version:
            lines.append('%s.py declares CHECKED_AGAINST = %r; this run sees build %s - treat its '
                         'rows as unverified until it is re-checked' % (source, recorded, installed_version))
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--quiet', action='store_true', help='print only the summary and the failures')
    ap.add_argument('--gameplay', default=GAMEPLAY, help='override the Gameplay folder (tests)')
    ap.add_argument('--game-dir', default=GAME_DIR, help='override the game folder (tests)')
    a = ap.parse_args(argv)

    zips = GameZips(gameplay=a.gameplay)
    if not zips.available():
        print('PROBLEM: game zips not found under %s - is E:\\The Sims 4 installed on this machine?' % a.gameplay)
        return 2

    version = game_build_version(a.game_dir)
    print('checking against installed game build %s' % (version or 'unknown'))
    warnings = version_warnings(version)
    if warnings:
        print('=' * 78)
        print('GAME VERSION WARNINGS (never a silent pass):')
        for w in warnings:
            print('  - ' + w)
        print('=' * 78)

    try:
        results = check(zips=zips)
    finally:
        zips.close()
    failures = [r for r in results if not r['ok']]

    if not a.quiet:
        for r in sorted(results, key=lambda r: (r['ok'], r['source'], r['module'], r['path'] or '')):
            mark = 'ok  ' if r['ok'] else 'MISS'
            where = r['where'] or '-'
            print('%s  %-11s %-35s %-40s  %s' % (mark, where, r['module'], r['path'] or '(module)', r['detail']))
    print('-' * 78)
    print('%d row(s) checked, %d ok, %d missing, game build %s' % (
        len(results), len(results) - len(failures), len(failures), version or 'unknown'))
    if failures:
        print('MISSING (verify or cut - never ship a guess):')
        for r in failures:
            print('  - %s (%s) [%s.py]: %s' % (r['module'], r['path'] or '(module)', r['source'], r['detail']))

    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

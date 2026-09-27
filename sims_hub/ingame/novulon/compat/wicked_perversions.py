"""Wicked Perversions presence/duplicate-install probe - informational only (SPEC.md Sec 10/Sec 12).

Two independent, WickedWhims-dependent Wicked Perversions builds exist and are BOTH installed side by
side on this machine today (research/adult_wants.md Sec 1/Sec 4.6): `HARKI_Wicked_Perversions` (package
`HRKWP`) and `NisaK_Wicked_Perversions` (package `NisaK`) - different authors, different internal module
trees. No research pass found, and this session's own re-check found, no single tuning id the two forks
both register - so unlike `mccc.py`/`wickedwhims.py`, this file does NOT use `compat.probe()`'s
instance-manager technique (there is nothing to cut here, this was checked - see the build report).

Instead it uses the exact technique WickedWhims itself already ships, live, for its OWN self-duplicate
check (`wickedwhims/utils_mods.pyc`, disassembled in research/adult_wants.md Sec 4.6): `os.walk` the
installed Mods folder, purely by filename. Nothing here inspects a file's contents or imports anything -
it is exactly as safe as `common.sims_dir()`'s own directory walk, and strictly read-only.

Informational only, surfaced by `settings_ui`'s Compatibility row (SPEC.md Sec 12's "Added in this
review" line: "Wicked Perversions: 2 copies detected - this can cause conflicts.") - never gates a
feature, unlike WickedWhims's own probe in this same package.
"""
import os

from .. import common

# Exact filenames each known build ships - see module docstring for why a filename scan, not a shared
# tuning id, is the detection key here.
KNOWN_FILENAMES = ('HARKI_Wicked_Perversions.ts4script', 'NisaK_Wicked_Perversions.ts4script')

_cache = None   # list of filenames found under <Sims 4>\Mods, cached after the first scan this session


def _scan():
    d = common.sims_dir()
    if not d:
        return []
    mods_dir = os.path.join(d, 'Mods')
    found = []
    for _root, _dirs, files in os.walk(mods_dir):
        for name in files:
            if name in KNOWN_FILENAMES and name not in found:
                found.append(name)
    return found


def installed_variants(force=False):
    """Filenames of every known Wicked Perversions build found under <Sims 4>\\Mods (0, 1, or 2 today on
    this machine). Cached after the first call this session; pass force=True to re-scan (tests only -
    the game never needs to, since the Mods folder doesn't change mid-session)."""
    global _cache
    if _cache is None or force:
        _cache = common.guarded('compat.wicked_perversions.installed_variants', _scan)
        if _cache is None:
            _cache = []
    return _cache


def is_present():
    """True if at least one known Wicked Perversions build is installed."""
    return bool(installed_variants())


def duplicate_count():
    """How many known Wicked Perversions builds are installed side by side - the count SPEC.md Sec 12's
    Compatibility row needs for its "N copies detected" line."""
    return len(installed_variants())


def reset_cache():
    """Forget the cached scan (tests only)."""
    global _cache
    _cache = None

"""adult/ - SPEC.md Sec.11's Adult section (BP11), V1 files only (the rest of the tree - `std.py`,
`fertility.py`, `presets.py`, `roster.py`, `bulk.py`, `journal.py`, `impressions.py` - is reserved
names only, not built this phase, per SPEC.md Sec.3's own tree).

  * `gate.py`     - the independent age/species predicate, and the section's own show/hide gate
                    (WickedWhims present AND the player opted in).
  * `settings.py` - the two `adult.*` settings.json fields (`enabled`, `interstitial_shown`).
  * `bridge.py`   - the Aggregated Settings Front Door's plumbing (WickedWhims' own three settings
                    accessor functions - nothing new is built here).
  * `panic.py`    - the one-click "Stop Everything" / "Resume Autonomy" pair.
  * `menu.py`     - wires all four into the actual "Adult" Main Menu tile
                    (`commands.add_section('adult', ...)`).

Importing this package registers the tile (`menu.py`'s own `commands.add_section` call runs at its
own import time, SPEC.md Sec.3.7) - it does not make the tile APPEAR; that still depends entirely on
`gate.is_adult_section_available()` being true at the time the Main Menu is actually built. Guarded,
like every other Novulon start-up step: a failure here (e.g. `menukit`/`commands` not loadable yet)
just means the tile never registers - logged, never a crash that takes the rest of the mod down.
"""
from .. import common


def _start():
    try:
        from . import menu  # noqa: F401  (import alone registers the Main Menu tile)
    except Exception:
        common.log_exception('novulon.adult: import menu')


_start()

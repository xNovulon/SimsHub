"""compat - safe presence probes for other installed Sims 4 mods (SPEC.md `compat/` Sec 10, build
package BP7): "ask the game's own instance manager for a known id", never `import <that mod>` - a
technique this repo's own research verified in two different installed, WORKING mods, disassembled
directly rather than assumed (research/adult_wants.md Sec 4.2): WickedWhims's own
`wickedwhims/main/game_handlers/basemental/availability.pyc` detects Basemental Drugs exactly this way,
and NisaK's own Wicked Perversions detects WickedWhims itself the same way. Nothing in this package ever
raises into the game, and nothing here `import`s another mod's package by name - a probe id is a bare
int, resolved through the game's own instance manager, which returns `None` (never raises) for an id it
doesn't have.

  * `mccc.py`              - MC Command Center presence + `should_defer(feature)` (Sec 9.1/Sec 10)
  * `wickedwhims.py`        - WickedWhims presence + version string + the three settings-accessor pairs
                              the research verified safe to call (Sec 10; `adult/bridge.py`, BP11, not
                              built in this pass, is expected to be the main caller of the accessors)
  * `wicked_perversions.py` - informational presence/duplicate-install probe (Sec 10/Sec 12)
  * `ui_cheats.py`          - documented no-op (Sec 10 - no known conflict surface to probe for)

`probe()` below is the one shared primitive `mccc.py`/`wickedwhims.py` call; `wicked_perversions.py`
does not use it (see that file's own docstring for why) and `ui_cheats.py` probes nothing at all. None of
this package's files import a game module at their own top level, so importing `novulon.compat` (or any
of its submodules) outside the game - a test, a tool - never raises.
"""
from .. import common

_cache = {}   # (instance_type, instance_id) -> bool, filled in on first probe() call for that pair


def probe(instance_type, instance_id):
    """True if the game's instance manager for `instance_type` currently has `instance_id` loaded - the
    generic "is some other mod's tuning present" test SPEC.md Sec 10 specifies, verified twice in real,
    installed mods (see module docstring). Cached per (instance_type, instance_id) after the first call
    - a mod's presence never changes mid-session, matching adult_wants.md Sec 4.2's own note that both
    real-world callers cache their result after the first call. Never raises; any failure (no `services`
    module outside the game, a manager that doesn't exist, ...) is cached as False, same as a genuinely
    absent mod - the always-safe direction (SPEC.md Sec 10's own primitive already returns False here
    on a caught exception, not just "unknown")."""
    key = (instance_type, instance_id)
    if key not in _cache:
        _cache[key] = bool(common.guarded('compat.probe %r' % (key,), _probe_now, instance_type, instance_id))
    return _cache[key]


def _probe_now(instance_type, instance_id):
    import services
    mgr = services.get_instance_manager(instance_type)
    return mgr is not None and mgr.get(instance_id) is not None


def reset_cache():
    """Forget every cached probe() result (tests only) - the game never needs to call this; a mod's
    presence is fixed for the life of one game session."""
    _cache.clear()

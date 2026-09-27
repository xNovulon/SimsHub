"""Put a "Novulon" pie-menu wedge on every computer and tablet (SPEC.md Sec.6).

**What is NOT built here**: there is no `Computer` class and no computer `Tag` to look up -
`objects/computer/computer.pyc` does not exist anywhere in this game build's own base.zip/simulation.zip
(gaps.md Sec.A.1, confirmed there by listing every module in both zips). Each catalog computer/tablet gets
its own tuning class generated from its own Object Tuning XML, not a shared Python superclass.

**The real, load-bearing test** (mechanism copied from MC Command Center's own already-disassembled
`_process_objects_on_load`, gaps.md Sec.A.1 - not its code): every computer/tablet object's tuning already
carries animation-override data that tells the game which sit/carry pose to use, and that data has a
'computerType' key, or 'carryObject' == 'tablet'. `_anim_overrides_cls` and `_super_affordances` are both
confirmed, this session, as real attribute names on `ScriptObject` (`objects/script_object.pyc`, this
game's own simulation.zip). The tuning VALUES compared against ('computerType', 'carryObject', 'tablet')
are not Python symbols at all - they live in per-object XML tuning resolved at runtime, so they cannot be
found in any .pyc; they are carried forward from gaps.md's own disassembly of an installed, working mod
that uses exactly this comparison in production, not guessed at here. `is_computer_tuning_class` is
getattr-guarded at every step, so a game build where this shape changed just returns False - it never
raises into the sweep below.

**Attaching the interaction** (verified mechanism, game_api.md Sec.1 + gaps.md Sec.A.1):
`_super_affordances` lives on the tuning CLASS and is re-read live on every pie-menu build
(`objects/script_object.pyc`, `ScriptObject.super_affordances`), so growing it once applies to every
existing and future instance of that catalog object, no reload needed.

**Finding every loaded object tuning class - verified this session, closing SPEC.md Sec.18's open item for
this exact call**: `sims4/tuning/instance_manager.py` inside this build's own core.zip disassembles to
`InstanceManager.types` being a `@property` that returns `self._tuned_classes` (a dict, keyed by resource
key), confirmed by reading its actual bytecode (`LOAD_NAME property` immediately precedes it, then
`self._tuned_classes; RETURN_VALUE`). So
`services.get_instance_manager(sims4.resources.Types.OBJECT).types.values()` is exactly "every loaded
object tuning class" - gaps.md Sec.A.1 flagged this as "worth a quick confirming pyc37.py --outline pass";
this file is that pass, and it holds up. `services.get_instance_manager` is itself confirmed the same way:
`services/__init__.pyc`'s module-level code does
`tuning_managers = InstanceTuningManagers(); get_instance_manager = tuning_managers.__getitem__`.

**Late-streamed objects** (verified this session against `indexed_manager.pyc`): `IndexedManager` has a
nested top-level `CallbackTypes` class with `ON_OBJECT_ADD = 0`, and
`register_callback(self, callback_type, callback)` appends the callback to a plain list that
`call_on_add(self, obj)` later calls with that one object as its only argument - so
`services.object_manager().register_callback(indexed_manager.CallbackTypes.ON_OBJECT_ADD, on_new_object)`
is exactly the shape SPEC.md Sec.6 describes. `services.object_manager()` returns None before any zone is
active (it reads the current zone's own IndexedManager), so the callback is (re-)registered at the START
of every zone, not once at mod import - each zone gets a fresh IndexedManager with an empty callback list.

**When the sweep runs**, both from the same `zone.Zone.start_services` hook (the exact attribute
speedkit_monitor/loadtimer.py already wraps live, confirmed unchanged in this build's zone.pyc this
session): (1) sweep every already-loaded object tuning class, (2) register the late-object callback for
this zone's own object manager.

**V1 scope**: computer and tablet only. `is_computer_tuning_class`/`sweep`/`on_new_object` all take the
interaction id as a parameter rather than a module-level constant baked into the check itself, so a v1.1
pass can add other entry points with no plumbing changes.
"""
from . import common, hooks

# tools/novulon_ids/bp13_package_build.py's INTERACTION_OPEN_MENU = custom_id('Novulon_OpenMenu_Interaction').
# `tools/` is dev-side build tooling only - it is never bundled into Novulon.ts4script, so the shipped
# runtime code cannot import it; this literal MUST stay equal to that value (tests/test_novulon_inject.py
# asserts the two are byte-for-byte the same number, so a hash/name change on either side is caught).
NOVULON_INTERACTION_ID = 0xB60FE75296EA0C95

MARK = 'NOVULON_INJECTED'
_seen_definitions = set()   # definition ids already handed to inject_if_computer via on_new_object


def is_computer_tuning_class(tuning_class):
    """True if `tuning_class` is per-object tuning for a computer or tablet. Never raises - a tuning
    class missing any of this data is just "not a computer"."""
    ov = getattr(tuning_class, '_anim_overrides_cls', None)
    params = getattr(ov, 'params', None) if ov is not None else None
    if not params:
        return False
    try:
        return 'computerType' in params or params.get('carryObject') == 'tablet'
    except Exception:
        return False


def _lookup_interaction(interaction_id):
    try:
        import services
        import sims4.resources
    except Exception:
        common.log_exception('inject: importing services/sims4.resources')
        return None
    mgr = common.guarded('inject: get_instance_manager(INTERACTION)', services.get_instance_manager,
                          sims4.resources.Types.INTERACTION)
    if mgr is None:
        return None
    return common.guarded('inject: interaction lookup', mgr.get, interaction_id)


def inject_if_computer(tuning_class, interaction_id):
    """Add Novulon's pie-menu interaction to `tuning_class._super_affordances` once, if it is a
    computer/tablet. Returns True if it was (newly, or already) injected, False otherwise."""
    if getattr(tuning_class, MARK, False):
        return True
    if not is_computer_tuning_class(tuning_class):
        return False
    aff = _lookup_interaction(interaction_id)
    if aff is None:
        common.log('inject: Novulon interaction tuning not loaded yet (id 0x%X)' % (interaction_id,))
        return False
    try:
        tuning_class._super_affordances = tuning_class._super_affordances + (aff,)
        setattr(tuning_class, MARK, True)
    except Exception:
        common.log_exception('inject: adding affordance to %r' % (tuning_class,))
        return False
    return True


def sweep(interaction_id):
    """Walk every currently loaded object tuning class and inject into each computer/tablet found.
    Returns the number injected (0 on any failure - never raises)."""
    try:
        import services
        import sims4.resources
    except Exception:
        common.log_exception('inject: sweep import')
        return 0
    mgr = common.guarded('inject: get_instance_manager(OBJECT)', services.get_instance_manager,
                          sims4.resources.Types.OBJECT)
    if mgr is None:
        return 0
    types = common.guarded('inject: reading loaded object types', lambda: list(mgr.types.values()))
    if not types:
        return 0
    count = 0
    for cls in types:
        if common.guarded('inject: sweep one tuning class', inject_if_computer, cls, interaction_id):
            count += 1
    common.log('inject: sweep found %d computer/tablet tuning class(es) among %d loaded object types' % (
        count, len(types)))
    return count


def on_new_object(obj, interaction_id):
    """IndexedManager.CallbackTypes.ON_OBJECT_ADD callback: a late-streamed object appeared. Dedupe by
    definition id so re-streaming the same catalog object doesn't re-walk its tuning class every time."""
    definition = getattr(obj, 'definition', None)
    cls = getattr(definition, 'cls', None)
    if cls is None:
        return
    def_id = getattr(definition, 'id', None)
    if def_id is not None:
        if def_id in _seen_definitions:
            return
        _seen_definitions.add(def_id)
    inject_if_computer(cls, interaction_id)


def _register_late_callback(interaction_id):
    import services
    import indexed_manager
    om = services.object_manager()
    if om is None:                          # no zone yet - nothing to register against
        return False
    om.register_callback(
        indexed_manager.CallbackTypes.ON_OBJECT_ADD,
        lambda obj: common.guarded('inject: on_new_object', on_new_object, obj, interaction_id))
    return True


def _on_zone_start(_zone_obj, interaction_id):
    common.guarded('inject: sweep at zone start', sweep, interaction_id)
    common.guarded('inject: register late-object callback', _register_late_callback, interaction_id)


def install(interaction_id):
    """Wrap zone.Zone.start_services (sweep + register the late-object callback, every zone start).
    Returns {hook label: installed?}."""
    done = {}
    try:
        import zone
        done['Zone.start_services'] = hooks.install(
            zone.Zone, 'start_services',
            lambda orig: hooks.around(
                orig, after=lambda a, r: _on_zone_start(a[0], interaction_id), label='novulon inject'),
            'Zone.start_services (novulon inject)')
    except Exception:
        common.log_exception('inject: hook Zone.start_services')
        done['Zone.start_services'] = False
    common.log('inject hooks: ' + ', '.join('%s %s' % (k, 'ok' if v else 'FAILED') for k, v in done.items()))
    return done

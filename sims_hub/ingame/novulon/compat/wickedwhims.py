"""WickedWhims presence probe, version string, and the three settings-accessor pairs SPEC.md Sec 10
names as the safe surface to call (research/adult_wants.md Sec 4.3 ranks plain accessor FUNCTIONS and
`ww.*` console commands as the only other reasonably stable coupling, well below reaching into
`wickedwhims.main.*`/`...integral.*` internals, which that same research confirms are deliberately
obfuscated release to release).

**Corrects a real bug in the spec's own carried-forward probe id-and-type pairing.** SPEC.md Sec 10
(citing research/adult_wants.md Sec 4.2) names WickedWhims's own presence-probe id as
`18173180371816048676` (NisaK Wicked Perversions' own constant for detecting WickedWhims) and says to
probe it "the same way" as MCCC's id - i.e. against `sims4.resources.Types.INTERACTION`. Re-verified
this session, directly against this machine's own currently-installed
`TURBODRIVER_WickedWhims_Tuning.package` (`wicked_animator/backend/dbpf.py:read_index`, read-only): the
id IS present in that package - but as DBPF resource type `0x0C772E27`, not `0xE882D22F` (Interaction
tuning). Disassembling this build's own `sims4/resources.pyc` (`Types()`'s class body - this package's
manifest) shows `0x0C772E27` is a real, distinct, separately-verified `Types` member:
`Types.ACTION` (confirmed `STORE_NAME ACTION` immediately after that constant, its own
`_add_inst_tuning('action', 209137191, ...)` call). NisaK's own already-disassembled code
(research/adult_wants.md Sec 4.2) reads `NisaServices.action_manager().get(18173180371816048676)` -
"action_manager" is NisaK's own name for `services.get_instance_manager(Types.ACTION)`, not
`Types.INTERACTION`; the spec's "probe it the same way" instruction just dropped which manager NisaK
actually used, since both MCCC's and WickedWhims's ids happen to look the same shape (a bare 64-bit int)
even though they live in different instance managers. Probing this id against `Types.INTERACTION` (what
MCCC's id needs) would silently and *permanently* cache "WickedWhims not present" for the rest of the
session, even with WickedWhims installed and running - `compat.probe()`'s own cache makes exactly this
kind of mistake permanent, which is why it needed catching before it shipped, not after: a false "not
present" here would silently hide the entire Adult tile (SPEC.md Sec 11's hard precondition) for every
player who has WickedWhims installed. `INSTANCE_TYPE_NAME = 'ACTION'` below, not 'INTERACTION'.

Version string (`get_mod_version_str`) and all three accessor pairs are confirmed, this session, as real
top-level functions at exactly these names, in this machine's own currently-installed
`TURBODRIVER_WickedWhims_Scripts.ts4script` (`tools/pyc37.py --outline` against
`wickedwhims/version_registry.pyc`, `wickedwhims/sex/sex_settings.pyc`,
`wickedwhims/nudity/nudity_settings.pyc`, `wickedwhims/relationships/relationship_settings.pyc` - see
this package's build report for the exact output). These are third-party module paths, not EA API - there
is no base-game `.pyc` to check them against, so they are NOT listed as `ROWS` in this package's manifest
file (`novulon_api_check.py` only ever opens the game's OWN zips; a third-party module path would just
show up there as a false "missing"). This prose is the equivalent verification the override note asks
for, done against the actual currently-installed copy instead of trusted from research. `RELEASE_BUILD_
NUMBER` on this machine is 185 (v185k, public build) - informational only (Settings > Compat), never a
version gate; SPEC.md Sec 10 is explicit V1 has no version-gated feature.

Every accessor call here is wrapped exactly like `inject.py`'s own game-module lookups: import inside the
function, `common.guarded` around the actual call, log-and-return-None on any failure - a WickedWhims
update that renames or removes one of these functions degrades this file to "informational line
missing"/"setting not read", never a crash.
"""
from .. import common
from . import probe

INSTANCE_ID = 18173180371816048676
INSTANCE_TYPE_NAME = 'ACTION'   # NOT 'INTERACTION' - see module docstring


def is_present():
    """True if WickedWhims's own root Action-tuning is currently loaded. Cached by compat.probe()."""
    try:
        import sims4.resources
    except Exception:
        common.log_exception('compat.wickedwhims.is_present (import sims4.resources)')
        return False
    return probe(sims4.resources.Types.ACTION, INSTANCE_ID)


def version_str():
    """WickedWhims's own version string (e.g. 'v185k'), or None if WW isn't present or the call fails.
    Display-only (Settings > Compat) - never a feature gate, see module docstring."""
    if not is_present():
        return None

    def _read():
        import importlib
        mod = importlib.import_module('wickedwhims.version_registry')
        return mod.get_mod_version_str()
    return common.guarded('compat.wickedwhims.version_str', _read)


def _accessor(module_name, func_name, *args):
    """Call WickedWhims's `<module_name>.<func_name>(*args)` if WW is present; guarded, returns None on
    any failure (WW absent, the function renamed/removed by an update, a bad argument, ...). `bridge.py`
    (adult, BP11) is the expected caller for these six; nothing else in Novulon needs to touch WickedWhims
    settings directly."""
    if not is_present():
        return None

    def _call():
        import importlib
        mod = importlib.import_module(module_name)
        return getattr(mod, func_name)(*args)
    return common.guarded('compat.wickedwhims.%s.%s' % (module_name, func_name), _call)


def get_sex_setting(name):
    return _accessor('wickedwhims.sex.sex_settings', 'get_sex_setting', name)


def set_sex_setting(name, value):
    return _accessor('wickedwhims.sex.sex_settings', 'set_sex_setting', name, value)


def get_nudity_setting(name):
    return _accessor('wickedwhims.nudity.nudity_settings', 'get_nudity_setting', name)


def set_nudity_setting(name, value):
    return _accessor('wickedwhims.nudity.nudity_settings', 'set_nudity_setting', name, value)


def get_relationship_setting(name):
    return _accessor('wickedwhims.relationships.relationship_settings', 'get_relationship_setting', name)


def set_relationship_setting(name, value):
    return _accessor('wickedwhims.relationships.relationship_settings', 'set_relationship_setting',
                      name, value)

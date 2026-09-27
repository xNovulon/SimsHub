"""EA names BP7 (`ingame/novulon/compat/`) and BP12 (`ingame/novulon/settings_ui/`) cite - see this
package's __init__.py for the ROWS shape. `compat/`'s `probe()` primitive reuses the exact
`services.get_instance_manager(...).get(...)` surface BP1/BP3 already verified against this machine
(`bp1_bp3_core_inject.py`) - re-cited here too so this file is self-contained for anyone auditing just
BP7/BP12's own code. `settings_ui/` introduces no new EA API at all (module docstring) - only `compat/`
adds one genuinely new row.

**New this session**: `sims4.resources.Types.ACTION`. Disassembled directly from this machine's own
`sims4/resources.pyc` (`Types()`'s class body, `tools/pyc37.py "E:/The Sims 4/Data/Simulation/Gameplay/
core.zip" sims4/resources.pyc Types`): a `_add_inst_tuning('action', 209137191, True, ...,
manager_type=sims4.tuning.instance_manager_types.INSTANCED_CLASS_MANAGER)` call immediately followed by
`STORE_NAME ACTION` - a real, class-level `Types` member, the same construction shape already verified
for `Types.INTERACTION`/`Types.OBJECT` in `bp1_bp3_core_inject.py`. This is what
`compat/wickedwhims.py`'s probe needs (see that file's own docstring for why `Types.INTERACTION`, the
type MCCC's probe id needs, is the WRONG type for WickedWhims's probe id) - finding this was itself the
main verification work in this pass, not a routine re-check.

`InstanceManager.get`'s behavior for a manager built with `manager_type=INSTANCED_CLASS_MANAGER` (what
backs `Types.ACTION`) specifically, as opposed to `INTERACTION_INSTANCE_MANAGER` (what backs
`Types.INTERACTION`, already verified in `bp1_bp3_core_inject.py`), was not independently disassembled
this session as a THIRD verification - it is corroborated instead by NisaK's own already-disassembled,
real, WORKING code (research/adult_wants.md Sec 4.2): `NisaServices.action_manager().get(id)` is exactly
`services.get_instance_manager(Types.ACTION).get(id)` under NisaK's own name for it, proving `.get()`
exists and behaves as expected on this specific manager kind in a real, installed, functioning mod - a
form of evidence this file records rather than omits, but distinct from this session's own direct
bytecode reads of the other rows below.

Third-party (non-EA) verification this pass also did, NOT listed as ROWS here on purpose (see
`novulon_api_manifest/__init__.py`'s own docstring on what `kind` describes and what
`novulon_api_check.py` actually opens - only this game's OWN `base.zip`/`core.zip`/`simulation.zip`; a
third-party mod's module path would only ever show up there as a false "missing"):
  * MC Command Center's own probe id (`compat/mccc.py`'s `INSTANCE_ID = 0xD27DB58CF1DAF8FA`) is actually
    present, as DBPF type `0xE882D22F` (Interaction tuning), inside this machine's real, installed
    `mc_cmd_center.package` - read directly, read-only, with `wicked_animator/backend/dbpf.py:
    read_index`.
  * WickedWhims's own probe id (`compat/wickedwhims.py`'s `INSTANCE_ID = 18173180371816048676`) is
    present in this machine's real, installed `TURBODRIVER_WickedWhims_Tuning.package` - but as DBPF
    type `0x0C772E27` (`Types.ACTION`, this row), NOT `0xE882D22F` - see that file's docstring for the
    full correction this finding drove.
  * All six of WickedWhims's settings-accessor functions plus `get_mod_version_str`
    (`compat/wickedwhims.py`'s own docstring lists the exact modules/functions) confirmed present, at
    exactly those names, in this machine's real, installed `TURBODRIVER_WickedWhims_Scripts.ts4script`
    via `tools/pyc37.py --outline`.
  * Wicked Perversions: no tuning id used at all (`compat/wicked_perversions.py` uses a filename scan
    instead, precedented by WickedWhims's own real, installed, working self-duplicate check,
    `wickedwhims/utils_mods.pyc` - see that file's own docstring) - nothing to verify against a `.pyc`
    here either way.

Game build note (matching every other manifest file in this tree): `novulon_api_check.py`'s own
`game_build_version()` reads `Delta\\<pack>\\Version.ini`, which is `1.126.73.1030` on this machine.
"""

CHECKED_AGAINST = '1.126.73.1030'

ROWS = [
    # services/__init__.pyc - compat.probe()'s own primitive; re-cited from bp1_bp3_core_inject.py
    # (an agreeing duplicate citation is fine, per novulon_api_manifest/__init__.py's own docstring)
    ('services.__init__', 'get_instance_manager', 'member'),

    # sims4/resources.pyc
    ('sims4.resources', 'Types', 'class'),
    ('sims4.resources', 'Types.INTERACTION', 'member'),   # compat/mccc.py's probe type
    ('sims4.resources', 'Types.ACTION', 'member', 209137191),   # NEW this session - compat/wickedwhims.py

    # sims4/tuning/instance_manager.pyc
    ('sims4.tuning.instance_manager', 'InstanceManager.get', 'method'),
]

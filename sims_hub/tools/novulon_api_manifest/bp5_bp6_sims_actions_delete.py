"""EA names BP5 (`ingame/novulon/sims/actions.py`) and BP6 (`ingame/novulon/sims/delete.py`) cite, all
checked this session against THIS installed game build's own `.pyc` with `sims_hub/tools/pyc37.py
"E:/The Sims 4/Data/Simulation/Gameplay/{core,simulation}.zip" <module>.pyc [name]` - outline first,
then a targeted disassembly of the actual handler, never taken on trust from `research/game_api.md` or
from another package's already-shipped manifest (though several rows below independently confirm what
`bp1_bp3_core_inject.py`/`bp4_sims_browser.py`/`bp8_bp9_bp10.py` also found - noted where that happened).

Real findings this session, each also noted at its point of use in `sims/actions.py`/`sims/delete.py`:
  * `sims.add_to_family` (`add_to_family`, `server_commands/sim_commands.pyc:345`) is the real, single
    vanilla "add to household" command - resolves SPEC.md Sec 5.5/18's "Add to Household... unverified"
    flag. With no second Sim it defaults to the ACTIVE household (`household_manager().
    switch_sim_household(from_sim, None, reason=HouseholdChangeOrigin.CHEAT)`).
  * `SimInfo.is_selectable`/`Client.add_selectable_sim_by_id`/`remove_selectable_sim_by_id`
    (`sims/sim_info.pyc:812`, `server/client.pyc:408/421`) - "playable" is a per-client selectable-Sims
    set, not a household-membership flag. Resolves SPEC.md Sec 5.5/18's "Make Playable/Make NPC...
    unverified" flag. `remove_selectable_sim_by_id` itself refuses (`return False`) rather than letting
    a household drop below one selectable Sim - a real, built-in safety rail, disassembled in full.
  * `Sim.level` (`sims/sim.pyc:681`) is a real property; `.position`/`.location` are read/written as
    plain attributes throughout the engine (`objects/doors/door_commands.pyc:validate_front_door`'s
    `door.position` read; `server_commands/object_commands.pyc:set_position`'s `obj.location.clone(
    translation=Vector3(x,y,z))` write, both disassembled in full) - resolves the "Teleport to Me"
    position/level read `gameplay/cheats.py` (BP9, shipped earlier in this session) explicitly left
    unverified and cut.
  * `'stats.set_stat'` and `'stats.set_commodity'` are two Command aliases of the SAME function,
    `set_statisitic(stat_type, value, opt_sim, opt_target_type, _connection)`
    (`statistic_commands.pyc:173`) - a RAW value setter, not a 0-100 percentage. Independently
    confirmed against `bp8_bp9_bp10.py`'s own citation of the identical pairing (`gameplay/menu.py`
    reached the same conclusion separately) - cross-checked, not copied blind.
  * `stats.clear_skill` (`clear_skill`, `statistic_commands.pyc:415`) clears EVERY tracked skill on the
    Sim (iterates every statistic, filters `is_skill`), not one named skill - independently confirmed
    against `bp8_bp9_bp10.py`'s identical finding.
  * `careers.promote`/`careers.demote` (`career_promote_sim`/`career_demote_sim`,
    `career_commands.pyc:335/361`) are real, verified command literals - SPEC.md Sec 5.5/9.3 flagged
    both as unverified before this pass; also independently confirmed by `bp8_bp9_bp10.py`.
  * `occult.switch_to_occult`/`occult.add_occult`/`occult.remove_occult`
    (`sims/occult/occult_commands.pyc:switch_to_occult_type`/`add_occult_type`/`remove_occult_type`,
    lines 63/29/46) are real, verified commands taking the occult type's NAME (e.g. `VAMPIRE`) - this
    file uses only `switch_to_occult`/`remove_occult` (Turn Into / Remove); `add_occult` is available
    but not wired to a row (Turn Into already covers the ask).
  * `alarms.add_alarm_real_time`/`cancel_alarm` (`alarms.pyc:71/103`) - the scheduling primitive
    SPEC.md Sec 18 flagged as the one build-blocking open item for `sims/delete.py`'s uninstanced poll.
    `AlarmHandle.__init__` (line 147) requires a real, weakly-referenceable, non-`None` `owner` (raises
    `ValueError` otherwise) - `delete.py` uses `services.get_reset_and_delete_service()`, confirmed
    used for exactly this purpose (`ResetAndDeleteService.trigger_reset`, line 299, confirmed `source`/
    `cause` are stored on a `ResetRecord` and only read back on a different, unreached branch -
    `RESET_ON_ERROR` - for the `BEING_DESTROYED` reason this file always passes, so `source=None,
    cause='Novulon delete'` is a safe, inert diagnostic tag, not a guessed-at required type).

`.position` itself is NOT listed as its own row, on purpose: it is never a class-body binding anywhere
(a native/engine attribute), so this checker's dotted-path descent (see `novulon_api_check.py`'s own
docstring) cannot find "the" definition of it - the same category `bp1_bp3_core_inject.py`'s own
docstring already carves out for `_super_affordances`. The confirming citation below
(`objects.doors.door_commands`/`validate_front_door`) is the actual method whose disassembly this
session read to confirm `.position` is read as a plain attribute on a `ScriptObject`-family instance,
the same base class hierarchy `Sim` belongs to - narrower and more honest than a whole-module string
search would be.

`full_name`/`first_name`/`last_name` on `SimInfo` are used for display text only (never a safety- or
delete-path decision) and are not listed either, matching `research/game_api.md`'s own treatment
("plain properties... not individually disassembled") and every sibling package already shipped in
this tree (`sims/browser.py`, `gameplay/menu.py`, `relationships/menu.py` all read them the same way
with no dedicated manifest row).
"""

ROWS = [
    # sims4/commands.pyc (core.zip)
    ('sims4.commands', 'execute', 'function'),
    ('sims4.commands', 'client_cheat', 'function'),

    # server_commands/cas_commands.pyc (simulation.zip) - confirms the exact client_cheat template
    ('server_commands.cas_commands', 'modify_in_cas_with_household_id', 'function'),

    # server_commands/sim_commands.pyc (simulation.zip)
    ('server_commands.sim_commands', 'add_to_family', 'function'),
    ('server_commands.sim_commands', 'sims.add_to_family', 'command'),
    ('server_commands.sim_commands', 'sims.reset', 'command'),
    ('server_commands.sim_commands', 'sims.teleport_instantly', 'command'),
    ('server_commands.sim_commands', 'sims.fill_all_commodities', 'command'),
    ('server_commands.sim_commands', 'sims.add_buff', 'command'),
    ('server_commands.sim_commands', 'sims.remove_buff', 'command'),

    # sims/sim.pyc (simulation.zip)
    ('sims.sim', 'Sim.level', 'method'),   # a @property, verified

    # objects/doors/door_commands.pyc (simulation.zip) - see module docstring re: .position
    ('objects.doors.door_commands', 'validate_front_door', 'function'),

    # services/__init__.pyc (a package - see bp1_bp3_core_inject.py's own docstring on the '.__init__' spelling)
    ('services.__init__', 'get_active_sim', 'function'),
    ('services.__init__', 'client_manager', 'function'),
    ('services.__init__', 'active_household_id', 'function'),
    ('services.__init__', 'active_sim_info', 'function'),
    ('services.__init__', 'get_reset_and_delete_service', 'function'),
    ('services.__init__', 'sim_info_manager', 'function'),
    ('services.__init__', 'get_instance_manager', 'member'),

    # server/client.pyc (simulation.zip)
    ('server.client', 'Client.add_selectable_sim_by_id', 'method'),
    ('server.client', 'Client.remove_selectable_sim_by_id', 'method'),

    # sims/sim_info.pyc (simulation.zip)
    ('sims.sim_info', 'SimInfo.is_selectable', 'method'),
    ('sims.sim_info', 'SimInfo.is_instanced', 'method'),
    ('sims.sim_info', 'SimInfo.get_sim_instance', 'method'),
    ('sims.sim_info', 'SimInfo.remove_permanently', 'method'),
    ('sims.sim_info', 'SimInfo.household', 'method'),   # a @property, verified

    # sims/household.pyc (simulation.zip)
    ('sims.household', 'Household.is_active_household', 'method'),

    # sims/sim_info_manager.pyc (simulation.zip)
    ('sims.sim_info_manager', 'SimInfoManager.get_sim_info_by_name', 'method'),

    # server_commands/aging_commands.pyc (simulation.zip)
    ('server_commands.aging_commands', 'sims.age_up', 'command'),
    ('server_commands.aging_commands', 'sims.age_down', 'command'),
    ('server_commands.aging_commands', 'sims.set_age_progress_percentage', 'command'),
    ('server_commands.aging_commands', 'sims.age_add_progress_percentage', 'command'),

    # server_commands/statistic_commands.pyc (simulation.zip)
    ('server_commands.statistic_commands', 'set_statisitic', 'method'),
    ('server_commands.statistic_commands', 'stats.set_commodity', 'command'),
    ('server_commands.statistic_commands', 'set_skill_level', 'method'),
    ('server_commands.statistic_commands', 'stats.set_skill_level', 'command'),
    ('server_commands.statistic_commands', 'set_skills_to_max_level', 'method'),
    ('server_commands.statistic_commands', 'stats.set_all_skills_max', 'command'),
    ('server_commands.statistic_commands', 'clear_skill', 'method'),
    ('server_commands.statistic_commands', 'stats.clear_skill', 'command'),

    # server_commands/career_commands.pyc (simulation.zip)
    ('server_commands.career_commands', 'add_career_to_sim', 'method'),
    ('server_commands.career_commands', 'careers.add_career', 'command'),
    ('server_commands.career_commands', 'career_promote_sim', 'method'),
    ('server_commands.career_commands', 'careers.promote', 'command'),
    ('server_commands.career_commands', 'career_demote_sim', 'method'),
    ('server_commands.career_commands', 'careers.demote', 'command'),
    ('server_commands.career_commands', 'add_pto', 'method'),
    ('server_commands.career_commands', 'careers.add_pto', 'command'),
    ('server_commands.career_commands', 'add_career_performance', 'method'),
    ('server_commands.career_commands', 'careers.add_performance', 'command'),

    # sims4/resources.pyc (core.zip)
    ('sims4.resources', 'Types.TRAIT', 'member'),
    ('sims4.tuning.instance_manager', 'InstanceManager.types', 'method'),   # a @property, verified

    # sims/occult/occult_commands.pyc (simulation.zip)
    ('sims.occult.occult_commands', 'switch_to_occult_type', 'method'),
    ('sims.occult.occult_commands', 'occult.switch_to_occult', 'command'),
    ('sims.occult.occult_commands', 'remove_occult_type', 'method'),
    ('sims.occult.occult_commands', 'occult.remove_occult', 'command'),

    # server_commands/pregnancy_commands.pyc (simulation.zip)
    ('server_commands.pregnancy_commands', 'pregnancy_start', 'method'),
    ('server_commands.pregnancy_commands', 'pregnancy.start', 'command'),
    ('server_commands.pregnancy_commands', 'pregnancy_clear', 'method'),
    ('server_commands.pregnancy_commands', 'pregnancy.clear', 'command'),

    # alarms.pyc (simulation.zip) - the delete-poll scheduling primitive, SPEC.md Sec 18
    ('alarms', 'add_alarm_real_time', 'function'),
    ('alarms', 'cancel_alarm', 'function'),
    ('alarms', 'AlarmHandle.__init__', 'method'),

    # clock.pyc (simulation.zip)
    ('clock', 'interval_in_real_seconds', 'function'),

    # services/reset_and_delete_service.pyc (simulation.zip)
    ('services.reset_and_delete_service', 'ResetAndDeleteService.trigger_destroy', 'method'),
    ('services.reset_and_delete_service', 'ResetAndDeleteService.trigger_reset', 'method'),
]

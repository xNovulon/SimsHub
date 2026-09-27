"""EA names BP8 (`ingame/novulon/household/`), BP9 (`gameplay/`) and BP10 (`relationships/`) cite, all
checked this session against THIS installed game build's own `.pyc` with `sims_hub/tools/pyc37.py
"E:/The Sims 4/Data/Simulation/Gameplay/simulation.zip" <module>.pyc [name]` (outline first, then a
targeted disassembly of the actual handler function - never taken on trust from `research/game_api.md`,
since several rows below correct or extend what that research pass said).

Real findings beyond `research/game_api.md`/`SPEC.md`'s own text, each also noted at its point of use in
the code:
  * `households.modify_funds` is an ADD/REMOVE **delta** (`household.funds.add`/`try_remove`), not a "set
    to X" - SPEC.md §8 calls the row "Set Household Funds"; `household/menu.py`'s UI text says "Add or
    remove" instead.
  * `money` **does** set an absolute value (computes `amount - current_amount`, applies the delta) -
    confirms SPEC.md §8's "Set Sim's Personal Funds" description is accurate for this one.
  * `stats.clear_skill` clears **every** skill on the Sim (iterates every tracked statistic with
    `is_skill == True`), not one named skill - `gameplay/menu.py` labels the row "Clear All Skills".
  * `careers.promote`/`careers.demote` (`career_promote_sim`/`career_demote_sim`) are real, verified
    command literals - SPEC.md §5.5/§9.3 flagged Promote/Demote as unverified before this pass; no
    `careers.reset_branch` (or any "reset branch" literal) was found anywhere in `career_commands.pyc`'s
    own string table, so Reset Branch stays cut.
  * `aspirations.complete_current_milestone`/`aspirations.reset_data` are real, verified command
    literals (`server_commands/aspiration_commands.pyc`) - SPEC.md §5.5/§9.5 flagged both as unverified
    before this pass.
  * `autonomy.global` (`global_autonomy_state`) is a real, verified command literal, and its own
    `_parse_state` helper (disassembled in full) accepts `on`/`full`/`true` -> FULL, `medium` -> MEDIUM,
    `off`/`false`/`limitedonly`/`la` -> LIMITED_ONLY, `default`/`undefined` -> UNDEFINED - SPEC.md §9.11
    flagged the whole toggle as unverified before this pass.
  * `inventory.purge` (`purge_sim_inventory`) is a real, verified per-target command, but only reaches
    objects with a live `inventory_component` - i.e. currently **instanced** Sims only. No headless
    "sell all"/"transfer selected" command was found (`inventory.sell_picker_response_by_ids` needs an
    already-open picker dialog id; `sim_inventory_sell_multiple` needs a hand-built protobuf and
    reimplements the sell math itself with an unverified `currency_type`) - both cut to V1.1, see
    `household/inventory.py`'s own docstring for the full citation trail.
  * `occult.add_occult`/`occult.remove_occult`/`occult.switch_to_occult`
    (`sims/occult/occult_commands.pyc`) are real console commands - simpler and preferred over calling
    `OccultTracker`'s own Python methods directly, since the mod never needs a live `SimInfo` reference
    for this action, only an id.
  * `relationship.set_score`'s `bidirectional` parameter is accepted but never read anywhere in the
    function body (only `track_type` reaches `relationship_tracker.set_relationship_score`) - left off
    the command line entirely in `relationships/menu.py`.

Game build note (matching the other `novulon_api_manifest/*.py` files in this tree): checked against
`Delta\\<pack>\\Version.ini`'s `1.126.73.1030`, the same string `bp1_bp3_core_inject.py`/`bp2_menukit.py`
already cite for this build.
"""

CHECKED_AGAINST = '1.126.73.1030'

MANIFEST = [
    # server_commands/household_commands.pyc (simulation.zip)
    ('server_commands.household_commands', 'modify_household_funds', 'method'),
    ('server_commands.household_commands', 'households.modify_funds', 'command'),

    # server_commands/sim_commands.pyc (simulation.zip)
    ('server_commands.sim_commands', 'set_money', 'method'),
    ('server_commands.sim_commands', 'money', 'command'),
    ('server_commands.sim_commands', 'sims.fill_all_commodities', 'command'),
    ('server_commands.sim_commands', 'add_buff', 'method'),
    ('server_commands.sim_commands', 'sims.add_buff', 'command'),
    ('server_commands.sim_commands', 'remove_buff', 'method'),
    ('server_commands.sim_commands', 'sims.remove_buff', 'command'),
    ('server_commands.sim_commands', 'reset', 'method'),
    ('server_commands.sim_commands', 'sims.reset', 'command'),

    # server_commands/inventory_commands.pyc (simulation.zip)
    ('server_commands.inventory_commands', 'purge_sim_inventory', 'method'),
    ('server_commands.inventory_commands', 'inventory.purge', 'command'),
    # cited only to justify cutting them (household/inventory.py's docstring):
    ('server_commands.inventory_commands', 'sell_picker_response_by_ids', 'method'),
    ('server_commands.inventory_commands', 'sim_inventory_sell_multiple', 'method'),

    # server_commands/statistic_commands.pyc (simulation.zip)
    ('server_commands.statistic_commands', 'set_statisitic', 'method'),
    ('server_commands.statistic_commands', 'stats.set_commodity', 'command'),
    ('server_commands.statistic_commands', 'set_commodities_to_best_values_household', 'method'),
    ('server_commands.statistic_commands', 'stats.fill_commodities_household', 'command'),
    ('server_commands.statistic_commands', 'set_skill_level', 'method'),
    ('server_commands.statistic_commands', 'stats.set_skill_level', 'command'),
    ('server_commands.statistic_commands', 'set_skills_to_max_level', 'method'),
    ('server_commands.statistic_commands', 'stats.set_all_skills_max', 'command'),
    ('server_commands.statistic_commands', 'clear_skill', 'method'),
    ('server_commands.statistic_commands', 'stats.clear_skill', 'command'),

    # traits/trait_commands.pyc (simulation.zip)
    ('traits.trait_commands', 'equip_trait', 'method'),
    ('traits.trait_commands', 'traits.equip_trait', 'command'),
    ('traits.trait_commands', 'remove_trait', 'method'),
    ('traits.trait_commands', 'traits.remove_trait', 'command'),
    ('traits.trait_commands', 'clear_traits', 'method'),
    ('traits.trait_commands', 'traits.clear_traits', 'command'),
    ('traits.trait_commands', 'clear_personality_traits', 'method'),
    ('traits.trait_commands', 'traits.clear_personality_traits', 'command'),

    # server_commands/aspiration_commands.pyc (simulation.zip)
    ('server_commands.aspiration_commands', 'complete_current_milestone', 'method'),
    ('server_commands.aspiration_commands', 'aspirations.complete_current_milestone', 'command'),
    ('server_commands.aspiration_commands', 'reset_aspirations', 'method'),
    ('server_commands.aspiration_commands', 'aspirations.reset_data', 'command'),

    # server_commands/career_commands.pyc (simulation.zip)
    ('server_commands.career_commands', 'add_career_to_sim', 'method'),
    ('server_commands.career_commands', 'careers.add_career', 'command'),
    ('server_commands.career_commands', 'add_career_performance', 'method'),
    ('server_commands.career_commands', 'careers.add_performance', 'command'),
    ('server_commands.career_commands', 'add_pto', 'method'),
    ('server_commands.career_commands', 'careers.add_pto', 'command'),
    ('server_commands.career_commands', 'career_promote_sim', 'method'),
    ('server_commands.career_commands', 'careers.promote', 'command'),
    ('server_commands.career_commands', 'career_demote_sim', 'method'),
    ('server_commands.career_commands', 'careers.demote', 'command'),

    # server_commands/aging_commands.pyc (simulation.zip)
    ('server_commands.aging_commands', 'advance_to_next_age', 'method'),
    ('server_commands.aging_commands', 'sims.age_up', 'command'),
    ('server_commands.aging_commands', 'reverse_to_previous_age', 'method'),
    ('server_commands.aging_commands', 'sims.age_down', 'command'),
    ('server_commands.aging_commands', 'add_age_progress_percentage', 'method'),
    ('server_commands.aging_commands', 'sims.age_add_progress_percentage', 'command'),
    ('server_commands.aging_commands', 'set_age_progress_percentage', 'method'),
    ('server_commands.aging_commands', 'sims.set_age_progress_percentage', 'command'),

    # sims/occult/occult_commands.pyc (simulation.zip)
    ('sims.occult.occult_commands', 'add_occult_type', 'method'),
    ('sims.occult.occult_commands', 'occult.add_occult', 'command'),
    ('sims.occult.occult_commands', 'remove_occult_type', 'method'),
    ('sims.occult.occult_commands', 'occult.remove_occult', 'command'),
    ('sims.occult.occult_commands', 'switch_to_occult_type', 'method'),
    ('sims.occult.occult_commands', 'occult.switch_to_occult', 'command'),

    # sims/occult/occult_enums.pyc (simulation.zip)
    ('sims.occult.occult_enums', 'OccultType', 'class'),
    ('sims.occult.occult_enums', 'OccultType.HUMAN', 'member', 1),
    ('sims.occult.occult_enums', 'OccultType.ALIEN', 'member', 2),
    ('sims.occult.occult_enums', 'OccultType.VAMPIRE', 'member', 4),
    ('sims.occult.occult_enums', 'OccultType.MERMAID', 'member', 8),
    ('sims.occult.occult_enums', 'OccultType.WITCH', 'member', 16),
    ('sims.occult.occult_enums', 'OccultType.WEREWOLF', 'member', 32),
    ('sims.occult.occult_enums', 'OccultType.FAIRY', 'member', 64),

    # server_commands/pregnancy_commands.pyc (simulation.zip)
    ('server_commands.pregnancy_commands', 'pregnancy_start', 'method'),
    ('server_commands.pregnancy_commands', 'pregnancy.start', 'command'),
    ('server_commands.pregnancy_commands', 'pregnancy_clear', 'method'),
    ('server_commands.pregnancy_commands', 'pregnancy.clear', 'command'),

    # server_commands/clock_commands.pyc (simulation.zip)
    ('server_commands.clock_commands', 'set_speed', 'method'),
    ('server_commands.clock_commands', 'clock.setspeed', 'command'),
    ('server_commands.clock_commands', 'set_anim_speed', 'method'),
    ('server_commands.clock_commands', 'clock.setanimspeed', 'command'),
    ('server_commands.clock_commands', 'set_game_time', 'method'),
    ('server_commands.clock_commands', 'clock.setgametime', 'command'),

    # server_commands/autonomy_commands.pyc (simulation.zip)
    ('server_commands.autonomy_commands', 'global_autonomy_state', 'method'),
    ('server_commands.autonomy_commands', 'autonomy.global', 'command'),

    # server_commands/relationship_commands.pyc (simulation.zip)
    ('server_commands.relationship_commands', 'set_score', 'method'),
    ('server_commands.relationship_commands', 'relationship.set_score', 'command'),
    ('server_commands.relationship_commands', 'add_bit', 'method'),
    ('server_commands.relationship_commands', 'relationship.add_bit', 'command'),
    ('server_commands.relationship_commands', 'remove_bit', 'method'),
    ('server_commands.relationship_commands', 'relationship.remove_bit', 'command'),

    # sims/sim_info_manager.pyc (simulation.zip) - pure Python, not a command
    ('sims.sim_info_manager', 'SimInfoManager.get_sim_info_by_name', 'method'),

    # sims/household.pyc (simulation.zip)
    ('sims.household', 'Household.__iter__', 'method'),
    ('sims.household', 'Household.__len__', 'method'),

    # services/__init__.pyc (simulation.zip) - re-cited from research/game_api.md §3, re-verified this
    # session against this build's own .pyc rather than trusted from that prior pass
    ('services', 'sim_info_manager', 'function'),
    ('services', 'active_sim_info', 'function'),
    ('services', 'get_active_sim', 'function'),
    ('services', 'active_household', 'function'),
    ('services', 'active_household_id', 'function'),
    ('services', 'household_manager', 'function'),

    # sims4/commands.pyc (core.zip) - re-cited from commands.py's (BP1) own manifest row; the same
    # (module, path) is fine to cite twice per this package's own __init__.py docstring
    ('sims4.commands', 'execute', 'function'),

    # ui/ui_dialog.pyc (simulation.zip) - re-cited from bp2_menukit.py's manifest for
    # household/inventory.py's own generic OK/Cancel confirmation (same verified construction, not
    # independently re-disassembled - see that file's docstring)
    ('ui.ui_dialog', 'UiDialogOkCancel', 'class'),
    ('ui.ui_dialog', 'ButtonType.DIALOG_RESPONSE_OK', 'member', 10001),
]

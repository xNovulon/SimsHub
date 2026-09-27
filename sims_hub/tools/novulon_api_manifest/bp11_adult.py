"""EA names BP11 (`ingame/novulon/adult/`) cites, checked THIS session against this machine's real
game zips with `sims_hub/tools/pyc37.py "E:/The Sims 4/Data/Simulation/Gameplay/{simulation,
core}.zip" <module>.pyc [name]` - not taken on trust from `research/game_api.md`, even though that
file already gave the same Age/Species values, because `gate.py`'s age/species predicate is the
single highest-compliance-risk piece of the whole mod (SPEC.md Sec 16 Tier 4's own words) and
deserves its own from-scratch check, not a re-citation.

Rows below, and how each was checked:
  * `sims.sim_info_types` (simulation.zip) - `Age`/`Species` are built by ordinary class-body
    `STORE_NAME`s (a `TunableEnumFlags`-style enum, not a `def`), so `pyc37.py`'s named-function mode
    (`python pyc37.py <zip> sims/sim_info_types.pyc Age`) was used to disassemble each class body
    directly and read every `LOAD_CONST <int>; STORE_NAME <NAME>` pair by hand - not the `--outline`
    mode, which only lists nested `def`s/classes, not their own bodies' assignments. Every value below
    matches `game_api.md` Sec.3 exactly for this installed build: `Age` bit flags BABY=1/TODDLER=2/
    CHILD=4/TEEN=8/YOUNGADULT=16/ADULT=32/ELDER=64/INFANT=128; `Species` HUMAN=1/DOG=2/CAT=3/FOX=5/
    HORSE=6 (INVALID=0, gap at 4 confirmed - no member at all, matching `gaps.md`'s "no Rabbit"
    finding for the same enum family). `gate.py` hardcodes these as plain ints (same convention
    `inject.py` already uses for `NOVULON_INTERACTION_ID`) rather than importing the enum module at
    runtime, so its predicate stays pure Python - importable/testable with no game and no Mods folder.
  * `server_commands.sim_commands` (simulation.zip) - `'sims.reset_all'` is a literal string constant
    in this module (`--strings` mode; also cross-checked with `--outline`'s
    `reset_all_sims(_connection)` at line 1057, the handler this command name registers). Disassembled
    the handler body directly this session (not just confirming the name exists): it calls
    `services.sim_info_manager().instanced_sims_gen(allow_hidden_flags=ALL_HIDDEN_REASONS)` then
    `services.get_reset_and_delete_service().trigger_batch_reset(sims)` - i.e. it resets every
    currently INSTANCED Sim (the ones loaded around the active lot right now), never the whole save.
    This is `panic.py`'s entire verification for why `sims.reset_all` is the right, already-scoped
    command for "ends active adult interactions on the lot" (SPEC.md Sec.11 V1 row 3) - not a guess
    at what the command does, a read of its actual body.
  * `sims4.commands` (core.zip) - `execute(command_line, _connection)` at line 145, matching
    `game_api.md` Sec.6's own citation; re-confirmed here since `panic.py` is the first Novulon file to
    call `execute` for a var-string command rather than `sims4.commands.Command`'s decorator (already
    covered by `bp1_bp3_core_inject.py`'s manifest).

What is NOT in this file, and why: every WickedWhims setting name/accessor function `adult/bridge.py`
calls (`get_sex_setting`/`set_sex_setting`, `get_nudity_setting`/`set_nudity_setting`,
`get_relationship_setting`/`set_relationship_setting`, and every individual setting-key string such as
`'autonomy_switch'`/`'pregnancy_menstrual_cycle'`) is deliberately left OUT of this shared,
game-zip-checked manifest. `novulon_api_check.py` (BP16) resolves every row here against THIS
installed game's own `base.zip`/`core.zip`/`simulation.zip` - WickedWhims is a third-party mod, not
EA code, and lives in an entirely different file
(`Mods\\scripts\\TURBODRIVER_WickedWhims_Scripts.ts4script`) that the shared checker never opens;
adding third-party rows here would make the checker report them "missing" against the game's own
zips, which is a false negative, not a real gap. `bridge.py`'s own module docstring carries the full
citation instead (exact `pyc37.py` invocations against the owner's actually-installed WickedWhims
copy, run this session, not merely carried from `research/adult_wants.md`'s prior pass) - the correct
place for a third-party citation, matching how `bp13_package_build.py`'s manifest already keeps its
own non-`.pyc`-checkable citations (DBPF resource-type constants, tuning XML field names) in its own
docstring rather than in a row here.

Game build note (matching every other manifest file in this package): `novulon_api_check.py`'s
`game_build_version()` reads `Delta\\<pack>\\Version.ini`'s `packversion`, `1.126.73.1030` on this
machine - independently re-read this session (`Delta/EP01/Version.ini`), matching every sibling
manifest file's own `CHECKED_AGAINST`.
"""

CHECKED_AGAINST = '1.126.73.1030'

ROWS = [
    # sims/sim_info_types.pyc (simulation.zip) - Age is a TunableEnumFlags-style bitflag enum; class
    # body STORE_NAMEs read directly, not `--outline` (see module docstring).
    ('sims.sim_info_types', 'Age', 'class'),
    ('sims.sim_info_types', 'Age.BABY', 'member', 1),
    ('sims.sim_info_types', 'Age.TODDLER', 'member', 2),
    ('sims.sim_info_types', 'Age.CHILD', 'member', 4),
    ('sims.sim_info_types', 'Age.TEEN', 'member', 8),
    ('sims.sim_info_types', 'Age.YOUNGADULT', 'member', 16),
    ('sims.sim_info_types', 'Age.ADULT', 'member', 32),
    ('sims.sim_info_types', 'Age.ELDER', 'member', 64),
    ('sims.sim_info_types', 'Age.INFANT', 'member', 128),
    ('sims.sim_info_types', 'Species', 'class'),
    ('sims.sim_info_types', 'Species.INVALID', 'member', 0),
    ('sims.sim_info_types', 'Species.HUMAN', 'member', 1),
    ('sims.sim_info_types', 'Species.DOG', 'member', 2),
    ('sims.sim_info_types', 'Species.CAT', 'member', 3),
    ('sims.sim_info_types', 'Species.FOX', 'member', 5),
    ('sims.sim_info_types', 'Species.HORSE', 'member', 6),

    # server_commands/sim_commands.pyc (simulation.zip) - the panic action's reset command; body
    # disassembled directly this session, see module docstring for what it actually does.
    ('server_commands.sim_commands', 'sims.reset_all', 'command'),

    # sims4/commands.pyc (core.zip) - already used live by core (bp1_bp3_core_inject.py's own
    # manifest covers Command/CommandType.Live/CheatOutput); `execute` is the one new name this
    # package adds, for panic.py's var-string command call.
    ('sims4.commands', 'execute', 'function'),
]

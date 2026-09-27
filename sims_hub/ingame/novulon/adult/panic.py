"""adult/panic.py - the one-click "Stop Everything" panic action (SPEC.md Sec.11 V1 row 3). Two
verified, independent pieces, run one after another (a failure in one never blocks the other):

  1. `sims4.commands.execute('sims.reset_all', connection)` - a vanilla, vanilla-verified command
     (`server_commands/sim_commands.pyc`, this session's own `pyc37.py` disassembly - see
     `tools/novulon_api_manifest/bp11_adult.py`). Its handler, `reset_all_sims(_connection)`, was
     disassembled directly, not just confirmed to exist: it calls
     `services.sim_info_manager().instanced_sims_gen(allow_hidden_flags=ALL_HIDDEN_REASONS)` then
     `services.get_reset_and_delete_service().trigger_batch_reset(sims)` - i.e. every currently
     INSTANCED Sim (the ones loaded around the active lot right now, never the whole save's Sims).
     That is exactly SPEC.md's "ends active adult interactions on the lot" scope, read off the
     command's own body rather than assumed from its name.
  2. Turn off every known WickedWhims sex-autonomy switch right now (`bridge.set_all_sex_autonomy`),
     so nothing new starts back up immediately after the reset.

Cut for V1, and why (SPEC.md Sec.18's "verify or cut" standard - never guessed at):
  * "restores modesty" - no research pass (`adult_wants.md` Sec.2/Sec.4) found a verified
    WickedWhims accessor/command for "force everyone clothed right now"; nudity is per-Sim runtime
    state, not one of the three settings-accessor surfaces this mod is scoped to touch.
  * A TIMED "cancels pending autonomy for N minutes" - no verified scheduling primitive exists
    anywhere in this codebase yet (the same open item SPEC.md Sec.18 already flags for
    `sims/delete.py`'s own poll). V1 ships an immediate, indefinite autonomy-off instead, paired with
    an explicit `resume_autonomy` the player triggers themselves when ready - stricter than a timer
    that might silently re-enable autonomy while the player still wants it off, never looser.
  * Resetting only the Sims actually mid-interaction, rather than every instanced Sim - no verified
    command exists to cancel a single Sim's current interaction without a full reset; `sims.reset_all`
    is the one command in this research pass whose exact scope (this lot's currently-loaded Sims) was
    independently disassembled and confirmed, and a panic button that is occasionally more thorough
    than strictly necessary is a safer trade than one that sometimes silently does nothing.
"""
from . import bridge
from .. import common

RESET_COMMAND = 'sims.reset_all'


def _run_reset(connection):
    import sims4.commands
    sims4.commands.execute(RESET_COMMAND, connection)
    return True


def stop_everything(connection=None):
    """Reset every currently-instanced Sim (ends whatever they're doing, adult interaction or not)
    and turn off every known WickedWhims sex-autonomy switch. Returns True if the reset command was
    at least issued - never raises, and the autonomy-off step still runs even if the reset failed."""
    ok = common.guarded('adult.panic: reset', _run_reset, connection) is not None
    common.guarded('adult.panic: autonomy off', bridge.set_all_sex_autonomy, False)
    return ok


def resume_autonomy(connection=None):
    """Turn every known WickedWhims sex-autonomy switch back on - the explicit, player-driven
    counterpart to `stop_everything`'s autonomy-off step (see module docstring: no timed auto-resume
    in V1). Returns True if at least one switch was written."""
    return bool(common.guarded('adult.panic: autonomy on', bridge.set_all_sex_autonomy, True))

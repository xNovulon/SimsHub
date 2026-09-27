"""Relationships (SPEC.md §9.4, build package BP10). Owns every `relationship.*` command the mod calls -
per SPEC.md §1's resolution of the `engineering.md` ownership ambiguity, both the Gameplay tile's
"Relationships" row and (eventually) a Sim Card quick action call into this file, never into
`gameplay/menu.py` directly.

No Sim Browser exists in this package (that's BP4) - the *other* Sim in a relationship action is resolved
by typed full name via `services.sim_info_manager().get_sim_info_by_name(first, last)` (verified pure
Python, `sims/sim_info_manager.pyc:707`), the same mechanism `gameplay/menu.py`'s pregnancy partner picker
uses. The *first* Sim is always the active Sim - Relationships here is reached from the Gameplay tile,
which (like Cheats) acts on the Sim you're already playing, never a separately-selected one.

Command literals, all checked this session against this build's own `server_commands/relationship_commands.pyc`
with `sims_hub/tools/pyc37.py` (see `tools/novulon_api_manifest/bp8_bp9_bp10.py` for the full citation):
  * `relationship.set_score <source> <target> <score> <track_type>` -> `set_score(source_sim_id,
    target_sim_id, score, track_type, bidirectional, _connection)` (line 492). **Verified finding**:
    `bidirectional` is accepted but never read anywhere in the function body (only `track_type` reaches
    `relationship_tracker.set_relationship_score`) - left off the command line entirely rather than
    guessing what value would matter.
  * `relationship.add_bit <source> <target> <bit>` -> `add_bit(source_sim_id, target_sim_id, rel_bit,
    _connection)` (line 579).
  * `relationship.remove_bit <source> <target> <bit>` -> `remove_bit(...)` (line 595).
`track_type`/`rel_bit` are typed, free-text tuning names (e.g. `LTR_Friendship_Main`,
`LTR_Romance_Main`) - this mod carries no copy of the relationship-track/bit catalog, matching the same
typed-field policy `gameplay/menu.py`'s docstring explains for skills/traits/careers.
"""
from .. import common
from ..menukit import Row, Page, search as _search, notify as _notify

BREADCRUMB = ('Gameplay', 'Relationships')


def _active_sim_id(connection):
    try:
        import services
        info = services.active_sim_info()
        return info.id if info is not None else None
    except Exception:
        return None


def _resolve_sim_by_name(full_text):
    try:
        import services
    except Exception:
        return None
    parts = str(full_text).strip().rsplit(' ', 1)
    first, last = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], '')
    try:
        return services.sim_info_manager().get_sim_info_by_name(first, last)
    except Exception:
        return None


def _exec(connection, command_line, ok_text):
    try:
        import sims4.commands
    except Exception:
        _notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False
    common.guarded('novulon.relationships: ' + command_line.split(' ', 1)[0],
                    sims4.commands.execute, command_line, connection)
    _notify('Done.', ok_text)
    return True


def _ask_text(connection, title, prompt, on_result):
    _search.open_search_box(connection, None, on_result, title=title, text=prompt)


def _ask_target(connection, on_target):
    """Types a full name, resolves it to a sim_info via the verified name lookup, reports a clear failure
    if nothing matches - shared by all three rows below."""
    def _got(name):
        if not name:
            return
        target = _resolve_sim_by_name(name)
        if target is None:
            _notify('Nothing changed.', 'No Sim found with that name.', urgent=True)
            return
        on_target(target)
    _ask_text(connection, 'Other Sim', "Type the other Sim's full name (First Last).", _got)


def _set_score_row(connection, selected_ids=None):
    source_id = _active_sim_id(connection)
    if source_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None

    def _with_target(target):
        def _build(values):
            score, track = values
            return 'relationship.set_score %s %s %s %s' % (source_id, target.id, score, track)
        _prompt_chain_local(connection,
                            [('Score', 'Type a score, -100 to 100.'),
                             ('Track', 'Type the track name, e.g. LTR_Friendship_Main.')],
                            _build, 'Relationship score updated.')
    _ask_target(connection, _with_target)
    return None


def _add_bit_row(connection, selected_ids=None):
    source_id = _active_sim_id(connection)
    if source_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None

    def _with_target(target):
        def _got(bit):
            if not bit:
                return
            _exec(connection, 'relationship.add_bit %s %s %s' % (source_id, target.id, bit.strip()),
                  'Relationship bit added.')
        _ask_text(connection, 'Relationship Bit', 'Type the bit name.', _got)
    _ask_target(connection, _with_target)
    return None


def _remove_bit_row(connection, selected_ids=None):
    source_id = _active_sim_id(connection)
    if source_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None

    def _with_target(target):
        def _got(bit):
            if not bit:
                return
            _exec(connection, 'relationship.remove_bit %s %s %s' % (source_id, target.id, bit.strip()),
                  'Relationship bit removed.')
        _ask_text(connection, 'Relationship Bit', 'Type the bit name.', _got)
    _ask_target(connection, _with_target)
    return None


def _prompt_chain_local(connection, fields, build_command, ok_text):
    values = []

    def _next(i):
        if i >= len(fields):
            cmd = build_command(values)
            if cmd:
                _exec(connection, cmd, ok_text)
            return
        title, prompt = fields[i]

        def _got(text):
            if not text:
                return
            values.append(str(text).strip())
            _next(i + 1)
        _ask_text(connection, title, prompt, _got)
    _next(0)


def relationships_page(connection, selected_ids=None):
    return Page('Relationships', [
        Row('novulon.relationships.set_score', 'Set Relationship Score…', on_activate=_set_score_row),
        Row('novulon.relationships.add_bit', 'Add Relationship Bit…', on_activate=_add_bit_row),
        Row('novulon.relationships.remove_bit', 'Remove Relationship Bit…', on_activate=_remove_bit_row),
    ], breadcrumb=BREADCRUMB)


def all_actions():
    return [
        ('novulon.relationships.set_score', _set_score_row),
        ('novulon.relationships.add_bit', _add_bit_row),
        ('novulon.relationships.remove_bit', _remove_bit_row),
    ]

"""Household & Money (SPEC.md `household/` §8, build package BP8).

Root tile page plus the two verified funds actions and the one verified inventory action
(`inventory.py` - Sell All/Transfer Selected are cut there, documented, not built here).

Command literals below, each checked this session against THIS installed game build's own
`server_commands/*.pyc` with `sims_hub/tools/pyc37.py` (outline, then a targeted disassembly of the
handler function itself - not taken on trust from prior research) - see
`tools/novulon_api_manifest/bp8_bp9_bp10.py` for the full citation list:

  * `households.modify_funds <amount> [household_id] [reason]` -> `modify_household_funds(amount,
    household_id, reason, _connection)` (`household_commands.pyc:68`). **Real, verified finding**: this is
    an ADD/REMOVE **delta**, not a "set to X" - the body branches `if amount > 0:
    household.funds.add(amount, reason)` else `household.funds.try_remove(-amount, reason)`. SPEC.md §8
    calls this row "Set Household Funds"; the UI text below says "Add or remove" instead, matching what
    the command actually does rather than the spec's paraphrase. `household_id=0` resolves to "the
    household of the client that issued this command" (`services.client_manager().get(_connection)
    .household`) - exactly the active household from the Novulon computer's own connection, so it is
    passed literally rather than re-resolving `active_household_id()` ourselves.
  * `money <amount> [sim]` -> `set_money(amount, sim, _connection)` (`sim_commands.pyc:1347`). Verified
    the opposite of the above: it reads `sim.family_funds.money`, computes `amount - current_amount`, and
    applies that delta - i.e. `money` **does** set an absolute value, matching SPEC.md §8's "Set Sim's
    Personal Funds". Omitting `sim` resolves through the same `get_optional_target` helper `clear_skill`/
    `add_buff`/etc. all share; this file instead always passes the active Sim's id explicitly (see
    `_active_sim_id`) rather than relying on that default-resolution behavior, since this package's own
    policy (see `gameplay/menu.py`'s docstring) is to never guess at an optional-argument's default when
    an id is easy to resolve and pass directly.
"""
from .. import common
from ..menukit import Row, Page, search as _search, notify as _notify
from . import inventory as _inventory

BREADCRUMB = ('Household',)


# ------------------------------------------------------------------ small shared helpers
def _active_sim_id(connection):
    try:
        import services
        info = services.active_sim_info()
        return info.id if info is not None else None
    except Exception:
        return None


def _active_household(connection):
    try:
        import services
        return services.active_household()
    except Exception:
        return None


def _exec(connection, command_line, ok_text):
    try:
        import sims4.commands
    except Exception:
        _notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False
    common.guarded('novulon.household: ' + command_line.split(' ', 1)[0],
                    sims4.commands.execute, command_line, connection)
    _notify('Done.', ok_text)
    return True


def _ask_text(connection, title, prompt, on_result):
    _search.open_search_box(connection, None, on_result, title=title, text=prompt)


# ------------------------------------------------------------------ Household Funds
def set_household_funds(connection, amount):
    """Add or remove funds from the connection's own household. `amount` is a signed int (a plain string
    like '-500' is fine too - `sims4.commands.execute` parses it same as a typed cheat)."""
    return _exec(connection, 'households.modify_funds %s 0' % amount, 'Household funds updated.')


def _household_funds_row(connection, selected_ids=None):
    def _got(text):
        if not text:
            return
        try:
            amount = int(str(text).strip())
        except ValueError:
            _notify('Nothing changed.', 'Type a whole number, e.g. 1000 or -500.', urgent=True)
            return
        set_household_funds(connection, amount)
    _ask_text(connection, 'Household Funds', 'Type an amount. Use a negative number to remove funds.', _got)
    return None


# ------------------------------------------------------------------ Personal Funds (active Sim)
def set_personal_funds(connection, sim_id, amount):
    """Sets `sim_id`'s money to exactly `amount` (an absolute set, per `money`'s verified body)."""
    return _exec(connection, 'money %s %s' % (amount, sim_id), "Sim's funds updated.")


def _personal_funds_row(connection, selected_ids=None):
    sim_id = _active_sim_id(connection)
    if sim_id is None:
        _notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None

    def _got(text):
        if not text:
            return
        try:
            amount = int(str(text).strip())
        except ValueError:
            _notify('Nothing changed.', 'Type a whole number, e.g. 5000.', urgent=True)
            return
        set_personal_funds(connection, sim_id, amount)
    _ask_text(connection, 'Personal Funds', "Type the active Sim's new funds.", _got)
    return None


# ------------------------------------------------------------------ Purge All Inventory
def _purge_inventory_row(connection, selected_ids=None):
    household = _active_household(connection)
    if household is None:
        _notify('Nothing changed.', 'No active household.', urgent=True)
        return None
    members = _inventory.instanced_members(household)
    if not members:
        _notify('Nothing changed.', 'No Sims from this household are on the lot right now.')
        return None

    def _confirmed(conn):
        n = _inventory.purge_instanced_members(conn, household)
        _notify('Done.', 'Purged inventory for %d Sim(s) on the lot.' % n)

    _inventory.confirm_ok_cancel(
        connection, 'Purge All Inventory?',
        "This empties inventory for every Sim from this household who's on the lot right now. "
        "This can't be undone.",
        _confirmed)
    return None


# ------------------------------------------------------------------ root page
def household_root(connection, selected_ids=None):
    return Page('Household', [
        Row('novulon.household.funds', 'Household Funds',
            description='Add or remove funds (negative to remove).',
            on_activate=_household_funds_row),
        Row('novulon.household.personal_funds', 'Personal Funds',
            description="Set the active Sim's funds.",
            on_activate=_personal_funds_row),
        Row('novulon.household.purge_inventory', 'Purge All Inventory',
            description="Empties inventory for Sims on the lot. Can't be undone.",
            on_activate=_purge_inventory_row),
    ], breadcrumb=BREADCRUMB)

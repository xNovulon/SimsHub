"""Household inventory bulk ops, and a small generic OK/Cancel confirmation (SPEC.md `household/` §8).

**Verify-or-cut, per the build override**: of the three inventory ops SPEC.md §8 lists, only **Purge All
Inventory** has a verified, headless (no open UI needed) command literal, `inventory.purge` ->
`purge_sim_inventory(opt_target, _connection)` (`server_commands/inventory_commands.pyc:109`, this
session's own `pyc37.py --outline`/targeted disassembly against
`E:/The Sims 4/Data/Simulation/Gameplay/simulation.zip`): it resolves `opt_target` through
`get_optional_target` (same helper `money`/`clear_skill`/etc. use) then calls
`target.inventory_component.purge_inventory()` - a plain per-Sim/per-object purge, safe to call once per
currently-**instanced** household member.

**Cut to V1.1** (documented here, not guessed at):
  * **Sell All Inventory** - no plain command exists. `inventory.sell_picker_response_by_ids` requires an
    already-open sell-picker dialog id; `inventory.sim_inventory_sell_multiple` (`sim_inventory_sell_multiple`,
    line 467) takes a `UI_pb2.InventorySellRequest` protobuf `msg` and, once parsed, reimplements the whole
    sell computation itself (`sell_price_modifier`, `add_currency_amount(currency_type=proto.currency_type,
    ...)`, `get_reset_and_delete_service().trigger_batch_destroy(destroy_objs)`) - a real, disassembled
    mechanism, but with an unverified `currency_type` default and no simple wrapper a mod can call
    headlessly. Reimplementing the sell math ourselves, with no live game to check `add_currency_amount`'s
    signature or the correct currency-type constant, is exactly the kind of guess the owner's hard rules
    forbid ("never ship a guess"). Left out of the menu.
  * **Transfer Selected** - no per-item move-between-Sims-inventory command was found anywhere in
    `server_commands/inventory_commands.pyc` or `objects/components/sim_inventory_component.pyc`. The
    closest hit, `SimInventoryComponent.push_items_to_household_inventory(self)` (line 150), moves an
    entire inventory into a shared household bin - not a selective per-item transfer - and its exact save
    semantics were not traced. Left out of the menu; worth a closer look for a v1.1 pass.

**Purge's own real scope, documented honestly**: `purge_sim_inventory` needs `target.inventory_component`,
which only exists on an **instanced** (spawned) game object. A Sim who is not currently on the loaded lot
has no live `inventory_component` to purge through this call. So "Purge All Inventory" here purges every
*currently instanced* Sim in the household - not every Sim who has ever been in it - and the confirmation
text says exactly that, rather than implying a stronger guarantee than the verified API gives.
"""
from .. import common

CAP = 10


def _display_name(sim_info):
    name = getattr(sim_info, 'full_name', None)
    if name:
        return name
    first = getattr(sim_info, 'first_name', '') or ''
    last = getattr(sim_info, 'last_name', '') or ''
    return (first + ' ' + last).strip() or ('Sim %s' % getattr(sim_info, 'id', '?'))


def instanced_members(household):
    """Every sim_info in `household` (any iterable of sim_infos) that `is_instanced()` right now. Pure
    Python except for the `is_instanced()` call itself - safe to unit test with plain fake sim_infos."""
    out = []
    for sim_info in household:
        try:
            if sim_info.is_instanced():
                out.append(sim_info)
        except Exception:
            continue
    return out


def purge_instanced_members(connection, household):
    """Runs the verified `inventory.purge <sim_id>` command once per currently-instanced member of
    `household`. Returns the count that ran without raising (not whether each one truly had items to
    purge - `sims4.commands.execute` always returns `None`, on success or failure alike per its own
    disassembled body, so a return-value check can never tell the two apart - only an exception can, which
    is what this counts). One bad id never stops the rest: caught and logged per-Sim, never re-raised."""
    import sims4.commands
    members = instanced_members(household)
    done = 0
    for sim_info in members:
        try:
            sims4.commands.execute('inventory.purge %s' % sim_info.id, connection)
            done += 1
        except Exception:
            common.log_exception('novulon.household.purge_inventory: sim %r'
                                  % (getattr(sim_info, 'id', None),))
    return done


def confirm_ok_cancel(connection, title, text, on_confirm, connection_owner=None):
    """A plain OK/Cancel confirmation with fixed text (not a named Sim list - `menukit.confirm_delete` is
    for deleting Sims specifically, SPEC.md §8 only asks for the same OkCancel safety posture, not a named
    list). Built from the exact, already-verified `UiDialogOkCancel` construction menukit's own
    `confirm.py` documents and uses (`ui.ui_dialog.UiDialogOkCancel`/`ButtonType`,
    `sims4.localization.LocalizationHelperTuning.get_raw_text`) - re-cited in this package's own manifest
    row rather than re-verified from scratch, since citing the same (module, path) from a second file is
    not a conflict (`tools/novulon_api_manifest/__init__.py`'s own docstring). Degrades to a failure toast
    on any mismatch, never raises. Returns True if the dialog was shown."""
    try:
        from ..menukit import notify as _notify
    except Exception:
        _notify = None

    def _fail():
        if _notify is not None:
            _notify('Nothing changed.', 'Something went wrong.', urgent=True)

    try:
        from ui.ui_dialog import UiDialogOkCancel, ButtonType
        from sims4.localization import LocalizationHelperTuning as L
    except Exception:
        _fail()
        return False

    def _on_response(dialog):
        try:
            if dialog.response == ButtonType.DIALOG_RESPONSE_OK and on_confirm is not None:
                on_confirm(connection)
        except Exception:
            _fail()

    try:
        dlg = UiDialogOkCancel.TunableFactory().default(
            connection_owner,
            title=(lambda *_a, **_k: L.get_raw_text(title)),
            text=(lambda *_a, **_k: L.get_raw_text(text)),
            text_ok=(lambda *_a, **_k: L.get_raw_text('Continue')),
            text_cancel=(lambda *_a, **_k: L.get_raw_text('Cancel')),
            include_cancel_response=True)
        dlg.show_dialog(on_response=_on_response)
        return True
    except Exception:
        _fail()
        return False

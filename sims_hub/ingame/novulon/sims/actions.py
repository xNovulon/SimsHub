"""Per-Sim action rows (SPEC.md `sims/actions.py` Sec 5.5, build package BP5).

PUBLIC HOOK THIS FILE IMPLEMENTS: `sims/browser.py` (BP4) calls a single sim (from the Sim Card) or a
whole tray of sims (from "Choose Action") through `commands.do('novulon.sims.selection_action',
connection, *sim_id_strings)` - see `browser.py`'s own docstring ("hands the whole tray off to
sims/actions.py ... via a stable action id this file only ever CALLS through commands.do, never
registers"). `open_selection_action` below is that action's body: exactly one id -> the single-Sim
action list (this section's main content); two or more ids -> the bulk action chooser. This is the
*only* coordination point with the browser package - nothing else here imports `sims.browser` or
`sims.query`, and nothing in this file builds a `UiSimPicker`/`SimPickerRow` (that stays BP4's job,
per `menukit/__init__.py`'s own note that only the browser package builds real Sim-picker dialogs).

THE "BOUND ROW" PATTERN (how one Row can call a shared, per-action-id registered function with a
Sim-specific argument). `menukit`'s own contract is that every `Row.on_activate` is called by
`render.py` as `on_activate(connection)` - no extra arguments - while the SAME logical action is also
a `novulon.do <action_id> [args]` console command, which needs a way to take a sim id as a typed
argument. So every action function here has signature `fn(connection, sim_id, *extra)` and is
registered ONCE, at import time, under one stable id (`commands.add('sims.actions.reset', reset_sim)`);
a Page built for a SPECIFIC Sim then supplies a thin `_bound(fn, sim_id)` closure as that row's
`on_activate`, which just calls the exact same registered function with the id already filled in. Many
rows across many different Sims' action pages legitimately share one `Row.id` string this way -
`menukit`'s dispatch maps a picked row back to its Python object by identity, never by that string
(`render.py`'s own `by_identity[id(built)] = row` - confirmed by reading its source before relying on
this), so re-using one id across many closures is exactly the supported shape, not a workaround.

SCOPE DECISIONS MADE THIS SESSION (verify-or-cut, all checked with `tools/pyc37.py` against this
machine's own `E:/The Sims 4` install - see `tools/novulon_api_manifest/bp5_bp6_sims_actions_delete.py`
for the full citation list):
  * **Add to Household** - previously flagged unverified (SPEC.md Sec 5.5/18: only the *removal*
    direction of `SimInfo.assign_to_household` had been disassembled). This session found the real,
    single vanilla command for the add direction: `sims.add_to_family <sim_id> [<target_sim_id>]`
    (`server_commands/sim_commands.pyc:add_to_family`, line 345) -> `household_manager().
    switch_sim_household(...)`; with no second id it defaults to the ACTIVE household, which is
    exactly what an "Add to Household" row wants. Ships as one row, no household picker needed.
  * **Make Playable / Make NPC** - previously flagged unverified for the same reason. This session
    found the real mechanism: "playable" is a client-side `selectable_sims` set, not a household-
    membership flag (`SimInfo.is_selectable`, `sims/sim_info.pyc:812`, checks `self in
    client.selectable_sims`) - toggled with `Client.add_selectable_sim_by_id`/
    `remove_selectable_sim_by_id` (`server/client.pyc:408/421`, both fully disassembled this session).
    `remove_selectable_sim_by_id` itself refuses (returns `False`) when it would drop a household to
    zero selectable Sims - a real, built-in safety rail this file relies on rather than duplicating.
    Making a non-active-household Sim playable first moves them into the active household via
    `sims.add_to_family`, the same verified command as above.
  * **Teleport to Me** - `gameplay/cheats.py` (BP9, already shipped in this tree) explicitly CUT this
    row, citing "no research pass verified which attributes expose [a live Sim's position] cleanly."
    This session verified it directly: `Sim.level` is a real property (`sims/sim.pyc:681`, returns
    `self.location.routing_surface.secondary_id`), and `.position`/`.location` are read as plain
    attributes throughout the engine's own code (cross-checked via `objects/doors/door_commands.pyc`'s
    `door.position` read and `server_commands/object_commands.pyc:set_position`'s `obj.location.clone(
    translation=Vector3(...))` write) - the same base-object surface a `Sim` inherits. "Teleport to Me"
    reads the active Sim's live `.position`/`.level` and calls the already-verified
    `sims.teleport_instantly <x> <y> <z> <level> <sim_id> <rotation>` (`sim_commands.pyc:936`).
  * **Traits** - the one place this file builds a real search-over-live-data picker (SPEC.md Sec
    5.5's "search-based add/remove"), using `services.get_instance_manager(sims4.resources.
    Types.TRAIT).types` (the exact `InstanceManager.types` property BP1/BP3's `inject.py` already
    verified) filtered by class-name substring - not a bespoke picker widget, plain `menukit.Page` rows.
    Removing a trait lists the Sim's OWN currently-equipped traits (`sim_info.trait_tracker`, confirmed
    iterable this session from `Household.add_sim_info`'s own `for t in sim_info.trait_tracker`).
  * **Skills, Career, Needs, Pregnancy** - every other typed field (skill/career/buff name, a level or
    amount, a pregnancy partner's name) is collected as free text via `menukit.search.open_search_box`,
    chained one field at a time - the identical, independently-arrived-at convention `gameplay/menu.py`
    and `relationships/menu.py` (both already shipped in this tree) document for the same reason: this
    mod carries no copy of the trait/skill/career/buff catalog, so a typed name is the verified, honest
    interface, matching exactly what a player would type into the debug cheat console by hand. This
    file's own copies of `_exec`/`_ask_text`/`_prompt_chain` intentionally mirror those two files'
    shape for consistency, not shared code (no cross-package import exists between feature packages).
  * **`stats.set_commodity`** for "Set Individual Need": this session found `'stats.set_stat'` and
    `'stats.set_commodity'` registered as two aliases of the SAME function, `set_statisitic(stat_type,
    value, opt_sim, opt_target_type, _connection)` (`statistic_commands.pyc:173`) - a RAW value setter,
    not a 0-100 percentage (`stats.set_commodity_percent` is a different, later function in the same
    file). `gameplay/menu.py` (BP9) independently reached the identical conclusion (its own manifest
    pairs the same two citations) - cross-checked, not assumed. The menu prompt says "raw value", not
    "percent", so the UI text doesn't imply a scale the command doesn't use.
  * **Relationship...** - SPEC.md Sec 1.4 resolves relationship-command ownership to
    `relationships/actions.py` alone. That package shipped in this tree as `relationships/menu.py`
    (BP10) instead, and its three rows always act on the ACTIVE Sim (never a passed-in "source" id -
    its own docstring: "The *first* Sim is always the active Sim"). Rather than duplicating
    `relationship.set_score`/`add_bit` here (which SPEC explicitly reserves to that one file), this
    row delegates to `relationships.menu.relationships_page(connection)` as-is - honestly labelled
    "Relationship..." since that page's own dialogs already state whose relationship is being edited.
    From a non-active browsed Sim this acts on the ACTIVE Sim, not the browsed one; flagged here and in
    this package's build report, not silently papered over. `relationships/menu.py` also has a real,
    separate bug (`_notify.notify(...)` calling `.notify` on the imported `notify` FUNCTION itself,
    not a module - `menukit.notify` is a plain function, not a module with its own `.notify` attribute)
    that would raise `AttributeError` on every one of its three rows; not this package's file to fix,
    flagged via a background task instead of touched directly.
  * **Cut, not guessed**: `careers.add_gig` (needs an unclear `sim_filter` argument no research pass
    checked), Ghost/Servo/PlantSim occult chips (no verified detection mechanism, matches SPEC.md
    Sec 18/`gaps.md` Sec B.6), and a household picker for Add to Household (the active-household
    default the verified command already provides covers the common case; picking an arbitrary target
    household needs a household browser this package doesn't own).
"""
from . import delete
from .. import commands, common
from .. import menukit
from ..menukit import Row, Page

BREADCRUMB_ROOT = ('Sims',)

_OCCULT_TYPES = (
    ('VAMPIRE', 'Vampire'), ('WITCH', 'Spellcaster'), ('MERMAID', 'Mermaid'),
    ('ALIEN', 'Alien'), ('WEREWOLF', 'Werewolf'), ('FAIRY', 'Fairy'),
)


# ======================================================================== small shared helpers
def _to_int(text):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _sim_info(sim_id):
    """`services.sim_info_manager().get(int(sim_id))`, or None - never raises. Accepts a plain int
    (from a Row closure) or a typed string (from `novulon.do sims.actions.<id> <sim_id>`)."""
    sim_id = _to_int(sim_id)
    if sim_id is None:
        return None
    try:
        import services
    except Exception:
        return None
    mgr = common.guarded('novulon sims.actions: sim_info_manager()', services.sim_info_manager)
    if mgr is None:
        return None
    return common.guarded('novulon sims.actions: sim_info_manager().get', mgr.get, sim_id)


def _name(sim_info):
    full = getattr(sim_info, 'full_name', None)
    if full:
        return full
    first = getattr(sim_info, 'first_name', '') or ''
    last = getattr(sim_info, 'last_name', '') or ''
    return (first + ' ' + last).strip() or ('Sim %s' % getattr(sim_info, 'id', '?'))


def _sim_gone(connection):
    menukit.notify('Nothing changed.', 'That Sim is no longer available.', urgent=True)
    return None


def _sim_gone_page():
    return Page('Sim not found', [
        Row('sims.actions.gone', 'That Sim is no longer available.', disabled_text='Not available',
            on_activate=_noop),
    ], breadcrumb=BREADCRUMB_ROOT)


def _noop(connection, *args):
    return None


commands.add('sims.actions.gone', _noop)


def _exec(connection, command_line, ok_text):
    """`sims4.commands.execute(command_line, connection)`, guarded; notifies `ok_text` on completion.
    Matches `gameplay/menu.py`/`relationships/menu.py`'s own identical, independently-shipped shape."""
    try:
        import sims4.commands
    except Exception:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False
    common.guarded('novulon sims.actions: ' + command_line.split(' ', 1)[0],
                    sims4.commands.execute, command_line, connection)
    if ok_text:
        menukit.notify('Done.', ok_text)
    return True


def _client_cheat(connection, command_line):
    try:
        import sims4.commands
    except Exception:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False
    common.guarded('novulon sims.actions (client): ' + command_line.split(' ', 1)[0],
                    sims4.commands.client_cheat, command_line, connection)
    return True


def _ask_text(connection, title, prompt, on_result):
    menukit.search.open_search_box(connection, None, on_result, title=title, text=prompt)


def _prompt_chain(connection, fields, build_command, ok_text):
    """Collects one text value per (title, prompt) in `fields`, in order, each via `_ask_text` -
    there is no native multi-field dialog (`menukit/search.py`'s own docstring). An empty/cancelled
    answer at any step stops the chain silently. `build_command(values)` turns the collected strings
    into a full command line (or None to abort quietly)."""
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


def _bound(fn, *bound_args):
    """A `Row.on_activate` that calls the SAME registered action `fn` with `bound_args` (cast to str,
    matching how a console-typed argument would arrive) already filled in - see the module docstring's
    "bound row" section. `fn` itself must already be `commands.add()`-registered under some id."""
    args = tuple(str(a) for a in bound_args)

    def _on_activate(connection, selected_ids=None, _fn=fn, _args=args):
        return _fn(connection, *_args)
    return _on_activate


# ======================================================================== 1. Edit in CAS
def edit_in_cas(connection, sim_id):
    """`sims.exit2caswithhouseholdid <sim_id> <household_id>` via `client_cheat` - the exact call
    `server_commands/cas_commands.pyc:modify_in_cas_with_household_id` (line 90) makes, re-verified
    this session byte-for-byte; works across households (the target's OWN household_id, never the
    active one)."""
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _client_cheat(connection, 'sims.exit2caswithhouseholdid %s %s' % (info.id, info.household_id))
    return None


commands.add('sims.actions.edit_cas', edit_in_cas)


# ======================================================================== 2. Traits
def _trait_classes():
    try:
        import services
        import sims4.resources
    except Exception:
        return []
    mgr = common.guarded('novulon sims.actions: instance_manager(TRAIT)', services.get_instance_manager,
                          sims4.resources.Types.TRAIT)
    if mgr is None:
        return []
    classes = common.guarded('novulon sims.actions: trait types', lambda: list(mgr.types.values()))
    return classes or []


def _trait_name(cls):
    return getattr(cls, '__name__', None) or str(cls)


def open_traits_menu(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    rows = [
        Row('sims.actions.traits.add', 'Add Trait…', description='Search by name.',
            on_activate=_bound(_traits_add_open, sim_id)),
        Row('sims.actions.traits.remove', 'Remove Trait…', description='Pick from equipped traits.',
            on_activate=_bound(_traits_remove_open, sim_id)),
        Row('sims.actions.traits.clear_all', 'Clear All Traits',
            on_activate=_bound(clear_all_traits, sim_id)),
        Row('sims.actions.traits.clear_personality', 'Clear Personality Traits',
            on_activate=_bound(clear_personality_traits, sim_id)),
    ]
    return Page('Traits', rows, breadcrumb=('Sims', _name(info), 'Traits'))


commands.add('sims.actions.traits_menu', open_traits_menu)


def _traits_add_open(connection, sim_id):
    def _on_query(query):
        classes = _trait_classes()
        q = (query or '').strip().lower()
        matched = sorted((_trait_name(c) for c in classes if q and q in _trait_name(c).lower()))
        matched = matched[:menukit.paging.DEFAULT_PAGE_SIZE]
        if not matched:
            rows = [Row('sims.actions.traits.no_match', 'No traits matched - try a different search.',
                         disabled_text='No matches', on_activate=_noop)]
        else:
            rows = [Row('sims.actions.traits.equip_result', name,
                         on_activate=_bound(_traits_equip, sim_id, name)) for name in matched]
        page = Page('Add Trait', rows, breadcrumb=('Sims', 'Traits', 'Results'))
        menukit.show_page(connection, page, push=True)
    _ask_text(connection, 'Add Trait', 'Type part of a trait name.', _on_query)
    return None


commands.add('sims.actions.traits.add', _noop)


def _traits_equip(connection, sim_id, trait_name):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'traits.equip_trait %s %s' % (trait_name, info.id), 'Trait added.')
    return None


commands.add('sims.actions.traits.equip_result', _traits_equip)
commands.add('sims.actions.traits.no_match', _noop)


def _equipped_traits(sim_info):
    tracker = getattr(sim_info, 'trait_tracker', None)
    if tracker is None:
        return []
    try:
        return list(tracker)
    except Exception:
        return []


def _traits_remove_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    equipped = _equipped_traits(info)
    if not equipped:
        menukit.notify('No traits.', '%s has no traits to remove.' % _name(info))
        return None
    rows = [Row('sims.actions.traits.remove_result', _trait_name(cls),
                on_activate=_bound(_traits_remove, sim_id, _trait_name(cls))) for cls in equipped]
    page = Page('Remove Trait', rows, breadcrumb=('Sims', _name(info), 'Traits', 'Remove'))
    menukit.show_page(connection, page, push=True)
    return None


commands.add('sims.actions.traits.remove', _noop)


def _traits_remove(connection, sim_id, trait_name):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'traits.remove_trait %s %s' % (trait_name, info.id), 'Trait removed.')
    return None


commands.add('sims.actions.traits.remove_result', _traits_remove)


def clear_all_traits(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'traits.clear_traits %s' % info.id, 'All traits cleared.')
    return None


commands.add('sims.actions.traits.clear_all', clear_all_traits)


def clear_personality_traits(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'traits.clear_personality_traits %s' % info.id, 'Personality traits cleared.')
    return None


commands.add('sims.actions.traits.clear_personality', clear_personality_traits)


# ======================================================================== 3. Reset
def reset_sim(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'sims.reset %s' % info.id, '%s was reset.' % _name(info))
    return None


commands.add('sims.actions.reset', reset_sim)


# ======================================================================== 4. Teleport to Me
def teleport_to_me(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    try:
        import services
    except Exception:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return None
    active = common.guarded('novulon sims.actions: get_active_sim', services.get_active_sim)
    if active is None:
        menukit.notify('Nothing changed.', 'No active Sim.', urgent=True)
        return None
    pos = getattr(active, 'position', None)
    level = getattr(active, 'level', None)
    if pos is None or level is None:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return None
    _exec(connection, 'sims.teleport_instantly %r %r %r %d %s 0' % (pos.x, pos.y, pos.z, level, info.id),
          '%s was teleported to you.' % _name(info))
    return None


commands.add('sims.actions.teleport_to_me', teleport_to_me)


# ======================================================================== 5. Add to Household
def add_to_household(connection, sim_id):
    """`sims.add_to_family <sim_id>` - with no second Sim it defaults to the ACTIVE household
    (`server_commands/sim_commands.pyc:add_to_family`, verified this session)."""
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'sims.add_to_family %s' % info.id, '%s was added to your household.' % _name(info))
    return None


commands.add('sims.actions.add_to_household', add_to_household)


# ======================================================================== 6. Make Playable / Make NPC
def _client_for_household(household_id):
    import services
    return services.client_manager().get_client_by_household_id(household_id)


def toggle_playable(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    try:
        import services
    except Exception:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return None
    is_selectable_fn = getattr(info, 'is_selectable', None) or (lambda: False)
    already = bool(common.guarded('novulon sims.actions: is_selectable', is_selectable_fn))
    if already:
        client = common.guarded('novulon sims.actions: client_for_household', _client_for_household,
                                 info.household_id)
        ok = bool(client) and bool(common.guarded(
            'novulon sims.actions: remove_selectable_sim_by_id', client.remove_selectable_sim_by_id, info.id))
        if ok:
            menukit.notify('Made NPC.', '%s is no longer playable.' % _name(info))
        else:
            menukit.notify('Nothing changed.', 'A household needs at least one playable Sim.')
        return None
    active_household_id = common.guarded('novulon sims.actions: active_household_id', services.active_household_id)
    if active_household_id is not None and info.household_id != active_household_id:
        _exec(connection, 'sims.add_to_family %s' % info.id, None)
        info = _sim_info(sim_id) or info
    target_household_id = active_household_id if active_household_id is not None else info.household_id
    client = common.guarded('novulon sims.actions: client_for_household', _client_for_household,
                             target_household_id)
    ok = bool(client) and bool(common.guarded(
        'novulon sims.actions: add_selectable_sim_by_id', client.add_selectable_sim_by_id, info.id))
    if ok:
        menukit.notify('Made Playable.', '%s can now be played.' % _name(info))
    else:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
    return None


commands.add('sims.actions.toggle_playable', toggle_playable)


# ======================================================================== 7. Fill Needs
def fill_needs(connection, sim_id):
    """`sims.fill_all_commodities <sim_id>` - the same literal `gameplay/menu.py`/`gameplay/cheats.py`
    (BP9, already shipped in this tree) use for the active-Sim version of this exact action."""
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'sims.fill_all_commodities %s' % info.id, "%s's needs were filled." % _name(info))
    return None


commands.add('sims.actions.fill_needs', fill_needs)


# ======================================================================== 8. Set Age
def open_set_age_menu(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    rows = [
        Row('sims.actions.age.up', 'Age Up', on_activate=_bound(age_up, sim_id)),
        Row('sims.actions.age.down', 'Age Down', on_activate=_bound(age_down, sim_id)),
        Row('sims.actions.age.set_progress', 'Set Age Progress %…',
            on_activate=_bound(_age_set_progress_open, sim_id)),
        Row('sims.actions.age.add_progress', 'Add Age Progress %…',
            on_activate=_bound(_age_add_progress_open, sim_id)),
    ]
    return Page('Set Age', rows, breadcrumb=('Sims', _name(info), 'Set Age'))


commands.add('sims.actions.set_age_menu', open_set_age_menu)


def age_up(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'sims.age_up %s' % info.id, '%s aged up.' % _name(info))
    return None


commands.add('sims.actions.age.up', age_up)


def age_down(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'sims.age_down %s' % info.id, '%s aged down.' % _name(info))
    return None


commands.add('sims.actions.age.down', age_down)


def _age_set_progress_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'sims.set_age_progress_percentage %s %s' % (text.strip(), info.id),
              'Age progress set.')
    _ask_text(connection, 'Set Age Progress', 'Type a percent, 0-100.', _got)
    return None


commands.add('sims.actions.age.set_progress', _age_set_progress_open)


def _age_add_progress_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'sims.age_add_progress_percentage %s %s' % (text.strip(), info.id),
              'Age progress added.')
    _ask_text(connection, 'Add Age Progress', 'Type a percent to add.', _got)
    return None


commands.add('sims.actions.age.add_progress', _age_add_progress_open)


# ======================================================================== 9. Relationship
def open_relationship_menu(connection, sim_id):
    """Delegates to `relationships/menu.py` (BP10) - see the module docstring for why this file never
    calls `relationship.*` commands itself, and for the known caveat (BP10's rows always act on the
    ACTIVE Sim, not `sim_id`)."""
    try:
        from ..relationships import menu as _rel_menu
    except Exception:
        _rel_menu = None
    if _rel_menu is not None and hasattr(_rel_menu, 'relationships_page'):
        page = common.guarded('novulon sims.actions: relationships.menu.relationships_page',
                               _rel_menu.relationships_page, connection)
        if page is not None:
            return page
    return Page('Relationship', [
        Row('sims.actions.relationship.unavailable', 'Relationships module is not available yet.',
            disabled_text='Not available', on_activate=_noop),
    ], breadcrumb=('Sims', 'Relationship'))


commands.add('sims.actions.relationship_menu', open_relationship_menu)
commands.add('sims.actions.relationship.unavailable', _noop)


# ======================================================================== 10. Needs & Moods
def open_needs_menu(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    rows = [
        Row('sims.actions.needs.fill_all', 'Fill All Needs', on_activate=_bound(fill_needs, sim_id)),
        Row('sims.actions.needs.set_one', 'Set Individual Need…',
            on_activate=_bound(_needs_set_one_open, sim_id)),
        Row('sims.actions.needs.add_moodlet', 'Add Moodlet…',
            on_activate=_bound(_needs_add_moodlet_open, sim_id)),
        Row('sims.actions.needs.remove_moodlet', 'Remove Moodlet…',
            on_activate=_bound(_needs_remove_moodlet_open, sim_id)),
    ]
    return Page('Needs & Moods', rows, breadcrumb=('Sims', _name(info), 'Needs & Moods'))


commands.add('sims.actions.needs_menu', open_needs_menu)
commands.add('sims.actions.needs.fill_all', fill_needs)   # the "Fill All Needs" row inside this page -
                                                            # real bug found by the integrator's own row-
                                                            # id-vs-registration audit: every other row on
                                                            # this exact page was registered, this one
                                                            # wasn't, so opening "Needs & Moods..." from a
                                                            # Sim Card would have raised ValueError out of
                                                            # menukit/stack.py's "every row needs a
                                                            # registered command" guard the first time a
                                                            # player ever clicked it.


def _needs_set_one_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _build(values):
        need, value = values
        return 'stats.set_commodity %s %s %s' % (need, value, info.id)
    _prompt_chain(connection,
                  [('Need', 'Type the need name, e.g. Hunger.'), ('Value', 'Type the raw value.')],
                  _build, 'Need updated.')
    return None


commands.add('sims.actions.needs.set_one', _needs_set_one_open)


def _needs_add_moodlet_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'sims.add_buff %s %s' % (text.strip(), info.id), 'Moodlet added.')
    _ask_text(connection, 'Add Moodlet', 'Type the moodlet name.', _got)
    return None


commands.add('sims.actions.needs.add_moodlet', _needs_add_moodlet_open)


def _needs_remove_moodlet_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'sims.remove_buff %s %s' % (text.strip(), info.id), 'Moodlet removed.')
    _ask_text(connection, 'Remove Moodlet', 'Type the moodlet name.', _got)
    return None


commands.add('sims.actions.needs.remove_moodlet', _needs_remove_moodlet_open)


# ======================================================================== 11. Skills & Career
def open_skills_career_menu(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    rows = [
        Row('sims.actions.skills.set_level', 'Set Skill Level…', on_activate=_bound(_skills_set_level_open, sim_id)),
        Row('sims.actions.skills.max_all', 'Max All Skills', on_activate=_bound(skills_max_all, sim_id)),
        Row('sims.actions.skills.clear_all', 'Clear All Skills', on_activate=_bound(skills_clear_all, sim_id)),
        Row('sims.actions.career.add', 'Add Career…', on_activate=_bound(_career_add_open, sim_id)),
        Row('sims.actions.career.promote', 'Promote…', on_activate=_bound(_career_promote_open, sim_id)),
        Row('sims.actions.career.demote', 'Demote…', on_activate=_bound(_career_demote_open, sim_id)),
        Row('sims.actions.career.add_pto', 'Add PTO…', on_activate=_bound(_career_add_pto_open, sim_id)),
        Row('sims.actions.career.add_performance', 'Add Career Performance…',
            on_activate=_bound(_career_add_performance_open, sim_id)),
    ]
    return Page('Skills & Career', rows, breadcrumb=('Sims', _name(info), 'Skills & Career'))


commands.add('sims.actions.skills_career_menu', open_skills_career_menu)


def _skills_set_level_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _build(values):
        skill, level = values
        return 'stats.set_skill_level %s %s %s' % (skill, level, info.id)
    _prompt_chain(connection,
                  [('Skill', 'Type the skill name.'), ('Level', 'Type the level.')],
                  _build, 'Skill level set.')
    return None


commands.add('sims.actions.skills.set_level', _skills_set_level_open)


def skills_max_all(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'stats.set_all_skills_max %s' % info.id, 'All skills maxed.')
    return None


commands.add('sims.actions.skills.max_all', skills_max_all)


def skills_clear_all(connection, sim_id):
    """`stats.clear_skill` clears EVERY tracked skill on the Sim, not one named skill - confirmed this
    session by disassembling its body (iterates every statistic, filters `is_skill`), independently
    matching `gameplay/menu.py` (BP9)'s own citation. The row is labelled accordingly."""
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'stats.clear_skill %s' % info.id, 'All skills cleared.')
    return None


commands.add('sims.actions.skills.clear_all', skills_clear_all)


def _career_add_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'careers.add_career %s %s' % (text.strip(), info.id), 'Career added.')
    _ask_text(connection, 'Add Career', 'Type the career name.', _got)
    return None


commands.add('sims.actions.career.add', _career_add_open)


def _career_promote_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'careers.promote %s %s' % (text.strip(), info.id), 'Promoted.')
    _ask_text(connection, 'Promote', 'Type the career name.', _got)
    return None


commands.add('sims.actions.career.promote', _career_promote_open)


def _career_demote_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'careers.demote %s %s' % (text.strip(), info.id), 'Demoted.')
    _ask_text(connection, 'Demote', 'Type the career name.', _got)
    return None


commands.add('sims.actions.career.demote', _career_demote_open)


def _career_add_pto_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        _exec(connection, 'careers.add_pto %s %s' % (text.strip(), info.id), 'PTO added.')
    _ask_text(connection, 'Add PTO', 'Type the amount.', _got)
    return None


commands.add('sims.actions.career.add_pto', _career_add_pto_open)


def _career_add_performance_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _build(values):
        amount, career = values
        return 'careers.add_performance %s %s %s' % (info.id, amount, career)
    _prompt_chain(connection,
                  [('Amount', 'Type the performance amount.'), ('Career', 'Type the career name.')],
                  _build, 'Performance added.')
    return None


commands.add('sims.actions.career.add_performance', _career_add_performance_open)


# ======================================================================== 12. Occult
def open_occult_menu(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    rows = []
    for name, label in _OCCULT_TYPES:
        rows.append(Row('sims.actions.occult.turn_into', 'Turn Into %s' % label,
                         on_activate=_bound(_occult_switch, sim_id, name)))
    for name, label in _OCCULT_TYPES:
        rows.append(Row('sims.actions.occult.remove', 'Remove %s' % label,
                         on_activate=_bound(_occult_remove, sim_id, name)))
    return Page('Occult', rows, breadcrumb=('Sims', _name(info), 'Occult'))


commands.add('sims.actions.occult_menu', open_occult_menu)


def _occult_switch(connection, sim_id, occult_type):
    """`occult.switch_to_occult <type> <sim_id>` (`sims/occult/occult_commands.pyc:switch_to_occult_type`,
    line 63, verified this session)."""
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'occult.switch_to_occult %s %s' % (occult_type, info.id),
          '%s is now a %s.' % (_name(info), occult_type.title()))
    return None


commands.add('sims.actions.occult.turn_into', _occult_switch)


def _occult_remove(connection, sim_id, occult_type):
    """`occult.remove_occult <type> <sim_id>` (`occult_commands.pyc:remove_occult_type`, line 46)."""
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'occult.remove_occult %s %s' % (occult_type, info.id), 'Occult type removed.')
    return None


commands.add('sims.actions.occult.remove', _occult_remove)


# ======================================================================== 13. Pregnancy
def open_pregnancy_menu(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    rows = [
        Row('sims.actions.pregnancy.start', 'Start Pregnancy…', on_activate=_bound(_pregnancy_start_open, sim_id)),
        Row('sims.actions.pregnancy.clear', 'Clear Pregnancy', on_activate=_bound(pregnancy_clear, sim_id)),
    ]
    return Page('Pregnancy', rows, breadcrumb=('Sims', _name(info), 'Pregnancy'))


commands.add('sims.actions.pregnancy_menu', open_pregnancy_menu)


def _resolve_sim_by_name(full_text):
    """`services.sim_info_manager().get_sim_info_by_name(first, last)` - verified pure-Python lookup
    (`sims/sim_info_manager.pyc:707`), the same mechanism `gameplay/menu.py`/`relationships/menu.py`
    already use for a second Sim, since this package has no Sim search of its own (that's the browser,
    BP4) beyond the tray it's handed."""
    try:
        import services
    except Exception:
        return None
    parts = str(full_text).strip().rsplit(' ', 1)
    first, last = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], '')
    return common.guarded('novulon sims.actions: get_sim_info_by_name',
                           services.sim_info_manager().get_sim_info_by_name, first, last)


def _pregnancy_start_open(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)

    def _got(text):
        if not text:
            return
        partner = _resolve_sim_by_name(text)
        if partner is None:
            menukit.notify('Nothing changed.', 'No Sim found with that name.', urgent=True)
            return
        _exec(connection, 'pregnancy.start %s %s' % (info.id, partner.id), 'Pregnancy started.')
    _ask_text(connection, 'Start Pregnancy', "Type the other parent's full name (First Last).", _got)
    return None


commands.add('sims.actions.pregnancy.start', _pregnancy_start_open)


def pregnancy_clear(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    _exec(connection, 'pregnancy.clear %s' % info.id, 'Pregnancy cleared.')
    return None


commands.add('sims.actions.pregnancy.clear', pregnancy_clear)


# ======================================================================== 14. Delete
def open_delete(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone(connection)
    delete.request_delete(connection, [info])
    return None


commands.add('sims.actions.delete', open_delete)


# ======================================================================== bulk (2+ Sims selected)
def _multi_delete(connection, *sim_id_args):
    infos = [i for i in (_sim_info(s) for s in sim_id_args) if i is not None]
    if infos:
        delete.request_delete(connection, infos)
    return None


commands.add('sims.actions.delete_selected', _multi_delete)


def _multi_fill_needs(connection, *sim_id_args):
    count = 0
    for raw in sim_id_args:
        info = _sim_info(raw)
        if info is None:
            continue
        _exec(connection, 'sims.fill_all_commodities %s' % info.id, None)
        count += 1
    if count:
        menukit.notify('Needs filled.', '%d Sims filled.' % count)
    else:
        menukit.notify('Nothing changed.', 'No Sims were available.', urgent=True)
    return None


commands.add('sims.actions.fill_needs_selected', _multi_fill_needs)


def build_multi_sim_action_page(connection, sim_ids):
    n = len(sim_ids)
    rows = [
        Row('sims.actions.delete_selected', 'Delete Selected', on_activate=_bound(_multi_delete, *sim_ids)),
        Row('sims.actions.fill_needs_selected', 'Fill Needs for Selected',
            on_activate=_bound(_multi_fill_needs, *sim_ids)),
        Row('sims.actions.edit_cas', 'Edit in CAS', disabled_text='Select exactly one Sim', on_activate=_noop),
        Row('sims.actions.traits_menu', 'Traits…', disabled_text='Select exactly one Sim', on_activate=_noop),
    ]
    return Page('%d Sims selected' % n, rows, breadcrumb=('Sims', '%d Selected' % n))


# ======================================================================== the single-Sim action list
def build_sim_action_page(connection, sim_id):
    info = _sim_info(sim_id)
    if info is None:
        return _sim_gone_page()
    name = _name(info)
    selectable = bool(common.guarded('novulon sims.actions: is_selectable',
                                      getattr(info, 'is_selectable', None) or (lambda: False)))
    playable_label = 'Make NPC' if selectable else 'Make Playable'
    rows = [
        Row('sims.actions.edit_cas', 'Edit in CAS', on_activate=_bound(edit_in_cas, sim_id)),
        Row('sims.actions.traits_menu', 'Traits…', on_activate=_bound(open_traits_menu, sim_id)),
        Row('sims.actions.reset', 'Reset', on_activate=_bound(reset_sim, sim_id)),
        Row('sims.actions.teleport_to_me', 'Teleport to Me', on_activate=_bound(teleport_to_me, sim_id)),
        Row('sims.actions.add_to_household', 'Add to Household', on_activate=_bound(add_to_household, sim_id)),
        Row('sims.actions.toggle_playable', playable_label, on_activate=_bound(toggle_playable, sim_id)),
        Row('sims.actions.fill_needs', 'Fill Needs', on_activate=_bound(fill_needs, sim_id)),
        Row('sims.actions.set_age_menu', 'Set Age…', on_activate=_bound(open_set_age_menu, sim_id)),
        Row('sims.actions.relationship_menu', 'Relationship…', on_activate=_bound(open_relationship_menu, sim_id)),
        Row('sims.actions.needs_menu', 'Needs & Moods…', on_activate=_bound(open_needs_menu, sim_id)),
        Row('sims.actions.skills_career_menu', 'Skills & Career…', on_activate=_bound(open_skills_career_menu, sim_id)),
        Row('sims.actions.occult_menu', 'Occult…', on_activate=_bound(open_occult_menu, sim_id)),
        Row('sims.actions.pregnancy_menu', 'Pregnancy…', on_activate=_bound(open_pregnancy_menu, sim_id)),
        Row('sims.actions.delete', 'Delete', on_activate=_bound(open_delete, sim_id)),
    ]
    return Page(name, rows, breadcrumb=('Sims', name))


# ======================================================================== the browser's public hook
def open_selection_action(connection, *sim_id_args):
    """Body of `'novulon.sims.selection_action'` - see the module docstring. `sims/browser.py` (BP4)
    calls this through `commands.do(...)`, never imports this module directly."""
    ids = []
    for raw in sim_id_args:
        n = _to_int(raw)
        if n is not None:
            ids.append(n)
    if not ids:
        return None
    if len(ids) == 1:
        return build_sim_action_page(connection, ids[0])
    return build_multi_sim_action_page(connection, ids)


commands.add('novulon.sims.selection_action', open_selection_action)

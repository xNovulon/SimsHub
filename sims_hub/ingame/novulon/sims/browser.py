"""Sim Browser (SPEC.md `sims/` Sec 5.1-5.4, BP4): the Males/Females/Pets/All/Advanced category
chooser, the Advanced filter picker, the paged multi-select Sim list, and the single-Sim Card.

Every EA name this file touches (`services.sim_info_manager`/`household_manager`/
`active_household_id`, `sims.sim_info_types.Gender/Age/Species`,
`sims.occult.occult_enums.OccultType`, `ui.ui_dialog_picker.UiSimPicker`/`SimPickerRow`) is verified
against THIS installed game build with `tools/pyc37.py` (this package's own manifest,
`tools/novulon_api_manifest/bp4_sims_browser.py`, has the line-number citations) - never imported at
module level, only lazily inside function bodies (same pattern `inject.py`/`commands.py` already
use), so this module stays importable with no game running at all (Tier 1 pure tests, Tier 2's
import-only check).

TWO DIFFERENT DIALOG MECHANISMS, ON PURPOSE (menukit/render.py's own verified finding, restated in
its docstring: `UiObjectPicker` only accepts `ObjectPickerRow`, `UiSimPicker` only accepts
`SimPickerRow` - the two picker dialogs are mutually exclusive about row type):
  * Every screen that is NOT a list of actual Sims (the category chooser, the Advanced filter
    picker, the household picker, the "Browse Controls" screen between one Sim-list view and the
    next) is a normal `menukit.Row`/`Page`, built and shown exactly like every other Novulon screen.
  * The one screen that IS a list of actual Sims (the paged Sim list, and the one-row Sim Card) is
    NOT a menukit Page at all - this file builds `ui.ui_dialog_picker.UiSimPicker` directly, reusing
    menukit's PURE helpers (`paging.page_of`, `search.apply`, `stack.for_connection`,
    `stack.apply_selection_delta`) exactly as `menukit/__init__.py`'s own docstring instructs BP4 to.

WHY THERE IS A SEPARATE "BROWSE CONTROLS" SCREEN: because a `UiSimPicker`'s rows can only ever be
Sims, there is nowhere on that dialog to put a "Next Page"/"Previous Page"/"Change Filters" row.
`game_api.md` Sec 2 already flags this for the whole picker family ("tabs/categories: not a
first-class feature... chained dialogs, not one dialog with in-place tabs"). V1's resolution: the
count pill, filter summary, and paging footer (SPEC.md Sec 5.3) live in the text (title/subtitle) of
a small menukit "Browse Controls" Page; that page's own rows are the real actions (search, next/prev
page, change filters, open the actual Sim list, act on whatever is selected). Opening/closing the raw
`UiSimPicker` never pushes/pops the menukit `NavStack` - it only reads/writes `nav.state`/`nav.tray`,
and every response from it re-shows a freshly rebuilt Browse Controls page in place. This is a real,
deliberate structural decision, not an oversight - noted here since a future reader may otherwise
wonder why paging isn't just extra rows on the Sim list itself.

SELECTION MODEL: the Sim list is always shown multi-select (`min_selectable=0, max_selectable=0` -
the verified plain-int "unlimited" shape, `menukit/render.py`'s own citation), with each row's
`is_selected` pre-set from the persistent `nav.tray` (SPEC.md Sec 5.3's cross-page tray). Checking
exactly one Sim and returning to Browse Controls offers "View Sim Card" (SPEC.md Sec 5.4); checking
one or more and choosing "Choose Action" hands the whole tray off to `sims/actions.py` (BP5, not yet
built) via a stable action id (`novulon.sims.selection_action`) this file only ever CALLS through
`commands.do(...)`, never registers - `commands.do` degrades to a logged no-op on an unknown id
(`commands.py`'s own documented contract), so this file works whether or not BP5 exists yet.

SIM CARD SCOPE (SPEC.md Sec 5.4): portrait (live-resolved from `sim_id` by `SimPickerRow` itself, no
icon plumbing needed - verified, `game_api.md` Sec 2/3), full name, age/gender/species/occult badges,
household name + played/NPC/instanced status. Traits/aspiration/career/skill/need/relationship-count
fields are CUT for V1 - `SimInfo.trait_tracker`/`aspiration_tracker`/`career_tracker`/
`relationship_tracker` exist as properties (`sims/sim_info.pyc` lines 1915/1986/2059, plus a
trait-related property this session did not resolve to a name on `SimInfo` itself), but no research
pass in this project (nor this session's own verification pass) disassembled what any of them
actually expose (e.g. "the top 3 traits" or "a relationship count") - shipping a guess on a screen
the owner explicitly asked to look good is exactly what SPEC.md's override forbids. Left for BP5/
V1.1, which already needs that same verification pass to open the real Traits/Career/Relationship
panels.

The tray (`nav.tray`) is explicitly RESET (to the empty set) every time a category is (re)entered
from the root chooser, and again right after a successful hand-off to BP5's action - `NavStack.tray`
is one set per CONNECTION, shared by every multi-select screen on that connection for the whole
session (menukit's own design, `stack.py`), so without this a Sim checked here could otherwise still
be "selected" if some unrelated future multi-select screen (e.g. a household inventory picker) reused
a colliding integer id. This keeps the tray scoped to "the Sims currently being browsed," which is
the only guarantee SPEC.md Sec 5.3 actually asks for ("persists across a filter change or page turn").
"""
from . import query
from .. import commands, common
from .. import menukit
from ..menukit import Row, Page

_LIFE_STAGE_ORDER = ('BABY', 'INFANT', 'TODDLER', 'CHILD', 'TEEN', 'YOUNGADULT', 'ADULT', 'ELDER')
_LIFE_STAGE_LABELS = {
    'BABY': 'Baby', 'INFANT': 'Infant', 'TODDLER': 'Toddler', 'CHILD': 'Child', 'TEEN': 'Teen',
    'YOUNGADULT': 'Young Adult', 'ADULT': 'Adult', 'ELDER': 'Elder',
}
# Spellcaster is the player-facing name for the internal 'Witch' OccultType member (SPEC.md Sec 5.2).
_OCCULT_ORDER = ('HUMAN', 'VAMPIRE', 'WITCH', 'MERMAID', 'ALIEN', 'WEREWOLF', 'FAIRY')
_OCCULT_LABELS = {
    'HUMAN': 'Human', 'VAMPIRE': 'Vampire', 'WITCH': 'Spellcaster', 'MERMAID': 'Mermaid',
    'ALIEN': 'Alien', 'WEREWOLF': 'Werewolf', 'FAIRY': 'Fairy',
}

_enum_cache = {}


def _enums():
    """Lazily import and cache Gender/Age/Species/OccultType - the one place this file touches those
    modules. Returns None (never raises) if they aren't available right now (Tier 1/4 tests, or a
    build-order problem); every caller degrades to plain, filter-less/badge-less behavior instead of
    crashing. NOTE: the game's OWN top-level `sims` package (`sims.sim_info_types`,
    `sims.occult.occult_enums`) is a different, unrelated package from this file's own parent
    `novulon.sims` - Python's absolute-import resolution keeps the two apart, but the name overlap is
    worth flagging for anyone reading this cold."""
    if 'ok' not in _enum_cache:
        try:
            from sims.sim_info_types import Gender, Age, Species
            from sims.occult.occult_enums import OccultType
        except Exception:
            common.log_exception('sims.browser: importing Gender/Age/Species/OccultType')
            _enum_cache['ok'] = False
        else:
            _enum_cache.update(ok=True, Gender=Gender, Age=Age, Species=Species, OccultType=OccultType)
    return _enum_cache if _enum_cache['ok'] else None


def _label_pairs():
    """(age_pairs, occult_pairs, species_pairs) - ordered `[(bit_or_value, label), ...]` lists built
    from the real enums, for `query.py`'s label helpers. Empty lists (never a raise) when the game
    enums aren't available right now."""
    enums = _enums()
    if enums is None:
        return [], [], []
    Age, OccultType, Species = enums['Age'], enums['OccultType'], enums['Species']
    age_pairs = [(getattr(Age, name), _LIFE_STAGE_LABELS[name]) for name in _LIFE_STAGE_ORDER]
    occult_pairs = [(getattr(OccultType, name), _OCCULT_LABELS[name]) for name in _OCCULT_ORDER]
    species_pairs = [(Species.HUMAN, 'Human'), (Species.DOG, 'Dog'), (Species.CAT, 'Cat'),
                      (Species.FOX, 'Fox'), (Species.HORSE, 'Horse')]
    return age_pairs, occult_pairs, species_pairs


def _badge_occult_pairs(occult_pairs):
    """`occult_pairs` minus Human - a badge/row-description shouldn't call out the default, unmarked
    form every ordinary Sim already has (SPEC.md Sec 5.3's own badge examples never show 'Human'),
    even though Human IS one of the seven checkable Advanced filter chips (SPEC.md Sec 5.2)."""
    return [(bit, label) for bit, label in occult_pairs if label != _OCCULT_LABELS['HUMAN']]


def _gender_labels():
    enums = _enums()
    if enums is None:
        return {}
    Gender = enums['Gender']
    return {Gender.MALE: 'Male', Gender.FEMALE: 'Female'}


# ------------------------------------------------------------------ game-facing data access
def _all_sim_infos():
    """Every SimInfo in the save (verified, `services.sim_info_manager().values()` -
    `services/__init__.pyc:631`, `indexed_manager.pyc`'s own `IndexedManager.values`). `[]`, never a
    raise, outside the game or before any zone is up."""
    try:
        import services
    except Exception:
        return []
    mgr = common.guarded('sims.browser: sim_info_manager()', services.sim_info_manager)
    if mgr is None:
        return []
    result = common.guarded('sims.browser: sim_info_manager().values()', lambda: list(mgr.values()))
    return result or []


def _sim_info_by_id(sim_id):
    try:
        import services
    except Exception:
        return None
    mgr = common.guarded('sims.browser: sim_info_manager()', services.sim_info_manager)
    if mgr is None:
        return None
    return common.guarded('sims.browser: sim_info_manager().get', mgr.get, sim_id)


def _all_households():
    """Every Household in the save (verified, `services.household_manager().values()` -
    `HouseholdManager(DistributableObjectManager(IndexedManager))`, this session's own pyc37.py
    check). `[]`, never a raise, outside the game."""
    try:
        import services
    except Exception:
        return []
    mgr = common.guarded('sims.browser: household_manager()', services.household_manager)
    if mgr is None:
        return []
    result = common.guarded('sims.browser: household_manager().values()', lambda: list(mgr.values()))
    return result or []


def _active_household_id():
    try:
        import services
    except Exception:
        return None
    return common.guarded('sims.browser: active_household_id()', services.active_household_id)


def _household_name(sim_info):
    household = getattr(sim_info, 'household', None)
    return getattr(household, 'name', None) if household is not None else None


def _household_name_by_id(household_id):
    for household in _all_households():
        if getattr(household, 'id', None) == household_id:
            return getattr(household, 'name', None) or ('Household %s' % household_id)
    return 'Household %s' % household_id


def _page_size():
    try:
        from .. import settings
    except Exception:
        return menukit.paging.DEFAULT_PAGE_SIZE
    size = common.guarded('sims.browser: settings.get(sim_browser.page_size)', settings.get,
                           'sim_browser.page_size', menukit.paging.DEFAULT_PAGE_SIZE)
    if (not isinstance(size, int) or isinstance(size, bool)
            or size < menukit.paging.MIN_PAGE_SIZE or size > menukit.paging.MAX_PAGE_SIZE):
        return menukit.paging.DEFAULT_PAGE_SIZE
    return size


def _noop(connection, *args):
    return None


def _to_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ filter/search/page pipeline
def _filtered_sorted(connection):
    """(sorted_filtered_sim_infos, active_household_id) for the current `nav.state` - filter, then
    search, then sort (`menukit/paging.py`'s own hard rule: filter/search first, page the result)."""
    nav = menukit.stack.for_connection(connection)
    active_household_id = _active_household_id()
    filters = nav.state.get('filters') or {}
    matched = query.filtered(_all_sim_infos(), filters, active_household_id)
    matched = menukit.search.apply(matched, nav.state.get('search_query'),
                                    key=lambda s: getattr(s, 'full_name', '') or '')
    return query.sorted_for_display(matched), active_household_id


def _current_page_sims(connection):
    nav = menukit.stack.for_connection(connection)
    sim_infos, active_household_id = _filtered_sorted(connection)
    page_index = nav.state.get('page_index', 0)
    rows, has_prev, has_next = menukit.paging.page_of(sim_infos, _page_size(), page_index)
    return rows, active_household_id, {'total': len(sim_infos), 'has_prev': has_prev, 'has_next': has_next}


def _status_subtitle(connection, total, page_index, page_size):
    nav = menukit.stack.for_connection(connection)
    age_pairs, occult_pairs, _species_pairs = _label_pairs()
    filters = nav.state.get('filters') or {}
    labels = query.active_filter_labels(filters, age_pairs, occult_pairs, _gender_labels())
    household_id = filters.get('household_id')
    if household_id is not None:
        labels.append('Household: %s' % _household_name_by_id(household_id))
    filter_text = 'Filters: ' + (', '.join(labels) if labels else 'All Sims')
    footer = menukit.paging.footer_text(total, page_size, page_index)
    tray_n = len(nav.tray)
    selected_text = ('%d Selected' % tray_n) if tray_n else 'Nothing selected yet.'
    return '%s\n%s\n%s' % (footer, filter_text, selected_text)


# ------------------------------------------------------------------ 5.1 category chooser
def open_root(connection, selected_ids=None):
    """'Novulon -> Sims' - Males/Females/Pets/All/Advanced, live counts (SPEC.md Sec 5.1; the
    owner's own build task adds an explicit 'All' tab alongside the three spec-named ones)."""
    enums = _enums()
    sim_infos = _all_sim_infos()
    if enums is not None:
        c = query.counts(sim_infos, enums['Gender'].MALE, enums['Gender'].FEMALE, enums['Species'].HUMAN)
    else:
        c = {'males': 0, 'females': 0, 'pets': 0, 'all': len(sim_infos)}
    rows = [
        Row('novulon.sims.category.males', 'Males', description='%d Sims' % c['males'],
            on_activate=_open_males),
        Row('novulon.sims.category.females', 'Females', description='%d Sims' % c['females'],
            on_activate=_open_females),
        Row('novulon.sims.category.pets', 'Pets', description='%d Sims' % c['pets'],
            on_activate=_open_pets),
        Row('novulon.sims.category.all', 'All', description='%d Sims' % c['all'],
            on_activate=_open_all),
        Row('novulon.sims.category.advanced', 'Advanced',
            description='Filter by life stage or occult type.', on_activate=_open_advanced_fresh),
    ]
    return Page('Sims', rows, breadcrumb=('Sims',))


def _reset_for_category(connection, label, filters):
    nav = menukit.stack.for_connection(connection)
    nav.state['filters'] = filters
    nav.state['page_index'] = 0
    nav.state['search_query'] = None
    nav.state['category_label'] = label
    nav.tray = set()   # see module docstring: the tray is scoped to one category's browsing session


def _open_males(connection, selected_ids=None):
    enums = _enums()
    _reset_for_category(connection, 'Males', {'gender': enums['Gender'].MALE} if enums else {})
    return _build_controls_page(connection)


def _open_females(connection, selected_ids=None):
    enums = _enums()
    _reset_for_category(connection, 'Females', {'gender': enums['Gender'].FEMALE} if enums else {})
    return _build_controls_page(connection)


def _open_pets(connection, selected_ids=None):
    enums = _enums()
    filters = {'species_ne': enums['Species'].HUMAN} if enums else {}
    _reset_for_category(connection, 'Pets', filters)
    return _build_controls_page(connection)


def _open_all(connection, selected_ids=None):
    _reset_for_category(connection, 'All', {})
    return _build_controls_page(connection)


def _open_advanced_fresh(connection, selected_ids=None):
    _reset_for_category(connection, 'Advanced', {})
    return open_advanced_filters(connection)


# ------------------------------------------------------------------ 5.2 advanced filters
def _toggle_bit(filters, key, bit):
    bits = set(filters.get(key) or ())
    if bit in bits:
        bits.discard(bit)
    else:
        bits.add(bit)
    filters[key] = bits


def _rebuild_advanced(connection):
    menukit.show_page(connection, open_advanced_filters(connection), push=False)


def _make_life_toggle(name):
    def _fn(connection, *args):
        enums = _enums()
        if enums is not None:
            nav = menukit.stack.for_connection(connection)
            _toggle_bit(nav.state.setdefault('filters', {}), 'life_stages', getattr(enums['Age'], name))
        _rebuild_advanced(connection)
        return None
    return _fn


def _make_occult_toggle(name):
    def _fn(connection, *args):
        enums = _enums()
        if enums is not None:
            nav = menukit.stack.for_connection(connection)
            _toggle_bit(nav.state.setdefault('filters', {}), 'occults', getattr(enums['OccultType'], name))
        _rebuild_advanced(connection)
        return None
    return _fn


def _make_status_toggle(key):
    def _fn(connection, *args):
        nav = menukit.stack.for_connection(connection)
        filters = nav.state.setdefault('filters', {})
        filters[key] = not filters.get(key)
        _rebuild_advanced(connection)
        return None
    return _fn


_LIFE_STAGE_TOGGLES = dict((name, _make_life_toggle(name)) for name in _LIFE_STAGE_ORDER)
_OCCULT_TOGGLES = dict((name, _make_occult_toggle(name)) for name in _OCCULT_ORDER)
_STATUS_TOGGLES = dict((key, _make_status_toggle(key)) for key in ('played', 'npc', 'here'))


def open_advanced_filters(connection, selected_ids=None):
    """'Novulon -> Sims -> Advanced' (SPEC.md Sec 5.2). Reflects whatever's already in
    `nav.state['filters']` - reached fresh (via `_open_advanced_fresh`, cleared first) or via
    'Change Filters' from Browse Controls (SPEC.md: 'reopens the choosers already at their current
    picks' - unchanged here on purpose)."""
    nav = menukit.stack.for_connection(connection)
    filters = nav.state.setdefault('filters', {})
    enums = _enums()
    if enums is None:
        rows = [Row('novulon.sims.advanced.unavailable', 'Filters need the game to be running.',
                     disabled_text='Not available', on_activate=_noop)]
        return Page('Advanced', rows, breadcrumb=('Sims', 'Advanced'))

    Age, OccultType = enums['Age'], enums['OccultType']
    life_bits = set(filters.get('life_stages') or ())
    occult_bits = set(filters.get('occults') or ())
    rows = []
    for name in _LIFE_STAGE_ORDER:
        checked = getattr(Age, name) in life_bits
        rows.append(Row('novulon.sims.advanced.life.%s' % name,
                         ('[x] ' if checked else '[ ] ') + _LIFE_STAGE_LABELS[name],
                         on_activate=_LIFE_STAGE_TOGGLES[name]))
    for name in _OCCULT_ORDER:
        checked = getattr(OccultType, name) in occult_bits
        rows.append(Row('novulon.sims.advanced.occult.%s' % name,
                         ('[x] ' if checked else '[ ] ') + _OCCULT_LABELS[name],
                         on_activate=_OCCULT_TOGGLES[name]))
    for key, label in (('played', 'Played'), ('npc', 'NPC'), ('here', 'Here')):
        checked = bool(filters.get(key))
        rows.append(Row('novulon.sims.advanced.status.%s' % key,
                         ('[x] ' if checked else '[ ] ') + label, on_activate=_STATUS_TOGGLES[key]))
    household_id = filters.get('household_id')
    household_label = ('Household: %s' % _household_name_by_id(household_id)) if household_id is not None \
        else 'Household: Any'
    rows.append(Row('novulon.sims.advanced.household', household_label, on_activate=open_household_picker))
    if query.has_any_filter(filters):
        rows.append(Row('novulon.sims.advanced.show_results', 'Show Results', on_activate=_row_show_results))
    return Page('Advanced', rows, breadcrumb=('Sims', 'Advanced'))


def _row_show_results(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.state['page_index'] = 0
    nav.state.setdefault('category_label', 'Advanced')
    return _build_controls_page(connection)


# ------------------------------------------------------------------ household picker (part of Advanced)
def open_household_picker(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    households = sorted(_all_households(), key=lambda h: (getattr(h, 'name', '') or '').lower())
    page_index = nav.state.get('household_page_index', 0)
    page_size = menukit.paging.DEFAULT_PAGE_SIZE
    page_items, has_prev, has_next = menukit.paging.page_of(households, page_size, page_index)

    rows = [Row('novulon.sims.household.clear', 'Any Household', on_activate=_clear_household)]
    for household in page_items:
        rows.append(Row('novulon.sims.household.pick',
                         getattr(household, 'name', None) or ('Household %s' % household.id),
                         on_activate=_pick_household_fn(household.id)))
    if has_prev:
        rows.append(Row('novulon.sims.household.prev_page', 'Previous Page', on_activate=_household_prev_page))
    if has_next:
        rows.append(Row('novulon.sims.household.next_page', 'Next Page', on_activate=_household_next_page))
    footer = menukit.paging.footer_text(len(households), page_size, page_index)
    return Page('Household', rows, breadcrumb=('Sims', 'Advanced', 'Household'), subtitle=footer)


def _pick_household_fn(household_id):
    def _fn(connection, selected_ids=None):
        nav = menukit.stack.for_connection(connection)
        nav.state.setdefault('filters', {})['household_id'] = household_id
        return _return_from_household_picker(connection)
    return _fn


def _clear_household(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.state.setdefault('filters', {})['household_id'] = None
    return _return_from_household_picker(connection)


def _return_from_household_picker(connection):
    nav = menukit.stack.for_connection(connection)
    nav.state['household_page_index'] = 0
    return open_advanced_filters(connection)


def _household_prev_page(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.state['household_page_index'] = max(0, nav.state.get('household_page_index', 0) - 1)
    menukit.show_page(connection, open_household_picker(connection), push=False)
    return None


def _household_next_page(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.state['household_page_index'] = nav.state.get('household_page_index', 0) + 1
    menukit.show_page(connection, open_household_picker(connection), push=False)
    return None


# ------------------------------------------------------------------ 5.3 browse controls (menukit Page)
def _build_controls_page(connection):
    nav = menukit.stack.for_connection(connection)
    sim_infos, _active_household_id_ = _filtered_sorted(connection)
    total = len(sim_infos)
    page_size = _page_size()
    page_index = nav.state.get('page_index', 0)
    _page_rows, has_prev, has_next = menukit.paging.page_of(sim_infos, page_size, page_index)

    query_text = nav.state.get('search_query')
    search_label = 'Search…' if not query_text else 'Search… (last: "%s")' % query_text
    tray_n = len(nav.tray)

    rows = [
        Row('novulon.sims.controls.view_select', 'View & Select Sims', on_activate=_row_view_select),
        Row('novulon.sims.controls.search', search_label, on_activate=_row_search),
    ]
    if has_prev:
        rows.append(Row('novulon.sims.controls.prev_page', 'Previous Page', on_activate=_row_prev_page))
    if has_next:
        rows.append(Row('novulon.sims.controls.next_page', 'Next Page', on_activate=_row_next_page))
    rows.append(Row('novulon.sims.controls.change_filters', 'Change Filters', on_activate=_row_change_filters))
    if tray_n == 1:
        rows.append(Row('novulon.sims.controls.view_card', 'View Sim Card', on_activate=_row_view_card))
    if tray_n >= 1:
        label = ('Choose Action for %d Sims' % tray_n) if tray_n > 1 else 'Choose Action'
        rows.append(Row('novulon.sims.controls.choose_action', label, on_activate=_row_choose_action))
        rows.append(Row('novulon.sims.controls.clear_selection', 'Clear Selection',
                         on_activate=_row_clear_selection))

    subtitle = _status_subtitle(connection, total, page_index, page_size)
    category = nav.state.get('category_label', 'Sims')
    return Page(category, rows, breadcrumb=('Sims', category), subtitle=subtitle)


def _row_view_select(connection, selected_ids=None):
    _open_sim_list(connection)
    return None


def _row_search(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)

    def _on_result(found_query):
        nav.state['search_query'] = found_query
        nav.state['page_index'] = 0
        menukit.show_page(connection, _build_controls_page(connection), push=False)

    menukit.search.open_search_box(connection, nav.state.get('search_query'), _on_result)
    return None


def _row_prev_page(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.state['page_index'] = max(0, nav.state.get('page_index', 0) - 1)
    menukit.show_page(connection, _build_controls_page(connection), push=False)
    return None


def _row_next_page(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.state['page_index'] = nav.state.get('page_index', 0) + 1
    menukit.show_page(connection, _build_controls_page(connection), push=False)
    return None


def _row_change_filters(connection, selected_ids=None):
    return open_advanced_filters(connection)


def _row_view_card(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    if len(nav.tray) != 1:
        menukit.show_page(connection, _build_controls_page(connection), push=False)
        return None
    sim_info = _sim_info_by_id(next(iter(nav.tray)))
    if sim_info is None:
        menukit.notify('Nothing changed.', 'That Sim is no longer available.', urgent=True)
        menukit.show_page(connection, _build_controls_page(connection), push=False)
        return None
    _show_sim_card(connection, sim_info)
    return None


def _row_choose_action(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    sim_ids = sorted(nav.tray)
    if not sim_ids:
        menukit.show_page(connection, _build_controls_page(connection), push=False)
        return None
    result = commands.do('novulon.sims.selection_action', connection, *[str(i) for i in sim_ids])
    nav.tray = set()   # handed off - see module docstring on why the tray doesn't linger past this
    if isinstance(result, Page):
        return result
    if result is None:
        menukit.notify('Nothing changed.', 'Sim actions are not available yet.')
    menukit.show_page(connection, _build_controls_page(connection), push=False)
    return None


def _row_clear_selection(connection, selected_ids=None):
    nav = menukit.stack.for_connection(connection)
    nav.tray = set()
    menukit.show_page(connection, _build_controls_page(connection), push=False)
    return None


# ------------------------------------------------------------------ the raw Sim list (UiSimPicker)
def _open_sim_list(connection):
    try:
        from ui.ui_dialog_picker import UiSimPicker, SimPickerRow
        from sims4.localization import LocalizationHelperTuning as L
    except Exception:
        common.log_exception('sims.browser: importing UiSimPicker/SimPickerRow')
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return

    nav = menukit.stack.for_connection(connection)
    page_sims, active_household_id, meta = _current_page_sims(connection)
    age_pairs, occult_pairs, species_pairs = _label_pairs()
    badge_pairs = _badge_occult_pairs(occult_pairs)
    subtitle_text = _status_subtitle(connection, meta['total'], nav.state.get('page_index', 0), _page_size())

    order = []          # SimInfo, in the exact order rows were added
    by_identity = {}     # id(built SimPickerRow) -> SimInfo

    try:
        dlg = UiSimPicker.TunableFactory().default(
            None,
            title=(lambda *_a, **_k: L.get_raw_text(nav.title_for())),
            subtitle=(lambda *_a, **_k: L.get_raw_text(subtitle_text)),
            min_selectable=0, max_selectable=0, display_filter=True)
        for sim_info in page_sims:
            full_name = getattr(sim_info, 'full_name', '') or ('Sim %s' % sim_info.id)
            desc_parts = [query.subtitle_for(sim_info, age_pairs, species_pairs, _household_name(sim_info))]
            badges = query.badges_for(sim_info, age_pairs, badge_pairs, active_household_id)
            if badges:
                desc_parts.append(' • '.join(badges))
            row = SimPickerRow(
                sim_id=sim_info.id, select_default=False, sim_location=None,
                household_id=getattr(sim_info, 'household_id', None),
                name=L.get_raw_text(full_name),
                row_description=L.get_raw_text(' — '.join(p for p in desc_parts if p)),
                is_selected=(sim_info.id in nav.tray))
            dlg.add_row(row)
            order.append(sim_info)
            by_identity[id(row)] = sim_info

        def _on_response(dialog):
            # This callback is invoked directly by the game's own dialog-response dispatch, so it must
            # never raise out to that caller. `_dispatch_sim_list` already guards
            # `dialog.get_result_rows()` internally, but its own trailing `menukit.show_page(...,
            # push=False)` call can still raise `ValueError` (`NavStack.replace_top` -> `validate_page`
            # - an unregistered row id in whatever `_build_controls_page` returns) - the same class of
            # unguarded-callback risk `menukit/render.py`'s own `_on_response` guards against.
            try:
                _dispatch_sim_list(connection, order, by_identity, dialog)
            except Exception:
                common.log_exception('sims.browser: sim list response')
                menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)

        dlg.show_dialog(on_response=_on_response)
    except Exception:
        common.log_exception('sims.browser: showing the Sim list')
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)


def _dispatch_sim_list(connection, order, by_identity, dialog):
    """`get_result_rows()` raising (the dialog was closed) and it returning an empty list (every row
    was unchecked, then OK was pressed) are indistinguishable from here - and, verified directly
    against `menukit/render.py`'s own `_dispatch` (`if not picked: return` before a multi-select page
    is ever folded into anything), the ENGINE's own convention treats both the same way: "nothing
    picked this response, leave the tray exactly as it was." So the only way to fully empty an
    already-non-empty tray is the explicit "Clear Selection" row on Browse Controls, never by
    unchecking every row and pressing OK - a real constraint of the underlying picker, not a Novulon
    limitation invented here."""
    nav = menukit.stack.for_connection(connection)
    try:
        picked_objs = dialog.get_result_rows()
    except Exception:
        picked_objs = None
    if picked_objs:
        picked_sims = [by_identity[id(o)] for o in picked_objs if id(o) in by_identity]
        if picked_sims:
            page_ids = set(s.id for s in order)
            checked_ids = set(s.id for s in picked_sims)
            nav.tray = menukit.stack.apply_selection_delta(nav.tray, page_ids, checked_ids)
    menukit.show_page(connection, _build_controls_page(connection), push=False)


# ------------------------------------------------------------------ 5.4 the Sim Card
def _show_sim_card(connection, sim_info):
    try:
        from ui.ui_dialog_picker import UiSimPicker, SimPickerRow
        from sims4.localization import LocalizationHelperTuning as L
    except Exception:
        common.log_exception('sims.browser: importing UiSimPicker/SimPickerRow (card)')
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return

    age_pairs, occult_pairs, species_pairs = _label_pairs()
    badge_pairs = _badge_occult_pairs(occult_pairs)
    active_household_id = _active_household_id()
    full_name = getattr(sim_info, 'full_name', '') or ('Sim %s' % sim_info.id)
    subtitle_line = query.subtitle_for(sim_info, age_pairs, species_pairs, _household_name(sim_info))
    badges = query.badges_for(sim_info, age_pairs, badge_pairs, active_household_id)
    badge_line = ' • '.join(badges)

    try:
        dlg = UiSimPicker.TunableFactory().default(
            None,
            title=(lambda *_a, **_k: L.get_raw_text(full_name)),
            subtitle=(lambda *_a, **_k: L.get_raw_text(subtitle_line)),
            min_selectable=1, max_selectable=1, display_filter=False)
        row = SimPickerRow(
            sim_id=sim_info.id, select_default=False, sim_location=None,
            household_id=getattr(sim_info, 'household_id', None),
            name=L.get_raw_text(full_name), row_description=L.get_raw_text(badge_line))
        dlg.add_row(row)

        def _on_response(dialog):
            # Same reasoning as `_open_sim_list`'s own `_on_response` just above: this callback is the
            # raw game dialog-response handler, and `_dispatch_sim_card`'s trailing `menukit.show_page`
            # calls can raise `ValueError` for an unregistered row - guard it here too.
            try:
                _dispatch_sim_card(connection, sim_info.id, dialog)
            except Exception:
                common.log_exception('sims.browser: sim card response')
                menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)

        dlg.show_dialog(on_response=_on_response)
    except Exception:
        common.log_exception('sims.browser: showing the Sim card')
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)


def _dispatch_sim_card(connection, sim_id, dialog):
    try:
        picked = dialog.get_result_rows()
    except Exception:
        picked = []
    result = None
    if picked:
        result = commands.do('novulon.sims.card.open_actions', connection, str(sim_id))
    if isinstance(result, Page):
        menukit.show_page(connection, result, push=True)
        return
    if picked and result is None:
        menukit.notify('Nothing changed.', 'Sim actions are not available yet.')
    menukit.show_page(connection, _build_controls_page(connection), push=False)


def _open_actions_for_card(connection, sim_id_text='', *args):
    """Body of `novulon.sims.card.open_actions` - the Sim Card's one interactive button
    (`commands.py`'s own docstring names this exact case: "a Sim Card button" is one of the things
    that should be registered under a stable action id, even though the Card itself isn't a menukit
    Row). Hands off to BP5's `sims/actions.py` the same way the bulk chooser does."""
    sim_id = _to_int(sim_id_text)
    if sim_id is None:
        return None
    return commands.do('novulon.sims.selection_action', connection, str(sim_id))


# ------------------------------------------------------------------ registration (run at import time)
def _register_commands():
    commands.add('novulon.sims.category.males', _open_males)
    commands.add('novulon.sims.category.females', _open_females)
    commands.add('novulon.sims.category.pets', _open_pets)
    commands.add('novulon.sims.category.all', _open_all)
    commands.add('novulon.sims.category.advanced', _open_advanced_fresh)
    for name in _LIFE_STAGE_ORDER:
        commands.add('novulon.sims.advanced.life.%s' % name, _LIFE_STAGE_TOGGLES[name])
    for name in _OCCULT_ORDER:
        commands.add('novulon.sims.advanced.occult.%s' % name, _OCCULT_TOGGLES[name])
    for key in ('played', 'npc', 'here'):
        commands.add('novulon.sims.advanced.status.%s' % key, _STATUS_TOGGLES[key])
    commands.add('novulon.sims.advanced.household', open_household_picker)
    commands.add('novulon.sims.advanced.show_results', _row_show_results)
    commands.add('novulon.sims.advanced.unavailable', _noop)
    commands.add('novulon.sims.household.pick', _noop)   # each row's own closure differs; this is
                                                          # only the console-command/registration
                                                          # fallback for the shared row id
    commands.add('novulon.sims.household.clear', _clear_household)
    commands.add('novulon.sims.household.prev_page', _household_prev_page)
    commands.add('novulon.sims.household.next_page', _household_next_page)
    commands.add('novulon.sims.controls.view_select', _row_view_select)
    commands.add('novulon.sims.controls.search', _row_search)
    commands.add('novulon.sims.controls.prev_page', _row_prev_page)
    commands.add('novulon.sims.controls.next_page', _row_next_page)
    commands.add('novulon.sims.controls.change_filters', _row_change_filters)
    commands.add('novulon.sims.controls.view_card', _row_view_card)
    commands.add('novulon.sims.controls.choose_action', _row_choose_action)
    commands.add('novulon.sims.controls.clear_selection', _row_clear_selection)
    commands.add('novulon.sims.card.open_actions', _open_actions_for_card)


_register_commands()

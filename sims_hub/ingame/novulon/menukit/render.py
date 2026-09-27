"""The only file that imports `ui.ui_dialog_picker`/`ui.ui_dialog` directly (SPEC.md `menukit/` §4).

`show_page`/`refresh`/`go_back` are what every feature package calls; they drive a `stack.NavStack` and
build a `UiObjectPicker` from a `Page`, wiring `dialog.response`/`get_result_rows()` back into Back /
search / row activation / the persistent multi-select tray automatically, so no feature package ever
touches `ui.ui_dialog_picker` itself (SPEC.md §4's own reason for centralizing this: "so no one
improvises their own dialog chaining", the exact trap `mccc_features.md` §5 documents MCCC falling into).

Everything below is verified directly against THIS installed game build with `sims_hub/tools/pyc37.py
"E:/The Sims 4/Data/Simulation/Gameplay/simulation.zip" ui/ui_dialog_picker.pyc <name>` (kept brief here;
the full disassembly transcripts are in this package's build report, not duplicated in every comment):

  * `UiObjectPicker._validate_row` (line 1915) requires `isinstance(row, ObjectPickerRow)`.
    `UiSimPicker._validate_row` (line 1752) requires `isinstance(row, SimPickerRow)`. These two picker
    dialogs are MUTUALLY EXCLUSIVE about row type - a `UiObjectPicker` cannot carry `SimPickerRow`s or a
    bare `BasePickerRow`, and vice versa. This is new information beyond `game_api.md`'s own pass (which
    listed both row/dialog classes but never checked whether they could mix). It is why `Row`/`Page`
    here only ever build `ObjectPickerRow`s through `UiObjectPicker` - a Sim Browser row (BP4,
    `sims/browser.py`) needs its own `UiSimPicker` + `SimPickerRow` construction outside this file, and
    should reuse `paging.py`/`search.py`/`stack.py`'s pure logic (and `stack.apply_selection_delta`)
    rather than reinvent them, exactly the way this file does.
  * `BasePickerRow.__init__`'s defaults (read from its class body's own `MAKE_FUNCTION` default tuple,
    not guessed): `option_id=None, is_enable=True, is_enable_fresh=True, is_enable_prepped=True,
    is_enable_both_fresh_prepped=True, name=None, icon=None, row_description=None, row_tooltip=None,
    tag=None, icon_info=None, pie_menu_influence_by_active_mood=False, is_selected=False, tag_list=None,
    second_tag_list=None, ...` - EVERY field defaults, so a bare `ObjectPickerRow()` is legal.
    `ObjectPickerRow.__init__` calls `super().__init__(**kwargs)` first, then sets its own 20 fields
    (`object_id=None, def_id=None, count=1, ..., object_picker_style=ObjectPickerStyle.DEFAULT,
    is_enable=True, ...`, also all defaulted) - so `ObjectPickerRow(option_id=None, name=...,
    row_description=..., is_enable=..., is_selected=..., object_picker_style=...)` is a fully verified,
    safe direct construction (no `.TunableFactory()` needed for row objects - only the top-level dialog
    classes use that pattern, confirmed by these being plain `__init__`s with real Python defaults).
  * `BasePickerRow.populate_protocol_buffer` (line 293) disassembles to: `name`/`row_description` are
    stored DIRECTLY onto the outgoing message (`base_row_data.name = name_override`,
    `base_row_data.description = self.row_description`) - NOT called. `row_tooltip` (and
    `tooltip_only_prepped`/`tooltip_both_fresh_prepped`) IS called with no arguments
    (`LOAD_METHOD row_tooltip; CALL_METHOD 0`) before being stored. This is a real, easy-to-get-backwards
    asymmetry with `UiDialog`'s own `title`/`text`/`subtitle` fields, which ARE always callables (see
    `confirm.py`'s docstring) - `name=`/`row_description=` here are plain `get_raw_text(...)` VALUES,
    `row_tooltip=` is a zero-arg callable.
  * `ObjectPickerStyle` (line 562): `DEFAULT = 0, NUMBERED = 1, DELETE = 2`.
  * `ObjectPickerType` (line 59): `OBJECT = 4, OBJECT_LARGE = 12` (among others) - `style='list'` uses
    `OBJECT`, `style='tiles'` uses `OBJECT_LARGE` (Main Menu only, per SPEC.md §4).
  * `UiDialogObjectPicker.add_row` (line 1396): `if row.option_id is None: row.option_id =
    len(self.picker_rows)` - **option_id auto-assigns to insertion order** when left `None` (this
    package's own rows always leave it `None`), so `render.py` never has to invent/track ids itself; it
    just keeps its own same-order Python list to map a returned row back to its `menukit.Row`.
  * `UiDialogObjectPicker.get_result_rows` (line 1464): returns the actual `ObjectPickerRow` OBJECTS
    (not bare ids) whose `option_id in self.picked_results`, in original insertion order - `render.py`
    maps these back to `menukit.Row`s by Python object identity (`id(obj)`), not by re-deriving an
    index, so it can never desync even if that assumption changed.
  * `UiDialogObjectPicker.build_object_picker` (line 1499) disassembles to
    `picker_data_max_selectable = self.max_selectable if isinstance(self.max_selectable, int) else
    self.max_selectable.get_max_selectable(self, self._resolver)` - **a plain Python int for
    `max_selectable` is explicitly, natively supported**, a fast path in the engine's own code, not an
    inferred behavior. This fully closes `game_api.md`'s open item 4 / `gaps.md` §B.6's "min_selectable/
    max_selectable as plain int" question, at least for the plain-int path menukit always uses (never a
    `_MaxSelectableXxx` tunable variant object). `self.min_selectable` is read with no such branch - a
    plain value is the only supported shape, so `Page.__init__` (page.py) always resolves both fields to
    a concrete int before they ever reach here (never `None` - see page.py's own comment: the engine's
    `multi_select` property does a raw `self.min_selectable < 1` comparison that would crash on `None`).
  * `UiDialog.show_dialog` (`ui/ui_dialog.pyc:991`) disassembles to: `caller_id=owner.id` only on the
    `ALARM`/`PIVOTAL_MOMENT` phone-ring branches (and returns `None`, i.e. never shows, if that owner is
    `None`); the default branch (any other `phone_ring_type`, which menukit never sets) uses
    `caller_id=self._target_sim_id` instead. So `owner=None` is safe for a picker dialog under
    menukit's own default phone-ring settings - the same precedent already proven working in this repo
    (`speedkit_monitor/common.py:notify()` passes `owner=None` to a different dialog class, but the same
    `UiDialogBase.show_dialog`/`.TunableFactory().default(None, ...)` construction pattern).
  * `UiDialogBase.show_dialog(self, on_response)` (line 692): `self.add_listener(on_response)` then
    `services.ui_dialog_service().dialog_show(self, self.get_phone_ring_type(), **kwargs)` - confirms
    `services.ui_dialog_service()` is the real dispatch call (also independently present in
    `services/__init__.pyc:937`, cited in `game_api.md` §3).

Row icons (`Row.icon`): left `None` in every page menukit itself builds (main menu tiles/action lists),
except the Back row, whose glyph (`design/logo/icon-back.svg`, SPEC.md §17) needs a resource key this
pass could not verify a safe runtime shape for (the "symbolic resource_key type:group" convention
`novulon_tuning.py`/BP13 use is for TUNING XML fields, a different resolution path from a row's raw
`icon` attribute at Python construction time - not the same mechanism, not assumed to be). Cut for V1,
noted in this package's build report rather than guessed at; `BasePickerRow.icon=None` is itself the
fully verified, safe default (`populate_protocol_buffer`'s own `if self.icon is not None:` guard).
"""
from . import confirm as _confirm
from . import notify as _notify
from . import page as _page
from . import search as _search
from . import stack as _stack

BACK_ID = _stack.BACK_ID
SEARCH_ID = _stack.SEARCH_ID


def show_page(connection, page, push=True, connection_owner=None):
    """Push (or, with `push=False`, replace-top-in-place - a filter chip/page-turn rebuild) `page` and
    display it. This is the one function feature packages call to open or update a menu screen."""
    nav = _stack.for_connection(connection)
    if push:
        nav.push(page)
    else:
        nav.replace_top(page)
    _render(connection, nav, connection_owner)


def refresh(connection, connection_owner=None):
    """Re-render whatever is currently on top, unchanged - e.g. after a background state change."""
    nav = _stack.for_connection(connection)
    if nav.current() is not None:
        _render(connection, nav, connection_owner)


def go_back(connection, connection_owner=None):
    """Pop and re-render, the same thing a Back row tap does - exposed for a feature that wants to
    programmatically back out (e.g. after a bulk action finishes)."""
    nav = _stack.for_connection(connection)
    nav.pop()
    if nav.current() is not None:
        _render(connection, nav, connection_owner)


def _render(connection, nav, connection_owner):
    page = nav.current()
    if page is None:
        return
    try:
        from ui.ui_dialog_picker import UiObjectPicker, ObjectPickerRow, ObjectPickerStyle, ObjectPickerType
        from sims4.localization import LocalizationHelperTuning as L
    except Exception:
        _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return

    rows = nav.rows_for_render(page)
    if page.search and not page.multi_select:
        rows = [_search.row_for(nav.state.get('search_query'))] + rows

    picker_type = ObjectPickerType.OBJECT_LARGE if page.style == 'tiles' else ObjectPickerType.OBJECT
    row_style = ObjectPickerStyle.DELETE if page.row_style == 'delete' else ObjectPickerStyle.DEFAULT

    order = []            # menukit.Row, in the exact order added to the dialog
    by_identity = {}       # id(built ObjectPickerRow) -> menukit.Row

    dlg_kwargs = dict(
        title=(lambda *_a, **_k: L.get_raw_text(nav.title_for(page))),
        picker_type=picker_type,
        min_selectable=page.min_selectable,
        max_selectable=page.max_selectable)
    if page.subtitle:
        subtitle_text = page.subtitle
        dlg_kwargs['subtitle'] = lambda *_a, **_k: L.get_raw_text(subtitle_text)

    try:
        dlg = UiObjectPicker.TunableFactory().default(connection_owner, **dlg_kwargs)
        for row in rows:
            built = _build_row(row, row_style, L)
            dlg.add_row(built)
            order.append(row)
            by_identity[id(built)] = row

        def _on_response(dialog):
            # `_dispatch` is invoked directly by the game's own dialog-response dispatch (this
            # function IS the raw on_response callback) - it must never raise out to that caller.
            # `_dispatch`/`_dispatch_multi` already guard `dialog.get_result_rows()` and the row's/
            # page's own `on_activate`/`on_select`, but the PUSH of whatever Page that returns
            # (`show_page(..., push=True, ...)` -> `NavStack.push` -> `validate_page`, which raises
            # `ValueError` for an unregistered row id) happens after that inner guard and was not
            # itself covered - a single missed `commands.add()` in any feature package (a real bug
            # already found once in this mod, `sims.actions.needs.fill_all`) would otherwise raise
            # straight out of this callback instead of degrading to a toast.
            try:
                _dispatch(connection, nav, page, order, by_identity, dialog, connection_owner)
            except Exception:
                _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)

        dlg.show_dialog(on_response=_on_response)
    except Exception:
        _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)


def _build_row(row, row_style, L):
    from ui.ui_dialog_picker import ObjectPickerRow
    kwargs = {
        'is_enable': row.enabled,
        'is_selected': bool(row.selected),
        'object_picker_style': row_style,
        'name': L.get_raw_text(row.label),
    }
    if row.description:
        kwargs['row_description'] = L.get_raw_text(row.description)
    tooltip_text = row.tooltip or row.disabled_text
    if tooltip_text:
        kwargs['row_tooltip'] = (lambda _t=tooltip_text: L.get_raw_text(_t))
    if row.icon is not None:
        kwargs['icon'] = row.icon
    return ObjectPickerRow(**kwargs)


def _dispatch(connection, nav, page, order, by_identity, dialog, connection_owner):
    try:
        picked_objs = dialog.get_result_rows()
    except Exception:
        return   # closed with nothing picked - leave everything exactly as it was
    picked = [by_identity[id(o)] for o in picked_objs if id(o) in by_identity]
    if not picked:
        return

    if page.multi_select:
        _dispatch_multi(connection, nav, page, order, picked, connection_owner)
        return

    row = picked[0]
    if row.id == BACK_ID:
        nav.pop()
        _render(connection, nav, connection_owner)
        return
    if row.id == SEARCH_ID:
        _open_search(connection, nav, connection_owner)
        return
    if row.on_activate is None:
        return
    try:
        result = row.on_activate(connection)
    except Exception:
        _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return
    if isinstance(result, _page.Page):
        show_page(connection, result, push=True, connection_owner=connection_owner)


def _dispatch_multi(connection, nav, page, order, picked, connection_owner):
    page_ids = [r.id for r in order if r.id not in (BACK_ID, SEARCH_ID)]
    checked_ids = [r.id for r in picked if r.id not in (BACK_ID, SEARCH_ID)]
    nav.tray = _stack.apply_selection_delta(nav.tray, page_ids, checked_ids)
    if page.on_select is None:
        return
    try:
        result = page.on_select(connection, sorted(nav.tray, key=str))
    except Exception:
        _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return
    if isinstance(result, _page.Page):
        show_page(connection, result, push=True, connection_owner=connection_owner)


def _open_search(connection, nav, connection_owner):
    def _on_result(query):
        nav.state['search_query'] = query or None
        _render(connection, nav, connection_owner)
    _search.open_search_box(connection, nav.state.get('search_query'), _on_result,
                             connection_owner=connection_owner)


# Re-exported so a feature package that needs the staged-delete confirmation flow (sims/delete.py,
# BP6) never imports ui.ui_dialog directly either.
confirm_delete = _confirm.confirm_delete
notify = _notify.notify

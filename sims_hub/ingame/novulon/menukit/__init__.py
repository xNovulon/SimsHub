"""menukit - Novulon's dialog framework (SPEC.md `menukit/` §4, build package BP2).

This is the ONE place that builds a `ui.ui_dialog_picker`/`ui.ui_dialog` dialog. Every other Novulon
package (sims/, household/, gameplay/, relationships/, adult/, settings_ui/) builds `Page`/`Row` objects
and calls `menukit.show_page` - never imports `ui.*` itself. That is the whole point: SPEC.md §4 exists
because MCCC's own menu code (`mccc_features.md` §5) never had this shared layer, so every module
invented its own filter/paging/search chaining. Don't repeat that here.

QUICK START for a feature builder
----------------------------------
    from novulon import menukit
    from novulon.menukit import Row, Page

    def _open_my_screen(connection, selected_ids=None):
        return Page('My Screen', [
            Row('my.thing.one', 'Do the thing', description='Short, natural, no first person.',
                on_activate=_do_the_thing),
        ], breadcrumb=('Gameplay', 'My Screen'))

    def _do_the_thing(connection, selected_ids=None):
        menukit.notify('Done.', 'The thing happened.')
        return None   # None = "handled it myself, don't push another page"

    commands.add('my.thing.one', _do_the_thing)   # (core, BP1) - see "Every row needs a command" below
    commands.add('my.open_screen', _open_my_screen)
    menukit.show_page(connection, _open_my_screen(connection))

THE PIECES
----------
  * `Row(id, label, description='', tooltip='', icon=None, disabled_text=None, selected=False,
    tags=(), sim_id=None, household_id=None, on_activate=None)` (page.py) - one row. `on_activate
    (connection, selected_ids=None) -> Page | None`: return a `Page` to push it, or `None` if the row
    already did everything itself (showed its own confirm/notify, or is a filter chip that mutated
    state and wants a re-render - call `menukit.show_page(connection, new_page, push=False)` yourself
    for that last case, from inside `on_activate`).
  * `Page(title, rows, breadcrumb=(), subtitle=None, multi_select=False, min_selectable=None,
    max_selectable=None, search=False, style='list', row_style='default', on_select=None)` (page.py) -
    one screen. `style='tiles'` is Main Menu-only (OBJECT_LARGE cards); everything else is `'list'`.
    `row_style='delete'` is `sims/delete.py`'s only expected caller. `search=True` gets a pinned
    "Search…" row for free - read the query back from `nav.state['search_query']` inside your own
    filter-building code (see "Filters, search and paging" below), you don't build the search UI
    yourself. `on_select(connection, tray_ids) -> Page | None` fires once when a multi_select page's OK
    response comes back (see "Multi-select tray" below) - unused for single-select pages.
  * `menukit.show_page(connection, page, push=True, connection_owner=None)` - open (`push=True`) or
    rebuild-in-place (`push=False`) a page. This is the ONLY function most feature code ever calls.
    `menukit.refresh(connection)` re-renders the current page unchanged; `menukit.go_back(connection)`
    does what a Back tap does, programmatically (e.g. after a bulk action finishes).
  * `menukit.confirm_delete(connection, sim_infos, protected_note=(), on_confirm=None, title=...)`
    (confirm.py) - the named-list delete confirmation, capped at 10 + "+N more" (SPEC.md §5.6). Always
    use this for a delete - never build your own `UiDialogOkCancel`.
  * `menukit.notify(title, text, urgent=False)` (notify.py) - a toast with Novulon's fixed defaults
    (PLAYER level, INFORMATION visual type, DEFAULT urgency; `urgent=True` for a genuine failure only).
  * `paging.page_of(items, page_size, page_index) -> (rows, has_prev, has_next)` /
    `paging.footer_text(n_items, page_size, page_index)` - pure Python, filter/search FIRST, then page
    the result (SPEC.md §4/§5.3, `gaps.md` §B.2 - there is no native row-count ceiling, so never build
    the full unfiltered row set before paging). Page size 60-100 (`paging.DEFAULT_PAGE_SIZE = 80`).
  * `search.apply(items, query, key=None)` - pure substring filter for whatever you paged (case
    insensitive). `search.SEARCH_ID` is the synthetic row id `render.py` recognizes automatically.
  * `stack.for_connection(connection).state` - a plain per-connection `dict` that survives a filter
    change or page turn (SPEC.md §4): put your current filter flags, search query, and page index here,
    not on the `Page` object itself (a fresh `Page` is built every render). `.tray` is the persistent
    multi-select `set()` (see below). `stack.for_connection(connection).title_for(page)` computes the
    "Novulon › Sims › Females" breadcrumb title from `Page.breadcrumb` if you ever need it outside of
    `render.py` (you normally won't).

FILTERS, SEARCH AND PAGING - THE PATTERN EVERY LIST SCREEN FOLLOWS
--------------------------------------------------------------------
    def _build_list_page(connection):
        nav = menukit.stack.for_connection(connection)
        query = nav.state.get('search_query')
        page_index = nav.state.get('page_index', 0)
        items = _all_items()                                   # cheap iterable/generator, not a list yet
        items = [i for i in items if _matches_filters(i, nav.state)]   # your own filter predicate
        items = menukit.search.apply(items, query, key=lambda i: i.name)
        rows, has_prev, has_next = menukit.paging.page_of(items, menukit.paging.DEFAULT_PAGE_SIZE, page_index)
        page_rows = [_row_for(i) for i in rows]
        if has_prev:
            page_rows.append(Row('my.list.prev_page', 'Previous Page', on_activate=_prev_page))
        if has_next:
            page_rows.append(Row('my.list.next_page', 'Next Page', on_activate=_next_page))
        return Page('My List', page_rows, subtitle=menukit.paging.footer_text(len(items), ..., page_index),
                    search=True)

    def _next_page(connection, selected_ids=None):
        nav = menukit.stack.for_connection(connection)
        nav.state['page_index'] = nav.state.get('page_index', 0) + 1
        menukit.show_page(connection, _build_list_page(connection), push=False)   # rebuild, don't push
        return None
A filter-chip row follows the exact same shape as `_next_page`: mutate `nav.state`, rebuild the page,
`show_page(..., push=False)`, return `None`. The pinned Search row is wired for you already - your
`on_activate` functions never see it.

MULTI-SELECT TRAY (persistent across a filter change or page turn)
--------------------------------------------------------------------
Build the page with `multi_select=True` (an explicit `max_selectable` int, or leave it unset for
unlimited) and set each row's `selected=(item.id in nav.tray)` from your OWN tray-membership check
before returning the `Page`, so a Sim/item already picked on a previous page view still shows checked.
`render.py` reads the dialog's OK response, computes which of THIS PAGE's rows are now checked vs. were
before, and folds only that delta into `nav.tray` (`stack.apply_selection_delta` - ids from other
pages/filters are left untouched), then calls your `Page.on_select(connection, tray_ids)` with the full,
cross-page tray. This is the exact mechanism the Sim Browser's "N Selected" flow needs (SPEC.md §5.3) -
a generic `Row`/`Page` multi-select page (e.g. a household inventory picker) gets it for free the same
way. NOTE: a Sim Browser row itself (with a live portrait) is NOT a generic `Row` - see below.

Sim Browser rows are NOT built through this file (verified, not a stylistic choice)
--------------------------------------------------------------------------------------
`ui.ui_dialog_picker.UiObjectPicker` only accepts `ObjectPickerRow`s; `UiSimPicker` only accepts
`SimPickerRow`s (`render.py`'s docstring has the disassembly). `Page`/`Row`/`render.py` here cover
every menu/action/tile/confirmation screen in the mod, but a Sim Browser row (with a live-resolved
portrait) needs `sims/browser.py` (BP4) to build its own `UiSimPicker` directly. Reuse
`stack.for_connection`, `paging.page_of`, `search.apply`, and `stack.apply_selection_delta` from there
too - only the final dialog-construction call differs.

EVERY ROW NEEDS A COMMAND (SPEC.md §3.7/§4)
----------------------------------------------
A `Row.id` must already be registered with `commands.add(action_id, fn)` (core, BP1) before you build a
`Page` containing it - `menukit.stack.push`/`replace_top` (and therefore `show_page`) RAISES
`ValueError` if a row's id has no matching command. This is what makes every menu action ALSO a
`novulon.do <action_id>` console command and a directly-callable Tier-4 test target, with no duplicate
code path. Register once, at import time, next to the function it names; the synthetic Back/Search rows
are exempt automatically. If `commands.py` isn't loadable yet (a build-order issue only, never expected
once the mod is finished), the check degrades to a no-op with a log line rather than blocking every
other package's own development - `stack.set_command_checker(fn)` lets a test (or `commands.py` itself,
eventually) inject the real/fake check explicitly.

WHAT MENUKIT DOES NOT DO
--------------------------
It never imports feature-specific game modules (`sims.sim_info`, `traits.trait_commands`, ...) - it only
knows about `Row`/`Page` and the handful of generic EA dialog/localization classes cited in each file's
own docstring. It never decides WHAT a menu contains - that is 100% up to the feature package. It never
retries/guesses at an unverified API shape; the one place that does something best-effort
(`search.open_search_box`'s `text_inputs=` construction, SPEC.md §18) is wrapped to degrade to "no
crash, no search this time" rather than assert it works.
"""
from .page import Row, Page, BACK_ID
from . import paging, search, stack   # exposed as modules - menukit.paging.page_of(...), etc.
from .render import show_page, refresh, go_back, confirm_delete, notify, SEARCH_ID

__all__ = [
    'Row', 'Page', 'BACK_ID', 'SEARCH_ID',
    'paging', 'search', 'stack',
    'show_page', 'refresh', 'go_back', 'confirm_delete', 'notify',
]

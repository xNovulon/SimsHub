"""The pinned search row and text-input round trip (SPEC.md `menukit/` §4).

`row_for`/`apply` are pure Python: no live keystroke filtering exists in this engine
(`ux_ideas.md` §1.5, confirmed absent - there is no per-character search callback anywhere in
`ui_dialog_picker.pyc`), so "search" is really "open a text box, get one string back, rebuild the page
at page 0 with that string as a query" - `apply()` is that last, pure step (matching against whatever
plain-Python predicate the caller supplies), independent of how the string was obtained.

`open_search_box` is the one function that touches the game, and it is the one item this whole package
could not fully verify (SPEC.md §18, `game_api.md` §2 open item 3, `gaps.md` §B.6): the exact `dict`- vs
attribute-style shape `UiDialogTextInputOkCancel` expects for its `text_inputs=` constructor kwarg.

What IS verified, directly, against `ui/ui_dialog_generic.pyc` (`sims_hub/tools/pyc37.py
"E:/The Sims 4/Data/Simulation/Gameplay/simulation.zip" ui/ui_dialog_generic.pyc <name>`):
  * `UiDialogTextInputOkCancel(UiDialogTextInput, UiDialogOkCancel)` (line 112) - an empty-body mixin;
    the class exists and is exactly what the vanilla "rename a Sim"/"cheat set skill level" text-entry
    dialogs use (`game_api.md` §2's citations, not re-walked here).
  * `UiDialogTextInput.on_text_input(self, text_input_name, text_input)` (line 44) disassembles to
    `if hasattr(self.text_inputs, text_input_name): self.text_input_responses[text_input_name] =
    text_input; return True` - **`hasattr`, not a dict membership test** - `self.text_inputs` is read as
    an object with the input's name as an ATTRIBUTE, not a dict key. This is new information this pass
    adds beyond `game_api.md`'s own citation (which quoted this line but didn't flag the
    attribute-vs-dict distinction) - it rules out passing a plain `{'search': ...}` dict for
    `text_inputs=` and is why `open_search_box` below builds a tiny attribute-holder object instead.
  * `ui/ui_text_input.pyc` (line 111) - `UiTextInput.__init__(self, sort_order)` (line 170) - the class
    exists; its own defaults were not walked (out of scope for one already-flagged, gracefully-degrading
    open item), so this file calls `.TunableFactory().default()` with no overrides, the same
    zero-argument-safe pattern relied on everywhere else the "every field defaults to None/a sane value"
    behavior has been independently verified (SPEC.md/`render.py`'s own citations).
  * Read-out after response: `dialog.text_input_responses.get('search')` (`game_api.md` §2, unchanged).

`open_search_box` is wrapped so ANY mismatch in the shape above - a wrong kwarg name, a construction
`TypeError`, a missing attribute at response time - degrades to "does nothing this call" with one log
line, never a crash (SPEC.md §4's own instruction for this exact open item). This is not a guess shipped
as fact: it is a best-effort attempt at the one shape the disassembly above narrows to, gated entirely
behind a try/except that assumes it might be wrong.
"""
from . import page as _page

SEARCH_ID = '__search__'


def row_for(query=None):
    """The pinned 'Search…' row for a Page that declares `search=True`. Subtext remembers the last
    query, per SPEC.md §4: 'Search… (last: "Bob")'. This is a synthetic row like the Back row - `id`
    is fixed (`SEARCH_ID`) and `render.py` recognizes it and opens the search box itself; it carries no
    `on_activate` of its own."""
    label = 'Search…' if not query else 'Search… (last: "%s")' % query
    return _page.Row(SEARCH_ID, label)


def apply(items, query, key=None):
    """Pure substring filter (case-insensitive): keeps items whose `key(item)` (default: `str(item)`)
    contains `query`. Empty/None query returns `items` unchanged. No game import - this is what a
    feature package's own filter pipeline calls after `open_search_box` hands back a query string, and
    it is what every Tier-1 test in this package exercises directly."""
    if not query:
        return list(items)
    q = query.strip().lower()
    if not q:
        return list(items)
    key = key or (lambda x: str(x))
    return [item for item in items if q in key(item).lower()]


class _Inputs(object):
    """Attribute-holder for `UiDialogTextInputOkCancel(text_inputs=...)` - `on_text_input` checks
    `hasattr(self.text_inputs, name)`, so this needs to expose `search` as an attribute, not a dict key
    (see module docstring)."""

    def __init__(self, **fields):
        self.__dict__.update(fields)


def open_search_box(connection, current_query, on_result, connection_owner=None,
                     title='Search', text='Type a name.'):
    """Show the text-entry dialog and call `on_result(query_or_None)` once the player responds.

    Degrades safely (logs, calls `on_result(None)`, returns False) if the text-input shape this build
    expects doesn't match what was disassembled - never raises into the caller (SPEC.md §4/§18)."""
    try:
        from ui.ui_dialog_generic import UiDialogTextInputOkCancel
        from ui.ui_text_input import UiTextInput
        from sims4.localization import LocalizationHelperTuning as L
    except Exception:
        _log('menukit.search: dialog classes unavailable, ignoring this search')
        on_result(None)
        return False

    try:
        text_input_field = UiTextInput.TunableFactory().default()
        inputs = _Inputs(search=text_input_field)

        def _title(*_a, **_k):
            return L.get_raw_text(title)

        def _text(*_a, **_k):
            return L.get_raw_text(text)

        def _on_response(dialog):
            # Reading the response back and invoking the caller's `on_result` are two separate steps,
            # each guarded on its own - `on_result` used to be called a SECOND time (with `None`) from
            # inside the except clause below when IT was the thing that raised (e.g. `on_result`
            # itself calls `menukit.show_page`, which can raise `ValueError` for an unregistered row),
            # which was both a wrong "recovery" (silently re-running the caller's callback with
            # different input) and left that second, retried call completely unguarded - an exception
            # from it would still reach this function's caller, the game's own dialog dispatch, exactly
            # the "unguarded callback" this whole mod's hard rules forbid.
            try:
                responses = getattr(dialog, 'text_input_responses', None) or {}
                query = responses.get('search')
            except Exception:
                _log('menukit.search: reading back the typed query failed')
                query = None
            try:
                on_result(query if query else None)
            except Exception:
                _log('menukit.search: on_result callback raised')

        dlg = UiDialogTextInputOkCancel.TunableFactory().default(
            connection_owner, title=_title, text=_text, text_inputs=inputs,
            text_ok=lambda *a, **k: L.get_raw_text('OK'),
            text_cancel=lambda *a, **k: L.get_raw_text('Cancel'),
            include_cancel_response=True)
        dlg.show_dialog(on_response=_on_response)
        return True
    except Exception:
        _log('menukit.search: text_inputs= construction did not match this build - ignoring (SPEC.md §18)')
        on_result(None)
        return False


def _log(msg):
    try:
        from .. import common
        common.log(msg)
    except Exception:
        pass

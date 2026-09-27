"""Named-list delete confirmation (SPEC.md `menukit/` §4/§5.6).

Split in two, same as every other menukit file:
  * `capped_names`/`display_name`/`format_note` - pure Python, no game import. Take plain names or
    anything SimInfo-shaped (`.full_name`/`.first_name`/`.last_name`/`.id`; a real SimInfo, or a
    FakeSimInfo in a test).
  * `confirm_delete` - the one function that touches the game: builds the bulleted name list via
    `sims4.localization.LocalizationHelperTuning.get_bulleted_list`, the protected-Sim note via
    `get_comma_separated_list`, and shows a `UiDialogOkCancel`.

Never a bare category name - always the real names, capped at 10 + "+N more" (SPEC.md §4/§5.6). This
caps independently of whatever internal limit the engine's own `get_bulleted_list` may apply
(`LocalizationHelperTuning.MAX_LIST_LENGTH`, seen but not decoded in `sims4/localization/__init__.pyc`)
- menukit's own 10-name cap is the one the design spec asks for and the one every caller can rely on.

Verified directly against this build (`sims_hub/tools/pyc37.py`):
  * `sims4/localization/__init__.pyc` (core.zip) - `get_bulleted_list(cls, header_string,
    *localized_strings)` (line 450, varargs; `header_string=None` -> no header row, matches
    disassembly's `if header_string is None` branch) and `get_comma_separated_list(cls, *strings)`
    (line 493, varargs) and `get_raw_text(cls, text)` (line 563, `return cls.RAW_TEXT(text)`).
  * `ui/ui_dialog.pyc` (simulation.zip) - `UiDialog.build_msg`'s own `_build_localized_string_msg`
    (line 1017) disassembles to `string(*tokens, *additional_tokens)` - i.e. `title=`/`text=`/
    `subtitle=` must be CALLABLES (the already-proven `lambda *_a, **_k: get_raw_text(...)` pattern
    from `speedkit_monitor/common.py:notify()`), not pre-built LocalizedStrings - unlike a picker
    row's `name`/`row_description`, which `BasePickerRow.populate_protocol_buffer` stores directly,
    never calls (see `render.py`'s docstring - a real, easy-to-get-backwards asymmetry, checked both
    ways here). `subtitle` is a distinct, independently-settable field from `text` (both handled the
    same way in `build_msg`, line 1151) - used here to carry the "can't be undone"/protected-Sim note
    separately from the bulleted name list.
  * `UiDialogOkCancel.responses()` (line 1397) disassembles to
    `UiDialogResponse(dialog_response_id=ButtonType.DIALOG_RESPONSE_OK, text=self.text_ok, ...)`, a
    Cancel response appended only `if self.include_cancel_response`, confirming `text_ok`/
    `text_cancel`/`include_cancel_response` are the real field names. `UiDialog.__init__(self, owner,
    resolver, target_sim_id)` (line 935); `owner=None` mirrors this repo's own already-working
    precedent (`speedkit_monitor/common.py:notify()` passes `owner=None` to `UiDialogNotification`).
  * `ButtonType.DIALOG_RESPONSE_OK = 10001`, `DIALOG_RESPONSE_CANCEL = 10002` (`ui/ui_dialog.pyc:46`).
"""
from . import notify as _notify

CAP = 10


def display_name(sim_info):
    """Best-effort display name for anything SimInfo-shaped (real or fake)."""
    name = getattr(sim_info, 'full_name', None)
    if name:
        return name
    first = getattr(sim_info, 'first_name', '') or ''
    last = getattr(sim_info, 'last_name', '') or ''
    return (first + ' ' + last).strip() or ('Sim %s' % getattr(sim_info, 'id', '?'))


def capped_names(sim_infos, cap=CAP):
    """(shown_names, remaining_count) - up to `cap` display names, plus how many more there are.
    Pure Python; no game import."""
    names = [display_name(s) for s in sim_infos]
    if len(names) <= cap:
        return names, 0
    return names[:cap], len(names) - cap


def format_note(sim_infos, cap=CAP):
    """Pure-Python fallback rendering of a capped named list as one comma-joined string, e.g.
    'Alex Doe, Sam Lee (+3 more)' - used for the plain-text protected-Sim note, and by tests that
    don't want to stand up the game's own localization module."""
    shown, more = capped_names(sim_infos, cap)
    if not shown:
        return ''
    text = ', '.join(shown)
    if more:
        text += ' (+%d more)' % more
    return text


def comma_list(names):
    """A plain comma-joined `LocalizedString` for `names` (already-capped plain strings), built via the
    real `LocalizationHelperTuning.get_comma_separated_list`/`get_raw_text` - for a feature package that
    wants the engine's own comma-list formatting with no surrounding sentence (unlike
    `confirm_delete`'s own protected-Sim note, which mixes fixed English with the list and so stays
    plain text - see `confirm_delete`'s docstring). Returns None if `names` is empty; raises whatever
    the game import raises if called outside the game (callers already run inside a `common.guarded()`
    entry point, per every other menukit/game-facing function)."""
    from sims4.localization import LocalizationHelperTuning as L
    if not names:
        return None
    tokens = [L.get_raw_text(n) for n in names]
    if len(tokens) == 1:
        return tokens[0]
    return L.get_comma_separated_list(*tokens)


def confirm_delete(connection, sim_infos, protected_note=(), on_confirm=None, title='Delete %d Sims?',
                    connection_owner=None):
    """`UiDialogOkCancel` confirmation listing the real Sims a delete would remove (SPEC.md §5.6).

    `sim_infos`: the Sims that WILL be deleted if confirmed (already filtered - never protected ones).
    `protected_note`: Sims that were dropped from the batch because they're protected (active
    household/active Sim) - shown as one extra informational line, capped the same way, never blocking
    the rest of the batch (SPEC.md §5.6: "Novulon silently drops them rather than blocking the whole
    batch").
    `on_confirm(connection)`: called if/when the player presses Delete. Novulon's red Delete-button
    tuning (SPEC.md §5.6's "the only place in the whole mod that uses a color outside the brand/section
    palette") is dialog CHROME, not a constructor field found anywhere in `ui_dialog.pyc` - out of
    scope for this framework call; noted as a look-and-feel follow-up, not a guessed API.
    Returns True if the dialog was shown, False if it degraded safely (never raises to the caller).
    """
    try:
        from ui.ui_dialog import UiDialogOkCancel, ButtonType
        from sims4.localization import LocalizationHelperTuning as L
    except Exception:
        _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False

    shown, more = capped_names(sim_infos, CAP)
    if not shown:
        _notify.notify('Nothing was deleted.', 'Every selected Sim is protected.')
        return False

    name_tokens = [L.get_raw_text(n) for n in shown]
    if more:
        name_tokens.append(L.get_raw_text('+%d more' % more))
    bulleted = L.get_bulleted_list(None, *name_tokens)

    subtitle_body = "This can't be undone."
    if protected_note:
        # format_note() is the same pure helper the Tier-1 tests exercise without the game; kept as
        # plain text here (not get_bulleted_list/get_comma_separated_list) because this sentence mixes
        # fixed English with an embedded name list, and no verified helper composes the two - see the
        # module docstring for why that specific composition is left as plain get_raw_text rather than
        # guessed at. comma_list() below is the honestly-labeled wrapper for callers who just want a
        # plain comma-joined LocalizedString list with no surrounding sentence.
        subtitle_body += '\nNot deleted: %s (protected).' % format_note(protected_note, CAP)

    def _text(*_a, **_k):
        return bulleted

    def _title(*_a, **_k):
        return L.get_raw_text(title % len(shown) if '%d' in title else title)

    def _subtitle(*_a, **_k):
        return L.get_raw_text(subtitle_body)

    def _on_response(dialog):
        try:
            if dialog.response == ButtonType.DIALOG_RESPONSE_OK and on_confirm is not None:
                on_confirm(connection)
        except Exception:
            _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)

    try:
        dlg = UiDialogOkCancel.TunableFactory().default(
            connection_owner,
            title=_title,
            text=_text,
            subtitle=_subtitle,
            text_ok=lambda *a, **k: L.get_raw_text('Delete'),
            text_cancel=lambda *a, **k: L.get_raw_text('Cancel'),
            include_cancel_response=True)
        dlg.show_dialog(on_response=_on_response)
        return True
    except Exception:
        _notify.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return False

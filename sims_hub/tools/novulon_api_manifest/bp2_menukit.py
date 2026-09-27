"""EA names BP2 (`ingame/novulon/menukit/`) cites, all checked against THIS installed game build's own
`.pyc` with `sims_hub/tools/pyc37.py "E:/The Sims 4/Data/Simulation/Gameplay/{simulation,core}.zip"
<module>.pyc [name]` - never taken on trust from `research/game_api.md`, even where that file already
covered the same class, because this package's own render/confirm/search/notify code depends on exact
field names and default-value behavior `game_api.md` didn't always drill into (see each row's note).

Rows this pass adds beyond what `game_api.md`/`gaps.md` already established (new information, not a
re-citation):
  * `UiObjectPicker`/`UiSimPicker` `_validate_row` bodies - proves the two picker dialogs are mutually
    exclusive about row type (`isinstance(row, ObjectPickerRow)` vs `isinstance(row, SimPickerRow)`).
    Neither `game_api.md` nor `gaps.md` checked whether the two could mix; this shapes menukit's whole
    row model (Sim Browser rows can't go through `Page`/`Row` at all - see `render.py`'s docstring).
  * `ObjectPickerRow`/`BasePickerRow.__init__`'s actual default-value tuples (read from the class body's
    own `MAKE_FUNCTION` const, not inferred) - confirms every field defaults, so a bare
    `ObjectPickerRow(option_id=None, name=..., ...)` construction is safe with no `.TunableFactory()`.
  * `BasePickerRow.populate_protocol_buffer`'s actual body - `name`/`row_description` are stored
    directly (never called), `row_tooltip` IS called with zero args. `game_api.md` didn't disassemble
    this method at all; get this backwards and every row's tooltip silently never resolves (or every
    row's name blows up trying to call a plain LocalizedString).
  * `UiDialogObjectPicker.add_row`'s option_id auto-assignment (`if row.option_id is None:
    row.option_id = len(self.picker_rows)`) and `get_result_rows`'s object-identity-preserving return -
    neither was disassembled by any prior research pass; this is what lets `render.py` avoid inventing
    its own id scheme.
  * `UiDialogObjectPicker.build_object_picker`'s `isinstance(self.max_selectable, int)` fast path -
    closes `game_api.md`'s open item 4 / `gaps.md` §B.6 (plain int for max_selectable) definitively, at
    least for that code path; also reveals `min_selectable`/`multi_select`'s own `< 1` comparison, which
    is why `page.py` never lets either field reach the engine as `None`.
  * `UiDialog.show_dialog`'s actual branching on `phone_ring_type` - `game_api.md` §2's paraphrase
    ("calls `super().show_dialog(caller_id=owner.id, ...)`") is only true on the ALARM/PIVOTAL_MOMENT
    branch; the default branch (what menukit always hits) uses `self._target_sim_id` instead, and the
    ALARM/PIVOTAL_MOMENT branch returns `None` (never shows the dialog) if the resolved owner is `None`.
    This directly justifies `owner=None` being safe for `render.py`'s picker construction.
  * `UiDialogOkCancel.responses()`'s actual body - confirms `text_ok`/`text_cancel`/
    `include_cancel_response` as the real field names (game_api.md paraphrased this one correctly, but
    it wasn't independently re-verified there against THIS build's own bytecode until this pass).
  * `UiDialog.build_msg`'s `_build_localized_string_msg` - proves `title`/`text`/`subtitle` are called
    with `(*tokens)` (must be callables), the opposite convention from a picker row's `name`/
    `row_description`. Also confirms `subtitle` is a distinct, independently settable field from `text`.
  * `UiDialogTextInput.on_text_input`'s `hasattr(self.text_inputs, name)` check - `game_api.md` quoted
    this exact line but didn't flag that `text_inputs` is read via `hasattr` (attribute access), not a
    dict membership test - `search.py`'s best-effort `_Inputs` attribute-holder exists because of this.
  * The three `UiDialogNotification` nested enum bodies, decoded (not left as "cheap to pull later" per
    `game_api.md` §2) - `notify.py`'s fixed defaults depend on the exact int values.

Game build note (matching `bp1_bp3_core_inject.py`'s own manifest file, which found this first):
`novulon_api_check.py`'s own `game_build_version()` reads `Delta\\<pack>\\Version.ini`, which is
`1.126.73.1030` - a different string from the non-Delta `E:/The Sims 4/EP21/Version.ini`'s
`packversion` (`109.0.465.1030`, the value `game_api.md`/this file's own disassembly sessions cited as
"the build identity"). `CHECKED_AGAINST` below uses the Delta value specifically so it matches what a
real `novulon_api_check.py` run compares against; both strings name the exact same installed `.zip`
files - re-run with `python tools/novulon_api_check.py` confirmed all rows below `found`, 0 missing,
against this same build, under either name.
"""

CHECKED_AGAINST = '1.126.73.1030'

MANIFEST = [
    # ui/ui_dialog_picker.pyc (simulation.zip)
    ('ui.ui_dialog_picker', 'ObjectPickerStyle', 'class'),
    ('ui.ui_dialog_picker', 'ObjectPickerStyle.DEFAULT', 'member', 0),
    ('ui.ui_dialog_picker', 'ObjectPickerStyle.NUMBERED', 'member', 1),
    ('ui.ui_dialog_picker', 'ObjectPickerStyle.DELETE', 'member', 2),
    ('ui.ui_dialog_picker', 'ObjectPickerType', 'class'),
    ('ui.ui_dialog_picker', 'ObjectPickerType.OBJECT', 'member', 4),
    ('ui.ui_dialog_picker', 'ObjectPickerType.OBJECT_LARGE', 'member', 12),
    ('ui.ui_dialog_picker', 'BasePickerRow', 'class'),
    ('ui.ui_dialog_picker', 'BasePickerRow.__init__', 'method'),
    ('ui.ui_dialog_picker', 'BasePickerRow.populate_protocol_buffer', 'method'),
    ('ui.ui_dialog_picker', 'ObjectPickerRow', 'class'),
    ('ui.ui_dialog_picker', 'ObjectPickerRow.__init__', 'method'),
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker', 'class'),
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker.__init__', 'method'),
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker.add_row', 'method'),
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker.get_result_rows', 'method'),
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker.build_object_picker', 'method'),
    ('ui.ui_dialog_picker', 'UiDialogObjectPicker.multi_select', 'method'),   # a property, not a field
    ('ui.ui_dialog_picker', 'UiObjectPicker', 'class'),
    ('ui.ui_dialog_picker', 'UiObjectPicker._validate_row', 'method'),
    ('ui.ui_dialog_picker', 'UiSimPicker', 'class'),
    ('ui.ui_dialog_picker', 'UiSimPicker._validate_row', 'method'),
    ('ui.ui_dialog_picker', 'SimPickerRow', 'class'),   # cited only to justify excluding it (render.py)

    # ui/ui_dialog.pyc (simulation.zip)
    ('ui.ui_dialog', 'ButtonType', 'class'),
    ('ui.ui_dialog', 'ButtonType.DIALOG_RESPONSE_CLOSED', 'member', -1),
    ('ui.ui_dialog', 'ButtonType.DIALOG_RESPONSE_OK', 'member', 10001),
    ('ui.ui_dialog', 'ButtonType.DIALOG_RESPONSE_CANCEL', 'member', 10002),
    ('ui.ui_dialog', 'UiDialogBase.show_dialog', 'method'),
    ('ui.ui_dialog', 'UiDialog.__init__', 'method'),
    ('ui.ui_dialog', 'UiDialog.show_dialog', 'method'),
    ('ui.ui_dialog', 'UiDialog.build_msg', 'method'),
    ('ui.ui_dialog', 'UiDialog._build_localized_string_msg', 'method'),
    ('ui.ui_dialog', 'UiDialogOkCancel', 'class'),
    ('ui.ui_dialog', 'UiDialogOkCancel.responses', 'method'),

    # ui/ui_dialog_generic.pyc (simulation.zip)
    ('ui.ui_dialog_generic', 'UiDialogTextInputOkCancel', 'class'),
    ('ui.ui_dialog_generic', 'UiDialogTextInput.on_text_input', 'method'),

    # ui/ui_text_input.pyc (simulation.zip)
    ('ui.ui_text_input', 'UiTextInput', 'class'),
    ('ui.ui_text_input', 'UiTextInput.__init__', 'method'),

    # ui/ui_dialog_notification.pyc (simulation.zip)
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationLevel.PLAYER', 'member', 0),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationLevel.SIM', 'member', 1),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationVisualType.INFORMATION', 'member', 0),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationVisualType.SPEECH', 'member', 1),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationVisualType.SPECIAL_MOMENT', 'member', 2),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationUrgency.DEFAULT', 'member', 0),
    ('ui.ui_dialog_notification', 'UiDialogNotification.UiDialogNotificationUrgency.URGENT', 'member', 1),
    ('ui.ui_dialog_notification', 'UiDialogNotification.build_msg', 'method'),

    # sims4/localization/__init__.pyc (core.zip)
    ('sims4.localization', 'LocalizationHelperTuning.get_raw_text', 'method'),
    ('sims4.localization', 'LocalizationHelperTuning.get_bulleted_list', 'method'),
    ('sims4.localization', 'LocalizationHelperTuning.get_comma_separated_list', 'method'),

    # services/__init__.pyc (simulation.zip) - cited via UiDialogBase.show_dialog's own body, and
    # independently present in this module's own symbol table (game_api.md §3, line 937)
    ('services', 'ui_dialog_service', 'function'),
]

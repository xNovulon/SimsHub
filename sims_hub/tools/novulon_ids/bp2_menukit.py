"""BP2 (`ingame/novulon/menukit/`) mints no resource ids in V1.

SPEC.md §17's asset table assigns `icon-back.svg` to "BP2 (`menukit/stack.py`)" - the synthetic Back
row's glyph. That needs a resource id here (a RAW DDS icon, same pipeline as BP13's own
`ICON_PIE_MENU_32`) plus a verified runtime shape for how a `BasePickerRow.icon=` field actually
references a packaged resource from a plain Python row construction. What IS verified (§14.5-style
"symbolic resource_key type:group" convention) is specific to TUNING XML fields - `novulon_tuning.py`'s
`pie_menu_icon` - a different resolution path from a row's raw `icon` attribute at construction time,
and this pass found no disassembled example of the latter to check against. Cut for V1 rather than
guessed at: `stack.back_row()` builds a `Row` with `icon=None`, itself a fully verified, safe default
(`ui/ui_dialog_picker.pyc: BasePickerRow.populate_protocol_buffer`'s own `if self.icon is not None:`
guard - confirmed directly, see `tools/novulon_api_manifest/bp2_menukit.py`).

This file exists (empty of constants) so a future v1.1 pass that verifies the row-icon resource shape
has an obvious place to add `ICON_BACK_32 = custom_id('Novulon_Icon_Back_32')` without having to
rediscover this reasoning first.
"""

"""BP7 (`ingame/novulon/compat/`) and BP12 (`ingame/novulon/settings_ui/`) mint no resource ids in V1.

SPEC.md Sec 17's asset table assigns `icon-settings.svg` to "BP4/8/9/11/12" - the Settings tile's Main
Menu icon. That needs the same thing BP2's own `novulon_ids/bp2_menukit.py` already found missing for the
Back row's icon: a verified runtime shape for how a `Row.icon=`/`BasePickerRow.icon=` field actually
references a packaged DBPF resource from plain Python construction - not found by any research pass, and
not re-found in this one either (this session's own verification work went into `compat/`'s probe-id/
probe-type correction instead, not the icon path). `settings_ui/menu.py`'s Settings tile ships with
`icon=None`, the same fully-verified, safe default `menukit/stack.py`'s Back row already uses.

This file exists (empty of constants) so a future v1.1 pass that verifies the row-icon resource shape has
an obvious place to add `ICON_SETTINGS_32 = custom_id('Novulon_Icon_Settings_32')` without having to
rediscover this reasoning first.
"""

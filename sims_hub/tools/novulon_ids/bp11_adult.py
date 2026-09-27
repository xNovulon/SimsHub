"""BP11 (`ingame/novulon/adult/`) mints no resource ids in V1.

The Adult tile's Main Menu icon is `design/logo/icon-adult.svg` (SPEC.md Sec.17), but no package has
a verified runtime shape for a `Row.icon=`/tile-row icon actually referencing a packaged DBPF
resource from plain Python construction yet (`novulon_ids/bp2_menukit.py` cut the identical thing for
the Back row's icon, for the identical reason). `adult/menu.py` registers its Main Menu tile with
`icon=None` - the same fully verified, safe default every other section uses until that shape is
confirmed.

Every other string the Adult section shows (the interstitial, the five settings-subgroup labels,
every individual WickedWhims setting's display name, "Stop Everything"/"Resume Autonomy") goes
through `sims4.localization.LocalizationHelperTuning.get_raw_text()` at call time, the same pattern
`common.notify()` already uses live - none of that needs an STBL entry, so this package needs no
`stbl_id()`/`fnv64()` constant either.

This file exists (empty of constants) so a future pass that verifies the row-icon resource shape has
an obvious place to add `ICON_ADULT_32 = custom_id('Novulon_Icon_Adult_32')` without re-deriving this
reasoning first.
"""

"""Ids BP13 (package build: tuning XML, STBL, icon, `dist/Novulon_Tuning.package`) mints.

FNV-1 32/64-bit hashing is already implemented identically three times in this repo, but only under
`wicked_animator/` (`clipfmt.py:fnv32/fnv64`, `wwpackage.py:fnv64`, `morph.py:fnv64`) - `sims_hub` and
`wicked_animator` have no existing Python cross-import today, so per SPEC.md `§9.4`/`§14.4` this file
implements its own small `fnv64()` rather than adding the first one. Correctness is checked against the
existing implementations in `tests/test_novulon_ids.py` (same output, same input), not by importing them.
"""


def fnv64(name):
    """Standard FNV-1 64-bit, lower-cased UTF-8 input (SPEC.md `§14.4`)."""
    h = 0xCBF29CE484222325
    for b in name.lower().encode('utf-8'):
        h = ((h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF) ^ b
    return h


def custom_id(name):
    """Interaction/icon instance ids: top bit set so they can never collide with an EA id
    (`wwpackage.py:instance_id()`'s convention, cited in `build_plan.md` §2b)."""
    return fnv64(name) | 0x8000000000000000


def stbl_id(name, locale=0x00):
    """STBL instance ids use the TOP BYTE for locale, not the top-bit convention above - `build_plan.md`
    §2b: `(inst>>56)&0xFF; 0x00 = English`, verified against `mc_cmd_center.package`'s own STBL instance
    `0x0094935F2685AD48`. Do not conflate the two conventions."""
    return (fnv64(name) & 0x00FFFFFFFFFFFFFF) | (locale << 56)


# ---- the ids BP13's own files (novulon_tuning.py / novulon_stbl.py / novulon_icon.py /
#      build_novulon_package.py) actually use - one named line each, never an inline hash. ----
INTERACTION_OPEN_MENU = custom_id('Novulon_OpenMenu_Interaction')
ICON_PIE_MENU_32 = custom_id('Novulon_PieMenu_Icon_32')
STBL_MAIN_EN = stbl_id('Novulon_Strings')
STR_MENU_TITLE = fnv64('Novulon.MenuTitle') & 0xFFFFFFFF          # pie-menu label: "Novulon"
STR_MENU_HOVER = fnv64('Novulon.MenuHover') & 0xFFFFFFFF          # pie-menu hover: "Open the Novulon menu."
INTERACTION_SIM_MENU = custom_id('Novulon_SimMenu_Interaction')    # the "Novulon" entry on every Sim

# The game's languages: a string table per language (the top byte of its instance), all with the same English text,
# so a game in another language still shows "Novulon" instead of a blank entry.
LOCALES = (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x11, 0x12, 0x13, 0x15)


def icon_instance(name):
    """A menu icon's image instance (ingame/novulon/icons.py instance() computes the same at runtime)."""
    return custom_id('novulon_icon_' + name)

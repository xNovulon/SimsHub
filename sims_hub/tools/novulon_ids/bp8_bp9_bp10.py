"""BP8 (`household/`), BP9 (`gameplay/`) and BP10 (`relationships/`) mint no resource ids in V1.

Every row these three packages build is either a plain `menukit.Row` (no packaged resource - `icon=None`,
the same verified-safe default `bp2_menukit.py`'s own ids file explains) or a call into an already-existing
EA console command. No new interaction tuning, STBL entry, or icon is needed anywhere in household/,
gameplay/, or relationships/ - the Main Menu tile icons for "Household"/"Gameplay"/"Cheats" that
`design/logo/` already renders (`icon-household.svg`, `icon-gameplay.svg`, `icon-cheats.svg`) are cut for
the same unverified-row-icon-resource-shape reason `bp2_menukit.py` documents, not because these three
packages found anything new to cite.

This file exists (empty of constants) purely so the shared-file override's per-package convention
(`tools/novulon_ids/<package>.py`) is followed consistently, and so a future pass that verifies the
row-icon resource shape and wants to wire up the three tile icons has an obvious place to add them.
"""

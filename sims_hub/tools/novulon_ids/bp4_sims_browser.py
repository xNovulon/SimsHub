"""BP4 (`ingame/novulon/sims/{__init__,query,browser}.py`) mints no resource ids in V1.

Every player-facing string the Sim Browser shows goes through `sims4.localization.
LocalizationHelperTuning.get_raw_text(...)` at runtime (the same mechanism `common.notify()` and
every other menukit-facing screen already uses), so nothing here needs an STBL entry, and this
package writes no icon of its own (row icons stay `None` - the same verified-safe default `menukit`
already ships; see `tools/novulon_ids/bp2_menukit.py` for the one place that reasoning was written
out in full).

This file exists (empty of constants) purely so a future pass that gives the Sim Browser its own
icon/STBL id has an obvious place to add it.
"""

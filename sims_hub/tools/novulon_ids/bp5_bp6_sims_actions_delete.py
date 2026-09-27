"""BP5 (`sims/actions.py`) and BP6 (`sims/delete.py`) mint no new resource/string ids - every string
either goes through `sims4.localization.LocalizationHelperTuning.get_raw_text()` at runtime (via
`common.notify`/`menukit.notify`, same as every other feature package - no STBL entry needed), or is a
console-command literal that already exists in the base game (never a Novulon-authored resource). This
file is deliberately empty of constants - `novulon_ids/__init__.py`'s own aggregator collects every
UPPER_CASE name a sibling module defines, so a stray `ROWS`/`IDS`-style list here would be picked up as
if it were an id itself and risk a bogus name collision with an unrelated package; matching
`menukit/bp2_menukit.py`'s own empty/documented precedent, this file exists only so a scan of
`tools/novulon_ids/` finds every package accounted for.
"""

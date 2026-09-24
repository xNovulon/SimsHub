# profiles - one-click Mods profiles that live alongside mods_switch.py

`speedkit/profiles.py` switches the Mods folder between three profiles. It uses the same parking store
as the other chat's `C:\Users\basim\Tools\sims4_fitstudio\mods_switch.py`, so you can mix the two tools
in any order without losing track of a file.

| profile  | what is in Mods |
|----------|-----------------|
| `full`   | every mod |
| `fast`   | everything except `speedkit.fastmode.park_set(lib)` (the CAS-heavy CC catalogs, in practice the `sim/` merges), plus the fast pack `!!!!!SpeedKit_Fast_NNN.package` at the Mods root |
| `studio` | exactly what mods_switch.py's `lean` keeps: its `KEEP` list, imported from that file at run time (a built-in copy is used when the file is missing or broken) |

`Mods\SpeedKit_Monitor.ts4script` stays at the Mods root in every profile. If the other tool parked it,
SpeedKit brings it back. In every profile except `fast`, the fast pack goes back to
`SIMS\SpeedKit\fastpack`.

Only those two are SpeedKit's own files, matched by exact name at the Mods root: the monitor, and
`!!!!!SpeedKit_Fast_###.package` (three digits, the same pattern `speedkit.fastmode` writes; a user's
`!!!!!SpeedKit_Fast_001 - Copy.package` is ordinary CC). `SpeedKit Merged\` and `SpeedKit Loose\`
(from `speedkit/merge.py`) hold the user's own CC and move like any other mod. This module only ever
undoes `profile` journals (`undo_switch` refuses other kinds); `merge` journals are undone with
`speedkit.merge.undo(id)`.

```python
from speedkit import profiles
plan = profiles.switch('fast')                 # dry run: nothing changes; plan['counts'], plan['moves'] ...
print(profiles.format_plan(plan))
profiles.switch('fast', dry_run=False)         # refuses while TS4_x64.exe runs
profiles.current()                             # {'profile': 'full'|'fast'|'studio'|'custom', 'differences', ...}
print(profiles.format_status(profiles.status()))
profiles.undo_switch(journal_id, dry_run=False)
profiles.check_manifest()                      # is Mods_parked\_manifest.json consistent for mods_switch.py?
```

CLI (every change is a dry run unless you add `--apply`):
`python -m speedkit.profiles status | check | switch full|fast|studio [--apply] [--no-update] [--json] | undo <id> [--apply]`.

## How a switch works

1. **Checks.** A real switch refuses while the game runs (`library.game_running`, which treats "can't tell"
   as running). The Journal checks the game again before every step. It also refuses when
   `Mods_parked\_manifest.json` is damaged: not JSON, not `{"moved": [...]}`, or an entry with `..`, a
   drive letter or a non-string value. The message is plain and nothing is changed.
2. **Library.** `fast` needs a library index for `park_set`. `studio` and `fast` use it for the
   script/companion check. By default this is the shared `data/library.sqlite`, scanned incrementally
   first. Tests and dry runs on the real folders pass a private copy.
3. **Fast pack first (fast only).** The switch calls `fastmode.status(out_dir)`.
   * If the pack is fresh, nothing happens to it.
   * If it is stale or missing, a real switch first brings every pack file home to the fastpack folder
     (its own `profile` journal). It checks the status again and calls
     `fastmode.update_pack(lib, refs, dry_run=False)` if the pack is still stale.
     `refs` is `usedpack.scan_references(workers=1)` unless the caller passes one.
   * If the pack still isn't fresh, or no pack file exists, the switch refuses and the pack goes back
     where it was. Without the pack, sims would lose CC they wear.
   * A dry run only reports `pack.action = 'update'`.
4. **Target.** The switch works out which side of the store each file belongs on.
   * `full`: every file goes to Mods.
   * `studio`: a file stays in Mods when `KEEP` keeps it. Matching ignores case, and `'dir/'` keeps the
     whole folder.
   * `fast`:
     * Packages in `park_set` are parked.
     * `.ts4script` files are never parked.
     * Nothing under `FitStudio/` or `animation/` is parked. This is a safety net on top of `park_set`.
     * Other files follow the mods of their folder: a `desktop.ini`, `.cfg` or log is parked only when
       every mod below its folder is parked. A folder with no mods follows its parent, and the Mods
       root always stays.
5. **Scripts and companions.** This uses `companions.classify`. A package that needs a script
   (`core`/`addon`) is never kept while its script is parked: the script is kept too. A script that
   stays keeps its `core` companions from the same folder. The fix always keeps more and never parks
   more. Relative paths never change, so a script never ends up deeper than it was. Kept scripts deeper
   than one folder are reported, because they never load.
6. **Fewest moves.** A folder moves as one rename when everything in it is on one side, all of it must
   go to the other side, and the destination has no such folder (for example, parking `Sliders/`).
   Otherwise files move one by one. A path that exists in both Mods and Mods_parked is never
   overwritten: it is reported in `conflicts`, and the Mods copy is the one the game uses. A parked
   folder with no file in it (say, an empty settings folder `lean` parked as `dir/`) comes back as one
   rename in `full` (in `fast` it follows its folder's files, in `studio` only what `KEEP` keeps), so
   SpeedKit's `full` leaves the parking list empty just like the other tool's `full`.
7. **Thumbnail cache, then one Journal of kind `profile`.** When the loaded CC set changes,
   `localthumbcache.package` is quarantined first, through its own small `profile` journal
   (`plan['thumbcache_journal']`); the research says to clear it after CC changes, and the game
   rebuilds it. It is kept out of the switch's journal on purpose: after the user plays, the game has
   written a new cache in the same place, and `journal.undo` would then refuse to undo the whole
   switch ("something is in its place"). The switch's journal (`plan['journal']`) moves the files,
   moves the fast pack (to the Mods root or home), and brings a parked monitor back. It also rewrites
   the manifest and `SIMS\SpeedKit\profile_state.json`: each file is staged whole, then the old one is
   quarantined and the new one moved in with `os.replace`. `undo_switch` can therefore put back the
   folders, the manifest and the state file exactly.
8. **Rollback.** If any step fails (a locked file, the game starting, Ctrl+C in the console window),
   the journal - and the thumbnail cache's - is undone at once and the error says so (Ctrl+C is raised
   again afterwards). If even that is refused (the game runs), the message names the journal to undo
   once the game is closed. Until then no file is lost: every moved file sits at a known place in Mods
   or Mods_parked.
9. **Tidy.** Only the folders the switch emptied (the ones moved things came out of) are removed when
   empty, with `os.rmdir`, which cannot remove anything with content; in Mods_parked also an empty
   folder whose twin exists in Mods (a leftover from a run killed before its tidy-up). Nothing else:
   empty folders that were there before - the 14 empty sub-folders of the downloads in `LittleMsSam
   Pack\` and `Srsly Pack\`, a mod's empty settings folder - stay, and travel with their folder. The
   root, `_old_caches` and the folders of still-valid `dir/` entries in Mods_parked are never removed.
   Why tidy: an emptied `Mods_parked\sim` would make mods_switch.py's `lean` skip `sim/` ("already
   parked with this name"), and an emptied `Mods\sim` would make its `full` skip a `sim/` entry. A
   `dir/` entry whose folder Mods has again (new CC dropped into `Mods\sim` after `lean` parked `sim/`)
   no longer protects its emptied parked folder.
10. **After the switch.** It writes `SpeedKit\profiles\last_<profile>.json` (SpeedKit's own record of the
    parked set, used by `current()`), rescans the library, and checks that the result matches the plan
    and the manifest is consistent (`plan['verified']`).

## The shared parking list (`Mods_parked\_manifest.json`)

mods_switch.py's `full` restores each entry by moving `Mods_parked\<entry>` to `Mods\<entry>`. It skips
an entry whose destination already exists, so an entry is only valid in these forms:

* `'dir/'`: only while `Mods\dir` does not exist.
* `'file'`: always valid. `full` creates the parent folders.

After every switch the list is rebuilt from the folders on disk, without throwing away the other tool's
work:

* Entries that are still valid stay as they are, in their order. That includes entries SpeedKit did
  not create.
* Entries whose path is back in Mods are dropped, as `full` does.
* Entries that point nowhere are kept. They are harmless.
* An entry nested inside a valid `'dir/'` entry is dropped. Depending on the order, it could otherwise
  make `full` create the folder first and then skip the `dir/`.
* A `'dir/'` entry that no longer fits is split into entries for what is still parked below it. For
  example, `fast` keeps two small `sim/` packages, so `Mods\sim` exists and `sim/` becomes 187 file
  entries.
* Parked files that no entry covers are added in the coarsest valid form. This heals a list that an
  interrupted run left short.
* Other keys of the JSON document are kept. The layout is `json.dump(indent=1)`, the same as
  mods_switch.py writes.

`check_manifest()` reports, from mods_switch.py's point of view:

* `unlisted`: parked files `full` would leave behind.
* `blocked`: `'dir/'` entries `full` would skip.
* `in_both`: two copies of a file, one in Mods and one parked.
* `nested`, `duplicates` and `stale` entries.

`ok` means none of `unlisted`, `blocked` or `nested`.

## Mods set aside until they are updated (`SpeedKit\set_aside.json`)

`speedkit.patchday` (the Hub's patch-day helper and "set this mod aside" button, docs/care.md) parks single
mod files through its own kind `aside` journal, rebuilding the manifest with `rebuild_manifest`, and lists
them in `SpeedKit\set_aside.json` `{"version": 1, "held": [{"rel", "since", "why", ...}]}`:

* `held_keys(P)` reads that list (a missing or unreadable file holds nothing).
* `compute_target(profile, inv, ..., held=...)` keeps every held file that is parked now on the parked side,
  in every profile, so a switch - even to `full` - never brings it back. `switch` passes `held_keys(P)`.
* `current()` leaves held files out of the comparison, so held files never make the folders look `custom`.
* Once a held file is back in Mods (put back, or mods_switch.py's `full` restored it), the hold has no effect.

## current() and status()

`current()` compares what is parked now with each profile's parked set and the fast pack's place:

* `full`: nothing parked and no pack in Mods.
* `studio`: the `KEEP` target, or the set of the last SpeedKit studio switch.
* `fast`: the set of the last SpeedKit fast switch, or `fastmode.park_set(lib)` when `lib` is given,
  with the pack in Mods.

It returns the matching profile, or `'custom'` with the closest profile and its differences
(`to_park`, `to_restore`, the pack), plus notes: a parked monitor, pack files in Mods_parked, and
paths that exist in both places. After mods_switch.py's `lean`, the folders are recognised as
`studio`. `status()` adds:

* `profile_state.json` and whether it still matches the folders; the other tool does not update it;
* the manifest check;
* the pack's freshness;
* the `KEEP` source;
* unfinished `profile` journals;
* whether the game runs.

`format_status()` prints all of this as plain lines.

## Undo

Use `undo_switch(id)` for `profile` journals. It runs `journal.undo()` and then removes the folders the
switch had moved things into (in Mods and Mods_parked) that are empty again. A leftover empty
`Mods\sim` would make mods_switch.py skip `sim/`. `journal.undo()` alone restores every file, the
manifest and the state file, but can leave such an empty folder behind. The next SpeedKit switch
copes with it, because the manifest uses file entries when `Mods\dir` exists.

* Undo works after the user has played: the thumbnail cache the game rebuilt is not in the switch's
  journal. The cache the switch moved aside stays in quarantine (`plan['thumbcache_journal']` can be
  undone on its own, but there is no need - the game rebuilds it).
* Every refusal is a `ProfileError` with a plain message: the game runs, the journal was already
  undone, it is not a `profile` journal, or something changed since. mods_switch.py rewriting the
  manifest after the switch is such a change - undo then refuses rather than undo over the other
  tool's moves; switch profiles instead.
* An undo stopped half-way by a file in use says so; running it again continues where it stopped.

## Tests

On fake trees under `E:\speedkit_test\profiles`:

* `tests/test_profiles.py` (37 tests):
  * the `KEEP` import and its fallback;
  * the manifest rebuild rules;
  * refusing a damaged manifest;
  * dry runs change nothing;
  * the cycle full → studio → fast → full with every invariant (no file lost or duplicated, manifest ok
    for mods_switch.py, no empty parked folders, scripts at depth ≤ 1, saves untouched);
  * no-op switches;
  * exact undo, including created folders; undo after the game rebuilt its thumbnail cache; undo
    refusals as `ProfileError`;
  * refusal while the game runs, also with a stale pack (nothing brought home, no update);
  * the game starting half-way;
  * a locked file half-way (automatic rollback), and a failure before and after every single journal
    step of a switch (studio → fast with empty download sub-folders);
  * Ctrl+C before and after every step: rolled back, then re-raised;
  * empty folders: kept when they were there, brought back by `full`, an emptied one removed even when
    an old `dir/` entry named it;
  * exact fast pack names;
  * script/companion closure;
  * the fast safety net;
  * a stale pack updated before switching, and brought home and back;
  * a failed update changes nothing;
  * the pack goes back into Mods when the switch after its update fails;
  * refusing without a pack;
  * a parked monitor comes back;
  * `SpeedKit Merged\`, `SpeedKit Loose\` and lookalike names move like ordinary mods;
  * same-path conflicts;
  * foreign entries and keys kept;
  * an unlisted parked file healed;
  * `current()` reporting `custom`;
  * the real `companions.classify` path;
  * the real `fastmode` return shapes.
* `tests/test_profiles_compat.py` (8 tests) imports the real mods_switch.py and points its constants at
  the fake tree:
  * SpeedKit fast → mods_switch full restores everything;
  * mods_switch lean → SpeedKit full restores everything;
  * SpeedKit studio gives the same files and entries as mods_switch lean (apart from the monitor, which
    SpeedKit keeps);
  * mixed sequences (fast → lean → full → SpeedKit full; lean → fast → studio → full; SpeedKit full →
    lean works as before; fast → lean → SpeedKit fast; lean parks `sim/`, new CC lands in `Mods\sim`,
    SpeedKit full, then lean parks `sim/` whole again).

The review also ran, outside the suite: ~60 random mixed sequences of SpeedKit switches, mods_switch
lean/full and undo; a failure (and a Ctrl+C) before and after every journal step of all 15
start-state × profile transitions; and a killed process (no rollback) at every step followed by
either `undo_switch` or the next SpeedKit switch. No file was lost or duplicated in any of them.

## Real folders (read-only dry run, 2026-09-24, game running, other chat's studio set active)

Re-checked by the review with the same method after its fixes: identical numbers, the folders' sizes
and mtimes unchanged afterwards. The empty download sub-folders travel inside the 5 folder renames.

These numbers come from a private copy of the library index and a private companions cache, with the
real `speedkit.fastmode.park_set`. Nothing in the Sims 4 folder changed: file sizes and mtimes were
compared before and after.

* **Now:** `current()` = `studio`. Mods holds 13 files (0.8 GB); 670 files (258.2 GB) are parked. The
  manifest has 311 entries and passes `check_manifest` (0 unlisted, blocked, nested or stale).
* **`switch('fast')`** brings back 483 files (7.7 GB) in 312 moves: 5 folder renames (`LittleMsSam
  Pack/`, `Scripts testing/`, `Sliders/`, `Srsly Pack/`, `TMEX-Settings/`) and 307 file moves.
  * `scripts/*`: 300 files, 0.59 GB.
  * `animation/anim1-5`: 6.76 GB.
  * 2 small `sim/` packages, 0.32 GB: `WW_KhlasGayAnimations`, not a CAS catalog; and the dreamlike
    preset set, a WW-linked companion.
  * **After:** 496 files (8.6 GB) in Mods, plus the fast pack, and 187 `sim/` packs (250.4 GB) parked.
  * **Manifest:** 311 → 187 entries (`sim/` is split, 310 restored entries dropped).
  * **Fast pack:** not built yet, so a real switch would first run `update_pack`.
  * **CAS parts:** fastmode's numbers are 366 in kept packages versus 755,662 in the full library.
* **`switch('full')`** brings back 670 files (258.2 GB) in 311 moves (6 folder renames incl. `sim/`).
  The manifest goes from 311 to 0 entries.
* **`switch('studio')`** has nothing to do.

## Limits

* Moves inside one journal are renames on the same drive. Mods and Mods_parked are both in the Sims 4
  folder, so a switch takes seconds whatever the GB.
* The manifest is swapped by two renames: quarantine the old, move in the new. For a moment there is no
  file. If mods_switch.py ran in exactly that moment, it would see an empty list. A killed process
  (power cut, console window closed - Ctrl+C is rolled back) between the moves and the manifest write
  leaves parked files unlisted until the next SpeedKit switch or `undo_switch` repairs it; until then
  mods_switch.py's `full` would leave them parked (not lost). The journal is not `committed` and
  `status()` shows it.
* Every switch that changes the loaded CC quarantines one `localthumbcache.package` into
  `SpeedKit\quarantine` (mods_switch.py keeps its own in `Mods_parked\_old_caches`). With the whole
  library loaded the cache can grow large; nothing prunes those copies yet.
* `undo_switch` removes a folder it moved things into when it is empty afterwards, even if that folder
  was already there and empty before the switch (an empty `Mods\sim` left by `lean`, say) - harmless,
  and it unblocks a `sim/` entry.
* `profile_state.json` is only written by SpeedKit. After mods_switch.py runs, it is stale, and
  `status()` flags that. `current()` always looks at the folders.
* The companion closure trusts `companions.classify` (heuristic). A script whose companion the
  classifier missed is not grouped.

## The 'save' profile (engine wave, 2026-09-24)

`switch('save', save_slot='Slot_00000014', fastmode=savepacks.PackProvider('Slot_00000014', refs=...))` parks
exactly what 'fast' parks and puts that save's pack (`!!!!!SpeedKit_Save_00000014_###.package`, from
`SpeedKit\savepacks\Slot_00000014`) at the Mods root instead of the fast pack. Every pack family is kept
apart by its exact file name (`SAVE_PACK_RX`, `Inventory.packs`): a switch deploys the profile's own pack and
moves every other one - the fast pack, other saves' packs - back to its own folder (quarantining a stale
duplicate as for the fast pack). `profile_state.json` then holds `profile`, `save_slot`, `pack_dir`,
`save_pack` and what identifies the save in the game (`save_name`, `save_slot_id`, `save_guid`, read from the
save by speedkit.savepacks) for SpeedKit Monitor; a fast switch records `pack_dir` too. `current()` returns
`'save'` with `save_slot` when exactly one save's pack is at the Mods root and no fast pack; 'full'/'studio'
need no SpeedKit pack in Mods at all. A switch whose pack update first brought the packs home records that
helper journal in its own journal (`packs_brought_home`), and `undo_switch` puts those packs back too.

# merge: the script-safe auto-merger and the download Inbox

Module: `speedkit/merge.py`. Tests: `tests/test_merge.py` (plan, apply, undo, mods_switch compatibility),
`tests/test_merge_inbox.py` (the Inbox), both on a fake Sims 4 tree under `E:\speedkit_test\merge`, and
`tests/test_merge_review.py` (the adversarial review, under `E:\speedkit_test\merge_review`). The review
tests cover a failure at every journal step, a crash followed by undo, the mods_switch full/lean cycle,
bad zips, and more.

## What it does

1. **plan_merge / apply_merge.** Loose packages are merged into a few files named
   `SpeedKit Merged/<Category>_NNN.package`. Inside each merged file the catalog records come first.
   The merger never changes what the game loads, because it only merges packages whose resources are:
   - unique in the library, or
   - identical, byte for byte or once decompressed, to every other loaded copy.

   So the merged file's place in the load order cannot matter.
2. **process_inbox.** The user drops downloads into `The Sims 4\SpeedKit\Inbox`, and SpeedKit installs them:
   - script mods go in untouched;
   - new CC is merged;
   - conflicting CC is installed unmerged;
   - updates replace the file they update.

Everything is a dry run unless `dry_run=False`. Real runs go through a Journal and refuse while
TS4_x64.exe runs. After a run, SpeedKit checks the result against what it intended; if they differ,
it undoes the run by itself.

## Facts it relies on

These come from research/research_results.json (merging, loadorder) and the skeptic's corrections.

- **Load order.** At the same priority the first-loaded copy of a key wins. The game walks Mods
  depth-first in NTFS name order (`Library.load_order()`). This was proven in-game for tuning in 2017
  and has not been re-tested on 1.126 for CC. The merger does not depend on it: it refuses any package
  that has a differing copy anywhere.
- **Size cap.** S4S refuses to merge above 2^31-1 bytes, and EA's largest package is 1.98e9 bytes.
  Merged files are capped at `max_bytes` = 1.9e9 (target 1e9).
- **Per-file cost.** Each file costs 0.5-10 ms at startup. The benefit of merging is fewer files plus
  catalog-first layout; it is small and is reported honestly below.
- **S4S manifest.** Type `0x7FB6AD8A`, written first by `speedkit.manifest.build_flat`. It lists every
  source, so Sims 4 Studio can unmerge the file. An identical resource held by several sources is written
  once and listed under each source, which is what S4S itself does.
- **Script companions.** Merging a companion does not break it at runtime, because keys stay the same.
  It does break updating: the stale copy stays inside the merge. That is why companions are never merged.

## What is never merged (plan_merge says why, per package)

| reason | rule |
|---|---|
| `shadowed` | the same path is in both Mods and Mods_parked (only the Mods copy loads) |
| `not loaded` | more than 5 folders deep (the default Resource.cfg never loads it) |
| `unreadable` | the library could not read its index |
| `speedkit` | any path part contains "SpeedKit": the fast pack, the used pack, earlier merges, `SpeedKit Loose` |
| `fitstudio` | anything under a `FitStudio` folder (the other chat's mod) |
| `studio set` | a file mods_switch.py's `lean` keeps in Mods (its `KEEP` list, parsed from its source by `studio_keep()`, never executed; built-in copy if the file is missing). A merged file is not on that list, so merging would take the file out of the studio set |
| `load-order name` | `companions.load_order_sensitive()`: `!`, `~`, `_`, `[`, `zz`, numbered prefixes, NSW lighting |
| `already merged` | holds an S4S manifest (`0x7FB6AD8A`) |
| `script companion` | `companions.never_merge()`: core / addon / orphan / weak / broken |
| `empty` | no resources |
| `next to a script` | its folder holds a `.ts4script` (as dedup; `protect_script_folders=False` turns this off) |
| `already big` | at or above `target_bytes` |
| `deleted entries` / `key twice` | deleted-flag index entries, or one key twice in the file |
| `conflict` / `undecidable` | a resource differs from, or cannot be compared with, another loaded package's copy (`speedkit.hashing`) |
| `parked folder` | a loose package in Mods while `Mods_parked\SpeedKit Merged` is parked as a whole folder (`SpeedKit Merged/` in the manifest) and no `Mods\SpeedKit Merged` exists. Creating that folder in Mods would stop mods_switch `full` from restoring the parked one, because `full` skips an entry whose name is taken. Also: parked packages the manifest does not list, while `SpeedKit Merged/` is listed; `full` would start restoring their merged file although it never restores them |

`.ts4script` files are never touched. **NameMap** (`0x0166038C`): S4S writes most NameMaps at key
`0166038C:0:0`, so every package with one "conflicts" with every other. By default a NameMap counts as
content, as in dedup, because nobody knows whether the game reads CC NameMaps. With
`ignore_namemap=True` it is tool metadata:
- a differing NameMap does not block a merge;
- the first source's NameMap is written;
- every source still lists the key;
- NameMaps are left out of the after-merge check.

## Groups and output

- **Grouping.** Packages are grouped by root, category and folder, and the sources of a group are
  always in one root.
- **Categories.** Chosen from the resource types and the classifier's kind:

  | Category | Contents | Grouped with |
  |---|---|---|
  | `CAS` | CASP / TONE | other packages under the same top-level folder |
  | `BuildBuy` | OBJD / COBJ / CWAL / CFLR | other packages under the same top-level folder |
  | `Tuning` | the `tuning` kind | only tuning from the **same folder** |
  | `Sliders` | SMOD / CPRE / sculpt / BGEO / DMAP / BOND | other packages under the same top-level folder |
  | `Other` | anything else | other packages under the same top-level folder |
- **Size and order.** Groups are filled in load order up to `target_bytes`. A bin with fewer than
  `min_group` (2) packages is not merged; it is reported as `alone`.
- **Resource order inside a merged file.** S4S manifest, then CASP, thumbnails, TONE/slider/preset
  records, OBJD, COBJ/CWAL/CFLR, SimData, XML tuning and other small records, STBL, and last the
  meshes, textures and clips. Within one kind, sources keep their load order and their index order.
- **Where output goes.** `<root>/SpeedKit Merged/<Category>_NNN.package`, in the root the sources are
  in. Numbers are unique across both roots, because mods_switch never restores a file whose name is
  already taken in Mods.
- **Coexistence with `Tools\sims4_fitstudio\mods_switch.py`.** A merged file written into Mods_parked
  is ADDED to `Mods_parked\_manifest.json` (`{"moved": [...]}`), so `mods_switch full` restores it.
  - It is not added if a folder entry already covers it.
  - The other tool's entries and extra keys are kept.
  - The file is rewritten with a temporary file plus `os.replace`.
  - A malformed manifest makes SpeedKit refuse before changing anything.

  A quarantined source keeps its entry. mods_switch skips missing entries and drops them; `undo()`
  lists a restored source again if that happened.
- **Whole-folder entries.** mods_switch `lean` parks a folder as one `dir/` entry, and `full` skips an
  entry whose name already exists in Mods. So SpeedKit never creates a folder in Mods while the
  same folder is parked whole (`park_dir_block()`):
  - plan/apply do not merge Mods packages then;
  - the Inbox puts new `SpeedKit Merged` / `SpeedKit Loose` files into the parked folder, where the
    folder entry covers them and `full` brings them back;
  - `undo()` refuses to restore a file into such a folder.
- **Studio set.** Files on mods_switch's `KEEP` list are never merged.

## apply_merge

1. Refuses in any of these cases:
   - the game is running;
   - the library changed since the scan (`dedup.index_problems`, `.ts4script` files included);
   - a path is in both roots;
   - `Mods\Resource.cfg` is not the default;
   - the plan is stale, or an output name is taken;
   - the parking manifest is malformed;
   - a Mods output would create `Mods\SpeedKit Merged` while that folder is parked whole;
   - a group's estimated size is over `max_bytes` (checked again on the written file);
   - less than 5 GiB would stay free.
2. Records the content the game uses for every key of every source (`hashing.effective_map`) in two
   scopes: all roots laid over each other, and Mods alone.
3. Handles each group in turn:
   - writes `<final>.speedkit-merge` (through PackageWriter's `.writing`);
   - re-reads it and verifies it: manifest first and readable, every resource bit-exact (bytes and
     index fields) against its source, every copy that was written once identical to the written one,
     size within `max_bytes`, sources unchanged while reading;
   - then Journal kind `merge`: `put_new` the merged file, add it to the parking manifest if it is
     parked, `quarantine` every source.

   `quarantine_home` may be on another drive, such as E:, to keep C: free.
4. Rescans and compares the effective content again. If anything differs, or anything fails, it undoes
   everything, the parking manifest included, and raises `InvariantError` or `MergeError`.

The parking-manifest changes are recorded in `SpeedKit\journal\<id>.merge.json`. `merge.undo(id)` is
`journal.undo` plus those manifest fixes, so undo `merge` and `inbox` journals with `merge.undo`, not
`journal.undo`. It refuses before changing anything in two cases (switch back first):
- a profile switch has moved a merged or installed file to the other root since;
- restoring a file into Mods would recreate a folder that is parked whole.

If the files were put back but the manifest could not be fixed (for example, the other tool had left it
malformed), running `undo` again fixes only the manifest.

A failure at any journal step, before or after that step's move, is rolled back automatically. After a
crash with no rollback, `merge.undo` restores everything.

## process_inbox

`Inbox` is `<Sims 4>\SpeedKit\Inbox`, outside Mods. It is created on the first real run, or by
`ensure_inbox()`. A dry run writes nothing in the Sims 4 folder; zips are opened in the system temp
folder.

**Items.** An item is one of:
- a `.zip`, extracted with zipfile; paths with `..`, a drive or an absolute path are refused, and so are
  nested archives;
- a folder;
- a loose `.package` or `.ts4script`. A loose package whose name starts with a loose script's name
  (without `_Scripts`) belongs to that script.

Zip members are flattened: whatever their depth inside the zip, a script and its packages end up one
folder deep. A member that cannot be extracted refuses that download only. Such members include Deflate64
(which Windows Explorer writes for big files), encrypted members, a bad CRC, or a name Windows forbids.
Files other than `.package` / `.ts4script`, such as a readme or a `.cfg`, are not installed; the report
lists them under `not_installed`, and they stay in `_done`.

Other items are handled as follows:
- `.rar`, `.7z` and other archives are refused: "extract it first".
- A `.package` that is really a zip is refused, with the hint to rename it to `.zip`.
- Partial downloads (`.crdownload`, `.part` and so on) are skipped.
- A download with two files of the same name is refused.
- A download with two packages that change the same resource differently ("alternative versions") is
  refused. NameMap and manifest keys do not count here.

**Files** are handled in this order:

| case | result |
|---|---|
| byte-for-byte an installed file (any name) | `duplicate`: nothing installed |
| same file name as an installed file and (for packages) at least one shared resource | `update`: replaces that file in place, in whichever root it is (a parked mod stays parked); old one quarantined |
| part of a download with a `.ts4script` | `install` untouched into `Mods\<download name>\` (one folder deep), or next to the script it updates or that is already installed under another name |
| a load-order name (`!`, `~`, `_`, `zz`, numbered prefix) | `install` untouched at the top of Mods, where its name decides when it loads |
| XML tuning, S4S merge, deleted entries, key twice, empty, or bigger than target | `install` untouched, same folder (gameplay mods are never merged) |
| CC with a resource that differs from the copy the game loads now, or from another download's new copy | `loose`: `Mods\SpeedKit Loose\<name>` unmerged |
| CC whose every resource is already loaded identically | `duplicate` |
| other CC | `merge`: its NEW resources go into `Mods\SpeedKit Merged\New_NNN.package` |

A few more rules for where things go:
- **New_NNN files.** The newest `New_NNN` in Mods below target size is rewritten with the new CC added,
  and the old version is quarantined; otherwise a new number is used. Its S4S manifest keeps the old
  sources and adds the new ones.
- **New folders.** Folders SpeedKit creates for new downloads never reuse a name that exists in either
  root.
- **Parked files.** A new file placed into a parked folder is added to the parking manifest.
- **Parked output folders.** If `SpeedKit Merged` or `SpeedKit Loose` is parked as a whole folder, new
  files go into that parked folder. The report says so, and they load after switching to full.
- **What is never replaced.** Updates never replace anything under FitStudio or SpeedKit's own files.

**Real run.** Journal kind `inbox`. It refuses before changing anything if less than `min_free`
(5 GiB) would stay free on the Mods drive, or if the library has no common Sims 4 folder (it never
falls back to the real one). Processed items move to `Inbox\_done\<date>\`; refused and skipped items
stay in the Inbox with their reason. Afterwards the library is rescanned and SpeedKit checks three
things:
- untouched files arrived bit-exact;
- every merged resource is what the game loads, in both scopes;
- the old content of a rewritten `New_NNN` is unchanged.

If any check fails, it undoes the run by itself. `merge.undo(id)` puts everything back, including the
Inbox.

## API

```python
plan_merge(lib, roots=('Mods','Mods_parked'), target_bytes=1_000_000_000, max_bytes=1_900_000_000,
           verdicts=None, cache_path=None, companions_cache=None, progress=None, threads=8,
           min_group=2, protect_script_folders=True, ignore_namemap=False, keep=None) -> MergePlan
    # MergePlan.groups [Group(root, category, folder, sources, keys, est, src_bytes, out_rel)],
    # .excluded {pkg_id: 'reason: detail'}, .alone, .warnings, .summary(), .to_dict(), .check_keys
apply_merge(plan, lib, dry_run=True, quarantine_home=None, journal_home=None, sims=None, check_game=True,
            cache_path=None, progress=None, threads=8, min_free=5 GiB) -> dict
process_inbox(lib, dry_run=True, inbox=None, journal_home=None, sims=None, check_game=True,
              target_bytes=1e9, max_bytes=1.9e9, cache_path=None, today=None, progress=None,
              ignore_namemap=False, min_free=5 GiB) -> {'items': [...], 'merged_into': [...], 'journal', 'invariant', 'warnings'}
undo(journal_id, home=<Sims 4>\SpeedKit, check_game=True, dry_run=False) -> [(action, path)]
inbox_path(lib=None, sims=None), ensure_inbox(lib=None, sims=None)
write_merged(parts, out_path, max_bytes, cache=None, final=None, lenient_types=()) -> (tmp, stats)
read_park_manifest(parked), park_manifest_add(parked, rels), park_manifest_remove(parked, rels), park_covered(moved, rel)
park_dir_block(mods, parked, rel, moved) -> 'dir/' entry a new Mods/<rel> would block, or None
studio_keep(path=MODS_SWITCH) -> mods_switch KEEP list; studio_kept(rel, keep)
rank(t), category_of(types, kind), is_speedkit_file(rel), is_fitstudio(rel)
```

CLI (dry run unless `--apply`):

```
python -m speedkit.merge plan|apply|inbox|undo [id] [--db D] [--scan] [--cache C] [--companions-cache CC]
                                                 [--quarantine E:\dir] [--ignore-namemap] [--json out] [--apply]
```

## Real library (read-only dry run, 2026-09-24)

The run used a private copy of library.sqlite, rescanned, plus private copies of hash.sqlite and
companions.sqlite on E:. At the time, Mods held the studio set and Mods_parked held the rest, 627
packages in all.

| variant | merged files | packages merged | GB | files fewer | excluded |
|---|---|---|---|---|---|
| default | 17 (10 CAS, 7 Tuning) | 68 | 8.18 | 51 | 523 |
| `ignore_namemap` | 19 (+1 Sliders with 46 packages, +1 Other) | 116 | 8.19 | 97 | 475 |
| no script-folder rule | 20 | 136 | 8.32 | 116 | 455 |
| both | 23 | 209 | 8.34 | 186 | 382 |

**What the default plan does.** It merges 33 standalone CAS packages parked in `sim\` into 10 CAS files
of 0.64-0.99 GB each (8.18 GB). These are hair, skins, lip glosses and the like: BirdySims, DOUX,
obscurus, sims3melancholic, Slephora and others. It also merges 35 small SrslySims tuning packages from
7 folders into 7 Tuning files (2 MB). All the output goes to `Mods_parked\SpeedKit Merged\` and is added
to `_manifest.json`.

**Why it does little.** Most of the library is already merged:
- 159 S4S merges (247.9 GB);
- 100 load-order-named files (2.2 GB, mostly the 20 NSW lighting variants and the `[bloodmoon]` sliders);
- 87 script companions;
- 107 packages next to scripts in `scripts\`;
- 64 conflicting packages (16 without NameMaps);
- 3 studio-set files that mods_switch keeps in Mods: the two WW_LAMABOY animation packs and the
  WickedWhims tuning. The review re-ran the plan on 2026-09-24 with the same result: 17 files, 68
  packages, 8.18 GB.

**Benefit.** The default plan removes 51 files, about 0.03-0.5 s per start, and puts the CASPs of 33
packages at the front of their files. That is small.

**Disk.** Writing 8.18 GB of new files on C: (56 GB free) grows C: by 8.18 GB until
`SpeedKit\quarantine` is emptied. `--quarantine E:\...` avoids the growth.

**Time.** The plan takes 18-41 s with warm caches. A real apply first reads the source resources once
(about 8.2 GB) for the before/after check.

**Inbox.** The real Inbox does not exist yet. A simulated Inbox outside the Sims folder (E:) was checked
against the real index in 0.6-2.6 s:
- a new synthetic hair was planned into `New_001`;
- a byte-identical re-download of an installed slider under another name was a `duplicate`, pointing at
  `Mods_parked/Sliders/LUUMIA_...`;
- a NEW slider built like a real S4S one, which carries the usual NameMap at `0166038C:0:0`, went `loose`
  by default and `merge` with `ignore_namemap=True`.

So with the default policy most S4S-made downloads are installed unmerged into `SpeedKit Loose`. That
is safe, and the same as a manual install.

## Limits

- **Real apply never run.** A real apply or Inbox run on the real folders was never done (the rules
  forbid it, and the game was running). Everything real was a dry run; fake-tree runs cover apply, undo
  and failures.
- **Heuristic classifier.** Companion classification is heuristic (see companions.md). The
  "next to a script" rule is the safety margin.
- **In-game truths untested.** First-loaded-wins and the NameMap question were not tested in-game.
  The merger avoids depending on the first (conflicts are excluded). The NameMap policy is the user's
  choice, and the default is conservative.
- **Inbox update detection.** It goes by file name plus a shared resource. A new version with a new
  file name (e.g. `Mod_v2.package` replacing `Mod_v1.package`) is not seen as an update. It is
  installed next to the old one if it is a script/tuning mod, or goes `loose` if it is CC whose
  resources changed.
- **New_NNN rewrite.** Appending to `New_NNN` rewrites the whole file, up to 1 GB, each time CC is
  added. The old version stays in quarantine until the user empties it.
- **Quarantine space.** Quarantined originals and replaced `New_NNN` versions use disk space until
  `SpeedKit\quarantine\<id>` is emptied. Nothing is ever deleted.
- **No lock with mods_switch.** mods_switch.py reads `_manifest.json` at the start of a switch and
  writes it at the end, without a lock. If it runs at the same moment as a SpeedKit merge or Inbox run,
  one tool's entries can be lost. SpeedKit refuses while the game runs, but it cannot see the other
  tool running.
- **Identical resources and parked copies.** The Inbox leaves out a resource that is identical to the
  copy the game uses in Mods + Mods_parked. If that copy is parked, the new CC is complete only after
  switching to full.
- **Crash leftovers.** A power loss while writing leaves
  `SpeedKit Merged\<name>.package.speedkit-merge(.writing)` behind. The game does not load it, and later
  runs use the next number. SpeedKit never removes it by itself.

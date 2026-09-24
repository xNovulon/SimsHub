# fastmode - the FAST profile and its pack

`speedkit/fastmode.py` decides what the FAST profile leaves out and builds the small pack that keeps
everything working without it. Startup cost follows the number of CAS parts (research 'lagdrivers'):
the library has 755,662 CASP entries and 755,461 of them sit in the 189 S4S-merged packs under `sim/`.
The fast profile parks those catalogs and loads, in their place, one pack of about 7-8 GB that holds
exactly what the rest of the game still needs from them.

```python
from speedkit.library import Library
from speedkit import usedpack as U, fastmode as F

lib = Library()                                  # an index that is up to date (scanned by its owner)
refs = U.scan_references()                       # saves + Tray (worker processes: use a __main__ guard)
parked = F.park_set(lib)                         # [(root, rel)] the fast profile leaves out; .reasons
plan = F.plan_pack(lib, refs, parked)            # read-only: which resources, from which copy, and why
F.build_pack(plan)                               # dry run: the layout
F.build_pack(plan, dry_run=False)                # SIMS\SpeedKit\fastpack\!!!!!SpeedKit_Fast_001.package ...
F.status()                                       # {'state': 'fresh'|'stale'|'missing', 'why': [...]}
F.update_pack(lib, refs, dry_run=False)          # nothing / refresh / a small delta / a rebuild
F.verify(lib, refs)                              # {'ok', 'missing', 'different', 'installed_nowhere'}
```

CLI (read-only unless `--really`): `python -m speedkit.fastmode park [--list] | plan | build [--really]
| status | update [--really] | verify`, with `--library --refs-db --game-ids-db --game-db
--companions-cache --out --sims --json` to point it at private copies or a test tree.

## park_set(lib, roots=('Mods','Mods_parked'), verdicts=None) -> ParkSet

A `ParkSet` is a plain list of `(root, rel)` in load order (so `for root, rel in park_set(lib)` works),
plus `.reasons {(root, rel): text}`, `.kept` / `.keep_reasons` for the loaded packages it keeps, `.info`
(CAS parts, bytes, asset share, script share, companion kind per package), `.stats` and `.rels()`.

Parked: CAS-heavy CC catalogs, decided from the library index (per package: CASP count, bytes of CAS
and BuildBuy asset types vs everything else, S4S manifest present):
* at least 20 CAS parts and at least 60% of the bytes CAS/BuildBuy assets, or
* one big standalone CAS file (>= 50 MB, >= 80% assets, at least one CAS part).

Never parked:
* `.ts4script` files (only packages are considered);
* anything under `animation/` (the WickedWhims animation packs) or `FitStudio/`;
* SpeedKit's own files, matched by exact name only: `!!!!!SpeedKit_Fast_###.package` (this pack),
  `SpeedKit_UsedCC_###.package` (usedpack) and `Mods\SpeedKit_Monitor.ts4script`. The merger's
  `SpeedKit Merged\<Category>_NNN.package` and `SpeedKit Loose\` files are the user's CC and are
  parked like any other CC when CAS-heavy; the same three names are also the only files left out of
  the library fingerprint (installing a new Monitor does not make the pack stale);
* packages whose index is unreadable, and packages classified `broken`/`empty`;
* packages `speedkit.companions` classifies core / addon / orphan / weak - EXCEPT an S4S-merged CC pack
  with at least 200 CAS parts whose script content (non-asset bytes) is at most 10%: it is parked and
  plan_pack carries its script content (tuning, SimData, strings, animations) in the pack. This is how
  the 46 sim/ merges that also hold script-mod tuning (m27's stale WickedWhims tuning, lot51 in m9, ...)
  are parked. A script companion that is a companion first (HARKI's 27-part tuning pack, WickedWhims'
  own tuning package with 167 CAS parts, WW_KhlasGayAnimations) stays.

Packages the game never loads (more than 5 folders deep, or a `Mods_parked` copy shadowed by the same
path in `Mods`) are in neither list. The verdicts come from `companions.classify(lib, cache_path=...)`
unless given.

## plan_pack(lib, refs, parked=None, kept=None, ...) -> FastPlan

Every planned key is the copy the FULL library uses (first in `lib.load_order` over Mods + Mods_parked),
and only keys whose winning copy is in a parked package are planned - a kept package keeps providing
its own winners. Three parts, reported separately (`plan.stats['parts']`, `plan.summary()`):

* **(a) saves and Tray** - `usedpack.plan()` reused as is: worn CAS parts with their meshes, textures
  and thumbnails (with the other-group / other-texture-type fallbacks), CC skin tones, sculpts, sliders,
  pet coats, lot objects with their models and tuning, every CC wall and floor, and the library's
  default replacements of the EA items sims wear.
* **(b) script and tuning content of the parked packages** - every resource that is not a CAS/BuildBuy
  asset: XML tuning of every type, SimData `545AC67A`, STBL `220557DA`, ASM `02D5DF13`, CLIP `6B20C4F3`,
  CLHD `BC4A5044`, sounds, unknown types; plus every key that overrides one of EA's
  (`GameIndex.override_keys`: default replacements of textures, meshes, tones, CAS parts) and every key
  a kept package also has but whose parked copy wins ("shadowed", e.g. a slider map inside a sim/ merge
  that loads before `Sliders/`). EA-override and shadowed CAS parts / objects / tones / sculpts / sliders
  / pet coats are added with their whole closure (a CAS part without its textures would show broken).
* **(c) what stays needed without a save naming it** - the closure of the CAS parts, objects, tones and
  sliders the kept packages hold (a kept CAS part whose mesh lives in a sim/ merge), and every CC id
  found in the XML tuning / SimData that stays loaded (kept packages + the pack itself) or hard-coded
  in a `.ts4script` (companions' cached bytecode facts), when a parked package holds a CAS part,
  object, tone, sculpt, slider or pet coat with that instance - with its closure, repeated until
  nothing new turns up (tuning the closure adds is scanned too). XML is read for decimal ids, `0x` hex
  and bare 16-digit hex (S4S `T:G:I` strings); SimData for 8-byte values at every offset. A CC id is
  64-bit, or a 32-bit instance of at least 65,536 that the game does not ship (`is_cc_id`): the parked
  sim/ merges hold 1,821 such older-tool records, and a CC makeup chair's buff in `sim/m12` sets 20 of
  them (`<T n="cas_part">4192089908</T>`). EA's own ids and the library's overrides of them are carried
  by (b) already. Also every asset key the loaded tuning writes out in full as `type:group:instance`
  (WickedWhims' `cas_part_display_icon`, an `_IMG` in the same sim/ merge; 43 keys today).

The closures reuse usedpack's code: CAS parts, tones, sculpts, sliders and pet coats by handing
`usedpack.plan()` a synthetic `Refs` that "references" the ids (`build_surfaces=False,
ea_overrides=False`); objects through usedpack's own object walk (`_Planner.resolve_embedded`: OBJD/COBJ,
thumbnail, models, LODs, footprints, slots, rigs, materials, textures) without usedpack's own-package
tuning/STBL steps - (b) already carries every parked tuning and string table, and those steps read
every string table of a package once per object (they made a real plan take 5 minutes). Never packed: the S4S manifest `7FB6AD8A`, NameMap
`0166038C` and S4S's batch-fix history `6BF15BBE` (the game reads none of them).

`FastPlan` has `.items {key: FastItem(t, g, i, pkg, off, fsize, msize, comp, why, part)}`,
`.packages`, `.parked`, `.sources` (saves/Tray fingerprints), `.library` / `.library_fp` (library
fingerprint), `.absent` / `.unloadable` / `.households` (from usedpack), `.stats` (parts, b kinds,
keys dropped because a kept package provides them, tuning-scan counts, CAS parts full vs fast,
`loads_before_pack`: kept packages the game reaches before the pack - see below).

`kept`, when given, must not overlap `parked` and must cover every loaded package (ValueError
otherwise): a loaded package in neither list would silently be treated as kept.

SpeedKit's own pack files are invisible to planning (`LibraryView`): when the fast pack sits in the Mods
root and the index is rescanned, it would otherwise look like a kept package that already provides
every winner.

## build_pack(plan, out_dir=None, max_package_bytes=1_900_000_000, dry_run=True, check_game=False, pack_dir=None) -> [{'path', 'keys', 'bytes'}]

Files: `!!!!!SpeedKit_Fast_001.package`, `002`, ... (each <= max_package_bytes, never over 2 GiB),
`fastpack.json` and `fastpack_keys.tsv` (every key, its part, why and source). The game walks Mods in
NTFS order (upper-cased ordinal; a folder is entered where its name comes up), where
`!!!!!SPEEDKIT_FAST_001` sorts before letters, digits, `!!!Mods/` and every name in the library today, so
the pack loads first and each of its keys wins over any stale copy in a kept package - fast mode uses
the same copy of every key as the full library. Only a first path part starting with 6+ `!`, with
`!!!!!` and a character below `S`, or with a space loads before it (`loads_before(rel)`); plan_pack
counts such kept packages and the pack keys they also hold (`stats['loads_before_pack']`, 0 today) and
verify reports each such key whose copy differs (`order`).

Inside: CASP, THUM, TONE, OBJD, COBJ, SimData, tuning, STBL, small assets, then meshes / textures /
clips; within a type in source order. Every resource is copied bit-exact (`add_raw`) and, with
`check_copy=True` (default), re-read from the written package and compared by blake2b.

`out_dir` (default `<Sims 4>\SpeedKit\fastpack` of the plan's library) holds fastpack.json; `pack_dir`
(default out_dir) holds the packages - the Mods ROOT when the fast profile is active, and then the game
must not run whatever `check_game` says. A real run: refuses out_dir/pack_dir in saves, Tray,
Mods_parked or outside the Sims folder, and fastpack.json inside Mods; refuses when pack files of
an earlier build sit in the other folder (two packs would load); checks every source still has the
size/mtime the plan saw (`usedpack.PlanStale`); needs the pack's size + 1 GiB free; stages under
`SpeedKit\staging\<journal>`; moves into place through `Journal('fastpack')` - the old manifest leaves
first, old pack files are quarantined (never deleted), the new manifest arrives last; any failure undoes
the journal. `journal.undo(result[0]['journal'])` restores the previous pack.

## status(out_dir) -> {'state', 'why', 'library_changed', 'saves_changed', 'pack', ...}

`missing` (no pack), `stale` or `fresh`. Stale when a pack file is missing or resized; when a pack
file sits in BOTH the fastpack folder and Mods (the game would load the Mods copy, maybe an older
build); when a fast pack file that fastpack.json does not list is in either folder (in Mods it would
load first in every profile); when the mod library changed; when a save/Tray file is new or changed;
or when SpeedKit's park/plan rules (`rules_fingerprint()`: the park thresholds, companions'
RULES_VERSION, PLAN_RULES_VERSION) differ from the ones the pack was built with - a threshold change
can park a package the pack was not planned for. The library fingerprint is the sorted
`[rel, size, mtime]` of every `.package` and `.ts4script` in both roots (SpeedKit's files left out), so
the profile switcher's and mods_switch.py's moves between Mods and Mods_parked do not make the pack
stale. `why` names what changed ("1 changed (e.g. sim/m2.package)"). `find_pack()` says where the pack
files are now (`fastpack` folder, `mods` root, `split`, `missing`) plus `duplicated` and `extra`.

## update_pack(lib, refs, out_dir=None, parked=None, delta_limit=500 MB, dry_run=True) -> {'action', 'why', ...}

Scan the library first: an index that does not match the files on disk is refused (`FastPackError`).

* fresh -> `none`;
* no pack, or a pack file missing/resized/doubled/unlisted -> `rebuild` (build_pack into the folder the
  pack is in now; it quarantines unlisted pack files there and refuses while pack files sit in the other
  folder - the profile switcher brings them home first);
* otherwise (saves/Tray or the library changed) plan again, then
  * `pack_problems()` finds a pack key that no longer reproduces the full library (its source package
    changed or went, the key is gone, or another copy now wins) -> `rebuild`;
  * every needed key already in the pack -> `refresh` (only fastpack.json is rewritten);
  * else the missing keys go into `!!!!!SpeedKit_Fast_900.package` (901, ...) next to the others ->
    `delta`, unless all deltas together would pass 500 MB -> `rebuild`.

So a change to a kept package (the other chat's FitStudio exporting an animation, a script-mod update)
or a new save costs a delta or nothing; only a change to what the pack copied costs a rebuild. Journal
kind `fastpack`; the delta journal is undone like any other.

`pack_problems(lib, out_dir)` -> `[(key, why)]`, empty when every pack key is still the full library's
winner copy (same source package by relative path, unchanged size/mtime, same stored size/compression).

## verify(lib, refs, out_dir=None) -> {'ok', 'missing', 'different', 'installed_nowhere', 'checked'}

What the fast profile (kept packages + the pack) would miss compared to the full library, from the
index as it is now: `refs` (every CAS part / tone / sculpt / slider / pet coat / object the saves and
Tray use that the full library loads), `closure` (every mesh/texture key those CAS parts - and the kept
ones - list that the full library has), `tuning` (every CC id in the tuning/SimData fast mode loads or
in a script, with its closure), `tuning_keys` (every asset key that tuning writes out in full),
`order` (no kept package that loads before a pack file holds another copy of one of its keys),
`winners` (every kept, non-asset or EA-override key whose full-library
copy is parked is in the pack; `different` if fast mode would use a kept package's copy instead) and
`pack` (pack copies still have the full library's size/compression). `ok` means nothing is missing or
different: what the saves use and is not there is CC installed nowhere (`installed_nowhere`, counted per
category - it is missing in the full library too).

## Real library (2026-09-24, read-only, private copies of every cache in E:\speedkit_test\fastmode\real)

627 loaded packages (the other chat's studio set in Mods, the rest in Mods_parked); 374 save/Tray sources.

* **park_set** (2.8 s): 187 packages parked, 250.4 GB, 755,296 CAS parts - 141 CAS catalogs + 46
  S4S-merged CC packs that also hold script-mod content. 440 kept, 8.55 GB, 366 CAS parts: 427 not CAS
  catalogs (scripts/, Sliders/, Srsly Pack/, LittleMsSam Pack/, Scripts testing/, ...), 7 animation/, 3
  FitStudio/, 3 script companions. Two sim/ files stay: WW_KhlasGayAnimations (2 CAS parts, 94%
  animations) and "[dreamlike] preset sets" (163 CAS parts, not merged, rated 'weak' of WickedWhims).
* **plan_pack** (82-88 s: 28 s of it usedpack.plan, 22-26 s the tuning scan): 85,257 keys, 7.817 GB
  from 116 source packages.
  * (a) saves/Tray: 52,275 keys, 6.87 GB (1,846 more are provided by kept packages);
  * (b) 26,971 keys, 446 MB: 8,058 tuning/other, 4,253 string tables, 2,956 SimData, 1,998 animation
    (982 CLIP 136 MB + 982 CLHD), 10,207 EA-override keys (6,299 of them CAS parts overriding EA parts,
    with closure), 1,113 shadowed keys;
  * (c) 6,011 keys, 503 MB: 1,897 ids followed from 20,111 tuning files, 8,467 SimData and 643 ids
    hard-coded in scripts (1,280 found in tuning/SimData, 20 of them 32-bit CC ids - the makeup CAS
    parts of a CC chair's buffs in sim/m12, and WickedWhims' own object), plus 43 asset keys the tuning
    names in full (25 `_IMG` icons of WickedWhims CAS-part snippets, ...). The review's first 70 keys
    (2.7 MB) over the original 85,187.
  * By type: GEOM 4.19 GB, RLE2 1.68 GB, LRLE 0.93 GB, _IMG 0.61 GB, CLIP 136 MB, RLES 117 MB, THUM 92 MB.
* **CAS parts loaded**: full 755,662 CASP entries; fast 15,923 (2.11%) = 366 kept + 15,557 in the pack,
  of which 6,299+ are overrides of EA parts (they replace EA's own entry; new CC parts ~1.2%).
* **Layout**: 5 packages of 1.900 x 4 + 0.221 GB, catalog records first (001 holds all 53,208 small
  records + the first meshes). No kept package loads before the pack (`loads_before_pack` 0).
* **Build** into `E:\speedkit_test\fastmode_review\realbuild` (then deleted): 68 s for 7.82 GB, every
  resource re-read and compared; `status` fresh; `verify` ok - 0 missing, 0 different; 81,752 save/Tray
  ids, 7,555 worn + 366 kept + 1,773 tuning-named CAS parts' key lists, 245 full keys named in tuning and
  85,257 pack keys checked; installed nowhere (missing in the full library too): 5,222 CAS parts, 267
  sculpts, 468 sliders, 232 objects. `update_pack` dry run: `none`; `pack_problems`: none.
* **Independent review checks** on that plan (every key's full-library winner computed from all 1.93 M
  index rows): every pack key is the winner copy; every non-asset key with a parked winner is packed;
  every CAS part / tone / sculpt / slider / pet coat / object the saves and Tray use whose winner is
  parked is packed (5 sampled saves: 267-929 worn CC parts each from the pack, 0 missing); every
  mesh/texture/thumbnail a packed CAS part lists with a parked winner is packed; no binary (b) resource
  and no kept binary resource embeds an asset key left behind.

## Tests

`tests/test_fastmode.py` builds a fake Sims tree under `E:\speedkit_test\fastmode\t_*` (a real 2 KB
LittleMsSam script copied for its hard-coded id) and checks the park rules, each part of the plan, that
every packed copy is the full library's winner, the layout order, a real build (bit-exact, catalog
first, split over several packages), status/verify, a delta and a rebuild decision, undo of both
journals, the pack sitting in the Mods root (status, rescan, refusal while the game "runs", delta next
to it), refusals (saves, Mods, Mods_parked, outside, changed source), and - end to end - the fast profile
itself: the kept packages and the pack copied into a separate Mods folder and indexed alone give the
same bytes for every needed key as the full library. `RealLibraryParkSet` runs park_set on a private
copy of the real index (skipped without `E:\speedkit_test\fastmode\real`).

`tests/test_fastmode_review.py` (fake tree under `E:\speedkit_test\fastmode_review\t_*`) adds a third
S4S merge whose buff names a 32-bit CC CAS part and whose WickedWhims-style snippet names an `_IMG`
icon by full key, and a parked `!!!!!!!!A_first.package`: both reach the pack, and verify misses each
when a pack lacks it; a kept `!!!!!!!!B_early.package` that loads before the pack is reported by
plan_pack and verify (`order`); pack files doubled in Mods or unlisted make the pack stale (a real
update refuses or quarantines them); a park-rule change makes it stale; `kept` must cover every loaded
package; a rebuild that fails half-way (simulated at the second file move) leaves the previous pack
bit for bit; a delta reports its final path. Each of these tests fails with its fix switched off.

## Pack families, the b/c cache and disk hygiene (engine wave, 2026-09-24)

* **Pack families.** Every function that finds, builds or checks a pack takes `kind=` (a `PackKind`; default
  `FAST`). `save_kind(slot)` is the family of one save's pack (speedkit.savepacks):
  `!!!!!SpeedKit_Save_<8 hex>_###.package`, `savepack.json`, `savepack_keys.tsv`, journal kind `savepack`,
  and only that one save file counts for staleness. `is_speedkit_pack` knows all three families (fast,
  save, used CC), so plans and library fingerprints ignore every SpeedKit pack wherever it sits.
* **b/c cache** (`plan_pack(..., bc_cache=path)`). Parts (b) and (c) do not depend on the saves: they are
  cached (gzip JSON, packages by relative path) under a key made of the library's files (rel, size,
  mtime - root-independent, so profile switches do not matter), the parked set, SpeedKit's rules and the
  game's package listing. A hit skips the EA-override lookup, the index pass and the tuning scan; only
  part (a) (usedpack.plan of the saves in `refs`) is planned. Part (a) adds no text resource the tuning
  scan would miss (its tuning/SimData/strings are parked winners, which (b) holds already), so a cached
  plan equals an uncached one key for key (tests/test_savepacks.py). `cached_bc(lib, parked, game,
  path)` answers "is there a valid cache?" (read-only); `stats['bc_cache']` is `hit`, `miss` or `off`.
* **Disk hygiene.** `prune_quarantine(home, keep=1)` keeps only the newest previous copy of each pack
  family in SpeedKit's quarantine and deletes older ones (exact SpeedKit pack names only, only in
  quarantine folders of fastpack/savepack/usedpack journals, never in open journals); each pruned copy
  is marked in its journal (`pruned` on the step, the journal's `pruned` list) and a committed journal
  whose pack copies are all gone gets the state `pruned` (it can no longer be undone). New pack files an
  undo set aside (`_undone_new`) count as copies too. `build_pack(..., prune=True)` /
  `update_pack(..., prune=True)` prune after a successful run; speedkit.api always does.
  `cleanup_staging(home)` removes what a crashed build left in `SpeedKit\staging\<journal>` (its staged
  pack files, manifest and keys file; a staging folder records its owner pid in `.speedkit_owner.json`, so
  a running build is never touched) and marks that journal `failed: interrupted`.

# usedpack - a lean pack of the CC your sims and lots use

`speedkit/usedpack.py` builds `SpeedKit_UsedCC_001.package, 002, ...` holding only the custom content
the user's saves and Tray actually reference, so a light profile can load a few GB instead of the
whole 259 GB library while every sim keeps its look.

```python
from speedkit.library import Library
from speedkit import usedpack as U

refs = U.scan_references()                  # saves + Tray -> ids (cached in data/used_refs.sqlite)
lib = Library()                             # a library index that is up to date (scanned by its owner)
p = U.plan(lib, refs)                       # read-only: which resources, from which copy
U.build(p)                                  # dry run: the package layout
U.build(p, dry_run=False)                   # writes SIMS\SpeedKit\usedpack through a Journal
U.verify(U.DEFAULT_OUT, refs, lib=lib)      # [] = every used library resource is in the pack
U.is_stale(U.DEFAULT_OUT)                   # True once a save/Tray file changed after the build
```

`scan_references()` uses worker processes: call it under `if __name__ == '__main__':` (Windows spawn).

CLI: `python -m speedkit.usedpack scan|plan|missing|build [--really]|verify|stale [--backups]`.

## Steps

**scan_references(saves_dir, tray_dir, cache_db, workers=3, include_backups=False) -> Refs**
Reads every current save slot (`Slot_*.save`) and parseable Tray file (`.householdbinary`,
`.trayitem`, `.blueprint`, `.room`; thumbnails are skipped). A schema-less protobuf walk finds values
by the field-number path that leads to them (patterns taken from the game's own `.proto` files):
worn CAS parts (outfits, genetics, occult forms, mannequins, club/career/retail uniforms, matchmaking
NPCs), reward / thrift / custom-colour part ids, skin tones, sculpts, sliders, pet coat layers, and
object definition ids on lots and in inventories. Every field number was checked against the
game's own schema (`Game\Bin\Python\generated.zip`). Results are cached per file by a content
fingerprint (blake2b of the whole file: a re-save can keep a package's first and last MiB while ids
in the middle change), so a re-run only parses new or changed files. The game's backup rotation
(`.save` -> `.ver0` -> `.ver1`) is a rename that keeps size and mtime, so a renamed file takes its
fingerprint over without being read. `.ver` backups are parsed only with `include_backups=True`.
Per sim it also keeps the name, household and worn ids for the "missing CC" report. A worker reads
the whole file into memory, checks that the bytes are exactly the ones fingerprinted, closes it and
only then parses (a big save takes ~40 s to parse). A file that changed in between (the game saving)
is not cached and shows in `refs.stats['errors']`; `plan()` then refuses until it is rescanned.

**Reading without getting in anyone's way.** Python's `open()` on Windows does not grant delete
sharing, so while it holds a file no other program can rename it: the game's save rotation
(`Slot.save` -> `.ver0`) fails with a sharing violation, and `mods_switch.py`'s `shutil.move` of a
package copies it, cannot delete the original and stops before saving its manifest - the package is
then in both Mods and Mods_parked. usedpack therefore opens every save, Tray, library and game
file with `FILE_SHARE_DELETE` (`_open_read`); a renamed or moved file keeps reading correctly.
`tests/test_usedpack_review.py` shows both failures with a plain handle and that they are gone.

**load_game_ids(game_dir, cache_db) -> GameIds** - instances of every type in every game package
(read-only on `E:\The Sims 4`), plus where every game CASP, TONE, sculpt, SMOD and pelt copy sits,
so `plan()` can read the EA ones sims wear (`GameIds.read(t, ids)`). Cached in
`data/game_ids.sqlite`, rebuilt when the package list or sizes/mtimes change (a patch).
Independent of the other components' game index. A game folder with no packages (wrong path, drive
not mounted) raises `FileNotFoundError` and leaves the cache alone - an empty id set would silently
drop every default replacement and mistake EA ids for CC.

**plan(lib, refs, roots, include_backups=False) -> PackPlan** (read-only)
* CAS: every CASP whose instance a sim wears (plus the reward/thrift/custom-colour ids that are in
  the library), every key in its resource-key list (GEOM, RLE2, LRLE, RLES, _IMG, RMAP, BOND...),
  with the research's fallbacks - same type under another group, then another texture type with
  the same instance - when the exact key is neither in the library nor EA's; tuning refs (BUFF)
  are left out. CAS thumbnails (THUM, same instance).
* Looks: CC skin tones (TONE + their textures, referenced by instance), sculpts and sliders
  (SCUL/SMOD + BGEO/DMAP/BOND/HotSpotControl), pet coat layers (0x26AF8338 + textures).
* Default replacements (`ea_overrides=True`): a library resource with the exact key of an EA mesh
  or texture changes every sim wearing that EA item. `plan()` reads every game copy (base, packs,
  delta patches) of the EA parts, skin tones, sculpts and sliders the sims use and packs the library
  copies of the keys they list, plus library CAS thumbnails of those EA parts. Without this a lean
  profile would silently drop e.g. the specular DR in `Mods_parked/scripts/00s.package`.
* Objects: CC OBJD/COBJ used on lots or in inventories, their thumbnail, models, LODs, footprints,
  slots, rigs, materials and textures; the object's own tuning + SimData only when they come from the
  same package as the OBJD (never an unrelated mod's override of EA tuning); whole STBLs of the COBJ's
  package that hold its name/description hashes.
* Walls/floors: lot architecture is not decoded, so every CC wall and floor (CWAL/CFLR + materials +
  textures) is included as a safety net (`build_surfaces=True`, a few KB in this library).
* For each key the copy first in `lib.load_order(roots)` is used - the one the game uses. Copies in
  packages deeper than Resource.cfg reaches never load and are never used.
* `absent`: referenced 64-bit ids installed nowhere; `unloadable`: in the library only too deep to
  load; `households`: per household, which sims wear which CC that is installed nowhere.

**build(plan, out_dir=SIMS\SpeedKit\usedpack, max_package_bytes=1.9e9, dry_run=True)** - resources
are copied bit-exact (`PackageWriter.add_raw`) in catalog-first order (CASP, THUM, TONE, OBJD, COBJ,
STBL, other small resources, then meshes/textures), split into packages of at most 1.9 GB. Writes
`usedpack.json` (sources, the saves/Tray fingerprints, counts, bytes, absent ids, households) and
`usedpack_keys.tsv` (every key with its source package). `max_package_bytes` may not pass 2 GiB
(no bigger package has been seen loading in-game). A real run:
* needs `out_dir` inside the Sims 4 folder but not in `saves` or `Tray`; the profile tool decides
  where the pack finally lives;
* refuses while the game runs - when it starts and again after the copy (which takes minutes),
  right before anything is moved;
* checks every source package still has the size/mtime the plan saw (`PlanStale` otherwise); a
  package the other tool moves between Mods and Mods_parked, before or during the copy, is found at
  the same relative path;
* refuses when the Sims 4 drive lacks the pack's size + 1 GiB;
* stages under `SpeedKit\staging` and moves files into place through a `Journal`: the old
  `usedpack.json` is moved out first and the new one arrives last, so a half-replaced pack never has
  a manifest vouching for it; older pack files are quarantined, never deleted;
* if anything fails once files have started moving (or the run is interrupted with Ctrl-C), the
  journal is undone at once and `out_dir` holds the previous pack again; if even that fails, the
  error names the journal to undo. A finished build is undone with `journal.undo(result[0]['journal'])`.

**verify(out_dir, refs, lib=None)** lists referenced ids (parts, tones, sculpts, sliders, pelts,
objects) the pack lacks; `[]` means complete. With `lib` it is exact: every referenced id that has a
loaded library copy - CC, or a library override of an EA id whatever its size - must be in the pack;
ids installed nowhere show only with `include_absent=True`. Without `lib` it reports 64-bit ids
that are neither in the pack nor EA's nor recorded by the build as absent/unloadable (small ids
cannot be told from EA ids without the library).
**is_stale(out_dir)** is True when a save/Tray file is new or changed since the build (whole-file
fingerprints; size+mtime first, so it is cheap).

## Placement note for the profile tool

The pack holds the full-library winner of each key, including the library's default replacements of
EA meshes/textures that worn EA items use. Loaded together with the originals it changes nothing
(identical bytes whichever loads first). In a lean profile, a package kept in Mods that holds a
*different* copy of a pack key wins or loses depending on which loads first; place the pack
accordingly (usedpack_keys.tsv lists every key with its source and why it is in the pack).

## Numbers (this machine, 2026-09-24, read-only; library index = refreshed private copy, 627 packages)

| | current slots + Tray | + 35 .ver backups |
|---|---|---|
| save/Tray files parsed | 374 (10 slots, 364 Tray) in 96 s, 3 workers | +33 in 291 s |
| re-scan, nothing changed | 0.8 s | |
| pack keys / on disk / uncompressed | 54,121 / 7.00 GB / 21.9 GB | 58,573 / 7.47 GB / 23.3 GB |
| source packages | 203 (397 keys from Mods, rest Mods_parked) | 204 |
| layout | 4 packages: 1.90 + 1.90 + 1.90 + 1.31 GB | 1.90 x 3 + 1.78 GB |
| CC CASPs worn / packed CASP keys | 6,978 CC + 425 overrides of EA / 7,555 | 7,636 + 595 / 8,466 |
| EA default replacements packed | 989 part keys (58 MB) + 178 look keys (9 MB) | 1,099 part keys (64 MB) |
| CC tones / sculpts / sliders / pelts | 29 (+21 EA overrides) / 69 / 281 / 0 | 41 (+21) / 71 / 284 / 0 |
| CC objects on lots / walls+floors | 15 / 87 | 16 / 87 |
| worn CAS ids installed nowhere | 5,222 (5,409 with reward/thrift ids) | 5,536 (5,763) |
| households wearing CC installed nowhere | 580 | 685 |
| plan() time | 45-49 s | 46 s |

By type (current): GEOM 4.04 GB, RLE2 1.18 GB, LRLE 0.94 GB, _IMG 0.55 GB, RLES 0.17 GB, THUM 70 MB,
DMAP 47 MB, CASP 3.1 MB. CASP refs: 52,070 exact, 4,356 EA's, 338 other-group and 98
other-texture-type fallbacks, 256 missing everywhere, 189 tuning refs (BUFF) skipped.
`load_game_ids()` rebuild: 5,080 packages in 56 s (538,327 CASP copies located). Reading the worn EA
parts: 91,874 game CASP copies, 0 read errors. A new 77 MB save re-scans in 35 s; a backup rotation
costs 0.1 s.

Checked on real data (built into `E:\speedkit_test\usedpack` only): a catalog-only pack of the real
plan (7,977 keys) verifies complete with and without `lib`; a 3,757-key sample (all default
replacements, fallbacks, looks, objects, surfaces + 2%) split at 100 MB is bit-exact from 196 source
packages.

## Review notes (2026-09-24)

* `HouseholdData.cas_inventory` (field 17) is `repeated uint64 [packed=true]` in the game's schema;
  the scanner now reads the packed form too. The research found no values there in any of the 44
  saves, so the numbers above do not change, but the pattern change invalidates `used_refs.sqlite`
  once: the next `scan_references()` re-parses every save and Tray file (~96 s, ~290 s more with
  backups).
* Tests: `python tests/test_usedpack.py` and `python tests/test_usedpack_review.py` (the second
  runs on fake trees under `E:\speedkit_test\usedpack_review`: files moved/renamed by others while
  read, a save changed after its fingerprint, the game starting mid-build, a failed move rolled back,
  a failed rollback, packages moved during the build, deleted and duplicate entries in one package,
  a RefPack CASP in a non-ASCII folder, the game-id cache).

## Known limits

* Lot architecture (walls/floors/terrain paint) and Tray blueprints/rooms are not decoded; CC walls
  and floors are all included instead, and blueprints are only scanned for the ObjectData.guid tag.
* CAS parts that script mods use through tuning (not worn in any save) are not included - script mods'
  companion packages must stay whole in any profile.
* Whether the game resolves a CASP reference through the other-group / other-texture-type fallbacks
  is unverified in-game; the pack includes those resources either way.
* Default replacements are packed only for EA items sims wear (parts, tones, sculpts, sliders);
  DRs of EA objects are not followed (the library has none of MODL/MLOD and 26 FTPT overrides).
* Skin tone / sculpts of mannequins outside SaveGameData.mannequins and the thrift store (mannequin
  objects, club/career/retail uniforms) are not read; their outfits are.
* New townies can only pick from CC in the pack.
* The pack reflects the library index it was planned from: re-scan the library (its owner's job)
  before planning, since the other tool moves packages between Mods and Mods_parked.

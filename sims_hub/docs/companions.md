# companions: S4S manifests, script companions, game index

Three read-only building blocks for the merger / dedup / profile tools. None of them writes under
`Documents\Electronic Arts\The Sims 4` or `E:\The Sims 4`; they only write their own caches in `data\`.

## speedkit/manifest.py - Sims 4 Studio merge manifest

S4S marks a merged package with one resource of type `0x7FB6AD8A` (FNV-1 32 of
"s4smergedpackagemanifest"), key `7FB6AD8A:0:0`, zlib, first in the file. It lists, per source
package, the keys that came from it; S4S "Unmerge" rebuilds the sources from it.

```python
from speedkit import manifest as M
root = M.read(path)                          # Folder tree or None (not merged)
data = M.read_payload(path)                  # decompressed payload bytes
assert M.encode(M.decode(data)) == data      # byte-exact codec
M.sources_of(data)                           # {'Source name': {(t, g, i), ...}}
M.rewrite_without(data, removed_keys)        # after taking resources out of a merged pack
data = M.build_flat([('Pretty Hair', keys_a), ('Other CC', keys_b)])
with PackageWriter(out) as w:
    w.add(M.MANIFEST_KEY, data)              # FIRST, then the resources
M.unmerge_report(root, pkg.entries)          # what an S4S unmerge would lose
```

Rules for packages SpeedKit writes (from S4S's own IL, and running its merge/unmerge on scratch files):
- exactly one resource of type 0x7FB6AD8A (S4S finds it by type; a second one makes it refuse);
- every resource listed under the source it should return to (unlisted ones are dropped on unmerge,
  listed-but-missing ones are skipped silently);
- names pass `sanitize_name()` and are unique ignoring case in their folder (S4S joins names into
  paths unchecked and writes with File.Create on a case-insensitive disk). `build_flat` does both;
  `decode`/`encode` stay faithful to whatever is in existing manifests (real ones contain trailing
  spaces, dots and ".package" inside names - `check_names()` reports those).
- "ignoring case" is `fold_name()`: each character upper-cased on its own like NTFS, then
  lower-cased, so pairs such as `s`/`ſ`, `σ`/`ς`, `i`/`ı` also count as the same file. The length cap
  (`MAX_NAME` = 180) is in UTF-16 units, the unit NTFS's 255-per-name limit uses (180 emoji used to
  pass as 360 units). Lone surrogates and the reserved names `CONIN$`, `CONOUT$`, `COM¹-³` and
  `LPT¹-³` are replaced or prefixed. ASCII and Latin-1 names come out exactly as before.

Real library (read-only): **165/165 manifests re-encode byte for byte**, 36,758 sources, 2,393,908
keys; 25 of the 165 packs would unmerge losslessly.

## speedkit/companions.py - which packages belong to a script mod

```python
from speedkit import companions as C
v = C.classify(lib)                 # {pkg_id: Verdict(kind, script, reasons)}
C.never_merge(v[pid])               # core/addon/orphan/weak/broken -> True
C.load_order_sensitive(rel)         # '!', '~', '_', '[', 'zz', '000'/'01_' prefixes, NSW lighting
C.script_modules(lib)               # {'wickedwhims': 'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script', ...}
C.script_bearing_sources(lib)       # {pkg_id of an S4S merge: ['TURBODRIVER_WickedWhims_Tuning', ...]}
```

Kinds: `core` (ships with its script), `addon` (third-party content needing a script),
`orphan` (needs a script / required mod that is not in the library), `weak` (name or CAS-asset id
link only), `tuning` (XML tuning, no script link), `cc` (no tuning), `empty`, `broken`.

Evidence: tuning `m=` modules (and module tuning `<M n=...>`) that are not the game's; classes and
instance types the game does not define; tuning names and 64-bit ids a script hard-codes; PlumbBuddy
/ Llama Logic Mod File Manifest `required_mods` (resolved to a script, or to another package's
manifest name whose link is inherited); same file name as a script once `_Scripts`/`_Tuning`
suffixes are dropped (fixes UI_Cheats_Extension, which research rated only "weak").

Differences from research/merging/companions.py: required mods that another installed package
provides are no longer "orphan" (10 LittleMsSam add-ons are now `core`), while a required mod whose
providing package itself needs a missing script (XML Injector) still counts as missing; same-name
packages are `core` (UI_Cheats_Extension, FallenCore_Tunings); only `.pyc`/`.pyo` count as script
modules (the game never imports `.py`); script int constants that are masks or hash parameters
(2^64-1, 2^64, FNV-64 constants) are not treated as resource ids.

Cache: `data\companions.sqlite` - per-package XML facts and per-script bytecode facts keyed by
(root, rel, size, mtime) (a file moved between Mods and Mods_parked reuses its facts), the game's
Python index (until a patch changes the Gameplay zips) and the last verdicts with a signature of
the rules, all scripts and all packages. `idref` reads the library index, so scan the library first.
A cold run commits facts every 20 packages and waits up to 60 s for the cache's lock, so dedup
and a CLI run can share it.

XML root attributes are read in either quote style and with spaces around `=` (`m = 'x.y'` is legal
XML). Before FACTS_VERSION 4 such a companion lost its `m=`/`i=` evidence and came out `cc`
(mergeable). No package in this library is written that way (0 of 25,808 roots differ), but the
first run after the upgrade re-sniffs everything once (~25 s). `roots` may be given as one name
(`classify(lib, roots='Mods_parked')`); a bare string used to be matched as a substring, so
'Mods_parked' also let in 'Mods'. A tuning instance type that neither the game nor any script
defines now also marks its resource as script-bearing, like a missing module or class does.

Real library, 2026-09-24 (626 packages, read-only):

| kind | packages |
|---|---|
| cc | 293 |
| tuning | 156 |
| addon | 82 |
| core | 39 |
| orphan | 28 |
| weak | 28 |

never-merge 177, load-order-sensitive names 100; 46 S4S merges (66.8 GB) carry script content from
920 sources (m27 holds the old TURBODRIVER_WickedWhims_Tuning, m9 holds lot51_plumbbros).
Cold run 26-48 s (XML sniffing of ~26k resources), rules/packages changed but facts cached ~5-9 s,
nothing changed 0.2 s. Re-measured after the review (627 packages, one new WickedWhims add-on
in Mods): addon 83, the other kinds unchanged, never-merge 178, still 920 sources; cold 23.5 s.

Known limits (review):
- A .ts4script deeper than one folder never loads in-game, but it still counts as installed.
  Its packages come out `core`/`addon` rather than `orphan`, which is never-merge either way.
- A companion with no tuning (e.g. only GFX or strings, like UI_Cheats_Extension) is `cc` if its
  script is not in either root: nothing links it any more.
- Mod File Manifest `required_mods` make a package `addon`/`core`/`orphan`, but they do not mark a
  merged pack's source as script-bearing. That affects 0 of the 3 merged-pack sources with
  requirements today, since all 3 are listed for other reasons.
- `load_order_sensitive` follows the spec's characters only. Names like `(marsosims)...` or a
  `- Multi Pack Requirements (check me)` folder (15 packages) are not flagged.
- The CLIs print names with `backslashreplace`: CJK names such as `sim/[dreamlike] preset
  sets无病毒版！！.package` and 294 mojibake S4S source names used to crash them (UnicodeEncodeError)
  whenever output went to a pipe or file.

## speedkit/game_index.py - the game's own resources

```python
from speedkit.game_index import GameIndex
gi = GameIndex()                    # data\game.sqlite, E:\The Sims 4
gi.scan()                           # incremental by size + mtime
gi.has(t, g, i); gi.ids_of_type(0x034AEECB); gi.where(t, g, i)   # -> [(rel, priority)]
gi.override_keys(lib)               # library keys that also exist in the game
```

Indexes exactly the packages the game's cfgs load: `Data/Client/Resource.cfg`,
`Data/Simulation/Resource.cfg`, `<EP|GP|SP|FP>xx/ResourceClient.cfg` + `ResourceSimulation.cfg`,
and the same under `Delta/<pack>/` (Select...End console blocks and `*_LE.cfg` skipped). All 5,080
.package files on disk are matched by some cfg line; priorities range -40..-9.

Real numbers: cold scan **46-72 s** (5,080 packages, 82.5 GB, 4,855,988 index rows, 2,616,474
distinct keys, 4,035 string-table packages; the range is disk contention from other tools), warm
rescan 1-8 s, database 355 MB. 96,751 rows are delta "deleted" records; they are ignored.
`override_keys` on the full library: 14,043 distinct keys = 21,009 library resources in 158
packages (same as research/merging/ea_overrides.json), 7.6 s on an idle disk, ~35 s under load.
During the query it holds a read lock on the library database. library.sqlite uses a rollback
journal, so that blocks writers; pass a private copy, not the shared file. `override_keys()` and
`ids_of_type()` raise RuntimeError on an index that was never scanned, because an empty answer
would read as "nothing overrides the game". A UTF-8 BOM in a cfg no longer hides its first
`Priority` line. `roots` may be a single name.

The DLC toggler's `dlc.ini` is not read. A pack switched off there is still indexed, which errs
on the safe side for override detection.

## Tests

```
python tests/test_companions_manifest.py     # synthetic + all real manifests byte-exact (read-only)
python tests/test_companions_classify.py     # fake Mods/Mods_parked tree + real library (read-only)
python tests/test_companions_game_index.py   # fake game folder + real cfg coverage (read-only)
python tests/test_companions_review.py       # adversarial fake tree: RefPack / cut zlib / const-type index /
                                             # duplicate keys / deleted-only / Unicode names / both roots /
                                             # quoting / CLI on cp1252 / cfg BOM / odd lib path / unscanned index
```

Against the pre-review code, 9 of the 18 review tests fail. The unscanned-index test was added
later.

Scratch data lives in `E:\speedkit_test\companions\` and is removed by the tests, except the
18 MB verdict cache `companions_real_test.sqlite` that keeps re-runs fast.

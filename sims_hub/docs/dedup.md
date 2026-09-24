# dedup: remove duplicate resources without changing what the game loads

Modules: `speedkit/hashing.py` (content hashes + cache) and `speedkit/dedup.py` (plan, report, apply, undo).
Tests: `tests/test_dedup.py` (fake Sims tree under `E:\speedkit_test\dedup`) and `tests/test_dedup_review.py`
(odd packages and apply() guards, fake tree under `E:\speedkit_test\dedup_review`).

## What it does

About 250k type/group/instance keys in the library are stored in 2-10 packages at once, mostly because
the same CC file was merged into several Sims 4 Studio merges. `plan()` finds copies that can go,
`report()` explains them, and `apply()` removes them one package at a time through a Journal. After the
run, apply() checks that the game would use the same content for every key. If anything differs, it
undoes the run by itself.

- **identical** policy (default): for a key whose copies all hold the same data (compared decompressed),
  one copy is kept and the rest are dropped. The copy kept is:
  1. a protected package's copy, if there is one. Every protected copy stays.
  2. otherwise the earliest-loaded copy in `Mods`, if the key is there, so the lean set the game loads
     now keeps every key.
  3. otherwise the earliest-loaded copy.

  This is safe under any load order.
- **winner** policy (experimental): the identical policy, plus the losing copies of conflicting keys
  are dropped. The first-loaded copy stays, as does the first copy in `Mods`. Keys held twice inside
  one package are left alone. This keeps what the game loads now, but the other versions are gone once
  the quarantine is emptied.
- Protected packages (never rewritten, never lose a resource) are:
  - the script companions from `speedkit.companions`. Verdicts core, addon, orphan, weak and broken
    count. If that module fails, `research/merging/companions.json` is used instead.
  - every package in a folder that holds a `.ts4script`.
  - `.ts4script` files themselves, which are never touched.

  `include_merged=False` (`--unprotect-merges`) lifts the protection only from S4S merges that hold
  stale copies of standalone script-mod files (`stale_copy_merges()`): every merge source that carries
  script-linked resources (`companions.script_bearing_sources`) has a standalone protected package of the
  same name, or the verdict is `weak` and no such source was found. Merges that are script add-ons in
  their own right (the WickedWhims animation packs in `Mods`, anim1-5, a mod's only copy of its tuning)
  stay protected. Without the classifier nothing is unprotected.
- A package whose remaining resources are only metadata is quarantined whole. The metadata types are
  the S4S manifest, and also the NameMap with `ignore_namemap=True`. Any other package that loses
  copies is rewritten:
  - the kept resources go in their original order through `PackageWriter.add_raw`, bit-exact.
  - the S4S manifest (`7FB6AD8A`) is rewritten without the removed keys through `speedkit.manifest`,
    so S4S can still unmerge the package.

## Facts it relies on

- Load order: the game walks Mods depth-first in NTFS name order, and the first-loaded copy of a key
  wins. This was proven in-game for tuning in 2017 and has not been re-tested on 1.126 for CC.
  `Library.load_order()` reproduces the walk, and Mods_parked mirrors Mods paths.
- Duplicates in this library:
  - 226,221 keys are byte-identical and 3,408 are identical once decompressed.
  - 20,067 keys conflict.
  - 7 keys are undecidable. These are corrupt RLE2 eyebrow textures in sim/111 and
    PRALINESIMS_MERGED that are not valid zlib.
- The S4S manifest is tool metadata: the game never reads it. Whether the game reads CC NameMaps is
  unknown, so by default they count as content.
- A few zlib streams end without a final block but still inflate to the full size. A stream is accepted
  when its output length equals the index's uncompressed size.

## Hash cache (`data/hash.sqlite`)

- `copy(root, rel, size, mtime_ms, t, g, i, off -> raw, data, err)`: one row per hashed copy.
  - Lookups ignore `root`, so a package that the other tool moves between Mods and Mods_parked is not
    read again.
  - A rewritten package has a new size or mtime, so it gets new rows.
- `content(raw, comp -> data)`: a data hash is computed once per stored byte string.
- Raw hashes (blake2b-128 of the stored bytes) are computed for every copy. Data hashes (of the
  decompressed bytes) are computed only for keys whose copies are stored differently.
- Reading is per package, sorted by offset, with neighbouring resources read in one call, on 8 threads.
  A package whose size or mtime differs from the library index is not read.
- Read errors are never cached. Decode errors are cached.

## Command line

```
python -m speedkit.hashing  [--db data\library.sqlite]            # hash duplicated keys, print counts
python -m speedkit.dedup report [--scan] [--policy identical|winner] [--ignore-namemap] [--unprotect-merges] [--json out.json]
python -m speedkit.dedup apply  [...same...] [--journal-home DIR] [--min-free-gb 5]   # dry run
python -m speedkit.dedup apply  [...] --really                    # real run: refuses while TS4_x64.exe runs
python -m speedkit.dedup journals
python -m speedkit.dedup undo <journal id>
```

## Safety

- `plan()` and `report()` are read-only. They write only to the hash cache and the companions cache.
- `apply()` is a dry run unless `dry_run=False`. A real run refuses when:
  - the game is running;
  - the library index does not match the files, `.ts4script` files included (rescan and plan again);
  - a package holding a kept copy has changed since the plan was made;
  - any copy that the before/after check depends on cannot be read.
- Each package is handled like this:
  1. The new file is written as `<name>.package.speedkit-dedup.writing` next to the original and
     renamed to `.speedkit-dedup` when complete.
  2. It is re-read and verified: same keys in the same order, identical index fields, every kept
     resource byte-identical, and the manifest reads back.
  3. `Journal.replace` moves the original to the quarantine and puts the new file in its place.
  4. Packages that become empty go through `Journal.quarantine` instead.

  Nothing is deleted.
- After the run, apply() rescans the library and compares the effective content of every duplicated
  key (the data hash of the first-loaded copy) in two scopes: `Mods`+`Mods_parked` laid over each
  other, and `Mods` alone. It also checks that no key of a changed package disappeared. On any
  difference it undoes the journal and raises `InvariantError`. Any other failure (a verification
  mismatch, the game being started, Ctrl+C) also undoes the journal. If the undo itself is refused,
  for example because the game is running, the error names the journal to undo later. Every finished
  step is complete on its own: each dropped copy has a kept copy elsewhere.
- The journal and quarantine go in `<Sims 4 folder>\SpeedKit` by default. The Sims 4 folder is the
  parent of the library roots, so a fake tree only ever journals into itself. If the roots have no
  common parent, a real run refuses unless `sims=` is given (it never falls back to the real folder).
- A real run also refuses when:
  - the journal/quarantine folder lies inside a mod folder (the game would load the quarantined files);
  - a package of the plan lies outside the Sims folder;
  - a package exists in both Mods and Mods_parked (the other tool never restores such a parked file,
    so a copy kept there might never load; `report()` lists them under `in_more_than_one_root`);
  - a journal with the id the new one would get already exists. Journal ids have one-second resolution
    and `speedkit.journal.Journal()` overwrites an existing journal file with the same id, which would
    lose the earlier run's undo record. apply() waits up to 2 s for a free id.
- If the check after the run cannot be made (an error, or Ctrl+C while it runs), the journal is undone too.

## Disk space

The quarantine keeps every replaced original.

- **Quarantine on C: (default).** The move is instant, but C: grows by the size of every rewritten
  file until the quarantine is emptied.
- **Quarantine on another drive (`--journal-home E:\...`).** Each original is copied there, and C: only
  needs room for the file being written. The largest new file is 2.1 GB.
  Read-only files are skipped in this mode: a move across drives copies the file and then deletes
  it, and Windows refuses to delete a read-only file (210 of the 627 library packages are read-only).
  On the same drive the move is a rename, which works for read-only files.

`apply()` skips a package when a drive would fall below `min_free` (5 GiB). Rewrites run in order of
most bytes saved per byte written. `free_space()` simulates the same run.

## Measured on the real library (2026-09-24, dry run, private copy of the index, game running)

The library had 627 packages in the index at the time: Mods held 6 packages (1.0 GB: FitStudio test
exports, two WickedWhims animation merges and the WickedWhims tuning, all protected) and Mods_parked the rest.

| plan | copies dropped | stored bytes | quarantined | rewritten | skipped | saved after emptying quarantine |
|---|---|---|---|---|---|---|
| identical, merges with script tuning protected (default, 345 protected) | 204,034 | 35.15 GB | 17 (2.52 GB) | 104 | 1 (sim/91: key twice) | 35.16 GB |
| identical, `--unprotect-merges` (334 protected: 11 merges freed) | 247,181 | 40.23 GB | 17 | 115 | 1 | 40.24 GB |
| identical, `--ignore-namemap` | 204,034 | 35.15 GB | 26 | 95 | 1 | 35.16 GB |
| winner (experimental) | 235,494 | 35.96 GB | 44 (24.0 GB) | 130 | 1 | 35.97 GB |

- Nothing in `Mods` changes under the default plan: every package there is protected.
- The default protection keeps 151,614 extra copies (10.1 GB). Most are in the 53 S4S merges that the
  classifier flags for carrying script-linked content. `--unprotect-merges` frees only the 11 of them
  whose script content is a copy of a standalone companion (sim/m9 holding lot51_plumbbros) or whose
  link is weak with no script-bearing source (sim/113, 114, 120, 126, 53, 54, 55, m21, DZSkinDetails,
  SkinDetails[MERGED]2). It then keeps 108,467 copies (5.1 GB) for protection and changes nothing in
  `Mods`. The other 42 stay protected: sim/m27, for example, also holds FallenCore_Tunings and other
  script tuning that exists nowhere outside merges. (Before this rule the option freed all 53 merges,
  including the WickedWhims animation packs in `Mods`: 1,162 copies there.)
- Simulating each plan's end state from the hashes gave no changed and no missing key, in both scopes,
  for all three policies.
- Free space for the default plan:
  - The rewritten files total 124.3 GB against 59.4 GB free on C:.
  - With the quarantine on C:, one run does 85 of 121 packages (68 of 104 rewrites) and saves
    34.8 GB of 35.2 GB. The rest needs the quarantine emptied first.
  - With the quarantine on E: (310 GB free), space is no limit and C: never needs more than 2.1 GB extra,
    but the 28 read-only targets (2.7 GB of originals) are skipped: one run does 93 of 121 packages (86 of
    104 rewrites) and saves 33.15 GB.
- Time:
  - Hashing the first time takes about 105 s for 80 GB. With a warm cache, `plan()` takes 27-58 s,
    report 4-8 s, and a dry apply 0.1 s.
  - Before changing anything, a real apply reads the effective copies it does not yet have data hashes
    for: 201,319 copies, 32.2 GB, once (then cached).
- Stale script tuning:
  - 95 (companion, merge) pairs are merges holding a copy of the companion file itself, with 205 stale
    differing keys. Examples: sim/m27 holds TURBODRIVER_WickedWhims_Tuning (6,635 identical, 48 differ);
    sim/113 and sim/126 hold 00s (44 differ); sim/m9 holds lot51_plumbbros (9 differ). In all of these
    the standalone copy loads first.
  - 1,340 keys are other mods' deliberate overrides, for example AllTheFallen tuning over WickedWhims keys.

## Limits

- Dedup assumes the library is used as a whole. If a stripped package is later enabled without the
  package that kept the copy, that resource is missing. Undo the dedup journal before re-arranging
  Mods/Mods_parked by hand. The other tool's lean set is covered, because `Mods` always keeps its keys.
- First-loaded-wins has not been re-tested on 1.126 for CC. The identical policy does not depend on it;
  the winner policy does.
- Packages holding one key twice with different content (sim/91) are skipped, because the package
  writer refuses a key twice. So are packages where two index entries of a dropped key point at the
  same bytes.
- Undecidable keys (unreadable or corrupt copies with differing bytes) are never touched.
- Plan while the lean set is in `Mods` (or keep that set protected). `Mods` keeping its keys protects
  the set that is in `Mods` when the plan is made. With the default protection every package of the
  other tool's lean set is protected, so a plan made in "full" mode is also safe for it.
- Journal limits (speedkit.journal, not changed here): if the run is interrupted between moving the new
  file into place and recording that step, or if an undo fails half-way (for example a file in use), a
  later `undo` refuses. The files are then consistent (each finished rewrite is complete and verified),
  but restoring the originals from `SpeedKit\quarantine\<id>` has to be done by hand.

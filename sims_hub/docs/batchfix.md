# CC that may need a Sims 4 Studio fix

Some game updates change how The Sims 4 reads custom content. Sims 4 Studio (S4S) then adds a *batch fix*: it
rewrites every affected file in a folder, usually the Mods folder. Players often don't know which of the many
batch fixes they need. This feature finds CC that matches a well-documented problem and names the exact fix to
run.

**The Hub never changes a CC file.** It reads the files, lists the ones that *may* need a fix and gives the reason
for each. It names the S4S menu path and can set files aside through the usual undoable change (`set_aside` with
`why: "fix"`). Nothing is deleted, every change can be undone, and nothing changes while the game runs.

| Part | Where |
|---|---|
| Detectors, results store | `speedkit/batchfix.py` |
| API | `speedkit/api_care.py`: `batch_fixes()`, `batch_fix_scan()`, `batch_fix_open(rel)`; `patch_day()['batch_fixes']` |
| Server | `speedkit/hub/care_routes.py`: `GET /api/batchfix`, `POST /api/batchfix/open`, task `batch_fix_scan`, `set_aside` with `why: "fix"` |
| Page | `speedkit/hub/web/js/batchfix.js` (card on Tools, line in the patch-day notice), `css/care.css` (`.bf-*`) |
| Preview data | `speedkit/hub/stub_care.py` (`batch_fixes`, `batch_fix_scan`, `batch_fix_open`) |
| Tests | `tests/test_batchfix.py`, `tests/test_batchfix_server.py`, `tests/test_batchfix_ui.py` (fakes: `tests/batchfix_fakes.py`) |

## The fixes that are detected

All five are in S4S under **Tools › Content Management › Batch Fixes › CAS**.

| Fix (S4S name) | Game update | What is wrong in the file | Rule used |
|---|---|---|---|
| **Update Sliders (Werewolf Patch)** | June 2022 (Werewolves) | The slider's HotSpotControl resource (type `0x8B18FF6E`) has a version below `0x0F`. The update stopped reading older ones, so those sliders do nothing. | any HotSpotControl with `version < 0x0F` |
| **Update Eye Colors for Infants (Infants Patch)** | March 2023 (infants) | An eye color (CAS part, body type 35) for toddlers but without the infant age flag `0x80`. Infants can't use it. If it replaces a game eye color, infants get the wrong (vampire) eyes. | body type 35, age has toddler `0x02` and not infant `0x80` |
| **Disable Shoes for Werewolves** | June 2022 (Werewolves) | Shoes (body type 8) for teens or older whose "disabled for occult" bits don't include the werewolf bit. Werewolves keep them on in wolf form. | body type 8, ages teen-elder, species human, occult bits without `32` (or a part too old to have the field) |
| **Disallow CC for Default Garment** | none (the flag is copied from the game item the CC was cloned from) | A new clothing part with a "default for body type" flag. The game can put it on Sims by itself, most often in the nude (bath) outfit. | clothing/accessory body types (1, 5-27, 36, 42), CAS part id ≥ 2³² (not a replacement of an EA part), flags bit `0x01` or flags2 bits `0x02`/`0x04` |
| **Update CAS CC Pets Patch** | November 2017 (Cats & Dogs) | The CAS part uses the layout from before Cats & Dogs (version below `0x20`; the species field was added in `0x20`). S4S recommends this fix for missing items and the "wooden doll" look in such CC. | any CAS part with `version < 0x20` |

A file is listed once per fix, with how many of its parts match ("1 of 2 shoe items are not turned off for
werewolves.").

### Field layouts relied on

* **CAS part** (`0x034AEECB`): the layout of TS4SimRipper's `CASP.cs` (copy in `research/usedcc/casp_simripper.cs`)
  up to the occult bits. It is spelled out in `batchfix.py`'s docstring. `tests/test_batchfix.py` checks that
  every version from `0x1B` to `0x34` reads the right fields. The same synthetic parts were also checked against
  the separate CAS part parser in `wicked_animator/backend/casptex.py` while this was written.
* **Flags** (s4pi `CASPFlags.cs`): `ParmFlag` bit 0 = `DefaultForBodyType`, bit 1 = `DefaultThumbnailPart`, bit 2 =
  `AllowForRandom`...; `ParmFlag2` bit 0 = `RestrictOppositeFrame`, bit 1 = `DefaultForBodyTypeMale`, bit 2 =
  `DefaultForBodyTypeFemale`.
* **Age/gender**: toddler `0x02` … elder `0x40`, infant `0x80`. S4S's all-ages value for eyes is `000030FE`.
* **Occult bits**: `OccultType` in the game's `sims/occult/occult_enums.py`: HUMAN 1, ALIEN 2, VAMPIRE 4, MERMAID 8,
  WITCH 16, WEREWOLF 32, FAIRY 64. s4pi's `OccultTypesDisabled` (Human 1, Alien 2) shows that the CAS part field
  uses the same bits.
* **HotSpotControl**: CmarNYC's TS4SliderConverter (`HOTC.cs`: `CurrentVersion = 0x0F`; `Form1.cs` only raises
  the version, nothing else).

## Researched, but not detected

These fixes are well known, but the problem can't be told reliably from the file alone, so they are not listed.
The card does not guess.

| Fix | Why it is left out |
|---|---|
| Update LRLE Images (Werewolf Patch), Update Hairs for Color Slider Compatibility | The broken hair can only be recognised by decoding every LRLE texture and counting its colors (more than 65,536 is the problem, per TS4AlphaConverter). That is too slow for big libraries and still a guess. |
| Fix Bed Slots (High School Years EP), other Objects fixes | Detection would need the object's slot and tuning data compared against the game's own files. There is no simple marker in the file. |
| Allow/disallow CC for Fairies, other occult switches | Whether CC should show for an occult is the creator's or player's choice, not a fault. |
| Toddler preset fixes (For Rent head mesh) | S4S calls its fix experimental. Nothing in the preset tells a broken one from a working one. |
| Fix Cats & Dogs Patch Glass Hair | The look depends on the hair's textures and shader, not on a field the Hub can check. |
| The February 3, 2026 update (1.121, Royalty & Legacy) | The trackers for it (EA forum "Broken and Updated Sims 4 Mods and CC: patch 1.121", SimsVIP) list broken script mods and single CC items. No S4S batch fix tied to that update was found, so there is nothing to detect. When S4S adds one with a clear file marker, add a detector (see *Adding a fix*). |

## Accuracy

* **"May need", not "is broken".** A match means the file has the marker that the batch fix exists for. Whether it
  *shows* depends on the player: shoes on werewolves only matter to players who have werewolves, and so on.
  The page says so.
* **Default garment** is the weakest rule. Some CC is flagged as a default on purpose (for example underwear made
  to be the default nude item). Replacements of EA parts (id < 2³²) are left out for that reason. Other deliberate
  defaults are still listed, with their reason.
* **Pets patch** lists all CC made before late 2017. In a real library of 2,025 CAS parts sampled for
  `research/usedcc`, 32 parts (1.6%) were below version `0x20`, 25 of them the very old version 18.
* **Shoes for werewolves**: the werewolf bit comes from the game's `OccultType` enum. The sources show that the
  CAS part's occult field uses the same bits as that enum, but no source was found that says so for werewolves in
  particular.
* Every CAS part and slider of a file is read, not a sample. Unreadable parts are skipped (the CC browser reports
  damaged files). Resources over 64 MB are skipped.
* SpeedKit's own packs (`fastmode.is_speedkit_file`) are left out: they hold copies of the player's CC. Merged
  files made by the Hub's merger are the player's CC and are checked.
* A file in both Mods and Mods_parked is checked once, as the Mods copy.

## How it runs

* `batch_fix_scan` (task, "Check my CC" / "Check again") first brings the library index up to date
  (`Library.scan`, only changed files). Then it reads the CAS parts and sliders of **new or changed files only**,
  found with a single query on the library's resource table. Results are kept per file (size, modified time,
  `DETECT_VERSION`) in `data\batchfix.sqlite`. A second check of a 41k-file library reads nothing it has seen,
  and raising `DETECT_VERSION` makes every file be read again. zlib resources are only partly unpacked (the
  header is at the start).
* `batch_fixes()` only reads the results file. For the files it lists, it checks where each one is now: in Mods,
  parked by a mode (`parked`, with a note to get Full Start ready first so S4S sees the file), set aside by the
  Hub (`set_aside`), or gone (then it is left out). It never opens a package.
* `patch_day()` adds a short summary (`batch_fixes`). The Home notice after a game update and the *After a game
  update* card show one line: "N CC files may need a Sims 4 Studio fix (…). See which fix".
* Set aside: the card's "Set these aside instead" sends up to 500 of a fix's files that are in Mods to
  `set_aside(rels, why='fix')`. That is the patch-day mechanism, so the files are parked, stay parked in every
  mode, show under *Set aside for now* ("until it gets a Sims 4 Studio fix") and can be put back or undone
  ("Set CC aside until it gets a Sims 4 Studio fix" in Recent changes). The saves are not backed up for this
  reason (they are only for `why='patch'`).
* "Open folder" (`POST /api/batchfix/open {"rel"}`) opens only files that the last check listed.

## Steps shown to the player

1. Close The Sims 4.
2. Open Sims 4 Studio (a recent version) and choose **Tools › Content Management › Batch Fixes › CAS › *fix***.
3. Pick your Mods folder when asked. Sims 4 Studio keeps a copy of each file it changes.
4. Come back here and press **Check again**.

## Adding a fix

Add an entry to `FIXES` (id, S4S name, section, `update`, `problem`, `what`, `sources`) and a rule in
`casp_problems` / `hotc_problems` (or a new resource type in `Store.scan`'s query). Add a sentence in `why()`,
raise `DETECT_VERSION`, and add a positive and a negative case to `tests/test_batchfix.py`. Only add rules
where the file itself shows the problem.

## Sources

The S4S forum, SrslySims, Mod The Sims and the EA forums could not be opened from the build machine. Their
content was taken from search-result excerpts of the pages below. The GitHub sources were read in full.

* S4S, *Batch Fix Information*: https://sims4studio.com/thread/37124/batch-fix-information (menu path *Tools ›
  Content Management › Batch Fixes*, the CAS / Objects / Misc groups)
* SrslySims, *How to Batch Fix CC with Sims4Studio*: https://srslysims.net/tutorials/sims4studio_batchfix/
  ("Update CAS CC Pets Patch", "Update LRLE Images (Werewolf Patch)", "Update Sliders (Werewolf Patch)",
  "Disallow CC for Default")
* S4S, *Studio updates for Werewolves + batch fixes*: https://sims4studio.com/thread/28677/studio-updates-werewolves-batch-fixes;
  *Studio updates with new & revised batch fixes*: https://sims4studio.com/thread/28904/studio-updates-revised-batch-fixes;
  *Studio updates with more Werewolf batch fixes*:
  https://sims4studioofficial.tumblr.com/post/689424635086979072/studio-updates-with-more-werewolf-batch-fixes
  (the shoes fix for werewolves); *Help with werewolves and shoes*: https://sims4studio.com/thread/29014/help-werewolves-shoes
* CmarNYC, *Fixers for sliders, hair, skins after werewolf patch*: https://modthesims.info/d/668332/ ; source:
  https://github.com/Oops19/cmarNYC_TS4SliderConverter (`HOTC.cs`, `Form1.cs`, `LRLE.cs`)
* S4S, *Studio updates for infant patch and Growing Together*: https://sims4studio.com/thread/31336/studio-updates-infant-patch-growing
  (*Content Management › Batch Fixes › CAS › Update Eye Colors for Infants (Infants Patch)*); *Infant update -
  Update default eye replacements*: https://sims4studio.com/thread/31299/infant-update-default-eye-replacements;
  Pralinesims, *Info about CC updates for the infants patch*: https://www.patreon.com/posts/info-about-cc-80044208;
  fivesims, *How to update eye colour for infants*: https://www.tumblr.com/fivesims/711960124652126208 (age flags
  `000030FE`)
* S4S, *Disallow CC for Default Garment not working*: https://sims4studio.com/thread/22091/disallow-default-garment-working-s4s
  (*Content Management › Batch Fixes › CAS › Disallow CC for Default Garment*, "uncheck the nude flag")
* S4S, *Batch fix CAS CC*: https://sims4studio.com/thread/11767/batch-fix-cas-cc; *Thread for reports about
  post-Pets CC problems*: https://sims4studio.com/thread/10933/thread-reports-post-pets-problems
* S4S, *Studio updates with batch fix for CC beds*: https://sims4studio.com/thread/29179/studio-updates-batch-fix-beds;
  *Toddler Preset Batch Fixes*: https://sims4studio.com/thread/35245/toddler-preset-batch-fixes; *Studio updates
  for Enchanted By Nature*: https://sims4studio.com/thread/38713/studio-updates-enchanted-nature (researched, not
  detected)
* S4S, *Post re: patch-related issues that may need a batch fix here*: https://sims4studio.com/thread/17679/post-patch-related-issues-batch
* EA forums, *Broken and Updated Sims 4 Mods and CC: patch 1.121, Feb. 3, 12 & 19, 2026*:
  https://forums.ea.com/discussions/the-sims-4-mods-and-custom-content-en/broken-and-updated-sims-4-mods-and-cc-patch-1-121-feb-3-12--19-2026/13149931;
  *Custom Content fix incoming!* (March 2026 launch crash, fixed by EA, no batch fix):
  https://www.ea.com/games/the-sims/the-sims-4/news/update-3-23-2026
* s4pi `CASPFlags.cs`: https://github.com/s4ptacle/Sims4Tools/blob/master/s4pi%20Wrappers/CASPartResource/CASPFlags.cs
* The game's `OccultType` (decompiled `sims/occult/occult_enums.py`, found in several public repositories, for
  example https://github.com/Coffee-Boyy/Sims4TikTokMod at `EA/simulation/sims/occult/occult_enums.py`)

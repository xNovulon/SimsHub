# Patch day, game errors, save backups and load-time savings

Four features players asked for, built on the Hub's usual rules: nothing is deleted, every change goes
through a journal and can be undone, and nothing changes while the game runs.

| Feature | Where players find it | Engine | API (`speedkit/api.py`) |
|---|---|---|---|
| Patch-day helper | Home (notice after an update), Tools → *After a game update* | `speedkit/patchday.py` | `patch_day`, `patch_seen`, `set_aside`, `put_back` |
| Which mod caused this error? | Home (notice about new errors), Tools → *Which mod caused this error?* | `speedkit/errorlogs.py` | `game_errors`, `errors_seen`, `set_aside` |
| Save backups and save health | Saves → *Save backups*, plus a size line on each save | `speedkit/savebackup.py` | `save_health`, `backup_saves`, `restore_saves` |
| Load-time savings | Home → *Loading times* | `speedkit/loadstats.py` | `load_savings` |
| CC that may need a Sims 4 Studio fix | Tools → *CC that may need a Sims 4 Studio fix*, a line in the patch-day notice | `speedkit/batchfix.py` | `batch_fixes`, `batch_fix_scan`, `batch_fix_open` (docs/batchfix.md) |

The API functions live in `speedkit/api_care.py`. `api.py` imports them at its end, so they sit next to the
other buttons (`api.patch_day()` and so on), use the same configuration (`api.configure(sims=...)`) and
follow the contract in `hub_contract.md`. Server routes are in `speedkit/hub/care_routes.py`. The page
sections are in `speedkit/hub/web/js/care.js` and `css/care.css`. The preview-mode example data is in
`speedkit/hub/stub_care.py`.

## 1. Patch day

### Noticing an update

Only files on this PC are read:

* **`<Game>\Game\Bin\TS4_x64.exe`**: its size and modified time are the build's fingerprint. A patch
  rewrites the exe, so the Hub notices the update before the game has been started again. That is the
  moment a warning helps. The exe's modified time counts as the *update time*.
* **Steam**: `steamapps\appmanifest_1222670.acf` gives `buildid` (added to the fingerprint) and
  `LastUpdated` (the update time).
* **`<Sims 4>\GameVersion.txt`**: the version the game wrote at its last start (`1.119.109.1020`, after
  a few header bytes). It is shown to the player. It changes only at the first start on the new build, so
  it never starts a second notice.

`SpeedKit\game_version.json` remembers the last fingerprint and version. The first look only remembers
them. A later look with a different fingerprint records the change (`previous`, `noticed`, a short
`history`) until the player presses **Dismiss** (`patch_seen`). When the game cannot be found, a change of
the `GameVersion.txt` version is the only clue that is used.

### Which script mods are older

`.ts4script` files that the game loads (the Mods root and one folder down) whose modified time is before
the update time. SpeedKit's own monitor is left out. Each one lists its **companions**, which go with it:

* packages in the same folder (not the Mods root) whose XML tuning names one of the script's Python
  modules (`m="mc_cmd_center.…"`, read with `companions.package_facts`; files over 64 MB are skipped);
* at the Mods root, packages with the same name (`UI_Cheats_Extension.package` next to
  `UI_Cheats_Extension.ts4script`).

The wording stays honest: "An older file does not prove that a mod is broken, and a newer file does not
prove that it is fixed." The list is selected and shown
prominently only while a new update is unacknowledged. Otherwise it is folded away under *Show the N script
mods older than the last update*.

A limitation: a mod file's modified time is usually its maker's build time (zip tools keep it), but a
script downloaded on its own gets the download time. The dates are a hint, not proof.

### Setting mods aside (`set_aside`) and putting them back (`put_back`)

One journal of kind **`aside`** (added to `journal.SCRIPT_KINDS`, because it moves `.ts4script` files).
Each step is checked against a running game:

1. Each file moves from `Mods\<rel>` to `Mods_parked\<rel>`, the same place in the shared parking store.
   A script's companions go with it.
2. `Mods_parked\_manifest.json` is rebuilt with `profiles.rebuild_manifest`, the same rules as a mode
   switch. The other tool's entries and keys are kept, and new file entries are added. It is written
   through the journal: the new copy is staged, the old copy is kept, and the new one is swapped in. So
   mods_switch.py's `full` can still restore everything, and `check_manifest()` stays ok.
3. `SpeedKit\set_aside.json` `{"version": 1, "held": [{"rel", "since", "why": "patch"|"error",
   "game_version", "size", "mtime"}]}` lists the held files. It is also written through the journal.
4. If anything fails half-way (the game starting, a locked file, Ctrl+C), the journal is undone at once
   and the empty folders it left in `Mods_parked` are removed.

It refuses, and changes nothing, when:

* the game runs;
* the parking list is damaged;
* the path is outside Mods (`..`, a drive letter);
* the file is SpeedKit's own (the monitor, the packs);
* the file is no longer there;
* the same path is already parked.

`why='patch'` (the patch-day button) first backs up the saves (`savebackup.backup`, reason *before setting
mods aside*). A backup that fails is reported as a warning step and does not stop the change, because the
change does not touch saves.

`put_back` moves held files back and drops them from the list, in its own `aside` journal. A held file
that has a copy in Mods again (an updated version was installed at the same place) stays parked, and the
page shows it as *Updated*.

**Every mode respects the hold.** `profiles.compute_target(..., held=...)` keeps every held file that is
parked now on the parked side, in `full`, `fast`, `save` and `studio`. So pressing Play never brings a
set-aside mod back. `profiles.current()` leaves held files out when it matches the folders to a mode, so
setting a mod aside does not turn the mode into "custom". Once a held file is back in Mods (put back, or
restored by mods_switch.py's `full`), the hold has no effect.

**Undo.** `undo_last` sends `aside` journals to `patchday.undo`: `journal.undo` puts the files, the held
list and the parking list back exactly, then the folders it had filled that are empty again are removed.
An emptied `Mods_parked\X` would make mods_switch.py's `lean` skip `X`. The Tools page names these changes
*Set mods aside until they're updated* and *Put mods back*.

## 2. Which mod caused this error?

Reports read (read-only; nothing is ever deleted):

| File | Where | Format |
|---|---|---|
| `lastException*.txt` | the Sims 4 folder | the game's XML: `<root><report>` blocks with `<createtime>`, `<categoryid>` (`path\file.py:line`), `<buildsignature>`, and the traceback in `<desyncdata>` (older builds: `<desc>`), with line breaks as `&#13;&#10;` |
| `lastUIException*.txt` | the Sims 4 folder | the same XML; ActionScript menu errors with no Python traceback |
| `mc_lastexception*.html` | the Sims 4 folder or up to 3 folders into Mods | MC Command Center's HTML copy |
| Better Exceptions reports | the Sims 4 folder, a `BetterExceptions` folder there, or up to 3 folders into Mods | any `.html`/`.txt`/`.log` whose name contains "BetterException" (or starts with `BE_` and mentions report/exception); tracebacks are found in the text |

Files over 8 MB are read from their newest end. A file with no known shape is still listed, as kind
`other` with its raw text.

How a mod gets named, strongest first:

1. A traceback path that runs through a `.ts4script` (`…\Mods\Kuttoe\kuttoe_tweaks.ts4script\kuttoe\tweaks.py`):
   that script, matched by file name.
2. A traceback path whose tail is a module a script ships. Scripts are compiled on their maker's PC, so
   paths look like `D:\Deaderpool\mccc\mc_cmd_center\mc_utils\mc_zone.py`. The longest dotted tail
   (`mc_cmd_center.mc_utils.mc_zone`) found in a script's zip wins.
3. With no traceback match, a mod file name (6+ characters, with or without its extension) written in the
   report as a whole word. This is only a *mention*, and the page says "Probably …".

The game's own code is never blamed (`T:\InGame\Gameplay\Scripts\…`, `…\_deploy\…`, the Python library).
The innermost mod line of a traceback names the mod. Other mods on the same traceback are listed under
`also`. When no mod is found, the page says so plainly: "The cause may be the game itself, or a mod
that changes the game's files." For menu errors it says: "Mods that change the menus can cause these."

Repeats are grouped by kind, mod, the error line (numbers and addresses blanked) and the innermost place.
Each group shows how many times it happened and when it happened first and last. The report text is
folded under *Technical details (for the mod's creator)*. **Mark as seen** stores `errors_seen_until` in
`SpeedKit\care.json`. Older groups then move under *Errors marked as seen*. A mod in Mods gets a
**Set … aside** button (`set_aside(rels, why='error')`, the same undoable change as on patch day, without
the save backup). A mod that is already parked is only named.

## 3. Save backups and save health

**Backups.** `SpeedKit\save_backups\<YYYYmmdd-HHMMSS[-n]>\` holds a copy of every `Slot_XXXXXXXX.save`
directly in `saves\`, plus `backup.json` `{id, when, reason, game_version, files: [{name, size, mtime,
save_name}]}`. The game never reads that folder.

* The game's own `.ver` copies and sub-folders such as `saves\FitStudio` are left out.
* A backup is written to `<id>.partial` and renamed only when every copy has the right size.
* A save that has not changed since the newest backup is hard-linked to it where the drive allows, so it
  costs no extra space.
* There must be free space for the copy plus a margin.
* It refuses while the game runs, so a save the game is writing is never copied.
* The newest 5 backups are kept. Older ones are the Hub's own extra copies and are removed, the same way
  the fast pack's old copies are pruned. A backup that an undoable restore still needs is never removed.

**Restore** (`restore_saves(backup)`; the game must be closed):

1. The backup is checked: every file must be there with its size. A backup that fails the check changes
   nothing.
2. The current saves are backed up (reason *before restore*).
3. Each file is copied next to its place as `<name>.hubrestore`, checked, then swapped in with
   `os.replace`.
4. Saves that are not in the backup (newer slots) are left alone.

The contents of a save are never changed. Whole files are copied.

A journal of kind **`saves`** records the restore: `backup`, `before`, and the files written with their
size and time. It has no journal steps, because a journal never touches `saves\`. If the restore stops
half-way, the files already written are put back from the *before* backup and the journal is marked
`rolled_back`.

`undo_last` sends `saves` journals to `savebackup.undo_restore`:

* The saves the restore wrote go back to how they were before, from the *before* backup.
* A save the restore brought back that was not there before is moved into
  `save_backups\<journal>-set-aside\`. It is never deleted.
* It refuses when a restored save has changed since (you played on). The page then points to the *before
  restore* backup.
* `saves` counts as an independent kind: it never touches Mods.

**Health.** Each time the Saves page asks, `save_health()` records each save's size once per day in
`SpeedKit\save_sizes.json` (up to 180 points). It never opens a save for writing. It reports each save's
size, its growth against the oldest point in the last 30 days, and a gentle level:

| Level | When |
|---|---|
| `very_big` | 250 MB or more |
| `big` | 150 MB or more |
| `growing` | grew by at least 15 MB and 25% in up to 30 days |

The notes are calm and factual: "which is common for long-played saves", "Save contents are never changed."
Each save card shows its size and growth. Warnings are repeated above the backup list.

## 4. Load-time savings

`load_savings()` reads SpeedKit Monitor's `SpeedKit\reports\loadtimes.csv` (columns in `ingame.md`).
Rows are grouped into one start per `launch_time`. The monitor writes a `main_menu` row, `lot_loaded`
rows, and another `main_menu` row after going back to the menu, all with the same launch.

* The **load time** of a start is `launch_to_menu_s` plus the `lot_load_s` of its first lot
  (`lot_index` 1). That is the waiting, not the time spent choosing in the menu.
* Per mode (`fast`, `save`, `full`, `studio`; mods_switch.py's `lean` counts as `studio`), the typical
  time is the median, so one very slow start (a patch, a pack update) does not skew it.
* The saving compares Full Start with Quick Start (else One save), per start and summed over the fast starts.
* `confidence` is one of:
  * `none`: no starts yet ("No start times recorded yet");
  * `one_mode`: only one side was measured ("Start once with Full Start to compare" / "Start once with Quick Start to compare");
  * `low`: fewer than 3 starts on a side ("Based on only a few starts so far");
  * `ok`.

  If Quick Start was not quicker, the message says so.

Home shows one bar per mode (for example "Quick Start 2 min · Full Start 8 min"), the time saved per start and
in total, and the honest line whenever the data is thin.

## Server

| Request | What |
|---|---|
| `GET /api/patchday`, `/api/errors`, `/api/save_health`, `/api/load_savings` `[?refresh=1]` | the reads above, cached for 30 s; while a task runs: the last answer or `busy` |
| `POST /api/patchday/seen`, `/api/errors/seen` | the notices were seen |
| `POST /api/task` `set_aside {"rels": [...], "why": "patch"\|"error"}` | one task at a time, like every change |
| `POST /api/task` `put_back {"rels": [...]}` | |
| `POST /api/task` `backup_saves {}` | |
| `POST /api/task` `restore_saves {"backup": "<id>"}` | |

`rels` are paths relative to Mods: 1-500 of them, no `..`, no drive letters. Backup ids must match
`YYYYmmdd-HHMMSS[-n]`. Anything else gets a 400 with a plain message. A finished task drops the cached
answers of these routes.

## Tests (cross-platform, temp folders)

| File | Covers |
|---|---|
| `tests/care_fakes.py` | fake Sims 4 folder: `GameVersion.txt` with header bytes, a fake install, dated `.ts4script` zips, tuning companions and CC packages, realistic `lastException` / `lastUIException` XML, an MCCC HTML copy, a Better Exceptions HTML report, `loadtimes.csv` rows as the monitor writes them |
| `tests/test_care_patchday.py` (13) | version file, first look, noticing an update, acknowledging it, Steam manifest, older scripts and companions, set aside + undo (manifest kept for the other tool, no empty folders), backup before patch-day changes, put back + undo, a newer copy in Mods, every mode keeping held files parked (`compute_target`, `current`, a real `switch('full')`), refusal while the game runs, rollback when the game starts half-way, damaged manifest and bad paths |
| `tests/test_care_errors.py` (6) | finding the report files, parsing the XML, naming mods by script path, by module path and by mention, grouping repeats across files, game-only errors, menu errors, a mod already parked, a garbage file, "seen", no reports |
| `tests/test_care_saves.py` (9) | which files are backed up, hard links, keeping the last N, protected backups, restore + undo, a save that was gone, refusing undo after playing on, refusal while the game runs, broken backups, no saves, health levels and history |
| `tests/test_care_loadtimes.py` (6) | one entry per start, no data, one mode, few starts, medians, total saved, Quick Start not quicker |
| `tests/test_care_server.py` (5) | every route with the stub, argument checks, busy behaviour, end to end with the real engine on a fake folder |
| `tests/test_care_ui.py` (4) | Playwright: starts `python -m speedkit.hub --serve --stub --port <free>`, checks Home, Tools and Saves draw the new sections, presses each button, checks the requests it sends and that there are no console errors |

## Needs a real PC and game to verify

* The exact bytes of `GameVersion.txt`, and that a patch really changes `TS4_x64.exe`'s modified time on
  EA app installs (Steam's `LastUpdated` is documented).
* Real `lastException` / `lastUIException` files from the current build, and a real Better Exceptions
  report. That tool's own file names and layout are assumed from its description. Unknown shapes are still
  listed, raw.
* Setting mods aside and undoing it on the real Mods folder with mods_switch.py in the mix. The logic is
  the same as the tested switch code, but only a fake tree was used here.
* Backup and restore of real multi-hundred-MB saves, and hard links on NTFS and OneDrive-synced
  Documents folders. OneDrive may upload the backups: the folder is inside Documents.

## Wording

All text these features add is neutral and descriptive: no mascot, no first person ("I'll", "Let me"), no
chatty asides. For example "4 script mods are older than the latest game update.", "No error reports
found.", "Saves backed up first (4 saves)."

# CC browser and "CC in this save"

Two features that build on what the engine already knows about the mod library (`library.py`) and about the
saves and the in-game library (`usedpack.py`, `savepacks.py`):

* **Library page - CC browser.** Every CC file with a picture and a category (Hair, Tops, Shoes, Makeup,
  Build/Buy objects ... Script mods), with search, category chips, folder and creator filters, "used in a save"
  / "not used anywhere", duplicates and damaged files, pages of 60. A file opens a details window (where it is,
  which saves use it, what it duplicates) with **Open folder** and **Set aside**. Several files can be picked
  and set aside at once.
* **Saves page - View CC.** For one save (or for the households and lots in the in-game library, the Tray):
  the installed CC files it uses, with pictures; the CC per household and per sim; and the CC it uses that is
  not installed anywhere, listed by its ID, with a name only when a copy is found.

Code: `speedkit/ccbrowser.py` (engine), the "CC browser" section of `speedkit/api.py` (the functions the app
calls), the "CC browser" section of `speedkit/hub/server.py` (routes), and the "CC browser" section of
`speedkit/hub/web/js/hub.js` + `css/hub.css` (UI). Example data: the "CC browser" section of
`speedkit/hub/stub_api.py` (with little generated pictures, so preview mode shows everything).

## Wording

Neutral and descriptive, like the rest of the Hub (`hub_contract.md`): no mascot, no first-person voice.
Files are "CC files"; the quarantine is "the safe copies"; moving a file there is "setting it aside"; Mods_parked
is never named ("put away by Quick Start or one-save mode"). When only an ID is known, the UI says exactly that.

## How files are sorted

`api.cc_scan()` (a task, one at a time like every long job) brings the library index up to date
(`Library.scan()`, incremental), reads which CC the saves and the Tray use (`usedpack.scan_references`, cached),
then `CCIndex.scan()` looks at every **new or changed** file only (same relative path, size and mtime = nothing
to do; a file moved between Mods and Mods_parked keeps its row and its id):

| The file holds                                     | Category                                        |
|----------------------------------------------------|-------------------------------------------------|
| CAS parts (CASP 0x034AEECB)                        | from the parts' **body type**: Hair, Hats, Tops, Bottoms, Full outfits, Shoes, Accessories, Makeup, Eyes & brows, Skin & tattoos, Pets, Other CAS |
| skin tones (TONE)                                  | Skin & tattoos                                  |
| sliders / presets only (SMOD, sculpts, BGEO, DMAP, CAS presets) | Sliders & presets                  |
| objects (OBJD / COBJ)                              | Build/Buy objects                               |
| walls, floors, fences (CWAL / CFLR / CFEN)         | Walls & floors                                  |
| animation clips and nothing above                  | Poses & animations                              |
| tuning / string tables and nothing above           | Gameplay mods                                   |
| `.ts4script`                                       | Script mods                                     |
| only textures / meshes                             | Other                                           |

Up to 12 CAS parts per file are read (spread over the file) and decompressed; the most common category wins and
every category found is kept (a merged file shows under each of its categories). The CAS part header layout is
the one `research/usedcc` verified on 2,000 of 2,025 parts of a real library (versions 0x1B-0x34; version 18
parts do not parse and fall back to "Other CAS"). Body types 1-61 are mapped by name; later ones are "Other CAS".

The same pass marks:

* **Damaged**: the library index could not read the file, or it holds nothing.
* **Duplicate**: every CAS part and object in it is also in another file (from the library index; SpeedKit's
  own packs are ignored). The details window names that other file.
* **Used / not used** (CAS, Build/Buy, walls and sliders only): whether a current save or the Tray references
  one of its CAS parts, looks or objects, and which saves do. Script and gameplay mods are never called unused.
  Lot walls/floors are not decoded (`usedpack.py`), and CC that only a script needs cannot be seen, so the
  details window says "not always detected".
* **Creator**: a guess from the file name (`[Creator] x`, `Creator_x`, `Creator - x`, CamelCase prefix), shown
  as a guess. **Folder**: the top folder in Mods.

The index lives in `data/ccbrowser.sqlite` beside `data/library.sqlite` (WAL mode: the page can read while a
scan writes, and shows what is sorted so far). The scan also adds two small partial indexes to the library index
(`cc_pic_<type>` on `res(i)` for CAS and Build/Buy thumbnails) so a picture is found by part id at once.

## Pictures

Candidates, in order: a thumbnail in the file with the representative part's instance (THUM 0x3C1AF1F2 for CAS;
0x3C2A8647 / 0x5B282D45 / 0x9C925813 / 0xCD9DE247 for objects), else the biggest thumbnail in the file; for
gameplay mods a plain PNG (0x2F7D0004) icon. A file with CAS parts or objects but no thumbnail borrows the same
part's thumbnail from another library file, else the game's own thumbnail cache
(`<Sims 4>\localthumbcache.package`, read-only; the newest few copies of it in the safe copies are tried too).

Decoding (`ccbrowser.decode_image`, Pillow): PNG, plain JPEG/JFIF, DDS, and EA's alpha-in-JPEG thumbnails - a JFIF
image with an APP0 segment `ALFA` + big-endian length + a grayscale PNG mask (at byte 0x18 right after the JFIF
segment); the mask becomes the alpha channel. A JPEG decoder that trips over the mask segment gets the image
without it.

Pictures are made **lazily**, when the page shows a card, scaled to 256 px and stored as WebP (PNG when Pillow has
no WebP) in `data/ccthumbs/` - never inside the game's folders. The file name is a hash of the source file's
relative path, size and mtime plus the resource key, so a changed file gets a new picture and an unchanged one is
never read again; a file with no usable picture gets an empty `.none` marker (same key). The browser caches each
picture for a week under a URL whose `?v=` token changes with the file.

## Setting files aside

`api.cc_set_aside(ids)` (task `cc_set_aside`) moves CC files out of Mods into the safe copies through one
`Journal('setaside', ...)` - `journal.quarantine()` for each file. Nothing is deleted; **Undo last change** on the
Tools page puts them back (plain `journal.undo`, with the usual "moved by a mode switch since" check). It refuses
while the game runs, never touches script mods (the journal refuses them too), refuses files that are not in Mods
right now (a mode switch put them in Mods_parked: switch to Full Start first) and files that changed since the last
look. The CC index forgets the files; after an undo, **Look again** brings them back.

## A save's CC

`api.save_cc(slot)` (`'tray'` = the in-game library) reads the save's references (`savepacks.scan_one`, which
parses the save only if it changed since the Saves page last read it) and matches them with the library index:

* **files**: installed CC files it uses, most used first, with how many CAS parts / objects / looks each gives,
  and which sims wear them. A part in several files is credited to the copy the game loads first (load order).
  The card picture is the thumbnail of one used part (`/api/cc/pic/cas/<id>`), else the file's own picture.
* **households**: per household (the played one first) and sim: the CC files they wear and how many of their
  items are missing.
* **missing**: CAS parts, objects and looks (skin tones, sliders) the save uses whose ID is 2^32 or more and that
  are neither in the library nor in the game (the research found EA's IDs all below 2^32; without the game folder
  that rule alone decides). Each shows its ID (and full type:group:instance key to copy), who wears it, and -
  only when a copy is found - its file name and a guessed creator: in the safe copies (every journal home's
  quarantine), the Inbox, Downloads or the Desktop, including `.package` files inside a `.zip` there. Those
  folders are indexed only when a save really misses CC (`CCIndex.side_update`, cached by file size/mtime for a
  plain file, by size+mtime of the whole `.zip` for what is inside one). A picture shows when the game's
  thumbnail cache still has one.

`api.cc_install_found(slot)` (task `cc_install_found`) installs one copy of each file `save_cc`'s 'missing' found
on this PC into `Mods\Found by Sims Hub` through one `Journal('restore', ...)` - `journal.put_new()` for each
file, always as a `.package` (never a script mod) and never overwriting a name already there. Copies, never
moves, the source; refuses while the game runs; a later run installs nothing more for CC this already resolved.
**Undo last change** removes the installed files again. Nothing here ever downloads anything - only files
already on the PC are looked at.

Objects are listed for the whole save (object IDs are not stored per lot), and lot walls/floors are not decoded.

## Performance

Measured with a synthetic library index the size of a 41,000-file / 259 GB library (755k CAS parts, 4.8M
resources): duplicates 3.8 s, "used by saves" 1.1 s, picture indexes 0.5 s (once), one filtered page of 60 in
60-115 ms, a picture lookup by part id under 1 ms. The per-file work of the first sort is a few small reads per
file (roughly 1-3 minutes on an SSD for 41k files, longer on a hard disk); later sorts only read what changed.
The page never holds more than 60 cards; pictures load lazily; the search box waits 260 ms after typing.
`data/ccthumbs/` grows by roughly 5-15 KB per picture actually viewed and is not pruned.

## Needs checking on a real PC with real CC

* Categories and body types on a real library (spot-check hair / tops / makeup / Build/Buy chips).
* Which thumbnail types real Build/Buy CC ships, and whether `localthumbcache.package` keys CAS pictures by the
  part's instance (assumed; objects likewise by the object's instance).
* EA's alpha-in-JPEG thumbnails from real packages (the tests build them from the documented layout).
* The time of the first sort on the 41k-file library, and Explorer opening with the file selected.

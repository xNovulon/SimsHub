# savepacks - "Play this save"

`speedkit/savepacks.py`. The user picks one save; the game then loads only the custom content that save
uses - every sim and every lot in every world of that save - while script mods, their tuning, animations
and default replacements stay loaded exactly as in Fast mode.

```python
from speedkit import savepacks as S, fastmode as F
S.list_saves()                              # current slots: name, household, world, sims, lots, slot id, guid
refs1 = S.scan_one(saves_dir, 'Slot_00000014')          # usedpack refs of that one save (cached)
plan = S.plan_save_pack(lib, refs1, 'Slot_00000014', parked, bc_cache=...)  # read-only
S.update_save_pack(lib, refs1, 'Slot_00000014', home, dry_run=False)        # none / refresh / delta / rebuild
S.status('Slot_00000014', home)             # fresh / stale / missing + why + gb
PR.switch('save', save_slot='Slot_00000014', fastmode=S.PackProvider('Slot_00000014', refs=...), ...)
```

The Hub uses it through `speedkit.api` (`list_saves()`, `play('save:<slot>')`).

## What a save pack is

A fast pack (speedkit.fastmode) planned from **one** save file:

* part (a) - the CC that save's sims wear and its lots use (usedpack's plan: CAS parts with their meshes,
  textures and thumbnails, skin tones, sculpts, sliders, pet coats, lot objects, walls/floors, and the
  library's default replacements of the EA items those sims wear) - from that save only (not the other
  saves, not the Tray);
* parts (b) and (c) - every non-asset resource of the parked packages (tuning, SimData, strings,
  animations), EA overrides, shadowed keys, and what kept CC, loaded tuning and scripts need - the same
  as the fast pack's, because they do not depend on saves. They come from fastmode's **b/c cache**.

The same packages are parked as in Fast mode (`fastmode.park_set`); FitStudio\ and animation\ are never
parked, scripts never.

## Names and places

* Files: `!!!!!SpeedKit_Save_<the slot's 8 hex digits>_###.package` (`fastmode.save_kind(slot)`), e.g.
  `!!!!!SpeedKit_Save_00000014_001.package`; deltas are `_900` and up, as for the fast pack. The name sorts
  right after the fast pack's and before every mod name, so the pack loads first and its copies win,
  and the slot in the name tells the profile switcher which folder a file belongs to. Only this exact
  pattern is SpeedKit's (fastmode `_PACK_RX` / `is_speedkit_pack`, profiles `SAVE_PACK_RX`): `... - Copy`
  is ordinary CC.
* Folder: `<Sims 4>\SpeedKit\savepacks\<slot>\` holds `savepack.json`, `savepack_keys.tsv` and, while
  another mode is active, the .package files. While the save is played they sit at the Mods root.
* Journal kind `savepack` (fastmode's `_run_journal`); undo with `journal.undo` (api.undo_last does it).

## Saves: what is read

Only `Slot_XXXXXXXX.save` files directly in `saves\` (never `.ver` backups, other files or sub-folders such
as the Wicked Animator's `saves\FitStudio\`; they are not opened, let alone changed). A save is read into
memory with usedpack's share-delete opener (the game can rotate it meanwhile) and its SaveGameData
(resource 0x0D) decoded with the game's own field numbers (`Game\Bin\Python\generated.zip`,
FileSerialization.proto):

| message | fields used |
|---|---|
| SaveGameData | guid 1, save_slot 2, neighborhoods 4, households 5, sims 6, zones 7 |
| SaveSlotData | slot_id 1, last_neighborhood 3, last_zone 5, slot_name 9, active_household_id 11 |
| HouseholdData | household_id 2, name 3, home_zone 4 |
| ZoneData | zone_id 1, name 2, neighborhood_id 10 |
| NeighborhoodData | neighborhood_id 1, name 3 (the world, e.g. 'Willow Creek') |

`household` is the active household, `world` the neighbourhood of its home lot (else of the last zone),
`sims` the SimData count, `lots` the zones of every world. `slot_id` is what the game wrote into the file:
normally the slot number, but a save the game recovered keeps its original's (Slot_00000018 holds 23 =
0x17), and copies share the guid - so the in-game check compares name + slot id + guid.

## The profile switch

`profiles.switch('save', save_slot=..., fastmode=PackProvider(slot, ...))` parks what 'fast' parks, brings
every other pack home (the fast pack to `SpeedKit\fastpack`, other saves' packs to their folders), deploys
this save's pack (building or updating it first; a changed save costs a refresh or a delta), and writes
`profile_state.json` = `{"profile": "save", "save_slot", "pack_dir", "save_name", "save_slot_id",
"save_guid", "save_pack", "switched"}`. `current()` reports `'save'` with `save_slot` when exactly one save
pack is at the Mods root. Undoing the switch also puts back the packs the update had brought home.

## Measured on the real library (2026-09-24, read-only, private copies of every cache)

627 loaded packages (259 GB, 755,662 CAS parts); 187 parked in Fast mode (250.4 GB), 440 kept (366 CAS parts).
10 current save slots, 374 save/Tray sources (53 s to parse them all again with 3 workers).

| slot | save | household | world | sims | lots | CC parts used | CC installed nowhere | save pack | CAS parts loaded |
|---|---|---|---|---|---|---|---|---|---|
| Slot_ffffffff | Autosave | - | - | 365 | 414 | 33 | 98 | 1.06 GB | 8,876 |
| Slot_00000019 | My Saved Game 24 | - | - | 365 | 414 | 33 | 98 | 1.06 GB | 8,876 |
| Slot_00000018 | My Saved Game 21 [Re [Recovered] | Lara | Willow Creek | 235 | 414 | 781 | 129 | 1.61 GB | 9,615 |
| Slot_00000017 | My Saved Game 21 [Recovered] | Lara | Willow Creek | 235 | 414 | 804 | 129 | 1.62 GB | 9,638 |
| Slot_00000016 | My Saved Game 21 | Lara | Willow Creek | 228 | 414 | 742 | 126 | 1.62 GB | 9,576 |
| Slot_00000015 | Neuworld Save File [Recovered] | Lara | Willow Creek | 443 | 425 | 4,346 | 3,845 | 5.73 GB | 13,166 |
| Slot_00000014 | Neuworld Save File | Lara | Windenburg | 442 | 425 | 4,282 | 3,752 | 5.61 GB | 13,101 |
| Slot_00000003 | NextGen v2 [Recovered] | Campos | Willow Creek | 39 | 416 | 536 | 559 | 1.63 GB | 9,369 |
| Slot_00000005 | NextGen v2 [Recovere [Recovered] | Campos | Willow Creek | 19 | 416 | 219 | 273 | 1.27 GB | 9,056 |
| Slot_00000002 | NextGen v2 | Campos | Ciudad Enamorada | 257 | 416 | 784 | 749 | 1.67 GB | 9,621 |

(Autosave and 'My Saved Game 24' have no played household yet; their pack is the b/c part plus 33 CC parts.)
For comparison: the full library loads 755,662 CAS parts, Fast mode 15,923 (7.82 GB pack). A save pack is
1.1-5.7 GB, of which about 1.0 GB is the save-independent b/c part (b 0.47-0.50 GB, c 0.52 GB).

Planning times (warm disk cache): the fast pack without the b/c cache 60.7 s (tuning scan 18.6 s, part a 17.1 s,
closures 13 s), with the cache written 51.7 s, with a cache hit **18.0 s** (part a 10.1 s) - and the hit gives
exactly the same 85,257 keys; one save's pack with a cache hit 11.2-15.2 s. `api.list_saves()` took 3.5 s with
the saves already parsed, `api.status()` 5.0 s. A dry-run 'save' switch from today's studio set would bring back
483 files (7.7 GB) in 312 moves, exactly as 'fast' (the parked set is the same), and cut the parking list from
311 to 187 entries.

# SpeedKit Monitor (in-game script mod)

A small script mod for The Sims 4 (game Python 3.7.0, build 1.126.73.1030). It has three parts:

| Part | What it does | Output |
|---|---|---|
| Load timer | Records when the game was launched, when script mods load, when the main menu appears and when a lot becomes playable | One row per event in `SpeedKit\reports\loadtimes.csv`, plus `monitor.log` |
| Lag meter | Cheat `speedkit.lag [seconds]` measures which script mods use the simulation thread, and times every simulation tick exactly | `SpeedKit\reports\lag_<time>.txt`, a notification listing the top 5 mods, and output in the cheat console |
| CC guard | After a lot loads, checks whether the active household wears CAS parts this mod profile does not load. If so, it warns you not to save | An urgent notification, with the sims and part ids in `monitor.log` |

All paths are relative to the Sims 4 user folder (`Documents\Electronic Arts\The Sims 4`). The mod writes only to `SpeedKit\reports`, never to `Mods`.

## Files

| Path | Role |
|---|---|
| `ingame/speedkit_monitor/__init__.py` | Start-up: reads two small files, wraps three game functions, registers the cheats. It does nothing when it is not loaded from a Mods folder. |
| `ingame/speedkit_monitor/common.py` | Finds the Sims folder from the module's own `__file__`; logging, guarded calls, notification and cheat-console helpers |
| `ingame/speedkit_monitor/hooks.py` | Installs each wrapper once. A wrapper never changes arguments, results or exceptions, and our own errors are logged, never raised. |
| `ingame/speedkit_monitor/loadtimer.py` | Load milestones and CSV rows |
| `ingame/speedkit_monitor/sampling.py` | Pure logic, testable under 3.12: parses faulthandler dumps, maps `co_filename` to archive, attributes samples, tick statistics, report text |
| `ingame/speedkit_monitor/lagmeter.py` | Measurement session: arms faulthandler once, wraps `Zone.update` and `Zone.on_teardown` (at the first `speedkit.lag`), then finishes, writes the report and notifies |
| `ingame/speedkit_monitor/ccguard.py` | CC guard: pure check plus game glue |
| `ingame/speedkit_monitor/commands.py` | The cheats `speedkit.lag`, `speedkit.cc` and `speedkit.status` (CommandType.Live, so no testingcheats needed) |
| `tools/game_python.py` | Runs a 3.7 script inside the game's own `python37_x64.dll` in a child process. The DLL is only read. |
| `tools/build_ingame.py` | Compiles with the game's DLL (`py_compile`), checks magic 3394 and zips to `dist/SpeedKit_Monitor.ts4script` |
| `speedkit/ingame_install.py` | Installs and uninstalls through a Journal of kind `install`. Dry run by default. |
| `tests/test_ingame.py`, `tests/test_ingame_install.py` | Tests. Scratch data goes in `E:\speedkit_test\ingame`. |
| `tests/test_ingame_review.py`, `tests/test_ingame_review2.py` | Adversarial review tests (fake Sims folders under `E:\speedkit_test\ingame_review`, plus one more scenario inside the game's DLL) |

## Build, test, install

```
python tools/build_ingame.py                     # dist/SpeedKit_Monitor.ts4script (8 modules, ~35 KB, ~1 s)
python tests/test_ingame.py                      # 22 tests: 3.12 logic + build + the mod inside the game's DLL
python tests/test_ingame_install.py              # 4 tests on a fake Sims folder
python tests/test_ingame_review.py               # review tests (3.12, fake Sims folders)
python tests/test_ingame_review2.py              # review tests (3.12 + one more scenario in the game's DLL)
python -m speedkit.ingame_install install        # dry run: shows the plan
python -m speedkit.ingame_install install --apply
python -m speedkit.ingame_install uninstall [--apply]
```

`install(dry_run=True)` returns a plan. The action is one of:
- `put_new`: no copy is installed yet.
- `replace`: the installed copy differs; it is quarantined first.
- `up_to_date`: the installed copy is identical, so nothing happens.

The plan also lists any other `SpeedKit_Monitor*.ts4script` files in the Mods root or a first-level folder, because two copies of the `speedkit_monitor` package would clash. Those copies are quarantined.

A real run refuses to start while `TS4_x64.exe` is running. `speedkit.journal.undo(<journal id>)` reverses it.

## In the game

- **`speedkit.lag`** measures for 60 s at 25 samples/s.
  - `speedkit.lag 120` measures for 120 s.
  - `speedkit.lag 30 50` measures for 30 s at 50 Hz.
  - `speedkit.lag stop` ends early. `speedkit.lag status` reports progress.
  - A run also ends when its lot is unloaded (travel, quit to the menu or the desktop all call `Zone.on_teardown`). The report is written then, and its notification appears after the next lot has loaded, titled "(previous lot)". Without this, faulthandler kept dumping through a travel loading screen, where no tick can end the run, and through the game's shutdown.
  - Limits: 5-1800 s and 5-100 Hz. The rate is lowered so a run never exceeds 12,000 samples.
- **`speedkit.cc`** runs the CC guard now.
- **`speedkit.status`** shows the launch time and source, the load events so far and the lag meter state.

### Reading a lag report

The report measures only the simulation thread, the one that runs Python.

**How each sample is charged.** A sample goes to the innermost stack frame that belongs to a script mod.
- That includes game code the mod called. A mod that wraps a busy game function is charged for that function.
- The **self%** column counts only samples where the mod's own code was the innermost frame. It separates "the mod is slow" from "the mod wraps something slow".
- A sample with no mod frame on the stack is charged to `game`.
- **`<outside Python>`** means the thread was in C++ (rendering, routing, animation, loading).
- SpeedKit's own wrapper frames are not counted.
- Decorated code is traced to the real function. A decorator made with `functools.wraps` returns a wrapper whose code lives where the decorator is defined, so the owner map follows `__wrapped__` and never uses the wrapper's own file. EA's files (`T:\InGame\Gameplay\Scripts\...`, `D:\dev\TS4\_deploy\...`) are never charged to a mod.
  - Why it matters: WickedWhims (in Mods now) has ten test classes with `@turbo_cached_test def __call__`, which is EA's `caches.cached_test`. Before this rule EA's `caches.py` was mapped to WickedWhims, so every EA cached test on the stack was charged to it. A mod with a module-level `@exception_protected` would have owned `sims4/utils.py`, which also wraps `areaserver.c_api_server_tick`, and so every Python sample.
  - Measured in the game's DLL (`tests/test_ingame_review2.py`, true split: WickedWhims-like mod 3.6%, game 25%, a Kuttoe-like mod 0%): the old map gave 19.5% / 0.8% / 11.1%, the fixed one gives 4.5% / 23.9% / 0%.

**Tick timing.** The `Zone.update` figures time every simulation tick exactly: min, avg, p95, max, and the number of ticks over 50 ms.

**Simulator debt.** This is how many sim minutes the simulation has fallen behind, read at the start and the end of the run.

## CSV columns (`loadtimes.csv`)

| Column | Meaning |
|---|---|
| `time` | Local time of the event |
| `event` | `main_menu` or `lot_loaded` |
| `since_launch_s` | Seconds from launch to this event |
| `launch_to_scripts_s` | Seconds from launch until script mods were imported (our import) |
| `launch_to_menu_s` | Seconds from launch to the first main menu. Also filled on `lot_loaded` rows. |
| `lot_load_s` | Seconds from `Zone.start_services` (zone init) to the end of the loading screen |
| `game_zone_load_s` | The game's own `areaserver.server_init_load_time`: zone init to zone loaded |
| `lot_index` | 1 for the first lot after a main menu, then 2, 3 and so on |
| `zone_id` | The zone id in hex |
| `profile` | From `SpeedKit\profile_state.json` |
| `script_mods` | Number of `.ts4script` archives with loaded modules, excluding ours |
| `script_modules` | Number of modules loaded from those archives |
| `launch_source` | `speedkit`, `config.log` or `unknown` |
| `launch_time` | The launch time that was used |
| `free_ram_mb_at_start` | The "Free memory" line from `Config.log` |
| `monitor_version` | Version of this mod |

## Contracts with the desktop tools

**`SpeedKit\launch_time.json`** is written by whatever launches the game:
- Format: `{"launch_time": <unix seconds or ISO-8601>}`. The keys `time`, `launched_at` and `epoch` are also accepted.
- It is used only when it is at most 1 hour before the mod's import, and when it belongs to the same launch as `Config.log` (written before `Config.log` and within 10 minutes of it). Otherwise the `Config.log` mtime is used.

**`SpeedKit\profile_state.json`**: the profile name is read from the first of these keys that is present: `profile`, `active_profile`, `active`, `current`, `name`. A string value or a nested `{"name": ...}` both work.

## Facts it relies on (and how they were checked)

**Hooks.** All of these were read in the game's bytecode with `tools/pyc37.py` and `tools/xref.py`.

| Hook | Call site |
|---|---|
| Main menu | `areaserver.c_api_notify_client_in_main_menu` calls `services.on_enter_main_menu()`, which does nothing. The name `c_api_notify_client_in_main_menu` is in `Simulation_x64.dll`'s string table. |
| Lot start | `areaserver.c_api_zone_init` calls `zone.start_services(gameplay_zone_data, save_slot_data)` |
| Lot loaded | The Live command `zone.loading_screen_animation_finished` (sent by the client) calls `services.current_zone().on_loading_screen_animation_finished()` (`zone.pyc` line 1085) |
| Ticks | `areaserver.c_api_server_tick` calls `zone.update(absolute_ticks)` |

- Every call site looks the function up by attribute at call time (`LOAD_GLOBAL` + `LOAD_METHOD`), so wrapping it on the module or class works even if C++ caches the `areaserver` functions.
- The game's importer (`sims4.importer.utils`) imports every `.pyc` in the archive. It maps `speedkit_monitor/__init__.pyc` to the package itself, so `__init__` runs only once.

**Launch time from `Config.log`.** The game rewrites `Config.log` once per start: `NumBoots` went from 43 to 44 between two launches. It is the first file the game writes.
- Measured live: the process started at 01:39:47.8, `Config.log` was written at 01:40:06.8, and it was not touched again during that session.
- So a `Config.log`-based launch time is **about 19 s late**, and every "since launch" figure based on it is about 19 s short. `launch_source` in the CSV says which launch time was used.

**CAS parts.**
- `cas.cas.get_caspart_bodytype` is the native `_cas` function from `Simulation_x64.dll`.
- WickedWhims (installed now) uses `get_caspart_bodytype(id) > 0` as its "CAS part loaded" test. Its log from the 00:31 session loaded 3,527 handlers. It skipped exactly the 24 `Hiroki:Body_CAS_Parts` handlers "caused by missing CAS part", and those 24 ids are in neither Mods nor Mods_parked.
- So in the running game the call returns a value <= 0 for a missing part and does not raise.
- Outfits are read with `SimInfo.get_outfits().get_all_outfits()` and each outfit's `part_ids`. `SimInfo` derives from `SimInfoWithOccultTracker`, then `SimInfoBaseWrapper`, then `OutfitTrackerMixin`. The guard never calls `get_outfit()`, which can generate a missing outfit.

**Sampler.** This comes from the profiler research.
- `faulthandler.dump_traceback_later(repeat=True)` is armed once per measurement. It samples without the GIL, and was measured unbiased under the game's DLL.
- A Python sampler thread is off by 5-16 points, and re-arming the sampler on every tick costs 4 ms at p90.
- The dump format is CPython 3.7's `traceback.c`:
  - Non-ASCII characters are escaped (`\xNN`, `\uNNNN`) and strings are cut at 500 characters.
  - Stacks are cut at 100 frames.
  - In 3.7 a thread with no Python frame prints only its header line.

## Measured (read-only, on this machine)

**Build.** 8 modules, about 35 KB. Compiled by game Python 3.7.0, magic `420d0d0a` (3394).

**Inside the game's DLL (tests/test_ingame.py).** The game's own `import_modules_by_path` imported all 8 modules with 0 errors in 27-58 ms.

The synthetic load per tick was: heavy mod 4 ms, light mod 1 ms, game 3 ms, then 20 ms of C++ outside Python. A 5 s run at 100 Hz produced about 260-315 samples at 52-62 samples/s:

| Owner | Share |
|---|---|
| Heavy mod | 14-17% |
| Light mod | 3-5% |
| Game | 9-14% |
| Outside Python | 65-74% |

For comparison, the fixed per-tick timings give 14.3 / 3.6 / 10.7 / 71.4%. The average tick was 8.7-11 ms, against 8 ms of work.

**Research dump.** The research recorded a real dump under the game's DLL. Re-parsed, it gives exactly the research's numbers: 1,411 dumps, 497 Python samples, heavy 245, light 67.

**Cost of stopping.** At the default rate, a 60 s run at 25 Hz with 100-frame stacks gives a 7.2 MB dump. The game's Python parses it in 0.36-0.97 s, once, when the measurement ends. With no measurement running, the per-tick cost is a single global check.

**Real Sims folder, dry run.**
- `install()` plans `put_new -> Mods\SpeedKit_Monitor.ts4script`, and there are no other copies.
- The game was running at the time, so an `--apply` would have been refused.
- Nothing was written.

## Limitations and open points

**Not yet run in the real game.** All of this was checked statically and inside the game's DLL with stubs. The first in-game session should confirm that `speedkit.status` shows `main menu events 1` after the menu appears and `lots loaded 1` after a lot.
- If the main-menu event is missing, the game may call `c_api_notify_client_in_main_menu` before script mods are imported. The `lot_loaded` rows still carry the full timings.

**faulthandler risks.**
- It reads stacks while the game runs. A very rare crash is possible if a frame is freed mid-read (an open question from the research), which is why it runs only on request.
- Only one `dump_traceback_later` can be armed per process. A mod that uses it at the same time loses its own.

**CC guard coverage.**
- If the game strips unknown part ids from outfits while loading, the guard finds nothing. This is not proven either way.
- It checks only the active household's outfits in their current occult form.

**Attribution limits.**
- A mod that wraps a busy game function is charged for it. Use the self% column to tell the cases apart.
- Mods that run code without a `__file__` in its globals, or that were never imported as modules, fall back to `game`, unless their `co_filename` contains `.ts4script`.

**Launch time.** Without `launch_time.json`, "since launch" figures are about 19 s short (see above).

**Start-up.** Reading the launch data, installing the hooks and registering the cheats are three separately guarded steps. A bad `launch_time.json` (for example a date before 1970, which makes `datetime.timestamp()` raise `OSError` in the game's Python) is ignored and costs nothing else.

**Import time.** `launch_to_scripts_s` is the moment the game imported this archive, not the first script mod. The game imports archives one after another, so mods imported before this one are included in the figure.

## The prepared save (engine wave, 2026-09-24)

In the modes Novulon's Sims Hub prepares - `fast` and `save` in `SpeedKit\profile_state.json` - the CC guard
also checks the save: at the first lot load after the main menu it reads which save is loaded
(`services.get_persistence_service().get_save_slot_proto_buff()` -> SaveSlotData `slot_id` / `slot_name`,
and `get_save_slot_proto_guid()` -> SaveGameData `guid`; services/persistence_service.pyc lines 853/862,
the same SaveSlotData areaserver.c_api_zone_init hands to Zone.start_services) and compares it with
`save_slot` / `save_slot_id` / `save_name` / `save_guid` in profile_state.json. The save counts as the
prepared one when every fact both sides know agrees (the slot id may be the recorded one or the file's
number; a recovered copy keeps its original's id and guid but not its name). When a different save is
loaded in the 'save' mode, or the household wears CC the fast/save mode does not load, one urgent
notification says: "This save was not prepared for this mode - do not save. Restart the game from
Novulon's Sims Hub." (in those modes it replaces the older "missing CC" notification; other profiles keep
that one). Later lots of the same session keep the first lot's verdict (a "Save As" mid-session does not
trigger it). Tests: `tests/test_ingame_saveguard.py` (pure logic, and the built mod in the game's DLL).

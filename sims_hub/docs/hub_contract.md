# Novulon's Sims Hub - contract between the engine (speedkit/api.py) and the app (speedkit/hub/)

The user is non-technical and must never be asked technical questions. Every user-facing string is plain,
short English - no "package", "quarantine", "journal", "profile" or "CASP" (the engine passes every message
it shows through a word filter; file names such as `x.package` stay as they are). Every function below is
safe to call from a background thread, never raises for expected failures (it returns
`{'ok': False, 'message': '<plain explanation>'}` instead), and reports progress through an optional
callback `progress(step: str, fraction: float | None, message: str)`. The functions keep their own
signatures (functools.wraps), so `inspect.signature(api.graphics_tune)` shows its `progress` parameter.

Keys marked *(added)* were added on 2026-09-24; every change is backwards compatible.

## speedkit/api.py (owned by the ENGINE agent)

```python
status() -> {
  'ok': True,
  'game_running': bool,
  'profile': {'name': 'full'|'fast'|'studio'|'save'|'custom', 'save_slot': str|None, 'label': str},
  'graphics': {'state': 'tuned'|'sgr_full'|'stock'|'other', 'label': str, 'can_tune': bool, 'details': [str]},
  'memory': {'free_gb': float, 'total_gb': float, 'warnings': [str], 'top': [{'name': str, 'gb': float}]},
  'library': {'packages': int, 'gb': float, 'cas_full': int, 'cas_fast': int|None,
              'cas_now': int|None},                    # (added) CAS parts loaded in the mode the Mods folder is in
                                                       #   now - any mode (full, fast, save, studio, custom)
  'fastpack': {'state': 'fresh'|'stale'|'missing', 'why': str, 'gb': float|None},   # why: a plain sentence
  'monitor': {'installed': bool, 'where': str|None},
  'load_times': [{'time': iso, 'profile': str, 'launch_to_menu_s': float|None, 'lot_load_s': float|None,
                  'event': 'main_menu'|'lot_loaded'}],                               # newest first, <= 20
  'journals': [{'id': str, 'kind': str, 'state': str, 'when': iso, 'note': str,
                'title': str,          # (added) a plain sentence: "Switched to Fast mode", "Graphics set to Max Quality"
                'undoable': bool,      # (added) undo_last may undo it (same rule undo_last uses)
                'next_undo': bool,     # (added) exactly the one undo_last would undo now (at most one True)
                'cannot_undo': bool}], # (added, e2e audit) it would be next, but its files were changed since
                                       #   (e.g. by the other chat's mods_switch.py): undo_last skips it
                                                                                     # newest first, <= 15
  'animator': {'installed': bool, 'path': str|None},   # path: Wicked Animator.exe, or the .bat fallback
  'disk': {'c_free_gb': float, 'sims_drive_free_gb': float},
  'game': {'found': bool, 'exe': str|None, 'source': str, 'saved': bool, 'message': str,       # (added)
           'store': 'steam'|'ea'|'unknown'|None, 'game_dir': str|None,
           'lost_path': str|None},   # a game folder the user chose that is gone (then found False)
      # found False -> show "Find my game" (browse / set_game_path). saved: the path is the user's own choice.
      # A chosen path that has gone (drive letter changed...) gives found False, lost_path, and the message
      # "The game is no longer at <path>. ..." so the app asks again.
  'inbox': {'path': str, 'waiting': int},              # (added) downloads waiting (a cheap count; nothing is read)
  'report': {'path': str|None, 'when': iso|None},      # (added) the last library_report.html, if any
  # 'problems': [str]  - only present when a part of the status could not be worked out (that part is then empty)
}

list_saves(progress=None) -> {'ok': True, 'saves': [{
  'slot': 'Slot_00000014',            # file stem, the id used by play('save:<slot>')
  'name': str,                         # the save's own name as shown in the game (the slot when unreadable)
  'household': str|None,               # active/played household name
  'world': str|None,
  'last_played': iso,                  # file mtime
  'size_mb': float,
  'sims': int, 'lots': int,            # sims in the save / lots (zones) in all its worlds
  'cc_parts': int|None,                # CC CAS parts this save uses (excl. EA); None when it could not be read
  'cc_missing': int|None,              # (added) CC CAS parts it uses that are installed nowhere
  'cas_loaded': int|None,              # CAS parts the game would load when playing this save only
                                       #   (None until a fast or save pack has been planned once)
  'pack': {'state': 'fresh'|'stale'|'missing', 'gb': float|None},
  # 'problem': str                     (added) only when the save could not be read
}]}
    # The first call reads every save once (a few minutes for big saves); later calls use the cache. While a
    # play/prepare runs it parses nothing (what is known is returned).
    # Only Slot_XXXXXXXX.save files directly in saves\ are read (.ver backups, other files and sub-folders
    # such as saves\FitStudio of the Wicked Animator are ignored and never touched).

play(target, progress=None) -> {'ok': bool, 'message': str, 'launched': bool,
                                'steps': [{'step': str, 'ok': bool, 'message': str,
                                           'warn': bool}]}   # (added) warn: fine, but needs attention
                                                             #   (memory warnings, a graphics file left alone...)
    # target: 'fast' | 'full' | 'studio' | 'save:<slot>'
    # One-click: refuse if the game runs; tidy SpeedKit's own old pack copies; scan the mods; install/refresh
    # SpeedKit Monitor; make graphics 'SpeedKit Max Quality' when SGR Full is active; build/update the needed
    # pack; switch the Mods folder; memory check (warnings go into steps); launch the game (writes
    # launch_time.json). Step names: housekeeping, library, monitor, graphics, pack, mods, memory, launch
    # (and game / error when refused).
    # (e2e audit) A monitor the other chat's mods_switch.py parked is brought back by the switch and checked
    # after it (no second copy is installed beside it). After graphics_restore(apply=True) - or undoing Max
    # Quality - Play leaves the graphics file alone ("as you chose") until graphics_tune(apply=True); the
    # choice is kept in SpeedKit\settings.json {"graphics": "keep_previous"}, as are the other-drive homes of
    # duplicate clean-ups {"cleanup_homes": [...]} (so they stay undoable after the Hub restarts).
prepare(target, progress=None) -> same shape, everything except launching.
undo_last(progress=None) -> {'ok': bool, 'message': str, 'journal': str|None}
    # undoes the journal status() marks next_undo; undoing a mode switch also puts back the packs its update
    # had moved. next_undo is the newest change whose undo would go through NOW (a dry run against the disk):
    # a change whose files were changed since (mods_switch.py rewrote the parking list, a file moved between
    # Mods and Mods_parked...) is skipped and marked cannot_undo; behind it only graphics/cache changes can
    # still be undone (they never touch Mods). When nothing is left the message says why, in plain words.
inbox(apply=False, progress=None) -> {'ok': bool, 'message': str, 'items': [{'name','status','where','reason',
                                      'files'}], 'inbox_path': str, 'journal': str|None, 'warnings': [str]}
    # reason: one plain sentence per download ("A script mod (3 files): it goes into its own folder in Mods,
    # untouched.", "1 new CC file, 1 already in your game."), or why it cannot be added.
cleanup_plan(progress=None) -> {'ok': bool, 'message': str, 'copies': int, 'gb': float, 'rewritten': int, 'removed': int,
                                'mb': float}    # (added, e2e audit) the same size in MB (for sizes under 0.1 GB)
cleanup_apply(progress=None) -> {'ok': bool, 'message': str, 'journal': str|None}
    # both refuse (ok False, plain message) while a Fast or save pack is in Mods: prepare 'full' first.
graphics_tune(apply=False, progress=None) -> {'ok': bool, 'message': str,
                                              'table': [{'setting','stock','before','after','prop','detail'}]}
    # setting: a plain label ("Sim detail distance", "Small-object culling", "Shadow sharpness", ...);
    # prop: the rules property; detail: a longer description.
graphics_restore(apply=False, progress=None) -> {'ok': bool, 'message': str}
report(progress=None) -> {'ok': bool, 'message': str, 'path': str}    # library_report.html
open_animator() -> {'ok': bool, 'message': str}                     # starts Tools\sims4_animator\Wicked Animator.exe
    # (the desktop app; single-instance, so a second start brings its window to the front), without a console;
    # falls back to 'Start Wicked Animator.bat' when the exe is missing. status()['animator']['path'] is the
    # one that would start (exe or .bat).
open_folder(which) -> {'ok': bool, 'message': str}                  # which: mods|reports|inbox|saves|quarantine
                                                                    # (added: 'report_html' opens library_report.html)

# (added) finding the game; the app draws its own folder browser:
browse(path=None) -> {'ok': bool, 'message': str, 'path': str|None, 'parent': str|None,
                      'drives': [{'name': 'C:', 'label': str, 'free_gb': float}],
                      'entries': [{'name': str, 'path': str, 'is_game': bool, 'hint': str|None}],
                      'is_game': bool,                      # the folder at 'path' itself is a Sims 4 install
                      'suggestions': [{'name', 'path', 'exe', 'source', 'is_game': True, 'hint'}]}
    # path None = "This PC": entries are the fixed drives. Otherwise one level of sub-folders, sorted, hidden/system
    # folders and folders that cannot be opened left out. is_game: the folder is a game root (Game\Bin\TS4_x64.exe),
    # its Game or Bin folder, or holds TS4_x64.exe. hint: 'Looks like The Sims 4', 'Steam library', 'Steam',
    # 'EA games folder', 'Might be The Sims 4', or for a drive '<n> GB free'. suggestions: installs found
    # automatically (running game, shortcuts, registry, Steam, common folders) - offer them first.
set_game_path(path) -> {'ok': bool, 'message': str, 'exe': str|None, 'game_dir': str|None}
    # Any of those shapes (or the exe itself); saved for good in <Sims 4>\SpeedKit\settings.json
    # {"game_exe", "saved"}; from then on it wins over every automatic clue.
choose_game_folder() -> {'ok': False, 'message': str, 'exe': None, 'game_dir': None}   # stub for old app builds

# for tests / other folders (not for the app): configure(sims=..., db_path=..., check_game=..., ...), reset()
```

Launching: a Steam install ('store' == 'steam', the exe is under steamapps\common) is started through
`steam://rungameid/1222670` (a direct start may relaunch through Steam); every other install starts
TS4_x64.exe directly. launch_time.json is written either way (for 'save:<slot>' it also names the save).

After play('save:<slot>'), SpeedKit\profile_state.json is
`{"profile": "save", "save_slot": "Slot_00000014", "pack_dir": "...\\SpeedKit\\savepacks\\Slot_00000014",
"save_name": ..., "save_slot_id": ..., "save_guid": ..., "save_pack": [...], "installed_nowhere": [...], "switched": iso}`.
SpeedKit Monitor reads it: when another save is loaded in that mode, or (fast and save modes) the household
wears CC the mode does not load (CC installed nowhere does not count - it is missing in every mode), it shows
"This save was not prepared for this mode - do not save. Restart the game from Novulon's Sims Hub."

## speedkit/hub/ (owned by the APP agent)

- `speedkit/hub/server.py`: `python -m speedkit.hub` starts a local server on 127.0.0.1:8766 (ThreadingHTTPServer),
  serving `speedkit/hub/web/` and a JSON API (server.py's docstring is the reference):
  - `GET /api/ping` -> a cheap "is it up" check for the launcher
  - `GET /api/status[?refresh=1]` -> api.status() (cached a few seconds) plus a 'hub' block
  - `GET /api/saves[?refresh=1]` -> api.list_saves() (cached for 60 s)
  - `GET /api/graphics[?refresh=1]` -> api.graphics_tune(apply=False) (the before/after table, read-only)
  - `GET /api/inbox[?refresh=1]` -> api.inbox(apply=False) (read-only)
    (these three never run beside a task: the last answer, or 'busy', instead)
  - `GET /api/browse?path=...` -> api.browse(path)
  - `POST /api/game_path` `{"path"}` -> api.set_game_path(path)
  - `POST /api/task` `{"action": "play"|"prepare"|"undo_last"|"inbox"|"cleanup_plan"|"cleanup_apply"|"graphics_tune"|"graphics_restore"|"report", "args": {...}}`
    -> `{"task": id}`; only one task at a time (second request -> 409 with a plain message)
  - `GET /api/task/<id>` -> `{"state": "running"|"done"|"failed", "progress": [...last 50 events], "result": {...}}`
  - `GET /api/task/current` -> the running task, else the newest one (or `{"task": null}`)
  - `POST /api/open` `{"what": "animator"|"mods"|"reports"|"inbox"|"saves"|"quarantine"|"report_html"}`
  - Binds only to 127.0.0.1; rejects requests whose Host/Origin is not local.
- Launcher `Start Novulon's Sims Hub.bat` in the project root, modelled on
  `C:\Users\basim\Tools\sims4_animator\Start Wicked Animator.bat` (start server once, open Chrome/Edge `--app`).
- Desktop shortcut `C:\Users\basim\Desktop\Novulon's Sims Hub.lnk` -> `pythonw.exe -m speedkit.hub --open`
  (no console window), icon `speedkit\hub\web\img\hub.ico`.
- Look: the same design language as Novulon's Wicked Animator (read its `web/css/app.css`): dark theme,
  pink->violet gradient, Plus Jakarta Sans, "Novulon's" brand text + gradient product name. Mascot Novi
  (`branding/novi.html`, inline SVG) may appear on the home screen.

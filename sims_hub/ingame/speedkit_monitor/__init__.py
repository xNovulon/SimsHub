"""SpeedKit Monitor - a small script mod for The Sims 4 (Python 3.7, game build 1.126.73).

  (a) load timer  - launch -> script mods -> main menu -> lot playable, one CSV row per event in
                    <Sims 4>\\SpeedKit\\reports\\loadtimes.csv (loadtimer.py)
  (b) lag meter   - cheat 'speedkit.lag [seconds]': which script mods use the simulation thread, with exact
                    Zone.update tick timing; report in reports\\lag_<time>.txt + a notification (lagmeter.py)
  (c) CC guard    - after a lot loads, warns when the active household wears CAS parts this mod profile
                    does not load (ccguard.py)

The game imports every .pyc in a .ts4script (sims4.importer.utils.module_names_gen, pattern
'.+\\.py[co]$'), so each submodule is imported on its own; importing any of them runs this file first.
Start-up does as little as possible: read two small files, wrap three game functions, register three
cheats. Nothing runs per tick until 'speedkit.lag' is used. Every failure is written to
reports\\monitor.log and never reaches the game. Outside a Mods folder (tests, tools) nothing happens.
"""
import time as _time

IMPORT_TIME = _time.time()


def _start():
    try:
        from . import common
    except Exception:
        return
    if common.sims_dir() is None:                  # not loaded from <Sims 4>\Mods: stay inert
        return
    try:
        from . import loadtimer, commands
    except Exception:
        common.log_exception('SpeedKit Monitor start-up')
        return
    # three independent steps: a bad launch_time.json must not also cost the hooks and the cheats
    common.guarded('SpeedKit Monitor start-up (load timer)', loadtimer.on_import, IMPORT_TIME)
    common.guarded('SpeedKit Monitor start-up (hooks)', loadtimer.install)
    common.guarded('SpeedKit Monitor start-up (cheats)', commands.register)


_start()

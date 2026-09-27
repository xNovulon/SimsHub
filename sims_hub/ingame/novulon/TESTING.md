# Testing Novulon

Five tiers (SPEC.md Sec 16), extended in this build's shared test harness (BP16:
`tools/novulon_api_manifest/`, `tools/novulon_api_check.py`, `tools/novulon_tier2_runner.py`,
`tests/novulon_fakes.py`, `tests/test_novulon_api_surface.py`, `tests/test_novulon_ingame.py`). Every
command below is run from the `sims_hub/` folder. None of them starts the game, and none writes to
`E:\The Sims 4` or the real `Documents\Electronic Arts\The Sims 4` - Tiers 1-4 use temp folders or
read-only zip access; only Tier 5 touches a real (disposable) save, by hand.

## Tier 1 - pure Python 3.12, no game

Plain unit tests of pure logic: STBL/DDS/package round-trips, `paging.page_of()`, `sims/query.py`'s
filter functions, the settings migration chain (both first-run branches - MCCC present vs absent, per
SPEC.md Sec 7), `common.guarded()` swallowing an exception, `novulon_ids`'s FNV64 cross-check,
`build_novulon.sources()`/`verify()`, and the aggregator logic in `tools/novulon_api_manifest`
(`test_novulon_api_surface.py`'s `AggregateTests`/`VersionWarningTests` - no sibling manifest file or
game install needed for these).

```
python -m unittest tests.test_novulon_menukit tests.test_novulon_sims_query tests.test_novulon_delete \
    tests.test_novulon_compat tests.test_novulon_settings tests.test_novulon_adult tests.test_novulon_stbl \
    tests.test_novulon_icon tests.test_novulon_package tests.test_novulon_build tests.test_novulon_ids
python -m unittest tests.test_novulon_api_surface.AggregateTests tests.test_novulon_api_surface.VersionWarningTests
```

(Only the test modules that exist for your package will run - most of the list above is owned by other
build packages; run whichever files exist in `tests/`.)

## Tier 2 - inside the game's own Python 3.7, no fake Sims folder, game never started

`tools/novulon_tier2_runner.py` walks every `.py` file under `ingame/novulon/` and imports each one,
by its real dotted name, inside `python37_x64.dll` (loaded standalone in a child process by
`tools/game_python.py` - the same technique `tools/build_ingame.py`/`tests/test_ingame.py` already use
for SpeedKit Monitor). It tries the real game zips first; a module is only retried with the small
`STUBS` stand-ins (`services`, `zone`, `areaserver`, `paths`, `ui.*`, `cas.*` - see that file's own
docstring for exactly why this list and not a bigger one) if importing it for real failed. The repo's
own convention - defer a game import to inside a guarded function body, never at module import time -
means most modules should import for real, with no stub at all; a module that falls back to a stub
just means it does something at import time that needs one of those eight names, which is worth a
second look but not automatically wrong.

```
python tools/novulon_tier2_runner.py
python -m unittest tests.test_novulon_ingame -v
```

Reading the report: `ok (real)` imported using the actual game zips; `ok (stub)` needed one of the
eight stand-ins; `FAIL` is a real problem - either your module has a wrong name/typo, or it needs a
name from one of those eight modules that `STUBS` doesn't define yet (in which case: add the name to
`tools/novulon_tier2_runner.py`'s `STUBS` dict with a harmless placeholder, matching the style already
there - never guess a whole new behaviour, just enough that the name exists).

If `ingame/novulon/` has no files yet, both commands print a note and pass with nothing to check -
that's a normal state while other build packages are still landing their files, not a Tier 2 failure.

## Tier 3 - the API-existence checker (the most important safety net)

Every EA name any package's code cites lives in that package's own
`tools/novulon_api_manifest/<package>.py` (one file per build package - see that package's
`__init__.py` for the row shape). `tools/novulon_api_check.py` walks every row against **this
installed game build's own `.pyc`** (`core.zip`/`simulation.zip` under
`E:\The Sims 4\Data\Simulation\Gameplay`) and re-reads `Delta\<pack>\Version.ini`'s `packversion`,
printing a loud warning - never a silent pass - for any file that recorded a different build in its own
`CHECKED_AGAINST`/`('game_version', ...)` note.

```
python tools/novulon_api_check.py
python -m unittest tests.test_novulon_api_surface -v
```

Run it once when you add a row, and again before every future rebuild/release (a patch can rename or
remove an API with no warning of its own). Exit code is non-zero the moment any row is missing -
**verify or cut**, per the spec's hard rule; never ship a guess. If the game install itself isn't found
at `E:\The Sims 4`, the command prints a clear problem and exits 2 (not a false pass); the game-dependent
tests in `test_novulon_api_surface.py` (`ResolveTests`, `RealGameCheckerTests`) skip cleanly on a
machine without the game installed, same as the rest of this repo's tests already do.

## Tier 4 - unit tests of real logic, small fakes, no game folder or DLL

`tests/novulon_fakes.py` has `FakeSimInfo`, `FakeHousehold`, `FakeConnection`, `FakeServices`,
`FakeInstanceManager` and `FakeResetAndDeleteService` - plain Python, no game import anywhere in that
file. A package's own Tier 4 test drives its real functions directly against these:

```python
from tests.novulon_fakes import FakeSimInfo, FakeHousehold, FakeConnection, FakeResetAndDeleteService

def test_delete_skips_the_active_household(self):
    household = FakeHousehold(1, active=True)
    active = FakeSimInfo(household=household)
    other = FakeSimInfo()
    # drive sims/delete.py's is_protected()/_run() directly with [active, other]
    ...
```

For `sims/delete.py`'s async-destroy path specifically: `FakeResetAndDeleteService(auto_finish=True)`
(the default) simulates a Sim that leaves the instanced set as soon as `trigger_destroy()` is called;
`FakeResetAndDeleteService(auto_finish=False)` simulates one that **never** leaves it, so the
bounded-timeout-and-skip branch is provably exercised, not just the happy path (SPEC.md Sec 5.6/Sec 16
Tier 4's own requirement). `svc.finish_now(sim_instance)` lets a test simulate the Sim finally leaving
the instanced set on its own schedule, in between poll checks, if the delete logic needs that shape
instead.

```
python -m unittest tests.test_novulon_delete tests.test_novulon_compat tests.test_novulon_adult -v
```

(again: only the files that exist for the packages already built.)

## Tier 5 - the live-game smoke test

The one tier that actually starts the game, gated behind every package above passing Tiers 1-4 first
(and Tier 3 reporting clean against the currently installed build).

1. **Back up the real saves folder first**: copy
   `Documents\Electronic Arts\The Sims 4\saves\*.save` somewhere safe before touching anything.
2. Install Novulon (once the Hub button exists and the owner has switched it on - this build does not
   wire it into automatic install) and start the game on a **fresh, disposable save**, never the
   owner's main save.
3. Computer (or tablet) click -> the Novulon pie wedge, with its own icon and label -> the root menu
   opens.
4. Confirm one delete of an on-lot NPC. Check `<Sims 4>\Novulon\logs\` for the deletion log line and
   confirm there is no `LastException`/partial-reset entry anywhere.
5. Only after step 4 passes clean, exercise the Sim Browser and a bulk delete on the same disposable
   save - the confirmation dialog is the only safety net here (no undo path exists once
   `remove_permanently()` has run, gaps.md Sec A.4), so this step is not optional polish.
6. While still on the disposable save, use the opportunity to close any of SPEC.md Sec 18's open items
   that need one live observation rather than another static `pyc37.py --outline` pass (the search
   round trip's exact `text_inputs=` shape, `max_selectable` as a plain int, the dialog chrome re-skin
   question, and the sweep-caller confirmation).
7. Only once 1-6 are clean does this get anywhere near the owner's real save.

Nothing in Tiers 1-4 substitutes for this step - they prove the Python is correct and every cited name
exists in this build; only Tier 5 proves the whole thing behaves inside the actual running engine.

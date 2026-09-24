# SpeedKit settings: graphics rules, Options.ini, caches, memory check, launcher

Modules: `speedkit/settings.py`, `speedkit/settings_sgr.py` (graphics-rules reader), `speedkit/launch.py`.
Tests: `python tests/test_settings.py` (fake Sims tree under `E:\speedkit_test\settings`, built from
copies of the user's files with the tested values pinned, so the game rewriting Options.ini/Config.log or
a real `use-stock` does not break them) and `python tests/test_settings_review.py` (small synthetic
trees under `E:\speedkit_test\settings_review`: partial failures, undo conflicts, odd Options.ini files,
include loops) and `python tests/test_settings_tuned.py` (SpeedKit Max Quality; fake trees under
`E:\speedkit_test\graphics` built from copies of the user's ConfigOverride, Setters, Options.ini and
Config.log plus the stock rules, and small synthetic rules files).

These fixes do not touch mods. They cover the causes of lag and slow loads that the research found
outside the mod library (`research/research_results.json`, sections `settings` and `lagdrivers`,
including the skeptic's corrections).

## Command line

Every command that changes something is a dry run unless you add `--apply`.

```
python -m speedkit.settings status                   # graphics + Options.ini + caches + memory, read-only
python -m speedkit.settings graphics                 # which rules are active, differences from stock
python -m speedkit.settings use-tuned [--apply]      # SpeedKit Max Quality: SGR Full with the lag values tuned
python -m speedkit.settings graphics-restore [journal id] [--apply]   # undo (default: the last use-tuned)
python -m speedkit.settings use-stock [--apply]      # quarantine ConfigOverride\*.sgr -> game's own rules
python -m speedkit.settings use-preset Ultimate Performance [--apply]
python -m speedkit.settings options [balanced|performance]
python -m speedkit.settings options-apply [balanced|performance] [auto|keep|fullscreen|borderless|windowed] [--apply]
python -m speedkit.settings caches
python -m speedkit.settings caches-clean [localthumbcache localsimtexturecache avatarcache cachestr onlinethumbnailcache] [--apply]
python -m speedkit.settings preflight
python -m speedkit.settings journals
python -m speedkit.settings restore <journal id> [--apply]
python -m speedkit.launch [--apply]                  # preflight, then start the game detached
```

## Safety

* Every change goes through `speedkit.journal.Journal` (kind `settings`, or `caches` for caches).
  Replaced or removed files are moved to `Documents\Electronic Arts\The Sims 4\SpeedKit\quarantine\<id>\`.
  Nothing is deleted. `restore(<id>)` puts things back and refuses if a file changed since.
* `restore` (and `graphics_restore`) first works out every undo step without touching anything, keeping
  track of which paths each step frees. If any step cannot be undone (a file changed, or something now
  sits where a file would come back) it raises and moves nothing. `journal.undo` on its own checks
  those paths only when it reaches them, so it could restore half a run and then stop, and its dry run
  reports a false conflict for every replaced file (Options.ini, a replaced .sgr). The dry run of
  `restore` therefore does not call `journal.undo(dry_run=True)`.
* Real runs refuse while `TS4_x64.exe` runs. The game rewrites Options.ini when it exits, so a change
  made while it runs would be lost anyway.
* Journal ids have one-second resolution. `_open_journal` waits for a free id, so two runs in the same
  second cannot overwrite each other's journal.
* New files are first written to `SpeedKit\staging\<id>\`, then moved into place by the journal. The
  staging folder is removed only when it is empty.
* `caches_clean` accepts only the five known cache names. It refuses anything inside saves, Tray,
  Options.ini, UserSetting.ini, accountDataDB, notify.glob, content, ConfigOverride, Mods, Mods_parked
  or SpeedKit.
* `preflight` only reads. It never closes or kills a process.
* `launch_time.json` is written straight into SpeedKit's own folder, not through a journal. It is
  SpeedKit's bookkeeping, like the journal files themselves, and the game never reads it.

## 1. Graphics rules

`ConfigOverride\GraphicsRules.sgr` replaces the stock `E:\The Sims 4\Game\Bin\GraphicsRules.sgr`
entirely. The first line of Config.log shows which file was parsed.

Simp4Sims' 2023 "Setters" version computes its values from variables set in `SimpsSetters.sgr` and
`MySetters.sgr` (`${SBCull}`, `${SFSimDist1}`...). A text diff cannot show those values, so
`settings_sgr` runs the rules script: variables, if/elseif/else, include, option/setting/prop,
setProp and setOption. It evaluates the result at the player's own Options.ini levels. Machine
variables (texture memory, CPU, vendor) come from Config.log. The reader handles all of the user's
rules files without errors. It reproduces the research numbers for stock and SGR Full, and it is
unit-tested on a synthetic script. A line it cannot run is listed in `errors` and skipped, a condition it
cannot run counts as false (so the if/else nesting stays right), and an include loop is an error, not a
crash. `graphics_status` names a missing include (e.g. Setters rules without SimpsSetters.sgr).

* `graphics_status()` reports:
  * which rules are active: `stock`, `speedkit_tuned` (SpeedKit Max Quality), `simp_sgr_full`,
    `simp_setters` (plus which preset), or another override
  * which ConfigOverride files are loaded
  * whether Config.log confirms the active rules
  * each key render property that differs from stock, marked heavier or lighter
  * the number of stock options that the override leaves undefined
* `graphics_use_stock(dry_run=True)` quarantines every `.sgr` in ConfigOverride.
* `graphics_use_preset(name='Ultimate Performance', dry_run=True)` follows Simp's own install steps
  ("CHOOSE ONLY ONE"). It copies `GraphicsRules.sgr`, `SimpsSetters.sgr` and the chosen preset's
  `MySetters.sgr` from `Simps_GraphicsRules_Setters` into ConfigOverride. Files that are already
  identical are left alone. The available presets are `Ultimate Performance`, `Ultimate Quality`,
  `With Distance Blur`, and `Defaults` (Simp's empty MySetters.sgr). The plan includes a `preview`
  of the differences from stock that the preset would give.
* `graphics_use_tuned(dry_run=True, ..., source=None, replace_other=False)` installs SpeedKit Max
  Quality (section 1a). This is the default fix for this user.
* `graphics_restore(journal_id=None, dry_run=True)` is the same as `journal.undo`. With no id, it
  undoes the last SpeedKit Max Quality install.

Real values on this PC, measured read-only on 2026-09-24 at the user's levels (simquality 4,
objectquality 3, lighting 4, reflections 3, edge smoothing 3, view distance 3):

| property | stock | active SGR Full | Setters + Ultimate Performance |
|---|---|---|---|
| ObjectSizeCullFactor | 200 | 9999 | -1 (its Pixelated Bread Shop switch; effect unknown) |
| ClipPlaneDistances | 0.1, 5, 1000, 1500 | 0.1, 0.42, 9999, 9999 | 0.042, 2.4, 4200, 9000 |
| RenderSimLODDistances | 25, 50, 100, 1000 | 2999.97 ... 3000 | 8997 ... 9000 |
| RenderSimTextureSizes | 2048, 1024, 512, 128 | 2048 x4 | 2048 x4 |
| ObjectLODBias | 0.6666 | 0.00 | 0.6666 |
| ShadowMapSize | 2048 | 5120 | 2048 |
| FSAALevel | 8 | 512 | 8 |
| ExteriorMirrorFarPlane | 150 | 1200 | 9999.9 |
| Normal maps / SSAO / DoF | on / on / on | on / off / off | off / off / off |

Compared with stock, SGR Full is heavier in 16 key properties and lighter in 2. MySetters.sgr and
SimpsSetters.sgr sit in ConfigOverride but are not loaded. The override leaves 42 stock options
undefined.

**The research left one point open.** It said the Setters version with Ultimate Performance
"keeps ObjectSizeCullFactor at 200". Evaluated, that is not the case: `X_Pixelated_Bread_Shop true`
in that preset overrides it to -1. The preset also still keeps Sims at full detail out to 9000 m.
Of the ready-made files, only the stock rules restore the game's own Sim LOD switching and
small-object culling. The user wants the highest graphics without the lag, so the default fix is
**SpeedKit Max Quality** (next section), not `use-stock`. None of this was measured in game (FPS, VRAM).

## 1a. SpeedKit Max Quality (`use-tuned`)

The user asked to "keep graphics at highest but fix the lag". `graphics_use_tuned()` installs
**SpeedKit Max Quality**: the user's own SGR Full file with only its lag-causing values brought back
to sane, still high-end values. Every other line stays SGR Full, so its visual changes are kept:
2048 px Sim textures up close, reflections on all water, 4096 px object textures, SSAO and DoF off,
and the rest. Options.ini is not touched, so the in-game settings stay at Ultra / Very High.
`options_apply` still exists, but nothing calls it by default.

Values at the user's levels (Sim detail Very High, Object detail High, Lighting Very High, Reflections
High, Edge smoothing High, View distance High, Terrain High). These were measured read-only on the
real files on 2026-09-24, and `tests/test_settings_tuned.py` asserts the same numbers:

| property | stock | SGR Full (before) | SpeedKit Max Quality (after) | rule |
|---|---|---|---|---|
| RenderSimLODDistances | 25, 50, 100, 1000 | 2999.97 ... 3000 | **50, 100, 200, 2000** | 2x stock |
| RenderSimTextureSizes | 2048, 1024, 512, 128 | 2048 x4 | **2048, 2048, 1024, 512** | each step gets the size stock uses one step closer |
| ObjectSizeCullFactor | 200 | 9999 | **200** | stock |
| ObjectLODBias | 0.6666 | 0.00 | **0.6666** | stock |
| ClipPlaneDistances | 0.1, 5, 1000, 1500 | 0.1, 0.42, 9999, 9999 | **0.1, 0.42, 1000, 1500** | far = stock, near stays |
| FSAALevel | 8 | 512 | **8** | at most 8 (stock High; 512 is not a real level) |
| ShadowMapSize | 2048 | 5120 | **4096** | at most 2x stock |
| MirrorFadeRadiusThreshold | 1.3 | 120 | **2.6** | at most 2x stock |
| InteriorMirrorFarPlane | 75 | 900 | **150** | at most 2x stock |
| ExteriorMirrorFarPlane | 150 | 1200 | **300** | at most 2x stock |
| TerrainLODBoost | 1 | 6 | **2** | at most 2 (or stock, if higher) |

How it works:

* **Every rule is a cap computed from the stock value of the same option level.** A value that is
  already at or below the cap is kept. Running it twice changes nothing, and a lighter value the user
  typed into the file later stays. The stock values are read from the game's own
  `GraphicsRules.sgr` at run time, so they follow game patches.
* **The same rules apply at every level of these options, not only the user's.** Choosing a lower
  level in the game therefore never brings back SGR Full's 3000 m Sim LOD, for example Sim detail
  High becomes 10/60/170/500 m. This changes 31 lines of the real file. Reflections Off and
  Low/Medium, shadows High, FSAA Low/Medium, object LOD bias Low/Medium, terrain and view distance
  Low all get the same kind of cap.
* **It is a minimal textual patch.** Only the value part of those `prop`/`setProp` lines changes.
  Quoting, `f` suffixes, comments, indentation and CRLF stay as they were. Two lines are added:
  * a header comment at the top that starts with `# Tuned by SpeedKit: SpeedKit Max Quality`
    (lines starting with `#`; Simp's own Setters rules also start with `#` comments)
  * `logSystemInfo "+++ Tuned by SpeedKit: Max Quality +++"` right after SGR Full's
    `+++ 19-08-2021 SGR Full +++` line, so Config.log proves the game parsed the tuned file
* **Machine-dependent if-branches get the same caps.** The rules test the GPU vendor, texture memory
  and RAM, and this laptop can also start the game on its AMD Radeon 780M iGPU. So the patch also
  covers lines in branches this PC does not take. `settings_sgr.Rules.dormant` lists them, with their
  option and level read from the file's structure. The plan marks them `other_hardware: True` and
  adds a note. The self-check checks their new values in the text. The user's SGR Full has none of its
  37 tuned-prop lines inside an if-branch, so its result does not change. The review tests evaluate
  the tuned file as the iGPU, an Intel 8 GB PC and a low-memory PC, and get the same capped values
  and every other value unchanged. Before the review, such lines were silently left at SGR Full
  values.
* **It checks the result before installing.** `settings_sgr.Rules.where` records the line where each
  prop is assigned, so the patch hits exactly those lines. The new text is then run through the rules
  reader and compared with SGR Full at every level of every option and for every global prop. The
  tuned props must have exactly the rule's value and everything else must be identical: variables,
  log lines, errors, includes, and the effective values at the user's levels. The changed lines must
  also be exactly the patched ones. If anything differs, `ValueError` is raised and nothing is
  written.
* **It installs through a Journal** of kind `settings`, with the note `graphics: SpeedKit Max Quality
  (from ...)`. The file is staged in `SpeedKit\staging\<id>\`, then `Journal.replace` quarantines the
  SGR Full file and moves the new one in, and the file is read back. If
  `ConfigOverride\GraphicsRules.sgr` changed while the plan was being made, it refuses before a
  journal is opened. It refuses while the game runs.
* **Undo** with `graphics_restore()`. With no id, it undoes the newest SpeedKit Max Quality install
  that was not undone. The dry run is the default; the real run puts back the original bytes.

Which source it uses:

* If `ConfigOverride\GraphicsRules.sgr` is SGR Full or already tuned, it uses that file. Tuning an
  already tuned file first strips SpeedKit's header and log line, and gives the same bytes as tuning
  the original.
* If there is no override (after `use-stock`, the "stock with SGR leftovers" case), it uses the
  newest SGR Full copy in SpeedKit's quarantine and adds the file. MySetters.sgr and SimpsSetters.sgr
  stay where they are.
* If ConfigOverride holds another rules file (the Setters or anything custom), it refuses with
  `action='refused'` and a plain reason. It never downgrades a user's own file silently.
  `replace_other=True` replaces it, and the other file is kept in quarantine.
* If no SGR Full can be found, it refuses.

`graphics_status()` reports `active='speedkit_tuned'` with the label `SpeedKit Max Quality (Simp4Sims
'SGR Full' 19-08-2021 with the lag-causing values tuned)`, plus:

* `tuned = {ok, over, journal, confirmed}`:
  * `ok` is False and `over` lists the props when someone edited the file back above the caps
  * `confirmed` means Config.log holds the SpeedKit line and is newer than the rules file
* `tune`: what `graphics_use_tuned` would do now (`none`, `add`, `replace`, `refused` or `error`)
* `tuned_journal`: the newest SpeedKit Max Quality install that was not undone

If the user later replaces the file, `active` shows the new kind and a note says "SpeedKit Max Quality
was installed (journal ...), but ConfigOverride\GraphicsRules.sgr has been replaced since".
`preflight()` names it too.

`graphics_tuned_table()` gives the read-only stock / before / after rows for reports. After
installation it reads the original SGR Full from quarantine. `build_tuned_rules(source)` builds the
file in memory, and `tuned_sources()` lists the files it can be made from.

Not changed on purpose, because the spec lists only the values above: SGR Full's
`ObjectLODInterestBias` 0 (stock 0.56), `ClipPlaneZoomDistant` 999 (stock 75), `ClipPlaneExponent` 0
(stock 1), `FogDistances` and water reflections on every water area (`WaterReflectionAreaThreshold*`
0; stock 50/75). They are visual choices of SGR Full. Their cost has not been measured.

Compared with stock: no value that SpeedKit changes ends up below stock, at any level of any option.
Each cap is at least the stock value, and `ObjectLODBias` becomes exactly stock. A review test
asserts this. Some values SGR Full itself sets below stock stay that way, because the spec keeps
every other SGR Full line. At the user's levels these are `SsaoEnabled` false (stock true),
`ShadowDecalEnabled` false (stock true), `DofEnabled` false (stock true) and
`TerrainSlopeScalingEnabled` 0 (stock 1). Turning SSAO back on would move the look closer to stock
and costs GPU time. It is a choice for the user, not part of the lag fix.

## 2. Options.ini

`options_status()` lists the performance-relevant keys with their plain meaning and what the
preset would change. `options_apply(preset='balanced', dry_run=True, display='auto', extra=None)`
rewrites only those keys. Every other line, including CRLF endings and blank lines, stays
byte-identical. A missing key is appended in the game's own style.

* `balanced` (the research proposal):

  | setting | new value |
  |---|---|
  | visualquality | 0 (Custom, so no preset re-applies) |
  | Sim detail | High (3) |
  | Uncompressed Sim textures | off |
  | Lighting | High (3) |
  | Reflections | Low (1) |
  | Edge smoothing | Low (1) |
  | Effects | Medium (2) |
  | Frame limit | 60 |
  | vsync | off (the 60 fps cap already limits the GPU; vsync would only add latency) |

* `performance` goes one step lower: Sim detail Medium, Lighting Medium, Reflections Off, Edge
  smoothing Off, Effects Low, Object detail Medium, Terrain Medium, frame limit 60. View distance
  stays unchanged.
* `display`:
  * `auto` fixes the current `fullscreen=1` + `windowedfullscreen=1` by choosing fullscreen (1/0).
    If the file is already consistent, it keeps it.
  * `fullscreen`, `borderless` (0/1), `windowed` (0/0) or `keep` choose explicitly.
  * The game's own encoding of "windowed fullscreen" is not verified: on 9/23 it wrote 1/1 itself.
* `extra={'maxprotectedsims': 0}` and similar set other listed keys.
* Every value must be a whole number, and for keys with levels one of the known levels (for example
  simquality 1-4, generalreflections 0-3); anything else raises ValueError, so no value can add lines.

For the real Options.ini of 9/23, `balanced` would change 9 keys: visualquality 5->0, simquality 4->3,
useuncompressedtextures 1->0, lightingquality 4->3, generalreflections 3->1, edgesmoothing 3->1,
visualeffects 3->2, frameratelimit 240->60, windowedfullscreen 1->0. On 9/24 (01:44 and 01:53) the game
itself rewrote Options.ini with fullscreen=0 and windowedfullscreen=1, so `auto` now keeps the display
keys and `balanced` changes the other 8. That the game writes 0/1 supports `borderless` = 0/1; the 9/23
state 1/1 was probably also windowed fullscreen, so `auto` turning 1/1 into 1/0 is a switch to
exclusive fullscreen, shown in the plan.

## 3. Caches

The safe list comes from Crinrict's pages, which the skeptic confirmed:

* `localthumbcache`: clean it after adding or removing CC. This is the default.
* `localsimtexturecache`, `avatarcache`, `cachestr`, `onlinethumbnailcache`: optional.

None of them makes startup faster. Files inside the `cachestr` and `onlinethumbnailcache` folders
are quarantined one by one, and the folders stay in place.

Real state: localthumbcache 0 files (the Mods switch tool moves it into `Mods_parked\_old_caches`,
2 files, 31.6 MB; SpeedKit reports those and never touches them). localsimtexturecache is 33.5 MB,
cachestr has 1 file, and onlinethumbnailcache has 18 files (2.3 MB).

## 4. Preflight

`preflight()` reports:

* free RAM and commit charge (GlobalMemoryStatusEx)
* page file use and the biggest apps by private memory, with all processes of an app added up
  (PowerShell Get-Process + Win32_PageFileUsage, one call of about 1.3 s; tasklist as a fallback)
* free space on C: and E:
* whether TS4 runs
* whether the Mods switch tool's lean set is active
* the free memory at the last game start (Config.log)
* a one-line graphics-rules hint

Warnings are plain sentences such as "Chrome uses 20.6 GB (53 processes) - close it before
playing". Windows services (session 0) get "restarting the PC gives that back" instead, because
they cannot simply be closed.

Real report, 2026-09-24:

* 0.4-0.5 GB of 15.3 GB RAM free; commit 47-48 GB of 74.6 GB
* page file 23.6-25.1 GB in use (peak 41 GB)
* Chrome 19.5-21.0 GB (53 processes), Claude 4.0 GB, the DtsApo4Service audio service 2.8 GB,
  Explorer 2.4 GB, Brave 1.6-2.2 GB, Discord 1.2 GB
* C: 57 GB free of 953 GB (6%)
* 559 MB free at the last game start
* lean set active: 652 mod files (240 GB) parked

## 5. Launch

`launch(exe=GAME_EXE, dry_run=True, args=(), profile=None)` works in these steps:

1. It runs `preflight`.
2. It refuses if TS4 already runs or the exe is missing.
3. It starts the exe detached: no console, its own process group, and outside the caller's job
   object when Windows allows it.
4. It writes `SpeedKit\launch_time.json` with `epoch`, `iso`, `profile`, `profile_source`, `exe`,
   `args` and `pid`.

`profile` comes from `SpeedKit\profile_state.json` when a profile tool wrote one (the in-game
monitor reads the same file). Otherwise it is `lean` or `full`, read from
`Mods_parked\_manifest.json`. No command-line flags are
passed by default, because the flag strings the research found in the exe are untested.

## Open points

* FPS and VRAM effects of stock vs SGR Full vs the Setters presets vs SpeedKit Max Quality are unmeasured
  (needs an in-game A/B; the SpeedKit Monitor's 'speedkit.lag' profiler can provide it).
* The meaning and unit of `MirrorFadeRadiusThreshold` are inferred (stock 1.0-1.3 rising with quality,
  SGR Full 2.4-120); SpeedKit caps it at 2x stock like the mirror far planes.
* The game has been seen to load SGR Full although the `#< ... #>` signature block at its end is EA's
  (Simp edited the file without re-signing), so the signature is not checked for ConfigOverride; the
  tuned file keeps that block unchanged. Config.log's `+++ Tuned by SpeedKit` line confirms it after the
  next start.
* The effect of ObjectSizeCullFactor -1 and ObjectLODInterestBias -1 (Setters "Pixelated Bread
  Shop") is unknown.
* The engine's handling of undefined rule variables is unknown. The reader treats them as 0; the
  Setters' auto quality mode reads `$adjustedTextureMemory` before the rules define it.
* How the game encodes "windowed fullscreen" in Options.ini (it has written both 1/1 and 0/1).

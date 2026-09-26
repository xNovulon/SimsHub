# Handoff: Novulon's Sims 4 Apps

Repository: https://github.com/xNovulon/SimsHub. The old repository, github.com/Novulxn/Sims-Hub, belongs to a
flagged account. Don't use it.

## Rules from the owner
- Commit as `xNovulon <333538462+xNovulon@users.noreply.github.com>`. Don't add Claude/AI attribution lines. The
  Contributors list must show only xNovulon.
- App text must read as natural, human-written product copy. No mascot, no first-person voice ("I'll", "Let's"),
  and no AI filler words ("seamlessly", "effortlessly", "unlock", "elevate").
- The Hub's start modes are named "Quick Start" and "Full Start". The README has no emojis.
- Keep replies to the owner short and plain.

## Releasing: push to dev, never to main
Both apps auto-update every user straight from `main` (Updater.cs, `speedkit/hub/update.py`), so a broken `main` is a
broken app for everyone the moment they open it. That happened on 2026-09-26: a lost `)` in
`wicked_animator/web/js/home.js` reached `main` and every copy of the animator opened to "Could not start" - nothing
had checked the apps' JavaScript, and nothing had opened either app in a real page first.

The fix is a gate (`.github/workflows/dev-gate.yml`): work goes on `dev`, never straight to `main`. Every push to
`dev` runs the checks below (`checks` job), and only if every one of them passes does `main` fast-forward to that
commit by itself (`promote` job) - a plain `git push`, so a `dev` that has diverged from `main` is refused, never
overwritten.
- **Syntax**: every `.js` under each app's web UI actually parses (`tools/ci/check_js_syntax.py` - what
  `python -m compileall` can't check, since it only reads Python) and every `.py` in both apps compiles.
- **Boot smoke test** (`tools/ci/smoke.py`, Playwright + Chromium, headless): starts the Hub in example-data mode and
  the animator against its stand-in game server, opens each one for real, visits every page, and fails on anything
  that stops it rendering. Run it yourself with `python tools/ci/smoke.py` (add `--hub` or `--animator` for just
  one); needs `pip install playwright && python -m playwright install chromium` once.
- Because `git push` with the bot's token doesn't trigger other workflows, `promote` starts `build-apps.yml` itself
  (`gh workflow run build-apps.yml --ref main`) when the commit touches something it watches - never otherwise.
- GitHub never lets the bot's token change files in `.github/workflows/`. A commit that edits a workflow can't be
  promoted by the gate: let its checks pass on `dev`, then push that same commit to `main` by hand.
- Tested on 2026-09-26: a deliberately broken `home.js` pushed to `dev` failed the syntax check and never reached
  `main`.

## Branches
| Branch | State |
| --- | --- |
| `main` | Live. This is what users and auto-updates get. Only `dev-gate.yml`'s `promote` job pushes here. |
| `dev` | Where work happens. Push here; the gate promotes it to `main` once the checks pass. |
| `next` | Released: its clothing preview is in `main`. Nothing left on it. |
| `wip/fbx-import` | FBX motion-file import. Unfinished. Builds on `next`. |
| `wip/hub-translations` | Hub in 6 languages. Unfinished: Spanish was started, the rest isn't done. Builds on `next`. |
| `wip/animator-translations` | Animator in 6 languages. Unfinished. Builds on `next`. It has unresolved conflict markers in `wicked_animator/web/js/dialogs/export.js`, `dialogs/tray.js`, `share.js` and `steps/body.js`. |

The animator redesign was stopped before anything was saved, so it has to be redone.

## How it's built
- `wicked_animator/`: Python engine (`backend/`) and web UI (`web/`). Plug-ins go in `web/js/features/`.
- `sims_hub/`: Python engine (`speedkit/`) and web UI (`speedkit/hub/web/`).
- `shared/desktop/`: C# code both Windows apps share. It covers self-install, auto-update, Python and WebView2
  setup, and the splash screen. Each app's `desktop/Program.cs` sets its details (install folder, files to skip,
  Python packages).
- **Updates:**
  - The apps fetch changed files from `main` through the GitHub API.
  - New `.exe` builds come from the release tagged `apps`, which also holds a `.sha256` file per program.
  - `.github/workflows/build-apps.yml` builds and publishes both programs whenever a `desktop/` folder,
    `shared/desktop` or an app icon changes.
  - The programs are single-file .NET apps that read parts of themselves from their own file while they run, so a
    running program's file must never be swapped. A new build waits in `%LOCALAPPDATA%\<app>\update\`; the old
    program ends and opens it with `--finish-update`, and it puts itself in place (`Setup.FinishUpdate`). Builds
    before 7202e4a swapped their own file and got stuck with an empty "Something went wrong"; `Setup.EndStaleCopy`
    ends such a copy when the app is opened again.
- `wicked_animator/data/ww_example_objects.json` is WickedWhims' list of places, uploaded by the owner. Keep it.

## Next steps, in order
1. Done: `next` is released into `main`.
2. **Finish FBX import** (`wip/fbx-import`).
   - Plan: load the file with three.js's FBXLoader, sample the joints' world positions for each frame, and feed
     them through the same path the BVH import uses (`web/js/capture/bvh.js`, `web/js/mocapfile.js`).
   - Add FBX test files, and extend `tools/checks/mocap/bvh_check.mjs` and `smoke_ui.py`.
3. **Finish the Hub translations** (`wip/hub-translations`).
   - Languages: es, pt-BR, fr, de, it, pl.
   - Catalogs go in `speedkit/hub/web/i18n/`, with a language picker on the Tools page.
   - As you move each piece of English text into the catalog, rewrite it to sound natural, then translate from the
     new English.
   - Include the text in `js/batchfix.js`.
   - Add checks that every catalog has the same keys and placeholders, and that no English text is left in the UI.
4. **Finish the animator translations** (`wip/animator-translations`).
   - First fix the 4 files with conflict markers.
   - Then do the same work as step 3, with catalogs in `wicked_animator/web/i18n/`. Leave the "Say it" parser in
     English.
5. **Redesign the animator.**
   - Aim for a premium look that's easy to use: a design system, a stronger Home screen, a clear step bar, a
     polished timeline, dialogs and motion that respects reduced-motion.
   - Use CSS and small changes to the markup. Keep ids and data attributes as they are.
   - The Hub redesign (`sims_hub/speedkit/hub/web/css/hub.css`) is the style reference.
6. **Ideas from research** (what players and Blender animators ask for that the apps don't have yet):
   - Hub: a Tray checker that lists the CC a saved household or lot uses and what is missing, before it's placed.
   - Hub: an update checker for script mods the player tracks (a link per mod, flagged when a newer file is out).
   - Animator: check that the Details step covers every WickedWhims tuning field creators edit by hand (actor
     offsets, naked type per actor, climax and PULLED_OUT events).
7. **Update the README screenshot** (`.github/assets/sims-hub-home.png`) once the text and design are final.
8. **The owner tests in the game.** These were only tested without The Sims 4:
   - Magic's claps and wet sounds (placed on each stroke's deepest moment; Magic adds no voices)
   - a growing erection (the penis base's scale channel: does the game play bone scale?)
   - lips pulling along in oral animations
   - Tray sims' makeup and outfits, the clothes remover
   - own sounds
   - the "Fit hands to each sim's body" switch
   - the clothes preview
   - props, dances and other places
   - batch-fix accuracy
   - patch-day detection
   - Better Exceptions report parsing

## Notes from the last session
- Run the Hub checks with The Sims 4 closed: the end-to-end tests see the real game and refuse to change files while
  it runs. With the game closed, all Hub tests pass (tests/__init__.py keeps another library's "tests" package from
  hiding the folder). wired/backend_check's two "without a game" rows need a PC without the game at a guessed
  install path.
- Animator checks that depend on the PC, not the code:
  - r2-2/contact: its kiss rows depend on which WickedWhims kiss animation `cache/poses_v6.json` was built from
    (the player's own Mods). With "Addicted to Her" it's 59/0; with the OLL "Sweet/Tender Kiss" the kiss gets no
    hand holds and 3 rows fail. Delete the cache file to rebuild it.
  - r2-1/editing check 1: at 1366x768 the timeline is 106 px tall and the second sim's lane is half out of view, so
    the box drag misses it. It fails the same way on the pushed version.
  - r1d/capture steps 7 and 8: the stand-in video stays at 0% "read" in headless Chrome, and the step times out.
    Same on the pushed version. Steps 3-6, 7a-7c and 7i pass.
- The animator opens on an empty scene. Checks that expect the couple pass `scene: 'couple'` to `harness.open`
  (or call `app.newScene(false, false, 'couple')`).
- The owner asked for "a normal app, not a browser". Both apps are Windows programs that draw with WebView2; the
  browser menu, text highlighting, dragging and pinch zoom are turned off. A native rewrite was not started.
- The owner asked for the animator to be "separated from Sims Hub". They are separate programs (own folder, exe,
  updater, data folder, port); the only link is the Hub's Tools card that opens the animator, with Studio mode.
  Ask whether to remove that card or split the repository before doing either (installed apps update from this
  repository's paths).

- Lip pull when sucking is on for new sims only (`body.open.lipPull === true`); sims saved before it keep it off so
  old projects bake the same.
- Clothes are drawn like the game: garments and painted pieces (tights) are painted onto the sim's skin picture and
  the bare body piece a garment replaces is hidden (Sim.setCovered, clothes.js paintOnSkin).
- README pictures come from shots.py-style runs against example data (Hub) and a test server (animator). Keep them
  free of nudity and adult words: faces, clothed sims, the Hub.

## Checks
**Hub** (from `sims_hub/`):

```
python3 -m unittest tests.test_update tests.test_hub_open tests.test_hub_server tests.test_hub_launcher \
  tests.test_care_patchday tests.test_care_errors tests.test_care_saves tests.test_care_loadtimes \
  tests.test_care_server tests.test_care_ui tests.test_ccbrowser tests.test_ccbrowser_hub tests.test_ccbrowser_ui \
  tests.test_batchfix tests.test_batchfix_server tests.test_batchfix_ui
```

On Linux, `test_pythonw_opens_python_serves` always fails. That's expected. Other tests need Windows (`E:\` paths).

**Animator** (from `wicked_animator/`):

```
python3 tools/checks/own_sounds/test_own_sounds.py
python3 tools/checks/bodyfit/test_bodyfit.py
python3 tools/checks/clothes/test_clothes.py
python3 tools/checks/wired/backend_check.py
python3 tools/checks/wwversion/ww_version_check.py
node tools/checks/mocap/bvh_check.mjs
node tools/checks/r3-5/sayit_check.js
node tools/checks/r3-4/beat_check.js
node tools/checks/wired/proptrack_check.js
```

These run in a browser and need `WA_THREE_DIR` set to a three.js copy:

```
node tools/checks/wired/ui_smoke.js
node tools/checks/clothes/ui_smoke.js
python3 tools/checks/mocap/smoke_ui.py
python3 tools/checks/own_sounds/smoke_ui.py
python3 tools/checks/bodyfit/smoke_ui.py
```

`tools/checks/lib/fake_game_server.py` stands in for the game, so the UI runs without it (its sims are box-shaped
stand-ins on the real skeleton).

Playwright checks (Node's `playwright` package; `pw.js` opens the app, `{ scene: 'couple' }` starts from the couple):

```
node tools/checks/posetools/pose_tools.js      # R turns, T moves the picked part, the circle at a sim's feet moves the whole sim
node tools/checks/clothes/ui_smoke.js          # clothes preview, incl. the hover glow and selection tint on worn clothes
```

## Posing: R, T and the circle
- R gives the picked part its rings, T its arrows (`Interaction.turnSelected` / `moveSelected`). T never moves the whole
  sim: the hips shift with the feet planted and the back bent so the chest and head stay (`shiftHips`; a straight leg
  drops the hips a little), a hand, foot, forearm or calf is pulled with its arm or leg (two-bone IK), and any other part
  is pulled by turning the joints above it (`PULL`, `_pullSolve`). Only bones turn - no new position tracks in the export.
- Each sim has a pink circle on the floor under its hips (`_syncRoots`): drawn over everything, picked before anything
  else, dragged to slide the whole sim (every key). The white ring is the object's centre (where WickedWhims puts the
  animation). The M tool is now called Move: a click picks the part to move; the circle moves the whole sim.
- The Drag tool's hips dot still carries the legs along (lifting a sim); only T on the hips plants the feet.

## Owner's PC
After the next release, the owner downloads both apps once from the README buttons and opens each one. They take
over the existing installs in `%USERPROFILE%\Tools\sims4_animator` and `%USERPROFILE%\Tools\sims4_speedkit`.
After that, updates are automatic.

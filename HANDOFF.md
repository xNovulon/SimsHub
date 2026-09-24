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

## Branches
| Branch | State |
| --- | --- |
| `main` | Live. This is what users and auto-updates get. |
| `next` | `main` plus the animator's clothing preview. It's merged but hasn't been tested together with the rest. It is one commit on top of `main`. |
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
- `wicked_animator/data/ww_example_objects.json` is WickedWhims' list of places, uploaded by the owner. Keep it.

## Next steps, in order
1. **Check `next`, then release it.**
   - Run every check listed below.
   - If they pass, update `main` to `next`. It's a fast-forward: `git push origin next:main`.
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
6. **Update the README screenshot** (`.github/assets/sims-hub-home.png`) once the text and design are final.
7. **The owner tests in the game.** These were only tested without The Sims 4:
   - own sounds
   - the "Fit hands to each sim's body" switch
   - the clothes preview
   - props, dances and other places
   - batch-fix accuracy
   - patch-day detection
   - Better Exceptions report parsing

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

`tools/checks/lib/fake_game_server.py` stands in for the game, so the UI runs without it.

## Owner's PC
After the next release, the owner downloads both apps once from the README buttons and opens each one. They take
over the existing installs in `%USERPROFILE%\Tools\sims4_animator` and `%USERPROFILE%\Tools\sims4_speedkit`.
After that, updates are automatic.

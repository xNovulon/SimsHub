# Sims Hub & Wicked Animator

Unified workspace containing:
- **Sims Hub** (sims_hub/): Performance and mod management suite for The Sims 4.
- **Wicked Animator** (wicked_animator/): Animation previewer, pose editor, and authoring tools for WickedWhims.

## Auto-update

Both apps keep themselves up to date from this repository's `main` branch, so pushing to GitHub is all it takes:

| App | Opens from | Updates on this PC |
| --- | --- | --- |
| Novulon's Wicked Animator | `Wicked Animator.exe` (Desktop shortcut) | the folder the exe is in (`Tools\sims4_animator`) from `wicked_animator/` |
| Novulon's Sims Hub | "Novulon's Sims Hub" Desktop shortcut | `Tools\sims4_speedkit` from `sims_hub/` |

Each time an app opens, it asks GitHub for the newest commit. That's one small request, and it's skipped when the PC is
offline. When there's a newer commit, only the changed files are downloaded and checked against GitHub's hashes. They
are put in place only after every download succeeds. Files that aren't in the repo, like your own poses, caches and
logs, are never touched. A file you edited yourself is copied to a backup before it's replaced (the last three backups
are kept).

- Animator: `wicked_animator/desktop/Updater.cs`. Its state, log and backups are in `%LOCALAPPDATA%\NovulonWickedAnimator\update`.
  When a new `Wicked Animator.exe` arrives, the app swaps itself and reopens as the new version.
- Hub: `sims_hub/speedkit/hub/update.py`, run by the launcher before the Hub starts. Its state, log and backups are in
  `%LOCALAPPDATA%\NovulonSimsHub\update`. A Hub that is already running is restarted for an update only when no Hub
  window is open and no task is running.
- `.github/workflows/build-animator-exe.yml` rebuilds `Wicked Animator.exe` whenever `wicked_animator/desktop/` changes and
  commits it, so the exe on GitHub always matches the code.
- A folder that is a git clone of this repo is left to git (`git pull`). To turn updating off, set
  `WICKED_NO_UPDATE=1` (Animator) or `SIMS_HUB_NO_UPDATE=1` (Hub).

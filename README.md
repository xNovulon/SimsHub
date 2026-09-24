# Novulon's apps for The Sims 4

Two Windows apps. Each one is a single download: open it and it installs itself, adds its shortcuts, sets up
everything it needs, and keeps itself up to date.

| | App | What it does | Download |
| --- | --- | --- | --- |
| 🎬 | **Novulon's Wicked Animator** | Make WickedWhims animations without Blender: pose your sims, key them on a timeline, add sounds, and send them straight to the game. | [**WickedAnimator.exe**](https://github.com/Novulxn/Sims-Hub/releases/latest/download/WickedAnimator.exe) |
| ⚡ | **Novulon's Sims Hub** | Load the game faster with only the CC your saves use, fix lag while keeping max graphics, merge new downloads, and clear out duplicate CC. Nothing is ever deleted, and every change can be undone. | [**SimsHub.exe**](https://github.com/Novulxn/Sims-Hub/releases/latest/download/SimsHub.exe) |

## Installing

1. Download the app you want (or both).
2. Open it. The first time, Windows may say **"Windows protected your PC"** because the apps aren't code-signed.
   Click **More info**, then **Run anyway**.
3. That's it. The app:
   - installs itself in your user folder (`Tools\sims4_animator` or `Tools\sims4_speedkit`) and adds Desktop and
     Start Menu shortcuts,
   - installs **Python** and the Python packages it needs if they're missing (just for you; no administrator needed),
   - installs **Microsoft Edge WebView2** if it's missing (it comes with Windows 11),
   - opens.

The first start takes a minute or two while all of this happens. You can delete the downloaded file afterwards and
use the shortcuts. Both apps need Windows 10 or 11 (64-bit), and an internet connection the first time.

## Updates

Each time you open an app, it checks GitHub for a newer version. That's one small request, and it's skipped when you're
offline. New files are downloaded and checked before anything is replaced, and the app updates its own program the same
way. Your own files (projects, poses, settings, caches) are never touched. If an update replaces a file you edited, a
backup is kept.

## For developers

| Folder | What's in it |
| --- | --- |
| `wicked_animator/` | The animator: Python engine (`backend/`), web interface (`web/`), desktop app (`desktop/`), checks (`tools/`) |
| `sims_hub/` | The Hub: Python engine (`speedkit/`, UI in `speedkit/hub/`), in-game mod (`ingame/`, built into `dist/`), desktop app (`desktop/`), `tests/`, `research/`, `docs/` |
| `shared/desktop/` | What both desktop apps share: installing, updating, Python and WebView2 setup, the splash card |
| `.github/workflows/build-apps.yml` | Builds both apps on every change to their desktop code and publishes them on the [apps release](https://github.com/Novulxn/Sims-Hub/releases/tag/apps) |

- **Releasing:** push to `main`. Installed apps pick up changed files the next time they open. When desktop code changes,
  the workflow publishes new builds, and installed apps swap themselves for them.
- **What's installed on users' PCs:** each app's folder, minus the files only developers need (`desktop/`, `tools/`,
  `tests/`, `research/`, `docs/`, `branding/`). The lists are in each app's `desktop/Program.cs`.
- **Working on the code:** a git clone is never auto-updated, so it stays yours. Build an app locally with
  `desktop\build.ps1`, or run the engines directly (`python backend\server.py`, `python -m speedkit.hub`). To turn
  updating off, set `WICKED_NO_UPDATE=1` or `SIMS_HUB_NO_UPDATE=1`.
- **Logs:** `%LOCALAPPDATA%\NovulonWickedAnimator` and `%LOCALAPPDATA%\NovulonSimsHub` hold `update\update.log`,
  `python-setup.log`, `setup.log` and `engine.log`.

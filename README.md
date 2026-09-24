# Novulon's Sims 4 Apps

Two apps for The Sims 4 on Windows. Download one, open it, and you're done: there's nothing else to install
and nothing to set up.

## 🎬 Wicked Animator

**Make your own WickedWhims animations, no Blender needed.** Pose your sims, build the animation on a timeline, add
sounds, and send it straight into your game.

### [⬇ Download Wicked Animator](https://github.com/xNovulon/SimsHub/releases/latest/download/WickedAnimator.exe)

## ⚡ Sims Hub

**Make your game load faster and lag less.** The Hub starts the game with only the custom content your saves actually
use, fixes the settings that cause lag without lowering your graphics, sorts your new downloads for you, and clears out
duplicate CC. It never deletes anything, and you can undo every change it makes.

### [⬇ Download Sims Hub](https://github.com/xNovulon/SimsHub/releases/latest/download/SimsHub.exe)

---

## How to install

1. Click one of the download links above.
2. Open the file you downloaded.
3. Wait a minute or two the first time while the app sets itself up.

When it's done, the app opens by itself, and you'll find it on your Desktop and in your Start Menu. You can delete the
file you downloaded.

**"Windows protected your PC"?** That's normal for small apps like these. Click **More info**, then **Run anyway**.

## Good to know

- **Updates are automatic.** Every time you open an app, it checks for a newer version and updates itself.
- **Your stuff is safe.** Updates never touch your animations, poses, saves or settings.
- **It sets up what it needs by itself.** If your PC is missing something the app needs to run (like Python), the app
  installs it for you the first time. You don't have to do anything.
- **You'll need** Windows 10 or 11, and an internet connection the first time you open the app.

## Something went wrong?

Each app keeps notes on what it did, which help track down problems. Paste this into the File Explorer address bar to
find them:

- Wicked Animator: `%LOCALAPPDATA%\NovulonWickedAnimator`
- Sims Hub: `%LOCALAPPDATA%\NovulonSimsHub`

---

<details>
<summary><b>For developers</b></summary>

### What's where

- `wicked_animator/`: the animator. `backend/` is its Python engine, `web/` is what you see, `desktop/` is the Windows
  app around it.
- `sims_hub/`: the Hub. `speedkit/` is its Python engine (the screens are in `speedkit/hub/`), `ingame/` is the small
  in-game mod, `desktop/` is the Windows app.
- `shared/desktop/`: the parts both Windows apps share, which handle installing, updating, setting up Python and the
  loading screen.

### How releases work

Push to `main` and every installed app picks up the change the next time it's opened. When you change anything in a
`desktop/` folder, GitHub builds new versions of the apps and puts them on the
[download page](https://github.com/xNovulon/SimsHub/releases/tag/apps). Installed apps then replace themselves with the
new version. You can watch this under the **Actions** tab.

Users only get what the apps need to run. Folders like `tests/`, `research/` and `tools/` stay on GitHub. The exact
list is near the top of each app's `desktop/Program.cs`.

### Working on the code

A copy made with `git clone` never updates itself, so your work in progress is safe. To try a change, build the app
with `desktop\build.ps1`, or run the engine directly (`python backend\server.py` for the animator, `python -m
speedkit.hub` for the Hub). To stop an installed app from updating, set `WICKED_NO_UPDATE=1` or `SIMS_HUB_NO_UPDATE=1`.

</details>

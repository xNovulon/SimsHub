r"""End-to-end audit of Novulon's Sims Hub (engine: Sims 4 SpeedKit) on a realistic FAKE Sims 4 tree.

The real user folders are only ever READ (packages through dbpf.open_shared, so the other chat can still
rename them meanwhile); every change happens under E:\speedkit_test\e2e:

  source\                     built once from copies of the user's real files (rebuilt when BUILD changes)
    The Sims 4\Mods           today's layout: the other chat's studio set - WickedWhims (scripts + tuning), the
                              two LAMABOY animation packs (a subset of their real resources), FitStudio\ -,
                              Resource.cfg, the desktop.ini files and SpeedKit_Monitor.ts4script
    The Sims 4\Mods_parked    the rest, parked the way mods_switch.py parks it, with a _manifest.json cut from
                              the real one: 7 small sim\ merged packs (the ones the chosen saves use most),
                              script mods with their companions, lighting variants, sliders (some exact
                              duplicates of each other), anim1, LittleMsSam Pack\ (with its empty sub-folders),
                              Scripts testing\, TMEX-Settings\, _old_caches\
    The Sims 4\saves          2 real saves (+ a .ver backup), saves\FitStudio\ and saves\TanksMods\ (json)
    The Sims 4\Tray           3 real Tray groups (a household, a lot, a room)
    The Sims 4\ConfigOverride the original Simp4Sims 'SGR Full' GraphicsRules.sgr (from SpeedKit's quarantine)
                              + MySetters.sgr / SimpsSetters.sgr; Options.ini, Config.log, localthumbcache
    downloads\                two download zips for the Inbox, made from real mods that are not in the tree
    data\                     private copies of SpeedKit's game caches (EA ids, EA overrides)
    bin\fake.exe              a tiny program that only appends a line to launched.txt next to itself
  work\                       a fresh copy of source per run; the fake TS4_x64.exe and Wicked Animator.exe
  screens\                    headless Chrome screenshots of every Hub page (real engine, fake tree)

The game: the exe is the fake one; EA's own ids, overrides and stock graphics rules are read (read-only) from
E:\The Sims 4. Every start of a program goes through a guard that refuses anything outside work\.

The story, driven over HTTP through the real Hub server with the real speedkit.api: status, list_saves, play
fast, play a save, play full, play studio, the other chat's mods_switch.py (full then lean, with its
constants pointed at the fake tree), play fast again, the Inbox with dropped zips, the duplicate clean-up,
graphics restore/tune, undo_last back to the start (SpeedKit cannot undo past the other tool's moves: it
says so plainly, and one Studio click finishes the way back), a clean-up the other tool's lean moved (its
undo is held back until 'full'), browse/set_game_path, open_animator and the library report. After every
step: no file lost or duplicated (blake2b inventory), .ts4script contents untouched, scripts at depth <= 1
with their companions, saves/Tray/saves\FitStudio untouched, the parking list consistent (SpeedKit's check
and mods_switch.py's 'full' worked out on paper), the mode's own packs only, CAS parts loaded vs referenced
(fast/save load far fewer than full and every installed one the saves wear), what the Hub says, and the
game-running refusal of every changing action. PlainWords / RememberedCleanupHome are quick checks of
fixes the audit made. Headless Chrome screenshots of every page go to E:\speedkit_test\e2e\screens.

Skipped when the user's Sims 4 folder, E:\The Sims 4 or drive E: are missing. Slow (about 2.5 minutes).
"""
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
sys.path.insert(0, HERE)
from speedkit import api, dbpf, library as L, journal as J, profiles as PR, fastmode as F, usedpack as U  # noqa: E402
from speedkit import settings as ST, launch as LA, ingame_install, dedup, merge  # noqa: E402
from speedkit import gamepath as G  # noqa: E402
from speedkit.hub import server  # noqa: E402

BUILD = 3                                    # bump to rebuild source\ (what is copied changed)
E2E = r'E:\speedkit_test\e2e'
SOURCE = os.path.join(E2E, 'source')
WORK = os.path.join(E2E, 'work')
SCREENS = os.path.join(E2E, 'screens')
REAL_SIMS = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4')
REAL_MODS = os.path.join(REAL_SIMS, 'Mods')
REAL_PARKED = os.path.join(REAL_SIMS, 'Mods_parked')
REAL_GAME = r'E:\The Sims 4'
REAL_DATA = os.path.join(PROJECT, 'data')
MODS_SWITCH = os.path.join(os.path.expanduser('~'), 'Tools', 'sims4_fitstudio', 'mods_switch.py')
CSC = r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# ------------------------------------------------------------------------------------------ what is copied
# rel paths (relative to Mods, '/' separated); 'dir/' copies the whole folder, empty sub-folders included
MODS_COPY = ['Resource.cfg', 'desktop.ini', 'SpeedKit_Monitor.ts4script', 'scripts/desktop.ini',
             'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script', 'scripts/TURBODRIVER_WickedWhims_Tuning.package',
             'animation/desktop.ini', 'FitStudio/']
MODS_SUBSET = {'animation/WW_LAMABOY_Animation.package': 12, 'animation/WW_LAMABOY_Animations.package': 12}  # CLIPs kept
LIGHTING = ['scripts/!!![NORTHERN SIBERIA WINDS] Better In-Game Lighting Mod v1.1 %s.package' % v for v in
            ('AVERAGE BASE LIGHT ROOMS', 'DARK SATURATED LIGHT ROOMS', 'AVERAGE PALE DARK ROOMS',
             'AVERAGE SATURATED DARK ROOMS')]
SCRIPT_COMPANIONS = {
    'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script': ['scripts/TURBODRIVER_WickedWhims_Tuning.package'],
    'scripts/FallenCore_Scripts.ts4script': ['scripts/FallenCore_Tunings.package'],
    'scripts/LittleMsSam_FirstLove.ts4script': ['scripts/LittleMsSam_FirstLove.package',
                                                'scripts/LittleMsSam_FirstLove_Addon_2xFasterProgress.package',
                                                'scripts/LittleMsSam_FirstLove_Addon_HideInteractions.package'],
    'scripts/lot51_plumbbros.ts4script': ['scripts/lot51_plumbbros.package'],
    'scripts/mc_cmd_center.ts4script': ['scripts/mc_cmd_center.package'],
    'scripts/mc_woohoo.ts4script': ['scripts/mc_woohoo.package'],
    'scripts/DQuiet_SimControlHub.ts4script': ['scripts/DQuiet_SimControlHub.package',
                                               'scripts/DQuiet_SimControlHub_SituationManager.package'],
    'scripts/HARKI_Wicked_Perversions.ts4script': ['scripts/HARKI_Wicked_Perversions_Tuning.package'],
    'scripts/[Kuttoe] BasementalAddons.ts4script': ['scripts/[Kuttoe] BasementalAddons - Holidays.package',
                                                    'scripts/[Kuttoe] BasementalAddons - SketchyLotTrait.package'],
    'scripts/UI_Cheats_Extension_Scripts.ts4script': ['scripts/UI_Cheats_Extension.package'],
}
PARKED_COPY = [
    # the smallest sim\ merged packs, chosen by how many CAS parts the two saves wear from them
    'sim/m1.package', 'sim/101.package', 'sim/SkinDetails[MERGED]2.package',
    'sim/[dreamlike] preset sets无病毒版！！.package', 'sim/WW_KhlasGayAnimations.package',
    'sim/[BR]Pregnancy Set Eva Jumpsuit.package', 'sim/[NORTHERN SIBERIA WINDS] SKIN N15 B.package',
    # script mods and their companions (+ their logs / settings files)
    'scripts/lot51_core.ts4script', 'scripts/lot51_core.log', 'scripts/mc_cmd_center.log', 'scripts/mc_settings.cfg',
    'scripts/DQuiet_SimControlHub.json', 'scripts/Cumshine.ts4script',
    'scripts/HRK_Aspirations.package', 'scripts/HRK_StringTables.package',
    # WickedWhims tuning add-ons, traits, sliders / presets (two pairs are exact duplicates), a tiny CAS CC
    'scripts/[Noir] SmoothVagina-Tuning-WickedWhims.package', 'scripts/[Noir] WerewolvesInTheWild-Tuning-WickedWhims.package',
    'scripts/chingyu_Trait_Homebody.package', 'scripts/!chingyu_casVer_BasicTraits_V2.6.package',
    'scripts/!chingyu_RewardVer_BasicTraits_V2.6.package',
    'scripts/LUUMIAmodEarPresets.package', 'scripts/LUUMIA_mod_EarPresets.package',
    'scripts/miikochinsliderremake.package', 'scripts/HFO_TS4AUNoseTipSlider.package',
    'scripts/GOLY_NECKSLIDER_FIXED.package', 'scripts/nickiminajtattoomh75.package',
    'animation/anim1.package',
    'Sliders/desktop.ini', 'Sliders/miiko-chin-slider(remake).package',
    'Sliders/Ice-CreamForBreakfast_TS4AUNoseTipSliderUpdated.package',
    'Sliders/LUUMIA_mod_EarUpDownSlider_UpdateJune2022.package', 'Sliders/(marsosims)HeadSizeSlider.package',
    'Sliders/obscurus nose depth slider_Fixed.package', 'Sliders/HFO_TS4LipUpSlider.package',
    'LittleMsSam Pack/', 'Scripts testing/', 'TMEX-Settings/',
] + LIGHTING + [r for s, cs in SCRIPT_COMPANIONS.items() if s.startswith('scripts/') and 'TURBODRIVER' not in s
                for r in [s] + cs]
SAVES_COPY = ['Slot_00000016.save', 'Slot_00000016.save.ver0', 'Slot_00000005.save', 'FitStudio/', 'TanksMods/']
SLOTS = ('Slot_00000016', 'Slot_00000005')
TRAY_IDS = ('00380fb29b4c1694', '530c2397061f433c', '00e10841de7d01e5')
ROOT_COPY = ['Options.ini', 'Config.log', 'GameVersion.txt', 'localthumbcache.package']
FAKE_EXE_CS = r'''using System; using System.IO;
class FakeProgram { static void Main(string[] a) {
  string d = AppDomain.CurrentDomain.BaseDirectory;
  File.AppendAllText(Path.Combine(d, "launched.txt"), DateTime.Now.ToString("o") + " " + string.Join(" ", a)
    + " cwd=" + Environment.CurrentDirectory + "\r\n"); } }
'''
KEEP_UNDER = (E2E,)


def _under(path, bases=KEEP_UNDER):
    p = os.path.normcase(os.path.abspath(path))
    return any(p == os.path.normcase(b) or p.startswith(os.path.normcase(b) + os.sep) for b in bases)


def _rmtree_e2e(path):
    """Remove a folder of the test - only ever below E:\\speedkit_test\\e2e."""
    assert _under(path) and os.path.normcase(os.path.abspath(path)) != os.path.normcase(E2E), path
    if os.path.isdir(path):
        subprocess.run(['cmd', '/c', 'attrib', '-h', '-s', '-r', os.path.join(path, '*'), '/s', '/d'],
                       capture_output=True)
        shutil.rmtree(path)


def available():
    return (os.name == 'nt' and os.path.isdir(REAL_MODS) and os.path.isdir(REAL_PARKED)
            and os.path.isfile(os.path.join(REAL_GAME, 'Game', 'Bin', 'TS4_x64.exe')) and os.path.isdir('E:\\')
            and os.path.isfile(MODS_SWITCH))


# ------------------------------------------------------------------------------------------ building source\
def _copy_shared(src, dst):
    """Copy a real file without blocking renames of it meanwhile (dbpf.open_shared); keeps its times."""
    assert _under(dst), dst
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    st = os.stat(src)
    with dbpf.open_shared(src) as f, open(dst + '.part', 'wb') as g:
        shutil.copyfileobj(f, g, 1 << 22)
    os.replace(dst + '.part', dst)
    os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))


def _copy_tree_shared(src, dst):
    for dp, dn, fn in os.walk(src):
        rel = os.path.relpath(dp, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for n in fn:
            _copy_shared(os.path.join(dp, n), os.path.join(dst, rel, n))


def _copy_rel(real_root, fake_root, rel):
    src = os.path.join(real_root, rel.rstrip('/').replace('/', os.sep))
    dst = os.path.join(fake_root, rel.rstrip('/').replace('/', os.sep))
    if rel.endswith('/'):
        _copy_tree_shared(src, dst)
    else:
        _copy_shared(src, dst)


def _hide(path):
    """desktop.ini files are hidden + system on the real PC; so are the copies."""
    import ctypes
    ctypes.windll.kernel32.SetFileAttributesW(path, 0x2 | 0x4)


def _subset_package(src, dst, keep):
    """A smaller package with a subset of src's resources, copied bit-exact (keep(entry, pkg) -> bool)."""
    with dbpf.Package(src) as p:
        seen = set()
        with dbpf.PackageWriter(dst) as w:
            for e in sorted(p.entries, key=lambda e: e.off):
                k = (e.t, e.g, e.i)
                if e.comp == dbpf.DELETED or k in seen or not keep(e, p):
                    continue
                seen.add(k)
                w.add_raw(e, p.raw(e))


def _clip_subset(n_clips):
    clips = set()

    def keep(e, p):
        if e.t == 0x6B20C4F3:                  # CLIP: the first n only (and their CLHD headers)
            if len(clips) >= n_clips:
                return False
            clips.add(e.i)
            return True
        if e.t == 0xBC4A5044:
            return e.i in clips
        return True
    return keep


def _cc_subset(src, dst, first, count):
    """A 'downloaded' CC file: CAS parts first..first+count of src with everything their TGI lists name and
    their thumbnails."""
    with dbpf.Package(src) as p:
        casps = [e for e in p.entries if e.t == U.T_CASP and e.comp != dbpf.DELETED][first:first + count]
        want = {(e.t, e.g, e.i) for e in casps}
        for e in casps:
            want.update(tuple(k) for k in U.casp_refs(p.read(e)))
        insts = {e.i for e in casps}
    _subset_package(src, dst, lambda e, p: (e.t, e.g, e.i) in want or e.i in insts)


def _sqlite_copy(src, dst):
    s = sqlite3.connect('file:%s?mode=ro' % src.replace(os.sep, '/'), uri=True)
    d = sqlite3.connect(dst)
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def _manifest_for(parked_dir):
    """The real parking list cut down to what the fake Mods_parked holds (same order, same layout)."""
    with open(os.path.join(REAL_PARKED, '_manifest.json'), encoding='utf-8') as f:
        real = json.load(f)
    moved = [e for e in real['moved'] if os.path.exists(os.path.join(parked_dir, e.rstrip('/').replace('/', os.sep)))]
    return dict(real, moved=moved)


def build_source(log=print):
    """source\\ from copies of the real files; reused while its BUILD number is current."""
    stamp = os.path.join(SOURCE, 'source.json')
    try:
        with open(stamp, encoding='utf-8') as f:
            if json.load(f).get('build') == BUILD:
                return
    except (OSError, ValueError):
        pass
    t0 = time.time()
    _rmtree_e2e(SOURCE)
    sims = os.path.join(SOURCE, 'The Sims 4')
    mods, parked = os.path.join(sims, 'Mods'), os.path.join(sims, 'Mods_parked')
    log('building %s from copies of the real files' % SOURCE)
    for rel in MODS_COPY:
        _copy_rel(REAL_MODS, mods, rel)
    for rel, n in MODS_SUBSET.items():
        dst = os.path.join(mods, rel.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _subset_package(os.path.join(REAL_MODS, rel.replace('/', os.sep)), dst, _clip_subset(n))
    for rel in PARKED_COPY:
        _copy_rel(REAL_PARKED, parked, rel)
    cache = min((n for n in os.listdir(os.path.join(REAL_PARKED, '_old_caches'))),
                key=lambda n: os.path.getsize(os.path.join(REAL_PARKED, '_old_caches', n)))
    _copy_rel(REAL_PARKED, parked, '_old_caches/' + cache)
    with open(os.path.join(parked, '_manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(_manifest_for(parked), f, indent=1)
    for rel in SAVES_COPY:
        _copy_rel(os.path.join(REAL_SIMS, 'saves'), os.path.join(sims, 'saves'), rel)
    tray = os.path.join(REAL_SIMS, 'Tray')
    for n in os.listdir(tray):
        if any(i in n.lower() for i in TRAY_IDS):
            _copy_shared(os.path.join(tray, n), os.path.join(sims, 'Tray', n))
    q = os.path.join(REAL_SIMS, 'SpeedKit', 'quarantine')
    sgr_full = sorted(os.path.join(dp, n) for dp, dn, fn in os.walk(q) for n in fn
                      if n.lower() == 'graphicsrules.sgr' and 'settings' in dp.lower())
    assert sgr_full, 'the original SGR Full is not in the real SpeedKit quarantine'
    _copy_shared(sgr_full[0], os.path.join(sims, 'ConfigOverride', 'GraphicsRules.sgr'))
    for n in ('MySetters.sgr', 'SimpsSetters.sgr'):
        _copy_shared(os.path.join(REAL_SIMS, 'ConfigOverride', n), os.path.join(sims, 'ConfigOverride', n))
    with open(os.path.join(sims, 'ConfigOverride', 'GraphicsRules.sgr'), encoding='utf-8', errors='replace') as f:
        assert 'Tuned by SpeedKit' not in f.read(), 'the quarantined rules are already tuned'
    for rel in ROOT_COPY:
        _copy_rel(REAL_SIMS, sims, rel)
    for dp, dn, fn in os.walk(sims):
        for n in fn:
            if n.lower() == 'desktop.ini':
                _hide(os.path.join(dp, n))
    # downloads for the Inbox, made from real mods that are not in the fake tree
    dl = os.path.join(SOURCE, 'downloads')
    tmp = os.path.join(SOURCE, 'downloads_tmp')
    os.makedirs(tmp, exist_ok=True)
    for n in ('[Kuttoe] CareerOverhaulSuite.ts4script', '[Kuttoe] CareerOverhaulSuite.package'):
        _copy_shared(os.path.join(REAL_PARKED, 'scripts', n), os.path.join(tmp, n))
    darcy = os.path.join(REAL_PARKED, 'sim', '[BR]DarcyDress.package')
    _cc_subset(darcy, os.path.join(tmp, 'Darcy Dress Recolor.package'), 0, 2)
    _cc_subset(darcy, os.path.join(tmp, 'DarcyDress_Extra.package'), 2, 2)
    _cc_subset(os.path.join(REAL_PARKED, 'sim', 'SkinDetails[MERGED]2.package'),
               os.path.join(tmp, 'SkinDetails_Copy.package'), 0, 3)       # identical to what the tree has
    os.makedirs(dl, exist_ok=True)
    with zipfile.ZipFile(os.path.join(dl, 'CareerOverhaulSuite_v1.5.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(tmp, '[Kuttoe] CareerOverhaulSuite.ts4script'), '[Kuttoe] CareerOverhaulSuite.ts4script')
        z.write(os.path.join(tmp, '[Kuttoe] CareerOverhaulSuite.package'), '[Kuttoe] CareerOverhaulSuite.package')
        z.write(os.path.join(tmp, 'Darcy Dress Recolor.package'), 'Darcy Dress Recolor.package')
        z.writestr('readme.txt', 'Career Overhaul Suite - put both files in Mods, one folder deep at most.')
    with zipfile.ZipFile(os.path.join(dl, 'DarcyDress_Extra.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(tmp, 'DarcyDress_Extra.package'), 'DarcyDress_Extra/DarcyDress_Extra.package')
        z.write(os.path.join(tmp, 'SkinDetails_Copy.package'), 'DarcyDress_Extra/SkinDetails_Copy.package')
    shutil.rmtree(tmp)
    # private copies of the game caches (EA ids and overrides of E:\The Sims 4), and the fake program
    os.makedirs(os.path.join(SOURCE, 'data'), exist_ok=True)
    for n in ('game_ids.sqlite', 'game.sqlite'):
        _sqlite_copy(os.path.join(REAL_DATA, n), os.path.join(SOURCE, 'data', n))
    os.makedirs(os.path.join(SOURCE, 'bin'), exist_ok=True)
    cs = os.path.join(SOURCE, 'bin', 'fake.cs')
    with open(cs, 'w', encoding='utf-8') as f:
        f.write(FAKE_EXE_CS)
    subprocess.run([CSC, '/nologo', '/target:winexe', '/out:' + os.path.join(SOURCE, 'bin', 'fake.exe'), cs],
                   check=True, capture_output=True)
    with open(stamp, 'w', encoding='utf-8') as f:
        json.dump({'build': BUILD, 'built': time.strftime('%Y-%m-%d %H:%M:%S'), 'seconds': round(time.time() - t0)}, f)
    log('source built in %.0f s' % (time.time() - t0))


def fresh_work():
    """work\\ = a fresh copy of source\\ (+ the fake game and Wicked Animator). Returns the paths."""
    _rmtree_e2e(WORK)
    src_sims = os.path.join(SOURCE, 'The Sims 4')
    sims = os.path.join(WORK, 'The Sims 4')
    subprocess.run(['robocopy', src_sims, sims, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:1', '/W:1', '/NFL', '/NDL',
                    '/NJH', '/NJS', '/NP'], capture_output=True)
    shutil.copytree(os.path.join(SOURCE, 'data'), os.path.join(WORK, 'data'))
    shutil.copytree(os.path.join(SOURCE, 'downloads'), os.path.join(WORK, 'downloads'))
    exe = os.path.join(WORK, 'game', 'Game', 'Bin', 'TS4_x64.exe')
    anim = os.path.join(WORK, 'animator', 'Wicked Animator.exe')
    for p in (exe, anim):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        shutil.copy2(os.path.join(SOURCE, 'bin', 'fake.exe'), p)
    shutil.copy2(os.path.join(REAL_GAME, 'Game', 'Bin', 'GraphicsRules.sgr'),
                 os.path.join(WORK, 'game', 'Game', 'Bin', 'GraphicsRules.sgr'))
    dist = os.path.join(WORK, 'dist', 'SpeedKit_Monitor.ts4script')
    os.makedirs(os.path.dirname(dist))
    shutil.copy2(os.path.join(PROJECT, 'dist', 'SpeedKit_Monitor.ts4script'), dist)
    return {'sims': sims, 'exe': exe, 'animator': anim, 'dist': dist, 'data': os.path.join(WORK, 'data')}


# ------------------------------------------------------------------------------------------ inventory
_DIGESTS = {}


def digest(path):
    """blake2b of a file, cached by its NTFS file id, size and mtime (a rename keeps all three)."""
    st = os.stat(path)
    key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    if key not in _DIGESTS:
        h = hashlib.blake2b(digest_size=16)
        with dbpf.open_shared(path) as f:
            for b in iter(lambda: f.read(1 << 22), b''):
                h.update(b)
        _DIGESTS[key] = h.hexdigest()
    return _DIGESTS[key]


def listing(root):
    """{rel ('/' separated): path} of every file below root."""
    out = {}
    if os.path.isdir(root):
        for dp, dn, fn in os.walk(root):
            for n in fn:
                p = os.path.join(dp, n)
                out[os.path.relpath(p, root).replace(os.sep, '/')] = p
    return out


def empty_dirs(root):
    out = set()
    for dp, dn, fn in os.walk(root):
        if not dn and not fn and dp != root:
            out.add(os.path.relpath(dp, root).replace(os.sep, '/'))
    return out


class Snapshot:
    """What matters of the fake Sims folder at one moment."""

    def __init__(self, sims):
        self.sims = sims
        self.mods, self.parked, self.packs, self.other = {}, {}, {}, {}
        for rel, p in listing(os.path.join(sims, 'Mods')).items():
            if '/' not in rel and F.is_speedkit_pack(rel):
                self.packs[rel] = digest(p)
            else:
                self.mods[rel] = digest(p)
        for rel, p in listing(os.path.join(sims, 'Mods_parked')).items():
            if rel.lower() in ('_manifest.json',) or rel.lower().startswith('_old_caches/'):
                continue
            self.parked[rel] = digest(p)
        for area in ('saves', 'Tray', 'ConfigOverride'):
            for rel, p in listing(os.path.join(sims, area)).items():
                st = os.stat(p)
                self.other['%s/%s' % (area, rel)] = (digest(p), st.st_mtime_ns)
        self.empty = {('Mods', d) for d in empty_dirs(os.path.join(sims, 'Mods'))} | \
                     {('Mods_parked', d) for d in empty_dirs(os.path.join(sims, 'Mods_parked'))}

    def files(self):
        """{rel: digest} of every mod file wherever it is (Mods over Mods_parked), and the rels found in both."""
        both = {r.lower() for r in self.mods} & {r.lower() for r in self.parked}
        out = dict(self.parked)
        out.update(self.mods)
        return out, both

    def side(self, rel):
        low = rel.lower()
        if any(r.lower() == low for r in self.mods):
            return 'M'
        if any(r.lower() == low for r in self.parked):
            return 'P'
        return None


def casp_ids(path):
    with dbpf.open_shared(path) as f:
        return {e.i for e in dbpf.read_entries(f) if e.t == U.T_CASP and e.comp != dbpf.DELETED}


class CasView:
    """CAS parts of the fake tree: all (full library), loaded now (what the game loads from Mods, 5 folders
    deep, SpeedKit packs included) and referenced by the saves and Tray."""
    _cache = {}

    def __init__(self, sims, refs_db):
        self.sims = sims
        self.full, self.loaded = set(), set()
        for root, into in (('Mods', (self.full, self.loaded)), ('Mods_parked', (self.full,))):
            for rel, p in listing(os.path.join(sims, root)).items():
                if not rel.lower().endswith('.package') or rel.lower().startswith('_old_caches/'):
                    continue
                pack = '/' not in rel and F.is_speedkit_pack(rel)
                if rel.count('/') > L.MAX_DEPTH:
                    continue
                ids = self._ids(p)
                if root == 'Mods':
                    self.loaded |= ids
                if not pack:
                    self.full |= ids
        refs = U.scan_references(os.path.join(sims, 'saves'), os.path.join(sims, 'Tray'), refs_db, workers=1)
        self.by_source = {}
        for s in refs.selected():
            ids = refs.by_fp[s.fp]
            self.by_source[s.name] = set(ids.get(U.PART, ())) | set(ids.get(U.PART_OTHER, ()))
        self.referenced = set().union(*self.by_source.values()) if self.by_source else set()

    def _ids(self, p):
        st = os.stat(p)
        key = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
        if key not in self._cache:
            self._cache[key] = casp_ids(p)
        return self._cache[key]

    def for_slot(self, slot):
        return self.by_source.get(slot + '.save', set())


# ------------------------------------------------------------------------------------------ safety nets
class Game:
    """The stand-in for 'is TS4_x64.exe running?' in every module that asks."""
    running = False
    MODULES = (L, J, PR, F, U, ST, LA, ingame_install, dedup, merge)

    @classmethod
    def check(cls):
        return cls.running


def _guard_start(orig):
    def start(cmd, cwd):
        exe = cmd[0] if isinstance(cmd, (list, tuple)) else cmd
        if not _under(exe, (WORK,)):
            raise AssertionError('refused to start %s: only the fake programs under %s may run' % (exe, WORK))
        return orig(cmd, cwd)
    return start


def _guard_quietly(orig):
    def start(path):
        if not _under(path, (WORK,)):
            raise AssertionError('refused to start %s' % path)
        return orig(path)
    return start


def _no_url(url):
    raise AssertionError('the test never opens %s (that could start the real game)' % url)


def _no_startfile(*a, **k):
    raise AssertionError('os.startfile(%r) in the e2e test' % (a,))


# ------------------------------------------------------------------------------------------ the Hub over HTTP
class HubClient:
    def __init__(self, port):
        self.base = 'http://127.0.0.1:%d' % port

    def req(self, method, path, body=None, timeout=900):
        data = None if body is None else json.dumps(body).encode()
        r = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            r.add_header('Content-Type', 'application/json')
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def get(self, path):
        code, body = self.req('GET', path)
        assert code == 200, (path, code, body)
        return body

    def post(self, path, body):
        return self.req('POST', path, body)

    def task(self, action, timeout=3600, **args):
        code, r = self.post('/api/task', {'action': action, 'args': args})
        assert code == 200 and r.get('task'), (action, code, r)
        t0 = time.time()
        while True:
            v = self.get('/api/task/' + r['task'])
            if v['state'] != 'running':
                v['result']['_progress'] = v['progress']
                return v['result']
            assert time.time() - t0 < timeout, 'task %s did not finish' % action
            time.sleep(0.25)


INSIDE_WORDS = re.compile(r'(?i)(?<![\w.])(package|packages|quarantine|quarantined|journal|journals|profile|profiles|casp|'
                          r'dedup|manifest|mods_parked|exe|traceback|errno|winerror|configoverride|lod|'
                          r'config\.log)(?![\w])')


def plain_problems(texts):
    """The user-facing texts that use SpeedKit's inside words."""
    return [t for t in texts if isinstance(t, str) and INSIDE_WORDS.search(t)]


# ------------------------------------------------------------------------------------------ the parking list
def mods_switch_full_leaves(sims):
    """Parked files mods_switch.py's 'full' would leave behind, worked out on paper from its own rules
    (entries in order; 'dir/' moves the whole folder; an entry is skipped when Mods has that path)."""
    parked = os.path.join(sims, 'Mods_parked')
    with open(os.path.join(parked, '_manifest.json'), encoding='utf-8') as f:
        moved = json.load(f)['moved']
    p_files = {r.lower(): r for r in listing(parked)
               if r.lower() != '_manifest.json' and not r.lower().startswith('_old_caches/')}
    p_dirs = {r.lower() for r in p_files for r in _ancestors(r)} | {d.lower() for d in empty_dirs(parked)}
    m_paths = set()
    for r in list(listing(os.path.join(sims, 'Mods'))) + sorted(empty_dirs(os.path.join(sims, 'Mods'))):
        m_paths.add(r.lower())
        m_paths.update(_ancestors(r.lower()))
    for e in moved:
        rel = e.rstrip('/').lower()
        is_dir = e.endswith('/')
        src = rel in p_dirs if is_dir else rel in p_files
        if not src or rel in m_paths:
            continue
        if is_dir:
            for k in [k for k in p_files if k.startswith(rel + '/')]:
                del p_files[k]
                m_paths.add(k)
                m_paths.update(_ancestors(k))
            p_dirs = {d for d in p_dirs if d != rel and not d.startswith(rel + '/')}
            m_paths.add(rel)
        else:
            del p_files[rel]
            m_paths.add(rel)
            m_paths.update(_ancestors(rel))
    return sorted(p_files.values())


def _ancestors(rel):
    parts = rel.split('/')
    return ['/'.join(parts[:n]) for n in range(1, len(parts))]


# ------------------------------------------------------------------------------------------ what the game uses
def effective_content(sims, db_path):
    """{(t, g, i): (raw digest, path, entry)} of the copy the game uses when everything is in Mods."""
    lib = L.Library(db_path=db_path, roots={'Mods': os.path.join(sims, 'Mods')})
    try:
        lib.scan()
        order = lib.load_order(('Mods',))
        paths = [lib.path(r, rel) for r, rel in order]
    finally:
        lib.close()
    out = {}
    for p in paths:
        with dbpf.Package(p) as pkg:
            for e in pkg.entries:
                k = (e.t, e.g, e.i)
                if e.comp == dbpf.DELETED or k in out:
                    continue
                out[k] = (hashlib.blake2b(pkg.raw(e), digest_size=16).hexdigest(), p, e)
    return out


def same_content(a, b):
    if a[0] == b[0]:
        return True
    try:
        with dbpf.Package(a[1]) as pa, dbpf.Package(b[1]) as pb:
            return pa.read(a[2]) == pb.read(b[2])
    except FileNotFoundError:
        return False


# ------------------------------------------------------------------------------------------ Chrome
def chrome_page(url, png, size=(1440, 1100), budget=15000):
    """(visible text, console errors) of one Hub page; a screenshot goes to png."""
    import tempfile
    prof = tempfile.mkdtemp(prefix='e2e_chrome_')
    try:
        args = [CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                '--no-default-browser-check', '--disable-extensions', '--mute-audio', '--user-data-dir=' + prof,
                '--window-size=%d,%d' % size, '--virtual-time-budget=%d' % budget, '--enable-logging=stderr', '--v=0',
                '--proxy-server=http://127.0.0.1:9', '--dump-dom', '--screenshot=' + png, url]
        p = subprocess.run(args, capture_output=True, timeout=300)
        dom, err = p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    text = re.sub(r'<script.*?</script>', ' ', dom, flags=re.S)
    # elements the page hides (the "Example data" / "game running" chips, the tooltip): not shown, not read
    text = re.sub(r'<(span|div)\b[^>]*\bclass="[^"]*\bhidden\b[^"]*"[^>]*>.*?</\1>', ' ', text, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text.replace('&amp;', '&').replace('&#39;', "'").replace('&quot;', '"')
                  .replace('&lt;', '<').replace('&gt;', '>'))
    errors = [ln for ln in err.splitlines() if 'CONSOLE' in ln and re.search(r'Uncaught|TypeError|ReferenceError', ln)]
    return text, errors


# ------------------------------------------------------------------------------------------ the story
def _log(msg):
    line = '%s  %s' % (time.strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    try:
        with open(os.path.join(E2E, 'e2e_log.txt'), 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


class PlainWords(unittest.TestCase):
    """What the audit fixed in the words the Hub shows (quick; no fake tree needed)."""

    NOTES = [
        'MySetters.sgr is in ConfigOverride but is not loaded by the active rules.',
        'SGR Full turns off Sim LOD, object LOD bias and small-object culling. SpeedKit Max Quality '
        '(graphics_use_tuned) keeps its look and brings only the lag-causing values back to high-end values; the '
        'stock rules (graphics_use_stock) cull the most.',
        'graphics_use_tuned would install SpeedKit Max Quality (made from C:\\x\\GraphicsRules.sgr).',
        '42 options of the stock rules are not defined by the override (the game still falls back to working '
        'values for them).',
        'The rules changed after the last game start; Config.log will confirm them next launch.',
        "Config.log starts with 'a', not what these rules log first ('b').",
        "SpeedKit Max Quality is active: SGR Full's look with only the lag-causing values tuned (Sim LOD 2x stock, "
        "stock culling, object LOD and far clip, FSAA 8, shadows and mirrors at most 2x stock).",
        "The SpeedKit Max Quality file was edited: RenderSimLODDistances is above SpeedKit's values again "
        "(graphics_use_tuned puts them back).",
        'Config.log confirms the game loaded SpeedKit Max Quality at its last start.',
        'SpeedKit Max Quality was installed (journal 20260924-073215-settings), but ConfigOverride\\GraphicsRules.sgr '
        'has been replaced since: the game now uses X.',
        'SpeedKit Max Quality: ConfigOverride\\GraphicsRules.sgr is Simp4Sims Setters, not SGR Full. SpeedKit leaves '
        'your own rules file alone (replace_other=True would replace it; it would be kept in quarantine).',
        'These Setters still keep Sims at full detail out to 9000 m; only the stock rules switch Sims to simpler '
        'models with distance.',
    ]

    def test_graphics_details(self):
        shown = [api._plain_detail(n) for n in self.NOTES]
        self.assertEqual(plain_problems([s for s in shown if s]), [])
        for bad in ('ConfigOverride', 'LOD', 'stock rules', 'override', 'journal', 'graphics_use', 'Config.log', '.sgr'):
            self.assertFalse([s for s in shown if s and bad in s], bad)
        self.assertIn('SpeedKit Max Quality can be switched on: the same sharp look, without the lag.', shown)
        self.assertIn('These settings keep sims in full detail up to 9000 m away.', shown)
        self.assertIsNone(shown[0])

    def test_graphics_values(self):
        for raw, want in (('120.0f', '120'), ('1.3f', '1.3'), ('0.6666', '0.6666'), ('0.00', '0.00'),
                          ('2999.97, 2999.98, 2999.99, 3000', '2999.97, 2999.98, 2999.99, 3000'), (8, '8'),
                          ('0.1, 0.42, 9999, 9999', '0.1, 0.42, 9999, 9999'), (None, None)):
            self.assertEqual(api._plain_value(raw), want, raw)

    def test_sizes(self):
        self.assertEqual(api._size_text(0), 'less than 1 MB')
        self.assertEqual(api._size_text(35_400_000), '35 MB')
        self.assertEqual(api._size_text(2_400_000_000), '2.4 GB')

    def test_report_words(self):
        from speedkit import report
        st = {'library': {'packages': 81, 'gb': 1.6, 'cas_full': 14100, 'cas_fast': 859},
              'profile': {'name': 'save', 'label': "Play this save - only the CC of 'X'"},
              'graphics': {'label': 'SpeedKit Max Quality - sharp graphics without the lag'},
              'memory': {'free_gb': 4.8, 'total_gb': 15.3, 'warnings': [], 'top': []},
              'fastpack': {'state': 'stale', 'gb': 0.3}, 'disk': {'c_free_gb': 44},
              'load_times': [{'time': '2026-09-24T08:00:00', 'event': 'main_menu', 'profile': 'lean',
                              'launch_to_menu_s': 100, 'lot_load_s': None}],
              'journals': [{'when': '2026-09-24T08:00:00', 'kind': 'profile', 'state': 'committed',
                            'note': 'switch to fast: park 5 files (0.7 GB), restore 0 files (0.0 GB)',
                            'title': 'Switched to Fast mode'}]}
        saves = [{'slot': 'Slot_00000016', 'name': 'My Saved Game 21', 'pack': {'state': 'fresh'}}]
        table = [{'setting': 'Mirror fade distance', 'stock': '1.3', 'before': '120', 'after': '2.6'}]
        html = report.build(st, saves, table)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<style>.*?</style>', ' ', html, flags=re.S)))
        self.assertEqual(plain_problems([text]), [], INSIDE_WORDS.findall(text))
        for want in ('Switched to Fast mode', 'Done', 'Studio mode', 'Main menu', 'One save', 'ready'):
            self.assertIn(want, text)
        self.assertNotIn('committed', text)
        self.assertNotIn('park 5 files', text)

    def test_preflight_names_the_mods_drive_only_when_it_is_c(self):
        from collections import namedtuple
        du = namedtuple('du', 'total used free')
        low = lambda d: du(1000 * 2 ** 30, 990 * 2 ** 30, 10 * 2 ** 30)          # noqa: E731
        with mock.patch.object(ST.shutil, 'disk_usage', low):
            on_e = ST.preflight(sims=os.path.join(E2E, 'nowhere', 'The Sims 4'), processes=False,
                                game_bin=os.path.join(E2E, 'nowhere', 'Game', 'Bin'))['warnings']
            on_c = ST.preflight(sims=r'C:\nowhere\The Sims 4', processes=False,
                                game_bin=os.path.join(E2E, 'nowhere', 'Game', 'Bin'))['warnings']
        self.assertTrue([w for w in on_e if w.startswith('C: has only') and 'Mods folder' not in w], on_e)
        self.assertTrue([w for w in on_c if w.startswith('C: has only') and 'Mods folder' in w], on_c)
        self.assertEqual(plain_problems(on_e + on_c), [])


@unittest.skipUnless(os.name == 'nt' and os.path.isdir('E:\\'), 'needs drive E:')
class RememberedCleanupHome(unittest.TestCase):
    """A clean-up whose safe copies went to another drive stays undoable after the Hub restarts."""

    def setUp(self):
        self.base = os.path.join(E2E, 'remembered')
        _rmtree_e2e(self.base)
        self.sims = os.path.join(self.base, 'The Sims 4')
        os.makedirs(os.path.join(self.sims, 'Mods'))
        self.other = os.path.join(self.base, 'OtherDrive', 'SpeedKit Quarantine')
        self.config = dict(sims=self.sims, check_game=False, db_path=os.path.join(self.base, 'lib.sqlite'),
                           game={'exe': os.path.join(self.base, 'TS4_x64.exe'), 'game_dir': self.base,
                                 'store': 'unknown', 'source': 'test'}, processes=False, opener=lambda p: None)
        api.reset()
        api.configure(**self.config)

    def tearDown(self):
        api.reset()
        _rmtree_e2e(self.base)

    def test_found_again_after_a_restart(self):
        victim = os.path.join(self.sims, 'Mods', 'copy.package')
        with open(victim, 'wb') as f:
            f.write(b'DBPF' + b'\0' * 92)
        with J.Journal('dedup', 'identical policy: 1 packages', home=self.other, sims=self.sims, check_game=False) as j:
            j.quarantine(victim)
        api._remember('cleanup_homes', [self.other])
        api.reset()                                                  # the Hub was closed and opened again
        api.configure(**self.config)
        js = api.status()['journals']
        self.assertEqual([(x['title'], x['next_undo']) for x in js], [('Removed duplicate copies', True)])
        r = api.undo_last()
        self.assertTrue(r['ok'], r)
        self.assertTrue(os.path.isfile(victim))


CC_SENTENCE = {'full': 'Everything is loaded.', 'fast': 'Only what your sims and lots need.',
               'save': 'Only what this save needs.',
               'studio': 'Only WickedWhims and your animations - for animation work.',
               'custom': 'Changed by hand or by another tool.'}


@unittest.skipUnless(available(), 'needs the user\'s Sims 4 folder, E:\\The Sims 4 and drive E:')
class Story(unittest.TestCase):
    """The whole Hub, one ordered story on the fake tree (see the module docstring)."""

    @classmethod
    def setUpClass(cls):
        os.makedirs(E2E, exist_ok=True)
        log = os.path.join(E2E, 'e2e_log.txt')
        if os.path.exists(log):
            try:
                shutil.copyfile(log, os.path.join(E2E, 'e2e_log_prev.txt'))
                open(log, 'w').close()
            except OSError:
                pass
        _rmtree_e2e(SCREENS)
        build_source(_log)
        cls.w = fresh_work()
        cls.sims = cls.w['sims']
        cls.home = os.path.join(cls.sims, 'SpeedKit')
        d = cls.w['data']
        cls.opened = []
        cls.config = dict(
            sims=cls.sims, db_path=os.path.join(d, 'library.sqlite'), refs_db=os.path.join(d, 'refs.sqlite'),
            game_ids_db=os.path.join(d, 'game_ids.sqlite'), game_db=os.path.join(d, 'game.sqlite'),
            companions_cache=os.path.join(d, 'companions.sqlite'), hash_cache=os.path.join(d, 'hash.sqlite'),
            bc_cache=os.path.join(d, 'plan_bc.json.gz'),
            game={'exe': cls.w['exe'], 'game_dir': REAL_GAME, 'store': 'ea', 'source': 'e2e test'},
            game_clues=None, remember_game=False, check_game=True, scan_workers=1, verdicts=None,
            dist=cls.w['dist'], build_monitor=False, animator=None, opener=cls.opened.append, cleanup_home=None)
        cls.test_refs_db = os.path.join(d, 'test_refs.sqlite')           # the test's own reading of the saves
        cls.patches = [mock.patch.object(m, 'game_running', Game.check) for m in Game.MODULES]
        cls.patches += [mock.patch.object(LA, '_start_detached', _guard_start(LA._start_detached)),
                        mock.patch.object(LA, '_open_url', _no_url),
                        mock.patch.object(api, '_start_quietly', _guard_quietly(api._start_quietly)),
                        mock.patch.object(os, 'startfile', _no_startfile, create=True),
                        mock.patch.object(api, 'ANIMATOR_EXE', cls.w['animator']),
                        mock.patch.object(api, 'ANIMATOR_BAT', os.path.join(WORK, 'animator', 'none.bat'))]
        for p in cls.patches:
            p.start()
        Game.running = False
        api.reset()
        api.configure(**cls.config)
        cls.httpd = server.make_server(0, api=api, mode='engine', opener=lambda p: {'ok': True, 'message': 'opened'},
                                       log_path=os.path.join(WORK, 'hub.log'))
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.hub = HubClient(cls.httpd.port)
        cls.start = Snapshot(cls.sims)
        cls.expected, _ = cls.start.files()
        cls.start_manifest = cls.manifest()
        cls.start_empty = cls.start.empty
        cls.sgr_original = cls.start.other['ConfigOverride/GraphicsRules.sgr'][0]
        cls.sgr_tuned = None
        cls.companions = {s: list(cs) for s, cs in SCRIPT_COMPANIONS.items()}
        cls.findings = []
        cls.numbers = {}
        cls.mode = 'studio'
        _log('work tree ready: %d mod files in Mods, %d parked' % (len(cls.start.mods), len(cls.start.parked)))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.httpd.shutdown()
            cls.httpd.server_close()
        finally:
            for p in reversed(cls.patches):
                p.stop()
            api.reset()
            Game.running = False
            for proc in list(LA._LAUNCHED) + list(api._STARTED):     # the fake programs exit at once; reap them
                try:
                    proc.wait(timeout=10)
                except Exception:
                    pass
            _log('numbers: %s' % json.dumps(cls.numbers, default=str))

    # ------------------------------------------------------------------ helpers
    @classmethod
    def manifest(cls):
        with open(os.path.join(cls.sims, 'Mods_parked', '_manifest.json'), encoding='utf-8') as f:
            return json.load(f)

    def journals(self):
        return J.list_journals(self.home)

    def status(self):
        return self.hub.get('/api/status?refresh=1')

    def task(self, action, **args):
        t0 = time.time()
        r = self.hub.task(action, **args)
        _log('%s %s -> ok=%s %s (%.0f s)' % (action, args or '', r.get('ok'), r.get('message'), time.time() - t0))
        for s in r.get('steps') or []:
            _log('    [%s%s] %s: %s' % ('ok' if s['ok'] else 'FAIL', ', warn' if s.get('warn') else '', s['step'],
                                       s['message']))
        return r

    def assert_plain(self, texts, where):
        bad = plain_problems(texts)
        self.assertEqual(bad, [], '%s: inside words shown to the user' % where)

    def listing_state(self):
        """Cheap state of the whole fake Sims folder: every path with its size and mtime."""
        out = {}
        for rel, p in listing(self.sims).items():
            st = os.stat(p)
            out[rel] = (st.st_size, st.st_mtime_ns)
        return out

    # ------------------------------------------------------------------ the checks after every step
    def check_all(self, label, mode, slot=None, cas=True, refusals=True):
        t0 = time.time()
        snap = Snapshot(self.sims)
        files, both = snap.files()
        # 1. no mod file lost, changed or duplicated
        missing = sorted(set(self.expected) - set(files))
        extra = sorted(set(files) - set(self.expected))
        changed = sorted(r for r in set(files) & set(self.expected) if files[r] != self.expected[r])
        self.assertEqual((missing, extra, changed, sorted(both)), ([], [], [], []),
                         '%s: mod files lost / new / changed / in both places' % label)
        # 2. .ts4script contents untouched
        for rel, d in files.items():
            if rel.lower().endswith('.ts4script') and rel in self.start.mods.keys() | self.start.parked.keys():
                self.assertEqual(d, self.expected[rel], '%s: %s changed' % (label, rel))
        # 3. scripts at most one folder deep in Mods, together with their companions
        for rel in snap.mods:
            if rel.lower().endswith('.ts4script'):
                self.assertLessEqual(rel.count('/'), 1, '%s: %s is too deep to load' % (label, rel))
        for s, cs in self.companions.items():
            for c in cs:
                self.assertEqual(snap.side(c), snap.side(s), '%s: %s and its script %s are apart' % (label, c, s))
        # 4. saves, Tray and saves\FitStudio untouched; the graphics file is the original or SpeedKit's
        for k, v in self.start.other.items():
            if k == 'ConfigOverride/GraphicsRules.sgr':
                self.assertIn(snap.other.get(k, (None,))[0], {self.sgr_original, self.sgr_tuned}, label)
            else:
                self.assertEqual(snap.other.get(k), v, '%s: %s changed' % (label, k))
        self.assertEqual({k for k in snap.other if not k.startswith('ConfigOverride/')},
                         {k for k in self.start.other if not k.startswith('ConfigOverride/')}, label)
        # 5. the parking list: SpeedKit's check and mods_switch.py's 'full' on paper; no empty folder lost
        chk = PR.check_manifest(self.sims)
        self.assertTrue(chk['ok'], '%s: parking list %s' % (label, {k: chk[k] for k in ('unlisted', 'blocked', 'nested')}))
        self.assertEqual(mods_switch_full_leaves(self.sims), [], '%s: mods_switch.py full would leave these' % label)
        now_empty = {d.lower() for _, d in snap.empty}
        for side, d in self.start_empty:
            self.assertIn(d.lower(), now_empty, '%s: the empty folder %s is gone' % (label, d))
        # 6. SpeedKit's packs: only the mode's own at the Mods root
        packs = sorted(snap.packs)
        if mode == 'fast':
            self.assertTrue(packs and all(p.lower().startswith('!!!!!speedkit_fast_') for p in packs), (label, packs))
        elif mode == 'save':
            want = '!!!!!speedkit_save_%s_' % slot[5:].lower()
            self.assertTrue(packs and all(p.lower().startswith(want) for p in packs), (label, packs))
        else:
            self.assertEqual(packs, [], label)
        # 7. CAS parts: the mode loads far fewer than full, and every one the saves wear that is installed
        if cas:
            cv = CasView(self.sims, self.test_refs_db)
            need = (cv.for_slot(slot) if mode == 'save' else cv.referenced) & cv.full
            self.numbers[label] = {'cas_full': len(cv.full), 'cas_loaded': len(cv.loaded), 'worn_installed': len(need),
                                   'referenced': len(cv.referenced if mode != 'save' else cv.for_slot(slot))}
            if mode in ('fast', 'save'):
                self.assertEqual(sorted('%016X' % i for i in need - cv.loaded), [],
                                 '%s: CAS parts the saves wear are not loaded' % label)
                self.assertLess(len(cv.loaded), 0.25 * len(cv.full), '%s: not far fewer CAS parts than full' % label)
            elif mode == 'full':
                self.assertEqual(cv.loaded, cv.full, label)
        # 8. what the Hub says
        st = self.status()
        self.assertTrue(st['ok'], st)
        self.assertEqual(st['profile']['name'], mode, '%s: the Hub says %s' % (label, st['profile']))
        if mode == 'save':
            self.assertEqual(st['profile']['save_slot'], slot)
        self.assertNotIn('problems', st, st.get('problems'))
        self.assert_plain([st['profile']['label'], st['fastpack']['why'], st['graphics']['label'], st['game']['message']]
                          + st['graphics']['details'] + st['memory']['warnings'] + [j['title'] for j in st['journals']],
                          label + ' status')
        self.assertLessEqual(sum(1 for j in st['journals'] if j['next_undo']), 1)
        # 9. the game running: every change is refused and nothing moves
        if refusals:
            self.check_refusals(label)
        _log('checked %s (%s%s) in %.0f s' % (label, mode, ' ' + slot if slot else '', time.time() - t0))
        return snap, st

    def check_refusals(self, label):
        before, jbefore = self.listing_state(), self.journals()
        Game.running = True
        try:
            st = self.status()
            self.assertTrue(st['game_running'])
            for action, args in (('play', {'target': 'fast'}), ('prepare', {'target': 'full'}),
                                 ('play', {'target': 'save:' + SLOTS[0]}), ('undo_last', {}), ('inbox', {'apply': True}),
                                 ('cleanup_apply', {}), ('graphics_tune', {'apply': True}),
                                 ('graphics_restore', {'apply': True})):
                r = self.hub.task(action, **args)
                self.assertFalse(r['ok'], '%s: %s ran while the game runs: %s' % (label, action, r))
                self.assertRegex(r['message'], r'(running|Close it first|close it first)', (label, action, r['message']))
                if action in ('play', 'prepare'):
                    self.assertFalse(r['launched'])
        finally:
            Game.running = False
        self.assertEqual(self.listing_state(), before, '%s: something changed while the game ran' % label)
        self.assertEqual(self.journals(), jbefore, label)

    # ------------------------------------------------------------------ the Hub's pages in Chrome
    def screens(self, tag, pages=('home', 'saves', 'library', 'performance', 'tools'), must=None):
        """Screenshot pages of the Hub (real engine, fake tree) and check their words. Returns {page: text}."""
        if not os.path.isfile(CHROME):
            return {}
        os.makedirs(SCREENS, exist_ok=True)
        for path in ('/api/status', '/api/saves', '/api/graphics', '/api/inbox'):   # warm the Hub's caches
            self.hub.get(path)
        out = {}

        def one(page):
            png = os.path.join(SCREENS, '%s_%s.png' % (tag, page))
            text, errors = chrome_page(self.hub.base + '/#' + page, png, size=(1440, 1500 if page != 'home' else 1100))
            with open(png[:-4] + '.txt', 'w', encoding='utf-8') as f:
                f.write(text)
            return page, text, errors
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(3) as ex:
            for page, text, errors in ex.map(one, pages):
                out[page] = text
                self.assertEqual(errors, [], '%s %s: script errors' % (tag, page))
                self.assertNotIn('Example data', text, 'the Hub shows the stand-in, not the engine')
                self.assertEqual(plain_problems([text]), [], '%s %s: inside words: %s' % (
                    tag, page, INSIDE_WORDS.findall(text)))
                for m in (must or {}).get(page, ()):
                    self.assertIn(m, text, '%s %s should show %r' % (tag, page, m))
        return out

    # ------------------------------------------------------------------ the story
    def test_01_status(self):
        st = self.status()
        self.assertEqual((st['hub']['engine'], st['hub']['preview']), ('engine', False))
        self.assertEqual(st['profile']['name'], 'studio')
        self.assertEqual((st['graphics']['state'], st['graphics']['can_tune']), ('sgr_full', True), st['graphics'])
        self.assertEqual(st['fastpack']['state'], 'missing')
        self.assertTrue(st['monitor']['installed'])
        self.assertTrue(st['game']['found'])
        self.assertFalse(st['game_running'])
        self.assertEqual(st['inbox'], {'path': os.path.join(self.home, 'Inbox'), 'waiting': 0})
        self.assertEqual(st['animator'], {'installed': True, 'path': self.w['animator']})
        self.check_all('1 status', 'studio')
        self.screens('01_start', must={'home': ['Ready to play?', 'Play FAST', 'Play with ALL CC', 'Studio mode',
                                                CC_SENTENCE['studio']],
                                       'tools': ['Recent changes', "Open Novulon's Wicked Animator", REAL_GAME]})

    def test_02_list_saves(self):
        r = self.hub.get('/api/saves?refresh=1')
        self.assertTrue(r['ok'], r)
        by = {s['slot']: s for s in r['saves']}
        self.assertEqual(sorted(by), sorted(SLOTS))            # no .ver backup, nothing from saves\FitStudio
        for s in by.values():
            self.assertTrue(s['name'] and s['name'] != s['slot'], s)
            self.assertGreater(s['sims'], 0)
            self.assertIsInstance(s['cc_parts'], int)
            self.assertEqual(s['pack']['state'], 'missing')
            self.assertNotIn('problem', s)
        self.numbers['saves'] = {k: {f: v[f] for f in ('name', 'household', 'world', 'sims', 'lots', 'cc_parts',
                                                        'cc_missing', 'cas_loaded')} for k, v in by.items()}
        self.__class__.save_names = {k: v['name'] for k, v in by.items()}
        self.check_all('2 list_saves', 'studio', cas=False)

    def _marker_lines(self, exe):
        p = os.path.join(os.path.dirname(exe), 'launched.txt')
        try:
            with open(p, encoding='utf-8') as f:
                return len(f.read().splitlines())
        except OSError:
            return 0

    def _wait_marker(self, exe, before):
        for _ in range(100):
            if self._marker_lines(exe) > before:
                return True
            time.sleep(0.1)
        return False

    def _play(self, target, launch=True):
        before = self._marker_lines(self.w['exe'])
        r = self.task('play' if launch else 'prepare', target=target)
        self.assertTrue(r['ok'], r)
        self.assertEqual(r['launched'], launch, r)
        self.assertTrue(all(s['ok'] for s in r['steps']), r['steps'])
        self.assert_plain([r['message']] + [s['message'] for s in r['steps']] +
                          [e['message'] for e in r['_progress']], 'play ' + target)
        if launch:
            self.assertTrue(self._wait_marker(self.w['exe'], before), 'the fake game did not start')
            with open(os.path.join(self.home, 'launch_time.json'), encoding='utf-8') as f:
                lt = json.load(f)
            self.assertEqual(os.path.normcase(lt['exe']), os.path.normcase(self.w['exe']))
        return r

    def test_03_play_fast(self):
        r = self._play('fast')
        steps = [s['step'] for s in r['steps']]
        for want in ('library', 'monitor', 'graphics', 'pack', 'mods', 'memory', 'launch'):
            self.assertIn(want, steps)
        with open(os.path.join(self.sims, 'ConfigOverride', 'GraphicsRules.sgr'), encoding='utf-8', errors='replace') as f:
            self.assertIn('Tuned by SpeedKit', f.read())
        self.__class__.sgr_tuned = digest(os.path.join(self.sims, 'ConfigOverride', 'GraphicsRules.sgr'))
        snap, st = self.check_all('3 play fast', 'fast')
        self.assertEqual(st['graphics']['state'], 'tuned')
        self.assertEqual(st['fastpack']['state'], 'fresh', st['fastpack'])
        titles = [j['title'] for j in st['journals']]
        for t in ('Switched to Fast mode', 'Made the fast pack', 'Graphics set to Max Quality'):
            self.assertIn(t, titles)
        self.assertEqual(st['library']['cas_now'], self.cas_entries_in_mods())
        self.assertLess(st['library']['cas_now'], st['library']['cas_full'])
        self.screens('03_fast', ('home', 'saves', 'performance'),
                     must={'home': [CC_SENTENCE['fast'], 'Play FAST', 'Max Quality, lag fixed'],
                           'saves': list(self.save_names.values())})

    def cas_entries_in_mods(self):
        n = 0
        for rel, p in listing(os.path.join(self.sims, 'Mods')).items():
            if rel.lower().endswith('.package') and rel.count('/') <= L.MAX_DEPTH:
                with dbpf.open_shared(p) as f:
                    n += sum(1 for e in dbpf.read_entries(f) if e.t == U.T_CASP and e.comp != dbpf.DELETED)
        return n

    def test_04_play_save(self):
        slot = SLOTS[0]
        self._play('save:' + slot)
        snap, st = self.check_all('4 play save', 'save', slot)
        self.assertIn(self.save_names[slot], st['profile']['label'])
        state = PR.read_state(self.sims)
        self.assertEqual((state['profile'], state['save_slot']), ('save', slot))
        self.assertTrue(any(n.lower().startswith('!!!!!speedkit_fast_') for n in os.listdir(os.path.join(self.home, 'fastpack'))))
        by = {s['slot']: s for s in self.hub.get('/api/saves?refresh=1')['saves']}
        self.assertEqual(by[slot]['pack']['state'], 'fresh')
        self.assertIsInstance(by[slot]['cas_loaded'], int)
        self.assertEqual(st['library']['cas_now'], self.cas_entries_in_mods())
        self.screens('04_save', ('home', 'saves'), must={'home': [CC_SENTENCE['save'], self.save_names[slot]]})

    def test_05_play_full(self):
        self._play('full')
        snap, st = self.check_all('5 play full', 'full')
        self.assertEqual(snap.parked, {})
        self.assertEqual(self.manifest()['moved'], [])
        self.screens('05_full', ('home',), must={'home': [CC_SENTENCE['full']]})

    def test_06_play_studio(self):
        self._play('studio')
        snap, st = self.check_all('6 play studio', 'studio')
        self.assertEqual(set(snap.mods), set(self.start.mods), 'studio is not the studio set it started with')
        self.screens('06_studio', ('home',), must={'home': [CC_SENTENCE['studio']]})

    def mods_switch(self):
        spec = importlib.util.spec_from_file_location('e2e_mods_switch', MODS_SWITCH)
        ms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ms)
        ms.SIMS = self.sims
        ms.MODS = os.path.join(self.sims, 'Mods')
        ms.PARKED = os.path.join(self.sims, 'Mods_parked')
        ms.MANIFEST = os.path.join(ms.PARKED, '_manifest.json')
        for name in ('SIMS', 'MODS', 'PARKED', 'MANIFEST'):
            self.assertTrue(_under(getattr(ms, name), (WORK,)), name)
        return ms

    def test_07_mods_switch(self):
        import io
        ms = self.mods_switch()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ms.full()
        _log('mods_switch full: ' + out.getvalue().strip())
        snap, st = self.check_all('7a mods_switch full', 'full')
        self.assertEqual(snap.parked, {})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ms.lean()
        _log('mods_switch lean: ' + out.getvalue().strip())
        snap, st = self.check_all('7b mods_switch lean', 'studio')
        self.assertEqual(snap.side('SpeedKit_Monitor.ts4script'), 'P')        # lean parks what KEEP does not list
        self.assertFalse(st['monitor']['installed'])
        self.__class__.after_lean = snap          # what SpeedKit's undo can go back to (it cannot undo mods_switch)
        # the studio switch before it can no longer be undone (the other tool rewrote the parking list): the
        # Hub must not offer it as the next undo
        nxt = [j for j in st['journals'] if j['next_undo']]
        self.assertFalse(nxt and nxt[0]['title'] == 'Switched to Studio', nxt)

    def test_08_play_fast_again(self):
        packs_before = [j for j in self.journals() if j[1] == 'fastpack']
        r = self._play('fast')
        snap, st = self.check_all('8 play fast again', 'fast')
        self.assertEqual(snap.side('SpeedKit_Monitor.ts4script'), 'M')
        self.assertTrue(st['monitor']['installed'])
        rebuilt = [j for j in self.journals() if j[1] == 'fastpack' and j not in packs_before]
        self.numbers['8 fast pack rebuilt or updated'] = [j[4] for j in rebuilt]

    def test_09_inbox(self):
        inbox = os.path.join(self.home, 'Inbox')
        os.makedirs(inbox, exist_ok=True)
        zips = sorted(os.listdir(os.path.join(WORK, 'downloads')))
        for n in zips:
            shutil.copy2(os.path.join(WORK, 'downloads', n), os.path.join(inbox, n))
        self.assertEqual(self.status()['inbox']['waiting'], len(zips))
        prev = self.hub.get('/api/inbox?refresh=1')
        self.assertTrue(prev['ok'], prev)
        self.assertEqual(sorted(i['name'] for i in prev['items']), zips)
        self.assertTrue(all(i['status'] not in ('refused', 'skipped') for i in prev['items']), prev['items'])
        self.assert_plain([prev['message']] + [i['reason'] for i in prev['items']], 'inbox preview')
        why = {i['name']: i['reason'] for i in prev['items']}
        self.assertEqual(why['CareerOverhaulSuite_v1.5.zip'],
                         'A script mod (3 files): it goes into its own folder in Mods, untouched.')
        self.assertEqual(why['DarcyDress_Extra.zip'], '1 new CC file, 1 already in your game.')
        before = Snapshot(self.sims).files()[0]
        r = self.task('inbox', apply=True)
        self.assertTrue(r['ok'], r)
        self.assertEqual([i['status'] for i in r['items']], ['done'] * len(zips), r['items'])
        self.assert_plain([r['message']] + [i['reason'] for i in r['items']] + r['warnings'], 'inbox')
        after = Snapshot(self.sims).files()[0]
        new = {rel: d for rel, d in after.items() if rel not in before}
        self.assertEqual({rel for rel in before if rel not in after}, set(), 'the Inbox removed mod files')
        _log('inbox added: %s' % sorted(new))
        # the script mod and its companions: one folder deep, together, bit-exact from the zip
        with zipfile.ZipFile(os.path.join(WORK, 'downloads', 'CareerOverhaulSuite_v1.5.zip')) as z:
            members = {m.filename: hashlib.blake2b(z.read(m), digest_size=16).hexdigest() for m in z.infolist()
                       if m.filename.endswith(('.ts4script', '.package'))}
        script = [rel for rel in new if rel.endswith('CareerOverhaulSuite.ts4script')]
        self.assertEqual(len(script), 1, new)
        folder = script[0].rsplit('/', 1)[0] if '/' in script[0] else ''
        self.assertEqual(script[0].count('/'), 1, script)
        for name, d in members.items():
            self.assertEqual(new.get(folder + '/' + name), d, '%s is not next to its script, bit-exact' % name)
        self.companions[script[0]] = [folder + '/' + n for n in members if n.endswith('.package')]
        # the CC-only download: merged (its copy of CC the library already has is not added twice)
        merged = [rel for rel in new if rel.lower().startswith('speedkit merged/')]
        self.assertTrue(merged, new)
        self.assertFalse(any('SkinDetails_Copy' in rel for rel in new), new)
        self.assertEqual(sorted(os.listdir(inbox)), ['_done'])
        self.expected.update(new)
        self.check_all('9 inbox', 'fast')

    def test_10_cleanup(self):
        r = self.task('cleanup_plan')
        self.assertFalse(r['ok'])
        self.assertIn('All CC', r['message'])
        self._play('full', launch=False)
        self.check_all('10a prepare full', 'full', refusals=False)
        eff_db = os.path.join(self.w['data'], 'effective.sqlite')
        eff_before = effective_content(self.sims, eff_db)
        r = self.task('cleanup_plan')
        self.assertTrue(r['ok'], r)
        self.assertGreater(r['copies'], 0, r)
        self.assert_plain([r['message']], 'cleanup plan')
        self.assertNotIn('0.0 GB', r['message'])                 # small amounts are said in MB
        self.assertIsInstance(r['mb'], float)
        before = Snapshot(self.sims).files()[0]
        r2 = self.task('cleanup_apply')
        self.assertTrue(r2['ok'], r2)
        self.assert_plain([r2['message']], 'cleanup apply')
        after = Snapshot(self.sims).files()[0]
        gone = sorted(set(before) - set(after))
        changed = sorted(rel for rel in set(before) & set(after) if before[rel] != after[rel])
        self.assertEqual(sorted(set(after) - set(before)), [])
        _log('clean-up: %d copies, %s GB; removed %s; rewritten %s' % (r['copies'], r['gb'], gone, changed))
        self.numbers['10 cleanup'] = {'copies': r['copies'], 'gb': r['gb'], 'removed': gone, 'rewritten': changed}
        protected = {c for cs in self.companions.values() for c in cs} | set(self.companions)
        self.assertEqual([rel for rel in gone + changed if rel.lower().endswith('.ts4script')], [])
        self.assertEqual([rel for rel in gone + changed if rel in protected], [], 'the clean-up touched a companion')
        eff_after = effective_content(self.sims, eff_db)
        lost = [k for k in eff_before if k not in eff_after]
        differ = [k for k in eff_before if k in eff_after and not same_content(eff_before[k], eff_after[k])]
        self.assertEqual((lost[:5], differ[:5]), ([], []), 'the game would see different content')
        self.__class__.expected = after
        self.check_all('10b cleanup', 'full')

    def test_11_graphics(self):
        g = self.hub.get('/api/graphics?refresh=1')
        self.assertTrue(g['ok'], g)
        self.assertIn('already on', g['message'])
        self.assertTrue(g['table'])
        self.assert_plain([g['message']] + [r['setting'] for r in g['table']], 'graphics table')
        r = self.task('graphics_restore', apply=True)
        self.assertTrue(r['ok'], r)
        self.assertEqual(digest(os.path.join(self.sims, 'ConfigOverride', 'GraphicsRules.sgr')), self.sgr_original)
        st = self.status()
        self.assertEqual((st['graphics']['state'], st['graphics']['can_tune']), ('sgr_full', True))
        self.assertEqual(api._graphics_choice(), api.GRAPHICS_KEEP)       # Play will not tune it back by itself
        self.screens('11_graphics_restored', ('performance',), must={'performance': ['Fix the lag, keep max quality']})
        r = self.task('graphics_tune', apply=True)
        self.assertTrue(r['ok'], r)
        self.assertIsNone(api._graphics_choice())
        self.assertEqual(digest(os.path.join(self.sims, 'ConfigOverride', 'GraphicsRules.sgr')), self.sgr_tuned)
        self.check_all('11 graphics', 'full')

    def test_12_undo_back_to_start(self):
        done = []
        seen = {d for d in self.start.files()[0].values()} | set(self.expected.values())
        for n in range(60):
            st = self.status()
            nxt = [j for j in st['journals'] if j['next_undo']]
            r = self.task('undo_last')
            done.append((nxt[0]['title'] if nxt else None, r['ok'], r['message']))
            self.assert_plain([r['message']], 'undo')
            if not r['ok']:
                self.assertEqual(nxt, [], 'undo_last refused the change the Hub offered: %s' % r['message'])
                break
            self.assertTrue(nxt, 'undo_last undid a change the Hub did not offer')
            self.assertEqual(r['journal'], nxt[0]['id'], 'undo_last undid another change than the one shown')
            snap = Snapshot(self.sims)
            files, both = snap.files()
            self.assertEqual(sorted(both), [], 'after undoing %s' % nxt[0]['title'])
            self.assertEqual(sorted(rel for rel, d in files.items() if d not in seen), [],
                             'after undoing %s: files nobody had' % nxt[0]['title'])
            for rel in snap.mods:
                if rel.lower().endswith('.ts4script'):
                    self.assertLessEqual(rel.count('/'), 1)
            self.assertTrue(PR.check_manifest(self.sims)['ok'], 'after undoing %s' % nxt[0]['title'])
        self.numbers['12 undo'] = done
        _log('undo: %s' % json.dumps(done, indent=1))
        # everything SpeedKit did after the other tool's lean is undone; the studio switch before it cannot be
        # (mods_switch.py rewrote the parking list since) and the Hub says so plainly instead of getting stuck
        self.assertTrue(done and not done[-1][1] and 'cannot be undone' in done[-1][2], done)
        self.assertIn('Switched to Fast mode', [t for t, ok, m in done if ok])
        end = Snapshot(self.sims)
        self.assertEqual(end.files()[0], self.start.files()[0], 'undo did not bring every mod file back')
        self.assertEqual((set(end.mods), set(end.parked)), (set(self.after_lean.mods), set(self.after_lean.parked)),
                         'undo did not put every file back where the other tool had left it')
        self.assertEqual(end.other, self.start.other, 'saves / Tray / graphics not as at the start')
        self.assertTrue(PR.check_manifest(self.sims)['ok'])
        self.assertEqual(mods_switch_full_leaves(self.sims), [])
        st = self.status()
        self.assertFalse([j for j in st['journals'] if j['next_undo']])
        self.assertTrue([j for j in st['journals'] if j['cannot_undo']])
        self.screens('12_undone', ('tools',), must={'tools': ["Can't be undone"]})
        # the rest of the way back is one click: Studio mode brings the parked monitor back too - and it leaves
        # the graphics file alone, because the user undid Max Quality on purpose
        r = self._play('studio', launch=False)
        self.assertIn('as you chose', ' '.join(s['message'] for s in r['steps'] if s['step'] == 'graphics'))
        self.assertEqual(digest(os.path.join(self.sims, 'ConfigOverride', 'GraphicsRules.sgr')), self.sgr_original)
        end = Snapshot(self.sims)
        self.assertEqual(end.files()[0], self.start.files()[0])
        self.assertEqual((set(end.mods), set(end.parked)), (set(self.start.mods), set(self.start.parked)),
                         'not back at the starting layout')
        self.__class__.expected = self.start.files()[0]
        self.check_all('12 back at the start', 'studio')

    def test_12b_undo_after_the_other_tool_moved_the_files(self):
        """Clean-up, then the other chat's lean parks the rewritten files: undoing the clean-up now would put the
        old copies back into Mods beside the parked new ones, so it is not offered; after its 'full' it is."""
        import io
        self._play('full', launch=False)
        r = self.task('cleanup_apply')
        self.assertTrue(r['ok'], r)
        cleaned = Snapshot(self.sims).files()[0]
        self.assertNotEqual(cleaned, self.start.files()[0])
        ms = self.mods_switch()
        with contextlib.redirect_stdout(io.StringIO()):
            ms.lean()
        self.__class__.expected = cleaned
        snap, st = self.check_all('12b lean after the clean-up', 'studio', cas=False, refusals=False)
        self.assertFalse([j for j in st['journals'] if j['next_undo']], 'an undo that would make two copies is offered')
        r = self.task('undo_last')
        self.assertFalse(r['ok'])
        self.assertIn('Removed duplicate copies', r['message'])
        self.assert_plain([r['message']], 'undo refused')
        self.assertEqual(Snapshot(self.sims).files(), (cleaned, set()), 'the refused undo changed something')
        with contextlib.redirect_stdout(io.StringIO()):
            ms.full()
        st = self.status()
        nxt = [j for j in st['journals'] if j['next_undo']]
        self.assertEqual([j['title'] for j in nxt], ['Removed duplicate copies'])
        r = self.task('undo_last')
        self.assertTrue(r['ok'], r)
        self.__class__.expected = self.start.files()[0]
        self.check_all('12b clean-up undone', 'full', refusals=False)
        self._play('studio', launch=False)
        end = Snapshot(self.sims)
        self.assertEqual((set(end.mods), set(end.parked)), (set(self.start.mods), set(self.start.parked)))
        self.check_all('12b back at the start', 'studio')

    def test_13_browse_and_game_path(self):
        nothing = G.Clues(processes=lambda: [], shortcuts=lambda: [], resolve=lambda p: {}, registry=lambda: [],
                          steam=lambda: None, drives=lambda: [])
        game_dir = os.path.join(WORK, 'game')
        try:
            api.configure(game=None, game_clues=nothing)
            self.httpd.hub.forget()
            st = self.status()
            self.assertFalse(st['game']['found'])
            self.assert_plain([st['game']['message']], 'game not found')
            self.screens('13_no_game', ('home',), must={'home': ["We couldn't find The Sims 4", 'Find my game']})
            b = self.hub.get('/api/browse')
            self.assertTrue(b['ok'], b)
            b = self.hub.get('/api/browse?path=' + urllib.request.quote(WORK))
            self.assertTrue(b['ok'], b)
            game_entry = [e for e in b['entries'] if e['name'] == 'game']
            self.assertEqual(len(game_entry), 1, b['entries'])
            self.assertTrue(game_entry[0]['is_game'])
            self.assertEqual(game_entry[0]['hint'], 'Looks like The Sims 4')
            self.assertEqual(b['parent'], E2E)
            b = self.hub.get('/api/browse?path=' + urllib.request.quote(os.path.join(game_dir, 'Game', 'Bin')))
            self.assertTrue(b['is_game'])
            code, r = self.hub.post('/api/game_path', {'path': os.path.join(self.w['data'])})
            self.assertEqual(code, 200)
            self.assertFalse(r['ok'], r)
            code, r = self.hub.post('/api/game_path', {'path': game_dir})
            self.assertTrue(r['ok'], r)
            self.assertEqual(os.path.normcase(r['exe']), os.path.normcase(self.w['exe']))
            st = self.status()
            self.assertEqual((st['game']['found'], st['game']['saved'], st['game']['source']), (True, True, 'your choice'))
            self.assertEqual(os.path.normcase(st['game']['exe']), os.path.normcase(self.w['exe']))
            self.assertEqual(st['game']['store'], 'unknown')
            # a drive with the real game on it: offered as a suggestion, the user's choice still wins
            api.configure(game_clues=G.Clues(processes=lambda: [], shortcuts=lambda: [], resolve=lambda p: {},
                                             registry=lambda: [], steam=lambda: None, drives=lambda: ['E:\\']))
            b = self.hub.get('/api/browse')
            self.assertIn('E:', [d['name'] for d in b['drives']])
            self.assertIn(os.path.normcase(REAL_GAME), [os.path.normcase(s['path']) for s in b['suggestions']])
            self.assertEqual(os.path.normcase(self.status()['game']['exe']), os.path.normcase(self.w['exe']))
        finally:
            api.configure(**self.config)
            self.httpd.hub.forget()
        self.check_all('13 game path', 'studio', cas=False)

    def test_14_open_animator(self):
        before = self._marker_lines(self.w['animator'])
        try:
            api.configure(opener=None)
            st = self.status()
            self.assertEqual(st['animator'], {'installed': True, 'path': self.w['animator']})
            code, r = self.hub.post('/api/open', {'what': 'animator'})
            self.assertTrue(r['ok'], r)
            self.assertTrue(self._wait_marker(self.w['animator'], before), 'the fake Wicked Animator did not start')
        finally:
            api.configure(**self.config)
        code, r = self.hub.post('/api/open', {'what': 'mods'})
        self.assertTrue(r['ok'], r)
        self.assertEqual(self.opened[-1], os.path.join(self.sims, 'Mods'))
        # the library report the Library page opens: the user's words too
        r = self.task('report')
        self.assertTrue(r['ok'], r)
        with open(r['path'], encoding='utf-8') as f:
            page = f.read()
        text = re.sub(r'<style>.*?</style>', ' ', page, flags=re.S)
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).replace('&#x27;', "'")
        self.assertEqual(plain_problems([text]), [], 'report: %s' % INSIDE_WORDS.findall(text))
        for name in self.save_names.values():
            self.assertIn(name, text)
        self.assertNotRegex(text, r'\d\.\d?f\b', 'report: graphics values with an f suffix')
        code, o = self.hub.post('/api/open', {'what': 'report_html'})
        self.assertTrue(o['ok'], o)
        self.check_all('14 animator', 'studio', cas=False)
        self.screens('14_end')

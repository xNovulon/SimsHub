"""Fake Sims 4 folders for the patch-day / game-error / save-backup / load-time tests (cross-platform, temp folders).

The samples follow the real formats: GameVersion.txt (a few header bytes, then the version), lastException.txt /
lastUIException.txt (the game's XML reports, traceback in <desyncdata> with &#13;&#10; line breaks), MC Command
Center's mc_lastexception.html and a Better Exceptions style HTML report, and SpeedKit Monitor's loadtimes.csv.
"""
import csv
import os
import shutil
import tempfile
import time
import zipfile

from speedkit.dbpf import PackageWriter

DAY = 86400
T_SNIPPET = 0x7DF2169C          # an XML tuning type (snippet)
T_CASP = 0x034AEECB


def make_sims(prefix='care_'):
    root = tempfile.mkdtemp(prefix=prefix)
    sims = os.path.join(root, 'The Sims 4')
    for d in ('Mods', 'saves', 'Tray', 'SpeedKit'):
        os.makedirs(os.path.join(sims, d))
    return root, sims


def cleanup(root):
    shutil.rmtree(root, ignore_errors=True)


def set_mtime(path, t):
    os.utime(path, (t, t))


def write_version(sims, version, t=None):
    p = os.path.join(sims, 'GameVersion.txt')
    body = version.encode('ascii')
    with open(p, 'wb') as f:
        f.write(bytes([len(body), 0, 0, 0]) + body)       # a length prefix, then the text (as the game writes it)
    if t:
        set_mtime(p, t)
    return p


def make_game(root, t, size=1000):
    """A fake install with Game\\Bin\\TS4_x64.exe modified at t. Returns the game folder."""
    g = os.path.join(root, 'Games', 'The Sims 4')
    b = os.path.join(g, 'Game', 'Bin')
    os.makedirs(b, exist_ok=True)
    exe = os.path.join(b, 'TS4_x64.exe')
    with open(exe, 'wb') as f:
        f.write(b'MZ' + b'\0' * size)
    set_mtime(exe, t)
    return g


def make_script(path, modules, t=None):
    """A .ts4script (zip) holding compiled modules ('pkg/mod.pyc' ...)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, 'w') as z:
        for m in modules:
            z.writestr(m, b'\x42\x0d\x0d\x0a' + b'\0' * 12 + b'fake bytecode')
    if t:
        set_mtime(path, t)
    return path


def make_tuning_package(path, module, t=None, name='mod_tuning'):
    """A package whose XML tuning names a script module (m="...") - a script mod's companion."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n<I c="Snippet" i="snippet" m="%s" n="%s" s="12345678901234567">'
           '\n  <T n="value">1</T>\n</I>\n' % (module, name)).encode()
    with PackageWriter(path) as w:
        w.add((T_SNIPPET, 0, 0x8000000000000001), xml)
    if t:
        set_mtime(path, t)
    return path


def make_cc_package(path, t=None):
    """A package with no tuning (plain CC)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PackageWriter(path) as w:
        w.add((T_CASP, 0, 0x1234), b'\0' * 64)
    if t:
        set_mtime(path, t)
    return path


def make_save(sims, slot, size, t=None):
    p = os.path.join(sims, 'saves', 'Slot_%08x.save' % slot)
    with open(p, 'wb') as f:
        f.write(os.urandom(min(size, 4096)))
        if size > 4096:
            f.truncate(size)                   # sparse where the drive allows: big saves cost no time
    if t:
        set_mtime(p, t)
    return p


# ------------------------------------------------------------------------------------------ error reports
def _report(when, category, text, build='Local.Unknown.Unknown.1.119.109.1020-1.200.000.254.Release'):
    esc = (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
           .replace('\n', '&#13;&#10;'))
    return ('    <report>\n        <version>2</version>\n        <sku>ONLINE</sku>\n'
            '        <createtime>%s</createtime>\n        <buildsignature>%s</buildsignature>\n'
            '        <categoryid>%s</categoryid>\n        <desyncid>0b0d1a2e-2819-11f1-b04b-2cf05d8e1a3c</desyncid>\n'
            '        <systemconfiguration/>\n        <screenshot/>\n        <desyncdata>%s</desyncdata>\n    </report>\n'
            % (when, build, category, esc))


MCCC_TB = ('[mccc] (MCCC) Error while loading the zone (LastException)\n'
           'Traceback (most recent call last):\n'
           '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\zone.py", line 1085, in on_loading_screen_animation_finished\n'
           '  File "D:\\Deaderpool\\mccc\\mc_cmd_center\\mc_utils\\mc_zone.py", line 188, in _on_loading_finished\n'
           "AttributeError: 'NoneType' object has no attribute 'household_id'")
PATH_TB = ('[interactions] Error invoking an interaction (LastException)\n'
           'Traceback (most recent call last):\n'
           '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\interactions\\base\\super_interaction.py", line 2345, in _run_interaction_gen\n'
           '  File "C:\\Users\\Player\\Documents\\Electronic Arts\\The Sims 4\\Mods\\Kuttoe\\kuttoe_tweaks.ts4script\\kuttoe\\tweaks.py", line 41, in wrapped\n'
           '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\sims\\sim_info.py", line 903, in get_sim_instance\n'
           "KeyError: 4231")
GAME_TB = ('[routing] Error in routing (LastException)\n'
           'Traceback (most recent call last):\n'
           '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\routing\\route_events.py", line 210, in process\n'
           "TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'")


def write_last_exception(sims, name='lastException.txt'):
    body = '<?xml version="1.0" ?>\n<root>\n'
    body += _report('2026-06-12 20:31:45', 'mc_cmd_center\\mc_utils\\mc_zone.py:188', MCCC_TB)
    body += _report('2026-06-12 20:44:02', 'mc_cmd_center\\mc_utils\\mc_zone.py:188', MCCC_TB)
    body += _report('2026-06-12 21:02:10', 'interactions\\base\\super_interaction.py:2345', PATH_TB)
    body += _report('2026-06-13 18:15:31', 'routing\\route_events.py:210', GAME_TB)
    body += '</root>\n'
    p = os.path.join(sims, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body)
    return p


UI_TEXT = ('Error: Error #1009: Cannot access a property or method of a null object reference.\n'
           '\tat widgets.CASPanel::ClothingPicker/onItemSelected()[C:\\dev\\UI\\src\\widgets\\CASPanel.as:412]\n'
           '\tat UI_Cheats_Extension hook: cheat menu (weerbesu_ui_cheats)')


def write_last_ui_exception(sims):
    body = '<?xml version="1.0" ?>\n<root>\n' + _report('2026-06-13 19:01:05', 'UI:CASPanel', UI_TEXT) + '</root>\n'
    p = os.path.join(sims, 'lastUIException.txt')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(body)
    return p


def write_mccc_html(folder):
    p = os.path.join(folder, 'mc_lastexception.html')
    tb = MCCC_TB.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>\n')
    with open(p, 'w', encoding='utf-8') as f:
        f.write('<html><head><title>MCCC Last Exception</title></head><body><h2>MC Command Center Exception</h2>'
                '<p>Date: 2026-06-14 10:02:03</p><pre>%s</pre></body></html>' % tb)
    return p


def write_be_report(sims):
    d = os.path.join(sims, 'BetterExceptions')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'BetterExceptions_Report_2026-06-14_11-20-00.html')
    tb = ('Traceback (most recent call last):\n'
          '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\services\\persistence_service.py", line 512, in save_game_gen\n'
          '  File "E:\\Modding\\LMS\\lms_firstlove\\firstlove\\save_hook.py", line 77, in _save\n'
          "ValueError: invalid literal for int() with base 10: 'abc'")
    with open(p, 'w', encoding='utf-8') as f:
        f.write('<!DOCTYPE html><html><body><h1>Better Exceptions Report</h1><div class="meta">Created: 2026-06-14 11:20:00'
                '</div><div class="analysis">Possible cause: a mod that hooks saving.</div><pre class="tb">%s</pre></body></html>'
                % tb.replace('<', '&lt;'))
    return p


# ------------------------------------------------------------------------------------------ load times
HEADER = ['time', 'event', 'since_launch_s', 'launch_to_scripts_s', 'launch_to_menu_s', 'lot_load_s',
          'game_zone_load_s', 'lot_index', 'zone_id', 'profile', 'script_mods', 'script_modules',
          'launch_source', 'launch_time', 'free_ram_mb_at_start', 'monitor_version']


def write_loadtimes(sims, starts):
    """starts: [(launch 'YYYY-mm-dd HH:MM:SS', profile, menu_s, lot_s or None)]; writes the monitor's rows
    (a main_menu row, then a lot_loaded row, then a second main_menu row after going back to the menu)."""
    d = os.path.join(sims, 'SpeedKit', 'reports')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, 'loadtimes.csv')
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for launch, profile, menu, lot in starts:
            w.writerow([launch, 'main_menu', menu, 30.5, menu, '', '', '', '', profile, 12, 480, 'speedkit', launch,
                        12000, '1.4'])
            if lot is not None:
                w.writerow([launch, 'lot_loaded', menu + 60 + lot, 30.5, menu, lot, lot - 2, 1, '0x1a2b', profile, 12,
                            480, 'speedkit', launch, 12000, '1.4'])
                w.writerow([launch, 'lot_loaded', menu + 400, 30.5, menu, lot * 3, lot - 2, 2, '0x1a2c', profile, 12,
                            480, 'speedkit', launch, 12000, '1.4'])
            w.writerow([launch, 'main_menu', menu + 900, 30.5, menu, '', '', '', '', profile, 12, 480, 'speedkit',
                        launch, 12000, '1.4'])
    return p


def now():
    return time.time()

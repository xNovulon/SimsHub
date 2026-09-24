"""The Game Doctor's WickedWhims version card (backend/doctor.py version_cards / ww_version_info), on fake Sims 4
folders - no game needed.

    python tools/checks/wwversion/ww_version_check.py

Each case builds a folder in %TEMP% (WICKED_SIMS_DIR points the Doctor at it): Mods with or without WickedWhims'
two files, saves\\WickedWhimsMod\\last_version_control.ww and/or WickedWhimsInfoLog.log saying a version, with chosen
file times. The card must say exactly what those files show: nothing when WickedWhims is the version the exporter
was written for (backend/wwpackage.py WW_WRITTEN_FOR), "can't tell" without a note, "very old", "a little older" or
"newer" otherwise, "updated since you last played" when the script is newer than the note. Two cases run the whole
scan (doctor.scan) to see the card among the others. Nothing outside %TEMP% (and the Doctor's cache folder) is written.
Prints a PASS/FAIL table, exits 1 when anything fails.
"""
import os
import shutil
import struct
import sys
import tempfile
import time
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import doctor  # noqa: E402
import gamelog  # noqa: E402
import wwpackage  # noqa: E402

BASE = tempfile.mkdtemp(prefix='wa_wwversion_')
DAY = 86400
NOW = time.time() - 10 * DAY
rows = []
# an empty, valid .package (DBPF 2.1 header, no resources): WickedWhims' tuning file stand-in
EMPTY_DBPF = bytearray(96)
EMPTY_DBPF[0:4] = b'DBPF'
struct.pack_into('<II', EMPTY_DBPF, 4, 2, 1)
struct.pack_into('<I', EMPTY_DBPF, 44, 4)
struct.pack_into('<I', EMPTY_DBPF, 64, 96)
EMPTY_DBPF = bytes(EMPTY_DBPF) + b'\0\0\0\0'


def row(name, ok, detail=''):
    rows.append((name, bool(ok), str(detail)))


def make(name, ww=True, note=None, note_time=None, log=None, log_time=None, script_time=None, mods=True, twice=False):
    """A fake 'The Sims 4' folder. note: text of last_version_control.ww; log: the version the log's start line says."""
    root = os.path.join(BASE, name, 'The Sims 4')
    os.makedirs(root)
    if mods:
        os.makedirs(os.path.join(root, 'Mods', 'scripts'))
        with open(os.path.join(root, 'Mods', 'someone_else_pose.package'), 'wb') as f:
            f.write(b'not really a package')
    if mods and ww:
        for folder in (['scripts', 'scripts2'] if twice else ['scripts']):
            os.makedirs(os.path.join(root, 'Mods', folder), exist_ok=True)
            script = os.path.join(root, 'Mods', folder, 'TURBODRIVER_WickedWhims_Scripts.ts4script')
            with zipfile.ZipFile(script, 'w') as z:
                z.writestr('wickedwhims/__init__.pyc', b'\0' * 16)
            with open(os.path.join(root, 'Mods', folder, 'TURBODRIVER_WickedWhims_Tuning.package'), 'wb') as f:
                f.write(EMPTY_DBPF)
            t = script_time or NOW - 30 * DAY
            os.utime(script, (t, t))
    if note is not None:
        d = os.path.join(root, 'saves', 'WickedWhimsMod')
        os.makedirs(d)
        p = os.path.join(d, 'last_version_control.ww')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(note)
        t = note_time or NOW
        os.utime(p, (t, t))
    if log is not None:
        p = os.path.join(root, 'WickedWhimsInfoLog.log')
        with open(p, 'w', encoding='utf-8') as f:
            f.write('09/24/26 01:53:38 [VERSION_REGISTRY/INFO] Running The Sims 4 version 1.126.73.1030...\n'
                    '09/24/26 01:53:38 [VERSION_REGISTRY/INFO] Running WickedWhims %s...\n' % log)
        t = log_time or NOW
        os.utime(p, (t, t))
    return root


def cards_for(root):
    os.environ['WICKED_SIMS_DIR'] = root
    mod_files = doctor._walk(doctor.mods_dir())
    session = gamelog.read(check_running=False).get('session') or {}
    return doctor.version_cards(mod_files, session), doctor.ww_version_info(mod_files, session)


def one(name, expect_level, expect_title, **kw):
    cards, info = cards_for(make(name, **kw))
    if expect_level is None:
        row('%s: no version card' % name, not cards, [c['title'] for c in cards] or 'version %s' % info['version'])
        return cards, info
    c = cards[0] if cards else {}
    ok = len(cards) == 1 and c.get('level') == expect_level and expect_title.lower() in c.get('title', '').lower()
    row('%s: %s card "%s"' % (name, expect_level, expect_title), ok, '%s | %s' % (c.get('title'), c.get('text', '')[:150]))
    return cards, info


try:
    want = wwpackage.WW_WRITTEN_FOR
    row('the exporter says which WickedWhims it was written for', doctor.parse_ww_version(want) == (185, 'k'), want)
    row('versions are read and compared', doctor.parse_ww_version('v185k') == (185, 'k') and doctor.parse_ww_version('v186') == (186, '')
        and doctor.parse_ww_version('185f') == (185, 'f') and doctor.parse_ww_version('nothing') is None
        and (185, '') < (185, 'a') < (185, 'k') < (186, ''), 'v185 < v185a < v185k < v186')

    one('no WickedWhims', None, '', ww=False, note='v185k')
    one('no Mods folder', None, '', mods=False)
    one('two copies (the install card says so)', None, '', note='v170a', twice=True)
    one('never started', 'info', "can't tell", note=None)
    one('only a year in the note', 'info', "can't tell", note='2024\n')
    _, info = one('the same version', None, '', note='v185k')
    row('the same version: read from the saves note', info['version'] == 'v185k' and info['source'] == 'saves', info)
    cards, _ = one('very old', 'yellow', 'very old', note='v170c')
    it = (cards[0].get('items') or [{}])[0] if cards else {}
    row('very old: the card names the script file, with "Show me"', it.get('file') == 'scripts/TURBODRIVER_WickedWhims_Scripts.ts4script'
        and (it.get('action') or {}).get('kind') == 'reveal' and 'v185k' in cards[0]['text'] and '15 version numbers' in cards[0]['text'], cards and cards[0]['text'])
    one('a little older', 'info', 'a little older', note='v183b')
    one('an older letter', 'info', 'a little older', note='v185f')
    one('newer', 'info', 'newer', note='v186a')
    one('a newer letter', 'info', 'newer', note='v185m')
    one('the note holds a date too', 'info', 'newer', note='2026-09-01 12:00 v187a\n')
    # two sources: the newer one counts
    _, info = one('log newer than the note', 'info', 'newer', note='v184a', note_time=NOW - 5 * DAY, log='v186b', log_time=NOW)
    row('log newer than the note: the log\'s version is used', info['version'] == 'v186b' and info['source'] == 'log', info['version'])
    _, info = one('note newer than the log', 'yellow', 'very old', note='v175a', note_time=NOW, log='v186b', log_time=NOW - 5 * DAY)
    row('note newer than the log: the note\'s version is used', info['version'] == 'v175a' and info['source'] == 'saves', info['version'])
    one('only the log', None, '', log='v185k')
    # updated since the last game start
    cards, _ = one('updated after the note (same version)', 'info', 'updated since you last played', note='v185k', note_time=NOW - 3 * DAY, script_time=NOW)
    cards, _ = one('updated after the note (old version)', 'yellow', 'very old', note='v170a', note_time=NOW - 3 * DAY, script_time=NOW)
    row('an old note under a newer script says to start the game once', cards and 'start the game once' in cards[0]['text'], cards and cards[0]['text'][-140:])
    # the target moves with the exporter
    old = wwpackage.WW_WRITTEN_FOR
    try:
        wwpackage.WW_WRITTEN_FOR = 'v186a'
        cards, _ = cards_for(make('target moved', note='v186a'))
        row('the card follows wwpackage.WW_WRITTEN_FOR', not cards, [c['title'] for c in cards])
    finally:
        wwpackage.WW_WRITTEN_FOR = old

    # the whole scan, on two folders
    for name, note, want_level in (('scan: very old', 'v170c', 'yellow'), ('scan: current', 'v185k', None)):
        root = make(name, note=note)
        os.environ['WICKED_SIMS_DIR'] = root
        res = doctor.scan()
        ids = [c['id'] for c in res['cards']]
        vc = [c for c in res['cards'] if c['id'] == 'install:wwversion']
        okc = next((c for c in res['cards'] if c['id'] == 'install:ok'), None)
        if want_level:
            row('%s: the card is in the scan, next to "is installed"' % name, vc and vc[0]['level'] == want_level and okc and note in okc['title'],
                '%s | %s' % (okc and okc['title'], ids[:6]))
        else:
            row('%s: no version card, "WickedWhims v185k is installed"' % name, not vc and okc and 'v185k' in okc['title'], '%s | %s' % (okc and okc['title'], ids[:6]))
finally:
    shutil.rmtree(BASE, ignore_errors=True)

w = max(len(n) for n, _, _ in rows)
print("\nThe Game Doctor's WickedWhims version card\n" + '-' * (w + 20))
for n, ok, d in rows:
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', n.ljust(w), d[:220]))
bad = sum(1 for _, ok, _ in rows if not ok)
print('-' * (w + 20) + '\n%d PASS, %d FAIL' % (len(rows) - bad, bad))
sys.exit(1 if bad else 0)

r"""Build dist/SpeedKit_Monitor.ts4script from ingame/speedkit_monitor/*.py.

    python tools/build_ingame.py

Facts this relies on (research/profiler):
  * The game imports only .pyc/.pyo from a .ts4script (core.zip sims4/importer/utils.module_names_gen:
    archives use '.+\.py[co]$'), so the archive must hold bytecode for the game's exact Python: 3.7.0,
    pyc magic 3394 (b'B\r\r\n').
  * The .pyc files are therefore compiled by py_compile running INSIDE the game's own python37_x64.dll
    (tools/game_python.py loads it into a child process; the DLL is only read), not by Python 3.12.
  * Paths inside the archive are speedkit_monitor/<name>.pyc (a package at the archive root; the game
    puts the archive on sys.path and imports 'speedkit_monitor.<name>'). Entries are deflated like the
    game's own base.zip and the mods' archives. co_filename is baked as
    'SpeedKit_Monitor.ts4script/speedkit_monitor/<name>.py' so tracebacks name the mod.
The archive is written to a temporary name and renamed into place.
"""
import json
import os
import sys
import tempfile
import time
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)
from tools import game_python  # noqa: E402

SRC = os.path.join(PROJECT, 'ingame', 'speedkit_monitor')
DIST = os.path.join(PROJECT, 'dist', 'SpeedKit_Monitor.ts4script')
ARCHIVE = 'SpeedKit_Monitor.ts4script'
PACKAGE = 'speedkit_monitor'
MAGIC_37 = 3394

COMPILE37 = r'''
import json, sys, importlib.util, py_compile
job = json.loads(HOST_ARGS)
out = {'version': sys.version, 'magic': importlib.util.MAGIC_NUMBER.hex(), 'compiled': [], 'errors': []}
for src, cfile, dfile in job['files']:
    try:
        py_compile.compile(src, cfile=cfile, dfile=dfile, doraise=True)
        out['compiled'].append(cfile)
    except Exception as e:
        out['errors'].append('%s: %s' % (src, e))
with open(job['result'], 'w', encoding='utf-8') as f:
    json.dump(out, f)
'''


def sources(src_dir=SRC):
    """The .py files of the package, sorted (no sub-packages)."""
    return sorted(os.path.join(src_dir, n) for n in os.listdir(src_dir) if n.endswith('.py'))


def magic_ok(data):
    """True if data starts with a Python 3.7.0 .pyc header (magic 3394 + b'\\r\\n', 16-byte header)."""
    return len(data) >= 16 and int.from_bytes(data[:2], 'little') == MAGIC_37 and data[2:4] == b'\r\n'


def compile_in_game_python(files, out_dir, timeout=300):
    """Compile .py files with py_compile inside the game's python37_x64.dll. Returns the child's report:
    {'version', 'magic', 'compiled': [pyc paths], 'errors': [...], 'stdout', 'returncode'}."""
    job = {'files': [], 'result': os.path.join(out_dir, '_compile_result.json')}
    for src in files:
        name = os.path.splitext(os.path.basename(src))[0]
        job['files'].append([src, os.path.join(out_dir, name + '.pyc'),
                             '%s/%s/%s.py' % (ARCHIVE, PACKAGE, name)])
    script = os.path.join(out_dir, '_compile37.py')
    with open(script, 'w', encoding='utf-8') as f:
        f.write(COMPILE37)
    cp = game_python.run(script, args=json.dumps(job), timeout=timeout)
    try:
        with open(job['result'], encoding='utf-8') as f:
            rep = json.load(f)
    except (OSError, ValueError):
        rep = {'version': None, 'magic': None, 'compiled': [], 'errors': ['no result from game Python']}
    rep['stdout'] = (cp.stdout or '') + (cp.stderr or '')
    rep['returncode'] = cp.returncode
    return rep


def build(src_dir=SRC, dist=DIST):
    """Compile and pack the mod. Returns {'dist', 'entries', 'bytes', 'python', 'seconds'}; raises
    RuntimeError if anything fails to compile or a .pyc has the wrong magic number."""
    if not game_python.available():
        raise RuntimeError('game Python not found at %s' % game_python.DLL)
    t0 = time.perf_counter()
    files = sources(src_dir)
    if not files:
        raise RuntimeError('no .py files in %s' % src_dir)
    with tempfile.TemporaryDirectory(prefix='speedkit_build_') as tmp:
        rep = compile_in_game_python(files, tmp)
        if rep['errors'] or len(rep['compiled']) != len(files):
            raise RuntimeError('compile failed: %s\n%s' % (rep['errors'], rep['stdout']))
        entries = []
        os.makedirs(os.path.dirname(dist), exist_ok=True)
        part = dist + '.writing'
        try:
            with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as z:
                for src, cfile in zip(files, rep['compiled']):
                    with open(cfile, 'rb') as f:
                        data = f.read()
                    if not magic_ok(data):
                        raise RuntimeError('%s: not a Python 3.7 .pyc (magic %r)' % (cfile, data[:4]))
                    arc = '%s/%s' % (PACKAGE, os.path.basename(cfile))
                    info = zipfile.ZipInfo(arc, time.localtime(os.path.getmtime(src))[:6])
                    info.compress_type = zipfile.ZIP_DEFLATED
                    z.writestr(info, data)
                    entries.append(arc)
            os.replace(part, dist)
        finally:
            if os.path.exists(part):             # a failed build leaves the previous dist untouched
                os.remove(part)
    return {'dist': dist, 'entries': entries, 'bytes': os.path.getsize(dist), 'python': rep['version'],
            'magic': rep['magic'], 'seconds': time.perf_counter() - t0}


def verify(dist=DIST):
    """Check a built archive: every entry is speedkit_monitor/<name>.pyc with magic 3394, no .py.
    Returns a list of problems (empty = fine)."""
    problems = []
    with zipfile.ZipFile(dist) as z:
        names = z.namelist()
        if not names:
            problems.append('empty archive')
        for n in names:
            if not (n.startswith(PACKAGE + '/') and n.endswith('.pyc') and n.count('/') == 1):
                problems.append('unexpected entry %s' % n)
            elif not magic_ok(z.read(n)):
                problems.append('bad magic in %s' % n)
        if PACKAGE + '/__init__.pyc' not in names:
            problems.append('missing %s/__init__.pyc' % PACKAGE)
    return problems


def main():
    r = build()
    problems = verify(r['dist'])
    print('built %s: %d modules, %d bytes, %.1f s, compiled by game Python %s (magic %s)' % (
        r['dist'], len(r['entries']), r['bytes'], r['seconds'], (r['python'] or '').split()[0], r['magic']))
    for e in r['entries']:
        print('  ' + e)
    if problems:
        print('PROBLEMS:', *problems, sep='\n  ')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

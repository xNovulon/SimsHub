r"""Run a Python 3.7 script inside The Sims 4's own python37_x64.dll, in a child process.

    python tools/game_python.py <script37.py> [--path DIR_OR_ZIP ...] [--args TEXT] [--ticks N --gap-ms MS]

How (the approach of research/profiler/host37.py, verified there): a normal Python 3.12 process loads
E:\The Sims 4\Game\Bin\python37_x64.dll with ctypes (read-only use of the file), sets the flags and
sys.path the way Simulation_x64.dll does (no site, no environment, no bytecode writing; path = the game's
base.zip\lib + core.zip + extras), calls Py_Initialize + PyEval_InitThreads - the calling thread then owns
the 3.7 GIL for good, like the game's simulation thread - and runs the script in 3.7's __main__ with
HOST_ARGS set to the --args text. With --ticks the host then calls the script's tick() N times, busy-waiting
--gap-ms between calls OUTSIDE 3.7 while still holding its GIL (like the game's C++ side between Python
bursts), and finally calls finish(host_seconds).
Each run is its own process because an embedded interpreter can be initialised only once.
The game itself is never started and nothing under E:\The Sims 4 is written.
"""
import argparse
import ctypes
import os
import subprocess
import sys
import time

BIN = r'E:\The Sims 4\Game\Bin'
GAMEPLAY = r'E:\The Sims 4\Data\Simulation\Gameplay'
DLL = os.path.join(BIN, 'python37_x64.dll')


def game_path():
    """The part of sys.path every game-Python run gets: base.zip\\lib and core.zip."""
    return [os.path.join(GAMEPLAY, 'base.zip', 'lib'), os.path.join(GAMEPLAY, 'core.zip')]


def available():
    """True if the game's python37_x64.dll and gameplay zips are where we expect them."""
    return os.path.isfile(DLL) and all(os.path.exists(p.split('.zip')[0] + '.zip') for p in game_path())


def run(script, path=(), args='', ticks=0, gap_ms=0.0, timeout=600):
    """Run script under the game's Python in a child process. Returns subprocess.CompletedProcess
    (stdout/stderr as text; returncode 0 when the script and every tick() ran without an exception)."""
    cmd = [sys.executable, os.path.abspath(__file__), os.path.abspath(script), '--args', args,
           '--ticks', str(int(ticks)), '--gap-ms', str(float(gap_ms))]
    for p in path:
        cmd += ['--path', p]
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                          encoding='utf-8', errors='replace')


def host(script, path=(), args='', ticks=0, gap_ms=0.0):
    """Child side: load the DLL into this process and run the script. Returns an exit code."""
    os.add_dll_directory(BIN)
    py = ctypes.PyDLL(DLL)
    for flag in ('Py_NoSiteFlag', 'Py_IgnoreEnvironmentFlag', 'Py_DontWriteBytecodeFlag', 'Py_NoUserSiteDirectory'):
        ctypes.c_int.in_dll(py, flag).value = 1
    py.Py_SetPath.argtypes = [ctypes.c_wchar_p]
    py.Py_SetPath(';'.join(game_path() + list(path)))
    py.Py_SetPythonHome.argtypes = [ctypes.c_wchar_p]
    py.Py_SetPythonHome(BIN)
    py.Py_Initialize()
    py.PyEval_InitThreads()
    py.PyRun_SimpleString.argtypes = [ctypes.c_char_p]
    py.PyRun_SimpleString.restype = ctypes.c_int
    boot = '\n'.join([
        'import sys, traceback',
        'HOST_ARGS = %r' % args,
        'try:',
        '    exec(compile(open(%r, encoding="utf-8").read(), %r, "exec"), globals())' % (script, script),
        'finally:',
        '    sys.stdout.flush(); sys.stderr.flush()',
        ''])
    if py.PyRun_SimpleString(boot.encode('utf-8')):
        return 1
    rc = 0
    if ticks:
        t0 = time.perf_counter()
        for _ in range(ticks):
            if py.PyRun_SimpleString(b'tick()'):
                rc = 2
                break
            if gap_ms:
                end = time.perf_counter() + gap_ms / 1000.0
                while time.perf_counter() < end:
                    pass
        host_s = time.perf_counter() - t0
        if py.PyRun_SimpleString(('finish(%r)' % host_s).encode()):
            rc = rc or 3
    py.PyRun_SimpleString(b'import sys; sys.stdout.flush(); sys.stderr.flush()')
    return rc


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('script')
    ap.add_argument('--path', action='append', default=[])
    ap.add_argument('--args', default='')
    ap.add_argument('--ticks', type=int, default=0)
    ap.add_argument('--gap-ms', type=float, default=0.0)
    a = ap.parse_args(argv)
    sys.stdout.flush()
    return host(a.script, a.path, a.args, a.ticks, a.gap_ms)


if __name__ == '__main__':
    sys.exit(main())

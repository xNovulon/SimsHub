r"""host37.py <script37.py> [--ticks N --gap-ms Y]
Loads the GAME's own python37_x64.dll (read-only, from E:\The Sims 4\Game\Bin) into this process via ctypes,
initializes it the way Simulation_x64.dll does (Py_Initialize + PyEval_InitThreads; the embedding thread keeps the
GIL - Simulation_x64.dll imports no PyEval_SaveThread/PyGILState_* at all), runs <script37.py> once, then optionally
emulates the game loop: call tick() N times, and between calls stay OUTSIDE Python for gap-ms while still holding the
3.7 GIL (like the C++ side of TS4 does while rendering/routing)."""
import ctypes, sys, os, time, argparse

BIN = r'E:\The Sims 4\Game\Bin'
GP = r'E:\The Sims 4\Data\Simulation\Gameplay'
ap = argparse.ArgumentParser()
ap.add_argument('script')
ap.add_argument('--ticks', type=int, default=0)
ap.add_argument('--gap-ms', type=float, default=0)
ap.add_argument('--extra-path', default='')
ap.add_argument('--args', default='')
ap.add_argument('--timer1', action='store_true', help='timeBeginPeriod(1) in this test process, like TS4_x64.exe (imports winmm!timeBeginPeriod)')
a = ap.parse_args()
if a.timer1:
    ctypes.WinDLL('winmm').timeBeginPeriod(1)
os.add_dll_directory(BIN)
py = ctypes.PyDLL(os.path.join(BIN, 'python37_x64.dll'))
for flag in ('Py_NoSiteFlag', 'Py_IgnoreEnvironmentFlag', 'Py_DontWriteBytecodeFlag', 'Py_NoUserSiteDirectory'):
    ctypes.c_int.in_dll(py, flag).value = 1
parts = [os.path.join(GP, 'base.zip', 'lib'), os.path.join(GP, 'core.zip')]
if a.extra_path:
    parts += a.extra_path.split(';')
py.Py_SetPath.argtypes = [ctypes.c_wchar_p]
py.Py_SetPath(';'.join(parts))
py.Py_SetPythonHome.argtypes = [ctypes.c_wchar_p]
py.Py_SetPythonHome(BIN)
py.Py_Initialize()
py.PyEval_InitThreads()  # same calls Simulation_x64.dll imports; this thread now owns the 3.7 GIL for good
py.PyRun_SimpleString.argtypes = [ctypes.c_char_p]
py.PyRun_SimpleString.restype = ctypes.c_int
NL = chr(10)
boot = NL.join([
    'import sys, traceback',
    'HOST_ARGS = %r' % a.args,
    'try:',
    '    exec(compile(open(%r, encoding="utf-8").read(), %r, "exec"), globals())' % (a.script, a.script),
    'except BaseException:',
    '    traceback.print_exc(file=sys.stdout); sys.stdout.flush(); raise',
    ''])
rc = py.PyRun_SimpleString(boot.encode('utf-8'))
if rc:
    print('script failed rc', rc)
    sys.exit(1)
if a.ticks:
    t0 = time.perf_counter()
    for i in range(a.ticks):
        if py.PyRun_SimpleString(b'tick()'):
            print('tick failed')
            break
        if a.gap_ms:  # "C++ time": busy-wait in the host, never touching 3.7, GIL still held by this thread
            end = time.perf_counter() + a.gap_ms / 1000
            while time.perf_counter() < end:
                pass
    host_s = time.perf_counter() - t0
    py.PyRun_SimpleString(('finish(%r)' % host_s).encode())
sys.stdout.flush()

r"""Open Novulon's Sims Hub with no console window at all (what the Desktop shortcut runs).

    pythonw -m speedkit.hub                 the same as --open (pythonw never shows a console)
    python  -m speedkit.hub --open

1. Is the Hub's server answering on 127.0.0.1:8766? If not, it is started in the background with no console
   (pythonw.exe; else this interpreter as a DETACHED_PROCESS), and we wait until it answers.
2. Is a Hub window open already? It is brought to the front. Otherwise one is opened: Chrome, then Edge (both
   install folders each), then the default browser - as an app window (--app) with its own browser profile in
   %LOCALAPPDATA%\NovulonSimsHub\browser, so it gets its own taskbar entry and remembers its size.
Problems are shown in a small Windows message box (there is no console to print to).
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

APP = "Novulon's Sims Hub"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PROFILE = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'NovulonSimsHub', 'browser')
BROWSERS = (r'%ProgramFiles%\Google\Chrome\Application\chrome.exe', r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe',
            r'%LocalAppData%\Google\Chrome\Application\chrome.exe', r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe',
            r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe')
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def ping(port, timeout=1.0):
    """Is the Hub itself (not some other program) answering on this port?"""
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/ping' % port, timeout=timeout) as r:
            return json.loads(r.read()).get('app') == APP
    except (OSError, ValueError, AttributeError):
        return False


def windowless_python():
    """pythonw.exe next to this interpreter (no console), else this interpreter."""
    exe = sys.executable or 'python'
    folder, name = os.path.split(exe)
    if name.lower() == 'pythonw.exe':
        return exe
    w = os.path.join(folder, 'pythonw.exe')
    return w if os.path.isfile(w) else exe


def server_command(port, stub=False):
    return [windowless_python(), '-m', 'speedkit.hub', '--serve', '--port', str(port)] + (['--stub'] if stub else [])


def start_server(port, stub=False):
    cmd = server_command(port, stub)
    # pythonw has no console to begin with; python.exe gets none either as a detached process
    flags = CREATE_NEW_PROCESS_GROUP | (0 if cmd[0].lower().endswith('pythonw.exe') else DETACHED_PROCESS)
    env = dict(os.environ)
    env['PYTHONPATH'] = ROOT + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    return subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, creationflags=flags if os.name == 'nt' else 0, close_fds=True)


def wait_ready(port, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        if ping(port):
            return True
        time.sleep(0.25)
    return False


def is_hub_title(title):
    """An --app window's title is the page's own: "Novulon's Sims Hub" or "Tools - Novulon's Sims Hub" (a normal
    browser window would add " - Google Chrome", and the banner page is "Novulon's Sims Hub banner")."""
    return title == APP or title.endswith(' - ' + APP)


def hub_windows():
    """Top-level app windows of the Hub."""
    if os.name != 'nt':
        return []
    user32 = ctypes.windll.user32
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def each(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            title = buf.value
            if cls.value == 'Chrome_WidgetWin_1' and is_hub_title(title):
                found.append(hwnd)
        return True
    user32.EnumWindows(proto(each), None)
    return found


def focus(hwnd):
    user32 = ctypes.windll.user32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)            # SW_RESTORE
    return bool(user32.SetForegroundWindow(hwnd))


def find_browser():
    for p in BROWSERS:
        p = os.path.expandvars(p)
        if '%' not in p and os.path.isfile(p):
            return p
    return None


def open_window(url, profile=PROFILE, browser=None):
    """An app window with the Hub's own profile; the default browser when there is no Chrome or Edge."""
    browser = browser or find_browser()
    if not browser:
        os.startfile(url)
        return None
    first = not os.path.isdir(profile)
    args = [browser, '--app=' + url, '--user-data-dir=' + profile, '--no-first-run', '--no-default-browser-check']
    if first:
        args.append('--start-maximized')      # after that the window keeps the size the user gave it
    return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=DETACHED_PROCESS if os.name == 'nt' else 0, close_fds=True)


def message(text, error=True):
    if os.name == 'nt':
        ctypes.windll.user32.MessageBoxW(None, text, APP, 0x10 if error else 0x40)
    else:
        print(text)


def open_hub(port, stub=False, profile=PROFILE):
    url = 'http://127.0.0.1:%d/' % port
    if not ping(port):
        try:
            start_server(port, stub)
        except OSError as ex:
            message("Novulon's Sims Hub could not start (%s). Please try once more." % ex)
            return 1
        if not wait_ready(port):
            message("Novulon's Sims Hub didn't start. Please try once more.\n\n"
                    "If it still doesn't open, another program may be using its place on this PC (port %d). "
                    "Restarting the PC usually fixes that." % port)
            return 1
    for hwnd in hub_windows():
        if focus(hwnd):
            return 0
    try:
        open_window(url, profile)
    except OSError as ex:
        message("The Hub is running, but its window could not be opened (%s).\nOpen %s in your browser." % (ex, url))
        return 1
    return 0

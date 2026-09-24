"""The Hub's icon and Desktop shortcut.

    python -m speedkit.hub.desktop              both
    python -m speedkit.hub.desktop --icon       only rebuild speedkit/hub/web/img/hub.ico from img/logo.svg
    python -m speedkit.hub.desktop --shortcut   only (re)create the Desktop shortcut

The icon: headless Chrome (or Edge) renders logo.svg to PNGs at 16, 32, 48 and 256 px on a transparent
background, and those PNGs go into one .ico file as they are (Windows Vista and later read PNG icons).
The shortcut: "<Desktop>\\Novulon's Sims Hub.lnk" -> pythonw.exe -m speedkit.hub --open (no console window at all;
see launcher.py), made with WScript.Shell. "Start Novulon's Sims Hub.bat" stays as a fallback. Nothing else on
the Desktop is touched.
"""
import base64
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IMG = os.path.join(HERE, 'web', 'img')
LOGO = os.path.join(IMG, 'logo.svg')
ICO = os.path.join(IMG, 'hub.ico')
BAT = os.path.join(ROOT, "Start Novulon's Sims Hub.bat")
NAME = "Novulon's Sims Hub"
SIZES = (16, 32, 48, 256)
BROWSERS = (r'%ProgramFiles%\Google\Chrome\Application\chrome.exe', r'%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe',
            r'%LocalAppData%\Google\Chrome\Application\chrome.exe', r'%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe',
            r'%ProgramFiles%\Microsoft\Edge\Application\msedge.exe')


def find_browser():
    for p in BROWSERS:
        p = os.path.expandvars(p)
        if os.path.isfile(p):
            return p
    return None


def png_size(data):
    if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
        raise ValueError('not a PNG')
    return struct.unpack('>II', data[16:24])


def png_alpha_corner(data):
    """Alpha of the top-left pixel of an 8-bit RGBA, non-interlaced PNG (to check the background is see-through)."""
    w, h = png_size(data)
    depth, ctype, interlace = data[24], data[25], data[28]
    if (depth, ctype, interlace) != (8, 6, 0):
        return None
    pos, idat = 8, b''
    while pos < len(data):
        n, kind = struct.unpack('>I4s', data[pos:pos + 8])
        if kind == b'IDAT':
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw = zlib.decompress(idat)
    return raw[1 + 3]           # row 0: filter byte, then R G B A; on the first pixel of the first row every filter adds 0


def render_pngs(browser=None, sizes=SIZES):
    browser = browser or find_browser()
    if not browser:
        raise RuntimeError('Chrome or Edge is needed to draw the icon.')
    tmp = tempfile.mkdtemp(prefix='hubicon_')
    out = {}
    try:
        logo_uri = 'file:///' + LOGO.replace('\\', '/')
        for s in sizes:
            page = os.path.join(tmp, 'icon%d.html' % s)
            with open(page, 'w', encoding='utf-8') as f:
                f.write('<!doctype html><html><body style="margin:0;background:transparent">'
                        '<img src="%s" width="%d" height="%d" style="display:block"></body></html>' % (logo_uri, s, s))
            png = os.path.join(tmp, 'icon%d.png' % s)
            subprocess.run([browser, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                            '--no-default-browser-check', '--user-data-dir=' + os.path.join(tmp, 'profile'),
                            '--force-device-scale-factor=1', '--default-background-color=00000000',
                            '--window-size=%d,%d' % (s, s), '--screenshot=' + png, 'file:///' + page.replace('\\', '/')],
                           capture_output=True, timeout=120)
            with open(png, 'rb') as f:
                data = f.read()
            if png_size(data) != (s, s):
                raise RuntimeError('The browser drew the %d px icon at %r.' % (s, png_size(data)))
            out[s] = data
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def ico_bytes(pngs):
    """An .ico holding each PNG as it is (PNG-in-ICO), smallest first."""
    sizes = sorted(pngs)
    head = struct.pack('<HHH', 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b'', b''
    for s in sizes:
        data = pngs[s]
        w, h = png_size(data)
        entries += struct.pack('<BBBBHHII', w % 256, h % 256, 0, 0, 1, 32, len(data), offset + len(blobs))
        blobs += data
    return head + entries + blobs


def make_icon(path=ICO, browser=None):
    pngs = render_pngs(browser)
    data = ico_bytes(pngs)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)
    return path, {s: len(p) for s, p in pngs.items()}


def desktop_dir():
    """The user's real Desktop (it may be moved, e.g. into OneDrive)."""
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-Command', '[Environment]::GetFolderPath("Desktop")'],
                           capture_output=True, text=True, timeout=30)
        p = r.stdout.strip()
        if p and os.path.isdir(p):
            return p
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.join(os.path.expanduser('~'), 'Desktop')


def _ps(s):
    return "'" + s.replace("'", "''") + "'"


def pythonw():
    """The pythonw.exe to start the Hub with: what 'where pythonw' finds (for the Microsoft Store Python that is the
    stable app alias in %LOCALAPPDATA%\\Microsoft\\WindowsApps, which survives Python updates), else the one next
    to this interpreter."""
    found = shutil.which('pythonw')
    if found:
        return found[:-4] + '.exe' if found.endswith('.EXE') else found
    w = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    if os.path.isfile(w):
        return w
    raise RuntimeError('pythonw.exe was not found.')


ARGS = '-m speedkit.hub --open'


def make_shortcut(desktop=None, target=None, args=ARGS, name=NAME):
    lnk = os.path.join(desktop or desktop_dir(), name + '.lnk')
    script = ('$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s); $s.TargetPath = %s; $s.Arguments = %s; '
              '$s.WorkingDirectory = %s; $s.IconLocation = %s; $s.Description = %s; $s.WindowStyle = 1; $s.Save()'
              % (_ps(lnk), _ps(target or pythonw()), _ps(args), _ps(ROOT), _ps(ICO + ',0'), _ps(NAME)))
    enc = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', enc], capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not os.path.isfile(lnk):
        raise RuntimeError('The shortcut could not be made: ' + (r.stderr or r.stdout).strip())
    return lnk


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    both = not ({'--icon', '--shortcut'} & set(argv))
    if both or '--icon' in argv:
        path, sizes = make_icon()
        print('Icon:', path, sizes)
    if both or '--shortcut' in argv:
        print('Shortcut:', make_shortcut())
    return 0


if __name__ == '__main__':
    sys.exit(main())

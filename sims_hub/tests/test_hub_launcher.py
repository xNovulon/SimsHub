"""The Hub's launcher (.bat), icon (.ico) and shortcut maker.

The launcher is run for real, as a copy whose 'start' lines only echo what they would open, against a stub Hub on a
free port and fake browser folders: that checks the batch file parses and picks Chrome, then Edge, then the
default browser. Nothing opens, and the real Desktop is never touched (the shortcut test uses a temp folder)."""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from speedkit.hub import desktop, server, stub_api  # noqa: E402

BAT = os.path.join(ROOT, "Start Novulon's Sims Hub.bat")
VARS = {'ProgramFiles': 'HUBTEST_PF', 'ProgramFiles(x86)': 'HUBTEST_PF86', 'LocalAppData': 'HUBTEST_LAD'}


class LauncherFile(unittest.TestCase):
    def setUp(self):
        with open(BAT, 'rb') as f:
            self.raw = f.read()
        self.text = self.raw.decode('ascii')

    def test_shape(self):
        self.assertNotIn(b'\n', self.raw.replace(b'\r\n', b''), 'the .bat needs CRLF line endings')
        self.assertIn("title Novulon's Sims Hub", self.text)
        self.assertIn('http://127.0.0.1:8766/', self.text)
        self.assertIn('python -m speedkit.hub', self.text)
        self.assertIn('--app=%URL%', self.text)
        self.assertIn('--user-data-dir="%PROFILE%"', self.text)
        self.assertIn('%LOCALAPPDATA%\\NovulonSimsHub\\browser', self.text)      # the same profile as launcher.py
        order = [r'%ProgramFiles%\Google\Chrome', r'%ProgramFiles(x86)%\Google\Chrome', r'%LocalAppData%\Google\Chrome',
                 r'%ProgramFiles(x86)%\Microsoft\Edge', r'%ProgramFiles%\Microsoft\Edge', 'start "" %URL%']
        where = [self.text.index(x) for x in order]
        self.assertEqual(where, sorted(where), 'Chrome, then Edge, then the default browser')


@unittest.skipUnless(os.name == 'nt', 'Windows only')
class LauncherRun(unittest.TestCase):
    def setUp(self):
        stub_api.reset()
        self.httpd = server.make_server(0, api=stub_api)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.tmp = tempfile.mkdtemp(prefix='hublaunch_')
        with open(BAT, encoding='ascii') as f:
            text = f.read()
        text = text.replace('8766', str(self.httpd.port))
        text = text.replace('start "" "%BROWSER%"', 'echo OPEN-APP "%BROWSER%"')
        text = text.replace('start "" %URL%', 'echo OPEN-DEFAULT %URL%')
        text = text.replace('start "Novulon\'s Sims Hub server" /min python -m speedkit.hub', 'echo WOULD-START-SERVER')
        # Windows sets %ProgramFiles% afresh for every process, so the copy reads stand-in names instead
        for var, fake in VARS.items():
            text = text.replace('%' + var + '%', '%' + fake + '%')
        self.assertIn('OPEN-APP', text)
        self.bat = os.path.join(self.tmp, 'launch.bat')
        with open(self.bat, 'w', encoding='ascii', newline='\r\n') as f:
            f.write(text)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_with(self, *installed):
        # the fake folders keep the real names, brackets and spaces included (a bracket can end a batch block)
        dirs = {k: os.path.join(self.tmp, n) for k, n in (('ProgramFiles', 'Program Files'), ('ProgramFiles(x86)', 'Program Files (x86)'),
                                                          ('LocalAppData', 'AppData Local'))}
        for d in dirs.values():
            os.makedirs(d, exist_ok=True)
        for var, rel in installed:
            p = os.path.join(dirs[var], rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'wb').close()
        env = dict(os.environ)
        env.update({VARS[k]: v for k, v in dirs.items()})
        r = subprocess.run(['cmd', '/c', self.bat], capture_output=True, text=True, env=env, timeout=60, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn('WOULD-START-SERVER', r.stdout, 'the Hub was already running, so it must not start again')
        return r.stdout, dirs

    def test_prefers_chrome_then_edge_then_default(self):
        chrome = r'Google\Chrome\Application\chrome.exe'
        edge = r'Microsoft\Edge\Application\msedge.exe'
        out, dirs = self.run_with(('ProgramFiles(x86)', edge), ('LocalAppData', chrome))
        self.assertIn('OPEN-APP "%s"' % os.path.join(dirs['LocalAppData'], chrome), out)
        self.assertIn('--app=http://127.0.0.1:%d/' % self.httpd.port, out)
        shutil.rmtree(os.path.join(dirs['LocalAppData'], 'Google'))
        out, dirs = self.run_with()
        self.assertIn('OPEN-APP "%s"' % os.path.join(dirs['ProgramFiles(x86)'], edge), out)
        shutil.rmtree(os.path.join(dirs['ProgramFiles(x86)'], 'Microsoft'))
        out, dirs = self.run_with(('ProgramFiles', edge))
        self.assertIn('OPEN-APP "%s"' % os.path.join(dirs['ProgramFiles'], edge), out)
        out, dirs = self.run_with(('ProgramFiles', chrome))
        self.assertIn('OPEN-APP "%s"' % os.path.join(dirs['ProgramFiles'], chrome), out)
        shutil.rmtree(os.path.join(dirs['ProgramFiles'], 'Google'))
        shutil.rmtree(os.path.join(dirs['ProgramFiles'], 'Microsoft'))
        out, _ = self.run_with()
        self.assertIn('OPEN-DEFAULT http://127.0.0.1:%d/' % self.httpd.port, out)
        self.assertNotIn('OPEN-APP', out)


class Icon(unittest.TestCase):
    def test_hub_ico(self):
        with open(desktop.ICO, 'rb') as f:
            data = f.read()
        self.assertEqual(struct.unpack('<HHH', data[:6]), (0, 1, 4))
        sizes = []
        for i in range(4):
            w, h, _, _, planes, bits, size, off = struct.unpack('<BBBBHHII', data[6 + 16 * i:22 + 16 * i])
            png = data[off:off + size]
            self.assertEqual(desktop.png_size(png), (w or 256, h or 256))
            self.assertEqual((planes, bits), (1, 32))
            self.assertEqual(desktop.png_alpha_corner(png), 0, 'the corners must be see-through')
            sizes.append(w or 256)
        self.assertEqual(sizes, [16, 32, 48, 256])

    def test_ico_bytes_layout(self):
        fake = {s: b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR' + struct.pack('>II', s, s) + b'\x08\x06\0\0\0' for s in (48, 16)}
        data = desktop.ico_bytes(fake)
        self.assertEqual(struct.unpack('<HHH', data[:6]), (0, 1, 2))
        w, _, _, _, _, _, size, off = struct.unpack('<BBBBHHII', data[6:22])
        self.assertEqual((w, data[off:off + size]), (16, fake[16]))


@unittest.skipUnless(os.name == 'nt', 'Windows only')
class Shortcut(unittest.TestCase):
    def test_make_shortcut_in_a_temp_folder(self):
        tmp = tempfile.mkdtemp(prefix='hublnk_')
        try:
            lnk = desktop.make_shortcut(tmp, args=desktop.ARGS)          # the pythonw one (not Sims Hub.exe)
            self.assertEqual(os.path.basename(lnk), "Novulon's Sims Hub.lnk")
            ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%s'); "
                  "$s.TargetPath; $s.Arguments; $s.WorkingDirectory; $s.IconLocation; $s.Description" % lnk.replace("'", "''"))
            out = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=60).stdout.splitlines()
            # pythonw, never a .bat: double-clicking it shows no console window
            self.assertEqual(os.path.basename(out[0]).lower(), 'pythonw.exe')
            self.assertEqual(os.path.normcase(out[0]), os.path.normcase(desktop.pythonw()))
            self.assertEqual(out[1], '-m speedkit.hub --open')
            self.assertEqual([os.path.normcase(x) for x in out[2:4]],
                             [os.path.normcase(os.path.abspath(desktop.ROOT)), os.path.normcase(desktop.ICO + ',0')])
            self.assertEqual(out[4], "Novulon's Sims Hub")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()

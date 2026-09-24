"""Opening the Hub with no console (speedkit/hub/launcher.py, python -m speedkit.hub --open / pythonw -m speedkit.hub).

Nothing here opens a window: the browser start, the focusing and the message box are replaced by recorders; the
server is a stub one on a free port."""
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import speedkit.hub.__main__ as hubmain  # noqa: E402
from speedkit.hub import launcher, server, stub_api  # noqa: E402


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Dispatch(unittest.TestCase):
    def setUp(self):
        self.env = dict(os.environ)
        self.calls = []
        self.p1 = mock.patch.object(launcher, 'open_hub', side_effect=lambda port, stub=False, profile=None: self.calls.append(('open', port, stub)) or 0)
        self.p2 = mock.patch.object(server, 'main', side_effect=lambda: self.calls.append(('serve', os.environ.get('SIMS_HUB_PORT'))) or 0)
        self.p1.start()
        self.p2.start()

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()
        os.environ.clear()
        os.environ.update(self.env)

    def run_as(self, exe, argv):
        with mock.patch.object(sys, 'executable', exe):
            os.environ.pop('SIMS_HUB_PORT', None)
            os.environ.pop('SIMS_HUB_API', None)
            self.assertEqual(hubmain.main(argv), 0)
        return self.calls.pop()

    def test_pythonw_opens_python_serves(self):
        self.assertEqual(self.run_as(r'C:\Py\pythonw.exe', []), ('open', 8766, False))
        self.assertEqual(self.run_as(r'C:\Py\pythonw.exe', ['--serve']), ('serve', None))
        self.assertEqual(self.run_as(r'C:\Py\python.exe', []), ('serve', None))
        self.assertEqual(self.run_as(r'C:\Py\python.exe', ['--open']), ('open', 8766, False))

    def test_port_and_stub(self):
        self.assertEqual(self.run_as(r'C:\Py\python.exe', ['--open', '--port', '8790', '--stub']), ('open', 8790, True))
        self.assertEqual(self.run_as(r'C:\Py\python.exe', ['--port', '8791', 'extra-word']), ('serve', '8791'))


class Pieces(unittest.TestCase):
    def test_server_runs_windowless(self):
        cmd = launcher.server_command(8766)
        self.assertEqual(cmd[1:], ['-m', 'speedkit.hub', '--serve', '--port', '8766'])
        if os.path.isfile(os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')):
            self.assertEqual(os.path.basename(cmd[0]).lower(), 'pythonw.exe')
        self.assertEqual(launcher.server_command(8, stub=True)[-1], '--stub')

    def test_hub_titles(self):
        for t in ("Novulon's Sims Hub", "Tools - Novulon's Sims Hub"):
            self.assertTrue(launcher.is_hub_title(t), t)
        for t in ("Novulon's Sims Hub banner", "Novulon's Sims Hub - Google Chrome", "Novulon's Wicked Animator", ''):
            self.assertFalse(launcher.is_hub_title(t), t)

    def test_app_window_arguments(self):
        seen = []
        with mock.patch.object(launcher.subprocess, 'Popen', side_effect=lambda args, **kw: seen.append(args)):
            prof = os.path.join(tempfile.mkdtemp(prefix='hubprof_'), 'browser')
            launcher.open_window('http://127.0.0.1:1/', prof, browser=r'C:\B\chrome.exe')
            os.makedirs(prof)
            launcher.open_window('http://127.0.0.1:1/', prof, browser=r'C:\B\chrome.exe')
        first, again = seen
        self.assertEqual(first[:3], [r'C:\B\chrome.exe', '--app=http://127.0.0.1:1/', '--user-data-dir=' + prof])
        self.assertIn('--no-first-run', first)
        self.assertIn('--start-maximized', first)          # the first time only; then it keeps the user's size
        self.assertNotIn('--start-maximized', again)
        self.assertTrue(launcher.PROFILE.endswith(os.path.join('NovulonSimsHub', 'browser')))

    def test_default_browser_when_no_chrome_or_edge(self):
        with mock.patch.object(launcher, 'find_browser', return_value=None), \
                mock.patch.object(launcher.os, 'startfile', create=True) as sf:
            self.assertIsNone(launcher.open_window('http://127.0.0.1:1/', 'x'))
        sf.assert_called_once_with('http://127.0.0.1:1/')


class OpenHub(unittest.TestCase):
    def setUp(self):
        stub_api.reset()
        self.port = free_port()
        self.servers, self.opened, self.messages = [], [], []
        self.patches = [mock.patch.object(launcher, 'open_window', side_effect=lambda url, profile=None: self.opened.append(url)),
                        mock.patch.object(launcher, 'message', side_effect=lambda text, error=True: self.messages.append(text))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        for s in self.servers:
            s.shutdown()
            s.server_close()

    def serve(self):
        httpd = server.make_server(self.port, api=stub_api)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.servers.append(httpd)

    def test_running_server_just_opens_the_window(self):
        self.serve()
        with mock.patch.object(launcher, 'start_server', side_effect=AssertionError('must not start a second server')), \
                mock.patch.object(launcher, 'hub_windows', return_value=[]):
            self.assertEqual(launcher.open_hub(self.port), 0)
        self.assertEqual(self.opened, ['http://127.0.0.1:%d/' % self.port])

    def test_starts_the_server_when_it_is_not_running(self):
        self.assertFalse(launcher.ping(self.port))
        with mock.patch.object(launcher, 'start_server', side_effect=lambda port, stub=False: self.serve()) as st, \
                mock.patch.object(launcher, 'hub_windows', return_value=[]):
            self.assertEqual(launcher.open_hub(self.port, stub=True), 0)
        st.assert_called_once_with(self.port, True)
        self.assertEqual(self.opened, ['http://127.0.0.1:%d/' % self.port])

    def test_an_open_window_is_brought_back_instead(self):
        self.serve()
        with mock.patch.object(launcher, 'hub_windows', return_value=[4242]), \
                mock.patch.object(launcher, 'focus', return_value=True) as fo:
            self.assertEqual(launcher.open_hub(self.port), 0)
        fo.assert_called_once_with(4242)
        self.assertEqual(self.opened, [])

    def test_a_server_that_never_answers_is_a_plain_message(self):
        with mock.patch.object(launcher, 'start_server'), mock.patch.object(launcher, 'wait_ready', return_value=False):
            self.assertEqual(launcher.open_hub(self.port), 1)
        self.assertEqual(self.opened, [])
        self.assertEqual(len(self.messages), 1)
        self.assertIn("didn't start", self.messages[0])

    def test_another_program_on_the_port_is_not_the_hub(self):
        with socket.socket() as s:                    # something that is not the Hub holds the port
            s.bind(('127.0.0.1', self.port))
            s.listen(1)
            self.assertFalse(launcher.ping(self.port, timeout=0.5))


if __name__ == '__main__':
    unittest.main()

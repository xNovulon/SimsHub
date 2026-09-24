"""The Hub's updater (speedkit/hub/update.py) against a stand-in GitHub: nothing goes over the network, and it updates a
temporary folder only (never this checkout)."""
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
from speedkit.hub import launcher, update  # noqa: E402


class FakeGitHub:
    """Commits of the repository: {commit: {path in the repo: bytes}}; the newest is the branch's head."""

    def __init__(self):
        self.commits, self.head, self.fail, self.calls = {}, None, set(), []

    def push(self, files):
        commit = ('%040x' % (len(self.commits) + 1))
        self.commits[commit] = dict(files)
        self.head = commit
        return commit

    def fetch(self, url, accept=None, timeout=60):
        self.calls.append(url)
        if url == '%s/commits/%s' % (update.API, update.BRANCH):
            if 'offline' in self.fail:
                raise urllib.error.URLError('offline')
            return self.head.encode()
        if url.startswith(update.API + '/git/trees/'):
            commit = url.rsplit('/', 1)[1].split('?')[0]
            tree = [{'path': p, 'mode': '100644', 'type': 'blob', 'sha': update.blob_sha(d)} for p, d in self.commits[commit].items()]
            tree.append({'path': 'sims_hub', 'mode': '040000', 'type': 'tree', 'sha': 'x'})
            return json.dumps({'sha': commit, 'tree': tree, 'truncated': False}).encode()
        if url.startswith(update.RAW + '/'):
            commit, path = url[len(update.RAW) + 1:].split('/', 1)
            path = urllib.parse.unquote(path)
            if path in self.fail:
                raise urllib.error.URLError('lost connection')
            return self.commits[commit][path]
        raise AssertionError('unexpected URL ' + url)


class Update(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='hubupdate_')
        self.root = os.path.join(self.tmp, 'sims4_speedkit')
        os.makedirs(self.root)
        self.gh = FakeGitHub()
        self.patches = [mock.patch.object(update, 'fetch', side_effect=self.gh.fetch),
                        mock.patch.object(update, 'DIR', os.path.join(self.tmp, 'state')),
                        mock.patch.object(update.time, 'sleep'),
                        mock.patch.dict(os.environ, {'SIMS_HUB_NO_UPDATE': ''})]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, data):
        path = os.path.join(self.root, *rel.split('/'))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)

    def read(self, rel):
        with open(os.path.join(self.root, *rel.split('/')), 'rb') as f:
            return f.read()

    def exists(self, rel):
        return os.path.exists(os.path.join(self.root, *rel.split('/')))

    def backups(self):
        folder = os.path.join(update.DIR, 'backup')
        return sorted(os.listdir(folder)) if os.path.isdir(folder) else []

    def test_blob_sha_is_gits(self):
        self.assertEqual(update.blob_sha(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')
        self.assertEqual(update.blob_sha(b'hello\n'), 'ce013625030ba8dba906f756967f9e9ca394464a')

    def test_first_update_brings_the_folder_level_and_keeps_own_files(self):
        self.write('speedkit/a.py', b'print(1)\r\nprint(2)\r\n')        # the same as GitHub's, with Windows line ends
        self.write('speedkit/b.py', b'old\n')                            # older than GitHub's
        self.write('data/hub.log', b'my log\n')                          # not on GitHub: never touched
        self.gh.push({'sims_hub/speedkit/a.py': b'print(1)\nprint(2)\n', 'sims_hub/speedkit/b.py': b'new\n',
                      'sims_hub/speedkit/c.py': b'added\n', 'wicked_animator/x.js': b'not the Hub\n',
                      "sims_hub/Start Novulon's Sims Hub.bat": b'@echo off\ngoto open\n:open\n'})
        r = update.run(self.root)
        self.assertEqual((r['changed'], r['commit'], r['complete']), (3, self.gh.head, True))
        self.assertEqual(self.read('speedkit/a.py'), b'print(1)\r\nprint(2)\r\n')     # not downloaded again
        self.assertEqual(self.read('speedkit/b.py'), b'new\n')
        self.assertEqual(self.read('speedkit/c.py'), b'added\n')
        self.assertEqual(self.read("Start Novulon's Sims Hub.bat"), b'@echo off\r\ngoto open\r\n:open\r\n')
        self.assertEqual(self.read('data/hub.log'), b'my log\n')
        self.assertFalse(self.exists('x.js') or self.exists('wicked_animator'))
        # before the first update nothing says a file is GitHub's: the replaced one is kept in the backup
        [b] = self.backups()
        with open(os.path.join(update.DIR, 'backup', b, 'speedkit', 'b.py'), 'rb') as f:
            self.assertEqual(f.read(), b'old\n')
        self.assertFalse(os.path.exists(os.path.join(update.DIR, 'staging')))

    def test_up_to_date_is_one_request(self):
        self.gh.push({'sims_hub/a.py': b'1\n'})
        update.run(self.root)
        self.gh.calls.clear()
        self.assertEqual(update.run(self.root)['changed'], 0)
        self.assertEqual(len(self.gh.calls), 1)
        self.assertIsNone(update.waiting(self.root))
        self.gh.push({'sims_hub/a.py': b'2\n'})
        self.assertEqual(update.waiting(self.root), self.gh.head)

    def test_next_update_backs_up_only_your_own_edits_and_removes_unchanged_files(self):
        self.gh.push({'sims_hub/mine.py': b'v1\n', 'sims_hub/theirs.py': b'v1\n',
                      'sims_hub/gone.py': b'v1\n', 'sims_hub/gone_edited.py': b'v1\n'})
        update.run(self.root)
        shutil.rmtree(os.path.join(update.DIR, 'backup'), ignore_errors=True)
        self.write('mine.py', b'my edit\n')
        self.write('gone_edited.py', b'my edit\n')
        self.gh.push({'sims_hub/mine.py': b'v2\n', 'sims_hub/theirs.py': b'v2\n'})
        r = update.run(self.root)
        self.assertEqual(self.read('mine.py'), b'v2\n')
        self.assertEqual(self.read('theirs.py'), b'v2\n')
        self.assertFalse(self.exists('gone.py'))
        self.assertEqual(self.read('gone_edited.py'), b'my edit\n')     # edited here: stays
        self.assertEqual(r['changed'], 3)
        [b] = self.backups()
        self.assertEqual(os.listdir(os.path.join(update.DIR, 'backup', b)), ['mine.py'])

    def test_a_failed_download_changes_nothing_and_is_tried_again(self):
        self.gh.push({'sims_hub/a.py': b'v1\n', 'sims_hub/b.py': b'v1\n'})
        update.run(self.root)
        self.gh.push({'sims_hub/a.py': b'v2\n', 'sims_hub/b.py': b'v2\n'})
        self.gh.fail.add('sims_hub/b.py')
        r = update.run(self.root)
        self.assertEqual((r['changed'], r['commit']), (0, None))
        self.assertEqual((self.read('a.py'), self.read('b.py')), (b'v1\n', b'v1\n'))
        self.gh.fail.clear()
        self.assertEqual(update.run(self.root)['changed'], 2)
        self.assertEqual((self.read('a.py'), self.read('b.py')), (b'v2\n', b'v2\n'))

    def test_a_download_that_does_not_match_is_refused(self):
        self.gh.push({'sims_hub/a.py': b'v1\n'})
        real = self.gh.fetch
        with mock.patch.object(update, 'fetch', side_effect=lambda url, *a, **k: b'tampered' if url.startswith(update.RAW)
                               else real(url, *a, **k)):
            self.assertEqual(update.run(self.root)['changed'], 0)
        self.assertFalse(self.exists('a.py'))

    def test_offline_opens_as_it_is(self):
        self.gh.push({'sims_hub/a.py': b'v1\n'})
        self.gh.fail.add('offline')
        self.assertEqual(update.run(self.root), {'changed': 0, 'commit': None, 'complete': True})
        self.assertFalse(self.exists('a.py'))

    def test_paths_never_leave_the_folder(self):
        self.gh.push({'sims_hub/../evil.py': b'x\n', 'sims_hub/ok.py': b'ok\n'})
        update.run(self.root)
        self.assertTrue(self.exists('ok.py'))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, 'evil.py')))

    def test_a_git_checkout_is_left_to_git(self):
        os.makedirs(os.path.join(self.tmp, '.git'))
        with open(os.path.join(self.tmp, '.git', 'config'), 'w') as f:
            f.write('[remote "origin"]\n\turl = https://github.com/%s/%s\n' % (update.OWNER, update.REPO))
        self.gh.push({'sims_hub/a.py': b'v1\n'})
        self.assertEqual(update.run(self.root)['changed'], 0)
        self.assertEqual(self.gh.calls, [])

    def test_switched_off(self):
        self.gh.push({'sims_hub/a.py': b'v1\n'})
        with mock.patch.dict(os.environ, {'SIMS_HUB_NO_UPDATE': '1'}):
            self.assertEqual(update.run(self.root)['changed'], 0)
        self.assertEqual(self.gh.calls, [])

    def test_files_only_developers_need_are_left_out(self):
        self.write('tests/old_test.py', b'mine\n')                     # a copy already here stays as it is
        self.gh.push({'sims_hub/speedkit/a.py': b'1\n', 'sims_hub/tests/test_a.py': b't\n', 'sims_hub/tests/old_test.py': b'new\n',
                      'sims_hub/research/big.bin': b'x' * 100, 'sims_hub/research/merging/companions.json': b'{}\n',
                      'sims_hub/desktop/Program.cs': b'//\n'})
        r = update.run(self.root)
        self.assertEqual(r['changed'], 2)
        self.assertEqual(self.read('research/merging/companions.json'), b'{}\n')
        self.assertFalse(self.exists('tests/test_a.py') or self.exists('research/big.bin') or self.exists('desktop'))
        self.assertEqual(self.read('tests/old_test.py'), b'mine\n')

    def test_only_three_backups_are_kept(self):
        for i in range(5):
            os.makedirs(os.path.join(update.DIR, 'backup', '2026-01-0%d_000000' % (i + 1)))
        update._prune(os.path.join(update.DIR, 'backup'))
        self.assertEqual(self.backups(), ['2026-01-03_000000', '2026-01-04_000000', '2026-01-05_000000'])


class LauncherUpdates(unittest.TestCase):
    """The launcher updates a stopped Hub, and restarts a running one only when that is safe."""

    def run_first(self, info, windows=(), waiting='f' * 40):
        with mock.patch.object(launcher, 'hub_info', return_value=info), \
                mock.patch.object(launcher, 'hub_windows', return_value=list(windows)), \
                mock.patch.object(launcher, 'ping', return_value=False), \
                mock.patch.object(update, 'waiting', return_value=waiting), \
                mock.patch.object(update, 'run') as run, \
                mock.patch.object(launcher.os, 'kill') as kill:
            launcher.update_first(8766)
        return run, kill

    def test_not_running_updates(self):
        run, kill = self.run_first(None)
        run.assert_called_once_with()
        kill.assert_not_called()

    def test_idle_hub_is_restarted_for_an_update(self):
        run, kill = self.run_first({'app': launcher.APP, 'pid': 99999, 'busy': False})
        kill.assert_called_once()
        run.assert_called_once_with(commit='f' * 40)

    def test_busy_open_or_old_hub_is_left_running(self):
        for info, windows in (({'pid': 99999, 'busy': True}, ()), ({'pid': 99999, 'busy': False}, (1,)),
                              ({'busy': False}, ()), ({'pid': os.getpid(), 'busy': False}, ())):
            run, kill = self.run_first(dict(info, app=launcher.APP), windows)
            run.assert_not_called()
            kill.assert_not_called()

    def test_nothing_new_leaves_it_running(self):
        run, kill = self.run_first({'app': launcher.APP, 'pid': 99999, 'busy': False}, waiting=None)
        run.assert_not_called()
        kill.assert_not_called()

    def test_an_update_problem_never_stops_the_hub_opening(self):
        with mock.patch.object(launcher, 'hub_info', side_effect=RuntimeError('boom')):
            launcher.update_first(8766)


if __name__ == '__main__':
    unittest.main()

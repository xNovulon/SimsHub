"""Tier-1 tests for ingame/novulon/common.py: path resolution, logging, guarded(). Pure Python 3.12, no
game/DLL needed - mirrors test_ingame.py's own split (pure logic tests run here; the Tier-2 in-game-DLL
import is a separate, heavier test not duplicated for every small helper module)."""
import os
import shutil
import sys
import tempfile
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import common  # noqa: E402


class TestFindSimsDir(unittest.TestCase):
    def test_mods_root(self):
        p = r'C:\Users\x\Documents\Electronic Arts\The Sims 4\Mods\Novulon.ts4script\novulon\common.pyc'
        self.assertEqual(common.find_sims_dir(p),
                          r'C:\Users\x\Documents\Electronic Arts\The Sims 4')

    def test_one_folder_down(self):
        p = (r'C:\Users\x\Documents\Electronic Arts\The Sims 4\Mods\SomeFolder\Novulon.ts4script'
             r'\novulon\common.pyc')
        self.assertEqual(common.find_sims_dir(p),
                          r'C:\Users\x\Documents\Electronic Arts\The Sims 4')

    def test_mods_mods_prefers_outer(self):
        # Mods\Mods\X.ts4script: both readings are possible; the folder holding Options.ini/Config.log wins
        with tempfile.TemporaryDirectory() as tmp:
            sims = os.path.join(tmp, 'The Sims 4')
            os.makedirs(os.path.join(sims, 'Mods', 'Mods'))
            open(os.path.join(sims, 'Options.ini'), 'w').close()
            p = os.path.join(sims, 'Mods', 'Mods', 'Novulon.ts4script', 'novulon', 'common.pyc')
            self.assertEqual(common.find_sims_dir(p), sims)

    def test_no_ts4script_in_path(self):
        self.assertIsNone(common.find_sims_dir(r'C:\some\random\path\common.py'))

    def test_none_input(self):
        self.assertIsNone(common.find_sims_dir(None))
        self.assertIsNone(common.find_sims_dir(''))


class TestArchiveOf(unittest.TestCase):
    def test_extracts_archive_name(self):
        p = r'C:\Sims\Mods\Novulon.ts4script\novulon\common.pyc'
        self.assertEqual(common.archive_of(p), 'Novulon.ts4script')

    def test_no_archive(self):
        self.assertIsNone(common.archive_of(r'C:\Sims\Mods\notanarchive.py'))
        self.assertIsNone(common.archive_of(None))


class TestConfigureAndDirs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)

    def tearDown(self):
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sims_dir_configured(self):
        self.assertEqual(common.sims_dir(), self.tmp)

    def test_novulon_dir_under_sims_dir_never_mods(self):
        d = common.novulon_dir()
        self.assertEqual(d, os.path.join(self.tmp, 'Novulon'))
        self.assertNotIn('Mods', d)

    def test_logs_dir_created_on_first_use(self):
        d = common.logs_dir()
        self.assertTrue(os.path.isdir(d))
        self.assertEqual(d, os.path.join(self.tmp, 'Novulon', 'logs'))

    def test_none_sims_dir_gives_none_everywhere(self):
        common.configure(None)
        self.assertIsNone(common.novulon_dir())
        self.assertIsNone(common.logs_dir())


class TestLogging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)

    def tearDown(self):
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_log_writes_line(self):
        common.log('hello world')
        path = os.path.join(self.tmp, 'Novulon', 'logs', 'novulon.log')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('hello world', text)

    def test_log_never_raises_with_no_sims_dir(self):
        common.configure(None)
        common.log('should be swallowed silently')   # must not raise

    def test_log_exception_includes_traceback(self):
        try:
            raise ValueError('boom')
        except ValueError:
            common.log_exception('test context')
        path = os.path.join(self.tmp, 'Novulon', 'logs', 'novulon.log')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('ERROR in test context', text)
        self.assertIn('ValueError: boom', text)

    def test_log_rotates_past_max_bytes(self):
        old_max = common.LOG_MAX_BYTES
        common.LOG_MAX_BYTES = 10
        try:
            common.log('first line is already over ten bytes')
            common.log('second line triggers rotation')
        finally:
            common.LOG_MAX_BYTES = old_max
        d = os.path.join(self.tmp, 'Novulon', 'logs')
        self.assertTrue(os.path.isfile(os.path.join(d, 'novulon.log')))
        self.assertTrue(os.path.isfile(os.path.join(d, 'novulon.log.1')))


class TestGuarded(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)

    def tearDown(self):
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_value_on_success(self):
        self.assertEqual(common.guarded('ok', lambda a, b: a + b, 1, 2), 3)

    def test_swallows_exception_and_logs(self):
        def boom():
            raise RuntimeError('nope')
        result = common.guarded('novulon: boom test', boom)
        self.assertIsNone(result)
        path = os.path.join(self.tmp, 'Novulon', 'logs', 'novulon.log')
        with open(path, encoding='utf-8') as f:
            text = f.read()
        self.assertIn('novulon: boom test', text)
        self.assertIn('RuntimeError: nope', text)

    def test_passes_kwargs(self):
        result = common.guarded('kw', lambda a, b=0: a + b, 1, b=5)
        self.assertEqual(result, 6)


class TestReadJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_returns_none(self):
        self.assertIsNone(common.read_json(os.path.join(self.tmp, 'nope.json')))

    def test_valid_json(self):
        p = os.path.join(self.tmp, 'x.json')
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{"a": 1}')
        self.assertEqual(common.read_json(p), {'a': 1})

    def test_invalid_json_returns_none(self):
        p = os.path.join(self.tmp, 'bad.json')
        with open(p, 'w', encoding='utf-8') as f:
            f.write('{not valid json')
        self.assertIsNone(common.read_json(p))


if __name__ == '__main__':
    unittest.main(verbosity=1)

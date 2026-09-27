"""Tests for tools/build_novulon.py.

sources()/verify() are pure Python (Tier 1). BuildTests drives a real compile through the game's own
python37_x64.dll (skipped where that DLL is not present), against a throwaway fake package under
E:\\speedkit_test - never against the real ingame/novulon (owned by other build packages, may not exist
yet in this working tree) and never against E:\\The Sims 4 itself; the game is never started.
"""
import os
import shutil
import sys
import textwrap
import unittest
import zipfile

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

from tools import build_novulon, game_python  # noqa: E402

SCRATCH = r'E:\speedkit_test\novulon_build' if os.path.isdir('E:\\') else os.path.join(PROJECT, '_test_scratch')

FAKE_PACKAGE = {
    '__init__.py': '# top-level package init\n',
    'common.py': 'VERSION = "1.0"\n',
    'menukit/__init__.py': '',
    'menukit/page.py': textwrap.dedent('''\
        class Row:
            def __init__(self, id):
                self.id = id
        '''),
    'sims/__init__.py': '',
    'sims/query.py': textwrap.dedent('''\
        def matches(sim_info):
            return True
        '''),
    'sims/nested/__init__.py': '',
    'sims/nested/deep.py': 'X = 1\n',
}


def _write_fake_package(root):
    if os.path.exists(root):
        shutil.rmtree(root)
    for rel, content in FAKE_PACKAGE.items():
        p = os.path.join(root, *rel.split('/'))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(content)
    # a __pycache__ folder must never be treated as a source
    cache = os.path.join(root, '__pycache__')
    os.makedirs(cache, exist_ok=True)
    with open(os.path.join(cache, 'common.cpython-312.pyc'), 'wb') as f:
        f.write(b'not really a pyc')


class SourcesTests(unittest.TestCase):
    """Pure Python, no game needed: the os.walk collector itself."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(SCRATCH, 'sources_fixture')
        os.makedirs(SCRATCH, exist_ok=True)
        _write_fake_package(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_finds_every_py_file_subpackage_aware(self):
        rels = sorted(rel for _abs, rel in build_novulon.sources(self.root))
        self.assertEqual(rels, sorted(FAKE_PACKAGE))

    def test_skips_pycache(self):
        for _abs, rel in build_novulon.sources(self.root):
            self.assertNotIn('__pycache__', rel)

    def test_abs_paths_exist_and_match_rel(self):
        for abspath, rel in build_novulon.sources(self.root):
            self.assertTrue(os.path.isfile(abspath))
            self.assertEqual(os.path.relpath(abspath, self.root).replace(os.sep, '/'), rel)

    def test_default_src_dir_is_ingame_novulon(self):
        self.assertEqual(os.path.normcase(build_novulon.SRC),
                         os.path.normcase(os.path.join(PROJECT, 'ingame', 'novulon')))


def _magic_ok(data):
    return len(data) >= 16 and int.from_bytes(data[:2], 'little') == 3394 and data[2:4] == b'\r\n'


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found')
class BuildTests(unittest.TestCase):
    """Compiles the fake package above with the game's real 3.7 interpreter - never the real ingame/novulon."""

    @classmethod
    def setUpClass(cls):
        cls.root = os.path.join(SCRATCH, 'build_fixture')
        os.makedirs(SCRATCH, exist_ok=True)
        _write_fake_package(cls.root)
        cls.dist = os.path.join(SCRATCH, 'FakeNovulon.ts4script')
        cls.result = build_novulon.build(src_dir=cls.root, dist=cls.dist)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)
        if os.path.exists(cls.dist):
            os.remove(cls.dist)

    def test_build_reports_python_37_and_correct_magic(self):
        self.assertTrue(self.result['python'].startswith('3.7.0'))
        self.assertEqual(self.result['magic'], '420d0d0a')

    def test_verify_is_clean(self):
        self.assertEqual(build_novulon.verify(self.dist), [])

    def test_archive_preserves_subpackage_layout(self):
        expected = sorted('novulon/%s.pyc' % rel[:-3] for rel in FAKE_PACKAGE)
        with zipfile.ZipFile(self.dist) as z:
            self.assertEqual(sorted(z.namelist()), expected)
            for n in z.namelist():
                data = z.read(n)
                self.assertTrue(_magic_ok(data), n)
                self.assertEqual(z.getinfo(n).compress_type, zipfile.ZIP_DEFLATED)

    def test_no_py_files_in_the_archive(self):
        with zipfile.ZipFile(self.dist) as z:
            for n in z.namelist():
                self.assertFalse(n.endswith('.py'), n)


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found')
class RealNovulonSourceTests(unittest.TestCase):
    """Only runs once other build packages have finished populating ingame/novulon/ (an __init__.py exists)
    - skipped until then, so this file never fails because of another package's own work-in-progress files
    in this shared working tree, which this package (BP13/BP14) does not own or control the timing of."""

    def test_real_source_tree_builds_if_present(self):
        if not os.path.isfile(os.path.join(build_novulon.SRC, '__init__.py')):
            self.skipTest('ingame/novulon/__init__.py does not exist yet (owned by other build packages)')
        dist = os.path.join(SCRATCH, 'Novulon_real_test.ts4script')
        try:
            r = build_novulon.build(dist=dist)
            self.assertEqual(build_novulon.verify(r['dist']), [])
            with zipfile.ZipFile(r['dist']) as z:
                self.assertIn('novulon/__init__.pyc', z.namelist())
        finally:
            if os.path.exists(dist):
                os.remove(dist)


if __name__ == '__main__':
    unittest.main(verbosity=2)

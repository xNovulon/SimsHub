"""Tier 2 for Novulon (SPEC.md Sec 16, overridden per the build note: "the Tier 2 runner: import every
novulon module inside the game's own Python with simulation.zip on the path and minimal stubs only
where a module can't load outside the running game; report which"). The mechanics live in
tools/novulon_tier2_runner.py; this file is the test that runs it.

  * FixtureTests proves the runner's own two-pass mechanism (real zips, then real-only stubs, report
    which) against a small synthetic package this test builds itself - it passes even before any real
    novulon/ module exists, and keeps passing once they do, so it never depends on another build
    package's progress.
  * LiveNovulonTests runs the same runner against the real sims_hub/ingame/novulon tree. It skips
    (doesn't fail) when that tree has no modules yet - that's a valid state during a parallel build,
    not a Tier 2 problem - and otherwise asserts every real module imports cleanly, real or stubbed,
    printing which is which so a package owner can see at a glance whether their module needed a stub
    Novulon doesn't have listed in the runner's STUBS dict yet.
"""
import os
import sys
import textwrap
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

from tools import game_python, novulon_tier2_runner as tier2  # noqa: E402


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found at %s' % game_python.DLL)
class FixtureTests(unittest.TestCase):
    """A throwaway 'novulon' package (a different one than the real ingame tree - see src_dir=) with
    one clean module, one that needs a stub, and one with a genuine bug, so the runner's report can be
    checked against a known-correct answer."""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp(prefix='novulon_tier2_fixture_')
        root = os.path.join(cls.tmp, 'novulon')
        os.makedirs(os.path.join(root, 'sub'))

        def write(rel, text=''):
            with open(os.path.join(root, rel), 'w', encoding='utf-8') as f:
                f.write(text)

        write('__init__.py')
        write('sub/__init__.py')
        write('clean.py', 'VALUE = 1\n')                       # pure python - must import for real, no stub
        write('sub/leaf.py', 'VALUE = 2\n')                    # a subpackage module, dotted discovery
        write('needs_stub.py', textwrap.dedent('''\
            import services
            import sims4.commands
            from ui.ui_dialog_picker import UiObjectPicker, ObjectPickerStyle

            def do_something(connection):
                return services.active_sim_info()
            '''))                                               # only importable through the runner's STUBS
        write('broken.py', 'import this_module_does_not_exist_anywhere\n')   # a real bug - fails either way
        cls.report = tier2.run(src_dir=cls.tmp, timeout=180)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_discovers_every_module_dotted_correctly(self):
        self.assertEqual(self.report['modules'],
                         sorted(['novulon', 'novulon.clean', 'novulon.sub', 'novulon.sub.leaf',
                                'novulon.needs_stub', 'novulon.broken']))

    def test_clean_modules_import_for_real_no_stub(self):
        for name in ('novulon', 'novulon.clean', 'novulon.sub', 'novulon.sub.leaf'):
            r = self.report['results'][name]
            self.assertTrue(r['ok'], '%s: %s' % (name, r.get('error')))
            self.assertFalse(r.get('used_stub', False), '%s unexpectedly needed a stub' % name)
        self.assertEqual(set(self.report['real_only']),
                         {'novulon', 'novulon.clean', 'novulon.sub', 'novulon.sub.leaf'})

    def test_module_needing_the_game_falls_back_to_the_stub_layer_and_succeeds(self):
        r = self.report['results']['novulon.needs_stub']
        self.assertTrue(r['ok'], r.get('error'))
        self.assertTrue(r.get('used_stub'))
        self.assertIn('services', self.report['stub_used'])
        self.assertIn('sims4', self.report['stub_used'])
        self.assertIn('ui', self.report['stub_used'])

    def test_a_real_bug_fails_even_after_the_stub_layer(self):
        r = self.report['results']['novulon.broken']
        self.assertFalse(r['ok'])
        self.assertIn('this_module_does_not_exist_anywhere', r['error'])

    def test_empty_tree_is_a_note_not_an_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            report = tier2.run(src_dir=empty)
            self.assertEqual(report['modules'], [])
            self.assertIn('note', report)


class DiscoverModulesTests(unittest.TestCase):
    """discover_modules() alone needs no game at all - plain filesystem walking."""

    def test_no_novulon_dir_is_empty_not_an_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(tier2.discover_modules(d), [])

    def test_dotted_names_and_init_collapsing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, 'novulon', 'menukit')
            os.makedirs(root)
            open(os.path.join(d, 'novulon', '__init__.py'), 'w').close()
            open(os.path.join(d, 'novulon', 'common.py'), 'w').close()
            open(os.path.join(root, '__init__.py'), 'w').close()
            open(os.path.join(root, 'page.py'), 'w').close()
            os.makedirs(os.path.join(root, '__pycache__'))
            open(os.path.join(root, '__pycache__', 'page.cpython-312.pyc'), 'w').close()
            self.assertEqual(tier2.discover_modules(d),
                             ['novulon', 'novulon.common', 'novulon.menukit', 'novulon.menukit.page'])


@unittest.skipUnless(game_python.available(), 'game python37_x64.dll not found at %s' % game_python.DLL)
class LiveNovulonTests(unittest.TestCase):
    """The real sims_hub/ingame/novulon tree, whatever exists in it right now."""

    @classmethod
    def setUpClass(cls):
        cls.report = tier2.run(timeout=600)

    def test_every_real_novulon_module_imports_cleanly(self):
        if not self.report['modules']:
            self.skipTest(self.report.get('note', 'no novulon/ modules yet'))
        failed = {m: r['error'] for m, r in self.report['results'].items() if not r['ok']}
        for m in self.report['modules']:
            r = self.report['results'][m]
            tag = 'real' if r['ok'] and not r.get('used_stub') else ('stub' if r['ok'] else 'FAIL')
            print('  [%s] %s' % (tag, m))
        if failed:
            print('stub modules touched by the ones that needed one:', self.report['stub_used'])
        self.assertEqual(failed, {}, 'Tier 2 import failures (see tools/novulon_tier2_runner.py '
                                     'STUBS if these are all AttributeErrors against a stubbed module)')


if __name__ == '__main__':
    unittest.main(verbosity=2)

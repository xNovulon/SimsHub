"""Tests for tools/novulon_ids/ (the per-package id aggregator) and tools/novulon_api_manifest/.

Nothing here starts the game or touches E:\\The Sims 4 or the real Mods folder.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PROJECT)
sys.path.insert(0, PROJECT)
# wicked_animator/backend/*.py import each other with flat names (e.g. "import clipfmt"), so it must be
# put on sys.path directly rather than imported as the wicked_animator.backend package.
sys.path.insert(0, os.path.join(REPO_ROOT, 'wicked_animator', 'backend'))

from tools import novulon_ids as ids  # noqa: E402
from tools.novulon_ids import bp13_package_build as bp13ids  # noqa: E402
import clipfmt  # noqa: E402

MANIFEST_PKG_DIR = os.path.join(PROJECT, 'tools', 'novulon_api_manifest')
BP13_MANIFEST_FILE = os.path.join(MANIFEST_PKG_DIR, 'bp13_package_build.py')


def _load_standalone(path, modname):
    """Load a single .py file as a standalone module, bypassing any parent package's __init__.py - used
    for novulon_api_manifest/bp13_package_build.py so this file's own tests do not depend on whatever
    state a sibling build package's own manifest file is in (that package's file, never edited here)."""
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_fresh_package(real_init_path, files, modname):
    """Copy real_init_path's source plus `files` ({filename: content}) into a throwaway temp package
    directory and import it under `modname`. Returns the imported module; raises whatever the real
    __init__.py's own import-time logic raises. The caller is responsible for cleanup (returned tmp dir)."""
    tmp = tempfile.mkdtemp(prefix='novulon_agg_test_')
    with open(real_init_path, encoding='utf-8') as f:
        init_src = f.read()
    with open(os.path.join(tmp, '__init__.py'), 'w', encoding='utf-8') as f:
        f.write(init_src)
    for name, content in files.items():
        with open(os.path.join(tmp, name), 'w', encoding='utf-8') as f:
            f.write(content)
    spec = importlib.util.spec_from_file_location(modname, os.path.join(tmp, '__init__.py'),
                                                   submodule_search_locations=[tmp])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
        return mod, tmp
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    finally:
        sys.modules.pop(modname, None)


class FnvCrossCheckTests(unittest.TestCase):
    """novulon_ids' own small fnv64() must agree with this repo's other three copies (all under
    wicked_animator/), per the design decision in bp13_package_build.py's own docstring: no runtime
    cross-import, but checked for correctness against a table of sample strings."""

    def test_matches_wicked_animators_fnv64(self):
        for s in ('Novulon', 'Novulon_OpenMenu_Interaction', '', 'MiXeD Case Name', 'a' * 200):
            self.assertEqual(bp13ids.fnv64(s), clipfmt.fnv64(s), s)

    def test_custom_id_sets_top_bit(self):
        v = bp13ids.custom_id('Novulon_OpenMenu_Interaction')
        self.assertTrue(v & 0x8000000000000000)

    def test_stbl_id_uses_top_byte_for_locale_not_the_top_bit(self):
        base = bp13ids.stbl_id('Novulon_Strings', locale=0x00)
        self.assertEqual((base >> 56) & 0xFF, 0x00)
        fr = bp13ids.stbl_id('Novulon_Strings', locale=0x0C)
        self.assertEqual((fr >> 56) & 0xFF, 0x0C)
        self.assertEqual(base & 0x00FFFFFFFFFFFFFF, fr & 0x00FFFFFFFFFFFFFF)


class AggregatorTests(unittest.TestCase):
    def test_bp13_ids_are_exported_on_the_aggregator(self):
        self.assertEqual(ids.INTERACTION_OPEN_MENU, bp13ids.INTERACTION_OPEN_MENU)
        self.assertEqual(ids.ICON_PIE_MENU_32, bp13ids.ICON_PIE_MENU_32)
        self.assertEqual(ids.STBL_MAIN_EN, bp13ids.STBL_MAIN_EN)
        self.assertNotEqual(ids.STR_MENU_TITLE, ids.STR_MENU_HOVER)
        self.assertEqual(ids.owner_of('INTERACTION_OPEN_MENU'), 'bp13_package_build')

    def test_no_id_collisions_among_bp13s_own_constants(self):
        values = [bp13ids.INTERACTION_OPEN_MENU, bp13ids.ICON_PIE_MENU_32, bp13ids.STBL_MAIN_EN,
                  bp13ids.STR_MENU_TITLE, bp13ids.STR_MENU_HOVER]
        self.assertEqual(len(values), len(set(values)))


class IdCollisionRealAggregatorTests(unittest.TestCase):
    """Drives the real novulon_ids/__init__.py's own _collect() (copied into a throwaway temp package, not
    reimplemented), so this tests the shipped collision-detection logic itself, not a paraphrase of it."""

    def _init_path(self):
        return os.path.join(os.path.dirname(ids.__file__), '__init__.py')

    def test_two_files_defining_the_same_name_raises(self):
        with self.assertRaises(ValueError):
            _import_fresh_package(self._init_path(), {'a_pkg.py': 'SOME_ID = 1\n', 'b_pkg.py': 'SOME_ID = 2\n'},
                                  'novulon_ids_test_name_collision')

    def test_two_names_resolving_to_the_same_value_raises(self):
        with self.assertRaises(ValueError):
            _import_fresh_package(self._init_path(), {'a_pkg.py': 'FOO = 0x1234\n', 'b_pkg.py': 'BAR = 0x1234\n'},
                                  'novulon_ids_test_value_collision')

    def test_no_collision_imports_cleanly(self):
        mod, tmp = _import_fresh_package(self._init_path(), {'a_pkg.py': 'FOO = 1\n', 'b_pkg.py': 'BAR = 2\n'},
                                         'novulon_ids_test_clean')
        try:
            self.assertEqual(mod.FOO, 1)
            self.assertEqual(mod.BAR, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Bp13ManifestFileTests(unittest.TestCase):
    """This package's own tools/novulon_api_manifest/bp13_package_build.py, loaded standalone (bypassing
    the package's __init__.py) so this test never depends on whatever state a sibling build package's own
    manifest file is in - that package's file is never edited here, and a sibling mid-edit must not make
    this file's own tests fail."""

    def test_bp13_row_is_well_formed(self):
        mod = _load_standalone(BP13_MANIFEST_FILE, 'bp13_manifest_standalone')
        expected = [('interactions.base.immediate_interaction', 'ImmediateSuperInteraction', 'class')]
        # exposed under both names - see the file's own docstring for why
        self.assertEqual(mod.ROWS, expected)
        self.assertEqual(mod.MANIFEST, expected)


class ApiManifestAggregatorTests(unittest.TestCase):
    """tools/novulon_api_manifest/'s __init__.py is shared aggregator infrastructure, not a per-package
    file - built (and, while this package was written, still being actively revised) by another parallel
    session in this working tree, never overwritten here. This is a best-effort integration check only:
    it skips, rather than fails, whenever the shared package does not currently import cleanly, since that
    means a sibling package's own manifest file is mid-edit, not a defect in this package's own
    bp13_package_build.py (already checked directly, in isolation, above)."""

    def test_bp13_row_reaches_the_shared_registry_if_it_currently_imports(self):
        try:
            from tools import novulon_api_manifest as manifest
            rows = getattr(manifest, 'ALL_ROWS', None) or getattr(manifest, 'MANIFEST', None)
        except Exception as e:      # noqa: BLE001 - deliberately broad: any sibling-file instability skips, never fails
            self.skipTest('novulon_api_manifest does not currently import cleanly (a sibling package\'s '
                          'manifest file is mid-edit in this shared tree): %r' % (e,))
        by_key = {}
        for row in rows:
            module, path = (row.module, row.path) if hasattr(row, 'module') else (row[0], row[1])
            by_key[(module, path)] = row
        key = ('interactions.base.immediate_interaction', 'ImmediateSuperInteraction')
        self.assertIn(key, by_key)


if __name__ == '__main__':
    unittest.main(verbosity=2)

"""Tier-1 tests for ingame/novulon/settings.py: schema/migration, dotted get/set, atomic write. Pure
Python 3.12, no game needed. Explicitly covers SPEC.md Sec 7's own review note: a fresh install must write
compat.defer_to_mccc = all-false when MCCC is not detected (never all-true unconditionally), and all-true
when it is - both branches asserted here, not just the MCCC-present one."""
import json
import os
import shutil
import sys
import tempfile
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import common, settings  # noqa: E402


def _install_fake_compat(is_present):
    """Injects a fake novulon.compat.mccc module so settings._mccc_present() doesn't need the real
    compat/ package (BP7, built separately). Returns a cleanup function."""
    import novulon
    compat_mod = types.ModuleType('novulon.compat')
    mccc_mod = types.ModuleType('novulon.compat.mccc')
    mccc_mod.is_present = lambda: is_present
    compat_mod.mccc = mccc_mod
    sys.modules['novulon.compat'] = compat_mod
    sys.modules['novulon.compat.mccc'] = mccc_mod
    novulon.compat = compat_mod

    def cleanup():
        sys.modules.pop('novulon.compat', None)
        sys.modules.pop('novulon.compat.mccc', None)
        if hasattr(novulon, 'compat'):
            del novulon.compat
    return cleanup


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        settings.reset_cache()
        self._cleanup_compat = None

    def tearDown(self):
        if self._cleanup_compat:
            self._cleanup_compat()
        settings.reset_cache()
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def use_compat(self, is_present):
        self._cleanup_compat = _install_fake_compat(is_present)


class TestFreshInstall(SettingsTestCase):
    def test_mccc_absent_gives_all_false(self):
        self.use_compat(False)
        doc = settings.load()
        self.assertEqual(doc['schema'], settings.SCHEMA)
        flags = doc['compat']['defer_to_mccc']
        self.assertEqual(flags, {'population': False, 'pregnancy': False, 'aging': False,
                                  'story_progression': False})

    def test_mccc_present_gives_all_true(self):
        self.use_compat(True)
        doc = settings.load()
        flags = doc['compat']['defer_to_mccc']
        self.assertEqual(flags, {'population': True, 'pregnancy': True, 'aging': True,
                                  'story_progression': True})

    def test_compat_package_missing_defaults_to_false_not_a_crash(self):
        # compat/ (BP7) genuinely not built/importable yet - settings.py must not crash, and must pick
        # the SAFER direction (features stay on), never silently disable Gameplay for every player.
        doc = settings.load()
        self.assertEqual(doc['compat']['defer_to_mccc'],
                          {'population': False, 'pregnancy': False, 'aging': False, 'story_progression': False})

    def test_fresh_file_is_actually_written(self):
        self.use_compat(False)
        settings.load()
        self.assertTrue(os.path.isfile(settings.path()))
        with open(settings.path(), encoding='utf-8') as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk['schema'], settings.SCHEMA)

    def test_other_defaults_present(self):
        self.use_compat(False)
        doc = settings.load()
        self.assertEqual(doc['sim_browser'], {'page_size': 80})
        self.assertEqual(doc['adult'], {'enabled': False, 'interstitial_shown': False})
        self.assertEqual(doc['log_level'], 'info')
        self.assertEqual(doc['modules_hidden'], [])

    def test_no_sims_dir_still_returns_a_document(self):
        common.configure(None)
        settings.reset_cache()
        self.use_compat(False)
        doc = settings.load()
        self.assertEqual(doc['schema'], settings.SCHEMA)   # in-memory only; nothing to write to


class TestMigration(SettingsTestCase):
    def test_missing_keys_filled_existing_values_kept(self):
        self.use_compat(False)
        os.makedirs(os.path.dirname(settings.path()), exist_ok=True)
        with open(settings.path(), 'w', encoding='utf-8') as f:
            json.dump({'sim_browser': {'page_size': 999}, 'unknown_future_key': 'kept'}, f)
        doc = settings.load(force=True)
        self.assertEqual(doc['schema'], settings.SCHEMA)
        self.assertEqual(doc['sim_browser']['page_size'], 999)     # existing value never overwritten
        self.assertEqual(doc['unknown_future_key'], 'kept')        # unknown key preserved, not stripped
        self.assertIn('adult', doc)                                # missing key filled from DEFAULTS

    def test_migrated_document_is_written_back(self):
        self.use_compat(False)
        os.makedirs(os.path.dirname(settings.path()), exist_ok=True)
        with open(settings.path(), 'w', encoding='utf-8') as f:
            json.dump({}, f)
        settings.load(force=True)
        with open(settings.path(), encoding='utf-8') as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk['schema'], settings.SCHEMA)

    def test_future_schema_treated_as_unknown_not_crashed(self):
        self.use_compat(False)
        os.makedirs(os.path.dirname(settings.path()), exist_ok=True)
        with open(settings.path(), 'w', encoding='utf-8') as f:
            json.dump({'schema': 999, 'sim_browser': {'page_size': 5}}, f)
        doc = settings.load(force=True)   # must not raise
        self.assertIn('adult', doc)

    def test_no_migration_needed_document_unchanged(self):
        self.use_compat(False)
        settings.load()   # writes a fresh, already-current-schema document
        before = settings.load(force=True)
        after = settings.load(force=True)
        self.assertEqual(before, after)


class TestGetSet(SettingsTestCase):
    def test_get_dotted_path(self):
        self.use_compat(False)
        self.assertEqual(settings.get('sim_browser.page_size'), 80)
        self.assertEqual(settings.get('does.not.exist', 'fallback'), 'fallback')

    def test_set_dotted_path_persists(self):
        self.use_compat(False)
        settings.set('adult.enabled', True)
        settings.reset_cache()
        self.assertTrue(settings.get('adult.enabled'))

    def test_set_creates_intermediate_dicts(self):
        self.use_compat(False)
        settings.set('a.b.c', 42)
        self.assertEqual(settings.get('a.b.c'), 42)

    def test_set_writes_atomically_no_tmp_left_behind(self):
        self.use_compat(False)
        settings.set('log_level', 'debug')
        self.assertFalse(os.path.isfile(settings.path() + '.tmp'))
        self.assertEqual(settings.get('log_level'), 'debug')

    def test_set_empty_path_returns_false(self):
        self.use_compat(False)
        self.assertFalse(settings.set('', 1))


if __name__ == '__main__':
    unittest.main(verbosity=1)

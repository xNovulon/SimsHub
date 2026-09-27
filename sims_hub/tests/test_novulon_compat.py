"""Tier-4-style tests for ingame/novulon/compat/*.py: the shared probe() primitive, MCCC's presence +
should_defer(), WickedWhims's presence/version/accessor pass-throughs, the Wicked Perversions filename
scan, and UI Cheats' documented no-op - all driven with fake game modules / a fake Sims folder, no real
game needed (SPEC.md Sec 16 Tier 4).

`TestWickedWhims.test_is_present_uses_action_type_not_interaction` is a regression test for the real bug
this build found and fixed in the spec's own carried-forward assumption (see compat/wickedwhims.py's
docstring): probing WickedWhims's id against Types.INTERACTION (the type MCCC's own id needs) must NOT
find it - only Types.ACTION may.
"""
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
from novulon import compat as compat_probe  # noqa: E402  (module - .probe()/.reset_cache())
from novulon.compat import mccc  # noqa: E402
from novulon.compat import ui_cheats, wicked_perversions, wickedwhims  # noqa: E402


class FakeInstanceManager(object):
    def __init__(self, known=()):
        self.known = set(known)

    def get(self, instance_id):
        return object() if instance_id in self.known else None


class FakeGameEnv(object):
    """Installs fake `sims4`/`sims4.resources`/`services` modules mirroring compat/*.py's own import
    shape (`import sims4.resources`, `import services`), the same pattern test_novulon_inject.py already
    uses for inject.py. `managers` maps a `Types` member name ('INTERACTION'/'ACTION') to the set of
    instance ids that manager 'has'."""

    def __init__(self, managers=None):
        self.managers = managers or {}

    def __enter__(self):
        fake_sims4 = types.ModuleType('sims4')
        fake_resources = types.ModuleType('sims4.resources')

        class Types(object):
            INTERACTION = 'INTERACTION'
            ACTION = 'ACTION'
        fake_resources.Types = Types
        fake_sims4.resources = fake_resources

        mgrs = {}
        for name, known in self.managers.items():
            mgrs[getattr(Types, name)] = FakeInstanceManager(known)

        fake_services = types.ModuleType('services')
        fake_services.get_instance_manager = lambda t: mgrs.get(t)

        self._saved = {n: sys.modules.get(n) for n in ('sims4', 'sims4.resources', 'services')}
        sys.modules['sims4'] = fake_sims4
        sys.modules['sims4.resources'] = fake_resources
        sys.modules['services'] = fake_services
        return self

    def __exit__(self, *exc):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


class CompatTestCase(unittest.TestCase):
    def setUp(self):
        compat_probe.reset_cache()

    def tearDown(self):
        compat_probe.reset_cache()


class SettingsBackedTestCase(CompatTestCase):
    def setUp(self):
        super(SettingsBackedTestCase, self).setUp()
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        settings.reset_cache()

    def tearDown(self):
        settings.reset_cache()
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        super(SettingsBackedTestCase, self).tearDown()


# ------------------------------------------------------------------ compat.probe()
class TestProbe(CompatTestCase):
    def test_true_when_id_present(self):
        with FakeGameEnv(managers={'INTERACTION': {1}}):
            self.assertTrue(compat_probe.probe('INTERACTION', 1))

    def test_false_when_id_absent(self):
        with FakeGameEnv(managers={'INTERACTION': {1}}):
            self.assertFalse(compat_probe.probe('INTERACTION', 2))

    def test_false_with_no_game_modules_never_raises(self):
        self.assertFalse(compat_probe.probe('INTERACTION', 999))

    def test_cached_after_first_call(self):
        calls = []
        with FakeGameEnv(managers={'INTERACTION': {1}}):
            import services
            real = services.get_instance_manager

            def counting(t):
                calls.append(t)
                return real(t)
            services.get_instance_manager = counting
            self.assertTrue(compat_probe.probe('INTERACTION', 1))
            self.assertTrue(compat_probe.probe('INTERACTION', 1))
            self.assertTrue(compat_probe.probe('INTERACTION', 1))
        self.assertEqual(len(calls), 1)

    def test_reset_cache_forces_a_fresh_probe(self):
        with FakeGameEnv(managers={'INTERACTION': {1}}):
            self.assertTrue(compat_probe.probe('INTERACTION', 1))
        compat_probe.reset_cache()
        with FakeGameEnv(managers={}):
            self.assertFalse(compat_probe.probe('INTERACTION', 1))

    def test_different_keys_cached_independently(self):
        with FakeGameEnv(managers={'INTERACTION': {1}, 'ACTION': {2}}):
            self.assertTrue(compat_probe.probe('INTERACTION', 1))
            self.assertFalse(compat_probe.probe('INTERACTION', 2))
            self.assertTrue(compat_probe.probe('ACTION', 2))


# ------------------------------------------------------------------ compat.mccc
class TestMccc(SettingsBackedTestCase):
    def test_is_present_true(self):
        with FakeGameEnv(managers={'INTERACTION': {mccc.INSTANCE_ID}}):
            self.assertTrue(mccc.is_present())

    def test_is_present_false_when_id_missing(self):
        with FakeGameEnv(managers={'INTERACTION': {0x1}}):
            self.assertFalse(mccc.is_present())

    def test_is_present_false_with_no_game(self):
        self.assertFalse(mccc.is_present())

    def test_is_present_false_when_registered_under_wrong_type(self):
        # MCCC's own id needs Types.INTERACTION specifically - present only under ACTION must not count
        with FakeGameEnv(managers={'ACTION': {mccc.INSTANCE_ID}}):
            self.assertFalse(mccc.is_present())

    def test_should_defer_reads_the_stored_setting(self):
        settings.set('compat.defer_to_mccc.population', True)
        self.assertTrue(mccc.should_defer('population'))
        self.assertFalse(mccc.should_defer('pregnancy'))

    def test_should_defer_unknown_feature_defaults_false(self):
        self.assertFalse(mccc.should_defer('not_a_real_feature'))

    def test_should_defer_does_not_reprobe_mccc(self):
        # should_defer only ever reads the persisted setting - it must not itself call is_present()/probe
        settings.set('compat.defer_to_mccc.aging', True)
        self.assertTrue(mccc.should_defer('aging'))   # no FakeGameEnv active at all - would raise/degrade
                                                        # to False through probe() if should_defer touched it


# ------------------------------------------------------------------ compat.wickedwhims
class TestWickedWhimsPresence(CompatTestCase):
    def test_is_present_true_with_action_type(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            self.assertTrue(wickedwhims.is_present())

    def test_is_present_uses_action_type_not_interaction(self):
        # Regression test for the real bug this build found: the id is only ever registered under
        # Types.ACTION on the actual installed copy - probing it under Types.INTERACTION (the type
        # MCCC's own id needs) must return False, not True.
        with FakeGameEnv(managers={'INTERACTION': {wickedwhims.INSTANCE_ID}}):
            self.assertFalse(wickedwhims.is_present())

    def test_is_present_false_with_no_game(self):
        self.assertFalse(wickedwhims.is_present())

    def test_instance_type_name_is_action(self):
        self.assertEqual(wickedwhims.INSTANCE_TYPE_NAME, 'ACTION')


class TestWickedWhimsVersion(CompatTestCase):
    def test_absent_when_ww_not_present(self):
        self.assertIsNone(wickedwhims.version_str())

    def test_present_reads_through(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            mod = types.ModuleType('wickedwhims.version_registry')
            mod.get_mod_version_str = lambda: 'v185k'
            sys.modules['wickedwhims.version_registry'] = mod
            try:
                self.assertEqual(wickedwhims.version_str(), 'v185k')
            finally:
                sys.modules.pop('wickedwhims.version_registry', None)

    def test_degrades_to_none_on_failure(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            mod = types.ModuleType('wickedwhims.version_registry')

            def boom():
                raise RuntimeError('renamed by an update')
            mod.get_mod_version_str = boom
            sys.modules['wickedwhims.version_registry'] = mod
            try:
                self.assertIsNone(wickedwhims.version_str())
            finally:
                sys.modules.pop('wickedwhims.version_registry', None)


class TestWickedWhimsAccessors(CompatTestCase):
    def _install(self, module_name, **funcs):
        mod = types.ModuleType(module_name)
        for name, fn in funcs.items():
            setattr(mod, name, fn)
        sys.modules[module_name] = mod

    def test_get_sex_setting_passes_through_value(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            self._install('wickedwhims.sex.sex_settings',
                           get_sex_setting=lambda name: {'sex_initiation': 'walk'}[name])
            try:
                self.assertEqual(wickedwhims.get_sex_setting('sex_initiation'), 'walk')
            finally:
                sys.modules.pop('wickedwhims.sex.sex_settings', None)

    def test_set_sex_setting_passes_through_args(self):
        seen = []
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            self._install('wickedwhims.sex.sex_settings',
                           set_sex_setting=lambda name, value: seen.append((name, value)))
            try:
                self.assertIsNone(wickedwhims.set_sex_setting('sex_initiation', 'teleport'))
                self.assertEqual(seen, [('sex_initiation', 'teleport')])
            finally:
                sys.modules.pop('wickedwhims.sex.sex_settings', None)

    def test_nudity_accessors(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            self._install('wickedwhims.nudity.nudity_settings',
                           get_nudity_setting=lambda n: 'nval', set_nudity_setting=lambda n, v: None)
            try:
                self.assertEqual(wickedwhims.get_nudity_setting('x'), 'nval')
                self.assertIsNone(wickedwhims.set_nudity_setting('x', 1))
            finally:
                sys.modules.pop('wickedwhims.nudity.nudity_settings', None)

    def test_relationship_accessors(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            self._install('wickedwhims.relationships.relationship_settings',
                           get_relationship_setting=lambda n: 'rval',
                           set_relationship_setting=lambda n, v: None)
            try:
                self.assertEqual(wickedwhims.get_relationship_setting('x'), 'rval')
                self.assertIsNone(wickedwhims.set_relationship_setting('x', 1))
            finally:
                sys.modules.pop('wickedwhims.relationships.relationship_settings', None)

    def test_accessor_returns_none_when_ww_absent(self):
        self.assertIsNone(wickedwhims.get_sex_setting('sex_initiation'))
        self.assertIsNone(wickedwhims.set_sex_setting('sex_initiation', 'x'))

    def test_accessor_degrades_on_missing_function(self):
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            self._install('wickedwhims.sex.sex_settings')   # module exists, function does not
            try:
                self.assertIsNone(wickedwhims.get_sex_setting('sex_initiation'))
            finally:
                sys.modules.pop('wickedwhims.sex.sex_settings', None)


# ------------------------------------------------------------------ compat.wicked_perversions
class TestWickedPerversions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        wicked_perversions.reset_cache()

    def tearDown(self):
        wicked_perversions.reset_cache()
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _touch(self, *parts):
        p = os.path.join(self.tmp, 'Mods', *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w').close()

    def test_no_mods_folder_no_variants(self):
        self.assertEqual(wicked_perversions.installed_variants(), [])
        self.assertFalse(wicked_perversions.is_present())
        self.assertEqual(wicked_perversions.duplicate_count(), 0)

    def test_one_variant_detected(self):
        self._touch('scripts', 'HARKI_Wicked_Perversions.ts4script')
        self.assertTrue(wicked_perversions.is_present())
        self.assertEqual(wicked_perversions.duplicate_count(), 1)

    def test_both_variants_detected(self):
        self._touch('scripts', 'HARKI_Wicked_Perversions.ts4script')
        self._touch('scripts', 'NisaK_Wicked_Perversions.ts4script')
        self.assertEqual(wicked_perversions.duplicate_count(), 2)

    def test_unrelated_files_ignored(self):
        self._touch('scripts', 'some_other_mod.ts4script')
        self.assertEqual(wicked_perversions.duplicate_count(), 0)

    def test_cached_until_forced(self):
        self.assertEqual(wicked_perversions.duplicate_count(), 0)
        self._touch('scripts', 'HARKI_Wicked_Perversions.ts4script')
        self.assertEqual(wicked_perversions.duplicate_count(), 0)   # still cached from the first call
        self.assertEqual(len(wicked_perversions.installed_variants(force=True)), 1)

    def test_no_sims_dir_returns_empty_not_a_crash(self):
        common.configure(None)
        wicked_perversions.reset_cache()
        self.assertEqual(wicked_perversions.installed_variants(), [])


# ------------------------------------------------------------------ compat.ui_cheats
class TestUiCheats(unittest.TestCase):
    def test_is_present_returns_none_not_false(self):
        self.assertIsNone(ui_cheats.is_present())

    def test_should_defer_always_false(self):
        self.assertFalse(ui_cheats.should_defer('anything'))
        self.assertFalse(ui_cheats.should_defer(None))


if __name__ == '__main__':
    unittest.main(verbosity=1)

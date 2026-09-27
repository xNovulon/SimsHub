"""Tier-4-style tests for ingame/novulon/settings_ui/menu.py: the Settings tile, the Adult Content
toggle + its "Adults only" notice, Compatibility status lines, the Log Level picker, and About - all
driven directly through the real menukit `Page`/`Row` model and the real `commands` registry, no dialog
and no real game needed (SPEC.md Sec 16 Tier 4). Importing `novulon.settings_ui.menu` registers the
'settings' Main Menu tile and its rows' actions into `commands`'s module-level registries once, the same
way the real game's own module auto-import does - these tests never remove that registration (matching
`test_novulon_commands.py`'s own note that `commands.py` has no reset(), by design, and is meant to be
append-only for the life of the process).
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

import importlib

from novulon import commands, common, settings  # noqa: E402
from novulon.settings_ui import menu  # noqa: E402


def _reset_compat_caches():
    """Reset every `compat` probe cache `menu.py`'s functions can actually reach at call time - not
    `novulon.compat`'s own `reset_cache()` fetched fresh, which is NOT reliably the same cache
    `compat.mccc`/`compat.wickedwhims` use.

    Both `test_novulon_settings.py` (BP1) and `test_novulon_adult.py` (BP11) fake-inject
    `sys.modules['novulon.compat']` for their own tests and then, on cleanup, `sys.modules.pop(
    'novulon.compat', ...)` it - removing the key rather than restoring the real package object that was
    there before. `compat/mccc.py`/`compat/wickedwhims.py` are typically imported once, early, and their
    own `from . import probe` binds `probe` (and its `_cache` dict) to THAT ORIGINAL `novulon.compat`
    object once, permanently - it never updates even though `mccc`'s/`wickedwhims`'s OWN entry in
    `sys.modules` is untouched by either sibling file's cleanup (only the PARENT `novulon.compat` key is
    popped, never `novulon.compat.mccc`/`novulon.compat.wickedwhims`). So once a sibling test file pops
    the parent key, a later plain `importlib.import_module('novulon.compat')` (or a bare `from novulon
    import compat`) creates a BRAND NEW, unrelated package object with its own empty `_cache` - resetting
    THAT does nothing for the cache `mccc.is_present()`/`wickedwhims.is_present()` actually read from,
    since their own `probe` name still points at the original, now-orphaned object. Reaching into
    `mccc.probe.__globals__['_cache']` (the dict the CURRENTLY-CACHED `novulon.compat.mccc`/
    `novulon.compat.wickedwhims` submodules will actually use next) sidesteps that divergence entirely -
    this is a test-isolation gap in those two sibling files, not something this package's own production
    code can or should work around."""
    for modname in ('novulon.compat.mccc', 'novulon.compat.wickedwhims'):
        mod = importlib.import_module(modname)
        cache = getattr(mod.probe, '__globals__', {}).get('_cache')
        if cache is not None:
            cache.clear()
    importlib.import_module('novulon.compat.wicked_perversions').reset_cache()


class FakeGameEnv(object):
    """Fake `sims4.resources`/`services`, same shape as test_novulon_compat.py's own helper - lets
    `compat.mccc`/`compat.wickedwhims`'s probes resolve to True/False on demand from inside a Settings
    test without needing the real game."""

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

        class Mgr(object):
            def __init__(self, known):
                self.known = set(known)

            def get(self, instance_id):
                return object() if instance_id in self.known else None

        mgrs = dict((getattr(Types, name), Mgr(known)) for name, known in self.managers.items())
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


class SettingsUiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        settings.reset_cache()
        _reset_compat_caches()

    def tearDown(self):
        settings.reset_cache()
        _reset_compat_caches()
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestSectionRegistration(SettingsUiTestCase):
    def test_settings_section_registered(self):
        secs = dict(commands.sections())
        self.assertIn('settings', secs)
        self.assertEqual(secs['settings']['label'], 'Settings')
        self.assertEqual(secs['settings']['description'], 'Turn modules on or off.')
        self.assertEqual(secs['settings']['icon'], None)

    def test_novulon_menu_settings_opens_the_settings_page(self):
        self.assertTrue(commands.is_registered('novulon.menu.settings'))
        page = commands.do('novulon.menu.settings', 'CONN')
        self.assertEqual(page.title, 'Settings')

    def test_every_row_id_on_every_page_is_registered(self):
        # menukit's own hard rule (stack.validate_page): every row on a page built by this file must
        # already have a matching commands.add() - push each real page through a real NavStack, which
        # raises ValueError if any row lacks one.
        from novulon.menukit import stack
        pages = [
            menu.build_settings_page('CONN'),
            menu.build_compat_page('CONN'),
            menu.build_log_level_page('CONN'),
            menu.build_about_page('CONN'),
        ]
        for page in pages:
            nav = stack.NavStack()
            nav.push(page)   # raises if any row.id has no registered command


class TestAdultToggleRow(SettingsUiTestCase):
    def test_disabled_without_wickedwhims(self):
        page = menu.build_settings_page('CONN')
        row = next(r for r in page.rows if r.id == menu.ADULT_TOGGLE_ID)
        self.assertFalse(row.enabled)
        self.assertEqual(row.disabled_text, 'Requires WickedWhims')
        self.assertEqual(row.description, 'Off')

    def test_shows_off_by_default_when_ww_present(self):
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            page = menu.build_settings_page('CONN')
            row = next(r for r in page.rows if r.id == menu.ADULT_TOGGLE_ID)
            self.assertTrue(row.enabled)
            self.assertEqual(row.description, 'Off')

    def test_turning_on_returns_the_adults_only_notice_not_the_setting_yet(self):
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            result = menu._activate_adult_toggle('CONN')
            self.assertEqual(result.title, 'Adults only')
            self.assertIn('young adult and older', result.subtitle)
            self.assertFalse(settings.get('adult.enabled'))   # not flipped yet - only the notice shown

    def test_confirming_sets_adult_enabled_true(self):
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            page = menu._activate_adult_toggle('CONN')
            continue_row = next(r for r in page.rows if r.id == menu.ADULT_CONFIRM_ID)
            result = continue_row.on_activate('CONN')
            self.assertIsNone(result)   # handled itself (rebuilds/shows in place), doesn't push a Page
            self.assertTrue(settings.get('adult.enabled'))

    def test_turning_off_needs_no_confirmation(self):
        settings.set('adult.enabled', True)
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            result = menu._activate_adult_toggle('CONN')
            self.assertIsNone(result)
            self.assertFalse(settings.get('adult.enabled'))

    def test_shows_on_when_already_enabled(self):
        settings.set('adult.enabled', True)
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            page = menu.build_settings_page('CONN')
            row = next(r for r in page.rows if r.id == menu.ADULT_TOGGLE_ID)
            self.assertEqual(row.description, 'On')

    def test_still_disabled_even_if_enabled_flag_is_stale_true_without_ww(self):
        # adult.enabled could be left True from a previous session where WW was installed - the row must
        # still show disabled/Off once WW is gone (SPEC.md Sec 11's hard precondition is independent of
        # the stored flag).
        settings.set('adult.enabled', True)
        page = menu.build_settings_page('CONN')
        row = next(r for r in page.rows if r.id == menu.ADULT_TOGGLE_ID)
        self.assertFalse(row.enabled)
        self.assertEqual(row.description, 'Off')


class TestCompatibilityPage(SettingsUiTestCase):
    def test_nothing_detected(self):
        page = menu.build_compat_page('CONN')
        statuses = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(statuses['MC Command Center'], 'Not detected')
        self.assertEqual(statuses['WickedWhims'], 'Not detected')
        self.assertNotIn('Wicked Perversions', statuses)   # nothing to report when 0 copies exist

    def test_mccc_detected(self):
        from novulon.compat import mccc
        with FakeGameEnv(managers={'INTERACTION': {mccc.INSTANCE_ID}}):
            page = menu.build_compat_page('CONN')
        statuses = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(statuses['MC Command Center'], 'Detected')

    def test_wickedwhims_detected_with_version(self):
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            mod = types.ModuleType('wickedwhims.version_registry')
            mod.get_mod_version_str = lambda: 'v185k'
            sys.modules['wickedwhims.version_registry'] = mod
            try:
                page = menu.build_compat_page('CONN')
            finally:
                sys.modules.pop('wickedwhims.version_registry', None)
        statuses = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(statuses['WickedWhims'], 'Detected (v185k)')

    def test_wickedwhims_detected_without_version(self):
        from novulon.compat import wickedwhims
        with FakeGameEnv(managers={'ACTION': {wickedwhims.INSTANCE_ID}}):
            page = menu.build_compat_page('CONN')
        statuses = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(statuses['WickedWhims'], 'Detected')

    def test_wicked_perversions_two_copies_warns(self):
        for name in ('HARKI_Wicked_Perversions.ts4script', 'NisaK_Wicked_Perversions.ts4script'):
            p = os.path.join(self.tmp, 'Mods', 'scripts', name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, 'w').close()
        page = menu.build_compat_page('CONN')
        statuses = dict((r.label, r.description) for r in page.rows)
        self.assertIn('2 copies detected', statuses['Wicked Perversions'])

    def test_wicked_perversions_one_copy_just_detected(self):
        p = os.path.join(self.tmp, 'Mods', 'scripts', 'HARKI_Wicked_Perversions.ts4script')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w').close()
        page = menu.build_compat_page('CONN')
        statuses = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(statuses['Wicked Perversions'], 'Detected')

    def test_info_rows_are_inert(self):
        page = menu.build_compat_page('CONN')
        for row in page.rows:
            self.assertIsNone(row.on_activate)


class TestLogLevelPage(SettingsUiTestCase):
    def test_all_levels_present_current_selected(self):
        settings.set('log_level', 'warning')
        page = menu.build_log_level_page('CONN')
        labels_selected = dict((r.label, r.selected) for r in page.rows)
        self.assertEqual(set(labels_selected), {'Debug', 'Info', 'Warning', 'Error'})
        self.assertTrue(labels_selected['Warning'])
        self.assertFalse(labels_selected['Info'])

    def test_row_on_activate_is_the_exact_registered_function(self):
        # commands.py's own contract: the Row's on_activate and the function registered for that same
        # action_id must be the literal same object.
        page = menu.build_log_level_page('CONN')
        for row in page.rows:
            level = row.label.lower()
            self.assertIs(row.on_activate, menu._LOG_LEVEL_FNS[level])

    def test_selecting_a_level_persists_it(self):
        page = menu.build_log_level_page('CONN')
        debug_row = next(r for r in page.rows if r.label == 'Debug')
        result = debug_row.on_activate('CONN')
        self.assertIsNone(result)
        self.assertEqual(settings.get('log_level'), 'debug')

    def test_settings_page_shows_current_level(self):
        settings.set('log_level', 'error')
        page = menu.build_settings_page('CONN')
        row = next(r for r in page.rows if r.id == menu.LOG_LEVEL_OPEN_ID)
        self.assertEqual(row.description, 'Error')


class TestAboutPage(SettingsUiTestCase):
    def test_shows_version_and_log_path(self):
        page = menu.build_about_page('CONN')
        by_label = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(by_label['Version'], common.VERSION)
        self.assertIn('novulon.log', by_label['Log File'])

    def test_no_sims_dir_still_renders(self):
        common.configure(None)
        page = menu.build_about_page('CONN')
        by_label = dict((r.label, r.description) for r in page.rows)
        self.assertEqual(by_label['Log File'], 'Not available')


if __name__ == '__main__':
    unittest.main(verbosity=1)

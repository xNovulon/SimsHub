"""Tier-4-style tests for ingame/novulon/adult/{gate,settings,bridge,panic,menu}.py (SPEC.md Sec.16
Tier 4's own new requirement: "no test file for the entire adult/ package existed before it, the
single highest-compliance-risk package in the mod").

Covers, directly and with no real game/Mods folder needed:
  * gate.is_adult_content_allowed - the FULL age x species matrix the spec requires (every Age bit
    flag x every Species value: False for every child/teen/toddler/infant/baby age and every
    non-HUMAN species, True only for young adult/adult/elder AND human).
  * gate.is_adult_section_available - the WickedWhims-present AND adult.enabled precondition, both
    branches, plus the compat-package-unavailable fallback (must default to "not available", the
    opposite safe direction from settings.py's own MCCC fallback - see gate.py's own docstring).
  * adult/settings.py's two fields, round-tripped through a real (temp-dir) settings.json.
  * adult/bridge.py's WickedWhims accessor plumbing - bridge.py delegates every actual WickedWhims
    call to compat.wickedwhims (BP7, see bridge.py's own docstring), so these tests fake
    novulon.compat.wickedwhims itself, the same fake-the-boundary convention test_novulon_settings.py
    already uses for novulon.compat.mccc.
  * adult/panic.py's stop_everything/resume_autonomy, against a fake sims4.commands + the same fake
    compat.wickedwhims module.
  * adult/menu.py's screen flow: the once-ever interstitial, the front door's row set, a subgroup
    page's rows reflecting live WickedWhims values, and a toggle row actually flipping the underlying
    setting when driven through commands.do (SPEC.md Sec.4's "every row is also a console command").
"""
import itertools
import os
import shutil
import sys
import tempfile
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands, common, settings          # noqa: E402
from novulon.adult import bridge, gate, menu, panic      # noqa: E402
from novulon.adult import settings as adult_settings     # noqa: E402
from tests.novulon_fakes import FakeConnection           # noqa: E402

# Verified this session against this installed game build's own sims/sim_info_types.pyc - see
# tools/novulon_api_manifest/bp11_adult.py. Copied here as plain ints (never imported at test time),
# same convention gate.py itself uses.
AGE_BABY, AGE_TODDLER, AGE_CHILD, AGE_TEEN = 1, 2, 4, 8
AGE_YOUNGADULT, AGE_ADULT, AGE_ELDER, AGE_INFANT = 16, 32, 64, 128
ALL_AGES = (AGE_BABY, AGE_TODDLER, AGE_CHILD, AGE_TEEN, AGE_YOUNGADULT, AGE_ADULT, AGE_ELDER, AGE_INFANT)
ADULT_AGES = (AGE_YOUNGADULT, AGE_ADULT, AGE_ELDER)

SPECIES_INVALID, SPECIES_HUMAN, SPECIES_DOG, SPECIES_CAT, SPECIES_FOX, SPECIES_HORSE = 0, 1, 2, 3, 5, 6
ALL_SPECIES = (SPECIES_INVALID, SPECIES_HUMAN, SPECIES_DOG, SPECIES_CAT, SPECIES_FOX, SPECIES_HORSE)

OCCULT_VAMPIRE = 4   # sims.occult.occult_enums.OccultType.VAMPIRE - a vampire's .species stays HUMAN


class _FakeSim(object):
    def __init__(self, age=None, species=None, occult_types=0):
        self.age = age
        self.species = species
        self.occult_types = occult_types


# ====================================================================== gate.is_adult_content_allowed
class AdultContentGateTests(unittest.TestCase):
    def test_full_age_x_species_matrix(self):
        for age, species in itertools.product(ALL_AGES, ALL_SPECIES):
            sim = _FakeSim(age=age, species=species)
            expected = (age in ADULT_AGES) and (species == SPECIES_HUMAN)
            self.assertEqual(
                gate.is_adult_content_allowed(sim), expected,
                'age=%r species=%r expected %r' % (age, species, expected))

    def test_occult_sim_still_allowed_because_species_stays_human(self):
        vampire = _FakeSim(age=AGE_ADULT, species=SPECIES_HUMAN, occult_types=OCCULT_VAMPIRE)
        self.assertTrue(gate.is_adult_content_allowed(vampire))

    def test_pet_species_never_allowed_even_at_adult_age(self):
        dog = _FakeSim(age=AGE_ADULT, species=SPECIES_DOG)
        self.assertFalse(gate.is_adult_content_allowed(dog))

    def test_child_age_never_allowed_even_if_species_human(self):
        child = _FakeSim(age=AGE_CHILD, species=SPECIES_HUMAN)
        self.assertFalse(gate.is_adult_content_allowed(child))

    def test_missing_attributes_never_raises(self):
        self.assertFalse(gate.is_adult_content_allowed(object()))

    def test_zero_age_never_allowed(self):
        self.assertFalse(gate.is_adult_content_allowed(_FakeSim(age=0, species=SPECIES_HUMAN)))

    def test_non_int_age_never_raises_or_allows(self):
        self.assertFalse(gate.is_adult_content_allowed(_FakeSim(age=None, species=SPECIES_HUMAN)))
        self.assertFalse(gate.is_adult_content_allowed(_FakeSim(age='adult', species=SPECIES_HUMAN)))


def _install_fake_ww_compat(is_present, raise_error=False):
    """Injects a fake novulon.compat.wickedwhims module so gate._ww_present() doesn't need the real
    compat/ package (BP7) - mirrors test_novulon_settings.py's own _install_fake_compat for
    novulon.compat.mccc."""
    import novulon

    def _is_present():
        if raise_error:
            raise RuntimeError('probe exploded')
        return is_present

    compat_mod = types.ModuleType('novulon.compat')
    ww_mod = types.ModuleType('novulon.compat.wickedwhims')
    ww_mod.is_present = _is_present
    compat_mod.wickedwhims = ww_mod
    sys.modules['novulon.compat'] = compat_mod
    sys.modules['novulon.compat.wickedwhims'] = ww_mod
    novulon.compat = compat_mod

    def cleanup():
        sys.modules.pop('novulon.compat', None)
        sys.modules.pop('novulon.compat.wickedwhims', None)
        if hasattr(novulon, 'compat'):
            del novulon.compat
    return cleanup


class AdultTestCase(unittest.TestCase):
    """Shared temp settings.json + fake-compat lifecycle, same pattern test_novulon_settings.py uses."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        settings.reset_cache()
        self._cleanup_compat = None
        self._actions_snapshot = dict(commands._actions)
        self._sections_snapshot = dict(commands._sections)

    def tearDown(self):
        if self._cleanup_compat:
            self._cleanup_compat()
        settings.reset_cache()
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)
        commands._actions.clear()
        commands._actions.update(self._actions_snapshot)
        commands._sections.clear()
        commands._sections.update(self._sections_snapshot)

    def use_compat(self, is_present, raise_error=False):
        self._cleanup_compat = _install_fake_ww_compat(is_present, raise_error=raise_error)


class AdultSectionAvailabilityTests(AdultTestCase):
    def test_compat_missing_defaults_unavailable(self):
        # simulate compat/ being genuinely unimportable - must default to "not available", the
        # opposite safe direction from settings.py's own MCCC fallback (gate.py's own docstring).
        import novulon
        saved = sys.modules.pop('novulon.compat', None)
        saved_ww = sys.modules.pop('novulon.compat.wickedwhims', None)
        had_attr = hasattr(novulon, 'compat')
        if had_attr:
            del novulon.compat
        try:
            adult_settings.set_enabled(True)
            self.assertFalse(gate.is_adult_section_available())
        finally:
            if saved is not None:
                sys.modules['novulon.compat'] = saved
                novulon.compat = saved
            if saved_ww is not None:
                sys.modules['novulon.compat.wickedwhims'] = saved_ww

    def test_ww_present_but_not_enabled(self):
        self.use_compat(True)
        adult_settings.set_enabled(False)
        self.assertFalse(gate.is_adult_section_available())

    def test_enabled_but_ww_not_present(self):
        self.use_compat(False)
        adult_settings.set_enabled(True)
        self.assertFalse(gate.is_adult_section_available())

    def test_both_true_makes_it_available(self):
        self.use_compat(True)
        adult_settings.set_enabled(True)
        self.assertTrue(gate.is_adult_section_available())

    def test_probe_exception_defaults_unavailable_not_a_crash(self):
        self.use_compat(True, raise_error=True)
        adult_settings.set_enabled(True)
        self.assertFalse(gate.is_adult_section_available())

    def test_section_registered(self):
        self.assertTrue(commands.is_registered('novulon.menu.adult'))

    def test_section_hidden_when_not_available(self):
        self.use_compat(False)
        adult_settings.set_enabled(False)
        keys = [k for k, _ in commands.visible_sections()]
        self.assertNotIn('adult', keys)

    def test_section_visible_once_both_conditions_true(self):
        self.use_compat(True)
        adult_settings.set_enabled(True)
        keys = [k for k, _ in commands.visible_sections()]
        self.assertIn('adult', keys)

    def test_adult_sorts_after_a_default_order_zero_section(self):
        commands.add_section('zzz_other', lambda c, selected_ids=None: None, label='Other', order=0)
        keys = [k for k, _ in commands.sections() if k in ('adult', 'zzz_other')]
        self.assertEqual(keys, ['zzz_other', 'adult'])


# ====================================================================== adult/settings.py
class AdultSettingsTests(AdultTestCase):
    def test_defaults_are_off(self):
        self.assertFalse(adult_settings.is_enabled())
        self.assertFalse(adult_settings.interstitial_shown())

    def test_enabled_round_trips(self):
        adult_settings.set_enabled(True)
        settings.reset_cache()
        self.assertTrue(adult_settings.is_enabled())

    def test_interstitial_shown_round_trips(self):
        adult_settings.mark_interstitial_shown()
        settings.reset_cache()
        self.assertTrue(adult_settings.interstitial_shown())


# ====================================================================== fake compat.wickedwhims
class FakeWickedWhims(object):
    """Installs a fake novulon.compat.wickedwhims module with the six accessor functions
    bridge.py calls plus is_present() - bridge.py delegates every actual WickedWhims call to
    compat.wickedwhims (BP7), so faking it here (rather than the deeper wickedwhims.* modules
    compat/wickedwhims.py itself talks to) is the correct Tier-4 boundary. `broken_domains` makes
    that domain's accessor functions raise, to exercise bridge.py's own guarded degrade;
    `present=False` simulates WickedWhims not being installed (every accessor returns None/no-ops,
    matching compat.wickedwhims's own real behavior when its is_present() is False)."""

    ACCESSOR_NAMES = {
        'sex': ('get_sex_setting', 'set_sex_setting'),
        'nudity': ('get_nudity_setting', 'set_nudity_setting'),
        'relationship': ('get_relationship_setting', 'set_relationship_setting'),
    }

    def __init__(self, initial=None, broken_domains=(), present=True):
        self.data = dict(initial or {})
        self.broken_domains = set(broken_domains)
        self.present = present
        self._saved = {}

    def __enter__(self):
        import novulon
        self._saved_compat = sys.modules.get('novulon.compat')
        self._saved_ww = sys.modules.get('novulon.compat.wickedwhims')
        self._had_attr = hasattr(novulon, 'compat')
        self._novulon = novulon

        compat_mod = types.ModuleType('novulon.compat')
        ww_mod = types.ModuleType('novulon.compat.wickedwhims')
        ww_mod.is_present = lambda: self.present
        for domain, (getter_name, setter_name) in self.ACCESSOR_NAMES.items():
            setattr(ww_mod, getter_name, self._getter(domain))
            setattr(ww_mod, setter_name, self._setter(domain))
        compat_mod.wickedwhims = ww_mod
        sys.modules['novulon.compat'] = compat_mod
        sys.modules['novulon.compat.wickedwhims'] = ww_mod
        novulon.compat = compat_mod
        return self

    def _getter(self, domain):
        def getter(key):
            if not self.present:
                return None
            if domain in self.broken_domains:
                raise RuntimeError('broken domain: %s' % domain)
            return self.data.get((domain, key))
        return getter

    def _setter(self, domain):
        def setter(key, value):
            if not self.present:
                return None
            if domain in self.broken_domains:
                raise RuntimeError('broken domain: %s' % domain)
            self.data[(domain, key)] = value
            return None   # WickedWhims' own set_*_setting always returns None - see bridge.py
        return setter

    def __exit__(self, *exc):
        sys.modules.pop('novulon.compat', None)
        sys.modules.pop('novulon.compat.wickedwhims', None)
        if self._saved_compat is not None:
            sys.modules['novulon.compat'] = self._saved_compat
        if self._saved_ww is not None:
            sys.modules['novulon.compat.wickedwhims'] = self._saved_ww
        if self._had_attr and self._saved_compat is not None:
            self._novulon.compat = self._saved_compat
        elif hasattr(self._novulon, 'compat'):
            del self._novulon.compat


# ====================================================================== adult/bridge.py
class BridgeTests(unittest.TestCase):
    def test_get_set_round_trip(self):
        with FakeWickedWhims():
            self.assertTrue(bridge.set_setting('sex', 'autonomy_switch', True))
            self.assertTrue(bridge.get_setting('sex', 'autonomy_switch'))

    def test_get_with_no_compat_module_is_none_not_a_crash(self):
        self.assertIsNone(bridge.get_setting('sex', 'autonomy_switch'))

    def test_set_with_no_compat_module_returns_false(self):
        self.assertFalse(bridge.set_setting('sex', 'autonomy_switch', True))

    def test_wickedwhims_not_present_gives_none_and_false(self):
        with FakeWickedWhims(present=False):
            self.assertIsNone(bridge.get_setting('sex', 'autonomy_switch'))
            self.assertFalse(bridge.set_setting('sex', 'autonomy_switch', True))

    def test_unknown_domain_returns_none_and_false(self):
        with FakeWickedWhims():
            self.assertIsNone(bridge.get_setting('not_a_domain', 'x'))
            self.assertFalse(bridge.set_setting('not_a_domain', 'x', True))

    def test_broken_accessor_degrades_instead_of_raising(self):
        with FakeWickedWhims(broken_domains=('sex',)):
            self.assertIsNone(bridge.get_setting('sex', 'autonomy_switch'))
            self.assertFalse(bridge.set_setting('sex', 'autonomy_switch', True))

    def test_toggle_flips_and_returns_new_value(self):
        with FakeWickedWhims(initial={('sex', 'autonomy_switch'): True}):
            new_value = bridge.toggle_setting('sex', 'autonomy_switch')
            self.assertFalse(new_value)
            self.assertFalse(bridge.get_setting('sex', 'autonomy_switch'))

    def test_toggle_with_unreadable_current_value_uses_default(self):
        with FakeWickedWhims():   # empty - .get() returns None for any key
            new_value = bridge.toggle_setting('sex', 'autonomy_switch', default=False)
            self.assertTrue(new_value)

    def test_set_all_sex_autonomy_writes_every_key(self):
        with FakeWickedWhims() as ww:
            count = bridge.set_all_sex_autonomy(True)
            self.assertEqual(count, len(bridge.AUTONOMY_SEX_KEYS))
            for key in bridge.AUTONOMY_SEX_KEYS:
                self.assertTrue(ww.data[('sex', key)])

    def test_set_all_sex_autonomy_zero_when_not_present(self):
        with FakeWickedWhims(present=False):
            count = bridge.set_all_sex_autonomy(True)
            self.assertEqual(count, 0)

    def test_subgroups_have_no_duplicate_action_ids(self):
        seen = set()
        for group in bridge.SUBGROUPS:
            self.assertIn('key', group)
            self.assertIn('label', group)
            for domain, key, label in group['settings']:
                action_id = 'novulon.adult.setting.%s.%s' % (domain, key)
                self.assertNotIn(action_id, seen, 'duplicate action id %r' % action_id)
                seen.add(action_id)
                self.assertIn(domain, bridge._ACCESSORS)


# ====================================================================== adult/panic.py
class FakeSims4Commands(object):
    """Installs a fake sims4.commands.execute that records every call, mirroring
    test_novulon_commands.py's own fake sims4.commands install for register()."""

    def __init__(self, raise_error=False):
        self.calls = []
        self.raise_error = raise_error

    def __enter__(self):
        self._saved_sims4 = sys.modules.get('sims4')
        self._saved_commands = sys.modules.get('sims4.commands')
        fake_sims4 = types.ModuleType('sims4')
        fake_commands = types.ModuleType('sims4.commands')

        def execute(command_line, connection):
            if self.raise_error:
                raise RuntimeError('execute failed')
            self.calls.append((command_line, connection))
        fake_commands.execute = execute
        fake_sims4.commands = fake_commands
        sys.modules['sims4'] = fake_sims4
        sys.modules['sims4.commands'] = fake_commands
        return self

    def __exit__(self, *exc):
        if self._saved_sims4 is None:
            sys.modules.pop('sims4', None)
        else:
            sys.modules['sims4'] = self._saved_sims4
        if self._saved_commands is None:
            sys.modules.pop('sims4.commands', None)
        else:
            sys.modules['sims4.commands'] = self._saved_commands


class PanicTests(unittest.TestCase):
    def test_stop_everything_issues_reset_all_and_turns_off_autonomy(self):
        conn = FakeConnection()
        initial = {('sex', k): True for k in bridge.AUTONOMY_SEX_KEYS}
        with FakeSims4Commands() as cmds, FakeWickedWhims(initial=initial) as ww:
            ok = panic.stop_everything(conn)
            self.assertTrue(ok)
            self.assertEqual(cmds.calls, [(panic.RESET_COMMAND, conn)])
            for key in bridge.AUTONOMY_SEX_KEYS:
                self.assertFalse(ww.data[('sex', key)])

    def test_reset_failure_still_attempts_autonomy_off(self):
        conn = FakeConnection()
        initial = {('sex', k): True for k in bridge.AUTONOMY_SEX_KEYS}
        with FakeSims4Commands(raise_error=True), FakeWickedWhims(initial=initial) as ww:
            ok = panic.stop_everything(conn)
            self.assertFalse(ok)
            for key in bridge.AUTONOMY_SEX_KEYS:
                self.assertFalse(ww.data[('sex', key)])

    def test_stop_everything_never_raises_with_no_game_modules_at_all(self):
        self.assertFalse(panic.stop_everything(FakeConnection()))

    def test_resume_autonomy_turns_everything_back_on(self):
        with FakeWickedWhims() as ww:
            ok = panic.resume_autonomy(FakeConnection())
            self.assertTrue(ok)
            for key in bridge.AUTONOMY_SEX_KEYS:
                self.assertTrue(ww.data[('sex', key)])

    def test_resume_autonomy_with_no_wickedwhims_returns_false(self):
        self.assertFalse(panic.resume_autonomy(FakeConnection()))


# ====================================================================== adult/menu.py
class MenuFlowTests(AdultTestCase):
    def test_open_adult_shows_interstitial_first_time(self):
        page = menu.open_adult('CONN')
        self.assertEqual(page.title, 'Adults only')
        ids = [r.id for r in page.rows]
        self.assertEqual(ids, ['novulon.adult.interstitial.continue'])

    def test_open_adult_shows_front_door_after_interstitial_shown(self):
        adult_settings.mark_interstitial_shown()
        page = menu.open_adult('CONN')
        self.assertEqual(page.title, 'Adult')

    def test_front_door_has_one_row_per_subgroup_plus_stop_everything(self):
        # MENU.md's own Adult row list has no separate "Resume Autonomy" row - see menu.py's
        # docstring for why that stays a console-only action (novulon.do ...resume_autonomy).
        page = menu._front_door_page('CONN')
        ids = [r.id for r in page.rows]
        for group in bridge.SUBGROUPS:
            self.assertIn('novulon.adult.group.%s' % group['key'], ids)
        self.assertIn('novulon.adult.stop_everything', ids)
        self.assertNotIn('novulon.adult.resume_autonomy', ids)
        self.assertEqual(len(ids), len(bridge.SUBGROUPS) + 1)

    def test_resume_autonomy_still_reachable_as_a_console_action(self):
        self.assertTrue(commands.is_registered('novulon.adult.resume_autonomy'))

    def test_every_front_door_row_id_is_registered(self):
        # menukit raises if a page ships an unregistered row id (SPEC.md Sec.3.7/Sec.4) - this is
        # exactly what pushing the page through a real NavStack exercises.
        from novulon.menukit import stack
        page = menu._front_door_page('CONN')
        nav = stack.NavStack()
        nav.push(page)   # must not raise

    def test_subgroup_page_reflects_live_wickedwhims_values(self):
        with FakeWickedWhims(initial={('sex', 'autonomy_switch'): True}):
            page = menu._GROUP_OPENERS['autonomy']('CONN')
            row = next(r for r in page.rows if r.id == 'novulon.adult.setting.sex.autonomy_switch')
            self.assertEqual(row.description, 'On')
            self.assertIsNone(row.disabled_text)

    def test_subgroup_row_disabled_when_setting_unavailable(self):
        # no FakeWickedWhims installed at all - every get_setting() call returns None
        page = menu._GROUP_OPENERS['pregnancy']('CONN')
        row = page.rows[0]
        self.assertIsNotNone(row.disabled_text)

    def test_toggling_a_setting_through_commands_do_flips_it(self):
        with FakeWickedWhims(initial={('sex', 'autonomy_switch'): True}) as ww:
            commands.do('novulon.adult.setting.sex.autonomy_switch', FakeConnection())
            self.assertFalse(ww.data[('sex', 'autonomy_switch')])

    def test_stop_everything_row_reachable_through_commands_do(self):
        conn = FakeConnection()
        with FakeSims4Commands() as cmds, FakeWickedWhims():
            commands.do('novulon.adult.stop_everything', conn)
            self.assertEqual(cmds.calls, [(panic.RESET_COMMAND, conn)])

    def test_all_subgroup_pages_push_cleanly(self):
        from novulon.menukit import stack
        with FakeWickedWhims():
            for group in bridge.SUBGROUPS:
                page = menu._GROUP_OPENERS[group['key']]('CONN')
                nav = stack.NavStack()
                nav.push(page)   # must not raise for any subgroup


if __name__ == '__main__':
    unittest.main(verbosity=1)

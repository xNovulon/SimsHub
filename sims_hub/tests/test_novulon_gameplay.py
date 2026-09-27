"""Tier-4-style tests for ingame/novulon/gameplay/*: the MCCC-defer guard's two fallback branches, every
subgroup's command-string construction (driven with a fake `sims4.commands.execute` that records calls,
and a fake `menukit.search.open_search_box` that answers synchronously from a canned queue instead of
showing a real dialog), the Cheats tile's reuse of `household`/`gameplay` functions, and the registered
Main Menu sections - all Tier 4 (SPEC.md §16), no real game needed.
"""
import os
import sys
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands  # noqa: E402
from novulon.gameplay import menu as gmenu  # noqa: E402
from novulon.gameplay import cheats  # noqa: E402
from novulon.menukit import search as search_mod  # noqa: E402


def _install_fake_exec():
    calls = []
    fake_sims4 = types.ModuleType('sims4')
    fake_commands = types.ModuleType('sims4.commands')

    def execute(command_line, _connection):
        calls.append(command_line)
    fake_commands.execute = execute
    fake_sims4.commands = fake_commands
    sys.modules['sims4'] = fake_sims4
    sys.modules['sims4.commands'] = fake_commands
    return calls


def _uninstall_fake_exec():
    sys.modules.pop('sims4', None)
    sys.modules.pop('sims4.commands', None)


def _install_fake_services(active_sim_id=123, sim_by_name=None):
    fake_services = types.ModuleType('services')

    class _Info(object):
        def __init__(self, sid):
            self.id = sid
    fake_services.active_sim_info = (lambda: (_Info(active_sim_id) if active_sim_id is not None else None))
    fake_services.active_household_id = (lambda: 1)

    class _Mgr(object):
        def get_sim_info_by_name(self, first, last):
            # the real method lower()s both names internally (sims/sim_info_manager.pyc:707) - mirrored
            # here so this fake's dict keys can be written in natural case
            if sim_by_name is None:
                return None
            return sim_by_name.get((first.lower(), last.lower()))
    fake_services.sim_info_manager = (lambda: _Mgr())
    sys.modules['services'] = fake_services


def _uninstall_fake_services():
    sys.modules.pop('services', None)


def _install_fake_answers(answers):
    """Patches menukit.search.open_search_box to answer synchronously from `answers` (a list consumed in
    call order) instead of showing a real text-entry dialog. Returns (cleanup, queue) - the queue object
    is returned so a caller can append more values to the SAME patch later without re-capturing
    `search_mod.open_search_box` as "original" a second time (see `GameplayTestCase.answers`'s docstring
    for why that double-capture is the actual bug this shape avoids)."""
    original = search_mod.open_search_box
    queue = list(answers)

    def fake(connection, current_query, on_result, connection_owner=None, title='Search', text=''):
        value = queue.pop(0) if queue else None
        on_result(value)
    search_mod.open_search_box = fake

    def cleanup():
        search_mod.open_search_box = original
    return cleanup, queue


class GameplayTestCase(unittest.TestCase):
    def setUp(self):
        self._cleanup_answers = None
        self._answer_queue = None

    def tearDown(self):
        _uninstall_fake_exec()
        _uninstall_fake_services()
        if self._cleanup_answers:
            self._cleanup_answers()

    def answers(self, values):
        """Queue text-input answers for this test's `open_search_box` calls. Safe to call more than once
        per test (several tests chain two or three prompts): only the FIRST call patches
        `search_mod.open_search_box` and captures the real function to restore later; a later call in
        the same test just extends the already-installed queue. Patching again on each call would
        capture the PREVIOUS call's fake as "original" instead of the real function, so tearDown would
        restore the module to a stale fake rather than the real `open_search_box` - a real, confirmed
        leak that used to strand every test in this file that called `self.answers()` twice, permanently
        breaking `test_novulon_menukit.OpenSearchBoxTests` for the rest of the process."""
        if self._cleanup_answers is None:
            self._cleanup_answers, self._answer_queue = _install_fake_answers(values)
        else:
            self._answer_queue.extend(values)


class TestMcccDeferGuard(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop('novulon.compat', None)
        sys.modules.pop('novulon.compat.mccc', None)

    def test_no_compat_module_and_no_settings_defaults_to_not_present_not_deferred(self):
        # neither compat/ (BP7) nor a real settings.json exist in this bare test environment
        self.assertFalse(gmenu.mccc_present())
        self.assertFalse(gmenu._should_defer('story_progression'))

    def test_prefers_live_compat_probe_when_available(self):
        import novulon
        compat_mod = types.ModuleType('novulon.compat')
        mccc_mod = types.ModuleType('novulon.compat.mccc')
        mccc_mod.is_present = lambda: True
        mccc_mod.should_defer = lambda feature: feature == 'aging'
        compat_mod.mccc = mccc_mod
        sys.modules['novulon.compat'] = compat_mod
        sys.modules['novulon.compat.mccc'] = mccc_mod
        novulon.compat = compat_mod
        try:
            self.assertTrue(gmenu.mccc_present())
            self.assertTrue(gmenu._should_defer('aging'))
            self.assertFalse(gmenu._should_defer('pregnancy'))
        finally:
            del novulon.compat

    def test_banner_text_only_when_present(self):
        self.assertIsNone(gmenu._banner_subtitle())


class TestNeedsAndMoods(GameplayTestCase):
    def test_fill_active_uses_active_sim(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=42)
        gmenu._needs_fill_active('CONN')
        self.assertEqual(calls, ['sims.fill_all_commodities 42'])

    def test_fill_household_needs_no_sim(self):
        calls = _install_fake_exec()
        gmenu._needs_fill_household('CONN')
        self.assertEqual(calls, ['stats.fill_commodities_household'])

    def test_set_individual_need_chains_two_prompts(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=42)
        self.answers(['Hunger', '80'])
        gmenu._needs_set_individual('CONN')
        self.assertEqual(calls, ['stats.set_commodity Hunger 80 42'])

    def test_cancelling_the_first_prompt_runs_nothing(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=42)
        self.answers([None, '80'])   # cancelled at step 1 - step 2 must never be asked
        gmenu._needs_set_individual('CONN')
        self.assertEqual(calls, [])

    def test_add_and_remove_moodlet(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=42)
        self.answers(['Happy'])
        gmenu._needs_add_moodlet('CONN')
        self.answers(['Sad'])
        gmenu._needs_remove_moodlet('CONN')
        self.assertEqual(calls, ['sims.add_buff Happy 42', 'sims.remove_buff Sad 42'])


class TestSkillsAndCareers(GameplayTestCase):
    def test_set_skill_level(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=7)
        self.answers(['Major_Charisma', '10'])
        gmenu._skills_set_level('CONN')
        self.assertEqual(calls, ['stats.set_skill_level Major_Charisma 10 7'])

    def test_max_all_and_clear_all(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=7)
        gmenu._skills_max_all('CONN')
        gmenu._skills_clear_all('CONN')
        self.assertEqual(calls, ['stats.set_all_skills_max 7', 'stats.clear_skill 7'])

    def test_add_career_and_add_pto(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=7)
        self.answers(['Politician'])
        gmenu._careers_add('CONN')
        self.answers(['3'])
        gmenu._careers_add_pto('CONN')
        self.assertEqual(calls, ['careers.add_career Politician 7', 'careers.add_pto 3 7'])

    def test_add_performance_order_matches_verified_usage_string(self):
        # careers.add_performance's own usage message (career_commands.pyc) is
        # "Usage: careers.add_performance <opt_sim> <amount> <career type>"
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=7)
        self.answers(['Politician', '500'])
        gmenu._careers_add_performance('CONN')
        self.assertEqual(calls, ['careers.add_performance 7 500 Politician'])

    def test_promote_always_passes_false_for_check_can_change_level(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=7)
        self.answers(['Politician'])
        gmenu._careers_promote('CONN')
        self.assertEqual(calls, ['careers.promote Politician 7 False'])

    def test_demote(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=7)
        self.answers(['Politician'])
        gmenu._careers_demote('CONN')
        self.assertEqual(calls, ['careers.demote Politician 7'])


class TestTraitsAndAspirations(GameplayTestCase):
    def test_add_remove_clear_trait_rows(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=9)
        self.answers(['Genius'])
        gmenu._traits_add('CONN')
        self.answers(['Genius'])
        gmenu._traits_remove('CONN')
        gmenu._traits_clear_all('CONN')
        gmenu._traits_clear_personality('CONN')
        self.assertEqual(calls, [
            'traits.equip_trait Genius 9', 'traits.remove_trait Genius 9',
            'traits.clear_traits 9', 'traits.clear_personality_traits 9',
        ])

    def test_aspiration_milestone_and_reset(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=9)
        gmenu._aspiration_complete_milestone('CONN')
        gmenu._aspiration_reset('CONN')
        self.assertEqual(calls, [
            'aspirations.complete_current_milestone 9', 'aspirations.reset_data 9',
        ])


class TestLifeAndAging(GameplayTestCase):
    def test_age_up_down(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=5)
        gmenu._life_age_up('CONN')
        gmenu._life_age_down('CONN')
        self.assertEqual(calls, ['sims.age_up 5', 'sims.age_down 5'])

    def test_add_and_set_progress(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=5)
        self.answers(['10'])
        gmenu._life_add_progress('CONN')
        self.answers(['50'])
        gmenu._life_set_progress('CONN')
        self.assertEqual(calls, [
            'sims.age_add_progress_percentage 10 5', 'sims.set_age_progress_percentage 50 5',
        ])


class TestOccults(GameplayTestCase):
    def test_turn_into_and_remove_use_the_verified_enum_member_names(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=3)
        page = gmenu._occults_turn_into_page('CONN')
        labels = {row.label: row.id for row in page.rows}
        self.assertIn('Spellcaster', labels)   # internal enum name is WITCH, per game_api.md/occult_enums
        vamp_row = next(r for r in page.rows if r.label == 'Vampire')
        vamp_row.on_activate('CONN')
        self.assertEqual(calls, ['occult.add_occult VAMPIRE 3'])

    def test_remove_occult(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=3)
        page = gmenu._occults_remove_page('CONN')
        fairy_row = next(r for r in page.rows if r.label == 'Fairy')
        fairy_row.on_activate('CONN')
        self.assertEqual(calls, ['occult.remove_occult FAIRY 3'])

    def test_human_is_not_offered(self):
        page = gmenu._occults_turn_into_page('CONN')
        self.assertNotIn('Human', [row.label for row in page.rows])


class TestPregnancy(GameplayTestCase):
    def test_start_resolves_partner_by_name(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1, sim_by_name={('bob', 'pancakes'): types.SimpleNamespace(id=2)})
        self.answers(['Bob Pancakes'])
        gmenu._pregnancy_start('CONN')
        self.assertEqual(calls, ['pregnancy.start 1 2'])

    def test_start_with_unknown_partner_notifies_and_runs_nothing(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1, sim_by_name={})
        self.answers(['Nobody Special'])
        gmenu._pregnancy_start('CONN')
        self.assertEqual(calls, [])

    def test_clear(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1)
        gmenu._pregnancy_clear('CONN')
        self.assertEqual(calls, ['pregnancy.clear 1'])


class TestWorldTimeWeather(GameplayTestCase):
    def test_set_speed_and_anim_speed(self):
        calls = _install_fake_exec()
        self.answers(['3'])
        gmenu._world_set_speed('CONN')
        self.answers(['1.5'])
        gmenu._world_set_anim_speed('CONN')
        self.assertEqual(calls, ['clock.setspeed 3', 'clock.setanimspeed 1.5'])

    def test_set_game_time_chains_three_prompts(self):
        calls = _install_fake_exec()
        self.answers(['13', '30', '0'])
        gmenu._world_set_game_time('CONN')
        self.assertEqual(calls, ['clock.setgametime 13 30 0'])


class TestPerformance(GameplayTestCase):
    def test_autonomy_on_off_default(self):
        calls = _install_fake_exec()
        page = gmenu._performance_page('CONN')
        by_label = {row.label: row for row in page.rows}
        by_label['Autonomy On'].on_activate('CONN')
        by_label['Autonomy Off'].on_activate('CONN')
        by_label['Restore Autonomy Defaults'].on_activate('CONN')
        self.assertEqual(calls, ['autonomy.global on', 'autonomy.global off', 'autonomy.global default'])


class TestStoryProgressionGuard(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop('novulon.compat', None)
        sys.modules.pop('novulon.compat.mccc', None)

    def test_shows_deferred_text_when_mccc_present(self):
        import novulon
        compat_mod = types.ModuleType('novulon.compat')
        mccc_mod = types.ModuleType('novulon.compat.mccc')
        mccc_mod.is_present = lambda: True
        mccc_mod.should_defer = lambda feature: True
        compat_mod.mccc = mccc_mod
        sys.modules['novulon.compat'] = compat_mod
        sys.modules['novulon.compat.mccc'] = mccc_mod
        novulon.compat = compat_mod
        try:
            page = gmenu._story_page('CONN')
            self.assertIn('MC Command Center', page.rows[0].label)
        finally:
            del novulon.compat

    def test_shows_coming_soon_when_mccc_absent(self):
        page = gmenu._story_page('CONN')
        self.assertIn('coming', page.rows[0].label.lower())


class TestCheatsReuseExistingFunctions(GameplayTestCase):
    def test_money_row_reuses_household_set_personal_funds(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=55)
        self.answers(['9000'])
        cheats._money_row('CONN')
        self.assertEqual(calls, ['money 9000 55'])

    def test_fill_needs_row_calls_the_same_gameplay_function(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=55)
        cheats._fill_needs_row('CONN')
        self.assertEqual(calls, ['sims.fill_all_commodities 55'])

    def test_max_skill_reset_age_up_age_down(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=55)
        cheats._max_skill_row('CONN')
        cheats._reset_row('CONN')
        cheats._age_up_row('CONN')
        cheats._age_down_row('CONN')
        self.assertEqual(calls, [
            'stats.set_all_skills_max 55', 'sims.reset 55', 'sims.age_up 55', 'sims.age_down 55',
        ])


class TestSectionsAndRegistry(unittest.TestCase):
    def test_gameplay_and_cheats_sections_registered(self):
        keys = [k for k, _ in commands.sections()]
        self.assertIn('gameplay', keys)
        self.assertIn('cheats', keys)

    def test_every_gameplay_and_cheats_action_is_registered(self):
        for action_id, _handler in gmenu.all_actions():
            self.assertTrue(commands.is_registered(action_id), action_id)
        for action_id, _handler in cheats.all_actions():
            self.assertTrue(commands.is_registered(action_id), action_id)

    def test_occult_sub_rows_are_registered_too(self):
        for label, token in gmenu._OCCULT_CHOICES:
            self.assertTrue(commands.is_registered('novulon.gameplay.occults.turn_into.%s' % token))
            self.assertTrue(commands.is_registered('novulon.gameplay.occults.remove.%s' % token))

    def test_every_built_page_pushes_without_raising(self):
        from novulon.menukit import stack
        pages = [
            gmenu.gameplay_root('CONN'), cheats.cheats_root('CONN'), gmenu._needs_page('CONN'),
            gmenu._skills_page('CONN'), gmenu._traits_page('CONN'), gmenu._occults_page('CONN'),
            gmenu._occults_turn_into_page('CONN'), gmenu._occults_remove_page('CONN'),
            gmenu._pregnancy_page('CONN'), gmenu._world_page('CONN'), gmenu._story_page('CONN'),
            gmenu._performance_page('CONN'), gmenu._life_page('CONN'),
        ]
        for page in pages:
            nav = stack.NavStack()
            nav.push(page)


if __name__ == '__main__':
    unittest.main(verbosity=1)

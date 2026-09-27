"""Tier-4-style tests for ingame/novulon/sims/actions.py: every per-Sim action's command composition,
the "bound row" pattern, and the browser's public hook (`novulon.sims.selection_action`) - driven with
FakeSimInfo/FakeHousehold (tests/novulon_fakes.py) and small fake `services`/`sims4.commands`/
`sims4.resources` modules, no fake Sims folder or game DLL needed (SPEC.md Sec 16 Tier 4).
"""
import os
import sys
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands  # noqa: E402
from novulon.sims import actions  # noqa: E402
from tests.novulon_fakes import FakeSimInfo, FakeHousehold  # noqa: E402


class _Vector3(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = x, y, z


class _FakeSimInstance(object):
    def __init__(self, x=1.0, y=2.0, z=3.0, level=0):
        self.position = _Vector3(x, y, z)
        self.level = level


class FakeClient(object):
    def __init__(self, selectable=()):
        self.selectable = set(selectable)
        self.add_calls = []
        self.remove_calls = []

    def add_selectable_sim_by_id(self, sim_id):
        self.add_calls.append(sim_id)
        self.selectable.add(sim_id)
        return True

    def remove_selectable_sim_by_id(self, sim_id):
        if len(self.selectable) <= 1:
            return False
        self.remove_calls.append(sim_id)
        self.selectable.discard(sim_id)
        return True


class FakeClientManager(object):
    def __init__(self):
        self.by_household = {}

    def get_client_by_household_id(self, household_id):
        return self.by_household.get(household_id)


class FakeInstanceManager(object):
    def __init__(self, types_dict=None):
        self.types = dict(types_dict or {})

    def get(self, key):
        return None


class FakeGameServices(object):
    def __init__(self, sims=(), active_sim_info=None, active_household_id=None, active_sim_instance=None,
                 client_manager=None, trait_types=None):
        self._sims = {s.id: s for s in sims}
        self._active_sim_info = active_sim_info
        self._active_household_id = active_household_id
        self._active_sim_instance = active_sim_instance
        self._client_manager = client_manager or FakeClientManager()
        self._trait_mgr = FakeInstanceManager(trait_types or {})

    def sim_info_manager(self):
        class _Mgr(object):
            def get(_s, sim_id):
                return self._sims.get(sim_id)
        return _Mgr()

    def active_sim_info(self):
        return self._active_sim_info

    def active_household_id(self):
        return self._active_household_id

    def get_active_sim(self):
        return self._active_sim_instance

    def client_manager(self):
        return self._client_manager

    def get_instance_manager(self, instance_type):
        if instance_type == 'TRAIT':
            return self._trait_mgr
        return None


class FakeGameEnv(object):
    """Installs fake `services`/`sims4.commands`/`sims4.resources` for one test."""

    def __init__(self, **service_kwargs):
        self.calls = {'execute': [], 'client_cheat': []}
        self.services_obj = FakeGameServices(**service_kwargs)

    def __enter__(self):
        fake_services = types.ModuleType('services')
        for name in ('sim_info_manager', 'active_sim_info', 'active_household_id', 'get_active_sim',
                     'client_manager', 'get_instance_manager'):
            setattr(fake_services, name, getattr(self.services_obj, name))

        fake_sims4 = types.ModuleType('sims4')
        fake_commands = types.ModuleType('sims4.commands')
        fake_commands.execute = lambda cmd, conn: self.calls['execute'].append(cmd)
        fake_commands.client_cheat = lambda cmd, conn: self.calls['client_cheat'].append(cmd)
        fake_sims4.commands = fake_commands

        fake_resources = types.ModuleType('sims4.resources')

        class Types(object):
            TRAIT = 'TRAIT'
        fake_resources.Types = Types
        fake_sims4.resources = fake_resources

        self._saved = {name: sys.modules.get(name) for name in
                       ('services', 'sims4', 'sims4.commands', 'sims4.resources')}
        sys.modules['services'] = fake_services
        sys.modules['sims4'] = fake_sims4
        sys.modules['sims4.commands'] = fake_commands
        sys.modules['sims4.resources'] = fake_resources
        return self

    def __exit__(self, *exc):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


class ActionsTestCase(unittest.TestCase):
    def setUp(self):
        self._notified = []
        self._orig_notify = actions.menukit.notify
        actions.menukit.notify = lambda title, text='', **k: self._notified.append((title, text))

    def tearDown(self):
        actions.menukit.notify = self._orig_notify


# ------------------------------------------------------------------------------ small pure helpers
class TestSmallHelpers(unittest.TestCase):
    def test_to_int_accepts_int_and_numeric_string(self):
        self.assertEqual(actions._to_int(5), 5)
        self.assertEqual(actions._to_int('42'), 42)
        self.assertEqual(actions._to_int('  7 '), 7)

    def test_to_int_rejects_garbage(self):
        self.assertIsNone(actions._to_int('not a number'))
        self.assertIsNone(actions._to_int(None))

    def test_name_prefers_full_name(self):
        sim = FakeSimInfo(first_name='Bob', last_name='Pancakes')
        self.assertEqual(actions._name(sim), 'Bob Pancakes')

    def test_bound_calls_the_same_fn_with_str_cast_args(self):
        seen = []
        fn = lambda connection, *a: seen.append((connection, a))
        bound = actions._bound(fn, 42, 7)
        bound('CONN')
        self.assertEqual(seen, [('CONN', ('42', '7'))])

    def test_bound_ignores_selected_ids_kwarg(self):
        seen = []
        fn = lambda connection, *a: seen.append(a)
        bound = actions._bound(fn, 1)
        bound('CONN', selected_ids=[1, 2, 3])
        self.assertEqual(seen, [('1',)])


# ------------------------------------------------------------------------------ 1. Edit in CAS
class TestEditInCas(ActionsTestCase):
    def test_uses_the_targets_own_household_id(self):
        sim = FakeSimInfo(id=5, household=FakeHousehold(9))
        with FakeGameEnv(sims=[sim]) as env:
            actions.edit_in_cas('CONN', sim.id)
        self.assertEqual(env.calls['client_cheat'], ['sims.exit2caswithhouseholdid 5 9'])

    def test_sim_not_found_notifies_and_does_not_crash(self):
        with FakeGameEnv(sims=[]) as env:
            actions.edit_in_cas('CONN', 999)
        self.assertEqual(env.calls['client_cheat'], [])


# ------------------------------------------------------------------------------ 3/4/5/7. simple execs
class TestSimpleExecActions(ActionsTestCase):
    def test_reset(self):
        sim = FakeSimInfo(id=1, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.reset_sim('CONN', sim.id)
        self.assertEqual(env.calls['execute'], ['sims.reset 1'])

    def test_fill_needs(self):
        sim = FakeSimInfo(id=2, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.fill_needs('CONN', sim.id)
        self.assertEqual(env.calls['execute'], ['sims.fill_all_commodities 2'])

    def test_add_to_household_defaults_to_active_household(self):
        sim = FakeSimInfo(id=3, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.add_to_household('CONN', sim.id)
        self.assertEqual(env.calls['execute'], ['sims.add_to_family 3'])

    def test_age_up_and_down(self):
        sim = FakeSimInfo(id=4, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.age_up('CONN', sim.id)
            actions.age_down('CONN', sim.id)
        self.assertEqual(env.calls['execute'], ['sims.age_up 4', 'sims.age_down 4'])


# ------------------------------------------------------------------------------ 4. Teleport to Me
class TestTeleportToMe(ActionsTestCase):
    def test_builds_command_from_the_active_sims_live_position_and_level(self):
        sim = FakeSimInfo(id=10, household=FakeHousehold(1))
        instance = _FakeSimInstance(x=12.5, y=-3.0, z=0.0, level=1)
        with FakeGameEnv(sims=[sim], active_sim_instance=instance) as env:
            actions.teleport_to_me('CONN', sim.id)
        self.assertEqual(len(env.calls['execute']), 1)
        cmd = env.calls['execute'][0]
        self.assertTrue(cmd.startswith('sims.teleport_instantly '))
        parts = cmd.split()
        self.assertEqual(parts[0], 'sims.teleport_instantly')
        self.assertAlmostEqual(float(parts[1]), 12.5)
        self.assertAlmostEqual(float(parts[2]), -3.0)
        self.assertAlmostEqual(float(parts[3]), 0.0)
        self.assertEqual(parts[4], '1')     # level
        self.assertEqual(parts[5], '10')    # target sim id
        self.assertEqual(parts[6], '0')     # rotation

    def test_no_active_sim_notifies_and_does_not_execute(self):
        sim = FakeSimInfo(id=11, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim], active_sim_instance=None) as env:
            actions.teleport_to_me('CONN', sim.id)
        self.assertEqual(env.calls['execute'], [])
        self.assertTrue(any('No active Sim' in text for _title, text in self._notified))


# ------------------------------------------------------------------------------ 6. Make Playable / NPC
class TestTogglePlayable(ActionsTestCase):
    def test_makes_an_active_household_sim_playable(self):
        sim = FakeSimInfo(id=20, household=FakeHousehold(1))
        client = FakeClient(selectable=set())
        cm = FakeClientManager()
        cm.by_household[1] = client
        with FakeGameEnv(sims=[sim], active_household_id=1, client_manager=cm):
            actions.toggle_playable('CONN', sim.id)
        self.assertIn(20, client.selectable)

    def test_moves_a_non_active_household_sim_before_making_it_playable(self):
        sim = FakeSimInfo(id=21, household=FakeHousehold(2))
        client = FakeClient(selectable=set())
        cm = FakeClientManager()
        cm.by_household[1] = client
        with FakeGameEnv(sims=[sim], active_household_id=1, client_manager=cm) as env:
            actions.toggle_playable('CONN', sim.id)
        self.assertIn('sims.add_to_family 21', env.calls['execute'])
        self.assertIn(21, client.selectable)

    def test_makes_a_selectable_sim_an_npc(self):
        sim = FakeSimInfo(id=22, household=FakeHousehold(1))
        sim.is_selectable = lambda: True   # FakeSimInfo has no real selectable-tracking of its own
        client = FakeClient(selectable={22, 23})
        cm = FakeClientManager()
        cm.by_household[1] = client
        with FakeGameEnv(sims=[sim], client_manager=cm):
            actions.toggle_playable('CONN', sim.id)
        self.assertNotIn(22, client.selectable)

    def test_refuses_to_drop_a_household_to_zero_playable_sims(self):
        sim = FakeSimInfo(id=24, household=FakeHousehold(1))
        sim.is_selectable = lambda: True
        client = FakeClient(selectable={24})   # the only selectable Sim in the household
        cm = FakeClientManager()
        cm.by_household[1] = client
        with FakeGameEnv(sims=[sim], client_manager=cm):
            actions.toggle_playable('CONN', sim.id)
        self.assertIn(24, client.selectable)   # unchanged - remove_selectable_sim_by_id refused
        self.assertTrue(any('at least one playable Sim' in text for _t, text in self._notified))


# ------------------------------------------------------------------------------ Traits
class TestTraits(ActionsTestCase):
    def _trait_class(self, name, is_npc_only=False):
        cls = type(name, (), {'is_npc_only': is_npc_only, '__name__': name})
        return cls

    def test_equip_trait(self):
        sim = FakeSimInfo(id=30, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions._traits_equip('CONN', sim.id, 'HotHeaded')
        self.assertEqual(env.calls['execute'], ['traits.equip_trait HotHeaded 30'])

    def test_remove_trait(self):
        sim = FakeSimInfo(id=31, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions._traits_remove('CONN', sim.id, 'Genius')
        self.assertEqual(env.calls['execute'], ['traits.remove_trait Genius 31'])

    def test_clear_all_and_clear_personality(self):
        sim = FakeSimInfo(id=32, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.clear_all_traits('CONN', sim.id)
            actions.clear_personality_traits('CONN', sim.id)
        self.assertEqual(env.calls['execute'],
                         ['traits.clear_traits 32', 'traits.clear_personality_traits 32'])

    def test_equipped_traits_reads_the_trait_tracker(self):
        cls_a, cls_b = self._trait_class('Genius'), self._trait_class('Cheerful')
        sim = FakeSimInfo(id=33)
        sim.trait_tracker = [cls_a, cls_b]
        self.assertEqual(actions._equipped_traits(sim), [cls_a, cls_b])

    def test_equipped_traits_empty_when_no_tracker(self):
        sim = FakeSimInfo(id=34)
        self.assertEqual(actions._equipped_traits(sim), [])

    def test_trait_classes_reads_the_instance_manager(self):
        cls_a = self._trait_class('HotHeaded')
        with FakeGameEnv(trait_types={1: cls_a}):
            classes = actions._trait_classes()
        self.assertEqual(classes, [cls_a])

    def test_open_traits_menu_builds_a_page_with_registered_rows(self):
        sim = FakeSimInfo(id=35, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_traits_menu('CONN', sim.id)
        self.assertEqual(len(page.rows), 4)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), row.id)


# ------------------------------------------------------------------------------ Needs, Skills, Career
class TestNeedsSkillsCareer(ActionsTestCase):
    def test_set_individual_need_uses_the_raw_value_command(self):
        sim = FakeSimInfo(id=40, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            def _run():
                calls = []
                orig_prompt = actions._prompt_chain

                def _fake_prompt(connection, fields, build_command, ok_text):
                    cmd = build_command(['Hunger', '75'])
                    calls.append(cmd)
                actions._prompt_chain = _fake_prompt
                try:
                    actions._needs_set_one_open('CONN', sim.id)
                finally:
                    actions._prompt_chain = orig_prompt
                return calls
            calls = _run()
        self.assertEqual(calls, ['stats.set_commodity Hunger 75 40'])

    def test_add_and_remove_moodlet(self):
        sim = FakeSimInfo(id=41, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            def _got_add(text):
                pass
            # directly exercise the inner _got closures via _ask_text monkeypatch
            captured = {}
            orig_ask = actions._ask_text
            actions._ask_text = lambda connection, title, prompt, on_result: captured.__setitem__('cb', on_result)
            try:
                actions._needs_add_moodlet_open('CONN', sim.id)
                captured['cb']('Confident')
                actions._needs_remove_moodlet_open('CONN', sim.id)
                captured['cb']('Confident')
            finally:
                actions._ask_text = orig_ask
        self.assertEqual(env.calls['execute'], ['sims.add_buff Confident 41', 'sims.remove_buff Confident 41'])

    def test_skills_max_all_and_clear_all(self):
        sim = FakeSimInfo(id=42, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.skills_max_all('CONN', sim.id)
            actions.skills_clear_all('CONN', sim.id)
        self.assertEqual(env.calls['execute'], ['stats.set_all_skills_max 42', 'stats.clear_skill 42'])

    def test_career_promote_and_demote(self):
        sim = FakeSimInfo(id=43, household=FakeHousehold(1))
        captured = {}
        orig_ask = actions._ask_text
        actions._ask_text = lambda connection, title, prompt, on_result: captured.__setitem__('cb', on_result)
        try:
            with FakeGameEnv(sims=[sim]) as env:
                actions._career_promote_open('CONN', sim.id)
                captured['cb']('Culinary')
                actions._career_demote_open('CONN', sim.id)
                captured['cb']('Culinary')
        finally:
            actions._ask_text = orig_ask
        self.assertEqual(env.calls['execute'], ['careers.promote Culinary 43', 'careers.demote Culinary 43'])

    def test_needs_menu_rows_are_all_registered(self):
        """Regression test for a real bug the integrator found by auditing every `Row(id, ...)` in this
        file against `commands.add()`: `open_needs_menu`'s "Fill All Needs" row used the id
        'sims.actions.needs.fill_all', which was never registered anywhere - every OTHER row on this
        exact page was registered, so the missing one was easy to miss by eye. Opening this page in
        game would have raised `ValueError` out of `menukit/stack.py`'s "every row needs a registered
        command" guard the first time a player clicked "Needs & Moods..." from a Sim Card. Fixed by
        registering `'sims.actions.needs.fill_all'` under the same `fill_needs` function the row's
        `on_activate` already binds."""
        sim = FakeSimInfo(id=44, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_needs_menu('CONN', sim.id)
        self.assertEqual(len(page.rows), 4)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), row.id)

    def test_skills_career_menu_rows_are_all_registered(self):
        sim = FakeSimInfo(id=45, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_skills_career_menu('CONN', sim.id)
        self.assertEqual(len(page.rows), 8)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), row.id)

    def test_set_age_menu_rows_are_all_registered(self):
        sim = FakeSimInfo(id=46, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_set_age_menu('CONN', sim.id)
        self.assertEqual(len(page.rows), 4)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), row.id)


# ------------------------------------------------------------------------------ Occult
class TestOccult(ActionsTestCase):
    def test_turn_into_and_remove(self):
        sim = FakeSimInfo(id=50, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions._occult_switch('CONN', sim.id, 'VAMPIRE')
            actions._occult_remove('CONN', sim.id, 'VAMPIRE')
        self.assertEqual(env.calls['execute'],
                         ['occult.switch_to_occult VAMPIRE 50', 'occult.remove_occult VAMPIRE 50'])

    def test_occult_menu_has_twelve_registered_rows(self):
        sim = FakeSimInfo(id=51, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_occult_menu('CONN', sim.id)
        self.assertEqual(len(page.rows), 12)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id))


# ------------------------------------------------------------------------------ Pregnancy
class TestPregnancy(ActionsTestCase):
    def test_start_pregnancy_resolves_partner_by_name(self):
        sim = FakeSimInfo(id=60, first_name='Alex', last_name='Doe', household=FakeHousehold(1))
        partner = FakeSimInfo(id=61, first_name='Sam', last_name='Lee', household=FakeHousehold(1))

        by_id = {sim.id: sim, partner.id: partner}

        class _Mgr(object):
            def get(_s, sim_id):
                return by_id.get(sim_id)

            def get_sim_info_by_name(_s, first, last):
                if first == 'Sam' and last == 'Lee':
                    return partner
                return None

        with FakeGameEnv(sims=[sim, partner]) as env:
            sys.modules['services'].sim_info_manager = lambda: _Mgr()
            captured = {}
            orig_ask = actions._ask_text
            actions._ask_text = lambda connection, title, prompt, on_result: captured.__setitem__('cb', on_result)
            try:
                actions._pregnancy_start_open('CONN', sim.id)
                captured['cb']('Sam Lee')
            finally:
                actions._ask_text = orig_ask
        self.assertEqual(env.calls['execute'], ['pregnancy.start 60 61'])

    def test_clear_pregnancy(self):
        sim = FakeSimInfo(id=62, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]) as env:
            actions.pregnancy_clear('CONN', sim.id)
        self.assertEqual(env.calls['execute'], ['pregnancy.clear 62'])

    def test_pregnancy_menu_rows_are_all_registered(self):
        sim = FakeSimInfo(id=63, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_pregnancy_menu('CONN', sim.id)
        self.assertEqual(len(page.rows), 2)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), row.id)


# ------------------------------------------------------------------------------ Delete hand-off
class TestDeleteHandoff(ActionsTestCase):
    def test_open_delete_calls_delete_request_delete_with_the_one_sim(self):
        sim = FakeSimInfo(id=70, household=FakeHousehold(1))
        seen = []
        orig = actions.delete.request_delete
        actions.delete.request_delete = lambda connection, sim_infos: seen.append((connection, list(sim_infos)))
        try:
            with FakeGameEnv(sims=[sim]):
                actions.open_delete('CONN', sim.id)
        finally:
            actions.delete.request_delete = orig
        self.assertEqual(seen, [('CONN', [sim])])

    def test_multi_delete_resolves_every_id_and_skips_unknown_ones(self):
        a = FakeSimInfo(id=71, household=FakeHousehold(1))
        b = FakeSimInfo(id=72, household=FakeHousehold(1))
        seen = []
        orig = actions.delete.request_delete
        actions.delete.request_delete = lambda connection, sim_infos: seen.append(list(sim_infos))
        try:
            with FakeGameEnv(sims=[a, b]):
                actions._multi_delete('CONN', '71', '72', '999')
        finally:
            actions.delete.request_delete = orig
        self.assertEqual(seen, [[a, b]])

    def test_multi_fill_needs(self):
        a = FakeSimInfo(id=73, household=FakeHousehold(1))
        b = FakeSimInfo(id=74, household=FakeHousehold(1))
        with FakeGameEnv(sims=[a, b]) as env:
            actions._multi_fill_needs('CONN', '73', '74')
        self.assertEqual(sorted(env.calls['execute']),
                         ['sims.fill_all_commodities 73', 'sims.fill_all_commodities 74'])


# ------------------------------------------------------------------------------ the action-list Pages
class TestBuildSimActionPage(ActionsTestCase):
    def test_page_has_fourteen_rows_all_registered(self):
        sim = FakeSimInfo(id=80, first_name='Bob', last_name='Pancakes', household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.build_sim_action_page('CONN', sim.id)
        self.assertEqual(page.title, 'Bob Pancakes')
        self.assertEqual(len(page.rows), 14)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), row.id)

    def test_playable_row_label_toggles_with_is_selectable(self):
        sim = FakeSimInfo(id=81, household=FakeHousehold(1))
        sim.is_selectable = lambda: False
        with FakeGameEnv(sims=[sim]):
            page = actions.build_sim_action_page('CONN', sim.id)
        toggle_row = next(r for r in page.rows if r.id == 'sims.actions.toggle_playable')
        self.assertEqual(toggle_row.label, 'Make Playable')

        sim.is_selectable = lambda: True
        with FakeGameEnv(sims=[sim]):
            page = actions.build_sim_action_page('CONN', sim.id)
        toggle_row = next(r for r in page.rows if r.id == 'sims.actions.toggle_playable')
        self.assertEqual(toggle_row.label, 'Make NPC')

    def test_sim_not_found_returns_a_safe_placeholder_page(self):
        with FakeGameEnv(sims=[]):
            page = actions.build_sim_action_page('CONN', 999)
        self.assertEqual(len(page.rows), 1)
        self.assertTrue(commands.is_registered(page.rows[0].id))


class TestBuildMultiSimActionPage(unittest.TestCase):
    def test_has_four_rows_two_disabled(self):
        page = actions.build_multi_sim_action_page('CONN', [1, 2, 3])
        self.assertEqual(page.title, '3 Sims selected')
        self.assertEqual(len(page.rows), 4)
        disabled = [r for r in page.rows if r.disabled_text]
        self.assertEqual(len(disabled), 2)
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id))


# ------------------------------------------------------------------------------ the browser's public hook
class TestOpenSelectionAction(ActionsTestCase):
    def test_one_id_opens_the_single_sim_page(self):
        sim = FakeSimInfo(id=90, household=FakeHousehold(1))
        with FakeGameEnv(sims=[sim]):
            page = actions.open_selection_action('CONN', '90')
        self.assertEqual(page.title, actions._name(sim))

    def test_two_ids_open_the_multi_sim_page(self):
        page = actions.open_selection_action('CONN', '1', '2')
        self.assertEqual(page.title, '2 Sims selected')

    def test_no_valid_ids_returns_none(self):
        self.assertIsNone(actions.open_selection_action('CONN', 'garbage'))
        self.assertIsNone(actions.open_selection_action('CONN'))

    def test_is_registered_under_the_stable_hook_id_browser_py_calls(self):
        self.assertTrue(commands.is_registered('novulon.sims.selection_action'))


# ------------------------------------------------------------------------------ Relationship delegation
class TestRelationshipMenu(unittest.TestCase):
    def test_delegates_to_relationships_menu_when_present(self):
        fake_page = object()
        fake_module = types.ModuleType('relationships.menu')
        fake_module.relationships_page = lambda connection: fake_page
        fake_pkg = types.ModuleType('novulon.relationships')
        fake_pkg.menu = fake_module
        saved = {n: sys.modules.get(n) for n in ('novulon.relationships', 'novulon.relationships.menu')}
        sys.modules['novulon.relationships'] = fake_pkg
        sys.modules['novulon.relationships.menu'] = fake_module
        try:
            result = actions.open_relationship_menu('CONN', 1)
        finally:
            for n, m in saved.items():
                if m is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m
        self.assertIs(result, fake_page)

    def test_falls_back_to_a_placeholder_when_relationships_menu_is_unavailable(self):
        # A None entry in sys.modules is CPython's own documented way to force `import` to raise
        # ImportError - needed here because `relationships/__init__.py` genuinely exists on disk in
        # this tree, so merely popping it would just make Python re-import the real (working) module.
        saved = {n: sys.modules.get(n) for n in ('novulon.relationships', 'novulon.relationships.menu')}
        sys.modules['novulon.relationships'] = None
        sys.modules['novulon.relationships.menu'] = None
        try:
            page = actions.open_relationship_menu('CONN', 1)
        finally:
            for n, m in saved.items():
                if m is None:
                    sys.modules.pop(n, None)
                else:
                    sys.modules[n] = m
        self.assertEqual(page.title, 'Relationship')
        self.assertTrue(commands.is_registered(page.rows[0].id))


if __name__ == '__main__':
    unittest.main(verbosity=1)

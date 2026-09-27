"""Tier-4-style tests for ingame/novulon/household/*: command-string construction, the purge-instanced-
members pure logic, the generic OK/Cancel confirmation's degrade path, and the registered Main Menu
section - all driven with fake `sims4.commands`/`services`/`ui.ui_dialog` modules, no real game needed
(SPEC.md §16 Tier 4 pattern, same as test_novulon_commands.py/test_novulon_inject.py in this same tree).
"""
import os
import sys
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands, common  # noqa: E402
from novulon.household import menu as hmenu  # noqa: E402
from novulon.household import inventory as hinv  # noqa: E402


class FakeSimInfo(object):
    def __init__(self, sim_id, instanced=True):
        self.id = sim_id
        self._instanced = instanced

    def is_instanced(self):
        return self._instanced


def _install_fake_sims4_commands():
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


def _uninstall_fake_sims4_commands():
    sys.modules.pop('sims4', None)
    sys.modules.pop('sims4.commands', None)


def _install_fake_services(active_sim_id=None, household=None):
    fake_services = types.ModuleType('services')

    class _Info(object):
        def __init__(self, sid):
            self.id = sid
    fake_services.active_sim_info = (lambda: (_Info(active_sim_id) if active_sim_id is not None else None))
    fake_services.active_household = (lambda: household)
    sys.modules['services'] = fake_services


def _uninstall_fake_services():
    sys.modules.pop('services', None)


class HouseholdTestCase(unittest.TestCase):
    def setUp(self):
        self._actions_snapshot = dict(commands._actions)
        self._sections_snapshot = dict(commands._sections)

    def tearDown(self):
        commands._actions.clear()
        commands._actions.update(self._actions_snapshot)
        commands._sections.clear()
        commands._sections.update(self._sections_snapshot)
        _uninstall_fake_sims4_commands()
        _uninstall_fake_services()


class TestHouseholdFunds(HouseholdTestCase):
    def test_delta_amount_is_passed_through_with_household_id_zero(self):
        calls = _install_fake_sims4_commands()
        hmenu.set_household_funds('CONN', 1000)
        self.assertEqual(calls, ['households.modify_funds 1000 0'])

    def test_negative_amount_removes_funds(self):
        calls = _install_fake_sims4_commands()
        hmenu.set_household_funds('CONN', -250)
        self.assertEqual(calls, ['households.modify_funds -250 0'])


class TestPersonalFunds(HouseholdTestCase):
    def test_absolute_amount_and_explicit_sim_id(self):
        calls = _install_fake_sims4_commands()
        hmenu.set_personal_funds('CONN', 12345, 5000)
        self.assertEqual(calls, ['money 5000 12345'])

    def test_personal_funds_row_uses_active_sim(self):
        calls = _install_fake_sims4_commands()
        _install_fake_services(active_sim_id=777)
        captured = {}

        def fake_open_search_box(connection, current_query, on_result, connection_owner=None,
                                  title='Search', text=''):
            captured['prompted'] = True
            on_result('2500')
        from novulon.menukit import search as search_mod
        original = search_mod.open_search_box
        search_mod.open_search_box = fake_open_search_box
        try:
            hmenu._personal_funds_row('CONN')
        finally:
            search_mod.open_search_box = original
        self.assertTrue(captured.get('prompted'))
        self.assertEqual(calls, ['money 2500 777'])

    def test_personal_funds_row_with_no_active_sim_does_not_crash_or_call_anything(self):
        calls = _install_fake_sims4_commands()
        _install_fake_services(active_sim_id=None)
        hmenu._personal_funds_row('CONN')
        self.assertEqual(calls, [])


class TestInstancedMembers(unittest.TestCase):
    def test_filters_to_instanced_only(self):
        household = [FakeSimInfo(1, instanced=True), FakeSimInfo(2, instanced=False),
                     FakeSimInfo(3, instanced=True)]
        result = hinv.instanced_members(household)
        self.assertEqual([s.id for s in result], [1, 3])

    def test_a_member_whose_is_instanced_raises_is_skipped_not_fatal(self):
        class Bad(object):
            id = 99

            def is_instanced(self):
                raise RuntimeError('boom')
        household = [FakeSimInfo(1, instanced=True), Bad()]
        result = hinv.instanced_members(household)
        self.assertEqual([s.id for s in result], [1])

    def test_empty_household_returns_empty(self):
        self.assertEqual(hinv.instanced_members([]), [])


class TestPurgeInstancedMembers(unittest.TestCase):
    def tearDown(self):
        _uninstall_fake_sims4_commands()

    def test_runs_inventory_purge_once_per_instanced_member(self):
        calls = _install_fake_sims4_commands()
        household = [FakeSimInfo(10, instanced=True), FakeSimInfo(20, instanced=False),
                     FakeSimInfo(30, instanced=True)]
        n = hinv.purge_instanced_members('CONN', household)
        self.assertEqual(n, 2)
        self.assertEqual(sorted(calls), ['inventory.purge 10', 'inventory.purge 30'])

    def test_a_bad_sim_id_does_not_stop_the_rest(self):
        fake_sims4 = types.ModuleType('sims4')
        fake_commands = types.ModuleType('sims4.commands')
        calls = []

        def execute(command_line, _connection):
            if '10' in command_line:
                raise RuntimeError('boom')
            calls.append(command_line)
        fake_commands.execute = execute
        fake_sims4.commands = fake_commands
        sys.modules['sims4'] = fake_sims4
        sys.modules['sims4.commands'] = fake_commands
        household = [FakeSimInfo(10, instanced=True), FakeSimInfo(20, instanced=True)]
        n = hinv.purge_instanced_members('CONN', household)
        self.assertEqual(calls, ['inventory.purge 20'])
        self.assertEqual(n, 1)   # only the one that didn't raise counts as attempted-and-ok


class TestConfirmOkCancel(unittest.TestCase):
    def test_degrades_safely_with_no_ui_module(self):
        # no ui.ui_dialog in sys.modules in this pure-3.12 test environment - must not raise
        shown = hinv.confirm_ok_cancel('CONN', 'Title', 'Text', lambda c: None)
        self.assertFalse(shown)


class TestPurgeRow(HouseholdTestCase):
    def test_no_active_household_notifies_and_does_nothing(self):
        calls = _install_fake_sims4_commands()
        _install_fake_services(household=None)
        hmenu._purge_inventory_row('CONN')
        self.assertEqual(calls, [])

    def test_no_instanced_members_notifies_and_does_nothing(self):
        calls = _install_fake_sims4_commands()
        _install_fake_services(household=[FakeSimInfo(1, instanced=False)])
        hmenu._purge_inventory_row('CONN')
        self.assertEqual(calls, [])


class TestSectionRegistration(unittest.TestCase):
    """household/__init__.py already ran at import time (module-level, guarded) - this just asserts what
    it did, the same way test_novulon_commands.py checks core's own section machinery."""

    def test_household_section_is_registered(self):
        keys = [k for k, _ in commands.sections()]
        self.assertIn('household', keys)

    def test_household_rows_are_all_registered_actions(self):
        page = hmenu.household_root('CONN')
        for row in page.rows:
            self.assertTrue(commands.is_registered(row.id), '%r not registered' % (row.id,))

    def test_root_page_pushes_without_raising(self):
        from novulon.menukit import stack
        page = commands.build_main_menu_page('CONN')
        nav = stack.NavStack()
        nav.push(page)


if __name__ == '__main__':
    unittest.main(verbosity=1)

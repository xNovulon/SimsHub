"""Tier-4-style tests for ingame/novulon/relationships/menu.py: name resolution, command-string
construction for set_score/add_bit/remove_bit, and the registered actions - same fake-module pattern as
test_novulon_gameplay.py, no real game needed (SPEC.md §16 Tier 4).
"""
import os
import sys
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands  # noqa: E402
from novulon.relationships import menu as rmenu  # noqa: E402
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


def _install_fake_services(active_sim_id=1, sim_by_name=None):
    fake_services = types.ModuleType('services')

    class _Info(object):
        def __init__(self, sid):
            self.id = sid
    fake_services.active_sim_info = (lambda: (_Info(active_sim_id) if active_sim_id is not None else None))

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
    original = search_mod.open_search_box
    queue = list(answers)

    def fake(connection, current_query, on_result, connection_owner=None, title='Search', text=''):
        value = queue.pop(0) if queue else None
        on_result(value)
    search_mod.open_search_box = fake

    def cleanup():
        search_mod.open_search_box = original
    return cleanup


class RelationshipsTestCase(unittest.TestCase):
    def setUp(self):
        self._cleanup_answers = None

    def tearDown(self):
        _uninstall_fake_exec()
        _uninstall_fake_services()
        if self._cleanup_answers:
            self._cleanup_answers()

    def answers(self, values):
        self._cleanup_answers = _install_fake_answers(values)


class TestResolveSimByName(unittest.TestCase):
    def test_splits_first_and_last_name(self):
        _install_fake_services(sim_by_name={('bob', 'pancakes'): 'BOB'})
        try:
            self.assertEqual(rmenu._resolve_sim_by_name('Bob Pancakes'), 'BOB')
        finally:
            _uninstall_fake_services()

    def test_single_word_name_uses_empty_last_name(self):
        _install_fake_services(sim_by_name={('bob', ''): 'BOB'})
        try:
            self.assertEqual(rmenu._resolve_sim_by_name('Bob'), 'BOB')
        finally:
            _uninstall_fake_services()

    def test_unknown_name_returns_none(self):
        _install_fake_services(sim_by_name={})
        try:
            self.assertIsNone(rmenu._resolve_sim_by_name('Nobody Home'))
        finally:
            _uninstall_fake_services()

    def test_no_services_module_returns_none_not_raise(self):
        self.assertIsNone(rmenu._resolve_sim_by_name('Bob Pancakes'))


class TestSetScore(RelationshipsTestCase):
    def test_source_is_active_sim_target_resolved_by_name(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1,
                                sim_by_name={('bob', 'pancakes'): types.SimpleNamespace(id=2)})
        self.answers(['Bob Pancakes', '50', 'LTR_Friendship_Main'])
        rmenu._set_score_row('CONN')
        self.assertEqual(calls, ['relationship.set_score 1 2 50 LTR_Friendship_Main'])

    def test_bidirectional_is_never_sent_since_the_engine_ignores_it(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1,
                                sim_by_name={('a', 'b'): types.SimpleNamespace(id=9)})
        self.answers(['A B', '10', 'LTR_Romance_Main'])
        rmenu._set_score_row('CONN')
        self.assertEqual(len(calls[0].split(' ')), 5)   # command + 4 args, no 5th bidirectional token

    def test_unknown_target_notifies_and_runs_nothing(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1, sim_by_name={})
        self.answers(['Nobody Here'])
        rmenu._set_score_row('CONN')
        self.assertEqual(calls, [])

    def test_no_active_sim_runs_nothing(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=None)
        rmenu._set_score_row('CONN')
        self.assertEqual(calls, [])


class TestAddRemoveBit(RelationshipsTestCase):
    def test_add_bit(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1,
                                sim_by_name={('bob', 'pancakes'): types.SimpleNamespace(id=2)})
        self.answers(['Bob Pancakes', 'BestFriends'])
        rmenu._add_bit_row('CONN')
        self.assertEqual(calls, ['relationship.add_bit 1 2 BestFriends'])

    def test_remove_bit(self):
        calls = _install_fake_exec()
        _install_fake_services(active_sim_id=1,
                                sim_by_name={('bob', 'pancakes'): types.SimpleNamespace(id=2)})
        self.answers(['Bob Pancakes', 'Enemies'])
        rmenu._remove_bit_row('CONN')
        self.assertEqual(calls, ['relationship.remove_bit 1 2 Enemies'])


class TestRegistration(unittest.TestCase):
    def test_every_relationships_action_is_registered(self):
        for action_id, _handler in rmenu.all_actions():
            self.assertTrue(commands.is_registered(action_id), action_id)

    def test_relationships_page_pushes_without_raising(self):
        from novulon.menukit import stack
        page = rmenu.relationships_page('CONN')
        nav = stack.NavStack()
        nav.push(page)

    def test_no_top_level_main_menu_tile_for_relationships(self):
        # §9.4/§1.4: Relationships is a Gameplay subgroup, never its own Main Menu section
        keys = [k for k, _ in commands.sections()]
        self.assertNotIn('relationships', keys)


if __name__ == '__main__':
    unittest.main(verbosity=1)

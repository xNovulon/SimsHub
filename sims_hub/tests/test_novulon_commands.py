"""Tier-4-style tests for ingame/novulon/commands.py: the action registry, the Main Menu section
registry, and the two cheat command bodies - driven directly with fake connections/fake sims4.commands,
no dialog and no real game needed (SPEC.md Sec 16 Tier 4: "commands.do(action_id, fake_connection, ...)
directly, with no dialog at all"). Uses the real menukit package (BP2) for build_main_menu_page(), since
it is a genuine, already-built sibling package by the time this test runs."""
import os
import shutil
import sys
import tempfile
import types
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, 'ingame'))

from novulon import commands, common  # noqa: E402
from novulon.menukit.page import Page  # noqa: E402


class CommandsTestCase(unittest.TestCase):
    """Every test gets a private slice of the action/section registries so tests never see each other's
    registrations (commands.py itself has no reset() - it's meant to be append-only for the life of the
    game process - so tests snapshot/restore the module dicts directly)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)
        self._actions_snapshot = dict(commands._actions)
        self._sections_snapshot = dict(commands._sections)
        self._registered_snapshot = commands._registered

    def tearDown(self):
        commands._actions.clear()
        commands._actions.update(self._actions_snapshot)
        commands._sections.clear()
        commands._sections.update(self._sections_snapshot)
        commands._registered = self._registered_snapshot
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestActionRegistry(CommandsTestCase):
    def test_add_and_is_registered(self):
        commands.add('test.one', lambda c, *a: 'ran')
        self.assertTrue(commands.is_registered('test.one'))
        self.assertFalse(commands.is_registered('test.unknown'))

    def test_do_calls_with_connection_and_args(self):
        seen = []
        commands.add('test.two', lambda c, *a: seen.append((c, a)))
        commands.do('test.two', 'CONN', 'x', 'y')
        self.assertEqual(seen, [('CONN', ('x', 'y'))])

    def test_do_returns_function_result(self):
        commands.add('test.three', lambda c, *a: 42)
        self.assertEqual(commands.do('test.three', 'CONN'), 42)

    def test_do_unknown_action_logs_and_returns_none(self):
        self.assertIsNone(commands.do('test.does.not.exist', 'CONN'))

    def test_do_swallows_exception_returns_none(self):
        def boom(c, *a):
            raise RuntimeError('kaboom')
        commands.add('test.boom', boom)
        self.assertIsNone(commands.do('test.boom', 'CONN'))

    def test_reregister_same_fn_is_silent_different_fn_is_logged(self):
        fn = lambda c, *a: None
        commands.add('test.four', fn)
        commands.add('test.four', fn)   # same function object - silent, no log line needed
        commands.add('test.four', lambda c, *a: None)   # different function - logged, but never raises
        self.assertTrue(commands.is_registered('test.four'))


class TestSectionRegistry(CommandsTestCase):
    def test_add_section_registers_action_too(self):
        commands.add_section('sims', lambda c, selected_ids=None: 'sims-page', label='Sims')
        self.assertTrue(commands.is_registered('novulon.menu.sims'))
        self.assertEqual(commands.do('novulon.menu.sims', 'CONN'), 'sims-page')

    def test_sections_ordered_by_order_then_key(self):
        commands.add_section('zzz', lambda c, selected_ids=None: None, label='Z', order=1)
        commands.add_section('aaa', lambda c, selected_ids=None: None, label='A', order=1)
        commands.add_section('first', lambda c, selected_ids=None: None, label='First', order=0)
        keys = [k for k, _ in commands.sections() if k in ('zzz', 'aaa', 'first')]
        self.assertEqual(keys, ['first', 'aaa', 'zzz'])

    def test_visible_sections_hides_when_predicate_false(self):
        commands.add_section('hidden', lambda c, selected_ids=None: None, label='Hidden',
                              is_visible=lambda: False)
        commands.add_section('shown', lambda c, selected_ids=None: None, label='Shown',
                              is_visible=lambda: True)
        keys = [k for k, _ in commands.visible_sections()]
        self.assertNotIn('hidden', keys)
        self.assertIn('shown', keys)

    def test_visible_sections_hides_on_exception_fail_closed(self):
        def boom():
            raise RuntimeError('probe failed')
        commands.add_section('flaky', lambda c, selected_ids=None: None, label='Flaky', is_visible=boom)
        keys = [k for k, _ in commands.visible_sections()]
        self.assertNotIn('flaky', keys)   # a broken visibility check hides the tile, never shows a broken one

    def test_visible_sections_none_means_always_shown(self):
        commands.add_section('always', lambda c, selected_ids=None: None, label='Always')
        keys = [k for k, _ in commands.visible_sections()]
        self.assertIn('always', keys)

    def test_build_main_menu_page_uses_real_menukit_row_and_page(self):
        commands.add_section('household', lambda c, selected_ids=None: None, label='Household',
                              description='Funds, needs, inventory.')
        page = commands.build_main_menu_page('CONN')
        self.assertIsInstance(page, Page)
        self.assertEqual(page.title, 'Novulon')
        self.assertEqual(page.style, 'tiles')
        ids = [r.id for r in page.rows]
        self.assertIn('novulon.menu.household', ids)
        row = next(r for r in page.rows if r.id == 'novulon.menu.household')
        self.assertEqual(row.label, 'Household')
        self.assertEqual(row.description, 'Funds, needs, inventory.')

    def test_root_page_validates_against_registered_actions(self):
        # every tile's row.id is registered via add_section() itself, so pushing the built page through
        # the real menukit NavStack must never raise "no registered command" for a Novulon-built tile
        from novulon.menukit import stack
        commands.add_section('gameplay', lambda c, selected_ids=None: None, label='Gameplay')
        page = commands.build_main_menu_page('CONN')
        nav = stack.NavStack()
        nav.push(page)   # raises ValueError if any row lacks a registered command - must not raise here


class FakeConnection(object):
    pass


class TestDoCommand(CommandsTestCase):
    def test_usage_message_on_empty_action_id(self):
        result = commands.do_command('', _connection=None)
        self.assertIsNone(result)

    def test_unknown_action_reported(self):
        result = commands.do_command('nope.nope', _connection=None)
        self.assertIsNone(result)

    def test_calls_through_and_does_not_crash_without_menukit_page(self):
        commands.add('test.plain', lambda c, *a: 'done')
        result = commands.do_command('test.plain', _connection=None)
        self.assertEqual(result, 'done')

    def test_page_like_result_attempts_show_but_never_raises(self):
        # a fake connection with no real game backing it: _show() will fail inside menukit's own game
        # imports, but do_command must swallow that and still return the Page it got
        page = Page('Sub Page', [])
        commands.add('test.subpage', lambda c, *a: page)
        result = commands.do_command('test.subpage', _connection=FakeConnection())
        self.assertIs(result, page)


class TestMenuCommand(CommandsTestCase):
    def test_menu_command_never_raises_with_no_real_game(self):
        commands.menu_command(_connection=None)   # must not raise even though menukit can't really show


class TestRegisterAndSessionResetHook(CommandsTestCase):
    def test_register_uses_fake_sims4_commands_and_is_idempotent(self):
        registered = {}

        class FakeCommandType(object):
            Live = 5

        def FakeCommand(name, command_type=None):
            def decorator(fn):
                registered[name] = fn
                return fn
            return decorator

        fake_sims4 = types.ModuleType('sims4')
        fake_commands_mod = types.ModuleType('sims4.commands')
        fake_commands_mod.Command = FakeCommand
        fake_commands_mod.CommandType = FakeCommandType
        fake_sims4.commands = fake_commands_mod
        sys.modules['sims4'] = fake_sims4
        sys.modules['sims4.commands'] = fake_commands_mod
        try:
            commands._registered = False
            ok = commands.register()
            self.assertTrue(ok)
            self.assertIn('novulon.menu', registered)
            self.assertIn('novulon.do', registered)
            # idempotent: calling again does not re-register (no exception, no duplicate work needed)
            again = commands.register()
            self.assertTrue(again)
        finally:
            sys.modules.pop('sims4', None)
            sys.modules.pop('sims4.commands', None)

    def test_install_session_reset_hook_wraps_on_enter_main_menu(self):
        calls = []

        def fake_on_enter_main_menu():
            calls.append('called')

        fake_services = types.ModuleType('services')
        fake_services.on_enter_main_menu = fake_on_enter_main_menu
        sys.modules['services'] = fake_services
        try:
            ok = commands.install_session_reset_hook()
            self.assertTrue(ok)
            fake_services.on_enter_main_menu()   # simulate the game calling it
            self.assertEqual(calls, ['called'])   # original still runs
        finally:
            sys.modules.pop('services', None)


if __name__ == '__main__':
    unittest.main(verbosity=1)

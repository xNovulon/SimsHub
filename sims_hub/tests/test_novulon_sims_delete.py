"""Tier-4-style tests for ingame/novulon/sims/delete.py: the staged delete state machine, driven with
FakeSimInfo/FakeHousehold/FakeResetAndDeleteService (tests/novulon_fakes.py) and small fake
`alarms`/`clock`/`services` modules - no fake Sims folder or game DLL needed (SPEC.md Sec 16 Tier 4).

The fake `alarms.add_alarm_real_time` records the poll callback instead of actually scheduling it, and
the test itself calls that callback repeatedly to simulate ticks - this drives `_await_uninstanced`'s
poll-then-timeout logic deterministically, in well under a second of real test time, instead of
sleeping through `delete.POLL_TIMEOUT_SECONDS` for real.
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

from novulon import common  # noqa: E402
from novulon.sims import delete  # noqa: E402
from tests.novulon_fakes import FakeSimInfo, FakeHousehold, FakeResetAndDeleteService  # noqa: E402


class FakeAlarmHandle(object):
    def __init__(self, callback):
        self.callback = callback
        self.canceled = False


class FakeAlarms(object):
    """Records every alarm added; `fire_all(times)` calls each live handle's callback that many times,
    the same one-argument-is-the-handle shape this session verified against the real `alarms.pyc`."""

    def __init__(self):
        self.handles = []

    def add_alarm_real_time(self, owner, time_span, callback, repeating=False, use_sleep_time=False,
                             cross_zone=False):
        if owner is None:
            raise ValueError('Alarm created without owner')   # mirrors the real AlarmHandle.__init__
        handle = FakeAlarmHandle(callback)
        self.handles.append(handle)
        return handle

    def cancel_alarm(self, handle):
        handle.canceled = True

    def fire_all(self, times=1):
        for _ in range(times):
            for handle in list(self.handles):
                if not handle.canceled:
                    handle.callback(handle)


class FakeClock(object):
    def interval_in_real_seconds(self, seconds):
        return seconds   # the fake alarms module never actually times anything, so the value is inert


class FakeGameServices(object):
    def __init__(self, active_sim_info=None, reset_and_delete_service=None):
        self._active_sim_info = active_sim_info
        self._rd_service = reset_and_delete_service or FakeResetAndDeleteService()

    def active_sim_info(self):
        return self._active_sim_info

    def get_reset_and_delete_service(self):
        return self._rd_service


class FakeGameEnv(object):
    def __init__(self, active_sim_info=None, reset_and_delete_service=None):
        self.services = FakeGameServices(active_sim_info, reset_and_delete_service)
        self.alarms = FakeAlarms()
        self.clock = FakeClock()

    def __enter__(self):
        fake_services = types.ModuleType('services')
        fake_services.active_sim_info = self.services.active_sim_info
        fake_services.get_reset_and_delete_service = self.services.get_reset_and_delete_service
        fake_alarms = types.ModuleType('alarms')
        fake_alarms.add_alarm_real_time = self.alarms.add_alarm_real_time
        fake_alarms.cancel_alarm = self.alarms.cancel_alarm
        fake_clock = types.ModuleType('clock')
        fake_clock.interval_in_real_seconds = self.clock.interval_in_real_seconds

        self._saved = {name: sys.modules.get(name) for name in ('services', 'alarms', 'clock')}
        sys.modules['services'] = fake_services
        sys.modules['alarms'] = fake_alarms
        sys.modules['clock'] = fake_clock
        return self

    def __exit__(self, *exc):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod


class DeleteTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='novulon_test_')
        common.configure(self.tmp)

    def tearDown(self):
        common.configure(None)
        shutil.rmtree(self.tmp, ignore_errors=True)


# ------------------------------------------------------------------------------ is_protected
class TestIsProtected(DeleteTestCase):
    def test_active_household_member_is_protected(self):
        household = FakeHousehold(1, active=True)
        sim = FakeSimInfo(household=household)
        with FakeGameEnv(active_sim_info=None):
            self.assertTrue(delete.is_protected(sim))

    def test_active_sim_is_protected_even_in_a_different_household(self):
        active = FakeSimInfo(id=99, household=FakeHousehold(2, active=False))
        with FakeGameEnv(active_sim_info=active):
            self.assertTrue(delete.is_protected(active))

    def test_ordinary_sim_is_not_protected(self):
        active = FakeSimInfo(id=1, household=FakeHousehold(1, active=True))
        other = FakeSimInfo(id=2, household=FakeHousehold(2, active=False))
        with FakeGameEnv(active_sim_info=active):
            self.assertFalse(delete.is_protected(other))

    def test_no_household_and_not_active_sim_is_not_protected(self):
        with FakeGameEnv(active_sim_info=None):
            self.assertFalse(delete.is_protected(FakeSimInfo(household=None)))

    def test_never_raises_with_no_game_modules(self):
        self.assertFalse(delete.is_protected(FakeSimInfo(household=None)))


# ------------------------------------------------------------------------------ request_delete
class TestRequestDelete(DeleteTestCase):
    def test_splits_protected_and_deletable_and_calls_confirm(self):
        household = FakeHousehold(1, active=True)
        protected = FakeSimInfo(first_name='Alex', last_name='Doe', household=household)
        deletable = FakeSimInfo(first_name='Bob', last_name='Pancakes', household=FakeHousehold(2))
        calls = {}

        def fake_confirm_delete(connection, sim_infos, protected_note=(), on_confirm=None, **kw):
            calls['connection'] = connection
            calls['sim_infos'] = list(sim_infos)
            calls['protected_note'] = list(protected_note)
            calls['on_confirm'] = on_confirm

        orig = delete.menukit.confirm_delete
        delete.menukit.confirm_delete = fake_confirm_delete
        try:
            with FakeGameEnv(active_sim_info=None):
                delete.request_delete('CONN', [protected, deletable])
        finally:
            delete.menukit.confirm_delete = orig

        self.assertEqual(calls['sim_infos'], [deletable])
        self.assertEqual(calls['protected_note'], [protected])
        self.assertIsNotNone(calls['on_confirm'])


# ------------------------------------------------------------------------------ the batch itself
class TestRunAndDeleteOne(DeleteTestCase):
    def test_batch_with_one_protected_and_two_deletable_deletes_exactly_the_two(self):
        """SPEC.md Sec 16 Tier 4's own explicit assertion: a batch with one protected and two
        deletable Sims deletes exactly the two - not zero, not three."""
        active = FakeSimInfo(id=1, household=FakeHousehold(1, active=True))
        a = FakeSimInfo(id=2, household=FakeHousehold(2), instanced=False)
        b = FakeSimInfo(id=3, household=FakeHousehold(3), instanced=False)
        with FakeGameEnv(active_sim_info=active):
            delete._run('CONN', [active, a, b])
        self.assertTrue(active.removed is False)   # re-checked and skipped, never removed
        self.assertTrue(a.removed)
        self.assertTrue(b.removed)

    def test_non_instanced_sim_deletes_synchronously(self):
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=False)
        with FakeGameEnv(active_sim_info=None):
            results = {'deleted': [], 'failed': [], 'skipped': []}
            done = []
            delete._delete_one(sim, results, lambda: done.append(1))
        self.assertEqual(results['deleted'], [sim])
        self.assertTrue(sim.removed)
        self.assertEqual(done, [1])

    def test_instanced_sim_deletes_once_the_poll_sees_it_leave(self):
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=True)
        rd = FakeResetAndDeleteService(auto_finish=False)   # never auto-finishes - the poll must do it
        with FakeGameEnv(active_sim_info=None, reset_and_delete_service=rd) as env:
            results = {'deleted': [], 'failed': [], 'skipped': []}
            done = []
            delete._delete_one(sim, results, lambda: done.append(1))
            self.assertEqual(results['deleted'], [])   # not yet - still instanced
            self.assertEqual(done, [])
            rd.finish_now(sim)                            # simulate the reset service reaching DESTROY
            env.alarms.fire_all(1)                          # the next poll tick observes it
        self.assertEqual(results['deleted'], [sim])
        self.assertTrue(sim.removed)
        self.assertEqual(done, [1])

    def test_instanced_sim_that_never_leaves_times_out_and_is_never_force_removed(self):
        """The bounded-timeout-and-skip path SPEC.md Sec 16 Tier 4 asks be provably exercised, not
        just the happy path - `auto_finish=False` and the fake alarm ticks past the real timeout."""
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=True)
        rd = FakeResetAndDeleteService(auto_finish=False)
        with FakeGameEnv(active_sim_info=None, reset_and_delete_service=rd) as env:
            results = {'deleted': [], 'failed': [], 'skipped': []}
            done = []
            delete._delete_one(sim, results, lambda: done.append(1))
            ticks = int(delete.POLL_TIMEOUT_SECONDS / delete.POLL_INTERVAL_SECONDS) + 2
            env.alarms.fire_all(ticks)   # sim never leaves the instanced set the whole time
        self.assertEqual(results['deleted'], [])
        self.assertEqual(results['failed'], [sim])
        self.assertFalse(sim.removed)   # never force-removed - protecting the save outranks the batch
        self.assertEqual(done, [1])

    def test_protected_mid_batch_is_skipped_not_deleted(self):
        sim = FakeSimInfo(household=FakeHousehold(1, active=True), instanced=False)
        with FakeGameEnv(active_sim_info=None):
            results = {'deleted': [], 'failed': [], 'skipped': []}
            delete._delete_one(sim, results, lambda: None)
        self.assertEqual(results['skipped'], [sim])
        self.assertFalse(sim.removed)

    def test_trigger_destroy_failure_is_recorded_failed_not_deleted(self):
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=True)

        class _RaisingRD(object):
            def trigger_destroy(self, *a, **k):
                raise RuntimeError('boom')
        with FakeGameEnv(active_sim_info=None, reset_and_delete_service=_RaisingRD()):
            results = {'deleted': [], 'failed': [], 'skipped': []}
            done = []
            delete._delete_one(sim, results, lambda: done.append(1))
        self.assertEqual(results['failed'], [sim])
        self.assertFalse(sim.removed)
        self.assertEqual(done, [1])

    def test_no_reset_and_delete_service_is_recorded_failed(self):
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=True)

        class _NoneRD(object):
            def get_reset_and_delete_service(self):
                return None
        fake_services = types.ModuleType('services')
        fake_services.get_reset_and_delete_service = _NoneRD().get_reset_and_delete_service
        fake_services.active_sim_info = lambda: None
        saved = sys.modules.get('services')
        sys.modules['services'] = fake_services
        try:
            results = {'deleted': [], 'failed': [], 'skipped': []}
            done = []
            delete._delete_one(sim, results, lambda: done.append(1))
        finally:
            if saved is None:
                sys.modules.pop('services', None)
            else:
                sys.modules['services'] = saved
        self.assertEqual(results['failed'], [sim])
        self.assertEqual(done, [1])

    def test_remove_permanently_raising_is_recorded_failed(self):
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=False)

        def _boom(household=None):
            raise RuntimeError('disk full')
        sim.remove_permanently = _boom
        with FakeGameEnv(active_sim_info=None):
            results = {'deleted': [], 'failed': [], 'skipped': []}
            delete._delete_one(sim, results, lambda: None)
        self.assertEqual(results['failed'], [sim])
        self.assertEqual(results['deleted'], [])

    def test_delete_one_never_raises_even_if_the_body_does(self):
        sim = FakeSimInfo(household=FakeHousehold(1))

        def _boom():
            raise RuntimeError('unexpected')
        orig = delete.is_protected
        delete.is_protected = lambda s: _boom()
        try:
            results = {'deleted': [], 'failed': [], 'skipped': []}
            done = []
            delete._delete_one(sim, results, lambda: done.append(1))
        finally:
            delete.is_protected = orig
        self.assertEqual(results['failed'], [sim])
        self.assertEqual(done, [1])   # on_done still fires exactly once - the batch can't hang


class TestOnceHelper(unittest.TestCase):
    def test_only_runs_the_wrapped_function_once(self):
        calls = []
        once = delete._once(lambda *a: calls.append(a))
        once(1)
        once(2)
        once(3)
        self.assertEqual(calls, [(1,)])


class TestFinishBatchNotifications(DeleteTestCase):
    def test_all_protected_notifies_nothing_was_deleted(self):
        seen = []
        orig = delete.menukit.notify
        delete.menukit.notify = lambda title, text, **k: seen.append((title, text))
        try:
            delete._run('CONN', [])
        finally:
            delete.menukit.notify = orig
        self.assertEqual(seen, [('Nothing was deleted.', 'Every selected Sim is protected.')])

    def test_successful_batch_notifies_a_count(self):
        seen = []
        orig = delete.menukit.notify
        delete.menukit.notify = lambda title, text, **k: seen.append((title, text))
        sims = [FakeSimInfo(household=FakeHousehold(1), instanced=False),
                FakeSimInfo(household=FakeHousehold(2), instanced=False)]
        try:
            with FakeGameEnv(active_sim_info=None):
                delete._run('CONN', sims)
        finally:
            delete.menukit.notify = orig
        self.assertEqual(seen, [('Deleted.', '2 Sims deleted.')])


# ------------------------------------------------------------------------------ deletions.log
class TestDeletionsLog(DeleteTestCase):
    def test_successful_delete_appends_one_line(self):
        sim = FakeSimInfo(first_name='Bob', last_name='Pancakes', household=FakeHousehold(1), instanced=False)
        with FakeGameEnv(active_sim_info=None):
            results = {'deleted': [], 'failed': [], 'skipped': []}
            delete._delete_one(sim, results, lambda: None)
        log_path = os.path.join(self.tmp, 'Novulon', 'logs', 'deletions.log')
        self.assertTrue(os.path.isfile(log_path))
        with open(log_path, encoding='utf-8') as f:
            line = f.read()
        self.assertIn('Bob Pancakes', line)
        self.assertIn('id=%s' % sim.id, line)

    def test_failed_delete_does_not_append_a_line(self):
        sim = FakeSimInfo(household=FakeHousehold(1), instanced=True)
        rd = FakeResetAndDeleteService(auto_finish=False)
        with FakeGameEnv(active_sim_info=None, reset_and_delete_service=rd) as env:
            results = {'deleted': [], 'failed': [], 'skipped': []}
            delete._delete_one(sim, results, lambda: None)
            env.alarms.fire_all(int(delete.POLL_TIMEOUT_SECONDS / delete.POLL_INTERVAL_SECONDS) + 2)
        log_path = os.path.join(self.tmp, 'Novulon', 'logs', 'deletions.log')
        self.assertFalse(os.path.isfile(log_path))


if __name__ == '__main__':
    unittest.main(verbosity=1)

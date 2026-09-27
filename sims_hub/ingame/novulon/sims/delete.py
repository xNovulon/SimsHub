"""Staged Sim delete (SPEC.md `sims/delete.py` Sec 5.6, `gaps.md` Sec A.2, build package BP6).

**The scheduling primitive** (SPEC.md Sec 18: "build-blocking open item... the exact scheduling
primitive for the poll... unconfirmed"). This session closed it by disassembling `alarms.pyc`
(`simulation.zip`) directly:

    alarms.add_alarm_real_time(owner, time_span, callback, repeating, use_sleep_time, cross_zone)
        -> AlarmHandle(owner, callback, services.time_service().wall_clock_timeline, ...)

Fully verified, function by function:
  * `add_alarm_real_time` (line 71) schedules against `services.time_service().wall_clock_timeline` -
    REAL wall-clock time, deliberately chosen over `add_alarm`'s in-game-clock timeline (line 24) so a
    paused or fast-forwarded game clock can never stall or rush this safety poll.
  * `clock.interval_in_real_seconds(seconds)` (line 71) -> `TimeSpan(seconds *
    date_and_time.TICKS_PER_REAL_WORLD_SECOND)` - the real, verified way to build `time_span`.
  * `AlarmHandle.__init__` (line 147) RAISES `ValueError('Alarm created without owner')` if `owner is
    None` (and later does `weakref.ref(owner, ...)` - `owner` must be a real, weakly-referenceable
    object, never `None` and never a plain int/str). This file uses
    `services.get_reset_and_delete_service()` as the owner - a long-lived singleton that is already
    being used for `trigger_destroy` in the same flow, so it is guaranteed alive for exactly as long as
    this poll needs it.
  * `AlarmElement._run`/`RepeatingAlarmElement._run` (lines 259/291) both disassemble to
    `self.callback(_lookup_alarm_handle(self._element_handle))` - the callback receives exactly ONE
    argument, the `AlarmHandle` itself (needed to call `alarms.cancel_alarm(handle)` from inside the
    callback body).
  * `alarms.cancel_alarm(handle)` (line 103) stops a repeating alarm.

`_await_uninstanced` below polls `sim_info.is_instanced()` on a short repeating real-time alarm and
resolves `on_done(True)` the moment it returns False, or `on_done(False)` once a bounded real-time
timeout elapses - `gaps.md` Sec A.2's own recommendation, now backed by a disassembled primitive rather
than "an alarms-style repeating callback vs. a reset-service completion signal" left as an open
question. A Sim that never leaves the instanced set within the timeout is recorded `failed` and
**never** force-removed - `SimInfo.remove_permanently()` is only ever called once `is_instanced()` has
actually gone False (or was already False to begin with), protecting the save over completing a batch.

**The delete call chain** (`gaps.md` Sec A.2, `game_api.md` Sec 4, both re-verified this session against
`services/reset_and_delete_service.pyc`/`sims/sim_info.pyc`):
  * `services.get_reset_and_delete_service().trigger_destroy(obj, source, cause)`
    (`reset_and_delete_service.pyc:292`) -> `self.trigger_reset(obj, ResetReason.BEING_DESTROYED,
    source=source, cause=cause)` -> builds a `ResetRecord` and calls `self.start_processing()` - this
    is the START of the staged state machine (`gaps.md` Sec A.2's `PENDING -> ... -> DESTROY`), not a
    same-tick completion. `source`/`cause` are stored on the record and only read back on the
    `RESET_ON_ERROR` branch (verified by disassembling `trigger_reset`, line 299) - our
    `BEING_DESTROYED` path never reaches that branch, so `source=None, cause='Novulon delete'` is a
    safe, inert diagnostic tag, not a guessed-at required type.
  * `SimInfo.remove_permanently(household=None, culled=False)` (`sims/sim_info.pyc:5517`) - called ONLY
    after `is_instanced()` is confirmed False (or was never instanced). This is the point of no return
    (`gaps.md` Sec A.4: no undo path exists once this has run) - `delete.py` keeps an append-only
    `deletions.log` line per completed delete for the player's own record, never a restore path.

**Protection** (`game_api.md` Sec 4's verified guard points, re-checked this session):
`Household.is_active_household()` (`sims/household.pyc:338`) and `services.active_sim_info()`
(`services/__init__.pyc:800`). `is_protected` is called twice by design: once in `request_delete` to
build the confirmation dialog's two lists, and again per-Sim inside `_delete_one` - a batch's
active-household/active-Sim membership can change mid-batch (a big multi-Sim delete takes real wall-
clock time via the poll above), so the second check is not redundant.

**No undo, by design** - `gaps.md` Sec A.4 disassembled `sims.recreate` in full and confirmed it has no
code path once `remove_permanently()` has run. This file leans entirely on `menukit.confirm_delete`'s
named-list confirmation as the safety net, per that finding's own recommendation.
"""
import os
import time

from .. import common
from .. import menukit

POLL_INTERVAL_SECONDS = 0.5
POLL_TIMEOUT_SECONDS = 10.0


# ======================================================================== protection
def is_protected(sim_info):
    """True if `sim_info` is the active household's member or the active Sim - never deletable."""
    household = getattr(sim_info, 'household', None)
    if household is not None and common.guarded(
            'novulon delete: is_active_household', household.is_active_household):
        return True
    try:
        import services
    except Exception:
        return False
    active = common.guarded('novulon delete: active_sim_info', services.active_sim_info)
    if active is None:
        return False
    return getattr(active, 'id', None) == getattr(sim_info, 'id', None)


# ======================================================================== entry point
def request_delete(connection, sim_infos):
    """Entry point from a menu row or `novulon.do sims.actions.delete_selected`. `sim_infos`: every Sim
    the player picked, protected ones included - `menukit.confirm_delete` splits them into the real
    named list that will be deleted and the (capped) protected note, and shows nothing at all (a plain
    notify instead) if every one of them turns out to be protected."""
    protected = [s for s in sim_infos if is_protected(s)]
    deletable = [s for s in sim_infos if s not in protected]
    menukit.confirm_delete(connection, deletable, protected_note=protected,
                            on_confirm=lambda conn: _run(conn, deletable))
    return None


# ======================================================================== the batch
def _once(fn):
    """Wrap `fn` so it only ever actually runs once, however many times the wrapper is called - used
    so a Sim whose delete raises partway through still lets the batch's summary notify fire exactly
    once, instead of hanging forever waiting for a decrement that never happens."""
    state = {'done': False}

    def _wrapped(*args, **kwargs):
        if state['done']:
            return
        state['done'] = True
        fn(*args, **kwargs)
    return _wrapped


def _run(connection, sim_infos):
    if not sim_infos:
        menukit.notify('Nothing was deleted.', 'Every selected Sim is protected.')
        return
    results = {'deleted': [], 'failed': [], 'skipped': []}
    state = {'pending': len(sim_infos)}

    def _one_done():
        state['pending'] -= 1
        if state['pending'] <= 0:
            _finish_batch(connection, results)

    for sim_info in sim_infos:
        _delete_one(sim_info, results, _one_done)


def _finish_batch(connection, results):
    n_deleted = len(results['deleted'])
    n_failed = len(results['failed'])
    n_skipped = len(results['skipped'])
    if n_deleted == 0 and n_failed == 0 and n_skipped == 0:
        menukit.notify('Nothing was deleted.', 'Every selected Sim is protected.')
        return
    if n_deleted == 0:
        menukit.notify('Nothing changed.', 'Something went wrong.', urgent=True)
        return
    text = ('1 Sim deleted.' if n_deleted == 1 else '%d Sims deleted.' % n_deleted)
    if n_failed:
        text += ' %d could not be removed.' % n_failed
    menukit.notify('Deleted.', text)


# ======================================================================== one Sim
def _delete_one(sim_info, results, on_done):
    """Never raises out to its caller (`_run`'s own loop) - any unexpected failure is recorded
    `failed` and `on_done` still fires exactly once, so one bad Sim can never hang the whole batch's
    summary notification."""
    once = _once(on_done)

    def _body():
        _delete_one_body(sim_info, results, once)
        return True
    ok = common.guarded('novulon delete: %s' % getattr(sim_info, 'id', '?'), _body)
    if not ok:
        results['failed'].append(sim_info)
        once()


def _delete_one_body(sim_info, results, on_done):
    if is_protected(sim_info):        # re-checked here: state can change mid-batch (SPEC.md Sec 5.6)
        results['skipped'].append(sim_info)
        on_done()
        return
    instanced = common.guarded('novulon delete: is_instanced', sim_info.is_instanced)
    if instanced:
        instance = common.guarded('novulon delete: get_sim_instance', sim_info.get_sim_instance)
        if instance is None:
            _finish(sim_info, False, results)
            on_done()
            return
        if not _trigger_destroy(instance):
            _finish(sim_info, False, results)
            on_done()
            return

        def _on_uninstanced(ok):
            _finish(sim_info, ok, results)
            on_done()
        _await_uninstanced(sim_info, _on_uninstanced)
    else:
        _finish(sim_info, True, results)
        on_done()


def _trigger_destroy(instance):
    try:
        import services
    except Exception:
        return False
    rd_service = common.guarded('novulon delete: get_reset_and_delete_service', services.get_reset_and_delete_service)
    if rd_service is None:
        return False

    def _call():
        rd_service.trigger_destroy(instance, source=None, cause='Novulon delete')
        return True
    return bool(common.guarded('novulon delete: trigger_destroy', _call))


def _still_instanced(sim_info):
    """`sim_info.is_instanced()`, failing OPEN (treated as "still instanced") on any error - the safer
    direction, since the caller only removes the SimInfo once this is confirmed False."""
    result = common.guarded('novulon delete: is_instanced (poll)', sim_info.is_instanced)
    return True if result is None else bool(result)


def _await_uninstanced(sim_info, on_done):
    """Polls `sim_info.is_instanced()` on a short repeating real-time alarm; resolves `on_done(True)`
    once it goes False, `on_done(False)` if `POLL_TIMEOUT_SECONDS` elapses first. See the module
    docstring for the full verification of `alarms.add_alarm_real_time`."""
    try:
        import alarms
        import clock
        import services
    except Exception:
        common.log_exception('novulon delete: importing alarms/clock/services')
        on_done(False)
        return
    owner = common.guarded('novulon delete: get_reset_and_delete_service (alarm owner)',
                            services.get_reset_and_delete_service)
    if owner is None:
        on_done(False)
        return

    state = {'elapsed': 0.0}

    def _poll_body(handle):
        if not _still_instanced(sim_info):
            common.guarded('novulon delete: cancel_alarm', alarms.cancel_alarm, handle)
            on_done(True)
            return
        state['elapsed'] += POLL_INTERVAL_SECONDS
        if state['elapsed'] >= POLL_TIMEOUT_SECONDS:
            common.guarded('novulon delete: cancel_alarm (timeout)', alarms.cancel_alarm, handle)
            common.log('novulon delete: %s never left the instanced set within %.1fs - not removing '
                       'SimInfo' % (getattr(sim_info, 'id', '?'), POLL_TIMEOUT_SECONDS))
            on_done(False)

    def _poll(handle):
        common.guarded('novulon delete: poll', _poll_body, handle)

    handle = common.guarded(
        'novulon delete: add_alarm_real_time', alarms.add_alarm_real_time, owner,
        clock.interval_in_real_seconds(POLL_INTERVAL_SECONDS), _poll,
        repeating=True, use_sleep_time=False, cross_zone=False)
    if handle is None:
        on_done(False)


def _finish(sim_info, ok, results):
    if not ok:
        results['failed'].append(sim_info)
        common.log('novulon delete: %s never left the instanced set, not removing SimInfo'
                   % getattr(sim_info, 'id', '?'))
        return
    household = getattr(sim_info, 'household', None)

    def _call():
        sim_info.remove_permanently(household)
        return True
    if not common.guarded('novulon delete: remove_permanently', _call):
        results['failed'].append(sim_info)
        return
    _log_deletion(sim_info)
    results['deleted'].append(sim_info)


# ======================================================================== deletions.log
def _display_name(sim_info):
    full = getattr(sim_info, 'full_name', None)
    if full:
        return full
    first = getattr(sim_info, 'first_name', '') or ''
    last = getattr(sim_info, 'last_name', '') or ''
    return (first + ' ' + last).strip() or ('Sim %s' % getattr(sim_info, 'id', '?'))


def _log_deletion(sim_info):
    """Append-only `<Sims 4>\\Novulon\\logs\\deletions.log` line: name, id, timestamp - informational
    only, never a restore path (`gaps.md` Sec A.4)."""
    try:
        d = common.logs_dir()
        if not d:
            return
        path = os.path.join(d, 'deletions.log')
        line = '%s  %s  id=%s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), _display_name(sim_info),
                                    getattr(sim_info, 'id', '?'))
        with open(path, 'a', encoding='utf-8', errors='replace') as f:
            f.write(line)
    except Exception:
        common.log_exception('novulon delete: writing deletions.log')

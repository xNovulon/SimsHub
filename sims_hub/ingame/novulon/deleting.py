"""Deleting a Sim for good, safely - the order the game itself needs, checked in its own code.

  1. A Sim on the lot is first taken off it: services.get_reset_and_delete_service().trigger_destroy(sim, source=None,
     cause='Novulon delete') starts the game's own staged destroy (services/reset_and_delete_service.pyc:292).
  2. A short real-time check (alarms.add_alarm_real_time with clock.interval_in_real_seconds, every 0.5 s, at most
     10 s; the callback gets the AlarmHandle, alarms.cancel_alarm(handle) stops it) waits until
     sim_info.is_instanced() is False. It only exists while a delete is going on.
  3. Only then sim_info.remove_permanently(household) (sims/sim_info.pyc:5517) - the point of no return. A Sim that
     never leaves the lot within 10 s is left alone, never forced out.
Every finished delete adds a line to <Sims 4>\\Novulon\\logs\\deletions.log, for the player's own record.

Never deleted: the Sim being played, anyone in the household being played (protected()).
"""
import os
import time

from . import common

POLL_SECONDS = 0.5
TIMEOUT_SECONDS = 10.0


def protected(sim_info):
    """Why this Sim can't be deleted, or '' when it can."""
    import services
    me = services.active_sim_info()
    if me is not None and getattr(me, 'id', None) == getattr(sim_info, 'id', 0):
        return 'This is the Sim being played.'
    hh = services.active_household()
    if hh is not None and getattr(sim_info, 'household_id', None) == getattr(hh, 'id', 0):
        return 'Sims in the household being played can\'t be deleted.'
    return ''


def delete(sim_info, on_done=None):
    """Start deleting one Sim. on_done(worked) runs when it's finished (straight away for a Sim not on the lot)."""
    on_done = on_done or (lambda worked: None)
    if protected(sim_info):
        on_done(False)
        return
    if not sim_info.is_instanced():
        on_done(_remove(sim_info))
        return
    import services
    sim = sim_info.get_sim_instance()
    if sim is None:
        on_done(False)
        return
    services.get_reset_and_delete_service().trigger_destroy(sim, source=None, cause='Novulon delete')
    _when_gone(sim_info, lambda gone: on_done(_remove(sim_info) if gone else False))


def _when_gone(sim_info, on_done):
    import alarms
    import clock
    import services
    state = {'waited': 0.0}

    def poll(handle):
        try:
            still = sim_info.is_instanced()
        except Exception:
            still = True                      # unsure: never remove
        if not still:
            alarms.cancel_alarm(handle)
            on_done(True)
            return
        state['waited'] += POLL_SECONDS
        if state['waited'] >= TIMEOUT_SECONDS:
            alarms.cancel_alarm(handle)
            common.log('delete: %s never left the lot within %.0f s - left alone' % (sim_info.id, TIMEOUT_SECONDS))
            on_done(False)

    alarms.add_alarm_real_time(services.get_reset_and_delete_service(), clock.interval_in_real_seconds(POLL_SECONDS),
                               lambda h: common.guarded('delete check', poll, h), repeating=True,
                               use_sleep_time=False, cross_zone=False)


def _remove(sim_info):
    try:
        sim_info.remove_permanently(getattr(sim_info, 'household', None))
    except Exception:
        common.log_exception('delete: remove_permanently %s' % getattr(sim_info, 'id', '?'))
        return False
    try:
        d = common.data_dir('logs')
        if d:
            name = ('%s %s' % (getattr(sim_info, 'first_name', ''), getattr(sim_info, 'last_name', ''))).strip()
            with open(os.path.join(d, 'deletions.log'), 'a', encoding='utf-8', errors='replace') as f:
                f.write('%s  %s  id=%s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), name, sim_info.id))
    except Exception:
        pass
    return True

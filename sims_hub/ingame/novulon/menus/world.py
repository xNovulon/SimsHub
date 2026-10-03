"""World: the time of day, how fast time goes, and whether Sims do things on their own."""
from .. import actions, ui

TIMES = [('Morning', 8), ('Noon', 12), ('Evening', 18), ('Night', 22)]


def build(conn):
    rows = [ui.Row('Set the time to %s (%d:00)' % (name, hour), _time(hour), icon='time')
            for name, hour in TIMES]
    rows += [
        ui.Row('Set another time', _custom_time, icon='edit'),
        ui.Row('Autonomy on', _autonomy(True), icon='autonomy', desc='Sims do things on their own'),
        ui.Row('Autonomy off', _autonomy(False), icon='off', desc='Sims only do what they are told'),
    ]
    return ui.Page('World', rows, subtitle='The time is %s.' % actions.time_text(), icon='world')


def _time(hour):
    def action(conn):
        worked, msg = actions.set_time(hour)
        ui.notify('World', msg, icon='time' if worked else 'warning')
        return ui.STAY
    return action


def _custom_time(conn):
    def done(c, hour):
        worked, msg = actions.set_time(hour)
        ui.notify('World', msg, icon='time' if worked else 'warning')
        ui.show(c)
    ui.ask_number(conn, 'Set another time', 'Which hour, from 0 to 23?', done, minimum=0, maximum=23, icon='time')
    return None


def _autonomy(on):
    def action(conn):
        worked, msg = actions.set_autonomy(on)
        ui.notify('World', msg, icon='autonomy' if worked else 'warning')
        return ui.STAY
    return action

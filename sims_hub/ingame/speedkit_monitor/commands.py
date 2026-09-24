"""Cheat-console commands (no testingcheats needed: CommandType.Live).

  speedkit.lag [seconds|stop|status] [hz]   start the lag meter (default 60 s at 25 Hz), stop it early, or ask
  speedkit.cc                               run the CC guard now for the active household
  speedkit.status                           what the monitor has recorded this session

sims4.commands.Command(*aliases, command_type=...) registers the function; CommandType.Live = 5 is valid
in the retail game (core.zip sims4/commands.pyc: only DebugOnly is refused by is_valid_command).
Arguments arrive as strings and are converted with the annotation (str here). Output goes to
sims4.commands.CheatOutput(_connection). Registration happens in register(), so importing this module
outside the game does nothing.
"""
from . import common

_registered = False


def lag_command(arg='', hz='', _connection=None):
    """Body of 'speedkit.lag'. Returns the lines printed (for tests)."""
    from . import lagmeter
    out = common.cheat_output(_connection)
    a = (arg or '').strip().lower()
    if a in ('stop', 'end', 'off'):
        if not lagmeter.running():
            lines = ['SpeedKit lag meter is not running. Start it with: speedkit.lag 60']
        else:
            r = lagmeter.finish('stop command')
            lines = [] if r else ['SpeedKit lag meter stopped (no report, see monitor.log)']
    elif a in ('status', '?'):
        lines = [lagmeter.status()]
    else:
        try:
            seconds = int(a) if a else lagmeter.DEFAULT_SECONDS
            rate = int(hz) if hz else lagmeter.DEFAULT_HZ
        except ValueError:
            lines = ['Usage: speedkit.lag [seconds|stop|status] [samples per second]']
        else:
            lines = [lagmeter.start(seconds, rate, _connection)]
    for line in lines:
        out(line)
    return lines


def cc_command(_connection=None):
    """Body of 'speedkit.cc'."""
    from . import ccguard
    out = common.cheat_output(_connection)
    r = common.guarded('speedkit.cc', ccguard.check, True)
    if r is None:
        lines = ['SpeedKit CC guard failed - see SpeedKit\\reports\\monitor.log']
    elif r['sims']:
        lines = ['SpeedKit CC guard: %d sim(s) wear %d CAS part(s) that are not loaded. Details in monitor.log.' % (
            len(r['sims']), len(r['missing']))]
    else:
        lines = ['SpeedKit CC guard: all %d CAS parts worn by the household are loaded.' % r['checked']]
    for line in lines:
        out(line)
    return lines


def status_command(_connection=None):
    """Body of 'speedkit.status'."""
    from . import lagmeter, loadtimer
    out = common.cheat_output(_connection)
    st = loadtimer.state
    lines = ['SpeedKit Monitor %s, reports in %s' % (common.VERSION, common.reports_dir()),
             'launch %s via %s; scripts at +%s s; main menu events %d; lots loaded %d' % (
                 loadtimer._fmt(st['launch']) or '?', st['launch_source'],
                 loadtimer.seconds(st['launch'], st['import_time']), st['menus'], st['lots']),
             lagmeter.status()]
    for line in lines:
        out(line)
    return lines


def register():
    """Register the cheat commands with the game (once). Returns True on success."""
    global _registered
    if _registered:
        return True
    import sims4.commands
    live = sims4.commands.CommandType.Live

    @sims4.commands.Command('speedkit.lag', command_type=live)
    def speedkit_lag(arg: str = '', hz: str = '', _connection=None):
        common.guarded('speedkit.lag', lag_command, arg, hz, _connection)

    @sims4.commands.Command('speedkit.cc', command_type=live)
    def speedkit_cc(_connection=None):
        common.guarded('speedkit.cc', cc_command, _connection)

    @sims4.commands.Command('speedkit.status', command_type=live)
    def speedkit_status(_connection=None):
        common.guarded('speedkit.status', status_command, _connection)

    _registered = True
    return True

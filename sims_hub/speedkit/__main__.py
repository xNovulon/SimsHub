r"""python -m speedkit <command>  -  Novulon's Sims Hub from the command line (plain output).

    status                         what is active, graphics, memory, packs, last load times
    saves                          your saves: name, household, world, sims, lots, CC, pack
    play fast|full|studio|save:<slot>      prepare everything and start the game
    prepare fast|full|studio|save:<slot>   the same, without starting the game
    undo                           undo the last SpeedKit change
    inbox [--apply]                what the download Inbox holds (--apply installs it)
    cleanup [--apply]              duplicate copies that can go (--apply removes them, kept in a quarantine)
    graphics [tune|restore] [--apply]      SpeedKit Max Quality table / install / put the old file back
    report                         write reports\library_report.html
    game [<folder>]                where the game is (with a folder: remember that one)
"""
import sys

from . import api


def _say(text):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode('ascii', 'backslashreplace').decode(), flush=True)


def _progress(step, fraction, message):
    if message:
        _say('  ... %s' % message)


def _steps(r):
    for s in r.get('steps', []):
        _say('  [%s] %s' % ('ok' if s['ok'] else '!!', s['message']))


def _status():
    st = api.status()
    if not st.get('ok'):
        _say(st.get('message'))
        return 1
    g = st['game']
    _say('Game:      %s' % (g['exe'] if g['found'] else g['message']))
    if st['game_running']:
        _say('           The Sims 4 is running now.')
    _say('Mods:      %s' % st['profile']['label'])
    _say('Graphics:  %s' % st['graphics']['label'])
    m = st['memory']
    _say('Memory:    %s GB free of %s GB' % (m.get('free_gb'), m.get('total_gb')))
    for w in m.get('warnings', []):
        _say('           ! %s' % w)
    lib = st['library']
    _say('Library:   %d packages, %.1f GB, %s CAS parts (fast mode: %s)' % (
        lib['packages'], lib['gb'], '{:,}'.format(lib['cas_full']), '-' if lib['cas_fast'] is None else '{:,}'.format(lib['cas_fast'])))
    fp = st['fastpack']
    _say('Fast pack: %s - %s' % (fp['state'], fp['why']))
    _say('Monitor:   %s' % ('installed' if st['monitor']['installed'] else 'not installed'))
    _say('Disk:      %s GB free on C:' % st['disk'].get('c_free_gb'))
    for t in st['load_times'][:5]:
        _say('Load time: %s %-10s %-8s menu %s s, lot %s s' % (t['time'].replace('T', ' '), t.get('event') or '',
                                                               t['profile'], t['launch_to_menu_s'], t['lot_load_s']))
    for j in st['journals'][:5]:
        _say('Change:    %s %s (%s)' % (j['id'], j['note'][:70], j['state']))
    for p in st.get('problems', []):
        _say('Problem:   %s' % p)
    return 0


def _saves():
    r = api.list_saves(_progress)
    if not r.get('ok'):
        _say(r.get('message'))
        return 1
    for s in r['saves']:
        _say('%-14s %-36s %-14s %-18s %4d sims %4d lots  CC %5s  loads %7s CAS parts  pack %-7s %s' % (
            s['slot'], (s['name'] or '')[:36], (s['household'] or '-')[:14], (s['world'] or '-')[:18], s['sims'],
            s['lots'], '-' if s['cc_parts'] is None else s['cc_parts'],
            '-' if s['cas_loaded'] is None else '{:,}'.format(s['cas_loaded']), s['pack']['state'],
            (s['last_played'] or '').replace('T', ' ')))
        if s.get('problem'):
            _say('               ! %s' % s['problem'])
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ('-h', '--help', 'help'):
        _say(__doc__)
        return 0
    api.configure(scan_workers=3)          # a console run may use worker processes (this is a __main__ guard)
    cmd, rest = args[0], args[1:]
    apply = '--apply' in rest
    rest = [a for a in rest if a != '--apply']
    if cmd == 'status':
        return _status()
    if cmd == 'saves':
        return _saves()
    if cmd in ('play', 'prepare'):
        if not rest:
            _say('Say what to %s: fast, full, studio or save:<slot> (see "saves").' % cmd)
            return 2
        r = (api.play if cmd == 'play' else api.prepare)(rest[0], _progress)
        _steps(r)
        _say(r['message'])
        return 0 if r['ok'] else 1
    if cmd == 'undo':
        r = api.undo_last(_progress)
        _say(r['message'])
        return 0 if r['ok'] else 1
    if cmd == 'inbox':
        r = api.inbox(apply, _progress)
        for it in r.get('items', []):
            _say('  %-40s %-8s %s%s' % (it['name'], it['status'], it['where'] or '', (' (%s)' % it['reason']) if it['reason'] else ''))
        _say(r['message'])
        return 0 if r['ok'] else 1
    if cmd == 'cleanup':
        r = (api.cleanup_apply if apply else api.cleanup_plan)(_progress)
        _say(r['message'])
        return 0 if r['ok'] else 1
    if cmd == 'graphics':
        what = rest[0] if rest else 'tune'
        if what == 'restore':
            r = api.graphics_restore(apply)
        else:
            r = api.graphics_tune(apply)
            for row in r.get('table', []):
                _say('  %-40s default %-22s before %-22s after %s' % (row['setting'], row['stock'], row['before'], row['after']))
        _say(r['message'])
        return 0 if r['ok'] else 1
    if cmd == 'report':
        r = api.report(_progress)
        _say(r['message'] + (' %s' % r['path'] if r.get('path') else ''))
        return 0 if r['ok'] else 1
    if cmd == 'game':
        if rest:
            r = api.set_game_path(' '.join(rest))
            _say(r['message'])
            return 0 if r['ok'] else 1
        g = api.status().get('game') or {}
        _say(g.get('exe') if g.get('found') else g.get('message'))
        return 0 if g.get('found') else 1
    _say('Unknown command %r.' % cmd)
    _say(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())

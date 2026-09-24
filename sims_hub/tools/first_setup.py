"""One-time setup on the user's PC, without switching the Mods folder.

Installs SpeedKit Monitor, sets graphics to SpeedKit Max Quality (SGR Full with the lag values tuned) and
builds the fast pack in <Sims 4>\\SpeedKit\\fastpack - the same steps the Hub's Play button runs, minus the
mode switch and the game launch. Everything goes through SpeedKit's journals and can be undone.
"""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speedkit import api  # noqa: E402


def log(step, fraction, message):
    print('  [%s] %s%s' % (step, message, '' if fraction is None else ' (%d%%)' % round(fraction * 100)), flush=True)


def main():
    if api._game_running():
        sys.exit('The Sims 4 is running - close it first.')
    game = api._game()
    if game is None:
        sys.exit("The game wasn't found.")
    print('game:', game)
    run = api._Run(log)
    t0 = time.time()
    api._housekeeping(run)
    lib = api._library()
    try:
        st = lib.scan()
        run.step('library', True, 'Checked your mods (%s mod files, %d re-read).' % ('{:,}'.format(st['packages']), st['reread']))
        api._ensure_monitor(run)
        api._ensure_graphics(run, game)
        prov = api._provider(None, game, lib, run)
        res = prov.update_pack(lib, out_dir=api._fastpack(), dry_run=False, check_game=False,
                               sims=api._sims(), home=api._home(), progress=run.tell)
        run.step('pack', True, api._pack_message('fast', None, {'done': True}, prov))
        print('pack result:', {k: v for k, v in res.items() if k not in ('result',)})
    finally:
        lib.close()
    print('\nsteps:')
    for s in run.steps:
        print('  %s %-10s %s' % ('!' if s['warn'] else '-', s['step'], s['message']))
    print('done in %.0f s' % (time.time() - t0))


if __name__ == '__main__':
    main()

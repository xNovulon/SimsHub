r"""Install or remove the SpeedKit Monitor script mod (dist/SpeedKit_Monitor.ts4script -> <Sims 4>\Mods\).

    python -m speedkit.ingame_install install      # show the plan (dry run)
    python -m speedkit.ingame_install install --apply
    python -m speedkit.ingame_install uninstall [--apply]

Facts this relies on:
  * The game loads .ts4script files from the Mods root or one folder below it only (research: loadorder,
    TS4_x64.exe script scanner), so the mod goes to the Mods root.
  * Two archives that both contain the package 'speedkit_monitor' would clash, so any other copy named
    SpeedKit_Monitor*.ts4script in the Mods root or a first-level folder is quarantined when installing.
  * Every change goes through a Journal of kind 'install' (the kind allowed to touch .ts4script files):
    the new file is put in place with put_new (or replace, which quarantines the old one first), nothing
    is deleted, and journal.undo() reverses it. The journal refuses to run while TS4_x64.exe is running.
Build the archive first with: python tools/build_ingame.py
"""
import argparse
import os
import shutil
import time

from .journal import Journal, JournalError, file_digest
from .library import SIMS, game_running

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(PROJECT, 'dist', 'SpeedKit_Monitor.ts4script')
NAME = 'SpeedKit_Monitor.ts4script'


def find_installed(sims=SIMS):
    """Every SpeedKit_Monitor*.ts4script the game would load: Mods root and first-level folders."""
    mods = os.path.join(sims, 'Mods')
    found = []
    if not os.path.isdir(mods):
        return found

    def scan(d):
        try:
            with os.scandir(d) as it:
                return list(it)
        except OSError:
            return []
    for e in scan(mods):
        if e.is_file() and _is_ours(e.name):
            found.append(e.path)
        elif e.is_dir():
            found.extend(x.path for x in scan(e.path) if x.is_file() and _is_ours(x.name))
    return sorted(found)


def _is_ours(name):
    low = name.lower()
    return low.startswith('speedkit_monitor') and low.endswith('.ts4script')


def plan_install(dist=DIST, sims=SIMS):
    """What install() would do. Returns {'action': 'put_new'|'replace'|'up_to_date', 'source', 'target',
    'quarantine': [other copies], 'source_digest', 'target_digest', 'game_running'}."""
    if not os.path.isfile(dist):
        raise FileNotFoundError('%s is missing - build it with: python tools/build_ingame.py' % dist)
    target = os.path.join(sims, 'Mods', NAME)
    src_digest = file_digest(dist)
    installed = find_installed(sims)
    same = [p for p in installed if os.path.normcase(p) == os.path.normcase(target)]
    others = [p for p in installed if os.path.normcase(p) != os.path.normcase(target)]
    tgt_digest = file_digest(target) if same else None
    if not same:
        action = 'put_new'
    elif tgt_digest == src_digest:
        action = 'up_to_date'
    else:
        action = 'replace'
    return {'action': action, 'source': dist, 'target': target, 'quarantine': others,
            'source_digest': src_digest, 'target_digest': tgt_digest, 'game_running': game_running()}


def plan_uninstall(sims=SIMS):
    """What uninstall() would do: {'quarantine': [copies], 'game_running'}."""
    return {'quarantine': find_installed(sims), 'game_running': game_running()}


def _free_journal_slot(home, kind):
    """Journal ids have one-second resolution; wait until this second's id for `kind` is unused so a
    quick install/uninstall pair never overwrites the earlier journal."""
    for _ in range(30):
        jid = time.strftime('%Y%m%d-%H%M%S') + '-' + kind
        if not os.path.exists(os.path.join(home, 'journal', jid + '.json')):
            return
        time.sleep(0.1)


def install(dry_run=True, dist=DIST, sims=SIMS, home=None, check_game=True):
    """Copy the built archive into <sims>\\Mods\\ via a Journal. dry_run (default) only returns the plan.
    Returns the plan plus 'journal' (id) and 'done' after a real run."""
    plan = plan_install(dist, sims)
    plan['dry_run'] = dry_run
    if dry_run:
        return plan
    home = home or os.path.join(sims, 'SpeedKit')
    if plan['action'] == 'up_to_date' and not plan['quarantine']:
        plan['done'] = []
        return plan
    _free_journal_slot(home, 'install')
    done = []
    with Journal('install', 'install SpeedKit Monitor', home=home, sims=sims, check_game=check_game) as j:
        for p in plan['quarantine']:
            j.quarantine(p)
            done.append(('quarantined', p))
        if plan['action'] != 'up_to_date':
            staging = os.path.join(home, 'staging')
            os.makedirs(staging, exist_ok=True)
            tmp = os.path.join(staging, NAME + '.%d.tmp' % os.getpid())
            shutil.copy2(dist, tmp)                       # same drive as Mods, so put_new is a rename
            if file_digest(tmp) != plan['source_digest']:
                raise RuntimeError('copy of %s does not match the source' % dist)
            if plan['action'] == 'replace':
                j.replace(tmp, plan['target'])
                done.append(('replaced', plan['target']))
            else:
                j.put_new(tmp, plan['target'])
                done.append(('installed', plan['target']))
        plan['journal'] = j.id
    plan['done'] = done
    return plan


def uninstall(dry_run=True, sims=SIMS, home=None, check_game=True):
    """Quarantine every installed SpeedKit_Monitor*.ts4script via a Journal. dry_run only plans."""
    plan = plan_uninstall(sims)
    plan['dry_run'] = dry_run
    if dry_run or not plan['quarantine']:
        plan['done'] = []
        return plan
    home = home or os.path.join(sims, 'SpeedKit')
    _free_journal_slot(home, 'install')
    done = []
    with Journal('install', 'uninstall SpeedKit Monitor', home=home, sims=sims, check_game=check_game) as j:
        for p in plan['quarantine']:
            done.append(('quarantined', p, j.quarantine(p)))
        plan['journal'] = j.id
    plan['done'] = done
    return plan


def main(argv=None):
    ap = argparse.ArgumentParser(description='Install or remove the SpeedKit Monitor script mod.')
    ap.add_argument('what', choices=['install', 'uninstall'])
    ap.add_argument('--apply', action='store_true', help='really do it (default: show the plan)')
    a = ap.parse_args(argv)
    try:
        if a.what == 'install':
            r = install(dry_run=not a.apply)
            print('%s: %s -> %s' % ('PLAN' if r['dry_run'] else 'DONE', r['action'], r['target']))
            for p in r['quarantine']:
                print('  quarantine other copy: %s' % p)
        else:
            r = uninstall(dry_run=not a.apply)
            print('%s: quarantine %d file(s)' % ('PLAN' if r['dry_run'] else 'DONE', len(r['quarantine'])))
            for p in r['quarantine']:
                print('  ' + p)
    except (JournalError, FileNotFoundError) as e:
        print('Not done: %s' % e)
        return 1
    if r.get('game_running'):
        print('The Sims 4 is running - close it before applying.')
    if r.get('journal'):
        print('journal %s (undo with speedkit.journal.undo)' % r['journal'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

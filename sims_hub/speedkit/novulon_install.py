r"""Install or remove Novulon (dist/Novulon.ts4script + dist/Novulon_Tuning.package -> <Sims 4>\Mods\).

    python -m speedkit.novulon_install install      # show the plan (dry run)
    python -m speedkit.novulon_install install --apply
    python -m speedkit.novulon_install uninstall [--apply]

Same shape as `ingame_install.py` (SpeedKit Monitor's own installer), extended to two files in one
`Journal`: `journal.py`'s `.ts4script`-only kind restriction (`SCRIPT_KINDS`, checked at `_check_path`)
gates that one extension specifically - nothing in `journal.py` restricts a `.package` write by kind, so
both `put_new`/`replace` calls legally share one `Journal('install', ...)` block, giving one atomic
install/undo for the whole mod (`speedkit.journal.undo(<id>)` reverses both files together).

Per the build task's override, this is a standalone command only for this release - it is never called
from `speedkit/api.py`'s automatic Play/Prepare install path (that file belongs to another job right now).
A player (or a later Hub button) runs this explicitly.

Build first with: python tools/build_novulon.py && python tools/build_novulon_package.py
"""
import argparse
import os
import shutil
import time

from .journal import Journal, JournalError, file_digest
from .library import SIMS, game_running

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_SCRIPT = os.path.join(PROJECT, 'dist', 'Novulon.ts4script')
DIST_PACKAGE = os.path.join(PROJECT, 'dist', 'Novulon_Tuning.package')
NAME_SCRIPT = 'Novulon.ts4script'
NAME_PACKAGE = 'Novulon_Tuning.package'


def _is_ours_script(name):
    low = name.lower()
    return low.startswith('novulon') and low.endswith('.ts4script')


def _is_ours_package(name):
    low = name.lower()
    return low.startswith('novulon') and low.endswith('.package')


def _scan(d):
    try:
        with os.scandir(d) as it:
            return list(it)
    except OSError:
        return []


def _find(sims, is_ours):
    """Every matching file the game would load: Mods root and first-level folders."""
    mods = os.path.join(sims, 'Mods')
    found = []
    if not os.path.isdir(mods):
        return found
    for e in _scan(mods):
        if e.is_file() and is_ours(e.name):
            found.append(e.path)
        elif e.is_dir():
            found.extend(x.path for x in _scan(e.path) if x.is_file() and is_ours(x.name))
    return sorted(found)


def find_installed(sims=SIMS):
    """{'script': [...], 'package': [...]} - every Novulon*.ts4script / Novulon_Tuning*.package the game
    would load (Mods root and first-level folders)."""
    return {'script': _find(sims, _is_ours_script), 'package': _find(sims, _is_ours_package)}


def _plan_one(dist, name, sims, is_ours):
    if not os.path.isfile(dist):
        raise FileNotFoundError('%s is missing - build it first' % dist)
    target = os.path.join(sims, 'Mods', name)
    src_digest = file_digest(dist)
    installed = _find(sims, is_ours)
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
            'source_digest': src_digest, 'target_digest': tgt_digest}


def plan_install(script=DIST_SCRIPT, package=DIST_PACKAGE, sims=SIMS):
    """What install() would do for both files. Returns
    {'script': {...}, 'package': {...}, 'quarantine': [combined], 'game_running'}. Raises FileNotFoundError
    if either dist file is missing (both must ship together - SPEC.md §15: an old tuning package pointing
    at an interaction id an old script no longer registers is a silent breakage)."""
    s = _plan_one(script, NAME_SCRIPT, sims, _is_ours_script)
    p = _plan_one(package, NAME_PACKAGE, sims, _is_ours_package)
    return {'script': s, 'package': p, 'quarantine': s['quarantine'] + p['quarantine'], 'game_running': game_running()}


def plan_uninstall(sims=SIMS):
    """What uninstall() would do: {'quarantine': [both kinds], 'game_running'}."""
    found = find_installed(sims)
    return {'quarantine': found['script'] + found['package'], 'game_running': game_running()}


def _free_journal_slot(home, kind):
    """Journal ids have one-second resolution; wait until this second's id for `kind` is unused so a
    quick install/uninstall pair never overwrites the earlier journal."""
    for _ in range(30):
        jid = time.strftime('%Y%m%d-%H%M%S') + '-' + kind
        if not os.path.exists(os.path.join(home, 'journal', jid + '.json')):
            return
        time.sleep(0.1)


def _stage_and_check(staging, dist, name, digest):
    os.makedirs(staging, exist_ok=True)
    tmp = os.path.join(staging, name + '.%d.tmp' % os.getpid())
    shutil.copy2(dist, tmp)                            # same drive as Mods, so put_new is a rename
    if file_digest(tmp) != digest:
        raise RuntimeError('copy of %s does not match the source' % dist)
    return tmp


def install(dry_run=True, script=DIST_SCRIPT, package=DIST_PACKAGE, sims=SIMS, home=None, check_game=True):
    """Copy both built files into <sims>\\Mods\\ via one Journal. dry_run (default) only returns the plan.
    Returns the plan plus 'journal' (id) and 'done' after a real run."""
    plan = plan_install(script, package, sims)
    plan['dry_run'] = dry_run
    if dry_run:
        return plan
    home = home or os.path.join(sims, 'Novulon')
    if plan['script']['action'] == 'up_to_date' and plan['package']['action'] == 'up_to_date' and not plan['quarantine']:
        plan['done'] = []
        return plan
    _free_journal_slot(home, 'install')
    done = []
    with Journal('install', 'install Novulon', home=home, sims=sims, check_game=check_game) as j:
        for p in plan['quarantine']:
            j.quarantine(p)
            done.append(('quarantined', p))
        staging = os.path.join(home, 'staging')
        for key, dist, name in (('script', script, NAME_SCRIPT), ('package', package, NAME_PACKAGE)):
            sub = plan[key]
            if sub['action'] == 'up_to_date':
                continue
            tmp = _stage_and_check(staging, dist, name, sub['source_digest'])
            if sub['action'] == 'replace':
                j.replace(tmp, sub['target'])
                done.append(('replaced', sub['target']))
            else:
                j.put_new(tmp, sub['target'])
                done.append(('installed', sub['target']))
        plan['journal'] = j.id
    plan['done'] = done
    return plan


def uninstall(dry_run=True, sims=SIMS, home=None, check_game=True):
    """Quarantine every installed Novulon*.ts4script / Novulon_Tuning*.package via a Journal."""
    plan = plan_uninstall(sims)
    plan['dry_run'] = dry_run
    if dry_run or not plan['quarantine']:
        plan['done'] = []
        return plan
    home = home or os.path.join(sims, 'Novulon')
    _free_journal_slot(home, 'install')
    done = []
    with Journal('install', 'uninstall Novulon', home=home, sims=sims, check_game=check_game) as j:
        for p in plan['quarantine']:
            done.append(('quarantined', p, j.quarantine(p)))
        plan['journal'] = j.id
    plan['done'] = done
    return plan


def main(argv=None):
    ap = argparse.ArgumentParser(description='Install or remove Novulon.')
    ap.add_argument('what', choices=['install', 'uninstall'])
    ap.add_argument('--apply', action='store_true', help='really do it (default: show the plan)')
    a = ap.parse_args(argv)
    try:
        if a.what == 'install':
            r = install(dry_run=not a.apply)
            print('%s: script %s -> %s' % ('PLAN' if r['dry_run'] else 'DONE', r['script']['action'], r['script']['target']))
            print('%s: package %s -> %s' % ('PLAN' if r['dry_run'] else 'DONE', r['package']['action'], r['package']['target']))
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

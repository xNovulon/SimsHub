"""Example data for patch day, game errors, save backups and load-time savings (the stand-in for speedkit/api_care.py,
see docs/care.md). stub_api.py imports every public name here, so the Hub's preview mode shows these pages with
realistic data. Like stub_api it never touches a file: every action changes only the in-memory state below (reset
together with stub_api.STATE - it belongs to the STATE object it was made for)."""
import copy
from datetime import datetime, timedelta

from speedkit.hub import stub_api as S

_CARE = {'owner': None, 'state': None}


def _ago(**kw):
    return (datetime.now() - timedelta(**kw)).replace(microsecond=0).isoformat()


def _day(days):
    return (datetime.now() - timedelta(days=days)).date().isoformat()


def _initial():
    older = [
        {'mod': 'MCCC', 'rel': 'MCCC/mc_cmd_center.ts4script', 'date': _ago(days=41), 'days_before': 39, 'size_mb': 1.9,
         'goes_with': ['MCCC/mc_cmd_center.package']},
        {'mod': 'LittleMsSam Pack', 'rel': 'LittleMsSam Pack/lms_firstlove.ts4script', 'date': _ago(days=96),
         'days_before': 94, 'size_mb': 0.2, 'goes_with': ['LittleMsSam Pack/LittleMsSam_FirstLove.package']},
        {'mod': 'UI Cheats Extension', 'rel': 'UI Cheats Extension/UI_Cheats_Extension_Scripts.ts4script',
         'date': _ago(days=12), 'days_before': 10, 'size_mb': 0.4,
         'goes_with': ['UI Cheats Extension/UI_Cheats_Extension.package']},
        {'mod': 'Kuttoe', 'rel': 'Kuttoe/kuttoe_tweaks.ts4script', 'date': _ago(days=150), 'days_before': 148,
         'size_mb': 0.1, 'goes_with': []},
    ]
    mccc_tb = ('Where: mc_cmd_center\\mc_utils\\mc_zone.py:188\n\n[mccc] (MCCC) Error while loading the zone\n'
               'Traceback (most recent call last):\n'
               '  File "T:\\InGame\\Gameplay\\Scripts\\Server\\zone.py", line 1085, in on_loading_screen_animation_finished\n'
               '  File "D:\\Deaderpool\\mccc\\mc_cmd_center\\mc_utils\\mc_zone.py", line 188, in _on_loading_finished\n'
               "AttributeError: 'NoneType' object has no attribute 'household_id'")
    errors = [
        {'id': 'a1', 'kind': 'script', 'error': "AttributeError: 'NoneType' object has no attribute 'household_id'",
         'mod': {'name': 'MCCC', 'file': 'mc_cmd_center.ts4script', 'rel': 'MCCC/mc_cmd_center.ts4script', 'root': 'Mods',
                 'script': True, 'can_set_aside': True},
         'how': 'named', 'also': [], 'count': 14, 'first': _ago(days=2, hours=3), 'last': _ago(hours=2),
         'files': ['lastException.txt', 'mc_lastexception.html'], 'details': mccc_tb, 'where': 'mc_zone.py:_on_loading_finished',
         'source': 'script', 'new': True, 'set_aside': False},
        {'id': 'b2', 'kind': 'ui', 'error': 'Error: Error #1009: Cannot access a property or method of a null object reference.',
         'mod': {'name': 'UI Cheats Extension', 'file': 'UI_Cheats_Extension_Scripts.ts4script',
                 'rel': 'UI Cheats Extension/UI_Cheats_Extension_Scripts.ts4script', 'root': 'Mods', 'script': True,
                 'can_set_aside': True},
         'how': 'mentioned', 'also': [], 'count': 3, 'first': _ago(days=1, hours=5), 'last': _ago(hours=5),
         'files': ['lastUIException.txt'], 'where': '',
         'details': 'Where: UI:PhotoStudio\n\nError: Error #1009: Cannot access a property or method of a null object '
                    'reference.\n\tat widgets.PhotoStudio::PosePicker/onItemSelected()', 'source': 'ui', 'new': True,
         'set_aside': False},
        {'id': 'c3', 'kind': 'script', 'error': "TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'",
         'mod': None, 'how': None, 'also': [], 'count': 1, 'first': _ago(days=6), 'last': _ago(days=6),
         'files': ['lastException.txt'], 'where': 'route_events.py:process', 'source': 'script', 'new': False,
         'set_aside': False,
         'details': 'Traceback (most recent call last):\n  File "T:\\InGame\\Gameplay\\Scripts\\Server\\routing\\'
                    'route_events.py", line 210, in process\nTypeError: unsupported operand type(s) for +: '
                    "'NoneType' and 'int'"},
    ]
    saves = [
        {'file': 'Slot_00000014.save', 'slot': 'Slot_00000014', 'name': 'Wicked Nights', 'size_mb': 48.2,
         'last_played': _ago(hours=3), 'growth_mb': 16.2, 'growth_days': 28, 'level': 'growing',
         'note': 'It grew 16 MB in the last 28 days.',
         'history': [[_day(d), round(32.0 + (28 - d) * 16.2 / 28, 1)] for d in range(28, -1, -4)]},
        {'file': 'Slot_00000009.save', 'slot': 'Slot_00000009', 'name': 'Legacy Challenge', 'size_mb': 36.7,
         'last_played': _ago(days=2, hours=1), 'growth_mb': 1.2, 'growth_days': 20, 'level': 'ok', 'note': None,
         'history': [[_day(20), 35.5], [_day(10), 36.1], [_day(2), 36.7]]},
        {'file': 'Slot_00000011.save', 'slot': 'Slot_00000011', 'name': 'San Myshuno Apartment Life with a Very Long Save Name',
         'size_mb': 29.4, 'last_played': _ago(days=9), 'growth_mb': None, 'growth_days': None, 'level': 'ok',
         'note': None, 'history': [[_day(9), 29.4]]},
        {'file': 'Slot_00000003.save', 'slot': 'Slot_00000003', 'name': 'Build Test', 'size_mb': 12.1,
         'last_played': _ago(days=41), 'growth_mb': 0.0, 'growth_days': 30, 'level': 'ok', 'note': None,
         'history': [[_day(41), 12.1]]},
    ]

    def bk(days, hours, reason, n=4, mb=264.6):
        when = datetime.now() - timedelta(days=days, hours=hours)
        return {'id': when.strftime('%Y%m%d-%H%M%S'), 'when': when.replace(microsecond=0).isoformat(), 'reason': reason,
                'files': n, 'bytes': int(mb * 1e6), 'complete': True, 'game_version': '1.119.109.1020',
                'saves': [{'name': s['file'], 'save_name': s['name'], 'size': int(s['size_mb'] * 1e6)} for s in saves]}
    backups = [bk(0, 4, 'by hand', mb=126.4), bk(3, 1, 'before setting mods aside', mb=121.9),
               bk(12, 6, 'by hand', mb=115.0)]
    return {
        'game': {'version': '1.119.109.1020', 'previous': '1.118.242.1030', 'updated': True, 'first_look': False,
                 'update_time': _ago(days=2, hours=6), 'noticed': _ago(days=2, hours=1)},
        'older': older, 'newer': 23,
        'set_aside': [{'rel': 'Srsly Pack/srsly_autonomy.ts4script', 'mod': 'Srsly Pack', 'since': _ago(days=2),
                       'why': 'patch', 'game_version': '1.119.109.1020', 'date': _ago(days=60), 'state': 'aside',
                       'script': True}],
        'errors': errors, 'seen_until': None,
        'saves': saves, 'backups': backups,
        'batch': {'scanned': _ago(days=1, hours=2), 'files_checked': 8412, 'found': _batch_examples()},
    }


def _batch_examples():
    """Example results of the Sims 4 Studio batch-fix check: {fix id: [{'rel', 'root', 'parts', 'total', 'versions'}]}."""
    f = lambda rel, parts=1, total=1, versions=(), root='Mods': {'rel': rel, 'root': root, 'parts': parts,  # noqa: E731
                                                                'total': total, 'versions': list(versions)}
    return {
        'sliders_werewolf': [f('Sliders/Obscurus_NoseShape_Sliders.package', 4, 4, [14]),
                             f('Sliders/Chin Width Slider 2021.package', 1, 1, [14]),
                             f('Sliders/Enhanced_Butt_Slider.package', 2, 3, [13])],
        'eyes_infants': [f('Eyes/Pralinesims_Dazzling_Light_Eyes.package', 24, 24),
                         f('Eyes/Default Eyes Replacement.package', 12, 12)],
        'shoes_werewolves': [f('Clothes/Shoes/Madlen_Sneakers.package', 8, 8), f('Clothes/Shoes/Winter Boots.package', 5, 5)],
        'nude_default': [f('Clothes/Tops/Basic_Tank_Top.package', 1, 1)],
        'pets_patch': [f('Old CC/2016/Hair_Bob_2016.package', 6, 6, [27]),
                       f('Old CC/2017/Sweater_Knit.package', 3, 3, [30], root='Mods_parked')],
    }


def _st():
    """The example state, made again whenever stub_api.reset() made a new STATE."""
    with S._lock:
        if _CARE['owner'] is not S.STATE:
            _CARE['owner'] = S.STATE
            _CARE['state'] = _initial()
        return _CARE['state']


def _msg_patch(c):
    n = len(c['older'])
    if c['game']['updated']:
        return ('The Sims 4 was updated to %s. %s' % (c['game']['version'],
                ("%d script mods are older than the update. Check these first." % n) if n else
                'All script mods are newer than the update.'))
    return ('%d script mods are older than the latest game update.' % n) if n else \
        'All script mods are newer than the latest game update.'


# ------------------------------------------------------------------ reads
def patch_day():
    c = _st()
    with S._lock:
        out = {'ok': True, 'game': copy.deepcopy(c['game']), 'older': copy.deepcopy(c['older']), 'newer': c['newer'],
               'set_aside': copy.deepcopy(c['set_aside']), 'message': _msg_patch(c)}
    r = batch_fixes()
    out['batch_fixes'] = None if not r['scanned'] else {
        'files': len({x['rel'] for fx in r['fixes'] for x in fx['files'] if not x['set_aside']}),
        'fixes': [{'id': fx['id'], 'name': fx['name'], 'files': fx['count'] - fx['set_aside']} for fx in r['fixes']
                  if fx['count'] - fx['set_aside']],
        'scanned': r['scanned']}
    return out


def patch_seen():
    with S._lock:
        _st()['game']['updated'] = False
    return {'ok': True, 'message': 'Notice dismissed.'}


def game_errors():
    c = _st()
    with S._lock:
        errs = copy.deepcopy(c['errors'])
        held = {h['rel'] for h in c['set_aside']}
    for g in errs:
        if g['mod'] and g['mod']['rel'] in held:
            g['set_aside'] = True
            g['mod']['can_set_aside'] = False
    new = [g for g in errs if g['new']]
    named = [g for g in new if g['mod']]
    msg = ('%d kinds of errors, %d pointing at a mod.' % (len(new), len(named))) if new else 'No new errors since the last review.'
    return {'ok': True, 'errors': errs, 'files': [{'name': 'lastException.txt', 'kind': 'script', 'reports': 15,
                                                  'when': _ago(hours=2)}], 'unreadable': [], 'message': msg,
            'seen_until': c['seen_until']}


def errors_seen():
    with S._lock:
        c = _st()
        c['seen_until'] = datetime.now().replace(microsecond=0).isoformat()
        for g in c['errors']:
            g['new'] = False
    return {'ok': True, 'message': 'The errors so far are marked as seen.'}


def save_health():
    c = _st()
    with S._lock:
        saves, backups = copy.deepcopy(c['saves']), copy.deepcopy(c['backups'])
    warn = [s for s in saves if s['level'] != 'ok']
    return {'ok': True, 'saves': saves, 'backups': backups, 'keep': 5, 'free_gb': 402.0,
            'backup_folder': r'C:\Users\basim\Documents\Electronic Arts\The Sims 4\SpeedKit\save_backups',
            'message': ('%d save%s large or growing quickly.' % (len(warn), ' is' if len(warn) == 1 else 's are')) if warn else 'No size warnings.'}


def load_savings():
    """Worked out from the example start times status() shows (the same rules as speedkit/loadstats.py), so the
    Home page's numbers agree with each other."""
    import statistics
    from speedkit import loadstats as LS
    with S._lock:
        rows = copy.deepcopy(S.STATE.get('load_times') or [])
    starts, lot = [], None
    for r in rows:                                # newest first: a start takes the lot load that followed it
        if r.get('launch_to_menu_s') is not None:
            starts.append({'profile': r.get('profile'), 'menu': r['launch_to_menu_s'], 'lot': lot, 'time': r.get('time')})
            lot = None
        elif r.get('lot_load_s') is not None:
            lot = r['lot_load_s']
    modes = {}
    for s in starts:
        d = modes.setdefault(LS._mode(s['profile']), {'starts': 0, 'menu': [], 'lot': [], 'total': [], 'last': None})
        d['starts'] += 1
        d['menu'].append(s['menu'])
        d['total'].append(s['menu'] + (s['lot'] or 0))
        if s['lot'] is not None:
            d['lot'].append(s['lot'])
        d['last'] = d['last'] or s['time']
    med = lambda xs: round(statistics.median(xs), 1) if xs else None  # noqa: E731
    view = {m: {'starts': d['starts'], 'menu_s': med(d['menu']), 'lot_s': med(d['lot']), 'total_s': med(d['total']),
                'last': d['last']} for m, d in modes.items()}
    fast_key = next((k for k in LS.FAST_FAMILY if k in view), None)
    saved = saved_total = None
    if 'full' in view and fast_key:
        saved = round(view['full']['total_s'] - view[fast_key]['total_s'], 1)
        saved_total = round(sum(max(0.0, view['full']['total_s'] - (s['menu'] + (s['lot'] or 0))) for s in starts
                                if LS._mode(s['profile']) in LS.FAST_FAMILY), 1)
    if not starts:
        conf = 'none'
    elif 'full' not in view or not fast_key:
        conf = 'one_mode'
    elif view['full']['starts'] < LS.ENOUGH or view[fast_key]['starts'] < LS.ENOUGH:
        conf = 'low'
    else:
        conf = 'ok'
    return {'ok': True, 'modes': view, 'compare': fast_key, 'saved_s': saved, 'saved_total_s': saved_total,
            'confidence': conf, 'starts': len(starts), 'message': LS._message(view, fast_key, saved, conf)}


# ------------------------------------------------------------------ changes
def set_aside(rels, why='patch', progress=None):
    bad = S._busy()
    if bad:
        return dict(bad, moved=[], skipped=[], journal=None)
    c = _st()
    steps = [('aside', 'Setting the mods aside')]
    if why == 'patch':
        steps.insert(0, ('backup', 'Backing up your saves first'))
    S._run(progress, steps)
    moved = []
    with S._lock:
        removed = [o for o in c['older'] if o['rel'] in rels]
        for r in rels:
            item = next((o for o in c['older'] if o['rel'] == r), None)
            files = [r] + (item['goes_with'] if item else [])
            for f in files:
                if f not in {h['rel'] for h in c['set_aside']}:
                    c['set_aside'].append({'rel': f, 'mod': f.split('/')[0], 'since': datetime.now().replace(microsecond=0).isoformat(),
                                           'why': why, 'game_version': c['game']['version'], 'date': item['date'] if item else None,
                                           'state': 'aside', 'script': f.endswith('.ts4script')})
                    moved.append(f)
            c['older'] = [o for o in c['older'] if o['rel'] != r]
        if why == 'patch':
            b = copy.deepcopy(c['backups'][0])
            b.update(id=datetime.now().strftime('%Y%m%d-%H%M%S'), when=datetime.now().replace(microsecond=0).isoformat(),
                     reason='before setting mods aside')
            c['backups'].insert(0, b)
            del c['backups'][5:]
    jid = S._journal('aside', 'set aside %d file(s) until updated (%s): %s' % (len(moved), why, ', '.join(moved[:5])))
    with S._lock:
        c.setdefault('undo', {})[jid] = ('aside', moved, removed)
    names = sorted({m.split('/')[0] for m in moved})
    msg = 'Set aside: %s (%d files). They can be put back on the Tools page.' % (
        ', '.join(names), len(moved))
    out_steps = [{'step': 'aside', 'ok': True, 'message': msg, 'warn': False}]
    if why == 'patch':
        out_steps.insert(0, {'step': 'backup', 'ok': True, 'message': 'Saves backed up first (4 saves).', 'warn': False})
    return {'ok': True, 'message': msg, 'moved': moved, 'skipped': [], 'journal': jid, 'steps': out_steps}


def put_back(rels, progress=None):
    bad = S._busy()
    if bad:
        return dict(bad, moved=[], skipped=[], journal=None)
    S._run(progress, [('back', 'Putting the mods back')])
    c = _st()
    with S._lock:
        moved = [h['rel'] for h in c['set_aside'] if h['rel'] in rels]
        c['set_aside'] = [h for h in c['set_aside'] if h['rel'] not in rels]
    if not moved:
        return {'ok': False, 'message': 'There is nothing to put back.', 'moved': [], 'skipped': [], 'journal': None}
    jid = S._journal('aside', 'put back %d file(s): %s' % (len(moved), ', '.join(moved[:5])))
    with S._lock:
        c.setdefault('undo', {})[jid] = ('back', moved, [])
    return {'ok': True, 'message': 'Put back: %s.' % ', '.join(sorted({m.split('/')[0] for m in moved})),
            'moved': moved, 'skipped': [], 'journal': jid}


def backup_saves(progress=None):
    bad = S._busy()
    if bad:
        return dict(bad, backup=None)
    S._run(progress, [('backup', 'Copying Wicked Nights'), ('backup', 'Copying Legacy Challenge'), ('backup', 'Done')])
    c = _st()
    with S._lock:
        b = copy.deepcopy(c['backups'][0]) if c['backups'] else {'files': 4, 'bytes': 264600000, 'saves': [],
                                                                'complete': True, 'game_version': None}
        b.update(id=datetime.now().strftime('%Y%m%d-%H%M%S'), when=datetime.now().replace(microsecond=0).isoformat(),
                 reason='by hand')
        c['backups'].insert(0, b)
        del c['backups'][5:]
    return {'ok': True, 'message': 'Backed up 4 saves (126 MB). The newest 5 backups are kept.', 'backup': b['id'],
            'files': 4, 'bytes': b['bytes']}


def restore_saves(backup, progress=None):
    bad = S._busy()
    if bad:
        return dict(bad, journal=None)
    c = _st()
    with S._lock:
        b = next((x for x in c['backups'] if x['id'] == backup), None)
    if not b:
        return {'ok': False, 'message': 'That backup is not there any more.', 'journal': None}
    S._run(progress, [('backup', 'Backing up your saves as they are now'), ('restore', 'Putting back Wicked Nights'),
                      ('restore', 'Putting back Legacy Challenge')])
    with S._lock:
        nb = copy.deepcopy(b)
        nb.update(id=datetime.now().strftime('%Y%m%d-%H%M%S'), when=datetime.now().replace(microsecond=0).isoformat(),
                  reason='before restore')
        c['backups'].insert(0, nb)
        del c['backups'][6:]
    jid = S._journal('saves', 'restore saves from backup %s' % backup)
    return {'ok': True, 'journal': jid, 'restored': [s['name'] for s in b['saves']], 'left': [],
            'message': 'Restored %d saves from the backup. The previous saves were backed up first; "Undo last '
                       'change" on the Tools page restores them.' % b['files']}


def on_undo(journal):
    """stub_api.undo_last calls this for the change it undid: put the example state back."""
    c = _st()
    with S._lock:
        rec = (c.get('undo') or {}).pop(journal.get('id'), None)
        if not rec:
            return
        what, moved, extra = rec
        if what == 'aside':
            c['set_aside'] = [h for h in c['set_aside'] if h['rel'] not in moved]
            c['older'] = extra + [o for o in c['older'] if o['rel'] not in {e['rel'] for e in extra}]
        else:
            for m in moved:
                c['set_aside'].append({'rel': m, 'mod': m.split('/')[0], 'since': _ago(minutes=5), 'why': 'patch',
                                       'game_version': c['game']['version'], 'date': None, 'state': 'aside',
                                       'script': m.endswith('.ts4script')})


# ------------------------------------------------------------------ Sims 4 Studio batch fixes (docs/batchfix.md)
def batch_fixes():
    """The same shape as api_care.batch_fixes, from the example results (test knob: _st()['batch']['scanned'] = None
    shows "not checked yet")."""
    from speedkit import batchfix as BF
    c = _st()
    with S._lock:
        b = copy.deepcopy(c['batch'])
        held = {h['rel'] for h in c['set_aside']}
    if not b['scanned']:
        return {'ok': True, 'scanned': None, 'files_checked': 0, 'files': 0, 'fixes': [], 'parked': 0,
                'message': 'Your CC has not been checked yet. The first check reads every CC file and can take a few '
                           'minutes for a big collection.'}
    fixes, names, parked = [], set(), 0
    for fx in BF.FIXES:
        files = b['found'].get(fx['id']) or []
        if not files:
            continue
        view = []
        for x in files:
            aside = x['rel'] in held
            parts = x['rel'].split('/')
            root = 'Mods_parked' if aside else x['root']
            view.append({'rel': x['rel'], 'name': parts[-1], 'folder': '/'.join(parts[:-1]), 'root': root,
                         'in_mods': root == 'Mods', 'set_aside': aside, 'parts': x['parts'], 'why': BF.why(fx['id'], x)})
            names.add(x['rel'])
        n_parked = sum(1 for v in view if not v['in_mods'] and not v['set_aside'])
        parked += n_parked
        fixes.append({'id': fx['id'], 'name': fx['name'], 'menu': list(fx['menu']), 'section': fx['section'],
                      'update': fx['update'], 'problem': fx['problem'], 'what': fx['what'], 'count': len(view),
                      'in_mods': sum(1 for v in view if v['in_mods']), 'set_aside': sum(1 for v in view if v['set_aside']),
                      'parked': n_parked, 'files': view, 'more': 0, 'sources': list(fx['sources'])})
    n = len(names)
    msg = ('%d CC file%s may need a Sims 4 Studio batch fix (%d fix%s).' % (n, '' if n == 1 else 's', len(fixes),
           '' if len(fixes) == 1 else 'es')) if fixes else \
        'No CC matches a problem that a Sims 4 Studio batch fix is known for.'
    return {'ok': True, 'scanned': b['scanned'], 'files_checked': b['files_checked'], 'files': n, 'fixes': fixes,
            'parked': parked, 'message': msg}


def batch_fix_scan(progress=None):
    c = _st()
    with S._lock:
        n = c['batch']['files_checked']
    S._run(progress, [('library', 'Looking for new or changed CC files'),
                      ('batchfix', 'Checking CC files: %s of %s' % (format(n // 2, ','), format(n, ','))),
                      ('done', 'Checked %s CC files' % format(n, ','))])
    with S._lock:
        c['batch']['scanned'] = datetime.now().replace(microsecond=0).isoformat()
        if not c['batch']['found']:
            c['batch']['found'] = _batch_examples()
    r = batch_fixes()
    return {'ok': True, 'files': n, 'found': r['files'], 'read': 37, 'seconds': 3.1,
            'message': 'Checked %s CC files. %d may need a Sims 4 Studio batch fix.' % (format(n, ','), r['files'])}


def batch_fix_open(rel):
    r = batch_fixes()
    if not any(x['rel'] == rel for fx in r['fixes'] for x in fx['files']):
        return {'ok': False, 'message': 'That file is not in the list any more. Check again.'}
    return {'ok': True, 'message': 'Preview: the folder of %s would open now.' % rel.split('/')[-1]}

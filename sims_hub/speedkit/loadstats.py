r"""How long the game takes to load in each mode, and the time Quick Start saves - from SpeedKit Monitor's
loadtimes.csv (<Sims 4>\SpeedKit\reports\loadtimes.csv, columns in docs\ingame.md).

    summary(csv_path)   # {'modes': {...}, 'saved_s', 'saved_total_s', 'confidence', 'message'}

One entry per game start (rows are grouped by their 'launch_time'; rows without one each count alone):
  * to the main menu: launch_to_menu_s of the start's first row that has it;
  * loading the save: lot_load_s of its first lot (lot_index 1, the earliest) - the time the player waits after
    picking a save, not the time spent in the menu;
  * load time = both together (only the menu part when no lot was loaded).
A mode's typical time is the median of its starts (one very slow start - a patch, an update of the fast pack -
does not skew it). The saving compares Full Start with the fast modes (Quick Start, else One save) and is only
claimed when both have starts; 'confidence' is 'none' (no starts), 'one_mode' (only one side measured), 'low'
(fewer than 3 starts on a side) or 'ok'.
"""
import csv
import statistics

MODES = ('fast', 'save', 'full', 'studio')
FAST_FAMILY = ('fast', 'save')
ENOUGH = 3


def _num(v):
    try:
        return float(v) if v not in (None, '') else None
    except ValueError:
        return None


def read_starts(csv_path):
    """[{'launch', 'profile', 'menu_s', 'lot_s', 'total_s', 'time'}] oldest first."""
    try:
        with open(csv_path, encoding='utf-8', errors='replace', newline='') as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return []
    starts, order = {}, []
    for i, r in enumerate(rows):
        key = (r.get('launch_time') or '').strip() or ('row%d' % i)
        s = starts.get(key)
        if s is None:
            s = starts[key] = {'launch': key, 'profile': (r.get('profile') or '').strip().lower(), 'menu_s': None,
                               'lot_s': None, 'lot_since': None, 'time': r.get('time') or ''}
            order.append(key)
        if not s['profile'] and r.get('profile'):
            s['profile'] = r['profile'].strip().lower()
        menu = _num(r.get('launch_to_menu_s'))
        if s['menu_s'] is None and menu is not None and menu > 0:
            s['menu_s'] = menu
        if (r.get('event') or '') == 'lot_loaded':
            lot = _num(r.get('lot_load_s'))
            since = _num(r.get('since_launch_s'))
            idx = (r.get('lot_index') or '').strip()
            if lot is not None and lot > 0 and idx in ('', '1'):
                if s['lot_s'] is None or (since is not None and s['lot_since'] is not None and since < s['lot_since']):
                    s['lot_s'], s['lot_since'] = lot, since
    out = []
    for k in order:
        s = starts[k]
        if s['menu_s'] is None and s['lot_s'] is None:
            continue
        s['total_s'] = (s['menu_s'] or 0) + (s['lot_s'] or 0)
        s.pop('lot_since', None)
        out.append(s)
    return out


def _mode(profile):
    p = (profile or '').lower()
    if p in MODES:
        return p
    if p in ('lean',):
        return 'studio'
    return 'other'


def summary(csv_path):
    starts = read_starts(csv_path)
    modes = {}
    for s in starts:
        m = _mode(s['profile'])
        d = modes.setdefault(m, {'starts': 0, 'menu': [], 'lot': [], 'total': [], 'last': None})
        d['starts'] += 1
        if s['menu_s'] is not None:
            d['menu'].append(s['menu_s'])
            d['total'].append(s['total_s'])
        if s['lot_s'] is not None:
            d['lot'].append(s['lot_s'])
        d['last'] = s['time'] or d['last']
    view = {}
    for m, d in modes.items():
        view[m] = {'starts': d['starts'], 'menu_s': round(statistics.median(d['menu']), 1) if d['menu'] else None,
                   'lot_s': round(statistics.median(d['lot']), 1) if d['lot'] else None,
                   'total_s': round(statistics.median(d['total']), 1) if d['total'] else None, 'last': d['last']}
    full = view.get('full')
    fast_key = next((k for k in FAST_FAMILY if view.get(k) and view[k]['total_s']), None)
    fast = view.get(fast_key) if fast_key else None
    saved = saved_total = None
    if full and full['total_s'] and fast:
        saved = round(full['total_s'] - fast['total_s'], 1)
        fast_totals = [s['total_s'] for s in starts if _mode(s['profile']) in FAST_FAMILY and s['menu_s'] is not None]
        saved_total = round(sum(max(0.0, full['total_s'] - t) for t in fast_totals), 1)
    if not starts:
        confidence = 'none'
    elif not (full and full['total_s']) or not fast:
        confidence = 'one_mode'
    elif full['starts'] < ENOUGH or fast['starts'] < ENOUGH:
        confidence = 'low'
    else:
        confidence = 'ok'
    return {'ok': True, 'modes': view, 'compare': fast_key, 'saved_s': saved, 'saved_total_s': saved_total,
            'confidence': confidence, 'starts': len(starts), 'message': _message(view, fast_key, saved, confidence)}


def _dur(s):
    """'45 s', '6 min', '1 h 5 min' - rounded the way people say load times (the page rounds the same way)."""
    s = int(round(s or 0))
    if s < 90:
        return '%d s' % s
    m = int(round(s / 60.0))
    if m < 60:
        return '%d min' % m
    return '%d h %d min' % (m // 60, m % 60)


WORDS = {'fast': 'Quick Start', 'save': 'One save', 'full': 'Full Start', 'studio': 'Studio mode', 'other': 'Other'}


def _message(view, fast_key, saved, confidence):
    if confidence == 'none':
        return 'No start times recorded yet. The SpeedKit Monitor times each game start made through the Hub.'
    parts = ['%s: %s' % (WORDS[m], _dur(view[m]['total_s'])) for m in ('fast', 'save', 'full')
             if view.get(m) and view[m]['total_s']]
    line = ' - '.join(parts)
    if confidence == 'one_mode':
        if view.get('full') and view['full']['total_s']:
            return line + '. Start once with Quick Start to compare.'
        return line + '. Start once with Full Start to compare.'
    if saved is not None and saved <= 0:
        return line + '. So far Quick Start has not been quicker on this PC.'
    tail = ' (about %s less per start)' % _dur(saved) if saved else ''
    if confidence == 'low':
        return line + tail + '. Based on only a few starts so far; the figures become more reliable with more starts.'
    return line + tail + '.'

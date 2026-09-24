"""library_report.html - one self-contained, readable page about the mod library, the saves and the game.

    write(path, status, saves, graphics_table)     # speedkit.api.report() fills it in

Everything shown comes from speedkit.api (status(), list_saves()) and settings.graphics_tuned_table(); the
page has no scripts and no outside resources, so it opens anywhere.
"""
import html
import os
import time


def _e(x):
    return html.escape('' if x is None else str(x))


def _num(x, fmt='{:,}'):
    return '-' if x is None else fmt.format(x)


CSS = """
body{font-family:'Segoe UI',Arial,sans-serif;background:#16121f;color:#ece8f5;margin:0;padding:24px;line-height:1.45}
h1{margin:0 0 4px;background:linear-gradient(90deg,#ff6fb5,#9b6bff);-webkit-background-clip:text;color:transparent}
h2{margin:28px 0 8px;color:#d8c8ff;font-size:18px}
.sub{color:#a99cc4;margin-bottom:18px}
.cards{display:flex;flex-wrap:wrap;gap:12px}
.card{background:#231c33;border-radius:12px;padding:12px 16px;min-width:180px}
.card b{display:block;font-size:22px;color:#fff}
table{border-collapse:collapse;width:100%;background:#1d1729;border-radius:10px;overflow:hidden}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid #2e2642;font-size:14px}
th{background:#2a2140;color:#cbb8ff}
.warn{color:#ffb86b}.ok{color:#7ee2a8}.muted{color:#8f84a8}
"""


# the words the Hub uses (docs\hub_contract.md: no 'package', 'profile', 'journal', 'CAS part' ...)
MODE_WORDS = {'fast': 'Quick Start', 'full': 'Full Start', 'save': 'One save', 'studio': 'Studio mode',
              'lean': 'Studio mode', 'custom': 'Your own mix'}
PACK_WORDS = {'fresh': 'ready', 'stale': 'gets a quick update when you press Play',
              'missing': 'made the first time you press Play'}
EVENT_WORDS = {'main_menu': 'Main menu', 'lot_loaded': 'Lot loaded'}
STATE_WORDS = {'committed': 'Done', 'undone': 'Undone', 'rolled_back': 'Cancelled', 'open': "Didn't finish"}


def _state_word(state):
    s = str(state or '')
    return STATE_WORDS.get(s) or ("Didn't finish" if s.startswith('failed') else s)


def build(status, saves, graphics_table):
    st = status or {}
    lib = st.get('library') or {}
    prof = st.get('profile') or {}
    mem = st.get('memory') or {}
    gr = st.get('graphics') or {}
    fp = st.get('fastpack') or {}
    out = ['<!doctype html><html><head><meta charset="utf-8"><title>Library report</title>',
           '<style>%s</style></head><body>' % CSS,
           "<h1>Novulon's Sims Hub</h1><div class='sub'>Library report, %s</div>" % _e(time.strftime('%Y-%m-%d %H:%M'))]
    cas_full, cas_fast = lib.get('cas_full'), lib.get('cas_fast')
    out.append("<div class='cards'>")
    for label, value in (('CC and mod files', '%s files' % _num(lib.get('packages'))),
                         ('Library size', '%s GB' % _num(lib.get('gb'), '{:,.1f}')),
                         ('CC items (all CC)', _num(cas_full)),
                         ('CC items (Quick Start)', _num(cas_fast)),
                         ('How the game starts', MODE_WORDS.get(prof.get('name')) or prof.get('label')),
                         ('Graphics', gr.get('label')),
                         ('Free memory', '%s of %s GB' % (_num(mem.get('free_gb'), '{:.1f}'), _num(mem.get('total_gb'), '{:.1f}'))),
                         ('Quick Start', '%s%s' % (PACK_WORDS.get(fp.get('state'), fp.get('state') or '-'),
                                                 (' (%.1f GB)' % fp['gb']) if fp.get('gb') else '')),
                         ('Free on C:', '%s GB' % _num((st.get('disk') or {}).get('c_free_gb'), '{:.0f}'))):
        out.append("<div class='card'>%s<b>%s</b></div>" % (_e(label), _e(value)))
    out.append('</div>')
    if cas_full and cas_fast:
        out.append("<p>Quick Start loads <b>%.1f%%</b> of your CC items - the number that decides how long the game "
                   "takes to start.</p>" % (100.0 * cas_fast / cas_full))
    out.append('<h2>Your saves</h2>')
    if saves:
        out.append('<table><tr><th>Save</th><th>Household</th><th>World</th><th>Sims</th><th>Lots</th>'
                   '<th>CC items used</th><th>CC items missing</th><th>CC items loaded when you play only this save</th>'
                   '<th>Fast start</th><th>Last played</th></tr>')
        for s in saves:
            out.append('<tr><td>%s<br><span class="muted">%s</span></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                       '<td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                           _e(s.get('name')), _e(s.get('slot')), _e(s.get('household') or '-'), _e(s.get('world') or '-'),
                           _num(s.get('sims')), _num(s.get('lots')), _num(s.get('cc_parts')), _num(s.get('cc_missing')),
                           _num(s.get('cas_loaded')), _e(PACK_WORDS.get((s.get('pack') or {}).get('state'), '-')),
                           _e((s.get('last_played') or '').replace('T', ' '))))
        out.append('</table>')
    else:
        out.append('<p class="muted">No saves found.</p>')
    if graphics_table:
        out.append('<h2>Graphics: your SGR Full settings and SpeedKit Max Quality</h2>')
        out.append('<table><tr><th>Setting</th><th>Game default</th><th>SGR Full (before)</th>'
                   '<th>SpeedKit Max Quality</th></tr>')
        for r in graphics_table:
            out.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                _e(r.get('setting') or r.get('what') or r.get('prop')), _e(r.get('stock')), _e(r.get('before')),
                _e(r.get('after'))))
        out.append('</table>')
    out.append('<h2>Memory</h2>')
    if mem.get('warnings'):
        out.append('<ul>%s</ul>' % ''.join("<li class='warn'>%s</li>" % _e(w) for w in mem['warnings']))
    else:
        out.append("<p class='ok'>No memory warnings.</p>")
    if mem.get('top'):
        out.append('<p class="muted">Biggest programs: %s</p>' % _e(', '.join('%s %.1f GB' % (t['name'], t['gb'])
                                                                              for t in mem['top'][:6])))
    lt = st.get('load_times') or []
    out.append('<h2>Load times</h2>')
    if lt:
        out.append('<table><tr><th>When</th><th>What</th><th>How it started</th><th>Start to main menu (s)</th>'
                   '<th>Loading a lot (s)</th></tr>')
        for r in lt:
            out.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                _e((r.get('time') or '').replace('T', ' ')), _e(EVENT_WORDS.get(r.get('event'), r.get('event'))),
                _e(MODE_WORDS.get(r.get('profile'), r.get('profile'))),
                _num(r.get('launch_to_menu_s'), '{:.0f}'), _num(r.get('lot_load_s'), '{:.1f}')))
        out.append('</table>')
    else:
        out.append('<p class="muted">No load times yet - they are measured by SpeedKit Monitor the next time you play.</p>')
    js = st.get('journals') or []
    if js:
        out.append('<h2>Recent changes (the newest one can be undone on the Tools page)</h2>'
                   '<table><tr><th>When</th><th>What</th><th></th></tr>')
        for j in js:
            out.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (_e((j.get('when') or '').replace('T', ' ')),
                                                                      _e(j.get('title') or j.get('kind')),
                                                                      _e(_state_word(j.get('state')))))
        out.append('</table>')
    out.append('</body></html>')
    return '\n'.join(out)


def write(path, status, saves, graphics_table):
    """Write the report to path (SpeedKit's own reports folder), atomically."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(build(status, saves, graphics_table))
    os.replace(tmp, path)
    return path

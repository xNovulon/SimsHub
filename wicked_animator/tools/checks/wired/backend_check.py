"""The server side of the newly wired features, without a game (nothing is written outside a temp folder).

    python tools/checks/wired/backend_check.py

- Send to game with props and a CC place: the prop clips and animation_props_list, and animation_custom_locations
  (read back the way the Doctor and WickedWhims' identifier read them - the animation counts as loadable).
- A strip-club lap dance: two clips and a StripClubDanceAnimationPackage WickedWhims' loader accepts.
- The add-on routes on a PC without The Sims 4 answer plainly (a 404 with "install not found"), never crash.
The rig is tools/checks/lib/fake_game_server.py's stand-in (the real one comes from the game).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'lib'))
os.environ['WA_FAKE_HOME'] = tempfile.mkdtemp(prefix='wa_wired_')
import fake_game_server as F        # noqa: E402  (swaps in the stand-in rig; the server is not started)
import exporter as X                # noqa: E402
import stripclub as S               # noqa: E402
import wwlists                      # noqa: E402
from clipfmt import parse_clip      # noqa: E402

rows = []


def row(name, ok, detail=''):
    rows.append((name, bool(ok), detail))


def snippet_xml(resources):
    return next(r[3] for r in resources if r[0] == 0x7DF2169C).decode('utf-8')


def baked(frames=30, actors=2, **extra):
    rig = F.fake_rig()
    tracks = {'b__Pelvis__': {'t': [[0, 1.0 + 0.01 * (i % 5), 0] for i in range(frames)], 'r': [[0, 0, 0, 1]] * frames}}
    base = {'uid': 'a0123456789ab', 'name': 'Wired check', 'author': 'Checks', 'category': 'VAGINAL', 'tags': [], 'next': [],
            'loops': 10, 'naked': 'ALL', 'locations': ['FLOOR'], 'fps': 30, 'frames': frames,
            'actors': [{'gender': g, 'naked': 'ALL', 'tracks': tracks, 'body': b, 'sounds': [], 'role': r}
                       for g, b, r in [('FEMALE', 'yf', 'receiver'), ('MALE', 'ym', 'giver')][:actors]]}
    base.update(extra)
    assert rig['bones']
    return base


# ---------------------------------------------------------------- props + a CC place
prop = {'guid': '14961458478131052544', 'name': 'Wine glass', 'source': 'game',
        'track': {'t': [[0.1, 1.2 + 0.001 * i, 0.3] for i in range(30)], 'r': [[0, 0, 0, 1]] * 30}}
res, info = X.animation_resources(baked(props=[prop], locations=['NONE'], customLocations=['1234567890123', 'x']), metas={})
xml = snippet_xml(res)
row('props: a prop clip is written with the animation', len(info['prop_clips']) == 1 and info['props'][0]['name'] == 'Wine glass', info['prop_clips'])
row('props: animation_props_list names the prop and its clip', 'animation_props_list' in xml and '<T n="prop_guids">14961458478131052544</T>' in xml
    and info['prop_clips'][0] in xml, [l.strip() for l in xml.splitlines() if 'prop_' in l][:3])
clip = next(r[3] for r in res if r[0] == 0x6B20C4F3 and r[2] == X.fnv64(info['prop_clips'][0]))
parsed = parse_clip(clip)
row('props: the prop clip is a readable clip of the same length (1 s)', isinstance(parsed, dict) and abs(parsed.get('duration', 0) - 1.0) < 0.05, {k: v for k, v in parsed.items() if isinstance(v, (int, float, str))} if isinstance(parsed, dict) else type(parsed).__name__)
row('CC place: animation_custom_locations holds the object id (a bad id is left out)',
    '<T n="animation_custom_locations">1234567890123</T>' in xml and '<T n="animation_locations">NONE</T>' in xml,
    [l.strip() for l in xml.splitlines() if 'locations' in l])
parsed_ww = wwlists.parse_xml(xml.encode('utf-8'))
ident = wwlists.identifier(parsed_ww[0]) if parsed_ww else None
row("CC place: WickedWhims' identifier accepts it (a custom object decides where it plays)", bool(ident), ident)
res2, _ = X.animation_resources(baked(), metas={})
row('without props or a CC place the XML is as before', 'animation_props_list' not in snippet_xml(res2) and 'custom_locations' not in snippet_xml(res2), '')

# ---------------------------------------------------------------- a lap dance
dance = baked(frames=225, dance={'type': 'LAP_DANCE', 'dancer': 0, 'watcher': 1, 'genders': ['FEMALE', 'MALE'], 'loops': 4, 'set': 'Neon nights', 'order': 2, 'bpm': 128})
dres, dinfo = S.dance_resources(dance)
d = S.parse_dance_xml(snippet_xml(dres))
row('lap dance: the dancer and the watcher each get a clip', len(dinfo['clips']) == 2 and dinfo['clips'][1].endswith('_watcher'), dinfo['clips'])
row("lap dance: WickedWhims' loader keeps every entry", d['class'] == 'StripClubDanceAnimationPackage' and len(d['entries']) == 2 and not any(S.problems(e) for e in d['entries']),
    d['entries'][0])
row('lap dance: the routine name and its place in it are written', d['entries'][0].get('dance_set_name') == 'Neon nights' and d['entries'][0].get('dance_set_order') == '2', '')
try:
    S.dance_resources(baked(frames=30, actors=1, dance={'type': 'LAP_DANCE'}))
    row('lap dance with one sim: refused in plain words', False, 'no error')
except ValueError as e:
    row('lap dance with one sim: refused in plain words', 'second sim' in str(e), str(e))

# ---------------------------------------------------------------- routes without a game
import ext_refit, ext_game, ext_props, ext_dance    # noqa: E402,E401
try:
    ext_refit.refit_places({})
    row('refit_places without a game: a plain 404', False, 'answered')
except LookupError as e:
    row('refit_places without a game: a plain 404', 'install not found' in str(e), str(e))
import time                                          # noqa: E402
st = ext_game._ea_status({})
for _ in range(100):                                  # the background read gives up on its own thread
    if st.get('error') or st.get('ready'):
        break
    time.sleep(0.1)
    st = ext_game._ea_status({})
row('ea_status without a game: says why', not st.get('ready') and 'install not found' in str(st.get('error')), st.get('error'))
row('props without a game: an empty list', ext_props._props({}) == [], '')
info = ext_dance._info({})
row("dance_info without WickedWhims: the pole's size for a stand-in", info['pole']['found'] is False and info['pole']['bounds']['max'][1] > 2.5, info['pole']['bounds'])

w = max(len(r[0]) for r in rows)
print('\nWired features: the server side (no game)')
print('-' * (w + 20))
for name, ok, detail in rows:
    print('%s  %s  %s' % ('PASS' if ok else 'FAIL', name.ljust(w), json.dumps(detail, default=str)[:220] if detail not in ('', None) else ''))
bad = sum(1 for r in rows if not r[1])
print('-' * (w + 20))
print('%d PASS, %d FAIL' % (len(rows) - bad, bad))
sys.exit(1 if bad else 0)

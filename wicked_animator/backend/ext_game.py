"""Game data routes (read-only on the game and Mods folders): the sims' game voices, effect names, creator moments,
and the game's own clips (romance references, idle layers, real faces).

    GET /api/voices                       {codes: {female, male}, lines: [{name, voices, tags, sec, lowprob, gender}]}
    GET /api/effects                      {popular, joints, groups}; ?joint=b__Penis_Tip sorts by that body part
    GET /api/effects?q=drool              {items: [{name, label, group, uses}]}
    GET /api/effects?check=a,b            {checks: {a: {valid, equivalent}}}  (an import's effect names)
    GET /api/animation_events?id=N        {events, dropped, swapped}: a library animation's moments (seconds, aN targets)
    GET /api/ea_status                    what of the game's clips is ready (the first build runs in the background)
    GET /api/ea_library?q=&cat=&loc=&page= {ready, total, items} - romance pairs from the game
    GET /api/ea_animation?id=ea:<base>&step=  the pair with its two decoded clips (like /api/animation)
    GET /api/ea_faces                     {ready, faces: [{id, label, group, group_label, bones: {bone: {r, t}}}]}
    GET /api/ea_idles                     {ready, groups: [{id, label, items: [{name, label}]}]}
    GET /api/ea_idle?name=                {name, ticks, fps, bones: {bone: [[x,y,z,w] per tick]}}
    GET /api/cum_layers                   {TYPE: [{level, inst, rect: [u0, v0, u1, v1]}]} - WickedWhims' cum parts
    GET /api/cum_tex?inst=                the cropped PNG of one of them (only instances cum_layers lists)
    GET /api/tray_voice?tray=&index=      {voice, voicePitch} of an adult Tray sim (its own game voice)

Adults only: voice lines through eaaudio._LINE_BLOCK, effects through vfx.adult, the game's clips through
eaclips.adult (plus the clip_cats BAD list); creator moments come from the adult library only.
"""
import traceback

import gamedata as G


def _voices(q):
    import eaaudio
    return {'codes': {'female': list(eaaudio.ADULT_VOICES['female']), 'male': list(eaaudio.ADULT_VOICES['male'])},
            'lines': eaaudio.adult_voice_lines()}


def _effects(q):
    import vfx
    if q.get('check'):
        names = [n.strip() for n in q['check'].split(',') if n.strip()][:200]
        return {'checks': {n: {'valid': vfx.valid(n), 'equivalent': vfx.adult_equivalent(n)} for n in names}}
    if q.get('q'):
        return {'items': vfx.search(q['q'], q.get('limit') or 60)}
    return {'popular': vfx.popular(q.get('joint')), 'joints': vfx.JOINTS, 'groups': vfx.GROUPS}


def _library_animation(q):
    try:
        i = int(q.get('id', ''))
    except ValueError:
        raise ValueError('id must be a number')
    lib = G.library()['animations']
    if not 0 <= i < len(lib):
        raise LookupError('no such animation')
    return lib[i]


def _animation_events(q):
    """A creator animation's moments, ready to become the app's moments: effect names swapped to their adult game
    version (or dropped when there is none), joints that are not bones fixed."""
    import vfx
    a = _library_animation(q)
    out, dropped, swapped = [], 0, 0
    for e in G.animation_events(a):
        if e['target'] >= len(a['actors']):
            dropped += 1
            continue
        if e['type'] == 'EFFECT':
            eq = vfx.adult_equivalent(e['effect_name'])
            if not eq or not vfx.joint_ok(e['effect_joint_name']):
                dropped += 1
                continue
            if eq != e['effect_name'].lower():
                swapped += 1
            e = dict(e, effect_name=eq)
        out.append(e)
    return {'id': a['id'], 'events': out, 'dropped': dropped, 'swapped': swapped}


# ------------------------------------------------------------------ the game's own clips
def _ready(part):
    """Is this part of the game-clip data in memory? If not, the background build is started (never blocks)."""
    import eaclips
    have = {'index': eaclips._idx, 'library': eaclips._lib, 'faces': eaclips._faces}[part]
    if have is not None:
        return True
    eaclips.start_background()
    return False


def _ea_status(q):
    import eaclips
    st = eaclips.status()
    if not st.get('ready') and not (eaclips._thread and eaclips._thread.is_alive()):
        st = eaclips.start_background()
    return st


def _ea_library(q):
    import eaclips
    if not _ready('library'):
        return {'ready': False, 'building': True, 'total': 0, 'items': []}
    text = (q.get('q') or '').lower().strip()
    cat, loc = q.get('cat') or '', q.get('loc') or ''
    out = []
    for a in eaclips.library():
        if cat and cat not in (a['category'], a['kind']):
            continue
        if loc and loc not in a['locations']:
            continue
        if text and text not in a['name'].lower() and text not in a['category'].lower():
            continue
        out.append({k: a[k] for k in ('id', 'name', 'author', 'locations', 'category', 'kind', 'loop', 'seconds',
                                      'actors', 'tags')})
    page = max(0, int(q.get('page', '0') or 0))
    cats = {}
    for a in eaclips.library():
        cats[a['category']] = cats.get(a['category'], 0) + 1
    return {'ready': True, 'total': len(out), 'items': out[page * 100:(page + 1) * 100], 'categories': cats}


def _ea_animation(q):
    import eaclips
    entry = eaclips.library_entry(q.get('id'))
    if not entry:
        raise LookupError('not a game animation')
    step = max(1, int(q.get('step', '1') or 1))
    return dict(entry, clips=[eaclips.tracks(c, step) for c in entry['clips']], events=[])


def _ea_faces(q):
    import eaclips
    if not _ready('faces'):
        st = eaclips.status()
        return {'ready': False, 'building': True, 'faces': [], 'done': st.get('faces_done', 0),
                'total': st.get('faces_total', 0)}
    return {'ready': True, 'faces': eaclips.face_library()}


def _ea_idles(q):
    import eaclips
    if not _ready('index'):
        return {'ready': False, 'building': True, 'groups': []}
    groups = []
    for gid, label, _ in eaclips.IDLE_GROUPS:
        groups.append({'id': gid, 'label': label, 'items': []})
    by = {g['id']: g for g in groups}
    for x in eaclips.idles():
        by[x['group']]['items'].append({'name': x['name'], 'label': x['label']})
    return {'ready': True, 'groups': [g for g in groups if g['items']]}


def _ea_idle(q):
    import eaclips
    name = q.get('name') or ''
    if not name:
        raise ValueError('name is needed')
    return eaclips.idle_deltas(name)


# ------------------------------------------------------------------ cum on the skin, a Tray sim's voice (R2-4)
def _cum_layers(q):
    import skintex
    return skintex.cum_layers()


def _cum_tex(q):
    import skintex
    path = skintex.cum_texture_path(q.get('inst') or '')
    if not path:
        raise LookupError('not a cum layer')
    with open(path, 'rb') as f:
        return f.read(), 'image/png'


_ADULT_AGES = ('youngadult', 'adult', 'elder')


def _tray_voice(q):
    """A Tray sim's own game voice, without building its body (the Sounds step asks for it). Adults only."""
    import eaaudio, trayfmt
    try:
        index = int(q.get('index', '0') or 0)
    except ValueError:
        raise ValueError('index must be a number')
    sims = trayfmt.household_sims(q.get('tray') or '')['sims']
    if not 0 <= index < len(sims):
        raise LookupError('no such sim')
    s = sims[index]
    if s.get('age') not in _ADULT_AGES or s.get('species', 'human') != 'human':
        raise LookupError('no such sim')
    return {'voice': eaaudio.voice_for_actor(s.get('voice_actor'), s.get('gender')),
            'voicePitch': s.get('voice_pitch') or 0}


GET = {'voices': _voices, 'effects': _effects, 'animation_events': _animation_events, 'ea_status': _ea_status,
       'ea_library': _ea_library, 'ea_animation': _ea_animation, 'ea_faces': _ea_faces, 'ea_idles': _ea_idles,
       'ea_idle': _ea_idle, 'cum_layers': _cum_layers, 'cum_tex': _cum_tex, 'tray_voice': _tray_voice}


def _warm():
    """After the sound list (server._warm runs add-on warm-ups last): the game's voice lines, effect names and
    WickedWhims' cum textures, then the game's clips in their own background thread (the first build takes a minute
    or two)."""
    for step in ('voices', 'effects', 'cum'):
        try:
            if step == 'voices':
                import eaaudio
                eaaudio.adult_voice_lines()
            elif step == 'effects':
                import vfx
                vfx.names()
            else:
                import skintex
                skintex.cum_layers()        # WickedWhims' cum textures, cropped once (about 10 s the first time)
        except Exception:
            traceback.print_exc()
    try:
        import eaclips
        eaclips.start_background()
    except Exception:
        traceback.print_exc()


WARM = [_warm]

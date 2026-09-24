"""WickedWhims strip-club dances: the XML, the clips and the package (R3-4).

WickedWhims' strip clubs play dances listed in a StripClubDanceAnimationPackage snippet. Custom dances are made
"exactly the same as creating sex animations, except for the XML part" (TURBODRIVER's tutorial), so the clips are
written with the app's own clip writer (clipfmt.write_clip + exporter.actor_channels, imported, never changed) and
packed with wwpackage.build_package. Only the XML is new here.

Checked against WickedWhims itself (read only):
- the tuning class (wickedwhims/nudity/business/stripclub/dancing/_ts4_dance_animations_tuning.pyc, v185k) reads
  wickedwhims_dance_animations + dance_animations_list, and per entry display_name_id | raw_display_name,
  author_name, dance_type, dancer_gender, dancer_animation_clip_name, watcher_animation_clip_name,
  object_animation_clip_name, animation_loops, animation_negative_duration_offset, dance_set_name, dance_set_order;
- the loader (dance_animations_loader.pyc) drops an entry "from incorrect dance type" (POLE_DANCE / SPOT_DANCE /
  LAP_DANCE, upper-cased), "from missing watcher animation" (a LAP_DANCE without watcher_animation_clip_name) and
  "from incorrect negative duration offset usage" (an offset is only for animation_loops = 1); dance_set_name is
  stripped and lower-cased; dancer_gender is FEMALE or MALE;
- the dance instance reads each clip's length from the CLIP whose FNV64 instance is the clip name ("Make sure the
  CLIP FNV64 hash ID is based on the animation ClipName variable") - the same key exporter.py uses;
- WickedWhims' own list (TURBODRIVER:WickedWhims_StripClub_DanceAnimations in TURBODRIVER_WickedWhims_Tuning.package)
  and the 13 dance packs in the user's Mods use exactly this layout: <I c="StripClubDanceAnimationPackage"
  i="snippet" m="wickedwhims.nudity.business.stripclub.dancing.dance_animations_tuning">, <L> of <U> entries.

Where the dancer stands (base_stripper_handler._get_proper_location): at the dance object's position and yaw (plus
0.8 m for one raised pole). A lap dance puts the dancer AND the watcher at the seat's position
(lap_stripper_handler._start_actors), so both clips share the seat's origin.

The pole: WickedWhims knows its poles by a "unique id" (dance_locations.DANCING_POLE_WWIDS) made from the object's
tuning id and catalog name hash (turbolib2 _get_object_inorganic_unique_id, reproduced in ww_unique_id()). The pole
WickedWhims ships in its own tuning package, TURBODRIVER_justarandommodelname_201909101224327775_set1, gives
10870645675159221360 - the first id in that list - and WickedWhims' two stage marks give its DANCING_SPOT_WWIDS. So
the app shows that pole and that stage mark, read (never written) from the WickedWhims tuning package.
"""
import os, re, time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

import clipfmt
import exporter
import wwpackage
from clipfmt import write_clip, fnv64
from exporter import actor_channels
from wwpackage import build_package

SNIPPET = 0x7DF2169C
T_CLIP, T_CLIP_HEADER = 0x6B20C4F3, 0xBC4A5044
TUNING_CLASS = 'StripClubDanceAnimationPackage'
TUNING_MODULE = 'wickedwhims.nudity.business.stripclub.dancing.dance_animations_tuning'
DANCE_TYPES = ('POLE_DANCE', 'SPOT_DANCE', 'LAP_DANCE')
DANCER_GENDERS = ('FEMALE', 'MALE')
# every field WickedWhims' tuning reads, in the order its own template writes them
FIELDS = ('display_name_id', 'raw_display_name', 'author_name', 'dance_type', 'dancer_gender',
          'dancer_animation_clip_name', 'watcher_animation_clip_name', 'object_animation_clip_name',
          'animation_loops', 'animation_negative_duration_offset', 'dance_set_name', 'dance_set_order')
REQUIRED = ('raw_display_name', 'author_name', 'dance_type', 'dancer_gender', 'dancer_animation_clip_name',
            'animation_loops')

# WickedWhims' own dance objects (TURBODRIVER_WickedWhims_Tuning.package), with the unique ids its script lists
POLE = {'id': 0xD7B5B605EF12BEEB, 'name': 'TURBODRIVER_justarandommodelname_201909101224327775_set1',
        'wwid': 10870645675159221360, 'label': "WickedWhims' dance pole"}
SPOT = {'id': 0xE289043B0CA203CA, 'name': 'TURBODRIVER_stageMarkSolo_EP06GEN_scene1_201909142034286554_set1',
        'wwid': 16653240763354693300, 'label': "WickedWhims' dance spot"}
DANCING_POLE_WWIDS = (10870645675159221360, 17583435395400619797, 12659171080646242041, 16613506613043897371,
                      12931634859377942158, 289998449, 4123777431, 1838749216, 14645616032557019053)
DANCING_SPOT_WWIDS = (16653240763220730622, 16653240763354693300)
POLE_SIZE = {'radius': 0.06, 'height': 2.91}          # the pole's own bounds (for a drawn stand-in)
# the seats a lap dance can happen on (dance_locations.DANCING_LAP_TAGS; sectional sofas are left out by WickedWhims)
LAP_SEATS = [{'id': 'chair_living', 'label': 'Armchair'}, {'id': 'chair_dining', 'label': 'Dining chair'},
             {'id': 'loveseat', 'label': 'Loveseat'}, {'id': 'sofa', 'label': 'Sofa'}]
PREFIX = 'WickedDance'
SOURCE = "Novulon's Wicked Animator"


def ww_unique_id(guid64, catalog_name):
    """turbolib2's object "unique id" (super_game_object._get_object_inorganic_unique_id): what WickedWhims compares
    with DANCING_POLE_WWIDS / DANCING_SPOT_WWIDS. The odd `eval(hex(x)[:-1])` of the original (written for Python 2's
    trailing 'L') drops the last hex digit."""
    data = [int(catalog_name), int(guid64)] if int(guid64) > int(catalog_name) else [int(guid64), int(catalog_name)]
    h = 3430008
    for item in data:
        hx = hex((1000003 * h) & 0xFFFFFFFF)[:-1]
        h = (int(hx, 16) if hx != '0x' else 0) ^ item
    h ^= len(data)
    return abs(h)


# ------------------------------------------------------------------ names
def safe_name(text, n=48):
    return (re.sub(r'[^A-Za-z0-9]+', '_', str(text or '')).strip('_') or 'Dance')[:n].strip('_') or 'Dance'


def base_name(author, name, uid=None):
    """WickedDance_<author>_<name>_<tag>: the package, the snippet and the start of every clip name."""
    tag = exporter.uid_tag(uid) if uid else ''
    return '%s_%s_%s' % (PREFIX, safe_name(author or 'Wicked', 32), safe_name(name or 'Dance')) + ('_' + tag if tag else '')


def clip_names(base, ticks, lap):
    """The dancer's clip (and the watcher's for a lap dance). The length is in the name: WickedWhims remembers a
    clip's length by its name, so a new length never needs the cache cheat."""
    d = '%s_%df_dancer' % (base, ticks)
    return (d, '%s_%df_watcher' % (base, ticks)) if lap else (d, None)


def set_name(text):
    """A routine name the way WickedWhims compares it (stripped, lower-case), kept readable."""
    s = ' '.join(str(text or '').split()).strip()
    return s[:60]


# ------------------------------------------------------------------ checking a dance like WickedWhims does
def problems(entry):
    """What would make WickedWhims drop this entry (its loader's own checks), in plain words. [] = fine."""
    out = []
    t = str(entry.get('dance_type') or '').strip().upper()
    if t not in DANCE_TYPES:
        out.append('The dance type must be pole, spot or lap.')
    g = str(entry.get('dancer_gender') or '').strip().upper()
    if g not in DANCER_GENDERS:
        out.append('The dancer must be a woman or a man.')
    if not str(entry.get('raw_display_name') or '').strip() and not entry.get('display_name_id'):
        out.append('The dance needs a name.')
    if not str(entry.get('dancer_animation_clip_name') or '').strip():
        out.append('The dancer has no clip.')
    if t == 'LAP_DANCE' and not str(entry.get('watcher_animation_clip_name') or '').strip():
        out.append('A lap dance needs the watching sim too.')
    try:
        loops = int(entry.get('animation_loops'))
    except (TypeError, ValueError):
        loops = 0
    if loops < 1:
        out.append('It has to play at least once.')
    off = float(entry.get('animation_negative_duration_offset') or 0)
    if off and loops != 1:
        out.append('An end offset only works for a dance that plays once.')
    return out


# ------------------------------------------------------------------ the XML
def _t(name, value, indent=6):
    return '%s<T n="%s">%s</T>' % (' ' * indent, name, escape(str(value)))


def entry_xml(e):
    """One <U> dance entry, fields in WickedWhims' own order; the watcher only for a lap dance, an offset only when
    it is used, the routine fields only when the dance is part of one."""
    lines = ['    <U>']
    lines.append(_t('raw_display_name', e['raw_display_name']))
    lines.append(_t('author_name', e['author_name']))
    lines.append(_t('dance_type', e['dance_type']))
    lines.append(_t('dancer_gender', e['dancer_gender']))
    lines.append(_t('dancer_animation_clip_name', e['dancer_animation_clip_name']))
    if e['dance_type'] == 'LAP_DANCE':
        lines.append(_t('watcher_animation_clip_name', e['watcher_animation_clip_name']))
    lines.append(_t('animation_loops', int(e['animation_loops'])))
    if e.get('animation_negative_duration_offset'):
        lines.append(_t('animation_negative_duration_offset', '%g' % round(float(e['animation_negative_duration_offset']), 4)))
    if e.get('dance_set_name'):
        lines.append(_t('dance_set_name', e['dance_set_name']))
        lines.append(_t('dance_set_order', int(e.get('dance_set_order') or 1)))
    lines.append('    </U>')
    return '\n'.join(lines)


def dance_xml(package_name, entries):
    """The StripClubDanceAnimationPackage snippet, laid out like WickedWhims' own list and its tutorial template."""
    body = '\n'.join(entry_xml(e) for e in entries)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<I c="%s" i="snippet" m="%s" n="%s" s="%d">\n'
            "  <!-- a strip-club dance made with Novulon's Wicked Animator -->\n"
            '  <T n="wickedwhims_dance_animations">1</T>\n'
            '  <L n="dance_animations_list">\n%s\n  </L>\n'
            '</I>\n') % (TUNING_CLASS, TUNING_MODULE, escape(package_name), wwpackage.instance_id(package_name), body)


def parse_dance_xml(xml):
    """A dance snippet (bytes or text) -> {'class', 'module', 'name', 's', 'flag', 'entries': [{field: text}]} - how
    WickedWhims' loader sees it (checks and tests)."""
    root = ET.fromstring(xml if isinstance(xml, bytes) else xml.encode('utf-8'))
    out = {'class': root.get('c'), 'module': root.get('m'), 'name': root.get('n'), 's': root.get('s'),
           'instance_type': root.get('i'), 'flag': None, 'entries': []}
    for c in root:
        if c.get('n') == 'wickedwhims_dance_animations':
            out['flag'] = (c.text or '').strip()
        if c.get('n') == 'dance_animations_list':
            for u in c:
                out['entries'].append({f.get('n'): (f.text or '').strip() for f in u})
    return out


# ------------------------------------------------------------------ building a dance
def _dance_of(baked):
    d = baked.get('dance') or {}
    t = str(d.get('type') or '').upper()
    if t not in DANCE_TYPES:
        raise ValueError('This is not a strip-club dance (make one with Dance on the Home page).')
    return d, t


def entries_for(baked, clips):
    """The XML entries of one dance: one per dancer gender (WickedWhims' own list names both for most dances)."""
    d, t = _dance_of(baked)
    name = (baked.get('name') or '').strip() or 'My dance'
    author = (baked.get('author') or '').strip() or 'Wicked'
    loops = max(1, min(99, int(d.get('loops') or baked.get('loops') or 4)))
    genders = [g for g in (d.get('genders') or []) if g in DANCER_GENDERS] or ['FEMALE']
    set_ = set_name(d.get('set'))
    out = []
    for g in dict.fromkeys(genders):
        e = {'raw_display_name': name, 'author_name': author, 'dance_type': t, 'dancer_gender': g,
             'dancer_animation_clip_name': clips[0], 'animation_loops': loops}
        if t == 'LAP_DANCE':
            e['watcher_animation_clip_name'] = clips[1]
        off = float(d.get('offset') or 0)
        if off and loops == 1:
            e['animation_negative_duration_offset'] = off
        if set_:
            e['dance_set_name'] = set_
            e['dance_set_order'] = max(1, int(d.get('order') or 1))
        out.append(e)
    return out


def dance_resources(baked):
    """([(type, group, instance, bytes)], info) for one baked dance (app.bake() + {dance: {...}}).

    baked['dance'] = {type: POLE_DANCE|SPOT_DANCE|LAP_DANCE, dancer: actor index (0), watcher: actor index (1, lap
    only), genders: [FEMALE, MALE], loops, set?, order?, bpm?}."""
    d, t = _dance_of(baked)
    actors = baked.get('actors') or []
    di = int(d.get('dancer') or 0)
    if not 0 <= di < len(actors):
        raise ValueError('The dance has no dancer.')
    lap = t == 'LAP_DANCE'
    wi = int(d.get('watcher') if d.get('watcher') is not None else (1 if di == 0 else 0))
    if lap and not (0 <= wi < len(actors) and wi != di):
        raise ValueError('A lap dance needs a second sim sitting on the seat.')
    frames = max(2, int(baked.get('frames') or 90))
    fps = float(baked.get('fps') or 30)
    base = base_name(baked.get('author'), baked.get('name'), baked.get('uid'))
    names = clip_names(base, frames, lap)
    resources, clips = [], []
    for idx, clip_name in ((di, names[0]), (wi, names[1])) if lap else ((di, names[0]),):
        actor = actors[idx]
        events = exporter.sound_events(actor, fps) if hasattr(exporter, 'sound_events') else ()
        clip, header = write_clip(clip_name, 'x', frames, actor_channels(actor, frames), source=SOURCE,
                                  events=events, tick_length=1.0 / fps)
        inst = fnv64(clip_name)
        resources.append((T_CLIP, 0, inst, clip))
        resources.append((T_CLIP_HEADER, 0, inst, header))
        clips.append(clip_name)
    entries = entries_for(baked, clips + ([None] if not lap else []))
    bad = [p for e in entries for p in problems(e)]
    if bad:
        raise ValueError(bad[0])
    xml = dance_xml(base, entries).encode('utf-8')
    resources.insert(0, (SNIPPET, 0, wwpackage.instance_id(base), xml))
    return resources, {'base': base, 'clips': clips, 'type': t, 'genders': [e['dancer_gender'] for e in entries],
                       'loops': entries[0]['animation_loops'], 'seconds': frames / fps,
                       'total_seconds': round(entries[0]['animation_loops'] * frames / fps, 2),
                       'set': entries[0].get('dance_set_name'), 'xml': xml.decode('utf-8')}


# ------------------------------------------------------------------ writing (only on a click in the app)
def _my_animations():
    env = os.environ.get('WICKED_EXPORTS_DIR')
    return os.path.join(env, 'Mods', 'FitStudio', 'MyAnimations') if env else exporter.MY_ANIMATIONS


def _exports():
    return os.environ.get('WICKED_EXPORTS_DIR') or exporter.EXPORTS


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError as ex:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if isinstance(ex, PermissionError) or getattr(ex, 'winerror', None) in (5, 32, 33):
            raise RuntimeError('The Sims 4 is using "%s". Close the game, then try again.' % os.path.basename(path)) from None
        raise RuntimeError('Could not write "%s": %s' % (os.path.basename(path), ex.strerror or ex)) from None
    return len(data)


def _older_copies(folder, base, uid):
    """Earlier sends of the same dance under another name (same uid tag), so a renamed dance never shows twice."""
    tag = exporter.uid_tag(uid) if uid else ''
    if not tag or not os.path.isdir(folder):
        return []
    return [f for f in os.listdir(folder) if f.lower().startswith(PREFIX.lower() + '_') and f.lower().endswith('_%s.package' % tag)
            and f.lower() != (base + '.package').lower()]


def readme(info, baked):
    kind = {'POLE_DANCE': 'pole dance', 'SPOT_DANCE': 'dance on a dance spot', 'LAP_DANCE': 'lap dance'}[info['type']]
    who = ' and '.join('women' if g == 'FEMALE' else 'men' for g in info['genders'])
    lines = ['%s by %s' % (baked.get('name') or 'My dance', baked.get('author') or '?'), '',
             'A WickedWhims strip-club %s (for %s), made with Novulon\'s Wicked Animator.' % (kind, who), '',
             'Install: put %s.package in your Mods folder (not deeper than one folder), then restart The Sims 4.' % info['base'],
             'Needs WickedWhims with strip clubs. Your dancers pick it by themselves; you can also choose it in',
             "WickedWhims' strip club dance settings.", '',
             'One loop is %.1f s; it plays %dx in a row (%.0f s).' % (info['seconds'], info['loops'], info['total_seconds'])]
    if info.get('set'):
        lines.append('Part of the routine "%s".' % info['set'])
    return '\n'.join(lines) + '\n'


def export_dance(baked, mode='send'):
    """mode 'send': into Mods\\FitStudio\\MyAnimations (your own game; an earlier copy under another name is
    removed). 'mod': a folder with the package and a README in Documents\\Wicked Animator Exports."""
    resources, info = dance_resources(baked)
    data = build_package(resources)
    replaced = []
    if mode == 'mod':
        title = '%s (strip club dance)' % ((baked.get('name') or '').strip() or 'My dance')
        folder_name = exporter._safe_file(title) if hasattr(exporter, '_safe_file') else safe_name(title, 80)
        root = os.path.realpath(_exports())
        folder = os.path.join(root, folder_name)
        if os.path.commonpath([os.path.realpath(folder), root]) != root or os.path.realpath(folder) == root:
            raise ValueError('Pick another name for the dance.')
        path = os.path.join(folder, info['base'] + '.package')
        size = _write(path, data)
        with open(os.path.join(folder, 'README.txt'), 'w', encoding='utf-8') as f:
            f.write(readme(info, baked))
    else:
        folder = _my_animations()
        path = os.path.join(folder, info['base'] + '.package')
        size = _write(path, data)
        for old in _older_copies(folder, info['base'], baked.get('uid')):
            try:
                os.replace(os.path.join(folder, old), os.path.join(folder, old + '.%d.replaced' % int(time.time())))
                replaced.append(old)
            except OSError:
                pass
    return {'ok': True, 'mode': mode, 'path': path, 'folder': folder, 'package': os.path.basename(path), 'bytes': size,
            'clips': info['clips'], 'type': info['type'], 'genders': info['genders'], 'loops': info['loops'],
            'seconds': info['seconds'], 'total_seconds': info['total_seconds'], 'set': info['set'], 'replaced': replaced,
            'xml': info['xml']}


# ------------------------------------------------------------------ the pole and the spot (read only)
def _mesh(obj):
    try:
        import objmesh
        m = objmesh.object_mesh(obj['id'])
    except Exception:
        return None
    if not m or not m.get('meshes'):
        return None
    return dict(m, dance_object=obj['label'], wwid=obj['wwid'])


def pole_mesh():
    """WickedWhims' own dance pole (game-space metres, origin = where the dancer is placed), or None."""
    return _mesh(POLE)


def spot_mesh():
    return _mesh(SPOT)


def info():
    """What the app needs to know before it makes a dance."""
    pole = pole_mesh()
    return {'types': list(DANCE_TYPES), 'genders': list(DANCER_GENDERS), 'fields': list(FIELDS),
            'pole': {'found': bool(pole), 'id': str(POLE['id']), 'name': POLE['name'], 'label': POLE['label'],
                     'wwid': str(POLE['wwid']), 'known_to_ww': POLE['wwid'] in DANCING_POLE_WWIDS,
                     'bounds': pole['bounds'] if pole else {'min': [-0.06, 0, -0.06], 'max': [0.06, POLE_SIZE['height'], 0.06]},
                     'package': (pole or {}).get('package')},
            'spot': {'id': str(SPOT['id']), 'label': SPOT['label'], 'wwid': str(SPOT['wwid']),
                     'known_to_ww': SPOT['wwid'] in DANCING_SPOT_WWIDS},
            'lap_seats': LAP_SEATS, 'prefix': PREFIX}

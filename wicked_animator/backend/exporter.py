"""Turn animations made in the app into game packages.

- export(project): one animation into Mods\\FitStudio\\MyAnimations (to try it in your own game).
- bundle(request): several animations and progressions packed into ONE .package (plus a README and a .zip) that
  anyone can drop into their Mods folder - with the sounds it needs from other mods packed inside.

Each animation = one CLIP + clip header per sim and a WickedWhims registration (snippet). The resource keys are the
same for a single export and inside a bundle, so having both installed never shows an animation twice.

Game names: FitStudio_<author>_<name>_<tag>, where the tag comes from the animation's uid, so two animations whose
names clean up to the same text ('Kiss!' / 'Kiss?', or any two names in Arabic) never share a package or clips.
Clip names also carry the clip's length in frames (..._90f_1): WickedWhims remembers each clip's length by its name,
so a new length is a new name and never needs the ww.clear_animation_clips_cache cheat."""
import datetime, glob, math, os, re, struct, threading, time, zipfile

import gamedata as G
import projects as P
import wwpackage as W
from clipfmt import encode_channel, write_clip, fnv32, fnv64
from dbpf import read_index, read_resource

T_CLIP, T_CLIP_HEADER = 0x6B20C4F3, 0xBC4A5044
T_SOUND, T_AUDIO = 0xFD04E3BE, 0x01A527DB
EPS = 1e-5
# clip event 19 at time 0: WickedWhims/the game keep lip-sync off this sim, so the clip's own jaw, lip and tongue
# keys are what shows (without it voices and the game's lip-sync take the mouth over)
LIPSYNC_OFF = (19, struct.pack('<IIff', 1, 100, 0.0, 100000.0))
EXPORTS = os.path.join(G.HOME, 'Documents', 'Wicked Animator Exports')
MY_ANIMATIONS = os.path.join(G.MODS_DIR, 'FitStudio', 'MyAnimations')
# a CLIMAX that plays once holds its last pose this long; WickedWhims ends it that much sooner (negative duration
# offset), so the clip never restarts for a split second before the next animation
HOLD_SECONDS = 1.0
PREF_GENDER = {'yf': 'FEMALE', 'yf_futa': 'FEMALE', 'ym': 'MALE'}


def _constant(frames):
    first = frames[0]
    return all(max(abs(a - b) for a, b in zip(first, f)) < EPS for f in frames)


def _continuous(quats):
    out, prev = [], None
    for q in quats:
        n = math.sqrt(sum(c * c for c in q)) or 1.0
        q = [c / n for c in q]
        if prev is not None and sum(a * b for a, b in zip(prev, q)) < 0:
            q = [-c for c in q]
        out.append(q)
        prev = q
    return out


def actor_channels(actor, frames, rig_key='au', hold=0):
    """actor: {'tracks': {bone: {'t': [[x,y,z]...] | None, 'r': [[x,y,z,w]...] | None}}} -> raw channels.
    hold: extra ticks at the end that keep the last pose (one more key at the very end)."""
    tracks = actor.get('tracks', {})
    frames = max(1, int(frames))
    chans = []
    for b in G.rig(rig_key)['bones']:
        # like every creator clip: the root (where the game places the sim) and the slots are left to the game
        if b['name'] == 'b__ROOT__' or b['name'].lower().endswith('_slot'):
            continue
        tr = tracks.get(b['name'], {})
        t = (tr.get('t') or [b['pos']])[:frames]
        r = _continuous((tr.get('r') or [b['rot']])[:frames])
        for sub, vals, quat in ((1, t, False), (2, r, True), (3, [[1.0, 1.0, 1.0]], False)):
            if _constant(vals):
                keys = [(0, list(vals[0]))]
            else:
                keys = [(k, list(v)) for k, v in enumerate(vals)]
                if hold:
                    keys.append((len(vals) - 1 + hold, list(vals[-1])))
            chans.append(encode_channel(b['hash'], sub, keys, quat))
    return chans


def sound_events(actor, fps):
    """Sound cues: clip event type 3 = [u32 0][u32 0][float seconds][char[128] sound name]; plus lip-sync off when the
    sim has a voice, or its jaw, lips or tongue move in the clip (open-mouth faces, licking, tongue out)."""
    events = []
    sounds = sorted(actor.get('sounds') or [], key=lambda x: x['frame'])
    if any(s.get('kind') == 'voice' for s in sounds) or actor.get('mouthMoves') or actor.get('tongueUsed'):
        events.append(LIPSYNC_OFF)
    for s in sounds:
        name = str(s['name']).encode('ascii', 'ignore')[:127]
        events.append((3, struct.pack('<IIf', 0, 0, float(s['frame']) / fps) + name.ljust(128, b'\x00')))
    return events


def _is_own(name):
    import mysounds
    return mysounds.is_mine(name)


def _own_sounds(actors, warnings):
    """Your own sounds (mysounds.py) the actors use -> (their resources, the names that are packed). One that is not
    on this computer any more is left out of the clips with a warning."""
    import mysounds
    names = sorted({str(s.get('name')) for a in actors for s in a.get('sounds') or [] if mysounds.is_mine(s.get('name'))})
    if not names:
        return [], set()
    res, missing = mysounds.resources(names)
    for n in missing:
        msg = 'Your sound \u2018%s\u2019 is not on this computer any more, so it was left out.' % n
        if msg not in warnings:
            warnings.append(msg)
    return res, set(names) - set(missing)


def _drop_missing_own(actor, packed):
    """The actor without sound events for your own sounds that are not packed."""
    sounds = actor.get('sounds') or []
    keep = [s for s in sounds if not _is_own(s.get('name')) or s.get('name') in packed]
    return actor if len(keep) == len(sounds) else dict(actor, sounds=keep)


def uid_tag(uid):
    """6 hex digits from an animation's uid (stable, and different for different animations)."""
    return '%06x' % (fnv32(str(uid)) & 0xFFFFFF) if uid else ''


def stage_name(author, name, uid=None):
    """The WickedWhims stage name of an animation made here (also the start of its package and clip names)."""
    a = W.safe_name(author or 'Fit Studio')[:32].strip('_')
    n = W.safe_name(name or 'My animation')[:48].strip('_')
    tag = uid_tag(uid)
    return 'FitStudio_%s_%s' % (a, n) + ('_' + tag if tag else '')


def _legacy_stage(author, name):
    """The name older versions gave the same animation (no uid tag) - its package is replaced on the next send."""
    return 'FitStudio_' + W.safe_name(author or 'Fit Studio') + '_' + W.safe_name(name or 'My animation')


def _meta_stage(m):
    return stage_name(m.get('author') or 'Fit Studio', m.get('name'), m.get('uid'))


def _installed(u, metas, sent):
    """Is animation u in your game now (its package in MyAnimations)?"""
    base = sent.get(u)
    if base and os.path.isfile(os.path.join(MY_ANIMATIONS, base + '.package')):
        return True
    m = metas.get(u)
    return bool(m) and os.path.isfile(os.path.join(MY_ANIMATIONS, _meta_stage(m) + '.package'))


def _links(project, metas, present=None):
    """(next stages, next names, may be picked at random, warnings).

    present: the uids packed together in a mod - links and 'only through the chain' then only count steps that are
    in the mod. None: your own game - an earlier step counts when it is installed, links point to every next step."""
    uid = project.get('uid')
    name = (project.get('name') or '').strip() or 'My animation'
    nxt, names, warnings, random_ok = [], [], [], True
    if uid:
        if present is None:
            sent = P.exports()
            has_step = lambda u: _installed(u, metas, sent)
            links_to = None
        else:
            has_step = links_to = lambda u: u in present
        uids, later, waiting = P.stage_links(uid, has_step, links_to)
        random_ok = not later
        for u in uids:
            m = metas.get(u)
            if m:
                nxt.append(_meta_stage(m))
                names.append(m.get('name') or 'Untitled')
        if random_ok:
            for prog, before in waiting:
                b = (metas.get(before) or {}).get('name') or 'the step before it'
                warnings.append('"%s" comes after "%s" in "%s", but "%s" is not %s, so "%s" can also start on its own.'
                                % (name, b, prog, b, 'in this mod' if present is not None else 'in your game yet', name))
    # links typed in by hand in older versions: {name, author[, uid]}
    for n in project.get('next') or []:
        if not n.get('name'):
            continue
        m = metas.get(n.get('uid')) or next((m for m in metas.values() if m.get('name') == n['name']
                                             and (m.get('author') or '') == (n.get('author') or '')), None)
        nxt.append(_meta_stage(m) if m else _legacy_stage(n.get('author'), n['name']))
        names.append(n['name'])
    own = stage_name(project.get('author'), project.get('name'), uid).lower()
    seen, out, out_names = set(), [], []
    for s, nm in zip(nxt, names):
        if s.lower() != own and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
            out_names.append(nm)
    return out, out_names, random_ok, warnings


# voice actor codes at the end of a voice line's name ('vo_..._fa'). Without a code the game adds each sim's own voice.
ADULT_VOICE_CODES = ('fa', 'fb', 'fc', 'fd', 'ma', 'mb', 'mc', 'md')
NOT_ADULT_VOICE_CODES = ('ca', 'cb', 'cc', 'cd', 'pa', 'ho', 're', 'ky', 'al')
_VOICE_CODE = re.compile(r'^voe?_.*_([a-z]{2})$', re.I)


def voice_code(name):
    """The actor code a voice line was saved with ('' = none)."""
    m = _VOICE_CODE.match(str(name or ''))
    c = m.group(1).lower() if m else ''
    return c if c in ADULT_VOICE_CODES or c in NOT_ADULT_VOICE_CODES else ''


def _check_voices(actor, warnings):
    """The actor's sounds without non-adult voice lines (left out), warning about other-gender voice lines."""
    sounds = actor.get('sounds') or []
    male = actor.get('body') == 'ym' if actor.get('body') else actor.get('gender') == 'MALE'
    keep = []
    for snd in sounds:
        c = voice_code(snd.get('name'))
        if c in NOT_ADULT_VOICE_CODES:
            msg = '\u2018%s\u2019 is not an adult voice line, so it was left out.' % snd.get('name')
            if msg not in warnings:
                warnings.append(msg)
            continue
        if c and (c[0] == 'm') != male:
            msg = "\u2018%s\u2019 is another gender's voice line; in the game it plays as written." % snd.get('name')
            if msg not in warnings:
                warnings.append(msg)
        keep.append(snd)
    return actor if len(keep) == len(sounds) else dict(actor, sounds=keep)


def _check_events(project, n_actors, warnings):
    """The baked moments that can go into the game: effects must be real, adult game effects (vfx.valid)."""
    events = [e for e in project.get('events') or [] if isinstance(e, dict)]
    if not events:
        return []
    out = []
    for e in events:
        if str(e.get('type', '')).upper() == 'EFFECT':
            name = str(e.get('effect_name') or '').strip()
            ok = False
            try:
                import vfx
                ok = vfx.valid(name)
            except Exception:
                ok = bool(name)          # no game effect list here: WickedWhims checks it in the game
            if not ok:
                msg = 'The effect \u2018%s\u2019 is not a game effect, so it was left out.' % name
                if msg not in warnings:
                    warnings.append(msg)
                continue
        out.append(e)
    return out


T_BONE = fnv32('transformBone')      # the bone every prop rig moves (b__ROOT__ -> transformBone -> _FX_)


def _prop_guid(prop):
    try:
        g = int(str(prop.get('guid')).strip())
    except (TypeError, ValueError, AttributeError):
        return None
    return g if 0 < g < (1 << 64) else None


def _prop_frames(vals, frames, size):
    """A prop's baked track, one value per frame (a short one keeps its last value); None when it is unusable."""
    out = []
    for v in (vals or [])[:frames]:
        if not isinstance(v, (list, tuple)) or len(v) != size:
            return None
        try:
            v = [float(c) for c in v]
        except (TypeError, ValueError):
            return None
        if any(math.isnan(c) or math.isinf(c) for c in v):
            return None
        out.append(v)
    if not out:
        return None
    return out + [out[-1]] * (frames - len(out))


def prop_resources(project, base, ticks, frames, hold, fps, warnings):
    """The prop clips of a baked animation (spec_bodies 10.2): one CLIP + clip header per prop that has a track,
    keying the prop rig's transformBone in the animation's space (the sims' space), the same length as the actors'
    clips. -> (resources, [{'id', 'guid', 'clip'}] for animation_props_list, [{'guid', 'name', 'source',
    'package'}] for the readme). A project without props gives ([], [], [])."""
    res, xml, info = [], [], []
    for prop in project.get('props') or []:
        if not isinstance(prop, dict):
            continue
        guid = _prop_guid(prop)
        tr = prop.get('track') if isinstance(prop.get('track'), dict) else None
        name = str(prop.get('name') or 'A prop')
        t = _prop_frames(tr.get('t'), frames, 3) if tr and guid else None
        r = _prop_frames(tr.get('r'), frames, 4) if tr and guid else None
        if t is None or r is None:
            msg = '‘%s’ has no movement to export, so it was left out.' % name
            if msg not in warnings:
                warnings.append(msg)
            continue
        source, package = prop.get('source'), None
        try:
            import objmesh
            found = objmesh.source_of(guid)
            if found:
                source = found
                if found == 'mods':
                    package = objmesh._where(objmesh.T_OBJD, guid)
            else:
                warnings.append('‘%s’ is not in the game or in your Mods folder, so WickedWhims will play the '
                                'animation without it.' % name)
        except Exception:
            pass                    # no game files here: WickedWhims finds the object in the game
        k = len(xml)
        pclip = '%s_%df_p%d' % (base, ticks, k + 1)
        chans = []
        for sub, vals, quat in ((1, t, False), (2, _continuous(r), True), (3, [[1.0, 1.0, 1.0]], False)):
            keys = [(0, list(vals[0]))] if _constant(vals) else [(i, list(v)) for i, v in enumerate(vals)]
            if hold and len(keys) > 1:
                keys.append((len(vals) - 1 + hold, list(vals[-1])))
            chans.append(encode_channel(T_BONE, sub, keys, quat))
        clip, header = write_clip(pclip, 'prop%d' % (k + 1), ticks, chans, source="Novulon's Wicked Animator",
                                  tick_length=1.0 / fps)
        inst = fnv64(pclip)
        res += [(T_CLIP, 0, inst, clip), (T_CLIP_HEADER, 0, inst, header)]
        xml.append({'id': k, 'guid': guid, 'clip': pclip})
        info.append({'guid': str(guid), 'name': name, 'source': source or 'game', 'package': package})
    return res, xml, info


def animation_resources(project, metas=None, present=None):
    """([(type, group, instance, bytes)], info) for one baked animation.

    Optional (missing = the old behaviour): project['events'] = baked moments (seconds, target = actor index), per
    actor 'cumAfter' ('AUTO' | 'NONE' | [layers]), and project['props'] = [{guid, name?, source?, track: {t: [[x, y,
    z] per frame], r: [[x, y, z, w] per frame]}}] (props held or placed: their own clips + animation_props_list)."""
    metas = metas if metas is not None else P.by_uid()
    name = (project.get('name') or '').strip() or 'My animation'
    author = (project.get('author') or '').strip() or 'Fit Studio'
    uid = project.get('uid')
    frames = max(1, int(project['frames']))
    fps = float(project.get('fps') or 30)
    category = project.get('category', 'TEASING')
    loops = int(project.get('loops', 10))
    hold = int(round(HOLD_SECONDS * fps)) if category == 'CLIMAX' and loops == 1 else 0
    ticks = frames + hold
    base = stage_name(author, name, uid)
    resources, actors_xml, sounds = [], [], []
    voices = False
    checks = []
    mine_res, mine_names = _own_sounds(project['actors'], checks)
    for k, actor in enumerate(project['actors']):
        actor = _check_voices(actor, checks)
        actor = _drop_missing_own(actor, mine_names)
        clip_name = '%s_%df_%d' % (base, ticks, k + 1)
        clip, header = write_clip(clip_name, 'x', ticks, actor_channels(actor, frames, hold=hold),
                                  source="Novulon's Wicked Animator", events=sound_events(actor, fps), tick_length=1.0 / fps)
        inst = fnv64(clip_name)
        resources.append((T_CLIP, 0, inst, clip))
        resources.append((T_CLIP_HEADER, 0, inst, header))
        voices = voices or any(s.get('kind') == 'voice' for s in actor.get('sounds') or [])
        sounds += [s['name'] for s in actor.get('sounds') or [] if not _is_own(s['name'])]
        gender = actor.get('gender') or 'BOTH'
        actors_xml.append({
            'clip': clip_name, 'gender': gender, 'naked': actor.get('naked'), 'body': actor.get('body'),
            'role': actor.get('role'), 'strapon': bool(actor.get('strapon')),
            'pref_gender': PREF_GENDER.get(actor.get('body')) if gender == 'BOTH' else None,
            'nude_feet': bool(actor.get('bareFeet')) or category == 'FOOTJOB',
            'visible_tongue': bool(actor.get('tongueUsed')),
            'animated_vagina': bool(actor.get('animatedVagina')) and gender != 'MALE',
            'invisible_teeth': bool(actor.get('invisibleTeeth')), 'cum_after': actor.get('cumAfter')})
    prop_res, props_xml, props_info = prop_resources(project, base, ticks, frames, hold, fps, checks)
    resources += prop_res + mine_res
    nxt, next_names, random_ok, warnings = _links(project, metas, present)
    tags = [t for t in (project.get('tags') or []) if t]
    if voices and 'CUSTOM_VOICE_SFX' not in tags:
        tags.append('CUSTOM_VOICE_SFX')
    anim = {'name': name, 'author': author, 'category': category, 'loops': loops, 'naked': project.get('naked', 'ALL'),
            'locations': project.get('locations') or ['FLOOR'], 'actors': actors_xml, 'tags': tags,
            'stage': base, 'next_stages': nxt, 'random': random_ok, 'act': project.get('act'),
            'negative_offset': hold / fps if hold else 0}
    if props_xml:
        anim['props'] = props_xml
    events = _check_events(project, len(actors_xml), checks)
    n_events = 0
    if events:
        anim['events'] = events
        anim['clip_seconds'] = ticks / fps
        ev_lines, ev_warnings = W.events_xml(events, len(actors_xml), ticks / fps)
        n_events = sum(1 for x in ev_lines if x.strip() == '<U>')
        checks += [w for w in ev_warnings if w not in checks]
    warnings = warnings + checks
    xml = W.snippet_xml(base, [anim]).encode('utf-8')
    resources.insert(0, (W.SNIPPET, 0, W.instance_id(base), xml))
    return resources, {'base': base, 'uid': uid, 'clips': [a['clip'] for a in actors_xml], 'sounds': sorted(set(sounds)),
                       'next': nxt, 'next_names': next_names, 'random': random_ok, 'name': name, 'author': author,
                       'category': category, 'locations': anim['locations'], 'genders': [a['gender'] for a in actors_xml],
                       'warnings': warnings, 'events': n_events, 'props': props_info,
                       'prop_clips': [p['clip'] for p in props_xml], 'own_sounds': sorted(mine_names)}


def _in_use(ex):
    return isinstance(ex, PermissionError) or getattr(ex, 'winerror', None) in (5, 32, 33)


def _write(path, resources):
    """Write the package through a temporary file. When the file can't be written (the game keeps loaded packages
    open), the temporary file is removed and a plain message is raised."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = W.build_package(resources)
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
        if _in_use(ex):
            raise RuntimeError('The Sims 4 is using "%s". Close the game, then try again.' % os.path.basename(path)) from None
        raise RuntimeError('Could not write "%s": %s' % (os.path.basename(path), ex.strerror or ex)) from None
    return len(data)


# ------------------------------------------------------------------ sounds
_idx_cache = {}


def _index(path):
    key = (path, os.path.getmtime(path))
    if key not in _idx_cache:
        _idx_cache[key] = read_index(path)
    return _idx_cache[key]


def _source_of(path):
    try:
        return 'mods' if os.path.commonpath([os.path.normcase(path), os.path.normcase(G.MODS_DIR)]) == os.path.normcase(G.MODS_DIR) else 'parked'
    except ValueError:
        return 'parked'


def _mod_packages():
    """Every package in Mods and Mods_parked except the blocked ones (adults only) and WickedWhims' own."""
    return [p for p in G.animation_packages() if not G.blocked_path(p) and 'TURBODRIVER_WickedWhims' not in p]


def _locate_sound(n, s):
    """(package path, index, sound entries) where sound n is NOW - the listed package when it still has it, else
    found again in Mods / Mods_parked (packs get moved between the two). None when it is nowhere."""
    h = fnv64(n)
    keys = (h, h | (1 << 63))
    listed = os.path.join(G.SIMS_DIR, s['package']) if s.get('package') else None

    def candidates():
        if listed:
            yield listed
        yield from (p for p in _mod_packages() if p != listed)     # only searched when the listed one misses
    for p in candidates():
        if not os.path.isfile(p) or G.blocked_path(p):
            continue
        try:
            idx = _index(p)
        except Exception:
            continue
        snd = [e for e in idx if e['type'] == T_SOUND and e['inst'] in keys]
        if snd:
            return p, idx, snd
    return None


def _audio_refs(data, local):
    """The audio clips a sound picks from: u32 count at byte 10, then that many u64 instances. When that doesn't
    match anything in its own package, any u64 in it that names audio there."""
    refs = set()
    try:
        cnt = struct.unpack_from('<I', data, 10)[0]
        if 0 < cnt < 64:
            refs = set(struct.unpack_from('<%dQ' % cnt, data, 14))
    except struct.error:
        pass
    if not refs & set(local):
        refs |= {struct.unpack_from('<Q', data, o)[0] for o in range(0, len(data) - 7)} & set(local)
    return refs


def _audio_elsewhere(refs, skip):
    """{ref: (package, entry)} for audio found in the other Mods / Mods_parked packages."""
    found = {}
    for p in _mod_packages():
        if p == skip:
            continue
        try:
            idx = _index(p)
        except Exception:
            continue
        for e in idx:
            if e['type'] == T_AUDIO and e['inst'] in refs and e['inst'] not in found:
                found[e['inst']] = (p, e)
        if len(found) == len(refs):
            break
    return found


_game_audio, _game_audio_lock = None, threading.Lock()


def _game_audio_packs():
    """audio instance -> '' (base game) or the pack folder that has it (EP15, GP04...). Made once, when needed."""
    global _game_audio
    with _game_audio_lock:
        if _game_audio is None:
            where = {}
            try:
                root = G.game_dir()
                paths = glob.glob(os.path.join(root, '**', 'Client*Build*.package'), recursive=True)
            except Exception:
                root, paths = '', []
            for p in paths:
                parts = os.path.relpath(p, root).split(os.sep)[:-1]
                pack = next((x.upper() for x in parts if re.match(r'^(EP|GP|SP|FP)\d+$', x, re.I)), '')
                try:
                    idx = read_index(p)
                except Exception:
                    continue
                for e in idx:
                    if e['type'] == T_AUDIO and (e['inst'] not in where or (where[e['inst']] and not pack)):
                        where[e['inst']] = pack
            _game_audio = where
        return _game_audio


def sound_kit(names, sources=('parked',)):
    """Sound resources (and the audio they play) for sounds that come from other mods.
    -> (resources, credits {package: [names]}, not_found [names], needs_pack {name: 'EP15'}).

    WickedWhims' own and the game's sounds are skipped. A sound is only packed and credited when the audio it plays
    is packed too (from its own package or another mod) or ships with the base game; audio that only a game pack has
    is noted in needs_pack; a sound whose audio is nowhere is listed as not found."""
    catalogue = {s['name']: s for s in G.sounds()}
    res, credits, missing, needs, seen = [], {}, [], {}, set()

    def add(t, e, path):
        key = (t, e['group'], e['inst'])
        if key not in seen:
            seen.add(key)
            res.append((t, e['group'], e['inst'], read_resource(path, e)))

    for n in names:
        s = catalogue.get(n)
        if not s:
            missing.append(n)
            continue
        if s['source'] not in ('mods', 'parked') or 'TURBODRIVER_WickedWhims' in (s.get('package') or ''):
            continue                 # the game's own sounds (and ones nobody has) play without packing
        hit = _locate_sound(n, s)
        if not hit:
            missing.append(n)
            continue
        path, idx, snd = hit
        if _source_of(path) not in sources:
            continue
        local = {e['inst']: e for e in idx if e['type'] == T_AUDIO}
        packed, pack_needed, from_pkgs = [], set(), {os.path.basename(path)}
        for e in snd:
            data = read_resource(path, e)
            refs = _audio_refs(data, local)
            here = refs & set(local)
            if here:
                packed.append((e, [(local[r], path) for r in here]))
                continue
            other = _audio_elsewhere(refs, path) if refs else {}
            if other:
                packed.append((e, [(ae, ap) for ap, ae in other.values()]))
                from_pkgs |= {os.path.basename(ap) for ap, _ in other.values()}
                continue
            game = _game_audio_packs() if refs else {}
            packs = {game[r] for r in refs if r in game}
            if '' in packs:
                packed.append((e, []))            # the audio ships with the base game: plays for everyone
            elif packs:
                packed.append((e, []))
                pack_needed |= packs
        if not packed:
            missing.append(n)
            continue
        for e, audio in packed:
            add(T_SOUND, e, path)
            for ae, ap in audio:
                add(T_AUDIO, ae, ap)
        for pkg in sorted(from_pkgs):
            credits.setdefault(pkg, []).append(n)
        if pack_needed:
            needs[n] = ', '.join(sorted(pack_needed))
    return res, credits, missing, needs


def _update_sound_kit(names):
    """Your own game: sounds from parked packs are copied into Mods\\FitStudio\\FitStudio_Sounds.package."""
    res, credits, _, _ = sound_kit(names, sources=('parked',))
    if not res:
        return None
    path = os.path.join(G.MODS_DIR, 'FitStudio', 'FitStudio_Sounds.package')
    have = {}
    if os.path.exists(path):
        for e in read_index(path):
            have[(e['type'], e['group'], e['inst'])] = read_resource(path, e)
    for t, g, i, d in res:
        have[(t, g, i)] = d
    _write(path, [(t, g, i, d) for (t, g, i), d in have.items()])
    return {'path': path, 'sounds': len({n for v in credits.values() for n in v})}


# ------------------------------------------------------------------ single animation into your game
def _retire_old(project, base):
    """The package this animation was sent as before (renamed since, or made by an older version without the uid
    tag) is moved out of Mods to saves\\FitStudio\\animator_replaced\\packages, so it never shows twice in the game.
    -> (moved file names, warnings)"""
    olds = []
    prev = P.exports().get(project.get('uid')) if project.get('uid') else None
    if prev:
        olds.append(prev)
    olds.append(_legacy_stage(project.get('author') or 'Fit Studio', project.get('name') or 'My animation'))
    moved, warnings = [], []
    for old in dict.fromkeys(olds):
        src = os.path.join(MY_ANIMATIONS, old + '.package')
        if old.lower() == base.lower() or not os.path.isfile(src):
            continue
        dst_dir = os.path.join(P.OLD, 'packages')
        try:
            os.makedirs(dst_dir, exist_ok=True)
            os.replace(src, os.path.join(dst_dir, '%s.%d.package' % (old, int(time.time()))))
            moved.append(old + '.package')
        except OSError as ex:
            warnings.append('The older copy "%s.package" is still in your Mods folder%s - it may show twice until it is '
                            'gone.' % (old, ' (the game is using it; close the game and send again)' if _in_use(ex) else ''))
    return moved, warnings


def export(project, present=None):
    resources, info = animation_resources(project, present=present)
    path = os.path.join(MY_ANIMATIONS, info['base'] + '.package')
    size = _write(path, resources)
    moved, warnings = _retire_old(project, info['base'])
    P.remember_export(info['uid'], info['base'])
    warnings = info['warnings'] + warnings
    try:
        kit = _update_sound_kit(info['sounds'])
    except Exception as ex:            # the animation is in; only the extra sounds failed
        kit = None
        warnings.append('The sounds from parked mods could not be copied: %s' % (str(ex) or repr(ex)))
    return {'path': path, 'package': info['base'] + '.package', 'clips': info['clips'], 'bytes': size,
            'next': info['next'], 'next_names': info['next_names'], 'random': info['random'], 'sound_kit': kit,
            'replaced': moved, 'warnings': warnings, 'own_sounds': len(info['own_sounds'])}


# ------------------------------------------------------------------ a mod to share
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$', re.I)


def _safe_file(name):
    """Folder and file name for a mod: letters, digits and a few signs, never '.', '..' or a Windows device name.
    When cleaning changed the title (another alphabet, signs), a short tag made from the title keeps two mods apart."""
    norm = ' '.join((name or '').split())
    clean = ' '.join(re.sub(r"[^A-Za-z0-9 _.()'-]+", '', norm).split()).strip(' .')[:80].strip(' .')
    if not clean:
        clean = 'My Animations'
    elif _RESERVED.match(clean):
        clean = 'My Animations ' + clean
    if norm and clean != norm:
        clean += ' %06x' % (fnv32(norm) & 0xFFFFFF)
    return clean


def bundle(req):
    """req: {name, author, animations: [baked project], include_sounds: bool, install: bool, progressions: [ids]}"""
    title = (req.get('name') or '').strip() or 'My Animations'
    author = (req.get('author') or '').strip()
    anims, done = [], set()
    for a in req.get('animations') or []:
        if a.get('uid') and a['uid'] in done:
            continue                    # the same animation ticked twice
        done.add(a.get('uid'))
        anims.append(a)
    if not anims:
        raise ValueError('Pick at least one animation.')
    metas = P.by_uid()
    present = {a.get('uid') for a in anims if a.get('uid')}
    resources, infos, sounds, warnings, bases = [], [], [], [], {}
    for a in anims:
        res, info = animation_resources(a, metas, present)
        other = bases.get(info['base'].lower())
        if other is not None:
            raise ValueError('"%s" and "%s" would get the same name in the game. Rename one of them, then export again.'
                             % (other, info['name']))
        bases[info['base'].lower()] = info['name']
        resources += res
        infos.append(info)
        sounds += info['sounds']
        warnings += info['warnings']
    credits, missing, needs = {}, [], {}
    if req.get('include_sounds', True):
        kit, credits, missing, needs = sound_kit(sorted(set(sounds)), sources=('mods', 'parked'))
        resources += kit
    # one copy of each resource key (sounds shared by several animations)
    uniq = {}
    for t, g, i, d in resources:
        uniq[(t, g, i)] = d
    resources = [(t, g, i, d) for (t, g, i), d in uniq.items()]

    fname = _safe_file(title)
    folder = os.path.join(EXPORTS, fname)
    root = os.path.realpath(EXPORTS)
    if os.path.commonpath([os.path.realpath(folder), root]) != root or os.path.realpath(folder) == root:
        raise ValueError('Pick another name for the mod.')
    pkg = os.path.join(folder, fname + '.package')
    size = _write(pkg, resources)
    progs = [g for g in P.progressions() if g['id'] in (req.get('progressions') or []) or (g['steps'] and all(s in present for s in g['steps']))]
    readme = _readme(title, author, fname, infos, progs, metas, credits, missing, needs)
    with open(os.path.join(folder, 'README.txt'), 'w', encoding='utf-8') as f:
        f.write(readme)
    zpath = os.path.join(EXPORTS, fname + '.zip')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(pkg, fname + '.package')
        z.writestr('README.txt', readme)
    installed = []
    if req.get('install'):
        for a in anims:
            r = export(a, present=present)
            installed.append(r['path'])
            warnings += [w for w in r['warnings'] if w not in warnings]
    return {'folder': folder, 'package': pkg, 'zip': zpath, 'bytes': size, 'animations': len(infos),
            'progressions': [g['name'] for g in progs], 'sounds_packed': len({n for v in credits.values() for n in v}),
            'credits': credits, 'missing_sounds': missing, 'sounds_need_pack': needs, 'installed': installed,
            'own_sounds': len({n for i in infos for n in i.get('own_sounds') or []}),
            'warnings': warnings}


def _prop_needs(infos):
    """' Also the custom props: Phone (from Some_Props.package), ...' for props from the Mods folder (custom content
    everyone who plays the animations needs too), '' when there are none."""
    seen, out = set(), []
    for i in infos:
        for p in i.get('props') or []:
            if p.get('source') != 'mods' or p.get('guid') in seen:
                continue
            seen.add(p.get('guid'))
            pkg = os.path.basename(p.get('package') or '')
            out.append('%s%s' % (p.get('name') or 'a prop', ' (from %s)' % pkg if pkg else ''))
    return (' Also the custom props: ' + ', '.join(out) + '.') if out else ''


def _readme(title, author, fname, infos, progs, metas, credits, missing, needs=None):
    nice = lambda s: s.replace('_', ' ').title()
    lines = [f'{title}' + (f' by {author}' if author else ''), '=' * 60, '',
             "WickedWhims animations made with Novulon's Wicked Animator.", '',
             'NEEDS: WickedWhims by TURBODRIVER (https://wickedwhimsmod.com).' + _prop_needs(infos), '',
             'INSTALL', '  1. Put "%s.package" in Documents\\Electronic Arts\\The Sims 4\\Mods (a sub-folder is fine).' % fname,
             '  2. Make sure "Enable Custom Content and Mods" is on in the game options.',
             '  3. Start the game. The animations show up in WickedWhims\' animation picker.', '',
             'ANIMATIONS (%d)' % len(infos)]
    for i in infos:
        lines.append(f"  - {i['name']} by {i['author']} - {nice(i['category'])} - {', '.join(nice(l) for l in i['locations'])} - {len(i['clips'])} sims ({', '.join(g.lower() for g in i['genders'])})")
    if progs:
        lines += ['', 'PROGRESSIONS']
        for g in progs:
            steps = [metas.get(s, {}).get('name', '?') for s in g['steps']]
            lines.append(f"  - {g['name']}: " + ' -> '.join(steps) + (' -> (back to the start)' if g.get('repeat') else ''))
        lines += ['  Start any animation of a progression and WickedWhims moves on to the next one by itself',
                  '  (WickedWhims > Sex Settings > Sex Progression: "Full" (default) or "Stages Only").',
                  '  The later steps are not picked at random - they are reached through the chain.',
                  '  Animations that are not in a progression move on to a random animation, as usual.']
    if credits:
        lines += ['', 'SOUNDS PACKED INSIDE (credit to their creators)']
        for pkg, names in credits.items():
            lines.append(f"  - from {pkg}: {', '.join(sorted(names))}")
    own = sorted({n for i in infos for n in i.get('own_sounds') or []})
    if own:
        lines += ['', "THE CREATOR'S OWN SOUNDS PACKED INSIDE: " + ', '.join(own)]
    if needs:
        lines += ['', 'SOUNDS THAT NEED A GAME PACK: ' + ', '.join(f'{n} ({p})' for n, p in sorted(needs.items()))]
    if missing:
        lines += ['', 'SOUNDS THAT NEED THEIR OWN MOD: ' + ', '.join(sorted(missing))]
    lines += ['', 'Updating: replace the old .package with the new one. No cheat is needed afterwards.',
              '', 'Made on %s.' % datetime.date.today().isoformat()]
    return '\n'.join(lines) + '\n'

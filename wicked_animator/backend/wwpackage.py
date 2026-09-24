"""Write a WickedWhims animation package - the same XML snippet a hand-made WickedWhims animation
uses (class WickedWoohooAnimationPackage), in a plain uncompressed .package file.

Nothing here touches the game, so it is tested offline.
"""
import re, struct
from xml.sax.saxutils import escape

SNIPPET = 0x7DF2169C
CATEGORIES = ('TEASING', 'HANDJOB', 'FOOTJOB', 'ORALJOB', 'VAGINAL', 'ANAL', 'CLIMAX')
GENDERS = ('FEMALE', 'MALE', 'BOTH')


def fnv64(text):
    h = 0xCBF29CE484222325
    for b in text.lower().encode('utf-8'):
        h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        h ^= b
    return h


def instance_id(name):
    return fnv64(name) | 0x8000000000000000   # high bit: custom content, never an EA id


def safe_name(text):
    s = re.sub(r'[^A-Za-z0-9]+', '_', text).strip('_')
    return s[:60] or 'Animation'


def _name_at(data, off):
    if off + 4 > len(data):
        return None
    n = struct.unpack_from('<i', data, off)[0]
    if 1 <= n <= 256 and off + 4 + n <= len(data):
        raw = data[off + 4:off + 4 + n]
        if raw[0] != 32 and all(32 <= c < 127 for c in raw):
            return raw.decode('ascii')
    return None


def clip_name_from_header(data):
    """A clip header (resource type 0xBC4A5044) holds the clip's name as an int32 length + ASCII,
    at byte 56 (after version, flags, duration, two 16-byte blocks and three hashes)."""
    data = bytes(data)
    name = _name_at(data, 56)
    if name:
        return name
    for off in range(8, min(len(data) - 4, 256)):
        name = _name_at(data, off)
        if name and len(name) >= 3:
            return name
    return None


def _t(name, value, indent):
    return '%s<T n="%s">%s</T>' % (' ' * indent, name, escape(str(value)))


# where the giver's cum lands on the receiver, by act (WickedWhims v185 cum layer names)
CUM_LAYERS = {'VAGINAL': 'VAGINA', 'ANAL': 'BUTT', 'ORALJOB': 'FACE', 'HANDJOB': 'CHEST', 'FOOTJOB': 'FEET'}
CUM_INSIDE_ACTS = ('VAGINAL', 'ANAL', 'ORALJOB')
ROLES = ('giver', 'receiver', 'both')


def has_penis(actor):
    """A male body or a female body with WickedWhims' penis (no body given: judged by the slot's gender)."""
    body = actor.get('body')
    return body in ('ym', 'yf_futa') if body else actor.get('gender') == 'MALE'


def role_of(actor):
    """'giver' | 'receiver' | 'both'. Without a choice from the author: sims with a penis (or a MALE slot) give."""
    r = actor.get('role')
    if r in ROLES:
        return r
    return 'giver' if has_penis(actor) or actor.get('gender') == 'MALE' else 'receiver'


def interaction_pairs(actors):
    """[(from, to, main)] - who acts on whom. In WickedWhims an actor's interactions are what it does TO the
    receiving actor (used for orientation filters, satisfaction and cum):
    - main pairs go from every giver to every receiver ('both' is on either side, e.g. a 69);
    - each receiver also gets a plain pair back to its giver, like most creator animations (no cum from it);
    - sims with the same role never act on each other, so an FFM threesome is not taken for a lesbian act.
    When nobody gives or nobody receives (two women, two men), the first sim acts on the others."""
    roles = [role_of(a) for a in actors]
    givers = [i for i, r in enumerate(roles) if r in ('giver', 'both')]
    takers = [i for i, r in enumerate(roles) if r in ('receiver', 'both')]
    main = [(g, t) for g in givers for t in takers if g != t]
    if not main and len(actors) > 1:
        main = [(0, t) for t in range(1, len(actors))]
    pairs = [(g, t, True) for g, t in main]
    have = set(main)
    for g, t in main:
        if (t, g) not in have:
            have.add((t, g))
            pairs.append((t, g, False))
    return pairs


# ------------------------------------------------------------------ moments (WickedWhims animation_events_list)
EVENT_TYPES = ('EFFECT', 'CUM', 'UNDRESS', 'REMOVE_CONDOM')
CUM_TYPES = ('FACE', 'CHEST', 'BELLY', 'UPPER_BACK', 'LOWER_BACK', 'VAGINA', 'BUTT', 'FEET')
# creator spellings WickedWhims does not read the way they meant: BACK is an alias of UPPER_BACK only; FOOT is invalid
CUM_ALIASES = {'BACK': 'UPPER_BACK', 'FOOT': 'FEET'}
UNDRESS_TYPES = ('TOP', 'TOP_UNDERWEAR', 'BOTTOM', 'BOTTOM_UNDERWEAR', 'SHOES', 'ALL', 'FORCE_ALL')
# not rig bones (WickedWhims' remap table for them is never used, so the effect would play at nothing)
BAD_JOINTS = {'b__penis_tip01': 'b__Penis_Tip', 'b__penis_tip02': 'b__Penis_Tip', 'b__penis_tip03': 'b__Penis_Tip',
              'b__tounge__4': 'b__Tounge__3'}


def cum_type(name):
    """A cum layer name WickedWhims accepts (aliases fixed), or None."""
    n = str(name or '').strip().upper()
    n = CUM_ALIASES.get(n, n)
    return n if n in CUM_TYPES else None


def _sec(x):
    """Seconds as WickedWhims reads them: '%.4f' without trailing zeros, always a dot."""
    s = ('%.4f' % max(0.0, float(x))).rstrip('0').rstrip('.')
    return s or '0'


def events_xml(events, n_actors, clip_seconds, indent=6):
    """Baked moments [{type, start, end, target, cum_layer_type, cum_layer_level, naked_type, effect_name,
    effect_joint_name, skip_with_condom}] (seconds; target = actor index) -> (XML lines, warnings).

    Sorted by start, then type. A moment that WickedWhims would drop as invalid (no effect name or joint, an unknown
    cum layer or naked type, a target that is not an actor) is left out with a warning. Start and end are clamped to
    the clip, end >= start. The dont_run_if block ('skip when the target wears a condom') goes last."""
    t = lambda name, value, ind: '%s<T n="%s">%s</T>' % (' ' * ind, name, escape(str(value)))
    try:
        clip_seconds = max(0.0, float(clip_seconds))
    except (TypeError, ValueError):
        clip_seconds = 0.0

    def start_of(e):
        try:
            return float(e.get('start') or 0)
        except (TypeError, ValueError):
            return 0.0
    out, warn = [], []
    for e in sorted([e for e in events or [] if isinstance(e, dict)], key=lambda e: (start_of(e), str(e.get('type', '')))):
        typ = str(e.get('type', '')).strip().upper()
        tgt = e.get('target')
        if typ not in EVENT_TYPES:
            continue                       # notes and unknown types are never written
        if isinstance(tgt, bool) or not isinstance(tgt, int) or not 0 <= tgt < n_actors:
            warn.append('A %s moment has no sim to happen to, so it was left out.' % typ.lower().replace('_', ' '))
            continue
        start = min(start_of(e), clip_seconds)
        body = [t('event_type', typ, indent + 4), t('event_start_timecode', _sec(start), indent + 4)]
        if typ == 'EFFECT':
            name = str(e.get('effect_name') or '').strip()
            joint = str(e.get('effect_joint_name') or '').strip()
            joint = BAD_JOINTS.get(joint.lower(), joint)
            if not name or not joint:
                warn.append('An effect moment needs an effect and a body part, so it was left out.')
                continue
            try:
                end = float(e.get('end')) if e.get('end') is not None else start + 1.0
            except (TypeError, ValueError):
                end = start + 1.0
            end = min(max(start, end), clip_seconds)
            body.append(t('event_end_timecode', _sec(end), indent + 4))
        body.append(t('event_target', 'a%d' % tgt, indent + 4))
        if typ == 'EFFECT':
            body += [t('effect_name', name, indent + 4), t('effect_joint_name', joint, indent + 4)]
        elif typ == 'CUM':
            ct = cum_type(e.get('cum_layer_type'))
            if not ct:
                warn.append('A cum moment needs a body part WickedWhims knows, so it was left out.')
                continue
            try:
                level = int(e.get('cum_layer_level') or 1)
            except (TypeError, ValueError):
                level = 1
            body += [t('cum_layer_type', ct, indent + 4), t('cum_layer_level', max(1, min(3, level)), indent + 4)]
        elif typ == 'UNDRESS':
            nt = str(e.get('naked_type') or '').strip().upper()
            if nt not in UNDRESS_TYPES:
                warn.append('An undress moment needs to say what comes off, so it was left out.')
                continue
            body.append(t('naked_type', nt, indent + 4))
        if e.get('skip_with_condom'):
            body += [' ' * (indent + 4) + '<U n="dont_run_if">', t('actor_has_condom', 1, indent + 6),
                     ' ' * (indent + 4) + '</U>']
        out += [' ' * (indent + 2) + '<U>'] + body + [' ' * (indent + 2) + '</U>']
    if not out:
        return [], warn
    return [' ' * indent + '<L n="animation_events_list">'] + out + [' ' * indent + '</L>'], warn


def cum_layers_for(receiver, act, cum, main):
    """What receiving_actor_cum_layers says for one pair (None = not written), from the receiver's cum_after:
    'NONE' -> DISABLED; a list -> those layers (main pairs); 'AUTO' or nothing -> by the act, like always."""
    after = receiver.get('cum_after') if isinstance(receiver, dict) else None
    if after == 'NONE':
        return 'DISABLED'
    if isinstance(after, (list, tuple)):
        layers = list(dict.fromkeys(c for c in (cum_type(x) for x in after) if c))
        if layers:
            return ', '.join(layers) if main else None
    return CUM_LAYERS[act] if cum and CUM_LAYERS.get(act) else None


def allow_strapon(actor):
    """Only where a strap-on belongs: a slot the author marked for one, or a giving MALE slot (when a sim without a
    penis plays it). Never on a receiving woman - with the player's strap-on set to Auto she would wear one."""
    if actor.get('strapon'):
        return True
    return actor.get('gender') == 'MALE' and role_of(actor) != 'receiver'


def animation_xml(anim):
    """anim: {name, author, category, loops, locations: [names], actors: [{clip, gender, ...}], naked}

    Per actor (all optional): role, body, strapon, nude_feet, visible_tongue, pref_gender, animated_vagina,
    invisible_teeth, cum_after ('AUTO' | 'NONE' | [layers]). Optional on the animation: events (baked moments),
    clip_seconds and props ([{id, guid, clip, type?}] -> animation_props_list). Laid out exactly like WickedWhims' own animation XML template (every list and item is a <T>; the
    moments list is an <L> of <U> items, as WickedWhims' template writes it)."""
    lines = []
    lines.append(_t('animation_raw_display_name', anim['name'], 6))
    lines.append(_t('animation_author', anim['author'], 6))
    lines.append(_t('animation_locations', ', '.join(anim['locations']), 6))
    lines.append(_t('animation_category', anim['category'], 6))
    if anim.get('tags'):
        lines.append(_t('animation_tags', ', '.join(anim['tags']), 6))
    lines.append(_t('animation_loops', int(anim.get('loops', 10)), 6))
    if anim.get('negative_offset'):
        # the clips hold their last pose this much longer; WickedWhims ends the animation that much sooner, so the
        # clip never restarts for a split second before the next animation
        lines.append(_t('animation_negative_duration_offset', '%g' % round(float(anim['negative_offset']), 4), 6))
    if anim.get('stage'):
        lines.append(_t('animation_stage_name', anim['stage'], 6))
    if anim.get('next_stages'):
        lines.append(_t('animation_next_stages', ', '.join(anim['next_stages']), 6))
    if anim.get('random') is False:
        # a later step of a progression: only reached through the chain, never picked at random
        lines.append(_t('animation_allowed_for_random', 0, 6))
    if int(anim.get('version', 1)) > 1:
        lines.append(_t('animation_version', int(anim['version']), 6))
    lines.append('      <T n="animation_actors_list">')
    actors = anim['actors']
    # the act the receiving sim gets (a climax animation still has to name the act, or WickedWhims drops it)
    act = anim['category'] if anim['category'] != 'CLIMAX' else (anim.get('act') or 'VAGINAL')
    pairs = interaction_pairs(actors)
    for i, actor in enumerate(actors):
        role = role_of(actor)
        lines.append('        <T>')
        lines.append(_t('actor_id', i, 10))
        lines.append(_t('animation_clip_name', actor['clip'], 10))
        lines.append(_t('animation_type', anim['category'], 10))
        lines.append(_t('animation_genders', actor['gender'], 10))
        if actor['gender'] == 'BOTH' and actor.get('pref_gender') in ('MALE', 'FEMALE'):
            lines.append(_t('animation_pref_gender', actor['pref_gender'], 10))
        lines.append(_t('animation_naked_type', actor.get('naked') or anim.get('naked', 'ALL'), 10))
        if actor.get('nude_feet'):
            lines.append(_t('animation_force_nude_feet', 1, 10))
        if allow_strapon(actor):
            lines.append(_t('animation_allow_strapon', 1, 10))
        if actor.get('animated_vagina'):
            lines.append(_t('animation_has_animated_vagina', 1, 10))
        if actor.get('visible_tongue'):
            # read by older WickedWhims versions (v185 puts the tongue on every sim during sex)
            lines.append(_t('animation_has_visible_tongue', 1, 10))
        if actor.get('invisible_teeth'):
            lines.append(_t('animation_has_invisible_teeth', 1, 10))
        tags = (['ROLE_GIVER'] if role in ('giver', 'both') else []) + (['ROLE_RECEIVER'] if role in ('receiver', 'both') else [])
        lines.append(_t('animation_actor_tags', ', '.join(tags), 10))
        mine = [(t, main) for f, t, main in pairs if f == i]
        if mine:
            # what this sim does to the others (WickedWhims uses it for orientation, satisfaction and cum)
            lines.append('          <T n="actor_interactions">')
            for j, main in mine:
                cum = main and has_penis(actor)
                lines.append('            <T>')
                lines.append(_t('receiving_actor_id', j, 14))
                lines.append(_t('receiving_actor_category', act, 14))
                layers = cum_layers_for(actors[j], act, cum, main)
                if layers:
                    lines.append(_t('receiving_actor_cum_layers', layers, 14))
                lines.append(_t('receiving_actor_cum_inside', 1 if cum and act in CUM_INSIDE_ACTS else 0, 14))
                lines.append('            </T>')
            lines.append('          </T>')
        lines.append('        </T>')
    lines.append('      </T>')
    if anim.get('props'):
        # props held or placed during the animation (spec_bodies 10.2): each plays its own clip on its transformBone.
        # WickedWhims reads this list as an <L> or a <T>; creators' packages use both.
        lines.append('      <T n="animation_props_list">')
        for p in anim['props']:
            lines.append('        <T>')
            lines.append(_t('prop_id', int(p['id']), 10))
            lines.append(_t('prop_type', p.get('type') or 'BASIC', 10))
            lines.append(_t('prop_guids', int(p['guid']), 10))
            lines.append(_t('prop_animation_clip_name', p['clip'], 10))
            lines.append('        </T>')
        lines.append('      </T>')
    if anim.get('events'):
        # moments (cum, undress, condom, effects) at animation level, after the actors (F2)
        ev, _ = events_xml(anim['events'], len(actors), anim.get('clip_seconds') or 0)
        lines += ev
    return chr(10).join(lines)


def snippet_xml(package_name, animations):
    body = '\n'.join('    <T>\n%s\n    </T>' % animation_xml(a) for a in animations)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<I c="WickedWoohooAnimationPackage" i="snippet" m="wickedwoohoo.utils_snippets" n="%s" s="%d">\n'
            "  <!-- made with Novulon's Wicked Animator -->\n"
            '  <T n="wickedwoohoo_animations">1</T>\n'
            '  <L n="animations_list">\n%s\n  </L>\n'
            '</I>\n') % (escape(package_name), instance_id(package_name), body)


def build_package(resources):
    """resources: [(type, group, instance, bytes)] -> DBPF 2.1 .package bytes (uncompressed)."""
    header = bytearray(96)
    header[0:4] = b'DBPF'
    struct.pack_into('<II', header, 4, 2, 1)
    blobs, index = bytearray(), bytearray(struct.pack('<I', 0))
    pos = 96
    for rtype, group, inst, data in resources:
        index += struct.pack('<IIIIIIIHH', rtype, group, inst >> 32, inst & 0xFFFFFFFF,
                             pos, len(data) | 0x80000000, len(data), 0, 1)
        blobs += data
        pos += len(data)
    struct.pack_into('<I', header, 36, len(resources))
    struct.pack_into('<I', header, 44, len(index))
    struct.pack_into('<I', header, 60, 3)
    struct.pack_into('<I', header, 64, pos)
    return bytes(header) + bytes(blobs) + bytes(index)


def animation_package(anim):
    """(file name, package bytes) for one animation."""
    name = 'FitStudio_' + safe_name(anim['author']) + '_' + safe_name(anim['name'])
    xml = snippet_xml(name, [anim]).encode('utf-8')
    return name + '.package', build_package([(SNIPPET, 0, instance_id(name), xml)])

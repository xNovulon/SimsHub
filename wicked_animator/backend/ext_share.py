"""Server routes for pose packs and the promo kit (plan 2.7; names reserved for R2-6).

    GET  /api/posepack       what a pose pack is made of and what the adults-only lock refuses (the app shows it)
    POST /api/posepack       {name, author, description, uid, install, meta, poses: [...], icon} -> writes the pack
                             ({check: true} only runs the lock: {ok, reasons, message})
    POST /api/promo_save     {name, author, baked?, files: [{name, data (base64)}], text?, text_only?}
                             -> everything in one folder next to the exports, with "Post text.txt"

Both write only on a click in the app. WICKED_EXPORTS_DIR (tests only) points every write of this module into a
test folder: the exports go there, and "also put it in my game" goes to <that folder>\\Mods.
"""
import base64, binascii, os, re

import exporter as X
import gamedata as G
import posepack

NICE_PLACES = {'CHAIR_LIVING': 'Armchair', 'CHAIR_DINING': 'Dining chair', 'TABLE_DINING_2X': 'Dining table'}


def _exports():
    return os.environ.get('WICKED_EXPORTS_DIR') or X.EXPORTS


def _mods():
    env = os.environ.get('WICKED_EXPORTS_DIR')
    return os.path.join(env, 'Mods') if env else G.MODS_DIR


def _b64(s, what):
    try:
        return base64.b64decode(str(s or '').split(',', 1)[-1], validate=False)
    except (binascii.Error, ValueError):
        raise ValueError('%s came through broken - try again.' % what) from None


def _pic(p, what='A pose picture'):
    if not isinstance(p, dict) or not p.get('rgba'):
        return None
    return {'w': int(p.get('w') or 0), 'h': int(p.get('h') or 0), 'rgba': _b64(p['rgba'], what)}


# ------------------------------------------------------------------ pose packs
def _posepack_info(q):
    return {'icon': posepack.ICON, 'languages': len(posepack.LOCALES), 'ticks': posepack.POSE_TICKS,
            'explicit_kinds': sorted(posepack.EXPLICIT_KINDS), 'explicit_tags': sorted(posepack.EXPLICIT_TAGS),
            'genital': sorted(posepack.GENITAL), 'max_poses': posepack.MAX_POSES,
            'layout': 'Sims 4 Studio pose pack (PosePackInstance, poseplayer)',
            'exports': _exports(), 'test_folder': bool(os.environ.get('WICKED_EXPORTS_DIR'))}


def _posepack(body, q):
    if not isinstance(body, dict):
        raise ValueError('Send the pose pack as a JSON object.')
    rig = None
    try:
        rig = G.rig('au')
    except Exception:
        rig = None
    if body.get('check'):
        reasons = posepack.lock(body.get('meta') or {}, body.get('poses') or [], rig)
        return {'ok': not reasons, 'reasons': reasons, 'message': posepack.lock_message(reasons) if reasons else ''}
    req = dict(body)
    req['icon'] = _pic(body.get('icon'), 'The pack picture')
    req['poses'] = [dict(p, icon=_pic(p.get('icon'))) for p in body.get('poses') or [] if isinstance(p, dict)]
    return posepack.write(req, _exports(), _mods(), rig)


# ------------------------------------------------------------------ promo kit
def _nice(s):
    s = str(s or '')
    return NICE_PLACES.get(s) or s.replace('_', ' ').lower().capitalize()


def credits_for(baked):
    """{package: [sounds]} for the sounds from other mods - the same credit the bundle README gives."""
    names = sorted({s.get('name') for a in (baked or {}).get('actors') or [] for s in a.get('sounds') or [] if s.get('name')})
    if not names:
        return {}
    try:
        catalogue = {s['name']: s for s in G.sounds()}
    except Exception:
        return {}
    out = {}
    for n in names:
        s = catalogue.get(n)
        if not s or s.get('source') not in ('mods', 'parked') or 'TURBODRIVER_WickedWhims' in (s.get('package') or ''):
            continue
        pkg = os.path.basename(s.get('package') or '') or 'another mod'
        if G.blocked_path(pkg):
            continue
        out.setdefault(pkg, []).append(n)
    return out


def post_text(baked, credits=None):
    """The text to post with the promo kit: name, acts, places, sims, needed mods and credits (from what the bundle
    README says about an animation)."""
    b = baked or {}
    name = (b.get('name') or 'My animation').strip()
    author = (b.get('author') or '').strip()
    kinds = {'TEASING': 'Teasing', 'HANDJOB': 'Handjob', 'FOOTJOB': 'Footjob', 'ORALJOB': 'Oral', 'VAGINAL': 'Vaginal',
             'ANAL': 'Anal', 'CLIMAX': 'Climax'}
    acts = [kinds.get(b.get('category'), _nice(b.get('category')))] if b.get('category') else []
    acts += [_nice(t) for t in b.get('tags') or [] if t and t != 'CUSTOM_VOICE_SFX' and _nice(t) not in acts]
    places = [_nice(x) for x in b.get('locations') or []] or ['Floor']
    actors = b.get('actors') or []
    genders = [str(a.get('gender') or 'BOTH').lower().replace('both', 'any') for a in actors]
    credits = credits if credits is not None else credits_for(b)
    lines = ['"%s"%s - a new WickedWhims animation' % (name, ' by ' + author if author else ''), '',
             'Acts: ' + (', '.join(acts) or 'Teasing'),
             'Places: ' + ', '.join(places),
             'Sims: %d%s' % (len(actors), ' (' + ', '.join(genders) + ')' if genders else ''),
             'Needs: WickedWhims by TURBODRIVER']
    if b.get('loops') == 1:
        lines.append('Plays once, then moves on')
    lines += ['', 'Credits:', '  Animation by ' + (author or 'me')]
    for pkg, snd in sorted(credits.items()):
        lines.append('  Sounds from %s (credit to their creators): %s' % (pkg, ', '.join(sorted(snd)[:6]) + (' ...' if len(snd) > 6 else '')))
    lines += ["  Made with Novulon's Wicked Animator", '',
              '18+ only. #TheSims4 #WickedWhims #Sims4Animations #TS4Mods']
    return '\n'.join(lines) + '\n'


_FILE = re.compile(r'^[A-Za-z0-9 _().,+&\'-]{1,80}\.(gif|png|webm|jpg|txt)$')


def _promo_save(body, q):
    if not isinstance(body, dict):
        raise ValueError('Send the promo kit as a JSON object.')
    baked = body.get('baked') if isinstance(body.get('baked'), dict) else {}
    name = ' '.join(str(body.get('name') or baked.get('name') or 'My animation').split())[:80]
    author = ' '.join(str(body.get('author') or baked.get('author') or '').split())[:40]
    text = post_text(dict(baked, name=name, author=author))
    if body.get('text_only'):
        return {'post_text': text}
    files = [f for f in body.get('files') or [] if isinstance(f, dict)]
    if not files:
        raise ValueError('Nothing to save - make the promo kit first.')
    exports = _exports()
    folder = os.path.join(exports, X._safe_file(name + (' by ' + author if author else '')) + ' - Promo kit')
    root = os.path.realpath(exports)
    if os.path.commonpath([os.path.realpath(folder), root]) != root or os.path.realpath(folder) == root:
        raise ValueError('Pick another name for the animation.')
    os.makedirs(folder, exist_ok=True)
    saved, total = [], 0
    for f in files:
        fn = os.path.basename(str(f.get('name') or ''))
        if not _FILE.match(fn):
            raise ValueError('"%s" is not a file name the promo kit makes.' % fn[:60])
        data = _b64(f.get('data'), fn)
        path = os.path.join(folder, fn)
        with open(path + '.tmp', 'wb') as out:
            out.write(data)
        os.replace(path + '.tmp', path)
        saved.append({'name': fn, 'path': path, 'bytes': len(data)})
        total += len(data)
    with open(os.path.join(folder, 'Post text.txt'), 'w', encoding='utf-8') as out:
        out.write(text)
    saved.append({'name': 'Post text.txt', 'path': os.path.join(folder, 'Post text.txt'), 'bytes': len(text.encode('utf-8'))})
    return {'folder': folder, 'files': saved, 'bytes': total, 'post_text': text}


GET = {'posepack': _posepack_info}
POST = {'posepack': _posepack, 'promo_save': _promo_save}

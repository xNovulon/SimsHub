"""Non-mod fixes for lag and slow loads: graphics rules, Options.ini, caches and a memory check.

What the research found (research/research_results.json 'settings' and 'lagdrivers', with the
skeptic's corrections) and what this module does about it:

1. Graphics override. ConfigOverride\\GraphicsRules.sgr replaces the game's own rules file
   (E:\\The Sims 4\\Game\\Bin\\GraphicsRules.sgr) completely; Config.log proves which one was parsed.
   The user's file is Simp4Sims "SGR Full" (19-08-2021): Sim LOD switching off (3000 m), object LOD
   bias 0, small-object culling 9999 instead of 200, far clip 9999, shadow map 5120, FSAA 512.
   MySetters.sgr / SimpsSetters.sgr next to it are never loaded (only the 2023 "Setters" version of
   GraphicsRules.sgr includes them). graphics_status() runs the rules (settings_sgr) for the player's
   own option levels and lists the differences from stock in plain words; graphics_use_stock()
   quarantines the override; graphics_use_preset() installs the Setters version with one preset from
   "Simps_GraphicsRules_Setters\\00 MySetter Presets" (Simp's instructions: copy GraphicsRules.sgr,
   SimpsSetters.sgr and ONE preset's MySetters.sgr into ConfigOverride - "CHOOSE ONLY ONE").
   Note: evaluated, the "Ultimate Performance" preset still keeps Sims at full detail out to 9000 m and
   sets ObjectSizeCullFactor to -1 (its "Pixelated Bread Shop" switch); only stock rules bring back
   the game's own Sim LOD and culling. Nothing about FPS was measured in game.
   The user wants "graphics at highest but no lag", so the default fix is graphics_use_tuned(): it installs
   'SpeedKit Max Quality' = the user's SGR Full file with ONLY its lag-causing values capped at sane high-end
   values (Sim LOD 2x stock, Sim textures 2048/2048/1024/512, stock culling / object LOD bias / far clip,
   FSAA 8, shadow map 4096, mirror reflections 2x stock, terrain LOD boost 2 at Ultra/Very High), as a
   minimal textual patch that the rules reader checks line by line; Options.ini stays at Ultra.
2. Options.ini is at Ultra+ (simquality 4, uncompressed Sim textures, lighting 4, reflections 3,
   edge smoothing 3, frame limit 240 with vsync off, fullscreen=1 AND windowedfullscreen=1).
   options_apply() rewrites only the listed keys, every other byte stays the same. The game rewrites
   Options.ini when it exits, so this refuses while TS4_x64.exe runs.
3. Caches (Crinrict's list, confirmed by the skeptic): delete localthumbcache after CC changes;
   localsimtexturecache, avatarcache, cachestr and onlinethumbnailcache are optional. None of them
   makes startup faster. caches_clean() quarantines (never deletes) and never touches saves, Tray,
   Options.ini, UserSetting.ini, accountDataDB, notify.glob, content or ConfigOverride.
4. Memory: 15.7 GB RAM, 306-559 MB free at recent game starts, Chrome alone 11.7 GB private, a 60 GB
   page file on a C: drive with 61 GB free. preflight() reports this and names what to close. It
   never kills anything.

Every change goes through a Journal (speedkit.journal) and can be undone with restore(journal_id).
All apply functions default to dry_run=True and return a plan.
"""
import ctypes, json, os, re, shutil, subprocess, sys, time

from .journal import Journal, JournalError, _fingerprint, file_digest, list_journals, undo
from .library import SIMS, game_running
from . import settings_sgr

GAME_DIR = r'E:\The Sims 4'
GAME_BIN = os.path.join(GAME_DIR, 'Game', 'Bin')
GAME_EXE = os.path.join(GAME_BIN, 'TS4_x64.exe')
SETTERS_DIR = 'Simps_GraphicsRules_Setters'          # where the user keeps Simp4Sims' 2023 download
PRESETS_DIR = '00 MySetter Presets'
SETTER_FILES = ('GraphicsRules.sgr', 'SimpsSetters.sgr', 'MySetters.sgr')


def _home(sims, home):
    return home or os.path.join(sims, 'SpeedKit')


def _open_journal(kind, note, sims, home, check_game):
    """A Journal whose id is not taken yet (ids have one-second resolution)."""
    home = _home(sims, home)
    for _ in range(3):
        jid = time.strftime('%Y%m%d-%H%M%S') + '-' + kind
        if not os.path.exists(os.path.join(home, 'journal', jid + '.json')):
            break
        time.sleep(1.05)
    return Journal(kind, note, home=home, sims=sims, check_game=check_game)


def _staging(home, journal_id):
    d = os.path.join(home, 'staging', journal_id)
    os.makedirs(d, exist_ok=True)
    return d


def _drop_empty_dir(d):
    """Remove SpeedKit's own staging folder once it is empty (never removes anything with content)."""
    for p in (d, os.path.dirname(d)):
        try:
            os.rmdir(p)
        except OSError:
            break


def _undo_plan(journal_id, home):
    """(actions, problems) of undoing a journal, worked out without touching anything.

    journal.undo() checks each file only when it reaches it, so it can restore some files and then stop
    (leaving a half-undone journal that a second undo refuses), and its dry run does not follow its own
    steps (for a quarantine+put_new 'replace' it reports the new file as 'in the way'). This follows the
    steps newest first while keeping track of which paths each step frees or fills."""
    path = os.path.join(home, 'journal', journal_id + '.json')
    with open(path, encoding='utf-8') as f:
        j = json.load(f)
    if j.get('state') == 'undone':
        return [], ['journal %s was already undone' % journal_id]
    taken = {}

    def exists(p):
        k = os.path.normcase(os.path.abspath(p))
        return taken[k] if k in taken else os.path.exists(p)

    def mark(p, value):
        taken[os.path.normcase(os.path.abspath(p))] = value

    actions, problems = [], []
    for s in reversed(j.get('steps', [])):
        if not s.get('done'):
            continue
        op = s.get('op')
        if op == 'put_new':
            if exists(s['path']):
                if 'fp' in s and os.path.exists(s['path']) and _fingerprint(s['path']) != s['fp']:
                    problems.append('%s changed after SpeedKit wrote it' % s['path'])
                actions.append(('remove new file (kept in quarantine)', s['path']))
                mark(s['path'], False)
        elif op == 'quarantine':
            if not os.path.exists(s['q']):
                problems.append('quarantined copy is missing: %s' % s['q'])
            if exists(s['path']):
                problems.append('cannot restore %s: something is in its place' % s['path'])
            actions.append(('restore', s['path']))
            mark(s['path'], True)
        elif op == 'move':
            if not os.path.exists(s['dst']):
                problems.append('moved item is missing: %s' % s['dst'])
            if exists(s['src']):
                problems.append('cannot move back to %s: something is in its place' % s['src'])
            actions.append(('move back', s['src']))
            mark(s['dst'], False)
            mark(s['src'], True)
        else:
            problems.append('unknown journal step %r' % op)
    return actions, problems


def restore(journal_id, dry_run=True, sims=SIMS, home=None, check_game=True):
    """Undo one SpeedKit settings/caches run. Returns the list of (action, path).

    Every step is checked before anything moves; if one cannot be undone (a file changed or something
    sits where a file would come back) it raises JournalError and nothing is touched. The dry run
    (default) only returns the actions; the real run uses journal.undo and refuses while the game runs."""
    home = _home(sims, home)
    actions, problems = _undo_plan(journal_id, home)
    if problems:
        raise JournalError('cannot undo %s: %s' % (journal_id, '; '.join(problems)))
    if dry_run:
        return actions
    return undo(journal_id, home=home, check_game=check_game, dry_run=False)


def journals(sims=SIMS, home=None):
    """SpeedKit journals of this module (kind 'settings' or 'caches'), newest last."""
    return [j for j in list_journals(_home(sims, home)) if j[1] in ('settings', 'caches')]


# ============================================================================================ Options.ini
# key -> (label, {value: meaning} or None for a plain number, what it costs)
OPTION_INFO = {
    'visualquality': ('Graphics quality preset', {0: 'Custom', 1: 'Low', 2: 'Low-Medium', 3: 'Medium', 4: 'High', 5: 'Ultra'},
                      'a preset re-applies its own levels; SpeedKit sets Custom when it changes single settings'),
    'simquality': ('Sim detail', {1: 'Low', 2: 'Medium', 3: 'High', 4: 'Very High'},
                   'Very High keeps 2048 px Sim textures up close and a 1000 m last LOD step (stock)'),
    'useuncompressedtextures': ('Uncompressed Sim textures', {0: 'Off', 1: 'On'},
                                'On costs video and system memory (6 GB GPU, 16 GB RAM here)'),
    'objectquality': ('Object detail', {1: 'Low', 2: 'Medium', 3: 'High'}, 'object LOD bias and texture mips'),
    'lightingquality': ('Lighting', {1: 'Low', 2: 'Medium', 3: 'High', 4: 'Very High'},
                        'Very High: 2048 px shadow map (stock) and sun shadows indoors'),
    'generalreflections': ('Reflections', {0: 'Off', 1: 'Low', 2: 'Medium', 3: 'High'},
                           'High re-renders the scene in mirrors and water'),
    'edgesmoothing': ('Edge smoothing', {0: 'Off', 1: 'Low', 2: 'Medium', 3: 'High'}, 'anti-aliasing level'),
    'visualeffects': ('Visual effects', {1: 'Low', 2: 'Medium', 3: 'High'}, 'particle density, detailed weather'),
    'viewdistance': ('View distance', {1: 'Low', 3: 'High'}, 'Low draws only about 100 m'),
    'terrainquality': ('Terrain detail', {1: 'Low', 2: 'Medium', 3: 'High'}, 'minor'),
    'sceneresolution': ('3D scene resolution', {1: 'Low (5/8)', 2: 'Medium (25/32)', 3: 'High (full)'},
                        'lower renders the world at a smaller size and scales it up'),
    'postprocessing': ('Post-processing', {0: 'Off', 1: 'On'}, ''),
    'advancedrendering': ('Advanced rendering', {0: 'Off', 1: 'On'}, 'Off forces minimum-spec shaders'),
    'frameratelimit': ('Frame rate limit', None, 'with vsync off, a high cap lets menus and loading screens run the GPU flat out'),
    'verticalsync': ('Vertical sync', {0: 'Off', 1: 'On'}, ''),
    'fullscreen': ('Fullscreen', {0: 'Off', 1: 'On'}, ''),
    'windowedfullscreen': ('Windowed fullscreen', {0: 'Off', 1: 'On'}, ''),
    'resolutionwidth': ('Resolution width', None, ''),
    'resolutionheight': ('Resolution height', None, ''),
    'maxprotectedsims': ('Max Sims in the world', {0: '80', 1: '150', 2: '200', 3: 'Unlimited'},
                         'Maxis: 150 is fine on mid/high-end PCs; 200/Unlimited not recommended'),
    'onlineaccess': ('Online access', {0: 'Off', 1: 'On'}, 'the client was stuck "connecting" (ConnectionStatus.txt)'),
}

# What each preset writes. 'balanced' is the research proposal (research/settings/proposed_settings.json).
OPTION_PRESETS = {
    'balanced': {'visualquality': 0, 'simquality': 3, 'useuncompressedtextures': 0, 'lightingquality': 3,
                 'generalreflections': 1, 'edgesmoothing': 1, 'visualeffects': 2, 'frameratelimit': 60,
                 'verticalsync': 0},
    'performance': {'visualquality': 0, 'simquality': 2, 'useuncompressedtextures': 0, 'lightingquality': 2,
                    'generalreflections': 0, 'edgesmoothing': 0, 'visualeffects': 1, 'objectquality': 2,
                    'terrainquality': 2, 'frameratelimit': 60, 'verticalsync': 0},
}

# One display mode. How the game encodes "windowed fullscreen" is not verified: on 9/23 it wrote
# fullscreen=1 AND windowedfullscreen=1; 'borderless' here writes 0/1.
DISPLAY_MODES = {
    'fullscreen': {'fullscreen': 1, 'windowedfullscreen': 0},
    'borderless': {'fullscreen': 0, 'windowedfullscreen': 1},
    'windowed': {'fullscreen': 0, 'windowedfullscreen': 0},
}

_OPT_LINE = re.compile(rb'^([ \t]*([A-Za-z0-9_]+)[ \t]*=[ \t]*)(.*?)([ \t]*)$')


def _read_options(path):
    """(lines, {key: [(line index, value text)]}) - lines are the raw bytes of each line incl. its ending."""
    with open(path, 'rb') as f:
        data = f.read()
    lines = data.splitlines(keepends=True)
    keys = {}
    for n, line in enumerate(lines):
        body = line.rstrip(b'\r\n')
        m = _OPT_LINE.match(body)
        if m:
            keys.setdefault(m.group(2).decode('latin-1').lower(), []).append((n, m.group(3).decode('latin-1')))
    return lines, keys


def read_options(sims=SIMS):
    """Options.ini as {key: value text} (lower-case keys; the last copy of a key wins)."""
    path = os.path.join(sims, 'Options.ini')
    if not os.path.exists(path):
        return {}
    _, keys = _read_options(path)
    return {k: v[-1][1] for k, v in keys.items()}


def _as_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _meaning(key, value):
    info = OPTION_INFO.get(key)
    if not info or value is None:
        return str(value)
    iv = _as_int(value)
    if info[1] is None or iv is None:
        return str(value)
    return info[1].get(iv, '%s (unknown level)' % value)


def options_status(sims=SIMS, preset='balanced'):
    """Performance-relevant Options.ini keys with their plain meaning and what `preset` would set."""
    if preset not in OPTION_PRESETS:
        raise ValueError('preset must be one of: %s' % ', '.join(OPTION_PRESETS))
    path = os.path.join(sims, 'Options.ini')
    out = {'path': path, 'exists': os.path.exists(path), 'settings': [], 'notes': []}
    if not out['exists']:
        out['notes'].append('Options.ini does not exist (the game creates it on first start).')
        return out
    cur = read_options(sims)
    want = dict(OPTION_PRESETS.get(preset, {}))
    want.update(_display_choice('auto', cur))
    for key, (label, _, cost) in OPTION_INFO.items():
        if key not in cur and key not in want:
            continue
        v = cur.get(key)
        row = {'key': key, 'label': label, 'value': v, 'meaning': _meaning(key, v), 'cost': cost}
        if key in want and str(want[key]) != str(v):
            row['suggested'] = want[key]
            row['suggested_meaning'] = _meaning(key, want[key])
        out['settings'].append(row)
    fs, wfs = _as_int(cur.get('fullscreen')), _as_int(cur.get('windowedfullscreen'))
    if fs == 1 and wfs == 1:
        out['notes'].append('Both fullscreen=1 and windowedfullscreen=1 are set; which mode the game uses is not '
                            'known. The preset picks one (fullscreen) unless you choose display=...')
    fr, vs = _as_int(cur.get('frameratelimit')), _as_int(cur.get('verticalsync'))
    if fr and fr > 120 and not vs:
        out['notes'].append('Frame limit %d with vsync off lets menus, CAS and loading screens run the laptop GPU '
                            'flat out (heat and a shared power budget).' % fr)
    if _as_int(cur.get('visualquality')) not in (0, None) and any(k in want for k in ('simquality', 'lightingquality')):
        out['notes'].append('visualquality=%s is a preset; changing single settings sets it to Custom (0).'
                            % cur.get('visualquality'))
    return out


def _display_choice(display, cur):
    """Display keys to write for display='auto'|'keep'|'fullscreen'|'borderless'|'windowed'."""
    if display in (None, 'keep'):
        return {}
    if display == 'auto':
        both = _as_int(cur.get('fullscreen')) == 1 and _as_int(cur.get('windowedfullscreen')) == 1
        return dict(DISPLAY_MODES['fullscreen']) if both else {}
    if display not in DISPLAY_MODES:
        raise ValueError('display must be auto, keep, %s' % ', '.join(DISPLAY_MODES))
    return dict(DISPLAY_MODES[display])


def _rewrite_options(lines, keys, changes):
    """New file bytes with only `changes` ({key: value}) rewritten; missing keys are appended."""
    new = list(lines)
    eol = b'\r\n' if (lines and lines[0].endswith(b'\r\n')) else b'\n'
    appended = []
    for key, value in changes.items():
        val = str(value).encode('latin-1')
        if key in keys:
            for n, _ in keys[key]:
                line = new[n]
                body = line.rstrip(b'\r\n')
                ending = line[len(body):]
                m = _OPT_LINE.match(body)
                new[n] = m.group(1) + val + m.group(4) + ending
        else:
            appended.append(key.encode('latin-1') + b' = ' + val + eol)
    if appended:
        if new and not new[-1].endswith((b'\n', b'\r')):
            new[-1] = new[-1] + eol
        # The game writes every entry followed by one blank line. Keep that: after a trailing blank
        # line write "key = v" + blank line; otherwise put the blank line in front.
        trailing_blank = bool(new) and not new[-1].strip()
        for a in appended:
            if trailing_blank:
                new.extend((a, eol))
            else:
                new.extend((eol, a))
    return b''.join(new)


def options_apply(preset='balanced', dry_run=True, display='auto', extra=None, sims=SIMS, home=None, check_game=True):
    """Set the preset's Options.ini keys (and one display mode); every other line stays byte-identical.

    preset: 'balanced' (research proposal) or 'performance'. display: 'auto' (fix fullscreen=1 +
    windowedfullscreen=1 by choosing fullscreen, else keep), 'keep', 'fullscreen', 'borderless',
    'windowed'. extra: more {key: value} for keys listed in OPTION_INFO (e.g. {'maxprotectedsims': 0}).
    Every value must be a whole number and, for keys with levels, one of the known levels (ValueError).
    Returns the plan; with dry_run=False it writes through a Journal (kind 'settings')."""
    if preset not in OPTION_PRESETS:
        raise ValueError('preset must be one of: %s' % ', '.join(OPTION_PRESETS))
    path = os.path.join(sims, 'Options.ini')
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    lines, keys = _read_options(path)
    cur = {k: v[-1][1] for k, v in keys.items()}
    want = dict(OPTION_PRESETS[preset])
    want.update(_display_choice(display, cur))
    for k, v in (extra or {}).items():
        if k.lower() not in OPTION_INFO:
            raise ValueError('not a known performance key: %s' % k)
        want[k.lower()] = v
    for k, v in want.items():               # whole numbers only, and a known level where the key has levels
        if isinstance(v, bool) or not re.fullmatch(r'\d+', str(v)):
            raise ValueError('bad value for %s: %r (a whole number is needed)' % (k, v))
        iv = int(str(v))
        levels = OPTION_INFO[k][1]
        if levels is not None and iv not in levels:
            raise ValueError('bad value for %s: %r (known: %s)' % (k, v, ', '.join(map(str, levels))))
        want[k] = iv
    changes = {k: v for k, v in want.items() if k not in keys or any(str(v) != old for _, old in keys[k])}
    plan = {'path': path, 'preset': preset, 'dry_run': dry_run, 'journal': None,
            'changes': [{'key': k, 'label': OPTION_INFO.get(k, (k,))[0], 'old': cur.get(k), 'new': v,
                         'old_meaning': _meaning(k, cur.get(k)) if k in cur else 'not set',
                         'new_meaning': _meaning(k, v)} for k, v in changes.items()],
            'game_running': game_running() if check_game else False}
    if not changes:
        plan['note'] = 'Options.ini already matches the preset.'
        return plan
    new_bytes = _rewrite_options(lines, keys, changes)
    plan['bytes_before'], plan['bytes_after'] = sum(map(len, lines)), len(new_bytes)
    if dry_run:
        if plan['game_running']:
            plan['note'] = 'The Sims 4 is running: the real run will refuse (the game rewrites Options.ini on exit).'
        return plan
    if check_game and game_running():
        raise JournalError('The Sims 4 is running - close it first (it rewrites Options.ini when it exits).')
    home = _home(sims, home)
    j = _open_journal('settings', 'Options.ini: %s preset (%s)' % (preset, ', '.join('%s=%s' % kv for kv in changes.items())),
                      sims, home, check_game)
    with j:
        stage = _staging(home, j.id)
        tmp = os.path.join(stage, 'Options.ini')
        with open(tmp, 'wb') as f:
            f.write(new_bytes)
        j.replace(tmp, path)
    _drop_empty_dir(stage)
    with open(path, 'rb') as f:
        if f.read() != new_bytes:
            raise JournalError('Options.ini does not read back as written; undo with restore(%r)' % j.id)
    plan['journal'] = j.id
    return plan


# ============================================================================================ graphics
# Props that decide render cost, in plain words. heavier: 'higher' / 'lower' / 'true' = which way costs more.
KEY_PROPS = [
    ('ObjectSizeCullFactor', 'Small-object culling (stock 200; higher = small far objects stay drawn - inferred)', 'higher'),
    ('ClipPlaneDistances', 'Draw distance, near..far clip planes in metres', 'higher'),
    ('ClipPlaneZoomDistant', 'Camera zoom-out clip distance', 'higher'),
    ('ObjectLODBias', 'Object detail switching (0 = always the most detailed model)', 'lower'),
    ('ObjectLODInterestBias', 'Detail bias for objects away from the camera focus (0 = none)', 'lower'),
    ('RenderSimLODDistances', 'Distances (m) where Sims switch to simpler models', 'higher'),
    ('RenderSimTextureSizes', 'Sim texture size (px) at each distance step', 'higher'),
    ('ShadowMapSize', 'Shadow map resolution (px)', 'higher'),
    ('SsaoEnabled', 'Ambient occlusion', 'true'),
    ('DofEnabled', 'Depth-of-field blur', 'true'),
    ('InteriorSunShadows', 'Sun shadows inside rooms', 'true'),
    ('NormalMappingEnabled', 'Surface bump detail (normal maps)', 'true'),
    ('FSAALevel', 'Edge smoothing level (values over 8 are probably clamped)', 'higher'),
    ('MirrorFadeRadiusThreshold', 'Mirror fade radius', 'higher'),
    ('InteriorMirrorFarPlane', 'How far mirrors reflect indoors (m)', 'higher'),
    ('ExteriorMirrorFarPlane', 'How far mirrors reflect outdoors (m)', 'higher'),
    ('WaterReflectionAreaThresholdLot', 'Smallest water area on a lot that reflects (0 = all)', 'lower'),
    ('WaterReflectionAreaThresholdWorld', 'Smallest water area in the world that reflects (0 = all)', 'lower'),
    ('TextureSizeThreshold', 'Object texture size limit (inactive at Object detail High)', 'higher'),
    ('TerrainLODBoost', 'Terrain detail boost', 'higher'),
    ('SimCacheSizeLimit', 'Sims kept ready in memory', 'higher'),
]


def _numbers(v):
    return [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', v or '')]


def _norm(v):
    return None if v is None else ', '.join(settings_sgr.fmt(x) for x in _numbers(v)) or v.strip().lower()


def _effect(stock, active, heavier):
    """'heavier' / 'lighter' / 'different' for one prop value change."""
    if heavier == 'true':
        s, a = str(stock).lower() in ('true', '1'), str(active).lower() in ('true', '1')
        return 'different' if s == a else ('heavier' if a else 'lighter')
    sn, an = _numbers(stock), _numbers(active)
    if not sn or not an or any(x < 0 for x in sn + an):
        return 'different (effect of this value unknown)'
    s, a = sum(sn), sum(an)
    if s == a:
        return 'different'
    return 'heavier' if (a > s) == (heavier == 'higher') else 'lighter'


def compare_rules(stock, active, levels):
    """Key render props that differ between two evaluated rule sets at the player's option levels."""
    se, ae = stock.effective(levels), active.effective(levels)
    out = []
    for prop, what, heavier in KEY_PROPS:
        s, a = se.get(prop, (None, ''))[0], ae.get(prop, (None, ''))[0]
        if _norm(s) == _norm(a):
            continue
        eff = _effect(s, a, heavier) if s is not None and a is not None else 'different'
        out.append({'prop': prop, 'what': what, 'stock': s, 'active': a, 'effect': eff,
                    'where': ae.get(prop, se.get(prop, (None, '')))[1],
                    'plain': '%s: %s instead of %s (%s)' % (what, a if a is not None else 'not set',
                                                             s if s is not None else 'not set', eff)})
    return out


def _levels(sims):
    return {k: iv for k, v in read_options(sims).items() if (iv := _as_int(v)) is not None}


def _identify(path):
    """(kind, label) of a GraphicsRules.sgr."""
    with open(path, encoding='utf-8', errors='replace') as f:
        text = f.read()
    if re.match(r'(?:﻿)?' + re.escape(TUNED_MARK), text):
        m = re.search(r'\+\+\+\s*(\S+)\s+SGR Full', text)
        return 'speedkit_tuned', "%s (Simp4Sims 'SGR Full'%s with the lag-causing values tuned)" % (
            TUNED_LABEL, ' %s' % m.group(1) if m else '')
    if re.search(r'^\s*include\s+"SimpsSetters\.sgr"', text, re.I | re.M):
        m = re.search(r'Release Date\s*:\s*([^"]+)"', text)
        return 'simp_setters', "Simp4Sims 'Setters' rules%s" % (' (release %s)' % m.group(1).strip() if m else '')
    m = re.search(r'\+\+\+\s*(\S+)\s+SGR Full', text)
    if m:
        return 'simp_sgr_full', "Simp4Sims 'SGR Full' (%s)" % m.group(1)
    if 'Simp4Sims' in text:
        return 'simp_other', 'a Simp4Sims rules file (unknown version)'
    return 'other', 'an unknown GraphicsRules.sgr override'


def _setter_text(path):
    """MySetters.sgr content reduced to its statements, for comparing against the presets."""
    with open(path, encoding='utf-8', errors='replace') as f:
        return [' '.join(l.split('#')[0].split()).lower() for l in f if l.split('#')[0].strip()]


def list_presets(sims=SIMS, source=None):
    """{preset name: MySetters.sgr path} from Simp4Sims' download folder ('Defaults' = empty MySetters.sgr)."""
    src = source or os.path.join(sims, SETTERS_DIR)
    out = {}
    root = os.path.join(src, PRESETS_DIR)
    if os.path.isdir(root):
        for n in sorted(os.listdir(root)):
            p = os.path.join(root, n, 'MySetters.sgr')
            if os.path.isfile(p):
                out[n] = p
    if os.path.isfile(os.path.join(src, 'MySetters.sgr')):
        out['Defaults'] = os.path.join(src, 'MySetters.sgr')
    return out


def _which_preset(mysetters, sims, source=None):
    if not os.path.exists(mysetters):
        return None
    mine = _setter_text(mysetters)
    for name, p in list_presets(sims, source).items():
        if _setter_text(p) == mine:
            return name
    return 'custom MySetters.sgr'


def _tuned_status(out, kind, sims, home, game_bin):
    """Add 'tune', 'tuned' and 'tuned_journal' (and their notes) to a graphics_status result."""
    out['tuned'] = None
    out['tuned_journal'] = jid = tuned_journal(sims, home)
    try:
        t = graphics_use_tuned(dry_run=True, sims=sims, home=home, check_game=False, game_bin=game_bin)
        out['tune'] = {'action': t['action'], 'reason': t['refused'] or t.get('note'), 'source': t['source']}
    except (OSError, ValueError) as e:         # an odd rules file must not break status/preflight
        t = None
        out['tune'] = {'action': 'error', 'reason': '%s: %s' % (type(e).__name__, e), 'source': None}
    log = out.get('config_log') or {}
    notes = out['notes']
    if kind == 'speedkit_tuned':
        over = ['%s (%s)' % (c['prop'], 'global' if c['option'] is None else '%s=%s' % (c['option'], c['level']))
                for c in t['changes']] if t else []
        confirmed = bool(log.get('tuned_logged') and log.get('newer_than_rules'))
        checked = t is not None and not t['refused']
        out['tuned'] = {'ok': checked and not t['changes'], 'over': over, 'journal': jid, 'confirmed': confirmed}
        if not checked:
            notes.append('The %s file could not be checked (%s).' % (TUNED_LABEL, out['tune']['reason']))
        elif over:
            notes.append('The %s file was edited: %s %s above SpeedKit\'s values again (graphics_use_tuned puts '
                         'them back).' % (TUNED_LABEL, ', '.join(over[:6]), 'is' if len(over) == 1 else 'are'))
        else:
            notes.append('%s is active: SGR Full\'s look with only the lag-causing values tuned (Sim LOD 2x stock, '
                         'stock culling, object LOD and far clip, FSAA 8, shadows and mirrors at most 2x stock).'
                         % TUNED_LABEL)
        if checked and t.get('problems'):
            notes.append('%d lines of the %s file could not be tuned and keep their SGR Full values (first: %s).'
                         % (len(t['problems']), TUNED_LABEL, t['problems'][0]))
        if confirmed:
            notes.append('Config.log confirms the game loaded %s at its last start.' % TUNED_LABEL)
    else:
        if jid:
            notes.append('%s was installed (journal %s), but ConfigOverride\\GraphicsRules.sgr has been replaced '
                         'since: the game now uses %s.' % (TUNED_LABEL, jid, out['label']))
        if out['tune']['action'] in ('add', 'replace'):
            notes.append('graphics_use_tuned would install %s (made from %s).' % (TUNED_LABEL, out['tune']['source']))
        elif out['tune']['action'] in ('refused', 'error') and kind != 'stock':
            notes.append('%s: %s' % (TUNED_LABEL, out['tune']['reason']))


def graphics_status(sims=SIMS, game_bin=GAME_BIN, home=None):
    """Which graphics rules the game uses and how they differ from stock, in plain words.

    Returns {'active': 'stock'|'speedkit_tuned'|'simp_sgr_full'|'simp_setters'|'simp_other'|'other', 'label'
    ('SpeedKit Max Quality (...)' for SpeedKit's tuned rules), 'preset', 'rules_file', 'files' (ConfigOverride
    contents, loaded or not), 'levels' (Options.ini), 'differences' [{prop, what, stock, active, effect, plain}],
    'missing_stock_options', 'config_log' {first_line, matches, newer_than_rules, tuned_logged}, 'notes',
    'tuned' (for SpeedKit Max Quality: {ok, over, journal, confirmed}; else None), 'tune' (what
    graphics_use_tuned would do now: {action 'none'|'add'|'replace'|'refused'|'error', reason, source}),
    'tuned_journal' (newest SpeedKit Max Quality install not undone)}."""
    co = os.path.join(sims, 'ConfigOverride')
    stock_path = os.path.join(game_bin, 'GraphicsRules.sgr')
    override = os.path.join(co, 'GraphicsRules.sgr')
    machine = settings_sgr.machine_vars(os.path.join(sims, 'Config.log'))
    stock = settings_sgr.evaluate(stock_path, machine)
    if os.path.exists(override):
        kind, label = _identify(override)
        active = settings_sgr.evaluate(override, machine)
        rules_file = override
    else:
        kind, label, active, rules_file = 'stock', "the game's own rules (%s)" % stock_path, stock, stock_path
    loaded = {os.path.normcase(os.path.abspath(p)) for p in active.files}
    files = []
    if os.path.isdir(co):
        for n in sorted(os.listdir(co)):
            p = os.path.join(co, n)
            if os.path.isfile(p):
                st = os.stat(p)
                files.append({'name': n, 'size': st.st_size, 'mtime': st.st_mtime,
                              'loaded': os.path.normcase(os.path.abspath(p)) in loaded})
    levels = _levels(sims)
    out = {'active': kind, 'label': label, 'rules_file': rules_file, 'files': files, 'levels': levels,
           'preset': _which_preset(os.path.join(co, 'MySetters.sgr'), sims) if kind == 'simp_setters' else None,
           'differences': compare_rules(stock, active, levels) if active is not stock else [],
           'missing_stock_options': sorted(stock.option_names() - active.option_names()) if active is not stock else [],
           'notes': []}
    # Config.log is written by the rules at every game start: its first line tells which file was parsed.
    log = os.path.join(sims, 'Config.log')
    if os.path.exists(log):
        with open(log, encoding='utf-8', errors='replace') as f:
            head = f.read(8000)                     # the rules' logSystemInfo lines come first
        first = next((l.strip() for l in head.splitlines() if l.strip()), '')
        expect = active.info[0].strip() if active.info else ''
        out['config_log'] = {'first_line': first, 'matches': bool(expect) and first == expect,
                             'newer_than_rules': os.path.getmtime(log) >= os.path.getmtime(rules_file),
                             'tuned_logged': TUNED_LOG_TEXT in head}
        if not out['config_log']['newer_than_rules']:
            out['notes'].append('The rules changed after the last game start; Config.log will confirm them next launch.')
        elif not out['config_log']['matches']:
            out['notes'].append('Config.log starts with %r, not what these rules log first (%r).' % (first, expect))
    else:
        out['config_log'] = None
    for f in files:
        if f['name'].lower().endswith('.sgr') and not f['loaded']:
            out['notes'].append('%s is in ConfigOverride but is not loaded by the active rules.' % f['name'])
    for kw, target in active.missing:       # e.g. Setters rules copied without SimpsSetters.sgr
        if kw == 'include' and 'graphicsCards' not in target:
            out['notes'].append('The rules include %s, which is missing; its values read as 0 here.' % target)
    if active.errors:
        out['notes'].append('%d rules lines could not be read (first: %s line %d: %s).'
                            % ((len(active.errors),) + tuple(active.errors[0])))
    if kind == 'simp_sgr_full':
        out['notes'].append('SGR Full turns off Sim LOD, object LOD bias and small-object culling. %s '
                            '(graphics_use_tuned) keeps its look and brings only the lag-causing values back to '
                            'high-end values; the stock rules (graphics_use_stock) cull the most.' % TUNED_LABEL)
    _tuned_status(out, kind, sims, home, game_bin)
    if kind == 'simp_setters':
        sim_lod = active.effective(levels).get('RenderSimLODDistances', ('',))[0]
        if sim_lod and max(_numbers(sim_lod) or [0]) > 1000:
            out['notes'].append('These Setters still keep Sims at full detail out to %s m; only the stock rules '
                                'switch Sims to simpler models with distance.' % settings_sgr.fmt(max(_numbers(sim_lod))))
    if out['missing_stock_options']:
        out['notes'].append('%d options of the stock rules are not defined by the override (the game still falls '
                            'back to working values for them).' % len(out['missing_stock_options']))
    out['heavier'] = sum(1 for d in out['differences'] if d['effect'] == 'heavier')
    out['lighter'] = sum(1 for d in out['differences'] if d['effect'] == 'lighter')
    return out


def graphics_use_stock(dry_run=True, sims=SIMS, home=None, check_game=True):
    """Quarantine every .sgr in ConfigOverride so the game uses its own GraphicsRules.sgr.

    Returns {'actions': [(action, path)], 'journal', 'dry_run'}. Undo with graphics_restore(journal)."""
    co = os.path.join(sims, 'ConfigOverride')
    targets = [os.path.join(co, n) for n in sorted(os.listdir(co))
               if n.lower().endswith('.sgr') and os.path.isfile(os.path.join(co, n))] if os.path.isdir(co) else []
    plan = {'dry_run': dry_run, 'journal': None, 'actions': [('quarantine', p) for p in targets],
            'game_running': game_running() if check_game else False}
    if not targets:
        plan['note'] = 'ConfigOverride has no .sgr file: the game already uses its own rules.'
        return plan
    if dry_run:
        return plan
    j = _open_journal('settings', "graphics: use the game's own rules (quarantine %d ConfigOverride .sgr)" % len(targets),
                      sims, home, check_game)
    with j:
        for p in targets:
            j.quarantine(p)
    plan['journal'] = j.id
    return plan


def graphics_use_preset(name='Ultimate Performance', dry_run=True, sims=SIMS, home=None, check_game=True,
                        source=None, game_bin=GAME_BIN):
    """Install Simp4Sims' 2023 Setters rules with one preset into ConfigOverride.

    source defaults to <Sims 4>\\Simps_GraphicsRules_Setters. Copies GraphicsRules.sgr and
    SimpsSetters.sgr from there and the chosen preset's MySetters.sgr ('Defaults' = Simp's empty one);
    files already identical are left alone. Returns the plan with 'preview': the key differences from
    stock this would give at the player's option levels."""
    src = source or os.path.join(sims, SETTERS_DIR)
    presets = list_presets(sims, src)
    match = {k.lower(): k for k in presets}
    if name.lower() not in match:
        raise ValueError('unknown preset %r; available: %s' % (name, ', '.join(presets) or 'none (folder missing)'))
    name = match[name.lower()]
    want = {'GraphicsRules.sgr': os.path.join(src, 'GraphicsRules.sgr'),
            'SimpsSetters.sgr': os.path.join(src, 'SimpsSetters.sgr'),
            'MySetters.sgr': presets[name]}
    for f, p in want.items():
        if not os.path.isfile(p):
            raise FileNotFoundError(p)
    if _identify(want['GraphicsRules.sgr'])[0] != 'simp_setters':
        raise ValueError('%s does not include SimpsSetters.sgr - not the Setters version' % want['GraphicsRules.sgr'])
    co = os.path.join(sims, 'ConfigOverride')
    actions = []
    for fname, s in want.items():
        final = os.path.join(co, fname)
        if not os.path.exists(final):
            actions.append(('add', s, final))
        elif file_digest(final) == file_digest(s):
            actions.append(('keep (identical)', s, final))
        else:
            actions.append(('replace', s, final))
    others = [n for n in (os.listdir(co) if os.path.isdir(co) else [])
              if n.lower().endswith('.sgr') and n not in want]
    machine = settings_sgr.machine_vars(os.path.join(sims, 'Config.log'))
    stock = settings_sgr.evaluate(os.path.join(game_bin, 'GraphicsRules.sgr'), machine)
    after = settings_sgr.evaluate(want['GraphicsRules.sgr'], machine, {'MySetters.sgr': presets[name]})
    plan = {'dry_run': dry_run, 'journal': None, 'preset': name, 'source': src,
            'actions': [(a, f) for a, _, f in actions],
            'preview': compare_rules(stock, after, _levels(sims)),
            'notes': ['%s in ConfigOverride is left as it is (not part of the Setters install).' % n for n in others],
            'game_running': game_running() if check_game else False}
    todo = [a for a in actions if a[0] in ('add', 'replace')]
    if not todo:
        plan['note'] = 'ConfigOverride already holds this preset.'
        return plan
    if dry_run:
        return plan
    home = _home(sims, home)
    j = _open_journal('settings', 'graphics: Simp4Sims Setters + %s' % name, sims, home, check_game)
    with j:
        stage = _staging(home, j.id)
        for action, s, final in todo:
            tmp = os.path.join(stage, os.path.basename(final))
            shutil.copy2(s, tmp)
            if action == 'replace':
                j.replace(tmp, final)
            else:
                j.put_new(tmp, final)
    _drop_empty_dir(stage)
    for _, s, final in actions:
        if file_digest(s) != file_digest(final):
            raise JournalError('%s does not match its source after install; undo with graphics_restore(%r)' % (final, j.id))
    plan['journal'] = j.id
    return plan


# ============================================================================================ SpeedKit Max Quality
# "Keep graphics at highest but fix the lag": the user's SGR Full file with ONLY its lag-causing values brought
# back to sane, still high-end values; every other line stays SGR Full (its sharper textures, reflections on all
# water, no SSAO/DoF, ...). Each rule is a CAP computed from the stock value of the same option level: a value
# already at or under the cap is kept, so tuning twice changes nothing and a lighter value a user chose stays.
# The rules are applied at every level of these options (not only the player's), so choosing a lower level in
# the game never brings SGR Full's 3000 m Sim LOD etc. back. At the player's Ultra / Very High levels they give:
#   Sim LOD distances 50/100/200/2000 (2x stock 25/50/100/1000; SGR Full 3000 = never switch)
#   Sim textures 2048/2048/1024/512 (stock 2048/1024/512/128; SGR Full 2048 at every distance)
#   ObjectSizeCullFactor 200, ObjectLODBias 0.6666, far clip 1000/1500 (stock; SGR Full 9999 / 0 / 9999)
#   FSAALevel 8 (stock High; 512 is not a real level), ShadowMapSize 4096 (stock 2048, SGR Full 5120)
#   mirror reflections 2x stock (fade 2.6, interior 150, exterior 300; SGR Full 120/900/1200), TerrainLODBoost 2
TUNED_LABEL = 'SpeedKit Max Quality'
TUNED_MARK = '# Tuned by SpeedKit'                     # first line of a tuned file (header comment)
TUNED_END = '# End of SpeedKit header'
TUNED_LOG_TEXT = '+++ Tuned by SpeedKit: Max Quality +++'
TUNED_LOG = 'logSystemInfo "%s"' % TUNED_LOG_TEXT      # lands in Config.log: proof the game parsed the tuned file
TUNED_NOTE = 'graphics: %s' % TUNED_LABEL              # journal note prefix
TUNED_HEADER = (
    '%s: %s' % (TUNED_MARK, TUNED_LABEL),
    '# This is Simp4Sims SGR Full with only the values that cause lag brought back to high-end values:',
    '# Sim LOD distances 2x stock, Sim textures one step sharper than stock (2048/2048/1024/512 at',
    '# Very High), small-object culling, object LOD bias and far clip as stock, edge smoothing at most 8,',
    '# shadow map at most 2x stock (4096 at Very High), mirror reflections at most 2x stock, terrain',
    '# LOD boost 2. Every other line is SGR Full unchanged. The original file is kept in the',
    '# SpeedKit/quarantine folder of The Sims 4 folder. To undo: python -m speedkit.settings journals',
    '# then python -m speedkit.settings restore JOURNAL-ID --apply',
    TUNED_END,
)
TUNABLE = ('simp_sgr_full', 'speedkit_tuned')
SIM_LOD_FACTOR = 2          # Sims switch to simpler models at 2x the stock distances
SHADOW_FACTOR = 2           # shadow map at most 2x stock (Very High: 4096; stock 2048, SGR Full 5120)
REFLECTION_FACTOR = 2       # mirror reflection distances at most 2x stock
FSAA_MAX = 8                # stock High; SGR Full's 16/64/512 are not real anti-aliasing levels
TERRAIN_LOD_BOOST = 2       # SGR Full 6, stock 0-1


def _cap_each(values, caps):
    return [min(v, c) for v, c in zip(values, caps)]


def _rule_sim_lod(b, s):
    """At most 2x the stock distances: Sims stay fully detailed farther than stock, but not to the horizon."""
    return _cap_each(b, [SIM_LOD_FACTOR * x for x in s]) if s and len(s) == len(b) else None


def _rule_sim_textures(b, s):
    """Each distance step gets at most the size stock uses one step closer (2048/2048/1024/512 at Very High)."""
    return _cap_each(b, s[:1] + s[:-1]) if s and len(s) == len(b) else None


def _rule_cull(b, s):
    """Stock small-object culling (a negative value is a special switch; it becomes stock too)."""
    if len(b) != 1 or len(s) != 1:
        return None
    return [s[0] if b[0] < 0 else min(b[0], s[0])]


def _rule_lod_bias(b, s):
    """Object LOD bias at least stock (0 = the most detailed model at any distance)."""
    return [max(b[0], s[0])] if len(b) == 1 and len(s) == 1 else None


def _rule_far_clip(b, s):
    """The two far clip values at most stock; the near values stay SGR Full's."""
    return b[:-2] + _cap_each(b[-2:], s[-2:]) if len(b) >= 3 and len(s) == len(b) else None


def _rule_fsaa(b, s):
    return [min(b[0], FSAA_MAX)] if len(b) == 1 else None


def _rule_times(factor):
    def rule(b, s):
        return [min(b[0], factor * s[0])] if len(b) == 1 and len(s) == 1 else None
    rule.__doc__ = 'At most %gx stock.' % factor
    return rule


def _rule_terrain(b, s):
    return [min(b[0], max(TERRAIN_LOD_BOOST, s[0]))] if len(b) == 1 and len(s) == 1 else None


# prop -> (plain words, rule(base numbers, stock numbers) -> new numbers or None). Order = report order.
TUNED_PROPS = {
    'RenderSimLODDistances': ('Distances (m) where Sims switch to simpler models (2x stock)', _rule_sim_lod),
    'RenderSimTextureSizes': ('Sim texture size (px) per distance step (one step sharper than stock)', _rule_sim_textures),
    'ObjectSizeCullFactor': ('Small-object culling (stock)', _rule_cull),
    'ObjectLODBias': ('Object detail switching (stock)', _rule_lod_bias),
    'ClipPlaneDistances': ('Clip planes near..far in metres (far = stock, near stays)', _rule_far_clip),
    'FSAALevel': ('Edge smoothing level (8 = the highest real level)', _rule_fsaa),
    'ShadowMapSize': ('Shadow map resolution in px (at most 2x stock)', _rule_times(SHADOW_FACTOR)),
    'MirrorFadeRadiusThreshold': ('Mirror fade radius (at most 2x stock)', _rule_times(REFLECTION_FACTOR)),
    'InteriorMirrorFarPlane': ('How far mirrors reflect indoors, m (at most 2x stock)', _rule_times(REFLECTION_FACTOR)),
    'ExteriorMirrorFarPlane': ('How far mirrors reflect outdoors, m (at most 2x stock)', _rule_times(REFLECTION_FACTOR)),
    'TerrainLODBoost': ('Terrain detail boost (2)', _rule_terrain),
}

_PROP_LINE = re.compile(r'^(\s*(?:prop|setprop)\s+\S+\s+(\w+)\s+)(.*)$', re.I)
_NUM_ELEMENT = re.compile(r'^\s*(-?(?:\d+(?:\.\d*)?|\.\d+))([fF]?)\s*$')
_SGR_FULL_LOG = re.compile(r'^\s*logSystemInfo\s+"\+\+\+[^"]*SGR Full[^"]*"', re.I)
_ANY_LOG = re.compile(r'^\s*logSystemInfo\b', re.I)


def _split_value(rest):
    """(value, tail) of the text after a prop name: tail is the spaces and # comment after the value."""
    quoted = False
    end = len(rest)
    for i, ch in enumerate(rest):
        if ch == '"':
            quoted = not quoted
        elif ch == '#' and not quoted:
            end = i
            break
    value = rest[:end].rstrip()
    return value, rest[len(value):]


def _parse_numbers(value):
    """(quoted, [(number, element text)]) of a plain numeric prop value such as "25, 50" or 120.0f;
    None when the value is not plain numbers (a ${variable}, a word...)."""
    quoted = len(value) >= 2 and value[0] == value[-1] == '"'
    core = value[1:-1] if quoted else value
    out = []
    for el in core.split(','):
        m = _NUM_ELEMENT.match(el)
        if not m:
            return None
        out.append((float(m.group(1)), el.strip()))
    return quoted, out


def _format_like(el, x, keep_point=False):
    """x written in the style of the element text el: '120.0f' -> '2.6f', '900.0f' -> '150.0f', '9999' -> '1000';
    keep_point: '0.60' -> '4.0' (a single value that had a decimal point keeps one)."""
    suffix = el[-1] if el.endswith(('f', 'F')) else ''
    s = settings_sgr.fmt(float(x))
    if (suffix or (keep_point and '.' in el)) and '.' not in s:
        s += '.0'
    return s + suffix


def _compose_value(value, quoted, elements, new):
    """New value text: changed elements formatted like the old ones, unchanged elements kept as they were."""
    core = value[1:-1] if quoted else value
    sep = ', ' if ', ' in core else ','
    single = len(elements) == 1
    parts = [text if n == x else _format_like(text, x, single) for (n, text), x in zip(elements, new)]
    body = sep.join(parts)
    return '"%s"' % body if quoted else body


def _strip_speedkit(text):
    """Rules text without SpeedKit's header and log line (the SGR Full text a tuned file was made from)."""
    lines = text.splitlines(keepends=True)
    if lines and lines[0].startswith(TUNED_MARK):
        end = next((i for i, l in enumerate(lines) if l.startswith(TUNED_END)), 0)
        lines = lines[end + 1:]
    return ''.join(l for l in lines if l.strip() != TUNED_LOG)


def _stock_value(stock, levels, option, level, prop):
    """Stock value text of prop at one option level (None if stock does not set it)."""
    lv = dict(levels)
    if option is not None:
        lv[option.lower()] = level
    return stock.effective(lv).get(prop, (None,))[0]


def _check_tuned(base, tuned, want, changes, levels, lines_before, lines_after, header_len, log_at, want_dormant=None):
    """Problems (list of str) if the tuned rules differ from the source anywhere they should not.

    want: {(option, level, prop): the rule's numbers} - what the tuned file must say (not the text written).
    want_dormant: {line number in the source: the rule's numbers} for lines in if-branches this PC does not run
    (the rules reader does not run them, so they are checked in the text).

    Checks: the text differs only on the changed lines (plus the header and one log line); run through the
    rules reader, every option level and every global prop is identical except the intended props, which
    have exactly their new values; variables, log lines, errors and includes are the same; and at the player's
    levels every effective value is the intended one."""
    problems = []
    # 1. text: only the patched lines differ
    body = lines_after[header_len:]
    if log_at is not None:
        body = body[:log_at] + body[log_at + 1:]
    if len(body) != len(lines_before):
        problems.append('line count changed (%d -> %d)' % (len(lines_before), len(body)))
    else:
        changed = {n + 1 for n, (a, b) in enumerate(zip(lines_before, body)) if a != b}
        expected = {c['line'] for c in changes}
        if changed != expected:
            problems.append('lines changed that should not: %s' % sorted(changed ^ expected)[:10])
        for n, nums in (want_dormant or {}).items():
            m = _PROP_LINE.match(body[n - 1].rstrip('\r\n'))
            parsed = _parse_numbers(_split_value(m.group(3))[0]) if m else None
            if parsed is None or [x for x, _ in parsed[1]] != nums:
                problems.append('line %d (used on other hardware) is %r, not the intended value' % (n, body[n - 1].strip()))
    if set(base.dormant) != set(tuned.dormant):
        problems.append('the if-branches for other hardware differ: %s' % sorted(set(base.dormant) ^ set(tuned.dormant),
                                                                                 key=str)[:5])
    # 2. every option level and global prop
    if set(base.options) != set(tuned.options):
        problems.append('options differ: %s' % sorted(set(base.options) ^ set(tuned.options)))
    for name, opt in base.options.items():
        topt = tuned.options.get(name)
        if topt is None:
            continue
        if opt['default'] != topt['default'] or set(opt['settings']) != set(topt['settings']):
            problems.append('option %s changed its levels or default' % name)
        for level, props in opt['settings'].items():
            tprops = topt['settings'].get(level, {})
            for p in set(props) | set(tprops):
                key = (name, level, p)
                if key in want:
                    if _numbers(tprops.get(p)) != want[key]:
                        problems.append('%s=%s %s is %r, not the intended value' % (name, level, p, tprops.get(p)))
                elif props.get(p) != tprops.get(p):
                    problems.append('%s=%s %s changed: %r -> %r' % (name, level, p, props.get(p), tprops.get(p)))
    for p in set(base.globals) | set(tuned.globals):
        key = (None, None, p)
        if key in want:
            if _numbers(tuned.globals.get(p)) != want[key]:
                problems.append('global %s is %r, not the intended value' % (p, tuned.globals.get(p)))
        elif base.globals.get(p) != tuned.globals.get(p):
            problems.append('global %s changed: %r -> %r' % (p, base.globals.get(p), tuned.globals.get(p)))
    # 3. the rest of the script
    if base.vars != tuned.vars:
        problems.append('variables changed: %s' % sorted(k for k in set(base.vars) | set(tuned.vars)
                                                         if base.vars.get(k) != tuned.vars.get(k))[:10])
    if [i for i in tuned.info if i != TUNED_LOG_TEXT] != base.info:
        problems.append('logSystemInfo lines changed')
    if [e[2] for e in base.errors] != [e[2] for e in tuned.errors] or base.missing != tuned.missing \
            or base.undefined != tuned.undefined:
        problems.append('the rules reader sees different errors, includes or undefined variables')
    # 4. at the player's levels
    want_where = {('global' if o is None else '%s=%s' % (o, lv), p): nums for (o, lv, p), nums in want.items()}
    be, te = base.effective(levels), tuned.effective(levels)
    for p in set(be) | set(te):
        if be.get(p) == te.get(p):
            continue
        key = (te.get(p, (None, ''))[1], p)
        if key not in want_where or be.get(p, (None, ''))[1] != key[0] or _numbers(te[p][0]) != want_where[key]:
            problems.append('at your levels %s is %r instead of %r' % (p, te.get(p, (None,))[0], be.get(p, (None,))[0]))
    return problems


def build_tuned_rules(source, sims=SIMS, game_bin=GAME_BIN, levels=None, target=None):
    """Make the 'SpeedKit Max Quality' rules from an SGR Full file (or an earlier tuned one). Writes nothing.

    source: the rules file to tune. target: where the result will live (default ConfigOverride\\GraphicsRules.sgr
    of sims; includes resolve there, as in the game). levels: option levels for the report table (default
    Options.ini). Every assignment of a TUNED_PROPS prop in source (in any option level, or global, also inside
    if-branches that only other hardware runs) gets its rule's value; the value text keeps its style ("quotes",
    120.0f). A header comment and one logSystemInfo
    line (so Config.log proves the game parsed this file) are added. The result is then run through the
    rules reader and compared with the source (_check_tuned); any unintended difference raises ValueError.

    Returns {'data': bytes, 'changes': [{option, level, prop, line, old, new, stock, other_hardware (True for a line
    in an if-branch this PC does not run)}], 'table': [{prop, what,
    stock, before, after}] at the player's levels, 'levels', 'source', 'source_label', 'problems' (lines that
    could not be tuned, e.g. a value made of variables)}."""
    target = target or os.path.join(sims, 'ConfigOverride', 'GraphicsRules.sgr')
    stock_path = os.path.join(game_bin, 'GraphicsRules.sgr')
    if not os.path.isfile(stock_path):
        raise FileNotFoundError(stock_path)
    with open(source, 'rb') as f:
        data = f.read()
    bom = b'\xef\xbb\xbf' if data.startswith(b'\xef\xbb\xbf') else b''
    text = _strip_speedkit(data[len(bom):].decode('latin-1'))        # latin-1: every byte round-trips
    levels = _levels(sims) if levels is None else {k.lower(): v for k, v in levels.items()}
    machine = settings_sgr.machine_vars(os.path.join(sims, 'Config.log'))
    stock = settings_sgr.evaluate(stock_path, machine)
    base = settings_sgr.evaluate(target, machine, text=text)
    me = os.path.normcase(os.path.abspath(target))
    lines = text.splitlines(keepends=True)
    new_lines = list(lines)
    changes, problems, want, want_dormant = [], [], {}, {}
    # every assignment: the ones this PC runs (where) and the ones in if-branches only other hardware runs
    # (dormant: another GPU vendor - this laptop also has an AMD iGPU -, less memory...), capped the same way
    assignments = [(k, v, False) for k, v in base.where.items()] + [(k, v, True) for k, v in base.dormant.items()]
    for (option, level, prop), places, dormant in assignments:
        if prop not in TUNED_PROPS or level == 'integer':
            continue
        if option is not None and level is None:
            problems.extend('line %d: the level of %s in option %s could not be read; left as it is' % (n, prop, option)
                            for _, n in places)
            continue
        rule = TUNED_PROPS[prop][1]
        stock_text = _stock_value(stock, levels, option, level, prop)
        s_nums = _numbers(stock_text) if stock_text is not None else []
        for path, n in places:
            if not dormant:     # the last assignment decides; a line left as it is must evaluate unchanged
                want.pop((option, level, prop), None)
            if os.path.normcase(os.path.abspath(path)) != me:
                problems.append('%s is set in the included file %s (line %d); left as it is' % (prop, path, n))
                continue
            line = lines[n - 1]
            body = line.rstrip('\r\n')
            m = _PROP_LINE.match(body)
            if not m or m.group(2) != prop:
                problems.append('line %d (%s) could not be read; left as it is' % (n, prop))
                continue
            value, tail = _split_value(m.group(3))
            parsed = _parse_numbers(value)
            if parsed is None:
                problems.append('line %d: %s = %s is not a plain number; left as it is' % (n, prop, value))
                continue
            quoted, elements = parsed
            b_nums = [x for x, _ in elements]
            new = rule(b_nums, s_nums)
            if new is None:
                problems.append('line %d: no stock value to tune %s = %s against; left as it is' % (n, prop, value))
                continue
            if dormant:
                want_dormant[n] = [float(x) for x in new]
            else:
                want[(option, level, prop)] = [float(x) for x in new]
            if new == b_nums:
                continue
            new_value = _compose_value(value, quoted, elements, new)
            new_lines[n - 1] = m.group(1) + new_value + tail + line[len(body):]
            changes.append({'option': option, 'level': level, 'prop': prop, 'line': n, 'old': value,
                            'new': new_value, 'stock': stock_text, 'other_hardware': dormant})
    changes.sort(key=lambda c: c['line'])
    eol = '\r\n' if lines and lines[0].endswith('\r\n') else '\n'
    anchor = next((i for i, l in enumerate(lines) if _SGR_FULL_LOG.match(l)), None)
    if anchor is not None:
        log_at = anchor + 1
    else:
        log_at = next((i for i, l in enumerate(lines) if _ANY_LOG.match(l)), None)
    if log_at is not None:
        if log_at > 0 and not new_lines[log_at - 1].endswith(('\n', '\r')):
            new_lines[log_at - 1] += eol
        new_lines.insert(log_at, TUNED_LOG + eol)
    header = [h + eol for h in TUNED_HEADER]
    out_lines = header + new_lines
    out_text = ''.join(out_lines)
    tuned = settings_sgr.evaluate(target, machine, text=out_text)
    bad = _check_tuned(base, tuned, want, changes, levels, lines, out_lines, len(header), log_at, want_dormant)
    if bad:
        raise ValueError('SpeedKit Max Quality check failed for %s: %s' % (source, '; '.join(bad[:5])))
    be, te, se = base.effective(levels), tuned.effective(levels), stock.effective(levels)
    table = [{'prop': p, 'what': TUNED_PROPS[p][0], 'stock': se.get(p, (None,))[0], 'before': be.get(p, (None,))[0],
              'after': te.get(p, (None,))[0]} for p in TUNED_PROPS if p in be or p in te]
    m = re.search(r'\+\+\+\s*(\S+)\s+SGR Full', text)
    label = "Simp4Sims 'SGR Full'%s" % (' (%s)' % m.group(1) if m else '')
    return {'data': bom + out_text.encode('latin-1'), 'changes': changes, 'table': table, 'levels': levels,
            'source': source, 'source_label': label, 'problems': problems}


def tuned_sources(sims=SIMS, home=None):
    """Rules files SpeedKit Max Quality can be made from, best first: ConfigOverride\\GraphicsRules.sgr when it
    is SGR Full or already tuned, then copies SpeedKit moved to its quarantine (newest journal first; in one
    journal the original before a removed tuned copy). Only those two known spots are looked at."""
    out = []
    override = os.path.join(sims, 'ConfigOverride', 'GraphicsRules.sgr')
    if os.path.isfile(override) and _identify(override)[0] in TUNABLE:
        out.append(override)
    q = os.path.join(_home(sims, home), 'quarantine')
    found = []
    if os.path.isdir(q):
        for jid in os.listdir(q):
            # a quarantined original (rank 1) before a tuned file that an undo moved away (rank 0)
            for rank, parts in ((1, ('ConfigOverride',)), (0, ('_undone_new', 'ConfigOverride'))):
                p = os.path.join(q, jid, *parts, 'GraphicsRules.sgr')
                if os.path.isfile(p) and _identify(p)[0] in TUNABLE:
                    found.append((jid, rank, p))
    found.sort(reverse=True)
    return out + [p for _, _, p in found]


def graphics_tuned_table(sims=SIMS, home=None, game_bin=GAME_BIN):
    """Read-only before/after table for reports: [{prop, what, stock, before (the user's SGR Full), after
    (SpeedKit Max Quality)}] at the player's levels. Uses the original SGR Full from ConfigOverride or, once
    SpeedKit Max Quality is installed, from SpeedKit's quarantine; [] when no original SGR Full is found."""
    for p in tuned_sources(sims, home):
        if _identify(p)[0] == 'simp_sgr_full':
            return build_tuned_rules(p, sims, game_bin)['table']
    return []


def tuned_journal(sims=SIMS, home=None):
    """Id of the newest SpeedKit Max Quality install that was not undone, or None."""
    for jid, kind, state, _, note in reversed(journals(sims, home)):
        if kind == 'settings' and state == 'committed' and note.startswith(TUNED_NOTE):
            return jid
    return None


def graphics_use_tuned(dry_run=True, sims=SIMS, home=None, check_game=True, game_bin=GAME_BIN, source=None,
                       replace_other=False):
    """Install 'SpeedKit Max Quality' as ConfigOverride\\GraphicsRules.sgr: SGR Full with only the lag-causing
    values tuned (see TUNED_PROPS). Options.ini is never touched (the in-game settings stay at Ultra).

    The source is `source`, else ConfigOverride's own file when it is SGR Full or already tuned, else the newest
    SGR Full copy in SpeedKit's quarantine (e.g. after graphics_use_stock). Another rules file in ConfigOverride
    (the Setters, anything custom) is never replaced unless replace_other=True. Idempotent: when ConfigOverride
    already holds exactly the tuned file, nothing happens (action 'none', no journal).

    Returns the plan {'action': 'add'|'replace'|'none'|'refused', 'refused' (why), 'actions', 'target',
    'active', 'active_label', 'source', 'source_label', 'levels', 'changes', 'table' (stock / before / after at
    the player's levels), 'problems' (lines that could not be tuned; also in notes), 'notes', 'journal', 'dry_run',
    'game_running'}. The real run goes through a Journal
    (kind 'settings'): the old file is quarantined, never deleted; undo with graphics_restore(journal)."""
    home = _home(sims, home)
    override = os.path.join(sims, 'ConfigOverride', 'GraphicsRules.sgr')
    exists = os.path.isfile(override)
    current = None                  # the bytes everything below is planned from
    if exists:
        with open(override, 'rb') as f:
            current = f.read()
    kind, label = _identify(override) if exists else ('stock', "the game's own rules")
    plan = {'dry_run': dry_run, 'journal': None, 'action': None, 'refused': None, 'actions': [], 'target': override,
            'active': kind, 'active_label': label, 'source': None, 'source_label': None, 'levels': _levels(sims),
            'changes': [], 'table': [], 'problems': [], 'notes': [],
            'game_running': game_running() if check_game else False}

    def refuse(why):
        plan['action'], plan['refused'] = 'refused', why
        return plan

    if not os.path.isfile(os.path.join(game_bin, 'GraphicsRules.sgr')):
        return refuse('The game\'s own rules (%s) were not found; SpeedKit needs their values to tune against.'
                      % os.path.join(game_bin, 'GraphicsRules.sgr'))
    if exists and kind not in TUNABLE and not replace_other:
        return refuse('ConfigOverride\\GraphicsRules.sgr is %s, not SGR Full. SpeedKit leaves your own rules file '
                      'alone (replace_other=True would replace it; it would be kept in quarantine).' % label)
    if source is not None:
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        if _identify(source)[0] not in TUNABLE:
            raise ValueError('%s is %s, not Simp4Sims SGR Full' % (source, _identify(source)[1]))
    else:
        found = tuned_sources(sims, home)
        source = found[0] if found else None
    if source is None:
        return refuse('No Simp4Sims SGR Full rules file was found (not in ConfigOverride, not in SpeedKit\'s '
                      'quarantine); SpeedKit Max Quality is made from it.')
    t = build_tuned_rules(source, sims, game_bin, target=override)
    plan.update(source=source, source_label=t['source_label'], changes=t['changes'], table=t['table'],
                problems=t['problems'])
    plan['notes'].extend(t['problems'])
    other = sum(1 for c in t['changes'] if c.get('other_hardware'))
    if other:
        plan['notes'].append('%d of the changed lines are in parts of the file this PC does not use (another graphics '
                             'card or less memory); they get the same caps.' % other)
    if exists:
        if current == t['data']:
            plan['action'] = 'none'
            plan['note'] = 'ConfigOverride already holds %s.' % TUNED_LABEL
            return plan
        if kind == 'speedkit_tuned' and t['changes']:
            plan['notes'].append('The %s file was edited after SpeedKit wrote it; %d values above SpeedKit\'s caps are '
                                 'put back.' % (TUNED_LABEL, len(t['changes'])))
    plan['action'] = 'replace' if exists else 'add'
    plan['actions'] = ([('quarantine', override)] if exists else []) + [('install ' + TUNED_LABEL, override)]
    plan['bytes'] = len(t['data'])
    if dry_run:
        if plan['game_running']:
            plan['notes'].append('The Sims 4 is running: the real run will refuse until it is closed.')
        return plan
    if check_game and game_running():
        raise JournalError('The Sims 4 is running - close it first.')
    now = None
    if os.path.isfile(override):
        with open(override, 'rb') as f:
            now = f.read()
    if now != current:
        raise JournalError('ConfigOverride\\GraphicsRules.sgr changed while SpeedKit was preparing; nothing was '
                           'changed - run it again.')
    j = _open_journal('settings', '%s (from %s)' % (TUNED_NOTE, t['source_label']), sims, home, check_game)
    with j:
        stage = _staging(home, j.id)
        tmp = os.path.join(stage, 'GraphicsRules.sgr')
        with open(tmp, 'wb') as f:
            f.write(t['data'])
        if exists:
            j.replace(tmp, override)
        else:
            j.put_new(tmp, override)
    _drop_empty_dir(stage)
    with open(override, 'rb') as f:
        if f.read() != t['data']:
            raise JournalError('%s does not read back as written; undo with graphics_restore(%r)' % (override, j.id))
    plan['journal'] = j.id
    return plan


def graphics_restore(journal_id=None, dry_run=True, sims=SIMS, home=None, check_game=True):
    """Undo graphics_use_tuned / graphics_use_stock / graphics_use_preset (journal.undo).

    journal_id None = the newest SpeedKit Max Quality install that was not undone (JournalError if none)."""
    if journal_id is None:
        journal_id = tuned_journal(sims, home)
        if journal_id is None:
            raise JournalError('there is no %s install to undo' % TUNED_LABEL)
    return restore(journal_id, dry_run=dry_run, sims=sims, home=home, check_game=check_game)


# ============================================================================================ caches
# name -> (file or folder under the Sims 4 folder, what it holds, when to clean it)
CACHES = {
    'localthumbcache': ('localthumbcache.package', 'thumbnails of Build/Buy and CAS items',
                        'after adding or removing CC (stale or missing thumbnails); the game rebuilds it'),
    'localsimtexturecache': ('localsimtexturecache.package', 'finished Sim textures (100 MB cap; it speeds up showing Sims)',
                             'optional - only if Sims show wrong textures'),
    'avatarcache': ('avatarcache.package', 'Sim portraits for the UI', 'optional'),
    'cachestr': ('cachestr', 'cached Gallery/online text', 'optional'),
    'onlinethumbnailcache': ('onlinethumbnailcache', 'thumbnails downloaded from the Gallery', 'optional'),
}
# Never touched by caches_clean, whatever is asked.
NEVER_TOUCH = ('saves', 'Tray', 'Options.ini', 'UserSetting.ini', 'accountDataDB.package', 'notify.glob',
               'content', 'ConfigOverride', 'Mods', 'Mods_parked', 'SpeedKit')


def _inside(path, base):
    path, base = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(base))
    return path == base or path.startswith(base.rstrip('\\/') + os.sep)


def _cache_files(sims, name):
    p = os.path.join(sims, CACHES[name][0])
    if os.path.isfile(p):
        return [p]
    out = []
    if os.path.isdir(p):
        for dp, _, fn in os.walk(p):
            out.extend(os.path.join(dp, n) for n in sorted(fn))
    return out


def _size(p):
    """File size, 0 if the file went away meanwhile (the Mods switch tool moves localthumbcache)."""
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def caches_status(sims=SIMS):
    """Size of each known cache and the old thumbnail caches the Mods switch parked (read-only)."""
    rows = []
    for name, (rel, what, when) in CACHES.items():
        files = _cache_files(sims, name)
        rows.append({'name': name, 'path': os.path.join(sims, rel), 'files': len(files),
                     'bytes': sum(_size(f) for f in files), 'what': what, 'when': when})
    old = os.path.join(sims, 'Mods_parked', '_old_caches')
    parked = [os.path.join(old, n) for n in os.listdir(old)] if os.path.isdir(old) else []
    return {'caches': rows,
            'parked_old_caches': {'path': old, 'files': len(parked), 'bytes': sum(_size(p) for p in parked
                                                                                 if os.path.isfile(p)),
                                  'note': 'moved there by the Mods switch tool; not mods, not touched by SpeedKit'},
            'note': 'None of these caches makes startup faster (research); clean localthumbcache after CC changes.'}


def caches_clean(which=('localthumbcache',), dry_run=True, sims=SIMS, home=None, check_game=True):
    """Quarantine (never delete) the named caches: any of CACHES. Folders keep existing, their files move.

    Returns {'actions': [(action, path)], 'bytes', 'journal', 'dry_run'}; undo with restore(journal)."""
    if isinstance(which, str):
        which = (which,)
    which = list(dict.fromkeys(which))          # a name given twice is cleaned once
    bad = [w for w in which if w not in CACHES]
    if bad:
        raise ValueError('not a cache SpeedKit cleans: %s (known: %s)' % (', '.join(bad), ', '.join(CACHES)))
    targets = []
    for w in which:
        for p in _cache_files(sims, w):
            if not _inside(p, sims) or any(_inside(p, os.path.join(sims, n)) for n in NEVER_TOUCH):
                raise JournalError('refusing to touch %s' % p)
            targets.append(p)
    plan = {'dry_run': dry_run, 'journal': None, 'which': list(which), 'actions': [('quarantine', p) for p in targets],
            'bytes': sum(_size(p) for p in targets),
            'game_running': game_running() if check_game else False}
    if not targets:
        plan['note'] = 'nothing to clean'
        return plan
    if dry_run:
        return plan
    j = _open_journal('caches', 'caches: quarantine %s' % ', '.join(which), sims, home, check_game)
    with j:
        for p in targets:
            j.quarantine(p)
    plan['journal'] = j.id
    return plan


# ============================================================================================ preflight
class _MemoryStatus(ctypes.Structure):
    _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]


def memory_status():
    """RAM and commit charge in MB (GlobalMemoryStatusEx). Commit limit = RAM + page files."""
    m = _MemoryStatus()
    m.dwLength = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        raise OSError('GlobalMemoryStatusEx failed')
    mb = 1 << 20
    return {'ram_total_mb': m.ullTotalPhys // mb, 'ram_available_mb': m.ullAvailPhys // mb, 'load_percent': m.dwMemoryLoad,
            'commit_limit_mb': m.ullTotalPageFile // mb,
            'commit_used_mb': (m.ullTotalPageFile - m.ullAvailPageFile) // mb}


_PS = ('$p = Get-Process | Select-Object Id,ProcessName,SessionId,PrivateMemorySize64,WorkingSet64; '
       '$f = Get-CimInstance Win32_PageFileUsage | Select-Object Name,AllocatedBaseSize,CurrentUsage,PeakUsage; '
       '@{p=@($p); f=@($f)} | ConvertTo-Json -Compress -Depth 3')


def process_memory():
    """({'processes': [{pid, name, session, private_mb, working_set_mb}], 'pagefiles': [...]}, source).

    Uses PowerShell Get-Process (private memory); falls back to tasklist (working set only).
    Session 0 holds Windows services, which the user cannot simply close."""
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        out = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _PS], capture_output=True,
                             text=True, timeout=90, creationflags=flags).stdout
        d = json.loads(out)
        procs = [{'pid': p['Id'], 'name': p['ProcessName'], 'session': p.get('SessionId'),
                  'private_mb': (p['PrivateMemorySize64'] or 0) / 1048576,
                  'working_set_mb': (p['WorkingSet64'] or 0) / 1048576} for p in d.get('p') or []]
        pf = [{'name': f['Name'], 'allocated_mb': f['AllocatedBaseSize'], 'current_mb': f['CurrentUsage'],
               'peak_mb': f['PeakUsage']} for f in d.get('f') or []]
        return {'processes': procs, 'pagefiles': pf}, 'Get-Process (private memory)'
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=60,
                         creationflags=flags).stdout
    procs = []
    for row in out.splitlines():
        cols = [c.strip('"') for c in row.split('","')]
        if len(cols) >= 5:
            kb = int(re.sub(r'\D', '', cols[4]) or 0)
            procs.append({'pid': int(cols[1]), 'name': re.sub(r'\.exe$', '', cols[0], flags=re.I),
                          'session': _as_int(cols[3]), 'private_mb': kb / 1024, 'working_set_mb': kb / 1024})
    return {'processes': procs, 'pagefiles': []}, 'tasklist (working set; private memory unknown)'


APP_NAMES = {'chrome': 'Chrome', 'msedge': 'Edge', 'brave': 'Brave', 'firefox': 'Firefox', 'opera': 'Opera',
             'discord': 'Discord', 'claude': 'Claude', 'code': 'VS Code', 'spotify': 'Spotify', 'steam': 'Steam',
             'steamwebhelper': 'Steam', 'ms-teams': 'Teams', 'teams': 'Teams', 'slack': 'Slack', 'obs64': 'OBS',
             'explorer': 'Windows Explorer', 'whatsapp': 'WhatsApp', 'telegram': 'Telegram', 'zoom': 'Zoom',
             'eadesktop': 'EA app', 'python': 'Python', 'node': 'Node.js', 'blender': 'Blender',
             's4studio': 'Sims 4 Studio', 'ts4_x64': 'The Sims 4'}
SYSTEM = {'system', 'registry', 'memory compression', 'idle', 'secure system', 'msmpeng', 'dwm', 'csrss', 'svchost',
          'lsass', 'wininit', 'services', 'smss', 'vmmem', 'vmmemwsl', 'searchindexer', 'ts4_x64'}


def _parked_state(sims):
    parked = os.path.join(sims, 'Mods_parked')
    out = {'path': parked, 'files': 0, 'bytes': 0, 'manifest_items': None, 'lean': False}
    if not os.path.isdir(parked):
        return out
    man = os.path.join(parked, '_manifest.json')
    if os.path.exists(man):
        try:
            with open(man, encoding='utf-8') as f:
                moved = json.load(f).get('moved', [])
            out['manifest_items'] = len(moved) if isinstance(moved, list) else None
        except (OSError, ValueError, AttributeError):       # AttributeError: not a {"moved": [...]} object
            out['manifest_items'] = None
    for dp, dn, fn in os.walk(parked):
        dn[:] = [d for d in dn if d != '_old_caches']
        for n in fn:
            if n.lower().endswith(('.package', '.ts4script')):
                out['files'] += 1
                try:
                    out['bytes'] += os.path.getsize(os.path.join(dp, n))
                except OSError:
                    pass
    out['lean'] = out['files'] > 0
    return out


def _last_start_free_mb(sims):
    log = os.path.join(sims, 'Config.log')
    if not os.path.exists(log):
        return None
    with open(log, encoding='utf-8', errors='replace') as f:
        m = re.search(r'^Free memory:\s*(\d+)MB', f.read(20000), re.M)
    return int(m.group(1)) if m else None


def preflight(sims=SIMS, processes=True, top=10, game_bin=None):
    """Memory and disk report before playing, with plain warnings. Reads only; never closes anything.
    game_bin: the game's Game\\Bin folder (the Hub passes the one it found; default GAME_BIN).

    Returns {'memory', 'pagefiles', 'top_processes', 'apps', 'disk', 'game_running', 'parked',
    'last_start_free_mb', 'graphics', 'warnings', 'ok'}."""
    game_bin = game_bin or GAME_BIN
    rep = {'memory': memory_status(), 'pagefiles': [], 'top_processes': [], 'apps': [], 'warnings': [], 'notes': []}
    mem = rep['memory']
    procs = []
    if processes:
        pm, rep['process_source'] = process_memory()
        procs, rep['pagefiles'] = pm['processes'], pm['pagefiles']
        rep['top_processes'] = sorted(procs, key=lambda p: -p['private_mb'])[:top]
        apps = {}
        for p in procs:
            key = p['name'].lower()
            a = apps.setdefault(APP_NAMES.get(key, p['name']), {'name': APP_NAMES.get(key, p['name']), 'count': 0,
                                                               'private_mb': 0.0, 'system': key in SYSTEM,
                                                               'service': True})
            a['service'] = a['service'] and p.get('session') == 0      # every process in session 0
            a['count'] += 1
            a['private_mb'] += p['private_mb']
        rep['apps'] = sorted(apps.values(), key=lambda a: -a['private_mb'])[:top]
    rep['game_running'] = game_running() or any(p['name'].lower() == 'ts4_x64' for p in procs)
    disk = {}
    for d in ('C:\\', os.path.splitdrive(os.path.abspath(game_bin))[0] + '\\'):
        try:
            u = shutil.disk_usage(d)
            disk[d[0]] = {'free_gb': u.free / 2 ** 30, 'total_gb': u.total / 2 ** 30}     # GB as Explorer shows them
        except OSError:
            pass
    rep['disk'] = disk
    rep['parked'] = _parked_state(sims)
    rep['last_start_free_mb'] = _last_start_free_mb(sims)
    try:
        g = graphics_status(sims, game_bin)
        rep['graphics'] = {'active': g['active'], 'label': g['label'], 'heavier': g['heavier'],
                           'tuned_ok': bool(g['tuned'] and g['tuned']['ok']), 'tune_action': g['tune']['action']}
    except Exception as e:                  # a hint only: an odd rules file must not stop preflight/launch
        rep['graphics'] = None
        rep['notes'].append('Graphics rules could not be read (%s: %s).' % (type(e).__name__, e))

    w = rep['warnings']
    if rep['game_running']:
        w.append('The Sims 4 is already running.')
    if mem['ram_available_mb'] < 3072:
        w.append('Only %.1f GB of %.1f GB memory is free. The game needs about 4 GB, and more with all your CC - '
                 'close some programs for a smoother start.' % (mem['ram_available_mb'] / 1024, mem['ram_total_mb'] / 1024))
    for a in rep['apps']:
        if a['system'] or a['private_mb'] < 1024 or a['name'] == 'The Sims 4':
            continue
        many = ' (%d processes)' % a['count'] if a['count'] > 1 else ''
        if a['name'] == 'Windows Explorer':
            w.append('Windows Explorer uses %.1f GB - restarting it (or the PC) gives that back.' % (a['private_mb'] / 1024))
        elif a['name'] == 'Claude':
            w.append('Claude uses %.1f GB%s - close the sessions you do not need before playing.' % (a['private_mb'] / 1024, many))
        elif a['service']:
            w.append('The background service %s uses %.1f GB - restarting the PC gives that back.'
                     % (a['name'], a['private_mb'] / 1024))
        else:
            w.append('%s uses %.1f GB%s - close it before playing.' % (a['name'], a['private_mb'] / 1024, many))
    if mem['commit_limit_mb'] and mem['commit_used_mb'] > 0.8 * mem['commit_limit_mb']:
        w.append('Committed memory is %.1f of %.1f GB: Windows is close to running out of memory.'
                 % (mem['commit_used_mb'] / 1024, mem['commit_limit_mb'] / 1024))
    used_pf = sum(p['current_mb'] or 0 for p in rep['pagefiles'])
    if used_pf > 4096:
        w.append('%.1f GB of memory sits in the page file; the game stutters whenever it has to read that back.'
                 % (used_pf / 1024))
    c = disk.get('C')
    if c and (c['free_gb'] < 30 or c['free_gb'] < 0.1 * c['total_gb']):
        mods_on_c = os.path.splitdrive(os.path.abspath(sims))[0].upper() == 'C:'
        w.append('C: has only %.0f GB free (%.0f%%); it holds the page file%s.'
                 % (c['free_gb'], 100 * c['free_gb'] / c['total_gb'], ' and the Mods folder' if mods_on_c else ''))
    if rep['last_start_free_mb'] is not None and rep['last_start_free_mb'] < 2048:
        rep['notes'].append('At the last game start only %d MB was free (Config.log).' % rep['last_start_free_mb'])
    gr = rep['graphics']
    if gr and gr['active'] == 'speedkit_tuned':
        rep['notes'].append('Graphics rules: %s%s.' % (gr['label'], '' if gr['tuned_ok'] else
                                                       ' - edited since, some lag values are back (see graphics status)'))
    elif gr and gr['active'] != 'stock':
        rep['notes'].append('Graphics rules: %s - %d settings heavier than stock (see graphics status).'
                            % (gr['label'], gr['heavier']))
    pk = rep['parked']
    if pk['lean']:
        rep['notes'].append('Lean mod set: %d mod files (%.0f GB) are parked in Mods_parked and will not load.'
                            % (pk['files'], pk['bytes'] / 2 ** 30))
    rep['ok'] = not w
    return rep


# ============================================================================================ CLI
def _gb(mb):
    return '%.1f GB' % (mb / 1024)


def _print_graphics(g):
    print('Graphics rules: %s' % g['label'])
    if g.get('preset'):
        print('  preset: %s' % g['preset'])
    for f in g['files']:
        print('  ConfigOverride\\%-22s %8d bytes  %s' % (f['name'], f['size'], 'loaded' if f['loaded'] else 'NOT loaded'))
    if g.get('config_log'):
        print('  Config.log first line: %r (%s)' % (g['config_log']['first_line'],
                                                    'matches' if g['config_log']['matches'] else 'does not match'))
    if g.get('tuned'):
        t = g['tuned']
        print('  %s: %s; loaded at the last game start: %s' % (
            TUNED_LABEL, 'values as SpeedKit set them' if t['ok'] else 'EDITED (%s)' % ', '.join(t['over'][:4]),
            'yes (Config.log)' if t['confirmed'] else 'not yet confirmed'))
    elif g.get('tune'):
        print('  %s: %s%s' % (TUNED_LABEL, {'add': 'can be installed', 'replace': 'can be installed',
                                            'none': 'active'}.get(g['tune']['action'], 'not available'),
                              (' - ' + g['tune']['reason']) if g['tune'].get('reason') else ''))
    if g['differences']:
        print('  Differences from stock at your settings (%d heavier, %d lighter):' % (g['heavier'], g['lighter']))
        for d in g['differences']:
            print('   - ' + d['plain'])
    for n in g['notes']:
        print('  * ' + n)


def _level_words(levels):
    names = [('simquality', 'Sim detail'), ('objectquality', 'Object detail'), ('lightingquality', 'Lighting'),
             ('generalreflections', 'Reflections'), ('edgesmoothing', 'Edge smoothing'), ('viewdistance', 'View distance'),
             ('terrainquality', 'Terrain')]
    return ', '.join('%s %s' % (label, _meaning(k, levels[k])) for k, label in names if k in levels)


def _print_tuned(p):
    """Print a graphics_use_tuned plan: what happens and the stock / before / after table at the player's levels."""
    head = {'refused': 'NOT INSTALLED - nothing changed', 'none': 'nothing to do'}.get(
        p['action'], 'DRY RUN - nothing changed' if p['dry_run'] else 'done')
    print('%s%s' % (head, (', journal %s' % p['journal']) if p.get('journal') else ''))
    print('  %s: %s' % ('now active', p['active_label']))
    if p['refused']:
        print('  ! not installed: ' + p['refused'])
        return
    print('  %s from %s (%s)' % (TUNED_LABEL, p['source_label'], p['source']))
    for a in p['actions']:
        print('  %-30s %s' % a)
    if p['table']:
        print('  at your settings (%s):' % (_level_words(p['levels']) or 'Options.ini not found'))
        print('    %-26s %-22s %-32s %s' % ('property', 'stock', 'before', 'after'))
        for r in p['table']:
            print('    %-26s %-22s %-32s %s%s' % (r['prop'], r['stock'], r['before'], r['after'],
                                                 '' if _norm(r['before']) == _norm(r['after']) else '   <- tuned'))
    print('  %d lines of the rules file change (these values at every level of their options); every other '
          'line stays as it is.' % len(p['changes']))
    for n in p['notes'] + ([p['note']] if p.get('note') else []):
        print('  * ' + n)


def _print_options(o):
    print('Options.ini (%s)' % o['path'])
    for s in o['settings']:
        extra = ('  -> %s (%s)' % (s['suggested'], s['suggested_meaning'])) if 'suggested' in s else ''
        print('  %-26s %-6s %-14s%s' % (s['label'], s['value'], s['meaning'], extra))
    for n in o['notes']:
        print('  * ' + n)


def _print_caches(c):
    print('Caches')
    for r in c['caches']:
        print('  %-22s %3d files %9.1f MB  %s' % (r['name'], r['files'], r['bytes'] / 1e6, r['when']))
    p = c['parked_old_caches']
    print('  (Mods_parked\\_old_caches: %d files, %.1f MB - %s)' % (p['files'], p['bytes'] / 1e6, p['note']))


def _print_preflight(r):
    m = r['memory']
    print('Memory: %s free of %s, commit %s of %s' % (_gb(m['ram_available_mb']), _gb(m['ram_total_mb']),
                                                     _gb(m['commit_used_mb']), _gb(m['commit_limit_mb'])))
    for p in r['pagefiles']:
        print('  page file %s: %s in use (peak %s) of %s' % (p['name'], _gb(p['current_mb']), _gb(p['peak_mb']),
                                                            _gb(p['allocated_mb'])))
    print('  biggest apps (private memory, %s):' % r.get('process_source', ''))
    for a in r['apps'][:8]:
        print('    %-22s %8s  %3d process(es)' % (a['name'], _gb(a['private_mb']), a['count']))
    for d, u in r['disk'].items():
        print('  %s: %.0f GB free of %.0f GB' % (d, u['free_gb'], u['total_gb']))
    print('  game running: %s' % r['game_running'])
    for n in r['notes']:
        print('  * ' + n)
    for w in r['warnings']:
        print('  ! ' + w)


def _print_plan(p):
    print('%s%s' % ('DRY RUN - nothing changed' if p['dry_run'] else 'done', (', journal %s' % p['journal']) if p.get('journal') else ''))
    for a in p.get('actions', []):
        print('  %-18s %s' % a)
    for c in p.get('changes', []):
        print('  %-26s %s (%s) -> %s (%s)' % (c['label'], c['old'], c['old_meaning'], c['new'], c['new_meaning']))
    for d in p.get('preview', []):
        print('  after: ' + d['plain'])
    for n in p.get('notes', []) + ([p['note']] if p.get('note') else []):
        print('  * ' + n)
    if p.get('game_running'):
        print('  ! The Sims 4 is running - the real run refuses until it is closed.')


def main(argv=None):
    """python -m speedkit.settings <command> [--apply]

    status | graphics | options [preset] | caches | preflight | journals
    use-tuned (SpeedKit Max Quality) | use-stock | use-preset [name] | graphics-restore [journal id]
    options-apply [preset] [display] | caches-clean [name ...] | restore <journal id>
    Changes happen only with --apply."""
    args = list(sys.argv[1:] if argv is None else argv)
    apply = '--apply' in args
    args = [a for a in args if a != '--apply']
    cmd = args[0] if args else 'status'
    rest = args[1:]
    if cmd == 'status':
        _print_graphics(graphics_status()); print()
        _print_options(options_status()); print()
        _print_caches(caches_status()); print()
        _print_preflight(preflight())
    elif cmd == 'graphics':
        _print_graphics(graphics_status())
    elif cmd == 'options':
        _print_options(options_status(preset=rest[0] if rest else 'balanced'))
    elif cmd == 'caches':
        _print_caches(caches_status())
    elif cmd == 'preflight':
        _print_preflight(preflight())
    elif cmd == 'journals':
        for j in journals():
            print('  %s  %-8s %-10s %3d steps  %s' % j)
    elif cmd in ('use-tuned', 'tuned'):
        p = graphics_use_tuned(dry_run=not apply)
        _print_tuned(p)
        return 1 if p['refused'] else 0
    elif cmd == 'graphics-restore':
        acts = graphics_restore(rest[0] if rest else None, dry_run=not apply)
        print(('DRY RUN - ' if not apply else '') + 'undo:')
        for a in acts:
            print('  %-40s %s' % a)
    elif cmd == 'use-stock':
        _print_plan(graphics_use_stock(dry_run=not apply))
    elif cmd == 'use-preset':
        _print_plan(graphics_use_preset(' '.join(rest) or 'Ultimate Performance', dry_run=not apply))
    elif cmd == 'options-apply':
        _print_plan(options_apply(rest[0] if rest else 'balanced', dry_run=not apply,
                                  display=rest[1] if len(rest) > 1 else 'auto'))
    elif cmd == 'caches-clean':
        _print_plan(caches_clean(tuple(rest) or ('localthumbcache',), dry_run=not apply))
    elif cmd == 'restore':
        if not rest:
            print('restore needs a journal id (see: journals)')
            return 2
        acts = restore(rest[0], dry_run=not apply)
        print(('DRY RUN - ' if not apply else '') + 'undo %s:' % rest[0])
        for a in acts:
            print('  %-40s %s' % a)
    else:
        print(main.__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

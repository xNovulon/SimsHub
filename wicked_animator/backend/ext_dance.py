"""Strip-club dances (R3-4) - loaded by server.py like every backend/ext_*.py:

    GET  /api/dance_info             what a dance can be (types, the pole, the spot, the seats for a lap dance)
    GET  /api/dance_pole             WickedWhims' own dance pole as a mesh (read from its tuning package; 404 if absent)
    GET  /api/dance_spot             WickedWhims' dance spot mark as a mesh (404 if absent)
    POST /api/dance_export           {baked, mode: 'send' | 'mod' | 'check'} -> writes the strip-club package
                                     ('check' only builds it in memory and answers the XML and the clip names)

The package holds the dancer's clip (and the watcher's for a lap dance), written by the app's own clip writer, and
the StripClubDanceAnimationPackage XML (backend/stripclub.py). Writes only on a click in the app; a test server with
WICKED_EXPORTS_DIR writes into that folder instead (like ext_share.py).
"""
import stripclub as S


def _info(q):
    return S.info()


def _pole(q):
    m = S.pole_mesh()
    if not m:
        raise LookupError("WickedWhims' dance pole was not found (is WickedWhims in your Mods folder?)")
    return m


def _spot(q):
    m = S.spot_mesh()
    if not m:
        raise LookupError("WickedWhims' dance spot was not found")
    return m


def _export(body, q):
    if not isinstance(body, dict) or not isinstance(body.get('baked'), dict):
        raise ValueError('Send the dance as {baked, mode}.')
    mode = str(body.get('mode') or 'send')
    if mode not in ('send', 'mod', 'check'):
        raise ValueError('mode must be send, mod or check')
    baked = body['baked']
    if mode == 'check':
        resources, info = S.dance_resources(baked)
        return {'ok': True, 'mode': 'check', 'package': info['base'] + '.package', 'clips': info['clips'],
                'type': info['type'], 'genders': info['genders'], 'loops': info['loops'], 'seconds': info['seconds'],
                'total_seconds': info['total_seconds'], 'set': info['set'], 'xml': info['xml'],
                'bytes': len(S.build_package(resources))}
    try:
        return S.export_dance(baked, mode)
    except RuntimeError as ex:          # the game has the file open, a disk error: said plainly
        raise ValueError(str(ex))


GET = {'dance_info': _info, 'dance_pole': _pole, 'dance_spot': _spot}
POST = {'dance_export': _export}

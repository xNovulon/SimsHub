"""Your own sounds (mysounds.py) - loaded by server.py like every backend/ext_*.py:

    POST /api/my_sound?name=<file name>&kind=<other|voice>   the sound file as it is -> {name, label, seconds, ...}
    GET  /api/my_sounds                                      your sounds, newest first

They play in the app through /api/sound like every other sound (server.py asks mysounds first for their names).
"""
import mysounds


def _upload(data, ctype, q):
    return mysounds.add(data, q.get('name', ''), q.get('kind', 'other'))


def _list(q):
    return mysounds.list_sounds()


GET = {'my_sounds': _list}
# browsers name sound files audio/wav, audio/mpeg, audio/ogg...; an unknown one comes as application/octet-stream
# (Ogg files are sometimes video/ogg)
POST_RAW = {'my_sound': (_upload, ('audio/', 'application/octet-stream', 'video/ogg'))}

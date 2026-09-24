"""Reference pictures and videos (spec_editing 12) - loaded by server.py like every backend/ext_*.py:

    POST /api/reference?uid=<animation uid>&name=<file name>   the file as it is (image/* or video/*) -> {file, bytes}
    GET  /api/reference_file?uid=<animation uid>&file=<name>   the kept file

The files are kept in saves\\FitStudio\\animator_refs\\<uid> (projects.REFS), named by their content's hash. Exports and
bundles never read them. A test server with ANIMATOR_SAVES or WICKED_PROJECTS_DIR keeps them in that folder instead.
"""
import os

import projects as P


def _upload(data, ctype, q):
    return P.save_ref(q.get('uid', ''), data, ctype)


def _file(q):
    try:
        path = P.ref_path(q.get('uid', ''), q.get('file', ''))
    except FileNotFoundError as ex:
        raise LookupError(str(ex))
    ext = os.path.splitext(path)[1][1:].lower()
    with open(path, 'rb') as f:
        return f.read(), P.REF_TYPES.get(ext, 'application/octet-stream')


GET = {'reference_file': _file}
POST_RAW = {'reference': (_upload, ('image/', 'video/'))}

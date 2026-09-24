"""Build the package Send to game or Export a mod would write - offline, into %TEMP%, never into Documents.

    python offline_pkg.py <job.json>        -> prints one JSON line (the server's answer for that request)

job = {"kind": "export" | "bundle", "body": <the request the app sent>,
       "projects": [saved project dicts the app knows], "progressions": [...], "out": <folder> (optional)}

The saved animations and progressions a test kept in its memory (harness memory mode) are written into a fresh
saves folder in %TEMP% (ANIMATOR_SAVES), so progression links and "only through the chain" resolve exactly as on the
server; the exporter's output folders (Mods\\FitStudio\\MyAnimations, Documents\\Wicked Animator Exports) are pointed
into the same temp folder. Nothing outside %TEMP% is written.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')


def run(job):
    tmp = job.get('out') or tempfile.mkdtemp(prefix='wa_offline_')
    tmp = os.path.abspath(tmp)
    if not tmp.lower().startswith(os.path.abspath(tempfile.gettempdir()).lower()):
        raise ValueError('offline packages are only built inside %TEMP%')
    saves = os.path.join(tmp, 'saves')
    os.makedirs(saves, exist_ok=True)
    os.environ['ANIMATOR_SAVES'] = saves          # read by projects.py when it is imported (below)
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    import projects as P
    import exporter as X
    import wwpackage as W
    assert os.path.abspath(P.ROOT).lower().startswith(tmp.lower()), P.ROOT
    X.MY_ANIMATIONS = os.path.join(tmp, 'MyAnimations')
    X.EXPORTS = os.path.join(tmp, 'Wicked Animator Exports')
    os.makedirs(X.MY_ANIMATIONS, exist_ok=True)
    os.makedirs(X.EXPORTS, exist_ok=True)
    for d in job.get('projects') or []:
        P.save(dict(d))
    if job.get('progressions') is not None:
        P.save_progressions(job.get('progressions') or [])
    body = job['body']
    if job['kind'] == 'export':
        resources, info = X.animation_resources(body)
        path = os.path.join(X.MY_ANIMATIONS, info['base'] + '.package')
        data = W.build_package(resources)
        with open(path, 'wb') as f:
            f.write(data)
        return {'path': path, 'package': info['base'] + '.package', 'clips': info['clips'], 'bytes': len(data),
                'next': info['next'], 'next_names': info['next_names'], 'random': info['random'], 'warnings': info['warnings'],
                'folder': tmp}
    if job['kind'] == 'bundle':
        body = dict(body)
        body['install'] = False                     # installing would write into the Mods folder
        res = X.bundle(body)
        res['tmp'] = tmp
        return res
    raise ValueError('unknown kind %r' % job['kind'])


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as f:
        job = json.load(f)
    try:
        out = run(job)
    except Exception as ex:
        import traceback
        out = {'error': str(ex) or repr(ex), 'trace': traceback.format_exc()}
    print(json.dumps(out))

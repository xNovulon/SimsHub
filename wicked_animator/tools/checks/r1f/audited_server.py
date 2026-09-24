"""R1-F: run backend/server.py with a Python audit hook that logs every write the server does (file opens for
writing, renames, removals, new folders) to the file named by R1F_AUDIT_LOG, one JSON line each. Used by
game_check.py for "nothing is written outside cache/ and %TEMP%"."""
import json, os, runpy, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_fd = os.open(os.environ['R1F_AUDIT_LOG'], os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_BINARY', 0))
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
_busy = [False]


def _log(kind, path):
    if isinstance(path, bytes):
        path = path.decode('utf-8', 'replace')
    if not isinstance(path, str):
        return
    os.write(_fd, (json.dumps({'kind': kind, 'path': os.path.abspath(path)}) + '\n').encode('utf-8'))


def hook(event, args):
    if _busy[0]:
        return
    _busy[0] = True
    try:
        if event == 'open':
            path, mode, flags = (list(args) + [None, None, None])[:3]
            writes = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or \
                     (mode is None and isinstance(flags, int) and flags & _WRITE_FLAGS)
            if writes:
                _log('open', path)
        elif event in ('os.rename', 'os.replace'):
            _log('rename', args[1])
        elif event in ('os.remove', 'os.rmdir', 'os.mkdir', 'shutil.rmtree', 'os.truncate'):
            _log(event, args[0])
    except Exception:
        pass
    finally:
        _busy[0] = False


sys.addaudithook(hook)
sys.argv = [os.path.join(ROOT, 'backend', 'server.py')]
runpy.run_path(sys.argv[0], run_name='__main__')

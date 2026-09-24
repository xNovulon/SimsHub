"""Test harness for Novulon's Wicked Animator checks (plan 2.9). Every slice may use it.

    import sys; sys.path.insert(0, r'<root>\\tools\\checks\\lib'); import harness as H
    p = H.start_server(8842)                 # ANIMATOR_PORT=8842, waits for /api/status of *this* process
    ...
    H.stop_server(p)
    path = H.offline_export(baked, out_dir)  # exporter.animation_resources + wwpackage.build_package, never into Mods

Ports 8765 (the user's app), 8766 (Sims Hub) and 8777 (verifier) are refused. The server's own output goes to
cache/checks/_servers/port<port>.log.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKEND = os.path.join(ROOT, 'backend')
REFUSED = {8765, 8766, 8777}


class PortBusy(RuntimeError):
    pass


def _status(port, timeout=2.0):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/status' % port, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception:
        return None


def start_server(port, env=None, wait=180, log_dir=None):
    """Start backend/server.py on `port` (in the background, no console window) and wait until it answers.
    Raises PortBusy when another process holds the port (the caller then takes the next free one)."""
    port = int(port)
    if port in REFUSED:
        raise ValueError('port %d belongs to someone else (the user\'s app, the Sims Hub or the verifier)' % port)
    if _status(port, 1.0) is not None:
        raise PortBusy('port %d already answers - another server runs there' % port)
    e = dict(os.environ)
    e.update({k: str(v) for k, v in (env or {}).items()})
    e['ANIMATOR_PORT'] = str(port)
    e['PYTHONUNBUFFERED'] = '1'
    log_dir = log_dir or os.path.join(ROOT, 'cache', 'checks', '_servers')
    os.makedirs(log_dir, exist_ok=True)
    log = open(os.path.join(log_dir, 'port%d.log' % port), 'ab')
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    p = subprocess.Popen([sys.executable, os.path.join(BACKEND, 'server.py')], cwd=ROOT, env=e,
                         stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    p._log = log
    t0 = time.time()
    while time.time() - t0 < wait:
        if p.poll() is not None:
            log.close()
            raise PortBusy('the server on port %d stopped at once (port in use?) - see %s' % (port, log.name))
        s = _status(port)
        if s and s.get('ok'):
            if s.get('pid') not in (None, p.pid):
                stop_server(p)
                raise PortBusy('port %d is answered by another process (pid %s)' % (port, s.get('pid')))
            return p
        time.sleep(0.4)
    stop_server(p)
    raise TimeoutError('the server on port %d did not answer within %d s' % (port, wait))


def free_port(start=8851, stop=8899):
    """The first port in [start, stop) nothing answers on (for when a slice's own port is busy)."""
    import socket
    for port in range(start, stop):
        if port in REFUSED:
            continue
        with socket.socket() as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise PortBusy('no free port between %d and %d' % (start, stop))


def stop_server(p):
    if p is None:
        return
    try:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
    finally:
        try:
            p._log.close()
        except Exception:
            pass


def offline_export(baked, out_dir=None):
    """Build the package Send to game would write, but into `out_dir` (default: a new folder in %TEMP%).
    `baked` is app.bake()'s payload (a dict, or a path to its JSON). -> the .package path."""
    if isinstance(baked, str):
        with open(baked, 'r', encoding='utf-8') as f:
            baked = json.load(f)
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    import exporter
    import wwpackage
    out_dir = out_dir or tempfile.mkdtemp(prefix='wa_export_')
    tmp = os.path.abspath(tempfile.gettempdir()).lower()
    if not os.path.abspath(out_dir).lower().startswith(tmp) and 'cache' not in os.path.abspath(out_dir).lower():
        raise ValueError('offline_export writes only into %TEMP% or the cache folder')
    os.makedirs(out_dir, exist_ok=True)
    resources, info = exporter.animation_resources(baked)
    path = os.path.join(out_dir, info['base'] + '.package')
    with open(path, 'wb') as f:
        f.write(wwpackage.build_package(resources))
    return path


if __name__ == '__main__':
    # python harness.py start <port>   /   python harness.py export <baked.json> [out_dir]
    if len(sys.argv) >= 3 and sys.argv[1] == 'start':
        proc = start_server(int(sys.argv[2]))
        print(json.dumps({'pid': proc.pid, 'port': int(sys.argv[2])}))
        sys.stdout.flush()
        try:
            proc.wait()
        except KeyboardInterrupt:
            stop_server(proc)
    elif len(sys.argv) >= 3 and sys.argv[1] == 'export':
        print(offline_export(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
    else:
        print(__doc__)

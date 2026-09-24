"""Motion capture's server routes (loaded by server.py like every backend/ext_*.py):

    GET  /api/capture_status    what is installed: {installed, missing, bytes_needed, busy, done_bytes, total_bytes, error, ...}
    POST /api/capture_install   starts the one-time download on a background thread; the page polls capture_status

Nothing is downloaded unless the user clicks Download in the app (the POST comes only from the app's own page).
"""
import capture_install


def _status(q):
    return capture_install.status()


def _install(body, q):
    return capture_install.start()


GET = {'capture_status': _status}
POST = {'capture_install': _install}

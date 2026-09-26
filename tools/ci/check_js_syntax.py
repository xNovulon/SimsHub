"""Parses every .js file the two apps' web UIs use, without running any of it.

This is the check `python -m compileall` can't do for us - it only reads Python - and the one that would have caught
the lost ')' in wicked_animator/web/js/home.js (Sep 2026): nothing parsed that file outside of a real browser before
it reached everyone through main.

    python tools/ci/check_js_syntax.py

Almost every file under the two folders below is an ES module (they use import/export), so each one is copied to a
throw-away .mjs and checked with `node --check` (a plain .js defaults to CommonJS without a package.json saying
otherwise, so import/export would look like a syntax error there even when the file is fine). The one classic
script - a Web Worker started with `new Worker(url)`, not `{type: 'module'}` - is checked as it is. vendor/ files are
included: there is only one (TransformControls.js), it is an ES module, and it is not slow to check.
Exits non-zero, and prints every failing file's error, on any syntax error.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIRS = [
    os.path.join(ROOT, 'wicked_animator', 'web', 'js'),
    os.path.join(ROOT, 'sims_hub', 'speedkit', 'hub', 'web', 'js'),
]
MODULE_RX = re.compile(r'^\s*(import|export)\s', re.M)


def js_files():
    for d in DIRS:
        for base, _dirs, files in sorted(os.walk(d)):
            for f in sorted(files):
                if f.endswith('.js'):
                    yield os.path.join(base, f)


def check(path):
    """(ok, detail) - detail is node's own error message when it isn't."""
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    is_module = bool(MODULE_RX.search(text))
    if is_module:
        fd, tmp = tempfile.mkstemp(suffix='.mjs')
        os.close(fd)
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(text)
            r = subprocess.run(['node', '--check', tmp], capture_output=True, text=True)
        finally:
            os.remove(tmp)
    else:
        r = subprocess.run(['node', '--check', path], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def main():
    rel = lambda p: os.path.relpath(p, ROOT).replace('\\', '/')  # noqa: E731
    bad = []
    n = 0
    for path in js_files():
        n += 1
        ok, detail = check(path)
        if not ok:
            bad.append((path, detail))
    if bad:
        print('%d of %d .js file(s) failed to parse:\n' % (len(bad), n))
        for path, detail in bad:
            print('--- %s ---\n%s\n' % (rel(path), detail))
        return 1
    print('%d .js file(s) under %s parsed cleanly' % (n, ', '.join(rel(d) for d in DIRS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

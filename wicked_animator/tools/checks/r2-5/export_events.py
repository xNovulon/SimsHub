"""R2-5 lip-sync export check: build the package Send to game would write, offline into %TEMP% (harness
offline_export), read it back from the .package file (dbpf) and list each clip's events.

    python tools/checks/r2-5/export_events.py <baked.json>
Prints JSON: {package, bytes, actors: [{clip, events: [types], mouth: [...event 19 payloads]}]}
Nothing is written outside %TEMP%.
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
os.environ.setdefault('ANIMATOR_SAVES', os.path.join(tempfile.gettempdir(), 'wa_r25_saves'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))

import clipfmt  # noqa: E402
import dbpf  # noqa: E402
import exporter  # noqa: E402
import harness  # noqa: E402


def main():
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        baked = json.load(f)
    out_dir = tempfile.mkdtemp(prefix='wa_r25_export_')
    pkg = harness.offline_export(baked, out_dir)
    actors = []
    for e in dbpf.read_index(pkg):
        if e['type'] != exporter.T_CLIP:
            continue
        clip = clipfmt.parse_clip(dbpf.read_resource(pkg, e))
        evs = clip.get('events') or []
        actors.append({'clip': clip['codec']['name'], 'events': sorted({x[0] for x in evs}),
                       'mouth': [repr(x[1])[:120] for x in evs if x[0] == 19]})
    print(json.dumps({'package': pkg, 'bytes': os.path.getsize(pkg), 'actors': actors}))


if __name__ == '__main__':
    main()

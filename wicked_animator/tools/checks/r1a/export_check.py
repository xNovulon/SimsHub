"""R1-A check 9 (export side): build the package Send to game would write, offline into %TEMP% (harness
offline_export: exporter.animation_resources + wwpackage.build_package), then read every clip back with
clipfmt.parse_clip and report, per actor and per asked bone, whether its channels move and which clip events exist.

    python tools/checks/r1a/export_check.py <baked.json> <bone>[:t|:r] ...
Prints JSON: {package, actors: [{clip, events: [types], bones: {bone: {t: {frames, span}, r: {frames, span}}}}]}
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
# never read or write the user's saves from a check
os.environ.setdefault('ANIMATOR_SAVES', os.path.join(tempfile.gettempdir(), 'wa_r1a_saves'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))

import clipfmt  # noqa: E402
import exporter  # noqa: E402
import gamedata as G  # noqa: E402

try:
    import harness  # noqa: E402
except Exception:          # the shared harness is another slice's; fall back to the same two calls
    harness = None


def main():
    baked_path, bones = sys.argv[1], sys.argv[2:]
    with open(baked_path, 'r', encoding='utf-8') as f:
        baked = json.load(f)
    out_dir = tempfile.mkdtemp(prefix='wa_r1a_export_')
    if harness:
        pkg = harness.offline_export(baked, out_dir)
    else:
        import wwpackage
        resources, info = exporter.animation_resources(baked, metas={})
        pkg = os.path.join(out_dir, info['base'] + '.package')
        with open(pkg, 'wb') as f:
            f.write(wwpackage.build_package(resources))
    resources, info = exporter.animation_resources(baked, metas={})
    rig = {b['hash']: b['name'] for b in G.rig('au')['bones']}
    by_name = {v: k for k, v in rig.items()}
    actors = []
    for typ, _g, _inst, data in resources:
        if typ != exporter.T_CLIP:
            continue
        clip = clipfmt.parse_clip(data)
        chans = clip['codec']['channels']
        rep = {}
        for spec in bones:
            name, _, sub = spec.partition(':')
            subs = {'t': 1, 'r': 2}
            h = by_name.get(name)
            rep[name] = {}
            for key in ([sub] if sub else ['t', 'r']):
                ch = next((c for c in chans if c['target'] == h and c['sub'] == subs[key]), None)
                if ch is None:
                    rep[name][key] = None
                    continue
                vals = [v for _t, v in clipfmt.decode_track(ch)]
                span = max((max(v[i] for v in vals) - min(v[i] for v in vals)) for i in range(len(vals[0]))) if vals else 0
                rep[name][key] = {'frames': len(ch['frames']), 'span': span, 'first': vals[0] if vals else None}
        actors.append({'clip': clip['codec']['name'], 'channels': len(chans), 'events': sorted({e[0] for e in clip['events']}), 'bones': rep})
    print(json.dumps({'package': pkg, 'bytes': os.path.getsize(pkg), 'actors': actors}))


if __name__ == '__main__':
    main()

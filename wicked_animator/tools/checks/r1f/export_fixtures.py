"""R1-F: export baked fixtures offline (never into the game folder).

    python tools/checks/r1f/export_fixtures.py <fixtures dir> <out dir>

Each <id>.baked.json becomes <out>/<id>.package, built with exporter.animation_resources + wwpackage.build_package.
The saves folder is pointed at an empty %TEMP% folder, so progressions and past sends can't change the bytes."""
import glob, json, os, sys, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
os.environ['ANIMATOR_SAVES'] = os.path.join(tempfile.gettempdir(), 'r1f_empty_saves')
sys.path.insert(0, os.path.join(ROOT, 'backend'))


def export_one(baked, out_path):
    import exporter, wwpackage
    res, info = exporter.animation_resources(baked, metas={}, present=set())
    data = wwpackage.build_package(res)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(data)
    return data, info


def main(src, out):
    done = {}
    for p in sorted(glob.glob(os.path.join(src, '*.baked.json'))):
        fid = os.path.basename(p)[:-len('.baked.json')]
        with open(p, encoding='utf-8') as f:
            baked = json.load(f)
        data, info = export_one(baked, os.path.join(out, fid + '.package'))
        done[fid] = len(data)
    print(json.dumps(done))
    return done


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])

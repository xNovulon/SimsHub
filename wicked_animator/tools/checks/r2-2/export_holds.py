"""R2-2 check (spec_bodies 4.10, bullet 3): export a held animation offline (into %TEMP% only) and read the package
back: every clip is decoded, the skeletons are rebuilt frame by frame from the clips' own tracks (the rig for any
bone a clip keeps constant), and the holder's palm (EA's palm spot on the hand) is compared with the partner's skin
point the hold is on.

    python tools/checks/r2-2/export_holds.py <job.json>
    job = {"baked": <app.bake() payload>, "holder": <actor index>, "partner": <actor index>, "limb": "R hand",
           "bone": <partner bone>, "off": [x, y, z]}
Prints JSON: {package, bytes, frames, palmTravelCm, palmSkinMinCm, palmSkinMaxCm, holderArmTrack}
"""
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
os.environ.setdefault('ANIMATOR_SAVES', os.path.join(tempfile.gettempdir(), 'wa_r22_saves'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
sys.path.insert(0, os.path.join(ROOT, 'tools', 'checks', 'lib'))

import clipfmt  # noqa: E402
import dbpf  # noqa: E402
import exporter  # noqa: E402
import gamedata as G  # noqa: E402
import harness  # noqa: E402


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qrot(q, v):
    x, y, z, w = q
    r = qmul(qmul(q, (v[0], v[1], v[2], 0.0)), (-x, -y, -z, w))
    return (r[0], r[1], r[2])


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def main():
    with open(sys.argv[1], 'r', encoding='utf-8') as f:
        job = json.load(f)
    baked = job['baked']
    out_dir = tempfile.mkdtemp(prefix='wa_r22_export_')
    pkg = harness.offline_export(baked, out_dir)
    # which clip is which actor: the exporter writes them in actor order (same instance ids as in the package)
    resources, _info = exporter.animation_resources(baked, metas={})
    clip_inst = [inst for typ, _g, inst, _d in resources if typ == exporter.T_CLIP]
    by_inst = {e['inst']: e for e in dbpf.read_index(pkg) if e['type'] == exporter.T_CLIP}
    rig = G.rig('au')['bones']
    idx_by_hash = {b['hash']: i for i, b in enumerate(rig)}
    idx_by_name = {b['name']: i for i, b in enumerate(rig)}
    frames = int(baked['frames'])

    def skeleton_frames(actor_index):
        data = dbpf.read_resource(pkg, by_inst[clip_inst[actor_index]])
        clip = clipfmt.parse_clip(data)
        tracks = {}
        for ch in clip['codec']['channels']:
            i = idx_by_hash.get(ch['target'])
            if i is None or ch['sub'] not in (1, 2):
                continue
            vals = clipfmt.decode_track(ch)
            per = [None] * frames
            for tick, v in vals:
                if 0 <= tick < frames:
                    per[tick] = v
            last = vals[0][1] if vals else None
            for k in range(frames):          # a constant channel is one key at tick 0: hold it
                if per[k] is None:
                    per[k] = last
                last = per[k]
            tracks[(i, ch['sub'])] = per
        out = []
        for k in range(frames):
            wq, wp = [None] * len(rig), [None] * len(rig)
            for i, b in enumerate(rig):
                t = tracks.get((i, 1), [None] * frames)[k] or b['pos']
                r = qnorm(tracks.get((i, 2), [None] * frames)[k] or b['rot'])
                p = b['parent']
                if p < 0:
                    wq[i], wp[i] = r, tuple(t)
                else:
                    wq[i] = qnorm(qmul(wq[p], r))
                    o = qrot(wq[p], t)
                    wp[i] = (wp[p][0] + o[0], wp[p][1] + o[1], wp[p][2] + o[2])
            out.append((wq, wp))
        return out, tracks

    holder, htracks = skeleton_frames(job['holder'])
    partner, _ = skeleton_frames(job['partner'])
    side = job['limb'][0]
    palm_i = idx_by_name['b__%s_Stigmata' % side]
    anchor_i = idx_by_name[job['bone']]
    off = job['off']
    dists, palms = [], []
    for k in range(frames):
        pq, pp = partner[k]
        o = qrot(pq[anchor_i], off)
        skin = (pp[anchor_i][0] + o[0], pp[anchor_i][1] + o[1], pp[anchor_i][2] + o[2])
        palm = holder[k][1][palm_i]
        palms.append(palm)
        dists.append(math.dist(palm, skin))
    travel = max(math.dist(p, palms[0]) for p in palms)
    arm = htracks.get((idx_by_name['b__%s_UpperArm__' % side], 2)) or []
    arm_span = max((max(v[j] for v in arm) - min(v[j] for v in arm)) for j in range(4)) if arm else 0
    print(json.dumps({'package': pkg, 'bytes': os.path.getsize(pkg), 'frames': frames,
                      'palmTravelCm': round(travel * 100, 2), 'palmSkinMinCm': round(min(dists) * 100, 2),
                      'palmSkinMaxCm': round(max(dists) * 100, 2), 'holderArmTrack': {'keys': len(arm), 'span': round(arm_span, 4)}}))


if __name__ == '__main__':
    main()

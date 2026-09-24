"""Independent check of backend/eaaudio.py (does not change it).

  python tools/audio_verify.py prep       pick sounds, decode them (sound_file + every variation, stage by stage),
                                          write cache/audio/verify/files/* + manifest.json (+ noise/corrupt controls)
  python tools/audio_verify.py serve PORT run the app's real HTTP handler (backend/server.py Handler) on PORT
  python tools/audio_verify.py report     merge Chrome's results (chrome.json, route.json) -> report.txt / report.json
"""
import io
import json
import os
import random
import re
import struct
import sys
import time
import traceback

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'backend'))
import eaaudio  # noqa: E402
import gamedata  # noqa: E402
from dbpf import read_resource  # noqa: E402

OUT = os.path.join(eaaudio.AUDIO_DIR, 'verify')
FILES = os.path.join(OUT, 'files')
MANIFEST = os.path.join(OUT, 'manifest.json')
SEED = 20260924

WW_AUTO = (['Plaps_Normal'] + ['Slap_Sounds_%02d' % i for i in range(1, 4)] + ['Oj_Sounds_%02d' % i for i in range(1, 10)]
           + ['SoftKiss_Moan_Sounds_%02d' % i for i in range(1, 7)] + ['Soft_Moan_Sounds']
           + ['Soft_Moan_Sounds_%02d' % i for i in range(1, 7)]
           + ['WET_PL_%d' % i for i in range(1, 6)] + ['Sx_WetPump8F', 'khlas_ass_impact_wet', 'E404P_wet_pussy',
                                                        'vo_romantic_kiss_succ_x'])

# (kind, source) -> how many random names
QUOTA = {('clap', 'game'): 3, ('clap', 'mods'): 2, ('clap', 'parked'): 3, ('clap', 'unknown'): 2,
         ('other', 'game'): 3, ('other', 'mods'): 2, ('other', 'parked'): 3, ('other', 'unknown'): 2,
         ('voice', 'game'): 2, ('voice', 'unknown'): 6,
         ('wet', 'game'): 3, ('wet', 'mods'): 2, ('wet', 'parked'): 3, ('wet', 'unknown'): 4}
MAX_VARIANTS = 8


def safe(s):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', s)[:80]


def pick():
    rng = random.Random(SEED)
    snd = gamedata.sounds()
    by = {}
    for s in snd:
        by.setdefault((s['kind'], s['source']), []).append(s)
    out = []
    for cell, n in QUOTA.items():
        pool = sorted(by.get(cell, []), key=lambda s: s['name'])
        for s in rng.sample(pool, min(n, len(pool))):
            out.append(dict(s, set='random'))
    known = {s['name']: s for s in snd}
    for n in WW_AUTO:
        s = known.get(n, {'name': n, 'kind': gamedata.sound_kind(n), 'source': '(not in sounds())', 'count': 0})
        out.append(dict(s, set='ww_auto'))
    return out


def first_pcm_block(data, h):
    """EA's own stored PCM (the 0xEE block) of an EALayer3 v1 RAM clip: (offset, int16 array (n, ch)) or None."""
    if h['codec'] != 5 or h['type'] != 0:
        return None
    for _, pl in eaaudio._blocks(data, h['header_size']):
        pos = 0
        while pos < len(pl):
            if not any(pl[pos:]):
                break
            f = eaaudio._ea_frame_v1(pl, pos, True)
            if f['pcm']:
                off, n, raw = f['pcm']
                a = np.frombuffer(raw, '>i2').astype(np.int16)
                return off, n, a.tolist()
            pos += f['size']
        break
    return None


def stage_decode(path, entry):
    """Decode one clip, naming the stage that fails: lookup (reading the resource), container (SNR header / blocks /
    SNS), decoding (codec)."""
    r = {'inst': '%016x' % entry['inst'], 'package': os.path.basename(path), 'comp': entry.get('comp')}
    try:
        data = read_resource(path, entry)
    except Exception as ex:
        r.update(ok=False, stage='lookup', error='read_resource: %r' % ex)
        return r, None
    try:
        h = eaaudio.parse_header(data)
        r.update(codec=h['codec_name'], codec_id=h['codec'], sample_rate=h['sample_rate'], channels=h['channels'],
                 num_samples=h['num_samples'], storage=h['type'], loop=h['loop'], snr_bytes=len(data))
        _, stream = eaaudio.load_clip(path, entry)
        if h['type'] == 0:
            blocks = eaaudio._blocks(data, h['header_size'])
        else:
            blocks = eaaudio._blocks(stream, 0) if stream is not None else eaaudio._blocks(data, h['header_size'])
        r['blocks'] = len(blocks)
        r['block_samples'] = sum(b[0] for b in blocks)
    except Exception as ex:
        r.update(ok=False, stage='container', error='%s: %s' % (type(ex).__name__, ex))
        return r, None
    try:
        pcm = first_pcm_block(data, h)
        if pcm:
            r['ea_pcm'] = {'offset': pcm[0], 'n': pcm[1], 'samples': pcm[2]}
    except Exception as ex:
        r['ea_pcm_error'] = str(ex)
    t = time.perf_counter()
    try:
        res = eaaudio.decode_audio(data, stream)
    except Exception as ex:
        r.update(ok=False, stage='decoding', error='%s: %s' % (type(ex).__name__, ex))
        return r, None
    r['decode_ms'] = round((time.perf_counter() - t) * 1000, 2)
    r.update(ok=True, mime=res['mime'], out_bytes=len(res['data']), route=res.get('route'),
             bitrate=res.get('bitrate'), frames=res.get('frames'), decoded_samples=res.get('decoded_samples'),
             pcm_samples_dropped=res.get('pcm_samples_dropped'))
    return r, res['data']


def write(name, data, mime):
    ext = '.mp3' if mime == 'audio/mpeg' else '.wav'
    fn = name + ext
    with open(os.path.join(FILES, fn), 'wb') as f:
        f.write(data)
    return fn


def controls():
    """Noise baselines + deliberately broken audio: what 'not noise' must reject."""
    rng = np.random.default_rng(SEED)
    out = []
    sr = 48000
    white = (rng.standard_normal(sr) * 0.2).clip(-1, 1)
    out.append(('ctl_white_noise_1s', white, sr))
    # pink noise (1/f) by spectral shaping
    X = np.fft.rfft(rng.standard_normal(sr))
    f = np.fft.rfftfreq(sr, 1 / sr)
    X[1:] /= np.sqrt(f[1:])
    X[0] = 0
    pink = np.fft.irfft(X)
    out.append(('ctl_pink_noise_1s', pink / np.abs(pink).max() * 0.5, sr))
    # noise burst with a clap-like envelope (decaying noise): the hard case for the clap check
    env = np.exp(-np.arange(sr // 2) / (0.03 * sr))
    out.append(('ctl_noise_burst_decay', rng.standard_normal(sr // 2) * env * 0.4, sr))
    files = []
    for name, x, sr in out:
        pcm = (np.asarray(x) * 32767).astype(np.int16)
        fn = write(name, eaaudio.wav_bytes(pcm, sr), 'audio/wav')
        files.append({'file': fn, 'set': 'control', 'name': name, 'kind': 'control', 'sample_rate': sr, 'channels': 1,
                      'num_samples': len(pcm), 'expect_ok': True})
    return files


def corrupt_controls(src_files):
    """Take real rebuilt MP3s and scramble every frame's main data (headers + side info kept): garbage that still
    parses. The not-noise checks must flag these."""
    rng = random.Random(SEED)
    files = []
    for it in src_files:
        with open(os.path.join(FILES, it['file']), 'rb') as f:
            mp3 = bytearray(f.read())
        pos = 0
        k = 0
        while pos + 4 <= len(mp3):
            h = struct.unpack_from('>I', mp3, pos)[0]
            if h >> 21 != 0x7FF:
                break
            bri, sri, pad = (h >> 12) & 15, (h >> 10) & 3, (h >> 9) & 1
            ch = 1 if ((h >> 6) & 3) == 3 else 2
            sr = (44100, 48000, 32000)[sri]
            size = 144 * eaaudio.BITRATES_MPEG1[bri] * 1000 // sr + pad
            side = 17 if ch == 1 else 32
            if k > 0:           # keep the Info frame
                for i in range(pos + 4 + side, pos + size):
                    mp3[i] = rng.randrange(256)
            pos += size
            k += 1
        fn = 'ctl_scrambled_' + it['file']
        with open(os.path.join(FILES, fn), 'wb') as f:
            f.write(mp3)
        files.append(dict(it, file=fn, set='control', name='scrambled ' + it['name'], kind='control',
                          expect_ok=False, variant=None))
    return files


def prep():
    os.makedirs(FILES, exist_ok=True)
    for fn in os.listdir(FILES):
        os.remove(os.path.join(FILES, fn))
    t0 = time.time()
    idx = eaaudio._Index.get()
    print('index', round(time.time() - t0, 2), 's')
    chosen = pick()
    sounds = []
    files = []
    for i, s in enumerate(chosen):
        name = s['name']
        rec = {'i': i, 'name': name, 'set': s['set'], 'kind': s['kind'], 'gd_source': s['source'],
               'gd_package': s.get('package', '')}
        r = None
        data = None
        try:
            r = eaaudio.resolve(name)
            rec['resolved'] = r and r[0]
            rec['source'] = r and r[1]
            rec['sound_package'] = r and (os.path.basename(r[2]) if r[1] == 'game' else os.path.relpath(r[2], gamedata.SIMS_DIR))
            clips = eaaudio.sound_clips(name)
            rec['n_clips'] = len(clips)
        except Exception as ex:
            rec.update(lookup_error=traceback.format_exc(limit=2))
            clips = []
        if r and not clips:
            try:
                rec['sound_resource_ids'] = ['%016x' % x for x in eaaudio.parse_sound(read_resource(r[2], r[3]))]
            except Exception as ex:
                rec['sound_resource_ids'] = 'unreadable: %s' % ex
        # 1) what the app serves: sound_file(name)
        t = time.perf_counter()
        try:
            data, mime = eaaudio.sound_file(name)
            rec['sound_file_ms'] = round((time.perf_counter() - t) * 1000, 1)
            if data:
                fn = write('%03d_%s_served' % (i, safe(name)), data, mime)
                rec['served'] = {'file': fn, 'mime': mime, 'bytes': len(data)}
            else:
                rec['served'] = None
        except Exception as ex:
            rec['served_error'] = '%s: %s' % (type(ex).__name__, ex)
        # 2) every variation, stage by stage, fresh (not from the clip cache)
        rec['variants'] = []
        for k, (p, e) in enumerate(clips[:MAX_VARIANTS]):
            v, blob = stage_decode(p, e)
            v['k'] = k
            if blob:
                v['file'] = write('%03d_%s_v%d' % (i, safe(name), k), blob, v['mime'])
                if k == 0 and rec.get('served') and data:
                    v['same_as_served'] = blob == data
            rec['variants'].append(v)
            if v.get('ok'):
                files.append({'file': v['file'], 'set': s['set'], 'name': name, 'kind': s['kind'], 'variant': k,
                              'sample_rate': v['sample_rate'], 'channels': v['channels'],
                              'num_samples': v['num_samples'], 'codec': v['codec'], 'mime': v['mime'],
                              'expect_ok': True, 'ea_pcm': v.get('ea_pcm')})
        sounds.append(rec)
        vs = rec['variants']
        print('%3d %-40s %-7s %-8s clips=%-3s served=%s %s' % (
            i, name[:40], s['kind'], rec.get('source'), rec.get('n_clips'),
            (rec.get('served') or {}).get('mime') or rec.get('served_error', 'None'),
            ','.join('ok' if v.get('ok') else v.get('stage') for v in vs)))
    # extra "try to break it": clips beyond the WW sounds - streamed, XAS, other rates / channel counts
    extra = find_odd_clips(idx)
    for j, (label, p, e) in enumerate(extra):
        v, blob = stage_decode(p, e)
        v['k'] = 0
        name = 'odd_%s_%s' % (label, v['inst'])
        rec = {'i': 1000 + j, 'name': name, 'set': 'odd_clip', 'kind': 'other', 'variants': [v]}
        if blob:
            v['file'] = write('%04d_%s' % (1000 + j, safe(name)), blob, v['mime'])
            files.append({'file': v['file'], 'set': 'odd_clip', 'name': name, 'kind': 'other', 'variant': 0,
                          'sample_rate': v['sample_rate'], 'channels': v['channels'], 'num_samples': v['num_samples'],
                          'codec': v['codec'], 'mime': v['mime'], 'expect_ok': True, 'ea_pcm': v.get('ea_pcm')})
        sounds.append(rec)
        print('odd %-30s %s %s' % (label, v.get('codec'), 'ok' if v.get('ok') else '%s %s' % (v['stage'], v['error'])))
    files += controls()
    src = [f for f in files if f.get('mime') == 'audio/mpeg' and f['kind'] in ('clap', 'voice')][:2]
    src += [f for f in files if f.get('mime') == 'audio/mpeg' and f['kind'] == 'wet'][:1]
    files += corrupt_controls(src)
    with open(MANIFEST, 'w') as f:
        json.dump({'sounds': sounds, 'files': files}, f, indent=1)
    print('files', len(files), 'in', round(time.time() - t0, 1), 's')


def find_odd_clips(idx, per=3, scan=60000):
    """Clips from the whole game index that differ from the WW ones: streamed (SNS), EA-XAS, MPEG-2 rates
    (EALayer3 at 16/22.05/24 kHz), looping, >2 channels, other codecs."""
    rng = np.random.default_rng(SEED)
    snr = idx['snr']
    n = len(snr['key'])
    picks = rng.choice(n, size=min(scan, n), replace=False)
    got = {}
    for i in sorted(picks.tolist()):
        path = idx['packages'][int(snr['pkg'][i])][1]
        e = {'inst': int(snr['key'][i]), 'pos': int(snr['pos'][i]), 'size': int(snr['size'][i]),
             'mem': int(snr['mem'][i]), 'comp': int(snr['comp'][i]), 'type': eaaudio.T_SNR, 'group': 0}
        try:
            if e['comp'] == 0 and e['size'] >= 8:
                with open(path, 'rb') as f:
                    f.seek(e['pos'])
                    d = f.read(16)
            else:
                d = read_resource(path, e)
            h = eaaudio.parse_header(d)
        except Exception as ex:
            got.setdefault('unreadable', []).append((path, e))
            continue
        labels = []
        if h['type'] == 1:
            labels.append('streamed' if h['channels'] <= 2 else 'streamed_multich')
        if h['codec'] != 5:
            labels.append('codec%d' % h['codec'])
        if h['codec'] == 5 and h['sample_rate'] not in (32000, 44100, 48000):
            labels.append('rate%d' % h['sample_rate'])
        if h['channels'] > 2:
            labels.append('ch%d' % h['channels'])
        if h['loop'] and h['channels'] <= 2:
            labels.append('loop')
        if h['version'] != 0:
            labels.append('ver%d' % h['version'])
        for lab in labels:
            got.setdefault(lab, []).append((path, e))
    out = []
    summary = {k: len(v) for k, v in got.items()}
    print('odd clips found in a %d-clip scan:' % len(picks), summary)
    for lab, lst in sorted(got.items()):
        for p, e in lst[:per]:
            out.append((lab, p, e))
    with open(os.path.join(OUT, 'odd_scan.json'), 'w') as f:
        json.dump({'scanned': int(len(picks)), 'counts': summary}, f)
    return out


def serve(port):
    sys.argv = [sys.argv[0]]
    import server
    from http.server import ThreadingHTTPServer
    if os.environ.get('AUDIO_VERIFY_CLIP_DIR'):        # a scratch clip cache (cold-cache / race tests)
        eaaudio.CLIP_DIR = os.environ['AUDIO_VERIFY_CLIP_DIR']
    httpd = ThreadingHTTPServer(('127.0.0.1', port), server.Handler)
    print('serving the real app handler on', port, flush=True)
    httpd.serve_forever()


# ------------------------------------------------------------------ report
def mpg123_decode(path):
    import soundfile
    a, sr = soundfile.read(path, dtype='float32', always_2d=True)
    return a, sr


def report():
    man = json.load(open(MANIFEST))
    chrome = {r['file']: r for r in json.load(open(os.path.join(OUT, 'chrome.json')))['results']}
    route = {}
    if os.path.exists(os.path.join(OUT, 'route.json')):
        route = {r['name']: r for r in json.load(open(os.path.join(OUT, 'route.json')))['results']}
    rows = []
    for it in man['files']:
        c = chrome.get(it['file'], {})
        row = {'file': it['file'], 'name': it['name'], 'set': it['set'], 'kind': it['kind'],
               'codec': it.get('codec', '-'), 'sr': it['sample_rate'], 'ch': it['channels'],
               'expect_s': it['num_samples'] / it['sample_rate'], 'ok': c.get('ok'), 'error': c.get('error')}
        if c.get('ok'):
            row.update({k: c[k] for k in ('length', 'duration', 'dur48', 'peak', 'rms_db', 'early150', 'zcr',
                                          'centroid', 'flatness', 'env_cv', 'nan', 'clip_runs', 'lead_ms',
                                          'active')})
            row['len_diff'] = c['length'] - it['num_samples']
            # correlation of EA's stored PCM start with Chrome's first samples
            ea = it.get('ea_pcm')
            if ea and c.get('head'):
                x = np.array(ea['samples'], np.float64) / 32768
                ch = it['channels']
                best = None
                for layout in ('interleaved', 'planar'):
                    if ch == 1:
                        ref = x
                    elif layout == 'interleaved':
                        ref = x.reshape(-1, ch)[:, 0]
                    else:
                        ref = x.reshape(ch, -1)[0]
                    y = np.array(c['head'][0][:len(ref)], np.float64)
                    if np.std(ref) < 1e-4 or np.std(y) < 1e-4:
                        continue
                    cc = float(np.corrcoef(ref, y)[0, 1])
                    lags = {}
                    for lag in range(-4, 5):
                        yy = np.array(c['head'][0][max(0, lag):max(0, lag) + len(ref)], np.float64)
                        rr = ref[max(0, -lag):][:len(yy)]
                        yy = yy[:len(rr)]
                        if len(rr) > 10 and np.std(rr) > 1e-4 and np.std(yy) > 1e-4:
                            lags[lag] = float(np.corrcoef(rr, yy)[0, 1])
                    if best is None or cc > best[1]:
                        best = (layout, cc, max(lags, key=lags.get) if lags else None,
                                float(np.sqrt(np.mean(ref ** 2))))
                if best:
                    row['ea_corr'] = round(best[1], 3)
                    row['ea_best_lag'] = best[2]
                    row['ea_layout'] = best[0]
                    row['ea_rms'] = best[3]
            # second decoder
            if it.get('mime') == 'audio/mpeg' or it['file'].endswith('.mp3'):
                try:
                    a, sr = mpg123_decode(os.path.join(FILES, it['file']))
                    row['mpg123_len'] = len(a)
                except Exception as ex:
                    row['mpg123_err'] = str(ex)[:80]
        rows.append(row)
    with open(os.path.join(OUT, 'report.json'), 'w') as f:
        json.dump({'rows': rows, 'sounds': man['sounds'], 'route': list(route.values())}, f, indent=1)
    print('rows', len(rows))


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'prep'
    if cmd == 'prep':
        prep()
    elif cmd == 'serve':
        serve(int(sys.argv[2]))
    elif cmd == 'report':
        report()

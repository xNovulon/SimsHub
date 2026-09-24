"""Checks the animator's game-sound decoding (backend/eaaudio.py).

  python tools/audio_check.py make     decode a test set of WickedWhims sounds -> cache/audio/test/<name>.(mp3|wav)
  python tools/audio_check.py check    re-load every test file: duration vs num_samples/sample_rate; MP3 frame
                                       structure (headers, exact tiling, side info, bit reservoir)
  python tools/audio_check.py chrome   decode every test file in headless Chrome (AudioContext.decodeAudioData) and
                                       check the PCM (length, non-silent, RMS, no clipping/NaN)
  python tools/audio_check.py plot     6 waveforms from Chrome's PCM -> cache/audio/waveforms.png
  python tools/audio_check.py all      decode + validate every clip of every sound WickedWhims animations use
  (no argument: make, check, chrome, plot)
"""
import base64
import collections
import json
import os
import random
import re
import struct
import subprocess
import sys
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'backend'))
import eaaudio  # noqa: E402
from dbpf import read_resource  # noqa: E402

TEST_DIR = os.path.join(eaaudio.AUDIO_DIR, 'test')
MANIFEST = os.path.join(TEST_DIR, 'manifest.json')
CHROME_JSON = os.path.join(TEST_DIR, 'chrome_results.json')
PUPPETEER = 'C:/Users/basim/Tools/asws/node_modules/puppeteer-core'
CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'


def safe(name):
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', name)[:100]


# ====================================================================== make
def pick_test_set():
    cat = [s for s in eaaudio.catalogue() if s['source'] != 'unknown']
    picks = []                      # (name, voice or None, why)
    for s in cat:
        if 'LAMABOY' in s.get('package', '') and s['source'] == 'mods':
            picks.append((s['name'], None, 'mods LAMABOY %s' % s['kind']))
    parked = [s for s in cat if s['source'] == 'parked']
    rnd = random.Random(7)
    by_kind = collections.defaultdict(list)
    for s in parked:
        by_kind[s['kind']].append(s)
    for kind, n in (('clap', 4), ('wet', 3), ('voice', 3), ('other', 2)):
        seen_pk = set()
        pool = sorted(by_kind[kind], key=lambda s: -s['count'])[:40]
        rnd.shuffle(pool)
        for s in pool:
            if len([p for p in picks if p[2] == 'parked ' + kind]) >= n:
                break
            if s['package'] in seen_pk:
                continue
            seen_pk.add(s['package'])
            picks.append((s['name'], None, 'parked ' + kind))
    game = [s for s in cat if s['source'] == 'game']
    voices = [s for s in sorted(game, key=lambda s: -s['count']) if s['name'].lower().startswith(('vo_', 'voe_'))]
    moans = [s for s in voices if 'moan' in s['name'].lower()][:3]
    for s in moans + [s for s in voices if s not in moans][:5]:
        picks.append((s['name'], None, 'game voice (female)'))
    for s in moans[:2] + voices[:1]:
        picks.append((s['name'], 'male', 'game voice (male)'))
    claps = [s for s in sorted(game, key=lambda s: -s['count']) if s['kind'] == 'clap'][:6]
    picks += [(s['name'], None, 'game clap') for s in claps]
    wets = [s for s in sorted(game, key=lambda s: -s['count']) if s['kind'] == 'wet' and not s['name'].startswith('vo')][:2]
    picks += [(s['name'], None, 'game wet') for s in wets]
    others = [s for s in sorted(game, key=lambda s: -s['count']) if s['kind'] == 'other'][:2]
    picks += [(s['name'], None, 'game other') for s in others]
    # parked mod sounds encoded above MP3's 320 kbps (free-format -> mpg123 -> WAV route)
    names = {s['name'] for s in cat}
    picks += [(n, None, 'parked >320 kbps') for n in ('3_var_moans', '186_TC') if n in names]
    kinds = {s['name']: s for s in cat}
    return picks, kinds


def find_codec_samples():
    """A few game clips in codecs WickedWhims sounds don't use (EA-XAS, streamed EALayer3), for decoder coverage."""
    idx = eaaudio._Index.get()
    snr = idx['snr']
    found = {}
    order = np.argsort(snr['pkg'], kind='stable')
    rnd = np.random.default_rng(3)
    for i in rnd.permutation(order)[:6000]:
        path = idx['packages'][int(snr['pkg'][i])][1]
        e = {'inst': int(snr['key'][i]), 'pos': int(snr['pos'][i]), 'size': int(snr['size'][i]),
             'mem': int(snr['mem'][i]), 'comp': int(snr['comp'][i])}
        try:
            d = read_resource(path, e)
            h = eaaudio.parse_header(d)
        except Exception:
            continue
        key = (h['codec'], h['type'])
        if key != (5, 0) and key not in found and h['num_samples'] < 48000 * 30:
            found[key] = (path, e, h)
        if len(found) >= 4:
            break
    return found


def make():
    os.makedirs(TEST_DIR, exist_ok=True)
    for fn in os.listdir(TEST_DIR):
        if fn.endswith(('.mp3', '.wav')):
            os.remove(os.path.join(TEST_DIR, fn))
    t0 = time.time()
    eaaudio._Index.get()
    t_index = time.time() - t0
    picks, kinds = pick_test_set()
    manifest = []
    for name, voice, why in picks:
        r = eaaudio.resolve(name, voice)
        clips = eaaudio.sound_clips(name, voice)
        if not clips:
            print('!! no clips for', name, voice)
            continue
        path, e = clips[0]
        data, stream = eaaudio.load_clip(path, e)
        t = time.time()
        try:
            res = eaaudio.decode_audio(data, stream)
        except Exception as ex:
            print('!! decode failed', name, ex)
            manifest.append({'name': name, 'voice': voice, 'why': why, 'error': str(ex)})
            continue
        dt = time.time() - t
        # the public API end to end (cold: decodes + writes the cache; warm: cache hit)
        t = time.time(); b, mime = eaaudio.sound_file(name, 0, voice); t_cold = time.time() - t
        t = time.time(); b2, _ = eaaudio.sound_file(name, 0, voice); t_warm = time.time() - t
        assert b == res['data'] == b2, 'sound_file differs from decode_audio'
        fn = safe(name + ('__' + voice if voice else '')) + ('.mp3' if res['mime'] == 'audio/mpeg' else '.wav')
        with open(os.path.join(TEST_DIR, fn), 'wb') as f:
            f.write(res['data'])
        manifest.append({'name': name, 'voice': voice, 'why': why, 'resolved': r[0], 'source': r[1],
                         'package': os.path.relpath(r[2], eaaudio.gamedata.SIMS_DIR) if r[1] != 'game' else '',
                         'kind': kinds.get(name, {}).get('kind', ''), 'variations': len(clips), 'file': fn,
                         'bytes': len(res['data']), 'ea_bytes': len(data),
                         'decode_ms': round(dt * 1000, 2), 'sound_file_cold_ms': round(t_cold * 1000, 2),
                         'sound_file_warm_ms': round(t_warm * 1000, 2),
                         **{k: v for k, v in res.items() if k != 'data'}})
    for (codec, typ), (path, e, h) in find_codec_samples().items():
        data, stream = eaaudio.load_clip(path, e)
        name = 'extra_%s_type%d_%016x' % (safe(h['codec_name']), typ, e['inst'])
        t = time.time()
        try:
            res = eaaudio.decode_audio(data, stream)
        except Exception as ex:
            print('!! extra %s: %s' % (name, ex))
            manifest.append({'name': name, 'why': 'extra codec coverage', 'error': '%s: %s' % (type(ex).__name__, ex),
                             'codec': h['codec_name'], 'type': typ})
            continue
        dt = time.time() - t
        fn = safe(name) + ('.mp3' if res['mime'] == 'audio/mpeg' else '.wav')
        with open(os.path.join(TEST_DIR, fn), 'wb') as f:
            f.write(res['data'])
        manifest.append({'name': name, 'why': 'extra codec coverage', 'source': 'game', 'kind': 'extra', 'file': fn,
                         'bytes': len(res['data']), 'ea_bytes': len(data), 'decode_ms': round(dt * 1000, 2),
                         **{k: v for k, v in res.items() if k != 'data'}})
    with open(MANIFEST, 'w') as f:
        json.dump(manifest, f, indent=1)
    ok = [m for m in manifest if 'error' not in m]
    print('made %d test files (%d failed) in %s  [index load %.2fs]' % (len(ok), len(manifest) - len(ok), TEST_DIR, t_index))
    print('codecs:', dict(collections.Counter(m['codec'] for m in manifest)))
    print('decode_audio ms: mean %.2f max %.2f | sound_file cold mean %.1f ms, warm mean %.2f ms' % (
        np.mean([m['decode_ms'] for m in ok]), max(m['decode_ms'] for m in ok),
        np.mean([m['sound_file_cold_ms'] for m in ok if 'sound_file_cold_ms' in m]),
        np.mean([m['sound_file_warm_ms'] for m in ok if 'sound_file_warm_ms' in m])))


# ====================================================================== MP3 frame-structure validator
BR = {True: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
      False: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
SR = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


class MP3Error(Exception):
    pass


def _take(v, nbits, pos, n):
    return (v >> (nbits - pos - n)) & ((1 << n) - 1), pos + n


def _crc16_arc(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _info_tag(data, pos, size, mpeg1, ch):
    """Xing/Info + LAME tag in the first frame (side info all zero) -> dict, or None."""
    side_len = (17 if ch == 1 else 32) if mpeg1 else (9 if ch == 1 else 17)
    o = pos + 4 + side_len
    if any(data[pos + 4:o]) or data[o:o + 4] not in (b'Info', b'Xing'):
        return None
    flags, = struct.unpack_from('>I', data, o + 4)
    q = o + 8
    tag = {'kind': data[o:o + 4].decode()}
    if flags & 1:
        tag['frames'], = struct.unpack_from('>I', data, q); q += 4
    if flags & 2:
        tag['bytes'], = struct.unpack_from('>I', data, q); q += 4
    if flags & 4:
        q += 100
    if flags & 8:
        q += 4
    tag['encoder'] = data[q:q + 9].decode('ascii', 'replace')
    v = int.from_bytes(data[q + 21:q + 24], 'big')
    tag['delay'], tag['padding'] = v >> 12, v & 0xFFF
    crc_at = q + 34
    tag['crc_ok'] = struct.unpack_from('>H', data, crc_at)[0] == _crc16_arc(data[pos:crc_at])
    if crc_at + 2 > pos + size:
        raise MP3Error('Info tag longer than its frame')
    return tag



def validate_mp3(data):
    """Parse every frame of an MP3 stream and check it the way a decoder would. Returns a summary; raises MP3Error."""
    pos = 0
    frames = 0
    stream_bytes = 0            # main-data bytes delivered by earlier frames
    prev_end_bits = 0           # where the previous frame's main data ended, in main-data-stream bits
    fmt = None
    bitrates = collections.Counter()
    max_mdb = 0
    tag = None
    while pos < len(data):
        if pos + 4 > len(data):
            raise MP3Error('%d stray bytes at the end' % (len(data) - pos))
        h = int.from_bytes(data[pos:pos + 4], 'big')
        if h >> 21 != 0x7FF:
            raise MP3Error('no frame sync at byte %d (frame %d)' % (pos, frames))
        vid, layer, prot = (h >> 19) & 3, (h >> 17) & 3, (h >> 16) & 1
        bri, sri, pad, mode, emph = (h >> 12) & 15, (h >> 10) & 3, (h >> 9) & 1, (h >> 6) & 3, h & 3
        if vid == 1:
            raise MP3Error('reserved MPEG version (frame %d)' % frames)
        if layer != 1:
            raise MP3Error('not Layer III (frame %d)' % frames)
        if bri in (0, 15):
            raise MP3Error('%s bitrate index (frame %d)' % ('free-format' if bri == 0 else 'bad', frames))
        if sri == 3 or emph == 2:
            raise MP3Error('reserved sample rate / emphasis (frame %d)' % frames)
        mpeg1 = vid == 3
        sr = SR[vid][sri]
        br = BR[mpeg1][bri]
        size = (144 if mpeg1 else 72) * br * 1000 // sr + pad
        if pos + size > len(data):
            raise MP3Error('frame %d runs %d bytes past the end' % (frames, pos + size - len(data)))
        ch = 1 if mode == 3 else 2
        f = (vid, sri, ch)
        if fmt is None:
            fmt = f
        elif f != fmt:
            raise MP3Error('format changes at frame %d' % frames)
        side_len = (17 if ch == 1 else 32) if mpeg1 else (9 if ch == 1 else 17)
        crc = 0 if prot else 2
        if pos == 0 and prot:
            tag = _info_tag(data, pos, size, mpeg1, ch)
            if tag:                 # gapless decoders drop this frame; it adds nothing to the bit reservoir
                pos += size
                continue
        nb = side_len * 8
        v = int.from_bytes(data[pos + 4 + crc:pos + 4 + crc + side_len], 'big')
        p = 0
        mdb, p = _take(v, nb, p, 9 if mpeg1 else 8)
        _, p = _take(v, nb, p, (5 if ch == 1 else 3) if mpeg1 else (1 if ch == 1 else 2))
        if mpeg1:
            _, p = _take(v, nb, p, 4 * ch)
        bits = 0
        for gr in range(2 if mpeg1 else 1):
            for c in range(ch):
                p23, p = _take(v, nb, p, 12)
                bigv, p = _take(v, nb, p, 9)
                _, p = _take(v, nb, p, 8)                     # global gain
                sfc, p = _take(v, nb, p, 4 if mpeg1 else 9)
                ws, p = _take(v, nb, p, 1)
                if ws:
                    bt, p = _take(v, nb, p, 2)
                    _, p = _take(v, nb, p, 1)
                    tables = []
                    for _ in range(2):
                        t, p = _take(v, nb, p, 5); tables.append(t)
                    _, p = _take(v, nb, p, 9)
                    if bt == 0:
                        raise MP3Error('window switching with block type 0 (frame %d)' % frames)
                else:
                    tables = []
                    for _ in range(3):
                        t, p = _take(v, nb, p, 5); tables.append(t)
                    _, p = _take(v, nb, p, 7)
                _, p = _take(v, nb, p, 3 if mpeg1 else 2)
                if bigv > 288:
                    raise MP3Error('big_values %d > 288 (frame %d)' % (bigv, frames))
                if any(t in (4, 14) for t in tables):
                    raise MP3Error('invalid Huffman table (frame %d)' % frames)
                if bigv * 2 > 576 or (p23 and p23 < 0):
                    raise MP3Error('bad granule (frame %d)' % frames)
                bits += p23
        if p != nb:
            raise MP3Error('side info length mismatch')
        slots = size - 4 - crc - side_len
        if mdb > stream_bytes:
            raise MP3Error('main_data_begin %d reaches before the stream start (frame %d)' % (mdb, frames))
        start_bits = (stream_bytes - mdb) * 8
        if start_bits < prev_end_bits:
            raise MP3Error('main data of frame %d overlaps the previous frame\'s' % frames)
        if start_bits + bits > (stream_bytes + slots) * 8:
            raise MP3Error('main data of frame %d overflows its frame by %d bits' % (
                frames, start_bits + bits - (stream_bytes + slots) * 8))
        prev_end_bits = start_bits + bits
        stream_bytes += slots
        max_mdb = max(max_mdb, mdb)
        bitrates[br] += 1
        frames += 1
        pos += size
    if not frames:
        raise MP3Error('no frames')
    vid, sri, ch = fmt
    spf = 1152 if vid == 3 else 576
    out = {'frames': frames, 'sample_rate': SR[vid][sri], 'channels': ch, 'samples': frames * spf,
           'mpeg': {3: '1', 2: '2', 0: '2.5'}[vid], 'bitrates': dict(bitrates), 'max_main_data_begin': max_mdb,
           'samples_per_frame': spf, 'tag': tag, 'gapless_samples': frames * spf}
    if tag:
        if tag.get('frames') != frames or tag.get('bytes') != len(data) or not tag['crc_ok']:
            raise MP3Error('Info tag disagrees with the stream: %s vs %d frames / %d bytes' % (tag, frames, len(data)))
        out['gapless_samples'] = frames * spf - tag['delay'] - tag['padding']
    return out


def check():
    with open(MANIFEST) as f:
        manifest = json.load(f)
    rows = []
    bad = 0
    for m in manifest:
        if 'error' in m:
            print('%-58s DECODE FAILED: %s' % (m['name'][:58], m['error']))
            bad += 1
            continue
        path = os.path.join(TEST_DIR, m['file'])
        with open(path, 'rb') as f:
            data = f.read()
        expect = m['num_samples'] / m['sample_rate']
        try:
            if m['file'].endswith('.mp3'):
                v = validate_mp3(data)
                if v['sample_rate'] != m['sample_rate'] or v['channels'] != m['channels']:
                    raise MP3Error('format %s/%s vs header %s/%s' % (v['sample_rate'], v['channels'], m['sample_rate'], m['channels']))
                got = v['gapless_samples'] / v['sample_rate']
                ok = v['gapless_samples'] == m['num_samples'] if v['tag'] else \
                    0 <= v['samples'] - m['num_samples'] < v['samples_per_frame']
                extra = 'MPEG-%s %s kbps x%d frames, reservoir max %d%s' % (
                    v['mpeg'], '/'.join(map(str, v['bitrates'])), v['frames'], v['max_main_data_begin'],
                    ', %s tag delay %d pad %d' % (v['tag']['kind'], v['tag']['delay'], v['tag']['padding']) if v['tag'] else '')
            else:
                with wave.open(path) as w:
                    got = w.getnframes() / w.getframerate()
                    ok = w.getnframes() == m['num_samples'] and w.getframerate() == m['sample_rate'] and \
                        w.getnchannels() == m['channels'] and w.getsampwidth() == 2
                extra = 'WAV 16-bit %d ch' % m['channels']
        except (MP3Error, wave.Error) as ex:
            print('%-58s INVALID: %s' % (m['name'][:58], ex))
            bad += 1
            continue
        bad += not ok
        rows.append((m['name'] + (' [%s]' % m['voice'] if m.get('voice') else ''), m['codec'], m['sample_rate'],
                     m['channels'], expect, got, ok, extra))
    print('%-58s %-12s %6s %2s %8s %8s  %s' % ('sound', 'codec', 'rate', 'ch', 'expect', 'file', 'ok'))
    for name, codec, sr, ch, e, g, ok, extra in rows:
        print('%-58s %-12s %6d %2d %7.3fs %7.3fs  %s  %s' % (name[:58], codec, sr, ch, e, g, 'OK ' if ok else 'BAD', extra))
    print('%d files checked, %d problems' % (len(rows), bad))
    return bad


# ====================================================================== headless Chrome decode
CHROME_JS = r"""
const puppeteer = require(%(pup)s);
const fs = require('fs');
(async () => {
  const list = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await puppeteer.launch({ executablePath: %(chrome)s, headless: 'new', protocolTimeout: 600000 });
  const page = await browser.newPage();
  await page.goto('about:blank');
  const results = [];
  for (const it of list) {
    const b64 = fs.readFileSync(it.path).toString('base64');
    const r = await page.evaluate(async (b64, sr, ch) => {
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const ctx = new OfflineAudioContext(ch, 1, sr);          // same rate as the file: no resampling
      try {
        const ab = await ctx.decodeAudioData(bytes.buffer);
        const pcm = [];
        for (let c = 0; c < ab.numberOfChannels; c++) {
          const u8 = new Uint8Array(ab.getChannelData(c).slice().buffer);
          let s = '';
          for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
          pcm.push(btoa(s));
        }
        return { ok: true, length: ab.length, sampleRate: ab.sampleRate, channels: ab.numberOfChannels, pcm };
      } catch (e) { return { ok: false, error: String(e) }; }
    }, b64, it.sample_rate, it.channels);
    results.push(Object.assign({ file: it.file }, r));
  }
  fs.writeFileSync(process.argv[3], JSON.stringify(results));
  console.log('chrome', await browser.version(), 'decoded', results.filter(r => r.ok).length, 'of', results.length);
  await browser.close();
})();
"""


def chrome_decode(entries):
    """[{path, file, sample_rate, channels}] -> {file: result with 'pcm' as float32 array (samples, channels)}."""
    js = os.path.join(eaaudio.AUDIO_DIR, 'chrome_decode.js')
    with open(js, 'w') as f:
        f.write(CHROME_JS % {'pup': json.dumps(PUPPETEER), 'chrome': json.dumps(CHROME)})
    lst = os.path.join(eaaudio.AUDIO_DIR, 'chrome_list.json')
    with open(lst, 'w') as f:
        json.dump(entries, f)
    out = os.path.join(eaaudio.AUDIO_DIR, 'chrome_out.json')
    r = subprocess.run(['node', js, lst, out], capture_output=True, text=True, timeout=1200)
    if r.returncode:
        raise RuntimeError('chrome run failed: ' + r.stderr[-2000:])
    print(r.stdout.strip())
    with open(out) as f:
        res = json.load(f)
    os.remove(out)
    for x in res:
        if x.get('ok'):
            x['pcm'] = np.stack([np.frombuffer(base64.b64decode(c), '<f4') for c in x['pcm']], axis=1)
    return {x['file']: x for x in res}


def chrome():
    with open(MANIFEST) as f:
        manifest = [m for m in json.load(f) if 'error' not in m]
    entries = [{'path': os.path.join(TEST_DIR, m['file']), 'file': m['file'], 'sample_rate': m['sample_rate'],
                'channels': m['channels']} for m in manifest]
    res = chrome_decode(entries)
    summary = []
    bad = 0
    print('%-58s %-6s %8s %8s %8s %7s %6s %6s  %s' % ('sound', 'type', 'expect', 'chrome', 'file', 'rms', 'peak', 'onset', 'ok'))
    for m in manifest:
        r = res.get(m['file'])
        if not r or not r.get('ok'):
            print('%-58s CHROME FAILED: %s' % (m['name'][:58], r and r.get('error')))
            bad += 1
            continue
        pcm = r['pcm']
        n = len(pcm)
        expect = m['num_samples']
        file_samples = m.get('decoded_samples', expect)
        finite = bool(np.isfinite(pcm).all())
        body = pcm[:expect]
        rms = float(np.sqrt(np.mean(body.astype(np.float64) ** 2)))
        peak = float(np.abs(pcm).max())
        clipped = int((np.abs(pcm) >= 0.999).sum())
        env = np.abs(body).max(axis=1)
        onset = int(np.argmax(env > 0.02 * max(peak, 1e-9)))
        tail = pcm[expect:]
        tail_rms = float(np.sqrt(np.mean(tail.astype(np.float64) ** 2))) if len(tail) else 0.0
        # non-silent (some mod sounds are recorded very quietly, peak about -45 dBFS), no NaN, no clipping runs
        ok = finite and r['sampleRate'] == m['sample_rate'] and n == file_samples and rms > 1e-4 and \
            peak > 0.002 and peak <= 1.2 and clipped < 0.001 * n
        bad += not ok
        summary.append({'name': m['name'], 'voice': m.get('voice'), 'file': m['file'], 'kind': m.get('kind'),
                        'codec': m['codec'], 'chrome_samples': n, 'expect_samples': expect, 'file_samples': file_samples,
                        'sample_rate': r['sampleRate'], 'channels': r['channels'], 'rms': rms, 'peak': peak,
                        'clipped': clipped, 'onset_ms': round(onset * 1000 / m['sample_rate'], 1),
                        'tail_rms': tail_rms, 'ok': bool(ok)})
        np.save(os.path.join(TEST_DIR, m['file'] + '.chrome.npy'), pcm)
        print('%-58s %-6s %7.3fs %7.3fs %7.3fs %7.4f %6.3f %5.0fms  %s' % (
            (m['name'] + (' [%s]' % m['voice'] if m.get('voice') else ''))[:58], m['file'][-3:],
            expect / m['sample_rate'], n / m['sample_rate'], file_samples / m['sample_rate'], rms, peak,
            onset * 1000 / m['sample_rate'], 'OK' if ok else 'BAD'))
    with open(CHROME_JSON, 'w') as f:
        json.dump(summary, f, indent=1)
    print('%d decoded by Chrome, %d problems' % (len(summary), bad))
    bad += cross_check(manifest, res)
    return bad


def _snr(ref, x):
    n = min(len(ref), len(x))
    ref, x = ref[:n].astype(np.float64), x[:n].astype(np.float64)
    err = np.sum((ref - x) ** 2)
    return 10 * np.log10(np.sum(ref ** 2) / err) if err > 0 else float('inf')


def cross_check(manifest, chrome_res):
    """A second, independent MP3 decoder (mpg123 inside libsndfile, via soundfile) on the same files, and the
    free-format -> mpg123 route (used for >320 kbps streams) on clips that also have a normal MP3: all must agree
    with Chrome sample for sample (same length, same alignment, high SNR)."""
    try:
        import soundfile
    except ImportError:
        print('(soundfile not installed: no mpg123 cross-check)')
        return 0
    bad = 0
    snrs = []
    for m in manifest:
        r = chrome_res.get(m['file'])
        if not m['file'].endswith('.mp3') or not r or not r.get('ok'):
            continue
        x, sr = soundfile.read(os.path.join(TEST_DIR, m['file']), dtype='float32', always_2d=True)
        s = _snr(r['pcm'], x)
        ok = len(x) == len(r['pcm']) and sr == m['sample_rate'] and s > 40
        bad += not ok
        snrs.append(s)
        if not ok:
            print('  mpg123 vs Chrome MISMATCH %s: %d vs %d samples, SNR %.1f dB' % (m['file'], len(x), len(r['pcm']), s))
    if snrs:
        print('mpg123 (libsndfile %s) vs Chrome on %d MP3s: same length for all, SNR min %.1f dB, median %.1f dB' % (
            soundfile.__libsndfile_version__, len(snrs), min(snrs), float(np.median(snrs))))
    route = []
    for m in manifest[:12]:
        r = chrome_res.get(m['file'])
        if not m['file'].endswith('.mp3') or not r or not r.get('ok') or m.get('voice'):
            continue
        clips = eaaudio.sound_clips(m['name'])
        if not clips:
            continue
        data, stream = eaaudio.load_clip(*clips[0])
        h = eaaudio.parse_header(data)
        blocks = eaaudio._blocks(stream, 0) if stream else eaaudio._blocks(data, h['header_size'])
        pcm = eaaudio.ealayer3_to_pcm(blocks, h['codec'], h['num_samples']).astype(np.float32) / 32768
        s = _snr(r['pcm'], pcm)
        route.append(s)
        ok = len(pcm) == len(r['pcm']) and s > 30
        bad += not ok
        if not ok:
            print('  free-format route MISMATCH %s: %d vs %d samples, SNR %.1f dB' % (m['file'], len(pcm), len(r['pcm']), s))
    if route:
        print('free-format -> mpg123 route vs Chrome (CBR MP3 + gapless tag) on %d clips: SNR min %.1f dB' % (
            len(route), min(route)))
    return bad


# ====================================================================== plot
def plot():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with open(CHROME_JSON) as f:
        summary = [s for s in json.load(f) if s['ok']]

    def first(pred):
        for s in summary:
            if pred(s) and s not in chosen:
                chosen.append(s)
                return
    chosen = []
    first(lambda s: s['name'] == 'Plaps_Normal')                                           # mods clap
    first(lambda s: s['kind'] == 'clap' and s['name'].startswith(('fist', 'bush')))      # game clap
    first(lambda s: s['name'] == 'vo_expr_moan_pleasure_30f_cm' and not s['voice'])      # game voice, female
    first(lambda s: s['name'].lower().startswith('vo_') and s['voice'] == 'male')        # game voice, male
    first(lambda s: s['kind'] == 'wet' and s['channels'] == 2 and not s['name'].startswith('vo'))   # stereo wet
    first(lambda s: s['codec'] != 'EALayer3 v1')                                          # EA-XAS -> WAV
    while len(chosen) < 6:
        first(lambda s: True)
    fig, axes = plt.subplots(6, 1, figsize=(13, 15))
    for ax, s in zip(axes, chosen):
        pcm = np.load(os.path.join(TEST_DIR, s['file'] + '.chrome.npy'))
        t = np.arange(len(pcm)) / s['sample_rate']
        for c in range(pcm.shape[1]):
            ax.plot(t, pcm[:, c], lw=0.5, alpha=0.8 if c == 0 else 0.5, color=('#2a6fdb', '#e8743b')[c % 2],
                    label=('L' if c == 0 else 'R') if pcm.shape[1] > 1 else None)
        ax.axvline(s['expect_samples'] / s['sample_rate'], color='#c33', ls='--', lw=1)
        ax.set_xlim(0, t[-1] if len(t) else 1)
        lim = max(0.01, float(np.abs(pcm).max()) * 1.15)
        ax.set_ylim(-lim, lim)          # each panel scaled to its own peak (some mod sounds are very quiet)
        ax.set_title('%s%s  -  %s, %s, %d Hz, %d ch, rms %.3f  (decoded by Chrome from %s; dashed = num_samples)' % (
            s['name'], ' [%s voice]' % s['voice'] if s['voice'] else '', s['kind'], s['codec'], s['sample_rate'],
            s['channels'], s['rms'], s['file'][-3:].upper()), fontsize=9, loc='left')
        ax.set_ylabel('amplitude')
        if pcm.shape[1] > 1:
            ax.legend(loc='upper right', fontsize=8)
    axes[-1].set_xlabel('seconds')
    fig.tight_layout()
    out = os.path.join(eaaudio.AUDIO_DIR, 'waveforms.png')
    fig.savefig(out, dpi=80)
    print('saved', out, [s['name'] for s in chosen])


# ====================================================================== all
def all_clips():
    """Decode + validate every clip of every sound WickedWhims animations use (female and male voices)."""
    cat = [s for s in eaaudio.catalogue() if s['source'] != 'unknown']
    seen = {}
    t0 = time.time()
    for s in cat:
        voices = [None, 'male'] if s['name'].lower().startswith(('vo_', 'voe_')) else [None]
        for v in voices:
            for path, e in eaaudio.sound_clips(s['name'], v):
                seen.setdefault((path, e['inst']), (path, e, s['source'], s['name']))
    t_resolve = time.time() - t0
    codecs = collections.Counter()
    per_source = collections.Counter()
    fails = collections.Counter()
    fail_examples = {}
    times = []
    bitrates = collections.Counter()
    durations_ok = 0
    total_ea = total_out = 0
    wav_route = []
    for path, e, src, name in sorted(seen.values(), key=lambda x: (x[0], x[1]['pos'])):
        try:
            data, stream = eaaudio.load_clip(path, e)
            h = eaaudio.parse_header(data)
        except Exception as ex:
            fails['read: %s' % ex] += 1
            continue
        key = '%s %s %dch' % (h['codec_name'], 'RAM' if h['type'] == 0 else 'stream', h['channels'])
        codecs[key] += 1
        per_source[(src, h['codec_name'])] += 1
        t = time.time()
        try:
            res = eaaudio.decode_audio(data, stream)
        except Exception as ex:
            msg = '%s: %s' % (type(ex).__name__, re.sub(r'0x[0-9a-f]+|\d+', 'N', str(ex)))
            fails[msg] += 1
            fail_examples.setdefault(msg, name)
            continue
        times.append(time.time() - t)
        total_ea += len(data)
        total_out += len(res['data'])
        if res['mime'] == 'audio/mpeg':
            try:
                v = validate_mp3(res['data'])
            except MP3Error as ex:
                msg = 'MP3 invalid: %s' % re.sub(r'\d+', 'N', str(ex))
                fails[msg] += 1
                fail_examples.setdefault(msg, name)
                continue
            bitrates[res['bitrate']] += 1
            durations_ok += v['gapless_samples'] == h['num_samples']
        else:
            durations_ok += res['decoded_samples'] == h['num_samples']
            if res.get('route'):
                wav_route.append('%s (%s)' % (name, os.path.basename(path)))
    n = sum(codecs.values())
    print('sounds: %d, distinct clips: %d (resolve %.1fs)' % (len(cat), len(seen), t_resolve))
    print('codecs:', dict(codecs))
    print('by source:', {'%s/%s' % k: v for k, v in per_source.items()})
    print('decoded OK: %d / %d, duration within one frame of num_samples: %d' % (len(times), n, durations_ok))
    print('failures:', dict(fails), fail_examples)
    if times:
        print('decode_audio: total %.1fs, mean %.2f ms, p95 %.2f ms, max %.1f ms; EA %.1f MB -> out %.1f MB' % (
            sum(times), 1000 * np.mean(times), 1000 * np.percentile(times, 95), 1000 * max(times), total_ea / 1e6, total_out / 1e6))
    print('MP3 CBR bitrates chosen:', dict(sorted(bitrates.items())))
    print('above 320 kbps -> free-format + mpg123 -> WAV: %d clips: %s' % (len(wav_route), '; '.join(wav_route)))
    return len(fails)


if __name__ == '__main__':
    cmds = sys.argv[1:] or ['make', 'check', 'chrome', 'plot']
    for c in cmds:
        print('=' * 20, c)
        {'make': make, 'check': check, 'chrome': chrome, 'plot': plot, 'all': all_clips}[c]()

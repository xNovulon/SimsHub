"""Your own sounds in exports (backend/mysounds.py): the EA-XAS encoder, the SNR it writes, reading sound files, the
copied sound resource and the exported package.

    python tools/checks/own_sounds/test_own_sounds.py        (no game needed; everything is written into a temp folder)

The EA-XAS output is decoded twice: by the app's own decoder (eaaudio.decode_audio, the one the app plays game audio
with) and by a line-for-line Python port of vgmstream's decode_ea_xas_v1 (src/coding/ea_xas_decoder.c, commit 764c84c)
kept below - both must give the same samples, and those must come back close to the input.

The sound resource tests use a SYNTHETIC template (no real 0xFD04E3BE is available without the game): they check what
the app does to a template (only the audio list changes, same size, the instance style copied), not the game's format.
"""
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

TMP = tempfile.mkdtemp(prefix='wa_own_sounds_')
os.environ['ANIMATOR_SAVES'] = os.path.join(TMP, 'saves')      # before projects.py is imported
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

import clipfmt  # noqa: E402
import dbpf  # noqa: E402
import eaaudio  # noqa: E402
import exporter as X  # noqa: E402
import gamedata as G  # noqa: E402
import mysounds as M  # noqa: E402
import wwpackage as W  # noqa: E402

assert os.path.abspath(M.FOLDER).startswith(os.path.abspath(TMP)), M.FOLDER


# ------------------------------------------------------------------ an independent decoder (vgmstream's, ported)
XA_COEFS = [(0.0, 0.0), (0.9375, 0.0), (1.796875, -0.8125), (1.53125, -0.859375)]


def _i16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def vgm_decode_frame(frame):
    """decode_ea_xas_v1 for one 0x4C-byte channel frame -> 128 samples (float coefs, C truncation, clamp16)."""
    out = []
    for group in range(4):
        hdr = struct.unpack_from('<I', frame, group * 4)[0]
        coef1, coef2 = XA_COEFS[hdr & 0x0F] if (hdr & 0x0F) < 4 else (0.0, 0.0)
        hist2 = _i16(hdr & 0xFFF0)
        hist1 = _i16((hdr >> 16) & 0xFFF0)
        shift = (hdr >> 16) & 0x0F
        out += [hist2, hist1]
        for row in range(15):
            nibbles = frame[16 + row * 4 + group]
            for i in range(2):
                s = (nibbles >> 0) & 0x0F if i & 1 else (nibbles >> 4) & 0x0F
                s = _i16(s << 12) >> shift
                s = int(s + hist1 * coef1 + hist2 * coef2)      # C float -> int: truncation
                s = max(-32768, min(32767, s))
                out.append(s)
                hist2, hist1 = hist1, s
    return out


def float_decode_mono(snr):
    """The decoder the way vgmstream says EA's own code runs (see its comments): float history, nothing truncated or
    clamped between steps. Mono only."""
    n = struct.unpack_from('>I', snr, 4)[0] & 0x1FFFFFFF
    payload, out = snr[16:], []
    for f in range(-(-n // 128)):
        fr = payload[f * 0x4C:(f + 1) * 0x4C]
        for g in range(4):
            hdr = struct.unpack_from('<I', fr, g * 4)[0]
            c1, c2 = XA_COEFS[hdr & 15]
            h2, h1, sh = float(_i16(hdr & 0xFFF0)), float(_i16((hdr >> 16) & 0xFFF0)), (hdr >> 16) & 15
            out += [h2, h1]
            for row in range(15):
                nb = fr[16 + row * 4 + g]
                for i in range(2):
                    v = (nb & 15) if i & 1 else (nb >> 4)
                    s = _i16(v << 12) / float(1 << sh) + h1 * c1 + h2 * c2
                    out.append(s)
                    h2, h1 = h1, s
    return np.array(out[:n])


def vgm_decode_snr(snr):
    """EAAC RAM resource -> int16 (samples, channels): header (vgmstream init_vgmstream_eaaudiocore_header) and the
    single RAM block (block_update_ea_sns: u8 flag, u24 size, u32 samples, then the frames)."""
    h1, h2 = struct.unpack_from('>II', snr, 0)
    assert h1 >> 28 == 0 and (h1 >> 24) & 0xF == 4, 'version 0, codec 4 (XAS1)'
    ch = ((h1 >> 18) & 0x3F) + 1
    assert h2 >> 30 == 0, 'RAM'
    n = h2 & 0x1FFFFFFF
    flag = snr[8]
    size = int.from_bytes(snr[9:12], 'big')
    samples = struct.unpack_from('>I', snr, 12)[0]
    assert flag in (0x00, 0x80) and 8 + size == len(snr) and samples == n, (flag, size, len(snr), samples, n)
    payload = snr[16:]
    nf = -(-n // 128)
    assert len(payload) == nf * ch * 0x4C
    out = np.zeros((nf * 128, ch), np.int64)
    for f in range(nf):
        for c in range(ch):
            off = (f * ch + c) * 0x4C
            out[f * 128:(f + 1) * 128, c] = vgm_decode_frame(payload[off:off + 0x4C])
    return out[:n]


def app_decode(snr):
    dec = eaaudio.decode_audio(snr)
    x, rate = sf.read(io.BytesIO(dec['data']), dtype='int16', always_2d=True)
    return x, rate, dec


def snr_db(ref, got):
    ref = np.asarray(ref, np.float64)
    got = np.asarray(got, np.float64)
    return 10 * np.log10(np.sum(ref ** 2) / max(1e-9, np.sum((ref - got) ** 2)))


def test_signals(rate=32000, seconds=2.0):
    rng = np.random.default_rng(7)
    t = np.arange(int(rate * seconds)) / rate
    env = np.clip(np.sin(np.pi * t / seconds), 0, 1)
    sigs = {
        'sine': 0.8 * np.sin(2 * np.pi * 440 * t),
        'chirp': 0.7 * np.sin(2 * np.pi * (100 + 3000 * t / seconds) * t) * env,
        # a voice-like sound: a buzzing 140 Hz source through two resonances, syllable envelope
        'voice': np.convolve(np.sign(np.sin(2 * np.pi * 140 * t)) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)),
                             np.exp(-np.arange(200) / 30.0) * np.sin(2 * np.pi * 700 * np.arange(200) / rate), 'same'),
        'claps': np.concatenate([rng.standard_normal(800) * np.exp(-np.arange(800) / 120.0), np.zeros(int(rate * 0.3) - 800)] * int(seconds / 0.3 + 1))[:len(t)],
        'quiet_noise': 0.01 * rng.standard_normal(len(t)),
    }
    out = {}
    for k, v in sigs.items():
        v = v / (np.max(np.abs(v)) or 1) * (0.9 if k != 'quiet_noise' else 0.01)
        out[k] = np.round(v * 32767).astype(np.int16)
    return out


class XasRoundTrip(unittest.TestCase):
    def test_signals_come_back(self):
        for name, pcm in test_signals().items():
            snr = M.snr_bytes(pcm, 32000)
            app, rate, info = app_decode(snr)
            vgm = vgm_decode_snr(snr)
            self.assertEqual(rate, 32000)
            self.assertEqual(info['codec_id'], 4)
            self.assertEqual(app.shape, (len(pcm), 1), name)
            np.testing.assert_array_equal(app[:, 0], vgm[:, 0], err_msg=name + ': app decoder != vgmstream port')
            db = snr_db(pcm, app[:, 0])
            print('  %-12s %6d samples  %6d bytes  SNR %.1f dB' % (name, len(pcm), len(snr), db))
            # 4-bit ADPCM: white-noise-like sounds (claps, hiss) come back around 20 dB - the codec's limit, the same
            # for the game's own XAS clips; tonal sounds and voices far higher
            self.assertGreater(db, 17.0 if name in ('claps', 'quiet_noise') else 30.0, name)

    def test_float_decoder_agrees(self):
        # EA's own decoder keeps its history as floats; the encoder models the integer one. The two stay within a
        # few dozen sample values (below -55 dBFS) and the sound comes back just as well.
        for name, pcm in test_signals().items():
            snr = M.snr_bytes(pcm, 32000)
            app, _, _ = app_decode(snr)
            fl = float_decode_mono(snr)
            diff = np.max(np.abs(fl - app[:, 0]))
            print('  %-12s float history: SNR %.1f dB, at most %.0f off the integer decoder' % (name, snr_db(pcm, fl), diff))
            self.assertLess(diff, 64, name)
            self.assertGreater(snr_db(pcm, fl), snr_db(pcm, app[:, 0]) - 5, name)

    def test_stereo_and_odd_lengths(self):
        rng = np.random.default_rng(3)
        for n in (1, 2, 31, 32, 33, 127, 128, 129, 1000):
            pcm = np.round(rng.uniform(-0.5, 0.5, (n, 2)) * 32767).astype(np.int16)
            pcm[:, 1] = np.round(np.sin(np.arange(n) / 5.0) * 12000)
            snr = M.snr_bytes(pcm, 44100)
            app, _, _ = app_decode(snr)
            vgm = vgm_decode_snr(snr)
            self.assertEqual(app.shape, (n, 2))
            np.testing.assert_array_equal(app, vgm)
            if n > 40:
                self.assertGreater(snr_db(pcm[:, 1], app[:, 1]), 20.0)

    def test_header_fields(self):
        pcm = test_signals()['sine']
        snr = M.snr_bytes(pcm, 32000)
        h = eaaudio.parse_header(snr)
        self.assertEqual((h['version'], h['codec'], h['channels'], h['sample_rate'], h['type'], h['loop'], h['num_samples']),
                         (0, 4, 1, 32000, 0, 0, len(pcm)))
        blocks = eaaudio._blocks(snr, h['header_size'])
        self.assertEqual(len(blocks), 1)          # RAM sounds are one block
        self.assertEqual(blocks[0][0], len(pcm))
        self.assertEqual(len(blocks[0][1]), -(-len(pcm) // 128) * 0x4C)

    def test_full_scale_does_not_wrap(self):
        t = np.arange(4096)
        pcm = np.where((t // 64) % 2, 32767, -32768).astype(np.int16)       # a square wave at the limits
        app, _, _ = app_decode(M.snr_bytes(pcm, 32000))
        self.assertGreater(snr_db(pcm, app[:, 0]), 15.0)


# ------------------------------------------------------------------ reading files
def encode_file(x, rate, fmt, subtype=None):
    b = io.BytesIO()
    sf.write(b, x, rate, format=fmt, subtype=subtype)
    return b.getvalue()


class ReadingFiles(unittest.TestCase):
    def test_formats(self):
        rate = 44100
        t = np.arange(int(rate * 1.5)) / rate
        x = np.stack([0.6 * np.sin(2 * np.pi * 330 * t), 0.4 * np.sin(2 * np.pi * 550 * t)], axis=1)
        for fmt, sub in (('WAV', 'PCM_16'), ('WAV', 'FLOAT'), ('OGG', 'VORBIS'), ('FLAC', 'PCM_16'), ('MP3', None)):
            data = encode_file(x, rate, fmt, sub)
            y, r = M.read_file(data)
            pcm = M.prepare(y, r)
            ref = np.round(x.mean(axis=1) * 32767)
            ref32 = np.interp(np.arange(len(pcm)) / M.RATE, t, ref)          # the same sound at 32 kHz
            skip = 3000                           # MP3/OGG decoders add a little delay/fade at the start
            lag = 0
            if fmt in ('MP3', 'OGG'):
                c = [np.dot(pcm[skip:skip + 8000].astype(float), np.roll(ref32, k)[skip:skip + 8000]) for k in range(-1200, 1200)]
                lag = int(np.argmax(c)) - 1200
            db = snr_db(np.roll(ref32, lag)[skip:-skip], pcm[skip:-skip].astype(float))
            print('  %-4s %-7s -> %d samples at %d Hz, SNR vs input %.1f dB' % (fmt, sub or '', len(pcm), M.RATE, db))
            self.assertEqual(len(pcm), int(round(len(x) * M.RATE / rate)))
            self.assertGreater(db, 12.0 if fmt in ('MP3', 'OGG') else 35.0, fmt)

    def test_plain_wav_without_libsndfile(self):
        # what the app's page sends (16-bit WAV), and other PCM widths, read without soundfile
        rng = np.random.default_rng(5)
        x = rng.uniform(-0.8, 0.8, (500, 2))
        for sub, tol in (('PCM_U8', 1 / 64), ('PCM_16', 1e-4), ('PCM_24', 1e-6), ('PCM_32', 1e-8)):
            data = encode_file(x, 22050, 'WAV', sub)
            y, rate = M._read_wav(data)
            ref, _ = sf.read(io.BytesIO(data), dtype='float64', always_2d=True)
            self.assertEqual(rate, 22050)
            self.assertEqual(y.shape, ref.shape)
            self.assertLess(np.max(np.abs(y - ref)), tol, sub)

    def test_errors(self):
        with self.assertRaises(M.SoundError) as e:
            M.read_file(b'this is not a sound at all' * 20)
        self.assertIn('WAV, MP3, OGG or FLAC', str(e.exception))
        with self.assertRaises(M.SoundError):
            M.read_file(b'')
        long = encode_file(np.zeros(22050 * 31) + 0.1, 22050, 'WAV', 'PCM_16')
        with self.assertRaises(M.SoundError) as e:
            M.prepare(*M.read_file(long))
        self.assertIn('up to 30 seconds', str(e.exception))
        with self.assertRaises(M.SoundError) as e:
            M.prepare(*M.read_file(encode_file(np.zeros(8000), 8000, 'WAV', 'PCM_16')))
        self.assertIn('silent', str(e.exception))

    def test_loud_file_is_turned_down(self):
        x = np.clip(np.sin(np.arange(32000) / 3.0) * 1.0, -1, 1)
        pcm = M.prepare(x[:, None], 32000)
        self.assertLessEqual(np.max(np.abs(pcm)), int(M.HEADROOM * 32767) + 1)


# ------------------------------------------------------------------ the copied sound resource + export
def synthetic_template(refs, chain=0, tail=b'\x11\x22\x33\x44\x55\x66\x77\x88'):
    """NOT the game's format - just bytes shaped like what the app knows (u64 at 2, count at 10, u64s at 14)."""
    return b'\x01\x00' + struct.pack('<Q', chain) + struct.pack('<I', len(refs)) + b''.join(struct.pack('<Q', r) for r in refs) + tail


class FakeMods:
    """A Sims 4 user folder in the temp dir with one mod package of creator sounds (synthetic sound resources)."""

    def __init__(self):
        self.sims = os.path.join(TMP, 'The Sims 4')
        mods = os.path.join(self.sims, 'Mods', 'Creator')
        os.makedirs(mods, exist_ok=True)
        pcm = test_signals()['claps'][:4000]
        audio = M.snr_bytes(pcm, 32000)
        self.a1, self.a2, self.a3 = 0x1111, 0x2222, 0x3333
        h = clipfmt.fnv64
        res = [(M.T_AUDIO, 0, self.a1, audio), (M.T_AUDIO, 0, self.a2, audio), (M.T_AUDIO, 0, self.a3, audio),
               # the most used one points (bytes 2-9) to another sound resource in its own package: skipped
               (M.T_SOUND, 0, h('Chained_Slap'), synthetic_template([self.a1], chain=h('Parent_Sound'))),
               (M.T_SOUND, 0, h('Parent_Sound'), synthetic_template([self.a1])),
               # its audio is not in the package: skipped
               (M.T_SOUND, 0, h('Lost_Audio'), synthetic_template([0x9999])),
               # two variations (used when nothing with one clip is there)
               (M.T_SOUND, 0, h('Two_Claps'), synthetic_template([self.a2, self.a3])),
               # the one to copy: one clip, instance with the top bit
               (M.T_SOUND, 0, h('Wet_Plap_1') | M.TOP, synthetic_template([self.a1], chain=0xABCDEF)),
               (M.T_SOUND, 0, h('vo_moan_x'), synthetic_template([self.a1]))]
        self.pkg = os.path.join(mods, 'Creator_Sounds.package')
        with open(self.pkg, 'wb') as f:
            f.write(W.build_package(res))
        rel = os.path.relpath(self.pkg, self.sims)
        self.catalogue = [{'name': n, 'count': c, 'kind': G.sound_kind(n), 'source': 'mods', 'package': rel}
                          for n, c in (('Chained_Slap', 900), ('vo_moan_x', 800), ('Lost_Audio', 700), ('Two_Claps', 600),
                                       ('Wet_Plap_1', 500))]

    def __enter__(self):
        self.saved = (G.SIMS_DIR, G.sounds, G.blocked_path)
        G.SIMS_DIR = self.sims
        G.sounds = lambda: self.catalogue
        G.blocked_path = lambda p: False
        return self

    def __exit__(self, *a):
        G.SIMS_DIR, G.sounds, G.blocked_path = self.saved


FAKE_RIG = {'bones': [{'name': 'b__ROOT__', 'hash': clipfmt.fnv32('b__ROOT__'), 'pos': [0, 0, 0], 'rot': [0, 0, 0, 1]},
                      {'name': 'b__Pelvis__', 'hash': clipfmt.fnv32('b__Pelvis__'), 'pos': [0, 1, 0], 'rot': [0, 0, 0, 1]}]}


class OwnSoundExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(M.FOLDER, ignore_errors=True)
        cls.fake = FakeMods()
        rate = 48000
        t = np.arange(int(rate * 1.2)) / rate
        cls.wav = encode_file(np.stack([0.5 * np.sin(2 * np.pi * 220 * t)] * 2, axis=1), rate, 'WAV', 'PCM_16')
        cls.ogg = encode_file(0.4 * np.sin(2 * np.pi * 660 * t), rate, 'OGG', 'VORBIS')

    def test_1_template_and_add(self):
        with self.fake:
            t = M.find_template()
            self.assertEqual(t['name'], 'Wet_Plap_1')      # chained, lost audio and voice lines skipped; one clip first
            self.assertTrue(t['top'])
            s = M.add(self.wav, 'My Moan (take 2).wav', 'voice')
            again = M.add(self.wav, 'My Moan (take 2).wav', 'voice')
        self.assertEqual(s['name'], again['name'])
        self.assertTrue(M.is_mine(s['name']) and s['name'].startswith('WA_My_Moan_take_2_'), s['name'])
        self.assertEqual(s['kind'], 'voice')
        self.assertAlmostEqual(s['seconds'], 1.2, places=2)
        self.assertGreater(s['snr_db'], 25)
        self.assertEqual([x['name'] for x in M.list_sounds()], [s['name']])
        # the sound resource: the template's bytes, only the audio list changed
        with open(os.path.join(M.FOLDER, s['name'] + '.propx'), 'rb') as f:
            propx = f.read()
        self.assertEqual(len(propx), len(t['data']))
        sound_inst, audio_inst = M.instances(s['name'], True)
        self.assertEqual(eaaudio.parse_sound(propx), [audio_inst])
        self.assertEqual(propx[:14], t['data'][:14])
        self.assertEqual(propx[22:], t['data'][22:])
        self.assertEqual(sound_inst, clipfmt.fnv64(s['name']) | M.TOP)
        wav = M.preview(s['name'])
        self.assertTrue(wav.startswith(b'RIFF'))

    def test_2_two_clip_template(self):
        cat = [c for c in self.fake.catalogue if c['name'] != 'Wet_Plap_1']
        with self.fake:
            G.sounds = lambda: cat
            t = M.find_template()
            self.assertEqual(t['name'], 'Two_Claps')
            self.assertFalse(t['top'])
            data = M.sound_resource(t, 0x77)
        self.assertEqual(eaaudio.parse_sound(data), [0x77, 0x77])
        self.assertEqual(len(data), len(t['data']))

    def test_3_no_template(self):
        with self.fake:
            G.sounds = lambda: []
            with self.assertRaises(M.SoundError) as e:
                M.add(self.ogg, 'other.ogg')
        self.assertIn('Mods folder', str(e.exception))

    def test_4_export_package(self):
        with self.fake:
            mine = M.add(self.ogg, 'splash.ogg', 'other')
            voice = M.add(self.wav, 'My Moan (take 2).wav', 'voice')
        gone = 'WA_deleted_sound_0123abcd'
        project = {'name': 'Own sound test', 'author': 'Tester', 'frames': 60, 'fps': 30, 'category': 'TEASING',
                   'locations': ['FLOOR'],
                   'actors': [{'gender': 'FEMALE', 'tracks': {}, 'sounds': [
                       {'frame': 15, 'name': voice['name'], 'kind': 'voice'},
                       {'frame': 30, 'name': gone, 'kind': 'other'}]},
                              {'gender': 'MALE', 'tracks': {}, 'sounds': [
                                  {'frame': 45, 'name': mine['name'], 'kind': 'other'},
                                  {'frame': 10, 'name': 'Plaps_Normal', 'kind': 'clap'}]}]}
        saved_rig = G.rig
        G.rig = lambda key='au': FAKE_RIG
        try:
            resources, info = X.animation_resources(project, metas={}, present=set())
        finally:
            G.rig = saved_rig
        self.assertEqual(info['own_sounds'], sorted([mine['name'], voice['name']]))
        self.assertEqual(info['sounds'], ['Plaps_Normal'])        # only other mods' sounds go to the sound kit
        self.assertTrue(any(gone in w and 'left out' in w for w in info['warnings']), info['warnings'])
        pkg = os.path.join(TMP, 'test.package')
        with open(pkg, 'wb') as f:
            f.write(W.build_package(resources))
        idx = dbpf.read_index(pkg)
        by_key = {(e['type'], e['inst']): e for e in idx}
        for s in (mine, voice):
            sound_inst, audio_inst = M.instances(s['name'], True)
            e = by_key.get((M.T_SOUND, sound_inst))
            self.assertIsNotNone(e, 'sound resource of ' + s['name'])
            self.assertEqual(eaaudio.parse_sound(dbpf.read_resource(pkg, e)), [audio_inst])
            a = by_key.get((M.T_AUDIO, audio_inst))
            self.assertIsNotNone(a)
            snr = dbpf.read_resource(pkg, a)
            x, rate, _ = app_decode(snr)
            self.assertEqual(rate, M.RATE)
            self.assertAlmostEqual(len(x) / rate, s['seconds'], places=2)
        # the clips name the sounds at their times; the missing one is gone; lip-sync is off for the voice
        clips = [clipfmt.parse_clip(dbpf.read_resource(pkg, e)) for e in idx if e['type'] == X.T_CLIP]
        ev = [[(t, d) for t, d in c['events']] for c in clips]
        names = [[(d[12:140].split(b'\0')[0].decode(), round(struct.unpack_from('<f', d, 8)[0], 3)) for t, d in e if t == 3] for e in ev]
        self.assertEqual(names[0], [(voice['name'], 0.5)])
        self.assertEqual(sorted(names[1]), sorted([(mine['name'], 1.5), ('Plaps_Normal', round(10 / 30, 3))]))
        self.assertIn(19, [t for t, _ in ev[0]])
        xml = dbpf.read_resource(pkg, next(e for e in idx if e['type'] == W.SNIPPET)).decode('utf-8')
        self.assertIn('CUSTOM_VOICE_SFX', xml)

    def test_5_bundle_readme(self):
        with self.fake:
            mine = M.add(self.ogg, 'splash.ogg', 'other')
            project = {'name': 'Bundle own sound', 'author': 'Tester', 'frames': 30, 'fps': 30, 'uid': 'u-own-1',
                       'locations': ['FLOOR'], 'actors': [{'gender': 'FEMALE', 'tracks': {}, 'sounds': [
                           {'frame': 3, 'name': mine['name'], 'kind': 'other'}]}]}
            saved = (G.rig, X.EXPORTS)
            G.rig = lambda key='au': FAKE_RIG
            X.EXPORTS = os.path.join(TMP, 'exports')
            try:
                r = X.bundle({'name': 'Own Sounds Mod', 'author': 'Tester', 'animations': [project], 'include_sounds': True})
            finally:
                G.rig, X.EXPORTS = saved
        self.assertEqual(r['own_sounds'], 1)
        self.assertEqual(r['missing_sounds'], [])
        with open(os.path.join(r['folder'], 'README.txt'), encoding='utf-8') as f:
            readme = f.read()
        self.assertIn("THE CREATOR'S OWN SOUNDS PACKED INSIDE: " + mine['name'], readme)
        types = {e['type'] for e in dbpf.read_index(r['package'])}
        self.assertTrue({M.T_SOUND, M.T_AUDIO} <= types)


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        shutil.rmtree(TMP, ignore_errors=True)

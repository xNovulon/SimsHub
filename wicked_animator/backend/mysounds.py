"""Your own sounds (a WAV, MP3, OGG or FLAC file) as sound events that play in the game.

A sound event in a clip names a sound; the game finds the sound resource (0xFD04E3BE, instance = fnv64(name)) and
plays one of the audio clips it lists (0x01A527DB, "SNR"). See eaaudio.py for both formats. To put a file of your
own in the game, add() makes both:

  - the audio: the file is decoded (the app's page decodes what the browser plays and sends 16-bit WAV; files it
    can't read come as they are, for soundfile / libsndfile: WAV, OGG, FLAC, MP3), mixed to mono, resampled to
    32 kHz and encoded as EA-XAS v1 ADPCM (EA Audio Core codec 4), a codec the game's own client packages use, in a
    RAM ("SNR", type 0) resource: 8-byte header + ONE block (RAM sounds are a single block - vgmstream,
    src/meta/ea_eaac.c). The encoder runs the decoder of eaaudio._xas_v1 in its loop (closed loop), and that decoder
    matches vgmstream's decode_ea_xas_v1 (src/coding/ea_xas_decoder.c, commit 764c84c) step for step; add() decodes its
    own output with eaaudio.decode_audio and refuses to keep it if it does not come back close to the input.
  - the sound resource: its layout is not documented beyond the list of audio clips (u32 count at byte 10, then
    that many u64 instances - eaaudio.parse_sound), so none is made up here. The sound resource of a creator sound
    that WickedWhims animations already use (found in the Mods folder, or Mods_parked) is copied byte for byte and
    only the audio instances in that list are replaced by the new clip's - count and size stay the same, every
    other setting (volume, category...) is the copied sound's. That is what cloning a sound in the modding tools
    does, too.

The files are kept in saves\\FitStudio\\animator_sounds (next to the saved animations): <name>.snr (the audio),
<name>.propx (the sound resource) and <name>.json (what the file was). The sound's name is WA_<file name>_<8 hex
digits of its audio> - the same file added twice is the same sound. exporter.animation_resources() packs the two
resources into the animation's package, so they go wherever the animation goes (Send to game and Export mod).
"""
import hashlib, io, json, os, re, struct, threading, time, wave

import numpy as np

import gamedata as G
import projects as P
from clipfmt import fnv64
from dbpf import read_index, read_resource

T_SOUND, T_AUDIO = 0xFD04E3BE, 0x01A527DB
TOP = 1 << 63
FOLDER = os.path.join(P.ROOT, 'animator_sounds')
RATE = 32000                 # Hz: a rate the game's own clips use (with 44100 and 48000); mono XAS = 19 KB a second
MAX_SECONDS = 30.0
MAX_UPLOAD = 60 * 1024 * 1024
HEADROOM = 0.97             # peaks above this are turned down (the ADPCM must never clip)
NAME = re.compile(r'^WA_[A-Za-z0-9_]{0,40}_[0-9a-f]{8}$')
_lock = threading.Lock()


class SoundError(ValueError):
    """A file that can't become a game sound; the message is for the user."""


def is_mine(name):
    """Is this sound name one of yours (made by add())? Only the name is checked."""
    return bool(NAME.match(str(name or '')))


# ====================================================================== EA-XAS v1 encoder
_COEFS = np.array([[0.0, 0.0], [0.9375, 0.0], [1.796875, -0.8125], [1.53125, -0.859375]])
_SHIFTS = range(0, 13)       # shift 12 = steps of 1; above that a step is below one sample value


def _q12(v):
    """A header sample: the decoder keeps only its top 12 bits (value & 0xFFF0)."""
    return np.clip(np.round(v / 16.0) * 16, -32768, 32752).astype(np.int64)


def _xas_groups(x):
    """x: int array (groups, 32) -> (headers u32 (groups,), nibbles (groups, 30) as 0..15).

    Per group the decoder outputs the two header samples, then 30 samples
        s = clamp16(trunc(((nibble << 12 as int16) >> shift) + h1 * c1 + h2 * c2))
    Every (coefficient pair, shift) is tried on all groups at once, feeding back the decoder's own output (closed
    loop), and each group keeps the pair with the smallest squared error."""
    n = x.shape[0]
    x = x.astype(np.float64)
    h2_0, h1_0 = _q12(x[:, 0]), _q12(x[:, 1])
    best_err = np.full(n, np.inf)
    best_nib = np.zeros((n, 30), np.int64)
    best_c = np.zeros(n, np.int64)
    best_s = np.zeros(n, np.int64)
    for c in range(4):
        c1, c2 = _COEFS[c]
        for s in _SHIFTS:
            h1, h2 = h1_0.astype(np.float64), h2_0.astype(np.float64)
            err = (h2 - x[:, 0]) ** 2 + (h1 - x[:, 1]) ** 2
            nib = np.empty((n, 30), np.int64)
            for t in range(30):
                pred = h1 * c1 + h2 * c2
                q = np.clip(np.round((x[:, t + 2] - pred) * (1 << s) / 4096.0), -8, 7).astype(np.int64)
                out = np.clip(np.trunc(((q << 12) >> s) + pred), -32768, 32767)
                err += (out - x[:, t + 2]) ** 2
                nib[:, t] = q
                h2, h1 = h1, out
            better = err < best_err
            best_err = np.where(better, err, best_err)
            best_nib[better] = nib[better]
            best_c[better] = c
            best_s[better] = s
    lo = (h2_0 & 0xFFF0) | best_c
    hi = (h1_0 & 0xFFF0) | best_s
    headers = (lo & 0xFFFF) | ((hi & 0xFFFF) << 16)
    return headers.astype(np.uint32), best_nib & 15


def encode_xas(pcm):
    """int16 PCM (samples, channels) -> EA-XAS v1 payload: per 128 samples one 0x4C-byte frame per channel (4 LE u32
    group headers, then 15 rows of 4 bytes: row r, group g holds samples 2+2r (high nibble) and 3+2r (low))."""
    pcm = np.asarray(pcm, np.int16)
    if pcm.ndim == 1:
        pcm = pcm[:, None]
    samples, channels = pcm.shape
    nf = -(-samples // 128)
    padded = np.zeros((nf * 128, channels), np.int64)
    padded[:samples] = pcm
    frames = np.zeros((nf, channels, 0x4C), np.uint8)
    for ch in range(channels):
        groups = padded[:, ch].reshape(nf * 4, 32)
        headers, nib = _xas_groups(groups)
        frames[:, ch, :16] = headers.reshape(nf, 4).astype('<u4').view(np.uint8).reshape(nf, 16)
        nib = nib.reshape(nf, 4, 15, 2)
        rows = (nib[..., 0] << 4) | nib[..., 1]                  # (frame, group, row)
        frames[:, ch, 16:] = rows.transpose(0, 2, 1).reshape(nf, 60).astype(np.uint8)
    return frames.tobytes()


def snr_bytes(pcm, rate):
    """int16 PCM (samples, channels) -> an EA Audio Core RAM resource: header version 0, codec 4 (EA-XAS v1),
    channels, sample rate, type 0 (RAM), no loop, sample count; then one block (flag 0x80 = last, u24 size with
    its 8-byte header, u32 samples) holding every frame."""
    pcm = np.asarray(pcm, np.int16)
    if pcm.ndim == 1:
        pcm = pcm[:, None]
    samples, channels = pcm.shape
    if not 1 <= channels <= 2 or not 8000 <= rate <= 48000 or not 0 < samples < (1 << 29):
        raise SoundError('This sound can\'t be stored (%d channels, %d Hz, %d samples).' % (channels, rate, samples))
    payload = encode_xas(pcm)
    size = 8 + len(payload)
    if size >= 1 << 24:
        raise SoundError('This sound is too long.')
    h1 = (0 << 28) | (4 << 24) | ((channels - 1) << 18) | rate
    h2 = (0 << 30) | samples
    return struct.pack('>II', h1, h2) + struct.pack('>II', (0x80 << 24) | size, samples) + payload


# ====================================================================== reading the file
def _resample(x, rate, to):
    """(samples, channels) float -> the same at `to` Hz (band-limited, by FFT; zero padding keeps the ends clean)."""
    if rate == to:
        return x
    pad = 2048
    n = x.shape[0] + 2 * pad
    m = int(round(n * to / float(rate)))
    xp = np.zeros((n, x.shape[1]))
    xp[pad:pad + x.shape[0]] = x
    spec = np.fft.rfft(xp, axis=0)
    keep = min(spec.shape[0], m // 2 + 1)
    out_spec = np.zeros((m // 2 + 1, x.shape[1]), complex)
    out_spec[:keep] = spec[:keep]
    y = np.fft.irfft(out_spec, n=m, axis=0) * (m / float(n))
    start = int(round(pad * to / float(rate)))
    length = int(round(x.shape[0] * to / float(rate)))
    return y[start:start + length]


def _read_wav(data):
    """A plain PCM WAV (8/16/24/32-bit) without libsndfile -> (float (n, channels), rate)."""
    with wave.open(io.BytesIO(data), 'rb') as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128.0
    elif width == 2:
        x = np.frombuffer(raw, '<i2') / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        x = (((b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)) << 8) >> 8) / 8388608.0
    elif width == 4:
        x = np.frombuffer(raw, '<i4') / 2147483648.0
    else:
        raise ValueError('sample width %d' % width)
    return x.reshape(-1, ch), rate


def read_file(data):
    """A sound file -> (float samples (n, channels), sample rate). libsndfile (the soundfile package) reads WAV, OGG,
    FLAC and MP3; without it plain PCM WAV still works (the app's page sends every file it can play as that)."""
    if not data:
        raise SoundError('The file is empty.')
    if len(data) > MAX_UPLOAD:
        raise SoundError('The file is too big (%d MB). Use a sound of up to %d seconds.' % (len(data) >> 20, MAX_SECONDS))
    x = rate = None
    try:
        import soundfile as sf
        x, rate = sf.read(io.BytesIO(data), dtype='float64', always_2d=True)
    except Exception:
        try:
            x, rate = _read_wav(data)
        except Exception:
            raise SoundError('This file could not be read as a sound. Use a WAV, MP3, OGG or FLAC file.') from None
    if not len(x) or not rate:
        raise SoundError('The file has no sound in it.')
    return x, int(rate)


def prepare(x, rate):
    """float (n, channels) at `rate` -> int16 mono at RATE, turned down when it would clip."""
    seconds = len(x) / float(rate)
    if seconds > MAX_SECONDS + 1e-6:
        raise SoundError('The sound is %.1f seconds long. A sound in an animation can be up to %d seconds - cut it '
                         'shorter, then add it again.' % (seconds, MAX_SECONDS))
    if not np.all(np.isfinite(x)):
        raise SoundError('The file is damaged (it has invalid samples).')
    mono = x.mean(axis=1, keepdims=True)
    y = _resample(mono, rate, RATE)[:, 0]
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak < 1e-4:
        raise SoundError('The sound is silent.')
    if peak > HEADROOM:
        y = y * (HEADROOM / peak)
    return np.round(y * 32767.0).astype(np.int16)


def snr_quality(pcm, snr):
    """(signal-to-noise ratio in dB, decoded int16) of an SNR against the PCM it was made from."""
    import eaaudio
    dec = eaaudio.decode_audio(snr)
    x, _rate = _read_wav(dec['data'])
    back = np.round(x * 32768).astype(np.int16)
    ref = np.asarray(pcm, np.float64).reshape(len(pcm), -1)
    if back.shape != ref.shape:
        return -np.inf, back
    noise = np.sum((back.astype(np.float64) - ref) ** 2)
    sig = np.sum(ref ** 2)
    return (10 * np.log10(sig / noise) if noise > 0 else np.inf), back


MIN_SNR_DB = 12.0           # far below what the encoder reaches on real sounds (25+ dB); catches a broken encode


# ====================================================================== the sound resource (copied settings)
def _audio_in(path):
    """{instance: entry} of the audio clips in a package."""
    return {e['inst']: e for e in read_index(path) if e['type'] == T_AUDIO}


def _template_from(path, name):
    """A usable sound resource for `name` in the package at `path`, or None. Usable: the count at byte 10 and the
    u64 list after it name audio clips in the same package (the layout known here), those clips are RAM clips of
    1-2 channels (like the one made here), and bytes 2-9 do not point to another sound resource in the same
    package (that one would have to come along)."""
    try:
        idx = read_index(path)
    except Exception:
        return None
    h = fnv64(name)
    sounds = {e['inst']: e for e in idx if e['type'] == T_SOUND}
    e = sounds.get(h) or sounds.get(h | TOP)
    if not e:
        return None
    data = read_resource(path, e)
    if len(data) < 22:
        return None
    count = struct.unpack_from('<I', data, 10)[0]
    if not 1 <= count <= 32 or 14 + 8 * count > len(data):
        return None
    refs = struct.unpack_from('<%dQ' % count, data, 14)
    audio = {x['inst']: x for x in idx if x['type'] == T_AUDIO}
    if not all(r in audio for r in refs):
        return None
    chain = struct.unpack_from('<Q', data, 2)[0]
    if chain and chain != e['inst'] and chain in sounds:
        return None
    import eaaudio
    for r in set(refs):
        try:
            hd = eaaudio.parse_header(read_resource(path, audio[r])[:16])
        except Exception:
            return None
        if hd['type'] != 0 or hd['channels'] > 2:
            return None
    return {'name': name, 'package': os.path.relpath(path, G.SIMS_DIR), 'inst': e['inst'], 'top': bool(e['inst'] & TOP),
            'count': count, 'data': data}


def find_template():
    """The sound resource to copy settings from: a creator sound (not a voice line) that WickedWhims animations use,
    from Mods first, then Mods_parked; one audio clip before several, then the most used. Raises SoundError."""
    try:
        catalogue = G.sounds()
    except Exception:
        catalogue = []
    order = {'mods': 0, 'parked': 1}
    cands = [s for s in catalogue if s.get('source') in order and s.get('package') and s.get('kind') != 'voice'
             and not str(s.get('name', '')).lower().startswith(('vo_', 'voe_')) and not is_mine(s.get('name'))]
    cands.sort(key=lambda s: (order[s['source']], -int(s.get('count') or 0)))
    later = []
    for s in cands[:400]:
        path = os.path.join(G.SIMS_DIR, s['package'])
        if not os.path.isfile(path) or G.blocked_path(path):
            continue
        t = _template_from(path, s['name'])
        if t and t['count'] == 1:
            return t
        if t:
            later.append(t)
    if later:
        return later[0]
    raise SoundError('To put your own sound in the game, the app copies the settings of a creator sound that '
                     'WickedWhims animations in your Mods folder already use - none was found here. Add a '
                     'WickedWhims animation pack that has sounds to your Mods folder, then try again.')


def sound_resource(template, audio_inst):
    """The template's bytes with every audio instance in its list replaced by audio_inst (same count, same size)."""
    data = bytearray(template['data'])
    count = struct.unpack_from('<I', data, 10)[0]
    for k in range(count):
        struct.pack_into('<Q', data, 14 + 8 * k, audio_inst)
    return bytes(data)


# ====================================================================== the store
def _slug(filename):
    base = os.path.splitext(os.path.basename(str(filename or '')))[0]
    s = re.sub(r'[^A-Za-z0-9]+', '_', base).strip('_')[:28].strip('_')
    return s or 'sound'


def _path(name, ext):
    if not is_mine(name):
        raise LookupError('not one of your sounds')
    return os.path.join(FOLDER, name + ext)


def _write(path, data):
    tmp = path + '.%d.tmp' % threading.get_ident()
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, path)


def instances(name, top):
    """(sound resource instance, audio instance) of one of your sounds."""
    h = fnv64(name)
    return (h | TOP) if top else h, fnv64(name + ':audio') | TOP


def add(data, filename='', kind='other'):
    """A sound file -> one of your sounds (made and kept; the same file again gives the same sound).
    -> {name, label, seconds, kind, bytes, snr_db, turned_down}. Raises SoundError with a message for the user."""
    x, rate = read_file(data)
    peak_in = float(np.max(np.abs(x))) if len(x) else 0.0
    pcm = prepare(x, rate)
    name = 'WA_%s_%s' % (_slug(filename), hashlib.sha1(pcm.tobytes()).hexdigest()[:8])
    with _lock:
        meta_path = _path(name, '.json')
        if os.path.isfile(meta_path) and os.path.isfile(_path(name, '.snr')) and os.path.isfile(_path(name, '.propx')):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            if kind in ('voice', 'other') and meta.get('kind') != kind:
                meta['kind'] = kind
                _write(meta_path, json.dumps(meta, indent=1).encode('utf-8'))
            return _public(meta)
        template = find_template()
        snr = snr_bytes(pcm, RATE)
        db, _ = snr_quality(pcm, snr)
        if not db >= MIN_SNR_DB:
            raise SoundError('This sound could not be stored well enough for the game (%.1f dB). Try another file.' % db)
        sound_inst, audio_inst = instances(name, template['top'])
        propx = sound_resource(template, audio_inst)
        meta = {'name': name, 'label': os.path.basename(str(filename or '')) or name, 'kind': kind if kind in ('voice', 'other') else 'other',
                'seconds': round(len(pcm) / float(RATE), 3), 'rate': RATE, 'channels': 1, 'codec': 'EA-XAS v1',
                'snr_db': round(float(db), 1), 'turned_down': peak_in > HEADROOM, 'created': int(time.time()),
                'sound_inst': '%016x' % sound_inst, 'audio_inst': '%016x' % audio_inst,
                'template': {k: template[k] if not isinstance(template[k], int) or k == 'count' else '%016x' % template[k]
                             for k in ('name', 'package', 'inst', 'count')}}
        os.makedirs(FOLDER, exist_ok=True)
        _write(_path(name, '.snr'), snr)
        _write(_path(name, '.propx'), propx)
        _write(meta_path, json.dumps(meta, indent=1).encode('utf-8'))
    return _public(meta)


def _public(meta):
    try:
        size = os.path.getsize(_path(meta['name'], '.snr'))
    except OSError:
        size = 0
    return {'name': meta['name'], 'label': meta.get('label') or meta['name'], 'seconds': meta.get('seconds'),
            'kind': meta.get('kind') or 'other', 'bytes': size, 'snr_db': meta.get('snr_db'),
            'turned_down': bool(meta.get('turned_down'))}


def _meta(name):
    try:
        with open(_path(name, '.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError, LookupError):
        return None


def list_sounds():
    """Your sounds, newest first."""
    out = []
    try:
        names = os.listdir(FOLDER)
    except OSError:
        return out
    for fn in names:
        if fn.endswith('.json') and is_mine(fn[:-5]):
            m = _meta(fn[:-5])
            if m and os.path.isfile(_path(m['name'], '.snr')) and os.path.isfile(_path(m['name'], '.propx')):
                out.append((m.get('created') or 0, _public(m)))
    out.sort(key=lambda x: -x[0])
    return [m for _, m in out]


def has(name):
    return is_mine(name) and all(os.path.isfile(_path(name, e)) for e in ('.json', '.snr', '.propx'))


def resources(names):
    """-> ([(type, group, instance, bytes)] for your sounds among names, [names of yours that are not here])."""
    res, missing, seen = [], [], set()
    for n in names:
        if not is_mine(n) or n in seen:
            continue
        seen.add(n)
        m = _meta(n)
        if not m or not has(n):
            missing.append(n)
            continue
        with open(_path(n, '.snr'), 'rb') as f:
            snr = f.read()
        with open(_path(n, '.propx'), 'rb') as f:
            propx = f.read()
        res.append((T_SOUND, 0, int(m['sound_inst'], 16), propx))
        res.append((T_AUDIO, 0, int(m['audio_inst'], 16), snr))
    return res, missing


def preview(name):
    """WAV bytes of one of your sounds, decoded from the stored game audio (what the game will play), or None."""
    if not has(name):
        return None
    import eaaudio
    with open(_path(name, '.snr'), 'rb') as f:
        return eaaudio.decode_audio(f.read())['data']

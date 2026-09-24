"""The game's sounds, playable in a web browser.

How The Sims 4 stores a sound (all inside .package files):
  - a sound resource (type 0xFD04E3BE, instance = fnv64(lowercase name), sometimes with the top bit set) lists one or
    more audio clips by instance id (random variations of the same sound);
  - each clip is an EA Audio Core resource (type 0x01A527DB, "SNR"): an 8-byte header (codec, channels, sample rate,
    sample count, RAM/stream, loop) and, for RAM sounds, the audio blocks. Streamed sounds keep their blocks in a
    0x01EEF63A ("SNS") resource with the same instance.

Nearly every clip is EALayer3 (codec 5): EA's MP3 variant. Its frames carry exactly the Huffman-coded granules of
MPEG Layer III, behind a compressed header and without the bit reservoir. Like vgmstream, this module rebuilds
standard MPEG-1/2 Layer III frames from them (frame header, side info, main data re-packed with a bit reservoir into
constant-bitrate frames), so every browser decodes them natively - nothing is re-encoded, no quality is lost. A LAME
"Info" tag carries the codec delay (576 + 529 samples) and end padding, so browsers decode exactly num_samples
samples, aligned the way the game plays them. The rare stream above MP3's 320 kbps ceiling (a few mod sounds) is
rebuilt as free-format MP3 and decoded to WAV with mpg123 (soundfile package).
EA-XAS v1 ADPCM (codec 4) and PCM16 (codec 2) are decoded to 16-bit WAV.

Voices: the game plays 'vo_<name>' as 'vo_<name>_<voice actor>' (fa/fc/fd = adult female voices, ma/mb/mc = male) and
'voe_<name>' as 'voe_<name>_<ehi|elo>_<actor>' (see the PrefixSuffixMappings / ObjectModifiers audio tuning in the
game's client packages); sound_clips() resolves that. Child and teen voices are never used.

API
  decode_audio(data, stream=None) -> {'mime', 'data', 'sample_rate', 'channels', 'num_samples', 'codec', ...}
  sound_clips(name, voice=None)   -> [(package_path, entry)]   (entry works with dbpf.read_resource)
  sound_file(name, variant=0, voice=None) -> (bytes, mime), or (None, None) when the sound doesn't exist
  catalogue() -> gamedata.sounds() with 'source'/'package' filled in for voices too
  voice_for_actor(actor_hash, gender) -> 'fa'..'mc': a Tray sim's own adult voice
  adult_voice_lines() -> [{name, voices, tags, sec, lowprob, gender}]: the game's adult voice lines (cached)
"""
import glob
import json
import os
import pickle
import re
import struct
import threading
import time

import numpy as np

import gamedata
from clipfmt import fnv64
from dbpf import read_index, read_resource

T_SOUND, T_SNR, T_SNS = 0xFD04E3BE, 0x01A527DB, 0x01EEF63A
TOP = 1 << 63
AUDIO_DIR = os.path.normpath(os.path.join(gamedata.CACHE, 'audio'))
INDEX_PATH = os.path.join(AUDIO_DIR, 'index.pickle')
CLIP_DIR = os.path.join(AUDIO_DIR, 'clips')
INDEX_VERSION = 1
DECODER_VERSION = 2          # bump to re-decode every cached clip

CODECS = {0: 'none', 1: 'reserved', 2: 'PCM16BE', 3: 'EA-XMA', 4: 'EA-XAS v1', 5: 'EALayer3 v1', 6: 'EALayer3 v2 PCM',
          7: 'EALayer3 v2 Spike', 8: 'GameCube DSP', 9: 'EA-Speex', 10: 'EA-ATRAC3plus', 11: 'EA-MP3', 12: 'EA-Opus',
          13: 'EA-ATRAC9', 14: 'EA-Opus M', 15: 'EA-Opus MU'}

# voice actors (game ObjectModifiers <SimActors>); adults only
FEMALE_VOICES = ['fa', 'fc', 'fd', 'fb', 'efa', 'efc', 'efd']
MALE_VOICES = ['ma', 'mb', 'mc', 'md', 'ema', 'emb', 'emc']
VOE_MOODS = ['ehi', 'elo', 'happy', 'neutral', 'sad', 'angry']
# the six adult voices a sim can have in the game (fb and md exist, but no Create-a-Sim voice uses them)
ADULT_VOICES = {'female': ['fa', 'fc', 'fd'], 'male': ['ma', 'mb', 'mc']}
ACTOR_CODES = FEMALE_VOICES + MALE_VOICES
VOICE_LINES_PATH = os.path.join(gamedata.CACHE, 'voice_lines_v1.json')
# adults only: voice lines about or for children, pets, family or school never reach the app
_LINE_BLOCK = re.compile(r'(child|children|toddler|infant|baby|teen|kid|pet|puppy|kitten|dog|cat|horse|animal|'
                         r'dolphin|crossage|family|parent|school|bassinet|crib|scold|fairyvox)', re.I)
# the actor codes of child and special (non-human) voices: a line saved with one of these is never offered
NOT_ADULT_CODES = ('ca', 'cb', 'cc', 'cd', 'pa', 'ho', 're', 'ky', 'al')
_TAGS = [('climax', r'finish'), ('woohoo', r'woohoo'), ('moan', r'moan|mmm|purr|swoon|pleasure'),
         ('breath', r'breath|pant|sigh|gasp|exhale|inhale'), ('kiss', r'kiss|makeout|smooch'),
         ('flirt', r'flirt|seduc|sexy|romantic|whisper'), ('laugh', r'laugh|giggle|chuckle'),
         ('effort', r'grunt|effort|strain'), ('pain', r'pain|ouch|hurt')]
_TAGS = [(t, re.compile(rx, re.I)) for t, rx in _TAGS]
T_CLIP_HEADER = 0xBC4A5044


# ====================================================================== EAAC container
def parse_header(data):
    """EA Audio Core SNR header -> dict (+ 'header_size': where the blocks start for RAM sounds)."""
    if len(data) < 8:
        raise ValueError('EA audio: resource too small (%d bytes)' % len(data))
    h1, h2 = struct.unpack_from('>II', data, 0)
    h = {'version': h1 >> 28, 'codec': (h1 >> 24) & 0x0F, 'channels': ((h1 >> 18) & 0x3F) + 1,
         'sample_rate': h1 & 0x3FFFF, 'type': h2 >> 30, 'loop': (h2 >> 29) & 1, 'num_samples': h2 & 0x1FFFFFFF}
    size = 8
    if h['loop']:
        h['loop_start'] = struct.unpack_from('>I', data, 8)[0] if len(data) >= 12 else 0
        size += 4
        if h['type'] == 1:              # streamed + loop: also the loop's byte offset in the stream
            size += 4
    h['header_size'] = size
    h['codec_name'] = CODECS.get(h['codec'], 'codec %d' % h['codec'])
    return h


def _blocks(buf, pos=0):
    """EAAC blocks: u8 flags (0x80 = last), u24 block size (with this 8-byte header), u32 samples, payload."""
    out = []
    while pos + 8 <= len(buf):
        flag = buf[pos]
        size = int.from_bytes(buf[pos + 1:pos + 4], 'big')
        samples = struct.unpack_from('>I', buf, pos + 4)[0]
        if size < 8 or pos + size > len(buf):
            raise ValueError('EA audio: bad block at 0x%x (size %d of %d)' % (pos, size, len(buf)))
        out.append((samples, buf[pos + 8:pos + size]))
        pos += size
        if flag & 0x80:
            break
    return out


# ====================================================================== EALayer3 -> MPEG Layer III
def _bits(buf, pos, n):
    """n bits (MSB first) starting at bit position pos."""
    if n <= 0:
        return 0
    a, b = pos >> 3, (pos + n + 7) >> 3
    if b > len(buf):
        raise ValueError('EALayer3: frame runs past the data')
    return (int.from_bytes(buf[a:b], 'big') >> ((b << 3) - pos - n)) & ((1 << n) - 1)


def _ea_common(buf, p):
    """The part shared by EALayer3 v1/v2 frames, at byte p: a compressed MPEG header and ONE granule's side info
    (per channel: part2_3_length + the other 47/51 side-info bits), then that granule's main data, byte-padded."""
    if p >= len(buf):
        raise ValueError('EALayer3: frame runs past the data')
    h = buf[p]
    vi, sri, cm, me = h >> 6, (h >> 4) & 3, (h >> 2) & 3, h & 3
    if h == 0:
        raise ValueError('EALayer3: empty frame')
    if vi == 1 or sri == 3:
        raise ValueError('EALayer3: bad frame header 0x%02x' % h)
    ch = 1 if cm == 3 else 2
    mpeg1 = vi == 3
    bit = (p + 1) * 8
    gi = _bits(buf, bit, 1); bit += 1
    scfsi = 0
    if mpeg1 and gi == 1:               # scfsi (4 bits per channel) is stored with the second granule only
        scfsi = _bits(buf, bit, 4 * ch); bit += 4 * ch
    ob = 47 if mpeg1 else 51
    side = []
    for _ in range(ch):
        v = _bits(buf, bit, 12 + ob); bit += 12 + ob
        side.append((v >> ob, v & ((1 << ob) - 1)))
    nbits = sum(s[0] for s in side)
    md = _bits(buf, bit, nbits)
    common = (bit - p * 8 + nbits + 7) // 8
    return {'vi': vi, 'sri': sri, 'cm': cm, 'me': me, 'ch': ch, 'mpeg1': mpeg1, 'gi': gi, 'scfsi': scfsi,
            'side': side, 'md': md, 'md_bits': nbits, 'common': common}


def _ea_frame_v1(buf, pos, v1b):
    """EALayer3 v1 frame: u8 flag (0x00, or 0xEE = a PCM block follows), common part,
    [0xEE: u16 sample offset, u16 PCM samples, (v1b: u32 0), big-endian PCM16]."""
    flag = buf[pos]
    if flag not in (0x00, 0xEE):
        raise ValueError('EALayer3 v1: bad frame flag 0x%02x at 0x%x' % (flag, pos))
    f = _ea_common(buf, pos + 1)
    size = 1 + f['common']
    f['pcm'] = None
    if flag == 0xEE:
        off_s, pcm_s = struct.unpack_from('>HH', buf, pos + size)
        size += 8 if v1b else 4
        n = 2 * pcm_s * f['ch']
        f['pcm'] = (off_s, pcm_s, bytes(buf[pos + size:pos + size + n]))
        size += n
    f['size'] = size
    return f


def _ea_frame_v2(buf, pos):
    """EALayer3 v2 frame: u16 (extended, stereo, reserved, frame size), [extended: u32 offset mode/offset/PCM samples/
    common size], common part (absent in PCM-only frames), PCM16BE samples."""
    w = (buf[pos] << 8) | buf[pos + 1]
    ext, stereo, fsize = w >> 15, (w >> 14) & 1, w & 0xFFF
    pre, pcm_s, csz = 2, 0, None
    if ext:
        x = struct.unpack_from('>I', buf, pos + 2)[0]
        pcm_s, csz = (x >> 10) & 0x3FF, x & 0x3FF
        pre += 4
    if not ext or csz:
        f = _ea_common(buf, pos + pre)
    else:
        f = {'common': 0, 'ch': 2 if stereo else 1}
    size = pre + f['common'] + 2 * pcm_s * f['ch']
    if fsize and size != fsize:
        raise ValueError('EALayer3 v2: frame size %d but parsed %d at 0x%x' % (fsize, size, pos))
    f['size'] = fsize or size
    f['pcm'] = None
    return f


BITRATES_MPEG1 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]
BITRATES_MPEG2 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]
SAMPLE_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}


def _side_info(g0, g1, main_data_begin):
    ch = g0['ch']
    if g0['mpeg1']:
        v = (main_data_begin << (5 if ch == 1 else 3)) << (4 * ch) | g1['scfsi']
        for g in (g0, g1):
            for p23, other in g['side']:
                v = (v << 59) | (p23 << 47) | other
        return v.to_bytes(17 if ch == 1 else 32, 'big')
    v = main_data_begin << (1 if ch == 1 else 2)
    for p23, other in g0['side']:
        v = (v << 63) | (p23 << 51) | other
    return v.to_bytes(9 if ch == 1 else 17, 'big')


def _reservoir_layout(lengths, side_size, mpeg1, sample_rate, kbps):
    """Constant-bitrate frame sizes + main_data_begin for each frame's main data (bytes), or None if it can't fit.
    Each frame's data starts as early as the bit reservoir allows (right after the previous frame's data, at most
    511 (MPEG-1) / 255 (MPEG-2) bytes back) and must end inside its own frame."""
    base, rem = divmod((144 if mpeg1 else 72) * kbps * 1000, sample_rate)
    maxback = 511 if mpeg1 else 255
    acc = p = end = 0
    out = []
    for n in lengths:
        acc += rem
        pad = 0
        if acc >= sample_rate:
            acc -= sample_rate
            pad = 1
        slots = base + pad - 4 - side_size
        if slots < 0:
            return None
        start = max(end, p - maxback)
        if start + n > p + slots:
            return None
        out.append((base + pad, pad, p - start, start))
        end = start + n
        p += slots
    return out, p


# EALayer3 is MP3 made by a LAME-style encoder: the decoded output lags the input by 576 (encoder) + 529 (decoder)
# samples. The game's decoder hides that: v1 streams start with a PCM block of the first 1152 - 1105 = 47 samples
# and drop the first decoded frame (an SNS stream's first block counts exactly 47 samples). So the sound is
# decoded[1105 : 1105 + num_samples]; a LAME "Info" tag with encoder delay 576 tells MP3 decoders to cut the same.
EAL3_ENCODER_DELAY = 576
MP3_DECODER_DELAY = 529


def _crc16_arc(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _lame_info_frame(g, stream_bri, mpeg1, sample_rate, side_size, audio_frames, audio_bytes, delay, padding, kbps):
    """A silent MP3 frame holding a Xing 'Info' tag + LAME extension (frame count, byte count, seek table, encoder
    delay and end padding): gapless decoders (FFmpeg/Chrome, Firefox, Safari, LAME, mpg123...) skip it and trim the
    codec delay; others play it as 1 frame of silence."""
    rates = BITRATES_MPEG1 if mpeg1 else BITRATES_MPEG2
    need = 4 + side_size + 120 + 36
    bri = stream_bri
    while (144 if mpeg1 else 72) * rates[bri] * 1000 // sample_rate < need:
        bri += 1
        if bri > 14:
            return b''
    size = (144 if mpeg1 else 72) * rates[bri] * 1000 // sample_rate
    total = size + audio_bytes
    toc = bytes(min(255, i * 256 // 100) for i in range(100))
    tag = b'Info' + struct.pack('>III', 0x0F, audio_frames, total) + toc + struct.pack('>I', 0)
    lame = bytearray(36)
    lame[0:9] = b'LAME3.100'
    lame[9] = 0x01                                    # tag revision 0, CBR
    lame[20] = min(255, kbps)
    lame[21:24] = ((min(delay, 4095) << 12) | min(max(padding, 0), 4095)).to_bytes(3, 'big')
    lame[28:32] = struct.pack('>I', total)
    frame = bytearray(size)
    frame[0:4] = _frame_header(g, bri)
    o = 4 + side_size
    frame[o:o + 120] = tag
    frame[o + 120:o + 156] = lame
    crc_at = o + 120 + 34
    frame[crc_at:crc_at + 2] = struct.pack('>H', _crc16_arc(frame[:crc_at]))
    return bytes(frame)


class TooBigForMP3(ValueError):
    """Some frames need more than MP3's top bitrate (320 kbps MPEG-1 / 160 kbps MPEG-2) even with the bit reservoir -
    seen in a few mod sounds encoded at ~350+ kbps. Only 'free format' MP3 can carry them, which browsers don't play."""


def _ealayer3_frames(blocks, codec):
    """EALayer3 blocks -> ([(granule0, granule1 or None)] per MPEG frame, first granule, PCM samples left out)."""
    grans = []
    pcm_dropped = 0
    for _, payload in blocks:
        pos = 0
        while pos < len(payload):
            if not any(payload[pos:]):            # zero padding at the end of a block (streams)
                break
            if codec == 5:
                f = _ea_frame_v1(payload, pos, v1b=True)
            else:
                f = _ea_frame_v2(payload, pos)
            pos += f['size']
            if f.get('pcm'):
                pcm_dropped += f['pcm'][1]
            if f['common']:
                grans.append(f)
        if pos > len(payload):
            raise ValueError('EALayer3: frames overrun their block (%d of %d)' % (pos, len(payload)))
    if not grans:
        raise ValueError('EALayer3: no audio frames')
    g = grans[0]
    mpeg1 = g['mpeg1']
    frames = []
    i = 0
    while i < len(grans):
        g0 = grans[i]
        if (g0['vi'], g0['sri'], g0['ch']) != (g['vi'], g['sri'], g['ch']):
            raise ValueError('EALayer3: format changes mid-stream')
        if not mpeg1:
            frames.append((g0, None)); i += 1
            continue
        if g0['gi'] != 0:              # a second granule without its first: skip it
            i += 1
            continue
        g1 = grans[i + 1] if i + 1 < len(grans) else None
        if g1 is None or g1['gi'] != 1:
            # lone first granule (stream end): pair it with a silent granule
            g1 = dict(g0, gi=1, scfsi=0, side=[(0, 0)] * g0['ch'], md=0, md_bits=0)
            i += 1
        else:
            if g1['ch'] != g0['ch']:
                raise ValueError('EALayer3: granules disagree on channels')
            i += 2
        frames.append((g0, g1))
    return frames, g, pcm_dropped


def _main_data(frames):
    """Each MPEG frame's main data: granule 0 then granule 1 part2_3 bits, byte-padded."""
    datas = []
    for g0, g1 in frames:
        v, n = g0['md'], g0['md_bits']
        if g1 is not None:
            v, n = (v << g1['md_bits']) | g1['md'], n + g1['md_bits']
        nb = (n + 7) // 8
        datas.append((v << (nb * 8 - n)).to_bytes(nb, 'big') if nb else b'')
    return datas


def _frame_header(g, bri, pad=0):
    return ((0x7FF << 21) | (g['vi'] << 19) | (1 << 17) | (1 << 16) | (bri << 12) | (g['sri'] << 10) | (pad << 9) |
            (g['cm'] << 6) | (g['me'] << 4) | (1 << 2)).to_bytes(4, 'big')


def ealayer3_to_mp3(blocks, codec, num_samples=None, gapless=True):
    """EALayer3 blocks -> (MP3 bytes, info). Rebuilds MPEG-1 (2 granules) or MPEG-2/2.5 (1 granule) Layer III frames,
    constant bitrate with the bit reservoir, behind a LAME Info tag that trims the codec delay (gapless=True), so a
    browser decodes exactly num_samples samples. The PCM block of the stream start (47 samples = the first ~1 ms)
    can't live in an MP3 and is left out - the MP3 decoder's own samples for that spot play instead.
    Raises TooBigForMP3 when the stream needs more than MP3's top bitrate."""
    frames, g, pcm_dropped = _ealayer3_frames(blocks, codec)
    mpeg1 = g['mpeg1']
    spf = 1152 if mpeg1 else 576
    delay = EAL3_ENCODER_DELAY + MP3_DECODER_DELAY if gapless else 0
    if num_samples:
        # frames past the sound's end are the encoder's flush (often a loud burst of bits): never play them. An MP3
        # frame's output depends only on it and the frames before it, so cutting there is clean.
        frames = frames[:max(1, min(len(frames), -(-(num_samples + delay) // spf)))]
    datas = _main_data(frames)
    ch = g['ch']
    side_size = (17 if ch == 1 else 32) if mpeg1 else (9 if ch == 1 else 17)
    sample_rate = SAMPLE_RATES[g['vi']][g['sri']]
    rates = BITRATES_MPEG1 if mpeg1 else BITRATES_MPEG2
    # smallest constant bitrate whose frames (with the bit reservoir) hold every granule
    need = sum(len(d) for d in datas) / max(1, len(datas)) + side_size + 4
    layout = None
    for bri in range(1, 15):
        if (144 if mpeg1 else 72) * rates[bri] * 1000 / sample_rate < need:
            continue
        layout = _reservoir_layout([len(d) for d in datas], side_size, mpeg1, sample_rate, rates[bri])
        if layout:
            break
    if not layout:
        peak = max(len(d) for d in datas) + 4 + side_size
        raise TooBigForMP3('%s needs more than MP3\'s %d kbps even with the bit reservoir (frames up to %d kbps)' % (
            CODECS[codec], rates[14], peak * 8 * sample_rate // spf // 1000))
    layout, total = layout
    stream = bytearray(total)
    for (_, _, _, start), d in zip(layout, datas):
        stream[start:start + len(d)] = d
    out = bytearray()
    p = 0
    for (fsize, pad, mdb, _), (g0, g1) in zip(layout, frames):
        out += _frame_header(g0, bri, pad)
        out += _side_info(g0, g1, mdb)
        slots = fsize - 4 - side_size
        out += stream[p:p + slots]
        p += slots
    decoded = len(frames) * spf
    info_frame = b''
    if gapless and num_samples:
        padding = decoded - EAL3_ENCODER_DELAY - num_samples
        info_frame = _lame_info_frame(g, bri, mpeg1, sample_rate, side_size, len(frames), len(out),
                                      EAL3_ENCODER_DELAY, padding, rates[bri])
        if info_frame:              # what a gapless decoder outputs (= num_samples unless the stream is short)
            decoded = decoded - EAL3_ENCODER_DELAY - max(0, padding)
    info = {'frames': len(frames), 'bitrate': rates[bri], 'mpeg1': mpeg1, 'samples_per_frame': spf,
            'decoded_samples': decoded, 'gapless_tag': bool(info_frame), 'pcm_samples_dropped': pcm_dropped,
            'mp3_sample_rate': sample_rate, 'mp3_channels': ch}
    return info_frame + bytes(out), info


def ealayer3_to_pcm(blocks, codec, num_samples):
    """EALayer3 -> int16 PCM (samples, channels) for streams MP3 can't carry at a standard bitrate: rebuilds
    free-format Layer III frames (fixed size, no bit reservoir - vgmstream's approach) and decodes them with mpg123
    (libsndfile, via the soundfile package), then trims the codec delay like the game does."""
    try:
        import io
        import soundfile
    except ImportError:
        raise NotImplementedError('%s above MP3\'s top bitrate needs the soundfile package (mpg123) to decode'
                                  % CODECS[codec])
    frames, g, _ = _ealayer3_frames(blocks, codec)
    spf = 1152 if g['mpeg1'] else 576
    delay = EAL3_ENCODER_DELAY + MP3_DECODER_DELAY
    frames = frames[:max(1, min(len(frames), -(-(num_samples + delay) // spf)))]
    datas = _main_data(frames)
    ch = g['ch']
    side_size = (17 if ch == 1 else 32) if g['mpeg1'] else (9 if ch == 1 else 17)
    size = max(len(d) for d in datas) + 4 + side_size
    out = bytearray()
    for (g0, g1), d in zip(frames, datas):
        fr = _frame_header(g0, 0) + _side_info(g0, g1, 0) + d
        out += fr + bytes(size - len(fr))
    try:
        pcm, _ = soundfile.read(io.BytesIO(bytes(out)), dtype='int16', always_2d=True)
    except Exception as ex:
        raise NotImplementedError('%s above MP3\'s top bitrate: mpg123 could not decode it (%s)' % (CODECS[codec], ex))
    pcm = pcm[delay:delay + num_samples]
    if len(pcm) < num_samples:
        pcm = np.concatenate([pcm, np.zeros((num_samples - len(pcm), pcm.shape[1]), np.int16)])
    return pcm


# ====================================================================== EA-XAS v1 / PCM -> WAV
_XAS_COEFS = np.zeros((16, 2))
_XAS_COEFS[:4] = [[0.0, 0.0], [0.9375, 0.0], [1.796875, -0.8125], [1.53125, -0.859375]]


def _xas_v1(blocks, channels):
    """EA-XAS v1: per channel 0x4C-byte frames of 128 samples (4 groups: LE u32 header with coefficient index,
    shift and 2 history samples, then 15 rows x 4 bytes of nibbles), channels interleaved frame by frame."""
    outs = []
    for samples, payload in blocks:
        nf = -(-samples // 128)
        need = nf * channels * 0x4C
        if len(payload) < need:
            raise ValueError('EA-XAS: block too small (%d < %d)' % (len(payload), need))
        fr = np.frombuffer(bytes(payload[:need]), np.uint8).reshape(nf, channels, 0x4C)
        hdr = fr[:, :, :16].copy().view('<u4').astype(np.int64)            # (nf, ch, 4 groups)
        nib = fr[:, :, 16:].reshape(nf, channels, 15, 4).transpose(0, 1, 3, 2).astype(np.int32)   # (nf,ch,group,row)
        n = np.stack([nib >> 4, nib & 15], axis=-1).reshape(nf, channels, 4, 30)
        n = np.where(n >= 8, n - 16, n)
        shift = ((hdr >> 16) & 0x0F)[..., None]
        delta = ((n << 12) >> shift).astype(np.float64)
        idx = hdr & 0x0F
        c1, c2 = _XAS_COEFS[idx, 0], _XAS_COEFS[idx, 1]
        h2 = ((hdr & 0xFFF0) ^ 0x8000) - 0x8000
        h1 = (((hdr >> 16) & 0xFFF0) ^ 0x8000) - 0x8000
        out = np.empty((nf, channels, 4, 32), np.int32)
        out[..., 0], out[..., 1] = h2, h1
        h1 = h1.astype(np.float64); h2 = h2.astype(np.float64)
        for t in range(30):
            s = np.clip(np.trunc(delta[..., t] + h1 * c1 + h2 * c2), -32768, 32767)
            out[..., t + 2] = s
            h2, h1 = h1, s
        pcm = out.transpose(0, 2, 3, 1).reshape(nf * 128, channels)[:samples]
        outs.append(pcm)
    return np.concatenate(outs).astype(np.int16) if outs else np.zeros((0, channels), np.int16)


def _pcm16be(blocks, channels):
    """PCM16 big-endian, each block planar (all of channel 0, then channel 1...)."""
    outs = []
    for samples, payload in blocks:
        a = np.frombuffer(bytes(payload[:samples * channels * 2]), '>i2')
        outs.append(a.reshape(channels, samples).T)
    return np.concatenate(outs).astype(np.int16) if outs else np.zeros((0, channels), np.int16)


def wav_bytes(pcm, sample_rate):
    pcm = np.asarray(pcm, np.int16)
    if pcm.ndim == 1:
        pcm = pcm[:, None]
    ch = pcm.shape[1]
    data = pcm.astype('<i2').tobytes()
    return (b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' +
            struct.pack('<IHHIIHH', 16, 1, ch, sample_rate, sample_rate * ch * 2, ch * 2, 16) +
            b'data' + struct.pack('<I', len(data)) + data)


# ====================================================================== decode_audio
def decode_audio(data, stream=None):
    """An SNR audio resource (plus, for streamed sounds, the SNS resource's bytes) -> browser-playable audio:
    {'mime': 'audio/mpeg' | 'audio/wav', 'data': bytes, 'sample_rate', 'channels', 'num_samples', 'codec', ...}.
    Raises NotImplementedError (naming the codec) for codecs it can't convert, ValueError for damaged data."""
    try:
        return _decode_audio(data, stream)
    except (struct.error, IndexError) as ex:
        raise ValueError('EA audio: damaged data (%s)' % ex)


def _decode_audio(data, stream):
    h = parse_header(data)
    codec = h['codec']
    if h['type'] == 0:
        blocks = _blocks(data, h['header_size'])
    elif h['type'] == 1:
        if stream is None:
            if len(data) > h['header_size'] + 8:
                blocks = _blocks(data, h['header_size'])
            else:
                raise ValueError('EA audio: streamed sound - pass its SNS resource as stream=')
        else:
            blocks = _blocks(stream, 0)
    else:
        raise NotImplementedError('EA audio: storage type %d (gigasample) is not supported' % h['type'])
    res = {'sample_rate': h['sample_rate'], 'channels': h['channels'], 'num_samples': h['num_samples'],
           'codec': h['codec_name'], 'codec_id': codec, 'loop': h['loop']}
    if codec in (5, 6, 7):
        if h['channels'] > 2:
            raise NotImplementedError('%s with %d channels (multi-stream) is not supported' % (h['codec_name'], h['channels']))
        try:
            mp3, info = ealayer3_to_mp3(blocks, codec, h['num_samples'])
            res.update(info, mime='audio/mpeg', data=mp3)
            return res
        except TooBigForMP3 as ex:          # rare: a few mod sounds encoded above 320 kbps
            pcm = ealayer3_to_pcm(blocks, codec, h['num_samples'])
            res.update(mime='audio/wav', data=wav_bytes(pcm, h['sample_rate']), decoded_samples=len(pcm),
                       route='free-format MP3 -> mpg123 -> WAV (%s)' % ex)
            return res
    if codec == 4:
        pcm = _xas_v1(blocks, h['channels'])
    elif codec == 2:
        pcm = _pcm16be(blocks, h['channels'])
    else:
        raise NotImplementedError('EA audio codec %d (%s) is not supported' % (codec, h['codec_name']))
    pcm = pcm[:h['num_samples']]
    res.update(mime='audio/wav', data=wav_bytes(pcm, h['sample_rate']), decoded_samples=len(pcm))
    return res


# ====================================================================== index of every sound in the packages
_COLS = ('type', 'inst', 'pos', 'size', 'mem', 'comp')


def _packages():
    """(label, path) in lookup priority: Mods (what the game loads, overriding), game delta then full builds,
    parked mods last. Adults only: packs on the block list (gamedata.blocked_path) are never a sound source,
    the same rule gamedata._sound_sources() and the exporter use. The game's own Client packages are kept."""
    out = [('mods', p) for p in sorted(glob.glob(os.path.join(gamedata.MODS_DIR, '**', '*.package'), recursive=True))
           if not gamedata.blocked_path(p)]
    try:
        g = gamedata.game_dir()
        game = sorted(set(glob.glob(os.path.join(g, 'Data', 'Client', 'Client*Build*.package')) +
                          glob.glob(os.path.join(g, '*', 'Client*Build*.package')) +
                          glob.glob(os.path.join(g, 'Delta', '*', 'Client*Build*.package'))))
        if not game:        # unusual layout: search everything (slower)
            game = glob.glob(os.path.join(g, '**', 'Client*Build*.package'), recursive=True)
    except FileNotFoundError:
        game = []
    game.sort(key=lambda p: (0 if 'delta' in os.path.basename(p).lower() else 1, p))
    out += [('game', p) for p in game]
    out += [('parked', p) for p in sorted(glob.glob(os.path.join(gamedata.PARKED_DIR, '**', '*.package'), recursive=True))
            if not gamedata.blocked_path(p)]
    return out


def _stat(p):
    try:
        s = os.stat(p)
        return int(s.st_mtime), s.st_size
    except OSError:
        return None


def _scan_package(path):
    cols = {k: [] for k in _COLS}
    try:
        idx = read_index(path)
    except Exception:
        idx = []
    for e in idx:
        if e['type'] in (T_SOUND, T_SNR, T_SNS) and e['size'] and e['comp'] != 0xFFE0:   # 0xFFE0 = deleted
            for k in _COLS:
                cols[k].append(e[k])
    return {'type': np.array(cols['type'], np.uint32), 'inst': np.array(cols['inst'], np.uint64),
            'pos': np.array(cols['pos'], np.uint32), 'size': np.array(cols['size'], np.uint32),
            'mem': np.array(cols['mem'], np.uint32), 'comp': np.array(cols['comp'], np.uint16)}


class _Index:
    lock = threading.RLock()
    data = None          # {'packages': [(label, path)], 'sound'/'snr'/'sns': {key, pkg, pos, size, mem, comp}}

    @classmethod
    def get(cls):
        with cls.lock:
            if cls.data is None:
                cls.data = cls._load()
            return cls.data

    @classmethod
    def reset(cls):
        with cls.lock:
            cls.data = None

    @classmethod
    def _load(cls):
        t0 = time.time()
        pkgs = _packages()
        sig = [(lab, p, _stat(p)) for lab, p in pkgs]
        saved = None
        if os.path.exists(INDEX_PATH):
            try:
                with open(INDEX_PATH, 'rb') as f:
                    saved = pickle.load(f)
                if saved.get('version') != INDEX_VERSION:
                    saved = None
            except Exception:
                saved = None
        if saved and saved.get('signature') == sig:
            return saved['merged']
        per = (saved or {}).get('per_package', {})
        new_per = {}
        for lab, p, st in sig:
            old = per.get(p)
            new_per[p] = old if old and old[0] == st else (st, _scan_package(p))
        merged = cls._merge(pkgs, new_per)
        os.makedirs(AUDIO_DIR, exist_ok=True)
        tmp = INDEX_PATH + '.tmp'
        with open(tmp, 'wb') as f:
            pickle.dump({'version': INDEX_VERSION, 'signature': sig, 'per_package': new_per, 'merged': merged}, f,
                        protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, INDEX_PATH)
        merged['build_seconds'] = round(time.time() - t0, 1)
        return merged

    @staticmethod
    def _merge(pkgs, per):
        merged = {'packages': pkgs}
        for name, t in (('sound', T_SOUND), ('snr', T_SNR), ('sns', T_SNS)):
            parts = {k: [] for k in ('key', 'pkg', 'pos', 'size', 'mem', 'comp')}
            for k, (lab, p) in enumerate(pkgs):
                a = per[p][1]
                m = a['type'] == t
                if not m.any():
                    continue
                key = a['inst'][m]
                if t == T_SOUND:
                    key = key & np.uint64(TOP - 1)
                parts['key'].append(key)
                parts['pkg'].append(np.full(int(m.sum()), k, np.uint16))
                for c in ('pos', 'size', 'mem', 'comp'):
                    parts[c].append(a[c][m])
            if not parts['key']:
                merged[name] = {'key': np.zeros(0, np.uint64), 'pkg': np.zeros(0, np.uint16), 'pos': np.zeros(0, np.uint32),
                                'size': np.zeros(0, np.uint32), 'mem': np.zeros(0, np.uint32), 'comp': np.zeros(0, np.uint16)}
                continue
            cat = {k: np.concatenate(v) for k, v in parts.items()}
            keys, first = np.unique(cat['key'], return_index=True)    # first = highest-priority package
            merged[name] = {k: (keys if k == 'key' else v[first]) for k, v in cat.items()}
        return merged


def _find(table, key):
    """-> (package index, entry dict) or None."""
    keys = table['key']
    i = int(np.searchsorted(keys, np.uint64(key)))
    if i < len(keys) and int(keys[i]) == key:
        return int(table['pkg'][i]), {'inst': key, 'pos': int(table['pos'][i]), 'size': int(table['size'][i]),
                                      'mem': int(table['mem'][i]), 'comp': int(table['comp'][i])}
    return None


def _voice_order(voice):
    if voice and voice.lower() in FEMALE_VOICES + MALE_VOICES:
        v = voice.lower()
        return [v] + [a for a in (FEMALE_VOICES if v in FEMALE_VOICES else MALE_VOICES) if a != v] + \
            (MALE_VOICES if v in FEMALE_VOICES else FEMALE_VOICES)
    if voice and voice.lower() in ('m', 'male', 'ym', 'man'):
        return MALE_VOICES + FEMALE_VOICES
    return FEMALE_VOICES + MALE_VOICES


# other suffix rules of the game's PrefixSuffixMappings (terrain / shoe), for the few such sounds animations use
TERRAINS = ['wood', 'cpet', 'lino', 'stone', 'cment', 'wdeck', 'grass', 'dirt', 'metal', 'sand', 'gravel', 'leaves', 'puddle']
SHOES = ['bare', 'rub', 'leath', 'heel', 'boot', 'slip', 'sand', 'flip']


def _candidates(name, voice=None):
    n = name.strip()
    out = [n]
    low = n.lower()
    if low.startswith('vo_') or low.startswith('voe_'):
        for a in _voice_order(voice):
            if low.startswith('voe_'):
                out += ['%s_%s_%s' % (n, m, a) for m in VOE_MOODS]
            out.append('%s_%s' % (n, a))
    elif low.startswith('foot_'):
        out += ['%s_%s_%s' % (n, t, s) for s in SHOES for t in TERRAINS]
    elif low.startswith(('bodyfall_', 'kneel_', 'handterrainmod_')):
        out += ['%s_%s' % (n, t) for t in TERRAINS]
    return out


def resolve(name, voice=None):
    """The sound resource a clip event's sound name plays: (resolved name, label, package path, entry) or None.
    Takes the first candidate (the name itself, then with voice / terrain suffixes) that lists audio clips."""
    idx = _Index.get()
    fallback = None
    for cand in _candidates(name, voice):
        hit = _find(idx['sound'], fnv64(cand) & (TOP - 1))
        if hit:
            lab, path = idx['packages'][hit[0]]
            r = (cand, lab, path, dict(hit[1], type=T_SOUND, group=0))
            try:
                if parse_sound(read_resource(path, r[3])):
                    return r
            except Exception:
                pass
            fallback = fallback or r
    return fallback


def parse_sound(data):
    """Sound resource (0xFD04E3BE) -> list of audio clip instance ids."""
    if len(data) < 14:
        return []
    count = struct.unpack_from('<I', data, 10)[0]
    if count > 4096 or 14 + 8 * count > len(data):
        return []
    return list(struct.unpack_from('<%dQ' % count, data, 14))


_clips_memo = {}


def sound_clips(name, voice=None):
    """Audio clips (random variations) a sound name plays: [(package path, entry)], entry has type/group/inst/pos/
    size/mem/comp (for dbpf.read_resource). [] if the sound doesn't exist."""
    idx = _Index.get()
    key = (name.strip().lower(), (voice or '').lower(), id(idx))
    hit = _clips_memo.get(key)
    if hit is not None:
        return list(hit)
    r = resolve(name, voice)
    out = []
    if r:
        _, _, path, e = r
        try:
            ids = parse_sound(read_resource(path, e))
        except Exception:
            ids = []
        for i in ids:
            hit = _find(idx['snr'], i) or _find(idx['snr'], i ^ TOP)
            if hit:
                out.append((idx['packages'][hit[0]][1], dict(hit[1], type=T_SNR, group=0)))
    _clips_memo[key] = tuple(out)
    return out


def load_clip(path, entry):
    """(SNR bytes, SNS bytes or None) for a clip; streamed sounds get their SNS resource (same instance)."""
    data = read_resource(path, entry)
    stream = None
    h = parse_header(data)
    if h['type'] == 1 and len(data) <= h['header_size'] + 8:
        idx = _Index.get()
        hit = _find(idx['sns'], entry['inst']) or _find(idx['sns'], entry['inst'] ^ TOP)
        if not hit:
            raise ValueError('EA audio: streamed sound without its SNS data')
        stream = read_resource(idx['packages'][hit[0]][1], hit[1])
    return data, stream


_file_lock = threading.Lock()


def clip_file(path, entry):
    """Decoded clip (bytes, mime), cached in cache/audio/clips."""
    stem = os.path.join(CLIP_DIR, '%016x_%d_%d_v%d' % (entry['inst'], entry['size'], entry['pos'], DECODER_VERSION))
    for ext, mime in (('.mp3', 'audio/mpeg'), ('.wav', 'audio/wav')):
        if os.path.exists(stem + ext):
            with open(stem + ext, 'rb') as f:
                return f.read(), mime
    data, stream = load_clip(path, entry)
    res = decode_audio(data, stream)
    ext = '.mp3' if res['mime'] == 'audio/mpeg' else '.wav'
    os.makedirs(CLIP_DIR, exist_ok=True)
    with _file_lock:
        tmp = stem + ext + '.%d.tmp' % threading.get_ident()
        with open(tmp, 'wb') as f:
            f.write(res['data'])
        os.replace(tmp, stem + ext)
    return res['data'], res['mime']


def sound_file(name, variant=0, voice=None):
    """(bytes, mime) of a sound ready to serve over HTTP, or (None, None) if there's no such sound.
    variant picks one of the sound's random variations (wraps around); voice: None/'female'/'male' or an actor code
    ('fa', 'ma', ...) for 'vo_'/'voe_' voice sounds. Raises NotImplementedError if no variation can be decoded."""
    clips = sound_clips(name, voice)
    if not clips:
        return None, None
    first = variant % len(clips)
    err = None
    for k in [first] + [k for k in range(len(clips)) if k != first]:
        try:
            return clip_file(*clips[k])
        except (NotImplementedError, ValueError) as ex:
            err = ex
    raise NotImplementedError('%s: %s' % (name, err))


def sound_info(name, voice=None):
    """What a sound name resolves to (for tools / the UI): resolved name, source, package, clip headers."""
    r = resolve(name, voice)
    if not r:
        return None
    cand, lab, path, e = r
    clips = []
    for p, ce in sound_clips(name, voice):
        try:
            h = parse_header(read_resource(p, ce))
            clips.append({'inst': '%016x' % ce['inst'], 'codec': h['codec_name'], 'sample_rate': h['sample_rate'],
                          'channels': h['channels'], 'seconds': round(h['num_samples'] / max(1, h['sample_rate']), 3)})
        except Exception as ex:
            clips.append({'inst': '%016x' % ce['inst'], 'error': str(ex)})
    return {'name': name, 'resolved': cand, 'source': lab,
            'package': os.path.relpath(path, gamedata.SIMS_DIR) if lab != 'game' else '', 'clips': clips}


def catalogue():
    """gamedata.sounds() with voice sounds resolved: 'source' is 'game' / 'mods' / 'parked' / 'unknown'."""
    out = []
    for s in gamedata.sounds():
        s = dict(s)
        if s.get('source') == 'unknown':
            r = resolve(s['name'])
            if r:
                s['source'] = r[1]
                s['package'] = os.path.relpath(r[2], gamedata.SIMS_DIR) if r[1] != 'game' else ''
                s['resolved'] = r[0]
        out.append(s)
    return out


# ====================================================================== each sim's own game voice
_ACTOR_BY_HASH = None


def voice_for_actor(actor_hash, gender=None):
    """A Tray sim's voice_actor (fnv32 of the actor code) -> its adult voice code ('fa', 'fc', 'fd', 'ma', 'mb', 'mc').
    A code that is not one of the gender's three adult voices (unknown, special or without lines) gives the first
    voice of the gender; no gender known: any of the six, else 'fa'."""
    global _ACTOR_BY_HASH
    if _ACTOR_BY_HASH is None:
        from clipfmt import fnv32
        _ACTOR_BY_HASH = {fnv32(c): c for c in ACTOR_CODES + ['ca', 'cb', 'cc', 'cd', 'pa']}
    g = str(gender or '').lower()
    g = 'male' if g in ('male', 'm', 'ym', 'man') else 'female' if g in ('female', 'f', 'yf', 'woman') else ''
    try:
        code = _ACTOR_BY_HASH.get(int(actor_hash)) if actor_hash is not None else None
    except (TypeError, ValueError):
        code = str(actor_hash).lower() if str(actor_hash).lower() in ACTOR_CODES else None
    if g:
        return code if code in ADULT_VOICES[g] else ADULT_VOICES[g][0]
    return code if code in ADULT_VOICES['female'] + ADULT_VOICES['male'] else 'fa'


def _event_sound_name(d):
    """The sound name of a clip sound event (type 3), in either layout:
    EA's own clips: u32 id, u32 0, f32 time, i32 length, name; WickedWhims/creator clips: u32 0, u32 0, f32 time,
    char[128] name (zero padded)."""
    if len(d) < 16:
        return ''
    n = struct.unpack_from('<i', d, 12)[0]
    if 1 <= n <= 256 and 16 + n <= len(d):
        raw = d[16:16 + n].split(b'\0')[0]
        if raw and all(32 < c < 127 for c in raw):
            return raw.decode('ascii')
    raw = d[12:140].split(b'\0')[0]
    return raw.decode('ascii', 'replace').strip() if raw and all(32 <= c < 127 for c in raw) else ''


def _clip_header_packages():
    try:
        g = gamedata.game_dir()
    except FileNotFoundError:
        return []
    return sorted(glob.glob(os.path.join(g, '**', 'ClipHeader.package'), recursive=True),
                  key=lambda p: (0 if os.sep + 'delta' + os.sep in p.lower() else 1, p))


def _snr_seconds(path, entry):
    """Length in seconds of an audio take from its SNR header only (8 bytes), or None."""
    try:
        if entry.get('comp', 0) == 0:
            with open(path, 'rb') as f:
                f.seek(entry['pos'])
                head = f.read(16)
        else:
            head = read_resource(path, entry)[:16]
        h = parse_header(head)
        return round(h['num_samples'] / max(1, h['sample_rate']), 3)
    except Exception:
        return None


def _line_tags(name):
    return [t for t, rx in _TAGS if rx.search(name)]


def _line_gender(name):
    words = name.split('_')
    if 'f' in words:
        return 'f'
    if 'm' in words:
        return 'm'
    return ''


_lines_lock = threading.Lock()
_lines = None


def adult_voice_lines():
    """The game's adult voice lines, each playable in the sims' own voices:
    [{name, voices: [codes], tags: [...], sec, lowprob, gender: 'f'|'m'|''}].

    Made from every clip header (0xBC4A5044) in the game's ClipHeader.package files (first copy of each clip):
    the names of their sound events (type 3) that start with vo_ / voe_, minus _LINE_BLOCK and child/special voice
    codes. voices = the six adult codes that resolve to a game sound (vo_: name_code; voe_: name_mood_code); lines
    with none are dropped. sec = length of the first voice's first take. lowprob = EA's low-chance variant.
    Cached in cache/voice_lines_v1.json with the ClipHeader packages' sizes and mtimes."""
    global _lines
    with _lines_lock:
        if _lines is not None:
            return _lines
        pkgs = _clip_header_packages()
        sig = [[os.path.relpath(p, gamedata.game_dir()), os.path.getsize(p), int(os.path.getmtime(p))] for p in pkgs]
        cached = gamedata._load_cache(VOICE_LINES_PATH) if os.path.exists(VOICE_LINES_PATH) else None
        if isinstance(cached, dict) and cached.get('signature') == sig and isinstance(cached.get('lines'), list):
            _lines = cached['lines']
            return _lines
        _lines = _build_voice_lines(pkgs)
        gamedata._store(VOICE_LINES_PATH, {'signature': sig, 'lines': _lines, 'built': time.time()})
        return _lines


def _build_voice_lines(pkgs):
    from clipfmt import parse_clip
    names, seen = set(), set()
    for p in pkgs:
        try:
            idx = read_index(p)
        except Exception:
            continue
        for e in idx:
            if e['type'] != T_CLIP_HEADER or e['inst'] in seen:
                continue
            seen.add(e['inst'])
            try:
                c = parse_clip(read_resource(p, e) + b'\0' * 64)
            except Exception:
                continue
            for t, d in c.get('events') or []:
                if t != 3:
                    continue
                n = _event_sound_name(d).lower()
                if n.startswith(('vo_', 'voe_')):
                    names.add(n)
    idx = _Index.get()
    codes = ADULT_VOICES['female'] + ADULT_VOICES['male']
    out = []
    for n in sorted(names):
        if _LINE_BLOCK.search(n) or n.rsplit('_', 1)[-1] in NOT_ADULT_CODES:
            continue
        voices, first = [], None
        for c in codes:
            cands = ['%s_%s_%s' % (n, m, c) for m in VOE_MOODS] if n.startswith('voe_') else ['%s_%s' % (n, c)]
            for cand in cands:
                hit = _find(idx['sound'], fnv64(cand) & (TOP - 1))
                if hit:
                    voices.append(c)
                    if first is None:
                        first = (idx['packages'][hit[0]][1], dict(hit[1], type=T_SOUND, group=0))
                    break
        if not voices:
            continue
        sec = None
        try:
            ids = parse_sound(read_resource(*first))
            for i in ids[:1]:
                snr = _find(idx['snr'], i) or _find(idx['snr'], i ^ TOP)
                if snr:
                    sec = _snr_seconds(idx['packages'][snr[0]][1], snr[1])
        except Exception:
            pass
        out.append({'name': n, 'voices': voices, 'tags': _line_tags(n), 'sec': sec, 'lowprob': 'lowprob' in n,
                    'gender': _line_gender(n)})
    return out


if __name__ == '__main__':
    import sys
    for n in sys.argv[1:]:
        print(json.dumps(sound_info(n), indent=1))

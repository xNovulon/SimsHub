// Your own sound files as sounds in the game (backend/mysounds.py): the server turns the sound into game audio, keeps
// it next to your saved animations, and every export packs it in. Names look like WA_<file>_1a2b3c4d.
//
// The browser decodes the file first (WAV, MP3, OGG, FLAC - whatever it plays) and sends plain 16-bit WAV, so the
// server needs no MP3 or OGG decoder of its own. A file the browser can't read is sent as it is (the server may still
// know it).
import { $t } from './i18n.js';
export const isMine = name => /^WA_[A-Za-z0-9_]{0,40}_[0-9a-f]{8}$/.test(String(name || ''));

export const ACCEPT = 'audio/*,.wav,.mp3,.ogg,.oga,.flac';
export const MAX_SECONDS = 30;
const RATE = 48000;

export async function listMySounds() {
  const r = await fetch('/api/my_sounds');
  if (!r.ok) throw new Error($t('mysounds.could_not_read_your_sounds'));
  return r.json();
}

// AudioBuffer -> 16-bit PCM WAV (1 or 2 channels)
export function wavOf(buffer) {
  const ch = Math.min(2, buffer.numberOfChannels), n = buffer.length, rate = buffer.sampleRate;
  const out = new DataView(new ArrayBuffer(44 + n * ch * 2));
  const str = (o, s) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); out.setUint32(4, 36 + n * ch * 2, true); str(8, 'WAVEfmt ');
  out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, ch, true); out.setUint32(24, rate, true);
  out.setUint32(28, rate * ch * 2, true); out.setUint16(32, ch * 2, true); out.setUint16(34, 16, true);
  str(36, 'data'); out.setUint32(40, n * ch * 2, true);
  const data = [...Array(ch).keys()].map(c => buffer.getChannelData(c));
  let o = 44;
  for (let i = 0; i < n; i++) {
    for (let c = 0; c < ch; c++) {
      const v = Math.max(-1, Math.min(1, data[c][i] || 0));
      out.setInt16(o, Math.round(v * 32767), true); o += 2;
    }
  }
  return new Blob([out.buffer], { type: 'audio/wav' });
}

async function decoded(file) {
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!Ctx) return null;
  try {
    const buf = await file.arrayBuffer();
    return await new Ctx(2, 2, RATE).decodeAudioData(buf.slice(0));
  } catch { return null; }
}

// -> {name, label, seconds, kind, bytes, snr_db, turned_down}; throws with a message for the user
export async function uploadMySound(file, kind = 'other') {
  const buffer = await decoded(file);
  if (buffer && buffer.duration > MAX_SECONDS + 0.05) {
    throw new Error($t('mysounds.sound_is_seconds_long_sound', { duration: buffer.duration.toFixed(1), MAX_SECONDS }));
  }
  const body = buffer ? wavOf(buffer) : file;
  const r = await fetch(`/api/my_sound?name=${encodeURIComponent(file.name || 'sound')}&kind=${kind === 'voice' ? 'voice' : 'other'}`,
    { method: 'POST', headers: { 'Content-Type': (buffer ? 'audio/wav' : file.type) || 'application/octet-stream' }, body });
  const b = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(r.status === 415 ? $t('mysounds.this_kind_of_file_can') : (b.error || $t('mysounds.sound_could_not_be_added')));
  return b;
}

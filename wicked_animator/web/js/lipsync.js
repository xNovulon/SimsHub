// Lip-sync from a sound (needs.md section 11): the face follows a voice line or a sound file.
//   - loudness opens the mouth (the `open` slider channel);
//   - bright sounds ("ee", "ah" high) widen it (`smile`), dark ones ("oh", "oo") round it (`pout`);
//   - loud peaks lift the inner brows (`inner`) and half-close the eyes (`eyes`);
//   - blinking keeps going on top, and talking steps aside for that sound (its cue gets `lipsync: true`).
// The per-frame face is turned into as few face keys as follow it within a tolerance (keyFramesFor), written on
// the slider channel (key.face; face-only keys where the body has no key), so everything stays editable in the
// Face step. The mouth moving makes the export switch off the game's own lip-sync (flags.mouthMoves, event 19).
import { keyFramesFor, evaluateFace, sortKeys } from './animation.js';

export const TOLERANCE = 0.05;          // face keys follow the sound within 5% of a slider (about 1 degree of jaw)
const CHANNELS = ['open', 'smile', 'pout', 'inner', 'eyes'];
const LEAD = 2;                          // the mouth starts to move 2 frames before the sound (it breathes in)
const r3 = x => Math.round(x * 1000) / 1000;
const clamp01 = x => Math.min(1, Math.max(0, x));

// ---------------------------------------------------------------- sound in
// An AudioBuffer from a File/Blob, an ArrayBuffer or a URL. Decoding needs no sound device and no click.
export async function decodeSound(src) {
  let data = src;
  if (typeof src === 'string') {
    const r = await fetch(src);
    if (!r.ok) throw new Error(r.status === 404 ? 'That sound could not be found in your game.' : 'The sound could not be loaded.');
    data = await r.arrayBuffer();
  } else if (src && typeof src.arrayBuffer === 'function') data = await src.arrayBuffer();
  if (!(data instanceof ArrayBuffer)) throw new Error('Not a sound.');
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const ctx = new Ctx(1, 2, 44100);
  try { return await ctx.decodeAudioData(data.slice(0)); }
  catch { throw new Error('That file is not a sound this app can read - use a WAV, MP3 or OGG.'); }
}

// A game voice line in a sim's own adult voice (the game adds the actor code), as a URL for /api/sound.
export const voiceOf = sim => (sim && sim.voice) || (sim && sim.frame === 'ym' ? 'ma' : 'fa');
export function voiceLineUrl(name, voice) {
  return '/api/sound?name=' + encodeURIComponent(name) + (voice ? '&voice=' + encodeURIComponent(voice) : '');
}

// ---------------------------------------------------------------- analysis
// Per animation frame: loudness (RMS, linear), env (0..1: how open the mouth should be), bright (-1 dark .. +1 bright,
// against the sound's own middle) and peak (0..1: the loud moments).
export function analyse(buffer, fps = 30) {
  const sr = buffer.sampleRate, len = buffer.length, chans = buffer.numberOfChannels;
  const mono = new Float32Array(len);
  for (let c = 0; c < chans; c++) { const d = buffer.getChannelData(c); for (let i = 0; i < len; i++) mono[i] += d[i] / chans; }
  const n = Math.max(1, Math.ceil((len / sr) * fps));
  const hop = sr / fps, win = Math.round(hop * 1.5);
  const rms = new Float32Array(n), ratio = new Float32Array(n);
  for (let f = 0; f < n; f++) {
    const mid = (f + 0.5) * hop, a = Math.max(1, Math.round(mid - win / 2)), b = Math.min(len, Math.round(mid + win / 2));
    let e = 0, dsum = 0, k = 0;
    for (let i = a; i < b; i++) { const x = mono[i], dx = x - mono[i - 1]; e += x * x; dsum += dx * dx; k++; }
    rms[f] = k ? Math.sqrt(e / k) : 0;
    // brightness: how fast the wave changes against how big it is (the mean frequency, in effect)
    ratio[f] = e > 1e-12 ? Math.sqrt(dsum / e) : 0;
  }
  // loudness in dB, gated 34 dB under the loudest moment and scaled so the loud part of the sound opens fully
  const db = Array.from(rms, x => 20 * Math.log10(x + 1e-9));
  const top = Math.max(...db);
  const floor = Math.max(top - 34, quantile(db, 0.1) + 3);
  const env = new Float32Array(n), bright = new Float32Array(n), peak = new Float32Array(n);
  for (let f = 0; f < n; f++) env[f] = clamp01((db[f] - floor) / Math.max(6, top - 3 - floor));
  // the jaw is heavy: it opens fast and closes a little slower
  let s = 0;
  for (let f = 0; f < n; f++) { const x = env[f]; s += (x - s) * (x > s ? 0.75 : 0.45); env[f] = s; }
  const voiced = [];
  for (let f = 0; f < n; f++) if (env[f] > 0.15) voiced.push(ratio[f]);
  const mid = voiced.length ? quantile(voiced, 0.5) : 0, spread = voiced.length ? Math.max(1e-6, quantile(voiced, 0.85) - quantile(voiced, 0.15)) : 1;
  let bs = 0, ps = 0;
  for (let f = 0; f < n; f++) {
    const b = env[f] > 0.1 ? Math.max(-1, Math.min(1, (ratio[f] - mid) / spread * 1.4)) : 0;
    bs += (b - bs) * 0.5; bright[f] = bs;
    const pk = clamp01((env[f] - 0.62) / 0.3);
    ps += (pk - ps) * (pk > ps ? 0.6 : 0.2); peak[f] = ps;
  }
  return { n, fps, sec: len / sr, rms, env, bright, peak };
}
function quantile(arr, q) {
  const a = Array.from(arr).sort((x, y) => x - y);
  if (!a.length) return 0;
  const i = Math.min(a.length - 1, Math.max(0, Math.round(q * (a.length - 1))));
  return a[i];
}

// The face for each frame of the sound: {open, smile, pout, inner, eyes} (slider values).
// strength: how far the mouth opens (1 = a full moan opens about 19 degrees); brows: the loud moments show on the
// brows and the eyes too.
export function faceTrack(an, { strength = 1, brows = true, smooth = 2 } = {}) {
  const out = [];
  // a face can't change shape 30 times a second: the mouth shape and the brows follow the sound's syllables, not
  // its flicker (a light [1 2 1] blur, `smooth` times; the loudness keeps its own fast jaw)
  const blur = (arr, times) => {
    let a = Float32Array.from(arr);
    for (let k = 0; k < times; k++) {
      const b = new Float32Array(a.length);
      for (let i = 0; i < a.length; i++) b[i] = (a[Math.max(0, i - 1)] + 2 * a[i] + a[Math.min(a.length - 1, i + 1)]) / 4;
      a = b;
    }
    return a;
  };
  const env = blur(an.env, Math.min(1, smooth)), bright = blur(an.bright, smooth * 2), peak = blur(an.peak, smooth);
  for (let f = 0; f < an.n; f++) {
    const e = env[f], b = bright[f], pk = peak[f];
    const face = { open: clamp01(strength * 0.8 * Math.pow(e, 0.9)) };
    face.smile = b > 0 ? clamp01(0.42 * b * e * strength) : 0;
    face.pout = b < 0 ? clamp01(0.55 * -b * e * strength) : 0;
    face.inner = brows ? clamp01(0.75 * pk + 0.15 * e) : 0;
    face.eyes = brows ? clamp01(0.45 * pk) : 0;
    out.push(face);
  }
  return out;
}

// ---------------------------------------------------------------- writing keys
// The sound's face onto a sim, starting at `start` (a frame): each channel shows the more of what was there and what
// the sound gives, so running it twice changes nothing. -> {keys, frames: [first, last], made}
export function writeLipSync(app, sim, track, start, { tolerance = TOLERANCE } = {}) {
  const p = app.store.project, L = Math.max(1, p.length), loop = !!p.loop;
  let n = track.length;
  if (n > L) n = L;
  // the frames it covers: a short lead-in (the face as it was), the sound, and one frame after it
  let from = start - LEAD, to = start + n;                // `to` inclusive: the face as it was again
  if (!loop) { from = Math.max(0, from); to = Math.min(L - 1, to); }
  let span = to - from + 1;
  if (span > L) { span = L; to = from + L - 1; }
  const frameAt = i => ((from + i) % L + L) % L;
  const base = [], target = [];
  for (let i = 0; i < span; i++) {
    const f = frameAt(i);
    const b = evaluateFace(sim.keys, f, L, loop) || {};
    base.push(b);
    const t = { ...b };
    const k = from + i - start;                          // this frame's place in the sound
    const lip = k >= 0 && k < track.length ? track[k] : null;
    if (lip) for (const c of CHANNELS) t[c] = Math.max(b[c] || 0, lip[c] || 0);
    for (const c of Object.keys(t)) t[c] = r3(t[c]);
    target.push(t);
  }
  const empty = { rot: {}, pos: {} };
  const at = keyFramesFor(new Array(span).fill(empty), target, false, { face: tolerance });
  // a key that already holds a face inside the stretch takes the new face too, so the curve runs through it
  const keep = new Set(at);
  for (let i = 0; i < span; i++) { const k = sim.keys.find(x => x.frame === frameAt(i)); if (k && k.face) keep.add(i); }
  let made = 0;
  for (const i of [...keep].sort((a, b) => a - b)) {
    const f = frameAt(i);
    let key = sim.keys.find(x => x.frame === f);
    if (!key) {
      const v = app.simViews.get(sim.id);
      if (typeof app._base === 'function') app._base({ sim, v }, f); else app.pipeline.base({ sim, v }, f);
      key = { frame: f, ease: 'linear', faceOnly: true, pose: typeof app._bodyPose === 'function' ? app._bodyPose(v) : v.getPose() };
      sim.keys.push(key);
      made++;
    }
    key.face = target[i];
  }
  sortKeys(sim.keys);
  return { keys: keep.size, made, frames: [frameAt(0), frameAt(span - 1)], base, target, from, span };
}

// ---------------------------------------------------------------- the whole thing
// source: {name} a game voice line (played in the sim's voice), {file} a File/Blob, {buffer} an AudioBuffer, or
// {url}. opts: frame (where the sound starts; default the playhead), strength, brows, addSound (a game voice line
// becomes one of the sim's voice sounds, so it plays in the preview and in the game; default true).
// -> {keys, made, frames, sec, name, analysis}
export async function lipSync(app, simId, source, opts = {}) {
  const sim = app.store.sim(simId);
  if (!sim) throw new Error('Select a sim first.');
  const p = app.store.project, fps = p.fps || 30;
  const frame = Math.max(0, Math.min(p.length - 1, Math.round(opts.frame ?? app.store.frame)));
  let buffer = source.buffer || null;
  if (!buffer) {
    const url = source.name ? voiceLineUrl(source.name, source.voice || voiceOf(sim)) : source.url;
    buffer = await decodeSound(source.file || url);
  }
  const an = analyse(buffer, fps);
  if (!an.env.some(x => x > 0.05)) throw new Error('That sound is silent - nothing for the mouth to follow.');
  const track = faceTrack(an, opts);
  if (app.playing) app.setPlaying(false);
  if (opts.checkpoint !== false) app.store.checkpoint();
  const res = writeLipSync(app, sim, track, frame, opts);
  if (source.name && opts.addSound !== false) {
    sim.sounds = sim.sounds || [];
    const cue = sim.sounds.find(x => x.kind === 'voice' && x.name === source.name && x.frame === frame);
    if (cue) cue.lipsync = true;
    else sim.sounds.push({ frame, name: source.name, kind: 'voice', lipsync: true });
  }
  app.applyPoses(false);
  app.afterEdit();
  if (app.emit) app.emit('keyed', { simId, frame, kind: 'face' });
  return { ...res, sec: an.sec, name: source.name || (source.file && source.file.name) || '', analysis: an, frame };
}

// Every voice sound of a sim that is not lip-synced yet (or all of them with {all: true}) -> [{cue, result}]
export async function lipSyncVoices(app, simId, opts = {}) {
  const sim = app.store.sim(simId);
  if (!sim) return [];
  const cues = (sim.sounds || []).filter(x => x.kind === 'voice' && (opts.all || !x.lipsync));
  if (!cues.length) return [];
  app.store.checkpoint();
  const out = [];
  for (const cue of cues) {
    try {
      const r = await lipSync(app, simId, { name: cue.name }, { ...opts, frame: cue.frame, checkpoint: false });
      out.push({ cue, result: r });
    } catch (err) { out.push({ cue, error: String((err && err.message) || err) }); }
  }
  return out;
}

// Hearing the animation: the game's own sounds (decoded by the server from EA's audio format) play when the
// playhead passes them, like in the game. Each sound is fetched and decoded once per voice.
//
// Voices (spec_game 2): the game's voice lines ('vo_...' / 'voe_...') are saved without a voice, and in the game every
// sim says them in its own voice. Here each sim has a voice of its own too (sim.voice: fa fc fd female, ma mb mc
// male - all adult voices), and a line is fetched in that voice (/api/sound?voice=). Child and special voices are
// never used.
import { localStorageGet, localStorageSet } from './state.js';

// ---------------------------------------------------------------- the sims' voices
export const ADULT_CODES = { female: ['fa', 'fc', 'fd'], male: ['ma', 'mb', 'mc'] };
const ALL_ADULT = [...ADULT_CODES.female, ...ADULT_CODES.male, 'fb', 'md'];
export const NOT_ADULT = ['ca', 'cb', 'cc', 'cd', 'pa', 'ho', 're', 'ky', 'al'];        // child and special voices
// the line every voice button plays
export const SAMPLE_LINE = 'vo_expr_moan_pleasure_30f_cm';

// The actor code a voice line was saved with ('' = none: the game adds each sim's own voice).
export function voiceCode(name) {
  const m = /^voe?_.*_([a-z]{2})$/i.exec(name || '');
  const c = m ? m[1].toLowerCase() : '';
  return ALL_ADULT.includes(c) || NOT_ADULT.includes(c) ? c : '';
}
export const isVoiceLine = name => /^voe?_/i.test(name || '');
// The voice a sim speaks with here: its own (Tray sims come with theirs), else by its body.
export function simVoice(sim) { return (sim && sim.voice) || (sim && sim.frame === 'ym' ? 'ma' : 'fa'); }
// (older name, kept for code that still asks for it)
export function simVoiceCode(sim) { return simVoice(sim); }
// Can this sound be given to this sim? Voice lines of children never; a line saved with a voice of the other
// gender does not fit either. Lines without a voice fit everyone (the game says them in the sim's own voice).
export function soundFitsSim(name, sim) {
  if (!isVoiceLine(name)) return true;
  const c = voiceCode(name);
  if (!c) return true;
  if (NOT_ADULT.includes(c)) return false;
  return (c[0] === 'm') === (simVoice(sim)[0] === 'm');
}
// The voice to fetch a sound in for this sim ('' = as written: not a voice line, or saved with its own voice).
export function voiceFor(name, sim) { return isVoiceLine(name) && !voiceCode(name) ? simVoice(sim) : ''; }
// "Voice 2" (female) / "Voice 3" (male)
export function voiceLabel(code) {
  const f = ADULT_CODES.female.indexOf(code), m = ADULT_CODES.male.indexOf(code);
  return f >= 0 ? `Voice ${f + 1}` : m >= 0 ? `Voice ${m + 1}` : code || '';
}

// ---------------------------------------------------------------- kinds of voice lines
// Tags the server gives every game line (/api/voices); creator sounds get the same tags from their name.
const TAGS = [['climax', /finish/], ['woohoo', /woohoo/], ['moan', /moan|mmm|purr|swoon|pleasure/],
  ['breath', /breath|pant|sigh|gasp|exhale|inhale/], ['kiss', /kiss|makeout|smooch/],
  ['flirt', /flirt|seduc|sexy|romantic|whisper/], ['laugh', /laugh|giggle|chuckle/],
  ['effort', /grunt|effort|strain/], ['pain', /pain|ouch|hurt/]];
export function tagsOf(name) { const n = String(name || '').toLowerCase(); return TAGS.filter(([, rx]) => rx.test(n)).map(([t]) => t); }
// lines that never sound sexy, whatever their tag says (a lightsaber duel's "finisher", a frog kiss, a bored sigh)
const NOT_SEXY = /fail|frog|poison|mermaid|putdown|lightsaber|magicduel|ghost|dumpster|snowpal|thanatology|unfinished|scold|angry|annoy|disgust|bored|disappoint|frustrat|_sad|mourn|death|puke|vomit|sick|cold|sleep|tired|cheek|blowkiss|greet|propose|actinggig|archery|climbing|computer|meditation|ecofootprint|funnyfaces|burglar|celldoor|cas_stories|cas_featured|trait/;
const line = x => (typeof x === 'string' ? { name: x, tags: tagsOf(x) } : x && !x.tags ? { ...x, tags: tagsOf(x.name) } : x || { name: '', tags: [] });
const has = (x, t) => x.tags.includes(t);
const ok = x => !NOT_SEXY.test(String(x.name).toLowerCase());
// [id, label, test]: test takes a /api/voices line, a creator sound or just a name (test.test(x) works too, for
// code that still treats it as a regular expression)
const set = fn => { const t = x => { const l = line(x); return !!l.name && fn(l, String(l.name).toLowerCase()); }; t.test = t; return t; };
export const VOICE_SETS = [
  ['moan_soft', 'Soft moans', set((x, n) => ok(x) && ((has(x, 'moan') && !/discomfort|uncomfortable/.test(n)) || has(x, 'kiss') || /makeout_breathe/.test(n)))],
  ['moan', 'Moans', set((x, n) => ok(x) && (has(x, 'moan') || (has(x, 'woohoo') && /loop/.test(n))))],
  ['woohoo', "WooHoo (the game's own)", set((x, n) => ok(x) && has(x, 'woohoo') && /loop/.test(n))],
  ['climax', 'Climax', set(x => ok(x) && has(x, 'climax'))],
  ['breath', 'Breathing & sighs', set(x => ok(x) && has(x, 'breath'))],
  ['kiss', 'Kisses', set(x => ok(x) && has(x, 'kiss'))],
  ['any', 'Any voice', set(() => true)],
];
// How well a line fits an adult animation (0 best): moans, WooHoo, climax, breathing and kisses first, then flirting,
// then the rest; lines that never sound sexy and EA's rare 'lowprob' takes last.
const TAG_ORDER = ['woohoo', 'moan', 'climax', 'breath', 'kiss', 'flirt'];
export function lineRank(x) {
  const l = line(x);
  const t = TAG_ORDER.findIndex(tag => has(l, tag));
  return (ok(l) ? 0 : 20) + (t < 0 ? 10 : t) + (l.lowprob || /lowprob/i.test(l.name) ? 40 : 0);
}
// a kind with no lines for a sim falls back to a broader one
export const VOICE_FALLBACK = {
  moan_soft: ['moan_soft', 'moan', 'any'], moan: ['moan', 'any'], woohoo: ['woohoo', 'moan', 'any'],
  climax: ['climax', 'moan', 'any'], breath: ['breath', 'any'], kiss: ['kiss', 'moan_soft', 'any'], any: ['any'],
};

// ---------------------------------------------------------------- playing sounds
export class SoundPlayer {
  constructor() {
    this.ctx = null;
    this.buffers = new Map();     // name|voice -> AudioBuffer | Promise | null (failed)
    this.muted = localStorageGet('muted', false);
    this.volume = localStorageGet('volume', 0.85);
    this.failed = new Set();
    // plain names of voice lines are left to whoever preloads them with their sim's voice (features/game.js)
    this.voiceAware = false;
  }

  // Browsers only allow sound after a click; call this from a click (Play, a preview button...).
  ensure() {
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      this.ctx = new AC();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.volume;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  setMuted(on) { this.muted = !!on; localStorageSet('muted', this.muted); }
  setVolume(v) { this.volume = v; localStorageSet('volume', v); if (this.master) this.master.gain.value = v; }

  static key(name, voice = '') { return voice ? name + '|' + voice : name; }

  // A voice line that does not exist in that voice is played as written (the game's own choice of voice).
  load(name, voice = '') {
    const key = SoundPlayer.key(name, voice);
    if (this.buffers.has(key)) return Promise.resolve(this.buffers.get(key));
    if (!this.ensure()) return Promise.resolve(null);
    const url = '/api/sound?name=' + encodeURIComponent(name) + (voice ? '&voice=' + encodeURIComponent(voice) : '');
    const p = fetch(url)
      .then(r => { if (!r.ok) throw new Error('not found'); return r.arrayBuffer(); })
      .then(buf => this.ctx.decodeAudioData(buf))
      .then(b => { this.buffers.set(key, b); return b; })
      .catch(() => {
        if (voice) return this.load(name, '').then(b => { this.buffers.set(key, b); return b; });
        this.buffers.set(key, null); this.failed.add(name); return null;
      });
    this.buffers.set(key, p);
    return p;
  }

  // items: names or {name, voice}
  preload(items) {
    const seen = new Set();
    for (const it of items || []) {
      const name = typeof it === 'string' ? it : it && it.name;
      const voice = typeof it === 'string' ? '' : (it && it.voice) || '';
      if (!name) continue;
      if (this.voiceAware && !voice && typeof it === 'string' && isVoiceLine(name) && !voiceCode(name)) continue;
      const key = SoundPlayer.key(name, voice);
      if (seen.has(key)) continue;
      seen.add(key);
      if (!this.buffers.has(key)) this.load(name, voice);
    }
  }

  // Play now. pan: -1 (left) .. 1 (right); voice: the actor code to say a voice line in; detune: cents (a sim's
  // own pitch). Returns false if the sound can't be played.
  async play(name, { gain = 1, pan = 0, force = false, voice = '', detune = 0 } = {}) {
    if (this.muted && !force) return false;
    if (!this.ensure()) return false;
    const key = SoundPlayer.key(name, voice);
    let b = this.buffers.get(key);
    if (b === undefined || b instanceof Promise) b = await this.load(name, voice);
    if (!b) return false;
    const src = this.ctx.createBufferSource();
    src.buffer = b;
    if (detune && src.detune) src.detune.value = Math.max(-1200, Math.min(1200, detune));
    const g = this.ctx.createGain();
    g.gain.value = gain;
    let node = src.connect(g);
    if (this.ctx.createStereoPanner) {
      const p = this.ctx.createStereoPanner();
      p.pan.value = Math.max(-1, Math.min(1, pan));
      node.connect(p); node = p;
    }
    node.connect(this.master);
    src.start();
    return true;
  }

  // Sounds whose frame the playhead crossed between `from` and `to` (wrapping at the loop end).
  static crossed(sounds, from, to, length) {
    if (to === from) return [];
    const hit = f => (to > from ? f > from && f <= to : f > from || f <= to);
    return (sounds || []).filter(s => hit(s.frame % length));
  }
}

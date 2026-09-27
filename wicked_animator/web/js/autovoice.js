// Random voices (spec_sounds R3): a sim's moans and lines that are not on the timeline. autoVoiceSchedule turns
// each sim's `autoVoice` setting ({on, set, every, shuffle}) into a fresh list of {frame, name, kind:'voice'}
// cues - never written into sim.sounds, so the timeline, drag and key edits never see them. Cues are spread
// through the loop and kept apart: from each other, from the same sim's other cues, and from every voice already
// placed by hand or by an older version of "Add random voice" (kind 'voice' sitting in sim.sounds - the exclusion
// zone). The seed comes from the sim's id and its `shuffle` count, never Math.random(), so the same project gives
// the same pattern until Shuffle is pressed.
import { VOICE_FALLBACK } from './audio.js';

// A candidate that still collides after this many nudges is placed anyway - a cue is never silently dropped.
const NUDGE_TRIES = 6;

function lcg(seed) {
  let s = (seed >>> 0) || 1;
  return () => (s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
}
// A number from the sim's id and its shuffle count (same idiom as face.js's blinkAt seed): stable across reloads,
// different once Shuffle bumps the count.
function seedOf(sim, shuffle) {
  let h = 0;
  for (const c of String(sim.id) + '|' + (shuffle || 0)) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h || 1;
}
// The shorter way around a loop of length L between frames a and b.
function loopGap(a, b, L) { const d = Math.abs(a - b) % L; return Math.min(d, L - d); }

// Map<simId, [{frame, name, kind:'voice'}]> - empty for a sim with autoVoice off or no lines to use.
export function autoVoiceSchedule(app, project) {
  const out = new Map();
  const fps = project.fps || 30, L = Math.max(1, project.length);
  // every voice already on the timeline (hand-placed, or baked by an older version): the exclusion zone no
  // random cue may crowd, whichever sim it belongs to
  const placed = [];
  for (const s of project.sims || []) for (const snd of s.sounds || []) if (snd.kind === 'voice') placed.push(snd.frame);
  for (const sim of project.sims || []) {
    const cues = [];
    out.set(sim.id, cues);
    const av = sim.autoVoice;
    if (!av || !av.on) continue;
    let pool = [];
    for (const k of VOICE_FALLBACK[av.set] || ['any']) { pool = app.voicePool(sim, k); if (pool.length) break; }
    if (!pool.length) continue;
    const every = av.every || 3;
    const n = Math.max(1, Math.round(L / fps / every));
    const rnd = lcg(seedOf(sim, av.shuffle));
    const ownGap = Math.round(Math.max(1.6, every * 0.45) * fps);     // this sim's own cues: "not too close"
    const crossGap = Math.round(0.9 * fps);                            // any other voice, hand-placed or random
    const clear = f => placed.every(t => loopGap(f, t, L) >= crossGap) && cues.every(c => loopGap(f, c.frame, L) >= ownGap);
    for (let k = 0; k < n; k++) {
      let frame = Math.round(((k + 0.2 + rnd() * 0.6) / n) * L) % L;
      for (let tries = 0; tries < NUDGE_TRIES && !clear(frame); tries++) frame = (frame + Math.round(fps * 0.5)) % L;
      const snd = pool[Math.floor(rnd() * pool.length)];
      cues.push({ frame, name: snd.name, kind: 'voice' });
      placed.push(frame);
    }
  }
  return out;
}

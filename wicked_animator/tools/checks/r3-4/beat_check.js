// R3-4 check: finding the beat (web/js/beat.js) on generated click tracks, in Node (no browser, nothing written).
//   node tools/checks/r3-4/beat_check.js
// Every track must come out within +-2 BPM (the plan's bar), and the first beat within 25 ms. Tracks: plain clicks,
// clicks with an accent every 4th beat under noise, a kick / snare / hi-hat groove, and a groove with a swung
// off-beat; tempos 70-180 BPM, 20-40 s long, at 44.1 and 48 kHz. Tap tempo and phrase() are checked too.
const fs = require('fs');
const path = require('path');
const H = require('../lib/harness.js');

const ROOT = path.join(__dirname, '..', '..', '..');

async function loadBeat() {
  const src = fs.readFileSync(path.join(ROOT, 'web', 'js', 'beat.js'), 'utf8');
  return import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
}

// a tiny deterministic random
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }

function track(kind, bpm, { sr = 44100, secs = 30, offset = 0.137, seed = 1 } = {}) {
  const n = Math.round(sr * secs), x = new Float32Array(n), rnd = rng(seed), period = 60 / bpm;
  const add = (t0, fn, len) => { const a = Math.round(t0 * sr), m = Math.round(len * sr); for (let i = 0; i < m && a + i < n; i++) if (a + i >= 0) x[a + i] += fn(i / sr); };
  const click = (amp, f = 1500) => t => amp * Math.sin(2 * Math.PI * f * t) * Math.exp(-t / 0.006);
  const kick = amp => t => amp * Math.sin(2 * Math.PI * (55 + 90 * Math.exp(-t / 0.03)) * t) * Math.exp(-t / 0.12);
  const noise = (amp, d) => t => amp * (rnd() * 2 - 1) * Math.exp(-t / d);
  let beat = 0;
  for (let t = offset; t < secs; t += period, beat++) {
    if (kind === 'click') add(t, click(0.8), 0.05);
    else if (kind === 'accent') add(t, click(beat % 4 === 0 ? 0.9 : 0.45, beat % 4 === 0 ? 2000 : 1200), 0.05);
    else if (kind === 'groove' || kind === 'swing') {
      add(t, kick(0.9), 0.35);
      if (beat % 2 === 1) add(t, noise(0.5, 0.05), 0.2);                                // snare on 2 and 4
      const off = kind === 'swing' ? period * 0.62 : period / 2;
      add(t + off, noise(0.18, 0.012), 0.05);                                            // hi-hat between beats
    }
  }
  if (kind === 'accent' || kind === 'groove' || kind === 'swing') for (let i = 0; i < n; i++) x[i] += 0.03 * (rnd() * 2 - 1);
  return x;
}

(async () => {
  const B = await loadBeat();
  const rows = [];
  const tempos = [70, 84, 92, 100, 108, 116, 120, 124, 128, 132, 140, 150, 160, 172, 180];
  const kinds = ['click', 'accent', 'groove', 'swing'];
  let worst = 0, worstPhase = 0, n = 0, total = 0;
  for (const kind of kinds) {
    for (const bpm of tempos) {
      const sr = (bpm % 3 === 0) ? 48000 : 44100, secs = 20 + (bpm % 5) * 4, offset = 0.05 + ((bpm * 7) % 40) / 100;
      const x = track(kind, bpm, { sr, secs, offset, seed: bpm });
      const t0 = Date.now();
      const r = B.detectTempo(x, sr);
      total += Date.now() - t0;
      const err = r.bpm - bpm;
      const per = 60 / bpm;
      let ph = Math.abs(((r.offset - offset) % per + per) % per);
      ph = Math.min(ph, per - ph);
      worst = Math.max(worst, Math.abs(err));
      worstPhase = Math.max(worstPhase, ph);
      n++;
      rows.push({ name: `${kind} ${bpm} BPM (${sr / 1000} kHz, ${secs} s)`, ok: Math.abs(err) <= 2 && ph <= 0.025,
        detail: `found ${r.bpm} (off by ${err.toFixed(2)}), first beat off by ${(ph * 1000).toFixed(0)} ms (signed ${(((((r.offset - offset) % per) + 1.5 * per) % per - per / 2) * 1000).toFixed(0)}), confidence ${r.confidence}` });
    }
  }
  rows.push({ name: `all ${n} tracks within +-2 BPM`, ok: worst <= 2, detail: `worst ${worst.toFixed(2)} BPM, worst first-beat ${(worstPhase * 1000).toFixed(0)} ms, ${(total / n).toFixed(0)} ms per track` });
  // silence and very short input never crash
  const quiet = B.detectTempo(new Float32Array(44100 * 5), 44100);
  rows.push({ name: 'silence gives no tempo, no crash', ok: quiet && typeof quiet.bpm === 'number', detail: quiet });
  const tiny = B.detectTempo(new Float32Array(100), 44100);
  rows.push({ name: 'a 2 ms sound gives no tempo', ok: tiny.bpm === 0, detail: tiny });
  // tap tempo: 8 taps at 125 BPM with +-12 ms of human wobble, one double tap, and a restart after a pause
  const tt = new B.TapTempo();
  const rnd = rng(7);
  let t = 1000, got = null;
  for (let i = 0; i < 8; i++) { got = tt.tap(t + (rnd() * 24 - 12)); t += 480; if (i === 4) tt.tap(t - 470); }
  rows.push({ name: 'tap tempo: 125 BPM tapped by hand', ok: got !== null && Math.abs(got - 125) <= 2, detail: got });
  const restart = tt.tap(t + 5000);
  rows.push({ name: 'tap tempo: a 5 s pause starts over', ok: restart === null, detail: restart });
  // phrase(): 16 beats as whole frames, the tempo nudged less than 1 BPM
  const ph = [120, 128, 97.3, 140].map(b => ({ b, p: B.phrase(b, { fps: 30, beats: 16 }) }));
  rows.push({ name: 'phrase: 16 beats = whole frames, tempo kept within 1 BPM', ok: ph.every(({ b, p }) => Number.isInteger(p.frames) && Math.abs(p.bpm - b) < 1 && p.beats === 16),
    detail: ph.map(({ b, p }) => `${b}->${p.bpm} (${p.frames}f)`).join(', ') });
  const ok = H.report(rows, 'R3-4 beat detection (web/js/beat.js)');
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(e); process.exit(1); });

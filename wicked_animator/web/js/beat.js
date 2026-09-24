// The beat of a song, found on this PC (nothing leaves it), and tap tempo (R3-4, Strip club dances).
//
//   detectTempo(samples, sampleRate)  -> {bpm, offset, confidence}   the tempo of mono samples (Float32Array)
//   decodeAudio(file | ArrayBuffer)    -> {samples, sampleRate, duration, buffer}   (WebAudio, in the browser)
//   findBeat(file)                     -> decodeAudio + detectTempo in one go (+ the decoded buffer to play it)
//   new TapTempo().tap(ms)             -> bpm once there are 3 taps (a pause of 2 s starts over)
//   phrase(bpm, {fps, beats})          -> the loop length in frames for a whole number of beats
//
// How the beat is found: an onset curve (spectral flux in 5 ms steps - how much louder each band got), its
// autocorrelation, and a comb over the first four multiples of every tempo from 60 to 200 BPM in 0.02 BPM steps
// (the multiples make it exact to a fraction of a BPM). A slight preference for 90-150 BPM (what people dance to)
// settles half/double tempo; the first beat is where the comb of that tempo lines up with the onsets best.
// Pure maths, no DOM: tools/checks/r3-4 runs it in Node on generated click tracks.

const TAU = Math.PI * 2;
const WIN_DELAY = 0.036;        // seconds from a sound to the onset curve's peak (the 512-sample window at 11 kHz, measured on clicks)

// ---------------------------------------------------------------- FFT (radix 2, in place)
function fft(re, im) {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = -TAU / len, wr = Math.cos(ang), wi = Math.sin(ang), half = len >> 1;
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let k = 0; k < half; k++) {
        const a = i + k, b = a + half;
        const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
        re[b] = re[a] - tr; im[b] = im[a] - ti;
        re[a] += tr; im[a] += ti;
        const nr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = nr;
      }
    }
  }
}

// Mono samples at about 11 kHz (averaging keeps the kick and the hats' energy; plenty for the beat).
function downsample(samples, sampleRate) {
  const step = Math.max(1, Math.round(sampleRate / 11025));
  if (step === 1) return { x: samples, sr: sampleRate };
  const n = Math.floor(samples.length / step), x = new Float32Array(n);
  for (let i = 0; i < n; i++) { let s = 0; for (let k = 0; k < step; k++) s += samples[i * step + k]; x[i] = s / step; }
  return { x, sr: sampleRate / step };
}

// Onset strength every `hop` seconds: positive log-magnitude change summed over 24 bands (spectral flux).
export function onsetCurve(samples, sampleRate, { hop = 0.005, win = 512 } = {}) {
  const { x, sr } = downsample(samples, sampleRate);
  const H = Math.max(1, Math.round(sr * hop)), N = win, frames = Math.max(0, Math.floor((x.length - N) / H) + 1);
  const bands = 24, re = new Float64Array(N), im = new Float64Array(N), w = new Float64Array(N);
  for (let i = 0; i < N; i++) w[i] = 0.5 - 0.5 * Math.cos(TAU * i / (N - 1));
  // band edges on a rough log scale between 40 Hz and 5 kHz
  const edges = [];
  for (let b = 0; b <= bands; b++) edges.push(Math.max(1, Math.min(N / 2, Math.round((40 * Math.pow(5000 / 40, b / bands)) / sr * N))));
  const prev = new Float64Array(bands), out = new Float32Array(frames);
  for (let f = 0; f < frames; f++) {
    const o = f * H;
    for (let i = 0; i < N; i++) { re[i] = x[o + i] * w[i]; im[i] = 0; }
    fft(re, im);
    let flux = 0;
    for (let b = 0; b < bands; b++) {
      let e = 0;
      const lo = edges[b], hi = Math.max(lo + 1, edges[b + 1]);
      for (let k = lo; k < hi; k++) e += re[k] * re[k] + im[k] * im[k];
      const l = Math.log1p(1000 * e / (hi - lo));
      if (f && l > prev[b]) flux += l - prev[b];
      prev[b] = l;
    }
    out[f] = flux;
  }
  // take away the slow loudness changes (a moving mean over ~0.4 s) and keep what sticks out
  const R = Math.max(1, Math.round(0.2 / hop)), res = new Float32Array(frames);
  let acc = 0;
  const pre = new Float64Array(frames + 1);
  for (let i = 0; i < frames; i++) { acc += out[i]; pre[i + 1] = acc; }
  for (let i = 0; i < frames; i++) {
    const a = Math.max(0, i - R), b = Math.min(frames, i + R + 1);
    res[i] = Math.max(0, out[i] - (pre[b] - pre[a]) / (b - a));
  }
  return { curve: res, rate: 1 / (H / sr) };
}

// Autocorrelation of the onset curve for lags 0..maxLag (biased: longer lags weigh a little less, which is what
// favours the true tempo over its half).
function autocorr(c, maxLag) {
  const n = c.length, out = new Float64Array(maxLag + 2);
  let mean = 0;
  for (let i = 0; i < n; i++) mean += c[i];
  mean /= n || 1;
  const d = new Float64Array(n);
  for (let i = 0; i < n; i++) d[i] = c[i] - mean;
  for (let lag = 0; lag <= maxLag + 1 && lag < n; lag++) {
    let s = 0;
    for (let i = 0; i + lag < n; i++) s += d[i] * d[i + lag];
    out[lag] = s / n;
  }
  return out;
}

const at = (arr, x) => {           // linear interpolation between samples
  const i = Math.floor(x), f = x - i;
  if (i < 0 || i + 1 >= arr.length) return 0;
  return arr[i] * (1 - f) + arr[i + 1] * f;
};

// The tempo of mono samples. -> {bpm, offset (seconds to the first beat), confidence 0..1, period (seconds)}
export function detectTempo(samples, sampleRate, { min = 60, max = 200, prefer = 120, maxSeconds = 120 } = {}) {
  if (!samples || !samples.length || !sampleRate) return { bpm: 0, offset: 0, confidence: 0, period: 0 };
  // a long song: a stretch from its middle is enough (and quicker)
  let s = samples;
  const most = Math.floor(maxSeconds * sampleRate);
  let skip = 0;
  if (s.length > most) { skip = Math.floor((s.length - most) / 2); s = s.subarray(skip, skip + most); }
  const { curve, rate } = onsetCurve(s, sampleRate);
  if (curve.length < rate * 2) return { bpm: 0, offset: 0, confidence: 0, period: 0 };
  let energy = 0;
  for (let i = 0; i < curve.length; i++) energy += curve[i];
  if (!(energy > 1e-6)) return { bpm: 0, offset: 0, confidence: 0, period: 0 };
  const K = 4, maxLag = Math.ceil(rate * 60 / min * K * 2) + 2;
  const ac = autocorr(curve, Math.min(maxLag, curve.length - 2));
  const zero = ac[0] || 1;
  const comb = b => { const lag = rate * 60 / b; let sc = 0; for (let k = 1; k <= K; k++) sc += at(ac, lag * k); return sc / (K * zero); };
  // people dance at 90-150: a gentle log-Gaussian preference around `prefer` settles most half / double tempos
  const prior = b => 0.75 + 0.25 * Math.exp(-0.5 * (Math.log2(b / prefer) / 0.9) ** 2);
  const search = (lo, hi, step = 0.02) => {
    let best = null;
    const scores = [];
    for (let b = lo; b <= hi + 1e-9; b += step) {
      const sc = comb(b) * prior(b);
      scores.push([b, sc]);
      if (!best || sc > best[1]) best = [b, sc];
    }
    // refine: a parabola through the best score and its neighbours
    const i = scores.indexOf(best);
    let b = best[0];
    if (i > 0 && i < scores.length - 1) {
      const [s0, s1, s2] = [scores[i - 1][1], scores[i][1], scores[i + 1][1]];
      const den = s0 - 2 * s1 + s2;
      if (Math.abs(den) > 1e-12) b += step * Math.max(-0.5, Math.min(0.5, 0.5 * (s0 - s2) / den));
    }
    return { bpm: b, score: best[1], scores };
  };
  let found = search(min, max);
  // half or double? At the double tempo's period p, beats in between show up at p and 3p (odd multiples); a true
  // half-time feel has them only at 2p and 4p. Clicks on every beat of a fast song -> the faster one.
  const oddEven = b => { const p = rate * 60 / b; const odd = at(ac, p) + at(ac, 3 * p), even = at(ac, 2 * p) + at(ac, 4 * p); return even > 0 ? odd / even : 0; };
  if (found.bpm * 2 <= max && oddEven(found.bpm * 2) > 0.55) found = { ...search(found.bpm * 2 * 0.97, found.bpm * 2 * 1.03), scores: found.scores };
  else if (found.bpm / 2 >= min && oddEven(found.bpm) < 0.3) found = { ...search(found.bpm / 2 * 0.97, found.bpm / 2 * 1.03), scores: found.scores };
  let bpm = found.bpm, second = 0;
  for (const [b2, sc] of found.scores) if (Math.abs(Math.log2(b2 / bpm)) > 0.08 && sc > second) second = sc;
  const best = [bpm, comb(bpm) * prior(bpm)];
  const period = rate * 60 / bpm;
  // the first beat: the phase where the onsets line up best with this tempo
  let bestPhase = 0, bestSum = -1;
  const steps = Math.max(16, Math.round(period * 4));
  for (let p = 0; p < steps; p++) {
    const ph = (p / steps) * period;
    let sum = 0;
    for (let t = ph; t < curve.length - 1; t += period) sum += at(curve, t) + 0.5 * (at(curve, t - 1) + at(curve, t + 1));
    if (sum > bestSum) { bestSum = sum; bestPhase = ph; }
  }
  // an onset shows when the sound reaches the middle of the analysis window: the beat is that much later
  const offset = ((skip / sampleRate + bestPhase / rate + WIN_DELAY) % (60 / bpm) + 60 / bpm) % (60 / bpm);
  const confidence = Math.max(0, Math.min(1, best[1] > 0 ? 1 - second / best[1] : 0) * 2);
  return { bpm: Math.round(bpm * 100) / 100, offset, confidence: Math.round(Math.min(1, confidence) * 100) / 100, period: 60 / bpm };
}

// ---------------------------------------------------------------- the browser side
// A dropped song -> its samples (mono) with WebAudio; nothing is uploaded.
export async function decodeAudio(input) {
  const data = input instanceof ArrayBuffer ? input : await input.arrayBuffer();
  const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const ctx = Ctx ? new Ctx(1, 2, 44100) : new (window.AudioContext || window.webkitAudioContext)();
  const buffer = await new Promise((res, rej) => {
    const p = ctx.decodeAudioData(data.slice(0), res, rej);
    if (p && p.then) p.then(res, rej);
  });
  const n = buffer.length, ch = buffer.numberOfChannels;
  let samples;
  if (ch === 1) samples = buffer.getChannelData(0);
  else {
    samples = new Float32Array(n);
    for (let c = 0; c < ch; c++) { const d = buffer.getChannelData(c); for (let i = 0; i < n; i++) samples[i] += d[i] / ch; }
  }
  return { samples, sampleRate: buffer.sampleRate, duration: buffer.duration, buffer };
}

export async function findBeat(input, opts = {}) {
  const a = await decodeAudio(input);
  // the maths takes a moment on a long song: let the page paint "Listening..." first
  await new Promise(r => setTimeout(r, 0));
  const t = detectTempo(a.samples, a.sampleRate, opts);
  return { ...t, duration: a.duration, buffer: a.buffer, sampleRate: a.sampleRate };
}

// ---------------------------------------------------------------- tap tempo
export class TapTempo {
  constructor({ gap = 2000, keep = 8 } = {}) { this.gap = gap; this.keep = keep; this.taps = []; }
  reset() { this.taps = []; }
  // -> the tempo (BPM, 0.1 precision) once there are 3 taps, else null. A pause longer than `gap` ms starts over.
  tap(ms = performance.now()) {
    const t = this.taps;
    if (t.length && ms - t[t.length - 1] > this.gap) t.length = 0;
    t.push(ms);
    if (t.length > this.keep) t.shift();
    if (t.length < 3) return null;
    const d = [];
    for (let i = 1; i < t.length; i++) d.push(t[i] - t[i - 1]);
    // one tap far off (a double tap, a late one) is left out
    const med = [...d].sort((a, b) => a - b)[Math.floor(d.length / 2)];
    const ok = d.filter(x => Math.abs(x - med) < med * 0.25);
    const avg = ok.reduce((a, b) => a + b, 0) / ok.length;
    return Math.round(600000 / avg) / 10;
  }
}

// The loop for a dance: a whole number of beats (default 16 = four bars), as whole frames. The tempo is nudged a
// hair so the beats land on frames (no drift from loop to loop). -> {beats, frames, bpm, framesPerBeat}
export function phrase(bpm, { fps = 30, beats = 16 } = {}) {
  bpm = Math.max(40, Math.min(240, +bpm || 120));
  const frames = Math.max(12, Math.round(beats * 60 / bpm * fps));
  const exact = beats * 60 * fps / frames;
  return { beats, frames, bpm: Math.round(exact * 100) / 100, framesPerBeat: frames / beats };
}

// Beats to play a loop of `frames`: the frame numbers of each beat (for the timeline marks).
export function beatFrames(frames, beats) {
  const out = [];
  for (let b = 0; b < beats; b++) out.push(Math.round(b * frames / beats));
  return out;
}

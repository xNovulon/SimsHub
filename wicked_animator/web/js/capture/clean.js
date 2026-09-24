// Cleaning a capture take before it is solved (capture.md 5.8): confidence, left/right swap repair, bone-length check,
// gap filling, resampling to the project's 30 fps grid (by real time - phone videos have a variable frame rate), and
// the one-euro filter (zero-lag for videos and recorded takes: the filter is run forwards and backwards and the two
// are averaged, so their lags cancel).
//
// Take = { source, width, height, fov, t: Float64Array(n) seconds,
//          people: [{ pose: Float32Array(n*33*4)  world x,y,z,visibility (MediaPipe axes: x right, y down, z away),
//                     img:  Float32Array(n*33*3)  normalised image x,y,z,
//                     hand: { L: Float32Array(n*21*3) | null, R, Lok: Uint8Array(n), Rok: Uint8Array(n) },
//                     face: { bs: Float32Array(n*52), m: Float32Array(n*16), ok: Uint8Array(n), eyeL, eyeR: Float32Array(n) } }],
//          tongue?: Float32Array(n) }
// A cleaned take also carries per person `miss` (limb -> Uint8Array(n): 1 = that limb was not seen for longer than
// a short gap, the solver eases it to the sim's own pose there) and `quality` (0..1 per frame).

export const FPS = 30;
export const MAX_GAP = 15;                        // frames filled in by a straight line; longer gaps are marked

// ---------------------------------------------------------------- one-euro filter (Casiez et al. 2012)
const alpha = (fc, te) => 1 / (1 + 1 / (2 * Math.PI * fc * te));
export class OneEuro {
  constructor(minCutoff = 1, beta = 0, dCutoff = 1) { this.minCutoff = minCutoff; this.beta = beta; this.dCutoff = dCutoff; this.reset(); }
  reset() { this.x = null; this.dx = 0; this.t = null; }
  filter(x, t) {
    if (this.x === null || !Number.isFinite(this.x)) { this.x = x; this.dx = 0; this.t = t; return x; }
    const te = Math.max(1e-4, t - this.t);
    this.t = t;
    const dx = (x - this.x) / te;
    this.dx = this.dx + alpha(this.dCutoff, te) * (dx - this.dx);
    const fc = this.minCutoff + this.beta * Math.abs(this.dx);
    this.x = this.x + alpha(fc, te) * (x - this.x);
    return this.x;
  }
}

// One pass over a series (returns a new Float64Array).
export function oneEuroSeries(xs, ts, { minCutoff = 1, beta = 0, dCutoff = 1 } = {}) {
  const f = new OneEuro(minCutoff, beta, dCutoff), out = new Float64Array(xs.length);
  for (let i = 0; i < xs.length; i++) out[i] = f.filter(xs[i], ts[i]);
  return out;
}

// Zero-lag: forwards, and backwards over the reversed series, averaged.
export function zeroLag(xs, ts, params) {
  const n = xs.length;
  const fwd = oneEuroSeries(xs, ts, params);
  const rx = new Float64Array(n), rt = new Float64Array(n);
  for (let i = 0; i < n; i++) { rx[i] = xs[n - 1 - i]; rt[i] = ts[n - 1] - ts[n - 1 - i] + ts[0]; }
  const back = oneEuroSeries(rx, rt, params);
  const out = new Float64Array(n);
  for (let i = 0; i < n; i++) out[i] = 0.5 * (fwd[i] + back[n - 1 - i]);
  return out;
}

// The "Smooth <-> Detailed" slider (0..1, middle = the starting values): minCutoff x0.5..x2.5, beta x0.3..x3.
export function smoothScale(s = 0.5) {
  s = Math.max(0, Math.min(1, s));
  const lerp = (a, b, t) => a + (b - a) * t;
  return s < 0.5 ? { cut: lerp(0.5, 1, s * 2), beta: lerp(0.3, 1, s * 2) } : { cut: lerp(1, 2.5, (s - 0.5) * 2), beta: lerp(1, 3, (s - 0.5) * 2) };
}
// Starting values, tuned on noisy test motions (a 10 cm sway at 0.5-3 Hz with 6 mm of jitter): the zero-lag pass
// lowers the jitter while keeping fast moves (thrusts, bounces) at full size. capture.md's first guesses (body 1.2 Hz,
// beta 1) flattened a 2 Hz move by a third.
export const FILTERS = {
  body: { minCutoff: 3.0, beta: 16, dCutoff: 2 },
  fingers: { minCutoff: 2.5, beta: 12, dCutoff: 2 },
  blend: { minCutoff: 2.5, beta: 3.0, dCutoff: 1 },
  head: { minCutoff: 3.0, beta: 6, dCutoff: 2 },
  depth: { minCutoff: 0.8, beta: 4, dCutoff: 1 },
  // after solving: the turns themselves (short recipe lines - the hip line, the face - make small jitter bigger)
  rot: { minCutoff: 4.0, beta: 20, dCutoff: 2 },
};
export const scaled = (p, k) => ({ minCutoff: p.minCutoff * k.cut, beta: p.beta * k.beta, dCutoff: p.dCutoff });

// ---------------------------------------------------------------- take helpers
export function emptyPerson(n) {
  return {
    pose: new Float32Array(n * 33 * 4), img: new Float32Array(n * 33 * 3),
    hand: { L: new Float32Array(n * 21 * 3), R: new Float32Array(n * 21 * 3), Lok: new Uint8Array(n), Rok: new Uint8Array(n) },
    face: { bs: new Float32Array(n * 52), m: new Float32Array(n * 16), ok: new Uint8Array(n), eyeL: new Float32Array(n), eyeR: new Float32Array(n) },
  };
}

// Limbs (pose point indices, odd = left) for the swap repair, the gap marks and the solver.
export const LIMBS = {
  armL: [11, 13, 15, 17, 19, 21], armR: [12, 14, 16, 18, 20, 22],
  legL: [23, 25, 27, 29, 31], legR: [24, 26, 28, 30, 32],
  head: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
};
const PAIRS = { arm: ['armL', 'armR'], leg: ['legL', 'legR'] };
// segments checked for length (point pairs)
const SEGMENTS = [[11, 13], [13, 15], [12, 14], [14, 16], [23, 25], [25, 27], [24, 26], [26, 28], [11, 12], [23, 24]];
const SEG_LIMB = { 11: 'armL', 13: 'armL', 12: 'armR', 14: 'armR', 23: 'legL', 25: 'legL', 24: 'legR', 26: 'legR' };

const P = (pose, i, j) => [pose[(i * 33 + j) * 4], pose[(i * 33 + j) * 4 + 1], pose[(i * 33 + j) * 4 + 2]];
const vis = (pose, i, j) => pose[(i * 33 + j) * 4 + 3];
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

function swapPoints(person, i, js) {
  const po = person.pose, im = person.img;
  for (const j of js) {
    const k = j + (j % 2 ? 1 : -1);              // odd (left) <-> even (right) partner
    if (k < j) continue;
    for (let c = 0; c < 4; c++) { const a = (i * 33 + j) * 4 + c, b = (i * 33 + k) * 4 + c; const t = po[a]; po[a] = po[b]; po[b] = t; }
    for (let c = 0; c < 3; c++) { const a = (i * 33 + j) * 3 + c, b = (i * 33 + k) * 3 + c; const t = im[a]; im[a] = im[b]; im[b] = t; }
  }
}
function swapHands(person, i) {
  const h = person.hand;
  if (!h || !h.L || !h.R) return;
  for (let c = 0; c < 63; c++) { const a = i * 63 + c; const t = h.L[a]; h.L[a] = h.R[a]; h.R[a] = t; }
  const t = h.Lok[i]; h.Lok[i] = h.Rok[i]; h.Rok[i] = t;
}

// 2. Left/right swap repair (often when the person turns side-on): per frame, per arm or leg pair, the labels are
// crossed when that matches the frame before much better (cost_swap < 0.6 x cost_keep). Returns the frames fixed.
export function repairSwaps(take, person = 0) {
  const pe = take.people[person], po = pe.pose, n = take.t.length;
  let fixed = 0;
  const fixedFrames = new Set();
  for (let i = 1; i < n; i++) {
    for (const [kind, [aL, aR]] of Object.entries(PAIRS)) {
      const L = LIMBS[aL], R = LIMBS[aR];
      let keep = 0, swap = 0, used = 0;
      for (let k = 0; k < L.length; k++) {
        const l = L[k], r = R[k];
        if (vis(po, i, l) < 0.5 || vis(po, i, r) < 0.5 || vis(po, i - 1, l) < 0.5 || vis(po, i - 1, r) < 0.5) continue;
        const pl = P(po, i, l), pr = P(po, i, r), ql = P(po, i - 1, l), qr = P(po, i - 1, r);
        keep += dist(pl, ql) + dist(pr, qr);
        swap += dist(pl, qr) + dist(pr, ql);
        used++;
      }
      if (used >= 2 && swap < 0.6 * keep) {
        swapPoints(pe, i, L);
        if (kind === 'arm') swapHands(pe, i);
        fixed++;
        fixedFrames.add(i);
      }
    }
  }
  return { fixed, frames: fixedFrames };
}

// 3. Bone-length check: a segment more than 30% off its median length in a frame makes that limb unsure (0.3).
export function checkLengths(take, person = 0) {
  const pe = take.people[person], po = pe.pose, n = take.t.length;
  let flagged = 0;
  for (const [a, b] of SEGMENTS) {
    const ls = [];
    for (let i = 0; i < n; i++) if (vis(po, i, a) >= 0.5 && vis(po, i, b) >= 0.5) ls.push(dist(P(po, i, a), P(po, i, b)));
    if (ls.length < 5) continue;
    ls.sort((x, y) => x - y);
    const med = ls[ls.length >> 1];
    const limb = SEG_LIMB[a];
    for (let i = 0; i < n; i++) {
      if (vis(po, i, a) < 0.5 || vis(po, i, b) < 0.5) continue;
      if (Math.abs(dist(P(po, i, a), P(po, i, b)) - med) > 0.3 * med) {
        flagged++;
        for (const j of (limb ? LIMBS[limb] : [a, b])) { const k = (i * 33 + j) * 4 + 3; po[k] = Math.min(po[k], 0.3); }
      }
    }
  }
  return flagged;
}

// 5. Resample onto a 30 fps grid by linear interpolation on each sample's real time.
export function resample(take, fps = FPS) {
  const t = take.t, n = t.length;
  if (!n) return { ...take, people: [], t: new Float64Array(0) };
  const t0 = t[0], m = Math.max(1, Math.floor((t[n - 1] - t0) * fps + 1e-6) + 1);
  const T = new Float64Array(m);
  for (let k = 0; k < m; k++) T[k] = t0 + k / fps;
  // for every output frame: input index a and weight w (value = a*(1-w) + (a+1)*w)
  const ia = new Int32Array(m), wa = new Float64Array(m);
  let a = 0;
  for (let k = 0; k < m; k++) {
    while (a < n - 2 && t[a + 1] <= T[k]) a++;
    const span = n > 1 ? t[Math.min(n - 1, a + 1)] - t[a] : 0;
    ia[k] = a; wa[k] = span > 0 ? Math.max(0, Math.min(1, (T[k] - t[a]) / span)) : 0;
  }
  const lerpArr = (src, width) => {
    if (!src) return null;
    const out = new Float32Array(m * width);
    for (let k = 0; k < m; k++) {
      const i0 = ia[k], i1 = Math.min(n - 1, i0 + 1), w = wa[k];
      for (let c = 0; c < width; c++) out[k * width + c] = src[i0 * width + c] * (1 - w) + src[i1 * width + c] * w;
    }
    return out;
  };
  // flags: the nearer sample decides, and a frame is only "seen" when both neighbours saw it
  const flagArr = src => {
    if (!src) return null;
    const out = new Uint8Array(m);
    for (let k = 0; k < m; k++) { const i0 = ia[k], i1 = Math.min(n - 1, i0 + 1); out[k] = src[i0] && src[i1] ? 1 : 0; }
    return out;
  };
  const people = take.people.map(pe => {
    const pose = lerpArr(pe.pose, 33 * 4);
    // visibility: the lower of the two neighbours, so a point is never "seen" in between two misses
    for (let k = 0; k < m; k++) {
      const i0 = ia[k], i1 = Math.min(n - 1, i0 + 1);
      for (let j = 0; j < 33; j++) pose[(k * 33 + j) * 4 + 3] = Math.min(pe.pose[(i0 * 33 + j) * 4 + 3], pe.pose[(i1 * 33 + j) * 4 + 3]);
    }
    return {
      pose, img: lerpArr(pe.img, 33 * 3),
      hand: pe.hand ? { L: lerpArr(pe.hand.L, 63), R: lerpArr(pe.hand.R, 63), Lok: flagArr(pe.hand.Lok), Rok: flagArr(pe.hand.Rok) } : null,
      face: pe.face ? { bs: lerpArr(pe.face.bs, 52), m: lerpArr(pe.face.m, 16), ok: flagArr(pe.face.ok), eyeL: lerpArr(pe.face.eyeL, 1), eyeR: lerpArr(pe.face.eyeR, 1) } : null,
    };
  });
  return { ...take, t: T, people, tongue: take.tongue ? lerpArr(take.tongue, 1) : undefined, fps };
}

// 4. Gaps: a point missing for up to MAX_GAP frames is filled in by a straight line; longer gaps keep the nearest
// seen value (so filters stay calm) and mark the limb as missing there.
export function fillGaps(take, person = 0, maxGap = MAX_GAP) {
  const pe = take.people[person], po = pe.pose, n = take.t.length;
  const missing = new Uint8Array(n * 33);
  let filled = 0;
  for (let j = 0; j < 33; j++) {
    let i = 0;
    while (i < n) {
      if (vis(po, i, j) >= 0.5) { i++; continue; }
      let e = i;
      while (e < n && vis(po, e, j) < 0.5) e++;
      const before = i - 1, after = e < n ? e : -1, len = e - i;
      for (let k = i; k < e; k++) {
        let src;
        if (before >= 0 && after >= 0 && len <= maxGap) {
          const w = (k - before) / (after - before);
          const A = P(po, before, j), B = P(po, after, j);
          src = [A[0] + (B[0] - A[0]) * w, A[1] + (B[1] - A[1]) * w, A[2] + (B[2] - A[2]) * w];
          for (let c = 0; c < 3; c++) {
            const ia0 = (before * 33 + j) * 3 + c, ib0 = (after * 33 + j) * 3 + c;
            pe.img[(k * 33 + j) * 3 + c] = pe.img[ia0] + (pe.img[ib0] - pe.img[ia0]) * w;
          }
          po[(k * 33 + j) * 4 + 3] = 0.5;         // filled in: counts as seen, a little unsure
          filled++;
        } else {
          const near = before >= 0 && (after < 0 || k - before <= after - k) ? before : after;
          if (near < 0) continue;
          src = P(po, near, j);
          for (let c = 0; c < 3; c++) pe.img[(k * 33 + j) * 3 + c] = pe.img[(near * 33 + j) * 3 + c];
          missing[k * 33 + j] = 1;
        }
        po[(k * 33 + j) * 4] = src[0]; po[(k * 33 + j) * 4 + 1] = src[1]; po[(k * 33 + j) * 4 + 2] = src[2];
      }
      i = e;
    }
  }
  // a limb counts as missing where its main points are missing
  pe.miss = {};
  for (const [limb, pts] of Object.entries(LIMBS)) {
    const main = limb === 'head' ? [0, 7, 8] : pts.slice(0, 3);
    const flags = new Uint8Array(n);
    for (let i = 0; i < n; i++) flags[i] = main.some(j => missing[i * 33 + j]) ? 1 : 0;
    pe.miss[limb] = flags;
  }
  // hands: short gaps filled per point from the neighbours; longer ones stay "not seen"
  if (pe.hand) for (const s of ['L', 'R']) {
    const ok = pe.hand[s + 'ok'], arr = pe.hand[s];
    if (!ok || !arr) continue;
    let i = 0;
    while (i < n) {
      if (ok[i]) { i++; continue; }
      let e = i;
      while (e < n && !ok[e]) e++;
      if (i > 0 && e < n && e - i <= maxGap) {
        for (let k = i; k < e; k++) {
          const w = (k - (i - 1)) / (e - (i - 1));
          for (let c = 0; c < 63; c++) arr[k * 63 + c] = arr[(i - 1) * 63 + c] + (arr[e * 63 + c] - arr[(i - 1) * 63 + c]) * w;
          ok[k] = 1;
        }
      }
      i = e;
    }
  }
  return filled;
}

// 6. Filter every channel (zero-lag unless live).
function filterChannels(arr, width, cols, T, params, live, okFlags = null) {
  if (!arr) return;
  const n = T.length, xs = new Float64Array(n);
  for (const c of cols) {
    for (let i = 0; i < n; i++) xs[i] = arr[i * width + c];
    const ys = live ? oneEuroSeries(xs, T, params) : zeroLag(xs, T, params);
    for (let i = 0; i < n; i++) if (!okFlags || okFlags[i]) arr[i * width + c] = ys[i];
  }
}
const range = n => Array.from({ length: n }, (_, i) => i);

// The whole cleaning: returns a new take on the 30 fps grid (the input is not changed).
export function cleanTake(take, { smooth = 0.5, live = false, fps = FPS } = {}) {
  const copy = {
    ...take, t: Float64Array.from(take.t),
    people: take.people.map(pe => ({
      pose: Float32Array.from(pe.pose), img: Float32Array.from(pe.img),
      hand: pe.hand ? { L: pe.hand.L && Float32Array.from(pe.hand.L), R: pe.hand.R && Float32Array.from(pe.hand.R), Lok: pe.hand.Lok && Uint8Array.from(pe.hand.Lok), Rok: pe.hand.Rok && Uint8Array.from(pe.hand.Rok) } : null,
      face: pe.face ? { bs: Float32Array.from(pe.face.bs), m: Float32Array.from(pe.face.m), ok: Uint8Array.from(pe.face.ok), eyeL: Float32Array.from(pe.face.eyeL), eyeR: Float32Array.from(pe.face.eyeR) } : null,
    })),
  };
  const report = { swaps: 0, lengths: 0, filled: 0 };
  copy.people.forEach((pe, p) => { report.swaps += repairSwaps(copy, p).fixed; report.lengths += checkLengths(copy, p); });
  const out = resample(copy, fps);
  const k = smoothScale(smooth);
  out.people.forEach((pe, p) => {
    report.filled += fillGaps(out, p);
    const T = out.t;
    const bodyCols = [];
    for (let j = 0; j < 33; j++) bodyCols.push(j * 4, j * 4 + 1, j * 4 + 2);
    filterChannels(pe.pose, 33 * 4, bodyCols, T, scaled(FILTERS.body, k), live);
    filterChannels(pe.img, 33 * 3, range(99), T, scaled(FILTERS.body, k), live);
    if (pe.hand) for (const s of ['L', 'R']) filterChannels(pe.hand[s], 63, range(63), T, scaled(FILTERS.fingers, k), live);
    if (pe.face) {
      filterChannels(pe.face.bs, 52, range(52), T, scaled(FILTERS.blend, k), live);
      filterChannels(pe.face.m, 16, range(16), T, scaled(FILTERS.head, k), live);
    }
    // quality per frame: how sure the tracker was about the 12 limb and torso points (filled-in gaps count less)
    const q = new Float32Array(T.length);
    const main = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];
    for (let i = 0; i < T.length; i++) {
      let s = 0;
      for (const j of main) s += Math.min(1, pe.pose[(i * 33 + j) * 4 + 3]);
      let v = s / main.length;
      for (const f of Object.values(pe.miss)) if (f[i]) v = Math.min(v, 0.2);
      q[i] = v;
    }
    pe.quality = q;
  });
  out.report = report;
  return out;
}

// Quaternion sign continuity (after solving): each q agrees in sign with the one before, and is normalised.
export function unflip(quats) {
  for (let i = 0; i < quats.length; i++) {
    const q = quats[i];
    if (!q) continue;
    const l = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
    for (let c = 0; c < 4; c++) q[c] /= l;
    const p = i > 0 ? quats[i - 1] : null;
    if (p && p[0] * q[0] + p[1] * q[1] + p[2] * q[2] + p[3] * q[3] < 0) for (let c = 0; c < 4; c++) q[c] = -q[c];
  }
  return quats;
}

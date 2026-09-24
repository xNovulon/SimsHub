// Turning a solved take into the sim's keys (capture.md section 7): find the best loop, close its seam, keep only
// the keys that are needed (the app's own splitter, with capture's tolerances), and put them on a sim with one undo
// step. Body keys hold every posable bone; the penis bones come from the sim's own keys, the hand-posed face
// (faceBones) is never overwritten, and a face-only take writes face-only keys.
import * as THREE from 'three';
import * as A from '../animation.js';
import { POSABLE, HIPS, PENIS } from '../bones.js';
import { FINGER_BONES } from './retarget.js';

const deg = THREE.MathUtils.degToRad;
const _a = new THREE.Quaternion(), _b = new THREE.Quaternion(), _c = new THREE.Quaternion();
const angle = (qa, qb) => { const d = Math.min(1, Math.abs(qa[0] * qb[0] + qa[1] * qb[1] + qa[2] * qb[2] + qa[3] * qb[3])); return 2 * Math.acos(d); };

// Loop weights: hips and spine count most, fingers least.
function weight(bone) {
  if (/Pelvis|Spine/.test(bone)) return 3;
  if (/Thigh|UpperArm/.test(bone)) return 2;
  if (FINGER_BONES.has(bone)) return 0.3;
  return 1;
}

// findLoop(poses, {minFrames, maxFrames, from, to}) -> { a, b, cost }: the frame pair that joins best (poses,
// speeds and the hips' place alike). Of the loops nearly as good as the best one, the shortest wins, so a repeated
// move loops once.
export function findLoop(poses, { minFrames = 30, maxFrames = Infinity, from = 0, to = poses.length - 1 } = {}) {
  const N = poses.length;
  to = Math.min(N - 1, to);
  const bones = Object.keys(poses[from].rot || {});
  const B = bones.length, w = bones.map(weight);
  const Q = new Float64Array(N * B * 4), V = new Float64Array(N * B * 3), H = new Float64Array(N * 3);
  for (let i = 0; i < N; i++) {
    bones.forEach((b, k) => { const q = poses[i].rot[b]; for (let c = 0; c < 4; c++) Q[(i * B + k) * 4 + c] = q[c]; });
    const hp = (poses[i].pos || {})[HIPS[1]] || [0, 0, 0];
    H[i * 3] = hp[0]; H[i * 3 + 1] = hp[1]; H[i * 3 + 2] = hp[2];
  }
  // angular velocity per bone (rotation vector from frame i to i+1)
  for (let i = 0; i < N; i++) {
    const j = Math.min(N - 1, i + 1), i0 = j === i ? i - 1 : i;
    for (let k = 0; k < B; k++) {
      _a.fromArray(Q, (i0 * B + k) * 4); _b.fromArray(Q, ((i0 + 1) * B + k) * 4);
      _c.copy(_a).invert().multiply(_b);
      if (_c.w < 0) _c.set(-_c.x, -_c.y, -_c.z, -_c.w);
      const s = Math.sqrt(Math.max(0, 1 - _c.w * _c.w)), ang = 2 * Math.acos(Math.min(1, _c.w));
      const f = s > 1e-8 ? ang / s : 2;
      V[(i * B + k) * 3] = _c.x * f; V[(i * B + k) * 3 + 1] = _c.y * f; V[(i * B + k) * 3 + 2] = _c.z * f;
    }
  }
  const cost = (a, b) => {
    let c = 0;
    for (let k = 0; k < B; k++) {
      const ia = (a * B + k) * 4, ib = (b * B + k) * 4;
      const d = Math.min(1, Math.abs(Q[ia] * Q[ib] + Q[ia + 1] * Q[ib + 1] + Q[ia + 2] * Q[ib + 2] + Q[ia + 3] * Q[ib + 3]));
      const ang = 2 * Math.acos(d);
      const va = (a * B + k) * 3, vb = (b * B + k) * 3;
      const dv = (V[va] - V[vb]) ** 2 + (V[va + 1] - V[vb + 1]) ** 2 + (V[va + 2] - V[vb + 2]) ** 2;
      c += w[k] * (ang * ang + 0.3 * dv);
    }
    c += 4 * ((H[a * 3] - H[b * 3]) ** 2 + (H[a * 3 + 1] - H[b * 3 + 1]) ** 2 + (H[a * 3 + 2] - H[b * 3 + 2]) ** 2);
    return c;
  };
  const cands = [];
  let best = { a: from, b: to, cost: Infinity };
  for (let a = from; a <= to - minFrames; a++) {
    for (let b = a + minFrames; b <= Math.min(to, a + maxFrames); b++) {
      const c = cost(a, b);
      cands.push([a, b, c]);
      if (c < best.cost) best = { a, b, cost: c };
    }
  }
  if (!cands.length) return { a: from, b: to, cost: Infinity, seam: null };
  // near-best (within 30% + a hair) and shortest: one clean cycle
  const limit = best.cost * 1.3 + 1e-4 * bones.length;
  let pick = best;
  for (const [a, b, c] of cands) if (c <= limit && (b - a < pick.b - pick.a || (b - a === pick.b - pick.a && c < pick.cost))) pick = { a, b, cost: c };
  return pick;
}

// closeLoop(poses, faces, a, b) -> { poses, faces }: frames a..b-1, with the leftover mismatch at the seam spread
// over the whole loop (so nothing jumps where it wraps).
export function closeLoop(poses, faces, a, b) {
  const L = b - a;
  const ss = t => t * t * (3 - 2 * t);
  const out = [], outF = [];
  const bones = Object.keys(poses[a].rot || {});
  const delta = {};
  for (const bn of bones) {
    const qa = new THREE.Quaternion().fromArray(poses[a].rot[bn]), qb = new THREE.Quaternion().fromArray(poses[b].rot[bn]);
    const d = qa.clone().multiply(qb.clone().invert());
    if (d.w < 0) d.set(-d.x, -d.y, -d.z, -d.w);
    delta[bn] = d;
  }
  const posNames = Object.keys(poses[a].pos || {});
  for (let i = a; i < b; i++) {
    const t = ss((i - a) / L);
    const rot = {}, pos = {};
    for (const bn of bones) rot[bn] = new THREE.Quaternion().slerp(delta[bn], t).multiply(new THREE.Quaternion().fromArray(poses[i].rot[bn])).normalize().toArray();
    for (const pn of posNames) {
      const pa = poses[a].pos[pn], pb = poses[b].pos[pn], pi = poses[i].pos[pn];
      pos[pn] = [0, 1, 2].map(c => pi[c] + (pa[c] - pb[c]) * t);
    }
    out.push({ rot, pos });
    if (faces) {
      const fa = faces[a], fb = faces[b], fi = faces[i];
      if (fi) { const f = {}; for (const k of Object.keys(fi)) f[k] = Math.round((fi[k] + (((fa || {})[k] || 0) - ((fb || {})[k] || 0)) * t) * 1000) / 1000; outF.push(f); }
      else outF.push(null);
    }
  }
  return { poses: out, faces: faces ? outF : null };
}

// How far the loop's wrap-around strays from its own motion (degrees): the first frame against the frame the last
// two predict (constant speed), for the worst bone.
export function seamError(poses) {
  const N = poses.length;
  if (N < 3) return 0;
  let worst = 0;
  for (const bn of Object.keys(poses[0].rot)) {
    const q1 = new THREE.Quaternion().fromArray(poses[N - 2].rot[bn]), q2 = new THREE.Quaternion().fromArray(poses[N - 1].rot[bn]);
    const pred = q2.clone().multiply(q1.clone().invert().multiply(q2));
    const q0 = new THREE.Quaternion().fromArray(poses[0].rot[bn]);
    // the same prediction one step inside the loop, so a fast bone's own acceleration is not counted as a seam
    const inside = (() => {
      const a = new THREE.Quaternion().fromArray(poses[N - 3] ? poses[N - 3].rot[bn] : poses[N - 2].rot[bn]);
      return q1.clone().multiply(a.clone().invert().multiply(q1)).angleTo(q2);
    })();
    worst = Math.max(worst, Math.max(0, pred.angleTo(q0) - inside));
  }
  return THREE.MathUtils.radToDeg(worst);
}

// Stretch a take to a new frame count (slerp between frames).
export function retime(poses, faces, newLen, loop = true) {
  const N = poses.length;
  const out = [], outF = [];
  for (let k = 0; k < newLen; k++) {
    const x = loop ? (k * N) / newLen : (newLen > 1 ? (k * (N - 1)) / (newLen - 1) : 0);
    const i0 = Math.floor(x) % N, i1 = loop ? (i0 + 1) % N : Math.min(N - 1, i0 + 1), t = x - Math.floor(x);
    const rot = {}, pos = {};
    for (const bn of Object.keys(poses[i0].rot)) rot[bn] = new THREE.Quaternion().fromArray(poses[i0].rot[bn]).slerp(new THREE.Quaternion().fromArray(poses[i1].rot[bn]), t).toArray();
    for (const pn of Object.keys(poses[i0].pos || {})) pos[pn] = [0, 1, 2].map(c => poses[i0].pos[pn][c] + (poses[i1].pos[pn][c] - poses[i0].pos[pn][c]) * t);
    out.push({ rot, pos });
    if (faces) {
      const a = faces[i0], b = faces[i1];
      if (a || b) { const f = {}; for (const kk of new Set([...Object.keys(a || {}), ...Object.keys(b || {})])) f[kk] = ((a || {})[kk] || 0) + (((b || {})[kk] || 0) - ((a || {})[kk] || 0)) * t; outF.push(f); }
      else outF.push(null);
    }
  }
  return { poses: out, faces: faces ? outF : null };
}

// ---------------------------------------------------------------- key reduction (7.3)
// Tolerances from the "Smooth <-> Detailed" slider (0 = fewest keys, 1 = most detail).
export function tolerances(detail = 0.5) {
  const body = detail <= 0.5 ? 1.5 + (0.8 - 1.5) * (detail / 0.5) : 0.8 + (0.4 - 0.8) * ((detail - 0.5) / 0.5);
  return { body: deg(body), fingers: deg(2.5), pos: 0.002, face: 0.04 };
}

// A local copy of the app's splitter, for an app that does not have animation.keyFramesFor yet.
function localKeyFramesFor(poses, faces, loop, { angle: tolA = deg(0.25), pos: tolP = 0.001, face: tolF = 0.02 } = {}) {
  const n = poses.length;
  if (n <= 2) return poses.map((p, i) => i);
  const at = i => (i === n ? 0 : i);
  const err = (a, b, i) => {
    const t = (i - a) / (b - a), P0 = poses[at(a)], P1 = poses[at(b)], P = poses[i];
    let e = 0;
    for (const bone of Object.keys(P.rot || {})) {
      const qa = P0.rot[bone], qb = P1.rot[bone];
      if (!qa || !qb) continue;
      _a.fromArray(qa).normalize(); _b.fromArray(qb).normalize(); _c.fromArray(P.rot[bone]).normalize();
      _a.slerp(_b, t);
      e = Math.max(e, _a.angleTo(_c) / tolA);
    }
    for (const bone of Object.keys(P.pos || {})) {
      const va = (P0.pos || {})[bone], vb = (P1.pos || {})[bone], v = P.pos[bone];
      if (!va || !vb) continue;
      e = Math.max(e, Math.hypot(va[0] + (vb[0] - va[0]) * t - v[0], va[1] + (vb[1] - va[1]) * t - v[1], va[2] + (vb[2] - va[2]) * t - v[2]) / tolP);
    }
    if (faces) {
      const Fa = faces[at(a)] || {}, Fb = faces[at(b)] || {}, F = faces[i] || {};
      for (const k of new Set([...Object.keys(Fa), ...Object.keys(Fb), ...Object.keys(F)])) {
        const x = (Fa[k] || 0) + ((Fb[k] || 0) - (Fa[k] || 0)) * t;
        e = Math.max(e, Math.abs(x - (F[k] || 0)) / tolF);
      }
    }
    return e;
  };
  const keys = new Set([0]);
  const stack = [[0, loop ? n : n - 1]];
  if (!loop) keys.add(n - 1);
  while (stack.length) {
    const [a, b] = stack.pop();
    if (b - a < 2) continue;
    let worst = -1, we = 1;
    for (let i = a + 1; i < b; i++) { const e = err(a, b, i); if (e > we) { we = e; worst = i; } }
    if (worst < 0) continue;
    keys.add(worst);
    stack.push([a, worst], [worst, b]);
  }
  return [...keys].sort((x, y) => x - y);
}
const keyFramesFor = (...args) => (typeof A.keyFramesFor === 'function' ? A.keyFramesFor(...args) : localKeyFramesFor(...args));

const split = (poses, pick) => poses.map(p => {
  const rot = {};
  for (const [b, q] of Object.entries(p.rot)) if (pick(b)) rot[b] = q;
  return { rot, pos: pick('__pos') ? p.pos : {} };
});

// Frames where a key is needed (linear in-betweens): the body at the body tolerance (with hips and face), the
// fingers at their own looser one.
export function linearKeyFrames(poses, faces, loop, tol) {
  const body = keyFramesFor(split(poses, b => !FINGER_BONES.has(b)), faces, loop, { angle: tol.body, pos: tol.pos, face: tol.face });
  const fing = keyFramesFor(split(poses, b => FINGER_BONES.has(b)), null, loop, { angle: tol.fingers, pos: 1, face: 1 });
  return [...new Set([...body, ...fing])].sort((a, b) => a - b);
}

// How far the keys (with their eases, as the app plays them) stray from the take at every frame: [{frame, e}]
// where e > 1 means past the tolerance.
function misfit(keys, poses, faces, loop, tol) {
  const N = poses.length, out = new Float64Array(N);
  for (let f = 0; f < N; f++) {
    const p = A.evaluate(keys, f, N, loop);
    let e = 0;
    if (p) {
      for (const [b, q] of Object.entries(poses[f].rot)) {
        const r = p.rot[b];
        if (r) e = Math.max(e, angle(q, r) / (FINGER_BONES.has(b) ? tol.fingers : tol.body));
      }
      for (const [b, v] of Object.entries(poses[f].pos || {})) {
        const r = (p.pos || {})[b];
        if (r) e = Math.max(e, Math.hypot(v[0] - r[0], v[1] - r[1], v[2] - r[2]) / tol.pos);
      }
    }
    if (faces && faces[f]) {
      const fv = A.evaluateFace(keys, f, N, loop) || {};
      for (const [k, v] of Object.entries(faces[f])) e = Math.max(e, Math.abs(v - (fv[k] || 0)) / tol.face);
    }
    out[f] = e;
  }
  return out;
}

// reduceKeys(poses, faces, loop, detail) -> keys [{frame, ease, pose, face?}]: the fewer of (a) straight keys from
// the splitter and (b) smooth 'auto' keys (the app's default curve): evenly spread at first, then a key added wherever
// the real curve strays past the tolerance, until every frame fits.
export function reduceKeys(poses, faces, loop, detail = 0.5) {
  const tol = tolerances(detail);
  const N = poses.length;
  const make = (frames, ease) => frames.map(f => ({ frame: f, ease, pose: poses[f], ...(faces && faces[f] ? { face: { ...faces[f] } } : {}) }));
  const lin = make(linearKeyFrames(poses, faces, loop, tol), 'linear');
  if (N < 6) return lin;
  const even = k => { const out = new Set(); for (let i = 0; i < k; i++) out.add(Math.min(N - 1, Math.round(i * (loop ? N : N - 1) / (loop ? k : k - 1)))); if (!loop) out.add(N - 1); return out; };
  const refine = (frames, budget) => {
    for (let it = 0; it < 40; it++) {
      const sorted = [...frames].sort((a, b) => a - b);
      const keys = make(sorted, 'auto');
      const m = misfit(keys, poses, faces, loop, tol);
      let added = 0;
      for (let k = 0; k < sorted.length; k++) {
        const a = sorted[k], b = k + 1 < sorted.length ? sorted[k + 1] : (loop ? N : N - 1);
        let worst = -1, we = 1;
        for (let f = a + 1; f < b && f < N; f++) if (m[f] > we) { we = m[f]; worst = f; }
        if (worst >= 0) { frames.add(worst); added++; }
      }
      if (!added) return keys;
      if (frames.size >= budget) return null;
    }
    return null;
  };
  // try a few even spreads (fewest first) and keep the smallest set that fits after refining
  let best = lin;
  const k0 = Math.max(3, Math.round(lin.length / 3));
  for (const k of [k0, Math.round(k0 * 1.4), Math.round(k0 * 2)]) {
    if (k >= best.length) break;
    const r = refine(even(k), best.length);
    if (r && r.length < best.length) best = r;
  }
  return best;
}

// A key every `every` frames (and on the last frame), like the Library's "Import as keys" - for motion files.
export function everyKeys(poses, faces, every) {
  const N = poses.length, frames = [];
  for (let f = 0; f < N; f += Math.max(1, Math.round(every))) frames.push(f);
  if (frames[frames.length - 1] !== N - 1) frames.push(N - 1);
  return frames.map(f => ({ frame: f, ease: 'auto', pose: poses[f], ...(faces && faces[f] ? { face: { ...faces[f] } } : {}) }));
}

// ---------------------------------------------------------------- putting it on a sim (7.4)
// applyToSim(app, simId, {poses, faces}, {mode, at, fitLength, detail, faceOnly, source, checkpoint, every}) -> number of keys.
// every: a key every that many frames instead of only where the motion needs one (null = the reducer).
// checkpoint: false when the caller already made the one undo step (two sims at once, the live mirror's Keep).
// mode 'replace' replaces the whole animation; 'insert' replaces only [at, at + length) and blends 6 frames at the
// edges. fitLength: true = the project takes the loop's length (other sims are stretched along); a number = the
// take is stretched to that many frames; null = the take is stretched to the project's length.
export function applyToSim(app, simId, take, { mode = 'replace', at = 0, fitLength = null, detail = 0.5, faceOnly = false, headTurns = null, source = 'video', quiet = false, checkpoint = true, every = null } = {}) {
  const store = app.store, p = store.project, s = store.sim(simId);
  if (!s) throw new Error('Pick a sim first.');
  let { poses, faces } = take;
  if (!poses || !poses.length) throw new Error('Nothing to put on.');
  if (checkpoint) store.checkpoint();                   // one Ctrl+Z undoes all of it (two sims: the caller's one)
  const loop = !!p.loop;
  const lenBefore = p.length;
  if (mode === 'replace' && fitLength === true && poses.length !== p.length) {
    // the animation takes the take's length: every other sim's keys, sounds and moments stretch along (the studio
    // says so), and the playhead stays inside the new length
    const newLen = Math.max(12, Math.min(3000, poses.length));
    if (typeof app._retimeProject === 'function') app._retimeProject(p, newLen, 'stretch'); else p.length = newLen;
    store.frame = Math.max(0, Math.min(Math.round(store.frame || 0), p.length - 1));
  } else if (mode === 'replace' && poses.length !== p.length) {
    ({ poses, faces } = retime(poses, faces, typeof fitLength === 'number' ? fitLength : p.length, loop));
  }
  const L = p.length, old = s.keys.map(k => JSON.parse(JSON.stringify(k)));
  const oldBody = f => A.evaluate(old, f, L, loop);
  const start = mode === 'insert' ? Math.max(0, Math.min(L - 1, Math.round(at))) : 0;
  const span = mode === 'insert' ? Math.min(poses.length, L - start) : poses.length;

  // "Only here": the first and last 6 frames blend from the old animation into the take and back (a take of 12
  // frames or fewer, e.g. a photo's single pose, goes in as it is)
  const EDGE = 6;
  const blendAt = i => {
    if (mode !== 'insert' || !old.length || span <= 2 * EDGE) return 1;
    const x = Math.min(1, (Math.min(i, span - 1 - i) + 1) / (EDGE + 1));
    return x * x * (3 - 2 * x);
  };
  const blend = (pose, ob, w) => {
    if (w >= 1) return pose;
    const qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
    for (const [b, q] of Object.entries(pose.rot)) {
      const o = ob.rot && ob.rot[b];
      if (o) pose.rot[b] = qa.fromArray(o).normalize().slerp(qb.fromArray(q).normalize(), w).toArray();
    }
    for (const [b, v] of Object.entries(pose.pos)) {
      const o = ob.pos && ob.pos[b];
      if (o && v) pose.pos[b] = [0, 1, 2].map(c => o[c] + (v[c] - o[c]) * w);
    }
    return pose;
  };

  // the take's poses on the sim: penis bones and other extra bones from the sim's own keys, no twist bones
  const TWIST = /Twist__$/;
  const merged = poses.slice(0, span).map((pose, i) => {
    const f = start + i, ob = oldBody(f) || { rot: {}, pos: {} };
    if (faceOnly) {
      // the body stays as it was; only the head turns (when asked) come from the take
      const rot = { ...ob.rot }, pos = { ...ob.pos };
      if (headTurns && headTurns[i]) for (const b of ['b__Neck__', 'b__Head__']) if (pose.rot[b]) rot[b] = pose.rot[b];
      return { rot, pos };
    }
    const rot = {}, pos = {};
    for (const [b, q] of Object.entries(ob.rot || {})) if (!POSABLE.includes(b) || PENIS.includes(b)) if (!TWIST.test(b)) rot[b] = q;
    for (const [b, q] of Object.entries(pose.rot)) if (!PENIS.includes(b)) rot[b] = q;
    for (const b of PENIS) if (ob.rot && ob.rot[b]) rot[b] = ob.rot[b];
    for (const b of HIPS) pos[b] = (pose.pos && pose.pos[b]) || (ob.pos && ob.pos[b]);
    for (const b of PENIS) if (ob.pos && ob.pos[b]) pos[b] = ob.pos[b];
    for (const b of POSABLE) if (!rot[b] && ob.rot && ob.rot[b]) rot[b] = ob.rot[b];
    return blend({ rot, pos }, ob, blendAt(i));
  });
  const faceVals = faces ? faces.slice(0, span) : null;
  let newKeys;
  if (faceOnly && !(headTurns && headTurns.some(Boolean))) {
    // face only: face keys where the face needs them; the body is untouched
    const frames = keyFramesFor(merged.map(() => ({ rot: {}, pos: {} })), faceVals, loop && mode === 'replace', { angle: 1, pos: 1, face: tolerances(detail).face });
    newKeys = frames.map(i => ({ frame: start + i, ease: 'linear', face: { ...(faceVals[i] || {}) } }));
  } else {
    newKeys = (every > 1 ? everyKeys(merged, faceVals, every) : reduceKeys(merged, faceVals, loop && mode === 'replace', detail)).map(k => ({ ...k, frame: start + k.frame }));
  }

  let keys;
  if (faceOnly && !(headTurns && headTurns.some(Boolean))) {
    // keep every body key; the new face keys replace the old face values in the range
    keys = old.map(k => ({ ...k }));
    const inRange = f => f >= start && f < start + span;
    for (const k of keys) if (inRange(k.frame)) delete k.face;
    keys = keys.filter(k => !(k.faceOnly && !k.faceBones && !k.face));
    for (const nk of newKeys) {
      const ex = keys.find(k => k.frame === nk.frame);
      if (ex) ex.face = nk.face;
      else keys.push({ frame: nk.frame, ease: 'linear', faceOnly: true, pose: oldBody(nk.frame) || merged[nk.frame - start], face: nk.face });
    }
  } else {
    const inRange = f => f >= start && f < start + span;
    keys = mode === 'insert' ? old.filter(k => !inRange(k.frame)) : [];
    keys.push(...newKeys);
    // the hand-posed face is never overwritten: old faceBones (and, for a body-only take, the old face values) stay
    for (const ok of old) {
      if (mode === 'insert' && !inRange(ok.frame)) continue;
      const keepFace = !faces && ok.face;
      if (!ok.faceBones && !keepFace) continue;
      let k = keys.find(x => x.frame === ok.frame);
      if (!k) {
        const i = ok.frame - start;
        k = { frame: ok.frame, ease: ok.ease || 'auto', faceOnly: true, pose: merged[Math.max(0, Math.min(merged.length - 1, i))] };
        keys.push(k);
      }
      if (ok.faceBones) k.faceBones = ok.faceBones;
      if (keepFace) k.face = ok.face;
    }
    // insert: blend 6 frames at each edge into the old animation
    if (mode === 'insert' && old.length) {
      for (const edge of [start, start + span - 1]) {
        const k = keys.find(x => x.frame === edge && !x.faceOnly);
        if (k) k.ease = 'smooth';
      }
    }
  }
  A.sortKeys(keys);
  s.keys = keys;
  if (faces && faces.some(Boolean)) {
    // real blinks are in the take: the automatic blinking would double them
    s.body = s.body || {};
    s.body.blink = false;
  }
  // a pending (unkeyed) pose of this sim belongs to its old keys; after a new length, every sim's does (as setLength)
  try {
    const ov = app.pipeline && app.pipeline.overrides;
    if (ov) { if (p.length !== lenBefore) ov.clear(); else ov.delete(s.id); }
  } catch { /* none */ }
  app.refreshAll && app.refreshAll();
  // a new length fills the timeline again, and the frame box shows the (clamped) playhead
  if (p.length !== lenBefore) {
    try { app.timeline && typeof app.timeline.fit === 'function' && app.timeline.fit(); } catch (e) { console.error('capture: timeline fit', e); }
    try { if (typeof app.setFrame === 'function') app.setFrame(store.frame); } catch (e) { console.error('capture: frame', e); }
  }
  app.physicsChanged && app.physicsChanged();
  return newKeys.length;
}

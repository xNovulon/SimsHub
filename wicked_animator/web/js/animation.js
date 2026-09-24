// Sampling game clips, and the keyframe model the editor animates with.
import * as THREE from 'three';
import { POSABLE, HIPS, HIPS_SET, KEYABLE, EXTRA, FACE_CHANNEL, FACE_SET, mirrorName } from './bones.js';

const _qa = new THREE.Quaternion(), _qb = new THREE.Quaternion(), _qc = new THREE.Quaternion();
const _X = new THREE.Vector3(1, 0, 0);

function findKey(keys, tick) {
  // last index with keys[i][0] <= tick
  let lo = 0, hi = keys.length - 1;
  if (tick <= keys[0][0]) return 0;
  if (tick >= keys[hi][0]) return hi;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (keys[mid][0] <= tick) lo = mid; else hi = mid - 1;
  }
  return lo;
}

// A decoded game clip ({ticks, fps, tracks: {bone: {t: [[tick,x,y,z]], r: [[tick,x,y,z,w]]}}}).
export class ClipPlayer {
  constructor(clip) {
    this.clip = clip;
    this.frames = clip.ticks;
  }
  sample(frame) {
    const out = {};
    for (const [bone, tr] of Object.entries(this.clip.tracks)) {
      const s = {};
      if (tr.t) s.t = sampleVec(tr.t, frame);
      if (tr.r) s.r = sampleQuat(tr.r, frame);
      out[bone] = s;
    }
    return out;
  }
}

function sampleVec(keys, tick) {
  const i = findKey(keys, tick), a = keys[i], b = keys[Math.min(i + 1, keys.length - 1)];
  if (a === b || b[0] === a[0]) return a.slice(1);
  const t = (tick - a[0]) / (b[0] - a[0]);
  return [a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t];
}

function sampleQuat(keys, tick) {
  const i = findKey(keys, tick), a = keys[i], b = keys[Math.min(i + 1, keys.length - 1)];
  if (a === b || b[0] === a[0]) return a.slice(1);
  const t = (tick - a[0]) / (b[0] - a[0]);
  _qa.set(a[1], a[2], a[3], a[4]); _qb.set(b[1], b[2], b[3], b[4]);
  return _qa.slerp(_qb, t).toArray();
}

// ---------------------------------------------------------------- the editor's keyframes
// A sim's animation: keys = [{frame, ease, pose: {rot: {bone: q}, pos: {bone: v}}, face?: {param: 0..1},
// faceBones?: {rot, pos}, faceOnly?: true}], sorted. `ease` says how the motion flows from this key into the next one.
// Three independent channels, each evaluated only over the keys that carry it:
//   body        key.pose (POSABLE dense, extra bones sparse), over keys without `faceOnly`    -> evaluate()
//   face bones  key.faceBones (the 30 FACE_CHANNEL bones, sparse: a bone not mentioned is at rest)
//                                                                                              -> evaluateFaceBones()
//   sliders     key.face ({eyes, smile, ...})                                                 -> evaluateFace()
const PI = Math.PI;
const bounceOut = t => {
  const n = 7.5625, d = 2.75;
  if (t < 1 / d) return n * t * t;
  if (t < 2 / d) return n * (t -= 1.5 / d) * t + 0.75;
  if (t < 2.5 / d) return n * (t -= 2.25 / d) * t + 0.9375;
  return n * (t -= 2.625 / d) * t + 0.984375;
};
export const EASES = {
  auto: t => t,                                   // smooth curve through the keys around it (see evaluate)
  smooth: t => t * t * (3 - 2 * t),
  linear: t => t,
  easeIn: t => t * t * t,
  easeOut: t => 1 - Math.pow(1 - t, 3),
  impact: t => t * t * t * t,                      // speeds up and hits hard (thrusts, slaps)
  back: t => { const c = 1.70158, c3 = c + 1; return 1 + c3 * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
  bounce: t => bounceOut(t),
  elastic: t => (t === 0 || t === 1) ? t : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * PI / 3)) + 1,
  hold: () => 0,
  custom: t => t,                                 // placeholder: a custom key's own curve goes through easeFn(key)
};
export const EASE_INFO = {
  auto: ['Auto smooth', 'Flows through the keys around it, like Blender - best for most motion', '#7c8cff'],
  smooth: ['Ease in & out', 'Starts and stops gently at each key', '#57b8ff'],
  linear: ['Linear', 'Constant speed', '#9aa3b5'],
  easeIn: ['Ease in', 'Starts slow, arrives fast', '#3ddc97'],
  easeOut: ['Ease out', 'Leaves fast, arrives slow', '#2fc5b8'],
  impact: ['Impact', 'Speeds up and hits hard - thrusts, slaps, slams', '#ff4f6a'],
  back: ['Overshoot', 'Goes a little past the pose and settles back', '#ffb547'],
  bounce: ['Bounce', 'Bounces into the pose', '#ff8a5b'],
  elastic: ['Elastic', 'Wobbles into the pose', '#e879f9'],
  custom: ['Custom curve', 'Your own timing - drag the two handles', '#f4f1fa'],
  hold: ['Hold', 'Stays still, then jumps to the next key', '#6b7280'],
};

// ---------------------------------------------------------------- custom timing (spec_editing 3.1)
// A key's own timing curve: a cubic Bezier like CSS cubic-bezier(x1, y1, x2, y2), from (0,0) to (1,1). x1 and x2
// stay in 0..1 (time never runs backwards); y1 and y2 may go past the ends (overshoot, anticipation).
const _bz = new Map();
export const validCurve = c => Array.isArray(c) && c.length === 4 && c.every(Number.isFinite)
  && c[0] >= 0 && c[0] <= 1 && c[2] >= 0 && c[2] <= 1;
export function bezierEase(c) {
  const id = c.join();
  let f = _bz.get(id);
  if (f) return f;
  const [x1, y1, x2, y2] = c;
  const bx = u => 3 * (1 - u) * (1 - u) * u * x1 + 3 * (1 - u) * u * u * x2 + u * u * u;
  const by = u => 3 * (1 - u) * (1 - u) * u * y1 + 3 * (1 - u) * u * u * y2 + u * u * u;
  const dx = u => 3 * (1 - u) * (1 - u) * x1 + 6 * (1 - u) * u * (x2 - x1) + 3 * u * u * (1 - x2);
  f = t => {
    if (t <= 0) return 0;
    if (t >= 1) return 1;
    let u = t;
    for (let i = 0; i < 8; i++) { const d = dx(u); if (Math.abs(d) < 1e-6) break; u = Math.min(1, Math.max(0, u - (bx(u) - t) / d)); }
    if (Math.abs(bx(u) - t) > 1e-4) { let lo = 0, hi = 1; for (let i = 0; i < 30; i++) { u = (lo + hi) / 2; if (bx(u) < t) lo = u; else hi = u; } }
    return by(u);
  };
  if (_bz.size > 500) _bz.clear();
  _bz.set(id, f);
  return f;
}
// The timing function of the segment that starts at `key`.
export function easeFn(key) {
  if (key && key.ease === 'custom' && validCurve(key.curve)) return bezierEase(key.curve);
  return EASES[key && key.ease] || EASES.smooth;
}
// The curve a timing starts from when "Custom curve" is picked.
export const EASE_CURVE = { auto: [0.33, 0, 0.67, 1], smooth: [0.42, 0, 0.58, 1], linear: [0, 0, 1, 1],
  easeIn: [0.55, 0, 1, 0.45], easeOut: [0, 0.55, 0.45, 1], impact: [0.8, 0, 1, 0.35], back: [0.34, 1.4, 0.64, 1],
  bounce: [0.42, 0, 0.58, 1], elastic: [0.42, 0, 0.58, 1], custom: [0.42, 0, 0.58, 1], hold: [1, 0, 1, 0] };
// Playing a stretch of keys backwards: the timing of each segment turns round.
export const REVERSE_EASE = { auto: 'auto', smooth: 'smooth', linear: 'linear', easeIn: 'easeOut', easeOut: 'easeIn',
  impact: 'easeOut', back: 'smooth', bounce: 'smooth', elastic: 'smooth', hold: 'hold', custom: 'custom' };
export const reverseCurve = c => [1 - c[2], 1 - c[3], 1 - c[0], 1 - c[1]].map(v => Math.round(v * 1e9) / 1e9);   // twice gives it back exactly

export function sortKeys(keys) { keys.sort((a, b) => a.frame - b.frame); return keys; }

// The keys around `frame` (with loop wrap-around) and how far between the two it is.
function around(keys, frame, length, loop) {
  const n = keys.length;
  let i = -1;
  for (let k = 0; k < n; k++) if (keys[k].frame <= frame) i = k; else break;
  let a, b, span, t, ia, ib;
  if (i < 0) {                  // before the first key
    if (!loop) return { a: keys[0], b: keys[0], t: 0, ia: 0, ib: 0 };
    ia = n - 1; ib = 0; a = keys[ia]; b = keys[ib];
    span = (length - a.frame) + b.frame; t = span > 0 ? (frame + length - a.frame) / span : 0;
  } else if (i === n - 1) {     // after the last key
    if (!loop) return { a: keys[i], b: keys[i], t: 0, ia: i, ib: i };
    ia = i; ib = 0; a = keys[ia]; b = keys[ib];
    span = (length - a.frame) + b.frame; t = span > 0 ? (frame - a.frame) / span : 0;
  } else {
    ia = i; ib = i + 1; a = keys[ia]; b = keys[ib];
    span = b.frame - a.frame; t = span > 0 ? (frame - a.frame) / span : 0;
  }
  return { a, b, t: Math.min(1, Math.max(0, t)), ia, ib };
}

// Keys at or past the end of the animation are off the timeline (e.g. it was made shorter): they are left out,
// so the loop still wraps back to the first key instead of drifting toward a key nobody can see.
export function onTimeline(keys, length) {
  if (!(length > 0) || !keys.length || keys[keys.length - 1].frame < length) return keys;
  const inside = keys.filter(k => k.frame < length);
  return inside.length ? inside : keys.slice(0, 1);
}

// Pose of a sim at `frame` (fractional allowed). `loop` wraps the last key back to the first. Face-only keys (a face
// key added where there was no body key) never bend the body's motion.
// curve: how "Auto smooth" keys flow - 'legacy' (uniform Catmull-Rom, what every project made before has) or
// 'clamped' (frame-aware, never overshoots, two equal keys really hold still; project.autoCurve of new projects).
export function evaluate(keys, frame, length, loop, curve = 'legacy') {
  keys = onTimeline(keys.filter(k => !k.faceOnly && k.pose), length);
  if (!keys.length) return null;
  if (keys.length === 1) return keys[0].pose;
  const { a, b, t, ia, ib } = around(keys, frame, length, loop);
  if (a === b) return a.pose;
  const ease = a.ease || 'auto';
  if (ease === 'auto' && keys.length > 2) {
    const n = keys.length;
    const i0 = loop ? (ia - 1 + n) % n : Math.max(0, ia - 1), i3 = loop ? (ib + 1) % n : Math.min(n - 1, ib + 1);
    if (curve === 'clamped') return clampedPoses(keys[i0].pose, a.pose, b.pose, keys[i3].pose, t, spanFrames(keys, i0, ia, ib, i3, length));
    return catmullPoses(keys[i0].pose, a.pose, b.pose, keys[i3].pose, t);
  }
  return blendPoses(a.pose, b.pose, ease === 'auto' ? EASES.smooth(t) : easeFn(a)(t));
}

// The hand-posed face between face keys (null when the sim has none). Within a face key, a face bone it does not
// mention is at rest, exactly as for body poses; one face key holds that face all the way through. Same eases and
// the same curve as the body.
export function evaluateFaceBones(keys, frame, length, loop, curve = 'legacy') {
  const fk = [];
  for (const k of keys) if (k.faceBones) fk.push(k.ease === 'custom' ? { frame: k.frame, ease: k.ease, curve: k.curve, pose: k.faceBones } : { frame: k.frame, ease: k.ease, pose: k.faceBones });
  if (!fk.length) return null;
  return evaluate(fk, frame, length, loop, curve);
}

// Face settings between keys (plain numbers).
export function evaluateFace(keys, frame, length, loop) {
  const withFace = onTimeline(keys.filter(k => k.face), length);
  if (!withFace.length) return null;
  if (withFace.length === 1) return withFace[0].face;
  const { a, b, t } = around(withFace, frame, length, loop);
  const e = easeFn(a)(a.ease === 'auto' ? EASES.smooth(t) : t);
  const out = {};
  for (const k of new Set([...Object.keys(a.face), ...Object.keys(b.face)])) out[k] = (a.face[k] || 0) + ((b.face[k] || 0) - (a.face[k] || 0)) * e;
  return out;
}

// A bone that a key doesn't mention sits at the rig's rest in that key - that is how the key itself shows - so
// blends and curves run through rest for it instead of holding the other key's value and then snapping.
// The hips' place is the exception: a key without it keeps the sim where the other key has it.
const restRot = n => REST[n] && REST[n].r;
const restPos = n => HIPS_SET.has(n) ? null : REST[n] && REST[n].t;
const eachName = (A, B, fn) => { for (const n in A) fn(n); for (const n in B) if (!(n in A)) fn(n); };

export function blendPoses(pa, pb, t) {
  const rot = {}, pos = {};
  const ra = pa.rot || {}, rb = pb.rot || {}, sa = pa.pos || {}, sb = pb.pos || {};
  eachName(ra, rb, n => {
    const qa = ra[n] || restRot(n) || rb[n], qb = rb[n] || restRot(n) || qa;
    _qa.fromArray(qa); _qb.fromArray(qb);
    rot[n] = _qa.slerp(_qb, t).toArray();
  });
  eachName(sa, sb, n => {
    const va = sa[n] || restPos(n) || sb[n], vb = sb[n] || restPos(n) || va;
    pos[n] = [va[0] + (vb[0] - va[0]) * t, va[1] + (vb[1] - va[1]) * t, va[2] + (vb[2] - va[2]) * t];
  });
  return { rot, pos };
}

// Centripetal-ish Catmull-Rom through four poses (uniform), quaternions kept in one hemisphere and renormalised.
const cr = (p0, p1, p2, p3, t) => {
  const t2 = t * t, t3 = t2 * t;
  return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3);
};
const al = (q, ref) => (q[0] * ref[0] + q[1] * ref[1] + q[2] * ref[2] + q[3] * ref[3]) < 0 ? q.map(x => -x) : q;
export function catmullPoses(A, B, C, D, t) {
  const rot = {}, pos = {};
  const rA = A.rot || {}, rB = B.rot || {}, rC = C.rot || {}, rD = D.rot || {};
  eachName(rB, rC, n => {
    const q1 = rB[n] || restRot(n) || rC[n], q2 = rC[n] || restRot(n) || q1;
    const q0 = rA[n] || restRot(n) || q1, q3 = rD[n] || restRot(n) || q2;
    const a0 = al(q0, q1), a2 = al(q2, q1), a3 = al(q3, a2);
    const q = [0, 1, 2, 3].map(k => cr(a0[k], q1[k], a2[k], a3[k], t));
    const len = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
    rot[n] = q.map(x => x / len);
  });
  const sA = A.pos || {}, sB = B.pos || {}, sC = C.pos || {}, sD = D.pos || {};
  eachName(sB, sC, n => {
    const v1 = sB[n] || restPos(n) || sC[n], v2 = sC[n] || restPos(n) || v1;
    const v0 = sA[n] || restPos(n) || v1, v3 = sD[n] || restPos(n) || v2;
    pos[n] = [0, 1, 2].map(k => cr(v0[k], v1[k], v2[k], v3[k], t));
  });
  return { rot, pos };
}

// ---------------------------------------------------------------- "Auto smooth" that never overshoots
// The frames of the 4 keys around a segment, unwrapped so f0 < f1 < f2 < f3 even across the loop point. At a first
// or last key that does not loop, the missing neighbour is a mirror copy (so the curve is flat there).
function spanFrames(keys, i0, ia, ib, i3, length) {
  const f1 = keys[ia].frame;
  let f2 = keys[ib].frame, f0 = keys[i0].frame, f3 = keys[i3].frame;
  if (f2 <= f1) f2 += length;                       // the segment wraps
  if (i0 === ia) f0 = f1 - (f2 - f1); else { while (f0 >= f1) f0 -= length; }
  if (i3 === ib) f3 = f2 + (f2 - f1); else { while (f3 <= f2) f3 += length; }
  return [f0, f1, f2, f3];
}
// Slope (per frame) at p1: frame-aware, flat at turning points and at holds, limited so the curve never overshoots
// (within 3x the neighbouring steps - the Fritsch-Carlson condition).
function slope(p0, p1, p2, h0, h1) {
  const d0 = h0 > 0 ? (p1 - p0) / h0 : 0, d1 = h1 > 0 ? (p2 - p1) / h1 : 0;
  if (d0 * d1 <= 0) return 0;
  const m = (d0 * h1 + d1 * h0) / (h0 + h1), lim = 3 * Math.min(Math.abs(d0), Math.abs(d1));
  return Math.sign(m) * Math.min(Math.abs(m), lim);
}
function herm(p1, p2, m1, m2, h, t) {
  const t2 = t * t, t3 = t2 * t;
  return (2 * t3 - 3 * t2 + 1) * p1 + (t3 - 2 * t2 + t) * h * m1 + (-2 * t3 + 3 * t2) * p2 + (t3 - t2) * h * m2;
}
export function clampedPoses(A, B, C, D, t, [f0, f1, f2, f3]) {
  const h0 = f1 - f0, h = f2 - f1, h2 = f3 - f2;
  const rot = {}, pos = {};
  const rA = A.rot || {}, rB = B.rot || {}, rC = C.rot || {}, rD = D.rot || {};
  eachName(rB, rC, n => {
    const q1 = rB[n] || restRot(n) || rC[n], q2 = rC[n] || restRot(n) || q1;
    const q0 = rA[n] || restRot(n) || q1, q3 = rD[n] || restRot(n) || q2;
    const a0 = al(q0, q1), a2 = al(q2, q1), a3 = al(q3, a2);
    const q = [0, 1, 2, 3].map(k => herm(q1[k], a2[k], slope(a0[k], q1[k], a2[k], h0, h), slope(q1[k], a2[k], a3[k], h, h2), h, t));
    const len = Math.hypot(q[0], q[1], q[2], q[3]) || 1;
    rot[n] = q.map(x => x / len);
  });
  const sA = A.pos || {}, sB = B.pos || {}, sC = C.pos || {}, sD = D.pos || {};
  eachName(sB, sC, n => {
    const v1 = sB[n] || restPos(n) || sC[n], v2 = sC[n] || restPos(n) || v1;
    const v0 = sA[n] || restPos(n) || v1, v3 = sD[n] || restPos(n) || v2;
    pos[n] = [0, 1, 2].map(k => herm(v1[k], v2[k], slope(v0[k], v1[k], v2[k], h0, h), slope(v1[k], v2[k], v3[k], h, h2), h, t));
  });
  return { rot, pos };
}

// A game clip turned into editor keys every `every` frames (the last frame is always kept), face bones included.
export function clipToKeys(clip, every = 6) {
  const player = new ClipPlayer(clip);
  const keys = [];
  const last = Math.max(0, clip.ticks - 1);
  const keyAt = f => { const s = player.sample(f); return { frame: f, ease: 'smooth', pose: sampleToPose(s), faceBones: sampleToFaceBones(s) }; };
  for (let f = 0; f <= last; f += every) keys.push(keyAt(f));
  if (keys[keys.length - 1].frame !== last) keys.push(keyAt(last));
  return keys;
}

// The rig's rest of b__ROOT_bind__ (set once the rig is loaded). Half of all creator clips place the body by
// moving that bone; here the body is placed by its two children (lower back and hips), so its motion is folded
// into them - the pose looks exactly the same, with the root bone back at rest.
let ROOT_REST = { t: [0, 1.0122, 0], r: [0.5, 0.5, 0.5, 0.5] };
const HIP_REST = {};
const REST = {};          // keyable bone -> {t, r} at the rig's rest
export function setRig(rig) {
  const b = rig.bones.find(x => x.name === 'b__ROOT_bind__');
  if (b) ROOT_REST = { t: b.pos.slice(), r: b.rot.slice() };
  for (const n of HIPS) { const x = rig.bones.find(y => y.name === n); if (x) HIP_REST[n] = { t: x.pos.slice(), r: x.rot.slice() }; }
  const keyable = new Set(KEYABLE);
  for (const x of rig.bones) if (keyable.has(x.name)) REST[x.name] = { t: x.pos.slice(), r: x.rot.slice() };
}
// A keyable bone's rest ({t: [x, y, z], r: [x, y, z, w]}, local to its parent), or null.
export function restOf(name) { return REST[name] || null; }

// Creator clips often move bones as well as turn them (a hand pulled 7 cm, a stretched spine): any posable bone
// placed more than 0.2 mm off its rest keeps that place, so the imported pose matches the clip's preview.
const MOVED = 0.0002 * 0.0002;
const NEAR_COS = Math.cos(THREE.MathUtils.degToRad(0.2) / 2);            // 0.2 degrees from rest
// (both normalised: the rig's float32 rest quaternions are not exactly unit length)
const turned = (q, r) => Math.abs(q[0] * r[0] + q[1] * r[1] + q[2] * r[2] + q[3] * r[3]) / ((Math.hypot(q[0], q[1], q[2], q[3]) * Math.hypot(r[0], r[1], r[2], r[3])) || 1) < NEAR_COS;
const moved = (t, r) => (t[0] - r[0]) ** 2 + (t[1] - r[1]) ** 2 + (t[2] - r[2]) ** 2 > MOVED;

export function sampleToPose(sample) {
  const rot = {}, pos = {};
  for (const n of POSABLE) if (sample[n] && sample[n].r) rot[n] = sample[n].r;
  for (const n of HIPS) if (sample[n] && sample[n].t) pos[n] = sample[n].t;
  for (const n of POSABLE) {
    const t = sample[n] && sample[n].t, r = REST[n] && REST[n].t;
    if (!t || HIPS_SET.has(n) || !r) continue;
    if (moved(t, r)) pos[n] = t.slice();
  }
  // extra bones (breasts, penis tip, twist helpers...) only where the clip really poses them, as creators keyed them
  for (const n of EXTRA) {
    const s = sample[n], r = REST[n];
    if (!s || !r) continue;
    if (s.r && turned(s.r, r.r)) rot[n] = s.r.slice();
    if (s.t && moved(s.t, r.t)) pos[n] = s.t.slice();
  }
  const rb = sample.b__ROOT_bind__;
  if (rb && (rb.t || rb.r)) {
    // child' = rest^-1 * animated * child
    const qr = new THREE.Quaternion().fromArray(ROOT_REST.r), tr = new THREE.Vector3().fromArray(ROOT_REST.t);
    const qa = rb.r ? new THREE.Quaternion().fromArray(rb.r) : qr.clone(), ta = rb.t ? new THREE.Vector3().fromArray(rb.t) : tr.clone();
    const inv = qr.clone().invert();
    const dq = inv.clone().multiply(qa), dt = ta.clone().sub(tr).applyQuaternion(inv);
    for (const n of HIPS) {
      const r0 = rot[n] || HIP_REST[n]?.r, t0 = pos[n] || HIP_REST[n]?.t;
      if (r0) rot[n] = dq.clone().multiply(new THREE.Quaternion().fromArray(r0)).toArray();
      if (t0) pos[n] = new THREE.Vector3().fromArray(t0).applyQuaternion(dq).add(dt).toArray();
    }
  }
  return { rot, pos };
}

// The face bones of a clip sample. Sparse (default): only bones more than 0.2 degrees or 0.2 mm from rest. Dense:
// every face bone in the sample (for key reduction). Bones the sample has no track for are skipped.
export function sampleToFaceBones(sample, { dense = false } = {}) {
  const rot = {}, pos = {};
  for (const n of FACE_CHANNEL) {
    const s = sample[n], r = REST[n];
    if (!s) continue;
    if (s.r && (dense || !r || turned(s.r, r.r))) rot[n] = s.r.slice();
    if (s.t && (dense || !r || moved(s.t, r.t))) pos[n] = s.t.slice();
  }
  return { rot, pos };
}

// Move the face bones a pose still holds (old projects kept the jaw and tongue in key.pose) into key.faceBones.
// Entries already in key.faceBones win. The result is sparse against the rest: a bone exactly at rest is dropped
// (absent = at rest, so nothing changes). `always` gives the key a faceBones (possibly empty) even when its pose had
// no face bones: the migration uses it, so the face channel keeps exactly the keys the old body channel had.
// Returns the key.
// exactly the rest: every component equal (either sign for a rotation), so dropping it changes nothing at all
const sameQ = (q, r) => [1, -1].some(s => Math.abs(q[0] - s * r[0]) <= 1e-12 && Math.abs(q[1] - s * r[1]) <= 1e-12 && Math.abs(q[2] - s * r[2]) <= 1e-12 && Math.abs(q[3] - s * r[3]) <= 1e-12);
const sameV = (t, r) => Math.abs(t[0] - r[0]) <= 1e-12 && Math.abs(t[1] - r[1]) <= 1e-12 && Math.abs(t[2] - r[2]) <= 1e-12;
export function splitFaceBones(key, { always = false } = {}) {
  if (!key) return key;
  const src = key.pose || {}, rot = {}, pos = {};
  let found = false;
  for (const part of ['rot', 'pos']) {
    const from = src[part];
    if (!from) continue;
    for (const n of Object.keys(from)) {
      if (!FACE_SET.has(n)) continue;
      found = true;
      (part === 'rot' ? rot : pos)[n] = from[n];
      delete from[n];
    }
  }
  if (!found && !always && !key.faceBones) return key;
  const fb = key.faceBones || { rot: {}, pos: {} };
  fb.rot = fb.rot || {}; fb.pos = fb.pos || {};
  for (const [n, q] of Object.entries(rot)) {
    if (n in fb.rot) continue;
    const r = REST[n] && REST[n].r;
    if (r && sameQ(q, r)) continue;
    fb.rot[n] = q;
  }
  for (const [n, t] of Object.entries(pos)) {
    if (n in fb.pos) continue;
    const r = REST[n] && REST[n].t;
    if (r && sameV(t, r)) continue;
    fb.pos[n] = t;
  }
  key.faceBones = fb;
  return key;
}

// One mirror rule for every face bone (spec_face_bones section 1), relative to rest: a turn (x, y, z, w) becomes
// (-x, -y, z, w), a move (x, y, z) becomes (x, y, -z), and left and right swap. Middle bones mirror onto themselves.
// Pure data: {rot, pos} in, {rot, pos} out. Applying it twice gives back the original.
export function mirrorFaceBonesData(fb) {
  const out = { rot: {}, pos: {} };
  if (!fb) return out;
  for (const [n, q] of Object.entries(fb.rot || {})) {
    const to = mirrorName(n), rn = REST[n], rt = REST[to];
    if (!rn || !rt) { out.rot[to] = q.slice(); continue; }
    _qa.fromArray(rn.r).invert().multiply(_qb.fromArray(q));              // the turn relative to rest
    _qc.set(-_qa.x, -_qa.y, _qa.z, _qa.w);
    out.rot[to] = _qb.fromArray(rt.r).multiply(_qc).toArray();
  }
  for (const [n, t] of Object.entries(fb.pos || {})) {
    const to = mirrorName(n), rn = REST[n], rt = REST[to];
    if (!rn || !rt) { out.pos[to] = t.slice(); continue; }
    out.pos[to] = [rt.t[0] + (t[0] - rn.t[0]), rt.t[1] + (t[1] - rn.t[1]), rt.t[2] - (t[2] - rn.t[2])];
  }
  return out;
}

// ---------------------------------------------------------------- twist
// Swing-twist split of a rotation about a unit `axis`: q = swing * twist, the twist applied first (in the bone's own
// frame). Returns {swing, twist} (new quaternions).
export function swingTwist(q, axis = _X) {
  const d = q.x * axis.x + q.y * axis.y + q.z * axis.z;
  const twist = new THREE.Quaternion(axis.x * d, axis.y * d, axis.z * d, q.w);
  if (twist.lengthSq() < 1e-16) twist.identity(); else twist.normalize();
  const swing = q.clone().multiply(twist.clone().invert());
  return { swing, twist };
}

// The signed turn of restQ^-1 * q about `axis` (radians, -pi..pi): how far a bone is twisted about its own axis.
const _tq = new THREE.Quaternion();
export function twistAngle(restQ, q, axis = _X) {
  _tq.copy(restQ).invert().multiply(q);
  const s = _tq.w < 0 ? -1 : 1;
  const p = (_tq.x * axis.x + _tq.y * axis.y + _tq.z * axis.z) * s;
  return 2 * Math.atan2(p, _tq.w * s);
}

// ---------------------------------------------------------------- key reduction
// Where keys are needed to follow a sampled motion (one pose per frame) with straight in-betweens: the first
// frame (and the last one when it doesn't loop), then - split by split - the frame that strays most, until no
// frame is further than the tolerance from the real motion (a quarter of a degree, 1 mm, or 2% of a face slider by
// default). `faces` (slider values per frame) may be null.
const _ka = new THREE.Quaternion(), _kb = new THREE.Quaternion(), _kc = new THREE.Quaternion();
export function keyFramesFor(poses, faces, loop, { angle = THREE.MathUtils.degToRad(0.25), pos: tolPos = 0.001, face: tolFace = 0.02 } = {}) {
  const n = poses.length;
  if (n <= 2) return poses.map((p, i) => i);
  const at = i => (i === n ? 0 : i);                       // frame n is frame 0 again when it loops
  const err = (a, b, i) => {
    const t = (i - a) / (b - a), A = poses[at(a)], B = poses[at(b)], P = poses[i];
    let e = 0;
    for (const bone of Object.keys(P.rot || {})) {
      const qa = (A.rot || {})[bone], qb = (B.rot || {})[bone];
      if (!qa || !qb) continue;
      _ka.fromArray(qa).normalize(); _kb.fromArray(qb).normalize(); _kc.fromArray(P.rot[bone]).normalize();
      _ka.slerp(_kb, t);
      e = Math.max(e, _ka.angleTo(_kc) / angle);
    }
    for (const bone of Object.keys(P.pos || {})) {
      const va = (A.pos || {})[bone], vb = (B.pos || {})[bone], v = P.pos[bone];
      if (!va || !vb) continue;
      const d = Math.hypot(va[0] + (vb[0] - va[0]) * t - v[0], va[1] + (vb[1] - va[1]) * t - v[1], va[2] + (vb[2] - va[2]) * t - v[2]);
      e = Math.max(e, d / tolPos);
    }
    if (faces) {
      const Fa = faces[at(a)], Fb = faces[at(b)], F = faces[i];
      if (Fa || Fb || F) {
        for (const k of new Set([...Object.keys(Fa || {}), ...Object.keys(Fb || {}), ...Object.keys(F || {})])) {
          const x = ((Fa || {})[k] || 0) + (((Fb || {})[k] || 0) - ((Fa || {})[k] || 0)) * t;
          e = Math.max(e, Math.abs(x - ((F || {})[k] || 0)) / tolFace);
        }
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

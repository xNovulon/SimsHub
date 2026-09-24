// Motion layers: one-click generated movement on top of the keys (like Blender's additive NLA strips).
// Pose the sims once, add "Thrust" or "Ride", set how often and how far - it loops perfectly because every
// motion repeats a whole number of times per loop. Pinned hands and feet stay put while the body moves.
import * as THREE from 'three';
import { spaceQuat, spacePos, rotateInSpace, solveTwoBone } from './posemath.js';
import { LIMBS } from './bones.js';
import { $t } from './i18n.js';

const PI = Math.PI, TAU = 2 * Math.PI;
const _q = new THREE.Quaternion();

// ---------------------------------------------------------------- the catalogue
// sign: which way "away from the pose" goes along the axis. Every motion starts from your pose (the contact point).
export const MOTIONS = {
  thrust: { label: $t('motion.thrust'), group: $t('motion.hips'), desc: $t('motion.hips_pull_back_and_push'),
    params: { strokes: 4, distance: 5, sharp: 0.65, tilt: 8, follow: 0.6, axis: 'forward', reverse: false } },
  ride: { label: $t('motion.ride'), group: $t('motion.hips'), desc: $t('motion.rises_and_drops_back_down'),
    params: { strokes: 3, distance: 6, sharp: 0.55, tilt: 6, follow: 0.6, axis: 'up', reverse: false } },
  grind: { label: $t('motion.grind'), group: $t('motion.hips'), desc: $t('motion.rocks_hips_back_and_forth'),
    params: { strokes: 2, distance: 2.5, sharp: 0, tilt: 14, follow: 0.5, axis: 'forward', reverse: false } },
  bounce: { label: $t('motion.bounce'), group: $t('motion.hips'), desc: $t('motion.bounces_up_and_down_soft'),
    params: { strokes: 4, distance: 5, sharp: 0.3, tilt: 2, follow: 0.5, axis: 'up', reverse: false } },
  twerk: { label: $t('motion.twerk'), group: $t('motion.hips'), desc: $t('motion.quick_hip_rolls_with_butt'),
    params: { strokes: 6, distance: 1.5, sharp: 0.4, tilt: 16, follow: 0.3, axis: 'up', reverse: false } },
  sway: { label: $t('motion.sway'), group: $t('motion.hips'), desc: $t('motion.gentle_side_to_side_hips'),
    params: { strokes: 1, distance: 3, sharp: 0, tilt: 0, follow: 0.6, axis: 'side', reverse: false } },
  headbob: { label: $t('motion.head_bob'), group: $t('motion.upper_body'), desc: $t('motion.head_and_neck_go_forward'),
    params: { strokes: 3, angle: 14, distance: 1.5, sharp: 0.3, follow: 0.5, reverse: false } },
  stroke: { label: $t('motion.hand_stroke'), group: $t('motion.hands'), desc: $t('motion.hand_slides_back_and_forth'),
    params: { strokes: 3, distance: 8, sharp: 0.2, limb: 'R hand', axis: 'penis', reverse: false } },
  breathe: { label: $t('motion.breathing'), group: $t('motion.upper_body'), desc: $t('motion.chest_rises_and_falls_makes'),
    params: { strokes: 2, angle: 2.5, sharp: 0, follow: 0 } },
  // late: they run after every sim's pose is known (pass B), so they see where the partner really is this frame
  look: { label: $t('motion.look_at'), group: $t('motion.upper_body'), late: true,
    desc: $t('motion.head_neck_and_eyes_turn'),
    params: { target: 'face', who: 'auto', eyes: true, limit: 70 } },
  tremble: { label: $t('motion.tremble'), group: $t('motion.whole_body'), late: true,
    desc: $t('motion.shaking_legs_hands_or_whole'),
    params: { amount: 2.5, speed: 1, parts: 'legs', start: 0, end: 1 } },
  // spec_game 6: the game's own idle loops on top of the pose. `times` (not `strokes`: a new motion copies the
  // partner's strokes, and breathing must keep its own pace) 0 = Auto, as often as fits the loop at the game's speed.
  idle: { label: $t('motion.idle_from_game'), group: $t('motion.upper_body'),
    desc: $t('motion.real_breathing_and_small_shifts'),
    params: { clip: 'a_idle_neutral_loop_3_x', times: 0 } },
};

export const MOTION_PARAMS = {
  strokes: { label: $t('motion.times_per_loop'), min: 1, max: 16, step: 1, unit: '×', hint: $t('motion.whole_numbers_keep_loop_seamless') },
  distance: { label: $t('motion.distance'), min: 0, max: 30, step: 0.5, unit: 'cm' },
  angle: { label: $t('motion.angle'), min: 0, max: 40, step: 0.5, unit: '°' },
  sharp: { label: $t('motion.soft_hard'), min: 0, max: 1, step: 0.05, pct: true, hint: $t('motion.hard_speeds_up_into_pose') },
  tilt: { label: $t('motion.hip_roll'), min: -30, max: 30, step: 1, unit: '°' },
  follow: { label: $t('motion.body_follows'), min: 0, max: 1, step: 0.05, pct: true, hint: $t('motion.spine_and_head_react_moment') },
  phase: { label: $t('motion.timing_offset'), min: 0, max: 1, step: 0.01, pct: true, hint: $t('motion.shift_it_against_partner') },
  weight: { label: $t('motion.strength'), min: 0, max: 1.5, step: 0.05, pct: true },
  amount: { label: $t('motion.shaking'), min: 0, max: 8, step: 0.1, unit: '°' },
  speed: { label: $t('motion.speed'), min: 0.5, max: 2, step: 0.05, unit: '×' },
  limit: { label: $t('motion.turn_up_to'), min: 20, max: 90, step: 1, unit: '°', hint: $t('motion.past_this_eyes_do_rest') },
  start: { label: $t('motion.starts_at'), min: 0, max: 1, step: 0.01, pct: true, hint: $t('motion.where_in_loop_it_begins') },
  end: { label: $t('motion.ends_at'), min: 0, max: 1, step: 0.01, pct: true, hint: $t('motion.where_in_loop_it_stops') },
};
export const LOOK_TARGETS = { face: $t('motion.look_face'), chest: $t('motion.look_chest'), groin: $t('motion.between_legs'), camera: $t('motion.where_camera_is_now') };
export const TREMBLE_PARTS = { legs: $t('motion.tremble_legs'), hands: $t('motion.tremble_hands'), body: $t('motion.tremble_body') };
export const AXES = { forward: $t('motion.where_hips_face'), up: $t('motion.straight_up'), bodyUp: $t('motion.along_back'), side: $t('motion.axis_side'), penis: $t('motion.axis_penis'), forearm: $t('motion.along_forearm') };

let _id = 0;
export function newLayer(type) {
  const m = MOTIONS[type];
  return { id: 'm' + Date.now().toString(36) + (_id++), type, on: true, weight: 1, phase: 0, params: { ...m.params } };
}

// ---------------------------------------------------------------- shapes
// How far from the pose the body is at loop phase p (0..1): 0 = at the pose (contact), 1 = farthest.
// Soft = a cosine. Hard = slow release, then speeds up into the pose (a real hit, velocity peaks at contact).
export function awayCurve(p, sharp) {
  p = ((p % 1) + 1) % 1;
  const soft = (1 - Math.cos(TAU * p)) / 2;
  const d = 0.42;
  let hard;
  if (p < 1 - d) { const u = p / (1 - d); hard = (1 - Math.cos(PI * u)) / 2; }
  else { const u = (p - (1 - d)) / d; hard = 1 - u * u * u; }
  return soft + (hard - soft) * sharp;
}

// ---------------------------------------------------------------- body frames (sim space)
export function pelvisAxes(v) {
  const q = spaceQuat(v, v.bone('b__Pelvis__'), _q.clone());
  return {
    forward: new THREE.Vector3(0, 1, 0).applyQuaternion(q),
    up: new THREE.Vector3(-1, 0, 0).applyQuaternion(q),
    left: new THREE.Vector3(0, 0, -1).applyQuaternion(q),
  };
}
export function chestLateral(v) {
  const l = spacePos(v, v.bone('b__L_Clavicle__')).sub(spacePos(v, v.bone('b__R_Clavicle__')));
  return l.lengthSq() > 1e-8 ? l.normalize() : new THREE.Vector3(1, 0, 0);
}

// The groin in sim space: where the penis starts (the rig has that bone on every body; on a female body it sits
// at the vulva), the point the hips roll around.
function groin(v) {
  const b = v.bone('b__Penis_Base');
  if (b) return spacePos(v, b);
  return spacePos(v, v.bone('b__Pelvis__')).add(new THREE.Vector3(0.19, 0.11, 0).applyQuaternion(spaceQuat(v, v.bone('b__Pelvis__'))));
}

// Move both hip bones by a sim-space offset.
export function offsetHips(v, d) {
  const toLocal = spaceQuat(v, v.bone('b__ROOT_bind__')).invert();
  const local = d.clone().applyQuaternion(toLocal);
  v.bone('b__Spine0__').position.add(local);
  v.bone('b__Pelvis__').position.add(local);
}

function turn(v, name, axis, deg) {
  if (!deg) return;
  const b = v.bone(name);
  if (b) rotateInSpace(v, b, new THREE.Quaternion().setFromAxisAngle(axis, THREE.MathUtils.degToRad(deg)));
}

// ---------------------------------------------------------------- applying
// ctx: {frame, length, others: [{v, sim}], base: {axes}} ; changes the view's bones in place.
export function applyLayer(v, layer, ctx) {
  const m = MOTIONS[layer.type];
  if (!m || !layer.on) return;
  const P = { ...m.params, ...layer.params };
  if (layer.type === 'look') return applyLook(v, layer, P, ctx);
  if (layer.type === 'tremble') { applyTremble(v, layer, P, ctx); return; }
  if (layer.type === 'idle') { applyIdle(v, layer, P, ctx); return; }
  const w = layer.weight ?? 1;
  const strokes = Math.max(1, Math.round(P.strokes || 1));
  const cyc = ctx.length / strokes;                         // frames per stroke
  const phase = (ctx.frame / ctx.length) * strokes + (layer.phase || 0);
  const a = awayCurve(phase, P.sharp || 0);
  const lag = k => awayCurve(phase - (k * 2.5) / cyc, P.sharp || 0);   // k * 2.5 frames later
  const sign = P.reverse ? -1 : 1;
  const ax = pelvisAxes(v);

  if (m.group === 'Hips') {
    let dir, away;
    if (layer.type === 'sway') { dir = ax.left; away = Math.sin(TAU * phase); }
    else {
      dir = { forward: ax.forward.clone().negate(), up: new THREE.Vector3(0, 1, 0), bodyUp: ax.up.clone(), side: ax.left.clone() }[P.axis] || ax.forward.clone().negate();
      away = a;
    }
    offsetHips(v, dir.multiplyScalar(sign * (P.distance || 0) / 100 * away * w));
    // hips roll: tucked under at the pose, tipped back (butt out) when away. The roll turns around the groin, so
    // it never adds to or eats into the stroke: "Distance" stays the real travel in and out.
    const lat = ax.left;
    const roll = (P.tilt || 0) * away * w * (layer.type === 'sway' ? 0 : 1);
    if (roll) {
      const before = groin(v);
      turn(v, 'b__Pelvis__', lat, roll);
      turn(v, 'b__Spine0__', lat, roll * 0.35);
      offsetHips(v, before.sub(groin(v)));
    }
    // follow-through: the upper body answers a little later and the head steadies itself
    const f = (P.follow || 0) * w;
    if (f) {
      const chest = chestLateral(v);
      const react = k => lag(k) * f;
      const mag = layer.type === 'sway' ? 0 : Math.max(2.5, Math.abs(P.tilt || 0) * 0.5) + (P.distance || 0) * 0.35;
      turn(v, 'b__Spine1__', chest, react(1) * mag * 0.45);
      turn(v, 'b__Spine2__', chest, react(2) * mag * 0.4);
      turn(v, 'b__Neck__', chest, react(3) * mag * 0.3);
      turn(v, 'b__Head__', chest, -react(2) * mag * 0.45);
      if (layer.type === 'sway') {
        const up = new THREE.Vector3(0, 1, 0);
        const s = k => Math.sin(TAU * (phase - (k * 2.5) / cyc)) * f;
        turn(v, 'b__Spine1__', ax.forward, s(1) * 3);
        turn(v, 'b__Spine2__', ax.forward, s(2) * 3);
        turn(v, 'b__Head__', ax.forward, -s(2) * 4);
        void up;
      }
    }
  } else if (layer.type === 'headbob') {
    const chest = chestLateral(v);
    const ang = (P.angle || 0) * sign * w;
    const s = k => -lag(k);                                 // 0 at the pose, -1 = head pulled back
    turn(v, 'b__Spine1__', chest, s(0) * ang * 0.35);
    turn(v, 'b__Spine2__', chest, s(1) * ang * 0.4);
    turn(v, 'b__Neck__', chest, s(1) * ang * 0.5);
    turn(v, 'b__Head__', chest, s(2) * ang * 0.25);
    offsetHips(v, ax.forward.clone().multiplyScalar(-a * (P.distance || 0) / 100 * w));
  } else if (layer.type === 'breathe') {
    const chest = chestLateral(v);
    const s = Math.sin(TAU * phase) * (P.angle || 0) * w;
    turn(v, 'b__Spine1__', chest, -s * 0.4);
    turn(v, 'b__Spine2__', chest, -s * 0.6);
    turn(v, 'b__Neck__', chest, s * 0.5);
    turn(v, 'b__L_Clavicle__', ax.forward, s * 0.5);
    turn(v, 'b__R_Clavicle__', ax.forward, -s * 0.5);
  } else if (layer.type === 'stroke') {
    const chain = LIMBS[P.limb] || LIMBS['R hand'];
    const [A, B, C] = chain.map(n => v.bone(n));
    const hand = spacePos(v, C);
    let dir = null;
    if (P.axis === 'penis') dir = nearestShaft(v, hand, ctx.others);
    if (!dir && P.axis === 'up') dir = new THREE.Vector3(0, 1, 0);
    if (!dir && P.axis === 'forward') dir = ax.forward.clone();
    if (!dir) dir = hand.clone().sub(spacePos(v, B)).normalize();
    const s = (a - 0.5) * 2 * sign;                          // -1..1 along the shaft
    const target = hand.clone().add(dir.multiplyScalar(s * (P.distance || 0) / 100 / 2 * w));
    const mid = spacePos(v, A).add(target).multiplyScalar(0.5);
    const pole = spacePos(v, B).add(spacePos(v, B).sub(mid).normalize().multiplyScalar(0.4));
    solveTwoBone(v, A, B, C, target, pole);
  }
}

// ---------------------------------------------------------------- look at (spec_bodies 6.1)
const RAD22 = THREE.MathUtils.degToRad(22);
const clamp1 = x => Math.max(-1, Math.min(1, x));
const midOf = (w, a, b) => (w.bone(a) && w.bone(b) ? w.worldPos(a).add(w.worldPos(b)).multiplyScalar(0.5) : null);

// Where to look, in the sim space of `v` (null: nothing to look at). ctx.others: [{sim, v}] (every other sim, posed
// this frame - look-at runs in pass B).
export function lookTarget(v, P, ctx) {
  if (P.target === 'camera') return Array.isArray(P.point) ? new THREE.Vector3().fromArray(P.point) : null;
  const others = (ctx.others || []).filter(o => o && o.v && o.v !== v && o.v.group.visible !== false);
  if (!others.length) return null;
  let o = P.who && P.who !== 'auto' ? others.find(x => x.sim && x.sim.id === P.who) : null;
  if (!o) {
    // the nearest other sim, by head distance
    const hp = v.bone('b__Head__') ? v.worldPos('b__Head__') : null;
    let best = Infinity;
    for (const x of others) {
      const d = hp && x.v.bone('b__Head__') ? x.v.worldPos('b__Head__').distanceTo(hp) : 0;
      if (d < best) { best = d; o = x; }
    }
  }
  if (!o) return null;
  const w = o.v;
  let at = null;
  if (P.target === 'chest') at = midOf(w, 'b__L_breastTarget_slot', 'b__R_breastTarget_slot') || (w.bone('b__Spine2__') ? w.worldPos('b__Spine2__') : null);
  else if (P.target === 'groin') at = w.bone('b__Penis_Base') ? w.worldPos('b__Penis_Base') : w.bone('b__Pelvis__') ? w.worldPos('b__Pelvis__') : null;
  else at = midOf(w, 'b__L_Eye__', 'b__R_Eye__') || (w.bone('b__Head__') ? w.worldPos('b__Head__') : null);
  if (!at) return null;
  v.space.updateWorldMatrix(true, false);
  return v.space.worldToLocal(at);
}

// Neck 40% and head 60% of the turn, at most `limit` degrees; the eyes (face sliders lookUp / lookSide, 22 degrees per
// 1.0) do what is left. -> {lookUp, lookSide, weight} for the face, or null (eyes off / nothing to look at).
function applyLook(v, layer, P, ctx) {
  const head = v.bone('b__Head__'), neck = v.bone('b__Neck__'), le = v.bone('b__L_Eye__'), re = v.bone('b__R_Eye__');
  if (!head || !neck || !le || !re) return null;
  const tgt = lookTarget(v, P, ctx);
  if (!tgt) return null;
  const w = Math.max(0, Math.min(1.5, layer.weight ?? 1));
  const eyes = () => spacePos(v, le).add(spacePos(v, re)).multiplyScalar(0.5);
  const fwd = () => new THREE.Vector3(0, 1, 0).applyQuaternion(spaceQuat(v, head));
  let want = tgt.clone().sub(eyes());
  if (want.lengthSq() < 1e-8) return null;
  want.normalize();
  const total = fwd().angleTo(want), lim = THREE.MathUtils.degToRad(P.limit ?? 70);
  const share = Math.min(1, lim / Math.max(total, 1e-6)) * Math.min(1, w);
  const swing = (f, part) => new THREE.Quaternion().slerp(new THREE.Quaternion().setFromUnitVectors(f, want), part);
  rotateInSpace(v, neck, swing(fwd(), share * 0.4));
  want = tgt.clone().sub(eyes()).normalize();          // the neck moved the eyes a little
  rotateInSpace(v, head, swing(fwd(), Math.min(1, share * 0.6 / Math.max(1e-6, 1 - share * 0.4))));
  if (P.eyes === false) return null;
  const d = tgt.clone().sub(eyes()).normalize().applyQuaternion(spaceQuat(v, head).invert());   // head frame: x up, y fwd, z left
  return { lookSide: clamp1(Math.atan2(d.z, d.y) / RAD22), lookUp: clamp1(Math.atan2(d.x, Math.hypot(d.y, d.z)) / RAD22), weight: Math.min(1, w) };
}

// ---------------------------------------------------------------- tremble (spec_bodies 6.1)
// Three sine waves per bone, each a whole number of times per loop (so the loop joins), fixed phases and axes per
// bone (a hash of the layer and the bone), faded in and out over 8% of the loop around [start, end].
const TREMBLE_BONES = {
  legs: [['Thigh', 1], ['Calf', 0.6], ['Foot', 0.5]],
  hands: [['Forearm', 0.5], ['Hand', 1], ['Thumb0', 0.4], ['Index0', 0.4], ['Mid0', 0.4], ['Ring0', 0.4], ['Pinky0', 0.4]],
  body: [['b__Spine1__', 0.5], ['b__Spine2__', 0.5], ['b__Neck__', 0.4], ['b__Head__', 0.3], ['Clavicle', 0.4], ['Thigh', 1], ['Calf', 0.6], ['Foot', 0.5]],
};
const TREMBLE_HZ = [6.5, 9.7, 13.3], TREMBLE_W = [0.55, 0.3, 0.15];
function hash01(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  h ^= h >>> 13; h = Math.imul(h, 0x5bd1e995); h ^= h >>> 15;
  return (h >>> 0) / 4294967296;
}
const smooth = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
// 1 inside [start, end] (a circle: start > end wraps over the loop point), fading over 8% of the loop at each end.
export function trembleEnvelope(u, start = 0, end = 1) {
  const s0 = Math.max(0, Math.min(1, start)), e0 = Math.max(0, Math.min(1, end));
  if (s0 <= 1e-6 && e0 >= 1 - 1e-6) return 1;
  const len = ((e0 - s0) % 1 + 1) % 1;
  if (len < 1e-6) return 0;
  const s = ((u - s0) % 1 + 1) % 1;
  const d = s <= len ? Math.min(s, len - s) : -Math.min(s - len, 1 - s);
  return smooth(-0.04, 0.04, d);
}
// The shake at loop position u (0..1) for one bone: the three waves summed (before the strength and the part weight).
export function trembleWave(key, u, cycles) {
  let a = 0;
  for (let i = 0; i < 3; i++) a += TREMBLE_W[i] * Math.sin(2 * Math.PI * (cycles[i] * u + hash01(key + '|' + i)));
  return a;
}
export function trembleCycles(length, fps, speed = 1) {
  const T = Math.max(1, length) / Math.max(1, fps || 30);
  return TREMBLE_HZ.map(f => Math.max(1, Math.round(T * f * (speed || 1))));
}
function applyTremble(v, layer, P, ctx) {
  const amount = (P.amount ?? 2.5) * (layer.weight ?? 1);
  if (!amount) return;
  const u = ((ctx.frame / Math.max(1, ctx.length)) % 1 + 1) % 1;
  const env = trembleEnvelope(u, P.start ?? 0, P.end ?? 1);
  if (env <= 0) return;
  const cycles = trembleCycles(ctx.length, ctx.fps, P.speed);
  const list = TREMBLE_BONES[P.parts] || TREMBLE_BONES.legs;
  for (const [nm, wPart] of list) {
    const names = nm.startsWith('b__') ? [nm] : ['b__L_' + nm + '__', 'b__R_' + nm + '__'];
    for (const n of names) {
      const b = v.bone(n);
      if (!b) continue;
      const key = (layer.id || 'tremble') + n;
      const deg = amount * wPart * env * trembleWave(key, u, cycles);
      if (!deg) continue;
      const axis = new THREE.Vector3(hash01(key + 'x') < 0.5 ? -0.35 : 0.35, 0, 1).normalize();
      b.quaternion.multiply(_q.setFromAxisAngle(axis, THREE.MathUtils.degToRad(deg)));
    }
  }
}

// ---------------------------------------------------------------- idle from the game (spec_game 6)
// IDLE_CACHE[clip] = {ticks, fps, bones: [[name, Float32Array(ticks * 4)]], shift: Float32Array(ticks * 3) | null}
// from /api/ea_idle: each bone's turn since the clip's first tick in its own space (the pelvis at half strength),
// and the hips' weight shift in the body's frame. Until a clip has arrived the layer does nothing; when it arrives,
// 'wa:idle-loaded' tells the app to show it (features/ea.js).
export const IDLE_CACHE = {};
const _idleLoading = new Map();
const _qa = new THREE.Quaternion(), _qb = new THREE.Quaternion(), _qp = new THREE.Quaternion(), _vs = new THREE.Vector3();

export function idleData(name) { return IDLE_CACHE[name] || null; }

// Fetch a game idle once (later calls share the same request). -> Promise<data | null>
export function loadIdle(name) {
  if (!name) return Promise.resolve(null);
  if (IDLE_CACHE[name]) return Promise.resolve(IDLE_CACHE[name]);
  if (_idleLoading.has(name)) return _idleLoading.get(name);
  if (typeof fetch !== 'function') return Promise.resolve(null);
  const pr = fetch('/api/ea_idle?name=' + encodeURIComponent(name)).then(r => (r.ok ? r.json() : r.json().then(b => { throw new Error(b.error || r.statusText); })))
    .then(d => {
      const ticks = Math.max(2, d.ticks | 0);
      const bones = [];
      for (const [n, rows] of Object.entries(d.bones || {})) {
        const a = new Float32Array(ticks * 4);
        for (let i = 0; i < ticks; i++) { const q = rows[Math.min(i, rows.length - 1)] || [0, 0, 0, 1]; a.set(q, i * 4); }
        bones.push([n, a]);
      }
      let shift = null;
      if (Array.isArray(d.shift) && d.shift.length) {
        shift = new Float32Array(ticks * 3);
        for (let i = 0; i < ticks; i++) shift.set(d.shift[Math.min(i, d.shift.length - 1)] || [0, 0, 0], i * 3);
      }
      IDLE_CACHE[name] = { name, ticks, fps: d.fps || 30, bones, shift };
      return IDLE_CACHE[name];
    })
    .catch(err => {
      IDLE_CACHE[name] = { name, ticks: 0, fps: 30, bones: [], shift: null, error: String((err && err.message) || err) };
      return IDLE_CACHE[name];
    })
    .finally(() => {
      _idleLoading.delete(name);
      if (typeof window !== 'undefined' && window.dispatchEvent) window.dispatchEvent(new CustomEvent('wa:idle-loaded', { detail: { name, ok: !IDLE_CACHE[name]?.error } }));
    });
  _idleLoading.set(name, pr);
  return pr;
}

// How many times the idle plays per loop: "Times per loop" when set, else as often as fits at the game's own speed.
export function idleCycles(d, length, fps, times = 0) {
  const t = Math.round(times || 0);
  if (t > 0) return t;
  if (!d || !d.ticks) return 1;
  const loopSec = Math.max(1, length) / (fps || 30), clipSec = Math.max(1, d.ticks - 1) / (d.fps || 30);
  return Math.max(1, Math.round(loopSec / clipSec));
}

// q to the power w (the same axis, w times the angle): strength 0..1.5.
function powQuat(q, w) {
  if (w === 1) return q;
  if (q.w < 0) q.set(-q.x, -q.y, -q.z, -q.w);
  const s = Math.sqrt(Math.max(0, 1 - q.w * q.w));
  if (s < 1e-9 || !w) return q.set(0, 0, 0, 1);
  const ang = 2 * Math.acos(Math.min(1, q.w)) * w, k = Math.sin(ang / 2) / s;
  return q.set(q.x * k, q.y * k, q.z * k, Math.cos(ang / 2));
}

function applyIdle(v, layer, P, ctx) {
  const name = P.clip || MOTIONS.idle.params.clip;
  const d = IDLE_CACHE[name];
  if (!d) { loadIdle(name); return; }
  if (!d.ticks) return;
  const w = Math.max(0, Math.min(1.5, layer.weight ?? 1));
  if (!w) return;
  const L = Math.max(1, ctx.length);
  const cycles = idleCycles(d, L, ctx.fps, P.times || P.strokes);
  let u = ((ctx.frame / L) * cycles + (layer.phase || 0)) % 1;
  if (u < 0) u += 1;
  const t = u * (d.ticks - 1), i0 = Math.floor(t), i1 = Math.min(d.ticks - 1, i0 + 1), f = t - i0;
  // the weight shift first, turned with the hips as they are posed (a lying sim shifts along the bed)
  if (d.shift) {
    const pel = v.bone('b__Pelvis__'), rest = v.restByName && v.restByName['b__Pelvis__'];
    if (pel && rest) {
      _vs.set(d.shift[i0 * 3] + (d.shift[i1 * 3] - d.shift[i0 * 3]) * f, d.shift[i0 * 3 + 1] + (d.shift[i1 * 3 + 1] - d.shift[i0 * 3 + 1]) * f,
        d.shift[i0 * 3 + 2] + (d.shift[i1 * 3 + 2] - d.shift[i0 * 3 + 2]) * f).multiplyScalar(w);
      spaceQuat(v, pel, _qp).multiply(_qb.copy(rest.quat).invert());
      offsetHips(v, _vs.applyQuaternion(_qp));
    }
  }
  for (const [n, a] of d.bones) {
    const b = v.bone(n);
    if (!b) continue;
    _qa.fromArray(a, i0 * 4); _qb.fromArray(a, i1 * 4);
    _qa.slerp(_qb, f);
    b.quaternion.multiply(powQuat(_qa, w));
  }
}

// Direction (sim space of `v`) of the penis shaft closest to `point`, from base to tip, if within 35 cm.
export function nearestShaft(v, point, others = []) {
  let best = null, bestD = 0.35;
  for (const o of others) {
    if (!o.v.hasPenis) continue;
    const base = o.v.worldPos('b__Penis_Base'), tip = o.v.worldPos('b__Penis_Tip');
    const pw = v.space.localToWorld(point.clone());
    const d = distToSegment(pw, base, tip);
    if (d < bestD) { bestD = d; best = [base, tip]; }
  }
  if (!best) return null;
  const a = v.space.worldToLocal(best[0].clone()), b = v.space.worldToLocal(best[1].clone());
  return b.sub(a).normalize();
}

export function distToSegment(p, a, b) {
  const ab = b.clone().sub(a), t = THREE.MathUtils.clamp(p.clone().sub(a).dot(ab) / Math.max(1e-9, ab.lengthSq()), 0, 1);
  return a.clone().add(ab.multiplyScalar(t)).distanceTo(p);
}

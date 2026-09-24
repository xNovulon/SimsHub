// Hand shapes: one click for a whole hand (Relaxed, Grip, Fist, Flat on skin, Point...), plus Curl / Spread /
// Thumb sliders. The shapes were mined from 700 creator clips (6,641 finger samples, right hands mirrored onto the
// left; spec_bodies Appendix B) and are written as left-hand rotation vectors in degrees from rest, per finger
// [base, middle, tip]. The right hand mirrors them: (x, y, z) -> (-x, -y, z). Fingers bend about their local z
// (+z curls toward the palm); the base joint's y spreads the finger. The middle and tip joints are hinges: only
// their z is used.
import * as THREE from 'three';
import { LIMITS } from './bones.js';
import { rvToQuat, quatToRv } from './posemath.js';
import { $t } from './i18n.js';

export const FINGERS = ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'];
const CURLED = ['Index', 'Mid', 'Ring', 'Pinky'];

// [base, middle, tip] rotation vectors per finger (left hand)
const M = {
  flat: { Thumb: [[1, -5, -6], [-1, -2, 0], [0, 0, 0]], Index: [[0, 2, 2], [0, 0, 3], [0, -1, 2]], Mid: [[-1, 0, 2], [0, 0, 3], [0, 0, 2]],
    Ring: [[-1, -1, 1], [0, 0, 3], [0, 0, 2]], Pinky: [[-2, -3, 1], [0, 0, 2], [0, 0, 1]] },
  relaxed: { Thumb: [[1, -1, -5], [-1, -2, 5], [0, -1, 5]], Index: [[0, 1, 16], [0, -2, 14], [0, -2, 12]], Mid: [[0, -1, 15], [0, -1, 16], [0, -2, 12]],
    Ring: [[-1, -2, 15], [0, -1, 16], [0, -1, 13]], Pinky: [[-2, -5, 15], [0, -1, 15], [0, -1, 12]] },
  soft: { Thumb: [[0, 3, -5], [0, -2, 9], [0, -1, 10]], Index: [[-2, -3, 26], [0, -5, 26], [0, -5, 24]], Mid: [[-2, -3, 29], [0, -3, 29], [1, -4, 26]],
    Ring: [[-3, -4, 31], [0, -3, 30], [0, -3, 27]], Pinky: [[-4, -6, 31], [0, -3, 30], [0, -2, 26]] },
  grip: { Thumb: [[6, 11, 5], [0, -1, 19], [-1, -1, 20]], Index: [[-3, -8, 42], [-1, -11, 45], [0, -11, 42]], Mid: [[-2, -5, 47], [-1, -7, 49], [1, -10, 47]],
    Ring: [[-4, -5, 54], [-1, -7, 55], [-1, -7, 52]], Pinky: [[-4, -4, 56], [-1, -6, 55], [0, -6, 52]] },
  pinch: { Thumb: [[35, 34, 2], [4, 0, 27], [-2, -1, 35]], Index: [[0, -3, 33], [-1, -3, 50], [0, -3, 35]], Mid: [[-2, -1, 38], [-1, -2, 53], [0, -3, 39]],
    Ring: [[-5, 1, 40], [-1, -2, 51], [0, -2, 38]], Pinky: [[-8, 0, 40], [-1, -1, 46], [0, -1, 35]] },
  stroke: { Thumb: [[20, 19, 5], [6, 1, 35], [-1, 0, 39]], Index: [[5, -3, 69], [0, 1, 75], [-1, 1, 68]], Mid: [[0, 0, 71], [0, 1, 76], [0, 0, 69]],
    Ring: [[-4, 3, 72], [-1, 1, 77], [0, 0, 68]], Pinky: [[-7, 4, 71], [0, 1, 76], [0, 1, 64]] },
  fist: { Thumb: [[5, 9, 4], [2, -2, 43], [-1, -3, 62]], Index: [[4, -2, 87], [0, 0, 94], [0, 0, 91]], Mid: [[1, 0, 87], [0, 0, 94], [0, 0, 95]],
    Ring: [[-2, 1, 88], [0, 0, 95], [0, 0, 95]], Pinky: [[-6, 0, 89], [0, 0, 94], [0, 0, 95]] },
};
// Spread: the base joints' y (left hand), degrees at 100% - the index away from the middle finger, the pinky away
// from the ring finger.
const SPREAD = { Thumb: 0, Index: 12, Mid: 4, Ring: -4, Pinky: -12 };
const withSpread = (rv, s) => Object.fromEntries(FINGERS.map(f => [f, rv[f].map((j, k) => (k === 0 ? [j[0], j[1] + SPREAD[f] * s, j[2]] : j))]));

export const HAND_SHAPES = {
  relaxed: { label: $t('hands.relaxed'), rv: M.relaxed, tip: $t('hands.loose_and_natural_most_poses') },
  soft: { label: $t('hands.soft'), rv: M.soft, tip: $t('hands.gently_bent') },
  grip: { label: $t('hands.grip'), rv: M.grip, tip: $t('hands.holding_on_to_something') },
  fist: { label: $t('hands.fist'), rv: M.fist, tip: $t('hands.closed_hand') },
  flat: { label: $t('hands.flat_on_skin'), short: $t('hands.flat'), rv: M.flat, tip: $t('hands.straight_fingers_palm_laid_on') },
  point: { label: $t('hands.point'), rv: { ...M.fist, Index: M.flat.Index }, tip: $t('hands.index_finger_out') },
  two: { label: $t('hands.two_fingers'), short: $t('hands.two'), rv: { ...M.fist, Index: M.flat.Index, Mid: M.flat.Mid }, tip: $t('hands.index_and_middle_finger_out') },
  spread: { label: $t('hands.spread'), rv: withSpread(M.flat, 1), spread: 1, tip: $t('hands.fingers_wide_apart') },
  pinch: { label: $t('hands.pinch'), rv: M.pinch, tip: $t('hands.thumb_and_fingers_together') },
  stroke: { label: $t('hands.stroke_grip'), short: $t('hands.stroke'), rv: M.stroke, tip: $t('hands.fingers_round_shaft_handjob') },
};
export const SHAPE_ORDER = ['relaxed', 'soft', 'grip', 'fist', 'flat', 'point', 'two', 'spread', 'pinch', 'stroke'];
export const MINED = ['flat', 'relaxed', 'soft', 'grip', 'pinch', 'stroke', 'fist'];

export const boneOf = (side, f, k) => `b__${side}_${f}${k}__`;
export const HAND_BONES = side => FINGERS.flatMap(f => [0, 1, 2].map(k => boneOf(side, f, k)));
const mirror = (side, [x, y, z]) => (side === 'R' ? [-x, -y, z] : [x, y, z]);
// The curl reach per joint at 100%: 0.95 x the upper natural limit (spec_bodies Appendix C)
export const Z_MAX = Object.fromEntries(CURLED.map(f => [f, [0, 1, 2].map(k => 0.95 * LIMITS[boneOf('L', f, k)].z[1])]));
const THUMB_T = [[35, 34, 2], [0, 0, 40], [0, 0, 60]];         // the thumb slider at 100% (it folds across the palm)

// The side of a hand or finger bone ('L' / 'R'), or null.
export function handSide(name) {
  const m = /^b__(L|R)_(Hand|Thumb\d|Index\d|Mid\d|Ring\d|Pinky\d)__$/.exec(name || '');
  return m ? m[1] : null;
}

// The shape's local rotations (rest x exp(rv)) for one side, as {bone: Quaternion}.
export function shapeQuats(v, side, shape, { spread = 0 } = {}) {
  const sh = typeof shape === 'string' ? HAND_SHAPES[shape] : shape;
  if (!sh) return {};
  const out = {};
  for (const f of FINGERS) {
    (sh.rv[f] || []).forEach((rv0, k) => {
      const name = boneOf(side, f, k), r = v.restByName[name];
      if (!r) return;
      let rv = k > 0 ? [0, 0, rv0[2]] : [rv0[0], rv0[1] + (k === 0 ? SPREAD[f] * spread : 0), rv0[2]];
      rv = mirror(side, rv);
      out[name] = r.quat.clone().multiply(rvToQuat(rv));
    });
  }
  return out;
}

// Blend the side's finger bones from their current rotation toward the shape by `amount` (slerp).
export function applyHandShape(v, side, id, amount = 1) {
  const qs = shapeQuats(v, side, id);
  for (const [name, q] of Object.entries(qs)) {
    const b = v.bone(name);
    if (b) b.quaternion.slerp(q, Math.max(0, Math.min(1, amount))).normalize();
  }
  return Object.keys(qs).length;
}

// One finger joint's turn from rest as a left-hand rotation vector (degrees).
function readRv(v, side, name) {
  const b = v.bone(name), r = v.restByName[name];
  if (!b || !r) return [0, 0, 0];
  return mirror(side, quatToRv(r.quat.clone().invert().multiply(b.quaternion).normalize()));
}
function writeRv(v, side, name, rv) {
  const b = v.bone(name), r = v.restByName[name];
  if (b && r) b.quaternion.copy(r.quat).multiply(rvToQuat(mirror(side, rv))).normalize();
}

// Sliders (relative to rest, on top of the current pose):
//   Curl 0..1   - every joint of the four fingers bends to curl x its reach (x and y kept)
//   Spread -0.5..1 - the base joints fan out (y), curl kept
//   Thumb 0..1  - the thumb folds across the palm
export function setCurl(v, side, c) {
  for (const f of CURLED) for (let k = 0; k < 3; k++) {
    const name = boneOf(side, f, k), rv = readRv(v, side, name);
    writeRv(v, side, name, k > 0 ? [0, 0, c * Z_MAX[f][k]] : [rv[0], rv[1], c * Z_MAX[f][k]]);
  }
}
export function setSpread(v, side, s) {
  for (const f of CURLED) {
    const name = boneOf(side, f, 0), rv = readRv(v, side, name);
    writeRv(v, side, name, [rv[0], SPREAD[f] * s, rv[2]]);
  }
}
export function setThumb(v, side, t) {
  THUMB_T.forEach((full, k) => writeRv(v, side, boneOf(side, 'Thumb', k), full.map(x => x * t)));
}
// The sliders' values for what the hand shows now (least squares on the curl z, the spread y and the thumb).
export function readHand(v, side) {
  let cn = 0, cd = 0, sn = 0, sd = 0, tn = 0, td = 0;
  for (const f of CURLED) for (let k = 0; k < 3; k++) {
    const rv = readRv(v, side, boneOf(side, f, k)), z = Z_MAX[f][k];
    cn += rv[2] * z; cd += z * z;
    if (k === 0) { sn += rv[1] * SPREAD[f]; sd += SPREAD[f] * SPREAD[f]; }
  }
  THUMB_T.forEach((full, k) => {
    const rv = readRv(v, side, boneOf(side, 'Thumb', k));
    for (let a = 0; a < 3; a++) { tn += rv[a] * full[a]; td += full[a] * full[a]; }
  });
  return { curl: cd ? cn / cd : 0, spread: sd ? sn / sd : 0, thumb: td ? tn / td : 0 };
}

// Which shape the hand shows now (within 6 degrees at every joint), or null.
export function currentShape(v, side) {
  for (const id of SHAPE_ORDER) {
    const qs = shapeQuats(v, side, id);
    let ok = true;
    for (const [name, q] of Object.entries(qs)) {
      const b = v.bone(name);
      if (b && b.quaternion.angleTo(q) > THREE.MathUtils.degToRad(6)) { ok = false; break; }
    }
    if (ok) return id;
  }
  return null;
}

// A small drawing of a shape (for its button), palm toward you: each finger as long as it looks from the front (a
// curled finger folds away and looks short), the thumb swings across the palm as it folds. 28 x 28.
export function shapeIcon(id) {
  const sh = HAND_SHAPES[id];
  if (!sh) return '';
  const RAD1 = Math.PI / 180;
  const base = { Index: 10.2, Mid: 13.6, Ring: 17, Pinky: 20.2 }, len = { Index: 9.4, Mid: 10.4, Ring: 9.6, Pinky: 7.6 };
  const seg = [0.45, 0.3, 0.25];
  const parts = [];
  for (const f of CURLED) {
    const rv = sh.rv[f] || [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    let a = 0, up = 0;
    rv.forEach((j, k) => { a += j[2] * RAD1; up += len[f] * seg[k] * Math.cos(a); });
    const fan = (rv[0][1] || 0) * -0.09;            // spread leans the finger sideways
    const x0 = base[f], y0 = 14.2;
    if (up > 1.2) parts.push(`<path d="M${x0} ${y0} L${(x0 + fan).toFixed(1)} ${(y0 - up).toFixed(1)}"/>`);
    else parts.push(`<circle cx="${x0}" cy="${(y0 + 1.2).toFixed(1)}" r="1.25" fill="currentColor" stroke="none"/>`);
  }
  const t = sh.rv.Thumb || [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const fold = Math.max(0, Math.min(1, (t[0][0] + t[0][1] + t[1][2] + t[2][2]) / 120));
  const ang = (-150 + fold * 95) * RAD1, tl = 7.5 - fold * 2.5;
  parts.push(`<path d="M8.4 19.5 L${(8.4 + Math.cos(ang) * tl).toFixed(1)} ${(19.5 + Math.sin(ang) * tl).toFixed(1)}"/>`);
  return '<svg viewBox="0 0 28 28" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="M8.6 14.6 Q8 25.5 14.6 25.6 Q21.6 25.6 21.6 15.2 Z" fill="currentColor" fill-opacity=".2" stroke-width="1.3"/>' + parts.join('') + '</svg>';
}

// Landmarks -> the game rig's bone rotations (capture.md section 5). Two building blocks, both checked on the real
// rig: (B) frame match - a recipe gives two directions from the landmarks, the same recipe on the rig at rest gives
// two more, and the bone turns from one frame to the other (no axis tables); (A) aim with bend plane - for a bone
// whose child is a hinge (upper arm, thigh, thumb base): it points at the middle joint, and the hinge bends by the
// angle between the two segments, about its own Z axis only.
// Stage order per frame: facing turn -> pelvis -> spine -> clavicles -> neck/head -> arms -> hands -> fingers -> legs
// -> feet -> limits -> hips place -> floor and sticky feet. Twist bones are left to the app's own twist stage (they
// are never keyed).
import * as THREE from 'three';
import { RigPose, landmarks, PL, PL_MIRROR, FINGERS, lowestSkin } from './rigpose.js';
import { HINGE, POSABLE, PENIS, HIPS } from '../bones.js';
import { setSpaceQuat, spaceQuat, solveTwoBone } from '../posemath.js';
import { zeroLag, oneEuroSeries, FILTERS, LIMBS, unflip, smoothScale, scaled } from './clean.js';

const deg = THREE.MathUtils.degToRad, rad2deg = THREE.MathUtils.radToDeg;
const UP = new THREE.Vector3(0, 1, 0);
const n = v => v.clone().normalize();
const mid = (a, b) => a.clone().add(b).multiplyScalar(0.5);
const smoothstep = (a, b, x) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

// the rotation whose columns are e1 = a, e2 = b made perpendicular to a, e3 = e1 x e2
const _m = new THREE.Matrix4();
export function basis(a, b, target = new THREE.Quaternion()) {
  const e1 = n(a);
  const e2 = b.clone().sub(e1.clone().multiplyScalar(b.dot(e1)));
  if (e2.lengthSq() < 1e-12) e2.set(0, 1, 0).sub(e1.clone().multiplyScalar(e1.y));
  e2.normalize();
  const e3 = e1.clone().cross(e2);
  _m.makeBasis(e1, e2, e3);
  return target.setFromRotationMatrix(_m);
}
// the same with the first direction as the "up" column (b primary, a made perpendicular): used for the chest, whose
// up comes from the whole torso and whose shoulder line may shrug
function basisUp(a, b, target) { return basis(b, a, target); }

// Bones the solver sets, parents first.
const SIDE = ['L', 'R'];
export const SOLVED = ['b__Pelvis__', 'b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__L_Clavicle__', 'b__R_Clavicle__', 'b__Neck__', 'b__Head__'];
for (const s of SIDE) {
  SOLVED.push(`b__${s}_UpperArm__`, `b__${s}_Forearm__`, `b__${s}_Hand__`);
  for (const f of FINGERS) for (let j = 0; j < 3; j++) SOLVED.push(`b__${s}_${f}${j}__`);
  SOLVED.push(`b__${s}_Thigh__`, `b__${s}_Calf__`, `b__${s}_Foot__`, `b__${s}_Toe__`);
}
const LIMB_BONES = { head: ['b__Neck__', 'b__Head__'] };
for (const s of SIDE) {
  LIMB_BONES['arm' + s] = [`b__${s}_UpperArm__`, `b__${s}_Forearm__`, `b__${s}_Hand__`, ...FINGERS.flatMap(f => [0, 1, 2].map(j => `b__${s}_${f}${j}__`))];
  LIMB_BONES['leg' + s] = [`b__${s}_Thigh__`, `b__${s}_Calf__`, `b__${s}_Foot__`, `b__${s}_Toe__`];
}
export const FINGER_BONES = new Set(SIDE.flatMap(s => FINGERS.flatMap(f => [0, 1, 2].map(j => `b__${s}_${f}${j}__`))));

// MediaPipe world axes -> sim space: x stays, y flips to up, z flips so "toward the camera" = the sim's forward.
const toSim = (x, y, z) => new THREE.Vector3(x, -y, -z);

// ---------------------------------------------------------------- the solver
export class Solver {
  constructor(rig) {
    this.rp = rig instanceof RigPose ? rig : new RigPose(rig);
    const rp = this.rp;
    const L = rp.restLm;
    this.rest = { pose: L.pose, hands: L.hands };
    this.restSpace = name => rp.restQuat(name);
    // rest frames of the (B) recipes
    this.R = {};
    const rb = (name, a, b, up = false) => { this.R[name] = (up ? basisUp(a, b, new THREE.Quaternion()) : basis(a, b)).invert(); };
    const p = L.pose;
    const midHip0 = mid(p[PL.hipL], p[PL.hipR]), midSh0 = mid(p[PL.shL], p[PL.shR]), midKn0 = mid(p[PL.knL], p[PL.knR]);
    this.torso0 = midSh0.clone().sub(midHip0);
    rb('b__Pelvis__', p[PL.hipL].clone().sub(p[PL.hipR]), n(midSh0.clone().sub(midHip0)).multiplyScalar(0.65).add(n(midHip0.clone().sub(midKn0)).multiplyScalar(0.35)));
    rb('b__Spine2__', p[PL.shL].clone().sub(p[PL.shR]), midSh0.clone().sub(midHip0), true);
    rb('b__Head__', p[PL.earL].clone().sub(p[PL.earR]), mid(p[PL.eyeL], p[PL.eyeR]).sub(mid(p[PL.mouthL], p[PL.mouthR])));
    for (const s of SIDE) {
      const o = s === 'L' ? 0 : 1, H = L.hands[s];
      rb(`b__${s}_Foot__`, p[PL.toeL + o].clone().sub(p[PL.heelL + o]), p[PL.anL + o].clone().sub(p[PL.heelL + o]));
      rb(`b__${s}_Hand__`, H[9].clone().sub(H[0]), H[5].clone().sub(H[17]));
      rb(`b__${s}_Hand__pose`, mid(p[PL.indexL + o], p[PL.pinkyL + o]).sub(p[PL.wrL + o]), p[PL.indexL + o].clone().sub(p[PL.pinkyL + o]));
      for (const [f, base] of [['Index', 5], ['Mid', 9], ['Ring', 13], ['Pinky', 17]]) rb(`b__${s}_${f}0__`, H[base + 1].clone().sub(H[base]), H[5].clone().sub(H[17]));
      // the clavicle's rest direction (from a point on the breastbone to the shoulder)
      this[`clav${s}`] = p[PL.shL + o].clone().sub(midSh0.clone().sub(n(this.torso0).multiplyScalar(0.04))).normalize();
    }
    this.legLen = p[PL.shL].distanceTo(p[PL.hipL]) + p[PL.hipL].distanceTo(p[PL.knL]) + p[PL.knL].distanceTo(p[PL.anL]);
    this.torsoRest = this.torso0.length();
  }

  // Sim-space landmarks of frame i: {pose: [33 Vector3], vis: [33], hands: {L, R} | null each}
  points(take, person, i, { mirror = false, psi = 0 } = {}) {
    const pe = take.people[person], po = pe.pose;
    const rot = new THREE.Quaternion().setFromAxisAngle(UP, psi);
    const pose = new Array(33), vis = new Float32Array(33);
    for (let j = 0; j < 33; j++) {
      const src = mirror ? PL_MIRROR[j] : j, k = (i * 33 + src) * 4;
      const v = toSim(po[k], po[k + 1], po[k + 2]);
      if (mirror) v.x = -v.x;
      pose[j] = v.applyQuaternion(rot);
      vis[j] = po[k + 3];
    }
    const hands = { L: null, R: null };
    if (pe.hand) for (const s of SIDE) {
      const src = mirror ? (s === 'L' ? 'R' : 'L') : s;
      const arr = pe.hand[src], ok = pe.hand[src + 'ok'];
      if (!arr || !ok || !ok[i]) continue;
      const h = new Array(21);
      for (let j = 0; j < 21; j++) {
        const k = (i * 21 + j) * 3, v = toSim(arr[k], arr[k + 1], arr[k + 2]);
        if (mirror) v.x = -v.x;
        h[j] = v.applyQuaternion(rot);
      }
      hands[s] = h;
    }
    return { pose, vis, hands };
  }

  // The captured body's facing (turn about the vertical), from the hips' side-to-side line: works standing and lying.
  static yawOf(left) { return Math.atan2(-left.z, left.x); }

  setSpace(name, q) { const b = this.rp.bone(name); if (b) setSpaceQuat(this.rp, b, q); }
  space(name) { return spaceQuat(this.rp, this.rp.bone(name)); }
  D(name) { return this.space(name).multiply(this.restSpace(name).clone().invert()); }

  // (A) aim with bend plane: parent points j0 -> j1, the hinge child bends by the angle to j1 -> j2.
  aim(parent, child, j0, j1, j2, grand, maxBend) {
    const s = HINGE[child];
    const X = n(j1.clone().sub(j0)), d = n(j2.clone().sub(j1));
    const perp = d.clone().sub(X.clone().multiplyScalar(d.dot(X)));
    let theta = Math.atan2(perp.length(), d.dot(X));
    // near-straight limbs: the bend side is noise; lean on the rest side carried by the grandparent's turn
    const Dg = this.D(grand);
    const hint = new THREE.Vector3(0, 1, 0).applyQuaternion(this.restSpace(parent)).applyQuaternion(Dg);
    hint.sub(X.clone().multiplyScalar(hint.dot(X))).normalize();
    let Y;
    if (perp.lengthSq() < 1e-12) Y = hint.clone();
    else {
      const meas = perp.normalize().multiplyScalar(s);
      if (theta < deg(35) && meas.dot(hint) < -0.3) { Y = hint.clone(); theta = 0; }
      else {
        const w = smoothstep(deg(8), deg(25), theta);
        Y = meas.multiplyScalar(w).add(hint.clone().multiplyScalar(1 - w));
        Y.sub(X.clone().multiplyScalar(Y.dot(X)));
        if (Y.lengthSq() < 1e-12) Y = hint.clone();
        Y.normalize();
      }
    }
    const Z = X.clone().cross(Y);
    this.setSpace(parent, new THREE.Quaternion().setFromRotationMatrix(_m.makeBasis(X, Y, Z)));
    theta = Math.min(theta, deg(maxBend));
    this.rp.bone(child).quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), s * theta);
  }

  // hinge from two consecutive segment directions, about the parent's own Z axis
  hinge(child, parent, u, v, lo, hi) {
    const Zp = new THREE.Vector3(0, 0, 1).applyQuaternion(this.space(parent));
    const th = Math.atan2(u.clone().cross(v).dot(Zp), u.dot(v));
    this.rp.bone(child).quaternion.setFromAxisAngle(new THREE.Vector3(0, 0, 1), THREE.MathUtils.clamp(th, deg(lo), deg(hi)));
  }

  frameMatch(name, a, b, key = name, up = false) {
    const q = (up ? basisUp(a, b, new THREE.Quaternion()) : basis(a, b)).multiply(this.R[key]).multiply(this.restSpace(name));
    this.setSpace(name, q);
    return q;
  }

  // Limit a bone's turn relative to its parent's carried rest (degrees about the parent-carried sim axes).
  limitRelative(name, parentName, { yaw = 180, pitchDown = 180, pitchUp = 180, roll = 180, total = 180 } = {}) {
    const Dp = this.D(parentName), Db = this.D(name);
    const rel = Dp.clone().invert().multiply(Db);
    const e = new THREE.Euler().setFromQuaternion(rel, 'YXZ');
    let changed = false;
    const clamp = (v, lo, hi) => { const c = Math.max(lo, Math.min(hi, v)); if (c !== v) changed = true; return c; };
    e.y = clamp(e.y, -deg(yaw), deg(yaw));
    e.x = clamp(e.x, -deg(pitchUp), deg(pitchDown));
    e.z = clamp(e.z, -deg(roll), deg(roll));
    let q = new THREE.Quaternion().setFromEuler(e);
    const ang = 2 * Math.acos(Math.min(1, Math.abs(q.w)));
    if (ang > deg(total)) { q = new THREE.Quaternion().slerp(q, deg(total) / ang); changed = true; }
    if (changed) this.setSpace(name, Dp.multiply(q).multiply(this.restSpace(name)));
  }

  // Limit how far a bone swings away from its rest direction (its turn about its own length - a wrist's roll - is
  // left alone; the app's twist stage shares that with the forearm).
  limitSwing(name, maxDeg) {
    const b = this.rp.bone(name), k = this.rp.index(name);
    const rest = this.rp.rest[k].quat;
    const r = rest.clone().invert().multiply(b.quaternion);
    const twist = new THREE.Quaternion(r.x, 0, 0, r.w);
    if (twist.lengthSq() < 1e-12) twist.set(0, 0, 0, 1); else twist.normalize();
    const swing = r.clone().multiply(twist.clone().invert());
    const ang = 2 * Math.acos(Math.min(1, Math.abs(swing.w)));
    if (ang <= deg(maxDeg)) return;
    const lim = new THREE.Quaternion().slerp(swing.w < 0 ? new THREE.Quaternion(-swing.x, -swing.y, -swing.z, -swing.w) : swing, deg(maxDeg) / ang);
    b.quaternion.copy(rest).multiply(lim).multiply(twist);
  }

  // Solve one frame's rotations on the RigPose (hips place untouched). opts: {hands, fingers, headFrom: Quaternion|null, limits}
  solveRotations(pts, { hands = true, fingers = true, headD = null, limits = true, torsoRef = null } = {}) {
    const rp = this.rp, p = pts.pose, vis = pts.vis;
    // keep what the stage before set for bones not solved (the caller resets the pose)
    const midHip = mid(p[PL.hipL], p[PL.hipR]), midSh = mid(p[PL.shL], p[PL.shR]), midKn = mid(p[PL.knL], p[PL.knR]);
    const torsoUp = midSh.clone().sub(midHip);
    // pelvis: its tilt is shared between the torso and the thighs (hips can't show their own tilt)
    const kneesOk = vis[PL.knL] >= 0.5 && vis[PL.knR] >= 0.5;
    const legsUp = midHip.clone().sub(midKn);
    const upP = kneesOk ? n(torsoUp).multiplyScalar(0.65).add(n(legsUp).multiplyScalar(0.35)) : n(torsoUp);
    if (!kneesOk) this.R.b__Pelvis__noknees = this.R.b__Pelvis__noknees || basis(this.rest.pose[PL.hipL].clone().sub(this.rest.pose[PL.hipR]), this.torso0).invert();
    this.frameMatch('b__Pelvis__', p[PL.hipL].clone().sub(p[PL.hipR]), upP, kneesOk ? 'b__Pelvis__' : 'b__Pelvis__noknees');
    // chest from the whole torso (up) and the shoulder line (turn); the spine shares the bend between them
    const Dpel = this.D('b__Pelvis__');
    const qChest = basisUp(p[PL.shL].clone().sub(p[PL.shR]), torsoUp, new THREE.Quaternion()).multiply(this.R.b__Spine2__);
    const Dchest = qChest.clone();
    // the spine shares the bend between the hips and the chest (a third, two thirds), and then leans as a whole so
    // the shoulders sit where the landmarks put them (seen from the hips) - the hips can't show their own tilt, so
    // this keeps a wrong pelvis guess from moving the shoulders, arms and head
    const S0 = rp.index('b__Spine0__'), SL = rp.index('b__L_UpperArm__'), SR = rp.index('b__R_UpperArm__'), TL = rp.index('b__L_Thigh__'), TR = rp.index('b__R_Thigh__');
    const upDir = n(torsoUp);
    let lean = new THREE.Quaternion();
    for (let it = 0; it < 4; it++) {
      this.setSpace('b__Spine0__', lean.clone().multiply(Dpel.clone().slerp(Dchest, 0.33)).multiply(this.restSpace('b__Spine0__')));
      this.setSpace('b__Spine1__', lean.clone().multiply(Dpel.clone().slerp(Dchest, 0.66)).multiply(this.restSpace('b__Spine1__')));
      this.setSpace('b__Spine2__', Dchest.clone().multiply(this.restSpace('b__Spine2__')));
      rp.fk();
      const hipC = rp.P[TL].clone().add(rp.P[TR]).multiplyScalar(0.5), shC = rp.P[SL].clone().add(rp.P[SR]).multiplyScalar(0.5);
      const s0 = rp.P[S0];
      const target = hipC.clone().add(upDir.clone().multiplyScalar(shC.distanceTo(hipC)));
      const cur = n(shC.clone().sub(s0)), want = n(target.sub(s0));
      if (cur.dot(want) > 0.99999) break;
      lean = new THREE.Quaternion().setFromUnitVectors(cur, want).multiply(lean);
    }
    // clavicles: raising an arm past about 30 degrees lifts the shoulder too (the shoulder blade turns about a third
    // of the rest - the "shoulder rhythm"), so the clavicle follows the arm's lift; this keeps working for any body
    // size, where comparing shoulder heights would mistake a long torso for a shrug
    for (const s of SIDE) {
      const o = s === 'L' ? 0 : 1;
      const armDir = n(p[PL.elL + o].clone().sub(p[PL.shL + o]));
      const lift = Math.acos(THREE.MathUtils.clamp(armDir.dot(upDir.clone().negate()), -1, 1));
      const e = Math.min(deg(35), 0.33 * Math.max(0, lift - deg(30)));
      const clavDir = this[`clav${s}`].clone().applyQuaternion(Dchest);
      const axis = clavDir.clone().cross(upDir);
      const sw = axis.lengthSq() > 1e-9 && e > 0 ? new THREE.Quaternion().setFromAxisAngle(axis.normalize(), e) : new THREE.Quaternion();
      this.setSpace(`b__${s}_Clavicle__`, sw.multiply(Dchest).multiply(this.restSpace(`b__${s}_Clavicle__`)));
    }
    // head: from the face's own turn when there is one, else from the ears / eyes / mouth corners
    let Dhead;
    if (headD) Dhead = headD.clone();
    else Dhead = basis(p[PL.earL].clone().sub(p[PL.earR]), mid(p[PL.eyeL], p[PL.eyeR]).sub(mid(p[PL.mouthL], p[PL.mouthR]))).multiply(this.R.b__Head__);
    this.setSpace('b__Neck__', Dchest.clone().slerp(Dhead, 0.5).multiply(this.restSpace('b__Neck__')));
    this.setSpace('b__Head__', Dhead.clone().multiply(this.restSpace('b__Head__')));
    if (limits) this.limitRelative('b__Head__', 'b__Spine2__', { yaw: 80, pitchDown: 60, pitchUp: 50, roll: 40 });
    // arms, hands, fingers
    for (const s of SIDE) {
      const o = s === 'L' ? 0 : 1;
      this.aim(`b__${s}_UpperArm__`, `b__${s}_Forearm__`, p[PL.shL + o], p[PL.elL + o], p[PL.wrL + o], `b__${s}_Clavicle__`, limits ? 150 : 179);
      const H = hands && pts.hands[s];
      if (H) this.frameMatch(`b__${s}_Hand__`, H[9].clone().sub(H[0]), H[5].clone().sub(H[17]));
      else this.frameMatch(`b__${s}_Hand__`, mid(p[PL.indexL + o], p[PL.pinkyL + o]).sub(p[PL.wrL + o]), p[PL.indexL + o].clone().sub(p[PL.pinkyL + o]), `b__${s}_Hand__pose`);
      if (limits) this.limitSwing(`b__${s}_Hand__`, 85);
      if (H && fingers) {
        for (const [f, b0] of [['Index', 5], ['Mid', 9], ['Ring', 13], ['Pinky', 17]]) {
          this.frameMatch(`b__${s}_${f}0__`, H[b0 + 1].clone().sub(H[b0]), H[5].clone().sub(H[17]));
          if (limits) this.limitSwing(`b__${s}_${f}0__`, 95);
          const seg = k => n(H[b0 + k + 1].clone().sub(H[b0 + k]));
          this.hinge(`b__${s}_${f}1__`, `b__${s}_${f}0__`, seg(0), seg(1), limits ? -5 : -179, limits ? 105 : 179);
          this.hinge(`b__${s}_${f}2__`, `b__${s}_${f}1__`, seg(1), seg(2), limits ? -5 : -179, limits ? 80 : 179);
        }
        this.aim(`b__${s}_Thumb0__`, `b__${s}_Thumb1__`, H[1], H[2], H[3], `b__${s}_Hand__`, limits ? 70 : 179);
        this.hinge(`b__${s}_Thumb2__`, `b__${s}_Thumb1__`, n(H[3].clone().sub(H[2])), n(H[4].clone().sub(H[3])), limits ? -5 : -179, limits ? 80 : 179);
      }
    }
    // legs and feet
    for (const s of SIDE) {
      const o = s === 'L' ? 0 : 1;
      this.aim(`b__${s}_Thigh__`, `b__${s}_Calf__`, p[PL.hipL + o], p[PL.knL + o], p[PL.anL + o], 'b__Pelvis__', limits ? 155 : 179);
      this.frameMatch(`b__${s}_Foot__`, p[PL.toeL + o].clone().sub(p[PL.heelL + o]), p[PL.anL + o].clone().sub(p[PL.heelL + o]));
      if (limits) this.limitSwing(`b__${s}_Foot__`, 70);
    }
    return rp;
  }
}

// ---------------------------------------------------------------- hips place from the camera (5.5)
// Least squares over the confident limb and torso points: where the hip centre is relative to the camera.
const PLACE_PTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];
export function cameraPlace(take, person, i, fovDeg = 60) {
  const pe = take.people[person];
  const W = take.width || 1280, Hh = take.height || 720;
  const f = Math.max(W, Hh) / (2 * Math.tan(deg(fovDeg) / 2));
  // normal equations for t = (tx, ty, tz): rows [1, 0, -a | a*Z - X] and [0, 1, -b | b*Z - Y]
  const A = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], r = [0, 0, 0];
  let used = 0;
  for (const j of PLACE_PTS) {
    const k4 = (i * 33 + j) * 4, k3 = (i * 33 + j) * 3;
    const v = pe.pose[k4 + 3];
    if (v < 0.5) continue;
    const w = v * v;
    const X = pe.pose[k4], Y = pe.pose[k4 + 1], Z = pe.pose[k4 + 2];
    const a = (pe.img[k3] * W - W / 2) / f, b = (pe.img[k3 + 1] * Hh - Hh / 2) / f;
    for (const [row, rhs] of [[[1, 0, -a], a * Z - X], [[0, 1, -b], b * Z - Y]]) {
      for (let p = 0; p < 3; p++) { for (let q = 0; q < 3; q++) A[p][q] += w * row[p] * row[q]; r[p] += w * row[p] * rhs; }
    }
    used++;
  }
  if (used < 4) return null;
  const m = new THREE.Matrix3().set(A[0][0], A[0][1], A[0][2], A[1][0], A[1][1], A[1][2], A[2][0], A[2][1], A[2][2]);
  if (Math.abs(m.determinant()) < 1e-12) return null;
  const t = new THREE.Vector3(r[0], r[1], r[2]).applyMatrix3(m.invert());
  return t.z > 0.2 ? t : null;
}

// ---------------------------------------------------------------- a whole take
// solveTake(take, person, rig, opts) -> { poses: [{rot, pos}], quality: Float32Array, contacts, low, psi }
// opts: { facing: yaw of the sim now (radians), base: the sim's keyed pose now {rot, pos} (its hips place),
//         basePoses: (f) => the sim's own pose at frame f (long gaps ease to it), floorY: null = where the sim is now,
//         ground: 'floor' | 'free' | 'lowest', stay: true, mirror: false, hands: true, fingers: true, headFromFace: true,
//         fov: 60, limits: true, stick: true, places: null }
// places: (take, person, i) -> the hips' place in frame i (MediaPipe axes, like cameraPlace), for takes that know it
// (a motion file, capture/bvh.js); smoothPlace: false keeps that place unfiltered; ground 'lowest': the lowest the
// body gets over the whole take is on the floor (jumps and lying down keep their height).
export function solveTake(take, person, rig, opts = {}) {
  const o = { facing: 0, base: null, basePoses: null, floorY: null, ground: 'floor', stay: true, mirror: false, hands: true, fingers: true,
    headFromFace: true, fov: 60, limits: true, stick: true, smooth: 0.5, smoothRot: true, ...opts };
  const solver = rig instanceof Solver ? rig : new Solver(rig);
  const rp = solver.rp;
  const pe = take.people[person];
  const N = take.t.length;
  // facing: at the first confident frame, turn the capture so it faces the way the sim faces now
  let psi = 0;
  for (let i = 0; i < N && o.psi === undefined; i++) {
    const pts = solver.points(take, person, i, { mirror: o.mirror });
    if (pts.vis[PL.hipL] >= 0.5 && pts.vis[PL.hipR] >= 0.5) { psi = o.facing - Solver.yawOf(pts.pose[PL.hipL].clone().sub(pts.pose[PL.hipR])); break; }
  }
  if (o.psi !== undefined) psi = o.psi;
  const rotY = new THREE.Quaternion().setFromAxisAngle(UP, psi);
  // the head from the face's own turn (it is much steadier), in frames where the face was found
  const face = o.headFromFace && pe.face;
  const headD = i => {
    if (!face || !face.ok[i]) return null;
    const m = face.m.subarray(i * 16, i * 16 + 16);
    const M = new THREE.Matrix4().fromArray(m);
    const q = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().extractRotation(M)).normalize();
    if (o.mirror) { q.y = -q.y; q.z = -q.z; }
    return rotY.clone().multiply(q);
  };
  // the take's typical torso length (hips to shoulders), so shoulders are lifted only by real shrugs and raised arms
  const tl = [];
  for (let i = 0; i < N; i++) {
    const pts = solver.points(take, person, i, {});
    if ([PL.shL, PL.shR, PL.hipL, PL.hipR].every(j => pts.vis[j] >= 0.5)) tl.push(mid(pts.pose[PL.shL], pts.pose[PL.shR]).distanceTo(mid(pts.pose[PL.hipL], pts.pose[PL.hipR])));
  }
  tl.sort((a, b) => a - b);
  const torsoRef = o.torsoRef || (tl.length ? tl[tl.length >> 1] : null);
  // 1. rotations, frame by frame
  const base = o.base || null;
  const poses = new Array(N);
  const hipsBase = HIPS.map(h => new THREE.Vector3().fromArray((base && base.pos && base.pos[h]) || rp.rest[rp.index(h)].pos.toArray()));
  const places = new Array(N);
  for (let i = 0; i < N; i++) {
    const pts = solver.points(take, person, i, { mirror: o.mirror, psi });
    rp.resetPose();
    HIPS.forEach((h, k) => rp.bone(h).position.copy(hipsBase[k]));
    solver.solveRotations(pts, { hands: o.hands, fingers: o.fingers, headD: headD(i), limits: o.limits, torsoRef });
    const rot = {};
    for (const b of SOLVED) { const x = rp.bone(b); if (x) rot[b] = x.quaternion.toArray(); }
    poses[i] = { rot, pos: {} };
    places[i] = typeof o.places === 'function' ? o.places(take, person, i) : cameraPlace(take, person, i, o.fov);
  }
  // quaternion sign continuity per bone, then a light zero-lag smoothing of the turns themselves
  for (const b of SOLVED) unflip(poses.map(p => p.rot[b]));
  if (N > 3 && o.smoothRot !== false) {
    const params = scaled(FILTERS.rot, smoothScale(o.smooth ?? 0.5));
    const xs = new Float64Array(N);
    for (const b of SOLVED) {
      if (!poses[0].rot[b]) continue;
      const ch = [0, 1, 2, 3].map(c => { for (let i = 0; i < N; i++) xs[i] = poses[i].rot[b][c]; return zeroLag(xs, take.t, params); });
      for (let i = 0; i < N; i++) {
        const q = [ch[0][i], ch[1][i], ch[2][i], ch[3][i]], l = Math.hypot(...q) || 1;
        poses[i].rot[b] = q.map(x => x / l);
      }
    }
  }
  // 2. long gaps: that limb eases (8 frames) to the sim's own pose
  if (pe.miss && o.basePoses) {
    for (const [limb, flags] of Object.entries(pe.miss)) {
      const bones = LIMB_BONES[limb];
      if (!bones) continue;
      const w = gapWeights(flags, 8);
      for (let i = 0; i < N; i++) {
        if (w[i] <= 0) continue;
        const bp = o.basePoses(i);
        for (const b of bones) {
          const target = (bp && bp.rot && bp.rot[b]) || rp.rest[rp.index(b)].quat.toArray();
          const q = new THREE.Quaternion().fromArray(poses[i].rot[b]).slerp(new THREE.Quaternion().fromArray(target), w[i]);
          poses[i].rot[b] = q.toArray();
        }
      }
    }
  }
  // 3. the hips' place: camera estimate relative to the first frame, scaled to the sim, turned like the body
  let perfLen = [];
  for (let i = 0; i < N; i++) {
    const pts = solver.points(take, person, i, {});
    const v = pts.vis;
    if ([PL.shL, PL.hipL, PL.knL, PL.anL].every(j => v[j] >= 0.5)) {
      const p = pts.pose;
      perfLen.push(p[PL.shL].distanceTo(p[PL.hipL]) + p[PL.hipL].distanceTo(p[PL.knL]) + p[PL.knL].distanceTo(p[PL.anL]));
    }
  }
  perfLen.sort((a, b) => a - b);
  const scale = perfLen.length ? solver.legLen / perfLen[perfLen.length >> 1] : 1;
  const T = new Array(N);
  let first = null;
  for (let i = 0; i < N; i++) if (places[i]) { first = places[i]; break; }
  for (let i = 0; i < N; i++) {
    const t = places[i] || (i > 0 ? null : first);
    T[i] = t && first ? toSim(t.x - first.x, t.y - first.y, t.z - first.z).multiplyScalar(scale).applyQuaternion(rotY) : null;
  }
  for (let i = 0; i < N; i++) if (!T[i]) T[i] = i > 0 ? T[i - 1].clone() : new THREE.Vector3();
  if (N > 2 && o.smoothPlace !== false) {
    const ts = take.t;
    const ch = (sel, params) => { const xs = Float64Array.from(T, sel); return zeroLag(xs, ts, params); };
    const X = ch(v => v.x, FILTERS.body), Y = ch(v => v.y, FILTERS.body), Z = ch(v => v.z, FILTERS.depth);
    for (let i = 0; i < N; i++) T[i].set(X[i], Y[i], Z[i]);
  }
  // "Stay in place": remove the slow drift (2 s moving average), keep thrusts, sways and bounces
  if (o.stay && N > 2) {
    const win = Math.round(1 * 30);
    const avg = T.map((_, i) => {
      const a = Math.max(0, i - win), b = Math.min(N - 1, i + win);
      const s = new THREE.Vector3();
      for (let k = a; k <= b; k++) s.add(T[k]);
      return s.multiplyScalar(1 / (b - a + 1));
    });
    const t0 = T[0].clone();
    for (let i = 0; i < N; i++) { T[i].x = T[i].x - avg[i].x + t0.x; T[i].z = T[i].z - avg[i].z + t0.z; }
  }
  // 4. floor: the lowest skin point sits at floorY (where the sim is now, or 0)
  let floorY = o.floorY;
  if (floorY === null || floorY === undefined) {
    if (base) { rp.resetPose(); rp.setPose(base); rp.fk(); floorY = Math.max(0, lowestSkin(rp)); } else floorY = 0;
  }
  const lows = new Float64Array(N);
  const hipsAt = i => {
    const d = T[i];
    // ROOT_bind's rest turns local x -> up, y -> forward, z -> left
    return hipsBase.map(h => h.clone().add(new THREE.Vector3(d.y, d.z, d.x)));
  };
  for (let i = 0; i < N; i++) {
    rp.resetPose(); rp.setPose(poses[i]);
    const hp = hipsAt(i);
    HIPS.forEach((h, k) => rp.bone(h).position.copy(hp[k]));
    rp.fk();
    lows[i] = lowestSkin(rp);
  }
  const off = new Float64Array(N);
  const lowest = o.ground === 'lowest' ? lows.reduce((a, b) => Math.min(a, b), Infinity) : 0;
  for (let i = 0; i < N; i++) off[i] = o.ground === 'free' ? floorY - lows[0] : o.ground === 'lowest' ? floorY - lowest : floorY - lows[i];
  const offS = N > 3 && o.ground !== 'free' && o.ground !== 'lowest' ? zeroLag(off, take.t, { minCutoff: 1.5, beta: 0.5, dCutoff: 1 }) : off;
  for (let i = 0; i < N; i++) {
    const hp = hipsAt(i);
    const dy = offS[i];
    HIPS.forEach((h, k) => { poses[i].pos[h] = [hp[k].x + dy, hp[k].y, hp[k].z]; });
  }
  // 5. sticky feet: where a foot rests on the floor, its ankle holds still (no "ice skating")
  const contacts = o.stick && N > 4 ? stickFeet(rp, poses, take.t, floorY) : [];
  return { poses, quality: pe.quality || new Float32Array(N).fill(1), contacts, psi, scale, floorY };
}

// weights 0..1 over the frames of a flag track (1 inside flagged spans, eased over `ease` frames at both ends)
function gapWeights(flags, ease) {
  const N = flags.length, w = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    if (flags[i]) { w[i] = 1; continue; }
    let d = Infinity;
    for (let k = 1; k <= ease; k++) if ((i - k >= 0 && flags[i - k]) || (i + k < N && flags[i + k])) { d = k; break; }
    w[i] = d === Infinity ? 0 : 1 - smoothstep(0, ease + 1, d);
  }
  return w;
}

// Feet that rest on the floor (heel, ankle or toe within 2.5 cm of the floor, moving < 0.25 m/s, for 6+ frames)
// keep their ankle at the span's average place (two-bone solve, the knee pushed forward), blended in and out smoothly.
function stickFeet(rp, poses, ts, floorY) {
  const N = poses.length, spans = [];
  for (const s of SIDE) {
    const ank = [], low = [];
    for (let i = 0; i < N; i++) {
      rp.resetPose(); rp.setPose(poses[i]); rp.fk();
      const a = rp.pos(`b__${s}_Foot__`).clone();
      ank.push(a);
      const heel = rp.rigidPoint(`b__${s}_Foot__`, new THREE.Vector3(rp.restPos(`b__${s}_Foot__`).x, 0, rp.restPos(`b__${s}_Foot__`).z - 0.07));
      low.push(Math.min(a.y - 0.03, heel.y, rp.pos(`b__${s}_Toe__`).y));
    }
    const still = ank.map((a, i) => {
      const j = Math.min(N - 1, i + 1), k = Math.max(0, i - 1);
      const dt = Math.max(1e-3, ts[j] - ts[k]);
      const sp = Math.hypot(ank[j].x - ank[k].x, ank[j].z - ank[k].z) / dt;
      return low[i] - floorY < 0.025 && sp < 0.25;
    });
    let i = 0;
    while (i < N) {
      if (!still[i]) { i++; continue; }
      let e = i;
      while (e < N && still[e]) e++;
      // planted: at least 6 frames, and the ankle wanders less than 6 cm over them (a swinging foot that only
      // slows down near the floor is not planted)
      if (e - i >= 6) {
        let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
        for (let k = i; k < e; k++) { x0 = Math.min(x0, ank[k].x); x1 = Math.max(x1, ank[k].x); z0 = Math.min(z0, ank[k].z); z1 = Math.max(z1, ank[k].z); }
        if (Math.hypot(x1 - x0, z1 - z0) < 0.06) spans.push({ side: s, from: i, to: e - 1 });
      }
      i = e;
    }
  }
  const Z = new THREE.Vector3(0, 0, 1);
  const EASE = 6;                                   // frames to blend in and out (smoothly, so the knee never pops)
  const kept = [];
  for (const sp of spans) {
    const s = sp.side, thigh = `b__${s}_Thigh__`, calf = `b__${s}_Calf__`, foot = `b__${s}_Foot__`;
    const target = new THREE.Vector3(), pts = [];
    for (let i = sp.from; i <= sp.to; i++) { rp.resetPose(); rp.setPose(poses[i]); rp.fk(); pts.push(rp.pos(foot).clone()); target.add(pts[pts.length - 1]); }
    target.multiplyScalar(1 / pts.length);
    // a foot that already holds still (within 1 cm) needs no help
    if (Math.max(...pts.map(p => p.distanceTo(target))) < 0.01) continue;
    kept.push(sp);
    for (let i = Math.max(0, sp.from - EASE); i <= Math.min(N - 1, sp.to + EASE); i++) {
      const d = i < sp.from ? sp.from - i : i > sp.to ? i - sp.to : 0;
      const w = 1 - smoothstep(0, EASE + 1, d);
      if (w <= 0) continue;
      rp.resetPose(); rp.setPose(poses[i]); rp.fk();
      const knee = rp.pos(calf).clone();
      const fwd = Z.clone().applyQuaternion(spaceQuat(rp, rp.bone('b__Pelvis__')).multiply(rp.restQuat('b__Pelvis__').clone().invert()));
      const pole = knee.add(fwd.multiplyScalar(0.4));
      const dest = rp.pos(foot).clone().lerp(target, w);
      solveTwoBone(rp, rp.bone(thigh), rp.bone(calf), rp.bone(foot), dest, pole);
      for (const b of [thigh, calf, foot]) poses[i].rot[b] = rp.bone(b).quaternion.toArray();
    }
  }
  spans.length = 0; spans.push(...kept);
  return spans;
}

// One frame, quickly (the live preview while reading, the webcam mirror, a photo): no filtering.
export function solveOne(solver, take, person, i, opts = {}) {
  const r = solveTake({ ...take, t: take.t.subarray ? take.t.subarray(i, i + 1) : [take.t[i]], people: take.people.map(pe => sliceFrame(pe, i)) }, person, solver, { ...opts, stick: false, smoothRot: false });
  return r.poses[0];
}

export function sliceFrame(pe, i) {
  const sl = (a, w) => (a ? a.slice(i * w, (i + 1) * w) : a);
  return {
    pose: sl(pe.pose, 132), img: sl(pe.img, 99),
    hand: pe.hand ? { L: sl(pe.hand.L, 63), R: sl(pe.hand.R, 63), Lok: sl(pe.hand.Lok, 1), Rok: sl(pe.hand.Rok, 1) } : null,
    face: pe.face ? { bs: sl(pe.face.bs, 52), m: sl(pe.face.m, 16), ok: sl(pe.face.ok, 1), eyeL: sl(pe.face.eyeL, 1), eyeR: sl(pe.face.eyeR, 1) } : null,
  };
}

export { rad2deg };

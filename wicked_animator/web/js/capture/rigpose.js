// A sim's skeleton without any meshes, for motion capture: the solver poses it, the mock tracker films it. Built the
// same way Sim builds its bones (the game's rig, sim space: Y up, the sim faces +Z, its left is +X), with the same
// fields posemath.js uses (space, byName, rest, restByName), so the displayed sims are never touched.
// Also: where MediaPipe's body, hand and face points sit on this rig (the same recipe is used on the rig at rest and
// on a posed rig, so the solver needs no axis tables).
import * as THREE from 'three';

export class RigPose {
  constructor(rig) {
    this.rig = rig;
    this.space = new THREE.Object3D();
    this.bones = rig.bones.map(b => {
      const o = new THREE.Object3D();
      o.name = b.name;
      o.position.fromArray(b.pos);
      o.quaternion.fromArray(b.rot);
      o.scale.fromArray(b.scale || [1, 1, 1]);
      o.matrixAutoUpdate = false;
      return o;
    });
    this.byName = {};
    this.parents = rig.bones.map(b => b.parent);
    this.bones.forEach((o, k) => {
      this.byName[o.name] = o;
      const p = rig.bones[k].parent;
      if (p >= 0) this.bones[p].add(o); else this.space.add(o);
    });
    this.rest = this.bones.map(b => ({ pos: b.position.clone(), quat: b.quaternion.clone() }));
    this.restByName = {};
    this.bones.forEach((b, k) => { this.restByName[b.name] = this.rest[k]; });
    this._index = new Map(this.bones.map((b, k) => [b.name, k]));
    // parents always come before their children in the game's rig; keep an order that guarantees it anyway
    const depth = k => { let d = 0; for (let p = this.parents[k]; p >= 0; p = this.parents[p]) d++; return d; };
    this.order = this.bones.map((b, k) => k).sort((a, b) => depth(a) - depth(b));
    this.W = this.bones.map(() => new THREE.Quaternion());     // space rotations after fk()
    this.P = this.bones.map(() => new THREE.Vector3());        // space positions after fk()
    this.fk();
    this.restW = this.W.map(q => q.clone());
    this.restP = this.P.map(p => p.clone());
    this.restLm = landmarks(this);                             // the recipe points at rest
  }

  bone(name) { return this.byName[name]; }
  index(name) { const k = this._index.get(name); return k === undefined ? -1 : k; }

  resetPose() {
    this.bones.forEach((b, k) => { b.position.copy(this.rest[k].pos); b.quaternion.copy(this.rest[k].quat); });
  }

  setPose(pose) {
    if (!pose) return;
    for (const [n, q] of Object.entries(pose.rot || {})) { const b = this.byName[n]; if (b) b.quaternion.fromArray(q); }
    for (const [n, p] of Object.entries(pose.pos || {})) { const b = this.byName[n]; if (b) b.position.fromArray(p); }
  }

  // Space rotation and position of every bone (one pass, parents first).
  fk() {
    const W = this.W, P = this.P, tmp = new THREE.Vector3();
    for (const k of this.order) {
      const b = this.bones[k], p = this.parents[k];
      if (p < 0) { W[k].copy(b.quaternion); P[k].copy(b.position); continue; }
      W[k].copy(W[p]).multiply(b.quaternion);
      tmp.copy(b.position).multiply(this.bones[p].scale).applyQuaternion(W[p]);
      P[k].copy(P[p]).add(tmp);
    }
    return this;
  }

  pos(name) { return this.P[this.index(name)]; }
  quat(name) { return this.W[this.index(name)]; }
  restQuat(name) { return this.restW[this.index(name)]; }
  restPos(name) { return this.restP[this.index(name)]; }
  // a point fixed to a bone, given where it sits at rest (sim space)
  rigidPoint(name, restPoint, target = new THREE.Vector3()) {
    const k = this.index(name);
    const local = restPoint.clone().sub(this.restP[k]).applyQuaternion(this.restW[k].clone().invert());
    return target.copy(local).applyQuaternion(this.W[k]).add(this.P[k]);
  }
}

// ---------------------------------------------------------------- where MediaPipe's points sit on the rig
// Pose landmarks (33): odd = the person's left. Hand landmarks (21): 0 wrist, then 4 per finger (base to tip).
export const PL = {
  nose: 0, eyeInL: 1, eyeL: 2, eyeOutL: 3, eyeInR: 4, eyeR: 5, eyeOutR: 6, earL: 7, earR: 8, mouthL: 9, mouthR: 10,
  shL: 11, shR: 12, elL: 13, elR: 14, wrL: 15, wrR: 16, pinkyL: 17, pinkyR: 18, indexL: 19, indexR: 20, thumbL: 21, thumbR: 22,
  hipL: 23, hipR: 24, knL: 25, knR: 26, anL: 27, anR: 28, heelL: 29, heelR: 30, toeL: 31, toeR: 32,
};
// left <-> right partner of every pose point
export const PL_MIRROR = [0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19, 22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31];
export const FINGERS = ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'];
const TIP = 0.021;                                  // finger tips: this far past the last joint, along its bone

// Head points MediaPipe reports that the rig has no bone for: fixed to the head (where they sit at rest).
const EAR_REST = s => new THREE.Vector3(0.072 * s, 1.735, -0.015);
const heelRest = (rp, side) => { const f = rp.restPos(`b__${side}_Foot__`); return new THREE.Vector3(f.x, 0, f.z - 0.07); };

// All recipe points of a posed RigPose (after fk()), in sim space: {pose: [33 x Vector3], hands: {L, R: [21]}}.
export function landmarks(rp) {
  const pose = new Array(33);
  const P = n => rp.pos(n).clone();
  // the eyes' inner and outer corners and the ears: points fixed to the head
  const eyeRest = { L: rp.restPos('b__L_Eye__'), R: rp.restPos('b__R_Eye__') };
  const corner = (s, out) => rp.rigidPoint('b__Head__', eyeRest[s].clone().add(new THREE.Vector3((s === 'L' ? 1 : -1) * out, 0, 0)));
  pose[PL.nose] = P('b__CAS_NoseTip__');
  pose[PL.eyeL] = P('b__L_Eye__'); pose[PL.eyeR] = P('b__R_Eye__');
  pose[PL.eyeInL] = corner('L', -0.014); pose[PL.eyeOutL] = corner('L', 0.014);
  pose[PL.eyeInR] = corner('R', -0.014); pose[PL.eyeOutR] = corner('R', 0.014);
  pose[PL.earL] = rp.rigidPoint('b__Head__', EAR_REST(1));
  pose[PL.earR] = rp.rigidPoint('b__Head__', EAR_REST(-1));
  pose[PL.mouthL] = P('b__L_Mouth__'); pose[PL.mouthR] = P('b__R_Mouth__');
  const hands = {};
  for (const [s, o] of [['L', 0], ['R', 1]]) {
    pose[PL.shL + o] = P(`b__${s}_UpperArm__`);
    pose[PL.elL + o] = P(`b__${s}_Forearm__`);
    pose[PL.wrL + o] = P(`b__${s}_Hand__`);
    pose[PL.pinkyL + o] = P(`b__${s}_Pinky0__`);
    pose[PL.indexL + o] = P(`b__${s}_Index0__`);
    pose[PL.thumbL + o] = P(`b__${s}_Thumb2__`);
    pose[PL.hipL + o] = P(`b__${s}_Thigh__`);
    pose[PL.knL + o] = P(`b__${s}_Calf__`);
    pose[PL.anL + o] = P(`b__${s}_Foot__`);
    pose[PL.heelL + o] = rp.rigidPoint(`b__${s}_Foot__`, heelRest(rp, s));
    pose[PL.toeL + o] = P(`b__${s}_Toe__`);
    const hand = [P(`b__${s}_Hand__`)];
    for (const f of FINGERS) {
      for (let j = 0; j < 3; j++) hand.push(P(`b__${s}_${f}${j}__`));
      const k = rp.index(`b__${s}_${f}2__`);
      hand.push(new THREE.Vector3(TIP, 0, 0).applyQuaternion(rp.W[k]).add(rp.P[k]));
    }
    hands[s] = hand;
  }
  return { pose, hands };
}

// Skin radius around each bone's joint (for "Keep on the floor"): the lowest skin point is joint.y - radius. The toe
// joint of the game's rig already sits on the sole (0.5 mm above the floor standing), so it counts as it is.
export const SKIN_RADIUS = {};
for (const s of ['L', 'R']) {
  Object.assign(SKIN_RADIUS, {
    [`b__${s}_Thigh__`]: 0.08, [`b__${s}_Calf__`]: 0.055, [`b__${s}_Foot__`]: 0.03, [`b__${s}_Toe__`]: 0,
    [`b__${s}_UpperArm__`]: 0.05, [`b__${s}_Forearm__`]: 0.04, [`b__${s}_Hand__`]: 0.03,
  });
}
Object.assign(SKIN_RADIUS, { b__Pelvis__: 0.12, b__Spine0__: 0.11, b__Spine1__: 0.11, b__Spine2__: 0.11, b__Head__: 0.09 });

// The lowest skin point of a posed RigPose (after fk()), in sim space. Heels count too (at ground level at rest).
export function lowestSkin(rp) {
  let low = Infinity;
  for (const [n, r] of Object.entries(SKIN_RADIUS)) {
    const k = rp.index(n);
    if (k >= 0) low = Math.min(low, rp.P[k].y - r);
  }
  for (const s of ['L', 'R']) low = Math.min(low, rp.rigidPoint(`b__${s}_Foot__`, heelRest(rp, s)).y);
  // the head's own points (the top of the head when upside down)
  const hk = rp.index('b__Head__');
  if (hk >= 0) low = Math.min(low, new THREE.Vector3(0.12, 0, 0).applyQuaternion(rp.W[hk]).add(rp.P[hk]).y - 0.09);
  return low;
}

// Pose math in the sim's own game space (the Sim.space group), independent of how it is displayed.
// Everything here works straight from the bones' local position / rotation / scale, so it never needs the whole
// skeleton's world matrices to be updated first (that was the slow part: ~40 full updates per sim per frame).
import * as THREE from 'three';
import { HINGE, limitsFor } from './bones.js';

const Z = new THREE.Vector3(0, 0, 1);
const _q = new THREE.Quaternion();

// Rotation of a bone relative to the sim's space: product of local rotations down the chain.
export function spaceQuat(sim, bone, target = new THREE.Quaternion()) {
  const chain = [];
  for (let b = bone; b && b !== sim.space; b = b.parent) chain.push(b);
  target.identity();
  for (let k = chain.length - 1; k >= 0; k--) target.multiply(chain[k].quaternion);
  return target;
}

export function setSpaceQuat(sim, bone, q) {
  const parentQ = bone.parent === sim.space ? new THREE.Quaternion() : spaceQuat(sim, bone.parent);
  bone.quaternion.copy(parentQ.invert().multiply(q)).normalize();
}

// Position of a bone in the sim's space: its local transforms composed up the chain (exactly what the world
// matrices would give, and always current - even right after a bone was turned).
export function spacePos(sim, bone, target = new THREE.Vector3()) {
  target.set(0, 0, 0);
  for (let b = bone; b && b !== sim.space; b = b.parent) target.multiply(b.scale).applyQuaternion(b.quaternion).add(b.position);
  return target;
}

// Only the sim's own group and space matrices are needed to go between world and sim space.
export function worldToSpace(sim, v) { sim.space.updateWorldMatrix(true, false); return sim.space.worldToLocal(v.clone()); }
export function spaceToWorld(sim, v) { sim.space.updateWorldMatrix(true, false); return sim.space.localToWorld(v.clone()); }

// Rotate a bone so that, in sim space, it turns by `delta` (a rotation applied in sim space).
export function rotateInSpace(sim, bone, delta) {
  const q = spaceQuat(sim, bone);
  setSpaceQuat(sim, bone, delta.clone().multiply(q));
}

// Analytic two-bone IK in sim space: a (upper), b (lower), c (end effector bone).
// Keeps the end bone's space rotation. Elbows and knees (HINGE bones) only bend about their own Z axis.
export function solveTwoBone(sim, a, b, c, targetSpace, poleSpace = null) {
  const endQ = spaceQuat(sim, c);
  const A = spacePos(sim, a), B = spacePos(sim, b), C = spacePos(sim, c);
  const lab = A.distanceTo(B), lbc = B.distanceTo(C);
  const T = targetSpace.clone();
  const toT = T.clone().sub(A);
  let dist = toT.length();
  const maxReach = (lab + lbc) * 0.9995, minReach = Math.abs(lab - lbc) * 1.001 + 1e-4;
  dist = Math.min(Math.max(dist, minReach), maxReach);

  // 1. bend at b to reach the distance
  if (HINGE[b.name]) bendHinge(sim, b, A, B, C, dist, HINGE[b.name]);
  else {
    const ba = A.clone().sub(B), bc = C.clone().sub(B);
    const cur = ba.angleTo(bc);
    const want = Math.acos(THREE.MathUtils.clamp((lab * lab + lbc * lbc - dist * dist) / (2 * lab * lbc), -1, 1));
    let axis = ba.clone().cross(bc);
    if (axis.lengthSq() < 1e-10) {
      // straight limb: bend toward the pole (or any perpendicular)
      const p = poleSpace ? poleSpace.clone().sub(B) : new THREE.Vector3(0, 0, 1);
      axis = ba.clone().cross(p);
      if (axis.lengthSq() < 1e-10) axis = ba.clone().cross(new THREE.Vector3(1, 0, 0));
    }
    axis.normalize();
    // axis = ba x bc, so turning bc about it by a positive angle opens the joint
    rotateInSpace(sim, b, new THREE.Quaternion().setFromAxisAngle(axis, want - cur));
  }

  // 2. swing a so the end reaches the target direction
  const C2 = spacePos(sim, c);
  const from = C2.clone().sub(A).normalize(), to = toT.clone().normalize();
  rotateInSpace(sim, a, new THREE.Quaternion().setFromUnitVectors(from, to));

  // 3. twist around the A->T axis so the middle joint points at the pole
  if (poleSpace) {
    const B3 = spacePos(sim, b), C3 = spacePos(sim, c);
    const dir = C3.clone().sub(A).normalize();
    const projB = B3.clone().sub(A); projB.sub(dir.clone().multiplyScalar(projB.dot(dir)));
    const projP = poleSpace.clone().sub(A); projP.sub(dir.clone().multiplyScalar(projP.dot(dir)));
    if (projB.lengthSq() > 1e-8 && projP.lengthSq() > 1e-8) {
      const ang = projB.angleTo(projP);
      const sign = Math.sign(projB.clone().cross(projP).dot(dir)) || 1;
      rotateInSpace(sim, a, new THREE.Quaternion().setFromAxisAngle(dir, ang * sign));
    }
  }
  setSpaceQuat(sim, c, endQ);
}

// Bend a hinge joint (elbow, knee) about its own local Z axis only, so the end is `dist` from the upper joint.
// Turning b by Rz(phi) turns the lower bone u (in b's frame) about z, while the upper bone w stays put:
//   |Rz(phi) u - w|^2 = |u|^2 + |w|^2 - 2 (u.z w.z + R cos(phi - psi))
// Of the two answers either side of the straight limb, it takes the one that bends the way the joint bends.
function bendHinge(sim, b, A, B, C, dist, bendSign) {
  const inv = spaceQuat(sim, b).invert();
  const u = C.clone().sub(B).applyQuaternion(inv);
  const w = A.clone().sub(B).applyQuaternion(inv);
  const P = u.x * w.x + u.y * w.y, Q = u.x * w.y - u.y * w.x, R = Math.hypot(P, Q);
  if (R < 1e-9) return;
  const psi = Math.atan2(Q, P);
  const D = (u.lengthSq() + w.lengthSq() - dist * dist) / 2;
  const c = THREE.MathUtils.clamp((D - u.z * w.z) / R, -1, 1);
  const phi = psi - bendSign * Math.acos(c);
  b.quaternion.multiply(_q.setFromAxisAngle(Z, phi)).normalize();
}

// How far a bone is bent about its own Z axis (degrees), and how much of its turn is off that axis.
export function hingeAngles(q) {
  const s = q.w < 0 ? -1 : 1;
  return { bend: THREE.MathUtils.radToDeg(2 * Math.atan2(s * q.z, s * q.w)), off: THREE.MathUtils.radToDeg(2 * Math.asin(Math.min(1, Math.hypot(q.x, q.y)))) };
}

// A turn from rest as Bend / Twist / Tilt degrees (XYZ Euler of rest^-1 * q) - what the inspector's rows show - and
// back.
export function restEuler(q, restQ) {
  const e = new THREE.Euler().setFromQuaternion(restQ.clone().invert().multiply(q), 'XYZ');
  return [e.x, e.y, e.z].map(THREE.MathUtils.radToDeg);
}
export function fromRestEuler(restQ, deg) {
  return restQ.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(...deg.map(THREE.MathUtils.degToRad), 'XYZ')));
}

// Rotation vectors (axis x angle, degrees) <-> quaternions: how hand shapes and natural limits are written.
const RAD = Math.PI / 180;
export function rvToQuat(rv, target = new THREE.Quaternion()) {
  const x = rv[0] * RAD, y = rv[1] * RAD, z = rv[2] * RAD, a = Math.hypot(x, y, z);
  if (a < 1e-12) return target.identity();
  const s = Math.sin(a / 2) / a;
  return target.set(x * s, y * s, z * s, Math.cos(a / 2));
}
export function quatToRv(q) {
  let { x, y, z, w } = q;
  if (w < 0) { x = -x; y = -y; z = -z; w = -w; }
  const s = Math.hypot(x, y, z);
  if (s < 1e-12) return [0, 0, 0];
  const a = 2 * Math.atan2(s, w) / RAD / s;
  return [x * a, y * a, z * a];
}

// Natural limits (spec_bodies 5.2): the bone's turn from rest as a rotation vector, each part clamped to the
// bone's range, and set back. -> true when it had to clamp. Hinges (elbows, knees, finger joints) have their bend
// clamped; a small sideways part a library pose may carry is left as it is (zeroing it would make the arm jump the
// moment it is touched - the hinge gizmo only turns the bend anyway).
const _lq = new THREE.Quaternion();
export function clampToLimits(sim, bone, lim = bone && limitsFor(bone.name)) {
  if (!lim || !bone) return false;
  const rest = sim.restByName[bone.name];
  if (!rest) return false;
  const rv = quatToRv(_lq.copy(rest.quat).invert().multiply(bone.quaternion).normalize());
  let hit = false;
  const out = rv.map((x, k) => {
    const ax = 'xyz'[k];
    if (lim.hinge && ax !== 'z') return x;
    const [lo, hi] = lim[ax];
    const v = Math.min(hi, Math.max(lo, x));
    if (Math.abs(v - x) > 1e-6) hit = true;
    return v;
  });
  if (!hit) return false;
  bone.quaternion.copy(rest.quat).multiply(rvToQuat(out, _lq)).normalize();
  return true;
}

// Shortest distance between the segments p1-q1 and p2-q2 (bodies in the way of the camera, clipping capsules).
export function segSegDist(p1, q1, p2, q2) {
  const d1 = q1.clone().sub(p1), d2 = q2.clone().sub(p2), r = p1.clone().sub(p2);
  const a = d1.dot(d1), e = d2.dot(d2), f = d2.dot(r);
  let s, t;
  if (a <= 1e-9 && e <= 1e-9) return p1.distanceTo(p2);
  if (a <= 1e-9) { s = 0; t = THREE.MathUtils.clamp(f / e, 0, 1); }
  else {
    const c = d1.dot(r);
    if (e <= 1e-9) { t = 0; s = THREE.MathUtils.clamp(-c / a, 0, 1); }
    else {
      const b = d1.dot(d2), den = a * e - b * b;
      s = den > 1e-9 ? THREE.MathUtils.clamp((b * f - c * e) / den, 0, 1) : 0;
      t = (b * s + f) / e;
      if (t < 0) { t = 0; s = THREE.MathUtils.clamp(-c / a, 0, 1); }
      else if (t > 1) { t = 1; s = THREE.MathUtils.clamp((b - c) / a, 0, 1); }
    }
  }
  return p1.clone().add(d1.multiplyScalar(s)).distanceTo(p2.clone().add(d2.multiplyScalar(t)));
}

// Mirror a rotation across the sim's side-to-side plane (normal = lateral axis in sim space).
export function mirrorQuat(q, lateral) {
  const S = new THREE.Matrix4().set(
    1 - 2 * lateral.x * lateral.x, -2 * lateral.x * lateral.y, -2 * lateral.x * lateral.z, 0,
    -2 * lateral.y * lateral.x, 1 - 2 * lateral.y * lateral.y, -2 * lateral.y * lateral.z, 0,
    -2 * lateral.z * lateral.x, -2 * lateral.z * lateral.y, 1 - 2 * lateral.z * lateral.z, 0,
    0, 0, 0, 1);
  const R = new THREE.Matrix4().makeRotationFromQuaternion(q);
  const M = S.clone().multiply(R).multiply(S);
  return new THREE.Quaternion().setFromRotationMatrix(M);
}

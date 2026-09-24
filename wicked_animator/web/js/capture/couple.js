// Two people (capture.md 9 "Two people", needs.md 7 / W3): both people of one video, webcam take or photo go onto two
// sims, standing where the camera saw them next to each other; hands that end up on the partner's body take hold
// ("snap contacts", through the hold solver of holds.js); and "Match the rhythm" (capture.md 7.2) shifts a take so
// its thrusts meet the partner's.
import * as THREE from 'three';
import * as A from '../animation.js';
import { LIMBS, isHold } from '../bones.js';
import { makeHold, limbPoint } from '../holds.js';
import { nearestSkin } from '../skin.js';
import { solveTake, cameraPlace, Solver } from './retarget.js';
import { hipCentre, shiftPose } from './mirror.js';
import { PL } from './rigpose.js';

const UP = new THREE.Vector3(0, 1, 0);
const toSim = (x, y, z) => new THREE.Vector3(x, -y, -z);

// ---------------------------------------------------------------- solving both people of a take
// solvePair(take, solver, opts0, opts1) -> [result0, result1 | null]: person 1 as solveTake does it; person 2 turned the
// same way (one camera) and moved along the floor so the two stand as the camera saw them, at the first frame where
// both were seen (after that each moves on its own, with its own "stay in place"). opts1.base: the second sim's pose
// now (its floor).
export function solvePair(take, solver, opts0, opts1) {
  const r0 = solveTake(take, 0, solver, opts0);
  if (!take.people[1]) return [r0, null];
  const N = take.t.length;
  const seen = (k, i) => take.people[k].pose[(i * 33 + PL.hipL) * 4 + 3] >= 0.5 && take.people[k].pose[(i * 33 + PL.hipR) * 4 + 3] >= 0.5;
  let i0 = -1;
  for (let i = 0; i < N; i++) if (seen(0, i) && seen(1, i)) { i0 = i; break; }
  if (i0 < 0) return [r0, null];
  const r1 = solveTake(take, 1, solver, { ...opts1, psi: r0.psi });
  const p0 = cameraPlace(take, 0, i0, opts0.fov || 60), p1 = cameraPlace(take, 1, i0, opts0.fov || 60);
  if (p0 && p1) {
    const rotY = new THREE.Quaternion().setFromAxisAngle(UP, r0.psi);
    const scale = ((r0.scale || 1) + (r1.scale || 1)) / 2;
    const off = toSim(p1.x - p0.x, p1.y - p0.y, p1.z - p0.z).multiplyScalar(scale).applyQuaternion(rotY);
    const rp = new Solver(solver.rp.rig).rp;
    const d = hipCentre(rp, r0.poses[i0]).add(off).sub(hipCentre(rp, r1.poses[i0])).setY(0);
    for (const pose of r1.poses) shiftPose(pose, d);
    r1.pairShift = d.toArray();
  }
  return [r0, r1];
}

// ---------------------------------------------------------------- snap contacts
const HANDS = ['L hand', 'R hand'];
// How far each hand's palm is from the partner's skin now (metres; Infinity when nothing is within `max`).
export function handGaps(app, simId, otherId, max = 1) {
  const v = app.simViews.get(simId), ov = app.simViews.get(otherId);
  const out = {};
  if (!v || !ov) return out;
  for (const limb of HANDS) {
    const hit = nearestSkin(ov, limbPoint(v, limb), max);
    out[limb] = hit ? hit.dist : Infinity;
  }
  return out;
}

// snapContacts(app, simIds, {within, frame}) -> [{simId, limb, other, gapCm}]: every hand of these sims whose palm is
// within `within` (6 cm) of a partner's skin at this frame holds on there (the palm settles 1.2 cm off the skin and
// follows that body). A sim with other body keys holds only around this frame (it eases in and out); a single pose
// holds for the whole loop. No undo step of its own (the caller made one).
export function snapContacts(app, simIds, { within = 0.06, frame = Math.round(app.store.frame) } = {}) {
  const made = [];
  app.applyPoses(false);
  for (const id of simIds) {
    const sim = app.store.sim(id), v = app.simViews.get(id);
    if (!sim || !v) continue;
    const partners = simIds.filter(x => x !== id).map(x => ({ sim: app.store.sim(x), v: app.simViews.get(x) })).filter(o => o.sim && o.v && o.sim.visible !== false);
    const others = sim.keys.filter(k => !k.faceOnly && k.pose && k.frame !== frame).length;
    for (const limb of HANDS) {
      if (isHold(sim.pins && sim.pins[limb])) continue;
      const at = limbPoint(v, limb);
      let best = null;
      for (const o of partners) { const hit = nearestSkin(o.v, at, within); if (hit && (!best || hit.dist < best.hit.dist)) best = { o, hit }; }
      if (!best) continue;
      const keep = others ? { from: frame, to: frame, fade: 6 } : null;
      const h = makeHold(app, id, limb, best.o, best.hit, { checkpoint: false, quiet: true, keep });
      if (h) made.push({ simId: id, limb, other: best.o.sim.id, label: h.label, fromCm: Math.round(best.hit.dist * 1000) / 10 });
    }
  }
  if (made.length) app.applyPoses(false);
  for (const m of made) { const g = handGaps(app, m.simId, m.other)[m.limb]; m.gapCm = Math.round(g * 1000) / 10; }
  return made;
}

// ---------------------------------------------------------------- match the rhythm (capture.md 7.2)
// Where the pelvis is at each frame of some poses (sim space).
export function pelvisTrack(rp, poses) {
  return poses.map(pose => { rp.resetPose(); if (pose) rp.setPose(pose); rp.fk(); return rp.pos('b__Pelvis__').clone(); });
}
// The partner's pelvis over the whole animation (its keys as they play).
export function partnerTrack(app, rp, simId) {
  const p = app.store.project, s = app.store.sim(simId);
  if (!s) return null;
  const L = p.length, poses = [];
  for (let f = 0; f < L; f++) poses.push(A.evaluate(s.keys, f, L, p.loop, p.autoCurve));
  return pelvisTrack(rp, poses);
}

// The circular shift of `mine` (a loop of L frames) that best lines its moves toward the partner up with the
// partner's moves toward it: both pelvis speeds along the line between them (or, when they are on top of each other,
// along the way the take moves most), cross-correlated over the loop. -> {lag, score (-1..1), strength (metres a
// frame)}; new[f] = old[(f + lag) % L].
export function rhythmLag(mine, theirs) {
  const L = Math.min(mine.length, theirs.length);
  if (L < 8) return { lag: 0, score: 0, strength: 0 };
  const mean = arr => arr.slice(0, L).reduce((a, b) => a.add(b), new THREE.Vector3()).multiplyScalar(1 / L);
  const mA = mean(mine), mB = mean(theirs);
  let u = mB.clone().sub(mA);
  if (u.length() < 0.05) {
    // the main direction of the take's own hip motion (power iteration on its spread)
    u = new THREE.Vector3(1, 1, 1).normalize();
    for (let it = 0; it < 12; it++) {
      const acc = new THREE.Vector3();
      for (let f = 0; f < L; f++) { const d = mine[f].clone().sub(mA); acc.addScaledVector(d, d.dot(u)); }
      if (acc.length() < 1e-9) break;
      u = acc.normalize();
    }
  } else u.normalize();
  const speed = (arr, dir) => { const out = new Float64Array(L); for (let f = 0; f < L; f++) { const a = arr[(f + 1) % L], b = arr[(f - 1 + L) % L]; out[f] = 0.5 * a.clone().sub(b).dot(dir); } return out; };
  const sA = speed(mine, u), sB = speed(theirs, u.clone().negate());
  const norm = x => Math.sqrt(x.reduce((a, b) => a + b * b, 0)) || 1e-12;
  const nA = norm(sA), nB = norm(sB);
  let best = { lag: 0, c: -Infinity };
  for (let lag = 0; lag < L; lag++) {
    let c = 0;
    for (let f = 0; f < L; f++) c += sA[(f + lag) % L] * sB[f];
    if (c > best.c) best = { lag, c };
  }
  return { lag: best.lag, score: best.c / (nA * nB), strength: Math.min(nA, nB) / Math.sqrt(L), u: u.toArray() };
}

// Shift a loop's poses (and faces) by `lag` frames: new[f] = old[(f + lag) % L].
export function shiftLoop(poses, faces, lag) {
  const L = poses.length, k = ((lag % L) + L) % L;
  const rot = arr => (arr ? arr.map((_, f) => arr[(f + k) % L]) : arr);
  return { poses: rot(poses), faces: rot(faces) };
}

// Everything "Match the rhythm" needs for a take about to go on `simId` (already the project's length): the lag and
// how sure it is. -> {lag, score, partner} or null when there is no partner with its own moves.
export function matchRhythm(app, simId, poses, partnerId = null) {
  const p = app.store.project;
  const partner = partnerId ? app.store.sim(partnerId) : p.sims.find(s => s.id !== simId && s.keys.some(k => !k.faceOnly && k.pose));
  if (!partner || poses.length !== p.length) return null;
  const rp = new Solver(app.assets.rig).rp;
  const theirs = partnerTrack(app, rp, partner.id);
  const mine = pelvisTrack(rp, poses);
  const r = rhythmLag(mine, theirs);
  return { ...r, partner: partner.id, label: partner.label };
}

export { HANDS, LIMBS };

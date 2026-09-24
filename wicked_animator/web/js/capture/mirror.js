// The live mirror (capture.md 9, "Webcam"): the sim copies you in the main 3D view, live, while you move in front of
// the webcam - two sims copy two people. Every frame the reader gives is solved (retarget.solveOne), smoothed with a
// light live filter, and shown on the sim through the app's afterApply hook, on top of what its keys show: no key
// changes until you press "Keep this pose" (K) or record a take. A partner whose hand holds a mirrored sim keeps
// holding on while you move.
import * as THREE from 'three';
import { applyFace, clampFace } from '../face.js';
import { HIPS } from '../bones.js';
import { spaceQuat } from '../posemath.js';
import * as A from '../animation.js';
import { Solver, solveOne, cameraPlace } from './retarget.js';
import { OneEuro } from './clean.js';
import { TakeRecorder } from './tracker.js';
import { faceTrack } from './facemap.js';
import { PL } from './rigpose.js';
import { applyToSim } from './keys.js';

const UP = new THREE.Vector3(0, 1, 0);
const toSim = (x, y, z) => new THREE.Vector3(x, -y, -z);             // MediaPipe world axes -> sim space
const styleOf = p => (p && p.faceStyle) || ((p && (p.version || 1) < 3) ? 'classic' : 'creator');
// live smoothing: steady when you hold still, quick when you move (one-euro, capture.md 5.8)
const ROT = { minCutoff: 2.0, beta: 12, dCutoff: 1.5 };
const MOVE = { minCutoff: 1.2, beta: 3, dCutoff: 1 };
const DRIFT = 1.5;                                                   // s: "stay in place" (slow drift removed)

// A one-frame take of a frame record (person 1 and, when there, person 2).
export function frameTake(fr, W = 1280, H = 720, people = null) {
  const n = people || 1 + ((fr && fr.others) ? fr.others.length : 0);
  const rec = new TakeRecorder('frame', W, H, 60, 1, n);
  rec.add(0, fr);
  return rec.take();
}

// The sim's facing (turn about the vertical, radians) from its hips, the app's own rule.
export function facingOf(app, simId, pose = null) {
  try {
    const v = app.simViews && app.simViews.get(simId);
    if (v && typeof app._facing === 'function' && !pose) { const q = app._facing(v); return 2 * Math.atan2(q.y, q.w); }
  } catch { /* below */ }
  const rp = new Solver(app.assets.rig).rp;
  rp.resetPose(); if (pose) rp.setPose(pose); rp.fk();
  const q = spaceQuat(rp, rp.bone('b__Pelvis__'));
  const fwd = new THREE.Vector3(0, 1, 0).applyQuaternion(q), left = new THREE.Vector3(0, 0, -1).applyQuaternion(q);
  return Math.hypot(fwd.x, fwd.z) >= Math.hypot(left.x, left.z) ? Math.atan2(fwd.x, fwd.z) : Math.atan2(-left.z, left.x);
}

// The middle of the hips of a solved pose (sim space).
export function hipCentre(rp, pose) {
  rp.resetPose(); rp.setPose(pose); rp.fk();
  return rp.pos('b__L_Thigh__').clone().add(rp.pos('b__R_Thigh__')).multiplyScalar(0.5);
}
// Move a pose along the floor by a sim-space offset (only x and z: the floor rule keeps the height).
export function shiftPose(pose, d) {
  for (const h of HIPS) {
    const p = pose.pos && pose.pos[h];
    if (!p) continue;
    // ROOT_bind's rest turns local x -> up, y -> forward (+Z), z -> left (+X)
    pose.pos[h] = [p[0], p[1] + d.z, p[2] + d.x];
  }
  return pose;
}

// The performer's leg length in a take frame (for the scale from their body to the sim's).
function perfLegLen(take, person, i) {
  const pe = take.people[person], po = pe.pose;
  const P = j => toSim(po[(i * 33 + j) * 4], po[(i * 33 + j) * 4 + 1], po[(i * 33 + j) * 4 + 2]);
  const ok = [PL.shL, PL.hipL, PL.knL, PL.anL].every(j => po[(i * 33 + j) * 4 + 3] >= 0.5);
  if (!ok) return null;
  return P(PL.shL).distanceTo(P(PL.hipL)) + P(PL.hipL).distanceTo(P(PL.knL)) + P(PL.knL).distanceTo(P(PL.anL));
}

export class LiveMirror {
  // simIds: the sim that copies person 1 (and person 2); opts: {hands, fingers, face, smooth}
  constructor(app, { simIds, solver = null, hands = true, face = true, smooth = 0.5 } = {}) {
    this.app = app;
    this.simIds = simIds.filter(Boolean).slice(0, 2);
    this.solver = solver || new Solver(app.assets.rig);
    this.rp2 = new Solver(app.assets.rig).rp;                        // a second skeleton for measuring
    this.opts = { hands, face, smooth };
    this.live = this.simIds.map(() => null);                         // {pose, face, seq}
    this.shownSeq = this.simIds.map(() => -1);
    this.seq = 0;
    this.shown = [];                                                 // times a new live pose reached the view
    this.solved = [];                                                // times a frame was solved
    this.solveMs = [];
    this.on = false;
    this._hook = (frame, info) => this._after(frame, info);
  }

  // Start copying: where each sim is now (its pose at this frame, its facing) is where it copies you.
  start() {
    const app = this.app, p = app.store.project, f = Math.round(app.store.frame);
    this.base = this.simIds.map(id => { const s = app.store.sim(id); return s ? A.evaluate(s.keys, f, p.length, p.loop, p.autoCurve) : null; });
    this.facing = facingOf(app, this.simIds[0]);
    this.psi = null; this.scale = null; this.first = this.simIds.map(() => null); this.pair = null;
    this.drift = this.simIds.map(() => ({ avg: new THREE.Vector3(), t: null, fx: new OneEuro(MOVE.minCutoff, MOVE.beta, MOVE.dCutoff), fz: new OneEuro(MOVE.minCutoff, MOVE.beta, MOVE.dCutoff) }));
    this.filters = this.simIds.map(() => new Map());
    this.prevQ = this.simIds.map(() => ({}));
    if (!this.on) { (app.hooks.afterApply = app.hooks.afterApply || []).push(this._hook); this.on = true; }
    return this;
  }

  stop() {
    if (!this.on) return;
    this.on = false;
    const list = this.app.hooks.afterApply || [], i = list.indexOf(this._hook);
    if (i >= 0) list.splice(i, 1);
    this.live = this.simIds.map(() => null);
    try { this.app.applyPoses(false); } catch (e) { console.error('capture: mirror stop', e); }
  }

  // A frame record from the reader: solve each person, smooth, keep it for the next drawn frame.
  feed(fr, tSec = performance.now() / 1000, { W = 1280, H = 720 } = {}) {
    if (!this.on || !fr) return false;
    const t0 = performance.now();
    const persons = [fr, ...(fr.others || [])].slice(0, this.simIds.length);
    if (!persons[0] || !persons[0].pose) return false;
    const take = frameTake(fr, W, H, persons.length);
    const solver = this.solver, rp = solver.rp;
    // the capture turned to face the way the sim faces now (fixed at the first frame, so turning around shows)
    if (this.psi === null) {
      const pts = solver.points(take, 0, 0, {});
      if (pts.vis[PL.hipL] < 0.5 || pts.vis[PL.hipR] < 0.5) return false;
      this.psi = this.facing - Solver.yawOf(pts.pose[PL.hipL].clone().sub(pts.pose[PL.hipR]));
      const leg = perfLegLen(take, 0, 0);
      this.scale = leg ? solver.legLen / leg : 1;
    }
    const rotY = new THREE.Quaternion().setFromAxisAngle(UP, this.psi);
    const places = persons.map((pe, k) => (pe && pe.pose ? cameraPlace(take, k, 0, 60) : null));
    let changed = false;
    persons.forEach((pe, k) => {
      if (!pe || !pe.pose || !this.base[k] && k > 0) return;
      const pose = solveOne(solver, take, k, 0, { facing: this.facing, psi: this.psi, base: this.base[k], hands: this.opts.hands, fingers: this.opts.hands, headFromFace: this.opts.face });
      // person 2 stands where the camera saw them next to person 1 (worked out once, on the first frame with both)
      if (k === 1) {
        if (!this.pair && places[0] && places[1] && this.live[0]) {
          const off = toSim(places[1].x - places[0].x, places[1].y - places[0].y, places[1].z - places[0].z).multiplyScalar(this.scale).applyQuaternion(rotY);
          const want = hipCentre(this.rp2, this.live[0].raw).add(off);
          const have = hipCentre(this.rp2, pose);
          this.pair = want.sub(have).setY(0);
        }
        if (this.pair) shiftPose(pose, this.pair);
      }
      // moves across the floor (thrusts, sways, steps), with the slow drift taken out ("stay in place")
      if (places[k]) {
        const dr = this.drift[k];
        if (!this.first[k]) this.first[k] = places[k].clone();
        const d = toSim(places[k].x - this.first[k].x, places[k].y - this.first[k].y, places[k].z - this.first[k].z).multiplyScalar(this.scale).applyQuaternion(rotY);
        const dt = dr.t === null ? 0 : Math.max(0, Math.min(0.5, tSec - dr.t));
        dr.t = tSec;
        dr.avg.lerp(d, 1 - Math.exp(-dt / DRIFT));
        const hp = d.clone().sub(dr.avg);
        shiftPose(pose, new THREE.Vector3(dr.fx.filter(hp.x, tSec), 0, dr.fz.filter(hp.z, tSec)));
      }
      const raw = { rot: { ...pose.rot }, pos: { ...pose.pos } };
      this._smooth(k, pose, tSec);
      let face = null;
      if (this.opts.face && pe.face) {
        const ft = faceTrack(take, k, { relativeHead: false, still: true });
        face = ft.ok ? ft.faces[0] : null;
      }
      this.live[k] = { pose, raw, face, seq: ++this.seq };
      changed = true;
    });
    if (changed) {
      const now = performance.now();
      this.solved.push(now); this.solveMs.push(now - t0);
      if (this.solved.length > 240) this.solved.splice(0, this.solved.length - 240);
      if (this.solveMs.length > 240) this.solveMs.splice(0, this.solveMs.length - 240);
    }
    return changed;
  }

  _smooth(k, pose, t) {
    const F = this.filters[k], prev = this.prevQ[k];
    const k01 = Math.max(0, Math.min(1, this.opts.smooth ?? 0.5));
    const cut = ROT.minCutoff * (0.5 + (1 - k01) * 1.5);
    for (const [b, q] of Object.entries(pose.rot)) {
      let f = F.get(b);
      if (!f) { f = [0, 1, 2, 3].map(() => new OneEuro(cut, ROT.beta, ROT.dCutoff)); F.set(b, f); }
      const p = prev[b];
      const s = p && p[0] * q[0] + p[1] * q[1] + p[2] * q[2] + p[3] * q[3] < 0 ? -1 : 1;     // keep the sign steady
      const out = [0, 1, 2, 3].map(c => f[c].filter(s * q[c], t));
      const l = Math.hypot(...out) || 1;
      pose.rot[b] = out.map(x => x / l);
      prev[b] = pose.rot[b];
    }
  }

  // Frames per second: how many new live poses reached the 3D view (and were solved) in the last second.
  fps(now = performance.now()) {
    const c = arr => arr.filter(x => now - x <= 1000).length;
    return { shown: c(this.shown), solved: c(this.solved) };
  }

  // The app's afterApply hook: the mirrored sims take the live pose (their face too, when it is read), on top of the
  // frame the keys show. Their twist helpers follow, and partners' holds on them follow.
  _after(frame) {
    if (!this.on) return;
    const app = this.app, pl = app.pipeline, p = app.store.project;
    if (app.preview) return;
    const all = pl.entries();
    const style = styleOf(p);
    let moved = false;
    this.simIds.forEach((id, k) => {
      const L = this.live[k];
      const e = L && all.find(x => x.sim.id === id);
      if (!e) return;
      const v = e.v;
      v.resetPose();
      v.setPose(L.pose);
      v.setFaceBones(pl.keyedFace(e.sim, frame));
      pl.twist(e);
      applyFace(v, L.face || pl.lastFace.get(id) || null, style);
      if (style !== 'classic') clampFace(v);
      moved = true;
      if (L.seq !== this.shownSeq[k]) {
        this.shownSeq[k] = L.seq;
        if (k === 0) { this.shown.push(performance.now()); if (this.shown.length > 240) this.shown.splice(0, this.shown.length - 240); }
      }
    });
    // a partner's hand on a mirrored sim follows it (the pipeline solves holds on parts that moved once more)
    if (moved) { try { pl.holdsAfter(all, frame); } catch { /* an older pipeline */ } }
  }

  // "Keep this pose": the live pose becomes a key at this frame on each mirrored sim (one Ctrl+Z).
  keep() {
    const app = this.app, f = Math.round(app.store.frame);
    const done = [];
    const list = this.simIds.map((id, k) => [id, this.live[k]]).filter(([id, L]) => L && app.store.sim(id));
    if (!list.length) return done;
    app.store.checkpoint();
    for (const [id, L] of list) {
      const pose = { rot: { ...L.pose.rot }, pos: { ...L.pose.pos } };
      applyToSim(app, id, { poses: [pose], faces: L.face ? [L.face] : null }, { mode: 'insert', at: f, detail: 0.5, checkpoint: false, source: 'webcam' });
      done.push(id);
    }
    return done;
  }
}

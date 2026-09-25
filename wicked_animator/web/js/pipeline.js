// How a frame is built, the same way for the 3D view and for the game:
//   1. keys           your poses, with the chosen easing between them
//   2. face keys      the face posed by hand (key.faceBones)
//   3. motion layers  thrust / ride / head bob ... added on top
//      (arms and head may follow the keys a few frames late: sim.lag, "Follow-through")
//   4. pins           pinned hands and feet stay where they are, knees and elbows bend (for the whole loop, or only
//                     from one frame to another, fading in and out)
//   --- pass B, once every sim has passes 1-4 (so a sim never sees its partner one frame late) ---
//   5. holds          hands (and feet) holding on to the partner follow the partner's body: the palm stays on the
//                     skin, the elbow bends by itself
//   6. hand layers    hand strokes (after pins, so a stroking hand can still be pinned elsewhere); then look-at
//                     (head, neck and eyes toward the partner) and tremble - the late motions
//   7. twist helpers  wrists, upper arms and hips twist softly with the hand, arm and leg (each can be switched off)
//   8. face           sliders and expressions from the keys + the mouth moving while a voice plays + blinking, on top
//                     of the hand-posed face (talking and blinking give way to a mouth or lids posed shut or open),
//                     then the safety clamp for lids and jaw
//   9. openings       vagina / anus / mouth open around whatever goes in (can be switched off per sim);
//                     the mouth corners follow the jaw
//  10. physics        breasts, butt, penis and balls bounce (simulated over the whole loop)
// Everything automatic (twist helpers, face sliders, blinking, talking, the clamp, the jaw carrying the mouth) is
// recorded as the sim's automatic layer (Sim.addLayer / setLayer), so hand-posing never bakes it into a key.
import * as THREE from 'three';
import { evaluate, evaluateFace, evaluateFaceBones, twistAngle } from './animation.js';
import { applyLayer, MOTIONS } from './motion.js';
import { LIMBS, POSABLE, HIPS, AUTO, MOUTH, TONGUE, FACE_CHANNEL, TWIST, PALM, PALM_GAP, SOLE_GAP, pinAt, pinWeight } from './bones.js';
import { spacePos, solveTwoBone, setSpaceQuat } from './posemath.js';
import { applyFace, talkAt, mergeFace, blinkAt, followJaw, clampFace, keyedAmounts, fadeOverlay } from './face.js';
import { measure, applyOpen } from './openings.js';
import { partsFor, simulate, applyFrame, defaultPhysics } from './physics.js';
import { migrateProject } from './state.js';
import { applyErection, hasGrow } from './erection.js';

export function simBody(sim) {
  // per-sim automatic settings, with defaults for older projects
  sim.body = sim.body || {};
  const b = sim.body;
  if (b.erect === undefined) b.erect = true;
  if (!b.open) b.open = { on: true, vagina: true, anus: true, mouth: true };
  if (!b.physics) b.physics = defaultPhysics(sim.frame);
  if (!b.talk) b.talk = { mouth: true };
  if (b.tongue === undefined) b.tongue = true;
  if (b.twist === undefined) b.twist = true;             // wrists and shoulders twist softly (like the game's own)
  // the hips too: on by default - measured on the skin (tools/checks/r1a/hip_twist.js), EA's -0.75 rule makes the hip,
  // groin and buttock stretch less in 7 of 9 test poses (a pure 45 degree thigh twist: 0.097 -> 0.031 mean stretch)
  if (b.hipTwist === undefined) b.hipTwist = true;
  sim.layers = sim.layers || [];
  return b;
}

// The project's face style: 'creator' (new projects) or 'classic' (projects made before faces could be posed by
// hand keep exactly the look and the playback they had).
export function faceStyleOf(p) {
  return (p && p.faceStyle) || ((p && (p.version || 1) < 3) ? 'classic' : 'creator');
}

// Thresholds for the exporter's flags (see bake).
const cosHalf = deg => Math.cos(THREE.MathUtils.degToRad(deg) / 2);
// The mouth is "used" when the clip really shows it. The ready poses come from creator clips whose jaw sits a
// degree or four off rest and drifts a little over the loop: that is a closed mouth, and the game's lip-sync may
// run over it. So a mouth bone counts only when it travels over the loop by more than MOUTH_MOVE (a full "Mouth
// open" is 24 degrees of jaw, the mouth corners follow the jaw by about 0.5 mm per degree), or is held open by
// more than MOUTH_HOLD at some frame.
const MOUTH_MOVE = { rot: cosHalf(4), pos: 0.002 ** 2 };      // 4 degrees, 2 mm
const MOUTH_HOLD = { rot: cosHalf(5), pos: 0.003 ** 2 };      // 5 degrees, 3 mm
const MOUTH_FACE = ['open', 'pout', 'bite', 'tongue'];        // face channels that shape the mouth (above 0.05)
const TONGUE_ROT = cosHalf(3), TONGUE_POS = 0.001 ** 2;       // 3 degrees, 1 mm

function awayFromRest(track, rest, cosLimit, posLimitSq) {
  if (!track || !rest) return false;
  const q = rest.quat, p = rest.pos;
  if (track.r) for (const r of track.r) if (Math.abs(r[0] * q.x + r[1] * q.y + r[2] * q.z + r[3] * q.w) < cosLimit) return true;
  if (track.t) for (const t of track.t) if ((t[0] - p.x) ** 2 + (t[1] - p.y) ** 2 + (t[2] - p.z) ** 2 > posLimitSq) return true;
  return false;
}

// Does a track travel further than the limit over the loop? The largest gap between two of its frames is looked
// for from the frame farthest from the first one: that gap is at least as big as any gap from the first frame and
// close to the true largest one, which is plenty for a threshold (and linear, not frames x frames).
const rotGap = (a, b) => 1 - Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]);
const posGap = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
function travels(list, gap, limit) {
  if (!list || list.length < 2) return false;
  let far = list[0], most = -1;
  for (const x of list) { const g = gap(list[0], x); if (g > most) { most = g; far = x; } }
  return list.some(x => gap(far, x) > limit);
}

function mouthTrackUsed(track, rest) {
  if (!track || !rest) return false;
  return travels(track.r, rotGap, 1 - MOUTH_MOVE.rot) || travels(track.t, posGap, MOUTH_MOVE.pos)
    || awayFromRest(track, rest, MOUTH_HOLD.rot, MOUTH_HOLD.pos);
}

const _tq = new THREE.Quaternion(), _X = new THREE.Vector3(1, 0, 0);
const _hq = new THREE.Quaternion(), _hq2 = new THREE.Quaternion(), _hv = new THREE.Vector3(), _hn = new THREE.Vector3();
const _spaceQ = new THREE.Quaternion(), _spaceM = new THREE.Matrix4();

// Follow-through (sim.lag): these bones take the keys a few frames late, the rest of the pose is on time.
const ARM_LAG = ['Clavicle', 'UpperArm', 'Forearm', 'Hand'].flatMap(n => [`b__L_${n}__`, `b__R_${n}__`]);
const HEAD_LAG = ['b__Neck__', 'b__Head__'];

// The eyes of a look-at layer blended into the face sliders (weight 0..1 of the look's own lookUp / lookSide).
export function withLook(face, look) {
  const w = Math.min(1, Math.max(0, look.weight ?? 1)), out = { ...(face || {}) };
  for (const k of ['lookUp', 'lookSide']) if (typeof look[k] === 'number') out[k] = (out[k] || 0) * (1 - w) + look[k] * w;
  return out;
}

export class Pipeline {
  constructor(app) {
    this.app = app;
    this.phys = new Map();          // sim id -> simulated offsets
    this.physKey = '';
    this.lastOpen = new Map();      // sim id -> openings measured at the shown frame
    this.mouthDepth = new Map();    // sim id -> how deep something is in the mouth on every frame (the lips' pull)
    this.lastFace = new Map();      // sim id -> the face shown at that frame (keys + talking + blinking), or null
    this.editing = null;            // sim id being posed by hand: its motion layers, openings and physics pause
    this.overrides = new Map();     // sim id -> {frame, pose?, faceBones?}: posed but not keyed yet (auto key off)
    this.reach = new Map();         // sim id -> {limb: metres}: how far a held hand or foot is from where it holds
                                    //   (above 0.01: out of reach at the frame shown)
  }

  // The keyed pose at `frame`. A pending pose (posed, not keyed yet) only counts where hand-posing sees it: the
  // paused view and the edit tools. Playback, physics, trails, automatic sounds and the export pass
  // `useOverrides = false`, so an unkeyed change never ends up in the game as a one-frame twitch.
  keyed(sim, frame, useOverrides = true) {
    const ov = useOverrides && this.overrides.get(sim.id);
    if (ov && ov.pose && ov.frame === Math.round(frame)) return ov.pose;
    const p = this.project;
    return evaluate(sim.keys, frame, p.length, p.loop, p.autoCurve);
  }

  // The keys with the arms and / or the head a few frames late (sim.lag = {arms, head}, 0-8 frames): they reach
  // each pose a moment after the body. The rest of the pose is on time. Without lag this is keyed().
  lagged(sim, frame, useOverrides = true) {
    const pose = this.keyed(sim, frame, useOverrides);
    const lag = sim.lag;
    if (!pose || !lag || (!(lag.arms > 0) && !(lag.head > 0))) return pose;
    const p = this.project, L = p.length;
    const at = n => (p.loop ? (((frame - n) % L) + L) % L : Math.max(0, frame - n));
    const out = { rot: { ...(pose.rot || {}) }, pos: pose.pos };
    if (lag.arms > 0) { const q = this.keyed(sim, at(lag.arms), false); for (const b of ARM_LAG) if (q && q.rot && q.rot[b]) out.rot[b] = q.rot[b]; }
    if (lag.head > 0) { const q = this.keyed(sim, at(lag.head), false); for (const b of HEAD_LAG) if (q && q.rot && q.rot[b]) out.rot[b] = q.rot[b]; }
    return out;
  }

  // The hand-posed face at `frame` (key.faceBones between face keys), or a pending one on this frame; null when the
  // sim has no face keys.
  keyedFace(sim, frame, useOverrides = true) {
    const ov = useOverrides && this.overrides.get(sim.id);
    if (ov && ov.faceBones && ov.frame === Math.round(frame)) return ov.faceBones;
    const p = this.project;
    return evaluateFaceBones(sim.keys, frame, p.length, p.loop);
  }

  get project() {
    const p = this.app.store.project;
    // a project that was never loaded through Store.load (e.g. a saved one baked by bakeOther) is brought up to
    // date first, so it plays exactly as it did
    if (p && (p.version || 1) < 3) migrateProject(p);
    return p;
  }

  entries() {
    const out = [];
    for (const sim of this.project.sims) {
      const v = this.app.simViews.get(sim.id);
      if (v) out.push({ sim, v });
    }
    return out;
  }

  // ---------------------------------------------------------------- stages
  // Keys + face keys + pins (+ holds) only: what hand-posing works on (so edits never bake the automatic layers
  // into keys).
  base(e, frame) {
    const { sim, v } = e;
    const pose = this.keyed(sim, frame);
    v.resetPose();
    if (pose) v.setPose(pose);
    v.setFaceBones(this.keyedFace(sim, frame));
    this.pins(e, frame);
    this.holds(e, frame, this.entries());
  }

  // Fixed pins: for the whole loop ([x, y, z]) or from one frame to another ({at, from, to, fade}), blended in and
  // out. Holds are pass B's (holds()).
  pins(e, frame) {
    const { sim, v } = e;
    if (!sim.pins) return;
    let f = frame;
    for (const [limb, pin] of Object.entries(sim.pins)) {
      const at = pinAt(pin);
      if (!at || !LIMBS[limb]) continue;
      if (f === undefined) f = (this.app.store && this.app.store.frame) || 0;
      const p = this.project;
      const w = pinWeight(pin, f, p.length, p.loop);
      if (w <= 0) continue;
      const chain = LIMBS[limb].map(n => v.bone(n));
      if (chain.some(b => !b)) continue;
      const before = w < 1 ? chain.map(b => b.quaternion.clone()) : null;
      const target = new THREE.Vector3().fromArray(at);
      const A = spacePos(v, chain[0]), C = spacePos(v, chain[2]), B = spacePos(v, chain[1]);
      const mid = A.clone().add(C).multiplyScalar(0.5), out = B.clone().sub(mid);
      const pole = out.lengthSq() > 1e-6 ? B.clone().add(out.normalize().multiplyScalar(0.4)) : null;
      solveTwoBone(v, chain[0], chain[1], chain[2], target, pole);
      if (before) chain.forEach((b, i) => b.quaternion.copy(before[i].slerp(b.quaternion, w)));
    }
  }

  // Holds (spec_bodies 4.4): a hand or foot holding on to a partner follows that partner's body. The hand is turned
  // as it was when it took hold (relative to the partner's bone), its palm centre goes 1.2 cm off the skin point
  // (a foot bone 3 cm), and the elbow / knee bends to reach it. Each hold uses the partner's pass-A pose, so two
  // sims holding each other never chase each other. A hold with a range fades in and out like a ranged pin.
  // `only`: just this limb. A limb being dragged in the view is left to the drag.
  holds(e, frame, all, only = null) {
    const { sim, v } = e;
    const pins = sim.pins;
    if (!pins) return;
    let reach = null;
    for (const limb in pins) {
      const h = pins[limb];
      if (!h || Array.isArray(h) || !h.sim || !h.bone || pinAt(h) || !LIMBS[limb]) continue;
      if (only && only !== limb) continue;
      const ia = this.app.interact, dh = ia && ia.dragHold;
      if (dh && dh.simId === sim.id && dh.limb === limb && this.app.vp && this.app.vp.dragging) continue;
      const p = this.project;
      const w = pinWeight(h, frame === undefined ? ((this.app.store && this.app.store.frame) || 0) : frame, p.length, p.loop);
      if (w <= 0) continue;
      const other = (all || this.entries()).find(x => x.sim.id === h.sim);
      const ab = other && other.v.bone(h.bone);
      if (!ab || other.v === v) continue;
      const chain = LIMBS[limb].map(n => v.bone(n));
      if (chain.some(b => !b)) continue;
      ab.updateWorldMatrix(true, false);
      (this._holdAt || (this._holdAt = new Map())).set(sim.id + '|' + limb, { m: ab.matrixWorld.elements.slice(), free: chain.map(b => b.quaternion.clone()) });
      const aQ = ab.getWorldQuaternion(_hq);
      const skinW = _hv.fromArray(h.off || [0, 0, 0]).applyMatrix4(ab.matrixWorld);
      const nW = _hn.fromArray(h.n || [0, 0, 0]).applyQuaternion(aQ);
      const handW = aQ.multiply(_hq2.fromArray(h.rot || [0, 0, 0, 1])).normalize();       // (aQ is reused)
      v.space.updateWorldMatrix(true, false);
      const spaceQ = v.space.getWorldQuaternion(_spaceQ);
      const handQ = spaceQ.clone().invert().multiply(handW);                              // in this sim's space
      const before = w < 1 ? chain.map(b => b.quaternion.clone()) : null;
      setSpaceQuat(v, chain[2], handQ);
      const isHand = !!PALM[limb];
      const contactW = skinW.addScaledVector(nW, isHand ? PALM_GAP : SOLE_GAP);
      const contact = contactW.applyMatrix4(_spaceM.copy(v.space.matrixWorld).invert());
      const palm = isHand && v.restByName[PALM[limb]];
      const wrist = palm ? contact.clone().sub(palm.pos.clone().applyQuaternion(handQ)) : contact.clone();
      const A = spacePos(v, chain[0]), B = spacePos(v, chain[1]), C = spacePos(v, chain[2]);
      const mid = A.clone().add(C).multiplyScalar(0.5), out = B.clone().sub(mid);
      const pole = out.lengthSq() > 1e-6 ? B.clone().add(out.normalize().multiplyScalar(0.4)) : null;
      solveTwoBone(v, chain[0], chain[1], chain[2], wrist, pole);                          // keeps the hand's turn
      if (before) chain.forEach((b, i) => b.quaternion.copy(before[i].slerp(b.quaternion, w)));
      (reach = reach || {})[limb] = w < 1 ? 0 : spacePos(v, chain[2]).distanceTo(wrist);
    }
    if (!only) {
      e.reach = reach;
      if (reach) this.reach.set(sim.id, reach); else this.reach.delete(sim.id);
    } else if (reach) {
      e.reach = { ...(e.reach || {}), ...reach };
      this.reach.set(sim.id, { ...(this.reach.get(sim.id) || {}), ...reach });
    }
  }

  // Twist helpers: each follows its driver's turn about its own axis (ForearmTwist 0.5 x the hand, ShoulderTwist
  // -0.4 x the upper arm, ThighTwist -0.75 x the thigh when "Smooth hip twist" is on). A twist bone a key poses by
  // hand stops following. Recorded as an absolute layer, so it never ends up in a key.
  twist(e) {
    const { sim, v } = e;
    const b = simBody(sim);
    if (b.twist === false) return;
    const ov = this.overrides.get(sim.id), ovRot = ov && ov.pose && ov.pose.rot;
    for (const t of TWIST) {
      if (t.opt && !b[t.opt]) continue;
      const bone = v.byName[t.bone], drv = v.byName[t.driver];
      if (!bone || !drv) continue;
      if ((ovRot && ovRot[t.bone]) || this._handKeyed(sim, t.bone)) continue;
      // turned by hand since this frame's helper was set (the rings are on the twist bone itself): leave it
      const d = v.layerDelta && v.layerDelta.get(t.bone), rest = v.restByName[t.bone].quat;
      if (d && d.abs) {
        _tq.copy(rest).multiply(d.q);
        const q = bone.quaternion, dot = Math.abs(_tq.x * q.x + _tq.y * q.y + _tq.z * q.z + _tq.w * q.w) / ((_tq.length() * q.length()) || 1);
        if (dot < 1 - 1e-12) continue;
      }
      const a = t.ratio * twistAngle(v.restByName[t.driver].quat, drv.quaternion, _X);
      _tq.setFromAxisAngle(_X, a);
      bone.quaternion.copy(v.restByName[t.bone].quat).multiply(_tq);
      if (v.setLayer) v.setLayer(t.bone, _tq, null);
    }
  }
  // Does any body key pose this twist bone by hand? (A plain look-up per key: always current, even for a key edited
  // in place, and far cheaper than the rest of the frame.)
  _handKeyed(sim, bone) {
    for (const k of sim.keys || []) if (!k.faceOnly && k.pose && k.pose.rot && k.pose.rot[bone]) return true;
    return false;
  }

  // Pass A for one sim: keys, face keys, early motion layers, fixed pins.
  body(e, frame, all, useOverrides = true) {
    const p = this.project, { sim, v } = e;
    const b = simBody(sim);
    v.setTongue(b.tongue);
    // posing by hand shows the keys as they are (no follow-through): what the gizmo turns is what gets keyed
    const pose = this.editing === sim.id ? this.keyed(sim, frame, useOverrides) : this.lagged(sim, frame, useOverrides);
    v.resetPose();
    if (pose) v.setPose(pose);
    v.setFaceBones(this.keyedFace(sim, frame, useOverrides));
    applyErection(v, b, frame);          // hard, soft, or growing between two times (erection.js)
    if (this.editing === sim.id) { this.pins(e, frame); return; }
    const ctx = { frame, length: p.length, fps: p.fps || 30, loop: p.loop, others: all.filter(x => x !== e) };
    for (const l of (sim.layers || []).filter(l => l.on)) if (!isLate(l)) applyLayer(v, l, ctx);
    this.pins(e, frame);
  }

  // Pass B for one sim (needs every sim's pass-A pose): holds, hand layers, twist helpers, face.
  // `holds`: false when the caller already ran every sim's holds (holdsAll), true when this sim is done on its own.
  late(e, frame, all, holds = true) {
    const p = this.project, { sim, v } = e;
    const style = faceStyleOf(p), creator = style !== 'classic';
    v.faceStyle = style;
    if (holds) this.holds(e, frame, all);
    const sliders = evaluateFace(sim.keys, frame, p.length, p.loop);
    if (this.editing === sim.id) {
      // posing by hand: the twist helpers and the face sliders stay visible (the automatic layer keeps them out of
      // the keys); motions, talking, blinking, openings and physics pause
      this.twist(e);
      applyFace(v, sliders, style);
      if (creator) clampFace(v);
      this.lastFace.set(sim.id, sliders);
      return;
    }
    // the late motions: hand motions first (on the posed, pinned and holding arm), then look-at (it answers with the
    // eyes' share for the face), then tremble and any other late motion (a held hand only shakes a little)
    let look = null;
    const layers = sim.layers;
    if (layers && layers.length) {
      const ctx = { frame, length: p.length, fps: p.fps || 30, loop: p.loop, others: all.filter(x => x !== e) };
      for (const l of layers) if (l.on && MOTIONS[l.type] && MOTIONS[l.type].group === 'Hands') applyLayer(v, l, ctx);
      for (const l of layers) if (l.on && l.type === 'look' && MOTIONS.look) { const r = applyLayer(v, l, ctx); if (r && typeof r === 'object') look = r; }
      for (const l of layers) if (l.on && isLate(l) && l.type !== 'look' && MOTIONS[l.type].group !== 'Hands') applyLayer(v, l, ctx);
    }
    this.twist(e);
    // talking and blinking give way where the hand-posed face already has the mouth open or the eyes shut
    const k = creator ? keyedAmounts(v) : null;
    // talking lasts each voice line's real length in creator-style projects (classic ones keep the old rule exactly)
    let talk = talkAt(sim, frame, p.length, p.loop, p.fps, style), blink = blinkAt(sim, frame, p.length, p.fps);
    if (k && talk && k.jaw > 0) talk = fadeOverlay(talk, 1 - k.jaw);
    if (k && blink && k.lids > 0) blink = fadeOverlay(blink, 1 - k.lids);
    let face = mergeFace(mergeFace(sliders, talk), blink);
    if (look) face = withLook(face, look);
    this.lastFace.set(sim.id, face);
    applyFace(v, face, style);
    if (creator) clampFace(v);
  }

  // Every sim's holds (the start of pass B), in an order where a hand that holds a partner's arm or leg waits until
  // that partner's own holds have placed that arm or leg (her hand on his shoulder while his hands hold her hips:
  // his arm first). Two holds on each other's held limbs just go in the listed order.
  holdsAll(all, frame) {
    if (this._holdAt) this._holdAt.clear();                   // holdsAfter only looks at the holds solved here
    const isH = x => !!(x && !Array.isArray(x) && x.sim && x.bone && !pinAt(x));
    const held = all.filter(e => e.sim.pins && Object.values(e.sim.pins).some(isH));
    for (const e of all) if (!held.includes(e)) { e.reach = null; this.reach.delete(e.sim.id); }
    if (!held.length) return;
    if (held.length === 1) { this.holds(held[0], frame, all); return; }
    const chain = new Map(held.map(e => [e.sim.id, new Set(Object.entries(e.sim.pins).filter(([, x]) => isH(x)).flatMap(([l]) => LIMBS[l] || []))]));
    const waits = new Map(held.map(e => [e, Object.values(e.sim.pins).filter(isH).filter(x => x.sim !== e.sim.id && chain.has(x.sim) && chain.get(x.sim).has(x.bone)).map(x => x.sim)]));
    const done = new Set(), left = [...held];
    while (left.length) {
      let i = left.findIndex(e => waits.get(e).every(id => done.has(id)));
      if (i < 0) i = 0;                                      // they wait for each other: the listed order
      const e = left.splice(i, 1)[0];
      this.holds(e, frame, all);
      done.add(e.sim.id);
    }
  }

  // The end of pass B: a hold whose partner moved the held part again after the holds were solved (a look-at turns
  // his head, a tremble shakes her legs, a hand motion moves an arm) is solved once more on that final pose, so a
  // palm on his neck stays on his neck while he turns to look. The holder's twist helpers follow.
  holdsAfter(all, frame) {
    if (!this._holdAt || !this._holdAt.size) return;
    for (const e of all) {
      const pins = e.sim.pins;
      if (!pins) continue;
      let again = false;
      for (const limb in pins) {
        const h = pins[limb];
        if (!h || Array.isArray(h) || !h.sim || !h.bone || pinAt(h)) continue;
        const was = this._holdAt.get(e.sim.id + '|' + limb), other = was && all.find(x => x.sim.id === h.sim);
        const ab = other && other.v.bone(h.bone);
        if (!ab) continue;
        ab.updateWorldMatrix(true, false);
        const now = ab.matrixWorld.elements;
        let moved = false;
        for (let i = 0; i < 16; i++) if (Math.abs(now[i] - was.m[i]) > 1e-7) { moved = true; break; }
        if (!moved) continue;
        // from the arm as it was before its hold (so a hold that fades in is blended once, not twice)
        LIMBS[limb].forEach((n, i) => { const b = e.v.bone(n); if (b && was.free[i]) b.quaternion.copy(was.free[i]); });
        this.holds(e, frame, all, limb);
        again = true;
      }
      if (again) this.twist(e);
    }
  }

  // Both passes for one sim, for callers that pose one sim on its own (the others keep what they have).
  one(e, frame, all, useOverrides = true) {
    this.body(e, frame, all, useOverrides);
    this.late(e, frame, all);
  }

  // Openings. Every consumer reads world positions through getWorldPosition / skinPointWorld, which bring their
  // own bone chain up to date, so the whole skeleton's matrices are not recomputed here.
  // frame: the lips pull along with what moves in the mouth (see lipPull), from the depths the last simulate() saw.
  openings(all, frame = null) {
    const res = measure(all);
    all.forEach((e, i) => {
      const o = simBody(e.sim).open;
      this.lastOpen.set(e.sim.id, res[i]);
      if (o.on && this.editing !== e.sim.id) for (const [hole, r] of Object.entries(res[i])) {
        if (o[hole] === false) continue;
        const pull = hole === 'mouth' && o.lipPull !== false ? this.lipPull(e.sim.id, frame) : 0;
        applyOpen(e.v, hole, r.open, pull ? { ...r, pull } : r);
      }
      followJaw(e.v);
    });
    return res;
  }

  // -1..1: the lips cling to what is in the mouth - positive while it pulls back out (they stretch forward), negative
  // while it pushes in (they tuck in a little). From the change in depth around the frame (20 cm/s = fully).
  lipPull(simId, frame) {
    const d = this.mouthDepth.get(simId), p = this.project;
    if (!d || frame === null || frame === undefined || d.length < 3) return 0;
    const n = d.length, f = Math.round(frame);
    const at = k => d[p.loop ? ((k % n) + n) % n : Math.max(0, Math.min(n - 1, k))];
    if (!(at(f) > 0.004)) return 0;
    const speed = (at(f + 2) - at(f - 2)) / 4 * (p.fps || 30);
    return THREE.MathUtils.clamp(-speed / 0.2, -0.6, 1);
  }

  // ---------------------------------------------------------------- the whole frame
  // `overrides`: show a pending (unkeyed) pose - only while paused, where it is being worked on.
  apply(frame, { physics = true, overrides = !this.app.playing } = {}) {
    const all = this.entries();
    for (const e of all) this.body(e, frame, all, overrides);     // pass A
    this.holdsAll(all, frame);                                    // pass B: holds first,
    for (const e of all) this.late(e, frame, all, false);         // then the rest,
    this.holdsAfter(all, frame);                                  // and holds on parts that moved since
    this.openings(all, frame);
    if (physics) {
      const p = this.project;
      for (const e of all) if (this.editing !== e.sim.id) applyFrame(e.v, this.phys.get(e.sim.id), frame, p.length, p.loop);
    }
    return all;
  }

  // ---------------------------------------------------------------- physics
  // Re-simulate when anything that moves the bodies changed (cheap: one pass of the stages per frame).
  // Pending poses are not part of it: the simulation never uses them. Faces are left out (editing a face never
  // re-runs physics): face-only keys, sliders and face bones do not move breasts, butt or penis.
  signature() {
    const p = this.project;
    return JSON.stringify([p.length, p.loop, p.fps, p.autoCurve, p.sims.map(s => [s.id, s.frame, (s.keys || []).filter(k => !k.faceOnly).map(k => [k.frame, k.ease, k.pose, k.curve]),
      s.layers, s.lag, s.pins, s.body, (s.sounds || []).filter(x => x.kind === 'voice')])]);
  }

  simulateIfNeeded(force = false) {
    const sig = this.signature();
    if (!force && sig === this.physKey) return false;
    this.physKey = sig;
    this.simulate();
    return true;
  }

  simulate() {
    const p = this.project, n = Math.max(1, p.length);
    const all = this.entries();
    const plan = all.map(e => ({ e, parts: partsFor(e.v, simBody(e.sim).physics) })).filter(x => x.parts.length);
    this.phys.clear();
    const mouthOn = all.map(e => { const o = simBody(e.sim).open; return o.on && o.mouth !== false && o.lipPull !== false; });
    if (!plan.length && !mouthOn.some(Boolean)) { this.mouthDepth.clear(); return; }
    const depth = all.map(() => new Float32Array(n));
    const saved = this.editing; this.editing = null;
    try {
      const samples = plan.map(() => new Array(n));
      for (let k = 0; k < n; k++) {
        for (const e of all) this.body(e, k, all, false);
        this.holdsAll(all, k);
        for (const e of all) this.late(e, k, all, false);
        this.holdsAfter(all, k);
        const res = this.openings(all, k);
        res.forEach((r, i) => { depth[i][k] = r.mouth ? r.mouth.depth : 0; });
        plan.forEach((x, i) => {
          const s = {};
          for (const part of x.parts) for (const bone of part.bones) {
            const b = x.e.v.byName[bone];
            s[bone] = { pos: b.getWorldPosition(new THREE.Vector3()), parentQ: b.parent.getWorldQuaternion(new THREE.Quaternion()) };
          }
          samples[i][k] = s;
        });
      }
      plan.forEach((x, i) => this.phys.set(x.e.sim.id, simulate(x.parts, samples[i], p.fps || 30, !!p.loop)));
      // the measured depth jitters from frame to frame: smoothed, so the lips move with the strokes, not the jitter
      const smooth = d => d.map((_, k) => {
        let sum = 0, w = 0;
        for (let j = -3; j <= 3; j++) {
          const q = p.loop ? ((k + j) % n + n) % n : Math.max(0, Math.min(n - 1, k + j));
          const wt = 4 - Math.abs(j);
          sum += d[q] * wt; w += wt;
        }
        return sum / w;
      });
      this.mouthDepth = new Map(all.map((e, i) => [e.sim.id, smooth(depth[i])]));
    } finally { this.editing = saved; }
  }

  // ---------------------------------------------------------------- export
  // Every frame of every sim, with all layers, as local bone transforms for the game's clip.
  // Recorded: the body, every face bone, the twist helpers, the automatic bones, and any other bone a key poses.
  // flags[i] = {mouthMoves, tongueUsed}:
  //   mouthMoves - the clip shapes the mouth, so the game must not lip-sync over it: the face shown (keys, or
  //                talking while a voice plays) has open / pout / bite / tongue above 0.05 at some frame, the mouth
  //                opens around something (above 0.05, with that opening switched on), or the mouth bones really
  //                move or are held open (see MOUTH_MOVE / MOUTH_HOLD) - hand-posed jaw, lips, corners and tongue
  //                included. A ready pose's slightly-off closed jaw does not count.
  //   tongueUsed - the WickedWhims tongue is used (it is hidden in the game otherwise).
  bake() {
    const p = this.project, n = p.length;
    this.simulateIfNeeded(true);
    const saved = this.editing; this.editing = null;
    const all = this.entries();
    const named = new Set();          // every bone any key poses (body extras, expert bones, face bones)
    for (const e of all) for (const k of e.sim.keys || []) for (const src of [k.pose, k.faceBones]) if (src)
      for (const part of [src.rot, src.pos]) for (const nm in part || {}) named.add(nm);
    const rotBones = [...new Set([...POSABLE, ...FACE_CHANNEL, ...TWIST.map(t => t.bone), ...AUTO, 'b__Penis_Tip', ...named])];
    const alwaysPos = new Set([...HIPS, ...AUTO, 'b__Tounge__1']);
    // other bones keep their place too (stretched bones from imported clips, moved face bones); dropped again below
    // when unmoved
    const posBones = [...new Set([...alwaysPos, ...POSABLE, ...FACE_CHANNEL, ...named])];
    const tracks = all.map(() => ({}));
    all.forEach((e, i) => {
      for (const b of rotBones) if (e.v.byName[b]) tracks[i][b] = { r: [] };
      for (const b of posBones) if (e.v.byName[b]) (tracks[i][b] = tracks[i][b] || {}).t = [];
      // a growing erection scales the penis base (exporter: the bone's scale channel)
      if (hasGrow(simBody(e.sim)) && e.v.byName.b__Penis_Base) (tracks[i].b__Penis_Base = tracks[i].b__Penis_Base || {}).s = [];
    });
    const openLog = all.map(() => []);
    const faceMouth = all.map(() => 0);     // the most any mouth-shaping face channel shows over the loop
    try {
      for (let k = 0; k < n; k++) {
        this.apply(k, { physics: true, overrides: false });
        all.forEach((e, i) => {
          for (const [b, tr] of Object.entries(tracks[i])) {
            const bone = e.v.byName[b];
            if (tr.r) tr.r.push(bone.quaternion.toArray());
            if (tr.t) tr.t.push(bone.position.toArray());
            if (tr.s) tr.s.push(bone.scale.toArray());
          }
          openLog[i].push(this.lastOpen.get(e.sim.id));
          const face = this.lastFace.get(e.sim.id);
          if (face) for (const c of MOUTH_FACE) faceMouth[i] = Math.max(faceMouth[i], face[c] || 0);
        });
      }
    } finally { this.editing = saved; }
    // a bone that never leaves its rest place needs no position track (the game uses the rig's)
    all.forEach((e, i) => {
      for (const [b, tr] of Object.entries(tracks[i])) {
        if (!tr.t || alwaysPos.has(b)) continue;
        const r = e.v.restByName[b].pos;
        if (tr.t.every(t => t[0] === r.x && t[1] === r.y && t[2] === r.z)) delete tr.t;
      }
    });
    const flags = all.map((e, i) => {
      const rest = e.v.restByName, tr = tracks[i];
      // the tongue pushed out by the sliders or posed by hand (more than 1 mm)
      const tonguePosed = k => k.faceBones && k.faceBones.pos && TONGUE.some(b => {
        const t = k.faceBones.pos[b], r = rest[b] && rest[b].pos;
        return t && r && (t[0] - r.x) ** 2 + (t[1] - r.y) ** 2 + (t[2] - r.z) ** 2 > TONGUE_POS;
      });
      const byFace = e.sim.keys.some(k => (k.face && (k.face.tongue || 0) > 0.05) || tonguePosed(k));
      const byBones = TONGUE.some(b => awayFromRest(tr[b], rest[b], TONGUE_ROT, TONGUE_POS));
      // licking: this sim's tongue measured at someone's opening
      const licks = openLog.some((log, j) => j !== i && log.some(o => o && Object.values(o).some(h => h && h.by === 'tongue' && h.from === e.sim.id && h.open > 0.5)));
      const tongueUsed = simBody(e.sim).tongue !== false && (byFace || byBones || licks);
      // the mouth opens around something (only when that opening is switched on - otherwise it stays as keyed)
      const opening = simBody(e.sim).open;
      const opensMouth = opening.on && opening.mouth !== false && openLog[i].some(x => x && x.mouth && x.mouth.open > 0.05);
      // a used tongue is a mouth action too (a French kiss, licking): lip-sync would shut the mouth over it
      const mouthMoves = faceMouth[i] > 0.05 || opensMouth || tongueUsed || MOUTH.some(b => mouthTrackUsed(tr[b], rest[b]));
      return { mouthMoves, tongueUsed };
    });
    return { tracks, openLog, sims: all.map(e => e.sim), flags };
  }
}

// Motion layers that run in pass B: hand motions (they act on the posed arm, after pins and holds) and any motion
// marked `late` (look-at, tremble).
function isLate(l) { const m = MOTIONS[l.type]; return !!m && (m.group === 'Hands' || !!m.late); }

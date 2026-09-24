// Hold on to the partner (spec_bodies section 4, spec_editing 9.2 / 10.4): a hand (or foot) dropped on a partner's
// skin holds on - it follows that body through every ride or thrust, the palm on the skin, the elbow bending by
// itself. Also pins for part of the loop and "Let go, keep the look". Plain functions on the app, shared by the
// view (interact.js), the inspector's Pins card, Magic's default holds and the app methods features/contact.js
// adds (app.makeHold, app.holdNamed, app.bakePin, ...).
import * as THREE from 'three';
import { LIMBS, LIMB_LABEL, PALM, GRAB, GRAB_MENU, grabLabel, pinAt, isHold } from './bones.js';
import { spacePos, spaceQuat } from './posemath.js';
import { nearestSkin, anchorFor } from './skin.js';
import { shapeQuats } from './hands.js';
import { evaluate, keyFramesFor, sortKeys } from './animation.js';
import { toast } from './ui.js';
import { $t } from './i18n.js';

const LIMB_SIDE = limb => limb[0];
export const isHandLimb = limb => !!PALM[limb];

// Where a limb holds from: the palm centre of a hand, the foot bone of a foot (world space, current pose).
export function limbPoint(v, limb) {
  const n = PALM[limb] && v.bone(PALM[limb]) ? PALM[limb] : LIMBS[limb][2];
  return v.worldPos(n);
}

// The other sims that can be held (shown, with a view).
function partnerEntries(app, simId) {
  const out = [];
  for (const s of app.store.project.sims) {
    if (s.id === simId || s.visible === false) continue;
    const v = app.simViews.get(s.id);
    if (v && v.group.visible) out.push({ sim: s, v });
  }
  return out;
}
const entryOf = (app, id) => { const s = app.store.sim(id), v = app.simViews.get(id); return s && v ? { sim: s, v } : null; };

// A short description of a hold, for chips and the view's hover line: "holding Female 1's hip".
export function holdText(app, pin) {
  const o = app.store.sim(pin.sim);
  return $t('holds.holding', { who: o ? o.label : $t('holds.partner'), part: pin.label || $t('holds.body') });
}

// ---------------------------------------------------------------- taking hold
// Hold on to `other` ({sim, v}) at skin point `hit` ({point, normal, boneIndex} in world space, from nearestSkin).
// The hand keeps its turn relative to the bone it holds, with the palm laid flat on the skin; the fingers relax onto
// the skin ("Flat on skin" at 70%). Keeps a range (from / to / fade) the limb had.
export function makeHold(app, simId, limb, other, hit, { checkpoint = true, quiet = false, label = null, shape = true, keep = null } = {}) {
  const sim = app.store.sim(simId), v = app.simViews.get(simId), ov = other && other.v;
  if (!sim || !v || !ov || !hit || !LIMBS[limb]) return null;
  if (checkpoint) app.store.checkpoint($t('holds.hold_on'));
  const anchor = anchorFor(ov, hit.boneIndex), ab = ov.bone(anchor);
  ab.updateWorldMatrix(true, false);
  const aQ = ab.getWorldQuaternion(new THREE.Quaternion()), aQi = aQ.clone().invert();
  const hand = v.bone(LIMBS[limb][2]);
  let handW = hand.getWorldQuaternion(new THREE.Quaternion());
  if (PALM[limb]) {
    // lay the palm flat on the skin (the palm is the hand's +Y)
    const palmN = new THREE.Vector3(0, 1, 0).applyQuaternion(handW);
    handW = new THREE.Quaternion().setFromUnitVectors(palmN, hit.normal.clone().negate()).multiply(handW);
  }
  const old = sim.pins && sim.pins[limb];
  const range = keep || (old && !Array.isArray(old) && old.from !== undefined ? { from: old.from, to: old.to, fade: old.fade } : null);
  sim.pins = sim.pins || {};
  sim.pins[limb] = {
    sim: other.sim.id, bone: anchor,
    off: ab.worldToLocal(hit.point.clone()).toArray(),
    n: hit.normal.clone().applyQuaternion(aQi).normalize().toArray(),
    rot: aQi.multiply(handW).normalize().toArray(),
    label: label || grabLabel(ov, hit.point, anchor),
    ...(range && range.from !== undefined ? range : {}),
  };
  if (shape && PALM[limb]) relaxFingers(app, sim, v, limb, !range);
  app.applyPoses(false);
  app.interact && app.interact.refreshHandles();
  app.afterEdit();
  if (!quiet) toast($t('holds.is_holding_s_it_follows', { v: LIMB_LABEL[limb], simLabel: other.sim.label, vLabel: sim.pins[limb].label }), 'ok');
  return sim.pins[limb];
}

// The fingers ease onto the skin: "Flat on skin" at 70%, in every key (a hold for the whole loop) or in the key here.
function relaxFingers(app, sim, v, limb, everyKey) {
  const side = LIMB_SIDE(limb), target = shapeQuats(v, side, 'flat');
  const f = Math.round(app.store.frame);
  const keys = sim.keys.filter(k => !k.faceOnly && k.pose && (everyKey || k.frame === f));
  const q = new THREE.Quaternion();
  const ease = pose => {
    pose.rot = pose.rot || {};
    for (const [name, t] of Object.entries(target)) {
      const r = v.restByName[name];
      q.fromArray(pose.rot[name] || [r.quat.x, r.quat.y, r.quat.z, r.quat.w]).normalize().slerp(t, 0.7).normalize();
      pose.rot[name] = q.toArray();
    }
  };
  keys.forEach(k => ease(k.pose));
  const ov = app.pipeline.overrides.get(sim.id);
  if (ov && ov.pose && !ov.poseSnapshot && ov.frame === f) ease(ov.pose);
}

// Drop a hand or foot on the nearest partner's skin within `maxDist` (the Drag tool's release: 4 cm; "Hold
// nearest": 30 cm). A held limb dragged away from every partner lets go. -> the hold, 'let go', or null.
// A drop also counts when it looks right on screen (`fromDrag`): the partner's skin seen through the palm, or under
// the mouse pointer, within 4 cm of the palm across the view and 20 cm in depth (the view hides depth - a hand that
// sits on his shoulder on screen may be 13 cm in front of it).
export function tryHold(app, simId, limb, { maxDist = 0.04, fromDrag = false, quiet = false, pointer = null } = {}) {
  const sim = app.store.sim(simId), v = app.simViews.get(simId);
  if (!sim || !v || !LIMBS[limb]) return null;
  const at = limbPoint(v, limb);
  let best = null;
  const partners = partnerEntries(app, simId);
  for (const o of partners) {
    const hit = nearestSkin(o.v, at, maxDist);
    if (hit && (!best || hit.dist < best.hit.dist)) best = { o, hit };
  }
  if (!best && fromDrag) best = viewHit(app, at, partners, pointer);
  const had = isHold(sim.pins && sim.pins[limb]);
  if (!best) {
    if (had && fromDrag) {
      delete sim.pins[limb];
      app.applyPoses(false);
      app.interact && app.interact.refreshHandles();
      if (!quiet) toast($t('holds.let_go', { v: LIMB_LABEL[limb] }));
      return $t('holds.let_go_2');
    }
    if (!fromDrag && !quiet) toast($t('holds.no_partner_within_cm_of', { maxDist: Math.round(maxDist * 100), v: LIMB_LABEL[limb].toLowerCase() }));
    return null;
  }
  return makeHold(app, simId, limb, best.o, best.hit, { checkpoint: !fromDrag, quiet });
}

export const holdNearest = (app, simId, limb) => tryHold(app, simId, limb, { maxDist: 0.3 });

// The partner's skin a dropped palm is seen on: along the camera's ray through the palm and the ray under the mouse
// pointer, every place the ray enters or leaves a partner's body; the one nearest the palm in depth wins, when the
// palm is within `across` of that ray and within `depth` of the skin along it. -> {o, hit} (hit as nearestSkin gives
// it) or null.
const _ray = new THREE.Raycaster();
export function viewHit(app, at, partners, pointer = null, { across = 0.04, depth = 0.2 } = {}) {
  const vp = app.vp, cam = vp && vp.camera;
  if (!cam || !partners.length) return null;
  cam.updateMatrixWorld();
  const rays = [];
  const eye = new THREE.Vector3().setFromMatrixPosition(cam.matrixWorld);
  rays.push(new THREE.Ray(eye.clone(), at.clone().sub(eye).normalize()));
  if (pointer && vp.canvas && Number.isFinite(pointer.clientX)) {
    const r = vp.canvas.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      _ray.setFromCamera(new THREE.Vector2(((pointer.clientX - r.left) / r.width) * 2 - 1, -((pointer.clientY - r.top) / r.height) * 2 + 1), cam);
      rays.push(_ray.ray.clone());
    }
  }
  const meshes = [];
  for (const o of partners) for (const m of o.v.meshes) if (m.visible && !['penis_hard', 'tongue'].includes(m.userData.role)) meshes.push([m, o]);
  if (!meshes.length) return null;
  // a skinned mesh keeps the bounds of the pose it was first tested in: this pose's, please
  for (const [m, o] of meshes) { o.v.group.updateMatrixWorld(true); m.boundingSphere = null; m.boundingBox = null; }
  const owner = new Map(meshes);
  let best = null;
  for (const ray of rays) {
    if (ray.distanceToPoint(at) > across) continue;             // the palm is not under this ray on screen
    const t = at.clone().sub(ray.origin).dot(ray.direction);      // the palm's depth along the ray
    _ray.set(ray.origin, ray.direction);
    _ray.far = t + depth + 0.01;
    for (const h of _ray.intersectObjects(meshes.map(x => x[0]), false)) {
      const gap = Math.abs(h.distance - t);
      if (gap > depth || (best && gap >= best.gap)) continue;
      best = { gap, o: owner.get(h.object), point: h.point.clone() };
    }
  }
  _ray.far = Infinity;
  if (!best) return null;
  const hit = nearestSkin(best.o.v, best.point, 0.03);
  return hit ? { o: best.o, hit } : null;
}

// Hold a named part ("hip", "lower back"...) of a partner: the grab point of that part nearest to the limb (or the
// given `slot`), snapped to the skin.
export function holdNamed(app, simId, limb, otherId, grabKey, { slot = null, checkpoint = true, quiet = false } = {}) {
  const me = entryOf(app, simId), o = entryOf(app, otherId);
  if (!me || !o || !LIMBS[limb]) return null;
  const slots = (slot ? [slot] : GRAB[grabKey] || []).filter(s => o.v.bone(s));
  if (!slots.length) return null;
  const at = limbPoint(me.v, limb);
  let best = slots[0], bd = Infinity;
  for (const s of slots) { const d = o.v.worldPos(s).distanceTo(at); if (d < bd) { bd = d; best = s; } }
  const sw = o.v.worldPos(best);
  const hit = nearestSkin(o.v, sw, 0.06) || nearestSkin(o.v, sw, 0.15);
  if (!hit) { if (!quiet) toast($t('holds.couldn_t_find_s', { simLabel: o.sim.label, grabKey }), 'err'); return null; }
  return makeHold(app, simId, limb, o, hit, { checkpoint, quiet, label: grabKey });
}

// The grab points a limb can reach from where the sim is now (for the "Hold her..." menu): [{key, dist}] - the
// parts with a point within 105% of the arm's (leg's) length from the shoulder (hip); `dist` is from the hand
// (foot) now, so the nearest parts can be picked.
export function reachableGrabs(app, simId, limb, otherId) {
  const me = entryOf(app, simId), o = entryOf(app, otherId);
  if (!me || !o || !LIMBS[limb]) return [];
  const [a, b, c] = LIMBS[limb].map(n => me.v.bone(n));
  if (!a || !b || !c) return [];
  const len = spacePos(me.v, a).distanceTo(spacePos(me.v, b)) + spacePos(me.v, b).distanceTo(spacePos(me.v, c)) + (PALM[limb] ? 0.08 : 0);
  const root = me.v.worldPos(LIMBS[limb][0]), tip = limbPoint(me.v, limb);
  const out = [];
  for (const key of GRAB_MENU) {
    let d = Infinity, reach = Infinity;
    for (const s of GRAB[key]) if (o.v.bone(s)) { const w = o.v.worldPos(s); reach = Math.min(reach, w.distanceTo(root)); d = Math.min(d, w.distanceTo(tip)); }
    if (reach <= len * 1.05) out.push({ key, dist: d });
  }
  return out;
}

export function letGo(app, simId, limb, { checkpoint = true, quiet = false } = {}) {
  const sim = app.store.sim(simId);
  if (!sim || !sim.pins || !sim.pins[limb]) return false;
  if (checkpoint) app.store.checkpoint($t('holds.let_go_3'));
  const was = sim.pins[limb];
  delete sim.pins[limb];
  app.applyPoses(false);
  app.interact && app.interact.refreshHandles();
  app.afterEdit();
  if (!quiet) toast(isHold(was) ? $t('holds.let_go', { v: LIMB_LABEL[limb] }) : $t('holds.is_free', { v: LIMB_LABEL[limb] }));
  return true;
}

// After the whole animation was mirrored (both sims, left <-> right): the hold's offsets are found again against
// the mirrored partner from where the hand is at frame 0 (spec_editing 9.3). Keeps the range and the part's name.
export function rebindHold(app, simId, limb) {
  const sim = app.store.sim(simId), me = entryOf(app, simId);
  const h = sim && sim.pins && sim.pins[limb];
  if (!me || !isHold(h)) return null;
  const o = entryOf(app, h.sim);
  if (!o) { delete sim.pins[limb]; return null; }
  delete sim.pins[limb];
  const frame = app.store.frame;
  try {
    app.store.frame = 0;
    app.pipeline.apply(0, { physics: false, overrides: false });
    const at = limbPoint(me.v, limb);
    const hit = nearestSkin(o.v, at, 0.1);
    if (!hit) { sim.pins[limb] = h; return h; }
    const keep = h.from !== undefined ? { from: h.from, to: h.to, fade: h.fade } : null;
    return makeHold(app, simId, limb, o, hit, { checkpoint: false, quiet: true, shape: false, keep, label: h.label });
  } finally {
    app.store.frame = frame;
    app.applyPoses(false);
  }
}

// Drop holds whose partner is gone (a removed sim, a loaded project with a dangling hold). -> how many.
export function cleanHolds(project, goneId = null) {
  let n = 0;
  const ids = new Set((project && project.sims || []).map(s => s.id));
  for (const s of (project && project.sims) || []) {
    for (const [limb, p] of Object.entries(s.pins || {})) {
      if (!isHold(p)) continue;
      if (p.sim === goneId || !ids.has(p.sim) || p.sim === s.id) { delete s.pins[limb]; n++; }
    }
  }
  return n;
}

// ---------------------------------------------------------------- pins for part of the loop
// Pin a limb where it is now, only from `from` to `to` (inclusive; wrapping when the animation loops), fading in
// and out over `fade` frames. A hold keeps holding, just for that part. Without a `fade`, it is as long as a smooth
// change needs: the arm turns at most about 3 degrees a frame on its way in and out (3-15 frames).
export function setPin(app, simId, limb, { from, to, fade } = {}) {
  const sim = app.store.sim(simId), v = app.simViews.get(simId);
  if (!sim || !v || !LIMBS[limb]) return null;
  app.store.checkpoint($t('holds.pin_for_part_of_loop'));
  sim.pins = sim.pins || {};
  const old = sim.pins[limb];
  const ranged = from !== undefined && to !== undefined;
  let pin;
  if (isHold(old)) {
    pin = old;
    if (!ranged) { delete old.from; delete old.to; delete old.fade; } else Object.assign(old, { from, to, fade: fade ?? 3 });
  } else {
    const at = pinAt(old) || spacePos(v, v.bone(LIMBS[limb][2])).toArray();
    pin = sim.pins[limb] = ranged ? { at: at.slice(), from, to, fade: fade ?? 3 } : at.slice();
  }
  if (ranged && fade === undefined) pin.fade = smoothFade(app, sim, v, limb, pin);
  app.applyPoses(false);
  app.interact && app.interact.refreshHandles();
  app.afterEdit();
  const L = app.store.project.length;
  toast(!ranged ? $t(isHold(pin) ? 'holds.holds_whole_loop' : 'holds.pinned_whole_loop', { limb: LIMB_LABEL[limb] })
    : $t(isHold(pin) ? 'holds.holds_range' : 'holds.pinned_range', { limb: LIMB_LABEL[limb], from: (from / 30).toFixed(2), to: (Math.min(to, L - 1) / 30).toFixed(2), fade: pin.fade }), 'ok');
  return pin;
}
export const setPinRange = (app, simId, limb, from, to, fade) => setPin(app, simId, limb, { from, to, fade });

// How many frames a ranged pin or hold needs to ease in and out without the arm (leg) jumping: the chain's turn
// between free and pinned at both ends of the range, at most ~3 degrees a frame (the ease's steepest part is 1.5x
// its average), 3-15 frames.
function smoothFade(app, sim, v, limb, pin) {
  const pl = app.pipeline, chain = LIMBS[limb].map(n => v.bone(n));
  const saved = pl.editing, frame = app.store.frame;
  pl.editing = null;
  let most = 0;
  try {
    for (const f of [pin.from, pin.to]) {
      pl.apply(f, { physics: false, overrides: false });
      const held = chain.map(b => spaceQuat(v, b));
      delete sim.pins[limb];
      pl.apply(f, { physics: false, overrides: false });
      const free = chain.map(b => spaceQuat(v, b));
      sim.pins[limb] = pin;
      held.forEach((q, i) => { most = Math.max(most, THREE.MathUtils.radToDeg(q.angleTo(free[i]))); });
    }
  } finally {
    sim.pins[limb] = pin;
    pl.editing = saved;
    app.store.frame = frame;
  }
  return Math.max(3, Math.min(15, Math.ceil(most * 1.5 / 2.5)));
}

// ---------------------------------------------------------------- "Let go, keep the look" (spec_editing 10.4)
// The pinned or holding arm / leg becomes keys: every frame is worked out as it plays with the pin on, and keys are
// added only where needed so the limb stays within 0.25 degrees of where the pin held it; then the pin goes. The
// rest of the pose at a new key is exactly what the old keys showed there.
export function bakePin(app, simId, limb) {
  const sim = app.store.sim(simId), v = app.simViews.get(simId);
  const pin = sim && sim.pins && sim.pins[limb];
  if (!sim || !v || !pin || !LIMBS[limb]) return 0;
  const p = app.store.project, L = p.length, pl = app.pipeline;
  if (app.playing) app.setPlaying(false);
  app.store.checkpoint($t('holds.let_go_keep_look'));
  const chain = LIMBS[limb];
  const saved = pl.editing;
  pl.editing = null;
  pl.overrides.delete(simId);
  const all = pl.entries(), me = all.find(e => e.sim.id === simId);
  const oldBody = sim.keys.filter(k => !k.faceOnly && k.pose).map(k => ({ ...k }));
  const live = [], poses = [];
  try {
    for (let f = 0; f < L; f++) {
      for (const e of all) pl.body(e, f, all, false);             // keys, motions, fixed pins (pass A)
      if (isHold(pin)) {                                          // the hold as it plays: after every hold, on the
        pl.holdsAll(all, f);                                      // partner's final pose (its own motions done)
        for (const o of all) if (o !== me) pl.late(o, f, all, false);
        pl.holdsAfter(all, f);
      }
      live.push(chain.map(n => v.bone(n).quaternion.toArray()));
      const keyed = evaluate(oldBody, f, L, p.loop, p.autoCurve);
      const pose = { rot: { ...((keyed && keyed.rot) || {}) }, pos: { ...((keyed && keyed.pos) || {}) } };
      chain.forEach((n, i) => { pose.rot[n] = live[f][i]; });
      poses.push(pose);
    }
  } finally {
    pl.editing = saved;
  }
  // frames needed: every key there is, plus where the limb needs one (the chain within 0.25 degrees)
  const chainPoses = poses.map(ps => ({ rot: Object.fromEntries(chain.map(n => [n, ps.rot[n]])), pos: {} }));
  const need = new Set([...oldBody.map(k => k.frame).filter(f => f < L), ...keyFramesFor(chainPoses, chainPoses.map(() => null), !!p.loop)]);
  let added = 0;
  for (const f of [...need].sort((a, b) => a - b)) {
    const key = sim.keys.find(k => k.frame === f && !k.faceOnly && k.pose);
    if (key) { chain.forEach((n, i) => { key.pose.rot[n] = live[f][i]; }); continue; }
    const face = sim.keys.find(k => k.frame === f && k.faceOnly);
    if (face) { face.pose = poses[f]; delete face.faceOnly; face.type = 'breakdown'; added++; continue; }
    sim.keys.push({ frame: f, ease: 'linear', type: 'breakdown', pose: poses[f] });
    added++;
  }
  sortKeys(sim.keys);
  delete sim.pins[limb];
  if (app.refreshAll) app.refreshAll();
  app.interact && app.interact.refreshHandles();
  app.physicsChanged && app.physicsChanged();
  toast(added ? $t('holds.free_now_added', { limb: LIMB_LABEL[limb], added }) : $t('holds.free_now', { limb: LIMB_LABEL[limb] }), 'ok');
  return added;
}


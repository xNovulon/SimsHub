// Editing operations on project data (spec_editing section 4): select, move, stretch, reverse, delete, copy/paste,
// in-between keys, exaggerate, moving holds, loop tools, smooth, simplify, mirror and body parts.
// Pure: no scene and no DOM. Every function changes the project (or key list) it is given - the caller has made an
// undo checkpoint first - and returns a small report. Keys stay whole-body keys (key.pose), with the face channel
// (key.face sliders and key.faceBones) carried along untouched except where a tool says otherwise.
import * as THREE from 'three';
import * as A from './animation.js';
import * as B from './bones.js';
import { mirrorQuat } from './posemath.js';
import { FACE_SLIDERS } from './face.js';
import { $t } from './i18n.js';

const clone = x => (x === undefined ? x : typeof structuredClone === 'function' ? structuredClone(x) : JSON.parse(JSON.stringify(x)));
const mod = (a, n) => ((a % n) + n) % n;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const isBody = k => !!(k && !k.faceOnly && k.pose);
const hasFaceData = k => !!(k && ((k.face && Object.keys(k.face).length) || (k.faceBones && (Object.keys(k.faceBones.rot || {}).length || Object.keys(k.faceBones.pos || {}).length))));
const restRot = n => { const r = A.restOf(n); return r ? r.r : null; };
const restPos = n => { const r = A.restOf(n); return r ? r.t : null; };
const HIPS = B.HIPS || ['b__Spine0__', 'b__Pelvis__'];
const HIPS_SET = new Set(HIPS);
const DEG = 180 / Math.PI;
const _qa = new THREE.Quaternion(), _qb = new THREE.Quaternion();
const qAngle = (a, b) => { const d = Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]) / ((Math.hypot(a[0], a[1], a[2], a[3]) * Math.hypot(b[0], b[1], b[2], b[3])) || 1); return 2 * Math.acos(Math.min(1, d)); };

// ---------------------------------------------------------------- body parts (R2-2's bones.js has the final lists)
const FINGERS = s => ['Thumb', 'Index', 'Mid', 'Ring', 'Pinky'].flatMap(f => [0, 1, 2].map(k => `b__${s}_${f}${k}__`));
const ARM = s => [`b__${s}_Clavicle__`, `b__${s}_UpperArm__`, `b__${s}_ShoulderTwist__`, `b__${s}_Forearm__`, `b__${s}_ForearmTwist__`, `b__${s}_Hand__`];
const LEG = s => [`b__${s}_Thigh__`, `b__${s}_ThighTwist__`, `b__${s}_Calf__`, `b__${s}_Foot__`, `b__${s}_Toe__`];
const FALLBACK_PARTS = {
  all: B.POSABLE,
  upper: ['b__Spine0__', 'b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__', ...ARM('L'), ...ARM('R'), ...FINGERS('L'), ...FINGERS('R')],
  lower: ['b__Pelvis__', ...LEG('L'), ...LEG('R'), ...(B.PENIS || []).slice(0, 4)],
  hands: ['b__L_Hand__', 'b__R_Hand__', ...FINGERS('L'), ...FINGERS('R')],
  'L hand': ['b__L_Hand__', ...FINGERS('L')],
  'R hand': ['b__R_Hand__', ...FINGERS('R')],
  face: [],                                       // the face part is key.face + key.faceBones (plan 2.1)
};
// Jaw and tongue live only in key.faceBones (plan 2.1), so no body part lists them.
const noFace = list => (list || []).filter(n => !(B.FACE_SET || new Set()).has(n));
export const BODY_PARTS = Object.fromEntries(Object.entries({ ...FALLBACK_PARTS, ...(B.BODY_PARTS || {}) }).map(([k, v]) => [k, k === 'all' ? v : noFace(v)]));
export const PART_LABEL = B.PART_LABEL || { all: $t('keyops.whole_body'), upper: $t('keyops.upper_body'), lower: $t('keyops.lower_body'), hands: $t('keyops.both_hands'),
  'L hand': $t('keyops.left_hand'), 'R hand': $t('keyops.right_hand'), face: $t('keyops.face') };
export const partBones = part => (!part || part === 'all' ? null : new Set(BODY_PARTS[part] || []));
export const partHasFace = part => !part || part === 'all' || part === 'face';

// ---------------------------------------------------------------- ids (timeline selection, spec 2.5)
export const kid = (simId, frame) => `k|${simId}|${frame}`;
export const sndId = (simId, s) => `s|${simId}|${s.frame}|${s.name}`;
export const evId = ev => `e|${ev.id}`;
export function parseId(id) {
  const p = String(id).split('|');
  if (p[0] === 'k') return { kind: 'key', simId: p[1], frame: +p[2] };
  if (p[0] === 's') return { kind: 'sound', simId: p[1], frame: +p[2], name: p.slice(3).join('|') };
  if (p[0] === 'e') return { kind: 'event', id: p.slice(1).join('|') };
  return { kind: '?' };
}
export const allKeyIds = (project, simIds = null) => project.sims.filter(s => !simIds || simIds.includes(s.id)).flatMap(s => s.keys.map(k => kid(s.id, k.frame)));
export const columnIds = (project, frame) => project.sims.flatMap(s => s.keys.filter(k => k.frame === frame).map(k => kid(s.id, k.frame)));

// What a selection holds now. Ids of things that are gone are skipped.
export function readSel(project, sel) {
  const out = { keys: [], sounds: [], events: [], min: Infinity, max: -Infinity, sims: new Set() };
  if (!sel || !sel.size) return out;
  const byId = new Map(project.sims.map(s => [s.id, s]));
  const add = f => { out.min = Math.min(out.min, f); out.max = Math.max(out.max, f); };
  for (const id of sel) {
    const p = parseId(id);
    if (p.kind === 'key') {
      const sim = byId.get(p.simId), key = sim && sim.keys.find(k => k.frame === p.frame);
      if (key) { out.keys.push({ sim, key }); out.sims.add(sim.id); add(key.frame); }
    } else if (p.kind === 'sound') {
      const sim = byId.get(p.simId);
      for (const snd of (sim && sim.sounds) || []) if (snd.frame === p.frame && snd.name === p.name && !out.sounds.some(x => x.snd === snd)) { out.sounds.push({ sim, snd }); out.sims.add(sim.id); add(snd.frame); }
    } else if (p.kind === 'event') {
      const ev = (project.events || []).find(e => String(e.id) === p.id);
      if (ev) { out.events.push(ev); add(ev.frame); }
    }
  }
  if (!Number.isFinite(out.min)) { out.min = 0; out.max = 0; }
  return out;
}

// Two keys of one sim met on a frame. A face-only key never wipes a body key out: they join (the full key keeps its
// body, the moving key's face wins - the timeline's old merge rule). Otherwise the moving key wins.
function landOn(sim, moving, other) {
  if (moving.faceOnly || other.faceOnly) {
    const body = moving.faceOnly ? other : moving;
    if (moving.face) body.face = { ...moving.face }; else if (body === moving && other.face && !moving.face) body.face = { ...other.face };
    if (moving.faceBones) body.faceBones = clone(moving.faceBones); else if (body === moving && other.faceBones) body.faceBones = clone(other.faceBones);
    if (!(moving.faceOnly && other.faceOnly)) delete body.faceOnly;
    body.frame = moving.frame;
    return { keep: body, drop: body === moving ? other : moving, merged: true };
  }
  return { keep: moving, drop: other, merged: false };
}

// Keys of the selection moved to their new frames (per sim); unselected keys they land on are replaced or joined.
function settle(project, moved, report) {
  const bySim = new Map();
  for (const m of moved) { if (!bySim.has(m.sim)) bySim.set(m.sim, []); bySim.get(m.sim).push(m); }
  for (const [sim, list] of bySim) {
    const movingSet = new Set(list.map(m => m.key));
    // two selected keys on one frame: the one from the later old frame wins (the retime rule)
    const at = new Map();
    for (const m of [...list].sort((a, b) => a.old - b.old)) {
      const prev = at.get(m.key.frame);
      if (prev) {
        const r = landOn(sim, m.key, prev.key);
        report.merged++;
        at.set(m.key.frame, { key: r.keep, old: m.old });
        movingSet.delete(r.drop); sim.keys = sim.keys.filter(k => k !== r.drop);
      } else at.set(m.key.frame, m);
    }
    for (const [f, m] of at) {
      const other = sim.keys.find(k => k.frame === f && !movingSet.has(k) && k !== m.key);
      if (!other) continue;
      const r = landOn(sim, m.key, other);
      sim.keys = sim.keys.filter(k => k !== r.drop);
      if (r.merged) report.joined.push({ simId: sim.id, frame: f });
      else report.replaced.push({ simId: sim.id, frame: f });
    }
    A.sortKeys(sim.keys);
  }
}

// ---------------------------------------------------------------- move and stretch (spec 4.2)
export function moveSel(project, sel, df) {
  const r = readSel(project, sel), L = project.length;
  const report = { sel: new Set(), replaced: [], joined: [], merged: 0, df: 0 };
  if (!r.keys.length && !r.sounds.length && !r.events.length) return report;
  df = Math.round(df);
  df = clamp(df, -r.min, L - 1 - r.max);          // the whole selection stays inside the loop (spacing never changes)
  report.df = df;
  const moved = r.keys.map(({ sim, key }) => { const old = key.frame; key.frame += df; return { sim, key, old }; });
  settle(project, moved, report);
  for (const { sim, snd } of r.sounds) { snd.frame += df; snd.auto = false; report.sel.add(sndId(sim.id, snd)); }
  for (const ev of r.events) { ev.frame += df; if (typeof ev.end === 'number') ev.end = clamp(ev.end + df, ev.frame, L); report.sel.add(evId(ev)); }
  for (const m of moved) if (m.sim.keys.includes(m.key)) report.sel.add(kid(m.sim.id, m.key.frame));
  for (const m of report.joined) report.sel.add(kid(m.simId, m.frame));
  return report;
}

export function scaleSel(project, sel, pivot, s) {
  const r = readSel(project, sel), L = project.length;
  const report = { sel: new Set(), replaced: [], joined: [], merged: 0, s };
  s = Math.max(0.05, s);
  const nf = f => clamp(Math.round(pivot + (f - pivot) * s), 0, L - 1);
  const moved = r.keys.map(({ sim, key }) => { const old = key.frame; key.frame = nf(old); return { sim, key, old }; });
  settle(project, moved, report);
  for (const { sim, snd } of r.sounds) { snd.frame = nf(snd.frame); snd.auto = false; report.sel.add(sndId(sim.id, snd)); }
  for (const ev of r.events) { const f0 = ev.frame; ev.frame = nf(f0); if (typeof ev.end === 'number') ev.end = Math.max(ev.frame, nf(ev.end)); report.sel.add(evId(ev)); }
  for (const m of moved) if (m.sim.keys.includes(m.key)) report.sel.add(kid(m.sim.id, m.key.frame));
  for (const m of report.joined) report.sel.add(kid(m.simId, m.frame));
  return report;
}

// ---------------------------------------------------------------- reverse, delete (spec 4.3)
export function reverseSel(project, sel) {
  const r = readSel(project, sel);
  const report = { sel: new Set(), replaced: [], joined: [], merged: 0 };
  const bySim = new Map();
  for (const x of r.keys) { if (!bySim.has(x.sim)) bySim.set(x.sim, []); bySim.get(x.sim).push(x.key); }
  const moved = [];
  for (const [sim, keys] of bySim) {
    keys.sort((a, b) => a.frame - b.frame);
    const ease = keys.map(k => [k.ease || 'auto', A.validCurve(k.curve) ? k.curve.slice() : null]);
    const m = keys.length - 1;
    const setEase = (k, [e, c], rev) => {
      k.ease = rev ? (A.REVERSE_EASE[e] || 'smooth') : e;
      if (k.ease === 'custom' && c) k.curve = rev ? A.reverseCurve(c) : c.slice(); else delete k.curve;
    };
    for (let i = 0; i < m; i++) setEase(keys[i + 1], ease[i], true);
    setEase(keys[0], ease[m], false);
    for (const k of keys) { const old = k.frame; k.frame = r.min + r.max - k.frame; moved.push({ sim, key: k, old }); }
  }
  settle(project, moved, report);
  for (const { sim, snd } of r.sounds) { snd.frame = r.min + r.max - snd.frame; snd.auto = false; report.sel.add(sndId(sim.id, snd)); }
  for (const ev of r.events) {
    const f = r.min + r.max - ev.frame;
    if (typeof ev.end === 'number') { const e = r.min + r.max - ev.end; ev.end = Math.max(f, e); ev.frame = Math.min(f, e); } else ev.frame = f;
    report.sel.add(evId(ev));
  }
  for (const m of moved) if (m.sim.keys.includes(m.key)) report.sel.add(kid(m.sim.id, m.key.frame));
  return report;
}

// A sim never loses its last body key: when all of them are selected the earliest one stays.
export function deleteSel(project, sel) {
  const r = readSel(project, sel);
  const report = { deleted: 0, kept: [], sounds: 0, events: 0 };
  const bySim = new Map();
  for (const x of r.keys) { if (!bySim.has(x.sim)) bySim.set(x.sim, new Set()); bySim.get(x.sim).add(x.key); }
  for (const [sim, set] of bySim) {
    const body = sim.keys.filter(isBody);
    if (body.length && body.every(k => set.has(k))) {
      const first = body.reduce((a, b) => (b.frame < a.frame ? b : a));
      set.delete(first);
      report.kept.push(sim.label);
    }
    report.deleted += set.size;
    sim.keys = sim.keys.filter(k => !set.has(k));
  }
  for (const { sim, snd } of r.sounds) { sim.sounds = sim.sounds.filter(x => x !== snd); report.sounds++; }
  if (r.events.length) { const gone = new Set(r.events); project.events = (project.events || []).filter(e => !gone.has(e)); report.events = gone.size; }
  return report;
}

// ---------------------------------------------------------------- copy, paste (spec 4.4, clipboard 2.4)
export function copySel(project, sel) {
  const r = readSel(project, sel);
  const origin = r.min;
  const rows = [];
  for (const sim of project.sims) {
    const keys = r.keys.filter(x => x.sim === sim).map(x => x.key).sort((a, b) => a.frame - b.frame);
    const sounds = r.sounds.filter(x => x.sim === sim).map(x => x.snd);
    if (!keys.length && !sounds.length) continue;
    rows.push({ simId: sim.id, label: sim.label, frame: sim.frame, gender: sim.gender,
      keys: keys.map(k => {
        const o = { df: k.frame - origin, ease: k.ease || 'auto', pose: clone(k.pose) };
        if (k.ease === 'custom' && A.validCurve(k.curve)) o.curve = k.curve.slice();
        if (k.type === 'breakdown') o.type = 'breakdown';
        if (k.face) o.face = { ...k.face };
        if (k.faceBones) o.faceBones = clone(k.faceBones);
        if (k.faceOnly) o.faceOnly = true;
        return o;
      }),
      sounds: sounds.map(s => ({ df: s.frame - origin, name: s.name, kind: s.kind })) });
  }
  return { v: 1, projectUid: project.uid, fps: project.fps, length: project.length, loop: !!project.loop, origin, rows,
    count: rows.reduce((n, x) => n + x.keys.length, 0), sounds: rows.reduce((n, x) => n + x.sounds.length, 0) };
}

// targets: Map(row index -> sim). flip(key copy) mirrors a pasted key in place (paste mirrored). The pasted keys and
// sounds come back as the new selection.
export function pasteClip(project, clip, at, { targets, flip = null } = {}) {
  const L = project.length;
  const report = { sel: new Set(), dropped: 0, replaced: 0, pasted: 0 };
  (clip.rows || []).forEach((row, i) => {
    const sim = targets && targets.get(i);
    if (!sim) return;
    for (const k of row.keys || []) {
      const f = at + k.df;
      if (f < 0 || f > L - 1) { report.dropped++; continue; }
      let key = { frame: f, ease: k.ease || 'auto', pose: clone(k.pose) };
      if (k.curve && k.ease === 'custom') key.curve = k.curve.slice();
      if (k.type === 'breakdown') key.type = 'breakdown';
      if (k.face) key.face = { ...k.face };
      if (k.faceBones) key.faceBones = clone(k.faceBones);
      if (k.faceOnly) key.faceOnly = true;
      if (flip) key = flip(key) || key;
      const old = sim.keys.find(x => x.frame === f);
      if (old) {
        report.replaced++;
        // a pasted face-only key keeps the body key that was there
        if (key.faceOnly && !old.faceOnly) { const r = landOn(sim, key, old); sim.keys = sim.keys.filter(x => x !== r.drop); report.sel.add(kid(sim.id, f)); report.pasted++; continue; }
        sim.keys = sim.keys.filter(x => x !== old);
      }
      sim.keys.push(key);
      report.pasted++;
      report.sel.add(kid(sim.id, f));
    }
    A.sortKeys(sim.keys);
    for (const s of row.sounds || []) {
      const f = at + s.df;
      if (f < 0 || f > L - 1) { report.dropped++; continue; }
      const snd = { frame: f, name: s.name, kind: s.kind, auto: false };
      sim.sounds = sim.sounds || [];
      sim.sounds.push(snd);
      report.sel.add(sndId(sim.id, snd));
    }
  });
  return report;
}

// ---------------------------------------------------------------- neighbours with loop wrap
// The body keys just before and after `frame` (wrapping round the loop): {prev, next, pf, nf} with unwrapped frames.
export function neighbours(project, sim, frame, { exclude = null } = {}) {
  const L = project.length, loop = !!project.loop;
  const body = A.onTimeline(sim.keys.filter(k => isBody(k) && k !== exclude), L);
  let prev = null, next = null;
  for (const k of body) { if (k.frame < frame) prev = k; else if (k.frame > frame && !next) next = k; }
  let pf = prev ? prev.frame : null, nf = next ? next.frame : null;
  if (loop && body.length) {
    if (!prev) { prev = body[body.length - 1]; pf = prev.frame - L; }
    if (!next) { next = body[0]; nf = next.frame + L; }
  }
  return { prev, next, pf, nf };
}

const blendFace = (a, b, t) => {
  if (!a && !b) return null;
  const out = {};
  for (const k of new Set([...Object.keys(a || {}), ...Object.keys(b || {})])) {
    const x = (a || {})[k] ?? 0, y = (b || {})[k] ?? 0;
    out[k] = x + (y - x) * t;
  }
  return out;
};
const emptyFB = () => ({ rot: {}, pos: {} });

// ---------------------------------------------------------------- in-between, exaggerate, moving hold (spec 4.5)
export function inBetween(project, sim, frame, t = 0.5) {
  t = clamp(t, -0.25, 1.25);
  const here = sim.keys.find(k => k.frame === frame);
  const { prev, next } = neighbours(project, sim, frame, { exclude: here });
  if (!prev || !next) return null;
  const pose = A.blendPoses(prev.pose, next.pose, t);
  let key = here;
  if (key) { key.pose = pose; delete key.faceOnly; }
  else {
    key = { frame, ease: prev.ease || 'auto', pose };
    if (prev.ease === 'custom' && A.validCurve(prev.curve)) key.curve = prev.curve.slice();
    // the face flows as before, unless both neighbours hold a face (then it is blended the same way)
    if (prev.face && next.face) key.face = blendFace(prev.face, next.face, t);
    if (prev.faceBones && next.faceBones) key.faceBones = A.blendPoses(prev.faceBones || emptyFB(), next.faceBones || emptyFB(), t);
    sim.keys.push(key);
    A.sortKeys(sim.keys);
  }
  key.type = 'breakdown';
  return key;
}

// amount -1..1: > 0 pushes the key away from its neighbours (exaggerate), < 0 pulls it toward them (soften).
export function pushKey(project, sim, key, amount) {
  const { prev, next, pf, nf } = neighbours(project, sim, key.frame, { exclude: key });
  if (!prev || !next || prev === key || next === key || nf === pf) return false;
  const u = (key.frame - pf) / (nf - pf);
  const mid = A.blendPoses(prev.pose, next.pose, u);
  key.pose = A.blendPoses(mid, key.pose, 1 + amount);
  if (key.face) {
    for (const [k, v] of Object.entries(key.face)) {
      const a = (prev.face || {})[k] ?? v, b = (next.face || {})[k] ?? v;
      const m = a + (b - a) * u, lim = FACE_SLIDERS[k] || { min: -1, max: 1 };
      key.face[k] = clamp(m + (v - m) * (1 + amount), lim.min, lim.max);
    }
  }
  return true;
}

// A copy of the pose a little later, drifting 8% toward the next key, so a held pose never looks frozen.
export function movingHold(project, sim, key, frames) {
  const L = project.length;
  const { next, nf } = neighbours(project, sim, key.frame, { exclude: key });
  let f = key.frame + Math.max(1, Math.round(frames));
  f = Math.min(f, L - 1);
  if (next && nf !== null) f = Math.min(f, nf - 1);
  if (f <= key.frame) return null;
  const hold = { frame: f, ease: key.ease || 'auto', pose: next && next !== key ? A.blendPoses(key.pose, next.pose, 0.08) : clone(key.pose) };
  if (key.ease === 'custom' && A.validCurve(key.curve)) hold.curve = key.curve.slice();
  if ((key.ease || 'auto') === 'auto') { key.ease = 'smooth'; delete key.curve; }
  const old = sim.keys.find(k => k.frame === f);
  if (old) {
    old.pose = hold.pose; old.ease = hold.ease; delete old.faceOnly;
    if (hold.curve) old.curve = hold.curve; else delete old.curve;
    return old;
  }
  sim.keys.push(hold);
  A.sortKeys(sim.keys);
  return hold;
}

// ---------------------------------------------------------------- loop check and loop tools (spec 4.6)
// How different two poses are: the largest bone angle (degrees) plus the hips' distance in mm / 5.
export function poseDiff(a, b) {
  const ra = (a && a.rot) || {}, rb = (b && b.rot) || {};
  let deg = 0;
  for (const n of new Set([...Object.keys(ra), ...Object.keys(rb)])) {
    const qa = ra[n] || restRot(n), qb = rb[n] || restRot(n);
    if (qa && qb) deg = Math.max(deg, qAngle(qa, qb) * DEG);
  }
  let mm = 0;
  for (const n of HIPS) {
    const va = (a && a.pos && a.pos[n]), vb = (b && b.pos && b.pos[n]);
    if (va && vb) mm = Math.max(mm, Math.hypot(va[0] - vb[0], va[1] - vb[1], va[2] - vb[2]) * 1000);
  }
  return deg + mm / 5;
}

export function loopCheck(project) {
  const L = project.length;
  return project.sims.map(sim => {
    if (!project.loop) return { simId: sim.id, kind: 'open', deg: 0, frames: 0 };
    const body = A.onTimeline(sim.keys.filter(isBody), L);
    if (body.length < 2) return { simId: sim.id, kind: 'ok', deg: 0, frames: 0 };
    const first = body[0], last = body[body.length - 1];
    const seam = L - last.frame + first.frame;
    const deg = poseDiff(last.pose, first.pose);
    if (last.ease === 'hold') return { simId: sim.id, kind: 'snap', deg, frames: seam };
    if (seam <= 3 && deg < 0.5) return { simId: sim.id, kind: 'pause', deg, frames: seam };
    if (seam <= 2 && deg > 15) return { simId: sim.id, kind: 'pop', deg, frames: seam };
    return { simId: sim.id, kind: 'ok', deg, frames: seam };
  });
}

export const LOOP_TEXT = {
  pause: $t('keyops.pauses_for_frame_at_loop'),
  snap: $t('keyops.jumps_at_loop_point_last'),
  pop: $t('keyops.end_jumps_back_to_start'),
  ok: $t('keyops.flows_smoothly'),
  open: $t('keyops.loop_is_off'),
};

export function fixLoop(project, sim, kind) {
  const L = project.length;
  const body = A.onTimeline(sim.keys.filter(isBody), L);
  if (body.length < 2) return false;
  const last = body[body.length - 1];
  if (kind === 'pause') {
    // the animation already flows from the last key back to the first: the copy at the end only adds a pause
    if (hasFaceData(last)) last.faceOnly = true; else sim.keys = sim.keys.filter(k => k !== last);
    return true;
  }
  if (kind === 'snap') { last.ease = 'auto'; delete last.curve; return true; }
  if (kind === 'pop') { blendEndIntoStart(project, sim, clamp(Math.round(L / 6), 6, 15)); return true; }
  return false;
}

const smoothstep = u => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };

export function blendEndIntoStart(project, sim, N = 10) {
  const L = project.length, W = Math.max(1, L - N);
  const body = () => A.onTimeline(sim.keys.filter(isBody), L);
  const first = body()[0];
  if (!first) return 0;
  if (!sim.keys.some(k => k.frame === W && isBody(k))) {
    const pose = A.evaluate(sim.keys, W, L, project.loop, project.autoCurve);
    const had = sim.keys.find(k => k.frame === W);
    if (had) { had.pose = clone(pose); delete had.faceOnly; had.type = 'breakdown'; }
    else { sim.keys.push({ frame: W, ease: 'auto', type: 'breakdown', pose: clone(pose) }); A.sortKeys(sim.keys); }
  }
  let n = 0;
  for (const k of body()) {
    if (k.frame <= W || k.frame > L - 1 || k === first) continue;
    const w = smoothstep((k.frame - W) / (N + 1));
    k.pose = A.blendPoses(k.pose, first.pose, w);
    if (k.face && first.face) k.face = blendFace(k.face, first.face, w);
    n++;
  }
  return n;
}

// Rotate the whole loop by n frames (keys, sounds, motions, ranged pins; with simIds null also the moments), so the
// same animation starts somewhere else. Only for looping animations: evaluate(new, f) == evaluate(old, f - n).
export function offsetCycle(project, simIds, n) {
  const L = project.length;
  if (!project.loop || !L) return false;
  n = Math.round(n);
  if (!mod(n, L)) return false;
  for (const sim of project.sims) {
    if (simIds && !simIds.includes(sim.id)) continue;
    // keys past the end are off the timeline: they stay where they are
    for (const k of sim.keys) if (k.frame < L) k.frame = mod(k.frame + n, L);
    A.sortKeys(sim.keys);
    for (const s of sim.sounds || []) s.frame = mod(s.frame + n, L);
    for (const l of sim.layers || []) {
      const st = Math.max(1, Math.round((l.params && l.params.strokes) ?? 1));
      l.phase = mod((l.phase || 0) - (n * st) / L, 1);
    }
    for (const p of Object.values(sim.pins || {})) {
      if (p && !Array.isArray(p) && typeof p.from === 'number' && typeof p.to === 'number') { p.from = mod(p.from + n, L); p.to = mod(p.to + n, L); }
    }
  }
  if (!simIds) for (const e of project.events || []) {
    if (typeof e.frame === 'number') { const len = typeof e.end === 'number' ? e.end - e.frame : null; e.frame = mod(e.frame + n, L); if (len !== null) e.end = Math.min(L, e.frame + len); }
  }
  return true;
}

export function makeEndMatchStart(project, sim) {
  const L = project.length;
  const first = A.onTimeline(sim.keys.filter(isBody), L)[0];
  if (!first || first.frame === L - 1) return null;
  const k = { frame: L - 1, ease: first.ease || 'auto', pose: clone(first.pose) };
  if (first.face) k.face = { ...first.face };
  if (first.faceBones) k.faceBones = clone(first.faceBones);
  sim.keys = sim.keys.filter(x => x.frame !== L - 1);
  sim.keys.push(k);
  A.sortKeys(sim.keys);
  return k;
}

// ---------------------------------------------------------------- smooth (spec 4.7)
const alignTo = (q, ref) => ((q[0] * ref[0] + q[1] * ref[1] + q[2] * ref[2] + q[3] * ref[3]) < 0 ? [-q[0], -q[1], -q[2], -q[3]] : q);
export function smoothKeys(keys, { frames = null, bones = null, strength = 0.5, length, loop } = {}) {
  const body = A.onTimeline(keys.filter(isBody), length);
  if (body.length < 3 || strength <= 0) return { changed: 0 };
  const gaps = [];
  for (let i = 0; i + 1 < body.length; i++) gaps.push(body[i + 1].frame - body[i].frame);
  if (loop) gaps.push(length - body[body.length - 1].frame + body[0].frame);
  gaps.sort((a, b) => a - b);
  const sigma = Math.max(1.5, gaps[gaps.length >> 1]);
  const reach = 3 * sigma;
  const orig = body.map(k => ({ rot: k.pose.rot || {}, pos: k.pose.pos || {}, face: k.face || null }));
  const boneSet = bones ? (bones instanceof Set ? bones : new Set(bones)) : null;
  const rotNames = new Set();
  for (const o of orig) for (const n of Object.keys(o.rot)) if (!boneSet || boneSet.has(n)) rotNames.add(n);
  const posNames = new Set();
  if (!boneSet) for (const o of orig) for (const n of Object.keys(o.pos)) posNames.add(n);
  const out = [];
  body.forEach((k, i) => {
    if (frames && !frames.has(k.frame)) return;
    if (!loop && (i === 0 || i === body.length - 1)) return;
    const nb = [];
    body.forEach((o, j) => {
      const cands = loop ? [o.frame - k.frame, o.frame - k.frame + length, o.frame - k.frame - length] : [o.frame - k.frame];
      let best = null;
      for (const d of cands) if (Math.abs(d) <= reach && (best === null || Math.abs(d) < Math.abs(best))) best = d;
      if (best !== null) nb.push([j, Math.exp(-(best * best) / (2 * sigma * sigma))]);
    });
    const rot = {}, pos = {};
    for (const n of rotNames) {
      const q0 = orig[i].rot[n] || restRot(n);
      if (!q0) continue;
      const s = [0, 0, 0, 0];
      for (const [j, w] of nb) { const q = alignTo(orig[j].rot[n] || restRot(n) || q0, q0); for (let c = 0; c < 4; c++) s[c] += w * q[c]; }
      const len = Math.hypot(...s) || 1;
      _qa.fromArray(q0); _qb.set(s[0] / len, s[1] / len, s[2] / len, s[3] / len);
      rot[n] = _qa.slerp(_qb, strength).toArray();
    }
    for (const n of posNames) {
      const v0 = orig[i].pos[n];
      if (!v0) continue;
      const s = [0, 0, 0]; let ws = 0;
      for (const [j, w] of nb) { const v = orig[j].pos[n]; if (!v) continue; for (let c = 0; c < 3; c++) s[c] += w * v[c]; ws += w; }
      if (ws > 0) pos[n] = v0.map((x, c) => x + (s[c] / ws - x) * strength);
    }
    let face = null;
    if (!boneSet && orig[i].face) {
      face = {};
      for (const [f, v] of Object.entries(orig[i].face)) {
        let s = 0, ws = 0;
        for (const [j, w] of nb) { const o = orig[j].face; if (o && typeof o[f] === 'number') { s += w * o[f]; ws += w; } }
        face[f] = ws > 0 ? v + (s / ws - v) * strength : v;
      }
    }
    out.push([k, rot, pos, face]);
  });
  for (const [k, rot, pos, face] of out) {
    k.pose = { rot: { ...(k.pose.rot || {}), ...rot }, pos: { ...(k.pose.pos || {}), ...pos } };
    if (face) k.face = face;
  }
  return { changed: out.length, sigma };
}

// ---------------------------------------------------------------- simplify (spec 4.8)
// A fast evaluator of the body channel over a subset of keys (dense arrays), matching animation.evaluate exactly for
// ordinary keys. Used to decide which keys can go; the result is checked with the real evaluate.
function denseKeys(body) {
  const rotNames = [...new Set(body.flatMap(k => Object.keys(k.pose.rot || {})))];
  const posNames = [...new Set(body.flatMap(k => Object.keys(k.pose.pos || {})))];
  const nr = rotNames.length, np = posNames.length, n = body.length;
  const Q = new Float64Array(n * nr * 4), P = new Float64Array(n * np * 3);
  body.forEach((k, i) => {
    rotNames.forEach((name, b) => {
      let q = (k.pose.rot || {})[name] || restRot(name);
      if (!q) { const o = body.find(x => x.pose.rot && x.pose.rot[name]); q = o ? o.pose.rot[name] : [0, 0, 0, 1]; }
      Q.set(q, (i * nr + b) * 4);
    });
    posNames.forEach((name, b) => {
      let v = (k.pose.pos || {})[name] || (HIPS_SET.has(name) ? null : restPos(name));
      if (!v) { let best = null; for (const o of body) if (o.pose.pos && o.pose.pos[name] && (!best || Math.abs(o.frame - k.frame) < Math.abs(best.frame - k.frame))) best = o; v = best ? best.pose.pos[name] : [0, 0, 0]; }
      P.set(v, (i * np + b) * 3);
    });
  });
  return { rotNames, posNames, nr, np, Q, P };
}

export function simplifyKeys(keys, { tolDeg = 1.5, tolMm = 2, tolFace = 0.03, length, loop, curve = 'legacy', protect = new Set() } = {}) {
  void tolFace;
  const L = length;
  const all = keys.slice();
  const body = A.onTimeline(all.filter(isBody), L).slice();
  const n = body.length;
  if (n < 3) return { keys: all, removed: 0, maxDeg: 0 };
  const D = denseKeys(body);
  const { nr, np, Q, P } = D;
  const tolRad = tolDeg / DEG, tolM = tolMm / 1000;
  // the truth: the original animation, every frame (never the simplified one, so errors never add up)
  const TQ = new Float64Array(L * nr * 4), TP = new Float64Array(L * np * 3);
  const orig = all.filter(k => isBody(k));
  for (let f = 0; f < L; f++) {
    const e = A.evaluate(orig, f, L, loop, curve);
    D.rotNames.forEach((name, b) => { const q = (e.rot || {})[name] || restRot(name) || [0, 0, 0, 1]; TQ.set(q, (f * nr + b) * 4); });
    D.posNames.forEach((name, b) => { const v = (e.pos || {})[name] || (HIPS_SET.has(name) ? [0, 0, 0] : restPos(name)) || [0, 0, 0]; TP.set(v, (f * np + b) * 3); });
  }
  // the keys that stay, as a linked list
  const alive = new Uint8Array(n).fill(1);
  const prv = new Int32Array(n), nxt = new Int32Array(n);
  for (let i = 0; i < n; i++) { prv[i] = i - 1; nxt[i] = i + 1; }
  if (loop) { prv[0] = n - 1; nxt[n - 1] = 0; } else { prv[0] = -1; nxt[n - 1] = -1; }
  let count = n;
  const frameOf = i => body[i].frame;
  const easeOf = i => body[i].ease || 'auto';
  // removable: not the first key, not the last when it doesn't loop, not a hold or right after a hold, not protected
  const removable = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const k = body[i];
    removable[i] = i > 0 && (loop || i < n - 1) && easeOf(i) !== 'hold' && !(i > 0 && easeOf(i - 1) === 'hold') && !protect.has(k.frame) ? 1 : 0;
  }
  const out = new Float64Array(nr * 4), outP = new Float64Array(np * 3);
  const tmp = [0, 0, 0, 0];
  const cr = (p0, p1, p2, p3, t) => { const t2 = t * t, t3 = t2 * t; return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3); };
  const slope = (p0, p1, p2, h0, h1) => {
    const d0 = h0 > 0 ? (p1 - p0) / h0 : 0, d1 = h1 > 0 ? (p2 - p1) / h1 : 0;
    if (d0 * d1 <= 0) return 0;
    const m = (d0 * h1 + d1 * h0) / (h0 + h1), lim = 3 * Math.min(Math.abs(d0), Math.abs(d1));
    return Math.sign(m) * Math.min(Math.abs(m), lim);
  };
  const herm = (p1, p2, m1, m2, h, t) => { const t2 = t * t, t3 = t2 * t; return (2 * t3 - 3 * t2 + 1) * p1 + (t3 - 2 * t2 + t) * h * m1 + (-2 * t3 + 3 * t2) * p2 + (t3 - t2) * h * m2; };
  // evaluate segment a -> b (key indices; b follows a in the list) at frame f (unwrapped between fa and fb)
  const seg = (a, b, f, fa, fb, p0, p3) => {
    const span = fb - fa, t = span > 0 ? clamp((f - fa) / span, 0, 1) : 0;
    const ease = easeOf(a);
    if (ease === 'auto' && count > 2) {
      const i0 = p0, i3 = p3;
      if (curve === 'clamped') {
        // spanFrames
        let f0 = frameOf(i0), f3 = frameOf(i3);
        const f1 = fa, f2 = fb;
        if (i0 === a) f0 = f1 - (f2 - f1); else { while (f0 >= f1) f0 -= L; }
        if (i3 === b) f3 = f2 + (f2 - f1); else { while (f3 <= f2) f3 += L; }
        const h0 = f1 - f0, h = f2 - f1, h2 = f3 - f2;
        for (let r = 0; r < nr; r++) {
          const o1 = (a * nr + r) * 4, o2 = (b * nr + r) * 4, o0 = (i0 * nr + r) * 4, o3 = (i3 * nr + r) * 4;
          const s2 = (Q[o2] * Q[o1] + Q[o2 + 1] * Q[o1 + 1] + Q[o2 + 2] * Q[o1 + 2] + Q[o2 + 3] * Q[o1 + 3]) < 0 ? -1 : 1;
          const s0 = (Q[o0] * Q[o1] + Q[o0 + 1] * Q[o1 + 1] + Q[o0 + 2] * Q[o1 + 2] + Q[o0 + 3] * Q[o1 + 3]) < 0 ? -1 : 1;
          const s3 = ((Q[o3] * Q[o2] + Q[o3 + 1] * Q[o2 + 1] + Q[o3 + 2] * Q[o2 + 2] + Q[o3 + 3] * Q[o2 + 3]) * s2) < 0 ? -s2 : s2;
          let len = 0;
          for (let c = 0; c < 4; c++) {
            const q0 = s0 * Q[o0 + c], q1 = Q[o1 + c], q2 = s2 * Q[o2 + c], q3 = s3 * Q[o3 + c];
            const m1 = slope(q0, q1, q2, h0, h), m2 = slope(q1, q2, q3, h, h2);
            tmp[c] = herm(q1, q2, m1, m2, h, t); len += tmp[c] * tmp[c];
          }
          len = Math.sqrt(len) || 1;
          for (let c = 0; c < 4; c++) out[r * 4 + c] = tmp[c] / len;
        }
        for (let r = 0; r < np; r++) for (let c = 0; c < 3; c++) {
          const v0 = P[(i0 * np + r) * 3 + c], v1 = P[(a * np + r) * 3 + c], v2 = P[(b * np + r) * 3 + c], v3 = P[(i3 * np + r) * 3 + c];
          outP[r * 3 + c] = herm(v1, v2, slope(v0, v1, v2, h0, h), slope(v1, v2, v3, h, h2), h, t);
        }
        return;
      }
      for (let r = 0; r < nr; r++) {
        const o1 = (a * nr + r) * 4, o2 = (b * nr + r) * 4, o0 = (i0 * nr + r) * 4, o3 = (i3 * nr + r) * 4;
        const s0 = (Q[o0] * Q[o1] + Q[o0 + 1] * Q[o1 + 1] + Q[o0 + 2] * Q[o1 + 2] + Q[o0 + 3] * Q[o1 + 3]) < 0 ? -1 : 1;
        const s2 = (Q[o2] * Q[o1] + Q[o2 + 1] * Q[o1 + 1] + Q[o2 + 2] * Q[o1 + 2] + Q[o2 + 3] * Q[o1 + 3]) < 0 ? -1 : 1;
        const s3 = ((Q[o3] * Q[o2] + Q[o3 + 1] * Q[o2 + 1] + Q[o3 + 2] * Q[o2 + 2] + Q[o3 + 3] * Q[o2 + 3]) * s2) < 0 ? -s2 : s2;
        let len = 0;
        for (let c = 0; c < 4; c++) { tmp[c] = cr(s0 * Q[o0 + c], Q[o1 + c], s2 * Q[o2 + c], s3 * Q[o3 + c], t); len += tmp[c] * tmp[c]; }
        len = Math.sqrt(len) || 1;
        for (let c = 0; c < 4; c++) out[r * 4 + c] = tmp[c] / len;
      }
      for (let r = 0; r < np; r++) for (let c = 0; c < 3; c++) outP[r * 3 + c] = cr(P[(i0 * np + r) * 3 + c], P[(a * np + r) * 3 + c], P[(b * np + r) * 3 + c], P[(i3 * np + r) * 3 + c], t);
      return;
    }
    const e = ease === 'auto' ? A.EASES.smooth(t) : A.easeFn(body[a])(t);
    for (let r = 0; r < nr; r++) {
      const o1 = (a * nr + r) * 4, o2 = (b * nr + r) * 4;
      _qa.set(Q[o1], Q[o1 + 1], Q[o1 + 2], Q[o1 + 3]); _qb.set(Q[o2], Q[o2 + 1], Q[o2 + 2], Q[o2 + 3]);
      _qa.slerp(_qb, e);
      out[r * 4] = _qa.x; out[r * 4 + 1] = _qa.y; out[r * 4 + 2] = _qa.z; out[r * 4 + 3] = _qa.w;
    }
    for (let r = 0; r < np; r++) for (let c = 0; c < 3; c++) { const v1 = P[(a * np + r) * 3 + c], v2 = P[(b * np + r) * 3 + c]; outP[r * 3 + c] = v1 + (v2 - v1) * e; }
  };
  const errAt = f => {
    let e = 0;
    for (let r = 0; r < nr; r++) {
      const o = (f * nr + r) * 4;
      let d = Math.abs(out[r * 4] * TQ[o] + out[r * 4 + 1] * TQ[o + 1] + out[r * 4 + 2] * TQ[o + 2] + out[r * 4 + 3] * TQ[o + 3]);
      d /= Math.hypot(TQ[o], TQ[o + 1], TQ[o + 2], TQ[o + 3]) || 1;
      const ang = 2 * Math.acos(Math.min(1, d));
      if (ang / tolRad > e) e = ang / tolRad;
    }
    for (let r = 0; r < np; r++) {
      const o = (f * np + r) * 3;
      const dist = Math.hypot(outP[r * 3] - TP[o], outP[r * 3 + 1] - TP[o + 1], outP[r * 3 + 2] - TP[o + 2]);
      if (dist / tolM > e) e = dist / tolM;
    }
    return e;
  };
  // the error of the list without key k, over the frames the Auto curve reaches (two keys either side)
  const skip = (i, dir, gone) => { let j = dir > 0 ? nxt[i] : prv[i]; if (j === gone) j = dir > 0 ? nxt[j] : prv[j]; return j; };
  const errWithout = k => {
    // the neighbourhood in the list without k
    const p1 = prv[k], n1 = nxt[k];
    if (p1 < 0 || n1 < 0 || p1 === n1) return Infinity;
    const p2 = skip(p1, -1, k), n2 = skip(n1, 1, k);
    const chain = [p2, p1, n1, n2];
    count--;
    let worst = 0;
    // segments (p2,p1), (p1,n1), (n1,n2)
    for (let s = 0; s < 3; s++) {
      const a = chain[s], b = chain[s + 1];
      if (a < 0 || b < 0) continue;
      const before = s === 0 ? skip(a, -1, k) : chain[s - 1];
      const after = s === 2 ? skip(b, 1, k) : chain[s + 2];
      const i0 = before < 0 ? a : before, i3 = after < 0 ? b : after;
      let fa = frameOf(a), fb = frameOf(b);
      if (fb <= fa) { if (!loop) continue; fb += L; }
      for (let f = fa + 1; f < fb; f++) {
        seg(a, b, f, fa, fb, i0, i3);
        const e = errAt(f % L);
        if (e > worst) worst = e;
        if (worst > 1) { count++; return worst; }
      }
    }
    count++;
    return worst;
  };
  const err = new Float64Array(n).fill(Infinity);
  for (let i = 0; i < n; i++) if (removable[i]) err[i] = errWithout(i);
  let removed = 0;
  for (;;) {
    let best = -1, be = 1;
    for (let i = 0; i < n; i++) if (alive[i] && removable[i] && err[i] <= be) { be = err[i]; best = i; }
    if (best < 0 || count <= 2) break;
    alive[best] = 0; count--; removed++;
    const p = prv[best], q = nxt[best];
    if (p >= 0) nxt[p] = q;
    if (q >= 0) prv[q] = p;
    err[best] = Infinity;
    // the keys whose reach covers the change
    const near = new Set();
    let a = p; for (let s = 0; s < 3 && a >= 0; s++) { near.add(a); a = prv[a]; }
    a = q; for (let s = 0; s < 3 && a >= 0; s++) { near.add(a); a = nxt[a]; }
    for (const i of near) if (alive[i] && removable[i]) err[i] = errWithout(i);
  }
  // the keys that went: a key with a face stays as a face-only key (the face plays exactly as before)
  const gone = new Set(body.filter((k, i) => !alive[i]));
  const result = [];
  for (const k of all) {
    if (!gone.has(k)) { result.push(k); continue; }
    if (hasFaceData(k)) result.push({ ...k, faceOnly: true });
  }
  // the largest angle left, measured with the real evaluate
  let maxDeg = 0;
  const kept = result.filter(isBody);
  for (let f = 0; f < L; f++) {
    const e = A.evaluate(kept, f, L, loop, curve);
    D.rotNames.forEach((name, b) => {
      const q = (e.rot || {})[name] || restRot(name);
      if (!q) return;
      const o = (f * nr + b) * 4;
      maxDeg = Math.max(maxDeg, qAngle(q, [TQ[o], TQ[o + 1], TQ[o + 2], TQ[o + 3]]) * DEG);
    });
  }
  return { keys: A.sortKeys(result), removed, maxDeg, before: n, after: n - removed };
}

// ---------------------------------------------------------------- rig data (mirror, placement)
const _rigCache = new WeakMap();
const IDQ = new THREE.Quaternion();
export function rigInfo(rig) {
  let R = _rigCache.get(rig);
  if (R) return R;
  const names = rig.bones.map(b => b.name), index = {};
  names.forEach((x, i) => { index[x] = i; });
  const parent = rig.bones.map(b => b.parent);
  // (normalised: the rig's float32 rest turns are not exactly unit length, and inverses need unit quaternions)
  const restQ = rig.bones.map(b => new THREE.Quaternion().fromArray(b.rot).normalize());
  const restP = rig.bones.map(b => new THREE.Vector3().fromArray(b.pos));
  const depth = i => { let d = 0; for (let p = parent[i]; p >= 0; p = parent[p]) d++; return d; };
  const order = names.map((x, i) => i).sort((a, b) => depth(a) - depth(b));
  const RS = [], SP = [];
  for (const i of order) {
    const p = parent[i];
    RS[i] = p >= 0 ? RS[p].clone().multiply(restQ[i]) : restQ[i].clone();
    SP[i] = p >= 0 ? restP[i].clone().applyQuaternion(RS[p]).add(SP[p]) : restP[i].clone();
  }
  const keyable = B.KEYABLE_SET || new Set(B.POSABLE);
  const posable = new Set(names.filter(n => keyable.has(n)));
  R = { names, index, parent, restQ, restP, RS, SP, order, posable };
  _rigCache.set(rig, R);
  return R;
}

// A bone's turn and place in the sim's space for a pose (bones the pose doesn't mention at rest).
export function spaceOf(pose, rig, name) {
  const R = rigInfo(rig), i = R.index[name];
  if (i === undefined) return null;
  const chain = [];
  for (let b = i; b >= 0; b = R.parent[b]) chain.push(b);
  const q = new THREE.Quaternion(), p = new THREE.Vector3();
  for (let c = chain.length - 1; c >= 0; c--) {
    const b = chain[c], nm = R.names[b];
    const lp = pose.pos && pose.pos[nm] ? new THREE.Vector3().fromArray(pose.pos[nm]) : R.restP[b].clone();
    p.add(lp.applyQuaternion(q));
    q.multiply(pose.rot && pose.rot[nm] ? new THREE.Quaternion().fromArray(pose.rot[nm]).normalize() : R.restQ[b]).normalize();
  }
  return { q, p };
}

// Which way the pose faces (radians about the vertical), from the hips (as main._facing does for a view).
export function facingOf(pose, rig) {
  const s = spaceOf(pose, rig, 'b__Pelvis__');
  if (!s) return 0;
  const f = new THREE.Vector3(0, 1, 0).applyQuaternion(s.q), l = new THREE.Vector3(0, 0, -1).applyQuaternion(s.q);
  return Math.hypot(f.x, f.z) >= Math.hypot(l.x, l.z) ? Math.atan2(f.x, f.z) : Math.atan2(-l.z, l.x);
}
export const hipsOf = (pose, rig) => { const s = spaceOf(pose, rig, 'b__Pelvis__'); return s ? s.p : new THREE.Vector3(); };

// Move and/or turn poses (the hips carry the sim's place): move first, then turn about `pivot` (sim space). The data
// version of interact.placeSim's key edit.
const UP = new THREE.Vector3(0, 1, 0);
export function placePoses(poses, rig, { move = null, turn = 0, pivot = null } = {}) {
  const R = rigInfo(rig), rb = R.index['b__ROOT_bind__'];
  if (rb === undefined) return poses;
  const rbQ = R.RS[rb], rbP = R.SP[rb], toLocal = rbQ.clone().invert();
  const piv = pivot || new THREE.Vector3();
  const Rq = turn ? new THREE.Quaternion().setFromAxisAngle(UP, turn) : null;
  const Rl = Rq ? toLocal.clone().multiply(Rq).multiply(rbQ) : null;
  const dl = move ? move.clone().applyQuaternion(toLocal) : null;
  for (const pose of poses) {
    if (!pose) continue;
    pose.pos = pose.pos || {}; pose.rot = pose.rot || {};
    for (const n of HIPS) {
      const i = R.index[n];
      if (i === undefined) continue;
      const p = pose.pos[n] ? new THREE.Vector3().fromArray(pose.pos[n]) : R.restP[i].clone();
      if (dl) p.add(dl);
      if (Rq) p.applyQuaternion(rbQ).add(rbP).sub(piv).applyQuaternion(Rq).add(piv).sub(rbP).applyQuaternion(toLocal);
      pose.pos[n] = p.toArray();
      if (Rl) pose.rot[n] = Rl.clone().multiply(pose.rot[n] ? new THREE.Quaternion().fromArray(pose.rot[n]) : R.restQ[i].clone()).normalize().toArray();
    }
  }
  return poses;
}

// ---------------------------------------------------------------- mirror (spec 4.9)
const X = new THREE.Vector3(1, 0, 0);
// Mirror across the scene's left/right (X) plane: bones swap sides, mirroring twice gives the pose back exactly.
export function mirrorPoseData(pose, rig) {
  const R = rigInfo(rig), n = R.names.length;
  const rot = (pose && pose.rot) || {}, pos = (pose && pose.pos) || {};
  const inSet = new Set();
  for (const nm of Object.keys(rot)) if (R.index[nm] !== undefined) { inSet.add(nm); inSet.add(B.mirrorName(nm)); }
  const S = new Array(n), S2 = new Array(n);
  for (const i of R.order) {
    const p = R.parent[i], nm = R.names[i];
    // (unit quaternions only: keys from clips are float32, and a rotation matrix needs a unit quaternion)
    const local = rot[nm] ? new THREE.Quaternion().fromArray(rot[nm]).normalize() : R.restQ[i];
    S[i] = (p >= 0 ? S[p].clone().multiply(local) : local.clone()).normalize();
  }
  const out = { rot: {}, pos: {} };
  for (const i of R.order) {
    const p = R.parent[i], nm = R.names[i];
    const P2 = p >= 0 ? S2[p] : IDQ;
    if (!inSet.has(nm) || !R.posable.has(nm)) { S2[i] = P2.clone().multiply(R.restQ[i]); continue; }
    const mn = B.mirrorName(nm), m = R.index[mn] !== undefined ? R.index[mn] : i;
    const delta = S[m].clone().multiply(R.RS[m].clone().invert()).normalize();
    S2[i] = mirrorQuat(delta, X).normalize().multiply(R.RS[i]).normalize();
    out.rot[nm] = P2.clone().invert().multiply(S2[i]).normalize().toArray();
  }
  for (const [mnm, v] of Object.entries(pos)) {
    const m = R.index[mnm];
    if (m === undefined) continue;
    const nm = B.mirrorName(mnm), i = R.index[nm] !== undefined ? R.index[nm] : m;
    const pm = R.parent[m], pi = R.parent[i];
    const d = new THREE.Vector3().fromArray(v).applyQuaternion(pm >= 0 ? S[pm] : IDQ);
    d.x = -d.x;
    out.pos[R.names[i]] = d.applyQuaternion((pi >= 0 ? S2[pi] : IDQ).clone().invert()).toArray();
  }
  return out;
}

const SIDE_SLIDERS = ['lookSide', 'wink', 'smileSide', 'browSide', 'jawSide'];
export const mirrorFace = f => { if (!f) return f; const o = { ...f }; for (const c of SIDE_SLIDERS) if (typeof o[c] === 'number') o[c] = -o[c]; return o; };
export const mirrorFaceBones = fb => (fb ? A.mirrorFaceBonesData(fb) : fb);
export function mirrorKey(key, rig) {
  const k = clone(key);
  if (k.pose) k.pose = mirrorPoseData(k.pose, rig);
  if (k.face) k.face = mirrorFace(k.face);
  if (k.faceBones) k.faceBones = mirrorFaceBones(k.faceBones);
  return k;
}
// A key mirrored left <-> right in the sim's own frame: it keeps its place and the way it faces.
export function mirrorKeyInPlace(key, rig) {
  const m = mirrorKey(key, rig);
  if (key.pose && m.pose) {
    const p0 = hipsOf(key.pose, rig), p1 = hipsOf(m.pose, rig), y0 = facingOf(key.pose, rig), y1 = facingOf(m.pose, rig);
    placePoses([m.pose], rig, { move: p0.clone().sub(p1), turn: y0 - y1, pivot: p0 });
  }
  return m;
}

const mirrorLimb = l => (l[0] === 'L' ? 'R' + l.slice(1) : l[0] === 'R' ? 'L' + l.slice(1) : l);
const MIRRORED = ' (mirrored)';
// The whole animation mirrored: every key of every sim, pins, motions, moments. It becomes a new animation (new uid).
export function mirrorProject(project, rig, newUid = null) {
  const holdsToRebind = [];
  for (const sim of project.sims) {
    sim.keys = sim.keys.map(k => mirrorKey(k, rig));
    const pins = {};
    for (const [limb, p] of Object.entries(sim.pins || {})) {
      const to = mirrorLimb(limb);
      if (Array.isArray(p)) pins[to] = [-p[0], p[1], p[2]];
      else if (p && Array.isArray(p.at)) pins[to] = { ...p, at: [-p.at[0], p.at[1], p.at[2]] };
      else if (p && p.bone) { pins[to] = { ...p, bone: B.mirrorName(p.bone) }; holdsToRebind.push({ simId: sim.id, limb: to }); }
      else pins[to] = p;
    }
    sim.pins = pins;
    for (const l of sim.layers || []) {
      const P = l.params || {};
      if (typeof P.limb === 'string') P.limb = mirrorLimb(P.limb);
      if (l.type === 'sway') l.phase = mod((l.phase || 0) + 0.5, 1);
      else if (P.axis === 'side') P.reverse = !P.reverse;
    }
  }
  for (const e of project.events || []) {
    for (const f of ['joint', 'effect_joint_name']) if (typeof e[f] === 'string') e[f] = B.mirrorName(e[f]);
  }
  const name = project.name || 'Untitled animation';
  project.name = name.endsWith(MIRRORED) ? name.slice(0, -MIRRORED.length) : name + MIRRORED;
  if (newUid) project.uid = newUid;
  return { holdsToRebind };
}

// ---------------------------------------------------------------- parts (spec 4.10)
export function maskPose(pose, bones, { keepHipPlace = true } = {}) {
  const set = bones instanceof Set ? bones : new Set(bones || []);
  const out = { rot: {}, pos: {} };
  for (const [n, q] of Object.entries((pose && pose.rot) || {})) if (set.has(n)) out.rot[n] = q.slice();
  for (const [n, v] of Object.entries((pose && pose.pos) || {})) if (set.has(n) && !(keepHipPlace && HIPS_SET.has(n))) out.pos[n] = v.slice();
  return out;
}

// target's bones in `bones` blended over base (null = the whole body: blendPoses). The hips' place stays base's.
export function blendInto(base, target, amount, bones = null) {
  if (!bones) return A.blendPoses(base, target, amount);
  const set = bones instanceof Set ? bones : new Set(bones);
  const b = maskPose(base, set), t = maskPose(target, set);
  for (const n of set) {
    // a bone in the part that neither pose mentions stays as it is; one only the target has blends from rest
    if (!(n in b.rot) && (n in t.rot)) { const r = restRot(n); if (r) b.rot[n] = r.slice(); }
    if (!(n in t.rot) && (n in b.rot)) { const r = restRot(n); if (r) t.rot[n] = r.slice(); }
  }
  const mixed = A.blendPoses(b, t, amount);
  const out = { rot: {}, pos: {} };
  for (const [n, q] of Object.entries((base && base.rot) || {})) out.rot[n] = q.slice();
  for (const [n, v] of Object.entries((base && base.pos) || {})) out.pos[n] = v.slice();
  Object.assign(out.rot, mixed.rot);
  Object.assign(out.pos, mixed.pos);
  return out;
}

// A pose turned (about the vertical, around its hips) so it faces the way `like` faces - for partial poses, so the
// hips' turn in a pasted lower body matches the sim it goes on.
export function faceLike(pose, like, rig) {
  const out = clone(pose);
  const turn = facingOf(like, rig) - facingOf(pose, rig);
  if (Math.abs(turn) > 1e-9) placePoses([out], rig, { turn, pivot: hipsOf(pose, rig) });
  return out;
}

// Put one part (a bone name or a BODY_PARTS name) of `source` on these keys. -> how many keys changed
export function putPart(keys, source, part) {
  const bones = BODY_PARTS[part] ? new Set(BODY_PARTS[part]) : new Set([part]);
  let n = 0;
  for (const k of keys) { if (!isBody(k)) continue; k.pose = blendInto(k.pose, source, 1, bones); n++; }
  return n;
}

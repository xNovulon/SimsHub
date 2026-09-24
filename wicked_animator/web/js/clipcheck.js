// Check clipping: where a hand, an arm or a leg goes through a body (the partner's or its own) or through the
// furniture, over the whole loop (spec_bodies 7.3).
// Each body part is a capsule (a line between two joints with a thickness). The thickness comes from the sim's own
// skin in the bind pose: the 60th percentile of how far the part's skin is from its line - a little inside the flesh,
// so parts that only touch are never flagged.
import * as THREE from 'three';
import { gridHeight, gridOf } from './placing.js';
import { $t } from './i18n.js';

// [name, from, to, kind]; names without 'b__' are expanded into a left and a right part
export const SEGMENTS = [
  ['pelvis', 'b__Pelvis__', 'b__Spine1__', 'torso'], ['belly', 'b__Spine1__', 'b__Spine2__', 'torso'],
  ['chest', 'b__Spine2__', 'b__Neck__', 'torso'], ['head', 'b__Head__', null, 'head'],
  [$t('clipcheck.upper_arm'), 'UpperArm', 'Forearm', 'limb'], ['forearm', 'Forearm', 'Hand', 'limb'], ['hand', 'Hand', 'Mid1', 'hand'],
  ['thigh', 'Thigh', 'Calf', 'limb'], ['shin', 'Calf', 'Foot', 'limb'], ['foot', 'Foot', 'Toe', 'limb'],
];
// the skin that counts for a part: the start bone and the helper bones that move with it
const SKIN_OF = {
  pelvis: ['b__Pelvis__', 'b__Spine0__', 'b__L_Butt__', 'b__R_Butt__'], belly: ['b__Spine1__'],
  chest: ['b__Spine2__', 'b__CAS_L_Breast__', 'b__CAS_R_Breast__'], head: ['b__Head__'],
  'upper arm': ['UpperArm', 'ShoulderTwist'], forearm: ['Forearm', 'ForearmTwist'], hand: ['Hand'],
  thigh: ['Thigh', 'ThighTwist'], shin: ['Calf'], foot: ['Foot'],
};
const DEFAULT_R = { pelvis: 0.12, belly: 0.11, chest: 0.12, head: 0.085, 'upper arm': 0.045, forearm: 0.038, hand: 0.03, thigh: 0.07, shin: 0.045, foot: 0.035 };
const LIMB_OF = { 'upper arm': 'hand', forearm: 'hand', hand: 'hand', thigh: 'foot', shin: 'foot', foot: 'foot' };
// How deep a part may go before it counts (the depths are measured a little inside the skin, from each part's reach
// toward the other). Tuned on the 16 couple ready poses (real creator clips) with a thrust on them: hands and
// forearms gripping hips and thighs, arms resting on a partner's or their own thighs, feet together and thighs in a
// lap ride press 4-9 cm into the flesh - that is touching, not clipping. What goes clearly through a body is caught:
// anything more than 4.5 cm into a belly, a chest or a head (a hand 5 cm into the belly counts), a hand more than 7 cm
// into the hips, an arm or a leg more than 6 cm into another limb.
export const LIMITS = { core: 0.045, grip: 0.07, limb: 0.06, feet: 0.08, lap: 0.10, selfLap: 0.07, selfCore: 0.05, held: 0.02, furniture: 0.03 };
const LOWLEG = new Set(['shin', 'foot']);
const CORE = new Set(['belly', 'chest', 'head']);
const LAP = new Set(['pelvis', 'thigh']);
function oneWay(a, b) {
  if (a === 'thigh' && (LAP.has(b) || b === 'belly' || b === 'chest')) return LIMITS.lap;       // bodies pressed together
  if (CORE.has(b)) return LIMITS.core;                                                        // into a belly, chest, head
  if ((a === 'hand' || a === 'forearm') && LAP.has(b)) return LIMITS.grip;                    // hands on hips and thighs
  if (LOWLEG.has(a) && LOWLEG.has(b)) return LIMITS.feet;                                     // feet and shins together
  return LIMITS.limb;
}
// the same both ways for two limbs (a limb against a limb is looked at from one side only)
const pairLimit = (x, y) => (y.kind === 'limb' || y.kind === 'hand' ? Math.max(oneWay(x.part, y.part), oneWay(y.part, x.part)) : oneWay(x.part, y.part));
const ARMS = new Set([$t('clipcheck.upper_arm'), 'forearm', 'hand']);
const SELF_TARGETS = new Set(['pelvis', 'belly', 'chest', 'thigh']);

const side = (n, s) => (n && !n.startsWith('b__') ? `b__${s}_${n}__` : n);

const _p = new THREE.Vector3(), _a = new THREE.Vector3(), _ab = new THREE.Vector3(), _DOWN = new THREE.Vector3(0, -1, 0);

// The closest points of the segments p1-q1 and p2-q2: {c1, c2, dist}.
function closest(p1, q1, p2, q2) {
  const d1 = q1.clone().sub(p1), d2 = q2.clone().sub(p2), r = p1.clone().sub(p2);
  const a = d1.dot(d1), e = d2.dot(d2), f = d2.dot(r);
  let s, t;
  if (a <= 1e-9 && e <= 1e-9) { s = 0; t = 0; } else if (a <= 1e-9) { s = 0; t = THREE.MathUtils.clamp(f / e, 0, 1); } else {
    const c = d1.dot(r);
    if (e <= 1e-9) { t = 0; s = THREE.MathUtils.clamp(-c / a, 0, 1); } else {
      const b = d1.dot(d2), den = a * e - b * b;
      s = den > 1e-9 ? THREE.MathUtils.clamp((b * f - c * e) / den, 0, 1) : 0;
      t = (b * s + f) / e;
      if (t < 0) { t = 0; s = THREE.MathUtils.clamp(-c / a, 0, 1); } else if (t > 1) { t = 1; s = THREE.MathUtils.clamp((b - c) / a, 0, 1); }
    }
  }
  const c1 = p1.clone().addScaledVector(d1, s), c2 = p2.clone().addScaledVector(d2, t);
  return { c1, c2, s, t, dist: c1.distanceTo(c2) };
}

// How far a part's skin reaches from its line toward `dir` (world) at `t` along it (0 = start, 1 = end): from the
// skin measured in 3 slices along the part (a thigh is thick at the hip, thin at the knee) and 8 directions around it
// (a torso is flat - deep to the sides, shallow front and back). skin: the skin itself (90th percentile - for the
// furniture); else a little inside it (70th - body against body, so parts that only touch never count). Toward the
// part's ends (along its line) and for parts without that data: the round radius of the slice.
const _r1 = new THREE.Vector3(), _r2 = new THREE.Vector3(), _ru = new THREE.Vector3();
const slice = t => (t < 1 / 3 ? 0 : t < 2 / 3 ? 1 : 2);
export function reach(x, dir, t = 0.5, skin = false) {
  const c = x.c, k = slice(t);
  const round = c.rs ? c.rs[k] : x.r;
  if (!c.sectors || !x.q) return round;
  _ru.copy(x.b).sub(x.a);
  if (_ru.lengthSq() < 1e-10) return round;
  _ru.normalize();
  const perp = dir.clone().addScaledVector(_ru, -dir.dot(_ru));
  const pl = perp.length();
  if (pl < 0.2) return round;
  _r1.fromArray(c.e1).applyQuaternion(x.q); _r2.fromArray(c.e2).applyQuaternion(x.q);
  const ang = Math.atan2(perp.dot(_r2), perp.dot(_r1)), f = ((ang / (Math.PI / 4)) % 8 + 8) % 8;
  const i0 = Math.floor(f), i1 = (i0 + 1) % 8, w = f - i0;
  const tab = (skin ? c.sectors : c.sectorsIn)[k];
  const rs = tab[i0] * (1 - w) + tab[i1] * w;
  return rs * pl + round * (1 - pl);
}

// How deep two parts go into each other: the overlap of their skin reach toward each other. x, y: {c, ...capsuleNow}.
export function overlap(x, y) {
  const k = closest(x.a, x.b, y.a, y.b);
  if (k.dist < 1e-6) return x.r + y.r;
  const d = k.c1.clone().sub(k.c2).divideScalar(k.dist);          // from y toward x
  return reach(x, d.clone().negate(), k.s) + reach(y, d, k.t) - k.dist;
}
function distToLine(p, a, b) {
  _ab.copy(b).sub(a);
  const t = THREE.MathUtils.clamp(_a.copy(p).sub(a).dot(_ab) / Math.max(1e-9, _ab.lengthSq()), 0, 1);
  return _a.copy(a).addScaledVector(_ab, t).distanceTo(p);
}

// The capsules of a sim view, with their radii from its own skin (cached on the view: a new body is a new view).
// -> [{name, part, side, kind, from, to, fromI, toI, r, limb}]
export function capsulesOf(v) {
  if (v._caps) return v._caps;
  const rw = typeof v._restWorld === 'function' ? v._restWorld() : null;
  const posOf = i => (rw && rw[i] ? new THREE.Vector3().setFromMatrixPosition(rw[i]) : null);
  const out = [];
  for (const [part, from, to, kind] of SEGMENTS) {
    const sides = from.startsWith('b__') ? [null] : ['L', 'R'];
    for (const s of sides) {
      const f = s ? side(from, s) : from, t = to ? (s ? side(to, s) : to) : null;
      const fi = v.index(f), ti = t ? v.index(t) : -1;
      if (fi < 0 || (t && ti < 0)) continue;
      const name = s ? `${s === 'L' ? 'left' : 'right'} ${part}` : part;
      const cap = { name, part, side: s, kind, from: f, to: t, fromI: fi, toI: ti, r: DEFAULT_R[part] || 0.05,
        limb: LIMB_OF[part] && s ? `${s} ${LIMB_OF[part]}` : null };
      // the hips' line starts between the hip joints (the pelvis bone sits above them, and the buttocks and the groin
      // hang below it)
      const iL = v.index('b__L_Thigh__'), iR = v.index('b__R_Thigh__');
      if (part === 'pelvis' && iL >= 0 && iR >= 0) cap.mid = [iL, iR];
      // radius from the skin: vertices at least half on the part's bones, their distance to the part's line (only the
      // skin along the line: what lies past its ends belongs to the next part)
      const a0 = cap.mid && posOf(iL) ? posOf(iL).add(posOf(iR)).multiplyScalar(0.5) : posOf(fi), b0 = ti >= 0 ? posOf(ti) : null;
      if (a0) {
        const b = b0 || a0.clone().add(new THREE.Vector3(1, 0, 0).applyQuaternion(new THREE.Quaternion().setFromRotationMatrix(rw[fi])).multiplyScalar(0.09));
        const ids = new Set((SKIN_OF[part] || [from]).map(n => v.index(s ? side(n, s) : n)).filter(i => i >= 0));
        const d = [];                                   // [distance to the line, t along it, x, y, z]
        cap.verts = [];                                 // [mesh, [vertex indices]]: the part's own skin (every 2nd vertex)
        for (const mesh of v.meshes || []) {
          const role = mesh.userData && mesh.userData.role;
          if (role === 'tongue' || /penis/.test(role || '')) continue;
          const pa = mesh.geometry.attributes.position, si = mesh.geometry.attributes.skinIndex, sw = mesh.geometry.attributes.skinWeight;
          if (!pa || !si || !sw) continue;
          const mine = [];
          for (let i = 0; i < pa.count; i++) {
            let w = 0;
            for (let k = 0; k < 4; k++) if (ids.has(si.getComponent(i, k))) w += sw.getComponent(i, k);
            if (w < 0.5) continue;
            if (!(i & 1)) mine.push(i);
            _p.set(pa.getX(i), pa.getY(i), pa.getZ(i));
            const along = _a.copy(_p).sub(a0).dot(_ab.copy(b).sub(a0)) / Math.max(1e-9, _ab.lengthSq());
            if (along < -0.08 || along > 1.08) continue;
            d.push([distToLine(_p, a0, b), along, _p.x, _p.y, _p.z]);
          }
          if (mine.length) cap.verts.push([mesh, Uint32Array.from(mine)]);
        }
        if (d.length >= 8) {
          const sorted = d.map(x => x[0]).sort((x, y) => x - y);
          cap.r = THREE.MathUtils.clamp(sorted[Math.floor(sorted.length * 0.6)], 0.015, 0.2);
        }
        // the skin in 3 slices along the line and 8 directions around it, in the start bone's frame
        const u = b.clone().sub(a0).normalize();
        const q0 = new THREE.Quaternion().setFromRotationMatrix(rw[fi]);
        const axes = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)].map(x => x.applyQuaternion(q0));
        const e1 = axes.reduce((m, x) => (Math.abs(x.dot(u)) < Math.abs(m.dot(u)) ? x : m)).clone().projectOnPlane(u).normalize();
        const e2 = u.clone().cross(e1);
        const rounds = [[], [], []], dirs = [0, 1, 2].map(() => Array.from({ length: 8 }, () => []));
        for (const [dist, t, x, y, z] of d) {
          const r = new THREE.Vector3(x, y, z).sub(a0.clone().lerp(b, THREE.MathUtils.clamp(t, 0, 1)));
          const k = slice(THREE.MathUtils.clamp(t, 0, 1));
          rounds[k].push(dist);
          dirs[k][((Math.round(Math.atan2(r.dot(e2), r.dot(e1)) / (Math.PI / 4)) % 8) + 8) % 8].push(r.length());
        }
        const pct = (v, f, dflt) => { if (v.length < 4) return dflt; const w = [...v].sort((x, y) => x - y); return THREE.MathUtils.clamp(w[Math.floor(w.length * f)], 0.01, 0.3); };
        if (d.length >= 16) {
          cap.rs = rounds.map(v => pct(v, 0.6, cap.r));
          const qi = q0.clone().invert();
          cap.sectors = dirs.map((sl, k) => sl.map(v => pct(v, 0.9, cap.rs[k])));     // the skin: what rests on the furniture
          cap.sectorsIn = dirs.map((sl, k) => sl.map(v => pct(v, 0.7, cap.rs[k])));   // a little inside it: body against body
          cap.e1 = e1.clone().applyQuaternion(qi).toArray();                            // in the start bone's own frame
          cap.e2 = e2.clone().applyQuaternion(qi).toArray();
        }
      }
      out.push(cap);
    }
  }
  v._caps = out;
  return out;
}

// A capsule where the body is now (world space): {a, b, r}. The head's line goes 9 cm up from the head joint.
const _m = new THREE.Matrix4(), _q = new THREE.Quaternion(), _s = new THREE.Vector3();
export function capsuleNow(v, c, { fresh = true } = {}) {
  const fb = v.bones[c.fromI];
  if (!fb) return null;
  if (fresh) fb.updateWorldMatrix(true, false);
  let a;
  if (c.mid) {
    const l = v.bones[c.mid[0]], r = v.bones[c.mid[1]];
    if (fresh) { l.updateWorldMatrix(true, false); r.updateWorldMatrix(true, false); }
    a = new THREE.Vector3().setFromMatrixPosition(l.matrixWorld).add(new THREE.Vector3().setFromMatrixPosition(r.matrixWorld)).multiplyScalar(0.5);
  } else a = new THREE.Vector3().setFromMatrixPosition(fb.matrixWorld);
  let b;
  if (c.toI >= 0) {
    const tb = v.bones[c.toI];
    if (fresh) tb.updateWorldMatrix(true, false);
    b = new THREE.Vector3().setFromMatrixPosition(tb.matrixWorld);
  } else {
    fb.matrixWorld.decompose(_s, _q, _s);
    b = a.clone().add(new THREE.Vector3(1, 0, 0).applyQuaternion(_q).multiplyScalar(0.09));
  }
  const out = { a, b, r: c.r };
  if (c.sectors) { out.q = new THREE.Quaternion(); fb.matrixWorld.decompose(new THREE.Vector3(), out.q, new THREE.Vector3()); }   // for the direction radii
  return out;
}

// ---------------------------------------------------------------- the scan
function simName(app, id) { const s = app.store.sim(id); return s ? s.label : 'a sim'; }

// Everything a scan needs that does not change from frame to frame.
function setup(app, info) {
  const all = app.pipeline.entries().filter(e => e.v.group.visible !== false && e.sim.visible !== false);
  const caps = new Map(all.map(e => [e.sim.id, capsulesOf(e.v)]));
  const grid = info ? gridOf(info) : null;
  const furnLabel = (() => {
    const def = (app.furniture || []).find(f => f.id === app.store.project.furniture);
    return def ? 'the ' + def.label.toLowerCase() : $t('clipcheck.furniture');
  })();
  return { all, caps, grid, furnLabel };
}

// One frame (the pose is already applied): -> [{simId, part, otherId, otherPart, depth, limb}]
function frameHits(app, S, frame) {
  const now = new Map();
  for (const e of S.all) {
    e.v.group.updateMatrixWorld(true);
    now.set(e.sim.id, S.caps.get(e.sim.id).map(c => ({ c, ...capsuleNow(e.v, c, { fresh: false }) })));
  }
  const hits = [];
  const open = app.pipeline.lastOpen || new Map();
  for (const A of S.all) {
    const la = now.get(A.sim.id);
    // fingers inside a partner this frame (the openings say so): that hand may be there
    const fingerIn = new Set();
    for (const B of S.all) {
      if (B === A) continue;
      const o = open.get(B.sim.id) || {};
      for (const h of Object.values(o)) if (h && h.by === 'finger' && h.from === A.sim.id && h.open > 0.02) fingerIn.add(B.sim.id);
    }
    for (const x of la) {
      if (x.c.kind !== 'limb' && x.c.kind !== 'hand') continue;
      const hold = x.c.limb && A.sim.pins ? A.sim.pins[x.c.limb] : null;
      const heldOn = hold && !Array.isArray(hold) && hold.sim ? hold.sim : null;
      for (const B of S.all) {
        if (B === A) continue;
        for (const y of now.get(B.sim.id)) {
          if (x.c.part === 'hand' && fingerIn.has(B.sim.id) && ['pelvis', 'thigh'].includes(y.c.part)) continue;
          // two limbs meet: found once (from the side that comes first), not from both sims
          if ((y.c.kind === 'limb' || y.c.kind === 'hand') && `${A.sim.id}|${x.c.name}` > `${B.sim.id}|${y.c.name}`) continue;
          const depth = overlap(x, y);
          let limit = pairLimit(x.c, y.c);
          if (heldOn === B.sim.id) limit += LIMITS.held;             // a held hand presses a little into the skin
          if (depth > limit) hits.push({ simId: A.sim.id, part: x.c.name, otherId: B.sim.id, otherPart: y.c.name, depth, limb: x.c.limb });
        }
      }
      // its own body: arms against the torso and the thighs (parts next to each other are left out)
      if (ARMS.has(x.c.part)) {
        for (const y of la) {
          if (!SELF_TARGETS.has(y.c.part) || y === x) continue;
          if (y.c.fromI === x.c.fromI || y.c.fromI === x.c.toI || y.c.toI === x.c.fromI || (y.c.toI >= 0 && y.c.toI === x.c.toI)) continue;
          if (x.c.part === 'upper arm' && y.c.part === 'chest') continue;       // the shoulder sits on the chest
          const depth = overlap(x, y);
          if (depth > (LAP.has(y.c.part) ? LIMITS.selfLap : LIMITS.selfCore)) hits.push({ simId: A.sim.id, part: x.c.name, otherId: A.sim.id, otherPart: 'own ' + y.c.name, depth, limb: x.c.limb });
        }
      }
    }
    // the furniture: three points along each part
    if (S.grid) {
      for (const x of la) {
        let worst = 0;
        for (const t of [0, 0.5, 1]) {
          _p.copy(x.a).lerp(x.b, t);
          const h = gridHeight(S.grid, _p.x, _p.z);
          if (h === null) continue;
          const low = _p.y - reach(x, _DOWN, t, true);
          if (low < h - LIMITS.furniture && _p.y + x.r > h - 0.3) worst = Math.max(worst, h - low);
        }
        // the capsule says it may be in: the part's own skin (skinned now) says how deep it really is
        if (worst > LIMITS.furniture && x.c.verts && x.c.verts.length) worst = skinDepth(x.c, S.grid);
        if (worst > LIMITS.furniture) hits.push({ simId: A.sim.id, part: x.c.name, otherId: null, otherPart: S.furnLabel, depth: worst, limb: x.c.limb });
      }
    }
  }
  void frame;
  return hits;
}

// How deep a part's own skin is inside the furniture now (its vertices, skinned on the current pose; the bones'
// world matrices must be up to date): the most any of them is under the furniture's top, within 30 cm of it.
const _sv = new THREE.Vector3();
function skinDepth(c, grid) {
  let worst = 0;
  for (const [mesh, list] of c.verts) {
    if (!mesh.visible) continue;
    for (let n = 0; n < list.length; n++) {
      mesh.getVertexPosition(list[n], _sv);            // the sim's space is the world (the mesh is bound there)
      const h = gridHeight(grid, _sv.x, _sv.z);
      if (h === null || _sv.y > h || _sv.y < h - 0.3) continue;
      if (h - _sv.y > worst) worst = h - _sv.y;
    }
  }
  return worst;
}

// Hits over the frames -> issues: the same part in the same other part on frames next to each other is one issue.
function merge(app, frames, step, length) {
  const open = new Map(), out = [];
  const keyOf = x => [x.simId, x.part, x.otherId, x.otherPart].join('|');
  for (const { frame, hits } of frames) {
    const seen = new Set();
    for (const x of hits) {
      const k = keyOf(x);
      if (seen.has(k)) { const cur = open.get(k); if (cur) cur.depth = Math.max(cur.depth, x.depth); continue; }
      seen.add(k);
      const cur = open.get(k);
      if (cur && frame - cur.to <= step) { cur.to = frame; cur.depth = Math.max(cur.depth, x.depth); if (x.depth > cur.peakDepth) { cur.peakDepth = x.depth; cur.peak = frame; } }
      else { const it = { ...x, from: frame, to: frame, peak: frame, peakDepth: x.depth }; open.set(k, it); out.push(it); }
    }
  }
  for (const it of out) it.to = Math.min(length - 1, it.to + step - 1);
  // the same part in the same place again later in the loop (every stroke, say) is one issue with several times
  const groups = new Map();
  for (const it of out) {
    const k = keyOf(it), g = groups.get(k);
    if (!g) { groups.set(k, { ...it, ranges: [[it.from, it.to]] }); continue; }
    g.ranges.push([it.from, it.to]);
    if (it.peakDepth > g.peakDepth) { g.peakDepth = it.peakDepth; g.peak = it.peak; }
    g.depth = Math.max(g.depth, it.depth);
  }
  const list = [...groups.values()];
  for (const it of list) {
    it.depth = Math.round(it.depth * 1000) / 1000;
    it.frames = it.ranges.reduce((a, [f, t]) => a + t - f + 1, 0);
    it.text = describe(app, it);
  }
  return list.sort((a, b) => b.depth - a.depth);
}

export function describe(app, it) {
  const fps = app.store.project.fps || 30;
  const t = f => (f / fps).toFixed(1);
  const n = (it.ranges || []).length;
  const when = (it.from === it.to ? `${t(it.from)} s` : `${t(it.from)}-${t(it.to)} s`) + (n > 1 ? $t('clipcheck.and_more_times', { n: n - 1 }) : '');
  const cm = Math.max(1, Math.round(it.depth * 100));
  const who = simName(app, it.simId);
  const into = it.otherId === null ? it.otherPart : it.otherId === it.simId ? $t('clipcheck.their_part', { part: it.otherPart }) : $t('clipcheck.sims_part', { sim: simName(app, it.otherId), part: it.otherPart });
  return $t('clipcheck.s_goes_cm_into', { when, who, part: it.part, cm, into });
}

function furnInfoNow(app) {
  const id = app.store.project.furniture;
  if (!id || id === 'floor') return null;
  const known = app._furnInfoKnown && app._furnInfoKnown.get(id);
  return known || null;
}

// The whole loop, all at once (used before Send to game: about 45 frames with step 2).
export function scanClipping(app, { step = 1, info = furnInfoNow(app) } = {}) {
  const p = app.store.project, S = setup(app, info);
  const frames = [];
  const saved = app.pipeline.editing;
  app.pipeline.editing = null;
  try {
    for (let k = 0; k < p.length; k += step) {
      app.pipeline.apply(k, { physics: false, overrides: false });
      frames.push({ frame: k, hits: frameHits(app, S, k) });
    }
  } finally { app.pipeline.editing = saved; }
  app.applyPoses(false);
  return merge(app, frames, step, p.length);
}

// The same, 20 frames per animation frame so the window stays responsive. Resolves after the scan; the view is put
// back as it was.
export async function checkClipping(app, { step = 1, onProgress = null } = {}) {
  const p = app.store.project;
  let info = null;
  const id = p.furniture;
  if (id && id !== 'floor') {
    try { info = app._furnitureInfo ? await app._furnitureInfo(id) : null; } catch { info = null; }
  }
  const S = setup(app, info);
  const frames = [];
  let k = 0;
  const saved = app.pipeline.editing;
  await new Promise(done => {
    const run = () => {
      app.pipeline.editing = null;
      try {
        for (let n = 0; n < 20 && k < p.length; n++, k += step) {
          app.pipeline.apply(k, { physics: false, overrides: false });
          frames.push({ frame: k, hits: frameHits(app, S, k) });
        }
      } finally { app.pipeline.editing = saved; }
      if (onProgress) try { onProgress(Math.min(1, k / p.length)); } catch { /* the ring is gone */ }
      if (k < p.length) requestAnimationFrame(run); else done();
    };
    run();
  });
  app.applyPoses(false);
  return merge(app, frames, step, p.length);
}

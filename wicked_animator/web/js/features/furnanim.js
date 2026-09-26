// Furniture animation: the bed, a couch, a chair or a table moves with the animation - slid, tipped over, lifted and
// thrown - and a bed's blanket and pillows move with the sims (by themselves, or by hand).
//
// "Bed animation" (the timeline bar; "Couch animation", "Chair animation"... for the others) opens its own rows on the
// timeline and a small panel over the stage:
//   - the piece itself (all kinds): keys by hand with the gizmo (T moves, R turns), or made for you: Tip over (four
//     ways), Lift and throw, Drop, Back in place. They only show here: WickedWhims keeps the real object standing still.
//   - the blanket and the pillows (beds): Automatic (the blanket covers the sims and follows their bodies when they are
//     "Under the blanket", else it lies pulled back to the foot of the bed; a pillow gives under a head) or By hand
//     (keys; "Start from automatic" turns the automatic movement into keys to fix). Send to game writes them as the
//     bed's own clip (backend/exporter.py), the way the game's own bed animations move a blanket.
// Every key sits inside the loop: the rows end where the animation ends, and a longer or shorter loop takes them along
// (the 'retime' hook). project.furnAnim = {parts: {object: {keys}, blanket: {mode, under, keys}, pillows: {mode, keys}}};
// a key is {f, v: {handle: [dx, dy, dz, qx, qy, qz, qw]}, l?} in the furniture's own space (l: straight to the next).
// A game bed's bedding is skinned to its rig (/api/furniture_mesh "skin"); the stand-in bed's blanket and pillows get
// the same kind of weights here, so both bend the same way.
import * as THREE from 'three';
import { h, icon, toast, contextMenu } from '../ui.js';

const ROW_H = 22;
const ID = [0, 0, 0, 0, 0, 0, 1];
const KIND_WORD = { bed: 'Bed', sofa: 'Couch', armchair: 'Chair', chair: 'Chair', table: 'Table', counter: 'Counter' };
const MOVABLE = new Set(['bed', 'sofa', 'armchair', 'chair', 'table']);
// the game beds' bones (RIG of objects 51719 and 288627) for each handle
const BONES = {
  single: {
    blanket: { head: '_bind_SB_blanket_Top_', middle: '_bind_SB_blanket_Mid_', foot: '_bind_SB_blanket_Bottom_' },
    pillows: { pillow: '_bind_SB_Pillow_trans_' },
    child: { _bind_SB_Pillow_squish_: '_bind_SB_Pillow_trans_' },
    mean: {},
  },
  double: {
    blanket: { headL: '_bind_DB_blanket_Top_L_', headR: '_bind_DB_blanket_Top_R_', middleL: '_bind_DB_blanket_Mid_L_',
      middleR: '_bind_DB_blanket_Mid_R_', footL: '_bind_DB_blanket_Bottom_L_', footR: '_bind_DB_blanket_Bottom_R_' },
    pillows: { left: '_bind_DB_Pillow_trans_L_', right: '_bind_DB_Pillow_trans_R_' },
    child: { _bind_DB_Pillow_squish_L_: '_bind_DB_Pillow_trans_L_', _bind_DB_Pillow_squish_R_: '_bind_DB_Pillow_trans_R_' },
    // the middle bones of the double blanket follow both halves
    mean: { _bind_DB_blanket_Top_: ['headL', 'headR'], _bind_DB_blanket_Mid_: ['middleL', 'middleR'], _bind_DB_blanket_Bottom_: ['footL', 'footR'] },
  },
};
const HANDLE_WORD = { head: 'top', middle: 'middle', foot: 'foot', headL: 'top left', headR: 'top right', middleL: 'middle left',
  middleR: 'middle right', footL: 'foot left', footR: 'foot right', pillow: 'pillow', left: 'left pillow', right: 'right pillow' };
// body points that lift the blanket: bone, how far the body reaches above it (m)
const BODY = [['b__Pelvis__', 0.13], ['b__Spine1__', 0.12], ['b__Spine2__', 0.12], ['b__Neck__', 0.08], ['b__Head__', 0.11],
  ['b__L_Thigh__', 0.09], ['b__R_Thigh__', 0.09], ['b__L_Calf__', 0.07], ['b__R_Calf__', 0.07], ['b__L_Foot__', 0.06], ['b__R_Foot__', 0.06],
  ['b__L_UpperArm__', 0.06], ['b__R_UpperArm__', 0.06], ['b__L_Hand__', 0.04], ['b__R_Hand__', 0.04]];

const _v = new THREE.Vector3(), _q = new THREE.Quaternion();
const smooth = t => t * t * (3 - 2 * t);
const r5 = x => Math.round(x * 1e5) / 1e5;
const valOf = (p, q) => [r5(p.x), r5(p.y), r5(p.z), r5(q.x), r5(q.y), r5(q.z), r5(q.w)];

// ---------------------------------------------------------------- the animation's data
function fa(app, proj = app.store.project) { return proj.furnAnim || null; }
function ensure(app) {
  const p = app.store.project;
  if (!p.furnAnim) p.furnAnim = { parts: { object: { keys: [] }, blanket: { mode: 'auto', under: false, keys: [] }, pillows: { mode: 'auto', keys: [] } } };
  const parts = p.furnAnim.parts = p.furnAnim.parts || {};
  parts.object = parts.object || { keys: [] };
  parts.blanket = parts.blanket || { mode: 'auto', under: false, keys: [] };
  parts.pillows = parts.pillows || { mode: 'auto', keys: [] };
  return p.furnAnim;
}
const partOf = (app, name, proj) => { const d = fa(app, proj); return d && d.parts && d.parts[name] || null; };
const pause = app => { if (app.playing) app.setPlaying(false); };
const sortKeys = keys => keys.sort((a, b) => a.f - b.f);

function mix(a, b, t) {
  const out = {};
  for (const k of new Set([...Object.keys(a || {}), ...Object.keys(b || {})])) {
    const x = (a && a[k]) || ID, y = (b && b[k]) || x;
    const qa = new THREE.Quaternion(x[3], x[4], x[5], x[6]), qb = new THREE.Quaternion(y[3], y[4], y[5], y[6]);
    qa.slerp(qb, t);
    out[k] = [x[0] + (y[0] - x[0]) * t, x[1] + (y[1] - x[1]) * t, x[2] + (y[2] - x[2]) * t, qa.x, qa.y, qa.z, qa.w];
  }
  return out;
}

// The keys' value at frame f: smooth between keys (straight when the key says so), held before the first and after
// the last. -> {handle: value} or null (no keys).
function sample(keys, f) {
  if (!keys || !keys.length) return null;
  if (f <= keys[0].f) return keys[0].v;
  const last = keys[keys.length - 1];
  if (f >= last.f) return last.v;
  let i = 0;
  while (i < keys.length - 2 && keys[i + 1].f <= f) i++;
  const a = keys[i], b = keys[i + 1], t0 = (f - a.f) / Math.max(1e-6, b.f - a.f);
  return mix(a.v, b.v, a.l ? t0 : smooth(t0));
}

function setKey(part, f, v, { linear = false } = {}) {
  const k = part.keys.find(x => x.f === f);
  if (k) { k.v = { ...k.v, ...v }; if (linear) k.l = 1; else delete k.l; }
  else part.keys.push(linear ? { f, v, l: 1 } : { f, v });
  sortKeys(part.keys);
}

// ---------------------------------------------------------------- the piece on the stage and its handles
function currentGroup(app) {
  const g = app.vp.furniture && app.vp.furniture.children[0];
  return g && g.children.length ? g : null;
}
function defOf(app) { return (app.furniture || []).find(f => f.id === app.store.project.furniture) || null; }
const movable = def => !!def && MOVABLE.has(def.kind);
export const kindWord = def => KIND_WORD[def && def.kind] || 'Furniture';

// Everything needed to move this piece: its box, and for a bed its handles (rest places in its own space), the
// meshes that bend with them and how their bones map to the handles.
// (measured with the piece standing where it belongs)
function prepare(app, g) {
  const saved = { p: g.position.clone(), q: g.quaternion.clone() };
  g.position.set(0, 0, 0); g.quaternion.identity(); g.updateMatrixWorld(true);
  try { return prepareAtRest(app, g); } finally { g.position.copy(saved.p); g.quaternion.copy(saved.q); g.updateMatrixWorld(true); }
}
function prepareAtRest(app, g) {
  const def = defOf(app);
  const box = new THREE.Box3().setFromObject(g);
  const rig = { g, def, box, bed: null };
  if (def && def.kind === 'bed') {
    const skinned = []; g.traverse(o => { if (o.isMesh && o.userData.skin) skinned.push(o); });
    const bones = new Map();
    for (const m of skinned) m.userData.skin.bones.forEach((n, i) => { if (!bones.has(n)) bones.set(n, m.userData.skin.rest[i]); });
    const double = [...bones.keys()].some(n => n.includes('_DB_')) || (!skinned.length && !!(g.userData.bed && g.userData.bed.double))
      || (!skinned.length && /double/.test(def.id));
    const B = BONES[double ? 'double' : 'single'];
    const real = skinned.length > 0 && Object.values(B.blanket).every(n => bones.has(n));
    const handles = { blanket: {}, pillows: {} };
    if (real) {
      for (const part of ['blanket', 'pillows']) for (const [hn, bn] of Object.entries(B[part])) handles[part][hn] = new THREE.Vector3().fromArray(bones.get(bn) || [0, 0.6, 0]);
    } else fakeHandles(g, handles, double);
    const pil = Object.values(handles.pillows)[0], mid = handles.blanket.middle || handles.blanket.middleL;
    const headDir = pil && mid ? Math.sign(pil.z - mid.z) || -1 : -1;
    rig.bed = { double, real, handles, headDir, B, meshes: [] };
    if (real) {
      for (const m of skinned) {
        m.geometry = m.geometry.clone();                       // this copy bends; the cached one stays as it was
        const s = m.userData.skin;
        const map = s.bones.map((n, i) => {
          if (B.mean[n]) return { mean: B.mean[n], pivot: new THREE.Vector3().fromArray(s.rest[i]) };
          const parent = B.child[n];
          const hn = handleOfBone(B, parent || n);
          if (!hn) return null;
          const pv = parent && bones.has(parent) ? bones.get(parent) : s.rest[i];
          return { handle: hn, pivot: new THREE.Vector3().fromArray(pv) };
        });
        rig.bed.meshes.push({ mesh: m, base: Float32Array.from(m.geometry.attributes.position.array), off: new THREE.Vector3(), skin: s, map });
      }
    } else {
      g.traverse(o => {
        if (!o.isMesh || !o.userData.part) return;
        const own = o.geometry;
        o.geometry = own.clone();
        own.dispose();                                          // the stand-in's shapes are its own, not shared
        const pos = o.geometry.attributes.position, n = pos.count, idx = new Uint8Array(n * 4), w = new Float32Array(n * 4);
        let names, map;
        if (o.userData.part === 'blanket') {
          names = Object.keys(handles.blanket);
          const pts = names.map(k => handles.blanket[k]);
          const spanZ = Math.max(0.2, Math.abs(pts[0].z - pts[pts.length - 1].z) / (double ? 2 : 2));
          for (let v = 0; v < n; v++) {
            const x = pos.getX(v) + o.position.x, z = pos.getZ(v) + o.position.z;
            const ws = pts.map(p => Math.max(0, 1 - Math.abs(z - p.z) / spanZ) * (double ? Math.max(0.02, 1 - Math.abs(x - p.x) / Math.max(0.3, Math.abs(pts[0].x - pts[1].x))) : 1));
            const order = ws.map((x2, i) => [x2, i]).sort((a, b) => b[0] - a[0]).slice(0, 4);
            const sum = order.reduce((s2, [x2]) => s2 + x2, 0) || 1;
            order.forEach(([x2, i], k) => { idx[v * 4 + k] = i; w[v * 4 + k] = x2 / sum; });
          }
          map = names.map(k => ({ handle: k, pivot: handles.blanket[k] }));
        } else {
          const hn = double ? (o.userData.side === 'L' ? 'left' : 'right') : 'pillow';
          names = [hn];
          for (let v = 0; v < n; v++) { idx[v * 4] = 0; w[v * 4] = 1; }
          map = [{ handle: hn, pivot: handles.pillows[hn] }];
        }
        rig.bed.meshes.push({ mesh: o, base: Float32Array.from(pos.array), baseN: o.geometry.attributes.normal ? Float32Array.from(o.geometry.attributes.normal.array) : null,
          rigid: o.userData.part === 'pillow', off: o.position.clone(), skin: { bones: names, idx, w }, map });
      });
    }
  }
  return rig;
}
// Free the bending copies of a piece that left the stage (the game object's own meshes stay cached).
function disposeRig(rig) {
  if (!rig || !rig.bed) return;
  for (const M of rig.bed.meshes) { try { M.mesh.geometry.dispose(); } catch { /* already gone */ } }
}
function handleOfBone(B, bone) {
  for (const part of ['blanket', 'pillows']) for (const [hn, bn] of Object.entries(B[part])) if (bn === bone) return hn;
  return null;
}
// the stand-in bed (no game here): handles on its blanket and pillow boxes
function fakeHandles(g, handles, double) {
  let bl = null; const pl = [];
  g.traverse(o => { if (o.isMesh && o.userData.part === 'blanket') bl = o; if (o.isMesh && o.userData.part === 'pillow') pl.push(o); });
  const b = bl ? new THREE.Box3().setFromObject(bl) : new THREE.Box3(new THREE.Vector3(-0.5, 0.5, -0.4), new THREE.Vector3(0.5, 0.56, 1));
  const y = b.max.y, zs = [b.min.z + 0.12, (b.min.z + b.max.z) / 2, b.max.z - 0.12];
  const names = ['head', 'middle', 'foot'];
  if (double) {
    const xL = b.min.x + (b.max.x - b.min.x) * 0.25, xR = b.min.x + (b.max.x - b.min.x) * 0.75;
    names.forEach((n, i) => { handles.blanket[n + 'L'] = new THREE.Vector3(xL, y, zs[i]); handles.blanket[n + 'R'] = new THREE.Vector3(xR, y, zs[i]); });
  } else names.forEach((n, i) => { handles.blanket[n] = new THREE.Vector3((b.min.x + b.max.x) / 2, y, zs[i]); });
  for (const o of pl) {
    const hn = double ? (o.userData.side === 'L' ? 'left' : 'right') : 'pillow';
    handles.pillows[hn] = o.position.clone();
  }
}

// ---------------------------------------------------------------- automatic movement
// Body points of every shown sim, in the bed's own space.
function bodyPoints(app, g, views = app.simViews, all = false) {
  const out = [];
  for (const [, v] of views) {
    if (!all && !v.group.visible) continue;
    for (const [bn, r] of BODY) {
      if (!v.bone(bn)) continue;
      const w = v.worldPos(bn, new THREE.Vector3());
      out.push({ p: g ? g.worldToLocal(w) : w, r, head: bn === 'b__Head__' });
    }
  }
  return out;
}

// The blanket, by itself. Under the blanket: each handle rises over the bodies near it (a soft round reach, the body's
// own thickness on top) and slides a little toward them. Otherwise it lies pulled back to the foot of the bed.
function autoBlanket(bed, pts, under) {
  const out = {}, H = bed.handles.blanket, reach = bed.double ? 0.42 : 0.5;
  const names = Object.keys(H);
  if (!under) {
    // folded toward the foot: the top half-way down, the middle toward the foot, a little bulk where it gathers
    const foot = bed.double ? ['footL', 'footR'] : ['foot'];
    for (const n of names) {
      const r = H[n], side = n.endsWith('L') ? 'L' : n.endsWith('R') ? 'R' : '';
      const f = H[(bed.double ? 'foot' + side : 'foot')] || H[foot[0]];
      const k = n.startsWith('head') ? 0.62 : n.startsWith('middle') ? 0.45 : 0;
      const dz = (f.z - r.z) * k, dy = n.startsWith('foot') ? 0.05 : n.startsWith('middle') ? 0.07 : 0.06;
      out[n] = [0, dy, dz, 0, 0, 0, 1];
    }
    return out;
  }
  for (const n of names) {
    const r = H[n];
    let lift = 0, wx = 0, wz = 0, ws = 0;
    for (const { p, r: thick } of pts) {
      const d = Math.hypot(p.x - r.x, p.z - r.z);
      if (d >= reach) continue;
      const k = smooth(1 - d / reach);
      const top = p.y + thick - r.y;
      if (top <= 0) continue;
      lift = Math.max(lift, top * k);
      wx += (p.x - r.x) * k; wz += (p.z - r.z) * k; ws += k;
    }
    lift = Math.min(0.75, lift);
    const sx = ws ? Math.max(-0.1, Math.min(0.1, (wx / ws) * 0.25)) : 0, sz = ws ? Math.max(-0.14, Math.min(0.14, (wz / ws) * 0.25)) : 0;
    out[n] = [sx, lift, sz, 0, 0, 0, 1];
  }
  return out;
}

// A pillow gives under a head resting on it and turns a little toward it.
function autoPillows(bed, pts) {
  const out = {};
  for (const [n, r] of Object.entries(bed.handles.pillows)) {
    let best = null, bd = 0.34;
    for (const q of pts) {
      if (!q.head) continue;
      const d = Math.hypot(q.p.x - r.x, q.p.z - r.z), up = q.p.y - r.y;
      if (d < bd && up > -0.1 && up < 0.32) { bd = d; best = q; }
    }
    if (!best) { out[n] = ID.slice(); continue; }
    const k = smooth(1 - bd / 0.34);
    const dx = Math.max(-0.05, Math.min(0.05, (best.p.x - r.x) * 0.3 * k)), dz = Math.max(-0.05, Math.min(0.05, (best.p.z - r.z) * 0.3 * k));
    const tilt = new THREE.Quaternion().setFromEuler(new THREE.Euler(dz * 2.2, 0, -dx * 2.2));
    out[n] = [dx, -0.055 * k, dz, tilt.x, tilt.y, tilt.z, tilt.w];
  }
  return out;
}

// Keys made on the other bed size still work: a single bed's handle takes the middle of the double's left and right,
// a double bed's halves both take the single's.
const PAIRS = { head: ['headL', 'headR'], middle: ['middleL', 'middleR'], foot: ['footL', 'footR'], pillow: ['left', 'right'] };
function adapt(v, bed, name) {
  const want = Object.keys(bed.handles[name]), out = { ...v };
  for (const hn of want) {
    if (out[hn]) continue;
    const pair = PAIRS[hn];
    if (pair && (v[pair[0]] || v[pair[1]])) { out[hn] = mix({ a: v[pair[0]] || v[pair[1]] }, { a: v[pair[1]] || v[pair[0]] }, 0.5).a; continue; }
    const single = Object.keys(PAIRS).find(k => PAIRS[k].includes(hn));
    if (single && v[single]) out[hn] = v[single];
  }
  return out;
}

// ---------------------------------------------------------------- what shows at a frame
function partValues(app, F, name, f, pts, proj) {
  const part = partOf(app, name, proj), bed = F.rig && F.rig.bed;
  const live = F.live && F.live[name];
  let v;
  if (name === 'object') v = (part && sample(part.keys, f)) || { root: ID };
  else if (!bed) return null;
  else if (part && part.mode === 'hand') v = adapt(sample(part.keys, f) || {}, bed, name);
  else if (part && name === 'blanket') v = autoBlanket(bed, pts(), !!part.under);
  else if (part && name === 'pillows') v = autoPillows(bed, pts());
  else v = {};
  return live ? { ...v, ...live } : v;
}

function setObject(g, val) {
  const x = val || ID;
  g.position.set(x[0], x[1], x[2]);
  g.quaternion.set(x[3], x[4], x[5], x[6]).normalize();
}

// Bend the bedding: each vertex moves with its bones' handles (turned about each bone's pivot).
function deform(bed, vals) {
  for (const M of bed.meshes) {
    const { mesh, base, off, skin, map } = M;
    const D = map.map(m => {
      if (!m) return null;
      let x;
      if (m.mean) { const a = vals[m.mean[0]] || ID, b = vals[m.mean[1]] || ID; x = mix({ a }, { a: b }, 0.5).a; }
      else x = vals[m.handle] || null;
      if (!x || (Math.abs(x[0]) + Math.abs(x[1]) + Math.abs(x[2]) < 1e-7 && Math.abs(1 - Math.abs(x[6])) < 1e-7)) return null;
      return { t: new THREE.Vector3(x[0], x[1], x[2]), q: new THREE.Quaternion(x[3], x[4], x[5], x[6]).normalize(), c: m.pivot };
    });
    const pos = mesh.geometry.attributes.position, arr = pos.array, n = pos.count;
    const moving = D.some(Boolean);
    if (!moving && !M.bent) continue;
    for (let v = 0; v < n; v++) {
      const bx = base[v * 3] + off.x, by = base[v * 3 + 1] + off.y, bz = base[v * 3 + 2] + off.z;
      let ax = 0, ay = 0, az = 0;
      if (moving) for (let k = 0; k < 4; k++) {
        const w = skin.w[v * 4 + k];
        if (!(w > 0)) continue;
        const d = D[skin.idx[v * 4 + k]];
        if (!d) continue;
        _v.set(bx - d.c.x, by - d.c.y, bz - d.c.z).applyQuaternion(d.q);
        ax += w * (_v.x + d.c.x + d.t.x - bx); ay += w * (_v.y + d.c.y + d.t.y - by); az += w * (_v.z + d.c.z + d.t.z - bz);
      }
      arr[v * 3] = base[v * 3] + ax; arr[v * 3 + 1] = base[v * 3 + 1] + ay; arr[v * 3 + 2] = base[v * 3 + 2] + az;
    }
    pos.needsUpdate = true;
    const nrm = mesh.geometry.attributes.normal;
    if (M.rigid && M.baseN && nrm) {
      // a whole pillow turns: its normals turn with it (keeps the rounded shading)
      const d = D[0], q = d ? d.q : new THREE.Quaternion();
      for (let v = 0; v < nrm.count; v++) { _v.set(M.baseN[v * 3], M.baseN[v * 3 + 1], M.baseN[v * 3 + 2]).applyQuaternion(q); nrm.setXYZ(v, _v.x, _v.y, _v.z); }
      nrm.needsUpdate = true;
    } else mesh.geometry.computeVertexNormals();
    mesh.geometry.computeBoundingSphere();
    M.bent = moving;
  }
}

// The game bones' movement for a set of handle values (export): each bone's shift about its own rest place.
function boneDeltas(bed, vals, restOf) {
  const out = {};
  const B = bed.B;
  for (const part of ['blanket', 'pillows']) for (const [hn, bn] of Object.entries(B[part])) out[bn] = vals[hn] || ID;
  for (const [bn, pair] of Object.entries(B.mean)) out[bn] = mix({ a: vals[pair[0]] || ID }, { a: vals[pair[1]] || ID }, 0.5).a;
  for (const [child, parent] of Object.entries(B.child)) {
    const x = out[parent] || ID, pc = restOf(parent), cc = restOf(child);
    if (!pc || !cc) { out[child] = x; continue; }
    const q = new THREE.Quaternion(x[3], x[4], x[5], x[6]);
    const rel = new THREE.Vector3().fromArray(cc).sub(new THREE.Vector3().fromArray(pc));
    const moved = rel.clone().applyQuaternion(q).sub(rel);
    out[child] = [x[0] + moved.x, x[1] + moved.y, x[2] + moved.z, x[3], x[4], x[5], x[6]];
  }
  return out;
}

// ---------------------------------------------------------------- made for you: tipping, throwing, dropping
// Keys from frame f0 on, fitted inside the loop. samples(t) -> [pos, quat] for t in 0..1, n steps; straight keys (the
// path itself carries the timing: a fall speeds up, a throw arcs).
function writePath(app, F, f0, frames, samples, n) {
  pause(app);
  const len = app.store.project.length;
  let span = frames;
  if (f0 + span > len - 1) { if (len - 1 - f0 >= 6) span = len - 1 - f0; else { f0 = Math.max(0, len - 1 - span); span = Math.min(span, len - 1 - f0); } }
  if (span < 2) { toast('There is no room left in the loop - go back a little on the timeline.'); return false; }
  app.store.checkpoint('Furniture animation');
  const part = ensure(app).parts.object;
  part.keys = part.keys.filter(k => k.f < f0 || k.f > f0 + span);
  for (let i = 0; i <= n; i++) {
    const t = i / n, [p, q] = samples(t);
    setKey(part, Math.round(f0 + t * span), { root: valOf(p, q) }, { linear: true });
  }
  app.store.setDirty(true);
  refresh(app);
  return true;
}
function currentRoot(app, F) {
  const part = partOf(app, 'object'), f = Math.round(app.store.frame);
  const v = (part && sample(part.keys, f)) || { root: ID };
  const x = v.root || ID;
  return { p: new THREE.Vector3(x[0], x[1], x[2]), q: new THREE.Quaternion(x[3], x[4], x[5], x[6]).normalize() };
}
// the lowest point of the piece when turned by q (its box corners), to rest it on the floor
function lowest(F, q) {
  const b = F.rig.box; let lo = Infinity;
  for (const x of [b.min.x, b.max.x]) for (const y of [b.min.y, b.max.y]) for (const z of [b.min.z, b.max.z]) lo = Math.min(lo, _v.set(x, y, z).applyQuaternion(q).y);
  return lo;
}

function tipOver(app, F, way) {
  const { p: p0, q: q0 } = currentRoot(app, F), b = F.rig.box;
  // the edge it falls over (its own space) and the turn
  const E = { back: [new THREE.Vector3(0, 0, b.min.z), new THREE.Vector3(-1, 0, 0)], front: [new THREE.Vector3(0, 0, b.max.z), new THREE.Vector3(1, 0, 0)],
    left: [new THREE.Vector3(b.max.x, 0, 0), new THREE.Vector3(0, 0, -1)], right: [new THREE.Vector3(b.min.x, 0, 0), new THREE.Vector3(0, 0, 1)] }[way];
  const pivot = E[0].clone().applyQuaternion(q0).add(p0), axis = E[1].clone().applyQuaternion(q0).normalize();
  const at = ang => { const R = new THREE.Quaternion().setFromAxisAngle(axis, ang); return [p0.clone().sub(pivot).applyQuaternion(R).add(pivot), R.multiply(q0.clone())]; };
  const fall = 16, settle = 8;
  const ok = writePath(app, F, Math.round(app.store.frame), fall + settle, t => {
    const tf = fall / (fall + settle);
    if (t <= tf) return at((Math.PI / 2) * Math.pow(t / tf, 2));            // gravity: slow, then fast
    const u = (t - tf) / (1 - tf);
    return at(Math.PI / 2 - 0.12 * Math.sin(Math.PI * u) * (1 - u));         // a small bounce, then still
  }, 12);
  if (ok) toast(`${kindWord(F.rig.def)} tips over - the keys are on the timeline.`);
}

function liftAndThrow(app, F) {
  const { p: p0, q: q0 } = currentRoot(app, F);
  const fwd = new THREE.Vector3(0, 0, 1).applyQuaternion(q0).setY(0).normalize(), side = new THREE.Vector3(1, 0, 0).applyQuaternion(q0).normalize();
  const lift = 12, fly = 14, land = 8, total = lift + fly + land;
  const spin = new THREE.Quaternion().setFromAxisAngle(side, Math.PI / 2).multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), 0.5));
  const qEnd = spin.clone().multiply(q0);
  const endY = -lowest(F, qEnd), up = 0.6;
  const ok = writePath(app, F, Math.round(app.store.frame), total, t => {
    const f = t * total;
    if (f <= lift) {                                                            // lifted, tilting back a little
      const u = smooth(f / lift);
      return [p0.clone().add(new THREE.Vector3(0, up * u, 0)), new THREE.Quaternion().setFromAxisAngle(side, -0.18 * u).multiply(q0.clone())];
    }
    if (f <= lift + fly) {                                                      // thrown: an arc forward, turning over
      const u = (f - lift) / fly;
      const y = (1 - u) * (p0.y + up) + u * endY + 0.35 * 4 * u * (1 - u);
      const pos = p0.clone().addScaledVector(fwd, 1.6 * u).setY(y);
      return [pos, new THREE.Quaternion().setFromAxisAngle(side, -0.18 * (1 - u)).multiply(q0.clone()).slerp(qEnd, u)];
    }
    const u = (f - lift - fly) / land;                                          // lands, rocks once, lies still
    const pos = p0.clone().addScaledVector(fwd, 1.6 + 0.12 * smooth(u)).setY(endY);
    return [pos, qEnd.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), 0.1 * Math.sin(Math.PI * u) * (1 - u)))];
  }, 20);
  if (ok) toast(`${kindWord(F.rig.def)} is lifted and thrown - fix any key by hand.`);
}

function drop(app, F) {
  const { p: p0, q: q0 } = currentRoot(app, F);
  const floorY = -lowest(F, q0), hgt = p0.y - floorY;
  if (hgt < 0.01) { toast('It is already on the floor.'); return; }
  const fall = Math.max(4, Math.round(30 * Math.sqrt((2 * hgt) / 9.8))), settle = 6;
  const ok = writePath(app, F, Math.round(app.store.frame), fall + settle, t => {
    const tf = fall / (fall + settle);
    if (t <= tf) { const u = t / tf; return [p0.clone().setY(p0.y - hgt * u * u), q0.clone()]; }
    const u = (t - tf) / (1 - tf);
    return [p0.clone().setY(floorY + Math.min(0.06, hgt * 0.1) * Math.sin(Math.PI * u) * (1 - u)), q0.clone()];
  }, 10);
  if (ok) toast('It drops to the floor.');
}

function backInPlace(app, F) {
  const { p: p0, q: q0 } = currentRoot(app, F);
  const ok = writePath(app, F, Math.round(app.store.frame), 12, t => { const u = smooth(t); return [p0.clone().lerp(new THREE.Vector3(), u), q0.clone().slerp(new THREE.Quaternion(), u)]; }, 6);
  if (ok) toast('Back where it belongs.');
}

// "Start from automatic": the automatic movement as keys (every 5 frames), to fix by hand.
function bakeAuto(app, F, name) {
  const part = ensure(app).parts[name], len = app.store.project.length, g = F.rig.g, bed = F.rig.bed;
  if (!bed) return;
  const keys = [], at = Math.round(app.store.frame);
  for (let f = 0; f < len; f += 5) keys.push(f);
  if (keys[keys.length - 1] !== len - 1) keys.push(len - 1);
  const out = [];
  for (const f of keys) {
    app.pipeline.apply(f, { physics: true, overrides: false });
    const pts = bodyPoints(app, g);
    out.push({ f, v: name === 'blanket' ? autoBlanket(bed, pts, !!part.under) : autoPillows(bed, pts), l: 1 });
  }
  part.keys = out.map(k => ({ ...k, v: Object.fromEntries(Object.entries(k.v).map(([hn, x]) => [hn, x.map(r5)])) }));
  part.mode = 'hand';
  app.store.frame = at;
  app.applyPoses(false);
}

// ---------------------------------------------------------------- the timeline rows
function rowsFor(app, F) {
  const def = defOf(app), bed = def && def.kind === 'bed';
  const list = [['object', kindWord(def)]];
  if (bed) list.push(['blanket', 'Blanket'], ['pillows', 'Pillows']);
  return list.map(([name, word], i) => {
    let drag = null;
    return {
      id: 'furn-' + name, height: ROW_H, order: 5 + i,
      get label() { const pt = partOf(app, name); return pt && name !== 'object' && pt.mode !== 'hand' ? `${word} · automatic` : word; },
      draw(g, ctx) {
        const { x0, x1, y, h: hh, xAt } = ctx, len = app.store.project.length, pt = partOf(app, name);
        const sel = F.sel === name;
        g.save(); g.beginPath(); g.rect(x0, y, x1 - x0, hh); g.clip();
        g.fillStyle = sel ? 'rgba(255,79,154,0.07)' : 'rgba(255,255,255,0.02)';
        g.fillRect(x0, y, Math.min(x1, xAt(len)) - x0, hh);
        if (pt && name !== 'object' && pt.mode !== 'hand') {
          // automatic: a soft wave the length of the loop
          g.strokeStyle = 'rgba(96,165,250,0.55)'; g.lineWidth = 1.5; g.beginPath();
          for (let x = Math.max(x0, xAt(0)); x <= Math.min(x1, xAt(len - 1)); x += 3) {
            const yy = y + hh / 2 + Math.sin(x / 7) * 3;
            if (x === Math.max(x0, xAt(0))) g.moveTo(x, yy); else g.lineTo(x, yy);
          }
          g.stroke();
        } else if (pt && pt.keys.length) {
          g.strokeStyle = 'rgba(255,79,154,0.35)'; g.lineWidth = 2;
          g.beginPath(); g.moveTo(xAt(pt.keys[0].f), y + hh / 2); g.lineTo(xAt(pt.keys[pt.keys.length - 1].f), y + hh / 2); g.stroke();
          for (const k of pt.keys) {
            const x = xAt(k.f); if (x < x0 - 6 || x > x1 + 6) continue;
            const s = k.l ? 3.2 : 4.6;
            g.fillStyle = sel ? '#ff4f9a' : '#d9a1bf';
            g.beginPath(); g.moveTo(x, y + hh / 2 - s); g.lineTo(x + s, y + hh / 2); g.lineTo(x, y + hh / 2 + s); g.lineTo(x - s, y + hh / 2); g.closePath(); g.fill();
          }
        } else {
          g.fillStyle = 'rgba(255,255,255,0.28)'; g.font = '500 10.5px Plus Jakarta Sans, Segoe UI, sans-serif'; g.textBaseline = 'middle';
          g.fillText(name === 'object' ? 'Drag it on the stage, or use Tip over, Lift and throw...' : 'By hand: drag a dot on the stage', x0 + 8, y + hh / 2 + 0.5);
        }
        // the end of the loop: nothing goes past it
        const xe = xAt(len - 1);
        if (xe < x1) { g.fillStyle = 'rgba(0,0,0,0.35)'; g.fillRect(xe + 1, y, x1 - xe, hh); }
        g.restore();
      },
      hit(x, y, ctx) {
        const pt = partOf(app, name);
        if (pt) for (const k of pt.keys) if (Math.abs(ctx.xAt(k.f) - x) <= 5) return k;
        return { row: name };
      },
      tooltip(item) { return item && item.f !== undefined ? `${word} key at ${item.f} · drag to move, right-click for more` : `${word} · click to pick it`; },
      onDown(item, e, ctx) {
        select(app, name);
        if (item && item.f !== undefined) { drag = { key: item, grab: item.f, moved: false }; app.setFrame(item.f); }
        app.timeline.draw();
      },
      onMove(item, frame) {
        if (!drag) return;
        const pt = partOf(app, name), len = app.store.project.length;
        const f = Math.max(0, Math.min(len - 1, frame));
        if (f === drag.key.f || pt.keys.some(k => k !== drag.key && k.f === f)) return;
        if (!drag.moved) { app.store.checkpoint('Move a furniture key'); drag.moved = true; }
        drag.key.f = f; sortKeys(pt.keys);
        app.setFrame(f);
      },
      onUp() { const d = drag; drag = null; if (d && d.moved) { app.store.setDirty(true); refresh(app); } },
      onContext(item, frame, e) {
        const pt = partOf(app, name);
        const items = [{ label: 'Key here', icon: 'key', onClick: () => keyHere(app, F, name, frame) }];
        if (item && item.f !== undefined) items.push({ label: 'Delete this key', icon: 'trash', danger: true, onClick: () => { app.store.checkpoint('Delete a furniture key'); pt.keys.splice(pt.keys.indexOf(item), 1); app.store.setDirty(true); refresh(app); } });
        if (pt && pt.keys.length) items.push({ label: `Delete every ${word.toLowerCase()} key`, icon: 'trash', danger: true, onClick: () => { app.store.checkpoint('Delete furniture keys'); pt.keys = []; app.store.setDirty(true); refresh(app); } });
        contextMenu(e.clientX, e.clientY, items);
      },
      onDblClick(item, frame) { if (!item || item.f === undefined) keyHere(app, F, name, frame); },
    };
  });
}

// A key at frame f with what shows there now (an automatic part turns "by hand" first, from its automatic movement).
function keyHere(app, F, name, f) {
  if (!F.rig) return;
  pause(app);
  app.store.checkpoint('Furniture key');
  const d = ensure(app), part = d.parts[name];
  if (name !== 'object' && part.mode !== 'hand') bakeAuto(app, F, name);
  const v = partValues(app, F, name, f, () => bodyPoints(app, F.rig.g));
  if (v) setKey(part, Math.max(0, Math.min(app.store.project.length - 1, Math.round(f))), JSON.parse(JSON.stringify(v)));
  app.store.setDirty(true);
  refresh(app);
}

// ---------------------------------------------------------------- picking and dragging
function select(app, name, handle = null) {
  const F = app._furn;
  F.sel = name; F.handle = handle;
  if (F.detach) { F.detach(); F.detach = null; }
  if (name === 'object' && F.rig) attachObject(app, F);
  else if (handle) attachHandle(app, F, name, handle);
  drawCard(app);
  app.timeline && app.timeline.draw();
}

function attachObject(app, F) {
  const g = F.rig.g;
  F.detach = app.interact.attachGizmo(g, {
    modes: ['translate', 'rotate'], size: 0.9,
    onStart: () => { app.store.checkpoint(`Move the ${kindWord(F.rig.def).toLowerCase()}`); F.dragging = 'object'; },
    onChange: () => { F.live = { object: { root: valOf(g.position, g.quaternion) } }; },
    onEnd: () => {
      const part = ensure(app).parts.object, f = Math.round(app.store.frame);
      if (!part.keys.length && f !== 0) setKey(part, 0, { root: ID.slice() });      // it starts where it stood
      setKey(part, f, { root: valOf(g.position, g.quaternion) });
      F.live = null; F.dragging = null;
      app.store.setDirty(true); refresh(app);
    },
  });
}

function attachHandle(app, F, name, hn) {
  const bed = F.rig.bed, rest = bed.handles[name][hn];
  if (!rest) return;
  const g = F.rig.g, proxy = F.proxy;
  const cur = (partValues(app, F, name, Math.round(app.store.frame), () => bodyPoints(app, g)) || {})[hn] || ID;
  proxy.position.copy(g.localToWorld(rest.clone().add(new THREE.Vector3(cur[0], cur[1], cur[2]))));
  proxy.quaternion.copy(g.getWorldQuaternion(new THREE.Quaternion())).multiply(new THREE.Quaternion(cur[3], cur[4], cur[5], cur[6]));
  const pillow = name === 'pillows';
  const read = () => {
    const local = g.worldToLocal(proxy.position.clone()).sub(rest);
    const q = g.getWorldQuaternion(new THREE.Quaternion()).invert().multiply(proxy.quaternion);
    return valOf(local, pillow ? q : new THREE.Quaternion());
  };
  F.detach = app.interact.attachGizmo(proxy, {
    modes: pillow ? ['translate', 'rotate'] : ['translate'], size: 0.55,
    onStart: () => {
      app.store.checkpoint(`Move the ${HANDLE_WORD[hn] || name}`);
      const part = ensure(app).parts[name];
      if (part.mode !== 'hand') bakeAuto(app, F, name);                         // from what it did by itself
      F.dragging = name;
    },
    onChange: () => { F.live = { [name]: { [hn]: read() } }; },
    onEnd: () => {
      const part = ensure(app).parts[name], f = Math.round(app.store.frame);
      const now = sample(part.keys, f) || {};
      setKey(part, f, { ...JSON.parse(JSON.stringify(now)), [hn]: read() });
      F.live = null; F.dragging = null;
      app.store.setDirty(true); refresh(app);
    },
  });
}

// the dots on the blanket and pillows (the part picked in the panel)
function syncDots(app, F, vals) {
  const on = F.on && F.rig && F.rig.bed && (F.sel === 'blanket' || F.sel === 'pillows');
  F.dots.visible = !!on && !app.preview && !app._recordingVideo;
  if (!on) return;
  const want = Object.keys(F.rig.bed.handles[F.sel]);
  if (F.dots.userData.key !== F.sel + want.join()) {
    F.dots.clear();
    for (const hn of want) {
      const m = new THREE.Mesh(new THREE.SphereGeometry(F.sel === 'pillows' ? 0.035 : 0.028, 16, 10),
        new THREE.MeshBasicMaterial({ color: F.sel === 'pillows' ? 0xfbbf24 : 0x60a5fa, depthTest: false, transparent: true, opacity: 0.95 }));
      m.renderOrder = 19; m.userData.handle = hn;
      F.dots.add(m);
    }
    F.dots.userData.key = F.sel + want.join();
  }
  const g = F.rig.g, H = F.rig.bed.handles[F.sel], cur = vals[F.sel] || {};
  for (const m of F.dots.children) {
    const x = cur[m.userData.handle] || ID;
    m.position.copy(g.localToWorld(H[m.userData.handle].clone().add(new THREE.Vector3(x[0], x[1], x[2]))));
    m.scale.setScalar(F.handle === m.userData.handle ? 1.35 : 1);
  }
}

// ---------------------------------------------------------------- every frame
function apply(app) {
  const F = app._furn, g = currentGroup(app);
  if (!g) { F.rig = null; return; }
  if (!F.rig || F.rig.g !== g) {
    if (F.rig) disposeRig(F.rig);
    F.rig = prepare(app, g);
    // a game bed's bones, kept for sending other animations on the same bed (a progression's steps)
    if (F.rig.bed && F.rig.bed.real && F.rig.def) F.rigs.set(F.rig.def.id, F.rig);
  }
  const f = Math.round(app.store.frame), d = fa(app);
  const pts = (() => { let c = null; return () => (c = c || bodyPoints(app, g)); })();
  if (F.dragging !== 'object') {
    const v = d ? partValues(app, F, 'object', f, pts) : null;
    setObject(g, v && v.root);
  }
  g.updateMatrixWorld(true);
  const vals = {};
  if (F.rig.bed && d) {
    for (const name of ['blanket', 'pillows']) vals[name] = partValues(app, F, name, f, pts) || {};
    deform(F.rig.bed, { ...vals.blanket, ...vals.pillows });
  } else if (F.rig.bed) deform(F.rig.bed, {});
  syncDots(app, F, vals);
}

// ---------------------------------------------------------------- the panel and the button
function drawCard(app) {
  const F = app._furn, def = defOf(app);
  if (!F.card) return;
  F.card.hidden = !F.on || !movable(def) || !!app.preview;
  if (F.card.hidden) return;
  const word = kindWord(def), bed = def.kind === 'bed', d = ensure(app), len = app.store.project.length, fps = app.store.project.fps || 30;
  const chip = (name, label) => h('button', { class: 'chipbtn' + (F.sel === name ? ' on' : ''), 'data-part': name, onclick: () => select(app, name) }, label);
  const seg = name => {
    const pt = d.parts[name];
    return h('div', { class: 'seg small fa-seg' },
      h('button', { class: pt.mode !== 'hand' ? 'active' : '', 'data-mode': 'auto', onclick: () => { if (pt.mode !== 'hand') return; pause(app); app.store.checkpoint('Automatic'); pt.mode = 'auto'; app.store.setDirty(true); refresh(app); } }, 'Automatic'),
      h('button', { class: pt.mode === 'hand' ? 'active' : '', 'data-mode': 'hand', onclick: () => { if (pt.mode === 'hand') return; pause(app); app.store.checkpoint('By hand'); if (!pt.keys.length) bakeAuto(app, F, name); pt.mode = 'hand'; app.store.setDirty(true); refresh(app); } }, 'By hand'));
  };
  const body = [];
  if (F.sel === 'object' || !bed) {
    body.push(h('div', { class: 'hint' }, 'Drag the arrows to slide it, R turns it. Or let it happen:'),
      h('div', { class: 'fa-row' }, h('span', { class: 'fa-l' }, 'Tip over'),
        ...[['back', 'Back'], ['front', 'Front'], ['left', 'Left'], ['right', 'Right']].map(([w, l]) => h('button', { class: 'btn small', 'data-tip': w, onclick: () => tipOver(app, F, w) }, l))),
      h('div', { class: 'fa-row' },
        h('button', { class: 'btn small', 'data-act': 'throw', onclick: () => liftAndThrow(app, F) }, icon('wand'), 'Lift and throw'),
        h('button', { class: 'btn small', 'data-act': 'drop', onclick: () => drop(app, F) }, 'Drop'),
        h('button', { class: 'btn small ghost', 'data-act': 'back', onclick: () => backInPlace(app, F) }, icon('undo'), 'Back in place')));
  } else if (F.sel === 'blanket') {
    const pt = d.parts.blanket;
    const under = h('input', { type: 'checkbox', checked: !!pt.under, 'data-under': '1', onchange: () => setUnder(app, under.checked) });
    body.push(seg('blanket'), h('label', { class: 'fa-check' }, under, 'Under the blanket'),
      h('div', { class: 'hint' }, pt.mode !== 'hand' ? (pt.under ? 'It covers the sims and follows their bodies.' : 'It lies pulled back to the foot of the bed.')
        : 'Drag a blue dot on the blanket. Keys go on the timeline.'),
      pt.mode === 'hand' ? h('button', { class: 'btn small', 'data-act': 'from-auto', onclick: () => { app.store.checkpoint('Start from automatic'); bakeAuto(app, F, 'blanket'); app.store.setDirty(true); refresh(app); } }, 'Start from automatic') : null);
  } else {
    const pt = d.parts.pillows;
    body.push(seg('pillows'), h('div', { class: 'hint' }, pt.mode !== 'hand' ? 'A pillow gives under a head resting on it.' : 'Drag a yellow dot; R turns the pillow.'),
      pt.mode === 'hand' ? h('button', { class: 'btn small', 'data-act': 'from-auto', onclick: () => { app.store.checkpoint('Start from automatic'); bakeAuto(app, F, 'pillows'); app.store.setDirty(true); refresh(app); } }, 'Start from automatic') : null);
  }
  F.card.replaceChildren(...[
    h('div', { class: 'fa-head' }, icon('bed'), h('b', {}, `${word} animation`), h('span', { class: 'grow' }),
      h('button', { class: 'icon-btn sm', title: 'Close', onclick: () => setOn(app, false) }, icon('x'))),
    bed ? h('div', { class: 'chips fa-parts' }, chip('object', word), chip('blanket', 'Blanket'), chip('pillows', 'Pillows')) : null,
    ...body,
    h('div', { class: 'fa-foot' }, `Keys stay inside the loop (${(len / fps).toFixed(1)} s). `,
      bed ? 'The blanket and pillows go to the game with the animation; moving the bed only shows here.' : 'It only moves here: in the game it stands still.'),
  ].filter(Boolean));
}

function setUnder(app, on) {
  pause(app);
  const p = app.store.project, pt = ensure(app).parts.blanket;
  app.store.checkpoint(on ? 'Under the blanket' : 'On the blanket');
  pt.under = !!on;
  // WickedWhims' own tag for it, so players can find it
  p.tags = Array.isArray(p.tags) ? p.tags : [];
  const i = p.tags.indexOf('UNDER_COVERS');
  if (on && i < 0) p.tags.push('UNDER_COVERS');
  if (!on && i >= 0) p.tags.splice(i, 1);
  app.store.setDirty(true);
  refresh(app);
}

function syncButton(app) {
  const F = app._furn, def = defOf(app), btn = F.btn;
  if (!btn) return;
  btn.hidden = !movable(def);
  btn.lastChild.textContent = `${kindWord(def)} animation`;
  btn.classList.toggle('on', !!F.on && movable(def));
  if (!movable(def) && F.on) setOn(app, false);
}

function setOn(app, on) {
  const F = app._furn, def = defOf(app);
  on = !!on && movable(def);
  F.on = on;
  for (const un of F.rows) un();
  F.rows = [];
  if (F.detach) { F.detach(); F.detach = null; }
  if (on) {
    ensure(app);
    if (!F.sel || (F.sel !== 'object' && def.kind !== 'bed')) F.sel = 'object';
    if (app.timeline && typeof app.timeline.addRow === 'function') F.rows = rowsFor(app, F).map(r => app.timeline.addRow(r));
    if (app.playing) app.setPlaying(false);
    apply(app);                                               // measure the piece now, so the gizmo can go on it
    select(app, F.sel);
  }
  syncButton(app);
  drawCard(app);
  app.applyPoses(false);
}

function refresh(app) {
  const F = app._furn;
  app.applyPoses(false);
  drawCard(app);
  if (app.timeline) app.timeline.draw();
  if (F.sel && F.detach && F.sel !== 'object' && F.handle) select(app, F.sel, F.handle);
}

// ---------------------------------------------------------------- plug in
export function install(app) {
  if (!app || app.__furnAnim) return;
  app.__furnAnim = true;
  const hooks = app.hooks || {};
  const add = (name, fn) => { const list = name.split('.').reduce((o, k) => o && o[k], hooks); if (Array.isArray(list)) list.push(fn); };
  const F = app._furn = { on: false, sel: 'object', handle: null, rows: [], rig: null, rigs: new Map(), live: null, dragging: null, detach: null };
  F.proxy = new THREE.Object3D(); app.vp.scene.add(F.proxy);
  F.dots = new THREE.Group(); F.dots.name = 'furniture-dots'; app.vp.overlay.add(F.dots);
  // the button in the timeline bar, and the panel over the stage
  const seg = document.getElementById('tl-view-seg');
  if (seg) { F.btn = h('button', { class: 'btn small ghost fa-btn', id: 'btn-furn-anim', hidden: true, title: 'Animate the furniture: slide it, tip it over, the blanket and pillows', onclick: () => setOn(app, !F.on) }, icon('bed'), 'Bed animation'); seg.after(F.btn); }
  const wrap = document.getElementById('viewport-wrap');
  if (wrap) { F.card = h('div', { class: 'fa-card', hidden: true }); wrap.append(F.card); }
  // a click on a dot picks that handle; on the piece itself (not on a sim) picks the piece
  if (app.interact) app.interact.pickers.push((e, kind) => {
    if (!F.on || kind === 'down' || !F.rig) return false;
    const dot = F.dots.visible ? app.vp.pick(e, F.dots.children) : null;
    if (kind === 'hover') { if (dot) { app.vp.canvas.style.cursor = 'pointer'; app.hud(`${HANDLE_WORD[dot.object.userData.handle] || 'handle'} · drag it`); return true; } return false; }
    if (dot) { select(app, F.sel, dot.object.userData.handle); return true; }
    if (app.vp.pick(e, app.interact._meshes())) return false;               // a sim: posing as usual
    const meshes = []; F.rig.g.traverse(o => { if (o.isMesh) meshes.push(o); });
    if (app.vp.pick(e, meshes)) { select(app, 'object'); return true; }
    return false;
  });
  add('afterApply', () => { try { apply(app); } catch (err) { console.error('furniture animation:', err); } });
  // the old piece left the stage: its bending copies go (a kept game bed keeps only its bone data, for sending)
  add('furnitureBuilt', () => { disposeRig(F.rig); F.rig = null; syncButton(app); if (F.on) setOn(app, true); else app.applyPoses(false); });
  add('projectLoaded', () => { F.live = null; F.dragging = null; F.rig = null; if (F.on) setOn(app, false); syncButton(app); });
  if (typeof app.on === 'function') app.on('undo', () => { F.live = null; drawCard(app); });
  // a longer or shorter loop takes the keys along (stretched, or cut at the new end)
  add('retime', (p, { newLen, mode, scale }) => {
    for (const pt of Object.values((p.furnAnim && p.furnAnim.parts) || {})) {
      if (!pt || !Array.isArray(pt.keys)) continue;
      if (mode === 'stretch') { const by = new Map(); for (const k of pt.keys) by.set(scale(k.f), { ...k, f: scale(k.f) }); pt.keys = sortKeys([...by.values()]); }
      else {
        // cut: what it looked like at the new last frame stays there (as the sims' keys do)
        const last = newLen - 1, gone = pt.keys.some(k => k.f >= newLen);
        const at = gone && !pt.keys.some(k => k.f === last) ? sample(pt.keys, last) : null;
        pt.keys = pt.keys.filter(k => k.f < newLen);
        if (at) setKey(pt, last, JSON.parse(JSON.stringify(at)));
      }
    }
  });
  // Send to game: the blanket and pillows as the bed's own clip (the game bed's bones), worked out frame by frame the
  // way the game will play the sims - with the bed where WickedWhims puts it (its own movement only shows here)
  add('bake', (payload, p, opts = {}) => {
    const other = !!(opts.pipeline && opts.pipeline !== app.pipeline);
    const d = p.furnAnim;
    // the bed's bones: the open scene's, or (another animation, e.g. a progression's step) the same bed's from before
    const rig = !other && F.rig && F.rig.def && F.rig.def.id === p.furniture ? F.rig : F.rigs.get(p.furniture), bed = rig && rig.bed;
    if (!d || !bed || !bed.real) return;
    const loc = bed.double ? 'DOUBLE_BED' : 'SINGLE_BED';
    if (!(p.locations || []).includes(loc) && !(payload.locations || []).includes(loc)) return;
    const pipe = other ? opts.pipeline : app.pipeline, views = other ? opts.views : app.simViews;
    const rest = new Map();
    for (const M of bed.meshes) M.skin.bones.forEach((n, i) => { if (M.skin.rest && !rest.has(n)) rest.set(n, M.skin.rest[i]); });
    const names = Object.keys(boneDeltas(bed, {}, n => rest.get(n)));
    const frames = [], n = payload.frames || p.length, R = { rig, live: null };
    try {
      for (let k = 0; k < n; k++) {
        pipe.apply(k, { physics: true, overrides: false });
        // the bed stands where WickedWhims puts it: the sims' own places are its space
        const pts = (() => { let c = null; return () => (c = c || bodyPoints(app, null, views, other)); })();
        const vals = { ...(partValues(app, R, 'blanket', k, pts, p) || {}), ...(partValues(app, R, 'pillows', k, pts, p) || {}) };
        const bd = boneDeltas(bed, vals, x => rest.get(x));
        frames.push(names.flatMap(bn => (bd[bn] || ID).map(r5)));
      }
    } finally {
      if (!other) app.applyPoses(false);
    }
    payload.bedAnim = { location: loc, bones: names, frames };
  });
  window.wickedFurnAnim = { setOn: on => setOn(app, on), select: (name, handle) => select(app, name, handle), tipOver: w => tipOver(app, F, w),
    liftAndThrow: () => liftAndThrow(app, F), drop: () => drop(app, F), backInPlace: () => backInPlace(app, F), setUnder: on => setUnder(app, on),
    keyHere: (name, f) => keyHere(app, F, name, f), state: F };
}

export default install;

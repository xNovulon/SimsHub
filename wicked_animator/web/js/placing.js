// Putting sims on furniture: the real top surface (mattress, seat, table top), where it is, which way a bed runs,
// and moving every sim of the animation together (every key, a pose not keyed yet and the pins) so the whole
// animation lands on it - not only the frame on screen.
// Shared by Magic, and later by the Place tool ("Sit here", "Lie here") and "Move to another place".
// Works with or without the server's surface grid and seat spots (objmesh v2): without them the grid is worked out
// here from the furniture's own meshes, and the object's bounds stand in for the spots.
import * as THREE from 'three';
import { spacePos, spaceQuat, solveTwoBone } from './posemath.js';
import { POSABLE, HIPS, LIMBS } from './bones.js';
import { pelvisAxes } from './motion.js';
import { $t } from './i18n.js';

const UP = new THREE.Vector3(0, 1, 0);
const LYING = 1.1;        // bodies longer than this (m, along their main line) lie or kneel along the furniture

// ---------------------------------------------------------------- the furniture
// Furniture info with the real surface, loaded once per place (null for the floor or when the game object is missing).
export async function furnitureInfo(app, placeId) {
  if (!placeId || placeId === 'floor') return null;
  app._furnInfo = app._furnInfo || new Map();
  if (!app._furnInfo.has(placeId)) {
    app._furnInfo.set(placeId, fetch('/api/furniture_mesh?v=2&id=' + encodeURIComponent(placeId))
      .then(r => (r.ok ? r.json() : null)).catch(() => null));
  }
  return app._furnInfo.get(placeId);
}

export function surfaceY(info, fallback = 0) {
  const y = info && info.surface_height;
  return typeof y === 'number' && isFinite(y) ? y : fallback;
}

// Height of the furniture's top at (x, z), metres, or null where there is nothing (or outside the grid).
export function gridHeight(grid, x, z) {
  if (!grid) return null;
  const i = Math.floor((x - grid.x0) / grid.cell), j = Math.floor((z - grid.z0) / grid.cell);
  if (i < 0 || j < 0 || i >= grid.w || j >= grid.d) return null;
  const h = grid.h[j * grid.w + i];
  return h === -32768 || h === null || h === undefined ? null : h / 1000;
}

// The server's surface grid, or the same thing worked out here from the meshes (top-most up-facing height per 5 cm
// cell, in mm; -32768 = nothing). Cached on the info object.
export function gridOf(info) {
  if (!info) return null;
  if (info.surface_grid && info.surface_grid.h) return info.surface_grid;
  if (info._grid !== undefined) return info._grid;
  let g = null;
  try { g = gridFromMeshes(info.meshes || []); } catch (e) { console.warn('surface grid', e); }
  Object.defineProperty(info, '_grid', { value: g, enumerable: false, configurable: true });
  return g;
}

function gridFromMeshes(meshes, cell = 0.05, lo = -1.0, hi = 2.0) {
  const fine = cell / 2;                                   // rasterise at 2.5 cm, keep the highest of each 2 x 2
  let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity;
  const use = meshes.filter(m => !m.transparent && !m.water && m.positions && m.faces && m.faces.length);
  for (const m of use) {
    const P = m.positions;
    for (let k = 0; k < P.length; k += 3) {
      if (P[k] < x0) x0 = P[k]; if (P[k] > x1) x1 = P[k];
      if (P[k + 2] < z0) z0 = P[k + 2]; if (P[k + 2] > z1) z1 = P[k + 2];
    }
  }
  if (!isFinite(x0)) return null;
  x0 = Math.floor(x0 / cell) * cell; z0 = Math.floor(z0 / cell) * cell;
  const W = Math.ceil((x1 - x0) / fine) + 1, D = Math.ceil((z1 - z0) / fine) + 1;
  const top = new Float32Array(W * D).fill(-Infinity), up = new Uint8Array(W * D);
  for (const m of use) {
    const P = m.positions, F = m.faces;
    for (let t = 0; t + 2 < F.length; t += 3) {
      const a = F[t] * 3, b = F[t + 1] * 3, c = F[t + 2] * 3;
      const ax = P[a], ay = P[a + 1], az = P[a + 2], bx = P[b], by = P[b + 1], bz = P[b + 2], cx = P[c], cy = P[c + 1], cz = P[c + 2];
      // normal's up share
      const ux = bx - ax, uy = by - ay, uz = bz - az, vx = cx - ax, vy = cy - ay, vz = cz - az;
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      const nl = Math.hypot(nx, ny, nz) || 1e-12;
      const upward = Math.abs(ny) / nl > 0.7;           // either winding: a top seen from above
      const fax = (ax - x0) / fine, faz = (az - z0) / fine, fbx = (bx - x0) / fine, fbz = (bz - z0) / fine, fcx = (cx - x0) / fine, fcz = (cz - z0) / fine;
      const i0 = Math.max(0, Math.floor(Math.min(fax, fbx, fcx))), i1 = Math.min(W - 1, Math.ceil(Math.max(fax, fbx, fcx)));
      const j0 = Math.max(0, Math.floor(Math.min(faz, fbz, fcz))), j1 = Math.min(D - 1, Math.ceil(Math.max(faz, fbz, fcz)));
      const den = (fbz - fcz) * (fax - fcx) + (fcx - fbx) * (faz - fcz);
      if (Math.abs(den) < 1e-9) continue;
      for (let j = j0; j <= j1; j++) {
        const zz = j + 0.5;
        for (let i = i0; i <= i1; i++) {
          const xx = i + 0.5;
          const w0 = ((fbz - fcz) * (xx - fcx) + (fcx - fbx) * (zz - fcz)) / den;
          const w1 = ((fcz - faz) * (xx - fcx) + (fax - fcx) * (zz - fcz)) / den;
          const w2 = 1 - w0 - w1;
          if (w0 < -1e-6 || w1 < -1e-6 || w2 < -1e-6) continue;
          const y = w0 * ay + w1 * by + w2 * cy, k = j * W + i;
          if (y > top[k]) { top[k] = y; up[k] = upward ? 1 : 0; }
        }
      }
    }
  }
  const w = Math.ceil(W / 2), d = Math.ceil(D / 2), h = new Array(w * d).fill(-32768);
  for (let j = 0; j < D; j++) for (let i = 0; i < W; i++) {
    const k = j * W + i, y = top[k];
    if (!up[k] || !(y > lo && y < hi)) continue;
    const o = (j >> 1) * w + (i >> 1), mm = Math.round(y * 1000);
    if (mm > h[o]) h[o] = mm;
  }
  return { x0, z0, cell, w, d, h };
}

// Cells of the grid near the surface height (the mattress, the seat cushions): [{x, z}] cell centres.
function surfaceCells(info, tol = 0.03) {
  const g = gridOf(info), top = surfaceY(info, NaN);
  if (!g || !isFinite(top)) return [];
  const out = [];
  for (let j = 0; j < g.d; j++) for (let i = 0; i < g.w; i++) {
    const h = g.h[j * g.w + i];
    if (h !== -32768 && Math.abs(h / 1000 - top) <= tol) out.push({ x: g.x0 + (i + 0.5) * g.cell, z: g.z0 + (j + 0.5) * g.cell });
  }
  return out;
}

// Where bodies are centred on the furniture: the middle of the lying spots, else of the bed's edge seats, else of the
// surface itself, else the middle of the object.
export function surfaceCentre(info) {
  if (!info) return null;
  const slots = info.slots || [];
  const mean = list => list.reduce((a, s) => a.add(new THREE.Vector3(s.pos[0], 0, s.pos[2])), new THREE.Vector3()).multiplyScalar(1 / list.length);
  const lie = slots.filter(s => s.kind === 'lie' && s.pos);
  if (lie.length) return mean(lie);
  const edge = slots.filter(s => s.kind === 'edge' && s.pos);
  if (edge.length) return mean(edge);
  const cells = surfaceCells(info);
  if (cells.length >= 20) return new THREE.Vector3(cells.reduce((a, c) => a + c.x, 0) / cells.length, 0, cells.reduce((a, c) => a + c.z, 0) / cells.length);
  const b = info.bounds;
  return b ? new THREE.Vector3((b.min[0] + b.max[0]) / 2, 0, (b.min[2] + b.max[2]) / 2) : null;
}

// Which way the surface runs (unit vector, y = 0, pointing from the head end to the foot end) and how long it is.
// Beds: the lying spots' direction (head end = where the headboard is). Otherwise the main line of the surface cells;
// its head end is the end next to the higher parts (headboard, armrest); on a tie -Z, then -X.
export function surfaceAxis(info) {
  if (!info) return null;
  const lie = (info.slots || []).filter(s => s.kind === 'lie' && s.dir);
  const cells = surfaceCells(info);
  let len = 0;
  if (lie.length) {
    const dir = new THREE.Vector3(lie[0].dir[0], 0, lie[0].dir[2]).normalize();
    if (cells.length) { const p = cells.map(c => c.x * dir.x + c.z * dir.z); len = Math.max(...p) - Math.min(...p); }
    return { dir, length: len || 1.9 };
  }
  let dir, cx, cz;
  if (cells.length >= 20) {
    cx = cells.reduce((a, c) => a + c.x, 0) / cells.length; cz = cells.reduce((a, c) => a + c.z, 0) / cells.length;
    let sxx = 0, szz = 0, sxz = 0;
    for (const c of cells) { sxx += (c.x - cx) ** 2; szz += (c.z - cz) ** 2; sxz += (c.x - cx) * (c.z - cz); }
    const a = 0.5 * Math.atan2(2 * sxz, sxx - szz);
    dir = new THREE.Vector3(Math.cos(a), 0, Math.sin(a));
    const p = cells.map(c => c.x * dir.x + c.z * dir.z);
    len = Math.max(...p) - Math.min(...p);
  } else if (info.bounds) {
    const b = info.bounds, wx = b.max[0] - b.min[0], wz = b.max[2] - b.min[2];
    dir = wz >= wx ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(1, 0, 0);
    len = Math.max(wx, wz); cx = (b.min[0] + b.max[0]) / 2; cz = (b.min[2] + b.max[2]) / 2;
  } else return null;
  // snap a nearly axis-aligned line onto the axis (furniture is built square to the room)
  if (Math.abs(dir.x) > 0.985) dir.set(Math.sign(dir.x), 0, 0);
  if (Math.abs(dir.z) > 0.985) dir.set(0, 0, Math.sign(dir.z));
  // head end: the end with more high parts just beyond the surface (a headboard, an armrest)
  const g = gridOf(info), top = surfaceY(info, 0);
  let s = 0;
  if (g) {
    for (let j = 0; j < g.d; j++) for (let i = 0; i < g.w; i++) {
      const h = g.h[j * g.w + i];
      if (h === -32768 || h / 1000 < top + 0.12) continue;
      const x = g.x0 + (i + 0.5) * g.cell, z = g.z0 + (j + 0.5) * g.cell;
      const along = (x - cx) * dir.x + (z - cz) * dir.z, across = Math.abs(-(x - cx) * dir.z + (z - cz) * dir.x);
      if (Math.abs(along) > len * 0.35 && across < 0.6) s += Math.sign(along);
    }
  }
  // dir points from the head end to the foot end
  if (s > 2) dir.negate();
  else if (Math.abs(s) <= 2) {
    // a tie: the head end is -Z, then -X
    if (dir.z < -0.5 || (Math.abs(dir.z) <= 0.5 && dir.x < 0)) dir.negate();
  }
  return { dir, length: len };
}

// ---------------------------------------------------------------- the bodies
// Every posable bone of the listed sims at `frame` (keys + fixed pins, as hand-posing sees them), in sim space.
export function bodyPoints(app, sims, frame) {
  const all = [], heads = [], pelvises = [], bySim = new Map();
  for (const sim of sims) {
    const v = app.simViews.get(sim.id);
    if (!v) continue;
    app.pipeline.base({ sim, v }, frame);
    const mine = [];
    for (const n of POSABLE) { const b = v.bone(n); if (b) mine.push(spacePos(v, b)); }
    all.push(...mine);
    bySim.set(sim.id, mine);
    const hd = v.bone('b__Head__'), pv = v.bone('b__Pelvis__');
    if (hd) heads.push(spacePos(v, hd));
    if (pv) pelvises.push(spacePos(v, pv));
  }
  return { all, heads, pelvises, bySim };
}

// Lowest skin point (y, sim space) of the sims at `frame`: the bodies' own skin, worked out from the skinned meshes
// (every 3rd vertex); where that is not possible, the lowest bone minus 6 cm.
export function lowestSkin(app, sims, frame) {
  let low = Infinity, bone = Infinity;
  const p = new THREE.Vector3();
  for (const sim of sims) {
    const v = app.simViews.get(sim.id);
    if (!v) continue;
    app.pipeline.base({ sim, v }, frame);
    v.space.updateMatrixWorld(true);
    for (const n of POSABLE) { const b = v.bone(n); if (b) bone = Math.min(bone, spacePos(v, b).y); }
    for (const mesh of v.meshes || []) {
      if (!mesh.visible || !mesh.isSkinnedMesh || typeof mesh.getVertexPosition !== 'function') continue;
      const n = mesh.geometry.attributes.position.count;
      for (let i = 0; i < n; i += 3) {
        mesh.getVertexPosition(i, p);
        if (p.y < low) low = p.y;          // the mesh is bound in the sim's space (identity bind): this is sim space
      }
    }
  }
  if (isFinite(low)) return low;
  // no skinned meshes to measure (a stand-in view): the body's capsules (clipcheck), else the lowest bone - 6 cm
  const caps = capsuleLow(app, sims);
  if (isFinite(caps)) return caps;
  return isFinite(bone) ? bone - 0.06 : 0;
}

// The lowest point of the body capsules (clipcheck.capsulesOf, radii from the sim's own skin) at the current pose.
let _clip = null;
import('./clipcheck.js').then(m => { _clip = m; }).catch(() => { _clip = null; });
function capsuleLow(app, sims) {
  if (!_clip || !_clip.capsulesOf) return Infinity;
  let low = Infinity;
  for (const sim of sims) {
    const v = app.simViews.get(sim.id);
    if (!v) continue;
    for (const c of _clip.capsulesOf(v)) {
      const now = _clip.capsuleNow(v, c);
      if (now) low = Math.min(low, now.a.y - now.r, now.b.y - now.r);
    }
  }
  return low;
}

// The bodies' main line in x/z (principal axis of the bone points) and which end the heads are at: the side the heads
// are on as seen from the hips (arms stretched above the head would put the heads in the middle of the points).
export function longAxis(points, heads = [], pelvises = []) {
  const n = points.length;
  if (!n) return { dir: new THREE.Vector3(0, 0, 1), headSign: 1, centre: new THREE.Vector3(), length: 0 };
  const cx = points.reduce((a, q) => a + q.x, 0) / n, cz = points.reduce((a, q) => a + q.z, 0) / n;
  let sxx = 0, szz = 0, sxz = 0;
  for (const q of points) { sxx += (q.x - cx) ** 2; szz += (q.z - cz) ** 2; sxz += (q.x - cx) * (q.z - cz); }
  const a = 0.5 * Math.atan2(2 * sxz, sxx - szz);
  const dir = new THREE.Vector3(Math.cos(a), 0, Math.sin(a));
  const proj = points.map(q => (q.x - cx) * dir.x + (q.z - cz) * dir.z);
  const lo = Math.min(...proj), hi = Math.max(...proj);
  let headSign = 1;
  if (heads.length) {
    const hp = heads.reduce((s, q) => s + (q.x - cx) * dir.x + (q.z - cz) * dir.z, 0) / heads.length;
    const pp = pelvises.length ? pelvises.reduce((s, q) => s + (q.x - cx) * dir.x + (q.z - cz) * dir.z, 0) / pelvises.length : null;
    headSign = pp !== null && Math.abs(hp - pp) > 0.05 ? (hp > pp ? 1 : -1) : (hp >= (lo + hi) / 2 ? 1 : -1);
  }
  const mid = (lo + hi) / 2;
  return { dir, headSign, length: hi - lo, centre: new THREE.Vector3(cx + dir.x * mid, 0, cz + dir.z * mid) };
}

function boxXZ(points) {
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (const q of points) { x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x); z0 = Math.min(z0, q.z); z1 = Math.max(z1, q.z); }
  return { x0, x1, z0, z1, cx: (x0 + x1) / 2, cz: (z0 + z1) / 2 };
}

// Move and turn sims together through the whole animation (every key, a pending pose and the pins).
// turn: radians about the vertical, around `pivot`; offset: a move. Sim space.
export function moveTogether(app, sims, { turn = 0, pivot = null, offset = null } = {}) {
  for (const s of sims) app.transformSim(s.id, { angle: turn, pivot: pivot || new THREE.Vector3(), offset });
}

// ---------------------------------------------------------------- putting them there
// Rest the bodies on a height: their lowest skin point `gap` above `top` (every key moves).
export function restOn(app, sims, top, { frame = 0, gap = 0.005 } = {}) {
  const dy = top + gap - lowestSkin(app, sims, frame);
  if (Math.abs(dy) > 1e-4) moveTogether(app, sims, { offset: new THREE.Vector3(0, dy, 0) });
  return dy;
}

// Put the sims on a surface: lying and kneeling couples along the bed with the heads at the head end, centred on
// it, resting on it, and nudged in where a part would hang over the edge.
export async function fitOnSurface(app, sims, info, { frame = 0, along = null } = {}) {
  const top = surfaceY(info, 0);
  let pts = bodyPoints(app, sims, frame);
  if (!pts.all.length) return;
  // 1. long bodies lie along the surface, heads toward the head end
  const axis = along ? { dir: along.clone().setY(0).normalize() } : surfaceAxis(info);
  const ax = longAxis(pts.all, pts.heads, pts.pelvises);
  // 0. someone sits on the floor with the others on the lap (a lap ride), and the furniture has seats: that sim sits
  //    on the middle seat exactly (feet on its foot spots), and the others come along
  const seats = ((info && info.slots) || []).filter(x => x.kind === 'seat' && x.pos && x.dir);
  if (!along && seats.length && !(ax.length > LYING)) {
    const sitter = seatedSim(app, sims, frame);
    if (sitter) {
      const mx = seats.reduce((a, x) => a + x.pos[0], 0) / seats.length;
      const seat = seats.reduce((a, x) => (Math.abs(x.pos[0] - mx) < Math.abs(a.pos[0] - mx) ? x : a));
      sitOn(app, sitter, seat, { frame, others: sims.filter(x => x !== sitter) });
      return;
    }
  }
  if (axis && axis.dir && ax.length > LYING) {
    const want = axis.dir;                                                    // head end -> foot end
    const head = ax.dir.clone().multiplyScalar(ax.headSign);                  // centre -> heads
    const turn = wrap(Math.atan2(-want.x, -want.z) - Math.atan2(head.x, head.z));
    if (Math.abs(turn) > 0.01) {
      moveTogether(app, sims, { turn, pivot: ax.centre.clone().setY(0) });
      pts = bodyPoints(app, sims, frame);
    }
  }
  // 2. centre the bodies on the surface
  const c = surfaceCentre(info);
  if (c) {
    const box = boxXZ(pts.all);
    moveTogether(app, sims, { offset: new THREE.Vector3(c.x - box.cx, 0, c.z - box.cz) });
  }
  // 3. rest on it: the lowest skin point just on the surface
  restOn(app, sims, top, { frame });
  // 4. still over an edge? nudge in (at most 0.4 m)
  nudgeInside(app, sims, gridOf(info), frame, top);
}

// Nudge the bodies onto the furniture: the shift (x, z) of at most 0.5 m that keeps the most bone points near the
// surface (y < top + 0.5) over the furniture and puts no part inside a higher part of it (a hand in the pillows, a
// foot in an armrest: a bone more than 3 cm under the furniture's top there). Each centimetre a bone is inside costs
// as much as a third of a bone hanging over the edge; the smallest such shift wins. No shift when nothing is wrong.
export function nudgeInside(app, sims, grid, frame = 0, top = null) {
  if (!grid) return new THREE.Vector3();
  const pts = bodyPoints(app, sims, frame).all;
  if (!pts.length) return new THREE.Vector3();
  // the toes' tips too (the skin reaches about 5 cm past the toe joint): a foot at the end of a bed stays out of the
  // footboard
  for (const sim of sims) {
    const v = app.simViews.get(sim.id);
    if (!v) continue;
    for (const sd of ['L', 'R']) {
      const f = v.bone(`b__${sd}_Foot__`), t = v.bone(`b__${sd}_Toe__`);
      if (!f || !t) continue;
      const tp = spacePos(v, t), dir = tp.clone().sub(spacePos(v, f));
      if (dir.lengthSq() > 1e-8) pts.push(tp.addScaledVector(dir.normalize(), 0.05));
    }
  }
  const t = top ?? Math.min(...pts.map(q => q.y));
  const near = pts.filter(q => q.y < t + 0.5);
  const cost = (dx, dz) => {
    let off = 0, pen = 0;
    for (const q of pts) {
      const h = gridHeight(grid, q.x + dx, q.z + dz);
      if (q.y < t + 0.5 && !(h !== null && h > t - 0.2)) off++;
      if (h !== null && q.y < h - 0.03) pen += (h - 0.03 - q.y) * 100;
    }
    return { c: pen + 3 * off + 5 * Math.hypot(dx, dz), off, pen };
  };
  const here = cost(0, 0);
  if (here.off === 0 && here.pen < 0.5) return new THREE.Vector3();
  let best = { ...here, dx: 0, dz: 0 };
  for (let i = -10; i <= 10; i++) for (let j = -10; j <= 10; j++) {
    const dx = i * 0.05, dz = j * 0.05;
    if (Math.hypot(dx, dz) > 0.5 + 1e-9) continue;
    const k = cost(dx, dz);
    if (k.c < best.c - 1e-9) best = { ...k, dx, dz };
  }
  void near;
  const off = new THREE.Vector3(best.dx, 0, best.dz);
  if (best.dx || best.dz) moveTogether(app, sims, { offset: off });
  return off;
}

// Stand the sims on the floor in front of a piece of furniture (upright poses at a sofa, a chair, a counter):
// the group's middle `gap` m in front of the middle seat (or of the object's front).
export function inFrontOf(app, sims, info, { frame = 0, gap = 0.55 } = {}) {
  const pts = bodyPoints(app, sims, frame).all;
  if (!pts.length || !info) return;
  const seats = (info.slots || []).filter(s => (s.kind === 'seat' || s.kind === 'edge') && s.pos && s.dir);
  let at;
  if (seats.length) {
    const mid = seats.reduce((a, s) => a + s.pos[0], 0) / seats.length;
    const s = seats.reduce((a, b) => (Math.abs(b.pos[0] - mid) < Math.abs(a.pos[0] - mid) ? b : a));
    at = new THREE.Vector3(s.pos[0] + s.dir[0] * gap, 0, s.pos[2] + s.dir[2] * gap);
  } else if (info.bounds) {
    const b = info.bounds;
    at = new THREE.Vector3((b.min[0] + b.max[0]) / 2, 0, b.max[2] + gap * 0.35);
  } else return;
  const box = boxXZ(pts);
  // keep clear of the furniture: the bodies' back edge (the bone points; the skin is a few cm further, and a motion
  // moves the body some more) stays 15 cm in front of it
  const front = info.bounds ? info.bounds.max[2] + 0.15 : -Infinity;
  const dz = Math.max(at.z - box.cz, front - box.z0);
  moveTogether(app, sims, { offset: new THREE.Vector3(at.x - box.cx, 0, dz) });
  restOn(app, sims, 0, { frame });
}

// ---------------------------------------------------------------- the furniture's spots (Place tool)
// Seats, bed edges, sitting up in bed and lying spots from the object's rig (objmesh v2 slots), each with a plain name
// ("Seat 2", "Edge (left, head end)", "Lie (middle)") and what a click does ('sit' / 'lie'). Spots at the same place
// (a single bed lists its in-bed seat twice) are shown once.
export function spotsOf(info) {
  const slots = ((info && info.slots) || []).filter(s => s && Array.isArray(s.pos));
  const seen = new Set(), out = [];
  for (const s of slots) {
    const k = s.kind + ':' + s.pos.map(x => Math.round(x * 100)).join(',');
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(s);
  }
  const side = x => (Math.abs(x) < 0.05 ? 'middle' : x < 0 ? 'left' : 'right');
  const sideWord = x => $t('placing.side_' + side(x));
  const seats = out.filter(s => s.kind === 'seat').sort((a, b) => a.pos[0] - b.pos[0]);
  const lies = out.filter(s => s.kind === 'lie');
  const label = s => {
    if (s.kind === 'seat') return seats.length > 1 ? $t('placing.seat_n', { n: seats.indexOf(s) + 1 }) : $t('placing.seat');
    if (s.kind === 'edge') return $t('placing.edge_at', { side: sideWord(s.pos[0]), end: s.pos[2] < 0 ? $t('placing.head_end') : $t('placing.foot_end') });
    if (s.kind === 'in') return $t('placing.spot_side', { spot: s.dir && s.dir[2] > 0 ? $t('placing.sit_up_in_bed') : $t('placing.foot_of_bed'), side: sideWord(s.pos[0]) });
    if (s.kind === 'lie') return lies.length > 1 ? $t('placing.lie_at', { side: side(s.pos[0]) === 'middle' ? $t('placing.side_middle') : $t('placing.side_' + side(s.pos[0]) + '_side') }) : $t('placing.lie_on_it');
    return $t('placing.spot');
  };
  const order = { seat: 0, edge: 1, in: 2, lie: 3 };
  return out.map(s => ({ slot: s, kind: s.kind, action: s.kind === 'lie' ? 'lie' : 'sit', label: label(s),
    verb: 'placing.verb_' + (s.kind === 'lie' ? 'lie' : s.kind === 'edge' ? 'edge' : s.kind === 'in' ? 'in' : 'sit') }))
    .sort((a, b) => order[a.kind] - order[b.kind] || a.slot.pos[0] - b.slot.pos[0] || a.slot.pos[2] - b.slot.pos[2]);
}

// Turn a sim by any rotation R (sim space) around `pivot`, through the whole animation: every key's hips, a pending
// pose and the fixed pins (app.transformSim only turns about the vertical).
export function turnSimBy(app, simId, R, pivot) {
  const s = app.store.sim(simId), v = app.simViews.get(simId);
  if (!s || !v) return;
  const rb = v.bone('b__ROOT_bind__');
  const rbQ = spaceQuat(v, rb), rbP = spacePos(v, rb), rbQi = rbQ.clone().invert();
  const turnLocal = rbQi.clone().multiply(R).multiply(rbQ);
  const fix = pose => {
    if (!pose) return;
    pose.rot = pose.rot || {}; pose.pos = pose.pos || {};
    for (const n of HIPS) {
      const k = v.index(n);
      if (k < 0) continue;
      const q = pose.rot[n] ? new THREE.Quaternion().fromArray(pose.rot[n]) : v.rest[k].quat.clone();
      const at = pose.pos[n] ? new THREE.Vector3().fromArray(pose.pos[n]) : v.rest[k].pos.clone();
      const sp = at.applyQuaternion(rbQ).add(rbP).sub(pivot).applyQuaternion(R).add(pivot);
      pose.pos[n] = sp.sub(rbP).applyQuaternion(rbQi).toArray();
      pose.rot[n] = turnLocal.clone().multiply(q).normalize().toArray();
    }
  };
  for (const key of s.keys) fix(key.pose);
  const ov = app.pipeline.overrides.get(simId);
  if (ov) fix(ov.pose);
  for (const [limb, pin] of Object.entries(s.pins || {})) {
    const turn = a => new THREE.Vector3().fromArray(a).sub(pivot).applyQuaternion(R).add(pivot).toArray();
    if (Array.isArray(pin)) s.pins[limb] = turn(pin);
    else if (pin && Array.isArray(pin.at)) pin.at = turn(pin.at);            // pinned for part of the loop
  }
}

// The one sitting on the floor (pelvis within 30 cm of its lowest skin, torso up): the lowest such pelvis, or null.
// Nobody may be standing (a standing partner would be lifted into the air with the sitter).
function seatedSim(app, sims, frame) {
  let best = null, bestY = Infinity;
  for (const sim of sims) {
    const v = app.simViews.get(sim.id);
    if (!v || !v.bone('b__Pelvis__') || !v.bone('b__Head__')) continue;
    const low = lowestSkin(app, [sim], frame);
    app.pipeline.base({ sim, v }, frame);
    const pel = spacePos(v, v.bone('b__Pelvis__')), head = spacePos(v, v.bone('b__Head__'));
    if (head.y - low > 1.25) return null;
    if (pel.y - low < 0.3 && head.y - pel.y > 0.35 && pel.y < bestY) { best = sim; bestY = pel.y; }
  }
  return best;
}

// "Sit here": the pelvis 0.11 m above the seat spot and 0.03 m in front of it (creators' seated pelvis, spec_bodies
// Appendix A), facing the seat's way; the feet pinned on the object's foot spots (fixed pins, so the knees bend by
// themselves). A bed's in-bed spots have their foot spots under the mattress: no feet are pinned there.
export function sitOn(app, sim, slot, { frame = null, others = [] } = {}) {
  const v = app.simViews.get(sim.id);
  if (!v || !slot || !slot.pos) return false;
  const f = Math.round(frame ?? app.store.frame);
  // the feet may be pinned somewhere else: they follow the new spot (or are let go) - pins first, so the turn below
  // does not carry old pins along
  for (const limb of ['L foot', 'R foot']) if (sim.pins && Array.isArray(sim.pins[limb])) delete sim.pins[limb];
  app.pipeline.base({ sim, v }, f);
  // which way the sim faces: where its knees are (a seated sim's thighs point forward), else its hips' forward
  const pel0 = spacePos(v, v.bone('b__Pelvis__'));
  const knees = v.bone('b__L_Calf__') && v.bone('b__R_Calf__') ? spacePos(v, v.bone('b__L_Calf__')).add(spacePos(v, v.bone('b__R_Calf__'))).multiplyScalar(0.5) : null;
  let fwd = knees ? knees.sub(pel0).setY(0) : new THREE.Vector3();
  if (fwd.length() < 0.15) fwd = pelvisAxes(v).forward.setY(0);
  if (fwd.lengthSq() < 1e-6) fwd.set(0, 0, 1);
  fwd.normalize();
  const want = new THREE.Vector3(slot.dir ? slot.dir[0] : 0, 0, slot.dir ? slot.dir[2] : 1);
  if (want.lengthSq() < 1e-6) want.set(0, 0, 1);
  want.normalize();
  const turn = wrap(Math.atan2(want.x, want.z) - Math.atan2(fwd.x, fwd.z));
  const pel = spacePos(v, v.bone('b__Pelvis__'));
  // `others` (someone on the lap) move exactly as the sitter does, so the couple keeps its contact
  if (Math.abs(turn) > 1e-4) moveTogether(app, [sim, ...others], { turn, pivot: pel.clone().setY(0) });
  app.pipeline.base({ sim, v }, f);
  const target = new THREE.Vector3(...slot.pos).addScaledVector(want, 0.03);
  target.y += 0.11;
  moveTogether(app, [sim, ...others], { offset: target.sub(spacePos(v, v.bone('b__Pelvis__'))) });
  seatLegs(app, sim, v, slot, want);
  sim.pins = sim.pins || {};
  if (slot.kind !== 'in' && slot.feet) {
    if (slot.feet.L) sim.pins['L foot'] = [...slot.feet.L];
    if (slot.feet.R) sim.pins['R foot'] = [...slot.feet.R];
  }
  app.pipeline.base({ sim, v }, f);
  return true;
}

// The legs of a seated sim, in every key: the knees forward and up, the feet on the object's foot spots (a seat, a bed's
// edge) or stretched out along the bed (sitting up in bed). Without this a standing pose's straight knees could fold
// backwards into the seat when the feet are pinned.
function seatLegs(app, sim, v, slot, want) {
  const UPV = new THREE.Vector3(0, 1, 0);
  const bend = (frame, pose) => {
    app.pipeline.base({ sim, v }, frame);
    for (const side of ['L', 'R']) {
      const [A, B, C] = LIMBS[side + ' foot'].map(n => v.bone(n));
      if (!A || !B || !C) continue;
      const hip = spacePos(v, A);
      const feet = slot.kind !== 'in' && slot.feet && slot.feet[side];
      const target = feet ? new THREE.Vector3(...feet) : hip.clone().addScaledVector(want, 0.8).setY(Math.max(slot.pos[1] - 0.02, hip.y - 0.12));
      const pole = feet ? hip.clone().addScaledVector(want, 0.9).addScaledVector(UPV, 0.3) : hip.clone().addScaledVector(want, 0.45).addScaledVector(UPV, 0.5);
      solveTwoBone(v, A, B, C, target, pole);
    }
    pose.rot = pose.rot || {};
    for (const n of [...LIMBS['L foot'], ...LIMBS['R foot']]) if (v.bone(n)) pose.rot[n] = v.bone(n).quaternion.toArray();
  };
  for (const key of sim.keys) if (key.pose && !key.faceOnly) bend(key.frame, key.pose);
  const ov = app.pipeline.overrides.get(sim.id);
  if (ov && ov.pose) bend(ov.frame, ov.pose);
}

// "Lie here": a standing (upright) sim is laid on its back first; then the body turns so its head points to the
// spot's head end (the spot's dir points from the head end to the feet), its pelvis goes over the spot, and it rests
// on the surface (the lowest skin 5 mm above it).
export async function lieOn(app, sim, spot, info, { frame = null } = {}) {
  const v = app.simViews.get(sim.id);
  if (!v || !spot || !spot.pos) return false;
  const f = Math.round(frame ?? app.store.frame);
  const at = n => { app.pipeline.base({ sim, v }, f); return spacePos(v, v.bone(n)); };
  const head = v.bone('b__Head__') ? at('b__Head__') : null;
  const low = lowestSkin(app, [sim], f);
  if (head && head.y - low > 1.0) {
    // upright: tip it over onto its back (the chest faces up), around the pelvis
    app.pipeline.base({ sim, v }, f);
    const pel = spacePos(v, v.bone('b__Pelvis__'));
    const fwd = pelvisAxes(v).forward.setY(0);
    if (fwd.lengthSq() < 1e-6) fwd.set(0, 0, 1);
    turnSimBy(app, sim.id, new THREE.Quaternion().setFromUnitVectors(fwd.normalize(), UP), pel);
  }
  // along the spot: pelvis -> head toward the head end
  const dir = new THREE.Vector3(spot.dir ? spot.dir[0] : 0, 0, spot.dir ? spot.dir[2] : 1);
  if (dir.lengthSq() < 1e-6) dir.set(0, 0, 1);
  dir.normalize();
  const pel0 = at('b__Pelvis__'), hd = v.bone('b__Head__') ? at('b__Head__') : pel0.clone().addScaledVector(dir, -1);
  const up = hd.clone().sub(pel0).setY(0);
  if (up.lengthSq() > 1e-6) {
    const turn = wrap(Math.atan2(-dir.x, -dir.z) - Math.atan2(up.x, up.z));
    if (Math.abs(turn) > 1e-4) app.transformSim(sim.id, { angle: turn, pivot: pel0.clone().setY(0) });
  }
  const pel = at('b__Pelvis__');
  moveTogether(app, [sim], { offset: new THREE.Vector3(spot.pos[0] - pel.x, 0, spot.pos[2] - pel.z) });
  restOn(app, [sim], surfaceY(info, spot.pos[1]), { frame: f });
  app.pipeline.base({ sim, v }, f);
  return true;
}

const wrap = a => Math.atan2(Math.sin(a), Math.cos(a));
export { UP };

// Any furniture, any body, any pairing (R3-3; needs.md 8, 9, 12 and W4).
//
//   Move to another place: the whole animation is put on another piece of furniture - one of WickedWhims' 75 places
//   or a CC object from the Mods folder - resting on its real top, lying along it or sitting on its seats, the
//   resting hands and feet put back on the new surface, checked for parts inside the furniture and for clipping, and
//   saved as a NEW animation with the right places (the original is never changed).
//   Versions: shorter or taller, on a Tray sim's body, two women, two men, or the roles swapped (a strap-on on the
//   one who gives; the opening that is used follows the new body). The contacts that matter are kept: feet stay
//   planted, hands stay on the partner, heads meet for a kiss, the penis or strap-on stays in the opening. Each
//   version is its own animation (its own id), so versions sit next to each other in the game as siblings.
//
// Everything moves every key, the pins and the holds together (placing.js / app.transformSim), and the versions are
// worked out on a stand-in (a workbench with its own sims and pipeline), so the animation on screen is never touched.
import * as THREE from 'three';
import { api, projectFileName } from './api.js';
import { uid, localStorageGet } from './state.js';
import { Sim } from './sim.js';
import { Pipeline, simBody } from './pipeline.js';
import { LIMBS, HIPS, CENTER, PALM } from './bones.js';
import { spacePos, spaceQuat, setSpaceQuat, solveTwoBone } from './posemath.js';
import * as PL from './placing.js';
import { scanClipping, capsulesOf, capsuleNow } from './clipcheck.js';

const UP = new THREE.Vector3(0, 1, 0);
const wrap = a => Math.atan2(Math.sin(a), Math.cos(a));
const clone = x => JSON.parse(JSON.stringify(x));

// ---------------------------------------------------------------- places
// The app's furniture kinds for a place's use (no size: the simple stand-in shapes are never built for them; the
// real object always is)
const APP_KIND = { bed: 'bed', seat: 'sofa', surface: 'table', water: 'tub', floor: 'mat', wall: 'wall' };
let _places = null;
export function loadPlaces({ force = false } = {}) {
  if (!_places || force) {
    // a refusal keeps the server's own words ("The Sims 4 install not found...") for the window to show
    _places = fetch('/api/refit_places').then(async r => {
      if (r.ok) return r.json();
      const body = await r.json().catch(() => ({}));
      throw Object.assign(new Error(body.error || 'HTTP ' + r.status), { status: r.status });
    }).catch(err => { _places = null; throw err; });
  }
  return _places;
}
export const isExtra = id => typeof id === 'string' && /^(ww|cc):/.test(id);

// Every place in one list: [{id, label, group, kind, location?, object_id, cc?}]
export async function allPlaces() {
  const r = await loadPlaces();
  return [...(r.places || []), ...(r.cc || [])];
}

// The app's furniture entry for a place: its own for the ones it knows (bed, sofa...), added for the others so the
// Scene step, the clipping check and Send to game name it and the stage shows its real object.
// The object itself comes from /api/refit_places?place=<id> (the server's furniture_mesh only knows the app's own
// places): that answer is put where the stage, placing.js and the clipping check look for it (app._furnInfo, by id).
export function ensurePlace(app, row) {
  if (!row) return null;
  let def = (app.furniture || []).find(f => f.id === row.id);
  if (!def) {
    def = { id: row.id, label: row.label, locations: row.location ? [row.location] : ['NONE'], kind: APP_KIND[row.kind] || 'table',
      extra: true, refitKind: row.kind, cc: !!row.cc, objectId: row.object_id };
    app.furniture.push(def);
  }
  if (isExtra(row.id)) {
    app._furnInfo = app._furnInfo instanceof Map ? app._furnInfo : new Map();
    app._refitAsked = app._refitAsked || new Set();
    if (!app._refitAsked.has(row.id)) {
      app._refitAsked.add(row.id);
      const ask = () => fetch('/api/refit_places?place=' + encodeURIComponent(row.id)).then(r => (r.ok ? r.json() : null)).catch(() => null);
      // something may have asked furniture_mesh first (which doesn't know these places): its empty answer is replaced
      const before = app._furnInfo.get(row.id);
      const info = before ? Promise.resolve(before).then(v => (v && v.meshes ? v : ask())) : ask();
      app._furnInfo.set(row.id, info);
      if (app._furnInfoKnown instanceof Map) info.then(v => app._furnInfoKnown.set(row.id, v || null));
    }
  }
  return def;
}

// An animation saved on one of the extra places (ww:... or cc:...): its place is added again when it is opened, and
// the stage shows the real object. -> the place's entry, or null (not an extra place, or not on this PC any more)
export async function restorePlace(app, project = app.store.project) {
  const id = project && project.furniture;
  if (!isExtra(id)) return null;
  const known = (app.furniture || []).find(f => f.id === id);
  const row = known ? { id, label: known.label, location: known.locations[0], kind: known.refitKind, cc: known.cc, object_id: known.objectId }
    : await placeRow(id);
  if (!row) return null;
  const def = ensurePlace(app, row);
  if (app.store.project === project && typeof app.buildFurniture === 'function') { app._furnId = null; app.buildFurniture(); }
  return def;
}

// The place row for an id (null when it is not known any more - a CC object that left the Mods folder)
export async function placeRow(id) {
  if (!id) return null;
  if (id === 'floor') return { id: 'floor', label: 'Floor', kind: 'floor', location: 'FLOOR', group: 'Floor and walls' };
  const list = await allPlaces().catch(() => []);
  return list.find(x => x.id === id || (x.location && ('ww:' + x.location) === id)) || null;
}

// ---------------------------------------------------------------- measuring
// Every posable bone's world position of the sims (their current pose).
const ALL_BONES = [...CENTER, ...['Clavicle', 'UpperArm', 'Forearm', 'Hand', 'Thigh', 'Calf', 'Foot', 'Toe'].flatMap(n => [`b__L_${n}__`, `b__R_${n}__`])];

// Bones inside the furniture: below its top - 3 cm where the grid has a height (down to 30 cm under it - not the
// floor under a table top), on the keyed pose of every key and over the playing loop (every 3rd frame).
export function bonesBelow(app, info, { frames = null, loop = true } = {}) {
  const g = info ? PL.gridOf(info) : null;
  const out = { n: 0, worst: 0, where: '' };
  const test = label => {
    for (const e of app.pipeline.entries()) {
      e.v.group.updateMatrixWorld(true);
      for (const n of ALL_BONES) {
        if (!e.v.bone(n)) continue;
        const q = e.v.worldPos(n);
        const hh = g ? PL.gridHeight(g, q.x, q.z) : 0;
        if (hh !== null && q.y < hh - 0.03 && q.y > hh - 0.3) {
          out.n++;
          if (hh - q.y > out.worst) { out.worst = hh - q.y; out.where = `${label} ${e.sim.label} ${n}`; }
        }
      }
    }
  };
  const p = app.store.project;
  const keyFrames = frames || [...new Set(p.sims.flatMap(s => s.keys.filter(k => !k.faceOnly).map(k => k.frame)))];
  for (const f of keyFrames) { for (const e of app.pipeline.entries()) app.pipeline.base(e, f); for (const e of app.pipeline.entries()) app.pipeline.base(e, f); test('key ' + f); }
  if (loop) for (let k = 0; k < p.length; k += 3) { app.pipeline.apply(k, { physics: true, overrides: false }); test('frame ' + k); }
  return out;
}

// ---------------------------------------------------------------- where the bodies go
function isStanding(app, sims) {
  return sims.some(s => {
    const v = app.simViews.get(s.id), hd = v && v.bone('b__Head__');
    if (!hd) return false;
    const low = PL.lowestSkin(app, [s], 0);
    return spacePos(v, hd).y - low > 1.25;
  });
}
function sittingSim(app, sims) {
  for (const s of sims) {
    const v = app.simViews.get(s.id);
    if (!v || !v.bone('b__Pelvis__') || !v.bone('b__Head__')) continue;
    const low = PL.lowestSkin(app, [s], 0);
    app.pipeline.base({ sim: s, v }, 0);
    const pel = spacePos(v, v.bone('b__Pelvis__')), head = spacePos(v, v.bone('b__Head__'));
    if (pel.y - low < 0.3 && head.y - pel.y > 0.35) return s;
  }
  return null;
}

// Centre the bodies on a point of the floor (or a low surface) and rest them on `top`.
function centreOn(app, sims, at, top) {
  const pts = PL.bodyPoints(app, sims, 0).all;
  if (!pts.length) return;
  let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
  for (const q of pts) { x0 = Math.min(x0, q.x); x1 = Math.max(x1, q.x); z0 = Math.min(z0, q.z); z1 = Math.max(z1, q.z); }
  PL.moveTogether(app, sims, { offset: new THREE.Vector3(at.x - (x0 + x1) / 2, 0, at.z - (z0 + z1) / 2) });
  PL.restOn(app, sims, top, { frame: 0 });
}

// Put the (already posed) sims on the place. Like Magic's placement, for any animation and any object:
//   no top (a door, a window, a dance floor): on the floor, in front of it;  someone stands: in front of it (on it
//   when it is a mat or a shower floor);  a lap ride with seats: the sitter on the middle seat;  beds and anything
//   with lying spots, and bodies that fit along the top: lying or kneeling along it;  too long for it: on the floor
//   in front of it.  -> 'on' | 'front' | 'lap' | 'floor'
export async function placeOn(app, sims, info, row) {
  const kind = row ? row.kind : 'surface';
  const top = info ? PL.surfaceY(info, NaN) : NaN;
  if (!info || !Number.isFinite(top) || kind === 'wall') {
    if (info && info.bounds && kind === 'wall') { PL.inFrontOf(app, sims, info, { frame: 0 }); return 'front'; }
    const b = info && info.bounds;
    centreOn(app, sims, b ? new THREE.Vector3((b.min[0] + b.max[0]) / 2, 0, (b.min[2] + b.max[2]) / 2) : new THREE.Vector3(), Math.max(0, Number.isFinite(top) && top < 0.1 ? top : 0));
    return 'floor';
  }
  const pts = PL.bodyPoints(app, sims, 0), body = PL.longAxis(pts.all, pts.heads, pts.pelvises);
  if (isStanding(app, sims)) {
    if (top < 0.2) {                       // a mat, a towel, a shower floor: they stand on it
      const c = PL.surfaceCentre(info) || new THREE.Vector3();
      centreOn(app, sims, c, top);
      PL.nudgeInside(app, sims, PL.gridOf(info), 0, top);
      return 'on';
    }
    PL.inFrontOf(app, sims, info, { frame: 0 });
    return 'front';
  }
  const slots = info.slots || [];
  const hasLie = slots.some(s => s.kind === 'lie' || s.kind === 'in');
  const seats = slots.filter(s => s.kind === 'seat');
  if (seats.length && sittingSim(app, sims) && body.length <= 1.1) { await PL.fitOnSurface(app, sims, info, { frame: 0 }); return 'lap'; }
  const surf = PL.surfaceAxis(info);
  if (kind === 'bed' || (hasLie && surf && surf.length >= body.length - 0.1) || body.length <= 1.1 || (surf && surf.length >= body.length - 0.1)) {
    await PL.fitOnSurface(app, sims, info, { frame: 0 });
    return 'on';
  }
  PL.inFrontOf(app, sims, info, { frame: 0 });
  return 'front';
}

// ---------------------------------------------------------------- the limbs on the new surface
// Fixed pins (a hand or a foot resting on the bed, pinned there by Magic or by hand) went along with the bodies. On
// the new furniture they are put back on its top: at the same height above it as before, onto the nearest spot of
// the top when they now hang over an edge or sit inside an armrest or a backrest.
function pinsOf(sims) {
  const out = [];
  for (const s of sims) for (const [limb, pin] of Object.entries(s.pins || {})) {
    if (Array.isArray(pin)) out.push({ sim: s, limb, get: () => s.pins[limb], set: a => { s.pins[limb] = a; } });
    else if (pin && Array.isArray(pin.at)) out.push({ sim: s, limb, get: () => pin.at, set: a => { pin.at = a; } });
  }
  return out;
}
export function pinClearances(sims, info) {
  const g = info ? PL.gridOf(info) : null;
  return pinsOf(sims).map(x => { const p = x.get(); const h = g ? PL.gridHeight(g, p[0], p[2]) : null; return { ...x, clear: p[1] - (h ?? 0) }; });
}
function nearestTopCell(g, top, x, z, radius = 0.35) {
  let best = null, bd = Infinity;
  const r = Math.ceil(radius / g.cell);
  const i0 = Math.floor((x - g.x0) / g.cell), j0 = Math.floor((z - g.z0) / g.cell);
  for (let dj = -r; dj <= r; dj++) for (let di = -r; di <= r; di++) {
    const i = i0 + di, j = j0 + dj;
    if (i < 0 || j < 0 || i >= g.w || j >= g.d) continue;
    const hh = g.h[j * g.w + i];
    if (hh === -32768 || Math.abs(hh / 1000 - top) > 0.05) continue;
    const cx = g.x0 + (i + 0.5) * g.cell, cz = g.z0 + (j + 0.5) * g.cell;
    // one cell in from the edge, so a palm or a foot rests on it, not on its rim
    const d = Math.hypot(cx - x, cz - z);
    if (d < bd && d <= radius) { bd = d; best = { x: cx, z: cz, h: hh / 1000 }; }
  }
  return best;
}
export function reseatPins(before, info) {
  const g = info ? PL.gridOf(info) : null, top = PL.surfaceY(info, 0);
  let moved = 0;
  for (const x of before) {
    const p = x.get();
    const h = g ? PL.gridHeight(g, p[0], p[2]) : 0;
    const clear = THREE.MathUtils.clamp(x.clear, 0, 0.15);
    if (h !== null && (!g || Math.abs(h - top) < 0.08)) {
      const y = h + clear;
      if (Math.abs(y - p[1]) > 0.002) { x.set([p[0], y, p[2]]); moved++; }
      continue;
    }
    if (!g) continue;
    const c = nearestTopCell(g, top, p[0], p[2]);
    if (c) { x.set([c.x, c.h + clear, c.z]); moved++; }
    else if (h === null && p[1] - clear > 0.25) {
      // over the floor beside the furniture, out of reach of its top: it goes down to the floor
      x.set([p[0], clear, p[2]]); moved++;
    }
  }
  return moved;
}

// After the move: anything still inside the furniture over the loop (a thrust pushing a knee into a cushion, a hand
// in the pillows) is lifted: a pinned limb by its pin; otherwise everyone together, by the depth (at most 3 rounds).
export function settleOnTop(app, sims, info) {
  const g = info ? PL.gridOf(info) : null;
  if (!g) return 0;
  let lifted = 0;
  for (let pass = 0; pass < 3; pass++) {
    const issues = scanClipping(app, { step: 2, info }).filter(i => i.otherId === null && i.depth > 0.03);
    const below = bonesBelow(app, info, { loop: true });
    if (!issues.length && !below.n) break;
    let body = 0;
    const pinned = pinClearances(sims, null);
    for (const it of issues) {
      const s = sims.find(x => x.id === it.simId);
      const pin = it.limb && pinned.find(x => x.sim === s && x.limb === it.limb);
      if (pin) { const p = pin.get(); pin.set([p[0], p[1] + it.depth - 0.02, p[2]]); }
      else body = Math.max(body, it.depth - 0.025);
    }
    if (below.n) body = Math.max(body, below.worst - 0.025);
    if (body > 0.002) { PL.moveTogether(app, sims, { offset: new THREE.Vector3(0, Math.min(body, 0.12), 0) }); lifted += Math.min(body, 0.12); }
  }
  return lifted;
}

// ---------------------------------------------------------------- a new animation
// A name no saved animation uses yet ("Cowgirl (Sofa)", "Cowgirl (Sofa) 2").
export async function freeName(app, name) {
  let list = [];
  try { list = await api.projects(); } catch { /* the server keeps both anyway */ }
  const taken = new Set(list.map(m => (m.name || '').toLowerCase()));
  const files = new Set(list.map(m => (m.file || '').toLowerCase()));
  if (!taken.has(name.toLowerCase()) && !files.has(projectFileName(name).toLowerCase())) return name;
  for (let n = 2; n < 1000; n++) {
    const c = `${name} ${n}`;
    if (!taken.has(c.toLowerCase()) && !files.has(projectFileName(c).toLowerCase())) return c;
  }
  return `${name} ${Date.now() % 10000}`;
}

// Someone else's animation (imported from the library): the copy is for the user's own game, the credit is kept.
export function creditOf(p) {
  const mine = (localStorageGet('author', '') || '').trim().toLowerCase();
  if (p.credit && p.credit.author && p.credit.author.trim().toLowerCase() !== mine) return p.credit;
  return null;
}

// A copy of the project as a new animation: its own id (so its game names never clash), no saved thumbnail.
export function newVersionOf(p, { name, label, kind }) {
  const q = clone(p);
  q.uid = uid('a');
  q.name = name;
  delete q.thumb;
  q.versionOf = { uid: p.uid, name: p.name, kind, label };
  return q;
}

// Open a project in the editor as a new, not yet saved animation (like opening a saved one).
export function openInEditor(app, p) {
  app.store.load(p);
  app._file = null;
  app.playRange = null;
  app._lastPreset = null;
  app.shareData = null;
  app.pipeline.overrides.clear();
  app.refreshAll();
  app.timeline.fit();
  app.pipeline.simulateIfNeeded(true);
  app._projectLoaded();
}

// Tray bodies arrive a moment after the sims: wait until every Tray sim has its own body (at most `ms`).
async function trayBodiesReady(app, ms = 15000) {
  const t0 = performance.now();
  while (performance.now() - t0 < ms) {
    const p = app.store.project;
    if (p.sims.every(s => !s.tray || app.assets.bodies['tray:' + s.id])) return true;
    await new Promise(r => setTimeout(r, 120));
  }
  return false;
}

// Move the open animation to another place, as a NEW animation. The original stays as it was (saved first when it
// has changes). -> {project, where, below, issues, deep, lifted, pins, name, from}
export async function moveToPlace(app, row, { save = true, name = null } = {}) {
  if (!row) throw new Error('Pick a place first.');
  const orig = app.store.project;
  if (!orig.sims.length) throw new Error('There are no sims to move.');
  if (app.playing) app.setPlaying(false);
  if (app.endTrial && app.trial && app.trial.size) app.endTrial();
  if (save && app.store.dirty && orig.sims.some(s => s.keys.length)) {
    const ok = await app.save();
    if (!ok) throw new Error('The original could not be saved first, so nothing was moved.');
  }
  const fromDef = (app.furniture || []).find(f => f.id === orig.furniture);
  const fromInfo = orig.furniture && orig.furniture !== 'floor' ? await app._furnitureInfo(orig.furniture) : null;
  const def = row.id === 'floor' ? app.furniture.find(f => f.id === 'floor') : ensurePlace(app, row);
  const label = def ? def.label : row.label;
  const p = newVersionOf(orig, { name: name || await freeName(app, `${orig.name} (${label})`), label, kind: 'place' });
  p.furniture = row.id;
  if (row.cc) { p.locations = ['NONE']; p.customLocations = [String(row.object_id)]; }
  else { p.locations = def ? [...def.locations] : [row.location]; delete p.customLocations; }
  p.movedFrom = { uid: orig.uid, name: orig.name, furniture: orig.furniture || 'floor', locations: [...(orig.locations || [])] };
  const info = row.id === 'floor' ? null : await app._furnitureInfo(row.id);
  if (row.id !== 'floor' && !info) throw new Error(`The ${label.toLowerCase()} could not be read from the game files.`);
  // the resting hands and feet: how high above the old furniture's top they were
  const clears = pinClearances(p.sims, fromInfo);
  openInEditor(app, p);
  await trayBodiesReady(app);
  const sims = app.store.project.sims;
  const clearsNow = clears.map(c => { const s = sims.find(x => x.id === c.sim.id); const pin = s && s.pins[c.limb];
    return pin ? { sim: s, limb: c.limb, clear: c.clear, get: () => (Array.isArray(s.pins[c.limb]) ? s.pins[c.limb] : s.pins[c.limb].at), set: a => { if (Array.isArray(s.pins[c.limb])) s.pins[c.limb] = a; else s.pins[c.limb].at = a; } } : null; }).filter(Boolean);
  const before = clone(sims.map(s => ({ keys: s.keys, pins: s.pins })));
  let where = await placeOn(app, sims, info, row);
  let pinsMoved = reseatPins(clearsNow, info);
  let lifted = settleOnTop(app, sims, info);
  let below = bonesBelow(app, info);
  let issues = scanClipping(app, { step: 1, info });
  let deep = issues.filter(i => i.depth > 0.04);
  // lying on it did not work out (it goes into the furniture): on the floor in front of it instead
  const furnDeep = () => deep.filter(i => i.otherId === null).length;
  if (info && where === 'on' && (below.n || furnDeep()) && row.kind !== 'bed') {
    sims.forEach((s, i) => { s.keys = clone(before[i].keys); s.pins = clone(before[i].pins); });
    PL.inFrontOf(app, sims, info, { frame: 0 });
    where = 'front';
    pinsMoved = reseatPins(clearsNow.map(c => ({ ...c, clear: Math.min(c.clear, 0.05) })), null);
    lifted = 0;
    below = bonesBelow(app, info);
    issues = scanClipping(app, { step: 1, info });
    deep = issues.filter(i => i.depth > 0.04);
  }
  app.applyPoses();
  app.refreshAll();
  app.physicsChanged();
  if (app.interact) app.interact.refreshHandles();
  try { app.frameSims({ fromFront: true }); } catch { /* no camera in a test page */ }
  app.store.setDirty(true);
  let saved = null;
  if (save) { const ok = await app.save(); saved = ok ? app._file : null; }
  return { project: app.store.project, name: app.store.project.name, where, below, issues, deep, lifted, pins: pinsMoved,
    from: { name: orig.name, uid: orig.uid, label: fromDef ? fromDef.label : 'Floor' }, to: label, saved, credit: creditOf(orig) };
}

// ---------------------------------------------------------------- the workbench (versions)
// A stand-in app with its own sims and pipeline: a project is posed, measured and changed there without touching the
// animation on screen.
export async function workbench(app, project, { strapOn = true } = {}) {
  const views = new Map();
  for (const s of project.sims) {
    simBody(s);
    let body = app.assets.bodies[s.frame] || app.assets.bodies.yf;
    if (s.tray) {
      const key = 'tray:' + s.id;
      const known = app.assets.bodies[key];
      if (known) body = known;
      else {
        const cacheKey = `refit:tray:${s.tray.id}:${s.tray.index}`;
        if (!app.assets.bodies[cacheKey]) { try { app.assets.bodies[cacheKey] = (await api.traySim(s.tray.id, s.tray.index)).body; } catch { /* the generic body */ } }
        body = app.assets.bodies[cacheKey] || body;
      }
    }
    const v = new Sim(app.assets.rig, body, { color: s.color, skin: s.skin });
    if (strapOn && wantsStrap(s, v)) v.hasPenis = true;
    views.set(s.id, v);
  }
  const wb = {
    store: { project, frame: 0, selected: { sim: null, bone: null }, sim: id => project.sims.find(s => s.id === (id ?? null)) },
    simViews: views, furniture: app.furniture, assets: app.assets, interact: null, vp: null,
    _furnInfo: app._furnInfo, _furnInfoKnown: app._furnInfoKnown,
    _furnitureInfo: id => app._furnitureInfo(id),
    applyPoses() {}, emit() {}, runHook() { return []; },
    dispose() { for (const v of views.values()) { try { app.disposeView(v); } catch { /* gone */ } } views.clear(); },
  };
  wb.pipeline = new Pipeline(wb);
  return wb;
}

// A strap-on is shown (and counts for the openings) on a sim that gives without a penis of its own.
export function wantsStrap(s, v = null) {
  if (!s || !s.strapon || s.strapView === false) return false;
  if (s.frame !== 'yf') return false;
  return !(v && v._ownPenis);
}

// ---------------------------------------------------------------- contacts
const HOLE_BONES = { vagina: ['b__Up_Vagina__', 'b__Low_Vagina__'], anus: ['b__Up_Anus', 'b__Low_Anus'], mouth: ['b__UpLip__', 'b__LoLip__'] };
const HOLE_FRAME = { vagina: 'b__Pelvis__', anus: 'b__Pelvis__', mouth: 'b__Head__' };
function holePoint(v, hole) {
  const [a, b] = HOLE_BONES[hole];
  if (!v.bone(a) || !v.bone(b)) return null;
  return v.worldPos(a).add(v.worldPos(b)).multiplyScalar(0.5);
}
const boneMatrix = (v, n) => { const b = v.bone(n); b.updateWorldMatrix(true, false); return b.matrixWorld.clone(); };
const palmOf = (v, limb) => (PALM[limb] && v.bone(PALM[limb]) ? v.worldPos(PALM[limb]) : v.worldPos(LIMBS[limb][2]));
const bodyKeyFrames = p => [...new Set(p.sims.flatMap(s => s.keys.filter(k => !k.faceOnly && k.pose).map(k => k.frame)))].sort((a, b) => a - b);

function poseAll(wb, f) {
  const all = wb.pipeline.entries();
  for (const e of all) wb.pipeline.base(e, f);
  for (const e of all) wb.pipeline.base(e, f);          // holds see the partner's pose of this frame
  for (const e of all) e.v.group.updateMatrixWorld(true);
  return all;
}

// What touches what at every key frame: the resting hands and feet (on the floor or the furniture), hands on the
// partner, heads together (a kiss), and the penis or strap-on in an opening. Pinned and held limbs are left out -
// their pins and holds keep them in place by themselves.
export function captureContacts(wb, info) {
  const p = wb.store.project, g = info ? PL.gridOf(info) : null;
  const ground = (x, z) => { const h = g ? PL.gridHeight(g, x, z) : null; return h ?? 0; };
  const frames = bodyKeyFrames(p), out = new Map();
  for (const f of frames) {
    const all = poseAll(wb, f), list = [];
    for (const e of all) {
      const { sim, v } = e;
      if (!sim.keys.some(k => k.frame === f && !k.faceOnly)) continue;
      for (const limb of Object.keys(LIMBS)) {
        if (sim.pins && sim.pins[limb]) continue;
        const end = v.bone(LIMBS[limb][2]);
        if (!end) continue;
        const isHand = limb.endsWith('hand');
        const pt = isHand ? palmOf(v, limb) : v.worldPos(LIMBS[limb][2]);
        const wrist = v.worldPos(LIMBS[limb][2]), q = spaceQuat(v, end);
        const lift = pt.y - ground(pt.x, pt.z);
        if (lift < (isHand ? 0.06 : 0.14)) { list.push({ type: 'ground', sim: sim.id, limb, at: wrist.toArray(), q: q.toArray(), lift }); continue; }
        if (!isHand) continue;
        // the nearest partner part within 4 cm of the palm
        let best = null;
        for (const o of all) {
          if (o === e) continue;
          for (const c of capsulesOf(o.v)) {
            const now = capsuleNow(o.v, c);
            if (!now) continue;
            const ab = now.b.clone().sub(now.a), t = THREE.MathUtils.clamp(pt.clone().sub(now.a).dot(ab) / Math.max(1e-9, ab.lengthSq()), 0, 1);
            const d = now.a.clone().addScaledVector(ab, t).distanceTo(pt) - now.r;
            if (d < 0.04 && (!best || d < best.d)) best = { d, other: o, bone: c.from };
          }
        }
        if (best) {
          const M = boneMatrix(best.other.v, best.bone), Mi = M.clone().invert();
          const bq = best.other.v.bone(best.bone).getWorldQuaternion(new THREE.Quaternion());
          list.push({ type: 'partner', sim: sim.id, limb, other: best.other.sim.id, bone: best.bone,
            local: wrist.clone().applyMatrix4(Mi).toArray(), q: bq.invert().multiply(end.getWorldQuaternion(new THREE.Quaternion())).toArray() });
        }
      }
      // a kiss: the heads within 22 cm
      const head = v.bone('b__Head__') && v.worldPos('b__Head__');
      if (head) for (const o of all) {
        if (o === e || !o.v.bone('b__Head__')) continue;
        if (o.v.worldPos('b__Head__').distanceTo(head) < 0.22) {
          const Mi = boneMatrix(o.v, 'b__Head__').invert();
          list.push({ type: 'head', sim: sim.id, other: o.sim.id, local: head.clone().applyMatrix4(Mi).toArray() });
        }
      }
      // the penis (or strap-on) in an opening of the partner: where its tip is, seen from that opening
      if (v.bone('b__Penis_Tip') && (v.hasPenis || wantsStrap(sim, v))) {
        const tip = v.worldPos('b__Penis_Tip');
        let best = null;
        for (const o of all) {
          if (o === e) continue;
          for (const hole of Object.keys(HOLE_BONES)) {
            if (hole === 'vagina' && !o.v.hasVagina) continue;
            const hp = holePoint(o.v, hole);
            if (!hp) continue;
            const d = hp.distanceTo(tip);
            if (d < 0.12 && (!best || d < best.d)) best = { d, other: o, hole, hp };
          }
        }
        if (best) {
          const fr = HOLE_FRAME[best.hole], bq = best.other.v.bone(fr).getWorldQuaternion(new THREE.Quaternion()).invert();
          list.push({ type: 'penis', sim: sim.id, other: best.other.sim.id, hole: best.hole, off: tip.clone().sub(best.hp).applyQuaternion(bq).toArray() });
        }
      }
    }
    out.set(f, list);
  }
  return out;
}

// Move a key's hips (both hip bones) by `delta` (sim space).
function shiftHips(v, pose, delta) {
  const rb = v.bone('b__ROOT_bind__');
  const rbQ = spaceQuat(v, rb), rbP = spacePos(v, rb), rbQi = rbQ.clone().invert();
  pose.pos = pose.pos || {};
  for (const n of HIPS) {
    const k = v.index(n);
    if (k < 0) continue;
    const at = pose.pos[n] ? new THREE.Vector3().fromArray(pose.pos[n]) : v.rest[k].pos.clone();
    const sp = at.applyQuaternion(rbQ).add(rbP).add(delta);
    pose.pos[n] = sp.sub(rbP).applyQuaternion(rbQi).toArray();
  }
}
const keyAt = (sim, f) => sim.keys.find(k => k.frame === f && !k.faceOnly && k.pose);

// Bend the neck and upper back (at most 18 degrees each) so the head goes toward `target` (a kiss).
function reachHead(v, target) {
  const chain = ['b__Spine1__', 'b__Spine2__', 'b__Neck__'].map(n => v.bone(n)).filter(Boolean);
  const head = v.bone('b__Head__');
  if (!head || !chain.length) return;
  const lim = THREE.MathUtils.degToRad(18);
  const start = chain.map(b => b.quaternion.clone());
  for (let it = 0; it < 4; it++) {
    for (let k = chain.length - 1; k >= 0; k--) {
      const b = chain[k];
      const bp = spacePos(v, b), hp = spacePos(v, head);
      const a = hp.clone().sub(bp), t = target.clone().sub(bp);
      if (a.lengthSq() < 1e-8 || t.lengthSq() < 1e-8) continue;
      const dq = new THREE.Quaternion().setFromUnitVectors(a.normalize(), t.normalize());
      const bq = spaceQuat(v, b);
      const want = dq.multiply(bq);
      setSpaceQuat(v, b, want);
      // keep it natural: no joint turns further than the limit from where the key had it
      const d = start[k].angleTo(b.quaternion);
      if (d > lim) b.quaternion.copy(start[k].clone().slerp(b.quaternion, lim / d));
      b.updateMatrixWorld(true);
    }
    if (spacePos(v, head).distanceTo(target) < 0.01) break;
  }
}

// Put the recorded contacts back on the changed bodies, key by key: the giver's hips move so the tip is where it was
// in the opening (or in the other opening when that body has no vagina); planted hands and feet reach their spots
// again; hands on the partner reach the same place on the partner's body (turned the same way); heads meet again.
// Only the bones that moved are written into the keys. -> {hips, limbs, heads, worst}
// movers: the sims whose body changed - when only the one receiving changed, it moves to the penis instead (a
// shorter woman riding stays on her knees; the man under her stays on the bed).
export function applyContacts(wb, contacts, { remap = {}, movers = null } = {}) {
  const stats = { hips: 0, limbs: 0, heads: 0, worst: 0, missed: 0 };
  const byId = id => wb.pipeline.entries().find(e => e.sim.id === id);
  for (const [f, list] of contacts) {
    // 1. the penis or strap-on in its opening: the giver's hips move (or the receiver's)
    for (const c of list.filter(x => x.type === 'penis')) {
      const e = byId(c.sim), o = byId(c.other);
      if (!e || !o) continue;
      const receiverMoves = movers && movers.has(c.other) && !movers.has(c.sim);
      const key = receiverMoves ? keyAt(o.sim, f) : keyAt(e.sim, f);
      if (!key) continue;
      poseAll(wb, f);
      let hole = remap[c.other] && remap[c.other][c.hole] ? remap[c.other][c.hole] : c.hole;
      if (hole === 'vagina' && !o.v.hasVagina) hole = 'anus';
      const hp = holePoint(o.v, hole);
      if (!hp || !e.v.bone('b__Penis_Tip')) continue;
      const bq = o.v.bone(HOLE_FRAME[hole]).getWorldQuaternion(new THREE.Quaternion());
      const target = hp.add(new THREE.Vector3().fromArray(c.off).applyQuaternion(bq));
      const delta = target.sub(e.v.worldPos('b__Penis_Tip'));
      if (delta.length() > 0.002) {
        if (receiverMoves) shiftHips(o.v, key.pose, delta.negate()); else shiftHips(e.v, key.pose, delta);
        stats.hips++;
      }
    }
    // 2. hands and feet, 3. heads
    const all = poseAll(wb, f);
    for (const c of list) {
      if (c.type !== 'ground' && c.type !== 'partner' && c.type !== 'head') continue;
      const e = all.find(x => x.sim.id === c.sim), key = e && keyAt(e.sim, f);
      if (!e || !key) continue;
      const v = e.v;
      if (c.type === 'head') {
        const o = all.find(x => x.sim.id === c.other);
        if (!o) continue;
        const target = new THREE.Vector3().fromArray(c.local).applyMatrix4(boneMatrix(o.v, 'b__Head__'));
        if (v.worldPos('b__Head__').distanceTo(target) < 0.012) continue;
        reachHead(v, target);
        for (const n of ['b__Spine1__', 'b__Spine2__', 'b__Neck__']) if (v.bone(n)) key.pose.rot[n] = v.bone(n).quaternion.toArray();
        stats.heads++;
        continue;
      }
      const chain = LIMBS[c.limb].map(n => v.bone(n));
      if (chain.some(b => !b)) continue;
      let target, handQ = null;
      if (c.type === 'ground') { target = new THREE.Vector3().fromArray(c.at); handQ = new THREE.Quaternion().fromArray(c.q); }
      else {
        const o = all.find(x => x.sim.id === c.other);
        if (!o || !o.v.bone(c.bone)) continue;
        target = new THREE.Vector3().fromArray(c.local).applyMatrix4(boneMatrix(o.v, c.bone));
        const bq = o.v.bone(c.bone).getWorldQuaternion(new THREE.Quaternion());
        handQ = bq.multiply(new THREE.Quaternion().fromArray(c.q));
      }
      const now = v.worldPos(LIMBS[c.limb][2]);
      if (now.distanceTo(target) < 0.006) continue;
      if (handQ) setSpaceQuat(v, chain[2], handQ);
      const A = spacePos(v, chain[0]), B = spacePos(v, chain[1]), C = spacePos(v, chain[2]);
      const mid = A.clone().add(C).multiplyScalar(0.5), outw = B.clone().sub(mid);
      const pole = outw.lengthSq() > 1e-6 ? B.clone().add(outw.normalize().multiplyScalar(0.4)) : null;
      solveTwoBone(v, chain[0], chain[1], chain[2], target, pole);
      for (const b of chain) key.pose.rot[b.name] = b.quaternion.toArray();
      const miss = spacePos(v, chain[2]).distanceTo(target);
      stats.worst = Math.max(stats.worst, miss);
      if (miss > 0.02) stats.missed++;
      stats.limbs++;
    }
  }
  return stats;
}

// ---------------------------------------------------------------- the versions
// Bones that make a body taller or shorter (their place along the parent grows or shrinks); the hands, feet, head and
// face keep their size.
const GROW = ['b__Spine1__', 'b__Spine2__', 'b__Neck__', 'b__Head__',
  ...['Clavicle', 'UpperArm', 'Forearm', 'Hand', 'Thigh', 'Calf', 'Foot', 'ShoulderTwist', 'ForearmTwist', 'ThighTwist'].flatMap(n => [`b__L_${n}__`, `b__R_${n}__`])];
export const HEIGHTS = { short: { scale: 0.93, label: 'shorter', word: 'Short' }, tall: { scale: 1.07, label: 'taller', word: 'Tall' } };

// Scale a sim's body in every key (the bones' places, so it shows in the game too), with the hips' height over
// what it stands, sits or lies on scaled the same way.
function scaleBody(wb, sim, s, info) {
  const e = wb.pipeline.entries().find(x => x.sim === sim);
  if (!e) return;
  const v = e.v, g = info ? PL.gridOf(info) : null;
  for (const key of sim.keys) {
    if (key.faceOnly || !key.pose) continue;
    wb.pipeline.base(e, key.frame);
    v.group.updateMatrixWorld(true);
    const pel = v.worldPos('b__Pelvis__');
    const low = PL.lowestSkin(wb, [sim], key.frame);
    const floorY = g ? (PL.gridHeight(g, pel.x, pel.z) ?? 0) : 0;
    const base = Math.max(floorY, Math.min(low, pel.y));
    const dy = (pel.y - base) * (s - 1);
    key.pose.pos = key.pose.pos || {};
    for (const n of GROW) {
      const k = v.index(n);
      if (k < 0) continue;
      const at = key.pose.pos[n] ? new THREE.Vector3().fromArray(key.pose.pos[n]) : v.rest[k].pos.clone();
      key.pose.pos[n] = at.multiplyScalar(s).toArray();
    }
    if (Math.abs(dy) > 1e-4) shiftHips(v, key.pose, new THREE.Vector3(0, dy, 0));
  }
}

const GENDER_OF = { yf: 'FEMALE', ym: 'MALE', yf_futa: 'MALE' };
const FRAME_WORD = { yf: 'Female', ym: 'Male', yf_futa: 'Female' };
const hasPenisFrame = f => f === 'ym' || f === 'yf_futa';

// A new body type for a sim (keeps its motion): label, gender, strap-on when it gives without a penis.
function reBody(sim, frame, p, giver) {
  const was = sim.frame;
  if (was === frame) return false;
  sim.frame = frame;
  sim.gender = GENDER_OF[frame] || 'BOTH';
  delete sim.tray;
  sim.tone = '';
  if (/^(Female|Male) \d+$/.test(sim.label || '')) {
    const word = FRAME_WORD[frame] || 'Sim', used = new Set(p.sims.filter(x => x !== sim).map(x => x.label));
    let n = 1; while (used.has(`${word} ${n}`)) n++;
    sim.label = `${word} ${n}`;
  }
  if (giver && !hasPenisFrame(frame)) { sim.strapon = true; sim.strapView = true; } else { delete sim.strapView; if (hasPenisFrame(frame)) delete sim.strapon; }
  // the voice goes with the body (a man's moans on a woman would be the wrong voice)
  if ((GENDER_OF[was] === 'MALE') !== (GENDER_OF[frame] === 'MALE')) {
    delete sim.voice; delete sim.voicePitch;
    sim.sounds = (sim.sounds || []).filter(x => x.kind !== 'voice');
    sim._needVoices = true;
    if (sim.hair && typeof sim.hair === 'object' && sim.hair.name && !sim.hair.name.startsWith(frame === 'ym' ? 'ym' : 'yf')) delete sim.hair;
  }
  return true;
}

// Which sim gives: explicit roles first, then who has a penis (or wears a strap-on).
function giverOf(app, p) {
  const role = s => (app && app.roleOf ? app.roleOf(s) : (s.role || (hasPenisFrame(s.frame) ? 'giver' : 'receiver')));
  return p.sims.find(s => role(s) === 'giver') || p.sims.find(s => hasPenisFrame(s.frame) || s.strapon) || null;
}

// The act follows the bodies: a man receiving can't have vaginal sex (it becomes anal), nor be licked there.
function actFor(p, receiverFrame) {
  if (receiverFrame === 'yf') return;
  if (p.category === 'VAGINAL') p.category = 'ANAL';
  const tags = new Set(p.tags || []);
  if (tags.has('CUNNILINGUS')) { tags.delete('CUNNILINGUS'); tags.add('BLOWJOB'); }
  if (p.category === 'ANAL' || tags.has('VAGINAL')) { tags.delete('VAGINAL'); tags.add('ANAL'); }
  p.tags = [...tags];
  if (p.act === 'VAGINAL') p.act = 'ANAL';
}

export const PAIRINGS = {
  ff: { label: 'Two women', short: 'F/F', frames: ['yf', 'yf'] },
  mm: { label: 'Two men', short: 'M/M', frames: ['ym', 'ym'] },
  fm: { label: 'A woman and a man', short: 'F/M', frames: ['yf', 'ym'] },
};

// What a version spec does, in words (and the name suffix).
export function specLabel(p, spec) {
  const sim = spec.simId && p.sims.find(s => s.id === spec.simId);
  if (spec.kind === 'height') return { suffix: `${sim ? sim.label + ' ' : ''}${HEIGHTS[spec.size].label}`, text: `${sim ? sim.label : 'One sim'} ${HEIGHTS[spec.size].label} (${Math.round(Math.abs(HEIGHTS[spec.size].scale - 1) * 100)}%)` };
  if (spec.kind === 'tray') return { suffix: `${spec.tray.name || 'Tray sim'}'s body`, text: `${sim ? sim.label : 'One sim'} with ${spec.tray.name || 'a Tray sim'}'s body` };
  if (spec.kind === 'pair') return { suffix: PAIRINGS[spec.pair].short, text: PAIRINGS[spec.pair].label };
  if (spec.kind === 'swap') return { suffix: 'roles swapped', text: 'The roles swapped' };
  return { suffix: 'version', text: 'A version' };
}

// Make one version of a project (the source is never changed). spec:
//   {kind: 'height', simId, size: 'short'|'tall'}  {kind: 'tray', simId, tray: {id, index, name, frame}}
//   {kind: 'pair', pair: 'ff'|'mm'|'fm'}  {kind: 'swap'}
// -> {project, report: {hips, limbs, heads, worst, missed, issues, deep, text}}
export async function makeVersion(app, source, spec, { name = null } = {}) {
  const lab = specLabel(source, spec);
  const p = newVersionOf(source, { name: name || await freeName(app, `${source.name} (${lab.suffix})`), label: lab.suffix, kind: spec.kind });
  const info = p.furniture && p.furniture !== 'floor' ? await app._furnitureInfo(p.furniture) : null;
  // the contacts on the bodies as they are
  const wb0 = await workbench(app, clone(source));
  let contacts;
  try { contacts = captureContacts(wb0, info); } finally { wb0.dispose(); }
  const remap = {};
  let movers = null;
  if (spec.kind === 'height') {
    const sim = p.sims.find(s => s.id === spec.simId) || p.sims[0];
    const wb = await workbench(app, p);
    try { scaleBody(wb, sim, HEIGHTS[spec.size].scale, info); } finally { wb.dispose(); }
    p.versionOf.scale = { sim: sim.id, by: HEIGHTS[spec.size].scale };
    movers = new Set([sim.id]);
  } else if (spec.kind === 'tray') {
    const sim = p.sims.find(s => s.id === spec.simId) || p.sims[0];
    const t = spec.tray;
    if (t.frame && t.frame !== sim.frame) reBody(sim, t.frame, p, giverOf(app, p) === sim);
    sim.tray = { id: t.id, index: t.index, name: t.name };
    movers = new Set([sim.id]);
    const first = (t.name || '').split(' ')[0];
    if (first) sim.label = first.replace(/^./, c => c.toUpperCase());
    try { const r = await api.traySim(t.id, t.index); if (r && r.tone) sim.tone = r.tone; } catch { /* its skin is loaded later */ }
  } else if (spec.kind === 'pair') {
    const giver = giverOf(app, p), others = p.sims.filter(s => s !== giver);
    const frames = PAIRINGS[spec.pair].frames;
    // the giver takes the pairing's second body (the man in F/M), the others the first
    if (giver) { giver.role = giver.role || 'giver'; reBody(giver, frames[1], p, true); }
    for (const s of others) { if (!s.role && giver) s.role = 'receiver'; reBody(s, frames[0], p, false); }
    const recv = others[0];
    if (recv) actFor(p, recv.frame);
  } else if (spec.kind === 'swap') {
    // the two sims trade bodies (the motion stays: whoever does the giving motion now has the other body)
    const giver = giverOf(app, p), recv = p.sims.find(s => s !== giver);
    if (!giver || !recv) throw new Error('Swapping roles needs two sims.');
    const bodyOf = s => ({ frame: s.frame, gender: s.gender, tray: s.tray, tone: s.tone, skin: s.skin, color: s.color, label: s.label, hair: s.hair, voice: s.voice, voicePitch: s.voicePitch, body: s.body });
    const a = bodyOf(giver), b = bodyOf(recv);
    const put = (s, x) => { for (const [k, val] of Object.entries(x)) { if (val === undefined) delete s[k]; else s[k] = clone(val); } };
    put(giver, b); put(recv, a);
    giver.role = 'giver'; recv.role = 'receiver';
    // voices follow the body: each sim's voice lines go with its body
    const gs = (giver.sounds || []).filter(x => x.kind === 'voice'), rs = (recv.sounds || []).filter(x => x.kind === 'voice');
    giver.sounds = [...(giver.sounds || []).filter(x => x.kind !== 'voice'), ...rs];
    recv.sounds = [...(recv.sounds || []).filter(x => x.kind !== 'voice'), ...gs];
    if (!hasPenisFrame(giver.frame)) { giver.strapon = true; giver.strapView = true; } else { delete giver.strapView; }
    if (hasPenisFrame(recv.frame)) { delete recv.strapon; delete recv.strapView; }
    actFor(p, recv.frame);
  }
  for (const s of p.sims) delete s._needVoices;
  // put the contacts back on the new bodies, then look for clipping
  const wb = await workbench(app, p);
  let stats, issues = [];
  try {
    stats = applyContacts(wb, contacts, { remap, movers });
    issues = scanClipping(wb, { step: 2, info });
  } finally { wb.dispose(); }
  const deep = issues.filter(i => i.depth > 0.04);
  return { project: p, report: { ...stats, issues: issues.length, deep: deep.length, deepest: issues.reduce((a, i) => Math.max(a, i.depth), 0), text: lab.text } };
}

// Make several versions and save each as its own animation. -> [{project, report, saved}]
export async function makeVersions(app, specs, { save = true, onProgress = null } = {}) {
  const source = clone(app.store.project);
  const out = [];
  const used = new Set();
  for (let i = 0; i < specs.length; i++) {
    if (onProgress) try { onProgress(i, specs.length, specLabel(source, specs[i]).text); } catch { /* the card is gone */ }
    let name = await freeName(app, `${source.name} (${specLabel(source, specs[i]).suffix})`);
    while (used.has(name.toLowerCase())) name = await freeName(app, name + ' 2');
    used.add(name.toLowerCase());
    const r = await makeVersion(app, source, specs[i], { name });
    let saved = null;
    if (save) {
      try { const res = await api.saveProject(r.project); saved = (res && (res.file || res.saved)) || r.project.name; if (res && res.name && res.name !== r.project.name) r.project.name = res.name; }
      catch (err) { r.report.error = err.message; }
    }
    out.push({ ...r, saved });
  }
  if (onProgress) try { onProgress(specs.length, specs.length, ''); } catch { /* the card is gone */ }
  return out;
}

// Bake a version (or any saved animation) for the game, with strap-ons counted for the openings.
export async function bakeProject(app, p) {
  const wb = await workbench(app, clone(p));
  try { return app.bake(wb.store.project, { pipeline: wb.pipeline, views: wb.simViews }); } finally { wb.dispose(); }
}

// ---------------------------------------------------------------- the strap-on (preview)
// A simple harnessed strap-on along the penis bones of a body without a penis. It follows the bones' aim, and the
// view counts it as a penis, so the partner's opening opens around it (the openings measure the penis bones).
const _strapMat = () => new THREE.MeshStandardMaterial({ color: 0x3b2552, roughness: 0.35, metalness: 0.05 });
export function attachStrap(v) {
  if (v._strap || !v.bone('b__Penis_Base') || !v.bone('b__Penis_Tip')) return false;
  v._ownPenis = !!v.hasPenis;
  if (v._ownPenis) return false;
  const base = v.bone('b__Penis_Base');
  // the bones' line at rest, in the base bone's frame
  v.group.updateMatrixWorld(true);
  const bw = new THREE.Vector3().setFromMatrixPosition(base.matrixWorld);
  const tw = v.worldPos('b__Penis_Tip');
  const len = Math.max(0.1, Math.min(0.2, tw.distanceTo(bw) + 0.03));
  const dirL = tw.clone().applyMatrix4(base.matrixWorld.clone().invert()).normalize();
  const g = new THREE.Group();
  g.name = 'strap-on';
  const mat = _strapMat();
  const shaft = new THREE.Mesh(new THREE.CapsuleGeometry(0.017, len - 0.034, 6, 16), mat);
  shaft.position.y = len / 2 - 0.005;
  const plate = new THREE.Mesh(new THREE.CylinderGeometry(0.034, 0.03, 0.012, 20), mat);
  plate.position.y = 0;
  g.add(shaft, plate);
  g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dirL);
  g.traverse(o => { if (o.isMesh) { o.castShadow = true; o.userData.role = 'strapon'; } });
  base.add(g);
  v._strap = g;
  v.hasPenis = true;
  return true;
}
export function detachStrap(v) {
  if (!v._strap) return false;
  v._strap.traverse(o => { if (o.isMesh) { o.geometry.dispose(); o.material.dispose(); } });
  v._strap.removeFromParent();
  v._strap = null;
  v.hasPenis = !!v._ownPenis;
  return true;
}

export { wrap, UP };

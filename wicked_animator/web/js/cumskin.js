// Cum on the skin (spec_game 5): when the playhead passes a Cum moment, that part of the sim gets WickedWhims' own
// cum texture - the same picture the game paints (its CAS parts, cropped by the server: /api/cum_layers).
//
// Like in the game (F5, F10): every loop adds the moment's level again, up to 3, and it stays on the sim - stopping or
// scrubbing shows the first loop. WickedWhims only shows cum when someone in the act has a penis.
import * as THREE from 'three';

let layers = null;                 // {TYPE: [{level, inst, rect}]} | null (not asked yet) | {} (none)
let loading = null;
const images = new Map();          // inst -> HTMLImageElement (decoded) | Promise
const state = new WeakMap();       // view -> {key, canvas, tex, base}

export const cumTexUrl = inst => '/api/cum_tex?inst=' + encodeURIComponent(inst);

// Fetch the list once (and later the pictures for the types that have moments).
export function load() {
  if (layers) return Promise.resolve(layers);
  if (!loading) {
    loading = fetch('/api/cum_layers').then(r => (r.ok ? r.json() : {})).catch(() => ({}))
      .then(x => { layers = x && typeof x === 'object' ? x : {}; return layers; });
  }
  return loading;
}
export function loaded() { return layers; }

function image(inst) {
  const hit = images.get(inst);
  if (hit) return hit instanceof Promise ? null : hit;
  const img = new Image();
  const p = new Promise(res => {
    img.onload = () => { images.set(inst, img); res(img); };
    img.onerror = () => { images.set(inst, null); res(null); };
  });
  images.set(inst, p);
  img.src = cumTexUrl(inst);
  return null;
}
function imageReady(inst) { const hit = images.get(inst); return hit instanceof Promise ? hit : Promise.resolve(hit || null); }

// Load these layers' pictures; resolves when all are there (or failed).
export function ready(list) { for (const l of list || []) image(l.inst); return Promise.all((list || []).map(l => imageReady(l.inst))); }

// Start loading the pictures a project will need (every level of every type it has a Cum moment for).
export function preload(project) {
  if (!layers) return;
  const types = new Set((project.events || []).filter(e => e.type === 'CUM').map(e => e.cum));
  if (types.has('VAGINA')) types.add('BUTT');
  for (const t of types) for (const x of layers[t] || []) image(x.inst);
}

const hasPenis = (app, s) => s.frame === 'ym' || s.frame === 'yf_futa' || !!(app.simViews && app.simViews.get(s.id) && app.simViews.get(s.id).hasPenis);

// {TYPE: level} a sim shows at this frame in loop number `pass` (0 = the first loop). Each loop adds all of its Cum
// moments again; a moment counts in this loop once the playhead passed it. Capped at 3 per type (WickedWhims shows
// parts[min(3, level) - 1]). VAGINA on a sim with a penis shows on the butt (like in the game). Empty when nobody has
// a penis, or when "Show cum" is off. opts.skipped(ev) leaves out moments skipped because of a condom.
export function activeCum(app, sim, frame, pass = 0, { on = true, skipped = null } = {}) {
  const out = {};
  if (!on || !sim) return out;
  const p = app.store.project;
  if (!p.sims.some(s => hasPenis(app, s))) return out;
  const penis = hasPenis(app, sim);
  const all = (p.events || []).filter(e => e.type === 'CUM' && e.sim === sim.id && e.cum && !(skipped && skipped(e)));
  const f = Math.round(frame);
  for (const e of all) {
    const t = e.cum === 'VAGINA' && penis ? 'BUTT' : e.cum;
    const lv = Math.max(1, Math.min(3, Math.round(e.level || 1)));
    out[t] = (out[t] || 0) + pass * lv + (e.frame <= f ? lv : 0);
  }
  for (const t of Object.keys(out)) { out[t] = Math.min(3, out[t]); if (out[t] <= 0) delete out[t]; }
  return out;
}

// The layers to paint for an active set: [{type, level, inst, rect}] (the level's own picture, not a pile).
export function layersFor(active) {
  const out = [];
  if (!layers) return out;
  for (const [t, lv] of Object.entries(active || {})) {
    const list = layers[t] || [];
    const x = list.find(l => l.level === lv) || list[Math.min(list.length, lv) - 1];
    if (x) out.push({ type: t, level: lv, inst: x.inst, rect: x.rect });
  }
  return out;
}

// Paint the base skin and the cum layers on a canvas (the size of the base picture; 1024x2048 normally).
export function compose(baseImage, list, canvas = document.createElement('canvas')) {
  const W = baseImage.naturalWidth || baseImage.width, H = baseImage.naturalHeight || baseImage.height;
  if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
  const g = canvas.getContext('2d');
  g.globalCompositeOperation = 'copy';
  g.drawImage(baseImage, 0, 0, W, H);
  g.globalCompositeOperation = 'source-over';
  for (const l of list) {
    const img = images.get(l.inst);
    if (!img || img instanceof Promise) continue;
    const [u0, v0, u1, v1] = l.rect;
    g.drawImage(img, u0 * W, v0 * H, (u1 - u0) * W, (v1 - v0) * H);
  }
  return canvas;
}

// Put the right skin on one sim's view: its own skin, or its skin with cum. Nothing happens when nothing changed.
export function apply(app, sim, view, active) {
  if (!view || !sim) return;
  let st = state.get(view);
  const key = JSON.stringify(active || {});
  if (st && st.key === key) return;
  const empty = !active || !Object.keys(active).length;
  if (empty) {
    if (!st) return;                                  // it never had any: the shared skin is on already
    if (st.tex) { st.tex.dispose(); st.tex = null; }
    st.key = key;
    app.applySkin(view, sim.frame, view.toneKey !== undefined ? view.toneKey : (sim.tone || ''));
    return;
  }
  if (!layers) { load().then(() => app.applyPoses && app.applyPoses(false)); return; }
  const list = layersFor(active);
  // the shared skin picture (the texture every sim of this body and tone uses)
  const map = view.material && view.material.map;
  const base = st && st.base && st.base.image ? st.base : (map && map !== (st && st.tex) ? map : null);
  const img = base && base.image;
  // (a picture that failed to load is left out, never waited for again)
  const missing = list.filter(l => { const x = images.get(l.inst); return x === undefined || x instanceof Promise; });
  if (!img || !(img.complete !== false && (img.naturalWidth || img.width)) || missing.length) {
    // not everything is there yet: paint as soon as it is (the stage keeps drawing, but nothing changes the key)
    if (!st) state.set(view, st = { key: null, canvas: null, tex: null, base: base || null });
    st.key = null;
    if (!st.waiting) {
      st.waiting = true;
      for (const l of missing) image(l.inst);
      const skinWait = base ? Promise.resolve(true) : app.skinReady(sim.frame, view.toneKey !== undefined ? view.toneKey : (sim.tone || ''));
      Promise.all([skinWait, ...missing.map(l => imageReady(l.inst))]).then(([skin]) => {
        // no skin picture at all (it failed to load): nothing to paint on, so the sim keeps its plain look
        if (skin === false && !(view.material && view.material.map)) { st.key = key; return; }
        st.waiting = false;
        if (app.applyPoses && !app.playing) app.applyPoses(false);
      });
    }
    return;
  }
  if (!st) state.set(view, st = { key: null, canvas: null, tex: null, base });
  st.base = base;
  st.canvas = compose(img, list, st.canvas || document.createElement('canvas'));
  if (!st.tex) {
    st.tex = new THREE.CanvasTexture(st.canvas);
    st.tex.flipY = false;
    st.tex.colorSpace = THREE.SRGBColorSpace;
    st.tex.anisotropy = 8;
  }
  st.tex.needsUpdate = true;
  st.key = key;
  view.setTexture(st.tex);
}

// What a view shows now ('' = its plain skin), for checks.
export function shownKey(view) { const st = view && state.get(view); return st && st.tex && view.material.map === st.tex ? st.key : ''; }
export function canvasOf(view) { const st = view && state.get(view); return st ? st.canvas : null; }
// A view was rebuilt or the skin tone changed: start again from its new skin.
export function forget(view) { const st = view && state.get(view); if (st && st.tex) st.tex.dispose(); if (view) state.delete(view); }

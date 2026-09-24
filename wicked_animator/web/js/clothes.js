// Clothes in the preview, to check clipping with outfits: a Tray sim's own outfits (by category), or a few basic
// EA outfits for the plain bodies. The CAS parts come from the game and Mods like hair does (backend clothes.py),
// skinned to the skeleton in the view. Preview only: clothes never go into the exported animation.
//
// A sim's choice is sim.clothes: none (undefined / null / false, as before), {outfit: 'EVERYDAY:0'} (a Tray sim's
// own outfit) or {basic: 'underwear'}. Undress moments on the timeline hide the parts they take off while the
// playhead is past them; app.clothesHidden hides every sim's clothes.
import * as THREE from 'three';

// what an undress moment takes off (WickedWhims' naked types -> the part kinds clothes.py gives)
const BODY = ['full', 'top', 'bottom', 'tights', 'socks', 'shoes'];
export const UNDRESS = {
  TOP: ['top', 'full'], TOP_UNDERWEAR: ['top', 'full'],
  BOTTOM: ['bottom', 'full', 'tights'], BOTTOM_UNDERWEAR: ['bottom', 'full', 'tights'],
  SHOES: ['shoes', 'socks'],
  ALL: [...BODY, 'hat', 'accessory'], FORCE_ALL: [...BODY, 'hat', 'accessory'],
};

// how a part without a CAS part name is called in the Body step's note
const KIND_LABEL = { full: 'outfit', top: 'top', bottom: 'bottom', tights: 'tights', socks: 'socks', shoes: 'shoes', hat: 'hat', accessory: 'accessory' };
const partName = p => p.name || KIND_LABEL[p.kind] || 'a part';

const json = async url => {
  const r = await fetch(url);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(body.error || ('HTTP ' + r.status)), { status: r.status });
  return body;
};
const q = o => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString();

// The part kinds undress moments have taken off `simId` by `frame` (the loop starts dressed again).
export function hiddenKinds(events, simId, frame) {
  const out = new Set();
  for (const e of events || []) {
    if (!e || e.type !== 'UNDRESS' || e.sim !== simId || !(e.frame <= frame)) continue;
    for (const k of UNDRESS[e.naked] || UNDRESS.ALL) out.add(k);
  }
  return out;
}

// ---------------------------------------------------------------- what a sim wears
// The body the clothes sit on: a trial Tray body shown for a while, else the sim's own Tray body (null: a plain body).
function shapeOf(app, s) {
  const t = app.trial && app.trial.get(s.id);
  if (t && t.uid === app.store.project.uid && t.opt && t.opt.kind === 'tray') return { shape_tray: t.opt.tray, shape_index: t.opt.index };
  return s.tray && s.tray.id ? { shape_tray: s.tray.id, shape_index: s.tray.index || 0 } : {};
}

// -> {list: {kind, ...}, pick, shape} or null (no clothes)
export function clothesSpecOf(app, s) {
  const c = s && s.clothes;
  if (!c || typeof c !== 'object') return null;
  if (c.outfit && s.tray && s.tray.id) return { list: { kind: 'tray', tray: s.tray.id, index: s.tray.index || 0 }, pick: c.outfit, shape: shapeOf(app, s) };
  if (c.basic) return { list: { kind: 'basic', frame: s.frame === 'ym' ? 'ym' : 'yf' }, pick: c.basic, shape: shapeOf(app, s) };
  return null;
}
const listKey = l => (l.kind === 'tray' ? `t:${l.tray}:${l.index}` : `b:${l.frame}`);
export const specKey = sp => (sp ? `${listKey(sp.list)}|${sp.pick}|${sp.shape.shape_tray || ''}:${sp.shape.shape_index ?? ''}` : '');

// The outfits a sim can wear (one request per Tray sim / body for the session): [{key, label, parts}]
export function outfitList(app, list) {
  app._clothesLists = app._clothesLists || new Map();
  const key = listKey(list);
  if (!app._clothesLists.has(key)) {
    const p = (list.kind === 'tray'
      ? json('/api/clothes_outfits?' + q({ tray: list.tray, index: list.index })).then(d => ({ items: d.outfits || [], current: d.current || null, name: d.name || '' }))
      : json('/api/clothes_basic?' + q({ frame: list.frame })).then(d => ({ items: (d.items || []).map(o => ({ ...o, key: o.id })), current: null })))
      .catch(err => { app._clothesLists.delete(key); throw err; });
    app._clothesLists.set(key, p);
  }
  return app._clothesLists.get(key);
}

const _texLoader = new THREE.TextureLoader();
// one request per part (and body shape) for the session: {data, texture}
function fetchPart(app, casp, shape) {
  app._clothesParts = app._clothesParts || new Map();
  const key = `${casp}@${shape.shape_tray || ''}:${shape.shape_index ?? ''}`;
  if (!app._clothesParts.has(key)) {
    const p = json('/api/clothes_part?' + q({ casp, ...shape })).then(data => {
      if (!data || !data.meshes || !data.meshes.length || !data.texture) return { data, texture: null };
      return new Promise(res => {
        _texLoader.load('/api/clothes_tex?file=' + encodeURIComponent(data.texture), tex => {
          tex.flipY = false; tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
          res({ data, texture: tex });
        }, undefined, () => res({ data, texture: null }));
      });
    }).catch(err => { app._clothesParts.delete(key); return { data: { casp, meshes: [], error: err.message }, texture: null }; });
    app._clothesParts.set(key, p);
  }
  return app._clothesParts.get(key);
}

// Put a sim's clothes on its view (after the view is made, and after a change). Stale answers are dropped.
// -> the number of parts shown. v.clothesInfo tells the Body step what happened: {label, shown, missing, painted, error}
export async function loadClothes(app, v, s) {
  const spec = clothesSpecOf(app, s), key = specKey(spec);
  if (v.clothesKey === key) return v.clothesInfo ? v.clothesInfo.shown : 0;
  v.clothesKey = key;
  if (!spec) { v.removeParts('clothes'); v.clothesInfo = null; return 0; }
  v.clothesInfo = { loading: true, shown: 0, missing: [], painted: [] };
  const stale = () => v.clothesKey !== key || app.simViews.get(s.id) !== v;
  let outfit;
  try {
    const list = await outfitList(app, spec.list);
    outfit = list.items.find(o => o.key === spec.pick) || null;
  } catch (err) {
    if (!stale()) { v.removeParts('clothes'); v.clothesInfo = { error: err.message, shown: 0, missing: [], painted: [] }; }
    return 0;
  }
  if (stale()) return 0;
  if (!outfit) { v.removeParts('clothes'); v.clothesInfo = { error: 'That outfit is not there any more.', shown: 0, missing: [], painted: [] }; return 0; }
  const parts = (outfit.parts || []).filter(p => p.origin !== null);             // origin null: not installed
  const results = await Promise.all(parts.map(p => fetchPart(app, p.casp, spec.shape)));
  if (stale()) return 0;
  v.removeParts('clothes');
  const info = { label: outfit.label, shown: 0, missing: [], painted: [] };
  for (const p of outfit.parts || []) if (p.origin === null) info.missing.push(partName(p));
  results.forEach((r, i) => {
    const p = parts[i], d = r && r.data;
    if (!d || d.origin === null || d.error) { info.missing.push(partName(p)); return; }
    if (!d.meshes || !d.meshes.length) { if (d.painted) info.painted.push(d.name || partName(p)); return; }
    const before = (v.parts || []).length;
    v.addPart(d, r.texture, { role: 'clothes', soft: false, offset: 1, color: '#8a8fa3', info: { kind: d.kind || p.kind, casp: d.casp } });
    if ((v.parts || []).length > before) info.shown++;
  });
  v.clothesInfo = info;
  applyVisibility(app);
  return info.shown;
}

export function reloadClothes(app, simId) {
  const s = app.store.sim(simId), v = s && app.simViews.get(simId);
  if (!v) return Promise.resolve(0);
  v.clothesKey = undefined;
  return loadClothes(app, v, s);
}

// Show or hide each clothes mesh: everything off with app.clothesHidden, else what the undress moments took off by
// now. Cheap (runs after every pose update).
export function applyVisibility(app, frame = app.store.frame) {
  const p = app.store.project;
  for (const s of p.sims) {
    const v = app.simViews.get(s.id);
    if (!v || !v.parts || !v.parts.length) continue;
    const off = app.clothesHidden ? null : hiddenKinds(p.events, s.id, Math.floor(frame));
    for (const m of v.parts) if (m.userData.role === 'clothes') m.visible = !!off && !off.has(m.userData.kind);
  }
}

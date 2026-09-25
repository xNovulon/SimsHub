// Clothes in the preview, to check clipping with outfits: a Tray sim's own outfits (by category), or a few basic
// EA outfits for the plain bodies. The CAS parts come from the game and Mods like hair does (backend clothes.py),
// skinned to the skeleton in the view. Preview only: clothes never go into the exported animation.
//
// A sim's choice is sim.clothes: none (undefined / null / false, as before), {outfit: 'EVERYDAY:0'} (a Tray sim's
// own outfit) or {basic: 'underwear'}, with off: [casp, ...] for the pieces taken off (the clothes remover). Undress moments on the timeline hide the parts they take off while the
// playhead is past them; app.clothesHidden hides every sim's clothes.
import * as THREE from 'three';

// what an undress moment takes off (WickedWhims' naked types -> the part kinds clothes.py gives)
const BODY = ['full', 'top', 'bottom', 'tights', 'socks', 'shoes'];
// the bare body piece a garment kind replaces (Sim.setCovered)
const COVERS = { full: ['top', 'bottom'], top: ['top'], bottom: ['bottom'], shoes: ['feet'] };
export const UNDRESS = {
  TOP: ['top', 'full'], TOP_UNDERWEAR: ['top', 'full'],
  BOTTOM: ['bottom', 'full', 'tights'], BOTTOM_UNDERWEAR: ['bottom', 'full', 'tights'],
  SHOES: ['shoes', 'socks'],
  ALL: [...BODY, 'hat', 'accessory'], FORCE_ALL: [...BODY, 'hat', 'accessory'],
};

// how a part without a CAS part name is called in the Body step's note
const KIND_LABEL = { full: 'outfit', top: 'top', bottom: 'bottom', tights: 'tights', socks: 'socks', shoes: 'shoes', hat: 'hat', accessory: 'accessory' };
const partName = p => p.name || KIND_LABEL[p.kind] || 'a part';

// What a piece is, in words (the clothes remover's list): body type -> label
const PIECE = {
  HAT: 'Hat', FULL_BODY: 'Outfit', UPPER_BODY: 'Top', LOWER_BODY: 'Bottom', SHOES: 'Shoes', TIGHTS: 'Tights', SOCKS: 'Socks',
  CUMMERBUND: 'Belt', EARRINGS: 'Earrings', GLASSES: 'Glasses', NECKLACE: 'Necklace', GLOVES: 'Gloves',
  WRIST_LEFT: 'Left bracelet', WRIST_RIGHT: 'Right bracelet', LIP_RING_LEFT: 'Lip piercing (left)', LIP_RING_RIGHT: 'Lip piercing (right)',
  NOSE_RING_LEFT: 'Nose piercing (left)', NOSE_RING_RIGHT: 'Nose piercing (right)', BROW_RING_LEFT: 'Brow piercing (left)',
  BROW_RING_RIGHT: 'Brow piercing (right)', INDEX_FINGER_LEFT: 'Ring (left index finger)', INDEX_FINGER_RIGHT: 'Ring (right index finger)',
  RING_FINGER_LEFT: 'Ring (left ring finger)', RING_FINGER_RIGHT: 'Ring (right ring finger)', MIDDLE_FINGER_LEFT: 'Ring (left middle finger)',
  MIDDLE_FINGER_RIGHT: 'Ring (right middle finger)', ATTACHMENT_BACK: 'On the back',
};
export const pieceLabel = p => PIECE[p.body_type_name] || KIND_LABEL[p.kind] || 'Piece';
// clothes (what "Take off clothes" removes) vs. accessories and hats (kept on unless taken off one by one)
export const isClothing = p => BODY.includes(p.kind);

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

// -> {list: {kind, ...}, pick, shape, off: [casp]} or null (no clothes)
export function clothesSpecOf(app, s) {
  const c = s && s.clothes;
  if (!c || typeof c !== 'object') return null;
  const off = Array.isArray(c.off) ? c.off : [];
  if (c.outfit && s.tray && s.tray.id) return { list: { kind: 'tray', tray: s.tray.id, index: s.tray.index || 0 }, pick: c.outfit, shape: shapeOf(app, s), off };
  if (c.basic) return { list: { kind: 'basic', frame: s.frame === 'ym' ? 'ym' : 'yf' }, pick: c.basic, shape: shapeOf(app, s), off };
  return null;
}
const listKey = l => (l.kind === 'tray' ? `t:${l.tray}:${l.index}` : `b:${l.frame}`);
export const specKey = sp => (sp ? `${listKey(sp.list)}|${sp.pick}|${sp.shape.shape_tray || ''}:${sp.shape.shape_index ?? ''}|${[...sp.off].sort().join(',')}` : '');

// The pieces a sim's chosen outfit has, each with on (still worn) -> {label, parts: [{casp, kind, body_type_name, name,
// origin, on}]} or null (wearing nothing)
export async function piecesOf(app, s) {
  const spec = clothesSpecOf(app, s);
  if (!spec) return null;
  const list = await outfitList(app, spec.list);
  const outfit = list.items.find(o => o.key === spec.pick);
  if (!outfit) return null;
  const off = new Set(spec.off);
  return { label: outfit.label, parts: (outfit.parts || []).map(p => ({ ...p, on: !off.has(p.casp) })) };
}

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
  if (!spec) { v.removeParts('clothes'); v.clothesInfo = null; if (v.setCovered) v.setCovered(null); return 0; }
  v.clothesInfo = { loading: true, shown: 0, missing: [], painted: [] };
  const stale = () => v.clothesKey !== key || app.simViews.get(s.id) !== v;
  let outfit;
  try {
    const list = await outfitList(app, spec.list);
    outfit = list.items.find(o => o.key === spec.pick) || null;
  } catch (err) {
    if (!stale()) { v.removeParts('clothes'); v.setCovered && v.setCovered(null); v.clothesInfo = { error: err.message, shown: 0, missing: [], painted: [] }; }
    return 0;
  }
  if (stale()) return 0;
  if (!outfit) { v.removeParts('clothes'); v.setCovered && v.setCovered(null); v.clothesInfo = { error: 'That outfit is not there any more.', shown: 0, missing: [], painted: [] }; return 0; }
  const off = new Set(spec.off);
  const parts = (outfit.parts || []).filter(p => p.origin !== null && !off.has(p.casp));   // origin null: not installed
  const results = await Promise.all(parts.map(p => fetchPart(app, p.casp, spec.shape)));
  if (stale()) return 0;
  v.removeParts('clothes');
  const info = { label: outfit.label, shown: 0, missing: [], painted: [] };
  for (const p of outfit.parts || []) if (p.origin === null && !off.has(p.casp)) info.missing.push(partName(p));
  results.forEach((r, i) => {
    const p = parts[i], d = r && r.data;
    if (!d || d.origin === null || d.error) { info.missing.push(partName(p)); return; }
    if (!d.meshes || !d.meshes.length) { if (d.painted) info.painted.push(d.name || partName(p)); return; }
    const before = (v.parts || []).length;
    v.addPart(d, r.texture, { role: 'clothes', soft: false, offset: 1, color: '#8a8fa3', info: { kind: d.kind || p.kind, casp: d.casp } });
    if ((v.parts || []).length > before) info.shown++;
  });
  v.clothesInfo = info;
  await paintOnSkin(app, v, s, results.map(r => r && r.texture).filter(Boolean), key);
  applyVisibility(app);
  return info.shown;
}

// As in the game, a garment is painted onto the sim's own skin picture: its texture is a see-through layer over the
// skin (the arms of a top, the neck of a dress are skin), so the garment pieces draw the skin with every garment on
// top of it, and the bare body under them is hidden (applyVisibility). Hats and accessories keep their own picture.
async function paintOnSkin(app, v, s, textures, key) {
  const worn = (v.parts || []).filter(m => m.userData.role === 'clothes' && BODY.includes(m.userData.kind));
  if (!worn.length) return;
  try { await app.skinReady(s.frame, v.toneKey !== undefined ? v.toneKey : (s.tone || '')); } catch { /* plain look below */ }
  if (v.clothesKey !== key || app.simViews.get(s.id) !== v) return;
  const skin = v.material && v.material.map && v.material.map.image;
  if (!skin || !(skin.naturalWidth || skin.width)) return;           // no skin picture: garments keep their own look
  const W = skin.naturalWidth || skin.width, H = skin.naturalHeight || skin.height;
  const canvas = document.createElement('canvas');
  canvas.width = W; canvas.height = H;
  const g = canvas.getContext('2d');
  g.drawImage(skin, 0, 0, W, H);
  // in the preview's order (outfit, top, bottom, tights, socks, shoes), each garment's layer over the skin
  const layers = worn.map(m => m.material.map).filter((t, i, a) => t && t.image && a.indexOf(t) === i);
  for (const t of layers) g.drawImage(t.image, 0, 0, W, H);
  const tex = new THREE.CanvasTexture(canvas);
  tex.flipY = false; tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  if (v._clothesSkin) v._clothesSkin.dispose();
  v._clothesSkin = tex;
  for (const m of worn) {
    m.material.map = tex;
    m.material.alphaTest = 0;            // the skin fills in what the garment leaves open
    m.material.needsUpdate = true;
  }
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
    if (!v) continue;
    if (!v.parts || !v.parts.length) { if (v.setCovered) v.setCovered(null); continue; }
    const off = app.clothesHidden ? null : hiddenKinds(p.events, s.id, Math.floor(frame));
    const covered = new Set();
    for (const m of v.parts) {
      if (m.userData.role !== 'clothes') continue;
      m.visible = !!off && !off.has(m.userData.kind);
      if (m.visible && m.material && m.material.alphaTest === 0) for (const r of COVERS[m.userData.kind] || []) covered.add(r);
    }
    if (v.setCovered) v.setCovered(covered);
  }
}

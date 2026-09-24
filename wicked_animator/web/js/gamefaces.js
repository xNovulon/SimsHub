// Game faces: about 135 real Sims expressions, read from the game's own animations at their strongest moment
// (GET /api/ea_faces - backend/eaclips.face_library, adult clips only). Picking one writes the face bones at this
// frame (key.faceBones, the hand-posed face channel), scaled from rest by Intensity; the face sliders still add on
// top, and blinking and talking keep going. A face-only key is made where the body has no key, so a face never
// bends the body's motion (spec_face_bones section 2, master_plan item 6).
import * as THREE from 'three';
import { h, icon, slider } from './ui.js';
import { FACE_SET } from './facekit.js';
import { restOf, sortKeys } from './animation.js';
import { faceThumbs, FaceThumbs } from './facethumbs.js';
import { $t } from './i18n.js';

// the groups the backend makes, in the order a creator of adult animations wants them
export const GROUPS = [
  ['all', $t('gamefaces.all')], ['mood', $t('gamefaces.moods')], ['pleasure', $t('gamefaces.pleasure_pain')], ['overlay', $t('gamefaces.expressions')], ['kiss', $t('gamefaces.kisses')],
  ['makeout', $t('gamefaces.make_outs')], ['woohoo', $t('gamefaces.woohoo')], ['laugh', $t('gamefaces.laughs')], ['react', $t('gamefaces.reactions')],
];
const GROUP_ORDER = Object.fromEntries(GROUPS.map(([id], i) => [id, i]));

// Adults only: the game's adult clip prefixes, never a child, teen, baby, pet or family clip (the backend's
// eaclips.adult + BAD list, checked again here so nothing else can ever reach the grid).
const ADULT = /^(a_|a2a_|a2o_)/i;
const BAD = /(child|toddler|infant|baby|babies|teen|kid|puberty|bassinet|crib|cat|dog|horse|pet|animalPen|crossAge|family|school|scout|dollhouse|toy|prom_|_prom|homework|parent)/i;
export function adultFace(f) {
  if (!f || typeof f !== 'object' || !f.bones) return false;
  const clip = String(f.clip || String(f.id || '').replace(/^ea:/, ''));
  return ADULT.test(clip) && !BAD.test(clip);
}

// A short, plain name for a tile (the full one is its tooltip): the game's bookkeeping words go.
const DROP = new Set(['seated', 'standing', 'longer', 'blend', 'pitch', 'shift', 'v', 't', 'nt', 'gs', 'soc', 'x', 'y', 'l', 'r',
  'temp', 'react', 'intimate', 'high', 'low', 'mid', 'first', 'loop', 'posture', 'ui', 'mood']);
export function shortLabel(f) {
  const words = String(f.label || '').split(/\s+/).filter(w => w && !DROP.has(w.toLowerCase()) && !/^\d+$/.test(w) && !/^\d+frame$/i.test(w));
  let s = words.join(' ');
  if (s.length > 26) s = s.slice(0, 25).replace(/\s+\S*$/, '') + '…';
  return s || f.label || 'Face';
}

// ---------------------------------------------------------------- loading
let _faces = null, _loading = null;
// -> {ready, faces, building?, done?, total?, error?}. Faces are kept once they are ready.
export function loadFaces({ fresh = false } = {}) {
  if (_faces && !fresh) return Promise.resolve({ ready: true, faces: _faces });
  if (_loading) return _loading;
  _loading = fetch('/api/ea_faces').then(r => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status))))
    .then(d => {
      if (d && d.ready && Array.isArray(d.faces)) {
        _faces = d.faces.filter(adultFace).map((f, i) => ({ ...f, short: shortLabel(f), fb: faceBonesOf(f), order: i }))
          .sort((a, b) => ((GROUP_ORDER[a.group] ?? 99) - (GROUP_ORDER[b.group] ?? 99)) || a.order - b.order);
        return { ready: true, faces: _faces };
      }
      return { ready: false, building: !!(d && d.building), done: (d && d.done) || 0, total: (d && d.total) || 0, faces: [] };
    })
    .catch(err => ({ ready: false, error: String((err && err.message) || err), faces: [] }))
    .finally(() => { _loading = null; });
  return _loading;
}
export function facesNow() { return _faces; }
export function faceById(id) { return (_faces || []).find(f => f.id === id) || null; }

// A game face as a key.faceBones {rot, pos} (the backend's {bone: {r, t}}), face bones only.
export function faceBonesOf(face) {
  const rot = {}, pos = {};
  for (const [n, e] of Object.entries((face && face.bones) || {})) {
    if (!FACE_SET.has(n) || !e) continue;
    if (Array.isArray(e.r) && e.r.length === 4) rot[n] = e.r.slice();
    if (Array.isArray(e.t) && e.t.length === 3) pos[n] = e.t.slice();
  }
  return { rot, pos };
}

// ---------------------------------------------------------------- intensity
const _qa = new THREE.Quaternion(), _qb = new THREE.Quaternion();
const same = (a, b) => a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) <= 1e-12);
// A face `t` of the way from rest (0 = rest, 1 = the face exactly): turns slerp, moves lerp. Bones exactly at rest
// are left out (absent = at rest), so Intensity 0 is an empty face.
export function scaleFaceBones(fb, t = 1) {
  const out = { rot: {}, pos: {} };
  t = Math.max(0, Math.min(1, +t || 0));
  if (!fb || t === 0) return out;
  for (const [n, q] of Object.entries(fb.rot || {})) {
    const r = restOf(n);
    if (!r) { if (t === 1) out.rot[n] = q.slice(); continue; }
    const v = t === 1 ? q.slice() : _qa.fromArray(r.r).slerp(_qb.fromArray(q), t).normalize().toArray();
    if (!same(v, r.r) && !same(v.map(x => -x), r.r)) out.rot[n] = v;
  }
  for (const [n, p] of Object.entries(fb.pos || {})) {
    const r = restOf(n);
    if (!r) { if (t === 1) out.pos[n] = p.slice(); continue; }
    const v = t === 1 ? p.slice() : [0, 1, 2].map(i => r.t[i] + (p[i] - r.t[i]) * t);
    if (!same(v, r.t)) out.pos[n] = v;
  }
  return out;
}

// ---------------------------------------------------------------- writing
// The key at this frame, or a new face-only key there (its body snapshot keeps old code that reads key.pose safe;
// the body's motion ignores it). The app's own helper when it has one.
export function faceKeyAt(app, sim, frame, { ease = null } = {}) {
  let key = sim.keys.find(k => k.frame === frame);
  if (key) return key;
  if (!ease && typeof app._faceKeyAt === 'function') return app._faceKeyAt(sim, frame);
  const v = app.simViews.get(sim.id);
  if (typeof app._base === 'function') app._base({ sim, v }, frame); else app.pipeline.base({ sim, v }, frame);
  const pose = typeof app._bodyPose === 'function' ? app._bodyPose(v) : v.getPose();
  key = { frame, ease: ease || (typeof app._defaultEase === 'function' ? app._defaultEase() : 'auto'), faceOnly: true, pose };
  sim.keys.push(key); sortKeys(sim.keys);
  if (app.timeline && app.timeline.flash) app.timeline.flash(sim.id, frame, 'add');
  if (app.emit) app.emit('keyed', { simId: sim.id, frame, kind: 'face' });
  return key;
}

// Which game face (and how strong) each written key.faceBones came from, so Intensity can be changed afterwards.
// Keyed on the faceBones object itself: once the face is posed by hand (a new object) it is simply forgotten.
const ORIGIN = new WeakMap();
export function originOf(fb) { return (fb && ORIGIN.get(fb)) || null; }

// app.setFaceBones(simId, fb, label, intensity): the face bones `fb` ({rot, pos}, full strength), `intensity` of
// the way from rest, become this frame's hand-posed face (a face-only key where the body has no key). The slider
// expression at this key is cleared, so the face shows as picked; sliders elsewhere still add on top.
// opts: {id} a game face id (remembered for Intensity), {checkpoint: false} (the caller made one), {quiet}.
export function setFaceBones(app, simId, fb, labelText = null, intensity = 1, opts = {}) {
  const sim = app.store.sim(simId);
  if (!sim || !app.simViews.get(simId)) return null;
  if (app.playing) app.setPlaying(false);
  if (opts.checkpoint !== false) app.store.checkpoint();
  const frame = Math.round(app.store.frame);
  const key = faceKeyAt(app, sim, frame);
  const scaled = scaleFaceBones(fb, intensity);
  key.faceBones = scaled;
  ORIGIN.set(scaled, { id: opts.id || null, label: labelText, full: fb, intensity: Math.max(0, Math.min(1, +intensity || 0)) });
  if (key.face && Object.values(key.face).some(x => Math.abs(x) > 1e-9)) key.face = {};
  // a pending (unkeyed) face on this frame would hide the new one
  const ov = app.pipeline.overrides.get(simId);
  if (ov && ov.frame === frame && ov.faceBones) delete ov.faceBones;
  if (opts.pickId) app._justPicked = opts.pickId;
  app.applyPoses(false);
  if (opts.live) { app.timeline.draw(); app.store.dirty = true; return key; }
  app.afterEdit();
  if (!opts.quiet && labelText) {
    const pct = intensity < 1 ? ` at ${Math.round(intensity * 100)}%` : '';
    import('./ui.js').then(m => m.toast($t('gamefaces.on_at_s', { labelText, pct, simLabel: sim.label, frame: (frame / (app.store.project.fps || 30)).toFixed(2) }), 'ok'));
  }
  return key;
}

// Change the Intensity of the game face at this frame (the one the current key holds). live: while dragging.
export function setIntensity(app, simId, t, { live = false } = {}) {
  const sim = app.store.sim(simId);
  const key = sim && sim.keys.find(k => k.frame === Math.round(app.store.frame));
  const o = key && originOf(key.faceBones);
  if (!o) return false;
  setFaceBones(app, simId, o.full, o.label, t, { id: o.id, checkpoint: false, live, quiet: true });
  return true;
}

// ---------------------------------------------------------------- hover preview
// While the pointer rests on a tile, the sim shows that face (nothing is written). Applied after every frame the
// app draws (hooks.afterApply), so it simply stops when the preview is cleared.
let _preview = null;
export function setPreview(app, simId, fb, el = null) {
  _preview = simId && fb ? { simId, fb, el } : null;
  if (app && !app.playing) app.applyPoses(false);
}
export function previewNow() { return _preview; }
export function applyPreview(app) {
  if (!_preview || app.playing) return;
  // the tile went away (the panel was redrawn) or the pointer left it without telling: the preview ends
  const el = _preview.el;
  if (el && (!el.isConnected || !el.matches(':hover'))) { _preview = null; return; }
  const v = app.simViews.get(_preview.simId);
  if (!v || typeof v.setFaceBones !== 'function') return;
  v.setFaceBones(_preview.fb);
}

// ---------------------------------------------------------------- the "Game faces" tab
let _poll = null;
const wantGame = app => app.step === 'face' && (app._faceTab || 'quick') === 'game';
function refreshSoon(app, ms) {
  if (_poll) return;
  _poll = setTimeout(() => {
    _poll = null;
    if (!wantGame(app)) return;
    loadFaces().then(r => { if (!wantGame(app)) return; if (r.ready) app.renderStep(); else refreshSoon(app, 2500); });
  }, ms);
}
let _thumbsHooked = false;
function hookThumbs(app) {
  if (_thumbsHooked) return;
  _thumbsHooked = true;
  faceThumbs(app).onReady((body, id, url) => {
    const sel = `img[data-gfimg="${CSS.escape(id)}"][data-body="${body}"]`;
    const imgs = new Set(document.querySelectorAll(sel));
    // the kept grid between two redraws of the panel is not in the page: it gets its pictures too
    if (app._gfGrid && app._gfGrid.el) for (const img of app._gfGrid.el.querySelectorAll(sel)) imgs.add(img);
    for (const img of imgs) { img.src = url; img.closest('.gf-pic')?.classList.add('ready'); }
  });
}
const matches = (f, q) => !q || q.toLowerCase().split(/\s+/).filter(Boolean).every(w => `${f.label} ${f.short} ${f.group_label} ${f.clip}`.toLowerCase().includes(w));

export function gameFacesPanel(app, sim) {
  const wrap = h('div', { class: 'gf' });
  const frame = Math.round(app.store.frame);
  const key = sim.keys.find(k => k.frame === frame);
  const origin = key && originOf(key.faceBones);
  if (app._gfAmount === undefined) app._gfAmount = 1;
  const amount = origin ? origin.intensity : app._gfAmount;
  wrap.append(slider({ label: origin ? $t('gamefaces.intensity', { originLabel: origin.label }) : $t('gamefaces.intensity_2'), min: 0, max: 1, step: 0.01, value: amount,
    title: origin ? $t('gamefaces.how_strong_game_face_on') : $t('gamefaces.how_strong_next_game_face'),
    fmt: v => Math.round(v * 100) + '%',
    onStart: () => { if (origin) app.store.checkpoint(); },
    onInput: (v, done) => { app._gfAmount = v; if (origin) setIntensity(app, sim.id, v, { live: !done }); } }));
  const faces = facesNow();
  if (!faces) {
    const note = h('div', { class: 'gf-note' }, h('span', { class: 'gf-spin' }), h('span', {}, $t('gamefaces.reading_game_s_faces')));
    const grid = h('div', { class: 'gf-grid loading' }, Array.from({ length: 9 }, () => h('div', { class: 'gf-tile skel' }, h('span', { class: 'gf-pic' }), h('span', { class: 'gf-name' }, ' '))));
    wrap.append(note, grid);
    loadFaces().then(r => {
      if (r.ready) { if (wantGame(app)) app.renderStep(); return; }
      if (r.building) {
        note.lastChild.textContent = r.total ? $t('gamefaces.reading_game_s_faces_first', { v: Math.round(100 * r.done / Math.max(1, r.total)) }) : $t('gamefaces.reading_game_s_faces_first_2');
        refreshSoon(app, 2500);
      } else {
        note.classList.add('bad');
        note.textContent = $t('gamefaces.game_s_faces_could_not');
        grid.remove();
      }
    });
    return wrap;
  }
  hookThumbs(app);
  const group = app._gfGroup || 'all';
  const counts = {};
  for (const f of faces) counts[f.group] = (counts[f.group] || 0) + 1;
  const chips = h('div', { class: 'gf-groups' }, GROUPS.filter(([id]) => id === 'all' || counts[id]).map(([id, text]) => h('button', {
    class: 'chip' + (group === id ? ' on' : ''), onclick: () => { app._gfGroup = id; app.renderStep(); } },
  text, h('span', { class: 'n' }, String(id === 'all' ? faces.length : counts[id])))));
  const search = h('input', { class: 'text gf-search', type: 'search', placeholder: $t('gamefaces.find_face_flirty_moan_kiss'), value: app._gfQuery || '', spellcheck: 'false' });
  const body = FaceThumbs.bodyOf(sim);
  // the grid is kept between redraws of the panel (fast, and it stays scrolled where it was); only the marks change
  const keyOf = () => `${sim.id}|${body}|${group}|${app._gfQuery || ''}|${faces.length}`;
  const kept = app._gfGrid && app._gfGrid.key === keyOf() ? app._gfGrid.el : null;
  const grid = kept || h('div', { class: 'gf-grid' });
  const fill = () => {
    app._gfGrid = { key: keyOf(), el: grid };
    grid.innerHTML = '';
    const list = faces.filter(f => (group === 'all' || f.group === group) && matches(f, app._gfQuery || ''));
    const thumbs = faceThumbs(app);
    for (const f of list) {
      const url = thumbs.get(body, f.id);
      const img = h('img', { alt: '', draggable: 'false', 'data-gfimg': f.id, 'data-body': body, src: url || null });
      const tile = h('button', { class: 'gf-tile',
        title: $t('gamefaces.from_game_animation', { fLabel: f.label, group_label: f.group_label, clip: f.clip }), 'data-gf': f.id,
        onclick: () => {
          setPreview(app, null);
          setFaceBones(app, sim.id, f.fb, f.short, app._gfAmount ?? 1, { id: f.id, pickId: 'gface:' + f.id });
        } },
      h('span', { class: 'gf-pic' + (url ? ' ready' : '') }, img), h('span', { class: 'gf-name' }, f.short));
      tile.addEventListener('pointerenter', () => setPreview(app, sim.id, scaleFaceBones(f.fb, app._gfAmount ?? 1), tile));
      tile.addEventListener('pointerleave', () => { if (previewNow() && previewNow().el === tile) setPreview(app, null); });
      grid.append(tile);
    }
    if (!list.length) grid.append(h('div', { class: 'hint' }, $t('gamefaces.no_game_face_matches')));
    // pictures: the ones in this list first
    thumbs.clear();
    thumbs.request(body, list.filter(f => !thumbs.get(body, f.id)));
  };
  const marks = () => {
    for (const t of grid.querySelectorAll('.gf-tile')) {
      t.classList.toggle('on', !!(origin && origin.id === t.dataset.gf));
      const pop = app._justPicked === 'gface:' + t.dataset.gf;
      if (t.classList.contains('pop')) t.classList.remove('pop');
      if (pop) { void t.offsetWidth; t.classList.add('pop'); }
    }
  };
  search.addEventListener('input', () => { app._gfQuery = search.value; fill(); marks(); });
  wrap.append(chips, h('div', { class: 'gf-find' }, icon('search'), search), grid);
  if (!kept) fill();
  marks();
  return wrap;
}

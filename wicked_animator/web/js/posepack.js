// "Export as a pose pack": every key becomes a pose for Andrew's Pose Player, laid out like a Sims 4 Studio pose pack
// (backend/posepack.py). Every sim in the scene shares one origin, so a couple lines up on one spot with no
// 0.7-unit trick. The app takes each pose's picture itself (64 x 64, like S4S) and writes the names in a string table.
//
// Adults only: Pose Player plays any pose on any sim, teens included - so a pose pack is NON-EXPLICIT ONLY. The lock
// here says why in one line (the server checks again and refuses the same things).
import * as THREE from 'three';
import { h, icon, modal, toast, emitWA } from './ui.js';
import { successHero, celebrateAt } from './fx.js';
import { api } from './api.js';
import { withStage, sphereOf, fitView, grab } from './promo.js';

// The server's lists (GET /api/posepack); this copy is used when the server is older than this page.
const LOCAL_RULES = {
  explicit_kinds: ['ANAL', 'CLIMAX', 'FOOTJOB', 'HANDJOB', 'ORALJOB', 'VAGINAL'],
  explicit_tags: `COWGIRL DOGGY MISSIONARY SPOONING PRONEBONE PILEDRIVER SIXTYNINE FACE_SITTING SPITROAST BLOWJOB DEEP_THROAT
    CUNNILINGUS RIMJOB LICKING FINGERING MASTURBATION TITJOB THIGHJOB BUTTJOB GROPING TITS_SUCKING TOES_SUCKING SPANKING CHOKING
    DOUBLE_PENETRATION FISTING PEEING FOREPLAY CLIMAX CUMSHOT CREAMPIE CUM_INSIDE CUM_IN_MOUTH BUKKAKE SQUIRT FEMDOM MALEDOM BDSM
    FORCED FREEUSE CUCK ONLOOKER SLEEPING WEIRD GROSS FUTA THREESOME FOURSOME ORGY GANGBANG HAREM TOY DILDO UNDER_COVERS VAGINAL
    ANAL ORALJOB HANDJOB FOOTJOB`.split(/\s+/).filter(Boolean),
  genital: ['b__Penis_Base', 'b__Penis_Base01', 'b__Penis_Mid', 'b__Penis_Mid01', 'b__Penis_Tip', 'b__Penis_Testicles',
    'b__Penis_L_Testicle', 'b__Penis_R_Testicle', 'b__Up_Vagina__', 'b__Low_Vagina__', 'b__Anus', 'b__L_Anus__', 'b__R_Anus__',
    'b__Up_Anus', 'b__Low_Anus'],
  max_poses: 200, icon: 64,
};
const OPENINGS = ['b__Up_Vagina__', 'b__Low_Vagina__', 'b__Anus', 'b__L_Anus__', 'b__R_Anus__', 'b__Up_Anus', 'b__Low_Anus'];
const KIND_WORD = { HANDJOB: 'Handjob', FOOTJOB: 'Footjob', ORALJOB: 'Oral', VAGINAL: 'Vaginal', ANAL: 'Anal', CLIMAX: 'Climax' };
const niceTag = t => { const s = String(t).replace(/_/g, ' ').toLowerCase(); return s.charAt(0).toUpperCase() + s.slice(1); };
const ICON = 64;

let rulesP = null;
export function loadRules() {
  rulesP = rulesP || fetch('/api/posepack').then(r => (r.ok ? r.json() : null)).catch(() => null).then(r => ({ ...LOCAL_RULES, ...(r || {}) }));
  return rulesP;
}

// Every frame with a body key (a face-only key is not a pose of its own), in order.
export function keyFrames(project) {
  const set = new Set();
  for (const s of project.sims) for (const k of s.keys || []) if (!k.faceOnly && k.frame < project.length) set.add(Math.max(0, Math.round(k.frame)));
  return [...set].sort((a, b) => a - b);
}

// Genital or opening bones this sim's keys pose away from its rest.
function keyedGenitals(app, s, R) {
  const v = app.simViews.get(s.id), out = new Set(), q = new THREE.Quaternion(), gen = new Set(R.genital);
  for (const k of s.keys || []) for (const src of [k.pose, k.faceBones]) {
    if (!src) continue;
    for (const [n, val] of Object.entries(src.rot || {})) {
      if (!gen.has(n)) continue;
      const rest = v && v.restByName[n];
      if (!rest || rest.quat.angleTo(q.fromArray(val)) > 1e-3) out.add(n);
    }
    for (const [n, val] of Object.entries(src.pos || {})) {
      if (!gen.has(n)) continue;
      const rest = v && v.restByName[n];
      if (!rest || Math.hypot(val[0] - rest.pos.x, val[1] - rest.pos.y, val[2] - rest.pos.z) > 0.0005) out.add(n);
    }
  }
  return [...out];
}

// Is an opening of this sim open (turned or moved away from its own rest) in one of the chosen poses?
function openIn(app, s, tracks, frames) {
  const v = app.simViews.get(s.id), q = new THREE.Quaternion();
  if (!v || !tracks) return false;
  for (const n of OPENINGS) {
    const tr = tracks[n], rest = v.restByName[n];
    if (!tr || !rest) continue;
    for (const f of frames) {
      const r = tr.r && tr.r[Math.min(f, tr.r.length - 1)], t = tr.t && tr.t[Math.min(f, tr.t.length - 1)];
      if (r && THREE.MathUtils.radToDeg(rest.quat.angleTo(q.fromArray(r))) > 4) return true;
      if (t && Math.hypot(t[0] - rest.pos.x, t[1] - rest.pos.y, t[2] - rest.pos.z) > 0.003) return true;
    }
  }
  return false;
}

// What the lock looks at (the server gets the same).
export function lockMeta(app, baked, frames, R = LOCAL_RULES) {
  const p = app.store.project;
  return {
    category: p.category, tags: [...(p.tags || [])],
    events: (p.events || []).map(e => e && e.type).filter(Boolean),
    actors: p.sims.map((s, i) => {
      const a = (baked && baked.actors && baked.actors[i]) || {};
      return { naked: a.naked || 'NONE', strapon: !!a.strapon, invisibleTeeth: !!a.invisibleTeeth, keyed: keyedGenitals(app, s, R),
        open: openIn(app, s, a.tracks, frames) };
    }),
  };
}

// Reasons this can't be a pose pack ([] = fine) - the server's wording (backend/posepack.lock).
export function lockReasons(meta, R = LOCAL_RULES) {
  const out = [], kinds = new Set(R.explicit_kinds), tags = new Set(R.explicit_tags), gen = new Set(R.genital);
  const kind = String(meta.category || '').toUpperCase();
  const acts = kinds.has(kind) ? [KIND_WORD[kind] || niceTag(kind)] : [];
  for (const t of meta.tags || []) { const u = String(t).toUpperCase(); if (tags.has(u) && !acts.includes(niceTag(u))) acts.push(niceTag(u)); }
  if (acts.length) out.push(`a WickedWhims act (${acts.slice(0, 3).join(', ')})${acts.length > 3 ? ' ...' : ''}`);
  if ((meta.events || []).length) out.push('WickedWhims moments (cum, undress, effects)');
  const actors = meta.actors || [];
  if (actors.some(a => String(a.naked || 'NONE').toUpperCase() !== 'NONE')) out.push('undressed sims');
  if (actors.some(a => a.strapon)) out.push('a strap-on');
  if (actors.some(a => a.invisibleTeeth)) out.push('a mouth opened by a penis');
  if (actors.some(a => (a.keyed || []).some(b => gen.has(b)))) out.push('genital or opening keys');
  if (actors.some(a => a.open)) out.push('an opening that is open');
  return out;
}

export function lockMessage(reasons) {
  const said = reasons.length === 1 ? reasons[0] : reasons.slice(0, -1).join(', ') + ' and ' + reasons[reasons.length - 1];
  return 'Pose packs are for non-explicit poses only - Pose Player can put a pose on any sim, teens too. This one has '
    + said + '. Explicit animations go to the game through WickedWhims (Send to game), which checks ages.';
}

// One frame of the baked tracks, genital bones left out (they stay at rest in a pose).
function sliceTracks(tracks, frame, R) {
  const out = {}, gen = new Set(R.genital);
  for (const [n, tr] of Object.entries(tracks || {})) {
    if (gen.has(n) || !tr) continue;
    const one = {};
    if (tr.t && tr.t.length) one.t = [tr.t[Math.min(frame, tr.t.length - 1)]];
    if (tr.r && tr.r.length) one.r = [tr.r[Math.min(frame, tr.r.length - 1)]];
    if (one.t || one.r) out[n] = one;
  }
  return out;
}

const b64 = bytes => { let s = ''; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)); return btoa(s); };
const rgbaOf = cv => { const d = cv.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, cv.width, cv.height).data; return { w: cv.width, h: cv.height, rgba: b64(new Uint8Array(d.buffer, d.byteOffset, d.byteLength)) }; };

// The pictures: a tile of the whole scene per frame (for the dialog) and a 64 x 64 picture per pose per sim (just
// that sim, framed on it), from the direction you look from now.
export async function takePictures(app, frames, { tile = 150 } = {}) {
  const p = app.store.project, dir = app.vp.viewDir().clone();
  if (dir.y < 0.12) dir.setY(0.12);
  const tiles = new Map(), icons = new Map();
  await withStage(app, async st => {
    const cv = document.createElement('canvas'); cv.width = cv.height = tile;
    const ic = document.createElement('canvas'); ic.width = ic.height = ICON;
    for (const f of frames) {
      st.only(null);
      const { crop } = fitView(app, sphereOf(app, [f], { margin: 0.22 }), dir, 1);
      st.pose(f); st.render();
      grab(app, crop, cv);
      tiles.set(f, cv.toDataURL('image/png'));
      for (const s of p.sims) {
        if (s.visible === false) continue;
        st.only([s.id]);
        const { crop: c2 } = fitView(app, sphereOf(app, [f], { simIds: [s.id], margin: 0.2 }), dir, 1);
        st.pose(f); st.render();
        grab(app, c2, ic);
        icons.set(`${f}|${s.id}`, rgbaOf(ic));
      }
      await new Promise(r => setTimeout(r, 0));
    }
    st.only(null);
  });
  return { tiles, icons };
}

// The request the server builds the pack from.
export function packRequest(app, baked, picks, { name, author, description = '', install = true, pictures = null, R = LOCAL_RULES } = {}) {
  const p = app.store.project, sims = p.sims.map((s, i) => ({ s, i })).filter(x => x.s.visible !== false);
  const frames = picks.map(x => x.frame);
  const poses = [];
  for (const pk of picks) {
    for (const { s, i } of sims) {
      const label = sims.length > 1 ? `${pk.label} - ${s.label}` : pk.label;
      poses.push({ label, sim: i, frame: pk.frame,
        description: sims.length > 1 ? `${s.label}'s part - put all ${sims.length} sims on the same spot` : '',
        tracks: sliceTracks(baked.actors[i] && baked.actors[i].tracks, pk.frame, R),
        icon: pictures ? pictures.icons.get(`${pk.frame}|${s.id}`) || null : null });
    }
  }
  // the pack's own picture: the whole scene of the first pose (else that pose's first sim)
  const packIcon = pictures ? pictures.packIcon || (picks.length && sims.length ? pictures.icons.get(`${picks[0].frame}|${sims[0].s.id}`) : null) || null : null;
  return { name, author, description, uid: p.uid, install, meta: lockMeta(app, baked, frames, R), poses, icon: packIcon };
}

// A 64 x 64 picture from a tile (the pack's own picture: the whole scene of the first pose).
function tileIcon(url) {
  return new Promise(res => {
    const img = new Image();
    img.onload = () => { const c = document.createElement('canvas'); c.width = c.height = ICON; const g = c.getContext('2d'); g.imageSmoothingQuality = 'high'; g.drawImage(img, 0, 0, ICON, ICON); res(rgbaOf(c)); };
    img.onerror = () => res(null);
    img.src = url;
  });
}

// ---------------------------------------------------------------- the dialog
export async function openPosePack(app) {
  const p = app.store.project;
  if (!p.sims.length) return toast('Add a sim first - each key of your sims becomes a pose.', 'err');
  if (app._stageBusy || app._recordingVideo) return toast('Wait a moment - the stage is busy.', 'err');
  const R = await loadRules();
  const frames = keyFrames(p).slice(0, Math.floor(R.max_poses / Math.max(1, p.sims.length)));
  if (!frames.length) return toast('Key a pose first (K) - each key becomes a pose.', 'err');
  let baked;
  try { baked = app.bake(); } catch (e) { return toast('Could not read the poses: ' + e.message, 'err'); }
  const picks = frames.map((f, i) => ({ frame: f, label: `Pose ${i + 1}`, on: true }));
  const reasons = lockReasons(lockMeta(app, baked, frames, R), R);
  const sims = p.sims.filter(s => s.visible !== false);

  const name = h('input', { class: 'text', value: p.name && !/^untitled/i.test(p.name) ? p.name : '', placeholder: 'e.g. Sofa cuddles' });
  const author = h('input', { class: 'text', value: p.author || '', placeholder: 'Your creator name' });
  const desc = h('input', { class: 'text', value: '', placeholder: 'e.g. 3 couple poses on the sofa' });
  let install = true;
  if (reasons.length) for (const el of [name, author, desc]) el.disabled = true;
  const count = h('div', { class: 'pp-count' });
  const grid = h('div', { class: 'pp-grid' });
  const lockLine = reasons.length
    ? h('div', { class: 'warn-box error pp-lock', role: 'alert' }, icon('pp-lock'), h('span', {}, lockMessage(reasons)))
    : h('div', { class: 'pp-ok' }, icon('check'), h('span', {}, 'Non-explicit poses - ready for Pose Player. (Pose Player can put a pose on any sim, teens too, so only non-explicit poses go in.)'));
  const drawCount = () => {
    const n = picks.filter(x => x.on).length;
    count.textContent = `${n} pose${n === 1 ? '' : 's'}${sims.length > 1 ? ` x ${sims.length} sims = ${n * sims.length} in Pose Player` : ''}`;
    const btn = dlg && dlg.footer.lastChild;
    if (btn) btn.disabled = !!reasons.length || !n;
  };
  picks.forEach((pk, i) => {
    const img = h('div', { class: 'pp-pic' }, reasons.length ? h('span', { class: 'pp-locked-pic' }, icon('pp-lock')) : h('span', { class: 'pp-skel' }));
    const cb = h('input', { type: 'checkbox', checked: true, disabled: !!reasons.length });
    const label = h('input', { class: 'text pp-name', value: pk.label, maxlength: 60, disabled: !!reasons.length, onchange: () => { pk.label = label.value.trim() || `Pose ${i + 1}`; } });
    const tile = h('label', { class: 'pp-tile on', style: { '--i': i }, 'data-frame': pk.frame }, img, h('div', { class: 'pp-meta' }, cb, label), h('small', {}, `frame ${pk.frame}`));
    cb.onchange = () => { pk.on = cb.checked; tile.classList.toggle('on', pk.on); drawCount(); };
    pk.el = img;
    grid.append(tile);
  });
  const body = h('div', { class: 'pp-wrap' + (reasons.length ? ' pp-locked' : '') },
    lockLine,
    h('div', { class: 'pp-cols' },
      h('div', {}, h('div', { class: 'section-title', style: { margin: '4px 0 8px' } }, 'Poses', count), grid),
      h('div', { class: 'pp-side' },
        h('label', { class: 'field' }, h('span', {}, 'Pack name (shown in Pose Player)'), name),
        h('label', { class: 'field' }, h('span', {}, 'Creator'), author),
        h('label', { class: 'field' }, h('span', {}, 'Description'), desc),
        h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Also put it in my game'), h('span', {}, 'Mods\\FitStudio\\PosePacks')),
          h('label', { class: 'switch' }, h('input', { type: 'checkbox', checked: true, onchange: e => { install = e.target.checked; } }), h('span'))),
        h('div', { class: 'pp-note' }, icon('pp-couple'), h('div', {}, h('b', {}, sims.length > 1 ? 'Couples line up by themselves' : 'One pose per key'),
          h('span', {}, sims.length > 1 ? `Every sim gets its own pose, and ${sims.length === 2 ? 'both' : 'all ' + sims.length} share one spot: put them on the same spot (Teleport Any Sim) and give each its pose - no 0.7 trick.` : 'Each key you picked becomes one pose, with its own little picture.'))),
        h('div', { class: 'hint' }, 'Needs Pose Player by Andrew in the game. You get a folder with the .package and a README.'))));
  const dlg = modal({
    title: 'Export as a pose pack', text: "For Andrew's Pose Player - each key becomes a pose, laid out like a Sims 4 Studio pose pack.", body, wide: true,
    buttons: [{ label: 'Cancel', kind: 'ghost' }, { label: 'Export pose pack', kind: 'primary', onClick: async () => {
      if (reasons.length) { toast(lockMessage(reasons), 'err'); return false; }
      const chosen = picks.filter(x => x.on);
      if (!chosen.length) { toast('Pick at least one pose.', 'err'); return false; }
      if (!name.value.trim()) { toast('Give the pose pack a name.', 'err'); name.focus(); return false; }
      const btn = dlg.footer.lastChild; btn.textContent = 'Packing...';
      try {
        await pictures;
        const req = packRequest(app, baked, chosen, { name: name.value.trim(), author: author.value.trim(), description: desc.value.trim(), install, pictures: pics, R });
        const r = await fetch('/api/posepack', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) });
        const res = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(res.error || r.statusText);
        showDone(app, res, req);
      } catch (e) { toast('Could not make the pose pack: ' + e.message, 'err'); btn.textContent = 'Export pose pack'; return false; }
    } }],
  });
  dlg.dialog.classList.add('pp-dialog');
  drawCount();
  setTimeout(() => {
    if (reasons.length) dlg.footer.firstChild.focus({ preventScroll: true });          // refused: Cancel, nothing to type
    else if (name.isConnected && !name.value) name.focus({ preventScroll: true });
  }, 50);
  // the pictures, taken a moment after the dialog shows
  let pics = null;
  // (none for a pose pack the lock refuses: there is nothing to pick)
  const pictures = reasons.length ? Promise.resolve(null) : new Promise(r => setTimeout(r, 60)).then(() => takePictures(app, frames)).then(async res => {
    pics = res;
    for (const pk of picks) {
      const url = res.tiles.get(pk.frame);
      if (url && pk.el) { pk.el.innerHTML = ''; pk.el.append(h('img', { src: url, alt: pk.label })); }
    }
    if (picks.length) pics.packIcon = await tileIcon(res.tiles.get(picks[0].frame));
    return res;
  }).catch(e => {
    console.error('pose pictures', e);
    pics = null;
    for (const pk of picks) if (pk.el) { pk.el.innerHTML = ''; pk.el.append(h('span', { class: 'pp-locked-pic' }, icon('pp-couple'))); }   // no endless shimmer
  });
  return dlg;
}

function showDone(app, res, req) {
  const hero = successHero();
  const n = res.poses || req.poses.length;
  const sims = new Set(req.poses.map(x => x.sim)).size, keys = Math.round(n / Math.max(1, sims));
  modal({
    title: 'Your pose pack is ready',
    body: h('div', {}, hero, h('h3', { class: 'hero-title' }, `"${res.title || req.name}" - ${sims > 1 ? `${keys} pose${keys === 1 ? '' : 's'} x ${sims} sims` : `${n} pose${n === 1 ? '' : 's'}`} for Pose Player`),
      h('div', { class: 'success' }, icon('check'), h('div', {}, h('b', {}, `${n} pose${n === 1 ? '' : 's'} · ${((res.bytes || 0) / 1024).toFixed(0)} KB`), h('div', { class: 'path' }, res.package || res.folder || ''))),
      res.installed ? h('div', { class: 'pp-installed' }, h('span', {}, 'Also in your game:'), h('div', { class: 'path' }, res.installed)) : null,
      h('ol', { class: 'pp-steps' },
        h('li', {}, 'Start the game with Pose Player by Andrew installed.'),
        h('li', {}, req.poses.some(x => x.sim > 0) ? 'Put the sims on the same spot (Teleport Any Sim), then click each sim and pick its part of the pose.' : 'Click your sim and pick a pose from the pack.'),
        h('li', {}, 'Share it: give people the .package from the folder.'))),
    buttons: [{ label: 'Open the folder', onClick: () => { if (res.folder) api.reveal(res.folder); return false; } }, { label: 'Done', kind: 'primary' }],
  });
  celebrateAt(hero, { delay: 480 });
  emitWA(app, 'exported', { result: res, kind: 'posepack' });
}

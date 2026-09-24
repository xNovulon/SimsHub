// Reference pictures and videos (spec_editing 12): drop a photo or a clip on the view (or use the picture button) and
// trace real motion. A reference shows either on the screen, over the 3D view (overlay), or standing in the scene
// (a board: in front, at the side or on the floor). Videos follow the timeline frame by frame, and play along.
// The files live next to the saved animations (saves\FitStudio\animator_refs\<uid>) - never in exports or bundles.
// Project data: project.refs[] (spec 2.7), plus `dir`, the animation id whose folder holds the file.
import * as THREE from 'three';
import { api } from './api.js';
import { h, icon, toast, slider, toggle, fillRange } from './ui.js';

const clone = x => JSON.parse(JSON.stringify(x));
const KINDS = { 'image/png': 'image', 'image/jpeg': 'image', 'image/webp': 'image', 'image/gif': 'image', 'video/mp4': 'video', 'video/webm': 'video' };
const MAX_BYTES = 400e6;
const uidRef = () => 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const wrap = (t, d) => (d > 0 ? ((t % d) + d) % d : Math.max(0, t));

export class References {
  constructor(app) {
    this.app = app;
    this.layer = document.getElementById('ref-layer');
    this.items = new Map();        // ref id -> {ref, el, media, mesh, tex, key}
    this.media = new Map();        // 'dir|file' -> Promise<{url, blob}> (fetched once, shown through an object URL)
    this.selectedId = null;
    this.hidden = false;
    this._sig = '';
    app.hooks.inspector.push((a, root) => this._card(root));
    // a click on a board in the scene selects it (interact's pickers, when that version of the app has them)
    const it = app.interact;
    if (it && Array.isArray(it.pickers)) it.pickers.push((e, kind) => this._pick(e, kind));
  }

  get project() { return this.app.store.project; }
  get list() { return this.project.refs || []; }
  get selected() { return this.list.find(r => r.id === this.selectedId) || null; }

  // Build the overlays and boards for project.refs (nothing happens when they did not change).
  load(project = this.project) {
    const sig = JSON.stringify(project.refs || []) + '|' + project.uid;
    if (sig === this._sig) return;
    this._sig = sig;
    const want = new Map((project.refs || []).filter(r => r && r.file && r.kind).map(r => [r.id, r]));
    for (const [id, it] of [...this.items]) if (!want.has(id)) this._drop(id, it);
    for (const [id, r] of want) {
      let it = this.items.get(id);
      const key = `${r.dir || project.uid}|${r.file}`;
      if (it && it.key !== key) { this._drop(id, it); it = null; }
      if (!it) it = this._make(r, key);
      it.ref = r;
      this._place(it);
    }
    if (this.selectedId && !want.has(this.selectedId)) this.selectedId = null;
    this.sync(this.app.store.frame, !!this.app.playing);
  }

  _url(key) {
    if (!this.media.has(key)) {
      const [dir, file] = key.split('|');
      this.media.set(key, fetch(api.refUrl(dir, file)).then(r => { if (!r.ok) throw new Error('missing'); return r.blob(); })
        .then(blob => ({ url: URL.createObjectURL(blob), blob })).catch(err => { this.media.delete(key); throw err; }));
    }
    return this.media.get(key);
  }

  _make(r, key) {
    const it = { ref: r, key, el: null, media: null, mesh: null, tex: null, ready: false };
    const el = r.kind === 'video' ? h('video', { muted: true, playsinline: true, preload: 'auto' }) : h('img', { alt: '', draggable: 'false' });
    if (r.kind === 'video') { el.muted = true; el.loop = false; }
    it.media = el;
    it.el = h('div', { class: 'ref-item', 'data-ref': r.id }, el);
    this.layer && this.layer.append(it.el);
    this.items.set(r.id, it);
    this._url(key).then(({ url }) => {
      if (this.items.get(r.id) !== it) return;
      el.src = url;
      const done = () => { it.ready = true; this._place(it); this.sync(this.app.store.frame, !!this.app.playing); };
      if (r.kind === 'video') el.addEventListener('loadedmetadata', done, { once: true }); else el.addEventListener('load', done, { once: true });
    }).catch(() => {
      if (this.items.get(r.id) !== it) return;
      it.el.append(h('div', { class: 'ref-missing' }));
      console.warn('Reference file missing:', key);
    });
    return it;
  }

  _drop(id, it) {
    try { if (it.media && it.media.pause) it.media.pause(); } catch { /* gone */ }
    it.el && it.el.remove();
    if (it.mesh) { it.mesh.parent && it.mesh.parent.remove(it.mesh); it.mesh.geometry.dispose(); it.mesh.material.dispose(); }
    if (it.tex) it.tex.dispose();
    this.items.delete(id);
    // the file's object URL goes when nothing shows it any more
    if (![...this.items.values()].some(x => x.key === it.key) && this.media.has(it.key)) {
      this.media.get(it.key).then(m => URL.revokeObjectURL(m.url)).catch(() => {});
      this.media.delete(it.key);
    }
  }

  // Where and how a reference shows: overlay (screen) or board (scene).
  _place(it) {
    const r = it.ref, vis = r.visible !== false && !this.hidden;
    const ov = r.overlay || { x: 0.5, y: 0.5, scale: 1, lock: true };
    const overlay = r.mode !== 'board';
    it.el.style.display = overlay && vis ? '' : 'none';
    it.el.classList.toggle('sel', r.id === this.selectedId && !ov.lock);
    if (overlay) {
      const box = this.layer ? this.layer.getBoundingClientRect() : { width: 800, height: 600 };
      const aspect = r.w && r.h ? r.w / r.h : 16 / 9;
      const baseW = Math.min(box.width * 0.55, box.height * 0.8 * aspect);
      const w = baseW * (ov.scale || 1), hh = w / aspect;
      Object.assign(it.el.style, { left: `${ov.x * 100}%`, top: `${ov.y * 100}%`, width: `${w}px`, height: `${hh}px`, transform: 'translate(-50%, -50%)', opacity: String(r.opacity ?? 0.5) });
      // unlocked: handles to move and size it (the only parts that take the mouse)
      it.el.querySelectorAll('.grip, .mover').forEach(x => x.remove());
      if (!ov.lock) {
        const grip = h('div', { class: 'grip', title: 'Drag to make it bigger or smaller' }), mover = h('div', { class: 'mover', title: 'Drag to move it' });
        grip.addEventListener('pointerdown', e => this._dragOverlay(e, it, 'scale'));
        mover.addEventListener('pointerdown', e => this._dragOverlay(e, it, 'move'));
        it.el.append(mover, grip);
      }
    }
    // the board: a picture standing in the scene
    if (!overlay && it.ready) {
      if (!it.mesh) {
        it.tex = r.kind === 'video' ? new THREE.VideoTexture(it.media) : new THREE.Texture(it.media);
        it.tex.colorSpace = THREE.SRGBColorSpace;
        it.tex.needsUpdate = true;
        const mat = new THREE.MeshBasicMaterial({ map: it.tex, transparent: true, side: THREE.DoubleSide, depthWrite: false, toneMapped: false, fog: false });
        it.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat);
        it.mesh.renderOrder = -1;
        it.mesh.userData.refId = r.id;
        it.mesh.raycast = () => {};              // never picked as a body; boards are picked by _pick
        this.app.vp.scene.add(it.mesh);
      }
      const b = r.board || this._defaultBoard(r, 'front');
      const width = b.width || 1.6, height = width * ((r.h && r.w) ? r.h / r.w : 9 / 16);
      it.mesh.scale.set(width, height, 1);
      it.mesh.position.fromArray(b.pos || [0, height / 2, -1.3]);
      if (b.plane === 'floor') it.mesh.rotation.set(-Math.PI / 2, 0, b.yaw || 0);
      else it.mesh.rotation.set(0, b.yaw || 0, 0);
      it.mesh.material.opacity = r.opacity ?? 0.5;
      it.mesh.visible = vis;
    } else if (it.mesh) it.mesh.visible = false;
    if (this.app.vp && this.app.vp.requestRender) this.app.vp.requestRender();
  }

  _defaultBoard(r, plane) {
    const width = 1.6, height = width * ((r.h && r.w) ? r.h / r.w : 9 / 16);
    if (plane === 'side') return { plane, pos: [-1.5, height / 2, 0], yaw: Math.PI / 2, width };
    if (plane === 'floor') return { plane, pos: [0, 0.003, 0], yaw: 0, width };
    return { plane: 'front', pos: [0, height / 2, -1.3], yaw: 0, width };
  }

  _dragOverlay(e, it, what) {
    e.preventDefault(); e.stopPropagation();
    const r = it.ref, box = this.layer.getBoundingClientRect();
    const ov0 = clone(r.overlay || { x: 0.5, y: 0.5, scale: 1, lock: false });
    const x0 = e.clientX, y0 = e.clientY;
    let started = false;
    const move = ev => {
      if (!started) { this.app.store.checkpoint('Move reference'); started = true; }
      const cur = this.list.find(x => x.id === r.id);
      if (!cur) return;
      cur.overlay = cur.overlay || clone(ov0);
      if (what === 'move') { cur.overlay.x = Math.max(0, Math.min(1, ov0.x + (ev.clientX - x0) / box.width)); cur.overlay.y = Math.max(0, Math.min(1, ov0.y + (ev.clientY - y0) / box.height)); }
      else cur.overlay.scale = Math.max(0.15, Math.min(4, ov0.scale * (1 + (ev.clientX - x0 + ev.clientY - y0) / 300)));
      const item = this.items.get(r.id); if (item) { item.ref = cur; this._place(item); }
    };
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); if (started) { this._sig = ''; this.app.store.setDirty(true); } };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }

  // A click on a board picks it (the card shows in the right panel).
  _pick(e, kind) {
    if (kind !== 'click' || this.hidden) return false;
    const boards = [...this.items.values()].filter(it => it.mesh && it.mesh.visible);
    if (!boards.length) return false;
    const vp = this.app.vp, rect = vp.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    const ray = new THREE.Raycaster();
    ray.setFromCamera(ndc, vp.camera);
    let best = null;
    for (const it of boards) {
      const m = it.mesh, inv = m.matrixWorld.clone().invert();
      const o = ray.ray.origin.clone().applyMatrix4(inv), d = ray.ray.direction.clone().transformDirection(inv);
      if (Math.abs(d.z) < 1e-9) continue;
      const t = -o.z / d.z;
      if (t <= 0) continue;
      const p = o.add(d.multiplyScalar(t));
      if (Math.abs(p.x) <= 0.5 && Math.abs(p.y) <= 0.5) {
        const dist = m.getWorldPosition(new THREE.Vector3()).distanceTo(vp.camera.position);
        if (!best || dist < best.dist) best = { it, dist };
      }
    }
    // the bodies stay pickable in front of a board: a board only wins when nothing else is under the mouse
    if (!best) return false;
    const bodyHit = (() => { try { const r2 = new THREE.Raycaster(); r2.setFromCamera(ndc, vp.camera); return r2.intersectObjects(this.app.interact._meshes ? this.app.interact._meshes() : [], false).length > 0; } catch { return false; } })();
    if (bodyHit) return false;
    this.select(best.it.ref.id);
    return true;
  }

  // Videos follow the timeline: paused, the frame that belongs to the playhead; playing, they play along.
  sync(frame, playing) {
    const p = this.project, fps = p.fps || 30;
    for (const it of this.items.values()) {
      const r = it.ref, v = it.media;
      if (r.kind !== 'video' || !v || !it.ready) continue;
      v.muted = !r.sound;
      const dur = v.duration || r.duration || 0;
      const want = wrap((r.offset || 0) + (frame / fps) * (r.speed || 1), dur);
      if (!playing || this.hidden || r.visible === false) {
        if (!v.paused) v.pause();
        if (Math.abs(v.currentTime - want) > 0.25 / fps) v.currentTime = want;
      } else {
        v.playbackRate = Math.max(0.0625, Math.min(16, (this.app.speed || 1) * (r.speed || 1)));
        if (Math.abs(v.currentTime - want) > 2 / fps) v.currentTime = want;
        if (v.paused) v.play().catch(() => {});
      }
    }
  }

  select(id) {
    this.selectedId = id;
    for (const it of this.items.values()) this._place(it);
    this.app.refreshPanels();
  }

  // Settings from the inspector card (the caller made the undo step).
  update(id, patch) {
    const r = this.list.find(x => x.id === id);
    if (!r) return;
    Object.assign(r, patch);
    this.app.store.setDirty(true);
    this.load();
  }

  remove(id) {
    const r = this.list.find(x => x.id === id);
    if (!r) return;
    this.app.store.checkpoint('Remove reference');
    this.project.refs = this.list.filter(x => x.id !== id);
    if (this.selectedId === id) this.selectedId = null;
    this.load();
    this.app.refreshPanels();
    toast(`"${r.name}" removed. Ctrl+Z brings it back.`);
  }

  boardMoved(id) {
    const it = this.items.get(id), r = this.list.find(x => x.id === id);
    if (!it || !it.mesh || !r) return;
    const b = r.board || this._defaultBoard(r, 'front');
    b.pos = it.mesh.position.toArray();
    b.yaw = b.plane === 'floor' ? it.mesh.rotation.z : it.mesh.rotation.y;
    r.board = b;
    this._sig = '';
    this.app.store.setDirty(true);
  }

  // Out of the way while recording a video.
  setHidden(on) {
    this.hidden = !!on;
    document.body.classList.toggle('ref-hidden', this.hidden);
    for (const it of this.items.values()) this._place(it);
    this.sync(this.app.store.frame, !!this.app.playing);
  }

  // Pictures and videos dropped on the view (or picked with the button): each is uploaded and becomes a reference.
  async addFiles(files) {
    const p = this.project;
    const ok = [...files].filter(f => KINDS[f.type]);
    if (!ok.length) return toast('Use a picture (PNG, JPG, WEBP, GIF) or a video (MP4, WEBM).');
    let added = 0;
    for (const f of ok) {
      if (f.size > MAX_BYTES) { toast(`"${f.name}" is too big for a reference (over 400 MB).`, 'err'); continue; }
      let res;
      try { res = await api.uploadRef(p.uid, f); }
      catch (err) { toast(`Could not add "${f.name}": ${err.message || err}`, 'err'); continue; }
      const kind = KINDS[f.type];
      const meta = await readMeta(f, kind).catch(() => ({}));
      if (this.project !== p) return;                      // another animation was opened meanwhile
      const first = !(p.refs || []).length && !added;
      const r = { id: uidRef(), name: f.name, kind, file: res.file, dir: p.uid, w: meta.w || 16, h: meta.h || 9,
        mode: first ? 'overlay' : 'board', visible: true, opacity: 0.5, offset: 0, speed: 1, sound: false,
        overlay: { x: 0.5, y: 0.5, scale: 1, lock: true } };
      if (kind === 'video') r.duration = meta.duration || 0;
      r.board = this._defaultBoard(r, 'front');
      this.app.store.checkpoint('Add reference');
      p.refs = [...(p.refs || []), r];
      this.selectedId = r.id;
      added++;
    }
    if (!added) return;
    this.load();
    this.app.refreshPanels();
    toast(added > 1 ? `${added} references added - they show on the right to change them.` : 'Reference added: it shows see-through over the view. Change it on the right (screen or scene, see-through, video timing).', 'ok');
  }

  // ---------------------------------------------------------------- the inspector card (spec 8.4)
  _card(root) {
    const list = this.list;
    if (!list.length) return;
    const r = this.selected;
    const sec = h('div', { class: 'section ref-card' });
    sec.append(h('div', { class: 'section-title' }, 'Reference', h('span', { class: 'count' }, String(list.length))));
    // one chip per reference
    sec.append(h('div', { class: 'pose-chips' }, list.map(x => h('button', { class: 'chipbtn' + (x.id === this.selectedId ? ' on' : ''), title: x.name,
      onclick: () => this.select(x.id === this.selectedId ? null : x.id) }, icon(x.kind === 'video' ? 'film' : 'image'), ' ', x.name.length > 16 ? x.name.slice(0, 15) + '…' : x.name))));
    if (!r) { sec.append(h('div', { class: 'hint' }, 'Click one to change it. Drop more pictures or videos on the view.')); root.append(sec); return; }
    const card = h('div', { class: 'card' });
    const set = (patch, label = 'Change reference') => { this.app.store.checkpoint(label); this.update(r.id, patch); this.app.refreshPanels(); };
    card.append(h('div', { class: 'field' }, h('span', {}, 'Show it'), h('div', { class: 'seg-inline' },
      h('button', { class: r.mode !== 'board' ? 'on' : '', onclick: () => set({ mode: 'overlay' }) }, 'On the screen'),
      h('button', { class: r.mode === 'board' ? 'on' : '', onclick: () => set({ mode: 'board', board: r.board || this._defaultBoard(r, 'front') }) }, 'In the scene'))));
    card.append(slider({ label: 'See-through', min: 0.05, max: 1, step: 0.01, value: r.opacity ?? 0.5, fmt: v => Math.round(v * 100) + '%',
      onStart: () => this.app.store.checkpoint('Reference see-through'), onInput: v => { r.opacity = v; this._sig = ''; this.load(); this.app.store.setDirty(true); } }));
    if (r.mode !== 'board') {
      const ov = r.overlay || { x: 0.5, y: 0.5, scale: 1, lock: true };
      card.append(h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Stay put'), h('span', {}, 'Off: drag it round the view and size it with its corner')),
        toggle(ov.lock !== false, on => set({ overlay: { ...ov, lock: on } }))));
    } else {
      const b = r.board || this._defaultBoard(r, 'front');
      card.append(h('div', { class: 'field' }, h('span', {}, 'Stand it'), h('div', { class: 'seg-inline' },
        ...[['front', 'In front'], ['side', 'At the side'], ['floor', 'On the floor']].map(([pl, t]) => h('button', { class: b.plane === pl ? 'on' : '', onclick: () => set({ board: this._defaultBoard(r, pl) }) }, t)))));
      const nudge = (label, get, put, min, max, step, fmt) => slider({ label, min, max, step, value: get(), fmt,
        onStart: () => this.app.store.checkpoint('Move reference'), onInput: v => { const nb = clone(r.board || b); put(nb, v); r.board = nb; this._sig = ''; this.load(); this.app.store.setDirty(true); } });
      card.append(nudge('Size', () => b.width || 1.6, (nb, v) => { nb.width = v; }, 0.3, 4, 0.05, v => v.toFixed(2) + ' m'),
        nudge('Left / right', () => b.pos[0], (nb, v) => { nb.pos = [v, nb.pos[1], nb.pos[2]]; }, -3, 3, 0.01, v => v.toFixed(2) + ' m'),
        nudge(b.plane === 'floor' ? 'Forward / back' : 'Height', () => (b.plane === 'floor' ? b.pos[2] : b.pos[1]), (nb, v) => { if (nb.plane === 'floor') nb.pos = [nb.pos[0], nb.pos[1], v]; else nb.pos = [nb.pos[0], v, nb.pos[2]]; }, -3, 3, 0.01, v => v.toFixed(2) + ' m'),
        b.plane === 'floor' ? null : nudge('Forward / back', () => b.pos[2], (nb, v) => { nb.pos = [nb.pos[0], nb.pos[1], v]; }, -4, 4, 0.01, v => v.toFixed(2) + ' m'),
        nudge('Turn', () => Math.round((b.yaw || 0) * 180 / Math.PI), (nb, v) => { nb.yaw = v * Math.PI / 180; }, -180, 180, 1, v => v + '°'));
      const it = this.items.get(r.id), gz = this.app.interact && this.app.interact.attachGizmo;
      if (gz && it && it.mesh) card.append(h('button', { class: 'btn small soft block', onclick: () => {
        this.app.interact.attachGizmo(it.mesh, { modes: ['translate', 'rotate'], onStart: () => this.app.store.checkpoint('Move reference'), onChange: () => this.boardMoved(r.id), onEnd: () => { this.boardMoved(r.id); this.app.refreshPanels(); } });
        toast('Drag the arrows to move the board (T: turn it).');
      } }, icon('move'), 'Move it with the arrows'));
    }
    if (r.kind === 'video') {
      const fps = this.project.fps || 30;
      const start = h('input', { class: 'num', type: 'number', min: 0, step: 0.1, value: (r.offset || 0).toFixed(1) });
      start.addEventListener('change', () => { set({ offset: Math.max(0, +start.value || 0) }, 'Video start'); start.blur(); });
      card.append(h('label', { class: 'field row' }, h('span', {}, 'Video starts at (s)'), start));
      card.append(slider({ label: 'Video speed', min: 0.25, max: 2, step: 0.05, value: r.speed || 1, fmt: v => v.toFixed(2).replace(/0$/, '') + '×',
        onStart: () => this.app.store.checkpoint('Video speed'), onInput: v => { r.speed = v; this._sig = ''; this.load(); this.app.store.setDirty(true); } }));
      card.append(h('div', { class: 'toggle-row' }, h('div', {}, h('b', {}, 'Hear the video')), toggle(!!r.sound, on => set({ sound: on }))));
      card.append(h('div', { class: 'hint' }, `← → step the video one frame at a time (${fps} frames a second), so you can trace it.`));
    }
    card.append(h('div', { class: 'btn-grid' },
      h('button', { class: 'btn small', onclick: () => set({ visible: r.visible === false }) }, icon(r.visible === false ? 'eye' : 'eye-off'), r.visible === false ? 'Show' : 'Hide'),
      h('button', { class: 'btn small', onclick: () => this.remove(r.id) }, icon('trash'), 'Remove')));
    card.querySelectorAll('input[type=range]').forEach(fillRange);
    sec.append(card);
    root.append(sec);
  }
}

// Width, height (and a video's length) of a local file, read in the browser.
function readMeta(file, kind) {
  return new Promise((res, rej) => {
    const url = URL.createObjectURL(file);
    const done = x => { URL.revokeObjectURL(url); res(x); };
    if (kind === 'video') {
      const v = document.createElement('video');
      v.preload = 'metadata'; v.muted = true;
      v.onloadedmetadata = () => done({ w: v.videoWidth, h: v.videoHeight, duration: v.duration });
      v.onerror = () => { URL.revokeObjectURL(url); rej(new Error('not a video')); };
      v.src = url;
    } else {
      const im = new Image();
      im.onload = () => done({ w: im.naturalWidth, h: im.naturalHeight });
      im.onerror = () => { URL.revokeObjectURL(url); rej(new Error('not a picture')); };
      im.src = url;
    }
  });
}
